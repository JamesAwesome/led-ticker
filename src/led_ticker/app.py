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
from led_ticker.config import TransitionConfig, load_config
from led_ticker.frame import LedFrame
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

# Keys that are text/foreground colors and should be coerced to
# ColorProvider instances. Background color keys remain raw
# graphics.Color (they drive SetPixel fills, not per-frame text draws).
_PROVIDER_COLOR_KEYS: set[str] = {
    "font_color",
    "top_color",
    "bottom_color",
    "font_color_temp",
}

# Keys that remain raw graphics.Color objects (background fills, title
# color, segment color for MLB/weather). Kept as Color so widget code
# that does `.red` / `SetPixel(x, y, c.red, c.green, c.blue)` keeps
# working unchanged while provider integration rolls out.
_RAW_COLOR_KEYS: set[str] = _COLOR_KEYS - _PROVIDER_COLOR_KEYS


def _coerce_color_provider(value: Any) -> Any:
    """Convert a TOML color spec to a ColorProvider instance.

    Accepts:
    - `[r, g, b]` / `(r, g, b)` → `_ConstantColor(graphics.Color(...))`
    - `"random"` → `Random()`
    - `"rainbow"` / `"color_cycle"` → corresponding provider with defaults
    - `{style = "...", ...kwargs}` → named provider with kwargs
    - already a Color (graphics.Color) → wrap in `_ConstantColor`
    - already a ColorProvider → returned as-is
    - None → None (caller decides default)

    Raises ValueError on unknown strings, unknown styles, missing
    required kwargs, or unknown kwargs.
    """
    from led_ticker.color_providers import _ConstantColor

    if value is None:
        return None

    # Already a provider — pass through
    if hasattr(value, "color_for") and hasattr(value, "per_char"):
        return value

    # Already a graphics.Color — wrap
    from led_ticker._compat import require_graphics

    graphics = require_graphics()
    if isinstance(value, graphics.Color):
        return _ConstantColor(value)

    # `[r, g, b]` list/tuple → wrap as constant
    if isinstance(value, list | tuple) and len(value) == 3:
        return _ConstantColor(graphics.Color(*value))

    # String shorthand
    if isinstance(value, str):
        return _provider_from_style(value, {})

    # Inline table
    if isinstance(value, dict):
        if "style" not in value:
            raise ValueError(
                f"font_color table requires 'style' key; got {list(value.keys())!r}"
            )
        style = value["style"]
        kwargs = {k: v for k, v in value.items() if k != "style"}
        return _provider_from_style(style, kwargs)

    raise ValueError(
        f"font_color must be [r,g,b], 'random'/'rainbow'/'color_cycle', "
        f"or {{style='...'}}; got {value!r}"
    )


def _provider_from_style(style: str, kwargs: dict[str, Any]) -> Any:
    """Instantiate a provider by name with kwargs. Validates kwargs
    against each provider's __init__ signature; raises with a helpful
    message on unknown styles or missing/unknown kwargs."""
    from led_ticker.color_providers import (
        ColorCycle,
        Gradient,
        Rainbow,
        Random,
    )

    registry = {
        "random": (Random, set()),
        "rainbow": (Rainbow, {"speed", "char_offset"}),
        "color_cycle": (ColorCycle, {"speed"}),
        "gradient": (Gradient, {"from_color", "to_color"}),
    }

    if style not in registry:
        raise ValueError(
            f"unknown font_color style {style!r}; available: "
            f"{sorted(registry.keys())}"
        )

    cls, allowed_kwargs = registry[style]

    # Special-case translation: TOML uses `from` / `to` (Pythonic
    # reserved words avoided), but provider takes from_color/to_color.
    # Coerce values to graphics.Color while we're at it.
    from led_ticker._compat import require_graphics

    graphics = require_graphics()
    if style == "gradient":
        from_val = kwargs.pop("from", None) or kwargs.pop("from_color", None)
        to_val = kwargs.pop("to", None) or kwargs.pop("to_color", None)
        if from_val is None or to_val is None:
            raise ValueError(
                "font_color style 'gradient' requires 'from' and 'to': "
                "font_color = {style='gradient', from=[r,g,b], to=[r,g,b]}"
            )
        kwargs["from_color"] = graphics.Color(*from_val)
        kwargs["to_color"] = graphics.Color(*to_val)

    unknown = set(kwargs.keys()) - allowed_kwargs
    if unknown:
        raise ValueError(
            f"font_color style {style!r} got unknown keys {sorted(unknown)!r}; "
            f"allowed: {sorted(allowed_kwargs)}"
        )
    return cls(**kwargs)


