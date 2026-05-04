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


_COLOR_KEYS: set[str] = {
    "font_color",
    "color",
    "top_color",
    "bottom_color",
    "bg_color",
    "top_bg_color",
    "bottom_bg_color",
}


def _coerce_color(value: Any) -> Any:
    """Convert an `[r, g, b]` TOML list to a `graphics.Color` object.

    Lets configs say `font_color = [255, 150, 190]` instead of forcing
    callers to construct a Color object themselves. Strings ("random")
    and existing Color objects pass through unchanged.
    """
    if isinstance(value, list | tuple) and len(value) == 3:
        from led_ticker._compat import require_graphics

        return require_graphics().Color(*value)
    return value


def _coerce_widget_colors(cfg: dict[str, Any]) -> None:
    """In-place convert known color keys from RGB lists to graphics.Color."""
    for key in _COLOR_KEYS:
        if key in cfg:
            cfg[key] = _coerce_color(cfg[key])


async def _build_widget(
    widget_cfg: dict[str, Any],
    session: aiohttp.ClientSession,
    config_dir: Path | None = None,
    default_bg_color: tuple[int, int, int] | None = None,
    panel_h_for_warning: int | None = None,
) -> Any:
    """Instantiate a widget from its config dict.

    `config_dir` is the directory containing the config.toml; used to
    resolve relative `path` values for widgets that reference asset
    files (currently just `type = "gif"`).

    `default_bg_color` is the section-level bg as an `(r, g, b)` tuple
    (or None). It's injected into `widget_cfg["bg_color"]` only when
    the widget config doesn't already specify it — preserving the
    "widget overrides section" precedence rule.

    `panel_h_for_warning` is the real panel height in pixels (or None
    to skip the check). When set and a hi-res `font_size` exceeds
    `panel_h_for_warning - 2`, log a warning — this catches small-sign
    users who set a font size that won't fit vertically. Bigsign hi-res
    is the supported use case, so callers pass None for it.
    """
    widget_type = widget_cfg.pop("type")
    cls = get_widget_class(widget_type)

    # Inject section default before color coercion runs. Skip when the
    # widget already specified bg_color (widget-level wins).
    if default_bg_color is not None and "bg_color" not in widget_cfg:
        widget_cfg["bg_color"] = list(default_bg_color)

    # Resolve `font` + `font_size` (+ optional `font_threshold`) into a
    # font object before passing to the widget. Hi-res fonts come from
    # config/fonts/ or the bundled hires/ dir; BDF aliases (6x12, 5x8,
    # etc.) fall back to the C bitmap fonts. Raises UnknownFontError on
    # bogus names. `font_threshold` (0-255, default 128) is only
    # meaningful for hi-res; lower it (~80) for thin-stroked fonts.
    font_name = widget_cfg.pop("font", None)
    font_size = widget_cfg.pop("font_size", None)
    font_threshold = widget_cfg.pop("font_threshold", None)
    if font_name is not None:
        from led_ticker.fonts import DEFAULT_HIRES_SIZE, resolve_font
        from led_ticker.fonts.hires_loader import HiresFont

        size = font_size if font_size is not None else DEFAULT_HIRES_SIZE
        font = resolve_font(font_name, size, threshold=font_threshold)
        widget_cfg["font"] = font

        # Warn on small-sign vertical overflow. Hi-res renders at native
        # physical pixels, so font_size is compared directly to panel
        # height. -2 leaves a 1px margin top + bottom (descenders, etc).
        # BDF fonts are sized by their FONTBOUNDINGBOX (e.g. 6x12 = 12)
        # and pre-validated to fit, so only warn for HiresFont here.
        if (
            isinstance(font, HiresFont)
            and panel_h_for_warning is not None
            and size > panel_h_for_warning - 2
        ):
            logging.warning(
                "font_size=%d exceeds panel height %dpx (-2 margin) for "
                "font %r — text will clip vertically. Hi-res fonts are "
                "intended for the bigsign (64px); on the small sign, "
                "stick to BDF aliases (5x8, 6x12) or font_size <= %d.",
                size,
                panel_h_for_warning,
                font_name,
                panel_h_for_warning - 2,
            )

    # Config uses "text" but TickerMessage/TickerCountdown use "message".
    # Only rename for widgets that don't accept `text` natively (e.g.
    # GifPlayer takes `text` directly for its alongside-text feature).
    cls_fields = {a.name for a in getattr(cls, "__attrs_attrs__", ())}
    if "text" in widget_cfg and "text" not in cls_fields:
        if "message" not in widget_cfg:
            widget_cfg["message"] = widget_cfg.pop("text")
        else:
            widget_cfg.pop("text")

    # File-backed widgets get config-relative paths resolved here so
    # the widgets themselves don't need to know about config layout.
    if (
        widget_type in ("gif", "image")
        and "path" in widget_cfg
        and config_dir is not None
    ):
        candidate = Path(widget_cfg["path"])
        if not candidate.is_absolute():
            widget_cfg["path"] = str((config_dir / candidate).resolve())

    # Convert any [r, g, b] lists in known color keys to graphics.Color.
    _coerce_widget_colors(widget_cfg)

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
    if color == "random":
        font_color = next(RANDOM_COLOR)
    else:
        coerced = _coerce_color(color)
        font_color = coerced if coerced is not None else None
    kwargs: dict[str, Any] = {"message": text}
    if font_color is not None:
        kwargs["font_color"] = font_color
    return TickerMessage(**kwargs)


