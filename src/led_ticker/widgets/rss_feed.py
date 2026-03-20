"""RSS feed monitor widget."""

import asyncio
import itertools
import logging

import attrs
import feedparser

from led_ticker.colors import DEFAULT_COLOR, DOWN_TREND_COLOR, UP_TREND_COLOR
from led_ticker.widget import run_monitor_loop
from led_ticker.widgets import register
from led_ticker.widgets.message import TickerMessage


@register("rss_feed")
@attrs.define
class RSSFeedMonitor:
    """Fetches and displays headlines from an RSS feed."""

    session: object
    feed_url: str
    padding: int = 6
    colors: object = attrs.Factory(
        lambda: itertools.cycle([DEFAULT_COLOR, DOWN_TREND_COLOR, UP_TREND_COLOR])
    )
    max_stories: int = 5
    feed_title: object = attrs.field(init=False, default=None)
    feed_stories: list = attrs.field(init=False, factory=list)

    @classmethod
    async def start(cls, session, feed_url, update_interval=1800, **kwargs):
        widget = cls(session=session, feed_url=feed_url, **kwargs)
        await widget.update()
        asyncio.create_task(run_monitor_loop(widget, update_interval))
        return widget

    async def update(self):
        logging.info("Updating RSS Feed from: %s", self.feed_url)
        async with self.session.get(self.feed_url) as response:
            feed_data = await response.text()
            feed = feedparser.parse(feed_data)
            self.feed_title = TickerMessage(
                feed["channel"]["title"], font_color=next(self.colors)
            )
            self.feed_stories = [
                TickerMessage(item["title"], font_color=next(self.colors))
                for item in itertools.islice(feed["items"], self.max_stories)
            ]