def _coerce_color(value: Any) -> Any:
    """Backwards-compat shim: defers to _coerce_color_provider for
    new uses. Kept so any out-of-tree caller doesn't immediately break.
    """
    return _coerce_color_provider(value)


def _coerce_border(value: Any) -> Any:
    """Convert a TOML border spec to a `BorderEffect` instance.

    Accepts:
    - `"rainbow"` (string shorthand) → `RainbowChaseBorder()` with defaults
    - `{style = "rainbow", speed = N, char_offset = N, thickness = N}`
      → `RainbowChaseBorder` with kwargs.
    - `{style = "constant", color = [r, g, b], thickness = N}`
      → `ConstantBorder` with the color + thickness.
    - `[r, g, b]` (list/tuple) → `ConstantBorder` shorthand.
    - already a BorderEffect (has `paint`) → passes through.
    - None → None (no border).

    Raises ValueError on unknown styles, missing required kwargs, or
    unknown kwargs.
    """
    from led_ticker.borders import ConstantBorder, RainbowChaseBorder

    def _validate_rgb(rgb: Any, context: str) -> tuple[int, int, int]:
        """Validate an RGB triple for a border `constant` color.

        - Reject bool components (bool is an int subclass; without
          this guard `[True, False, True]` would silently coerce to
          (1, 0, 1)). Same hardening pattern documented for
          `font_threshold` in CLAUDE.md.
        - Reject out-of-range values; SetPixel takes 0..255 bytes.
          Letting `[300, -50, 999]` through produces undefined
          rgbmatrix behavior and silently broken renders.
        """
        if not (isinstance(rgb, list | tuple) and len(rgb) == 3):
            raise ValueError(f"border {context} must be [r,g,b]; got {rgb!r}")
        if not all(isinstance(c, int) and not isinstance(c, bool) for c in rgb):
            raise ValueError(
                f"border {context} components must be ints; got {list(rgb)!r}"
            )
        if not all(0 <= c <= 255 for c in rgb):
            raise ValueError(
                f"border {context} RGB values must be 0-255; got {list(rgb)!r}"
            )
        return tuple(rgb)

    if value is None:
        return None
    # Already a BorderEffect — duck-typed via the `paint` method
    if hasattr(value, "paint") and hasattr(value, "frame_invariant"):
        return value
    # Constant-color shorthand: [r, g, b]. Validate via _validate_rgb
    # so the same shape works whether passed as a top-level list or
    # via the inline-table form below. Bool is rejected (subclass of
    # int) and out-of-range values are rejected (SetPixel needs 0-255).
    if isinstance(value, list | tuple) and len(value) == 3:
        return ConstantBorder(color=_validate_rgb(value, "shorthand color"))
    # String shorthand
    if isinstance(value, str):
        if value == "rainbow":
            return RainbowChaseBorder()
        raise ValueError(
            f"unknown border style {value!r}; "
            "available: 'rainbow', or use an inline table"
        )
    # Inline table
    if isinstance(value, dict):
        if "style" not in value:
            raise ValueError(
                f"border table requires 'style' key; got {list(value.keys())!r}"
            )
        style = value["style"]
        kwargs = {k: v for k, v in value.items() if k != "style"}
        if style == "rainbow":
            allowed = {"speed", "char_offset", "thickness"}
            unknown = set(kwargs.keys()) - allowed
            if unknown:
                raise ValueError(
                    f"border style 'rainbow' got unknown keys "
                    f"{sorted(unknown)!r}; allowed: {sorted(allowed)}"
                )
            return RainbowChaseBorder(**kwargs)
        if style == "constant":
            allowed = {"color", "thickness"}
            unknown = set(kwargs.keys()) - allowed
            if unknown:
                raise ValueError(
                    f"border style 'constant' got unknown keys "
                    f"{sorted(unknown)!r}; allowed: {sorted(allowed)}"
                )
            if "color" not in kwargs:
                raise ValueError(
                    "border style 'constant' requires 'color' kwarg: "
                    "border = {style='constant', color=[r,g,b]}"
                )
            color = kwargs.pop("color")
            return ConstantBorder(
                color=_validate_rgb(color, "'constant' color"), **kwargs
            )
        raise ValueError(
            f"unknown border style {style!r}; available: 'rainbow', 'constant'"
        )
    # Reject anything else loudly
    raise ValueError(
        f"border must be a string, table, or [r,g,b] list; "
        f"got {type(value).__name__}"
    )


