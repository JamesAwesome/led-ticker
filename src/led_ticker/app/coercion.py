"""TOML → led-ticker object coercion layer.

Converts raw config values (strings, lists, dicts) to led-ticker objects:
ColorProvider, BorderEffect, Animation, Font. No dependencies on the
widget/ticker engine — only on provider registries and the _coerce helpers.
"""

from __future__ import annotations

from typing import Any

from led_ticker.animations import Animation
from led_ticker.borders import BorderEffect
from led_ticker.color_providers import ColorProvider
from led_ticker.widgets._image_base import (
    VALID_SCROLL_DIRECTIONS,
    VALID_TEXT_ALIGNS,
    VALID_TEXT_VALIGNS,
)
from led_ticker.widgets._image_fit import VALID_FITS, VALID_IMAGE_ALIGNS

_COLOR_KEYS: set[str] = {
    "font_color",
    "color",
    "top_color",
    "bottom_color",
    "bg_color",
    "top_bg_color",
    "bottom_bg_color",
    "label_color",
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

_SHIMMER_COLOR_SHORTHANDS: dict[str, tuple[int, int, int]] = {
    "white": (255, 255, 255),
    "gold": (255, 200, 50),
    "blue": (100, 180, 255),
    "cyan": (0, 220, 220),
}


def _coerce_color_provider(
    value: Any, context: str = "font_color"
) -> ColorProvider | None:
    """Convert a TOML color spec to a ColorProvider instance.

    Accepts:
    - `[r, g, b]` / `(r, g, b)` → `_ConstantColor(graphics.Color(...))`
    - `"random"` → `Random()`
    - `"rainbow"` / `"color_cycle"` / `"shimmer"` → corresponding provider with defaults
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


def _provider_from_style(style: str, kwargs: dict[str, Any]) -> ColorProvider:
    """Instantiate a provider by name with kwargs. Validates kwargs
    against each provider's __init__ signature; raises with a helpful
    message on unknown styles or missing/unknown kwargs."""
    from led_ticker.color_providers import (
        ColorCycle,
        Gradient,
        Rainbow,
        Random,
        Shimmer,
    )

    registry = {
        "random": (Random, set()),
        "rainbow": (Rainbow, {"speed", "char_offset"}),
        "color_cycle": (ColorCycle, {"speed"}),
        "gradient": (Gradient, {"from_color", "to_color"}),
        "shimmer": (
            Shimmer,
            {"speed", "width", "pause", "base_color", "shimmer_color"},
        ),
    }

    # Maps style → TOML-facing key names (what the user writes in their config).
    # Used in error messages so we show "from"/"to" instead of internal names
    # like "from_color"/"from_hue" that the user never types.
    _user_allowed: dict[str, set[str]] = {
        "random": set(),
        "rainbow": {"speed", "char_offset"},
        "color_cycle": {"speed", "from", "to"},
        "gradient": {"from", "to"},
        "shimmer": {"base", "shimmer", "speed", "width", "pause"},
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

    if style == "shimmer":
        # base_color/shimmer_color are internal names injected below — reject them
        # if the user somehow typed them directly (they should use base= / shimmer=)
        for _internal in ("base_color", "shimmer_color"):
            if _internal in kwargs:
                raise ValueError(
                    f"font_color shimmer: use 'base' and 'shimmer' keys, not "
                    f"{_internal!r} (that is an internal name)"
                )
        base_val = kwargs.pop("base", None)
        shimmer_val = kwargs.pop("shimmer", None)

        if base_val is None:
            base_rgb: tuple[int, int, int] = (60, 60, 80)
        elif isinstance(base_val, str):
            if base_val not in _SHIMMER_COLOR_SHORTHANDS:
                raise ValueError(
                    f"font_color shimmer 'base' shorthand {base_val!r} unknown; "
                    f"available: {sorted(_SHIMMER_COLOR_SHORTHANDS)} or use [r, g, b]"
                )
            base_rgb = _SHIMMER_COLOR_SHORTHANDS[base_val]
        else:
            base_rgb = _validate_rgb(base_val, "font_color shimmer 'base'")

        if shimmer_val is None:
            shimmer_rgb: tuple[int, int, int] = (255, 255, 255)
        elif isinstance(shimmer_val, str):
            if shimmer_val not in _SHIMMER_COLOR_SHORTHANDS:
                raise ValueError(
                    f"font_color shimmer 'shimmer' shorthand {shimmer_val!r} unknown; "
                    f"available: {sorted(_SHIMMER_COLOR_SHORTHANDS)} or use [r, g, b]"
                )
            shimmer_rgb = _SHIMMER_COLOR_SHORTHANDS[shimmer_val]
        else:
            shimmer_rgb = _validate_rgb(shimmer_val, "font_color shimmer 'shimmer'")

        kwargs["base_color"] = graphics.Color(*base_rgb)
        kwargs["shimmer_color"] = graphics.Color(*shimmer_rgb)

    unknown = set(kwargs.keys()) - allowed_kwargs
    if unknown:
        raise ValueError(
            f"font_color style {style!r} got unknown keys {sorted(unknown)!r}; "
            f"allowed: {sorted(_user_allowed[style])}"
        )
    return cls(**kwargs)


def _coerce_color(value: Any) -> ColorProvider | None:
    """Backwards-compat shim: defers to _coerce_color_provider for
    new uses. Kept so any out-of-tree caller doesn't immediately break.
    """
    return _coerce_color_provider(value)


def _coerce_border(value: Any) -> BorderEffect | None:
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
    from led_ticker.borders import (
        ColorCycleBorder,
        ConstantBorder,
        LightbulbBorder,
        RainbowChaseBorder,
    )

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
        match value:
            case "rainbow":
                return RainbowChaseBorder()
            case "color_cycle":
                return ColorCycleBorder()
            case "lightbulbs":
                return LightbulbBorder()
            case _:
                raise ValueError(
                    f"unknown border style {value!r}; "
                    "available: 'rainbow', 'color_cycle', 'lightbulbs', "
                    "or use an inline table"
                )
    # Inline table
    if isinstance(value, dict):
        if "style" not in value:
            raise ValueError(
                f"border table requires 'style' key; got {list(value.keys())!r}"
            )
        style = value["style"]
        kwargs = {k: v for k, v in value.items() if k != "style"}
        match style:
            case "rainbow":
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
            case "constant":
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
            case "color_cycle":
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
            case "lightbulbs":
                allowed = {
                    "mode",
                    "bulb_size",
                    "gap",
                    "lit_color",
                    "unlit_color",
                    "speed_frames",
                    "chase_density",
                    "direction",
                }
                unknown = set(kwargs.keys()) - allowed
                if unknown:
                    raise ValueError(
                        f"border style 'lightbulbs' got unknown keys "
                        f"{sorted(unknown)!r}; allowed: {sorted(allowed)}"
                    )
                # Coerce RGB-list color fields to tuples; _validate_rgb
                # rejects out-of-range / wrong-shape values.
                if "lit_color" in kwargs:
                    kwargs["lit_color"] = tuple(
                        _validate_rgb(
                            kwargs["lit_color"], "border lightbulbs lit_color"
                        )
                    )
                if "unlit_color" in kwargs:
                    kwargs["unlit_color"] = tuple(
                        _validate_rgb(
                            kwargs["unlit_color"], "border lightbulbs unlit_color"
                        )
                    )
                return LightbulbBorder(**kwargs)
            case _:
                raise ValueError(
                    f"unknown border style {style!r}; "
                    "available: 'rainbow', 'constant', 'color_cycle', 'lightbulbs'"
                )
    # Reject anything else loudly
    raise ValueError(
        f"border must be a string, table, or [r,g,b] list; got {type(value).__name__}"
    )


def _coerce_animation(value: Any) -> Animation | None:
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

    match value:
        case str():
            if value not in registry:
                raise ValueError(
                    f"unknown animation {value!r}; available: {sorted(registry.keys())}"
                )
            cls, _allowed = registry[value]
            return cls()
        case dict():
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
        case _:
            raise ValueError(
                f"animation must be a string or table; " f"got {type(value).__name__}"
            )


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
        "play_count",
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
        "hold_time",
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
