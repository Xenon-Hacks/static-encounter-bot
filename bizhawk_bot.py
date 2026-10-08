"""
bizhawk_bot.py -- the static-encounter soft-reset shiny hunter, running
Pokemon Crystal in the BizHawk emulator instead of on the 3DS.

Same idea as static_encounter_bot.py: your save stands right in front of
the static Pokemon; every attempt is soft reset -> mash A -> battle starts
-> shiny or not -> reset. The differences:

  * BizHawk runs the game one frame at a time for the bot (through
    bizhawk/bridge.lua), so every single frame is seen. The shiny flash
    lasts 5 frames; here it can't be missed.
  * It runs as fast as your PC allows, not at real-time speed.
  * Nothing to calibrate: the bot gets the exact 160x144 picture.

Shininess comes from the shiny animation's flash (shiny_flash.py). No
Pokemon graphics are used. Battle Scene must be ON in the game's OPTIONS;
the bot checks and tells you if it isn't.

Usage (Windows):
    py bizhawk_bot.py --emuhawk C:\\path\\to\\EmuHawk.exe --rom C:\\path\\to\\crystal.gbc

or start EmuHawk yourself with the command the bot prints when run
without --emuhawk.

Emulators are exact: the same button presses at the same frames give the
same Pokemon every time. So the bot waits a random number of frames after
each reset and mashes A at a random pace, which lands each battle on a
different frame and gives a different Pokemon.
"""

import argparse
import os
import random
import subprocess
import sys
import time

import cv2

import bizhawk_link
import gb_screen
import session_log
import shiny_flash

PORT = 43885
CONNECT_TIMEOUT = 120         # s to wait for EmuHawk to connect
RESET_BUTTONS = ("A", "B", "Select", "Start")
RESET_HOLD = 6                # frames the soft-reset combo is held
MAX_RESET_WAIT = 300          # frames for the reset to take effect
RANDOM_DELAY = (0, 120)       # frames waited after each reset before mashing
MASH_HOLD = 2                 # frames A is held per press
MASH_GAP = (2, 6)             # frames between presses (random each time)
MASH_TIMEOUT = 60 * 60        # frames (1 min of game time) to reach a battle
TEXT_TIMEOUT = 60 * 20        # frames from battle start to "Wild X appeared!"
MAX_RESET_FAILURES = 3


class Attempt:
    """Everything seen during one attempt."""

    def __init__(self):
        self.recorder = shiny_flash.FlashRecorder(keep_seconds=1e9)
        self.last = None

    def see(self, obs):
        self.last = obs
        self.recorder.add(obs.state.frame / 60.0, gb_screen.native(obs.image))
        return obs


def soft_reset(link, obs):
    """A+B+SELECT+START, then waits for the game to have really restarted
    (out of battle)."""
    obs = link.step(RESET_BUTTONS, RESET_HOLD)
    for _ in range(MAX_RESET_WAIT):
        if obs.state.battle_mode == 0:
            break
        obs = link.step((), 1)
    return obs


def mash_to_battle(link, attempt, rng):
    """Waits a random number of frames, then mashes A until a battle has
    started (wBattleMode set). Never presses anything but A. Returns the
    first in-battle Observation, or None on timeout."""
    obs = attempt.see(link.step((), rng.randint(*RANDOM_DELAY) + 1))
    frames = 0
    while frames < MASH_TIMEOUT:
        if obs.state.battle_mode != 0:
            return obs
        # A for MASH_HOLD frames, one frame at a time so every frame is seen
        for _ in range(MASH_HOLD):
            obs = attempt.see(link.step(("A",), 1))
            frames += 1
            if obs.state.battle_mode != 0:
                return obs
        for _ in range(rng.randint(*MASH_GAP)):
            obs = attempt.see(link.step((), 1))
            frames += 1
            if obs.state.battle_mode != 0:
                return obs
    return None


def watch_battle_intro(link, attempt, obs):
    """Presses nothing and records every frame until "Wild X appeared!" is
    in the text box (the shiny animation always plays before it). Returns
    the last Observation and whether the text was reached."""
    for _ in range(TEXT_TIMEOUT):
        if gb_screen.battle_text_shown(gb_screen.native(obs.image)):
            return obs, True
        obs = attempt.see(link.step((), 1))
    return obs, False


def save_picture(image, kind):
    os.makedirs("alerts", exist_ok=True)
    path = os.path.join("alerts", time.strftime(f"%Y%m%d_%H%M%S_{kind}.png"))
    cv2.imwrite(path, cv2.resize(image, (image.shape[1] * 3, image.shape[0] * 3),
                                 interpolation=cv2.INTER_NEAREST))
    return path


