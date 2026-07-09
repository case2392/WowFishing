"""Finding the fishing bobber on screen -- WITHOUT moving the mouse.

The bobber is located by looking at the screen pixels only. The mouse does not
move at all during the search, so there is no robotic sweeping. Once found, the
caller moves to it a single time and lets it sit still.

Default strategy: ``vision``
    1. If a bobber template image exists (captured from your screenshot), do a
       multi-scale template match -- robust to camera zoom.
    2. Otherwise (or if that fails), fall back to color+shape blob detection:
       the WoW bobber is a compact red/white float that stands out against the
       water.

Legacy strategies ``template`` (single-scale) and ``cursor_scan`` (the old
mouse-sweep method) are still selectable in config but no longer the default.
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
#  Optional Windows cursor inspection (only for the legacy cursor_scan mode)   #
# --------------------------------------------------------------------------- #
_win32_ok = False
try:  # pragma: no cover - platform dependent
    import win32gui

    _win32_ok = True
except Exception:
    _win32_ok = False


def current_cursor_handle() -> Optional[int]:
    if not _win32_ok:
        return None
    try:
        _flags, handle, _pos = win32gui.GetCursorInfo()
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
        self._load_template()  # harmless if the file isn't there yet

    # ------------------------------------------------------------------ #
    def find(self, retries: int = 3) -> Optional[Point]:
        """Locate the bobber. Retries a few times since it takes a beat to render."""
        strategy = self.b.get("strategy", "vision")
        for attempt in range(max(1, retries)):
            if strategy == "cursor_scan" and _win32_ok:
                pt = self._find_cursor_scan()
            elif strategy == "template":
                pt = self._find_template_singlescale()
            else:  # "vision" (default) and any unknown value
                pt = self._find_vision()
            if pt is not None:
                return pt
            humanize.human_sleep(humanize.rand_range([0.25, 0.5]))
        return None

    # ================================================================== #
    #  VISION (default): template multi-scale, then color blob            #
    # ================================================================== #
    def _find_vision(self) -> Optional[Point]:
        if cv2 is None:
            return None
        frame = self.capture.grab(self.region)  # NO mouse movement here
        self._blank_ignore_zones(frame)
        # Template match (your actual bobber) is the most reliable when the bobber
        # can be anywhere in a big region alongside UI; color signature backs it up.
        pt = self._match_template_multiscale(frame)
        if pt is not None:
            return pt
        return self._find_color_blob(frame)

    def _blank_ignore_zones(self, frame: np.ndarray) -> None:
        """Paint configured ignore rectangles black so UI can't be mistaken for a bobber."""
        zones = getattr(self.cfg, "ignore_zones", None) or []
        left, top, w, h = self.region
        H, W = frame.shape[:2]
        for z in zones:
            try:
                zl, zt, zw, zh = z
            except Exception:
                continue
            x0 = max(0, int(zl - left)); y0 = max(0, int(zt - top))
            x1 = min(W, int(zl - left + zw)); y1 = min(H, int(zt - top + zh))
            if x1 > x0 and y1 > y0:
                frame[y0:y1, x0:x1] = 0

    def _match_template_multiscale(self, frame: np.ndarray) -> Optional[Point]:
        if self._template is None:
            return None
        threshold = float(self.b.get("match_threshold", 0.62))
        th0, tw0 = self._template.shape[:2]
        best_val = -1.0
        best_loc = None
        best_wh = (tw0, th0)
        # Try a range of scales so camera zoom / resolution differences don't matter.
        for scale in (0.5, 0.65, 0.8, 0.9, 1.0, 1.1, 1.25, 1.5, 1.8):
            tw, th = int(tw0 * scale), int(th0 * scale)
            if tw < 8 or th < 8 or tw >= frame.shape[1] or th >= frame.shape[0]:
                continue
            tmpl = cv2.resize(self._template, (tw, th), interpolation=cv2.INTER_AREA)
            res = cv2.matchTemplate(frame, tmpl, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(res)
            if max_val > best_val:
                best_val, best_loc, best_wh = max_val, max_loc, (tw, th)
        if best_loc is None or best_val < threshold:
            return None
        left, top, _, _ = self.region
        cx = left + best_loc[0] + best_wh[0] // 2
        cy = top + best_loc[1] + best_wh[1] // 2
        return (cx, cy)

    def _blobs(self, mask: np.ndarray, min_area: float, max_area: float) -> List[dict]:
        """Return cleaned-up colored blobs as dicts of {x, y, area}."""
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        mask = cv2.dilate(mask, np.ones((3, 3), np.uint8), iterations=1)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        out: List[dict] = []
        for c in contours:
            area = cv2.contourArea(c)
            if area < min_area or area > max_area:
                continue
            m = cv2.moments(c)
            if m["m00"] == 0:
                continue
            out.append({"x": m["m10"] / m["m00"], "y": m["m01"] / m["m00"], "area": area})
        return out

    def _find_color_blob(self, frame: np.ndarray) -> Optional[Point]:
        """Detect the standard Classic bobber by its red-feather + blue-band signature.

        The WoW fishing bobber is a red/crimson feather sitting just above a
        steel-blue band. In the warm, olive-colored water this player fishes in,
        that red-directly-above-blue pairing essentially never occurs by chance,
        so we score candidate locations by how well a red blob and a blue blob sit
        close together (red on top). We fall back to the strongest red blob, then
        the strongest blue blob, if no clean pair is found.
        """
        h, w = frame.shape[:2]
        max_area = (w * h) * 0.05
        min_area = 10.0

        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        # Red wraps around the hue circle -> two ranges.
        red = cv2.inRange(hsv, np.array([0, 80, 70]), np.array([12, 255, 255])) | \
              cv2.inRange(hsv, np.array([166, 80, 70]), np.array([180, 255, 255]))
        # Steel/medium blue of the bobber band; absent from warm water & sunset sky here.
        blue = cv2.inRange(hsv, np.array([90, 70, 60]), np.array([132, 255, 255]))

        red_blobs = self._blobs(red, min_area, max_area)
        blue_blobs = self._blobs(blue, min_area, max_area)

        cxr, cyr = w / 2, h / 2

        def centrality(x, y):
            d = ((x - cxr) ** 2 + (y - cyr) ** 2) ** 0.5
            return 1.0 - min(1.0, d / (0.5 * (w + h) / 2))

        # 1) Best red+blue pair (the strong signature).
        best_pair = None
        best_pair_score = -1.0
        for r in red_blobs:
            for b in blue_blobs:
                dist = ((r["x"] - b["x"]) ** 2 + (r["y"] - b["y"]) ** 2) ** 0.5
                if dist > 55:               # must be part of the same small lure
                    continue
                red_on_top = r["y"] <= b["y"] + 8   # red feather sits above blue
                # Aim between the two, biased slightly toward the waterline float.
                tx = (r["x"] + b["x"]) / 2
                ty = (r["y"] + b["y"]) / 2 + 4
                # The bobber roams the whole box, so centrality is only a faint
                # tie-breaker; the red-above-blue pairing is what identifies it.
                score = (r["area"] + b["area"]) \
                    + 400.0 / (dist + 8) \
                    + (250 if red_on_top else 0) \
                    + 25 * centrality(tx, ty)
                if score > best_pair_score:
                    best_pair_score = score
                    best_pair = (tx, ty)
        if best_pair is not None:
            left, top, _, _ = self.region
            return (int(left + best_pair[0]), int(top + best_pair[1]))

        # 2) Fall back to the best red feather blob. We prefer compact, bobber-
        #    sized red (the feather) and reject big low-saturation splotches
        #    (warm water reflections). No lone-BLUE fallback: blue alone is more
        #    likely a nameplate mana bar than a bobber.
        best, best_s = None, -1.0
        for k in red_blobs:
            area = k["area"]
            if area > (w * h) * 0.01:      # too big to be the little feather
                continue
            # sweet-spot size score peaks around a small feather, plus faint centrality
            size_fit = 1.0 - min(1.0, abs(area - 120) / 400.0)
            s = size_fit * (0.7 + 0.3 * centrality(k["x"], k["y"]))
            if s > best_s:
                best_s, best = s, (k["x"], k["y"])
        if best is not None:
            left, top, _, _ = self.region
            return (int(left + best[0]), int(top + best[1]))
        return None

    # ================================================================== #
    #  Legacy: single-scale template                                      #
    # ================================================================== #
    def _find_template_singlescale(self) -> Optional[Point]:
        if cv2 is None or self._template is None:
            return None
        frame = self.capture.grab(self.region)
        res = cv2.matchTemplate(frame, self._template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(res)
        if max_val < float(self.b.get("match_threshold", 0.62)):
            return None
        th, tw = self._template.shape[:2]
        left, top, _, _ = self.region
        return (left + max_loc[0] + tw // 2, top + max_loc[1] + th // 2)

    # ================================================================== #
    #  Legacy: cursor sweep (the old, robotic-looking method)             #
    # ================================================================== #
    def _scan_points(self) -> List[Point]:
        left, top, width, height = self.region
        step = int(self.b.get("scan_step", 22))
        pts: List[Point] = []
        rows = list(range(top + step, top + height - step, step))
        for ri, y in enumerate(rows):
            xs = list(range(left + step, left + width - step, step))
            if ri % 2 == 1:
                xs.reverse()
            for x in xs:
                pts.append((x + random.randint(-4, 4), y + random.randint(-4, 4)))
        return pts

    def _find_cursor_scan(self) -> Optional[Point]:
        settle = self.b.get("scan_settle_ms", 9) / 1000.0
        left, top, _w, _h = self.region
        self.controller.move_to((left + 5, top + 5), duration=humanize.rand_range([0.15, 0.3]))
        humanize.human_sleep(settle * 3)
        self._default_cursor = current_cursor_handle()
        for pt in self._scan_points():
            self.controller.move_to(pt, duration=humanize.rand_range([0.02, 0.06]))
            humanize.human_sleep(settle)
            handle = current_cursor_handle()
            if handle is not None and handle != self._default_cursor:
                humanize.human_sleep(settle)
                if current_cursor_handle() == handle:
                    return pt
        return None

    # ------------------------------------------------------------------ #
    def _load_template(self) -> None:
        if cv2 is None:
            return
        path = Path(self.b.get("template_path", "assets/bobber.png"))
        if not path.is_absolute():
            path = Path(__file__).resolve().parent.parent / path
        if path.exists():
            self._template = cv2.imread(str(path), cv2.IMREAD_COLOR)
