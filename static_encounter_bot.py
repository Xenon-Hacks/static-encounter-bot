"""
static_encounter_bot.py -- shiny-hunts a stationary (static) wild encounter
in Pokemon Crystal by soft-resetting: save your game standing right in
front of the Pokemon, and every attempt is reset -> mash A through the
boot logos, title screen, CONTINUE, and any pre-battle dialogue -> the
battle starts on its own, no walking involved.

Shininess comes from the shiny animation: a shiny wild Pokemon makes the
whole battle screen flash to a photo-negative for an instant before its
HP box appears; a normal one doesn't (see shiny_flash.py). No Pokemon
graphics are used. Battle Scene must be ON in the game's OPTIONS.

Run calibrate.py first. Then:
    py static_encounter_bot.py --ip <3ds ip>

Safety rules:
  * The only inputs this bot ever sends are A (mashed through the
    pre-battle screens) and the A+B+SELECT+START soft-reset combo.
    Never a direction, never any other single button -- so it can
    never walk the character or move a menu cursor onto something
    unintended.
  * There's no flee: a "normal" encounter is handled by soft-resetting
    again immediately, which reloads the exact same save. Nothing here
    ever risks a wrong menu selection the way navigating to RUN would.
  * It only reads pixels off your screen (or the frame-sharing NTR
    Viewer) and sends button presses -- it never touches your ROM or
    save file itself.
"""

import argparse
import json
import os
import sys
import time
import traceback
import faulthandler

from luma_input import Luma3DSInput, Button
import cv2

from vision import Capture, match_score
import gb_screen
from frame_recorder import RecordingCapture
import shared_frame
import reset_menu
import watch
import ntr_status
import session_log

CONFIG_PATH = "config.json"

BATTLE_MATCH_THRESHOLD = 0.35  # see the same constant in the Sweet Scent
                               # bot -- watch the printed
                               # (battle-indicator match: X.XX) lines and
                               # nudge this if it ever misfires
MAX_RESET_FAILURES = 3         # pause for you after this many soft resets
                               # in a row never reach a battle
TRANSIENT_ERROR_PAUSE = 2.0    # brief pause after an unexpected exception
                               # (a dropped capture frame, a momentary
                               # Windows BitBlt failure, ...) before
                               # retrying, so a persistent problem doesn't
                               # spam the log at full speed while still
                               # counting toward MAX_RESET_FAILURES


def load_config():
    try:
        with open(CONFIG_PATH) as f:
            cfg = json.load(f)
    except FileNotFoundError:
        print(f"{CONFIG_PATH} not found -- run calibrate.py first.")
        sys.exit(1)
    required = ["battle_indicator_roi"]
    if cfg.get("frame_source", "screen") != "shared":
        required.append("capture_region")
    for key in required:
        if key not in cfg:
            print(f"config.json is missing '{key}' -- run calibrate.py first.")
            sys.exit(1)
    if not os.path.exists("ref_battle.png"):
        print("ref_battle.png not found -- run calibrate.py first.")
        sys.exit(1)
    return cfg


def make_capture(cfg):
    """Where the bot gets its picture: the frame-sharing NTRViewer-HR build
    (works while NTR Viewer is minimised) or a fixed area of the screen."""
    if cfg.get("frame_source", "screen") == "shared":
        cap = shared_frame.SharedFrameCapture(rotation=cfg.get("shared_rotation", 1))
        print("Reading frames from the frame-sharing NTR Viewer (it can be "
              "minimised)...")
        if not shared_frame.wait_until_available(cap, timeout=15.0):
            print("No frames from the frame-sharing NTR Viewer. Start that "
                  "build of NTRViewer-HR, connect it to the 3DS, and run the "
                  "bot again. (py test_shared_frame.py checks the connection.)")
            sys.exit(1)
        ntr_status.shared_source = cap
        return cap
    print("Reading frames from the screen (NTR Viewer must stay visible and "
          "in place).")
    return Capture(cfg["capture_region"])


def wait_until_fully_shown(cap, timeout=8.0):
    """Waits until "Wild X appeared!" is in the battle text box. The shiny
    animation always plays before that text prints, so by then every frame
    the flash could be in has been recorded. Returns the current frame."""
    end = time.time() + timeout
    while time.time() < end:
        _heartbeat()
        frame = cap.frame()
        if gb_screen.battle_text_shown(gb_screen.native(frame)):
            return frame
        time.sleep(0.05)
    print("(text box never filled -- checking anyway)", end=" ", flush=True)
    return cap.frame()


