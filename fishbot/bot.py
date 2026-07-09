"""The main fishing loop and its control state machine.

Flow per cast:
    1. (human pause) press the cast key
    2. wait for the line to settle, then locate the bobber
    3. arm the splash detector and watch for the bite
    4. (human reaction delay) shift-right-click the bobber to loot
    5. occasionally take a break / get distracted; enforce session limits

Global hotkeys (default F9 pause/resume, F10 quit) let you take control at any
time without alt-tabbing to a terminal.
"""

from __future__ import annotations

import random
import threading
import time
from dataclasses import dataclass, field

from . import humanize
from .bobber import BobberFinder
from .capture import ScreenCapture
from .config import Config
from .input_control import InputController, backend_name
from .splash import PixelSplashDetector, make_detector

try:
    import keyboard as _kb
except Exception:  # pragma: no cover
    _kb = None


@dataclass
class Stats:
    casts: int = 0
    catches: int = 0
    misses: int = 0
    fumbles: int = 0
    started_at: float = field(default_factory=time.monotonic)

    def summary(self) -> str:
        mins = (time.monotonic() - self.started_at) / 60.0
        rate = self.catches / mins if mins > 0 else 0.0
        return (
            f"casts={self.casts} catches={self.catches} misses={self.misses} "
            f"fumbles={self.fumbles} time={mins:.1f}min "
            f"({rate:.1f} catches/min)"
        )


