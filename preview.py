#!/usr/bin/env python3
"""See what the bot sees -- WITHOUT sending any input to the game.

Cast in-game so your bobber is on the water, then run this. It grabs the
configured fishing region, runs the exact same bobber detection the bot uses,
draws a crosshair where it thinks the bobber is, and saves an annotated image
to ``detection_preview.png`` so you can check it (and send it to me if it's off).

    python preview.py           # one shot
    python preview.py --loop    # keep re-checking every ~1.5s until Ctrl+C

Nothing here presses keys or moves the mouse. It is 100% safe to run while you
watch.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from fishbot.config import Config

try:
    import cv2
    import numpy as np
    from fishbot.capture import ScreenCapture
    from fishbot.bobber import BobberFinder
except Exception as exc:  # pragma: no cover
    print(f"Preview needs opencv-python, numpy and mss installed: {exc}")
    raise SystemExit(1)


class _NoController:
    """Bobber detection may reference a controller for the legacy mode; stub it."""
    def move_to(self, *a, **k): pass


def run_once(cfg: Config, capture: ScreenCapture, finder: BobberFinder) -> None:
    frame = capture.grab(cfg.region)
    pt = finder.find(retries=1)

    annotated = frame.copy()
    left, top, w, h = cfg.region
    if pt is not None:
        # Map absolute screen coord back into region-local pixels for drawing.
        lx, ly = pt[0] - left, pt[1] - top
        cv2.drawMarker(annotated, (int(lx), int(ly)), (0, 255, 0),
                       cv2.MARKER_CROSS, 40, 2)
        cv2.circle(annotated, (int(lx), int(ly)), 18, (0, 255, 0), 2)
        print(f"  FOUND bobber at screen ({pt[0]}, {pt[1]})  "
              f"[region-local ({int(lx)}, {int(ly)})]")
    else:
        cv2.putText(annotated, "NO BOBBER FOUND", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
        print("  no bobber found in this region. Tips: cast first, or widen/"
              "move the region (python calibrate.py).")

    out = Path(__file__).resolve().parent / "detection_preview.png"
    cv2.imwrite(str(out), annotated)
    print(f"  saved -> {out}")


def _countdown(secs: int) -> None:
    print(f"\n>>> Switch to WoW NOW (click the game window). Capturing in {secs}s...")
    for i in range(secs, 0, -1):
        print(f"    {i}...", end="\r", flush=True)
        time.sleep(1)
    print("    capturing!            ")


def main() -> None:
    ap = argparse.ArgumentParser(description="Preview bobber detection (no input sent)")
    ap.add_argument("--config", default=None)
    ap.add_argument("--loop", action="store_true", help="re-check every few seconds")
    ap.add_argument("--delay", type=int, default=5,
                    help="seconds to switch to WoW before the first capture (default 5)")
    args = ap.parse_args()

    cfg = Config.load(args.config)
    print(f"Region being watched: {cfg.region}  strategy={cfg.bobber.get('strategy')}")
    print("Single monitor? Cast in WoW first, run this, then click back into WoW\n"
          "during the countdown so the game (not this terminal) is on screen.")

    capture = ScreenCapture()
    finder = BobberFinder(cfg, capture, _NoController())
    try:
        _countdown(max(1, args.delay))
        if args.loop:
            # Keep capturing every couple seconds so you can watch it lock on.
            # Stay in WoW; alt-tab back to the terminal / image when done (Ctrl+C).
            while True:
                run_once(cfg, capture, finder)
                time.sleep(2.0)
        else:
            run_once(cfg, capture, finder)
    except KeyboardInterrupt:
        pass
    finally:
        capture.close()
    print("\nNow alt-tab back and open detection_preview.png to see the crosshair.")


if __name__ == "__main__":
    main()
