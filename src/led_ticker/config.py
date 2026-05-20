"""TOML configuration loader for led-ticker."""

from __future__ import annotations

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore[import-not-found]
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from led_ticker._coerce import CoercionWarning


@dataclass
class DisplayConfig:
    rows: int = 16
    cols: int = 32
    chain: int = 1
    parallel: int = 1
    pixel_mapper: str = ""
    default_scale: int = 1
    brightness: int = 100
    slowdown_gpio: int = 1
    gpio_mapping: str = "adafruit-hat"
    # Performance / refresh tuning
    pwm_bits: int = 11  # 8 ≈ 8× faster refresh, slightly worse color depth
    pwm_lsb_nanoseconds: int = 130  # higher = slower but more stable
    show_refresh: bool = False  # log measured refresh rate to stderr
    no_hardware_pulse: bool = False  # disable hw PWM (rare; uses CPU instead)
    rp1_rio: int = 0  # Pi 5 only: 0 = PIO (low CPU), 1 = RIO (faster, more CPU)


@dataclass
class TransitionConfig:
    type: str = "cut"
    duration: float = 0.5
    easing: str = "linear"
    color: tuple[int, int, int] | None = None
    colors: list[tuple[int, int, int]] | None = None
    show_pikachu: bool = True
    show_pokeball: bool = True
    transition_obj: Any = None


@dataclass
class SectionConfig:
    mode: str  # "forever_scroll", "infini_scroll", "swap"
    loop_count: int = 1
    title: dict | None = None
    widgets: list[dict] = field(default_factory=list)
    transition: TransitionConfig = field(
        default_factory=TransitionConfig,
    )
    # Whether the user explicitly specified `transition` in this
    # section's TOML. When True, `transition` is also used as the
    # inter-section ENTRY transition (overriding the global
    # `between_sections` for this section's appearance). When False,
    # `transition` falls back to the global `default_transition` for
    # inter-widget purposes only — `between_sections` controls entry.
    # Without this flag, the parser cannot distinguish "user wrote
    # `transition = X`" from "section inherited X from default" — but
    # that distinction is exactly what determines whether the user
    # wanted X to fire on section entry (see app.py inter-section
    # transition selection).
    transition_specified: bool = False
    hold_time: float = 3.0  # seconds to hold each widget in swap mode
    # Whether the user explicitly wrote `hold_time` in this section's TOML.
    # Same mechanism as `transition_specified`: lets the validator surface
    # a warning (rule 30) when a user sets both `hold_time` AND a loop
    # count (e.g. `bottom_text_loops` on two_row) without realizing the
    # engine uses `max()` of the two durations. The flag is purely
    # informational; runtime behavior is unaffected.
    hold_time_specified: bool = False
    continuous_scroll: bool = False  # skip holds for overflow text in scroll mode
    scale: int = 1  # falls back to display.default_scale in load_config
    # Logical canvas height in rows. Default 16 fits one row of 5x8 or 6x12
    # text. Use a larger value (e.g. 20-24) for two_row layouts that need
    # vertical breathing room between rows. The wrapper still letterboxes
    # any space not covered (rows × scale < real.height).
    content_height: int = 16
    # Optional section-level background color. Widgets that omit bg_color
    # inherit this value via _build_widget's default_bg_color parameter.
    bg_color: tuple[int, int, int] | None = None
    # Engine scroll cadence in milliseconds per pixel-step. None falls
    # back to the engine default (50 ms = 1 logical pixel per engine
    # tick). Lowering to 30-40 ms speeds up dense RSS feeds or
    # storefront layouts where the default reads as sluggish; raising
    # above 50 makes it more deliberate. Applies to forever_scroll,
    # infini_scroll, and the post-hold scroll on swap mode. Distinct
    # from the per-widget `scroll_speed_ms` on gif/image text overlays,
    # which controls a text-marquee cadence inside a single widget
    # rather than the engine's cursor advance across widgets.
    scroll_step_ms: int | None = None
    # Pre-roll delay before the section's first widget begins scrolling
    # (forever_scroll / infini_scroll only). `None` inherits the
    # playlist-wide `[title] delay`. An explicit value (including 0.0)
    # overrides — set `start_hold = 0.0` to make this section start
    # immediately while leaving the global delay in place for other
    # sections. Has no runtime effect on `swap` / `gif` modes; the
    # validator (rule 25) rejects the field on those.
    start_hold: float | None = None
    # Per-section override for the forever_scroll loop separator
    # (the small bullet "•" between widgets in side-by-side scroll).
    # `None` inherits today's DEFAULT_BUFFER_MSG (white "•"). An empty
    # string `""` renders as two spaces (no glyph, minimum gap). Any
    # non-empty string is rendered as-is (no auto-padding — caller
    # controls spacing). Only honored on mode = "forever_scroll";
    # rule 26 rejects on other modes.
    separator: str | None = None
    # Font name (BDF alias or hires) for the separator glyph. `None`
    # uses TickerMessage's default font (FONT_DEFAULT). Useful when the
    # section's widget uses a custom display font and the separator
    # should match.
    separator_font: str | None = None
    # Required for hires fonts; ignored for BDF.
    separator_font_size: int | None = None
    # Color provider config. Accepts the same shapes as widget
    # `font_color`: [r, g, b], "rainbow", "color_cycle", or
    # {style = "gradient", ...}. Raw value here; normalized to
    # ColorProvider by app._resolve_buffer_msg at build time.
    separator_color: list[int] | str | dict | None = None
    # Raw TOML dict for this section. Populated by load_config; used by
    # the validator to inspect unknown / cross-scope keys (rules 34, 35).
    # Not included in repr to keep logs readable. Other consumers of
    # SectionConfig are unaffected — field has a default factory so
    # programmatic construction without _raw still works.
    _raw: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)


