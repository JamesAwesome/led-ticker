"""TOML → led-ticker object coercion layer.

Converts raw config values (strings, lists, dicts) to led-ticker objects:
ColorProvider, BorderEffect, Animation, Font. No dependencies on the
widget/ticker engine — only on provider registries and the _coerce helpers.
"""

import inspect
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
    "highlight_color",
}

# Keys that remain raw graphics.Color objects (background fills, title
# color, segment color for weather / data widgets). Kept as Color so widget code
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


def _allowed_init_kwargs(cls: type) -> set[str]:
    """Keyword names a class's constructor accepts (for plugin coercion).

    Explicit parameters only. A plugin class whose constructor takes
    ``**kwargs`` will appear to accept nothing here, so all user kwargs would
    be rejected as unknown — plugin author classes must enumerate their config
    fields as real (positional-or-keyword) parameters, which attrs classes do.
    """
    return {
        name
        for name, p in inspect.signature(cls).parameters.items()
        if p.kind in (p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY)
    }


def _build_plugin_style(cls: type, kwargs: dict, label: str):
    """Validate kwargs against cls's constructor and instantiate, raising
    ValueError (a clean config error) for unknown OR missing-required keys —
    not a raw TypeError. Used by the generic (plugin) coercion paths."""
    allowed = _allowed_init_kwargs(cls)
    unknown = set(kwargs) - allowed
    if unknown:
        raise ValueError(
            f"{label} got unknown keys {sorted(unknown)!r}; allowed: {sorted(allowed)}"
        )
    required = {
        name
        for name, p in inspect.signature(cls).parameters.items()
        if p.kind in (p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY) and p.default is p.empty
    }
    missing = required - set(kwargs)
    if missing:
        raise ValueError(f"{label} missing required keys {sorted(missing)!r}")
    return cls(**kwargs)


_SPECIAL_PROVIDER_STYLES = {"gradient", "color_cycle", "shimmer"}


