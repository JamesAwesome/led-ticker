"""CLI entry point for led-ticker."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path
from typing import Any

import aiohttp

from led_ticker.app.coercion import (  # noqa: F401
    _COLOR_KEYS,
    _PROVIDER_COLOR_KEYS,
    _RAW_COLOR_KEYS,
    _WIDGET_ENUM_FIELDS,
    _WIDGET_FLOAT_FIELDS,
    _WIDGET_INT_FIELDS,
    _coerce_animation,
    _coerce_border,
    _coerce_color,
    _coerce_color_provider,
    _coerce_widget_cfg,
    _coerce_widget_colors,
    _is_hires_font_name,
    _provider_from_style,
    _validate_rgb,
)
from led_ticker.app.factories import (  # noqa: F401
    RANDOM_COLOR,
    RUN_MODES,
    _build_title,
    _build_trans_obj,
    _build_widget,
    _cache_key,
    _configure_user_font_dir,
    _list_widget_fields,
    _resolve_buffer_msg,
    _resolve_title_delay,
    build_frame_from_config,
)
from led_ticker.config import load_config
from led_ticker.ticker import Ticker, _maybe_wrap
from led_ticker.transitions import run_transition
from led_ticker.widgets.mlb import MLBScoreMonitor
from led_ticker.widgets.mlb_standings import MLBStandingsMonitor
from led_ticker.widgets.rss_feed import RSSFeedMonitor


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


async def run(config_path: Path) -> None:
    """Main application loop."""
    config = load_config(config_path)
    # Surface any coerce warnings recorded by load_config (string-of-digits
    # int/float fields, mixed-case enum strings). Same messages that
    # `led-ticker validate` shows as rule-37 warnings; logging at startup
    # lets users who skip pre-flight still see the fixes.
    for w in config._coerce_warnings:
        logging.warning("config coerce: %s", w.message)
    _configure_user_font_dir(config_path)

    led_frame = build_frame_from_config(config.display)

    # Default inter-section transition built once at startup. Used for
    # sections that don't specify their own `transition` field — see
    # the per-section override logic below.
    default_section_trans: Any = _build_trans_obj(config.between_sections)

    # Compute the panel height to use for hi-res font_size warnings.
    # Only meaningful on the small sign (default_scale == 1) — bigsign
    # users intentionally pick large sizes, no warning needed there.
    panel_h_for_warning: int | None = (
        config.display.rows if config.display.default_scale == 1 else None
    )

    async with aiohttp.ClientSession() as session:
        notif_queue: asyncio.Queue[Any] = asyncio.Queue()
        last_widget: Any = None  # track for section-to-section transitions
        last_scroll_pos: int = 0  # track scroll pos for between-section transitions
        last_scale: int = config.display.default_scale  # outgoing section's scale
        last_content_height: int = 16  # outgoing section's content_height
        last_bg_color: tuple[int, int, int] | None = (
            None  # outgoing section's bg_color (for run_transition's t<0.5 reset)
        )
        widget_cache: dict[str, Any] = {}

        while True:
            for section in config.sections:
                widgets: list[Any] = []
                runtime_coerce: list[Any] = []
                for widget_cfg in section.widgets:
                    # Cache async widgets to avoid leaking background tasks
                    key = _cache_key(widget_cfg)
                    if key in widget_cache:
                        widget = widget_cache[key]
                    else:
                        cfg = dict(widget_cfg)
                        widget = await _build_widget(
                            cfg,
                            session,
                            config_dir=config_path.parent,
                            default_bg_color=section.bg_color,
                            panel_h_for_warning=panel_h_for_warning,
                            coercion_collector=runtime_coerce,
                        )
                        widget_cache[key] = widget
                    # Container widgets expand into stories
                    if isinstance(
                        widget,
                        RSSFeedMonitor | MLBScoreMonitor | MLBStandingsMonitor,
                    ):
                        logging.debug(
                            "Expanding %s: %d stories",
                            type(widget).__name__,
                            len(widget.feed_stories),
                        )
                        widgets.extend(widget.feed_stories)
                    else:
                        widgets.append(widget)
                # Drain coerce warnings collected during this section's
                # widget build. Empty in the common case; one log line per
                # CoercionWarning otherwise.
                for w in runtime_coerce:
                    logging.warning("config coerce: %s", w.message)

                title = await _build_title(
                    section.title,
                    session=session,
                    config_dir=config_path.parent,
                    default_bg_color=section.bg_color,
                    panel_h_for_warning=panel_h_for_warning,
                )
                run_method = RUN_MODES.get(
                    section.mode,
                    "run_forever_scroll",
                )

                # Entry transition precedence:
                #   1. entry_transition (explicit per-section entry override)
                #   2. transition (when transition_specified)
                #   3. between_sections (global default)
                if section.entry_transition is not None:
                    entry_trans = _build_trans_obj(section.entry_transition)
                    entry_duration = section.entry_transition.duration
                    entry_easing = section.entry_transition.easing
                elif section.transition_specified:
                    entry_trans = _build_trans_obj(section.transition)
                    entry_duration = section.transition.duration
                    entry_easing = section.transition.easing
                else:
                    entry_trans = default_section_trans
                    entry_duration = config.between_sections.duration
                    entry_easing = config.between_sections.easing

                # Run section-to-section transition.
                # Wrap at the OUTGOING section's scale so the outgoing widget
                # keeps its on-screen size during the dissolve. Any visual jolt
                # from the scale change happens at the very end of the
                # transition (one frame), where the new section's first render
                # immediately overwrites it.
                first_widget = title if title else (widgets[0] if widgets else None)
                just_transitioned = (
                    last_widget is not None
                    and first_widget is not None
                    and entry_trans is not None
                )
                if just_transitioned:
                    canvas = _maybe_wrap(
                        led_frame.get_clean_canvas(),
                        last_scale,
                        last_content_height,
                    )
                    canvas = await run_transition(
                        canvas,
                        led_frame,
                        last_widget,
                        first_widget,
                        transition=entry_trans,
                        duration=entry_duration,
                        easing=entry_easing,
                        outgoing_scroll_pos=last_scroll_pos,
                        # Smoothly cross between scales: outgoing fades out
                        # at last_scale; at t >= 0.5 the wrapper switches
                        # to section.scale so incoming dissolves IN at its
                        # native size (no wrong-scale flash, no snap-in
                        # after the dissolve completes). Content height
                        # must also match the new section so widgets like
                        # two_row don't shift vertically when the section
                        # actually starts running.
                        incoming_scale=section.scale,
                        incoming_content_height=section.content_height,
                        # Preserve bg color through the transition.
                        # `outgoing_bg_color` keeps the previous
                        # section's bg painted at t<0.5 so it doesn't
                        # vanish to black the instant the transition
                        # starts; `incoming_bg_color` ramps in the
                        # new bg at t>=0.5 (and the hires snap respects
                        # it too) so the last transition frame matches
                        # the section's first reset_canvas. Both
                        # default to None — the legacy behavior was
                        # `Clear()` for the entire transition.
                        outgoing_bg_color=last_bg_color,
                        incoming_bg_color=section.bg_color,
                    )

                # Widget transition precedence:
                #   1. widget_transition (explicit per-section widget override)
                #   2. transition (when transition_specified)
                #   3. None (cut)
                widget_trans_cfg = section.widget_transition or (
                    section.transition if section.transition_specified else None
                )
                if widget_trans_cfg is not None and widget_trans_cfg.type != "cut":
                    widget_trans_cfg.transition_obj = _build_trans_obj(widget_trans_cfg)
                    transition_config = widget_trans_cfg
                else:
                    transition_config = None

                ticker_kwargs: dict[str, Any] = {
                    "monitors": widgets,
                    "frame": led_frame,
                    "title": title,
                    "title_delay": _resolve_title_delay(
                        section.start_hold, config.title_delay
                    ),
                    "notif_queue": notif_queue,
                    "transition_config": transition_config,
                    "hold_time": section.hold_time,
                    "continuous_scroll": section.continuous_scroll,
                    "scale": section.scale,
                    "content_height": section.content_height,
                }
                if section.scroll_step_ms is not None:
                    ticker_kwargs["scroll_speed"] = section.scroll_step_ms / 1000
                buffer_msg = _resolve_buffer_msg(section)
                if buffer_msg is not None:
                    ticker_kwargs["buffer_msg"] = buffer_msg
                ticker = Ticker(**ticker_kwargs)

                # If a between-section transition just ran, the title is
                # already on-screen at t=1.0 of the dissolve. Tell the section
                # to start at pos=0 (no scroll-in) so we don't blank the panel
                # before redrawing.
                run_kwargs: dict[str, Any] = {"loop_count": section.loop_count}
                # `start_pos` is only meaningful for scrolling modes —
                # `run_swap` and `run_gif` don't have a scroll position
                # to skip past.
                if just_transitioned and run_method in (
                    "run_forever_scroll",
                    "run_infini_scroll",
                ):
                    run_kwargs["start_pos"] = 0

                await getattr(ticker, run_method)(**run_kwargs)

                # Brief pause before between-sections transition
                if section.continuous_scroll:
                    await asyncio.sleep(1.0)

                # Track the last widget and scroll pos for next section transition
                last_scroll_pos = ticker.last_scroll_pos
                last_scale = section.scale
                last_content_height = section.content_height
                last_bg_color = section.bg_color
                if widgets:
                    last_widget = widgets[-1]
                elif title:
                    last_widget = title


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