RUN_MODES: dict[str, str] = {
    "forever_scroll": "run_forever_scroll",
    "infini_scroll": "run_infini_scroll",
    "swap": "run_swap",
    "gif": "run_gif",
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
    if display.show_refresh:
        # The rgbmatrix C library prints the live refresh rate to
        # stderr using `\b` backspaces so it overwrites in place.
        # That's by design (a status line, not a log line) but it
        # interleaves with our log output and looks like a glitch.
        # No Python API exposes the value, so we can't fold it into
        # the log stream cleanly. Note where to look so users don't
        # think it's broken.
        logging.info(
            "show_refresh=true: live Hz updates print to stderr in place "
            "(separate from this log stream — that's the C library, "
            "not a glitch). Disable in config to silence."
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


def _configure_user_font_dir(config_path: Path) -> None:
    """Anchor user-supplied hi-res fonts to ``<config_dir>/fonts/``.

    The module-level default in ``hires_loader`` resolves relative to
    the package install path, which is fine in the dev tree but points
    at the wrong place under ``pip install`` / Docker (the package
    lives in site-packages, not next to the user's config). Override
    here at startup based on where ``config.toml`` actually lives, and
    invalidate the load cache so any earlier lookups don't stick.

    SCOPE: Only effective for callers that go through ``app.run()``.
    Custom entry points or test harnesses that build widgets directly
    (without running the app loop) need to call this manually before
    invoking ``_build_widget`` with a ``font`` keyword, otherwise the
    package-relative default applies and user-supplied fonts in a
    Docker install won't be found.
    """
    from led_ticker.fonts import hires_loader

    hires_loader.USER_FONT_DIR = (config_path.parent / "fonts").resolve()
    hires_loader.load_hires_font.cache_clear()


async def run(config_path: Path) -> None:
    """Main application loop."""
    config = load_config(config_path)
    _configure_user_font_dir(config_path)

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
        if not config.between_sections.show_pokeball:
            trans_kwargs["show_pokeball"] = False
        section_trans = section_trans_cls(**trans_kwargs)

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
                        widget = await _build_widget(
                            cfg,
                            session,
                            config_dir=config_path.parent,
                            default_bg_color=section.bg_color,
                            panel_h_for_warning=panel_h_for_warning,
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
                        transition=section_trans,
                        duration=config.between_sections.duration,
                        easing=config.between_sections.easing,
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
                    if not trans_cfg.show_pokeball:
                        trans_kwargs["show_pokeball"] = False
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
                    content_height=section.content_height,
                )

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
