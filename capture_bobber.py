#!/usr/bin/env python3
"""Capture YOUR exact bobber as a template image (single-monitor friendly).

Why: matching a picture of your real bobber is far more reliable than guessing
it from colors, especially in low-contrast water with nameplates around.

How (no clicking in-game needed):
    1. In WoW, cast so the bobber is floating.
    2. Alt-tab here and run:  python capture_bobber.py
    3. During the countdown, click back into WoW and put your MOUSE CURSOR
       right on top of the bobber. Hold it there.
    4. It grabs a small crop centered on your cursor and saves it as the
       template (assets/bobber.png), plus a zoomed bobber_preview.png so you
       can check the bobber is centered.

Re-run until bobber_preview.png shows the bobber nicely centered. Then run
preview.py to confirm the bot locks on.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from fishbot.config import Config

try:
    import cv2
    import numpy as np
    import mss
except Exception as exc:  # pragma: no cover
    print(f"Needs opencv-python, numpy and mss installed: {exc}")
    raise SystemExit(1)

try:
    from fishbot.input_control import _backend as _mouse
except Exception:
    _mouse = None


def _countdown(secs: int) -> None:
    print(f"\n>>> Click into WoW and hover your MOUSE on the bobber. Capturing in {secs}s...")
    for i in range(secs, 0, -1):
        print(f"    {i}...  (put the cursor on the bobber)", end="\r", flush=True)
        time.sleep(1)
    print("    capturing!                                   ")


def main() -> None:
    ap = argparse.ArgumentParser(description="Capture your bobber as a match template")
    ap.add_argument("--delay", type=int, default=6, help="seconds before capture (default 6)")
    ap.add_argument("--size", type=int, default=48,
                    help="crop size in px around the cursor (default 48)")
    args = ap.parse_args()

    if _mouse is None:
        print("Could not read the mouse position (need pydirectinput or pyautogui).")
        raise SystemExit(1)

    cfg = Config.load()
    _countdown(max(1, args.delay))

    mx, my = _mouse.position()
    half = max(12, args.size // 2)
    box = {"left": int(mx - half), "top": int(my - half),
           "width": half * 2, "height": half * 2}
    with mss.mss() as sct:
        raw = sct.grab(box)
    img = np.asarray(raw)[:, :, :3]

    out = Path(cfg.bobber.get("template_path", "assets/bobber.png"))
    if not out.is_absolute():
        out = Path(__file__).resolve().parent / out
    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), img)

    # Zoomed preview so a human can verify the bobber is centered in the crop.
    preview = cv2.resize(img, (img.shape[1] * 5, img.shape[0] * 5),
                         interpolation=cv2.INTER_NEAREST)
    cv2.drawMarker(preview, (preview.shape[1] // 2, preview.shape[0] // 2),
                   (0, 255, 0), cv2.MARKER_CROSS, 30, 1)
    pv = Path(__file__).resolve().parent / "bobber_preview.png"
    cv2.imwrite(str(pv), preview)

    print(f"\nSaved template -> {out}")
    print(f"Check it       -> {pv}  (bobber should sit under the green cross)")
    print("If it's off-center or shows water/UI instead, just run this again.")
    print("When it looks good:  python preview.py")


if __name__ == "__main__":
    main()