def _provider_from_style(style: str, kwargs: dict[str, Any]) -> ColorProvider:
    """Instantiate a provider by name with kwargs. Validates kwargs
    against each provider's __init__ signature; raises with a helpful
    message on unknown styles or missing/unknown kwargs."""
    from led_ticker.color_providers import _PROVIDER_REGISTRY

    cls = _PROVIDER_REGISTRY.get(style)
    if cls is None:
        raise ValueError(
            f"unknown font_color style {style!r}; "
            f"available: {sorted(_PROVIDER_REGISTRY)}"
        )

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
        _gradient_user_allowed = {"from", "to"}
        # kwargs at this point only contains internal keys from_color/to_color
        # plus any unexpected extra keys from the user — detect via the internal
        # names we just set vs the full set of non-internal kwargs that remain.
        _gradient_extra = set(kwargs) - {"from_color", "to_color"}
        if _gradient_extra:
            raise ValueError(
                f"font_color style 'gradient' got unknown keys "
                f"{sorted(_gradient_extra)!r}; "
                f"allowed: {sorted(_gradient_user_allowed)}"
            )

    if style == "color_cycle":
        _cycle_user_allowed = {"speed", "from", "to"}
        unknown = set(kwargs) - _cycle_user_allowed
        if unknown:
            raise ValueError(
                f"font_color style 'color_cycle' got unknown keys "
                f"{sorted(unknown)!r}; allowed: {sorted(_cycle_user_allowed)}"
            )
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
        _shimmer_user_allowed = {"base", "shimmer", "speed", "width", "pause"}
        _shimmer_internal = {"base_color", "shimmer_color", "speed", "width", "pause"}
        _shimmer_extra = set(kwargs) - _shimmer_internal
        if _shimmer_extra:
            raise ValueError(
                f"font_color style 'shimmer' got unknown keys "
                f"{sorted(_shimmer_extra)!r}; allowed: {sorted(_shimmer_user_allowed)}"
            )

    if style not in _SPECIAL_PROVIDER_STYLES:
        return _build_plugin_style(cls, kwargs, f"font_color style {style!r}")
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
    - `{style = "bands", colors = "candy_cane" | [[r,g,b], ...], band_width = N,
      speed = N, thickness = N, align_rings = bool}` → `ColorBandsBorder`.
      `colors` is required: a `BAND_PALETTES` name or a list of >= 2 RGB
      colors. `align_rings` radially stacks bands across rings at
      thickness > 1 (default false = woven continuous index).
    - `[r, g, b]` (list/tuple) → `ConstantBorder` shorthand.
    - already a BorderEffect (has `paint`) → passes through.
    - None → None (no border).

    Raises ValueError on unknown styles, missing required kwargs, or
    unknown kwargs.
    """
    from led_ticker.borders import (
        BAND_PALETTES,
        ColorBandsBorder,
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
            case "bands":
                # No defaults make sense without colors — point at the
                # inline-table form instead of the generic missing-keys
                # error from the registry fallback.
                raise ValueError(
                    "border style 'bands' requires 'colors' — use the "
                    "inline-table form: "
                    "border = {style='bands', colors='candy_cane'}"
                )
            case _:
                # Not a built-in shorthand — check the plugin registry
                # (mirrors how _coerce_animation handles unknown strings).
                from led_ticker.borders import _BORDER_REGISTRY

                cls = _BORDER_REGISTRY.get(value)
                if cls is not None:
                    return _build_plugin_style(cls, {}, f"border style {value!r}")
                raise ValueError(
                    f"unknown border style {value!r}; "
                    "available: 'rainbow', 'color_cycle', 'lightbulbs', "
                    "or a registered plugin border"
                )
    # Inline table
    if isinstance(value, dict):
        if "style" not in value:
            raise ValueError(
                f"border table requires 'style' key; got {list(value.keys())!r}"
            )
        style = value["style"]
        kwargs = {k: v for k, v in value.items() if k != "style"}
        from led_ticker.borders import _BORDER_REGISTRY

        cls = _BORDER_REGISTRY.get(style)
        if cls is None:
            raise ValueError(
                f"unknown border style {style!r}; available: {sorted(_BORDER_REGISTRY)}"
            )
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
                    "hue_wraps",
                }
                unknown = set(kwargs.keys()) - allowed
                if unknown:
                    raise ValueError(
                        f"border style 'lightbulbs' got unknown keys "
                        f"{sorted(unknown)!r}; allowed: {sorted(allowed)}"
                    )
                # Coerce RGB-list color fields to tuples; _validate_rgb
                # rejects out-of-range / wrong-shape values.
                # "rainbow" sentinel passes through untouched — handled by
                # LightbulbBorder.__init__. Any other string is invalid.
                if "lit_color" in kwargs and kwargs["lit_color"] != "rainbow":
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
            case "bands":
                allowed = {"colors", "band_width", "speed", "thickness", "align_rings"}
                unknown = set(kwargs.keys()) - allowed
                if unknown:
                    raise ValueError(
                        f"border style 'bands' got unknown keys "
                        f"{sorted(unknown)!r}; allowed: {sorted(allowed)}"
                    )
                if "colors" not in kwargs:
                    raise ValueError(
                        "border style 'bands' requires 'colors': a named "
                        "palette string or a list of [r, g, b] colors, e.g. "
                        "border = {style='bands', colors='candy_cane'}"
                    )
                colors = kwargs.pop("colors")
                if isinstance(colors, str):
                    if colors not in BAND_PALETTES:
                        raise ValueError(
                            f"border 'bands' unknown palette {colors!r}; "
                            f"available: {sorted(BAND_PALETTES)}"
                        )
                    colors = BAND_PALETTES[colors]
                elif isinstance(colors, list | tuple):
                    if len(colors) == 0:
                        raise ValueError("border 'bands' colors must not be empty")
                    if len(colors) == 1:
                        raise ValueError(
                            "border 'bands' colors has a single entry — "
                            "use border = [r, g, b] instead"
                        )
                    colors = [
                        tuple(_validate_rgb(c, f"border 'bands' colors[{i}]"))
                        for i, c in enumerate(colors)
                    ]
                else:
                    raise ValueError(
                        f"border 'bands' colors must be a palette name "
                        f"string or a list of [r, g, b]; got "
                        f"{type(colors).__name__}"
                    )
                kwargs["colors"] = colors
                if "band_width" in kwargs:
                    bw = kwargs["band_width"]
                    if isinstance(bw, bool) or not isinstance(bw, int) or bw < 1:
                        raise ValueError(
                            f"border 'bands' band_width must be an int >= 1; got {bw!r}"
                        )
                if "speed" in kwargs:
                    sp = kwargs["speed"]
                    if isinstance(sp, bool) or not isinstance(sp, int):
                        raise ValueError(
                            f"border 'bands' speed must be an int "
                            f"(negative reverses, 0 = static); got {sp!r}"
                        )
                if "align_rings" in kwargs:
                    ar = kwargs["align_rings"]
                    if not isinstance(ar, bool):
                        raise ValueError(
                            f"border 'bands' align_rings must be a bool; got {ar!r}"
                            "; use align_rings = true or align_rings = false"
                            " (TOML lowercase, no quotes)"
                        )
                return ColorBandsBorder(**kwargs)
            case _:
                return _build_plugin_style(cls, kwargs, f"border style {style!r}")
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
    from led_ticker.animations import _ANIMATION_REGISTRY

    if hasattr(value, "frame_for"):
        return value

    match value:
        case str():
            cls = _ANIMATION_REGISTRY.get(value)
            if cls is None:
                raise ValueError(
                    f"unknown animation {value!r}; "
                    f"available: {sorted(_ANIMATION_REGISTRY)}"
                )
            return cls()
        case dict():
            if "style" not in value:
                raise ValueError(
                    f"animation table requires 'style' key; got {list(value.keys())!r}"
                )
            style = value["style"]
            cls = _ANIMATION_REGISTRY.get(style)
            if cls is None:
                raise ValueError(
                    f"unknown animation {style!r}; "
                    f"available: {sorted(_ANIMATION_REGISTRY)}"
                )
            kwargs = {k: v for k, v in value.items() if k != "style"}
            return _build_plugin_style(cls, kwargs, f"animation {style!r}")
        case _:
            raise ValueError(
                f"animation must be a string or table; got {type(value).__name__}"
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
