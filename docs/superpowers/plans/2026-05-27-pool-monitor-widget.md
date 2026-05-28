# Pool Monitor Widget Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `pool` widget that reads pool water temperature from the pool_monitor InfluxDB v2 server and cycles through title → today → 7-day → season screens with zone-colored temps and a trend arrow.

**Architecture:** A `PoolMonitor` feed-monitor widget (mirroring `MLBStandingsMonitor`): async `start()` does an initial fetch then spawns `run_monitor_loop`; `update()` issues small scalar Flux queries over the injected `aiohttp.ClientSession` and rebuilds `feed_title` + `feed_stories`. Each screen is a generic `SegmentMessage` (promoted out of `mlb.py`). `app/run.py` expands the monitor's stories into the playlist.

**Tech Stack:** Python 3.12, attrs, aiohttp, InfluxDB v2 Flux/CSV, pytest. Run all commands from the worktree root with the project venv (`make dev` first).

**Spec:** `docs/superpowers/specs/2026-05-27-pool-monitor-widget-design.md`

---

## Pre-flight

- [ ] **Set up the worktree dev env**

Run: `make dev`
Expected: venv created/updated, dev deps installed (pyright, ruff, pytest available).

- [ ] **Confirm a clean baseline**

Run: `pytest tests/test_widgets/ -q`
Expected: PASS (note the count; this is the green baseline).

---

## File Structure

- Create `src/led_ticker/widgets/pool.py` — the `PoolMonitor` widget plus its pure helpers (zone color, trend, unit conversion, formatting), Flux query strings, and CSV scalar parsing.
- Modify `src/led_ticker/widgets/message.py` — add the generic `SegmentMessage` class (moved from `mlb.py`).
- Modify `src/led_ticker/widgets/mlb.py` — delete `MLBGameMessage`, import `SegmentMessage`, alias `MLBGameMessage = SegmentMessage` removed in favor of renaming usages.
- Modify `src/led_ticker/widgets/mlb_standings.py` — use `SegmentMessage`.
- Modify `src/led_ticker/app/run.py` — import `PoolMonitor`, add it to the container `isinstance` tuple (line ~96).
- Create `tests/test_widgets/test_pool.py` — widget + helper tests.
- Modify `tests/test_widgets/test_mlb_standings.py` and `tests/test_widgets/test_mlb.py` — update `MLBGameMessage` references to `SegmentMessage`.
- Modify `config/config.example.toml` — add a `pool` example block.
- Create `docs/site/src/content/docs/widgets/pool.mdx`; modify `docs/site/src/content/docs/widgets/index.mdx` and `docs/site/astro.config.mjs`.

---

## Task 1: Promote `MLBGameMessage` → generic `SegmentMessage`

**Files:**
- Modify: `src/led_ticker/widgets/message.py`
- Modify: `src/led_ticker/widgets/mlb.py` (class def ~262-352 and all usages)
- Modify: `src/led_ticker/widgets/mlb_standings.py` (import + usages)
- Modify: `tests/test_widgets/test_mlb.py`, `tests/test_widgets/test_mlb_standings.py`
- Test: `tests/test_widgets/test_message.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_widgets/test_message.py`:

```python
from led_ticker.widgets.message import SegmentMessage
from led_ticker.colors import RGB_WHITE, GREEN


class TestSegmentMessage:
    def test_segments_stored(self):
        msg = SegmentMessage([("A", RGB_WHITE), ("B", GREEN)])
        assert [t for t, _ in msg.segments] == ["A", "B"]

    def test_conforms_to_widget_protocol(self):
        from led_ticker.widget import Widget
        assert isinstance(SegmentMessage([("x", RGB_WHITE)]), Widget)

    def test_draw_centered_returns_canvas(self, canvas):
        msg = SegmentMessage([("82", RGB_WHITE)], center=True)
        result_canvas, cursor_pos = msg.draw(canvas)
        assert result_canvas is canvas
        assert cursor_pos == 160
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_widgets/test_message.py::TestSegmentMessage -v`
Expected: FAIL with `ImportError: cannot import name 'SegmentMessage'`.

