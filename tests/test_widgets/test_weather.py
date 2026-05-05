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


def test_weather_bg_color_default_is_none(monkeypatch):
    monkeypatch.setenv("WEATHERAPI_KEY", "test-key")
    from led_ticker.widgets.weather import WeatherWidget

    w = WeatherWidget(session=mock.Mock(), location="London", message="London")
    assert w.bg_color is None


def test_weather_bg_color_accepts_color(monkeypatch):
    monkeypatch.setenv("WEATHERAPI_KEY", "test-key")
    from rgbmatrix.graphics import Color

    from led_ticker.widgets.weather import WeatherWidget

    w = WeatherWidget(
        session=mock.Mock(),
        location="London",
        message="London",
        bg_color=Color(5, 10, 15),
    )
    assert w.bg_color.red == 5


class TestWeatherColorProvider:
    """WeatherWidget materializes Color from font_color (provider) and
    font_color_temp (provider). Both wrap Color into _ConstantColor in
    post_init so draw is uniform."""

    def test_font_color_wrapped_to_constant_provider_in_post_init(self):
        from rgbmatrix.graphics import Color

        from led_ticker.color_providers import _ConstantColor
        from led_ticker.widgets.weather import WeatherWidget

        w = WeatherWidget(
            session=mock.Mock(),
            message="NYC",
            location="NYC",
            font_color=Color(255, 0, 0),
        )
        assert isinstance(w.font_color, _ConstantColor)

    def test_font_color_temp_wrapped_to_constant_provider(self):
        from rgbmatrix.graphics import Color

        from led_ticker.color_providers import _ConstantColor
        from led_ticker.widgets.weather import WeatherWidget

        w = WeatherWidget(
            session=mock.Mock(),
            message="NYC",
            location="NYC",
            font_color_temp=Color(0, 255, 0),
        )
        assert isinstance(w.font_color_temp, _ConstantColor)

    def test_provider_passed_through_unchanged(self):
        from led_ticker.color_providers import Rainbow
        from led_ticker.widgets.weather import WeatherWidget

        provider = Rainbow()
        w = WeatherWidget(
            session=mock.Mock(), message="NYC", location="NYC", font_color=provider
        )
        assert w.font_color is provider

    def test_advance_frame_increments_count(self):
        from led_ticker.widgets.weather import WeatherWidget

        w = WeatherWidget(session=mock.Mock(), message="NYC", location="NYC")
        assert w._frame_count == 0
        w.advance_frame()
        assert w._frame_count == 1
