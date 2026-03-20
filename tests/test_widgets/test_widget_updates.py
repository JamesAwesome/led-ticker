"""Tests for async widget update() and start() methods."""

import unittest.mock as mock

import pytest

from led_ticker.widgets.crypto.coinbase import CoinbasePriceMonitor
from led_ticker.widgets.crypto.coingecko import CoinGeckoPriceMonitor
from led_ticker.widgets.crypto.etherscan import EtherscanGasMonitor
from led_ticker.widgets.rss_feed import RSSFeedMonitor
from led_ticker.widgets.weather import LocationData, WeatherWidget


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


class TestWeatherUpdate:
    async def test_update_parses_weather(self):
        session = _make_session(
            json_response={"current": {"temp": 72, "weather": [{"main": "Clear"}]}}
        )
        w = WeatherWidget(
            session=session,
            location=LocationData(40.7, -74.0),
            message="NYC",
        )
        await w.update()
        assert w.current_temp == 72
        assert w.weather == "Clear"

    async def test_update_truncates_fractional_temp(self):
        session = _make_session(
            json_response={"current": {"temp": 72.9, "weather": [{"main": "Rain"}]}}
        )
        w = WeatherWidget(
            session=session,
            location=LocationData(0, 0),
            message="T",
        )
        await w.update()
        assert w.current_temp == 72  # int() truncates

    async def test_update_raises_on_missing_current(self):
        session = _make_session(json_response={"hourly": []})
        w = WeatherWidget(
            session=session,
            location=LocationData(0, 0),
            message="T",
        )
        with pytest.raises(KeyError):
            await w.update()

    async def test_start_returns_initialized_widget(self):
        session = _make_session(
            json_response={"current": {"temp": 72, "weather": [{"main": "Clear"}]}}
        )
        widget = await WeatherWidget.start(
            session=session,
            location=LocationData(40.7, -74.0),
            message="NYC",
        )
        assert isinstance(widget, WeatherWidget)
        assert widget.current_temp == 72

    def test_location_dict_auto_converted(self):
        """TOML gives location as dict; __attrs_post_init__ converts it."""
        w = WeatherWidget(
            session=mock.Mock(),
            location={"lat": 40.7, "lon": -74.0},
            message="NYC",
        )
        assert isinstance(w.location, LocationData)
        assert w.location.lat == 40.7


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
        assert widget.feed_title.message == "Test"

    async def test_update_with_empty_feed(self):
        empty = '<?xml version="1.0"?><rss><channel><title>E</title></channel></rss>'
        session = _make_session(text_response=empty)
        m = RSSFeedMonitor(session=session, feed_url="http://x.com")
        await m.update()
        assert m.feed_stories == []


# --- Coinbase ---


