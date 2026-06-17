"""Tests for the widget registry."""

import pytest

from led_ticker.widgets import _WIDGET_REGISTRY, get_widget_class
from led_ticker.widgets.message import TickerCountdown, TickerMessage


def test_all_widgets_registered():
    expected = {
        "message": TickerMessage,
        "countdown": TickerCountdown,
    }
    for name, cls in expected.items():
        assert get_widget_class(name) is cls


def test_get_unknown_widget_raises():
    with pytest.raises(ValueError, match="Unknown widget type"):
        get_widget_class("nonexistent_widget")


def test_registry_has_six_widgets():
    assert len(_WIDGET_REGISTRY) == 6


def test_register_duplicate_name_raises():
    from led_ticker.widgets import register

    with pytest.raises(ValueError, match="Widget name.*message.*already registered"):

        @register("message")
        class ShouldFail:
            pass
