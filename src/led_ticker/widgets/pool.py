"""Pool water-temperature widget backed by the pool_monitor InfluxDB v2 server."""

from __future__ import annotations

import asyncio
import csv
import io
import logging
import os
import re
from datetime import UTC, datetime
from typing import Any, Self

import aiohttp
import attrs

from led_ticker._types import Color, Font
from led_ticker.colors import BLUE, GREEN, ORANGE, PINK, RED, RGB_WHITE, make_color
from led_ticker.fonts import FONT_DEFAULT
from led_ticker.widget import run_monitor_loop
from led_ticker.widgets import register
from led_ticker.widgets.message import SegmentMessage
from led_ticker.widgets.two_row import TwoRowMessage

# Deadband (in the display unit) below which a change reads as "steady" —
# avoids flicker on sub-degree sensor noise.
_TREND_DEADBAND: float = 0.5

_SENSOR_ID_RE: re.Pattern[str] = re.compile(r"^[A-Za-z0-9_-]+$")

# Color palette.
#
# DIM is reserved for the stale-temp signal (sensor data older than
# `stale_after`) — kept distinctly washed-out so users can tell the
# temperature isn't current.
#
# The prefix labels ("Pool 24h", "Pool 7D", etc.) and separators ("/")
# use the widget's configurable `label_color` field — defaults to white
# but can be tinted (e.g. an icy cyan for a pool widget).
#
# AVG_COLOR is the 7-day mean — pink, deliberately distinct from the
# HI/LO orange/blue axis and from white labels. The 7D AVG is the only
# value on its row that isn't an extreme, so it gets its own attention-
# grabbing color.
#
# STEADY_COLOR is the trend-arrow "no change" case (used only when
# `_trend_arrow` returns the steady glyph). Kept neutral gray so the
# arrow reads as the absence of trend rather than a third alert color.
DIM: Color = make_color(110, 110, 110)
AVG_COLOR: Color = PINK
STEADY_COLOR: Color = make_color(210, 210, 210)
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
    """Whole-degree temp with unit suffix, e.g. '82F'.

    No degree symbol — the hires Inter rasterized at small `font_size`
    drops the U+00B0 glyph (renders as '?'), and the weather widget
    already uses bare 'F'/'C' for the same reason. Stay consistent.
    """
    suffix = "F" if units == "imperial" else "C"
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
    if delta > _TREND_DEADBAND:
        return up
    if delta < -_TREND_DEADBAND:
        return down
    return steady