class TestCoinbaseUpdate:
    def _make_session(self, spot="50000.00", yesterday="48000.00"):
        session = mock.MagicMock()
        call_count = 0

        def make_ctx(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            resp = mock.AsyncMock()
            resp.json.return_value = {
                "data": {"amount": spot if call_count == 1 else yesterday}
            }
            ctx = mock.AsyncMock()
            ctx.__aenter__.return_value = resp
            return ctx

        session.get.side_effect = make_ctx
        return session

    async def test_update_computes_change(self):
        session = self._make_session("50000.00", "48000.00")
        m = CoinbasePriceMonitor(symbol="BTC", currency="USD", session=session)
        await m.update()
        assert m.price == 50000.0
        assert m.yesterdays_price == 48000.0
        assert abs(m.change_24h - 4.1667) < 0.01

    async def test_update_zero_yesterday_no_crash(self):
        """Was ZeroDivisionError before fix."""
        session = self._make_session("100.00", "0")
        m = CoinbasePriceMonitor(symbol="X", currency="USD", session=session)
        await m.update()
        assert m.change_24h == 0.0

    async def test_get_spot_price_missing_amount_raises(self):
        """Was TypeError(float(None)) before fix."""
        session = _make_session(json_response={"data": {}})
        m = CoinbasePriceMonitor(symbol="X", currency="USD", session=session)
        with pytest.raises(KeyError, match="amount"):
            await m.get_spot_price()

    async def test_start_returns_widget(self):
        session = self._make_session()
        widget = await CoinbasePriceMonitor.start(
            symbol="BTC",
            currency="USD",
            session=session,
        )
        assert isinstance(widget, CoinbasePriceMonitor)
        assert widget.price == 50000.0

    async def test_start_accepts_extra_kwargs(self):
        """start() should not crash on extra config keys."""
        session = self._make_session()
        widget = await CoinbasePriceMonitor.start(
            symbol="BTC",
            currency="USD",
            session=session,
            padding=3,
        )
        assert widget is not None


# --- CoinGecko ---


class TestCoinGeckoUpdate:
    async def test_update_parses_price(self):
        session = _make_session(
            json_response={"bitcoin": {"usd": 50000.0, "usd_24h_change": 2.55}}
        )
        m = CoinGeckoPriceMonitor(
            symbol="BTC",
            symbol_id="bitcoin",
            currency="USD",
            session=session,
        )
        await m.update()
        assert m.price_data["price"] == "50,000.0000"
        assert m.price_data["change_24h"] == "2.55%"

    async def test_draw_with_default_price_data(self, canvas):
        """Default price_data has safe fallback values."""
        m = CoinGeckoPriceMonitor(
            symbol="BTC",
            symbol_id="bitcoin",
            currency="USD",
            session=mock.Mock(),
        )
        # Should not crash with default values
        result_canvas, pos = m.draw(canvas)
        assert result_canvas is canvas

    async def test_update_incomplete_data_keeps_defaults(self):
        session = _make_session(json_response={"bitcoin": {}})
        m = CoinGeckoPriceMonitor(
            symbol="BTC",
            symbol_id="bitcoin",
            currency="USD",
            session=session,
        )
        await m.update()
        # Should still have safe defaults
        assert "price" in m.price_data

    async def test_start_returns_widget(self):
        session = _make_session(
            json_response={"bitcoin": {"usd": 50000.0, "usd_24h_change": 2.55}}
        )
        widget = await CoinGeckoPriceMonitor.start(
            symbol="BTC",
            symbol_id="bitcoin",
            currency="USD",
            session=session,
        )
        assert isinstance(widget, CoinGeckoPriceMonitor)


# --- Etherscan ---


class TestEtherscanUpdate:
    async def test_update_parses_gas_prices(self):
        session = _make_session(
            json_response={
                "result": {
                    "SafeGasPrice": "20",
                    "ProposeGasPrice": "45",
                    "FastGasPrice": "80",
                }
            }
        )
        m = EtherscanGasMonitor(session=session, api_key="key")
        await m.update()
        assert m.price_data == {"Low": "20", "Avg": "45", "High": "80"}

    async def test_update_error_response_raises(self):
        """Was TypeError before fix — Etherscan returns string result on error."""
        session = _make_session(
            json_response={
                "status": "0",
                "message": "NOTOK",
                "result": "Max rate limit reached",
            }
        )
        m = EtherscanGasMonitor(session=session, api_key="key")
        with pytest.raises(ValueError, match="Etherscan API error"):
            await m.update()

    async def test_start_returns_widget(self):
        session = _make_session(
            json_response={
                "result": {
                    "SafeGasPrice": "20",
                    "ProposeGasPrice": "45",
                    "FastGasPrice": "80",
                }
            }
        )
        widget = await EtherscanGasMonitor.start(session=session, api_key="key")
        assert isinstance(widget, EtherscanGasMonitor)
        assert widget.price_data["Low"] == "20"

    async def test_start_accepts_extra_kwargs(self):
        session = _make_session(
            json_response={
                "result": {
                    "SafeGasPrice": "20",
                    "ProposeGasPrice": "45",
                    "FastGasPrice": "80",
                }
            }
        )
        widget = await EtherscanGasMonitor.start(
            session=session,
            api_key="key",
            extra_param="ignored",
        )
        assert widget is not None
