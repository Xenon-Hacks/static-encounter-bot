"""
calibrate.py -- one-time setup helper. Run this BEFORE static_encounter_bot.py.

Much shorter than the Sweet Scent/master calibration: this bot never
navigates a menu and never flees, so it only needs to know (1) where to
read the picture from and (2) how to tell "still on the pre-battle
screens" from "battle has started". Everything else (species/shininess)
reuses the NORMAL/SHINY sprite folders, which you copy over rather than
calibrate.

Have NTR Viewer open and showing the 3DS top screen before you start (or
the frame-sharing build running, for --shared).

Usage:
    py calibrate.py            full setup (capture region + battle indicator)
    py calibrate.py --battle   redo just the battle indicator
    py calibrate.py --shared   switch to the frame-sharing NTR Viewer
    py calibrate.py --screen   switch back to reading the screen
"""

import argparse
import json
import sys
import time

import cv2
import mss
import numpy as np

CONFIG_PATH = "config.json"
CAPTURE_DELAY = 3  # seconds you get to switch back to NTR Viewer before each shot


def wait_then_switch(prompt):
    """Prompts, waits for ENTER, then gives you CAPTURE_DELAY seconds to
    click back onto NTR Viewer before the screenshot is taken. Needed
    because pressing ENTER means clicking into this terminal, which would
    otherwise be the frontmost window at the exact moment of capture."""
    input(prompt)
    print(f"Capturing in {CAPTURE_DELAY}s -- click/alt-tab to NTR Viewer now!")
    time.sleep(CAPTURE_DELAY)


def choose_monitor():
    """Lists real monitors (mss index 0 is the "all combined" pseudo-
    monitor, which can crash cv2's window on multi-monitor systems if used
    directly) and lets you pick the one NTR Viewer is showing on."""
    with mss.mss() as sct:
        real_monitors = sct.monitors[1:]
    if len(real_monitors) == 1:
        return real_monitors[0]
    print("Multiple monitors detected:")
    for i, m in enumerate(real_monitors, start=1):
        print(f"  {i}: {m['width']}x{m['height']} at "
              f"({m['left']}, {m['top']})")
    while True:
        choice = input(f"Which monitor is NTR Viewer on? [1-{len(real_monitors)}]: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(real_monitors):
            return real_monitors[int(choice) - 1]
        print("Enter one of the numbers above.")


def grab_full_screen(mon):
    with mss.mss() as sct:
        shot = sct.grab(mon)
        img = np.array(shot)
        return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR), mon


def select_region(prompt, img):
    print(prompt)
    print("Drag a box, then press ENTER or SPACE to confirm (C to cancel).")
    r = cv2.selectROI("calibrate - " + prompt, img, showCrosshair=True)
    cv2.waitKey(1)  # let the window finish one more redraw before closing --
                     # skipping this can crash/hang cv2's GUI teardown on Windows
    cv2.destroyAllWindows()
    cv2.waitKey(1)
    x, y, w, h = (int(v) for v in r)
    print(f"Got a {w}x{h} box at ({x}, {y}).")
    return x, y, w, h


def load_config():
    try:
        with open(CONFIG_PATH) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def save_config(cfg):
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)
    print(f"Saved {CONFIG_PATH}")


_shared_cap = None


def capture_region_frame(cfg):
    """The picture every calibration step works on: from the frame-sharing
    NTR Viewer (frame_source "shared") or the calibrated screen area."""
    global _shared_cap
    if cfg.get("frame_source") == "shared":
        import shared_frame
        if _shared_cap is None:
            _shared_cap = shared_frame.SharedFrameCapture(rotation=cfg.get("shared_rotation", 1))
            if not shared_frame.wait_until_available(_shared_cap, timeout=15.0):
                raise SystemExit("No frames from the frame-sharing NTR Viewer -- "
                                 "start it, connect it to the 3DS, and try again "
                                 "(py test_shared_frame.py checks the connection).")
        return _shared_cap.frame()
    with mss.mss() as sct:
        return cv2.cvtColor(np.array(sct.grab(cfg["capture_region"])),
                             cv2.COLOR_BGRA2BGR)