class FishingBot:
    def __init__(self, config: Config):
        self.cfg = config
        self.controller = InputController(config.human, dry_run=config.control.get("dry_run", False))
        self.capture = ScreenCapture()
        self.finder = BobberFinder(config, self.capture, self.controller)
        self.detector = make_detector(config, self.capture)
        self.stats = Stats()

        self._paused = bool(config.control.get("start_paused", True))
        self._quit = False
        self._casts_until_break = humanize.rand_int_range(
            config.human.get("break_every_casts", [55, 120])
        )
        self._register_hotkeys()

    # ------------------------------------------------------------------ #
    #  Control                                                            #
    # ------------------------------------------------------------------ #
    def _register_hotkeys(self) -> None:
        if _kb is None:
            print("[control] `keyboard` not installed -- hotkeys disabled. "
                  "Use Ctrl+C in the terminal to stop.")
            return
        toggle = self.cfg.control.get("hotkey_toggle", "f9")
        quit_key = self.cfg.control.get("hotkey_quit", "f10")
        try:
            _kb.add_hotkey(toggle, self._toggle_pause)
            _kb.add_hotkey(quit_key, self.stop)
            print(f"[control] {toggle.upper()} = pause/resume, {quit_key.upper()} = quit")
        except Exception as exc:  # pragma: no cover
            print(f"[control] could not register hotkeys ({exc}); use Ctrl+C.")

    def _toggle_pause(self) -> None:
        self._paused = not self._paused
        state = "PAUSED" if self._paused else "RUNNING"
        print(f"\n[control] {state}  |  {self.stats.summary()}")

    def stop(self) -> None:
        self._quit = True
        print("\n[control] stopping...")

    def _wait_while_paused(self) -> None:
        announced = False
        while self._paused and not self._quit:
            if not announced:
                print("[control] paused -- press the toggle hotkey to start fishing.")
                announced = True
            time.sleep(0.1)

    # ------------------------------------------------------------------ #
    #  Main loop                                                          #
    # ------------------------------------------------------------------ #
    def run(self) -> None:
        print(f"[bot] input backend: {backend_name()}  "
              f"dry_run={self.cfg.control.get('dry_run', False)}")
        print(f"[bot] bobber strategy: {self.cfg.bobber.get('strategy')}  "
              f"splash: {type(self.detector).__name__}")
        max_minutes = float(self.cfg.human.get("max_session_minutes", 150))
        try:
            while not self._quit:
                self._wait_while_paused()
                if self._quit:
                    break
                if (time.monotonic() - self.stats.started_at) / 60.0 >= max_minutes:
                    print(f"[bot] session limit reached ({max_minutes} min). Stopping.")
                    break
                self._one_cast_cycle()
                self._maybe_break()
        except KeyboardInterrupt:
            print("\n[bot] interrupted.")
        finally:
            self._shutdown()

    def _one_cast_cycle(self) -> None:
        cfg = self.cfg
        # Occasional fumble: pretend we misclicked and just recast, wasting a beat.
        if random.random() < cfg.human.get("fumble_chance", 0.02):
            self.stats.fumbles += 1
            humanize.human_sleep(humanize.rand_range([0.4, 1.3]))

        # 1) Cast (with a human pre-press hesitation).
        humanize.human_sleep(humanize.rand_ms(cfg.human.get("cast_delay_ms", [90, 420])))
        self._cast()
        self.stats.casts += 1

        # 2) Let the line settle, then find the bobber.
        humanize.human_sleep(humanize.jittered(cfg.timing.get("post_cast_wait", 1.6), 0.2))
        if self._paused or self._quit:
            return
        bobber = self.finder.find()
        if bobber is None:
            self.stats.misses += 1
            print(f"[cast {self.stats.casts}] bobber not found; recasting.")
            humanize.human_sleep(humanize.rand_range([0.3, 0.9]))
            return

        # Hover the bobber with a little idle tremor while we wait for the bite.
        self.controller.move_to(bobber)
        if isinstance(self.detector, PixelSplashDetector):
            self.detector.set_target(bobber)

        # 3) Arm & wait for the splash.
        self.detector.arm()
        timeout = humanize.jittered(cfg.timing.get("bite_timeout", 26.0), 0.05)
        got_bite = self._watch_for_bite(timeout)
        if not got_bite:
            self.stats.misses += 1
            print(f"[cast {self.stats.casts}] no bite ({timeout:.0f}s); recasting.")
            return

        # 4) React like a human, then loot.
        humanize.human_sleep(humanize.rand_ms(cfg.human.get("reaction_ms", [180, 520])))
        if self._paused or self._quit:
            return
        self._loot(bobber)
        self.stats.catches += 1
        print(f"[cast {self.stats.casts}] catch! {self.stats.summary()}")

        # 5) Maybe get briefly distracted before the next cast.
        self._maybe_distraction()
        base_gap = cfg.timing.get("min_cast_interval", 0.0)
        humanize.human_sleep(humanize.jittered(base_gap + 0.4, 0.4))

    def _watch_for_bite(self, timeout: float) -> bool:
        """Wait for a splash, keeping a light idle tremor on the cursor."""
        # Split the wait so we can micro-jitter and honor pause/quit mid-wait.
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._paused or self._quit:
                return False
            slice_time = min(2.0, deadline - time.monotonic())
            if self.detector.wait_for_splash(slice_time):
                return True
            self.controller.micro_jitter()
        return False

    # ------------------------------------------------------------------ #
    #  Actions                                                            #
    # ------------------------------------------------------------------ #
    def _cast(self) -> None:
        self.controller.press_key(str(self.cfg.keys.get("cast", "8")))

    def _loot(self, bobber) -> None:
        mod = self.cfg.keys.get("loot_modifier", "shift")
        button = self.cfg.keys.get("interact_button", "right")
        if mod:
            self.controller.key_combo_click(mod, button, at=bobber)
        else:
            self.controller.click(button, at=bobber)

    # ------------------------------------------------------------------ #
    #  Human breaks / distractions                                        #
    # ------------------------------------------------------------------ #
    def _maybe_distraction(self) -> None:
        if random.random() > self.cfg.human.get("distraction_chance", 0.05):
            return
        secs = humanize.rand_range(self.cfg.human.get("distraction_secs", [1.5, 6.0]))
        print(f"[bot] ...distracted for {secs:.1f}s")
        # Drift the mouse somewhere idle, as if glancing away.
        left, top, width, height = self.cfg.region
        idle = (left + random.randint(0, width), top + random.randint(0, height))
        self.controller.move_to(idle, duration=humanize.rand_range([0.4, 1.0]))
        humanize.human_sleep(secs)

    def _maybe_break(self) -> None:
        self._casts_until_break -= 1
        if self._casts_until_break > 0:
            return
        secs = humanize.rand_range(self.cfg.human.get("break_secs", [25, 140]))
        print(f"[bot] taking a break for {secs:.0f}s  |  {self.stats.summary()}")
        # Break is interruptible by pause/quit.
        end = time.monotonic() + secs
        while time.monotonic() < end and not self._quit:
            if self._paused:
                break
            time.sleep(0.2)
        self._casts_until_break = humanize.rand_int_range(
            self.cfg.human.get("break_every_casts", [55, 120])
        )

    # ------------------------------------------------------------------ #
    def _shutdown(self) -> None:
        print(f"\n[bot] final: {self.stats.summary()}")
        try:
            self.detector.close()
        except Exception:
            pass
        try:
            self.capture.close()
        except Exception:
            pass
