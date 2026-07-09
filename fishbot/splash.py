"""Detecting the "bite" -- the moment the bobber splashes.

Two detectors:

* :class:`SoundSplashDetector` (Windows): opens a WASAPI *loopback* stream of the
  system's own audio output and watches for a sudden loudness spike. The fishing
  splash is a sharp transient that stands out clearly. This is the most robust
  method because it does not care what the water looks like, and it mirrors how a
  human actually notices a bite (they hear it).

* :class:`PixelSplashDetector` (cross-platform): watches a small box around the
  bobber and fires when enough pixels change from the calm baseline -- the white
  foam of the splash.

Both expose ``arm()`` (call right after casting) and ``wait_for_splash(timeout)``.
"""

from __future__ import annotations

import time
from typing import Optional, Tuple

import numpy as np

try:
    import cv2
except Exception:  # pragma: no cover
    cv2 = None

from . import humanize

Point = Tuple[int, int]


# --------------------------------------------------------------------------- #
#  Sound                                                                       #
# --------------------------------------------------------------------------- #
class SoundSplashDetector:
    """Loudness-spike detector over a WASAPI loopback stream."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.s = cfg.splash
        self._pa = None
        self._stream = None
        self._baseline = 0.0
        self._open_stream()

    def _open_stream(self) -> None:
        try:
            import pyaudiowpatch as pyaudio
        except Exception as exc:  # pragma: no cover
            raise RuntimeError(
                "Sound splash detection needs PyAudioWPatch (Windows). "
                "Install it, or set splash.method: pixel in config.yaml.\n"
                f"Underlying error: {exc}"
            )
        self._pa = pyaudio.PyAudio()
        # Find the default output device's loopback companion.
        wasapi = self._pa.get_host_api_info_by_type(pyaudio.paWASAPI)
        default_out = self._pa.get_device_info_by_index(wasapi["defaultOutputDevice"])
        loopback = None
        for dev in self._pa.get_loopback_device_info_generator():
            if default_out["name"] in dev["name"]:
                loopback = dev
                break
        if loopback is None:  # fall back to first loopback device
            for dev in self._pa.get_loopback_device_info_generator():
                loopback = dev
                break
        if loopback is None:
            raise RuntimeError("No WASAPI loopback device found.")

        self._rate = int(loopback["defaultSampleRate"])
        self._channels = int(loopback["maxInputChannels"])
        self._stream = self._pa.open(
            format=pyaudio.paInt16,
            channels=self._channels,
            rate=self._rate,
            frames_per_buffer=1024,
            input=True,
            input_device_index=loopback["index"],
        )

    def _read_level(self) -> float:
        """Return normalized RMS loudness (0..~1) of the latest audio chunk."""
        try:
            avail = self._stream.get_read_available()
            frames = self._stream.read(max(1024, avail), exception_on_overflow=False)
        except Exception:
            return 0.0
        samples = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
        if samples.size == 0:
            return 0.0
        return float(np.sqrt(np.mean(samples ** 2)))

    def arm(self) -> None:
        # Drain any buffered audio (the cast "plop") and sample a calm baseline.
        cooldown = self.s.get("sound_cooldown_ms", 1500) / 1000.0
        humanize.human_sleep(cooldown)
        levels = [self._read_level() for _ in range(5)]
        self._baseline = float(np.median(levels)) if levels else 0.0

    def wait_for_splash(self, timeout: float) -> bool:
        threshold = float(self.s.get("sound_threshold", 0.16))
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            level = self._read_level()
            # Fire on an absolute spike OR a big jump over the calm baseline.
            if level >= threshold or (level - self._baseline) >= threshold:
                return True
            time.sleep(0.01)
        return False

    def close(self) -> None:
        try:
            if self._stream:
                self._stream.stop_stream()
                self._stream.close()
            if self._pa:
                self._pa.terminate()
        except Exception:
            pass


# --------------------------------------------------------------------------- #
#  Pixel                                                                       #
# --------------------------------------------------------------------------- #
class PixelSplashDetector:
    """Watches a small region around the bobber for the splash foam."""

    def __init__(self, cfg, capture):
        if cv2 is None:
            raise RuntimeError("Pixel splash detection needs opencv-python.")
        self.cfg = cfg
        self.s = cfg.splash
        self.capture = capture
        self._center: Optional[Point] = None
        self._baseline: Optional[np.ndarray] = None
        self._region = None

    def set_target(self, center: Point) -> None:
        self._center = center

    def arm(self) -> None:
        if self._center is None:
            raise RuntimeError("Pixel detector armed without a bobber target.")
        radius = int(self.s.get("pixel_watch_radius", 45))
        img, region = self.capture.grab_around(self._center, radius)
        self._region = region
        self._baseline = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.int16)

    def wait_for_splash(self, timeout: float) -> bool:
        if self._baseline is None or self._region is None:
            return False
        ratio_needed = float(self.s.get("pixel_change_ratio", 0.06))
        total = self._baseline.size
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            img = self.capture.grab(self._region)
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.int16)
            if gray.shape != self._baseline.shape:
                return False
            diff = np.abs(gray - self._baseline)
            changed = int(np.count_nonzero(diff > 35))
            if changed / total >= ratio_needed:
                return True
            time.sleep(0.03)
        return False

    def close(self) -> None:
        pass


def make_detector(cfg, capture):
    """Factory: build the splash detector named in the config, with fallback."""
    method = cfg.splash.get("method", "sound")
    if method == "sound":
        try:
            return SoundSplashDetector(cfg)
        except Exception as exc:
            print(f"[splash] sound detector unavailable ({exc}); using pixel.")
            return PixelSplashDetector(cfg, capture)
    return PixelSplashDetector(cfg, capture)
