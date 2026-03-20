"""Tests for led_ticker.app — widget building from config dicts."""

import unittest.mock as mock
from datetime import date
from pathlib import Path

import pytest

from led_ticker.app import _build_title, _build_widget
from led_ticker.widget import Widget
from led_ticker.widgets.message import TickerCountdown, TickerMessage


class TestBuildWidget:
    """Test that _build_widget correctly maps config dicts to widget instances."""

    async def test_message_with_text_key(self):
        """Config uses 'text' — must map to 'message' param."""
        cfg = {"type": "message", "text": "Hello world"}
        widget = await _build_widget(cfg, session=mock.Mock())
        assert isinstance(widget, TickerMessage)
        assert widget.message == "Hello world"

    async def test_message_with_message_key(self):
        """Config can also use 'message' directly."""
        cfg = {"type": "message", "message": "Hello world"}
        widget = await _build_widget(cfg, session=mock.Mock())
        assert isinstance(widget, TickerMessage)
        assert widget.message == "Hello world"

    async def test_countdown_with_text_key(self):
        """Countdown config uses 'text' — must map to 'message'."""
        cfg = {
            "type": "countdown",
            "text": "Days Until Spring",
            "countdown_date": date(2026, 3, 20),
        }
        widget = await _build_widget(cfg, session=mock.Mock())
        assert isinstance(widget, TickerCountdown)
        assert widget.message == "Days Until Spring"

    async def test_countdown_with_message_key(self):
        cfg = {
            "type": "countdown",
            "message": "Days Until Spring",
            "countdown_date": date(2026, 3, 20),
        }
        widget = await _build_widget(cfg, session=mock.Mock())
        assert isinstance(widget, TickerCountdown)

    async def test_unknown_widget_type_raises(self):
        cfg = {"type": "nonexistent_widget"}
        with pytest.raises(ValueError, match="Unknown widget type"):
            await _build_widget(cfg, session=mock.Mock())

    async def test_text_key_does_not_override_message(self):
        """If both 'text' and 'message' are present, 'message' wins."""
        cfg = {
            "type": "message",
            "text": "from text",
            "message": "from message",
        }
        widget = await _build_widget(cfg, session=mock.Mock())
        assert widget.message == "from message"

    async def test_built_widget_conforms_to_protocol(self):
        cfg = {"type": "message", "text": "test"}
        widget = await _build_widget(cfg, session=mock.Mock())
        assert isinstance(widget, Widget)

    async def test_config_dict_not_mutated(self):
        """_build_widget receives a copy, but verify the mapping works
        even when called multiple times with fresh dicts."""
        for _ in range(3):
            cfg = {"type": "message", "text": "repeat"}
            widget = await _build_widget(cfg, session=mock.Mock())
            assert widget.message == "repeat"


class TestBuildTitle:
    async def test_build_title_with_text(self):
        title = await _build_title({"text": "News", "color": "random"})
        assert isinstance(title, TickerMessage)
        assert title.message == "News"

    async def test_build_title_none(self):
        title = await _build_title(None)
        assert title is None

    async def test_build_title_no_color(self):
        title = await _build_title({"text": "Plain"})
        assert isinstance(title, TickerMessage)
        assert title.message == "Plain"

    async def test_build_title_empty_text(self):
        title = await _build_title({"text": ""})
        assert isinstance(title, TickerMessage)
        assert title.message == ""


class TestExampleConfigWidgets:
    """Verify every widget in config.example.toml can be instantiated.

    This is the integration test that would have caught the text/message bug.
    """

    async def test_all_example_config_widgets_build(self):
        """Load config.example.toml and build every widget."""
        from led_ticker.config import load_config

        config_path = Path(__file__).resolve().parent.parent / "config.example.toml"
        if not config_path.exists():
            pytest.skip("config.example.toml not found")

        config = load_config(config_path)

        for section in config.sections:
            # Build title
            if section.title:
                title = await _build_title(section.title)
                assert isinstance(title, TickerMessage)

            # Build each widget
            for widget_cfg in section.widgets:
                cfg = dict(widget_cfg)
                widget_type = cfg.get("type")

                # Skip widgets that need network (rss_feed, weather, crypto)
                if widget_type in (
                    "rss_feed",
                    "weather",
                    "coinbase",
                    "coingecko",
                    "etherscan",
                ):
                    continue

                widget = await _build_widget(cfg, session=mock.Mock())
                assert isinstance(widget, Widget), (
                    f"Widget type={widget_type} did not produce a Widget"
                )
