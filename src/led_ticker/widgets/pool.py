"""Pool water-temperature widget backed by the pool_monitor InfluxDB v2 server."""

from __future__ import annotations

import asyncio
import csv
import io
import logging
import os
from datetime import UTC, datetime
from typing import Any, Self

import aiohttp
import attrs

from led_ticker._types import Color
from led_ticker.colors import BLUE, GREEN, ORANGE, RED, RGB_WHITE, make_color
from led_ticker.widget import run_monitor_loop
from led_ticker.widgets import register
from led_ticker.widgets.message import SegmentMessage

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


logger = logging.getLogger(__name__)

_DEFAULT_INTERVAL = 300


@register("pool")
@attrs.define
class PoolMonitor:
    """Pool water temperature, cycled as title/today/7-day/season screens."""

    session: aiohttp.ClientSession
    title: str = "POOL TEMPS"
    sensor_id: str | None = None
    units: str = "imperial"
    stale_after: float = 900.0
    influxdb_url: str = attrs.field(
        factory=lambda: os.getenv("INFLUXDB_URL", "http://influxdb:8086")
    )
    influxdb_org: str = attrs.field(factory=lambda: os.getenv("INFLUXDB_ORG", "pool"))
    influxdb_bucket: str = attrs.field(
        factory=lambda: os.getenv("INFLUXDB_BUCKET", "pool_temps")
    )
    influxdb_token: str = attrs.field(factory=lambda: os.getenv("INFLUXDB_TOKEN", ""))
    feed_title: SegmentMessage | None = attrs.field(init=False, default=None)
    feed_stories: list[SegmentMessage] = attrs.field(init=False, factory=list)

    @classmethod
    async def start(
        cls,
        session: aiohttp.ClientSession,
        update_interval: int = _DEFAULT_INTERVAL,
        **kwargs: Any,
    ) -> Self:
        widget = cls(session=session, **kwargs)
        if not widget.influxdb_token:
            raise ValueError("INFLUXDB_TOKEN not set. Add it to your .env file.")
        widget._set_placeholder()
        try:
            await widget.update()
        except Exception:
            logger.exception("Pool initial update failed; showing placeholder")
        asyncio.create_task(run_monitor_loop(widget, update_interval))
        return widget

    async def _query(
        self, range_start: str, agg: str
    ) -> tuple[float | None, str | None]:
        flux = _build_flux(
            bucket=self.influxdb_bucket,
            sensor_id=self.sensor_id,
            range_start=range_start,
            agg=agg,
        )
        url = f"{self.influxdb_url}/api/v2/query?org={self.influxdb_org}"
        headers = {
            "Authorization": f"Token {self.influxdb_token}",
            "Content-Type": "application/vnd.flux",
            "Accept": "application/csv",
        }
        async with self.session.post(url, data=flux, headers=headers) as resp:
            resp.raise_for_status()
            text = await resp.text()
        return _parse_scalar_csv(text)

    async def update(self) -> None:
        year_start = f"{datetime.now(UTC).year}-01-01T00:00:00Z"
        current_c, current_time = await self._query("-1h", "last")
        past_c, _ = await self._query("-45m", "mean")  # ~30 min lookback avg
        today_min_c, _ = await self._query("today()", "min")
        today_max_c, _ = await self._query("today()", "max")
        d7_mean_c, _ = await self._query("-7d", "mean")
        d7_min_c, _ = await self._query("-7d", "min")
        d7_max_c, _ = await self._query("-7d", "max")
        season_min_c, _ = await self._query(year_start, "min")
        season_max_c, _ = await self._query(year_start, "max")

        if current_c is None:
            self._set_placeholder()
            return

        age = self._age_seconds(current_time)
        self._build_screens(
            current_c=current_c,
            current_age_s=age,
            past_c=past_c,
            today_min_c=today_min_c,
            today_max_c=today_max_c,
            d7_mean_c=d7_mean_c,
            d7_min_c=d7_min_c,
            d7_max_c=d7_max_c,
            season_min_c=season_min_c,
            season_max_c=season_max_c,
        )

    @staticmethod
    def _age_seconds(ts: str | None) -> float:
        if not ts:
            return float("inf")
        try:
            t = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            return float("inf")
        return (datetime.now(UTC) - t).total_seconds()

    def _disp(self, c: float | None) -> str:
        if c is None:
            return "--"
        return str(round(_c_to_display(c, self.units)))

    def _build_screens(
        self,
        *,
        current_c: float,
        current_age_s: float,
        past_c: float | None,
        today_min_c: float | None,
        today_max_c: float | None,
        d7_mean_c: float | None,
        d7_min_c: float | None,
        d7_max_c: float | None,
        season_min_c: float | None,
        season_max_c: float | None,
    ) -> None:
        now_f = _c_to_display(current_c, self.units)
        past_f = _c_to_display(past_c, self.units) if past_c is not None else None
        stale = current_age_s > self.stale_after

        self.feed_title = SegmentMessage([(self.title, RGB_WHITE)], center=True)

        temp_color = DIM if stale else _zone_color(now_f)
        arrow, arrow_color = _trend_arrow(now_f, past_f, ascii_only=True)
        today = SegmentMessage(
            [
                (_fmt_temp(now_f, self.units), temp_color),
                (f" {arrow} ", arrow_color),
                (self._disp(today_max_c), HI_COLOR),
                ("/", DIM),
                (self._disp(today_min_c), LO_COLOR),
            ],
            center=True,
        )
        d7 = SegmentMessage(
            [
                ("7D ", DIM),
                ("AVG ", DIM),
                (self._disp(d7_mean_c), STEADY_COLOR),
                ("  ", DIM),
                (self._disp(d7_max_c), HI_COLOR),
                ("/", DIM),
                (self._disp(d7_min_c), LO_COLOR),
            ],
            center=True,
        )
        season = SegmentMessage(
            [
                ("Season ", DIM),
                ("HI ", DIM),
                (self._disp(season_max_c), HI_COLOR),
                ("  ", DIM),
                ("LO ", DIM),
                (self._disp(season_min_c), LO_COLOR),
            ],
            center=True,
        )
        self.feed_stories = [today, d7, season]

    def _set_placeholder(self) -> None:
        self.feed_title = SegmentMessage([(self.title, RGB_WHITE)], center=True)
        self.feed_stories = [
            SegmentMessage([(f"{self.title} ", DIM), ("--", DIM)], center=True)
        ]
