"""Full-panel color diagnostic.

Cycles the panel through Red → Green → Blue → White → Black, looping
forever until Ctrl-C. Reuses the same config loader and LedFrame
construction the main app uses, so all hardware knobs (panel_type,
led_rgb_sequence, chain_length, gpio_slowdown, rp1_rio, etc.) come straight
from the config TOML.

Use this to isolate hardware/wiring/driver issues from config issues.
A green Red means led_rgb_sequence is wrong. A garbled bottom half
means panel_type isn't initializing the FM6126A. Etc. See
docs.ledticker.dev/tools/panel-test/ for the full diagnostic matrix.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

from led_ticker.app.factories import build_frame_from_config
from led_ticker.config import load_config

COLORS: list[tuple[str, int, int, int]] = [
    ("Red", 255, 0, 0),
    ("Green", 0, 255, 0),
    ("Blue", 0, 0, 255),
    ("White", 255, 255, 255),
    ("Black", 0, 0, 0),
]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Cycle the panel through full-frame R/G/B/White/Black to "
            "diagnose hardware/wiring/driver issues independent of config."
        ),
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/config.longboi.toml"),
        help=(
            "Path to a led-ticker config TOML. Only [display] is used; "
            "widget/section config is ignored. Default: config/config.longboi.toml."
        ),
    )
    parser.add_argument(
        "--hold",
        type=float,
        default=2.0,
        help="Seconds to hold each color before advancing. Default: 2.0.",
    )
    return parser.parse_args()


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
        stream=sys.stderr,
    )
    args = _parse_args()

    config = load_config(args.config)
    # Mirror app/run.py: surface any coercion warnings from load_config so
    # diagnostic output matches what users see when running the main app.
    for w in config._coerce_warnings:
        logging.warning("config coerce: %s", w.message)

    frame = build_frame_from_config(config.display)
    canvas = frame.get_clean_canvas()

    n = len(COLORS)
    try:
        i = 0
        while True:
            name, r, g, b = COLORS[i % n]
            logging.info("[%d/%d] %s (%d, %d, %d)", (i % n) + 1, n, name, r, g, b)
            canvas.Fill(r, g, b)
            # Constraint #1: SwapOnVSync return value MUST be captured.
            canvas = frame.matrix.SwapOnVSync(canvas)
            time.sleep(args.hold)
            i += 1
    except KeyboardInterrupt:
        logging.info("Interrupted — clearing panel.")
        canvas.Fill(0, 0, 0)
        canvas = frame.matrix.SwapOnVSync(canvas)
        return 0


if __name__ == "__main__":
    sys.exit(main())
