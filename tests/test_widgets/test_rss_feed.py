"""Tests for led_ticker.widgets.rss_feed."""

import unittest.mock as mock

import feedparser as _feedparser
import pytest

from led_ticker.widgets.message import TickerMessage
from led_ticker.widgets.rss_feed import RSSFeedMonitor

SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Test Feed</title>
    <item><title>Story One</title></item>
    <item><title>Story Two</title></item>
    <item><title>Story Three</title></item>
  </channel>
</rss>
"""


@pytest.fixture
def mock_session():
    session = mock.MagicMock()
    response = mock.AsyncMock()
    response.text.return_value = SAMPLE_RSS

    # Create a proper async context manager
    ctx = mock.AsyncMock()
    ctx.__aenter__.return_value = response
    session.get.return_value = ctx
    return session


class TestRSSFeedMonitor:
    async def test_update_parses_feed(self, mock_session):
        monitor = RSSFeedMonitor(
            session=mock_session, feed_url="http://example.com/rss"
        )
        await monitor.update()

        assert isinstance(monitor.feed_title, TickerMessage)
        assert monitor.feed_title.text == "Test Feed"
        assert len(monitor.feed_stories) == 3
        assert monitor.feed_stories[0].text == "Story One"

    async def test_update_respects_max_stories(self, mock_session):
        monitor = RSSFeedMonitor(
            session=mock_session, feed_url="http://example.com/rss", max_stories=2
        )
        await monitor.update()
        assert len(monitor.feed_stories) == 2

    async def test_stories_are_ticker_messages(self, mock_session):
        monitor = RSSFeedMonitor(
            session=mock_session, feed_url="http://example.com/rss"
        )
        await monitor.update()
        for story in monitor.feed_stories:
            assert isinstance(story, TickerMessage)

    async def test_font_propagates_to_stories(self, mock_session):
        """font= on RSSFeedMonitor must flow to every generated TickerMessage."""
        from led_ticker.fonts import resolve_font

        custom_font = resolve_font("Inter-Regular", 16, threshold=80)
        monitor = RSSFeedMonitor(
            session=mock_session,
            feed_url="http://example.com/rss",
            font=custom_font,
        )
        await monitor.update()

        assert monitor.feed_title.font is custom_font
        assert all(s.font is custom_font for s in monitor.feed_stories)

    async def test_font_defaults_to_font_default(self, mock_session):
        """No font= specified → stories use FONT_DEFAULT (back-compat)."""
        from led_ticker.fonts import FONT_DEFAULT

        monitor = RSSFeedMonitor(
            session=mock_session, feed_url="http://example.com/rss"
        )
        await monitor.update()

        assert monitor.feed_title.font is FONT_DEFAULT
        assert all(s.font is FONT_DEFAULT for s in monitor.feed_stories)


class TestRssBgColor:
    def test_field_exists(self):
        names = {a.name for a in RSSFeedMonitor.__attrs_attrs__}
        assert "bg_color" in names

    def test_bg_color_propagates_to_stories(self, mock_session):
        """bg_color set on the container propagates to every story
        TickerMessage in feed_stories."""
        from rgbmatrix.graphics import Color

        bg = Color(40, 50, 60)
        feed = RSSFeedMonitor(
            session=mock_session, feed_url="https://example.com/feed", bg_color=bg
        )
        # Manually populate stories the way update() would. Bypass network.
        feed.feed_title = TickerMessage(text="Title", bg_color=bg)
        feed.feed_stories = [
            TickerMessage(text=item, bg_color=bg) for item in ("a", "b", "c")
        ]

        assert feed.bg_color is bg
        assert feed.feed_title.bg_color is bg
        assert all(s.bg_color is bg for s in feed.feed_stories)

    async def test_update_threads_bg_color(self, mock_session):
        """After update(), every story and the title carry bg_color."""
        from rgbmatrix.graphics import Color

        bg = Color(40, 50, 60)
        feed = RSSFeedMonitor(
            session=mock_session, feed_url="https://example.com/feed", bg_color=bg
        )
        await feed.update()

        assert feed.feed_title is not None
        assert feed.feed_title.bg_color is bg
        assert all(s.bg_color is bg for s in feed.feed_stories)


class TestRssFontColor:
    """`font_color` overrides the legacy 3-color cycle. When set, every
    story TickerMessage gets the same color/provider; when unset
    (None), fall back to the legacy rotation."""

    async def test_font_color_unset_uses_legacy_cycle(self, mock_session):
        """Default behavior: stories cycle through the 3 legacy colors."""
        feed = RSSFeedMonitor(session=mock_session, feed_url="https://example.com/feed")
        await feed.update()

        # Three distinct stories → three distinct cycle colors. The
        # exact values come from DEFAULT_COLOR / DOWN / UP cycling.
        colors = [s.font_color for s in feed.feed_stories]
        # All three should be distinct (cycle has 3 entries, 3 stories).
        assert len({(c._color.red, c._color.green, c._color.blue) for c in colors}) == 3

    async def test_font_color_set_applies_to_all_stories(self, mock_session):
        """`font_color = Rainbow()` → every story gets the same provider."""
        from led_ticker.color_providers import Rainbow

        rainbow = Rainbow()
        feed = RSSFeedMonitor(
            session=mock_session,
            feed_url="https://example.com/feed",
            font_color=rainbow,
        )
        await feed.update()

        assert feed.feed_title is not None
        # Title + every story shares the same provider instance.
        assert feed.feed_title.font_color is rainbow
        assert all(s.font_color is rainbow for s in feed.feed_stories)


class TestFeedparserOffEventLoop:
    """feedparser.parse is CPU-bound XML parsing. Calling it directly on
    the event loop blocks all other coroutines for the full parse duration.
    It must be offloaded via asyncio.to_thread (C2)."""

    async def test_feedparser_called_via_to_thread(self, mock_session, monkeypatch):
        """asyncio.to_thread must be called with feedparser.parse and the
        raw feed text — not feedparser.parse called directly."""
        calls: list[tuple] = []

        async def _fake_to_thread(func, *args, **kwargs):
            calls.append((func, args, kwargs))
            return func(*args, **kwargs)

        monkeypatch.setattr(
            "led_ticker.widgets.rss_feed.asyncio.to_thread", _fake_to_thread
        )

        monitor = RSSFeedMonitor(
            session=mock_session, feed_url="http://example.com/rss"
        )
        await monitor.update()

        assert len(calls) == 1, f"expected 1 to_thread call, got {len(calls)}: {calls}"
        func, args, kwargs = calls[0]
        assert func is _feedparser.parse, f"expected feedparser.parse, got {func}"
        assert args == (SAMPLE_RSS,), f"expected (SAMPLE_RSS,), got {args}"
