"""Fast screen capture helpers built on ``mss``.

A single :class:`ScreenCapture` instance is reused for the whole session so we
are not re-allocating grab buffers every frame.
"""

from __future__ import annotations

from typing import Sequence, Tuple

import numpy as np

try:
    import mss
except Exception:  # pragma: no cover
    mss = None


class ScreenCapture:
    def __init__(self):
        if mss is None:
            raise RuntimeError("mss is not installed. Run: pip install mss")
        self._sct = mss.mss()

    def grab(self, region: Sequence[int]) -> np.ndarray:
        """Grab ``[left, top, width, height]`` and return a BGR uint8 array."""
        left, top, width, height = region
        mon = {"left": int(left), "top": int(top), "width": int(width), "height": int(height)}
        raw = self._sct.grab(mon)
        # mss returns BGRA; drop alpha, keep BGR (what OpenCV expects).
        arr = np.asarray(raw)[:, :, :3]
        return np.ascontiguousarray(arr)

    def grab_around(self, center: Tuple[int, int], radius: int) -> Tuple[np.ndarray, Sequence[int]]:
        """Grab a square of half-size ``radius`` centered on ``center``.

        Returns the image and the region used, so callers can map coordinates.
        """
        cx, cy = center
        region = [int(cx - radius), int(cy - radius), int(radius * 2), int(radius * 2)]
        return self.grab(region), region

    def close(self):
        try:
            self._sct.close()
        except Exception:
            pass
