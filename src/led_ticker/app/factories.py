"""Widget, transition, and frame factory functions.

Converts resolved config objects into live led-ticker instances.
All coercion of raw TOML values happens in coercion.py before these
functions are called.
"""

import collections
import difflib
import inspect
import itertools
import logging
import re
from pathlib import Path
from typing import Any

import aiohttp

from led_ticker.app.coercion import (
    _build_plugin_style,
    _coerce_animation,
    _coerce_border,
    _coerce_color_provider,
    _coerce_widget_cfg,
    _coerce_widget_colors,
    _is_hires_font_name,
)
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
from led_ticker.config import SectionConfig, TransitionConfig
from led_ticker.frame import LedFrame
from led_ticker.transitions import Transition, get_transition_class
from led_ticker.widgets import get_widget_class
from led_ticker.widgets.message import TickerMessage

# ---------------------------------------------------------------------------
# Field metadata for --list-fields CLI output
# ---------------------------------------------------------------------------

FieldHint = collections.namedtuple(
    "FieldHint", ["display_type", "description", "default_display"]
)

# Human-readable type strings, descriptions, and default overrides for --list-fields.
# Fields not in this dict fall back to attrs annotation + repr.
FIELD_HINTS: dict[str, FieldHint] = {
    # Universal widget fields
    "font": FieldHint(
        "font name", "BDF alias or hi-res font name", "panel default font"
    ),
    "font_size": FieldHint(
        "int (pixels)", "text height in real pixels; required for hi-res fonts", "none"
    ),
    "font_threshold": FieldHint(
        "int 0–255", "bitmask threshold for hi-res font rendering", "128"
    ),
    "font_color": FieldHint(
        'color | "rainbow" | "color_cycle" | "shimmer" | {style=...}',
        "text color or animated color provider",
        "white",
    ),
    "bg_color": FieldHint("[r, g, b] | none", "solid background fill color", "none"),
    "top_bg_color": FieldHint(
        "[r, g, b] | none", "solid background fill for the top row band", "none"
    ),
    "bottom_bg_color": FieldHint(
        "[r, g, b] | none", "solid background fill for the bottom row band", "none"
    ),
    "animation": FieldHint(
        '"typewriter" | {style="typewriter", frames_per_char=N}',
        "text animation effect",
        "none",
    ),
    "border": FieldHint(
        '"rainbow" | "color_cycle" | "lightbulbs" | [r,g,b]'  # noqa: E501
        ' | {style="rainbow"|"color_cycle"|"constant"|"lightbulbs"|"bands", ...}',
        "animated border painted at panel edges"
        " — five styles (rainbow chase, color cycle, constant, bands, lightbulbs)"
        "; see /concepts/borders/",
        "none",
    ),
    # TickerMessage / TickerCountdown
    "text": FieldHint("str", "widget text content", None),
    "center": FieldHint("bool", "center text when it fits; false = left-align", "true"),
    "padding": FieldHint(
        "int (pixels)", "end padding (spacing in side-by-side scroll)", "6"
    ),
    # GifPlayer / StillImage single-row
    "path": FieldHint("str", "path to file (relative to config dir or absolute)", None),
    "text_align": FieldHint(
        '"auto" | "scroll" | "scroll_over" | "left" | "right" | "center"',
        "text scroll/position mode",
        '"auto"',
    ),
    "text_valign": FieldHint(
        '"top" | "center" | "bottom"', "vertical text alignment", '"center"'
    ),
    "fit": FieldHint(
        '"pillarbox" | "letterbox" | "stretch" | "crop"',
        "how image fills canvas",
        '"pillarbox"',
    ),
    "image_align": FieldHint(
        '"left" | "center" | "right"',
        "horizontal image alignment within canvas",
        '"center"',
    ),
    "scroll_direction": FieldHint(
        '"left" | "right"', "direction the text scrolls", '"left"'
    ),
    "scroll_speed_ms": FieldHint("int (ms)", "milliseconds per scroll step", "50"),
    "text_loops": FieldHint(
        "int",
        "minimum full text scrolls before advancing; 0 = one loop (NOT zero loops)",
        "0",
    ),
    "play_count": FieldHint(
        "int",
        "times the gif/image plays per visit; 0 = loop for section hold_time duration",
        "1",
    ),
    "hold_time": FieldHint(
        "float (seconds)",
        "per-widget display duration floor; 0.0 defers to section",
        "0.0",
    ),
    # GifPlayer / StillImage two-row overlay (active when bottom_text != "")
    "top_text": FieldHint("str", "top row text content", "''"),
    "bottom_text": FieldHint(
        "str", "bottom row text; set to non-empty to enable two-row mode", "''"
    ),
    "top_color": FieldHint(
        'color | "rainbow" | "color_cycle" | "shimmer" | {style=...}',
        "top row text color",
        "white",
    ),
    "bottom_color": FieldHint(
        'color | "rainbow" | "color_cycle" | "shimmer" | {style=...}',
        "bottom row text color",
        "white",
    ),
    "top_align": FieldHint(
        '"left" | "center" | "right"', "top row horizontal alignment", '"center"'
    ),
    "bottom_align": FieldHint(
        '"left" | "center" | "right"', "bottom row horizontal alignment", '"center"'
    ),
    "top_font": FieldHint(
        "font name",
        "per-row font override for the top row; BDF alias or hi-res font name",
        "none",
    ),
    "bottom_font": FieldHint(
        "font name",
        "per-row font override for the bottom row; BDF alias or hi-res font name",
        "none",
    ),
    "bottom_text_scroll": FieldHint(
        '"marquee" | "scroll_through"',
        "bottom row scroll behavior on overflow",
        '"marquee"',
    ),
    "top_row_height": FieldHint(
        "int | none", "top row height in logical pixels (none = 50/50 split)", "none"
    ),
    # --- Clock ---
    "format": FieldHint(
        '"12h" | "24h" | strftime template',
        'time format: a preset or a strftime string like "%a %b %-d  %-I:%M %p"',
        '"12h"',
    ),
    "timezone": FieldHint(
        "IANA name | none",
        'timezone override, e.g. "America/New_York" (default: system local)',
        "system local",
    ),
    # --- Countdown ---
    "countdown_date": FieldHint(
        "YYYY-MM-DD",
        "target date to count down to (ISO format, e.g. 2026-12-25)",
        None,
    ),
    # --- Weather ---
    "location": FieldHint(
        "str",
        "WeatherAPI query string — city name, zip code, or lat,lon",
        None,
    ),
    "units": FieldHint(
        '"imperial" | "metric"',
        "temperature unit system",
        '"imperial"',
    ),
    "font_color_temp": FieldHint(
        "color | ...",
        "color for the temperature value (separate from label font_color)",
        "white",
    ),
    "show_icon": FieldHint(
        "bool",
        "show weather condition icon alongside temperature",
        "true",
    ),
    # --- RSS feed ---
    "feed_url": FieldHint(
        "str (URL)",
        "RSS or Atom feed URL to poll for headlines",
        None,
    ),
    "max_stories": FieldHint(
        "int",
        "maximum stories to show per cycle",
        "5",
    ),
    # --- Pool (shared layout knob) ---
    "layout": FieldHint(
        '"ticker" | "two_row" | "scoreboard"',
        "widget render mode. pool: ticker (single-row segmented, with "
        "trend arrow) or two_row (stacked label-on-top / big-value-on-"
        "bottom, bigsign-recommended).",
        '"ticker"',
    ),
    # --- label color (shared: pool.monitor) ---
    "label_color": FieldHint(
        "[r, g, b]", "color for the prefix labels and separators", "white"
    ),
    # --- Calendar ---
    "ics_url": FieldHint("str", "public .ics feed URL (or file:// path)", "required"),
    "max_events": FieldHint("int", "max agenda events to show", "5"),
    "lookahead_days": FieldHint("int", "days ahead to scan for events", "7"),
    "time_format": FieldHint("str", "'12h' or '24h' for the event time", "12h"),
    "empty_text": FieldHint(
        "str", "shown when no upcoming events", "No upcoming events"
    ),
    "filter": FieldHint(
        "list[str]", "keep only events whose summary matches a keyword", "[] (all)"
    ),
    "highlight": FieldHint(
        "list[str]", "recolor + always-include matching events", "[] (none)"
    ),
    "highlight_color": FieldHint(
        '[r,g,b] | "rainbow" | {style=...}', "color for highlighted events", "amber"
    ),
}

