import unittest.mock as mock

import pytest

from led_ticker.colors import BLUE, GREEN, ORANGE, RED
from led_ticker.widget import Widget
from led_ticker.widgets.message import SegmentMessage
from led_ticker.widgets.pool import (
    DIM,
    PoolMonitor,
    _build_flux,
    _c_to_display,
    _fmt_temp,
    _parse_scalar_csv,
    _trend_arrow,
    _zone_color,
)


class TestZoneColor:
    @pytest.mark.parametrize(
        "f,expected",
        [
            (60.0, BLUE),
            (69.9, BLUE),
            (70.0, GREEN),
            (79.9, GREEN),
            (80.0, ORANGE),
            (89.9, ORANGE),
            (90.0, RED),
            (95.0, RED),
        ],
    )
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
        # No degree symbol — hires Inter at small font_size drops U+00B0
        # to '?'. Consistent with the weather widget's bare 'F'/'C'.
        assert _fmt_temp(81.6, "imperial") == "82F"
        assert _fmt_temp(25.4, "metric") == "25C"


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
            bucket="pool_temps",
            sensor_id="123",
            range_start="-7d",
            agg="mean",
        )
        assert 'from(bucket: "pool_temps")' in flux
        assert 'r._field == "temperature_C"' in flux
        assert 'r.id == "123"' in flux
        assert "|> mean()" in flux
        assert "range(start: -7d)" in flux

    def test_omits_sensor_filter_when_none(self):
        flux = _build_flux(
            bucket="pool_temps",
            sensor_id=None,
            range_start="-1h",
            agg="last",
        )
        assert "r.id ==" not in flux
        assert "|> last()" in flux