- [ ] **Step 3: Move the class into `message.py`**

Cut the entire `MLBGameMessage` class body (currently `src/led_ticker/widgets/mlb.py` lines ~262-352, from `class MLBGameMessage:` through the end of its `draw`) and paste it into `src/led_ticker/widgets/message.py` renamed to `SegmentMessage`. Keep the implementation identical. Ensure `message.py` has the imports the class needs at top of file:

```python
from typing import Any
from led_ticker._types import Canvas, Color, DrawResult, Font
from led_ticker.color_providers import ColorProvider
from led_ticker.drawing import compute_baseline, compute_cursor
from led_ticker.fonts import FONT_DEFAULT
```

(Several of these already exist in `message.py`; add only the missing ones. The `draw` method's local `from led_ticker.pixel_emoji import draw_with_emoji, measure_width` stays as an in-method import.)

Update the class docstring first line to: `"""A line of color-coded text segments, optionally centered."""`

- [ ] **Step 4: Repoint MLB modules to `SegmentMessage`**

In `src/led_ticker/widgets/mlb.py`: delete the moved class, and add `from led_ticker.widgets.message import SegmentMessage`. Replace every `MLBGameMessage(` constructor call and every `MLBGameMessage` type annotation in `mlb.py` with `SegmentMessage`.

In `src/led_ticker/widgets/mlb_standings.py`: change `from led_ticker.widgets.mlb import (... MLBGameMessage ...)` so `MLBGameMessage` is no longer imported from `mlb`; add `from led_ticker.widgets.message import SegmentMessage`; replace `MLBGameMessage` usages (the `_build_standing_message` return type and constructor) with `SegmentMessage`.

In `tests/test_widgets/test_mlb.py` and `tests/test_widgets/test_mlb_standings.py`: replace `from led_ticker.widgets.mlb import MLBGameMessage` with `from led_ticker.widgets.message import SegmentMessage`, and replace `MLBGameMessage` references with `SegmentMessage`.

- [ ] **Step 5: Run the new test + full MLB/message suites**

Run: `pytest tests/test_widgets/test_message.py tests/test_widgets/test_mlb.py tests/test_widgets/test_mlb_standings.py -q`
Expected: PASS (new SegmentMessage tests green; MLB tests still green — pure rename).

- [ ] **Step 6: Type-check the touched modules**

Run: `pyright src/led_ticker/widgets/message.py src/led_ticker/widgets/mlb.py src/led_ticker/widgets/mlb_standings.py`
Expected: 0 errors.

- [ ] **Step 7: Commit**

```bash
git add src/led_ticker/widgets/message.py src/led_ticker/widgets/mlb.py src/led_ticker/widgets/mlb_standings.py tests/test_widgets/test_message.py tests/test_widgets/test_mlb.py tests/test_widgets/test_mlb_standings.py
git commit -m "refactor: promote MLBGameMessage to generic SegmentMessage"
```

---

## Task 2: Pure display helpers (zone color, trend, units, formatting)

All functions live in the new `src/led_ticker/widgets/pool.py`. This task creates the file with only the pure helpers + module color constants; the widget class comes in Task 4.

**Files:**
- Create: `src/led_ticker/widgets/pool.py`
- Create: `tests/test_widgets/test_pool.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_widgets/test_pool.py`:

```python
import unittest.mock as mock
import pytest

from led_ticker.colors import BLUE, GREEN, ORANGE, RED
from led_ticker.widgets.pool import (
    _zone_color,
    _trend_arrow,
    _c_to_display,
    _fmt_temp,
)


class TestZoneColor:
    @pytest.mark.parametrize("f,expected", [
        (60.0, BLUE), (69.9, BLUE),
        (70.0, GREEN), (79.9, GREEN),
        (80.0, ORANGE), (89.9, ORANGE),
        (90.0, RED), (95.0, RED),
    ])
    def test_zones(self, f, expected):
        assert _zone_color(f) is expected


class TestTrendArrow:
    def test_up_when_above_deadband(self):
        glyph, _ = _trend_arrow(now_f=82.0, past_f=81.0, ascii_only=True)
        assert glyph == "^"

    def test_down_when_below_deadband(self):
        glyph, _ = _trend_arrow(now_f=80.0, past_f=81.0, ascii_only=True)
        assert glyph == "v"

    def test_steady_within_deadband(self):
        glyph, _ = _trend_arrow(now_f=81.2, past_f=81.0, ascii_only=True)
        assert glyph == "-"

    def test_steady_when_past_missing(self):
        glyph, _ = _trend_arrow(now_f=81.0, past_f=None, ascii_only=True)
        assert glyph == "-"


class TestUnits:
    def test_c_to_fahrenheit(self):
        assert _c_to_display(25.0, "imperial") == pytest.approx(77.0)

    def test_c_to_metric_passthrough(self):
        assert _c_to_display(25.0, "metric") == pytest.approx(25.0)

    def test_fmt_temp_rounds_and_suffixes(self):
        assert _fmt_temp(81.6, "imperial") == "82°F"
        assert _fmt_temp(25.4, "metric") == "25°C"
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_widgets/test_pool.py -v`
Expected: FAIL with `ModuleNotFoundError: led_ticker.widgets.pool`.

- [ ] **Step 3: Write the helpers**

Create `src/led_ticker/widgets/pool.py`:

```python
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
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/test_widgets/test_pool.py -v`
Expected: PASS (all helper tests green).

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/widgets/pool.py tests/test_widgets/test_pool.py
git commit -m "feat: add pool widget display helpers (zone color, trend, units)"
```

---

## Task 3: Flux query strings + scalar CSV parsing

**Files:**
- Modify: `src/led_ticker/widgets/pool.py`
- Modify: `tests/test_widgets/test_pool.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_widgets/test_pool.py`:

```python
from led_ticker.widgets.pool import _parse_scalar_csv, _build_flux


SAMPLE_CSV = (
    "#datatype,string,long,dateTime:RFC3339,double,string,string\r\n"
    ",result,table,_time,_value,_field,_measurement\r\n"
    ",_result,0,2026-05-27T15:00:00Z,27.5,temperature_C,mqtt_consumer\r\n"
    "\r\n"
)

EMPTY_CSV = "\r\n"


class TestParseScalarCsv:
    def test_parses_value_and_time(self):
        value, ts = _parse_scalar_csv(SAMPLE_CSV)
        assert value == pytest.approx(27.5)
        assert ts == "2026-05-27T15:00:00Z"

    def test_empty_returns_none(self):
        assert _parse_scalar_csv(EMPTY_CSV) == (None, None)


class TestBuildFlux:
    def test_includes_bucket_field_and_filter(self):
        flux = _build_flux(
            bucket="pool_temps", sensor_id="123",
            range_start="-7d", agg="mean",
        )
        assert 'from(bucket: "pool_temps")' in flux
        assert 'r._field == "temperature_C"' in flux
        assert 'r.id == "123"' in flux
        assert "|> mean()" in flux
        assert "range(start: -7d)" in flux

    def test_omits_sensor_filter_when_none(self):
        flux = _build_flux(
            bucket="pool_temps", sensor_id=None,
            range_start="-1h", agg="last",
        )
        assert "r.id ==" not in flux
        assert "|> last()" in flux
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_widgets/test_pool.py::TestParseScalarCsv tests/test_widgets/test_pool.py::TestBuildFlux -v`
Expected: FAIL with `ImportError` for `_parse_scalar_csv` / `_build_flux`.

- [ ] **Step 3: Implement parser + query builder**

Add to `src/led_ticker/widgets/pool.py` (add `import csv` and `import io` at top):

```python
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
        record = dict(zip(header, row))
        raw = record.get("_value", "")
        if raw == "":
            return None, None
        return float(raw), record.get("_time") or None
    return None, None
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/test_widgets/test_pool.py::TestParseScalarCsv tests/test_widgets/test_pool.py::TestBuildFlux -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/widgets/pool.py tests/test_widgets/test_pool.py
git commit -m "feat: add pool widget Flux query builder + CSV scalar parser"
```

---

## Task 4: `PoolMonitor` widget (fetch, build screens, staleness)

**Files:**
- Modify: `src/led_ticker/widgets/pool.py`
- Modify: `tests/test_widgets/test_pool.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_widgets/test_pool.py`:

```python
from led_ticker.widget import Widget
from led_ticker.widgets.message import SegmentMessage
from led_ticker.widgets.pool import PoolMonitor, DIM


def _monitor(**kw):
    """PoolMonitor without network; env + session mocked."""
    return PoolMonitor(
        session=mock.Mock(),
        influxdb_url="http://influx:8086",
        influxdb_org="pool",
        influxdb_bucket="pool_temps",
        influxdb_token="tok",
        **kw,
    )


class TestBuildScreens:
    def test_title_and_three_stories(self):
        m = _monitor(title="POOL TEMPS", units="imperial")
        m._build_screens(
            current_c=27.78, current_age_s=10.0, past_c=27.2,
            today_min_c=25.6, today_max_c=28.9,
            d7_mean_c=26.7, d7_min_c=24.4, d7_max_c=28.9,
            season_min_c=21.7, season_max_c=31.1,
        )
        assert m.feed_title.segments[0][0] == "POOL TEMPS"
        assert len(m.feed_stories) == 3
        for s in m.feed_stories:
            assert isinstance(s, SegmentMessage)

    def test_today_screen_has_temp_and_arrow(self):
        m = _monitor(units="imperial")
        m._build_screens(
            current_c=27.78, current_age_s=10.0, past_c=27.2,
            today_min_c=25.6, today_max_c=28.9,
            d7_mean_c=26.7, d7_min_c=24.4, d7_max_c=28.9,
            season_min_c=21.7, season_max_c=31.1,
        )
        today = m.feed_stories[0]
        texts = "".join(t for t, _ in today.segments)
        assert "82°F" in texts   # 27.78C -> 82F
        assert "^" in texts       # rising (27.78 > 27.2 by >0.5F)

    def test_stale_dims_temp(self):
        m = _monitor(units="imperial", stale_after=900)
        m._build_screens(
            current_c=27.78, current_age_s=1800.0, past_c=27.2,
            today_min_c=25.6, today_max_c=28.9,
            d7_mean_c=26.7, d7_min_c=24.4, d7_max_c=28.9,
            season_min_c=21.7, season_max_c=31.1,
        )
        today = m.feed_stories[0]
        temp_color = today.segments[0][1]
        assert temp_color is DIM

    def test_season_label_spelled_out(self):
        m = _monitor(units="imperial")
        m._build_screens(
            current_c=27.78, current_age_s=10.0, past_c=27.2,
            today_min_c=25.6, today_max_c=28.9,
            d7_mean_c=26.7, d7_min_c=24.4, d7_max_c=28.9,
            season_min_c=21.7, season_max_c=31.1,
        )
        season = m.feed_stories[2]
        texts = "".join(t for t, _ in season.segments)
        assert "Season" in texts


class TestConformance:
    def test_stories_are_widgets(self):
        m = _monitor()
        m._build_screens(
            current_c=27.78, current_age_s=10.0, past_c=None,
            today_min_c=25.6, today_max_c=28.9,
            d7_mean_c=26.7, d7_min_c=24.4, d7_max_c=28.9,
            season_min_c=21.7, season_max_c=31.1,
        )
        assert isinstance(m.feed_title, Widget)
        assert all(isinstance(s, Widget) for s in m.feed_stories)


class TestMissingToken:
    @pytest.mark.asyncio
    async def test_start_raises_without_token(self, monkeypatch):
        monkeypatch.delenv("INFLUXDB_TOKEN", raising=False)
        with pytest.raises(ValueError, match="INFLUXDB_TOKEN"):
            await PoolMonitor.start(session=mock.Mock())
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_widgets/test_pool.py::TestBuildScreens -v`
Expected: FAIL — `PoolMonitor` not defined.

- [ ] **Step 3: Implement the widget**

Append to `src/led_ticker/widgets/pool.py` (add these imports at top: `import asyncio`, `import logging`, `import os`, `from datetime import datetime, timezone`, `from typing import Any, Self`, `import aiohttp`, `import attrs`, `from led_ticker.colors import RGB_WHITE`, `from led_ticker.widget import run_monitor_loop`, `from led_ticker.widgets import register`, `from led_ticker.widgets.message import SegmentMessage`):

```python
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
    influxdb_token: str = attrs.field(
        factory=lambda: os.getenv("INFLUXDB_TOKEN", "")
    )
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
            raise ValueError(
                "INFLUXDB_TOKEN not set. Add it to your .env file."
            )
        widget._set_placeholder()
        try:
            await widget.update()
        except Exception:
            logger.exception("Pool initial update failed; showing placeholder")
        asyncio.create_task(run_monitor_loop(widget, update_interval))
        return widget

    async def _query(self, range_start: str, agg: str) -> tuple[float | None, str | None]:
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
            text = await resp.text()
        return _parse_scalar_csv(text)

    async def update(self) -> None:
        year_start = f"{datetime.now(timezone.utc).year}-01-01T00:00:00Z"
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
            current_c=current_c, current_age_s=age, past_c=past_c,
            today_min_c=today_min_c, today_max_c=today_max_c,
            d7_mean_c=d7_mean_c, d7_min_c=d7_min_c, d7_max_c=d7_max_c,
            season_min_c=season_min_c, season_max_c=season_max_c,
        )

    @staticmethod
    def _age_seconds(ts: str | None) -> float:
        if not ts:
            return float("inf")
        try:
            t = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            return float("inf")
        return (datetime.now(timezone.utc) - t).total_seconds()

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
            SegmentMessage([("POOL ", DIM), ("--", DIM)], center=True)
        ]
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/test_widgets/test_pool.py -v`
Expected: PASS (all pool tests green). If `pytest-asyncio` complains about the async test, confirm the repo's existing async tests pattern (e.g. `test_weather.py`) and match its marker/config.

- [ ] **Step 5: Type-check**

Run: `pyright src/led_ticker/widgets/pool.py`
Expected: 0 errors.

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/widgets/pool.py tests/test_widgets/test_pool.py
git commit -m "feat: add PoolMonitor widget with cycling temp screens"
```

