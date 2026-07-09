#!/usr/bin/env python3
"""Crop the bobber template out of full_screen.png at a given spot.

Claude reads your full_screen.png and gives you the fractional position of the
bobber (resolution-independent, so it survives image resizing in chat). You run:

    python make_template.py --fx 0.50 --fy 0.28

This crops a small box centered there and saves it as the match template
(assets/bobber.png), plus a zoomed bobber_preview.png so you can confirm the
bobber is centered. You can also pass absolute pixels with --x/--y.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from fishbot.config import Config

try:
    import cv2
    import numpy as np
except Exception as exc:  # pragma: no cover
    print(f"Needs opencv-python and numpy installed: {exc}")
    raise SystemExit(1)


def main() -> None:
    ap = argparse.ArgumentParser(description="Crop bobber template from full_screen.png")
    ap.add_argument("--image", default="full_screen.png", help="source screenshot")
    ap.add_argument("--fx", type=float, help="bobber X as a fraction of width (0-1)")
    ap.add_argument("--fy", type=float, help="bobber Y as a fraction of height (0-1)")
    ap.add_argument("--x", type=int, help="bobber X in absolute pixels")
    ap.add_argument("--y", type=int, help="bobber Y in absolute pixels")
    ap.add_argument("--size", type=int, default=54, help="crop size in px (default 54)")
    args = ap.parse_args()

    src = Path(args.image)
    if not src.is_absolute():
        src = Path(__file__).resolve().parent / src
    if not src.exists():
        print(f"Can't find {src}. Run grab_screen.py first.")
        raise SystemExit(1)

    img = cv2.imread(str(src), cv2.IMREAD_COLOR)
    if img is None:
        print(f"Could not read {src}.")
        raise SystemExit(1)
    h, w = img.shape[:2]

    if args.x is not None and args.y is not None:
        cx, cy = args.x, args.y
    elif args.fx is not None and args.fy is not None:
        cx, cy = int(args.fx * w), int(args.fy * h)
    else:
        print("Provide either --fx/--fy (fractions) or --x/--y (pixels).")
        raise SystemExit(1)

    half = max(12, args.size // 2)
    x0, y0 = max(0, cx - half), max(0, cy - half)
    x1, y1 = min(w, cx + half), min(h, cy + half)
    crop = img[y0:y1, x0:x1]
    if crop.size == 0:
        print("Crop is empty -- coordinates out of range.")
        raise SystemExit(1)

    cfg = Config.load()
    out = Path(cfg.bobber.get("template_path", "assets/bobber.png"))
    if not out.is_absolute():
        out = Path(__file__).resolve().parent / out
    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), crop)

    preview = cv2.resize(crop, (crop.shape[1] * 5, crop.shape[0] * 5),
                         interpolation=cv2.INTER_NEAREST)
    cv2.drawMarker(preview, (preview.shape[1] // 2, preview.shape[0] // 2),
                   (0, 255, 0), cv2.MARKER_CROSS, 30, 1)
    pv = Path(__file__).resolve().parent / "bobber_preview.png"
    cv2.imwrite(str(pv), preview)

    print(f"Cropped at pixel ({cx}, {cy}) from a {w}x{h} image.")
    print(f"Saved template -> {out}")
    print(f"Check it       -> {pv}  (bobber should sit under the green cross)")
    print("Looks good? Cast in-game, then:  python preview.py")


if __name__ == "__main__":
    main()
