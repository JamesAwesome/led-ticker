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
from led_ticker.ticker import Ticker
from led_ticker.widgets import get_widget_class
from led_ticker.widgets.message import TickerMessage


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

    if hasattr(cls, "start"):
        return await cls.start(session=session, **widget_cfg)
    else:
        return cls(**widget_cfg)


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

    async with aiohttp.ClientSession() as session:
        notif_queue = asyncio.Queue()

        while True:
            for section in config.sections:
                widgets = []
                for widget_cfg in section.widgets:
                    cfg = dict(widget_cfg)  # copy to avoid mutating config
                    widget = await _build_widget(cfg, session)
                    widgets.append(widget)

                title = await _build_title(section.title)
                run_method = RUN_MODES.get(section.mode, "run_forever_scroll")

                ticker = Ticker(
                    monitors=widgets,
                    frame=led_frame,
                    title=title,
                    title_delay=config.title_delay,
                    notif_queue=notif_queue,
                )

                await getattr(ticker, run_method)(loop_count=section.loop_count)


def main():
    """CLI entry point."""
    _setup_logging()

    parser = argparse.ArgumentParser(description="LED Ticker Display")
    parser.add_argument(
        "--config", "-c",
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
