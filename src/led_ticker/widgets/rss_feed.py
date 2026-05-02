"""RSS feed monitor widget."""

from __future__ import annotations

import asyncio
import itertools
import logging
from typing import Any, Self

import aiohttp
import attrs
import feedparser

from led_ticker._types import Color
from led_ticker.colors import DEFAULT_COLOR, DOWN_TREND_COLOR, UP_TREND_COLOR
from led_ticker.widget import run_monitor_loop
from led_ticker.widgets import register
from led_ticker.widgets.message import TickerMessage


@register("rss_feed")
@attrs.define
class RSSFeedMonitor:
    """Fetches and displays headlines from an RSS feed."""

    session: aiohttp.ClientSession
    feed_url: str
    padding: int = 6
    colors: itertools.cycle[Color] = attrs.Factory(
        lambda: itertools.cycle([DEFAULT_COLOR, DOWN_TREND_COLOR, UP_TREND_COLOR])
    )
    max_stories: int = 5
    bg_color: Color | None = attrs.field(default=None, kw_only=True)
    feed_title: TickerMessage | None = attrs.field(init=False, default=None)
    feed_stories: list[TickerMessage] = attrs.field(init=False, factory=list)

    @classmethod
    async def start(
        cls,
        session: aiohttp.ClientSession,
        feed_url: str,
        update_interval: int = 1800,
        **kwargs: Any,
    ) -> Self:
        widget = cls(session=session, feed_url=feed_url, **kwargs)
        await widget.update()
        asyncio.create_task(run_monitor_loop(widget, update_interval))
        return widget

    async def update(self) -> None:
        logging.info("Updating RSS Feed from: %s", self.feed_url)
        async with self.session.get(self.feed_url) as response:
            feed_data = await response.text()
            feed = feedparser.parse(feed_data)
            self.feed_title = TickerMessage(
                feed["channel"]["title"],  # type: ignore[index]
                font_color=next(self.colors),
                bg_color=self.bg_color,
            )
            self.feed_stories = [
                TickerMessage(
                    item["title"],  # type: ignore[index]
                    font_color=next(self.colors),
                    bg_color=self.bg_color,
                )
                for item in itertools.islice(feed["items"], self.max_stories)  # type: ignore[index]
            ]
