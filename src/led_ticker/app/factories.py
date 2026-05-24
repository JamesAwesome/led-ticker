"""Widget, transition, and frame factory functions.

Converts resolved config objects into live led-ticker instances.
All coercion of raw TOML values happens in coercion.py before these
functions are called.
"""

from __future__ import annotations

import difflib
import inspect
import itertools
import logging
from pathlib import Path
from typing import Any

import aiohttp

from led_ticker.app.coercion import (
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
    ``bottom_font_size``, and ``bottom_font_threshold`` from
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
    if font_name is not None:
        if _is_hires_font_name(font_name) and font_size is None:
            raise ValueError(
                f"HiresFont {font_name!r} requires font_size (real "
                f"pixels). e.g. font_size = 24 for bigsign, "
                f"font_size = 12 for small sign."
            )
        font = resolve_font(font_name, font_size, threshold=font_threshold)
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

    cls_fields = {a.name for a in getattr(cls, "__attrs_attrs__", ())}
    if font_size is not None and "font_size" in cls_fields:
        widget_cfg["font_size"] = font_size

    for prefix in ("top_font", "bottom_font"):
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

    _resolve_fonts(widget_cfg, cls, panel_h_for_warning)

    # Config uses "text" but TickerMessage/TickerCountdown use "message".
    # Only rename for widgets that don't accept `text` natively (e.g.
    # GifPlayer takes `text` directly for its alongside-text feature).
    cls_fields = {a.name for a in getattr(cls, "__attrs_attrs__", ())}

    if "text" in widget_cfg and "text" not in cls_fields:
        if "message" not in widget_cfg:
            widget_cfg["message"] = widget_cfg.pop("text")
        else:
            widget_cfg.pop("text")

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


def _list_widget_fields(widget_type: str) -> str:
    """Return a human-readable field listing for widget_type.

    Shows dispatch-level fields (_build_widget pops these before the
    allowlist check) and the widget's init-able attrs fields with types
    and defaults.
    """
    import attrs as _attrs

    from led_ticker.widgets import _WIDGET_REGISTRY

    if widget_type not in _WIDGET_REGISTRY:
        candidates = sorted(_WIDGET_REGISTRY.keys())
        matches = difflib.get_close_matches(widget_type, candidates, n=3, cutoff=0.6)
        hint = (
            f"\nDid you mean: {', '.join(repr(m) for m in matches)}" if matches else ""
        )
        raise ValueError(
            f"Unknown widget type: {widget_type!r}. Available: {candidates}{hint}"
        )

    cls = _WIDGET_REGISTRY[widget_type]
    lines: list[str] = [f'Fields for type="{widget_type}":', ""]

    # Widget-specific attrs fields (init=True only)
    init_attrs = [
        a
        for a in getattr(cls, "__attrs_attrs__", ())
        if a.init is not False and a.name != "session"
    ]
    if init_attrs:
        lines.append("Widget-level fields:")
        for a in init_attrs:
            if a.type is None:
                type_str = ""
            elif isinstance(a.type, str):
                type_str = a.type
            else:
                type_str = getattr(a.type, "__name__", str(a.type))

            if a.default is _attrs.NOTHING:
                default_str = "(required)"
            elif isinstance(a.default, _attrs.Factory):  # type: ignore[arg-type]
                default_str = "default: <computed>"
            else:
                default_str = f"default: {a.default!r}"

            lines.append(f"  {a.name:<30}  {type_str:<35}  {default_str}")
        lines.append("")

    # Dispatch-level fields that _build_widget handles (popped before allowlist)
    lines.append("Dispatch-level fields (shared; _build_widget handles these):")
    dispatch: list[tuple[str, str]] = [
        ("type", "required; widget type name (e.g. 'message', 'gif')"),
        ("text", "alias → widget's primary text field"),
        ("font", "BDF alias or hi-res font name"),
        ("font_size", "pixel height; required for hi-res fonts"),
        ("font_threshold", "int 0–255; default 128"),
        ("animation", "e.g. 'typewriter'; valid on message/gif/image only"),
        ("border", "{style='...',...}; valid on message/countdown/two_row/gif/image"),
        ("text_wrap", "bool; valid on gif/image only"),
        ("text_separator", "str; valid on gif/image only"),
        ("text_separator_color", "color; valid on gif/image only"),
        ("bottom_text_wrap", "bool; valid on gif/image/two_row"),
        ("bottom_text_separator", "str; valid on gif/image/two_row"),
        ("bottom_text_separator_color", "color; valid on gif/image/two_row"),
        ("top_font", "font name; valid on two_row"),
        ("top_font_size", "pixel height; valid on two_row"),
        ("top_font_threshold", "int 0–255; valid on two_row"),
        ("bottom_font", "font name; valid on two_row"),
        ("bottom_font_size", "pixel height; valid on two_row"),
        ("bottom_font_threshold", "int 0–255; valid on two_row"),
    ]
    for name, desc in dispatch:
        lines.append(f"  {name:<30}  {desc}")

    return "\n".join(lines)