def save_encounter_picture(frame, kind):
    """Keeps a screenshot of anything the bot stops for."""
    os.makedirs("alerts", exist_ok=True)
    path = os.path.join("alerts", time.strftime(f"%Y%m%d_%H%M%S_{kind}.png"))
    cv2.imwrite(path, frame)
    return path


_last_status_print = 0.0


HANG_REPORT_AFTER = 180   # seconds with no progress before writing a report
_hang_log = open("hang_report.txt", "a")


def _disable_console_select_freeze():
    """Windows consoles have a 'QuickEdit' mode: clicking in the window
    starts a text selection, and the program FREEZES on its next print
    until Enter/Esc is pressed. This switches QuickEdit off for this
    window only, while the bot runs. Harmless no-op elsewhere."""
    if os.name != "nt":
        return
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-10)          # console input
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            ENABLE_QUICK_EDIT_MODE, ENABLE_EXTENDED_FLAGS = 0x0040, 0x0080
            kernel32.SetConsoleMode(
                handle, (mode.value | ENABLE_EXTENDED_FLAGS) & ~ENABLE_QUICK_EDIT_MODE)
            print("(Console click-to-select disabled so a stray click "
                  "can't freeze the bot.)")
    except Exception:
        pass  # never let this stop the bot from running


def _heartbeat():
    """Re-arms the watchdog. faulthandler runs on its own C-level thread,
    so it still works if the bot freezes inside a screen grab or a
    blocked terminal write. If no heartbeat arrives within
    HANG_REPORT_AFTER seconds, it writes the exact line the bot is stuck
    on to hang_report.txt (repeating every HANG_REPORT_AFTER while
    stuck)."""
    faulthandler.dump_traceback_later(HANG_REPORT_AFTER, repeat=True,
                                      file=_hang_log)


def _wait_for_enter(prompt):
    """A deliberate pause is not a hang, so disarm the watchdog while
    waiting for you, and re-arm it afterwards."""
    faulthandler.cancel_dump_traceback_later()
    try:
        return input(prompt)
    finally:
        _heartbeat()


def in_battle(cap: Capture, cfg: dict) -> bool:
    """Also prints the raw match score every couple of seconds (even while
    mashing through the pre-battle screens) so a silent hang is visible/
    debuggable instead of a total black box -- if the score never gets
    anywhere near BATTLE_MATCH_THRESHOLD even during a real battle,
    that's a miscalibrated battle_indicator_roi, not a stuck script."""
    global _last_status_print
    _heartbeat()
    frame = cap.frame()
    score = match_score(frame, cfg["battle_indicator_roi"], "ref_battle.png")
    result = score >= BATTLE_MATCH_THRESHOLD
    now = time.time()
    if now - _last_status_print > 2.0:
        flag = " [BATTLE]" if result else ""
        print(f"  (battle-indicator match: {score:.2f}{flag})", flush=True)
        _last_status_print = now
    return result


def pause_for_user(pad, message):
    print(f"\n*** [{time.strftime('%H:%M:%S')}] {message} ***")
    print("The bot is NOT sending any buttons now; it's waiting for you to "
          "press ENTER in this window.")
    pad.release_all()
    pad.send()
    pad.return_control()
    _wait_for_enter("Press ENTER to resume (Ctrl+C instead to quit): ")


def ntr_dead_message():
    """Says WHICH problem caused the pause (ntr_status.last_reason)."""
    reason = ntr_status.last_reason or "0%"
    what = {"not responding": "NTR-VC / NTR Viewer has stopped responding "
                              "(Windows reports it as Not Responding)",
            "closed": "NTR-VC / NTR Viewer has been closed",
            "frozen": "NTR-VC has stopped updating (its heartbeat stalled)",
            "0%": "NTR Viewer has shown Connection Quality 0.0% -- the 3DS "
                  "has probably frozen or disconnected"}[reason]
    return (f"{what}, for 30 seconds straight. The bot pressed nothing while "
            f"the picture couldn't be trusted. PAUSED. Get NTR-VC and the 3DS "
            f"running and streaming again, then press ENTER (the bot will "
            f"soft-reset and start fresh).")


