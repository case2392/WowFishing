#!/usr/bin/env python3
"""Capture your whole screen to full_screen.png (single-monitor friendly).

You do NOT need to aim the mouse at anything. Just have the bobber visible.

    1. In WoW, cast so the bobber is floating.
    2. Alt-tab here, run:  python grab_screen.py
    3. During the countdown, click back into WoW so the game is on screen.
    4. It saves full_screen.png. Send that image to Claude and it will tell you
       exactly where the bobber is and the command to crop it into a template.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

try:
    import cv2
    import numpy as np
    import mss
except Exception as exc:  # pragma: no cover
    print(f"Needs opencv-python, numpy and mss installed: {exc}")
    raise SystemExit(1)


def _countdown(secs: int) -> None:
    print(f"\n>>> Click into WoW so the game is on screen. Capturing in {secs}s...")
    for i in range(secs, 0, -1):
        print(f"    {i}...", end="\r", flush=True)
        time.sleep(1)
    print("    capturing!        ")


def main() -> None:
    ap = argparse.ArgumentParser(description="Grab a full-screen shot for template setup")
    ap.add_argument("--delay", type=int, default=6, help="seconds before capture (default 6)")
    args = ap.parse_args()

    _countdown(max(1, args.delay))
    with mss.mss() as sct:
        mon = sct.monitors[1]  # primary monitor, full
        raw = sct.grab(mon)
    img = np.asarray(raw)[:, :, :3]

    out = Path(__file__).resolve().parent / "full_screen.png"
    cv2.imwrite(str(out), img)
    h, w = img.shape[:2]
    print(f"\nSaved -> {out}   ({w} x {h} px)")
    print("Send full_screen.png to Claude. It will reply with a command like:")
    print("    python make_template.py --fx 0.50 --fy 0.28")
    print("that crops your bobber into the template automatically.")


if __name__ == "__main__":
    main()
