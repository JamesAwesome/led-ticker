"""CLI entry point for led-ticker."""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

import aiohttp

from led_ticker.colors import RANDOM_COLOR
from led_ticker.config import load_config
from led_ticker.frame import LedFrame
from led_ticker.presentation import (
    WidgetPresenter,
    get_presentation_class,
)
from led_ticker.ticker import Ticker
from led_ticker.transition import get_transition_class, run_transition
from led_ticker.widgets import get_widget_class
from led_ticker.widgets.message import TickerMessage
from led_ticker.widgets.rss_feed import RSSFeedMonitor


def _setup_logging():
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)


async def _build_widget(widget_cfg, session):
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


async def _build_title(title_cfg):
    """Build a title TickerMessage from config."""
    if title_cfg is None:
        return None
    text = title_cfg.get("text", "")
    color = title_cfg.get("color")
    font_color = next(RANDOM_COLOR) if color == "random" else None
    kwargs = {"message": text}
    if font_color:
        kwargs["font_color"] = font_color
    return TickerMessage(**kwargs)


RUN_MODES = {
    "forever_scroll": "run_forever_scroll",
    "infini_scroll": "run_infini_scroll",
    "swap": "run_swap",
}


async def run(config_path: Path):
    """Main application loop."""
    config = load_config(config_path)

    led_frame = LedFrame(
        led_rows=config.display.rows,
        led_cols=config.display.cols,
        led_chain=config.display.chain,
        led_slowdown_gpio=config.display.slowdown_gpio,
        led_brightness=config.display.brightness,
        led_gpio_mapping=config.display.gpio_mapping,
    )

    # Build section-to-section transition if configured
    section_trans = None
    if config.between_sections.type != "cut":
        section_trans_cls = get_transition_class(
            config.between_sections.type,
        )
        trans_kwargs = {}
        if config.between_sections.color is not None:
            trans_kwargs["color"] = config.between_sections.color
        section_trans = section_trans_cls(**trans_kwargs)

    async with aiohttp.ClientSession() as session:
        notif_queue = asyncio.Queue()
        last_widget = None  # track for section-to-section transitions

        while True:
            for section in config.sections:
                widgets = []
                for widget_cfg in section.widgets:
                    cfg = dict(widget_cfg)  # copy to avoid mutating config
                    widget = await _build_widget(cfg, session)
                    # RSSFeedMonitor is a container, expand its stories
                    if isinstance(widget, RSSFeedMonitor):
                        widgets.extend(widget.feed_stories)
                    else:
                        widgets.append(widget)

                title = await _build_title(section.title)
                run_method = RUN_MODES.get(
                    section.mode,
                    "run_forever_scroll",
                )

                # Run section-to-section transition
                first_widget = title if title else (widgets[0] if widgets else None)
                if (
                    last_widget is not None
                    and first_widget is not None
                    and section_trans is not None
                ):
                    canvas = led_frame.get_clean_canvas()
                    canvas = await run_transition(
                        canvas,
                        led_frame,
                        last_widget,
                        first_widget,
                        transition=section_trans,
                        duration=config.between_sections.duration,
                        easing=config.between_sections.easing,
                    )

                # Build within-section transition config
                trans_cfg = section.transition
                if trans_cfg.type != "cut":
                    trans_cls = get_transition_class(trans_cfg.type)
                    trans_kwargs = {}
                    if trans_cfg.color is not None:
                        trans_kwargs["color"] = trans_cfg.color
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
                )

                await getattr(ticker, run_method)(
                    loop_count=section.loop_count,
                )

                # Track the last widget for next section transition
                if widgets:
                    last_widget = widgets[-1]
                elif title:
                    last_widget = title


def main():
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
