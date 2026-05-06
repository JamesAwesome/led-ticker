"""Tests for weather icons."""

from led_ticker.widgets.weather_icons import _match_condition


class TestMatchCondition:
    def test_sunny(self):
        assert _match_condition("Sunny") == "sun"

    def test_clear(self):
        assert _match_condition("Clear") == "sun"

    def test_partly_cloudy(self):
        assert _match_condition("Partly cloudy") == "partly_cloudy"

    def test_cloudy(self):
        assert _match_condition("Cloudy") == "cloud"

    def test_overcast(self):
        assert _match_condition("Overcast") == "cloud"

    def test_light_rain(self):
        assert _match_condition("Light rain") == "rain"

    def test_heavy_rain(self):
        assert _match_condition("Heavy rain") == "rain"

    def test_moderate_rain_shower(self):
        assert _match_condition("Moderate or heavy rain shower") == "rain"

    def test_drizzle(self):
        assert _match_condition("Light drizzle") == "rain"

    def test_light_snow(self):
        assert _match_condition("Light snow") == "snow"

    def test_blizzard(self):
        assert _match_condition("Blizzard") == "snow"

    def test_ice_pellets(self):
        assert _match_condition("Ice pellets") == "snow"

    def test_sleet(self):
        assert _match_condition("Light sleet") == "snow"

    def test_thunder(self):
        assert _match_condition("Moderate or heavy rain with thunder") == "thunder"

    def test_thundery_outbreaks(self):
        assert _match_condition("Thundery outbreaks possible") == "thunder"

    def test_fog(self):
        assert _match_condition("Fog") == "fog"

    def test_mist(self):
        assert _match_condition("Mist") == "fog"

    def test_freezing_fog(self):
        assert _match_condition("Freezing fog") == "fog"

    def test_unknown_defaults_to_sun(self):
        assert _match_condition("Something weird") == "sun"
