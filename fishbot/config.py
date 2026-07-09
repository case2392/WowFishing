"""Configuration loading and typed access.

Reads ``config.yaml`` into small dataclasses so the rest of the code gets
attribute access with sensible defaults instead of dictionary spelunking.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List

import yaml

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge ``override`` into a copy of ``base``."""
    out = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


# Baseline so a partial config.yaml still produces a fully-formed object.
_DEFAULTS: dict = {
    "keys": {"cast": "8", "loot_modifier": "shift", "interact_button": "right"},
    "region": [335, 175, 1115, 705],
    "ignore_zones": [],
    "bobber": {
        "strategy": "cursor_scan",
        "template_path": "assets/bobber.png",
        "match_threshold": 0.62,
        "scan_step": 22,
        "scan_settle_ms": 9,
    },
    "splash": {
        "method": "sound",
        "sound_threshold": 0.16,
        "sound_cooldown_ms": 1500,
        "pixel_watch_radius": 45,
        "pixel_change_ratio": 0.06,
    },
    "timing": {
        "bite_timeout": 26.0,
        "post_cast_wait": 1.6,
        "min_cast_interval": 0.0,
    },
    "human": {
        "reaction_ms": [180, 520],
        "mouse_speed": [0.25, 0.55],
        "mouse_overshoot": 0.35,
        "micro_jitter_px": 3,
        "cast_delay_ms": [90, 420],
        "distraction_chance": 0.05,
        "distraction_secs": [1.5, 6.0],
        "break_every_casts": [55, 120],
        "break_secs": [25, 140],
        "max_session_minutes": 150,
        "fumble_chance": 0.02,
    },
    "control": {
        "hotkey_toggle": "f9",
        "hotkey_quit": "f10",
        "start_paused": True,
        "dry_run": False,
    },
}


@dataclass
class Config:
    keys: dict
    region: List[int]
    ignore_zones: list
    bobber: dict
    splash: dict
    timing: dict
    human: dict
    control: dict
    raw: dict = field(default_factory=dict)
    path: Path = DEFAULT_CONFIG_PATH

    @classmethod
    def load(cls, path: str | Path | None = None) -> "Config":
        path = Path(path) if path else DEFAULT_CONFIG_PATH
        user: dict[str, Any] = {}
        if path.exists():
            with open(path, "r", encoding="utf-8") as fh:
                user = yaml.safe_load(fh) or {}
        merged = _deep_merge(_DEFAULTS, user)
        return cls(
            keys=merged["keys"],
            region=list(merged["region"]),
            ignore_zones=list(merged.get("ignore_zones", [])),
            bobber=merged["bobber"],
            splash=merged["splash"],
            timing=merged["timing"],
            human=merged["human"],
            control=merged["control"],
            raw=merged,
            path=path,
        )

    def save(self, path: str | Path | None = None) -> None:
        """Write the current config back to disk (used by the calibrator)."""
        path = Path(path) if path else self.path
        data = {
            "keys": self.keys,
            "region": self.region,
            "ignore_zones": self.ignore_zones,
            "bobber": self.bobber,
            "splash": self.splash,
            "timing": self.timing,
            "human": self.human,
            "control": self.control,
        }
        with open(path, "w", encoding="utf-8") as fh:
            yaml.safe_dump(data, fh, sort_keys=False, default_flow_style=False)
