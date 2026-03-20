"""Tests for weather icons."""

from rgbmatrix import _StubCanvas

from led_ticker.widgets.weather_icons import (
    CLOUD,
    FOG,
    ICON_WIDTH,
    PARTLY_CLOUDY,
    RAIN,
    SNOW,
    SUN,
    THUNDER,
    _match_condition,
    draw_weather_icon,
)


class TestMatchCondition:
    def test_sunny(self):
        assert _match_condition("Sunny") is SUN

    def test_clear(self):
        assert _match_condition("Clear") is SUN

    def test_partly_cloudy(self):
        assert _match_condition("Partly cloudy") is PARTLY_CLOUDY

    def test_cloudy(self):
        assert _match_condition("Cloudy") is CLOUD

    def test_overcast(self):
        assert _match_condition("Overcast") is CLOUD

    def test_light_rain(self):
        assert _match_condition("Light rain") is RAIN

    def test_heavy_rain(self):
        assert _match_condition("Heavy rain") is RAIN

    def test_moderate_rain_shower(self):
        assert _match_condition("Moderate or heavy rain shower") is RAIN

    def test_drizzle(self):
        assert _match_condition("Light drizzle") is RAIN

    def test_light_snow(self):
        assert _match_condition("Light snow") is SNOW

    def test_blizzard(self):
        assert _match_condition("Blizzard") is SNOW

    def test_ice_pellets(self):
        assert _match_condition("Ice pellets") is SNOW

    def test_sleet(self):
        assert _match_condition("Light sleet") is SNOW

    def test_thunder(self):
        assert _match_condition("Moderate or heavy rain with thunder") is THUNDER

    def test_thundery_outbreaks(self):
        assert _match_condition("Thundery outbreaks possible") is THUNDER

    def test_fog(self):
        assert _match_condition("Fog") is FOG

    def test_mist(self):
        assert _match_condition("Mist") is FOG

    def test_freezing_fog(self):
        assert _match_condition("Freezing fog") is FOG

    def test_unknown_defaults_to_sun(self):
        assert _match_condition("Something weird") is SUN


class TestDrawWeatherIcon:
    def test_draws_pixels_to_canvas(self):
        canvas = _StubCanvas(width=20, height=16)
        end_x = draw_weather_icon(canvas, "Sunny", x=0)
        assert end_x == ICON_WIDTH + 2  # icon + padding
        assert canvas.count_nonzero() > 0

    def test_returns_correct_position(self):
        canvas = _StubCanvas(width=40, height=16)
        end_x = draw_weather_icon(canvas, "Rain", x=5)
        assert end_x == 5 + ICON_WIDTH + 2

    def test_icon_stays_in_bounds(self):
        canvas = _StubCanvas(width=20, height=16)
        draw_weather_icon(canvas, "Sunny", x=0, y_offset=4)
        # All pixels should be within canvas bounds
        for (x, y), _color in canvas._pixels.items():
            assert 0 <= x < 20
            assert 0 <= y < 16

    def test_all_icons_have_pixels(self):
        """Every icon should draw at least one pixel."""
        for condition in [
            "Sunny", "Partly cloudy", "Cloudy", "Rain",
            "Snow", "Thundery outbreaks possible", "Fog",
        ]:
            canvas = _StubCanvas(width=20, height=16)
            draw_weather_icon(canvas, condition, x=0)
            assert canvas.count_nonzero() > 0, (
                f"Icon for '{condition}' drew no pixels"
            )
