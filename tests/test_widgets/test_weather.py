"""Tests for led_ticker.widgets.weather."""

import unittest.mock as mock

import pytest

from led_ticker.widget import Widget
from led_ticker.widgets.weather import WeatherWidget


@pytest.fixture(autouse=True)
def _set_weather_api_key(monkeypatch):
    monkeypatch.setenv("WEATHERAPI_KEY", "test-key-12345")


@pytest.fixture
def weather_widget():
    """A WeatherWidget with pre-set data (no network needed)."""
    w = WeatherWidget(
        session=mock.Mock(),
        location="40.7,-74.0",
        message="NYC",
    )
    w.current_temp = 72
    w.weather = "Clear"
    return w


class TestWeatherWidget:
    def test_conforms_to_widget_protocol(self, weather_widget):
        assert isinstance(weather_widget, Widget)

    def test_post_init_imperial(self):
        w = WeatherWidget(
            session=mock.Mock(),
            location="New York",
            message="Test",
            units="imperial",
        )
        assert w.unit_symbol == "F"

    def test_post_init_metric(self):
        w = WeatherWidget(
            session=mock.Mock(),
            location="London",
            message="Test",
            units="metric",
        )
        assert w.unit_symbol == "C"

    def test_location_dict_converted_to_string(self):
        """TOML gives location as dict; __attrs_post_init__ converts it."""
        w = WeatherWidget(
            session=mock.Mock(),
            location={"lat": 40.7, "lon": -74.0},
            message="NYC",
        )
        assert w.location == "40.7,-74.0"

    def test_location_string_passthrough(self):
        w = WeatherWidget(
            session=mock.Mock(),
            location="New York",
            message="NYC",
        )
        assert w.location == "New York"

    def test_draw_returns_canvas(self, canvas, weather_widget):
        result_canvas, cursor_pos = weather_widget.draw(canvas)
        assert result_canvas is canvas
        assert cursor_pos > 0

    def test_draw_centered(self, canvas, weather_widget):
        _, cursor_pos = weather_widget.draw(canvas)
        assert cursor_pos == 160

    def test_draw_uncentered(self, canvas):
        w = WeatherWidget(
            session=mock.Mock(),
            location="NYC",
            message="NYC",
            center=False,
        )
        w.current_temp = 72
        w.weather = "Clear"
        _, cursor_pos = w.draw(canvas)
        assert cursor_pos > 0
        assert cursor_pos < 160
