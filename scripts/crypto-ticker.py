#!/usr/bin/env python3
"""Legacy entry point — use `led-ticker` CLI instead."""

import sys
print(
    "WARNING: crypto-ticker.py is deprecated. Use `led-ticker --config config.toml` instead.",
    file=sys.stderr,
)

from led_ticker.app import main
main()
