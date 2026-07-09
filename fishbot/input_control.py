"""Keyboard / mouse output, tuned for DirectX games like WoW.

Regular ``pyautogui`` events are often ignored by DirectX-based games because
they arrive as higher-level Windows messages. ``pydirectinput`` sends hardware
scan codes via ``SendInput``, which WoW accepts. We wrap it behind a small
interface and move the cursor along the human-like paths from :mod:`humanize`.
"""

from __future__ import annotations

import time
from typing import Tuple

from . import humanize

Point = Tuple[float, float]

# --------------------------------------------------------------------------- #
#  Backend selection                                                           #
# --------------------------------------------------------------------------- #
_backend = None
_backend_name = "none"

try:  # preferred: works with DirectX games
    import pydirectinput as _pdi

    _pdi.PAUSE = 0.0            # we handle our own (human) pauses
    _pdi.FAILSAFE = False       # our own hotkeys are the failsafe
    _backend = _pdi
    _backend_name = "pydirectinput"
except Exception:  # pragma: no cover - platform dependent
    try:
        import pyautogui as _pag

        _pag.PAUSE = 0.0
        _pag.FAILSAFE = False
        _backend = _pag
        _backend_name = "pyautogui"
    except Exception:
        _backend = None
        _backend_name = "none"


def backend_name() -> str:
    return _backend_name


class InputController:
    """Sends keystrokes and mouse actions, or logs them in dry-run mode."""

    def __init__(self, human_cfg: dict, dry_run: bool = False):
        self.h = human_cfg
        self.dry_run = dry_run
        if _backend is None and not dry_run:
            raise RuntimeError(
                "No input backend available. Install pydirectinput "
                "(`pip install pydirectinput`) or run with dry_run: true."
            )

    # -- low level ---------------------------------------------------------- #
    def position(self) -> Point:
        if _backend is None:
            return (0.0, 0.0)
        x, y = _backend.position()
        return float(x), float(y)

    def _raw_move(self, x: int, y: int) -> None:
        if self.dry_run or _backend is None:
            return
        _backend.moveTo(int(x), int(y))

    # -- human-like movement ------------------------------------------------ #
    def move_to(self, target: Point, duration: float | None = None) -> None:
        """Glide the cursor to ``target`` along an eased Bezier arc.

        Occasionally overshoots the target and corrects back, the way a person
        does when clicking a small object.
        """
        start = self.position()
        dist = ((target[0] - start[0]) ** 2 + (target[1] - start[1]) ** 2) ** 0.5
        if duration is None:
            duration = humanize.rand_range(self.h.get("mouse_speed", [0.25, 0.55]))
        # Very short hops don't need a whole arc.
        if dist < 3:
            self._raw_move(int(target[0]), int(target[1]))
            return

        over = humanize.maybe_overshoot(
            target, dist, self.h.get("mouse_overshoot", 0.35)
        )
        if over is not None:
            self._glide(start, over, duration * 0.8)
            start = self.position()
            self._glide(start, target, duration * 0.35)
        else:
            self._glide(start, target, duration)

    def _glide(self, start: Point, end: Point, duration: float) -> None:
        steps = max(12, int(duration / 0.012))
        path = humanize.bezier_path(start, end, steps=steps)
        for pt, delay in humanize.travel_schedule(path, duration):
            self._raw_move(int(pt[0]), int(pt[1]))
            if delay:
                time.sleep(delay)

    def micro_jitter(self) -> None:
        """Nudge the cursor a couple pixels -- idle hand tremor while hovering."""
        radius = int(self.h.get("micro_jitter_px", 3))
        if radius <= 0:
            return
        p = humanize.jitter_point(self.position(), radius)
        self._raw_move(int(p[0]), int(p[1]))

    # -- clicks & keys ------------------------------------------------------ #
    def click(self, button: str = "right", at: Point | None = None) -> None:
        if at is not None:
            self.move_to(at)
            humanize.human_sleep(humanize.rand_ms([40, 130]))
        if self.dry_run or _backend is None:
            return
        # A real press has a small dwell between down and up.
        _backend.mouseDown(button=button)
        time.sleep(humanize.rand_range([0.03, 0.09]))
        _backend.mouseUp(button=button)

    def press_key(self, key: str) -> None:
        if self.dry_run or _backend is None:
            return
        _backend.keyDown(key)
        time.sleep(humanize.rand_range([0.03, 0.10]))
        _backend.keyUp(key)

    def key_combo_click(self, modifier: str, button: str, at: Point | None = None) -> None:
        """Hold ``modifier`` (e.g. shift) while clicking -- used for auto-loot."""
        if at is not None:
            self.move_to(at)
            humanize.human_sleep(humanize.rand_ms([40, 130]))
        if self.dry_run or _backend is None:
            return
        _backend.keyDown(modifier)
        time.sleep(humanize.rand_range([0.02, 0.06]))
        _backend.mouseDown(button=button)
        time.sleep(humanize.rand_range([0.03, 0.09]))
        _backend.mouseUp(button=button)
        time.sleep(humanize.rand_range([0.02, 0.05]))
        _backend.keyUp(modifier)
