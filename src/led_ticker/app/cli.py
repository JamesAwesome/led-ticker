"""CLI entry point for led-ticker.

Parses argv, dispatches to `validate` subcommand or the main run loop.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from led_ticker.app.factories import _list_widget_fields
from led_ticker.app.run import run


def _setup_logging() -> None:
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)


def main() -> None:
    """CLI entry point."""
    _setup_logging()

    parser = argparse.ArgumentParser(description="LED Ticker Display")
    # Top-level --config kept for back-compat: `led-ticker --config foo.toml`
    parser.add_argument(
        "--config",
        "-c",
        type=Path,
        default=Path("config.toml"),
        help="Path to TOML configuration file (default: config.toml)",
    )

    subparsers = parser.add_subparsers(dest="command")

    # `validate` subcommand
    val_parser = subparsers.add_parser(
        "validate",
        help="Validate a config file without running the display",
    )
    val_parser.add_argument(
        "path",
        type=Path,
        nargs="?",
        default=None,
        help="Path to TOML config file (required unless --list-fields is given)",
    )
    val_parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Emit JSON output",
    )
    val_parser.add_argument(
        "--list-fields",
        metavar="TYPE",
        dest="list_fields",
        default=None,
        help=(
            "Print all valid fields for a widget type and exit "
            "(e.g. --list-fields message)"
        ),
    )

    args = parser.parse_args()

    if args.command == "validate":
        if args.list_fields is not None:
            try:
                print(_list_widget_fields(args.list_fields))
            except ValueError as e:
                print(str(e), file=sys.stderr)
                sys.exit(2)
            sys.exit(0)

        if args.path is None:
            val_parser.print_usage(sys.stderr)
            print(
                "error: path is required when --list-fields is not given",
                file=sys.stderr,
            )
            sys.exit(2)

        from led_ticker.validate import (  # noqa: PLC0415
            _format_human,
            _format_json,
            validate_config,
        )

        try:
            result = asyncio.run(validate_config(args.path))
        except FileNotFoundError as e:
            print(str(e), file=sys.stderr)
            sys.exit(2)

        if args.json_output:
            print(_format_json(result))
        else:
            print(_format_human(result))

        sys.exit(0 if result.valid else 1)

    # Default: run the display (back-compat path)
    if not args.config.exists():
        print(f"Config file not found: {args.config}", file=sys.stderr)
        print(
            "Copy config.example.toml to config.toml and customize it.",
            file=sys.stderr,
        )
        sys.exit(1)

    asyncio.run(run(args.config))


if __name__ == "__main__":
    main()
