#!/usr/bin/env python3
"""Interactive setup helper.

Walks you through the two things the bot needs to know:

  1. The fishing *region* -- the screen rectangle your bobber lands in.
  2. (optional) A *bobber template* image, if you use the "template" strategy.

Run it, then follow the prompts:

    python calibrate.py
"""

from __future__ import annotations

import time
from pathlib import Path

from fishbot.config import Config

try:
    import mss
    import numpy as np
    import cv2
except Exception as exc:  # pragma: no cover
    print(f"Calibration needs mss, numpy and opencv-python installed: {exc}")
    raise SystemExit(1)

try:
    from fishbot.input_control import _backend as _mouse_backend
except Exception:
    _mouse_backend = None


def _get_mouse_pos():
    if _mouse_backend is None:
        raise SystemExit("Need pydirectinput or pyautogui to read the mouse position.")
    x, y = _mouse_backend.position()
    return int(x), int(y)


def _countdown(msg: str, secs: int = 5) -> None:
    print(msg)
    for i in range(secs, 0, -1):
        print(f"   capturing in {i}...", end="\r", flush=True)
        time.sleep(1)
    print(" " * 40, end="\r")


def calibrate_region(cfg: Config) -> None:
    print("\n=== STEP 1: fishing region ===")
    print("You'll mark two corners of the box your bobber can land in.")
    print("Cast once in-game first so you can see the typical splash zone.\n")

    input("Move your mouse to the TOP-LEFT of the fishing area, then press Enter...")
    x1, y1 = _get_mouse_pos()
    print(f"   top-left  = ({x1}, {y1})")

    input("Move your mouse to the BOTTOM-RIGHT of the fishing area, then press Enter...")
    x2, y2 = _get_mouse_pos()
    print(f"   bottom-right = ({x2}, {y2})")

    left, top = min(x1, x2), min(y1, y2)
    width, height = abs(x2 - x1), abs(y2 - y1)
    if width < 20 or height < 20:
        print("   That region looks too small; try again.")
        return
    cfg.region = [left, top, width, height]
    print(f"   region set to {cfg.region}")


def calibrate_template(cfg: Config) -> None:
    print("\n=== STEP 2: bobber template (only needed for the 'template' strategy) ===")
    ans = input("Capture a bobber image now? [y/N] ").strip().lower()
    if ans != "y":
        print("   skipped.")
        return

    print("Cast in-game so the bobber is visible and sitting still.")
    _countdown("Then leave it alone -- I'll grab a small crop around your cursor.", 6)

    cx, cy = _get_mouse_pos()
    half = 26
    region = {"left": cx - half, "top": cy - half, "width": half * 2, "height": half * 2}
    with mss.mss() as sct:
        raw = sct.grab(region)
    img = np.asarray(raw)[:, :, :3]

    out = Path(cfg.bobber.get("template_path", "assets/bobber.png"))
    if not out.is_absolute():
        out = Path(__file__).resolve().parent / out
    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), img)
    print(f"   saved bobber template -> {out}")
    print("   (If detection is poor, re-run and hover the bobber's center exactly.)")


def main() -> None:
    cfg = Config.load()
    print("WoW Fishing Bot -- calibration")
    print("Have WoW open in windowed-fullscreen on your primary monitor.\n")

    calibrate_region(cfg)
    calibrate_template(cfg)

    cfg.save()
    print(f"\nSaved to {cfg.path}. You're ready:  python run.py")


if __name__ == "__main__":
    main()
