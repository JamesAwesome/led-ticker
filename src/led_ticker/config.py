"""TOML configuration loader for led-ticker."""

from __future__ import annotations

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class DisplayConfig:
    rows: int = 16
    cols: int = 32
    chain: int = 1
    brightness: int = 100
    slowdown_gpio: int = 1
    gpio_mapping: str = "adafruit-hat"


@dataclass
class SectionConfig:
    mode: str  # "forever_scroll", "infini_scroll", "swap"
    loop_count: int = 1
    title: dict | None = None
    widgets: list[dict] = field(default_factory=list)


@dataclass
class AppConfig:
    display: DisplayConfig
    sections: list[SectionConfig]
    title_delay: int = 5


def load_config(path: Path) -> AppConfig:
    """Load and parse a TOML configuration file."""
    with open(path, "rb") as f:
        raw = tomllib.load(f)

    display_raw = raw.get("display", {})
    display = DisplayConfig(
        rows=display_raw.get("rows", 16),
        cols=display_raw.get("cols", 32),
        chain=display_raw.get("chain", 1),
        brightness=display_raw.get("brightness", 100),
        slowdown_gpio=display_raw.get("slowdown_gpio", 1),
        gpio_mapping=display_raw.get("gpio_mapping", "adafruit-hat"),
    )

    sections = []
    for section_raw in raw.get("playlist", {}).get("section", []):
        section = SectionConfig(
            mode=section_raw.get("mode", "forever_scroll"),
            loop_count=section_raw.get("loop_count", 1),
            title=section_raw.get("title"),
            widgets=section_raw.get("widget", []),
        )
        sections.append(section)

    return AppConfig(
        display=display,
        sections=sections,
        title_delay=raw.get("title", {}).get("delay", 5),
    )