# Attrs fields on gif/image widgets that only activate when bottom_text != "".
# _list_widget_fields groups these into a separate "Two-row overlay" section.
TWO_ROW_OVERLAY_FIELDS: frozenset[str] = frozenset(
    {
        "top_text",
        "bottom_text",
        "top_color",
        "bottom_color",
        "top_align",
        "bottom_align",
        "top_font",
        "top_font_size",
        "top_font_threshold",
        "top_text_y_offset",
        "top_emoji_y_offset",
        "bottom_font",
        "bottom_font_size",
        "bottom_font_threshold",
        "bottom_text_y_offset",
        "bottom_emoji_y_offset",
        "bottom_text_scroll",
        "bottom_text_wrap",
        "bottom_text_separator",
        "bottom_text_separator_color",
        "top_row_height",
    }
)

# Dispatch-level fields and which widget types they apply to.
# None = applies to all types. Fields applicable to the queried type
# AND not already present in widget-level attrs are shown in "Shared fields".
_DISPATCH_APPLICABLE_TYPES: dict[str, set[str] | None] = {
    "type": None,
    "text": None,
    "font": None,
    "font_size": None,
    "font_threshold": None,
    "animation": {"message", "gif", "image"},
    "border": {"message", "countdown", "two_row", "gif", "image"},
    "text_wrap": {"gif", "image"},
    "text_separator": {"gif", "image"},
    "text_separator_color": {"gif", "image"},
    "bottom_text_wrap": {"gif", "image", "two_row"},
    "bottom_text_separator": {"gif", "image", "two_row"},
    "bottom_text_separator_color": {"gif", "image", "two_row"},
    "top_font": {"two_row"},
    "top_font_size": {"two_row"},
    "top_font_threshold": {"two_row"},
    "bottom_font": {"two_row"},
    "bottom_font_size": {"two_row"},
    "bottom_font_threshold": {"two_row"},
}

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


