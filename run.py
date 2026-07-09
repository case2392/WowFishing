#!/usr/bin/env python3
"""Entry point for the WoW Classic fishing bot.

Usage:
    python run.py                 # use config.yaml
    python run.py --config my.yaml
    python run.py --dry-run       # detect & log, but never send input
"""

from __future__ import annotations

import argparse
import sys

from fishbot.bot import FishingBot
from fishbot.config import Config

BANNER = r"""
  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
   WoW Classic Fishing Bot
   Cast -> spot bobber -> wait for splash -> loot -> repeat
  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="WoW Classic fishing bot")
    parser.add_argument("--config", default=None, help="path to config.yaml")
    parser.add_argument("--dry-run", action="store_true",
                        help="detect and log, but never press keys or click")
    args = parser.parse_args()

    print(BANNER)
    cfg = Config.load(args.config)
    if args.dry_run:
        cfg.control["dry_run"] = True

    print("Tips:")
    print("  * Make sure WoW is in *windowed (fullscreen)* mode, not exclusive fullscreen.")
    print("  * Enable Auto Loot in Interface options for clean pickups.")
    print("  * Stand still, face the water, and equip a fishing pole first.")
    print(f"  * Config: {cfg.path}")
    print()

    try:
        bot = FishingBot(cfg)
    except RuntimeError as exc:
        print(f"[fatal] {exc}")
        return 2

    bot.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
