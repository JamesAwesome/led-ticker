"""TOML configuration loader for led-ticker."""

from __future__ import annotations

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore[import-not-found]
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


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
    hold_time: float = 3.0  # seconds to hold each widget in swap mode
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
    )


def load_config(path: Path) -> AppConfig:
    """Load and parse a TOML configuration file."""
    with open(path, "rb") as f:
        raw = tomllib.load(f)

    display_raw = raw.get("display", {})
    display = DisplayConfig(
        rows=display_raw.get("rows", 16),
        cols=display_raw.get("cols", 32),
        chain=display_raw.get("chain", 1),
        parallel=display_raw.get("parallel", 1),
        pixel_mapper=display_raw.get("pixel_mapper", ""),
        default_scale=display_raw.get("default_scale", 1),
        brightness=display_raw.get("brightness", 100),
        slowdown_gpio=display_raw.get("slowdown_gpio", 1),
        gpio_mapping=display_raw.get("gpio_mapping", "adafruit-hat"),
        pwm_bits=display_raw.get("pwm_bits", 11),
        pwm_lsb_nanoseconds=display_raw.get("pwm_lsb_nanoseconds", 130),
        show_refresh=display_raw.get("show_refresh", False),
        no_hardware_pulse=display_raw.get("no_hardware_pulse", False),
        rp1_rio=display_raw.get("rp1_rio", 0),
    )

    transitions_raw = raw.get("transitions", {})
    default_transition = TransitionConfig(
        type=transitions_raw.get("default", "cut"),
        duration=transitions_raw.get("duration", 0.5),
        easing=transitions_raw.get("easing", "linear"),
        show_pikachu=transitions_raw.get("show_pikachu", True),
    )

    sections = []
    for section_raw in raw.get("playlist", {}).get("section", []):
        trans = _parse_transition(
            section_raw.get("transition"),
            default_transition,
        )
        # Per-section overrides
        if "transition_duration" in section_raw:
            trans.duration = section_raw["transition_duration"]
        if "transition_color" in section_raw:
            trans.color = tuple(section_raw["transition_color"])
        if "transition_colors" in section_raw:
            trans.colors = [tuple(c) for c in section_raw["transition_colors"]]
        if "show_pikachu" in section_raw:
            trans.show_pikachu = section_raw["show_pikachu"]

        bg_color_raw = section_raw.get("bg_color")
        bg_color = tuple(bg_color_raw) if bg_color_raw is not None else None

        section = SectionConfig(
            mode=section_raw.get("mode", "forever_scroll"),
            loop_count=section_raw.get("loop_count", 1),
            title=section_raw.get("title"),
            widgets=section_raw.get("widget", []),
            transition=trans,
            hold_time=section_raw.get("hold_time", 3.0),
            continuous_scroll=section_raw.get("continuous_scroll", False),
            scale=section_raw.get("scale", display.default_scale),
            content_height=section_raw.get("content_height", 16),
            bg_color=bg_color,
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
    )
