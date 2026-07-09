"""Human-likeness helpers: natural timing, Bezier mouse paths, jitter, breaks.

The goal of this module is to make every timing and movement decision look like
it came from a slightly bored, imperfect human hand rather than a metronome.
Nothing here is a fixed constant -- everything is drawn from a distribution.
"""

from __future__ import annotations

import math
import random
import time
from typing import Iterable, List, Sequence, Tuple

Point = Tuple[float, float]


# --------------------------------------------------------------------------- #
#  Timing                                                                      #
# --------------------------------------------------------------------------- #
def jittered(base: float, spread: float = 0.15) -> float:
    """Return ``base`` seconds nudged by a small Gaussian, clamped to >= 0.

    ``spread`` is a fraction of ``base`` used as the standard deviation, so the
    variance scales with the magnitude of the delay -- long waits wobble more
    than short ones, just like human patience.
    """
    if base <= 0:
        return max(0.0, random.gauss(0, spread))
    val = random.gauss(base, base * spread)
    return max(0.0, val)


def rand_range(bounds: Sequence[float]) -> float:
    """Uniform float within ``[lo, hi]`` given a 2-element sequence."""
    lo, hi = bounds
    return random.uniform(lo, hi)


def rand_ms(bounds: Sequence[float]) -> float:
    """Like :func:`rand_range` but the bounds are in milliseconds; returns seconds."""
    return rand_range(bounds) / 1000.0


def rand_int_range(bounds: Sequence[float]) -> int:
    lo, hi = bounds
    return random.randint(int(lo), int(hi))


def human_sleep(seconds: float, *, chunk: float = 0.05) -> None:
    """Sleep in small chunks so the bot stays responsive to pause/quit hotkeys.

    A single ``time.sleep(30)`` would make F9/F10 feel dead for 30s; chunking
    keeps the control loop lively while still, overall, waiting the right time.
    """
    end = time.monotonic() + max(0.0, seconds)
    while True:
        remaining = end - time.monotonic()
        if remaining <= 0:
            return
        time.sleep(min(chunk, remaining))


# --------------------------------------------------------------------------- #
#  Mouse pathing                                                               #
# --------------------------------------------------------------------------- #
def _bezier(p0: Point, p1: Point, p2: Point, p3: Point, t: float) -> Point:
    """Cubic Bezier interpolation at parameter ``t`` in [0, 1]."""
    mt = 1 - t
    a = mt * mt * mt
    b = 3 * mt * mt * t
    c = 3 * mt * t * t
    d = t * t * t
    x = a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0]
    y = a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1]
    return x, y


def _ease(t: float) -> float:
    """Ease-in-out so the cursor accelerates then decelerates, not linear."""
    return 0.5 - 0.5 * math.cos(math.pi * t)


def bezier_path(
    start: Point,
    end: Point,
    *,
    steps: int = 60,
    curviness: float = 0.22,
) -> List[Point]:
    """Build a curved, eased list of points from ``start`` to ``end``.

    The two control points are offset perpendicular to the travel direction by a
    random amount, giving a gentle arc that differs every call. Points are
    distributed with an ease curve so speed ramps up and down naturally.
    """
    sx, sy = start
    ex, ey = end
    dx, dy = ex - sx, ey - sy
    dist = math.hypot(dx, dy) or 1.0

    # Perpendicular unit vector for bowing the path sideways.
    px, py = -dy / dist, dx / dist
    bow = dist * curviness
    off1 = random.uniform(-bow, bow)
    off2 = random.uniform(-bow, bow)

    c1 = (sx + dx * 0.33 + px * off1, sy + dy * 0.33 + py * off1)
    c2 = (sx + dx * 0.66 + px * off2, sy + dy * 0.66 + py * off2)

    pts: List[Point] = []
    for i in range(steps + 1):
        t = _ease(i / steps)
        pts.append(_bezier(start, c1, c2, end, t))
    return pts


def maybe_overshoot(end: Point, dist: float, chance: float) -> Point | None:
    """With probability ``chance`` return a point slightly *past* the target.

    Humans frequently fly past a small target and then correct back onto it. The
    caller moves to this overshoot point first, then to the real target.
    """
    if random.random() > chance:
        return None
    over = random.uniform(0.05, 0.16) * max(dist, 40)
    ang = random.uniform(0, 2 * math.pi)
    return end[0] + math.cos(ang) * over, end[1] + math.sin(ang) * over


def travel_schedule(points: Iterable[Point], duration: float) -> List[Tuple[Point, float]]:
    """Pair each path point with a per-step sleep so the whole move takes ``duration``.

    Tiny random noise is added to each step delay so the cadence is not perfectly
    uniform even along a single stroke.
    """
    points = list(points)
    n = max(1, len(points) - 1)
    base = duration / n
    schedule: List[Tuple[Point, float]] = []
    for pt in points:
        delay = max(0.0, base * random.uniform(0.6, 1.4))
        schedule.append((pt, delay))
    return schedule


def jitter_point(p: Point, radius: int) -> Point:
    """Return ``p`` displaced by up to ``radius`` px -- idle hand tremor."""
    if radius <= 0:
        return p
    return (
        p[0] + random.uniform(-radius, radius),
        p[1] + random.uniform(-radius, radius),
    )