def _coerce_animation(value: Any) -> Any:
    """Convert a TOML animation spec to an Animation instance.

    Accepts:
    - `"typewriter"` (string) → instance with defaults
    - `{style = "...", ...}` (dict) → instance with kwargs
    - already an Animation → returned as-is

    Raises ValueError on unknown names or unknown kwargs.
    """
    from led_ticker.animations import Typewriter

    if hasattr(value, "frame_for"):
        return value

    registry = {
        "typewriter": (Typewriter, {"chars_per_frame", "frames_per_char"}),
    }

    if isinstance(value, str):
        if value not in registry:
            raise ValueError(
                f"unknown animation {value!r}; available: " f"{sorted(registry.keys())}"
            )
        cls, _allowed = registry[value]
        return cls()

    if isinstance(value, dict):
        if "style" not in value:
            raise ValueError(
                f"animation table requires 'style' key; got {list(value.keys())!r}"
            )
        style = value["style"]
        if style not in registry:
            raise ValueError(
                f"unknown animation {style!r}; available: " f"{sorted(registry.keys())}"
            )
        cls, allowed = registry[style]
        kwargs = {k: v for k, v in value.items() if k != "style"}
        unknown = set(kwargs.keys()) - allowed
        if unknown:
            raise ValueError(
                f"animation {style!r} got unknown keys {sorted(unknown)!r}; "
                f"allowed: {sorted(allowed)}"
            )
        return cls(**kwargs)

    raise ValueError(f"animation must be a string or table; got {type(value).__name__}")


def _coerce_widget_colors(cfg: dict[str, Any]) -> None:
    """In-place convert color keys to ColorProvider instances or raw Colors.

    - `_PROVIDER_COLOR_KEYS` (font_color, top_color, bottom_color,
      font_color_temp): coerced to ColorProvider instances. Constant
      [r,g,b] lists get wrapped in _ConstantColor so all downstream
      widget code is uniform — widgets
      call `provider.color_for(...)` regardless of source shape.
    - `_RAW_COLOR_KEYS` (bg_color, color, …): coerced to raw graphics.Color.
      These are used for SetPixel fills / background rectangles, not
      per-frame text draws.
    """
    from led_ticker._compat import require_graphics

    graphics = require_graphics()

    for key in _PROVIDER_COLOR_KEYS:
        if key in cfg:
            cfg[key] = _coerce_color_provider(cfg[key])

    for key in _RAW_COLOR_KEYS:
        if key in cfg and isinstance(cfg[key], list | tuple) and len(cfg[key]) == 3:
            cfg[key] = graphics.Color(*cfg[key])


def _is_hires_font_name(name: str) -> bool:
    """True if `name` resolves to a HiresFont (TTF/OTF), False if BDF
    alias. Verified `list_available_hires_fonts` exists in
    `fonts/__init__.py` and is the canonical way to enumerate hires
    font names."""
    from led_ticker.fonts import list_available_hires_fonts

    return name in list_available_hires_fonts()


