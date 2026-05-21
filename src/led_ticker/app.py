"""CLI entry point for led-ticker."""

from __future__ import annotations

import argparse
import asyncio
import itertools
import logging
import sys
from pathlib import Path
from typing import Any

import aiohttp

from led_ticker.colors import (
    BLUE,
    CYAN,
    GREEN,
    ORANGE,
    PINK,
    PURPLE,
    RED,
    RGB_WHITE,
    YELLOW,
)
from led_ticker.config import SectionConfig, TransitionConfig, load_config
from led_ticker.frame import LedFrame
from led_ticker.ticker import Ticker, _maybe_wrap
from led_ticker.transitions import get_transition_class, run_transition
from led_ticker.widgets import get_widget_class
from led_ticker.widgets._image_base import (
    VALID_SCROLL_DIRECTIONS,
    VALID_TEXT_ALIGNS,
    VALID_TEXT_VALIGNS,
)
from led_ticker.widgets._image_fit import VALID_FITS, VALID_IMAGE_ALIGNS
from led_ticker.widgets.message import TickerMessage
from led_ticker.widgets.mlb import MLBScoreMonitor
from led_ticker.widgets.mlb_standings import MLBStandingsMonitor
from led_ticker.widgets.rss_feed import RSSFeedMonitor

# Section-title random color cycle. One stable color per section visit.
# Lives here (not in `colors.py`) because this is the only consumer; a
# module-level `itertools.cycle` is mutable singleton state and belongs
# next to the code whose lifecycle owns it.
#
# Note: the 8 palette imports above are intentionally eager — `app.py`
# can't run without the graphics library anyway, so deferring color
# materialization here buys nothing. Don't "lazify" this with
# `lazy_palette` — the eagerness is the right tradeoff for the entry
# point.
RANDOM_COLOR: itertools.cycle = itertools.cycle(
    [RED, GREEN, BLUE, YELLOW, ORANGE, PURPLE, CYAN, PINK]
)


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
    "text_separator_color",
    "bottom_text_separator_color",
}

# Keys that remain raw graphics.Color objects (background fills, title
# color, segment color for MLB/weather). Kept as Color so widget code
# that does `.red` / `SetPixel(x, y, c.red, c.green, c.blue)` keeps
# working unchanged while provider integration rolls out.
_RAW_COLOR_KEYS: set[str] = _COLOR_KEYS - _PROVIDER_COLOR_KEYS


def _coerce_color_provider(value: Any, context: str = "font_color") -> Any:
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

    The ``context`` parameter is included in error messages so callers
    for fields other than ``font_color`` (e.g. ``top_color``,
    ``bottom_color``) produce accurate diagnostics.
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

    # `[r, g, b]` list/tuple → validate then wrap as constant
    if isinstance(value, list | tuple) and len(value) == 3:
        return _ConstantColor(graphics.Color(*_validate_rgb(value, f"{context} list")))

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


def _validate_rgb(rgb: Any, context: str) -> tuple[int, int, int]:
    """Validate an RGB triple at config-load time.

    - Reject bool components (bool is int subclass; `[True, False, True]`
      would silently coerce to (1, 0, 1)).
    - Reject out-of-range values; SetPixel takes 0..255 bytes.
    """
    if not (isinstance(rgb, list | tuple) and len(rgb) == 3):
        raise ValueError(f"{context} must be [r,g,b]; got {rgb!r}")
    if not all(isinstance(c, int) and not isinstance(c, bool) for c in rgb):
        raise ValueError(f"{context} components must be ints; got {list(rgb)!r}")
    if not all(0 <= c <= 255 for c in rgb):
        raise ValueError(f"{context} RGB values must be 0-255; got {list(rgb)!r}")
    return tuple(rgb)


