"""Tests for the widget registry."""

import pytest

from led_ticker.widgets import _WIDGET_REGISTRY, get_widget_class
from led_ticker.widgets.crypto.coinbase import CoinbasePriceMonitor
from led_ticker.widgets.crypto.coingecko import CoinGeckoPriceMonitor
from led_ticker.widgets.crypto.etherscan import EtherscanGasMonitor
from led_ticker.widgets.message import TickerCountdown, TickerMessage
from led_ticker.widgets.rss_feed import RSSFeedMonitor
from led_ticker.widgets.weather import WeatherWidget


def test_all_widgets_registered():
    expected = {
        "message": TickerMessage,
        "countdown": TickerCountdown,
        "weather": WeatherWidget,
        "rss_feed": RSSFeedMonitor,
        "coinbase": CoinbasePriceMonitor,
        "coingecko": CoinGeckoPriceMonitor,
        "etherscan": EtherscanGasMonitor,
    }
    for name, cls in expected.items():
        assert get_widget_class(name) is cls


def test_get_unknown_widget_raises():
    with pytest.raises(ValueError, match="Unknown widget type"):
        get_widget_class("nonexistent_widget")


def test_registry_has_seven_widgets():
    assert len(_WIDGET_REGISTRY) == 7
