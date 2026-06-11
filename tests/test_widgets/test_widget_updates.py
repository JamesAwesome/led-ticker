"""Tests for async widget update() and start() methods."""

import unittest.mock as mock

import pytest

from led_ticker.widgets.rss_feed import RSSFeedMonitor
from led_ticker.widgets.weather import WeatherWidget


def _make_session(json_response=None, text_response=None):
    """Create a mock aiohttp session."""
    session = mock.MagicMock()
    response = mock.AsyncMock()
    if json_response is not None:
        response.json.return_value = json_response
    if text_response is not None:
        response.text.return_value = text_response
    ctx = mock.AsyncMock()
    ctx.__aenter__.return_value = response
    session.get.return_value = ctx
    return session


# --- Weather ---


@pytest.fixture(autouse=True)
def _set_weather_api_key(monkeypatch):
    monkeypatch.setenv("WEATHERAPI_KEY", "test-key-12345")


class TestWeatherUpdate:
    async def test_update_parses_weather(self):
        session = _make_session(
            json_response={
                "current": {
                    "temp_f": 72,
                    "temp_c": 22,
                    "condition": {"text": "Clear"},
                }
            }
        )
        w = WeatherWidget(
            session=session,
            location="40.7,-74.0",
            text="NYC",
        )
        await w.update()
        assert w.current_temp == 72
        assert w.weather == "Clear"

    async def test_update_metric(self):
        session = _make_session(
            json_response={
                "current": {
                    "temp_f": 72,
                    "temp_c": 22,
                    "condition": {"text": "Rain"},
                }
            }
        )
        w = WeatherWidget(
            session=session,
            location="London",
            text="LDN",
            units="metric",
        )
        await w.update()
        assert w.current_temp == 22

    async def test_update_raises_on_api_error_response(self):
        """WeatherAPI returns {error: {code, message}} on failure."""
        session = _make_session(
            json_response={"error": {"code": 1006, "message": "No matching location"}}
        )
        w = WeatherWidget(
            session=session,
            location="nowhere",
            text="T",
        )
        with pytest.raises(ValueError, match="WeatherAPI error 1006"):
            await w.update()

    async def test_update_raises_on_invalid_api_key(self):
        session = _make_session(
            json_response={"error": {"code": 2006, "message": "API key is invalid"}}
        )
        w = WeatherWidget(
            session=session,
            location="NYC",
            text="T",
        )
        with pytest.raises(ValueError, match="API key is invalid"):
            await w.update()

    async def test_update_raises_on_missing_current_key(self):
        """If response has no 'current' and no 'error', KeyError."""
        session = _make_session(json_response={"location": {}})
        w = WeatherWidget(
            session=session,
            location="NYC",
            text="T",
        )
        with pytest.raises(KeyError):
            await w.update()

    async def test_update_preserves_stale_data_on_error(self):
        """On error, previously fetched data should remain intact."""
        w = WeatherWidget(
            session=mock.Mock(),
            location="NYC",
            text="T",
        )
        w.current_temp = 72
        w.weather = "Clear"

        session = _make_session(
            json_response={"error": {"code": 1006, "message": "No match"}}
        )
        w.session = session

        with pytest.raises(ValueError):
            await w.update()

        # Stale data preserved
        assert w.current_temp == 72
        assert w.weather == "Clear"

    async def test_start_returns_initialized_widget(self):
        session = _make_session(
            json_response={
                "current": {
                    "temp_f": 72,
                    "temp_c": 22,
                    "condition": {"text": "Clear"},
                }
            }
        )
        widget = await WeatherWidget.start(
            session=session,
            location="40.7,-74.0",
            text="NYC",
        )
        assert isinstance(widget, WeatherWidget)
        assert widget.current_temp == 72

    def test_location_dict_auto_converted(self):
        """TOML gives location as dict; converted to lat,lon string."""
        w = WeatherWidget(
            session=mock.Mock(),
            location={"lat": 40.7, "lon": -74.0},
            text="NYC",
        )
        assert w.location == "40.7,-74.0"


# --- RSS Feed ---

SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Test</title>
<item><title>A</title></item><item><title>B</title></item>
</channel></rss>"""


class TestRSSFeedUpdate:
    async def test_start_returns_widget(self):
        session = _make_session(text_response=SAMPLE_RSS)
        widget = await RSSFeedMonitor.start(
            session=session,
            feed_url="http://example.com/rss",
        )
        assert isinstance(widget, RSSFeedMonitor)
        assert widget.feed_title.text == "Test"

    async def test_update_with_empty_feed(self):
        empty = '<?xml version="1.0"?><rss><channel><title>E</title></channel></rss>'
        session = _make_session(text_response=empty)
        m = RSSFeedMonitor(session=session, feed_url="http://x.com")
        await m.update()
        assert m.feed_stories == []


