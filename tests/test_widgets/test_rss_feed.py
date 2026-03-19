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
        monitor = RSSFeedMonitor(session=mock_session, feed_url="http://example.com/rss")
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
        monitor = RSSFeedMonitor(session=mock_session, feed_url="http://example.com/rss")
        await monitor.update()
        for story in monitor.feed_stories:
            assert isinstance(story, TickerMessage)