def calibrate_capture_region(cfg, mon):
    wait_then_switch(
        "Press ENTER, then immediately switch to the NTR Viewer window "
        "so it's fully visible and in front: ")
    img, mon = grab_full_screen(mon)
    x, y, w, h = select_region(
        "Drag a box around the WHOLE NTR Viewer game view (top screen).",
        img)
    if w == 0 or h == 0:
        print("Empty selection, aborting.")
        sys.exit(1)
    cfg["capture_region"] = {
        "left": mon["left"] + x, "top": mon["top"] + y,
        "width": w, "height": h,
    }
    save_config(cfg)
    return cfg


def calibrate_battle_indicator(cfg):
    """A small region, relative to capture_region, that looks visibly
    different on the overworld/pre-battle screens vs. mid-battle -- e.g. a
    corner where the HP box appears. Captured twice: once now, once once
    you're in the static encounter's battle.

    Since this bot never sees a "normal" overworld screen (every attempt
    starts from a reset and goes straight to the encounter), the first
    shot can be taken from anywhere pre-battle -- the title screen, the
    loading flash, or standing in front of the encounter all work, as
    long as it's clearly NOT the battle screen."""
    wait_then_switch(
        "Get the game to any PRE-BATTLE screen (e.g. standing in front of "
        "the encounter, or the title screen), then press ENTER here: ")
    frame = capture_region_frame(cfg)
    x, y, w, h = select_region(
        "Drag a box around a spot that will clearly change once the "
        "battle starts (e.g. where the HP box appears).", frame)
    if w == 0 or h == 0:
        print("Empty selection, aborting.")
        sys.exit(1)
    roi = {"left": x, "top": y, "width": w, "height": h}
    cfg["battle_indicator_roi"] = roi
    cv2.imwrite("ref_overworld.png", frame[y:y + h, x:x + w])
    print("Saved ref_overworld.png.")

    wait_then_switch(
        "Now let a soft reset run all the way into the static encounter's "
        "battle (mash A yourself if needed). Once you're in it, press "
        "ENTER here: ")
    frame2 = capture_region_frame(cfg)
    cv2.imwrite("ref_battle.png", frame2[y:y + h, x:x + w])
    print("Saved ref_battle.png.")
    save_config(cfg)
    return cfg


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture-region", action="store_true",
                         help="redo step 1 (whole game view) only")
    parser.add_argument("--battle", action="store_true",
                         help="redo step 2 (battle indicator) only")
    parser.add_argument("--shared", action="store_true",
                         help="switch to the frame-sharing NTR Viewer (can be "
                              "minimised) and recalibrate everything for it")
    parser.add_argument("--screen", action="store_true",
                         help="switch back to reading NTR Viewer off the screen "
                              "and recalibrate everything for it")
    args = parser.parse_args()

    SOURCE_DEPENDENT = ["capture_region", "battle_indicator_roi"]
    try:
        cfg = load_config()
        if args.shared or args.screen:
            # battle_indicator_roi is measured in the picture's own pixels,
            # and the two sources give differently sized pictures -- so
            # switching means recalibrating it.
            for key in SOURCE_DEPENDENT:
                cfg.pop(key, None)
            cfg["frame_source"] = "shared" if args.shared else "screen"
            save_config(cfg)
            print(f"Switched to {'the frame-sharing NTR Viewer' if args.shared else 'screen capture'}"
                  f" -- recalibrating every region for it.")
        if args.capture_region:
            cfg = calibrate_capture_region(cfg, choose_monitor())
        elif args.battle:
            cfg = calibrate_battle_indicator(cfg)
        else:
            # Only run whichever steps aren't already saved, so re-running
            # this after an interruption doesn't force you to redo
            # earlier steps that already worked.
            if cfg.get("frame_source") == "shared":
                print("Using the frame-sharing NTR Viewer -- no screen area "
                      "needed.")
            elif "capture_region" not in cfg:
                cfg = calibrate_capture_region(cfg, choose_monitor())
            else:
                print("capture_region already set -- skipping (use "
                      "--capture-region to redo it).")
            if "battle_indicator_roi" not in cfg:
                cfg = calibrate_battle_indicator(cfg)
            else:
                print("battle_indicator_roi already set -- skipping (use "
                      "--battle to redo it).")
            print("\nAll regions calibrated. Copy over your NORMAL/, SHINY/ "
                  "folders from the Sweet Scent/master bot, then run:\n"
                  "    py static_encounter_bot.py --ip <3ds ip>")
    except Exception:
        import traceback
        traceback.print_exc()
    finally:
        input("\nDone -- press ENTER to close this window.")
