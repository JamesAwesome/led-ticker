import pytest

from led_ticker.colors import BLUE, GREEN, ORANGE, RED
from led_ticker.widgets.pool import (
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
        assert _fmt_temp(81.6, "imperial") == "82°F"
        assert _fmt_temp(25.4, "metric") == "25°C"


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
