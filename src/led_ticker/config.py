"""TOML configuration loader for led-ticker."""

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from led_ticker._coerce import CoercionWarning


@dataclass
class DisplayConfig:
    rows: int = 16
    cols: int = 32
    chain_length: int = 1
    parallel: int = 1
    pixel_mapper_config: str = ""
    default_scale: int = 1
    brightness: int = 100
    gpio_slowdown: int = 1
    hardware_mapping: str = "adafruit-hat"
    # Performance / refresh tuning
    pwm_bits: int = 11  # 8 ≈ 8× faster refresh, slightly worse color depth
    pwm_lsb_nanoseconds: int = 130  # higher = slower but more stable
    pwm_dither_bits: int = (
        0  # 0=off, 1–2 spreads PWM energy to reduce row brightness unevenness
    )
    show_refresh_rate: bool = False  # log measured refresh rate to stderr
    disable_hardware_pulsing: bool = False  # disable hw PWM (rare; uses CPU instead)
    rp1_rio: int = 0  # Pi 5 only: 0 = PIO (low CPU), 1 = RIO (faster, more CPU)
    limit_refresh_rate_hz: int = 0  # cap hardware refresh rate (0 = unlimited)
    # Panel scan / wiring — tune if the bottom half renders inverted or garbled.
    # multiplexing: 0=direct 1=Stripe 2=Checker 3=Spiral 4=ZStripe 5=ZnMirrorZStripe
    # row_address_type: 0=direct 1=AB-addr 2=direct-shifted 3=ABC-shifted
    multiplexing: int = 0
    row_address_type: int = 0
    # Driver IC init — set to "FM6126A" or "FM6127" for panels that use those
    # chips (common on cheap P2/P3 AliExpress panels). Without it, FM6126A panels
    # power up in a bad state and show the bottom half mirrored or garbled.
    panel_type: str = ""
    led_rgb_sequence: str = "RGB"


@dataclass
class TransitionConfig:
    type: str = "cut"
    duration: float = 0.5
    easing: str = "linear"
    color: tuple[int, int, int] | None = None
    colors: list[tuple[int, int, int]] | None = None
    show_pikachu: bool = True
    show_pokeball: bool = True
    transition_fps: float | None = None  # None = use run_transition default (20 fps)
    # Non-built-in keys from a plugin transition's TOML table (e.g. {type=
    # "acme.swoosh", speed=3} -> extra={"speed": 3}). Passed to the plugin
    # transition's constructor; empty for built-in transitions.
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class SectionConfig:
    mode: str  # "forever_scroll", "infini_scroll", "swap"
    loop_count: int = 1
    title: dict[str, Any] | None = None
    widgets: list[dict[str, Any]] = field(default_factory=list)
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
    # Independent transition for this section's inter-section ENTRY.
    # When set, overrides both `transition` (when transition_specified=True)
    # and the global `between_sections` default for this section's appearance.
    # `None` means fall through to transition/between_sections precedence.
    entry_transition: TransitionConfig | None = None
    # Independent transition for inter-widget swaps within this section.
    # When set, overrides `transition` (when transition_specified=True).
    # `None` means fall through to transition/cut.
    widget_transition: TransitionConfig | None = None
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
    separator_color: list[int] | str | dict[str, Any] | None = None
    # Raw TOML dict for this section. Populated by load_config; used by
    # the validator to inspect unknown / cross-scope keys (rules 34, 35).
    # Not included in repr to keep logs readable. Other consumers of
    # SectionConfig are unaffected — field has a default factory so
    # programmatic construction without _raw still works.
    _raw: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)


@dataclass
class BusyLightConfig:
    enabled: bool = False
    file_path: str = "~/.busy"
    poll_interval: float = 5.0
    corner: str = "top_right"
    color: tuple[int, int, int] = (255, 0, 0)
    size: int = 4
    source: str = "file"
    http_host: str = "0.0.0.0"
    http_port: int = 8080
    token: str = ""
    ttl_seconds: float = 0.0


@dataclass
class PluginsConfig:
    enabled: bool = True
    dir: str = "plugins"
    disable: list[str] = field(default_factory=list)


def _parse_plugins_block(raw: dict) -> PluginsConfig:
    """Parse + validate the ``[plugins]`` TOML table into a PluginsConfig.

    Shared by ``load_config`` and the lightweight early reader the run loop /
    validate / CLI use (so plugin discovery can run before full config
    validation). Defaults: enabled=True, dir="plugins", disable=[].
    """
    p_raw = raw.get("plugins", {})
    cfg = PluginsConfig(
        enabled=p_raw.get("enabled", True),
        dir=p_raw.get("dir", "plugins"),
        disable=p_raw.get("disable", []),
    )
    if not isinstance(cfg.enabled, bool):
        raise ValueError(
            f"plugins.enabled must be a bool; got {type(cfg.enabled).__name__}."
        )
    if not isinstance(cfg.dir, str):
        raise ValueError(
            f"plugins.dir must be a string; got {type(cfg.dir).__name__}."
        )
    cfg.dir = cfg.dir.strip()
    if not cfg.dir:
        raise ValueError("plugins.dir must not be empty.")
    if Path(cfg.dir).is_absolute():
        raise ValueError(
            f"plugins.dir must be a relative path (joined to the config dir); "
            f"got {cfg.dir!r}."
        )
    if not isinstance(cfg.disable, list) or not all(
        isinstance(n, str) for n in cfg.disable
    ):
        raise ValueError(
            f"plugins.disable must be a list of strings; got {cfg.disable!r}."
        )
    cfg.disable = [n.strip() for n in cfg.disable]
    return cfg


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
    between_sections_specified: bool = False
    busy_light: BusyLightConfig = field(default_factory=BusyLightConfig)
    plugins: PluginsConfig = field(default_factory=PluginsConfig)
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
        "chain_length",
        "parallel",
        "default_scale",
        "brightness",
        "gpio_slowdown",
        "pwm_bits",
        "pwm_lsb_nanoseconds",
        "pwm_dither_bits",
        "rp1_rio",
        "limit_refresh_rate_hz",
    }
)