def _build_trans_obj(trans_cfg: TransitionConfig) -> Any:
    """Construct a transition instance from a `TransitionConfig`.

    Returns None when `trans_cfg.type == "cut"` (treated as
    "no transition"). Used for both the global `between_sections`
    fallback AND per-section overrides — when a section explicitly
    specifies its own `transition`, the engine builds an instance
    here and uses it for both inter-section ENTRY and inter-widget
    transitions.
    """
    if trans_cfg.type == "cut":
        return None
    cls = get_transition_class(trans_cfg.type)
    kwargs: dict[str, Any] = {}
    if trans_cfg.colors is not None:
        kwargs["colors"] = trans_cfg.colors
    elif trans_cfg.color is not None:
        kwargs["color"] = trans_cfg.color
    if not trans_cfg.show_pikachu:
        kwargs["show_pikachu"] = False
    if not trans_cfg.show_pokeball:
        kwargs["show_pokeball"] = False
    return cls(**kwargs)


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
    # Migration check: text_scale was the BDF block-expansion knob.
    # Replaced by font_size (real pixels) which works uniformly for
    # BDF and HiresFont. Loud failure here catches stale TOMLs at
    # load time rather than letting them silently render wrong.
    if "text_scale" in widget_cfg:
        raise ValueError(
            "text_scale removed in favor of font_size (real pixels). "
            "Migrate: font_size = N × cell_h_of_your_font. "
            "For BDF 6×12: font_size = N × 12 (e.g. text_scale=2 → "
            "font_size=24, text_scale=4 → font_size=48). "
            "For BDF 5×8: font_size = N × 8."
        )

    # Migration check: presentation = "..." was the wrapper-based effect
    # knob. Replaced by font_color (color effects) + animation
    # (typewriter/bounce on TickerMessage). Loud failure here catches
    # stale TOMLs at load time.
    if "presentation" in widget_cfg:
        raise ValueError(
            "presentation removed in favor of font_color (color effects) + "
            "animation (typewriter on TickerMessage). Migration:\n"
            "  presentation = 'typewriter'  → animation = 'typewriter' "
            "(type='message' only)\n"
            "  presentation = 'rainbow'     → font_color = 'rainbow'\n"
            "  presentation = 'color_cycle' → font_color = 'color_cycle'\n"
            "  presentation = 'pulse' / 'bounce' — these effects were "
            "removed in the rework. Use font_color = [r,g,b] / 'rainbow' / "
            "'color_cycle' / 'gradient' and/or animation = 'typewriter' "
            "instead."
        )

    widget_type = widget_cfg.pop("type")
    cls = get_widget_class(widget_type)

    # Animation field (TickerMessage-only). Pop before construction so
    # it doesn't reach the widget constructor as an unknown kwarg.
    animation_value = widget_cfg.pop("animation", None)
    if animation_value is not None and widget_type != "message":
        raise ValueError(
            f'animation is only valid on type="message"; got '
            f"type={widget_type!r}. For color effects on other widgets, "
            f"use font_color = 'rainbow' (or similar)."
        )
    if animation_value is not None:
        widget_cfg["animation"] = _coerce_animation(animation_value)

    # Coerce `border` (TickerMessage-only) to a BorderEffect instance
    # at config-load. Same TickerMessage-only rule as `animation` —
    # the field doesn't make sense on data widgets that have their
    # own draw paths and don't paint a perimeter. Loud failure here
    # catches misplaced `border = ...` in TOML before it surfaces as
    # a confusing "unknown kwarg" downstream.
    border_value = widget_cfg.pop("border", None)
    if border_value is not None and widget_type not in (
        "message",
        "countdown",
        "two_row",
    ):
        raise ValueError(
            f'border is only valid on type="message", "countdown", or '
            f'"two_row"; got type={widget_type!r}.'
        )
    if border_value is not None:
        widget_cfg["border"] = _coerce_border(border_value)

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
        from led_ticker.fonts import resolve_font
        from led_ticker.fonts.hires_loader import HiresFont

        # HiresFont requires explicit font_size at construction (the
        # rasterizer needs a real-px target). BDF fonts pass through
        # to widget which derives a smart default at first paint.
        if _is_hires_font_name(font_name) and font_size is None:
            raise ValueError(
                f"HiresFont {font_name!r} requires font_size (real "
                f"pixels). e.g. font_size = 24 for bigsign, "
                f"font_size = 12 for small sign."
            )
        font = resolve_font(font_name, font_size, threshold=font_threshold)
        widget_cfg["font"] = font

        # Warn on small-sign vertical overflow. Hi-res renders at native
        # physical pixels, so font_size is compared directly to panel
        # height. -2 leaves a 1px margin top + bottom (descenders, etc).
        # BDF fonts are sized by their FONTBOUNDINGBOX (e.g. 6x12 = 12)
        # and pre-validated to fit, so only warn for HiresFont here.
        if (
            isinstance(font, HiresFont)
            and panel_h_for_warning is not None
            and font_size is not None
            and font_size > panel_h_for_warning - 2
        ):
            logging.warning(
                "font_size=%d exceeds panel height %dpx (-2 margin) for "
                "font %r — text will clip vertically. Hi-res fonts are "
                "intended for the bigsign (64px); on the small sign, "
                "stick to BDF aliases (5x8, 6x12) or font_size <= %d.",
                font_size,
                panel_h_for_warning,
                font_name,
                panel_h_for_warning - 2,
            )

    # Per-row font overrides for TwoRowMessage. Same resolution as the
    # main `font` knob but keyed `top_font` / `bottom_font`. Each
    # accepts its own _size and _threshold. Resolved object replaces
    # the string name in widget_cfg so the widget constructor sees a
    # Font / HiresFont, not a string.
    for prefix in ("top_font", "bottom_font"):
        row_name = widget_cfg.pop(prefix, None)
        row_size = widget_cfg.pop(f"{prefix}_size", None)
        row_threshold = widget_cfg.pop(f"{prefix}_threshold", None)
        if row_name is not None:
            from led_ticker.fonts import resolve_font

            if _is_hires_font_name(row_name) and row_size is None:
                raise ValueError(
                    f"HiresFont {row_name!r} requires {prefix}_size "
                    f"(real pixels). e.g. {prefix}_size = 22 for "
                    f"bigsign two-row layouts."
                )
            widget_cfg[prefix] = resolve_font(
                row_name, row_size, threshold=row_threshold
            )

    # Config uses "text" but TickerMessage/TickerCountdown use "message".
    # Only rename for widgets that don't accept `text` natively (e.g.
    # GifPlayer takes `text` directly for its alongside-text feature).
    cls_fields = {a.name for a in getattr(cls, "__attrs_attrs__", ())}

    # Pass font_size through only to widgets that accept it (gif/still
    # subclass _BaseImageWidget which has font_size as an attrs field).
    # TickerMessage and similar widgets don't have font_size and would
    # raise TypeError if it's injected.
    if font_size is not None and "font_size" in cls_fields:
        widget_cfg["font_size"] = font_size

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

    # Convert color keys (font_color, top_color, bottom_color) to
    # ColorProvider instances. Constant [r,g,b] lists get wrapped in
    # _ConstantColor so all downstream widget code is uniform.
    _coerce_widget_colors(widget_cfg)

    if hasattr(cls, "start"):
        widget = await cls.start(session=session, **widget_cfg)
    else:
        widget = cls(**widget_cfg)

    return widget