def wait_for_live_stream(pad):
    """If NTR Viewer reports a dead stream, pause (repeatedly, until it's
    alive again). Returns True if it had to pause."""
    paused = False
    while ntr_status.stream_dead(heartbeat=_heartbeat):
        pause_for_user(pad, ntr_dead_message())
        paused = True
    return paused


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ip", required=True,
                         help="3DS IP address, shown in Rosalina's "
                              "InputRedirection screen")
    args = parser.parse_args()
    log_path = session_log.start(prefix="static_encounter")
    _disable_console_select_freeze()
    print(f"Logging this session to {log_path}")

    cfg = load_config()
    cap = RecordingCapture(make_capture(cfg))
    pad = Luma3DSInput(args.ip)
    watch.install(pad)       # presses from every code path take turns
    print("Shiny check: watching for the shiny flash (Battle Scene must be "
          "ON in the game's OPTIONS).")
    print("Make sure your save is standing right in front of the static "
          "encounter, in the overworld, with no menu open. The bot will "
          "soft-reset from here on, so THIS is the state every attempt "
          "returns to.")

    encounters = 0
    reset_failures = 0
    start = time.time()

    try:
        _hang_log.write(f"\n=== session started {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
        _hang_log.flush()
        _heartbeat()
        while True:
            try:
                if wait_for_live_stream(pad):
                    reset_failures = 0
                cap.clear()      # this attempt's frames only
                reset_menu.soft_reset(pad)
                if not reset_menu.mash_to_battle(pad, cap, cfg, in_battle, _heartbeat):
                    if wait_for_live_stream(pad):     # the real reason it failed
                        reset_failures = 0
                        continue
                    reset_failures += 1
                    if reset_failures >= MAX_RESET_FAILURES:
                        pause_for_user(pad, f"No battle after {reset_failures} soft "
                                       f"resets in a row -- PAUSED. Check that the "
                                       f"save is standing right in front of the "
                                       f"encounter and that CONTINUE (not NEW GAME) "
                                       f"is what gets selected.")
                        reset_failures = 0
                    continue
                reset_failures = 0

                # Until "Wild X appeared!" has printed: the shiny flash, if
                # any, has played by then.
                ntr_status.wait_for_good_quality(heartbeat=_heartbeat)
                frame = wait_until_fully_shown(cap)
                encounters += 1
                elapsed_min = (time.time() - start) / 60
                print(f"[{elapsed_min:.1f} min] Encounter #{encounters}...", end=" ")

                result = cap.analyse()
                kind = result["verdict"]
                if kind == "normal":
                    print(f"normal ({result['reason']}). Resetting.")
                    # No flee needed: the next loop iteration soft-resets right
                    # back to the same save, standing in front of the encounter.
                    continue
                picture = save_encounter_picture(frame, kind)
                if kind == "shiny":
                    print(f"SHINY! ({result['reason']})")
                    message = (f"SHINY! The shiny flash played ({result['reason']}). "
                               f"Take over now! Screenshot: {picture}.")
                else:
                    print(f"can't tell: {result['reason']}.")
                    message = (f"COULDN'T TELL whether this one is shiny: "
                               f"{result['reason']}. Check it yourself. Screenshot: "
                               f"{picture}. If it's normal, press ENTER and the bot "
                               f"will soft-reset and keep going.")
                pause_for_user(pad, message)
                # Whatever's on screen now, the top of the loop soft-resets
                # unconditionally -- so resuming is always safe here.
                continue

            except Exception:
                # A transient hiccup here -- a dropped screen-capture frame,
                # a momentary Windows BitBlt/GDI failure, a vision-math edge
                # case on a blank or corrupt frame -- must never take the
                # whole unattended run down. This isn't hypothetical: two
                # different uncaught exceptions (mss.ScreenShotError: BitBlt
                # access denied; a ValueError in sprite_id.find_game, now gb_screen, on a
                # degenerate frame) actually crashed the process overnight
                # on 2026-09-28/29, sitting dead for hours until someone
                # noticed and restarted it by hand. Log the full traceback
                # so it's still visible in session_log.py, then treat it
                # exactly like a failed attempt -- a short pause, then let
                # the top of the loop soft-reset and try again.
                print(f"\n*** [{time.strftime('%H:%M:%S')}] Unexpected error during "
                      f"this attempt -- NOT stopping the run, treating it like a "
                      f"failed attempt and soft-resetting. Full traceback for "
                      f"diagnosis: ***")
                traceback.print_exc()
                time.sleep(TRANSIENT_ERROR_PAUSE)
                reset_failures += 1
                if reset_failures >= MAX_RESET_FAILURES:
                    pause_for_user(pad, f"{reset_failures} unexpected errors/failed "
                                   f"attempts in a row -- PAUSED. This may be more "
                                   f"than a one-off glitch (NTR Viewer, the capture "
                                   f"region, or the 3DS itself) -- check the "
                                   f"traceback above or in logs/ before resuming.")
                    reset_failures = 0
                continue

    except KeyboardInterrupt:
        elapsed_min = (time.time() - start) / 60
        print(f"\nStopped after {encounters} encounters in {elapsed_min:.1f} min.")
    finally:
        cap.close()
        pad.close()


if __name__ == "__main__":
    main()