def _build_flux(
    *, bucket: str, sensor_id: str | None, range_start: str, agg: str
) -> str:
    """Build a single-scalar Flux query.

    `range_start` is a Flux duration ('-7d', '-1h') or an RFC3339
    timestamp. `agg` is one of 'last', 'mean', 'min', 'max'.

    A `group()` is inserted before the aggregation so that buckets
    with multiple sensors (pool water + ambient air + heater coil etc.)
    return a single global aggregate row, not one row per series.
    Without `group()` the CSV parser would pick the first series's
    aggregate — which depends on InfluxDB's tag-value sort order and
    on which sensors happen to have data in the query range. That
    inconsistency surfaced as "season HI 37°F but pool app shows 90°F"
    on a multi-sensor bucket: for short ranges only the pool sensor
    had data so its max returned first; for year-to-date the ambient
    air sensor had data too and sorted earlier.

    Set `sensor_id` in config to pin a specific sensor and skip the
    cross-sensor aggregation.
    """
    sensor_clause = f' and r.id == "{sensor_id}"' if sensor_id else ""
    return (
        f'from(bucket: "{bucket}")\n'
        f"  |> range(start: {range_start})\n"
        f'  |> filter(fn: (r) => r._measurement == "mqtt_consumer"'
        f' and r._field == "temperature_C"{sensor_clause})\n'
        f"  |> group()\n"
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
    font: Font = attrs.field(default=FONT_DEFAULT, kw_only=True)
    layout: str = attrs.field(default="ticker", kw_only=True)
    label_color: Color = attrs.field(default=RGB_WHITE, kw_only=True)
    top_font: Font | None = attrs.field(default=None, kw_only=True)
    bottom_font: Font | None = attrs.field(default=None, kw_only=True)
    top_row_height: int | None = attrs.field(default=None, kw_only=True)
    feed_title: SegmentMessage | TwoRowMessage | None = attrs.field(
        init=False, default=None
    )
    feed_stories: list[SegmentMessage | TwoRowMessage] = attrs.field(
        init=False, factory=list
    )

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
        if widget.sensor_id is not None and not _SENSOR_ID_RE.match(widget.sensor_id):
            raise ValueError(
                f"Invalid sensor_id {widget.sensor_id!r}: " "must match [A-Za-z0-9_-]+"
            )
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
        value, ts = _parse_scalar_csv(text)
        # DEBUG-level so production logs stay quiet; flip --log-level DEBUG
        # to verify each scalar query is returning a sensible value when
        # the displayed numbers look wrong (e.g. season HI too low).
        logger.debug(
            "pool query: range=%s agg=%s → value=%s ts=%s",
            range_start,
            agg,
            value,
            ts,
        )
        return value, ts

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
        if self.layout == "two_row":
            self._build_two_row_screens(
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
        else:
            self._build_ticker_screens(
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

    def _build_two_row_screens(
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
        """Build feed_title + feed_stories in two_row layout. See spec
        docs/superpowers/specs/2026-05-28-pool-two-row-layout-design.md.
        """
        now_display = _c_to_display(current_c, self.units)
        zone_f = _c_to_display(current_c, "imperial")
        stale = current_age_s > self.stale_after

        kw = {
            "font": self.font,
            "top_font": self.top_font,
            "bottom_font": self.bottom_font,
            "top_row_height": self.top_row_height,
            "top_color": self.label_color,
        }

        self.feed_title = TwoRowMessage(
            top_text="POOL",
            bottom_text="TEMPS",
            bottom_color=RGB_WHITE,
            **kw,
        )

        today_bottom_color = DIM if stale else _zone_color(zone_f)
        today = TwoRowMessage(
            top_text="POOL 24H",
            bottom_text=_fmt_temp(now_display, self.units),
            bottom_color=today_bottom_color,
            **kw,
        )
        d7 = TwoRowMessage(
            top_text="POOL 7D AVG",
            bottom_text=self._disp(d7_mean_c),
            bottom_color=AVG_COLOR,
            **kw,
        )
        season_hi = TwoRowMessage(
            top_text="POOL SEASON HI",
            bottom_text=self._disp(season_max_c),
            bottom_color=HI_COLOR,
            **kw,
        )
        season_lo = TwoRowMessage(
            top_text="POOL SEASON LO",
            bottom_text=self._disp(season_min_c),
            bottom_color=LO_COLOR,
            **kw,
        )
        self.feed_stories = [today, d7, season_hi, season_lo]

    def _build_ticker_screens(
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
        now_display = _c_to_display(current_c, self.units)
        past_display = _c_to_display(past_c, self.units) if past_c is not None else None
        # Zone color always evaluated in °F so thresholds are consistent across units.
        zone_f = _c_to_display(current_c, "imperial")
        stale = current_age_s > self.stale_after

        self.feed_title = SegmentMessage(
            [(self.title, RGB_WHITE)], center=True, font=self.font
        )

        temp_color = DIM if stale else _zone_color(zone_f)
        arrow, arrow_color = _trend_arrow(now_display, past_display, ascii_only=True)
        today = SegmentMessage(
            [
                ("Pool 24h ", self.label_color),
                (_fmt_temp(now_display, self.units), temp_color),
                (f" {arrow} ", arrow_color),
                (self._disp(today_max_c), HI_COLOR),
                ("/", self.label_color),
                (self._disp(today_min_c), LO_COLOR),
            ],
            center=True,
            font=self.font,
        )
        d7 = SegmentMessage(
            [
                ("Pool 7D AVG ", self.label_color),
                (self._disp(d7_mean_c), AVG_COLOR),
                ("  ", self.label_color),
                (self._disp(d7_max_c), HI_COLOR),
                ("/", self.label_color),
                (self._disp(d7_min_c), LO_COLOR),
            ],
            center=True,
            font=self.font,
        )
        season = SegmentMessage(
            [
                ("Pool Season HI ", self.label_color),
                (self._disp(season_max_c), HI_COLOR),
                ("  LO ", self.label_color),
                (self._disp(season_min_c), LO_COLOR),
            ],
            center=True,
            font=self.font,
        )
        self.feed_stories = [today, d7, season]

    def _set_placeholder(self) -> None:
        self.feed_title = SegmentMessage(
            [(self.title, RGB_WHITE)], center=True, font=self.font
        )
        self.feed_stories = [
            SegmentMessage(
                [(f"{self.title} ", self.label_color), ("--", self.label_color)],
                center=True,
                font=self.font,
            )
        ]