# Widget types removed from core. coingecko was re-homed in the led-ticker-crypto
# plugin; coinbase and etherscan were RETIRED (no direct replacement). The message
# is per-type so the hint is honest — an etherscan (gas) user must not be told to
# use crypto.coingecko (a price ticker).
_CRYPTO_MIGRATION: dict[str, tuple[str, str]] = {
    "coingecko": (
        "Widget type 'coingecko' was removed from led-ticker core; it now ships "
        "in the led-ticker-crypto plugin as 'crypto.coingecko'.",
        'Install led-ticker-crypto and use type = "crypto.coingecko".',
    ),
    "coinbase": (
        "Widget type 'coinbase' was retired from led-ticker core (no direct "
        "replacement). For a crypto price ticker, the led-ticker-crypto plugin "
        "offers 'crypto.coingecko' — note it needs a CoinGecko symbol_id "
        '(e.g. "bitcoin").',
        'Install led-ticker-crypto and use type = "crypto.coingecko" with a '
        "symbol_id, or remove the widget.",
    ),
    "etherscan": (
        "Widget type 'etherscan' was retired from led-ticker core and has no "
        "replacement.",
        "Remove the etherscan widget from your config.",
    ),
}


def build_widget_cfg_error_for_type(widget_type: str) -> tuple[str, str] | None:
    """(message, suggested_fix) for a widget type removed from core, else None."""
    return _CRYPTO_MIGRATION.get(widget_type)


def _cache_key(widget_cfg: dict[str, Any]) -> str:
    """Generate a stable cache key from widget config."""
    return str(sorted(widget_cfg.items()))


def _build_trans_obj(trans_cfg: TransitionConfig) -> Transition | None:
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
    # Plugin transitions (namespaced, dotted type) declare their own config
    # fields and are built through the generic plugin-style path, which gives a
    # clean ValueError for unknown/missing keys (not a raw TypeError). Built-in
    # transitions keep their special-cased kwargs.
    if "." in trans_cfg.type:
        return _build_plugin_style(
            cls, trans_cfg.extra, f"transition {trans_cfg.type!r}"
        )
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