async def _build_title(title_cfg: dict[str, Any] | None) -> TickerMessage | None:
    """Build a title TickerMessage from config.

    `color` accepts the same shapes as widget `font_color`: a constant
    `[r, g, b]`, the `"random"` sentinel (which also accepts a stable
    per-section choice via the legacy `RANDOM_COLOR` cycle), a string
    shorthand (`"rainbow"` / `"color_cycle"`), or an inline table
    (`{style = "rainbow", speed = 8}`). All shapes coerce to a
    ColorProvider so titles can use the same animated effects as their
    body widgets.
    """
    if title_cfg is None:
        return None
    text = title_cfg.get("text", "")
    color = title_cfg.get("color")
    if color == "random":
        # Preserve the legacy "random" semantic — picks from
        # RANDOM_COLOR cycle (one stable color per section). The
        # color_providers.Random class would also work here but uses a
        # different RNG; cycle keeps the established palette.
        font_color = next(RANDOM_COLOR)
    elif color is not None:
        # Any other shape (list, string shorthand, inline table) goes
        # through the unified provider coercion. _coerce_color_provider
        # already handles `[r,g,b]` → _ConstantColor, `"rainbow"` →
        # Rainbow(), table → keyword'd provider, etc.
        font_color = _coerce_color_provider(color)
    else:
        font_color = None
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

                # Pick the inter-section ENTRY transition. Precedence:
                #   1. If the section explicitly set `transition`,
                #      use that — same object as the inter-widget
                #      transition. Solves the "single-widget section
                #      with `transition = pokeball` never fires" UX
                #      bug: the configured value now controls how the
                #      section APPEARS (not just inter-widget moves).
                #   2. Else fall back to `between_sections` (the
                #      global default for sections that don't override).
                if section.transition_specified:
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
                        # Ramp to the incoming section's bg over the
                        # second half of the transition so the panel
                        # is already on the new bg when the section
                        # starts — no single-tick brightness step.
                        # No-op when section.bg_color is None.
                        incoming_bg_color=section.bg_color,
                    )

                # Build within-section transition config (used between
                # widgets within a multi-widget section). Mirrors the
                # entry transition selection above when the section
                # specifies one — same `_build_trans_obj` factory.
                trans_cfg = section.transition
                if trans_cfg.type != "cut":
                    trans_cfg.transition_obj = _build_trans_obj(trans_cfg)
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