@dataclass
class AppConfig:
    display: DisplayConfig
    sections: list[SectionConfig]
    title_delay: int = 5
    default_transition: TransitionConfig = field(
        default_factory=TransitionConfig,
    )
    between_sections: TransitionConfig = field(
        default_factory=TransitionConfig,
    )
    # Warnings collected during load_config when string-of-digits or
    # mixed-case enum values get coerced to canonical typed values.
    # validate.py surfaces these as rule-37 warnings; app.py:run() logs
    # them at startup. Empty list when no coercions fired.
    _coerce_warnings: list[CoercionWarning] = field(
        default_factory=list, repr=False, compare=False
    )


_DISPLAY_INT_FIELDS: frozenset[str] = frozenset(
    {
        "rows",
        "cols",
        "chain",
        "parallel",
        "default_scale",
        "brightness",
        "slowdown_gpio",
        "pwm_bits",
        "pwm_lsb_nanoseconds",
        "rp1_rio",
    }
)


def _coerce_display(
    display_raw: dict[str, Any], warnings: list[CoercionWarning]
) -> DisplayConfig:
    """Build DisplayConfig from raw TOML, coercing string-of-digits → int
    on numeric fields. Warnings appended to `warnings`."""
    import dataclasses

    from led_ticker._coerce import coerce_int

    defaults = {f.name: f.default for f in dataclasses.fields(DisplayConfig)}
    kwargs: dict[str, Any] = {}
    for name in _DISPLAY_INT_FIELDS:
        if name in display_raw:
            value, warning = coerce_int(display_raw[name], field=f"display.{name}")
            kwargs[name] = value
            if warning is not None:
                warnings.append(warning)
        else:
            kwargs[name] = defaults[name]
    # String / bool fields pass through without coercion.
    for name in set(defaults) - _DISPLAY_INT_FIELDS:
        kwargs[name] = display_raw.get(name, defaults[name])
    return DisplayConfig(**kwargs)


def _coerce_section(
    section_raw: dict[str, Any],
    index: int,
    display: DisplayConfig,
    warnings: list[CoercionWarning],
) -> dict[str, Any]:
    """Coerce SectionConfig numeric fields. Returns a kwargs dict
    suitable for passing to SectionConfig(...). Bool-typed and
    free-text fields pass through unchanged."""
    from led_ticker._coerce import coerce_float, coerce_int

    prefix = f"section[{index}]"

    def _maybe(name: str, coerce: Any, default: Any) -> Any:
        if name not in section_raw:
            return default
        value, warning = coerce(section_raw[name], field=f"{prefix}.{name}")
        if warning is not None:
            warnings.append(warning)
        return value

    return {
        "loop_count": _maybe("loop_count", coerce_int, 1),
        "hold_time": _maybe("hold_time", coerce_float, 3.0),
        "scale": _maybe("scale", coerce_int, display.default_scale),
        "content_height": _maybe("content_height", coerce_int, 16),
        "scroll_step_ms": _maybe("scroll_step_ms", coerce_int, None),
        "start_hold": _maybe("start_hold", coerce_float, None),
        "separator_font_size": _maybe("separator_font_size", coerce_int, None),
    }


