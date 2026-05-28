"""Pool water-temperature widget backed by the pool_monitor InfluxDB v2 server."""

from __future__ import annotations

from led_ticker._types import Color
from led_ticker.colors import BLUE, GREEN, ORANGE, RED, make_color

# Deadband (in °F) below which a change reads as "steady" — avoids
# flicker on sub-degree sensor noise.
_TREND_DEADBAND_F: float = 0.5

# Dim gray for stale temps and segment labels.
DIM: Color = make_color(110, 110, 110)
STEADY_COLOR: Color = make_color(150, 150, 150)
HI_COLOR: Color = ORANGE
LO_COLOR: Color = BLUE


def _zone_color(temp_f: float) -> Color:
    """Color for a water temp by dashboard zone (boundaries in °F)."""
    if temp_f < 70.0:
        return BLUE
    if temp_f < 80.0:
        return GREEN
    if temp_f < 90.0:
        return ORANGE
    return RED


def _c_to_display(temp_c: float, units: str) -> float:
    """Convert stored Celsius to the display unit."""
    if units == "imperial":
        return temp_c * 9.0 / 5.0 + 32.0
    return temp_c


def _fmt_temp(temp_display: float, units: str) -> str:
    """Whole-degree temp with unit suffix, e.g. '82°F'."""
    suffix = "°F" if units == "imperial" else "°C"
    return f"{round(temp_display)}{suffix}"


def _trend_arrow(
    now_f: float, past_f: float | None, *, ascii_only: bool
) -> tuple[str, Color]:
    """Return (glyph, color) for the trend vs ~30 min ago.

    `ascii_only` selects the lores-safe glyph set. Color: green up,
    red down, gray steady.
    """
    up = ("^" if ascii_only else "▲", GREEN)
    down = ("v" if ascii_only else "▼", RED)
    steady = ("-" if ascii_only else "–", STEADY_COLOR)
    if past_f is None:
        return steady
    delta = now_f - past_f
    if delta > _TREND_DEADBAND_F:
        return up
    if delta < -_TREND_DEADBAND_F:
        return down
    return steady