# Built-in transition knobs. Any other key in a transition table is plugin
# config and gets carried in TransitionConfig.extra for the plugin constructor.
_BUILTIN_TRANSITION_KEYS: frozenset[str] = frozenset(
    {
        "type",
        "duration",
        "easing",
        "transition_color",
        "transition_colors",
        "show_pikachu",
        "show_pokeball",
        "transition_fps",
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
    raw: dict[str, Any] | str | None,
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
    # Any table key that isn't a built-in transition knob is plugin config —
    # carry it in `extra` for the plugin transition's constructor.
    extra = {k: v for k, v in raw.items() if k not in _BUILTIN_TRANSITION_KEYS}
    return TransitionConfig(
        type=raw.get("type", default.type),
        duration=raw.get("duration", default.duration),
        easing=raw.get("easing", default.easing),
        color=color,
        colors=colors,
        show_pikachu=raw.get("show_pikachu", default.show_pikachu),
        show_pokeball=raw.get("show_pokeball", default.show_pokeball),
        transition_fps=raw.get("transition_fps", default.transition_fps),
        extra=extra,
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

    bl_raw = raw.get("busy_light", {})
    busy_light = BusyLightConfig(
        enabled=bl_raw.get("enabled", False),
        file_path=bl_raw.get("file_path", "~/.busy"),
        poll_interval=bl_raw.get("poll_interval", 5.0),
        corner=bl_raw.get("corner", "top_right"),
        color=tuple(bl_raw.get("color", [255, 0, 0])),
        size=bl_raw.get("size", 4),
        source=bl_raw.get("source", "file"),
        http_host=bl_raw.get("http_host", "0.0.0.0"),
        http_port=bl_raw.get("http_port", 8080),
        token=bl_raw.get("token", ""),
        ttl_seconds=bl_raw.get("ttl_seconds", 0.0),
    )
    _BUSY_CORNERS = ("top_left", "top_right", "bottom_left", "bottom_right")
    if busy_light.corner not in _BUSY_CORNERS:
        raise ValueError(
            f"busy_light.corner={busy_light.corner!r} is not valid; "
            f"choose one of: {', '.join(_BUSY_CORNERS)}."
        )
    if busy_light.size < 1:
        raise ValueError(f"busy_light.size must be >= 1; got {busy_light.size}.")
    if (
        len(busy_light.color) != 3
        or not all(isinstance(c, int) for c in busy_light.color)
        or not all(0 <= c <= 255 for c in busy_light.color)
    ):
        raise ValueError(
            f"busy_light.color must be 3 ints in 0-255 [r, g, b]; "
            f"got {busy_light.color!r}."
        )
    _BUSY_SOURCES = ("file", "http")
    if busy_light.source not in _BUSY_SOURCES:
        raise ValueError(
            f"busy_light.source={busy_light.source!r} is not valid; "
            f"choose one of: {', '.join(_BUSY_SOURCES)}."
        )
    if not 1 <= busy_light.http_port <= 65535:
        raise ValueError(
            f"busy_light.http_port must be 1-65535; got {busy_light.http_port}."
        )
    if busy_light.ttl_seconds < 0:
        raise ValueError(
            f"busy_light.ttl_seconds must be >= 0; got {busy_light.ttl_seconds}."
        )
    if not isinstance(busy_light.token, str):
        raise ValueError(
            f"busy_light.token must be a string; "
            f"got {type(busy_light.token).__name__}."
        )

    plugins = _parse_plugins_block(raw)

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
        if "transition_fps" in section_raw:
            trans.transition_fps = section_raw["transition_fps"]
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

        # Parse entry_transition and widget_transition independently.
        # We cannot use _parse_transition(section_raw.get(...), default) because
        # _parse_transition(None, default) returns `default` — not `None`.
        # The fields must be None when absent so the engine can distinguish
        # "user set this" from "user did not set this".
        entry_transition = (
            _parse_transition(section_raw["entry_transition"], TransitionConfig())
            if "entry_transition" in section_raw
            else None
        )
        widget_transition = (
            _parse_transition(section_raw["widget_transition"], TransitionConfig())
            if "widget_transition" in section_raw
            else None
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
            entry_transition=entry_transition,
            widget_transition=widget_transition,
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

    between_sections_specified = "between_sections" in transitions_raw
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
        between_sections_specified=between_sections_specified,
        busy_light=busy_light,
        plugins=plugins,
        _coerce_warnings=coerce_warnings,
    )
