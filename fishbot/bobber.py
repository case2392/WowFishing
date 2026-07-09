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
    #  Gear-cursor confirmation                                           #
    # ------------------------------------------------------------------ #
    def learn_default_cursor(self) -> None:
        """Sample the normal cursor over open water so we can spot the interact gear.

        Called once at startup; a region corner is almost always empty water.
        """
        if not _win32_ok:
            return
        left, top, _w, _h = self.region
        self.controller.move_to((left + 8, top + 8),
                                duration=humanize.rand_range([0.2, 0.4]))
        humanize.human_sleep(0.06)
        self._default_cursor = current_cursor_handle()

    def _is_interact_cursor(self) -> bool:
        """True if the cursor is currently the golden gear (differs from default)."""
        h = current_cursor_handle()
        return (h is not None and self._default_cursor is not None
                and h != self._default_cursor)

    def move_and_confirm(self, candidate: Point) -> Point:
        """Move onto the bobber, confirming via the gear cursor.

        If the gear doesn't show, make a TINY local spiral nudge (a few px, like a
        person adjusting their aim) until it does. Returns the final point.
        """
        self.controller.move_to(candidate)
        if not _win32_ok or not self.b.get("cursor_confirm", True):
            return candidate
        humanize.human_sleep(humanize.rand_range([0.04, 0.09]))
        if self._is_interact_cursor():
            return candidate
        # Small local search only -- never a big sweep.
        for pt in self._local_nudges(candidate):
            self.controller.move_to(pt, duration=humanize.rand_range([0.03, 0.07]))
            humanize.human_sleep(humanize.rand_range([0.02, 0.04]))
            if self._is_interact_cursor():
                return (int(pt[0]), int(pt[1]))
        return candidate  # give it our best visual guess if the gear never showed

    def _local_nudges(self, center: Point) -> List[Point]:
        import math
        pts: List[Point] = []
        for radius in (8, 15, 22, 30):
            for k in range(8):
                ang = 2 * math.pi * k / 8 + radius  # rotate each ring so points differ
                pts.append((center[0] + radius * math.cos(ang),
                            center[1] + radius * math.sin(ang)))
        return pts

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
                ranked = self.find_ranked(max_candidates=1)
                pt = ranked[0] if ranked else None
            if pt is not None:
                return pt
            humanize.human_sleep(humanize.rand_range([0.25, 0.5]))
        return None

    # ================================================================== #
    #  ACQUIRE: rank several candidates, then let the gold gear cursor    #
    #  pick the real bobber (rejecting the crate / water false positives) #
    # ================================================================== #
    def acquire(self, retries: int = 2) -> Optional[Point]:
        """Find the bobber and move onto it, VERIFIED by the interact cursor.

        Produces several ranked candidate points, then moves to each and checks
        for the golden gear cursor. The first candidate that shows the gear is
        the real bobber. If none do, returns None so the bot recasts instead of
        sitting on a crate or empty water for the whole cast.
        """
        gear_ok = _win32_ok and self.b.get("cursor_confirm", True)
        for _ in range(max(1, retries)):
            candidates = self.find_ranked(max_candidates=5)
            if candidates:
                if not gear_ok:
                    # Can't verify (no pywin32) -> trust the top visual match.
                    self.controller.move_to(candidates[0])
                    return candidates[0]
                for cand in candidates:
                    self.controller.move_to(cand)
                    humanize.human_sleep(humanize.rand_range([0.05, 0.10]))
                    if self._is_interact_cursor():
                        return cand
                    nudged = self._nudge_until_interact(cand)
                    if nudged is not None:
                        return nudged
            humanize.human_sleep(humanize.rand_range([0.2, 0.4]))
        return None

    def _nudge_until_interact(self, center: Point) -> Optional[Point]:
        """Tiny local search for the gear cursor around a candidate; None if not found."""
        for pt in self._local_nudges(center):
            self.controller.move_to(pt, duration=humanize.rand_range([0.03, 0.07]))
            humanize.human_sleep(humanize.rand_range([0.03, 0.05]))
            if self._is_interact_cursor():
                return (int(pt[0]), int(pt[1]))
        return None

    def find_ranked(self, max_candidates: int = 5) -> List[Point]:
        """Return several likely bobber points, best first (template + color)."""
        if cv2 is None:
            return []
        frame = self.capture.grab(self.region)
        self._blank_ignore_zones(frame)
        left, top, _, _ = self.region

        scored: List[tuple] = []  # (score, x, y)
        for (lx, ly), val in self._template_candidates(frame, n=max_candidates):
            scored.append((val + 1.0, left + lx, top + ly))   # template ranks first
        for (lx, ly), val in self._color_candidates(frame):
            scored.append((val, left + lx, top + ly))

        # Deduplicate points that are within ~22 px of a higher-scoring one.
        scored.sort(key=lambda s: s[0], reverse=True)
        picked: List[Point] = []
        for _s, x, y in scored:
            if all((x - px) ** 2 + (y - py) ** 2 > 22 * 22 for px, py in picked):
                picked.append((int(x), int(y)))
            if len(picked) >= max_candidates:
                break
        return picked

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

    def _template_candidates(self, frame: np.ndarray, n: int = 5) -> List[tuple]:
        """Return up to n template-match peaks as ((local_x, local_y), score).

        Threshold is deliberately loose because the gear-cursor check downstream
        rejects false peaks -- better to over-offer candidates than to miss the
        real bobber when the match is a bit weak.
        """
        if self._template is None:
            return []
        th0, tw0 = self._template.shape[:2]
        # Find the scale that matches best, then pull several peaks from its map.
        best = None  # (res, tw, th, maxval)
        for scale in (0.6, 0.8, 0.9, 1.0, 1.1, 1.25, 1.5):
            tw, th = int(tw0 * scale), int(th0 * scale)
            if tw < 8 or th < 8 or tw >= frame.shape[1] or th >= frame.shape[0]:
                continue
            tmpl = cv2.resize(self._template, (tw, th), interpolation=cv2.INTER_AREA)
            res = cv2.matchTemplate(frame, tmpl, cv2.TM_CCOEFF_NORMED)
            _, mx, _, _ = cv2.minMaxLoc(res)
            if best is None or mx > best[3]:
                best = (res, tw, th, mx)
        if best is None:
            return []
        res, tw, th, _mx = best
        min_val = float(self.b.get("match_threshold", 0.6)) * 0.75  # loose; gear filters
        supp = max(tw, th)
        out: List[tuple] = []
        work = res.copy()
        for _ in range(n):
            _, mv, _, ml = cv2.minMaxLoc(work)
            if mv < min_val:
                break
            cx, cy = ml[0] + tw // 2, ml[1] + th // 2
            out.append(((cx, cy), float(mv)))
            x0, y0 = max(0, ml[0] - supp), max(0, ml[1] - supp)
            x1, y1 = min(work.shape[1], ml[0] + supp), min(work.shape[0], ml[1] + supp)
            work[y0:y1, x0:x1] = -1.0  # suppress around this peak
        return out

    def _color_candidates(self, frame: np.ndarray) -> List[tuple]:
        """Return red+blue-signature points as ((local_x, local_y), score)."""
        h, w = frame.shape[:2]
        max_area = (w * h) * 0.01
        min_area = 10.0
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        red = cv2.inRange(hsv, np.array([0, 80, 70]), np.array([12, 255, 255])) | \
              cv2.inRange(hsv, np.array([166, 80, 70]), np.array([180, 255, 255]))
        blue = cv2.inRange(hsv, np.array([90, 70, 60]), np.array([132, 255, 255]))
        red_blobs = self._blobs(red, min_area, max_area)
        blue_blobs = self._blobs(blue, min_area, max_area)
        out: List[tuple] = []
        for r in red_blobs:
            for b in blue_blobs:
                dist = ((r["x"] - b["x"]) ** 2 + (r["y"] - b["y"]) ** 2) ** 0.5
                if dist > 55:
                    continue
                red_on_top = r["y"] <= b["y"] + 8
                # Aim at the bobber body (between the feathers), a touch low toward
                # the cork that floats on the water.
                tx = (r["x"] + b["x"]) / 2
                ty = (r["y"] + b["y"]) / 2 + 4
                # A red-above-blue pairing is the most trustworthy signal we have --
                # score it ABOVE template peaks so the crate/water never wins.
                score = 1.8 + (0.6 if red_on_top else 0.0) + 0.4 * (1.0 - min(1.0, dist / 55.0))
                out.append(((tx, ty), score))
        # Weak fallback: a lone bobber-sized red feather, ranked below templates.
        for r in sorted(red_blobs, key=lambda k: abs(k["area"] - 120))[:2]:
            out.append(((r["x"], r["y"]), 0.35))
        return out

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