def _rgb_to_hue(rgb: list[int] | tuple[int, ...], context: str) -> float:
    """Convert an [r,g,b] triple to a hue in degrees [0, 360).

    Raises ValueError when the color is nearly achromatic (saturation
    < 0.1) — the hue of a gray/white/black is undefined and using it
    as a `color_cycle` range endpoint produces meaningless output.
    """
    import colorsys as _cs

    r, g, b = (c / 255.0 for c in rgb)
    h, s, _ = _cs.rgb_to_hsv(r, g, b)
    if s < 0.1:
        raise ValueError(
            f"{context}: color {list(rgb)!r} is nearly achromatic "
            f"(saturation={s:.2f}); hue is undefined. "
            "Use a saturated color (e.g. [255,0,0] for red) so the "
            "hue arc is meaningful."
        )
    return h * 360.0


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

    # Maps style → TOML-facing key names (what the user writes in their config).
    # Used in error messages so we show "from"/"to" instead of internal names
    # like "from_color"/"from_hue" that the user never types.
    _user_allowed: dict[str, set[str]] = {
        "random": set(),
        "rainbow": {"speed", "char_offset"},
        "color_cycle": {"speed", "from", "to"},
        "gradient": {"from", "to"},
    }

    if style not in registry:
        raise ValueError(
            f"unknown font_color style {style!r}; available: {sorted(registry.keys())}"
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
        kwargs["from_color"] = graphics.Color(
            *_validate_rgb(from_val, "font_color gradient 'from'")
        )
        kwargs["to_color"] = graphics.Color(
            *_validate_rgb(to_val, "font_color gradient 'to'")
        )

    if style == "color_cycle":
        from_val = kwargs.pop("from", None)
        to_val = kwargs.pop("to", None)
        if (from_val is None) != (to_val is None):
            raise ValueError(
                "font_color style 'color_cycle' requires both 'from' and 'to' "
                "when specifying a hue range, or neither for the full wheel: "
                "font_color = {style='color_cycle', from=[r,g,b], to=[r,g,b]}"
            )
        speed = kwargs.get("speed", 5)
        if speed == 0:
            raise ValueError(
                "font_color style 'color_cycle' with speed=0 is a static color — "
                "use font_color = [r, g, b] instead"
            )
        if from_val is not None:
            from_val = list(_validate_rgb(from_val, "font_color color_cycle 'from'"))
            to_val = list(_validate_rgb(to_val, "font_color color_cycle 'to'"))
            from_hue = _rgb_to_hue(from_val, "font_color 'color_cycle' from")
            to_hue = _rgb_to_hue(to_val, "font_color 'color_cycle' to")
            diff = (to_hue - from_hue) % 360
            if diff > 180:
                diff -= 360
            if diff == 0:
                raise ValueError(
                    f"font_color 'color_cycle' from and to have the same hue "
                    f"({from_hue:.0f}°); use a plain color instead: "
                    "font_color = [r, g, b]"
                )
            kwargs["from_hue"] = from_hue
            kwargs["to_hue"] = to_hue
            allowed_kwargs = {"speed", "from_hue", "to_hue"}

    unknown = set(kwargs.keys()) - allowed_kwargs
    if unknown:
        raise ValueError(
            f"font_color style {style!r} got unknown keys {sorted(unknown)!r}; "
            f"allowed: {sorted(_user_allowed[style])}"
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
    - `{style = "rainbow", from = [r,g,b], to = [r,g,b], ...}`
      → `RainbowChaseBorder` restricted to the shorter hue arc.
    - `{style = "constant", color = [r, g, b], thickness = N}`
      → `ConstantBorder` with the color + thickness.
    - `[r, g, b]` (list/tuple) → `ConstantBorder` shorthand.
    - already a BorderEffect (has `paint`) → passes through.
    - None → None (no border).

    Raises ValueError on unknown styles, missing required kwargs, or
    unknown kwargs.
    """
    from led_ticker.borders import ColorCycleBorder, ConstantBorder, RainbowChaseBorder

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
        return ConstantBorder(color=_validate_rgb(value, "border shorthand color"))
    # String shorthand
    if isinstance(value, str):
        if value == "rainbow":
            return RainbowChaseBorder()
        if value == "color_cycle":
            return ColorCycleBorder()
        raise ValueError(
            f"unknown border style {value!r}; "
            "available: 'rainbow', 'color_cycle', or use an inline table"
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
            allowed = {"speed", "char_offset", "thickness", "from", "to"}
            unknown = set(kwargs.keys()) - allowed
            if unknown:
                raise ValueError(
                    f"border style 'rainbow' got unknown keys "
                    f"{sorted(unknown)!r}; allowed: {sorted(allowed)}"
                )
            from_val = kwargs.pop("from", None)
            to_val = kwargs.pop("to", None)
            if (from_val is None) != (to_val is None):
                raise ValueError(
                    "border style 'rainbow' requires both 'from' and 'to' "
                    "when specifying a hue range, or neither for the full wheel"
                )
            if from_val is not None:
                from_hue = _rgb_to_hue(from_val, "border 'rainbow' from")
                to_hue = _rgb_to_hue(to_val, "border 'rainbow' to")
                diff = (to_hue - from_hue) % 360
                if diff > 180:
                    diff -= 360
                if diff == 0:
                    raise ValueError(
                        f"border 'rainbow' from and to have the same hue "
                        f"({from_hue:.0f}°); use border = [r, g, b] instead"
                    )
                kwargs["from_hue"] = from_hue
                kwargs["to_hue"] = to_hue
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
                color=_validate_rgb(color, "border constant color"), **kwargs
            )
        if style == "color_cycle":
            allowed = {"speed", "thickness", "from", "to"}
            unknown = set(kwargs.keys()) - allowed
            if unknown:
                raise ValueError(
                    f"border style 'color_cycle' got unknown keys "
                    f"{sorted(unknown)!r}; allowed: {sorted(allowed)}"
                )
            speed = kwargs.get("speed", 5)
            if speed == 0:
                raise ValueError(
                    "border style 'color_cycle' with speed=0 is a static color — "
                    "use border = [r, g, b] instead"
                )
            from_val = kwargs.pop("from", None)
            to_val = kwargs.pop("to", None)
            if (from_val is None) != (to_val is None):
                raise ValueError(
                    "border style 'color_cycle' requires both 'from' and 'to' "
                    "when specifying a hue range, or neither for the full wheel"
                )
            if from_val is not None:
                from_hue = _rgb_to_hue(from_val, "border 'color_cycle' from")
                to_hue = _rgb_to_hue(to_val, "border 'color_cycle' to")
                diff = (to_hue - from_hue) % 360
                if diff > 180:
                    diff -= 360
                if diff == 0:
                    raise ValueError(
                        f"border 'color_cycle' from and to have the same hue "
                        f"({from_hue:.0f}°); use border = [r, g, b] instead"
                    )
                kwargs["from_hue"] = from_hue
                kwargs["to_hue"] = to_hue
            return ColorCycleBorder(**kwargs)
        raise ValueError(
            f"unknown border style {style!r}; "
            "available: 'rainbow', 'constant', 'color_cycle'"
        )
    # Reject anything else loudly
    raise ValueError(
        f"border must be a string, table, or [r,g,b] list; got {type(value).__name__}"
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
                f"unknown animation {value!r}; available: {sorted(registry.keys())}"
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
                f"unknown animation {style!r}; available: {sorted(registry.keys())}"
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
            cfg[key] = _coerce_color_provider(cfg[key], context=key)

    for key in _RAW_COLOR_KEYS:
        if key in cfg and isinstance(cfg[key], list | tuple) and len(cfg[key]) == 3:
            cfg[key] = graphics.Color(*_validate_rgb(cfg[key], key))


def _is_hires_font_name(name: str) -> bool:
    """True if `name` resolves to a HiresFont (TTF/OTF), False if BDF
    alias. Verified `list_available_hires_fonts` exists in
    `fonts/__init__.py` and is the canonical way to enumerate hires
    font names."""
    from led_ticker.fonts import list_available_hires_fonts

    return name in list_available_hires_fonts()


# Numeric fields that flow through widget_cfg before reaching the
# widget constructor. The pop()-side fields (font_size, font_threshold,
# top_font_size, etc.) also pass through here so their type is fixed
# before resolve_font sees them.
_WIDGET_INT_FIELDS = frozenset(
    {
        "font_size",
        "font_threshold",
        "top_font_size",
        "bottom_font_size",
        "top_font_threshold",
        "bottom_font_threshold",
        "top_row_height",
        "text_loops",
        "bottom_text_loops",
        "gif_loops",
        "padding",
        "scroll_speed_ms",
        "text_x_offset",
        "text_y_offset",
        "top_text_y_offset",
        "bottom_text_y_offset",
    }
)

_WIDGET_FLOAT_FIELDS = frozenset(
    {
        "hold_seconds",
    }
)


# text_align includes "auto": image widgets use it as a pre-resolution sentinel
# (maps to a side opposite the image at draw time); VALID_TEXT_ALIGNS covers
# post-resolution values only, so the coerce-side set augments it here.
_WIDGET_ENUM_FIELDS: dict[str, frozenset[str]] = {
    "text_align": VALID_TEXT_ALIGNS | {"auto"},
    "text_valign": VALID_TEXT_VALIGNS,
    "image_align": VALID_IMAGE_ALIGNS,
    "scroll_direction": VALID_SCROLL_DIRECTIONS,
    "fit": VALID_FITS,
    "bottom_text_scroll": frozenset({"marquee", "scroll_through"}),
}


def _coerce_widget_cfg(
    widget_cfg: dict[str, Any],
    collector: list[Any] | None,
) -> None:
    """In-place coerce of widget_cfg numeric fields. Bool stays a hard
    error so the existing bottom_text_loops / font_threshold guards
    continue to fire."""
    from led_ticker._coerce import coerce_choice, coerce_float, coerce_int

    for name in list(widget_cfg.keys()):
        if name in _WIDGET_INT_FIELDS:
            value, warning = coerce_int(widget_cfg[name], field=f"widget.{name}")
            widget_cfg[name] = value
            if warning is not None and collector is not None:
                collector.append(warning)
        elif name in _WIDGET_FLOAT_FIELDS:
            value, warning = coerce_float(widget_cfg[name], field=f"widget.{name}")
            widget_cfg[name] = value
            if warning is not None and collector is not None:
                collector.append(warning)
        elif name in _WIDGET_ENUM_FIELDS:
            value, warning = coerce_choice(
                widget_cfg[name],
                field=f"widget.{name}",
                valid=_WIDGET_ENUM_FIELDS[name],
            )
            widget_cfg[name] = value
            if warning is not None and collector is not None:
                collector.append(warning)


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
    validate_only: bool = False,
    coercion_collector: list[Any] | None = None,
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
    from led_ticker.validate import MigrationError

    # Migration check: text_scale was the BDF block-expansion knob.
    # Replaced by font_size (real pixels) which works uniformly for
    # BDF and HiresFont. Loud failure here catches stale TOMLs at
    # load time rather than letting them silently render wrong.
    if "text_scale" in widget_cfg:
        raise MigrationError(
            "text_scale removed in favor of font_size (real pixels). "
            "Migrate: font_size = N × cell_h_of_your_font. "
            "For BDF 6×12: font_size = N × 12 (e.g. text_scale=2 → "
            "font_size=24, text_scale=4 → font_size=48). "
            "For BDF 5×8: font_size = N × 8.",
            suggested_fix=(
                "Replace text_scale with font_size = N × cell_h"
                " (e.g. font_size=24 for 6×12 BDF at 2×)"
            ),
        )

    # Migration check: presentation = "..." was the wrapper-based effect
    # knob. Replaced by font_color (color effects) + animation
    # (typewriter/bounce on TickerMessage). Loud failure here catches
    # stale TOMLs at load time.
    if "presentation" in widget_cfg:
        raise MigrationError(
            "presentation removed in favor of font_color (color effects) + "
            "animation (typewriter on TickerMessage). Migration:\n"
            "  presentation = 'typewriter'  → animation = 'typewriter' "
            "(type='message' only)\n"
            "  presentation = 'rainbow'     → font_color = 'rainbow'\n"
            "  presentation = 'color_cycle' → font_color = 'color_cycle'\n"
            "  presentation = 'pulse' / 'bounce' — these effects were "
            "removed in the rework. Use font_color = [r,g,b] / 'rainbow' / "
            "'color_cycle' / 'gradient' and/or animation = 'typewriter' "
            "instead.",
            suggested_fix="Use font_color / animation instead of presentation",
        )

    widget_type = widget_cfg.pop("type")
    cls = get_widget_class(widget_type)

    _coerce_widget_cfg(widget_cfg, coercion_collector)

    # Animation field. Currently allowed on `message`, `gif`, and
    # `image` — image widgets restrict to single-row mode (validated
    # in `_BaseImageWidget._validate_common`). Pop before construction
    # so it doesn't reach the widget constructor as an unknown kwarg
    # for widget types that don't accept it.
    animation_value = widget_cfg.pop("animation", None)
    if animation_value is not None and widget_type not in (
        "message",
        "gif",
        "image",
    ):
        raise ValueError(
            f'animation is only valid on type="message", "gif", or '
            f'"image"; got type={widget_type!r}. For color effects on '
            f"other widgets, use font_color = 'rainbow' (or similar)."
        )
    if animation_value is not None:
        widget_cfg["animation"] = _coerce_animation(animation_value)

    # Coerce `border` to a `BorderEffect` instance at config-load.
    # Restricted to widget types whose draw paths can host a perimeter
    # (message, countdown, two_row, gif, image) — data widgets like
    # weather/mlb have their own paint logic and a perimeter border
    # isn't a meaningful concept there. Loud failure here catches
    # misplaced `border = ...` in TOML before it surfaces as a
    # confusing "unknown kwarg" downstream.
    border_value = widget_cfg.pop("border", None)
    if border_value is not None and widget_type not in (
        "message",
        "countdown",
        "two_row",
        "gif",
        "image",
    ):
        raise ValueError(
            f'border is only valid on type="message", "countdown", '
            f'"two_row", "gif", or "image"; got type={widget_type!r}.'
        )
    if border_value is not None:
        widget_cfg["border"] = _coerce_border(border_value)

    # text_wrap / text_separator / text_separator_color — single-row
    # image widgets only (gif, image). bottom_text_wrap / bottom_text_separator
    # / bottom_text_separator_color — image (two-row) AND two_row widgets.
    # On widget types not supporting these, drop falsy defaults silently
    # and raise on truthy values (matches the animation / border guard
    # pattern above).
    SINGLE_ROW_WRAP_KEYS = (
        "text_wrap",
        "text_separator",
        "text_separator_color",
    )
    BOTTOM_ROW_WRAP_KEYS = (
        "bottom_text_wrap",
        "bottom_text_separator",
        "bottom_text_separator_color",
    )

    if widget_type not in ("gif", "image"):
        for wrap_key in SINGLE_ROW_WRAP_KEYS:
            val = widget_cfg.pop(wrap_key, None)
            if val not in (None, False):
                raise ValueError(
                    f'{wrap_key} is only valid on type="gif" or "image"; '
                    f"got type={widget_type!r}."
                )

    if widget_type not in ("gif", "image", "two_row"):
        for wrap_key in BOTTOM_ROW_WRAP_KEYS:
            val = widget_cfg.pop(wrap_key, None)
            if val not in (None, False):
                raise ValueError(
                    f'{wrap_key} is only valid on type="gif", "image", '
                    f'or "two_row"; got type={widget_type!r}.'
                )

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

    if validate_only:
        return None

    if hasattr(cls, "start"):
        widget = await cls.start(session=session, **widget_cfg)
    else:
        widget = cls(**widget_cfg)

    return widget


async def _build_title(
    title_cfg: dict[str, Any] | None,
    *,
    session: aiohttp.ClientSession,
    config_dir: Path | None = None,
    default_bg_color: tuple[int, int, int] | None = None,
    panel_h_for_warning: int | None = None,
) -> TickerMessage | None:
    """Build a title TickerMessage from config.

    A section title is a regular `type="message"` widget — it supports
    every knob `_build_widget` does (`font`, `font_size`, `animation`,
    `border`, `bg_color`, etc.). Routing through `_build_widget` keeps
    titles in lockstep with the message widget surface; an explicit
    allowlist here would drift the moment a new knob lands.

    `color` is the title-only spelling for the foreground text color
    (every example config uses it). It is translated to `font_color`
    here so the rest of the pipeline handles it uniformly. The legacy
    `color = "random"` sentinel still picks from the RANDOM_COLOR
    palette cycle (one stable color per section visit) rather than the
    `color_providers.Random` RNG — preserved because existing configs
    rely on this palette.

    `session` is required for consistency with `_build_widget` even
    though title widgets (type="message") have no `.start` classmethod
    and never touch it; callers always have one in scope.
    """
    if title_cfg is None:
        return None

    cfg = dict(title_cfg)
    cfg["type"] = "message"
    cfg.setdefault("text", "")

    color = cfg.pop("color", None)
    if color is not None and "font_color" not in cfg:
        if color == "random":
            cfg["font_color"] = next(RANDOM_COLOR)
        else:
            cfg["font_color"] = color

    return await _build_widget(
        cfg,
        session=session,
        config_dir=config_dir,
        default_bg_color=default_bg_color,
        panel_h_for_warning=panel_h_for_warning,
    )


def _resolve_title_delay(section_start_hold: float | None, global_delay: int) -> float:
    """Section-level start_hold wins over the playlist-wide [title] delay.

    None means 'inherit'; any explicit value (including 0.0) overrides.
    """
    if section_start_hold is not None:
        return section_start_hold
    return float(global_delay)


def _resolve_buffer_msg(section: SectionConfig) -> TickerMessage | None:
    """Build a per-section forever_scroll separator widget.

    Returns None when all four separator_* fields are unset — Ticker
    falls back to DEFAULT_BUFFER_MSG (a _CircleBufferMsg that adapts
    to canvas type at draw time).

    Routing:
    - All four unset → None (inherit default circle).
    - Color-only override → _CircleBufferMsg with the user's color
      (still adapts to canvas type — circle on bigsign, BDF '•' on
      smallsign — just with a different fill).
    - Any of separator / separator_font / separator_font_size set
      → TickerMessage with literal text/font rendering (today's
      behavior, unchanged).
    """
    text_or_font_set = (
        section.separator is not None
        or section.separator_font is not None
        or section.separator_font_size is not None
    )
    color_set = section.separator_color is not None

    if not text_or_font_set and not color_set:
        return None

    color_provider = _coerce_color_provider(
        section.separator_color if color_set else RGB_WHITE
    )

    if not text_or_font_set:
        # Color-only: still want the hi-res circle on bigsign.
        from led_ticker.ticker import _CircleBufferMsg

        return _CircleBufferMsg(message=" • ", center=False, font_color=color_provider)

    # Explicit text / font: TickerMessage with literal rendering.
    text = section.separator if section.separator is not None else "•"
    if text == "":
        text = "  "

    kwargs: dict[str, Any] = {
        "message": text,
        "center": False,
        "font_color": color_provider,
    }
    if section.separator_font is not None:
        from led_ticker.fonts import resolve_font

        kwargs["font"] = resolve_font(
            section.separator_font, section.separator_font_size
        )
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
    val_parser.add_argument("path", type=Path, help="Path to TOML config file")
    val_parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Emit JSON output",
    )

    args = parser.parse_args()

    if args.command == "validate":
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