def _coerce_easing(
    raw: dict[str, Any],
    default_easing: str,
    prefix: str,
    warnings: list[CoercionWarning],
) -> str:
    """Coerce the `easing` value if present. Unknown values raise."""
    from led_ticker._coerce import coerce_choice
    from led_ticker.transitions import EASING

    if "easing" not in raw:
        return default_easing
    valid = frozenset(EASING.keys())
    value, warning = coerce_choice(raw["easing"], field=f"{prefix}.easing", valid=valid)
    if warning is not None:
        warnings.append(warning)
    return value


def _parse_transition(
    raw: dict | str | None,
    default: TransitionConfig,
) -> TransitionConfig:
    if raw is None:
        return default
    if isinstance(raw, str):
        return TransitionConfig(
            type=raw,
            duration=default.duration,
            easing=default.easing,
        )
    color = raw.get("transition_color")
    if color is not None:
        color = tuple(color)
    colors = raw.get("transition_colors")
    if colors is not None:
        colors = [tuple(c) for c in colors]
    return TransitionConfig(
        type=raw.get("type", default.type),
        duration=raw.get("duration", default.duration),
        easing=raw.get("easing", default.easing),
        color=color,
        colors=colors,
        show_pikachu=raw.get("show_pikachu", default.show_pikachu),
        show_pokeball=raw.get("show_pokeball", default.show_pokeball),
    )


def load_config(path: Path) -> AppConfig:
    """Load and parse a TOML configuration file."""
    with open(path, "rb") as f:
        raw = tomllib.load(f)

    display_raw = raw.get("display", {})
    coerce_warnings: list[CoercionWarning] = []
    display = _coerce_display(display_raw, coerce_warnings)

    transitions_raw = raw.get("transitions", {})
    default_transition = TransitionConfig(
        type=transitions_raw.get("default", "cut"),
        duration=transitions_raw.get("duration", 0.5),
        easing=_coerce_easing(
            transitions_raw, "linear", "transitions", coerce_warnings
        ),
        show_pikachu=transitions_raw.get("show_pikachu", True),
        show_pokeball=transitions_raw.get("show_pokeball", True),
    )

    sections = []
    for i, section_raw in enumerate(raw.get("playlist", {}).get("section", [])):
        trans = _parse_transition(
            section_raw.get("transition"),
            default_transition,
        )
        # Track whether the user explicitly wrote `transition = ...` in
        # this section's TOML. The parser's `_parse_transition` swallows
        # that signal (returns the default when raw is None), so we
        # inspect the raw dict directly. Used by app.py to decide
        # whether the section should override `between_sections` for
        # its inter-section ENTRY transition.
        transition_specified = "transition" in section_raw
        # Per-section transition overrides
        if "transition_duration" in section_raw:
            trans.duration = section_raw["transition_duration"]
        if "transition_color" in section_raw:
            trans.color = tuple(section_raw["transition_color"])
        if "transition_colors" in section_raw:
            trans.colors = [tuple(c) for c in section_raw["transition_colors"]]
        if "show_pikachu" in section_raw:
            trans.show_pikachu = section_raw["show_pikachu"]
        if "show_pokeball" in section_raw:
            trans.show_pokeball = section_raw["show_pokeball"]
        # Coerce section-level transition easing if present in dict form
        if isinstance(section_raw.get("transition"), dict):
            trans.easing = _coerce_easing(
                section_raw["transition"],
                trans.easing,
                f"section[{i}].transition",
                coerce_warnings,
            )

        bg_color_raw = section_raw.get("bg_color")
        bg_color = tuple(bg_color_raw) if bg_color_raw is not None else None

        section_kwargs = _coerce_section(section_raw, i, display, coerce_warnings)

        section = SectionConfig(
            mode=section_raw.get("mode", "forever_scroll"),
            title=section_raw.get("title"),
            widgets=section_raw.get("widget", []),
            transition=trans,
            transition_specified=transition_specified,
            hold_time_specified=("hold_time" in section_raw),
            continuous_scroll=section_raw.get("continuous_scroll", False),
            bg_color=bg_color,
            separator=section_raw.get("separator"),
            separator_font=section_raw.get("separator_font"),
            separator_color=section_raw.get("separator_color"),
            _raw=section_raw,
            **section_kwargs,
        )
        sections.append(section)

    between_sections = _parse_transition(
        transitions_raw.get("between_sections"),
        default_transition,
    )

    return AppConfig(
        display=display,
        sections=sections,
        title_delay=raw.get("title", {}).get("delay", 5),
        default_transition=default_transition,
        between_sections=between_sections,
        _coerce_warnings=coerce_warnings,
    )