---

## Task 5: Register the monitor as a container in the run loop

**Files:**
- Modify: `src/led_ticker/app/run.py` (import line ~32-34; isinstance ~line 96)
- Test: `tests/test_widgets/test_pool.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_widgets/test_pool.py`:

```python
class TestRunIntegration:
    def test_pool_is_recognized_container(self):
        # run.py expands these container types' feed_stories into the playlist.
        import inspect
        from led_ticker.app import run
        src = inspect.getsource(run)
        assert "PoolMonitor" in src
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_widgets/test_pool.py::TestRunIntegration -v`
Expected: FAIL — `PoolMonitor` not referenced in `run.py`.

- [ ] **Step 3: Wire it in**

In `src/led_ticker/app/run.py`, add after the other monitor imports (~line 34):

```python
from led_ticker.widgets.pool import PoolMonitor
```

Change the container check (~line 96) from:

```python
                        RSSFeedMonitor | MLBScoreMonitor | MLBStandingsMonitor,
```

to:

```python
                        RSSFeedMonitor | MLBScoreMonitor | MLBStandingsMonitor | PoolMonitor,
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/test_widgets/test_pool.py::TestRunIntegration -v`
Expected: PASS.

- [ ] **Step 5: Full suite + type check**

Run: `pytest tests/ -q && pyright src/led_ticker/app/run.py`
Expected: PASS, 0 type errors.

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/app/run.py tests/test_widgets/test_pool.py
git commit -m "feat: expand PoolMonitor feed stories in the run loop"
```

---

## Task 6: Config example + documentation

**Files:**
- Modify: `config/config.example.toml`
- Create: `docs/site/src/content/docs/widgets/pool.mdx`
- Modify: `docs/site/src/content/docs/widgets/index.mdx`
- Modify: `docs/site/astro.config.mjs`

- [ ] **Step 1: Add a config example**

In `config/config.example.toml`, add near the other live-data widgets:

```toml
# Pool water temperature from the pool_monitor InfluxDB server.
# Requires INFLUXDB_URL / INFLUXDB_TOKEN / INFLUXDB_ORG / INFLUXDB_BUCKET in .env.
[[playlist.section.widget]]
type = "pool"
title = "POOL TEMPS"
# sensor_id = "12345"   # optional; omit to use the only/first sensor
units = "imperial"
update_interval = 300
stale_after = 900
```

- [ ] **Step 2: Validate the example config loads**

Run: `python -m led_ticker.validate config/config.example.toml` (or the project's existing config-validation entry point — check `Makefile`/`README` for the exact command).
Expected: validates without error (token may be unset; validation does not call `.start()`, so it should pass).

- [ ] **Step 3: Write the docs page**

Create `docs/site/src/content/docs/widgets/pool.mdx`, modeled on `weather.mdx`:

```mdx
---
title: pool widget
description: Live pool water temperature from the pool_monitor InfluxDB server. Cycles title, today, 7-day, and season screens.
---

