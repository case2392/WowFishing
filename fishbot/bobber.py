"""Finding the fishing bobber on screen.

Two strategies are provided:

* ``cursor_scan`` (Windows): sweep the mouse across the fishing region in a
  randomized grid; when the Windows cursor handle changes to WoW's
  "interact/cast" cursor we know we are hovering the bobber. This is the classic,
  highly reliable method because it uses the game's own hit-testing rather than
  guessing from pixels, and it works regardless of water color or weather.

* ``template`` (cross-platform): OpenCV template match of a saved bobber image
  against the captured region.

Both return the absolute screen coordinate of the bobber, or ``None``.
"""

from __future__ import annotations

import random
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np

try:
    import cv2
except Exception:  # pragma: no cover
    cv2 = None

from . import humanize

Point = Tuple[int, int]

# --------------------------------------------------------------------------- #
#  Windows cursor inspection (for cursor_scan)                                 #
# --------------------------------------------------------------------------- #
_win32_ok = False
try:  # pragma: no cover - platform dependent
    import win32gui

    _win32_ok = True
except Exception:
    _win32_ok = False


def current_cursor_handle() -> Optional[int]:
    """Return the OS handle of the cursor currently displayed, or None."""
    if not _win32_ok:
        return None
    try:
        flags, handle, (x, y) = win32gui.GetCursorInfo()
        return handle
    except Exception:
        return None


class BobberFinder:
    def __init__(self, cfg, capture, controller):
        self.cfg = cfg
        self.capture = capture
        self.controller = controller
        self.b = cfg.bobber
        self.region = cfg.region
        self._template = None
        self._default_cursor: Optional[int] = None
        if self.b.get("strategy") == "template":
            self._load_template()

    # ------------------------------------------------------------------ #
    def find(self) -> Optional[Point]:
        strategy = self.b.get("strategy", "cursor_scan")
        if strategy == "cursor_scan":
            if not _win32_ok:
                # Fall back gracefully if pywin32 is missing (e.g. non-Windows).
                if self._template is None:
                    self._load_template()
                return self._find_template()
            return self._find_cursor_scan()
        return self._find_template()

    # ------------------------------------------------------------------ #
    #  cursor_scan                                                        #
    # ------------------------------------------------------------------ #
    def _scan_points(self) -> List[Point]:
        left, top, width, height = self.region
        step = int(self.b.get("scan_step", 22))
        pts: List[Point] = []
        # Serpentine grid keeps consecutive probes physically close, so the
        # mouse path between them stays short and natural-looking.
        rows = list(range(top + step, top + height - step, step))
        for ri, y in enumerate(rows):
            xs = list(range(left + step, left + width - step, step))
            if ri % 2 == 1:
                xs.reverse()
            for x in xs:
                # jitter each probe a few px so the grid isn't machine-perfect
                pts.append((x + random.randint(-4, 4), y + random.randint(-4, 4)))
        return pts

    def _find_cursor_scan(self) -> Optional[Point]:
        settle = self.b.get("scan_settle_ms", 9) / 1000.0
        # Establish the "normal" cursor from a corner unlikely to hold the bobber.
        left, top, width, height = self.region
        self.controller.move_to((left + 5, top + 5), duration=humanize.rand_range([0.15, 0.3]))
        humanize.human_sleep(settle * 3)
        self._default_cursor = current_cursor_handle()

        for pt in self._scan_points():
            self.controller.move_to(pt, duration=humanize.rand_range([0.02, 0.06]))
            humanize.human_sleep(settle)
            handle = current_cursor_handle()
            if handle is not None and handle != self._default_cursor:
                # Confirm it wasn't a one-frame fluke.
                humanize.human_sleep(settle)
                if current_cursor_handle() == handle:
                    return pt
        return None

    # ------------------------------------------------------------------ #
    #  template                                                           #
    # ------------------------------------------------------------------ #
    def _load_template(self) -> None:
        if cv2 is None:
            return
        path = Path(self.b.get("template_path", "assets/bobber.png"))
        if not path.is_absolute():
            path = Path(__file__).resolve().parent.parent / path
        if path.exists():
            self._template = cv2.imread(str(path), cv2.IMREAD_COLOR)

    def _find_template(self) -> Optional[Point]:
        if cv2 is None or self._template is None:
            return None
        frame = self.capture.grab(self.region)
        res = cv2.matchTemplate(frame, self._template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(res)
        if max_val < float(self.b.get("match_threshold", 0.62)):
            return None
        th, tw = self._template.shape[:2]
        left, top, _, _ = self.region
        # Center of the matched patch, in absolute screen coordinates.
        cx = left + max_loc[0] + tw // 2
        cy = top + max_loc[1] + th // 2
        return (cx, cy)
