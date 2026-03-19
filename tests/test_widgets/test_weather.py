"""Tests for led_ticker.widgets.weather."""

import unittest.mock as mock

import pytest

from led_ticker.widget import Widget
from led_ticker.widgets.weather import LocationData, WeatherWidget


@pytest.fixture
def canvas():
    c = mock.Mock()
    c.width = 160
    return c


@pytest.fixture
def weather_widget():
    """A WeatherWidget with pre-set data (no network needed)."""
    w = WeatherWidget(
        session=mock.Mock(),
        location=LocationData(lat=40.7, lon=-74.0),
        message="NYC",
    )
    # Set the data that update() would normally fetch
    w.current_temp = 72
    w.weather = "Clear"
    return w


class TestWeatherWidget:
    def test_conforms_to_widget_protocol(self, weather_widget):
        assert isinstance(weather_widget, Widget)

    def test_post_init_imperial(self):
        w = WeatherWidget(
            session=mock.Mock(),
            location=LocationData(lat=0, lon=0),
            message="Test",
            units="imperial",
        )
        assert w.unit_symbol == "F"

    def test_post_init_metric(self):
        w = WeatherWidget(
            session=mock.Mock(),
            location=LocationData(lat=0, lon=0),
            message="Test",
            units="metric",
        )
        assert w.unit_symbol == "C"

    def test_draw_returns_canvas(self, canvas, weather_widget):
        result_canvas, cursor_pos = weather_widget.draw(canvas)
        assert result_canvas is canvas
        assert cursor_pos > 0

    def test_draw_centered(self, canvas, weather_widget):
        _, cursor_pos = weather_widget.draw(canvas)
        # "NYC: Clear 72F" centered on 160px canvas
        assert cursor_pos == 160  # fills canvas when centered

    def test_draw_uncentered(self, canvas):
        w = WeatherWidget(
            session=mock.Mock(),
            location=LocationData(lat=0, lon=0),
            message="NYC",
            center=False,
        )
        w.current_temp = 72
        w.weather = "Clear"
        _, cursor_pos = w.draw(canvas)
        # Text width + padding, starting from 0
        assert cursor_pos > 0
        assert cursor_pos < 160
