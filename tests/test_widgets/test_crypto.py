"""Tests for led_ticker.widgets.crypto (coinbase, coingecko, etherscan)."""

import unittest.mock as mock

import pytest

from led_ticker.colors import (
    DEFAULT_COLOR,
    DOWN_TREND_COLOR,
    NEUTRAL_TREND_COLOR,
    UP_TREND_COLOR,
)
from led_ticker.fonts import FONT_VALUE, FONT_VALUE_SMALL
from led_ticker.widget import Widget
from led_ticker.widgets.crypto.coinbase import (
    CoinbasePriceMonitor,
    _draw_price_ticker,
    _get_change_color,
    _get_price_font,
)
from led_ticker.widgets.crypto.coingecko import (
    CoinGeckoPriceMonitor,
    _find_coingecko_symbol_id,
)
from led_ticker.widgets.crypto.etherscan import (
    EtherscanGasMonitor,
    _get_gas_price_color,
)

# --- Coinbase ---


class TestCoinbasePriceMonitor:
    @pytest.fixture
    def monitor(self):
        m = CoinbasePriceMonitor(symbol="BTC", currency="USD", session=mock.Mock())
        m.price = 50000.1234
        m.change_24h = 2.55
        return m

    def test_conforms_to_widget_protocol(self, monitor):
        assert isinstance(monitor, Widget)

    def test_draw_returns_canvas(self, canvas, monitor):
        result, cursor_pos = monitor.draw(canvas)
        assert result is canvas
        assert cursor_pos > 0

    def test_draw_centered(self, canvas, monitor):
        _, cursor_pos = monitor.draw(canvas)
        assert cursor_pos == 160  # centered fills canvas

    def test_draw_uncentered(self, canvas):
        m = CoinbasePriceMonitor(
            symbol="BTC", currency="USD", session=mock.Mock(), center=False
        )
        m.price = 50000.1234
        m.change_24h = 2.55
        _, cursor_pos = m.draw(canvas)
        assert cursor_pos < 160

    def test_post_init_sets_spot_url(self):
        m = CoinbasePriceMonitor(symbol="ETH", currency="USD", session=mock.Mock())
        assert "ETH-USD" in m.spot_url


class TestCoinbaseHelpers:
    def test_get_change_color_positive(self):
        assert _get_change_color("2.55%") == UP_TREND_COLOR

    def test_get_change_color_negative(self):
        assert _get_change_color("-1.23%") == DOWN_TREND_COLOR

    def test_get_change_color_zero_is_neutral(self):
        # Regression: previously "0.00%" matched the "everything not '-'"
        # branch and rendered as up-trend (green).
        assert _get_change_color("0.00%") == NEUTRAL_TREND_COLOR
        assert _get_change_color("0%") == NEUTRAL_TREND_COLOR

    def test_get_change_color_unparseable_is_neutral(self):
        # Defensive: API returning malformed strings shouldn't crash mid-render.
        assert _get_change_color("N/A") == NEUTRAL_TREND_COLOR
        assert _get_change_color("") == NEUTRAL_TREND_COLOR

    def test_get_price_font_short(self):
        assert _get_price_font("1234.5678") == FONT_VALUE

    def test_get_price_font_long(self):
        assert _get_price_font("12345678.90") == FONT_VALUE_SMALL


class TestDrawPriceTicker:
    def test_returns_canvas(self, canvas):
        result, pos = _draw_price_ticker(canvas, "BTC", "50000.00", "2.55%")
        assert result is canvas
        assert pos > 0

    def test_centered_fills_canvas(self, canvas):
        _, pos = _draw_price_ticker(canvas, "BTC", "50000.00", "2.55%", center=True)
        assert pos == 160


# --- CoinGecko ---


class TestCoinGeckoPriceMonitor:
    @pytest.fixture
    def monitor(self):
        m = CoinGeckoPriceMonitor(
            symbol="ETH", symbol_id="ethereum", currency="USD", session=mock.Mock()
        )
        m.price_data = {"price": "3,000.0000", "change_24h": "1.50%"}
        return m

    def test_conforms_to_widget_protocol(self, monitor):
        assert isinstance(monitor, Widget)

    def test_draw_returns_canvas(self, canvas, monitor):
        result, pos = monitor.draw(canvas)
        assert result is canvas

    def test_find_symbol_id(self):
        coin_list = [
            {"id": "bitcoin", "symbol": "btc"},
            {"id": "ethereum", "symbol": "eth"},
        ]
        assert _find_coingecko_symbol_id(coin_list, "ETH") == "ethereum"
        assert _find_coingecko_symbol_id(coin_list, "DOGE") is None


# --- Etherscan ---


class TestEtherscanGasMonitor:
    @pytest.fixture
    def monitor(self):
        m = EtherscanGasMonitor(session=mock.Mock(), api_key="test-key")
        m.price_data = {"Low": "20", "Avg": "45", "High": "80"}
        return m

    def test_conforms_to_widget_protocol(self, monitor):
        assert isinstance(monitor, Widget)

    def test_draw_returns_canvas(self, canvas, monitor):
        result, pos = monitor.draw(canvas)
        assert result is canvas
        assert pos > 0

    def test_gas_price_color_low(self):
        assert _get_gas_price_color("30") == UP_TREND_COLOR

    def test_gas_price_color_mid(self):
        color = _get_gas_price_color("60")
        # OK_GAS_COLOR (255, 255, 100)
        assert color.red == 255
        assert color.blue == 100

    def test_gas_price_color_high(self):
        assert _get_gas_price_color("100") == DOWN_TREND_COLOR

    def test_gas_price_color_handles_fractional(self):
        # Regression: int("42.5") raised ValueError and crashed mid-render,
        # corrupting the in-progress canvas frame.
        assert _get_gas_price_color("42.5") == UP_TREND_COLOR
        assert _get_gas_price_color("60.7") is not None  # mid-range, no crash

    def test_gas_price_color_handles_garbage(self):
        # Etherscan rate-limit responses or schema changes shouldn't crash.
        assert _get_gas_price_color("N/A") == DEFAULT_COLOR
        assert _get_gas_price_color("") == DEFAULT_COLOR


class TestCryptoBgColor:
    def test_coinbase_bg_color_default_is_none(self):
        w = CoinbasePriceMonitor(symbol="BTC", currency="USD", session=mock.Mock())
        assert w.bg_color is None

    def test_coinbase_accepts_bg_color(self):
        from rgbmatrix.graphics import Color

        w = CoinbasePriceMonitor(
            symbol="BTC", currency="USD", session=mock.Mock(), bg_color=Color(7, 8, 9)
        )
        assert w.bg_color.green == 8

    def test_coingecko_bg_color_default_is_none(self):
        w = CoinGeckoPriceMonitor(
            symbol="ETH", symbol_id="ethereum", currency="USD", session=mock.Mock()
        )
        assert w.bg_color is None

    def test_coingecko_accepts_bg_color(self):
        from rgbmatrix.graphics import Color

        w = CoinGeckoPriceMonitor(
            symbol="ETH",
            symbol_id="ethereum",
            currency="USD",
            session=mock.Mock(),
            bg_color=Color(11, 12, 13),
        )
        assert w.bg_color.blue == 13

    def test_etherscan_bg_color_default_is_none(self):
        w = EtherscanGasMonitor(session=mock.Mock(), api_key="test-key")
        assert w.bg_color is None

    def test_etherscan_accepts_bg_color(self):
        from rgbmatrix.graphics import Color

        w = EtherscanGasMonitor(
            session=mock.Mock(), api_key="test-key", bg_color=Color(99, 100, 101)
        )
        assert w.bg_color.red == 99