def start_emuhawk(args, port):
    lua = os.path.abspath(os.path.join(os.path.dirname(__file__), "bizhawk", "bridge.lua"))
    cmd = [args.emuhawk, "--socket_ip=127.0.0.1", f"--socket_port={port}",
           f"--lua={lua}"]
    if args.rom:
        cmd.append(args.rom)
    if args.emuhawk:
        print("Starting EmuHawk...")
        subprocess.Popen(cmd, cwd=os.path.dirname(os.path.abspath(args.emuhawk)))
    else:
        shown = ["EmuHawk.exe"] + [f'"{c}"' if " " in c else c for c in cmd[1:]]
        print("Start EmuHawk now with:\n    " + " ".join(shown)
              + ("" if args.rom else " <your Crystal ROM>"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--emuhawk", help="path to EmuHawk.exe (the bot starts it)")
    parser.add_argument("--rom", help="path to your Pokemon Crystal ROM (.gbc)")
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--check-dvs", action="store_true",
                        help="also read the Pokemon's DVs from RAM and stop if "
                             "they ever disagree with the flash")
    parser.add_argument("--seed", type=int, help="fixed random seed (testing)")
    args = parser.parse_args()

    log_path = session_log.start(prefix="bizhawk_static")
    print(f"Logging this session to {log_path}")
    rng = random.Random(args.seed)

    link = bizhawk_link.BizHawkLink(args.port)
    start_emuhawk(args, args.port)
    print(f"Waiting for EmuHawk to connect on port {args.port}...")
    if not link.accept(CONNECT_TIMEOUT):
        print("EmuHawk never connected. It must be started with the "
              "--socket_ip/--socket_port/--lua options shown above.")
        sys.exit(1)
    print("Connected. Make sure your save is standing right in front of the "
          "static encounter -- every attempt soft-resets back to it.")

    encounters, failures = 0, 0
    start = time.time()
    obs = link.observe()
    try:
        while True:
            attempt = Attempt()
            obs = soft_reset(link, obs)
            battle = mash_to_battle(link, attempt, rng)
            if battle is None:
                failures += 1
                print("  No battle within a minute of game time -- resetting.")
                if failures >= MAX_RESET_FAILURES:
                    print("*** No battle after 3 resets in a row. Check that the "
                          "save stands right in front of the encounter and that "
                          "CONTINUE is what gets selected. Stopping. ***")
                    break
                obs = attempt.last
                continue
            failures = 0
            if battle.state.options & bizhawk_link.BATTLE_SCENE_OFF:
                print("*** Battle Scene is OFF in this save's OPTIONS. The game "
                      "skips the shiny animation then, so the bot can't see "
                      "shinies. Turn it ON, save, and start the bot again. ***")
                link.stop()
                return
            obs, text = watch_battle_intro(link, attempt, battle)
            encounters += 1
            minutes = (time.time() - start) / 60
            print(f"[{minutes:.1f} min] Encounter #{encounters}...", end=" ")
            if not text:
                result = {"verdict": "unsure",
                          "reason": "the battle text never appeared"}
            else:
                result = attempt.recorder.analyse(frame_exact=True)
            dv_shiny = bizhawk_link.is_shiny_dvs(obs.state.dv1, obs.state.dv2)
            kind = result["verdict"]
            if args.check_dvs and kind != "unsure" and (kind == "shiny") != dv_shiny:
                print(f"\n*** The flash says {kind} but the DVs "
                      f"({obs.state.dv1:02X} {obs.state.dv2:02X}) say "
                      f"{'shiny' if dv_shiny else 'normal'}. Stopping so you can "
                      f"look. ***")
                kind = "disagree"
            if kind == "normal":
                print(f"normal ({result['reason']}). Resetting.")
                continue
            picture = save_picture(obs.image, kind)
            if kind == "shiny":
                print(f"SHINY! ({result['reason']})")
            elif kind == "unsure":
                print(f"can't tell: {result['reason']}.")
            print(f"Screenshot: {picture}. EmuHawk is paused on the battle; "
                  f"it's yours now.")
            link.stop()
            return
    except KeyboardInterrupt:
        link.stop()
    except bizhawk_link.LinkClosed as e:
        print(f"\nLost EmuHawk: {e}")
    finally:
        minutes = (time.time() - start) / 60
        print(f"\nStopped after {encounters} encounters in {minutes:.1f} min.")
        link.close()


if __name__ == "__main__":
    main()