def _resolve_fonts(
    widget_cfg: dict[str, Any],
    cls: type | None,
    panel_h_for_warning: int | None,
) -> None:
    """Resolve font name strings in widget_cfg to font objects, in place.

    Pops ``font``, ``font_size``, ``font_threshold``, ``top_font``,
    ``top_font_size``, ``top_font_threshold``, ``bottom_font``,
    ``bottom_font_size``, ``bottom_font_threshold``, ``small_font``,
    ``small_font_size``, and ``small_font_threshold`` from
    ``widget_cfg``, then inserts back the resolved font objects and
    (for the main font) ``font_size`` when ``cls`` accepts it as an
    attrs field.

    Raises ``ValueError`` when a hi-res font name is supplied without
    the matching ``*_size`` key (the rasterizer requires an explicit
    target height).  Logs a warning when ``panel_h_for_warning`` is set
    and a hi-res ``font_size`` exceeds it.
    """
    from led_ticker.fonts import resolve_font
    from led_ticker.fonts.hires_loader import HiresFont

    font_name = widget_cfg.pop("font", None)
    font_size = widget_cfg.pop("font_size", None)
    font_threshold = widget_cfg.pop("font_threshold", None)

    cls_fields = {a.name for a in getattr(cls, "__attrs_attrs__", ())}

    if font_name is not None:
        if _is_hires_font_name(font_name) and font_size is None:
            raise ValueError(
                f"HiresFont {font_name!r} requires font_size (real "
                f"pixels). e.g. font_size = 24 for bigsign, "
                f"font_size = 12 for small sign."
            )
        font = resolve_font(font_name, font_size, threshold=font_threshold)
        # Only re-insert the resolved font when cls has a `font` attrs field.
        # When cls is None (direct / test calls), insert unconditionally.
        # This prevents widgets without a font field (e.g. rss_feed) from
        # getting an unexpected key that _validate_cfg_fields later rejects.
        if cls is None or "font" in cls_fields:
            widget_cfg["font"] = font

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

    if font_size is not None and "font_size" in cls_fields:
        widget_cfg["font_size"] = font_size

    # `small_font` has no core widget consumer (it was the MLB scoreboard's
    # secondary font); it is retained as a generic per-prefix font hook for
    # plugin widgets — the led-ticker-baseball scoreboard resolves its
    # `small_font` here. Keep it (like GEOMETRIC_SHAPES / lazy_palette) unless
    # no plugin needs it.
    for prefix in ("top_font", "bottom_font", "small_font"):
        row_name = widget_cfg.pop(prefix, None)
        row_size = widget_cfg.pop(f"{prefix}_size", None)
        row_threshold = widget_cfg.pop(f"{prefix}_threshold", None)
        if row_name is not None:
            if _is_hires_font_name(row_name) and row_size is None:
                raise ValueError(
                    f"HiresFont {row_name!r} requires {prefix}_size "
                    f"(real pixels). e.g. {prefix}_size = 22 for "
                    f"bigsign two-row layouts."
                )
            widget_cfg[prefix] = resolve_font(
                row_name, row_size, threshold=row_threshold
            )


def _validate_cfg_fields(
    widget_cfg: dict[str, Any],
    cls: type,
    widget_type: str,
) -> None:
    """Check that all keys in widget_cfg are recognized attrs fields of cls.

    Raises ValueError with did-you-mean suggestions on unknown keys.
    Also includes `cls.start()` parameter names for data widgets that use
    a class-method factory instead of direct construction.
    """
    cls_init_fields = {
        a.name for a in getattr(cls, "__attrs_attrs__", ()) if a.init is not False
    }
    # start()-based data widgets accept kwargs like update_interval via cls.start()
    # that are not attrs fields — include them in the allowlist so configs using
    # these widgets don't get false-positive "unknown field" errors.
    if hasattr(cls, "start"):
        try:
            start_params = set(inspect.signature(cls.start).parameters) - {
                "session",
                "cls",
            }
            cls_init_fields |= start_params
        except (ValueError, TypeError) as exc:
            logging.debug("skipping widget construction: %s", exc)
    unknown = set(widget_cfg.keys()) - cls_init_fields
    if unknown:
        suggestions = []
        for key in sorted(unknown):
            matches = difflib.get_close_matches(
                key, sorted(cls_init_fields), n=1, cutoff=0.6
            )
            hint = f" (did you mean {matches[0]!r}?)" if matches else ""
            suggestions.append(f"{key!r}{hint}")
        raise ValueError(
            f"widget type={widget_type!r} got unknown "
            f"{'field' if len(unknown) == 1 else 'fields'}: " + ", ".join(suggestions)
        )


def _resolve_asset_paths(
    widget_cfg: dict[str, Any],
    widget_type: str,
    config_dir: Path | None,
) -> None:
    """Resolve relative `path` to absolute anchored at config_dir.

    Widgets don't need to know config layout; this keeps that knowledge here.
    """
    if widget_type not in ("gif", "image"):
        return
    if "path" not in widget_cfg:
        return
    if config_dir is None:
        return
    candidate = Path(widget_cfg["path"])
    if not candidate.is_absolute():
        widget_cfg["path"] = str((config_dir / candidate).resolve())


def _widget_declares_field(cls: type, name: str) -> bool:
    """True if an (attrs) widget class declares a config field `name` — lets a
    plugin widget opt into the `animation`/`border` knobs by declaring the field,
    without hardcoding plugin type names."""
    return any(a.name == name for a in getattr(cls, "__attrs_attrs__", ()))


