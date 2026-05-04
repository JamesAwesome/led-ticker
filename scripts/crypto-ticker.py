#!/usr/bin/env python3
"""Legacy entry point — use `led-ticker` CLI instead."""

import sys

from led_ticker.app import main

print(
    "WARNING: crypto-ticker.py is deprecated. Use `led-ticker --config "
    "config.toml` instead.",
    file=sys.stderr,
)

main()