# ---------------------------------------------------------------------------
# PoolMonitor widget tests
# ---------------------------------------------------------------------------


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
            current_c=27.78,
            current_age_s=10.0,
            past_c=27.2,
            today_min_c=25.6,
            today_max_c=28.9,
            d7_mean_c=26.7,
            d7_min_c=24.4,
            d7_max_c=28.9,
            season_min_c=21.7,
            season_max_c=31.1,
        )
        assert m.feed_title.segments[0][0] == "POOL TEMPS"
        assert len(m.feed_stories) == 3
        for s in m.feed_stories:
            assert isinstance(s, SegmentMessage)

    def test_widget_font_threads_into_feed_title_and_stories(self):
        """Custom `font` configured on the widget must reach every
        SegmentMessage (title + 3 stories + placeholder). Without this
        wiring, bigsign configs that specify `font = "Inter-Regular"`
        would silently fall back to FONT_DEFAULT (BDF), producing the
        chunky-text-misplaced bug fixed alongside config.pool_longboi.toml.
        """
        sentinel_font = object()  # Font is duck-typed downstream
        m = _monitor(font=sentinel_font)
        m._build_screens(
            current_c=27.78,
            current_age_s=10.0,
            past_c=27.2,
            today_min_c=25.6,
            today_max_c=28.9,
            d7_mean_c=26.7,
            d7_min_c=24.4,
            d7_max_c=28.9,
            season_min_c=21.7,
            season_max_c=31.1,
        )
        assert m.feed_title.font is sentinel_font
        for s in m.feed_stories:
            assert s.font is sentinel_font

    def test_widget_font_threads_into_placeholder(self):
        """Placeholder screens (shown on initial fetch / failure) must
        also carry the configured font."""
        sentinel_font = object()
        m = _monitor(font=sentinel_font)
        m._set_placeholder()
        assert m.feed_title.font is sentinel_font
        assert m.feed_stories[0].font is sentinel_font

    def test_today_screen_has_temp_and_arrow(self):
        m = _monitor(units="imperial")
        m._build_screens(
            current_c=27.78,
            current_age_s=10.0,
            past_c=27.2,
            today_min_c=25.6,
            today_max_c=28.9,
            d7_mean_c=26.7,
            d7_min_c=24.4,
            d7_max_c=28.9,
            season_min_c=21.7,
            season_max_c=31.1,
        )
        today = m.feed_stories[0]
        texts = "".join(t for t, _ in today.segments)
        assert "82F" in texts  # 27.78C -> 82F (no degree symbol — see _fmt_temp)
        assert "^" in texts  # rising (27.78 > 27.2 by >0.5F)

    def test_stale_dims_temp(self):
        m = _monitor(units="imperial", stale_after=900)
        m._build_screens(
            current_c=27.78,
            current_age_s=1800.0,
            past_c=27.2,
            today_min_c=25.6,
            today_max_c=28.9,
            d7_mean_c=26.7,
            d7_min_c=24.4,
            d7_max_c=28.9,
            season_min_c=21.7,
            season_max_c=31.1,
        )
        today = m.feed_stories[0]
        temp_color = today.segments[0][1]
        assert temp_color is DIM

    def test_season_label_spelled_out(self):
        m = _monitor(units="imperial")
        m._build_screens(
            current_c=27.78,
            current_age_s=10.0,
            past_c=27.2,
            today_min_c=25.6,
            today_max_c=28.9,
            d7_mean_c=26.7,
            d7_min_c=24.4,
            d7_max_c=28.9,
            season_min_c=21.7,
            season_max_c=31.1,
        )
        season = m.feed_stories[2]
        texts = "".join(t for t, _ in season.segments)
        assert "Season" in texts

    def test_missing_values_render_dashes(self):
        m = _monitor(units="imperial")
        m._build_screens(
            current_c=27.78,
            current_age_s=10.0,
            past_c=27.2,
            today_min_c=None,
            today_max_c=None,
            d7_mean_c=26.7,
            d7_min_c=24.4,
            d7_max_c=28.9,
            season_min_c=21.7,
            season_max_c=31.1,
        )
        today_texts = "".join(t for t, _ in m.feed_stories[0].segments)
        assert "--" in today_texts

    def test_metric_units_pick_correct_zone(self):
        from led_ticker.colors import ORANGE

        m = _monitor(units="metric")
        # 28°C = 82.4°F — should be the ORANGE (warm) zone.
        m._build_screens(
            current_c=28.0,
            current_age_s=10.0,
            past_c=27.5,
            today_min_c=25.0,
            today_max_c=29.0,
            d7_mean_c=27.0,
            d7_min_c=24.0,
            d7_max_c=29.0,
            season_min_c=21.0,
            season_max_c=31.0,
        )
        today = m.feed_stories[0]
        # First segment is the temp text in the zone color
        assert today.segments[0][1] is ORANGE
        assert "28C" in today.segments[0][0]


class TestConformance:
    def test_stories_are_widgets(self):
        m = _monitor()
        m._build_screens(
            current_c=27.78,
            current_age_s=10.0,
            past_c=None,
            today_min_c=25.6,
            today_max_c=28.9,
            d7_mean_c=26.7,
            d7_min_c=24.4,
            d7_max_c=28.9,
            season_min_c=21.7,
            season_max_c=31.1,
        )
        assert isinstance(m.feed_title, Widget)
        assert all(isinstance(s, Widget) for s in m.feed_stories)


class TestMissingToken:
    async def test_start_raises_without_token(self, monkeypatch):
        monkeypatch.delenv("INFLUXDB_TOKEN", raising=False)
        with pytest.raises(ValueError, match="INFLUXDB_TOKEN"):
            await PoolMonitor.start(session=mock.Mock())


class TestSensorIdValidation:
    async def test_invalid_sensor_id_rejected(self, monkeypatch):
        monkeypatch.setenv("INFLUXDB_TOKEN", "tok")
        with pytest.raises(ValueError, match="Invalid sensor_id"):
            await PoolMonitor.start(session=mock.Mock(), sensor_id='abc"def')


# Container Protocol conformance for PoolMonitor is asserted in
# tests/test_widget_protocol.py::test_container_protocol_recognizes_pool_monitor
# alongside the MLB / RSS / standings conformance tests. The 2026-05-28
# Container refactor removed the per-type isinstance tuple from app/run.py,
# so an older test that searched the run.py source for "PoolMonitor" no
# longer applies — structural Protocol conformance is the new contract.
