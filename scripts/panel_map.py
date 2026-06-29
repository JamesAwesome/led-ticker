"""panel-map — derive and verify a pixel_mapper_config Remap string.

  reveal   Paint each panel with its chain index + orientation markers (NO
           mapper applied) so a photo reveals the physical layout. [hardware]
  derive   Turn the transcribed ASCII grid into a Remap string. [no hardware]
  verify   Apply a candidate mapper and paint a self-diagnosing pattern so a
           wrong mapper is visibly, per-panel obvious. [hardware]

Full workflow + orientation legend: docs.ledticker.dev/tools/panel-map/
Run `make panel-test` first to rule out wiring/driver problems.
"""

from __future__ import annotations

import argparse
import dataclasses
import logging
import sys
import time
from pathlib import Path

from led_ticker.app.factories import build_frame_from_config
from led_ticker.config import load_config
from led_ticker.panel_map import (
    LayoutError,
    derive_remap_string,
    paint_reveal,
    paint_verify,
)

# Shared --config argument inherited by every subcommand via parents=[].
_CONFIG_PARENT = argparse.ArgumentParser(add_help=False)
_CONFIG_PARENT.add_argument(
    "--config",
    type=Path,
    default=Path("config/config.bigsign.example.toml"),
    help="Config TOML; only [display] geometry is used.",
)


def _hold_loop(frame, canvas, paint, hold):
    """Repaint + swap at `hold` cadence until Ctrl-C, then clear."""
    try:
        while True:
            paint(canvas)
            canvas = frame.matrix.SwapOnVSync(canvas)  # constraint #1
            time.sleep(hold)
    except KeyboardInterrupt:
        logging.info("Interrupted — clearing panel.")
        canvas.Fill(0, 0, 0)
        canvas = frame.matrix.SwapOnVSync(canvas)
        return 0


def _cmd_reveal(args, display):
    # Force identity mapper so the canvas is the raw data chain.
    d = dataclasses.replace(display, pixel_mapper_config="")
    frame = build_frame_from_config(d)
    canvas = frame.get_clean_canvas()
    logging.info(
        "reveal: %d panels (chain_length=%d parallel=%d), no mapper. "
        "Photograph the wall; transcribe the grid; run `derive`.",
        d.chain_length * d.parallel,
        d.chain_length,
        d.parallel,
    )

    def paint(c):
        paint_reveal(
            c,
            cols=d.cols,
            rows=d.rows,
            chain_length=d.chain_length,
            parallel=d.parallel,
        )

    return _hold_loop(frame, canvas, paint, args.hold)


def _cmd_derive(args, display):
    text = args.layout.read_text() if args.layout else sys.stdin.read()
    try:
        out = derive_remap_string(
            text,
            cols=display.cols,
            rows=display.rows,
            chain_length=display.chain_length,
            parallel=display.parallel,
        )
    except LayoutError as exc:
        logging.error("%s", exc)
        return 2
    n_cells = out.count("|")
    expected = display.chain_length * display.parallel
    if n_cells != expected:
        logging.warning(
            "Grid has %d panels but [display] expects %d "
            "(chain_length×parallel). Deriving for the grid as typed.",
            n_cells,
            expected,
        )
    print(out)  # the string on stdout, pipeable
    return 0


def _cmd_verify(args, display):
    mapper = args.mapper or display.pixel_mapper_config
    if not mapper:
        logging.error(
            "No mapper to verify. Pass --mapper 'Remap:...' or set "
            "pixel_mapper_config in the config."
        )
        return 2
    frame = build_frame_from_config(
        dataclasses.replace(display, pixel_mapper_config=mapper)
    )
    canvas = frame.get_clean_canvas()
    logging.info("verify: applying mapper %r", mapper)

    def paint(c):
        paint_verify(c, mapper=mapper, cols=display.cols, rows=display.rows)

    return _hold_loop(frame, canvas, paint, args.hold)


def _parse_args():
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    pr = sub.add_parser(
        "reveal",
        parents=[_CONFIG_PARENT],
        help="Paint chain index + orientation, no mapper.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Run `make panel-test` first to confirm your panels light up cleanly"
            " with solid colors. If colors look wrong there, fix that before using"
            " panel-map — it can't help with wiring/driver problems."
        ),
    )
    pr.add_argument(
        "--hold",
        type=float,
        default=2.0,
        help=(
            "Repaint interval in seconds (default: 2.0)."
            " Press Ctrl-C to stop and clear the panel."
        ),
    )
    pr.set_defaults(func=_cmd_reveal)

    pd = sub.add_parser(
        "derive",
        parents=[_CONFIG_PARENT],
        help="ASCII grid (stdin or --layout) -> Remap string.",
    )
    pd.add_argument(
        "--layout",
        type=Path,
        default=None,
        help=(
            "File with the transcribed grid (one cell per panel, e.g. '3n' '1s';"
            " top wall row first). Omit to read the grid from stdin."
        ),
    )
    pd.set_defaults(func=_cmd_derive)

    pv = sub.add_parser(
        "verify",
        parents=[_CONFIG_PARENT],
        help="Apply a candidate mapper, paint a diagnostic pattern.",
    )
    pv.add_argument(
        "--hold",
        type=float,
        default=2.0,
        help=(
            "Repaint interval in seconds (default: 2.0)."
            " Press Ctrl-C to stop and clear the panel."
        ),
    )
    pv.add_argument(
        "--mapper",
        default=None,
        help="Remap string to verify. Omit to use the config's.",
    )
    pv.set_defaults(func=_cmd_verify)
    return p.parse_args()


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr)
    args = _parse_args()
    config = load_config(args.config)
    for w in config._coerce_warnings:
        logging.warning("config coerce: %s", w.message)
    return args.func(args, config.display)


if __name__ == "__main__":
    sys.exit(main())
