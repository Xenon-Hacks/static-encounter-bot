"""
test_reset.py -- runs the REAL soft_reset() + mash_to_battle() functions
once (same code path as static_encounter_bot.py), so you can confirm the
whole reset -> boot logos -> title -> CONTINUE -> dialogue -> battle
sequence actually lands in a battle before trusting it to run unattended.

Requires calibrate.py to have already saved battle_indicator_roi (and
capture_region, unless frame_source is "shared") and ref_battle.png.

Stand your save right in front of the static encounter, in the
overworld, with no menu open, THEN run:

    py test_reset.py --ip <3ds ip>
"""

import argparse
import json

from luma_input import Luma3DSInput
from vision import Capture
import shared_frame
import ntr_status
import reset_menu
from static_encounter_bot import in_battle


def load_test_config():
    try:
        with open("config.json") as f:
            cfg = json.load(f)
    except FileNotFoundError:
        print("config.json not found -- run calibrate.py first.")
        raise SystemExit(1)
    required = ["battle_indicator_roi"]
    if cfg.get("frame_source", "screen") != "shared":
        required.append("capture_region")
    for key in required:
        if key not in cfg:
            print(f"config.json is missing '{key}'. Run calibrate.py first.")
            raise SystemExit(1)
    return cfg


def make_capture(cfg):
    if cfg.get("frame_source", "screen") == "shared":
        cap = shared_frame.SharedFrameCapture(rotation=cfg.get("shared_rotation", 1))
        if not shared_frame.wait_until_available(cap, timeout=15.0):
            raise SystemExit("No frames from the frame-sharing NTR Viewer.")
        ntr_status.shared_source = cap
        return cap
    return Capture(cfg["capture_region"])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ip", required=True)
    args = parser.parse_args()

    cfg = load_test_config()
    cap = make_capture(cfg)
    pad = Luma3DSInput(args.ip)

    print("Make sure your save is standing right in front of the static "
          "encounter, in the overworld, with no menu open.")
    input("Press ENTER to soft-reset and mash through to the battle: ")

    try:
        reset_menu.soft_reset(pad)
        print("Reset sent -- mashing A until the battle indicator lights up...\n")
        ok = reset_menu.mash_to_battle(pad, cap, cfg, in_battle)
        if ok:
            print("\nmash_to_battle() reports the battle started -- confirm "
                  "you're actually looking at the wild encounter now.")
        else:
            print("\nmash_to_battle() timed out without ever seeing the "
                  "battle indicator. Check your 3DS: if it's stuck "
                  "somewhere before the battle, the timing constants in "
                  "reset_menu.py (MASH_TIMEOUT, MASH_INTERVAL) or the "
                  "battle_indicator_roi calibration may need adjusting.")
    finally:
        pad.close()
        print("Released control back to the physical buttons.")


if __name__ == "__main__":
    main()