def _run_validate_config(cls: type, cfg: dict[str, Any], widget_type: str) -> None:
    """Run a widget class's optional ``validate_config(cls, cfg) -> list[str]``.

    A by-convention cross-field check that travels with the type (no API
    registration needed). Messages become a pre-flight ``ValueError``. The
    validator gets a COPY of the config so it can't mutate the real one. A
    validator that itself raises is wrapped so the error names the type.
    It must be a ``@classmethod``; a plain instance method raises ``TypeError``
    (caught and re-raised as ``ValueError``).
    """
    validator = getattr(cls, "validate_config", None)
    if validator is None:
        return
    try:
        messages = validator(dict(cfg))
    except Exception as e:
        raise ValueError(f"{widget_type}: validate_config raised: {e}") from e
    if messages:
        raise ValueError(f"{widget_type}: {'; '.join(messages)}")


async def validate_widget_cfg(
    widget_cfg: dict[str, Any],
    session: aiohttp.ClientSession | None,
    config_dir: Path | None = None,
    default_bg_color: tuple[int, int, int] | None = None,
    panel_h_for_warning: int | None = None,
    coercion_collector: list[Any] | None = None,
) -> None:
    """Run all widget configuration validation phases without constructing the widget.

    Equivalent to the former _build_widget(validate_only=True) path but with an
    explicit name and return type. Used by validate.py so the construction/validation
    boundary is explicit.

    Raises ValueError, MigrationError, or other exceptions on invalid config.
    Mutates widget_cfg in-place (type is popped, values coerced).

    `session` is accepted for signature parity with `_build_widget` and is not
    used during validation — validation never calls data-widget `.start()`.
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

    # Migration check: the primary text field on TickerMessage,
    # TickerCountdown, and WeatherWidget was renamed from "message" to
    # "text". Loud failure here catches stale TOMLs at load time.
    if "message" in widget_cfg and widget_cfg.get("type") in (
        "message",
        "countdown",
        "weather",
    ):
        raise MigrationError(
            'The primary text field was renamed from "message" to "text". '
            'Update your config: replace message = "..." with text = "...".',
            suggested_fix='Rename "message" to "text" in your config.',
            fix_key="message",
            fix_replacement_key="text",
        )

    if "gif_loops" in widget_cfg:
        raise MigrationError(
            "gif_loops was renamed to play_count. "
            "Update your config: replace gif_loops = N with play_count = N.",
            suggested_fix='Rename "gif_loops" to "play_count" in your config.',
            fix_key="gif_loops",
            fix_replacement_key="play_count",
        )

    if "loops" in widget_cfg:
        raise MigrationError(
            "loops was renamed to play_count. "
            "Update your config: replace loops = N with play_count = N.",
            suggested_fix='Rename "loops" to "play_count" in your config.',
            fix_key="loops",
            fix_replacement_key="play_count",
        )

    widget_type = widget_cfg.pop("type")
    _crypto_migration = build_widget_cfg_error_for_type(widget_type)
    if _crypto_migration is not None:
        _msg, _suggested_fix = _crypto_migration
        raise MigrationError(_msg, suggested_fix=_suggested_fix)
    cls = get_widget_class(widget_type)
    _run_validate_config(cls, widget_cfg, widget_type)

    _coerce_widget_cfg(widget_cfg, coercion_collector)

    # Animation field. Currently allowed on `message`, `gif`, and
    # `image` — image widgets restrict to single-row mode (validated
    # in `_BaseImageWidget._validate_common`). Pop before construction
    # so it doesn't reach the widget constructor as an unknown kwarg
    # for widget types that don't accept it.
    animation_value = widget_cfg.pop("animation", None)
    if (
        animation_value is not None
        and widget_type not in ("message", "gif", "image")
        and not _widget_declares_field(cls, "animation")
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
    # weather have their own paint logic and a perimeter border
    # isn't a meaningful concept there. Loud failure here catches
    # misplaced `border = ...` in TOML before it surfaces as a
    # confusing "unknown kwarg" downstream.
    border_value = widget_cfg.pop("border", None)
    if (
        border_value is not None
        and widget_type not in ("message", "countdown", "two_row", "gif", "image")
        and not _widget_declares_field(cls, "border")
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

    _resolve_fonts(widget_cfg, cls, panel_h_for_warning)

    _resolve_asset_paths(widget_cfg, widget_type, config_dir)

    # Convert color keys (font_color, top_color, bottom_color) to
    # ColorProvider instances. Constant [r,g,b] lists get wrapped in
    # _ConstantColor so all downstream widget code is uniform.
    _coerce_widget_colors(widget_cfg)

    # Reject top_color / bottom_color on single-row image widgets.
    # These fields are two-row-only (activated when bottom_text != ""); on a
    # single-row widget they're silently ignored, misleading users who expect
    # them to affect the visible text color.
    if widget_type in ("gif", "image") and not widget_cfg.get("bottom_text", ""):
        two_row_only = [k for k in ("top_color", "bottom_color") if k in widget_cfg]
        if two_row_only:
            verb = "is" if len(two_row_only) == 1 else "are"
            raise ValueError(
                f"widget type={widget_type!r}: "
                + ", ".join(repr(k) for k in two_row_only)
                + f" {verb} only valid in two-row mode (when bottom_text is set). "
                "Use font_color for single-row image widgets."
            )

    # Dispatch-level keys were all popped above; remaining keys are splatted
    # directly into cls(**widget_cfg). Any key not in attrs __init__ raises
    # a raw TypeError from attrs — catch it here with a usable message.
    _validate_cfg_fields(widget_cfg, cls, widget_type)


async def _build_widget(
    widget_cfg: dict[str, Any],
    session: aiohttp.ClientSession,
    config_dir: Path | None = None,
    default_bg_color: tuple[int, int, int] | None = None,
    panel_h_for_warning: int | None = None,
    coercion_collector: list[Any] | None = None,
) -> Any:
    """Instantiate a widget from its config dict.

    `config_dir` is the directory containing the config.toml; used to
    resolve relative `path` values for widgets that reference asset
    files (currently `"gif"` and `"image"`).

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
    widget_type: str = widget_cfg["type"]  # peek before validate_widget_cfg pops it
    await validate_widget_cfg(
        widget_cfg,
        session=session,
        config_dir=config_dir,
        default_bg_color=default_bg_color,
        panel_h_for_warning=panel_h_for_warning,
        coercion_collector=coercion_collector,
    )
    cls = get_widget_class(widget_type)
    if hasattr(cls, "start"):
        return await cls.start(session=session, **widget_cfg)
    return cls(**widget_cfg)


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

    `color` is no longer accepted as a title field — it was renamed to
    `font_color`. Using the old spelling raises `MigrationError` so users
    see a clear message and are forced to update their config.

    `session` is required for consistency with `_build_widget` even
    though title widgets (type="message") have no `.start` classmethod
    and never touch it; callers always have one in scope.
    """
    if title_cfg is None:
        return None

    cfg = dict(title_cfg)
    cfg["type"] = "message"
    cfg.setdefault("text", "")

    if "color" in cfg:
        from led_ticker.validate import MigrationError

        raise MigrationError(
            'The title color field was renamed from "color" to "font_color". '
            'Update your config: replace color = "..." with font_color = "...".',
            suggested_fix=(
                'Rename "color" to "font_color" in your'
                " [playlist.section.title] config."
            ),
            fix_key="color",
            fix_replacement_key="font_color",
        )

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

        return _CircleBufferMsg(text=" • ", center=False, font_color=color_provider)

    # Explicit text / font: TickerMessage with literal rendering.
    text = section.separator if section.separator is not None else "•"
    if text == "":
        text = "  "

    kwargs: dict[str, Any] = {
        "text": text,
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
        "Display: %dx%d rows × %dx%d cols (chain_length=%d parallel=%d) "
        "mapper=%r brightness=%d gpio_slowdown=%d pwm_bits=%d "
        "pwm_lsb_ns=%d dither=%d rp1_pio=%d limit_refresh_hz=%d show_refresh_rate=%s",
        display.rows,
        display.parallel,
        display.cols,
        display.chain_length,
        display.chain_length,
        display.parallel,
        display.pixel_mapper_config or "(none)",
        display.brightness,
        display.gpio_slowdown,
        display.pwm_bits,
        display.pwm_lsb_nanoseconds,
        display.pwm_dither_bits,
        display.rp1_pio,
        display.limit_refresh_rate_hz,
        display.show_refresh_rate,
    )
    if display.show_refresh_rate:
        # The rgbmatrix C library prints the live refresh rate to
        # stderr using `\b` backspaces so it overwrites in place.
        # That's by design (a status line, not a log line) but it
        # interleaves with our log output and looks like a glitch.
        # No Python API exposes the value, so we can't fold it into
        # the log stream cleanly. Note where to look so users don't
        # think it's broken.
        logging.info(
            "show_refresh_rate=true: live Hz updates print to stderr in place "
            "(separate from this log stream — that's the C library, "
            "not a glitch). Disable in config to silence."
        )
    return LedFrame(
        led_rows=display.rows,
        led_cols=display.cols,
        led_chain_length=display.chain_length,
        led_parallel=display.parallel,
        led_pixel_mapper_config=display.pixel_mapper_config,
        led_gpio_slowdown=display.gpio_slowdown,
        led_brightness=display.brightness,
        led_hardware_mapping=display.hardware_mapping,
        led_pwm_bits=display.pwm_bits,
        led_pwm_lsb_nanoseconds=display.pwm_lsb_nanoseconds,
        led_pwm_dither_bits=display.pwm_dither_bits,
        led_show_refresh_rate=display.show_refresh_rate,
        led_disable_hardware_pulsing=display.disable_hardware_pulsing,
        led_rp1_pio=display.rp1_pio,
        led_limit_refresh_rate_hz=display.limit_refresh_rate_hz,
        led_multiplexing=display.multiplexing,
        led_row_address_type=display.row_address_type,
        led_panel_type=display.panel_type,
        led_rgb_sequence=display.led_rgb_sequence,
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


def _list_widget_fields(widget_type: str) -> str:
    """Return a human-readable grouped field listing for widget_type."""
    import attrs as _attrs

    from led_ticker.widgets import _WIDGET_REGISTRY

    if widget_type not in _WIDGET_REGISTRY:
        from led_ticker._plugin_hint import plugin_hint

        candidates = sorted(_WIDGET_REGISTRY.keys())
        matches = difflib.get_close_matches(widget_type, candidates, n=3, cutoff=0.6)
        did_you_mean = (
            f"\nDid you mean: {', '.join(repr(m) for m in matches)}" if matches else ""
        )
        base = (
            f"Unknown widget type: {widget_type!r}. "
            f"Available: {candidates}{did_you_mean}"
        )
        plugin = plugin_hint(widget_type, "widget")
        raise ValueError(f"{base} {plugin}" if plugin else base)

    cls = _WIDGET_REGISTRY[widget_type]
    init_attrs = [
        a
        for a in getattr(cls, "__attrs_attrs__", ())
        if a.init is not False and a.name != "session"
    ]
    widget_field_names = {a.name for a in init_attrs}

    # Per-widget hint overrides: a widget class may declare
    # ``_LIST_FIELD_HINTS: ClassVar[dict]`` whose values are either a
    # ``FieldHint`` namedtuple or a plain 3-tuple ``(display_type,
    # description, default_display)``.  Checked first; falls back to the
    # global ``FIELD_HINTS`` dict.  Defined on the widget side as plain
    # data to avoid importing ``FieldHint`` from this module (which would
    # create a circular import: factories → widgets → factories).
    _per_widget_hints: dict[str, Any] = getattr(cls, "_LIST_FIELD_HINTS", {})

    def _resolve_hint(name: str) -> FieldHint | None:
        raw = _per_widget_hints.get(name)
        if raw is not None:
            if isinstance(raw, tuple) and not isinstance(raw, FieldHint):
                return FieldHint(*raw)
            return raw
        return FIELD_HINTS.get(name)

    def _render_field(a: Any) -> str:
        hint = _resolve_hint(a.name)
        if hint:
            type_str = hint.display_type
        elif a.type is None:
            type_str = ""
        elif isinstance(a.type, str):
            type_str = a.type
        else:
            # PEP 649 (3.14, no future-import): a.type is a real type object.
            # Plain types (class 'str', 'int', etc.) have a clean __name__; use
            # it directly.  Union / generic aliases have __name__ == "Union" or
            # lack it entirely — for those, use str() which gives the pipe-form
            # ("bool | None", "typing.Any | None"), then strip any module
            # qualifiers so the output matches the bare-name form the old
            # stringified annotations produced (e.g. "led_ticker.fonts.Font |
            # None" → "Font | None", "typing.Any | None" → "Any | None").
            name = getattr(a.type, "__name__", None)
            if name and name != "Union":
                type_str = name
            else:
                raw = str(a.type)
                type_str = re.sub(r"[\w]+(?:\.[\w]+)*\.([A-Za-z_]\w*)", r"\1", raw)
        if a.default is _attrs.NOTHING:
            default_str = "(required)"
        elif hint and hint.default_display is not None:
            default_str = f"default: {hint.default_display}"
        elif isinstance(a.default, _attrs.Factory):  # type: ignore[arg-type]
            default_str = "default: <computed>"
        else:
            default_str = f"default: {a.default!r}"
        desc_str = f"  — {hint.description}" if hint and hint.description else ""
        return f"  {a.name:<28}  {type_str:<44}  {default_str}{desc_str}"

    # Partition widget attrs into required / optional / two-row-overlay.
    # Two-row overlay only applies to gif/image — for other types all attrs
    # go into required/optional only.
    use_two_row_split = widget_type in ("gif", "image")
    required_attrs = [a for a in init_attrs if a.default is _attrs.NOTHING]
    if use_two_row_split:
        two_row_attrs = [
            a
            for a in init_attrs
            if a.default is not _attrs.NOTHING and a.name in TWO_ROW_OVERLAY_FIELDS
        ]
        optional_attrs = [
            a
            for a in init_attrs
            if a.default is not _attrs.NOTHING and a.name not in TWO_ROW_OVERLAY_FIELDS
        ]
    else:
        two_row_attrs = []
        optional_attrs = [a for a in init_attrs if a.default is not _attrs.NOTHING]

    lines: list[str] = [f'Fields for type="{widget_type}":', ""]

    if required_attrs:
        lines.append("Required:")
        for a in required_attrs:
            lines.append(_render_field(a))
        lines.append("")

    if optional_attrs:
        lines.append("Optional:")
        for a in optional_attrs:
            lines.append(_render_field(a))
        lines.append("")

    if two_row_attrs:
        lines.append("Two-row overlay (set bottom_text to enable):")
        for a in two_row_attrs:
            lines.append(_render_field(a))
        lines.append("")

    # Shared dispatch fields: applicable to this widget type AND not
    # already shown in widget-level (dedup by name).
    dispatch_rows: list[tuple[str, str]] = []
    is_plugin_widget = "." in widget_type
    for name, applicable_types in _DISPATCH_APPLICABLE_TYPES.items():
        if applicable_types is not None and widget_type not in applicable_types:
            continue
        # Plugin widgets don't auto-receive the built-in shared knobs (`type`,
        # `text`, `font`, `font_size`, `font_threshold`); suppress that whole
        # block for them rather than advertise fields they'd reject.
        if is_plugin_widget and applicable_types is None:
            continue
        if name in widget_field_names:
            continue  # already shown above
        hint = FIELD_HINTS.get(name)
        if hint:
            type_part = hint.display_type
            default_part = (
                f"default: {hint.default_display}" if hint.default_display else ""
            )
            desc_suffix = f"  — {hint.description}" if hint.description else ""
            desc = f"{type_part}  {default_part}{desc_suffix}".rstrip()
        else:
            desc = ""
        dispatch_rows.append((name, desc))

    if dispatch_rows:
        lines.append("Shared fields:")
        for name, desc in dispatch_rows:
            lines.append(f"  {name:<28}  {desc}")

    return "\n".join(lines)


def _list_section_fields() -> str:
    """Return a human-readable listing of [[playlist.section]] fields."""
    _SECTION_FIELDS: list[tuple[str, str, str, str]] = [
        # (name, type_str, default_str, description)
        (
            "mode",
            '"forever_scroll" | "infini_scroll" | "swap"',
            "(required)",
            "scroll/display mode for this section",
        ),
        (
            "loop_count",
            "int",
            "default: 1",
            "times the section repeats before advancing; 0 = infinite",
        ),
        (
            "hold_time",
            "float (seconds)",
            "default: 3.0",
            "seconds each widget is held in swap mode",
        ),
        (
            "scroll_step_ms",
            "int (ms)",
            "default: 50",
            "engine cadence — ms per pixel-step in scroll modes; lower = faster scroll",
        ),
        (
            "start_hold",
            "float (seconds)",
            "default: [title].delay",
            "pre-roll pause before first widget scrolls in",
        ),
        (
            "content_height",
            "int (rows)",
            "default: 16",
            "logical canvas height; must not exceed panel_h ÷ scale (see rule 1)",
        ),
        (
            "scale",
            "int",
            "default: [display].default_scale",
            "per-section scale override (bigsign default 4, smallsign default 1)",
        ),
        (
            "bg_color",
            "[r, g, b]",
            "default: none",
            "section background color; widgets inherit this if they omit bg_color",
        ),
        (
            "continuous_scroll",
            "bool",
            "default: false",
            "skip per-widget hold pauses in scroll mode — content streams continuously",
        ),
        (
            "separator",
            "str",
            "default: '•'",
            "bullet between widgets in side-by-side scroll; '' = two spaces",
        ),
        (
            "transition",
            "str",
            "default: [transitions].default",
            "inter-widget transition; also used as section entry transition",
        ),
        (
            "entry_transition",
            "str",
            "default: [transitions].between_sections",
            "overrides how THIS section appears — independent of widget transitions",
        ),
        (
            "widget_transition",
            "str",
            "default: transition or cut",
            "overrides inter-widget transitions within this section only",
        ),
        (
            "transition_duration",
            "float (seconds)",
            "default: [transitions].duration",
            "duration for transitions within this section",
        ),
    ]

    lines: list[str] = ["Fields for [[playlist.section]]:", ""]
    for name, type_str, default_str, description in _SECTION_FIELDS:
        lines.append(f"  {name:<28}  {type_str:<44}  {default_str}  — {description}")
    return "\n".join(lines)
