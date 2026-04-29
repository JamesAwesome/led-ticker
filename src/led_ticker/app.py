"""CLI entry point for led-ticker."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path
from typing import Any

import aiohttp

from led_ticker.colors import RANDOM_COLOR
from led_ticker.config import load_config
from led_ticker.frame import LedFrame
from led_ticker.presentation import (
    WidgetPresenter,
    get_presentation_class,
)
from led_ticker.ticker import Ticker, _maybe_wrap
from led_ticker.transitions import get_transition_class, run_transition
from led_ticker.widgets import get_widget_class
from led_ticker.widgets.message import TickerMessage
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


def _cache_key(widget_cfg: dict[str, Any]) -> str:
    """Generate a stable cache key from widget config."""
    return str(sorted(widget_cfg.items()))


async def _build_widget(
    widget_cfg: dict[str, Any], session: aiohttp.ClientSession
) -> Any:
    """Instantiate a widget from its config dict."""
    widget_type = widget_cfg.pop("type")
    cls = get_widget_class(widget_type)

    # Config uses "text" but TickerMessage/TickerCountdown use "message"
    if "text" in widget_cfg:
        if "message" not in widget_cfg:
            widget_cfg["message"] = widget_cfg.pop("text")
        else:
            widget_cfg.pop("text")

    # Extract presentation config before passing to widget
    presentation_name = widget_cfg.pop("presentation", None)
    widget_cfg.pop("presentation_speed", None)

    if hasattr(cls, "start"):
        widget = await cls.start(session=session, **widget_cfg)
    else:
        widget = cls(**widget_cfg)

    # Wrap with presentation mode if configured
    if presentation_name:
        pres_cls = get_presentation_class(presentation_name)
        widget = WidgetPresenter(widget, pres_cls())

    return widget


async def _build_title(title_cfg: dict[str, Any] | None) -> TickerMessage | None:
    """Build a title TickerMessage from config."""
    if title_cfg is None:
        return None
    text = title_cfg.get("text", "")
    color = title_cfg.get("color")
    font_color = next(RANDOM_COLOR) if color == "random" else None
    kwargs: dict[str, Any] = {"message": text}
    if font_color:
        kwargs["font_color"] = font_color
    return TickerMessage(**kwargs)


RUN_MODES: dict[str, str] = {
    "forever_scroll": "run_forever_scroll",
    "infini_scroll": "run_infini_scroll",
    "swap": "run_swap",
}


def build_frame_from_config(display) -> LedFrame:
    """Build an LedFrame from a DisplayConfig."""
    logging.info(
        "Display: %dx%d rows × %dx%d cols (chain=%d parallel=%d) "
        "mapper=%r brightness=%d slowdown_gpio=%d pwm_bits=%d "
        "pwm_lsb_ns=%d rp1_rio=%d show_refresh=%s",
        display.rows,
        display.parallel,
        display.cols,
        display.chain,
        display.chain,
        display.parallel,
        display.pixel_mapper or "(none)",
        display.brightness,
        display.slowdown_gpio,
        display.pwm_bits,
        display.pwm_lsb_nanoseconds,
        display.rp1_rio,
        display.show_refresh,
    )
    return LedFrame(
        led_rows=display.rows,
        led_cols=display.cols,
        led_chain=display.chain,
        led_parallel=display.parallel,
        led_pixel_mapper=display.pixel_mapper,
        led_slowdown_gpio=display.slowdown_gpio,
        led_brightness=display.brightness,
        led_gpio_mapping=display.gpio_mapping,
        led_pwm_bits=display.pwm_bits,
        led_pwm_lsb_nanoseconds=display.pwm_lsb_nanoseconds,
        led_show_refresh=display.show_refresh,
        led_no_hardware_pulse=display.no_hardware_pulse,
        led_rp1_rio=display.rp1_rio,
    )


async def run(config_path: Path) -> None:
    """Main application loop."""
    config = load_config(config_path)

    led_frame = build_frame_from_config(config.display)

    # Build section-to-section transition if configured
    section_trans: Any = None
    if config.between_sections.type != "cut":
        section_trans_cls = get_transition_class(
            config.between_sections.type,
        )
        trans_kwargs: dict[str, Any] = {}
        if config.between_sections.colors is not None:
            trans_kwargs["colors"] = config.between_sections.colors
        elif config.between_sections.color is not None:
            trans_kwargs["color"] = config.between_sections.color
        if not config.between_sections.show_pikachu:
            trans_kwargs["show_pikachu"] = False
        section_trans = section_trans_cls(**trans_kwargs)

    async with aiohttp.ClientSession() as session:
        notif_queue: asyncio.Queue[Any] = asyncio.Queue()
        last_widget: Any = None  # track for section-to-section transitions
        last_scroll_pos: int = 0  # track scroll pos for between-section transitions
        last_scale: int = config.display.default_scale  # outgoing section's scale
        widget_cache: dict[str, Any] = {}

        while True:
            for section in config.sections:
                widgets: list[Any] = []
                for widget_cfg in section.widgets:
                    # Cache async widgets to avoid leaking background tasks
                    key = _cache_key(widget_cfg)
                    if key in widget_cache:
                        widget = widget_cache[key]
                    else:
                        cfg = dict(widget_cfg)
                        widget = await _build_widget(cfg, session)
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

                title = await _build_title(section.title)
                run_method = RUN_MODES.get(
                    section.mode,
                    "run_forever_scroll",
                )

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
                    and section_trans is not None
                )
                if just_transitioned:
                    canvas = _maybe_wrap(led_frame.get_clean_canvas(), last_scale)
                    canvas = await run_transition(
                        canvas,
                        led_frame,
                        last_widget,
                        first_widget,
                        transition=section_trans,
                        duration=config.between_sections.duration,
                        easing=config.between_sections.easing,
                        outgoing_scroll_pos=last_scroll_pos,
                        # Smoothly cross between scales: outgoing fades out
                        # at last_scale; at t >= 0.5 the wrapper switches
                        # to section.scale so incoming dissolves IN at its
                        # native size (no wrong-scale flash, no snap-in
                        # after the dissolve completes).
                        incoming_scale=section.scale,
                    )

                # Build within-section transition config
                trans_cfg = section.transition
                if trans_cfg.type != "cut":
                    trans_cls = get_transition_class(trans_cfg.type)
                    trans_kwargs: dict[str, Any] = {}
                    if trans_cfg.colors is not None:
                        trans_kwargs["colors"] = trans_cfg.colors
                    elif trans_cfg.color is not None:
                        trans_kwargs["color"] = trans_cfg.color
                    if not trans_cfg.show_pikachu:
                        trans_kwargs["show_pikachu"] = False
                    trans_cfg.transition_obj = trans_cls(**trans_kwargs)
                    transition_config = trans_cfg
                else:
                    transition_config = None

                ticker = Ticker(
                    monitors=widgets,
                    frame=led_frame,
                    title=title,
                    title_delay=config.title_delay,
                    notif_queue=notif_queue,
                    transition_config=transition_config,
                    hold_time=section.hold_time,
                    continuous_scroll=section.continuous_scroll,
                    scale=section.scale,
                )

                # If a between-section transition just ran, the title is
                # already on-screen at t=1.0 of the dissolve. Tell the section
                # to start at pos=0 (no scroll-in) so we don't blank the panel
                # before redrawing.
                run_kwargs: dict[str, Any] = {"loop_count": section.loop_count}
                if just_transitioned and run_method != "run_swap":
                    run_kwargs["start_pos"] = 0

                await getattr(ticker, run_method)(**run_kwargs)

                # Brief pause before between-sections transition
                if section.continuous_scroll:
                    await asyncio.sleep(1.0)

                # Track the last widget and scroll pos for next section transition
                last_scroll_pos = ticker.last_scroll_pos
                last_scale = section.scale
                if widgets:
                    last_widget = widgets[-1]
                elif title:
                    last_widget = title


def main() -> None:
    """CLI entry point."""
    _setup_logging()

    parser = argparse.ArgumentParser(description="LED Ticker Display")
    parser.add_argument(
        "--config",
        "-c",
        type=Path,
        default=Path("config.toml"),
        help="Path to TOML configuration file (default: config.toml)",
    )
    args = parser.parse_args()

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
