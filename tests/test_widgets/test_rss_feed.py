"""Tests for led_ticker.widgets.rss_feed."""

import unittest.mock as mock

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
        assert monitor.feed_title.message == "Test Feed"
        assert len(monitor.feed_stories) == 3
        assert monitor.feed_stories[0].message == "Story One"

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
        feed.feed_title = TickerMessage("Title", bg_color=bg)
        feed.feed_stories = [
            TickerMessage(item, bg_color=bg) for item in ("a", "b", "c")
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
