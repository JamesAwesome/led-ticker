"""Pool water-temperature widget backed by the pool_monitor InfluxDB v2 server."""

from __future__ import annotations

import csv
import io

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


def _build_flux(
    *, bucket: str, sensor_id: str | None, range_start: str, agg: str
) -> str:
    """Build a single-scalar Flux query.

    `range_start` is a Flux duration ('-7d', '-1h') or an RFC3339
    timestamp. `agg` is one of 'last', 'mean', 'min', 'max'.
    """
    sensor_clause = f' and r.id == "{sensor_id}"' if sensor_id else ""
    return (
        f'from(bucket: "{bucket}")\n'
        f"  |> range(start: {range_start})\n"
        f'  |> filter(fn: (r) => r._measurement == "mqtt_consumer"'
        f' and r._field == "temperature_C"{sensor_clause})\n'
        f"  |> {agg}()"
    )


def _parse_scalar_csv(text: str) -> tuple[float | None, str | None]:
    """Parse an InfluxDB v2 annotated-CSV response into (value, time).

    Returns (None, None) when there is no data row. Reads the first
    data row's `_value` (float) and `_time` columns.
    """
    reader = csv.reader(io.StringIO(text))
    header: list[str] | None = None
    for row in reader:
        if not row or all(c == "" for c in row):
            continue
        if row[0].startswith("#"):
            continue
        if header is None:
            header = row
            continue
        record = dict(zip(header, row, strict=False))
        raw = record.get("_value", "")
        if raw == "":
            return None, None
        return float(raw), record.get("_time") or None
    return None, None
