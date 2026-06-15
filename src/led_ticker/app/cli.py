"""CLI entry point for led-ticker.

Parses argv, dispatches to `validate` subcommand or the main run loop.
"""

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


def _format_plugins(result) -> str:
    """Human-readable summary of loaded + failed plugins for `led-ticker plugins`."""
    lines: list[str] = []
    if not result.loaded and not result.failed:
        return "No plugins found."
    if result.loaded:
        lines.append(f"Loaded {len(result.loaded)} plugin(s):")
        for info in result.loaded:
            lines.append(f"  {info.namespace}  [{info.source}]")
            names = getattr(info, "names", {}) or {}
            if names:
                for surface in sorted(names):
                    lines.append(f"      {surface}: {', '.join(names[surface])}")
            elif info.counts:
                contrib = ", ".join(f"{k}: {v}" for k, v in sorted(info.counts.items()))
                lines.append(f"      {contrib}")
            else:
                lines.append("      (hooks only)")
    if result.failed:
        lines.append(f"Failed {len(result.failed)} plugin(s):")
        for ns, err in result.failed:
            lines.append(f"  {ns}: {err}")
    return "\n".join(lines)


def _run_plugin_status(config: Path) -> None:
    """Load plugins for the config and print loaded/failed (shared by
    `plugin status` and the deprecated `plugins` alias)."""
    from led_ticker._plugin_loader import load_plugins_for_config  # noqa: PLC0415

    try:
        result = load_plugins_for_config(config)
    except (OSError, ValueError) as e:
        print(str(e), file=sys.stderr)
        sys.exit(2)
    print(_format_plugins(result))


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
            "(e.g. --list-fields message). "
            "Use --list-fields section for [[playlist.section]] fields."
        ),
    )
    val_parser.add_argument(
        "--strict",
        action="store_true",
        default=False,
        help=(
            "Treat all warnings as errors. "
            "Also checks that asset file paths (gif/image `path`) exist. "
            "Use in CI to enforce a warning-clean config."
        ),
    )
    val_parser.add_argument(
        "--fix",
        action="store_true",
        default=False,
        help=(
            "Apply auto-fixable migrations (key renames) to the config file in-place. "
            "NOTE: comments in the TOML file will not be preserved."
        ),
    )
    val_parser.add_argument(
        "--config",
        "-c",
        type=Path,
        default=argparse.SUPPRESS,
        help="Path to TOML config file (defaults to the top-level --config)",
    )

    # `plugins` subcommand — deprecated alias of `plugin status`
    plugins_parser = subparsers.add_parser(
        "plugins",
        help="(deprecated) alias of `plugin status`",
    )
    plugins_parser.add_argument(
        "--config",
        "-c",
        type=Path,
        default=argparse.SUPPRESS,
        help="Path to TOML config file (defaults to the top-level --config)",
    )

    # `plugin` subcommand — manage plugins (status/list/search/install)
    plugin_parser = subparsers.add_parser(
        "plugin",
        help="Manage plugins: status, list/search the catalog, install",
    )
    plugin_sub = plugin_parser.add_subparsers(dest="plugin_command")

    pstatus = plugin_sub.add_parser(
        "status", help="List loaded plugins (and any that failed) for the config"
    )
    pstatus.add_argument(
        "--config",
        "-c",
        type=Path,
        default=argparse.SUPPRESS,
        help="Path to TOML config file (defaults to the top-level --config)",
    )

    plugin_sub.add_parser("list", help="List available plugins from the catalog")

    psearch = plugin_sub.add_parser("search", help="Search the plugin catalog")
    psearch.add_argument("query", help="Substring to match (name/summary/provides)")

    pinstall = plugin_sub.add_parser(
        "install", help="Install a plugin by catalog name or pip spec"
    )
    pinstall.add_argument(
        "target", help="Catalog name (e.g. pool) or a pip spec (git+https://…, name==x)"
    )
    pinstall.add_argument(
        "--source",
        choices=["git", "pypi"],
        default=None,
        help="Which catalog source to use (default: the entry's first source)",
    )
    pinstall.add_argument(
        "--unpinned",
        action="store_true",
        help="Write @main / a bare PyPI name instead of the catalog's pinned ref",
    )
    pinstall.add_argument(
        "--save-only",
        action="store_true",
        dest="save_only",
        help="Only update requirements-plugins.txt; skip pip install (Docker flow)",
    )
    pinstall.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run",
        help="Print the plan without changing anything",
    )
    pinstall.add_argument(
        "--config",
        "-c",
        type=Path,
        default=argparse.SUPPRESS,
        help="Path to TOML config file (defaults to the top-level --config)",
    )

    # `webui` subcommand — the unprivileged status sidecar
    webui_parser = subparsers.add_parser(
        "webui",
        help="Run the web status UI sidecar (requires a [web] block in the config)",
    )
    webui_parser.add_argument(
        "--config",
        "-c",
        type=Path,
        default=argparse.SUPPRESS,
        help="Path to TOML config file (defaults to the top-level --config)",
    )

    args = parser.parse_args()

    if args.command == "plugins":
        # Deprecated alias of `plugin status`.
        print(
            "note: 'led-ticker plugins' is deprecated; use 'led-ticker plugin status'.",
            file=sys.stderr,
        )
        _run_plugin_status(args.config)
        sys.exit(0)

    if args.command == "plugin":
        pc = getattr(args, "plugin_command", None)
        if pc is None or pc == "status":
            _run_plugin_status(args.config)
            sys.exit(0)

        from led_ticker.app import plugin_cmd  # noqa: PLC0415

        if pc == "list":
            sys.exit(plugin_cmd.cmd_list())
        if pc == "search":
            sys.exit(plugin_cmd.cmd_search(args.query))
        if pc == "install":
            # Whether the user gave a config (vs the bare default config.toml).
            # When they didn't, cmd_install defaults the requirements file to the
            # canonical config/requirements-plugins.txt instead of the cwd.
            config_explicit = args.config != Path("config.toml")
            sys.exit(
                plugin_cmd.cmd_install(
                    args.target,
                    config_path=args.config,
                    config_explicit=config_explicit,
                    source=args.source,
                    pinned=not args.unpinned,
                    save_only=args.save_only,
                    dry_run=args.dry_run,
                )
            )

    if args.command == "webui":
        from led_ticker.config import read_web_config  # noqa: PLC0415
        from led_ticker.webui import run_webui  # noqa: PLC0415

        try:
            web_cfg = read_web_config(args.config)
        except (OSError, ValueError) as e:
            print(str(e), file=sys.stderr)
            sys.exit(2)
        if web_cfg is None:
            print(
                f"No [web] block in {args.config} — add one to enable the "
                "status sidecar (see config.example.toml).",
                file=sys.stderr,
            )
            sys.exit(2)
        asyncio.run(run_webui(args.config, web_cfg))
        sys.exit(0)

    if args.command == "validate":
        if args.list_fields is not None:
            from led_ticker.app.factories import _list_section_fields  # noqa: PLC0415

            if args.list_fields == "section":
                print(_list_section_fields())
                sys.exit(0)
            # Load plugins so a plugin widget type (e.g. acme.clock) is listable.
            from led_ticker._plugin_loader import (
                load_plugins_for_config,  # noqa: PLC0415
            )

            try:
                load_plugins_for_config(args.config)
            except (OSError, ValueError) as e:
                print(str(e), file=sys.stderr)
                sys.exit(2)
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
            result = asyncio.run(validate_config(args.path, strict=args.strict))
        except (OSError, ValueError) as e:
            print(str(e), file=sys.stderr)
            sys.exit(2)

        if args.fix:
            from led_ticker.validate import apply_migrations  # noqa: PLC0415

            n = apply_migrations(args.path, result)
            if n > 0:
                print(
                    f"Applied {n} migration(s). "
                    "Re-run validate to check for remaining issues.",
                    file=sys.stderr,
                )
                print(
                    "NOTE: TOML comments were not preserved.",
                    file=sys.stderr,
                )
            else:
                print("No auto-fixable migrations found.", file=sys.stderr)
            sys.exit(0)

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