import DemoGif from "../../../components/DemoGif.astro";
import TomlExample from "../../../components/TomlExample.astro";
import OptionsTable from "../../../components/OptionsTable.astro";
import RelatedPages from "../../../components/RelatedPages.astro";

The `pool` widget reads pool water temperature directly from the [pool_monitor](https://github.com/jamesawesome/pool_monitor) InfluxDB v2 server and cycles through four glanceable screens: a title, today's reading (current temp, trend arrow, today's high/low), a 7-day summary (mean + high/low), and the season high/low. The current temperature is color-coded by zone (blue cool, green normal, amber warm, red hot). It polls in the background with retry, so the display keeps running if InfluxDB is briefly unreachable.

<DemoGif
  src="/demos-long/widget-pool.gif"
  caption="Pool widget cycling through today, 7-day, and season screens in their real deployed colors."
/>

<TomlExample
  title="Minimal example"
  code={`[[playlist.section.widget]]
type = "pool"
title = "POOL TEMPS"
units = "imperial"`}
/>

The sign needs network access to the InfluxDB server. Set these in your `.env` file:

- `INFLUXDB_URL` — e.g. `http://influxdb:8086`
- `INFLUXDB_TOKEN` — InfluxDB v2 API token (**required**)
- `INFLUXDB_ORG` — e.g. `pool`
- `INFLUXDB_BUCKET` — e.g. `pool_temps`

## Options

<OptionsTable
  rows={[
    ["title", "string", '"POOL TEMPS"', "Text shown on the title screen."],
    ["sensor_id", "string", "(unset)", "InfluxDB `id` tag to filter on. Omit to use the only/first sensor."],
    ["units", "string", '"imperial"', '"imperial" (°F) or "metric" (°C).'],
    ["update_interval", "int", "300", "Seconds between InfluxDB polls."],
    ["stale_after", "int", "900", "Seconds before a reading is shown dimmed as stale."],
    ["influxdb_url", "string", "$INFLUXDB_URL", "Override the InfluxDB base URL."],
    ["influxdb_org", "string", "$INFLUXDB_ORG", "Override the InfluxDB org."],
    ["influxdb_bucket", "string", "$INFLUXDB_BUCKET", "Override the InfluxDB bucket."],
  ]}
/>

<RelatedPages
  pages={[
    ["weather widget", "/widgets/weather/"],
    ["All widgets", "/widgets/"],
  ]}
/>
```

> Before writing, open `weather.mdx` and `mlb_standings.mdx` to confirm the exact prop shapes for `OptionsTable` and `RelatedPages` (column/array vs. object form) and match them. Adjust the JSX above to the real component API.

- [ ] **Step 4: Add the index row + live-data entry**

In `docs/site/src/content/docs/widgets/index.mdx`, add a table row alongside the others:

```md
| [`pool`](/widgets/pool/)                   | pool_monitor InfluxDB       | water temp (today / 7-day / season)        |
```

and add `pool` to the "Live data (background fetch)" list line.

- [ ] **Step 5: Add the sidebar nav entry**

In `docs/site/astro.config.mjs`, in the widgets sidebar group, add:

```js
            { label: "pool", link: "/widgets/pool/" },
```

- [ ] **Step 6: Build the docs site**

Run: `cd docs/site && npm install && npm run build` (or the project's `make docs` target if present).
Expected: build succeeds; `/widgets/pool/` is generated; astro check passes.

- [ ] **Step 7: Commit**

```bash
git add config/config.example.toml docs/site/src/content/docs/widgets/pool.mdx docs/site/src/content/docs/widgets/index.mdx docs/site/astro.config.mjs
git commit -m "docs: document the pool widget + config example"
```

---

## Task 7: Demo gif

**Files:**
- Create: `docs/site/demos-long/widget-pool.gif`
- (the `<DemoGif src>` in `pool.mdx` already points here)

- [ ] **Step 1: Decide the data source for the render**

The widget needs real values at render time. Choose:
- (a) Render on a machine that can reach the live InfluxDB, with `INFLUXDB_*` set in `.env`; or
- (b) If `render-demo` cannot reach InfluxDB, point `influxdb_url` at a reachable instance seeded with representative data.

Confirm which the `render-demo` tooling supports before rendering. Record the choice in the commit message.

- [ ] **Step 2: Use the making-a-gif skill**

Invoke the `making-a-gif` skill to get the correct `make render-demo` invocation and `--duration` for a config containing only the `pool` widget. The duration must be long enough to show the full cycle (title → today → 7-day → season).

- [ ] **Step 3: Render and place the gif**

Run the `make render-demo` command the skill produced; output the gif to `docs/site/demos-long/widget-pool.gif`.
Expected: a gif that visibly cycles all four screens with correct zone colors.

- [ ] **Step 4: Verify it renders in the docs**

Run: `cd docs/site && npm run build` and confirm `/widgets/pool/` shows the gif (no broken-image / missing-asset warning).

- [ ] **Step 5: Commit**

```bash
git add docs/site/demos-long/widget-pool.gif
git commit -m "docs: add pool widget demo gif"
```

---

## Final verification

- [ ] **Full test suite**

Run: `pytest tests/ -q`
Expected: PASS (baseline count + the new pool tests).

- [ ] **Lint + type check**

Run: `ruff check src/led_ticker/widgets/pool.py && pyright src/led_ticker/widgets/pool.py src/led_ticker/app/run.py`
Expected: clean.

- [ ] **Manual smoke (optional, needs InfluxDB)**

With `INFLUXDB_*` set in `.env`, run the app against a config containing the `pool` widget and confirm the cycle renders and colors match the spec.

---

## Notes for the implementer

- **Branch:** work stays on `worktree-pool-monitor-widget`. Do NOT switch to `main`.
- **Async test marker:** match `test_weather.py`'s async-test setup exactly (the repo configures `pytest-asyncio`); don't introduce a different marker style.
- **No new dependencies:** everything uses stdlib `csv`/`io` + the already-injected `aiohttp` session.
- **Glyph fallback:** Task 2 uses ASCII `^`/`v`/`-`. If you confirm the BDF font has `▲`/`▼`, you may switch `ascii_only` per-mode, but ASCII is the safe default and what the tests assert.
