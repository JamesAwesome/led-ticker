"""RSS feed monitor widget."""

from __future__ import annotations

import asyncio
import itertools
import logging
from typing import Any, Self

import aiohttp
import attrs
import feedparser

from led_ticker._types import Color, Font
from led_ticker.colors import DEFAULT_COLOR, GREEN, RED
from led_ticker.fonts import FONT_DEFAULT
from led_ticker.widget import run_monitor_loop
from led_ticker.widgets import register
from led_ticker.widgets.message import TickerMessage

logger: logging.Logger = logging.getLogger(__name__)


@register("rss_feed")
@attrs.define
class RSSFeedMonitor:
    """Fetches and displays headlines from an RSS feed."""

    session: aiohttp.ClientSession
    feed_url: str
    padding: int = 6
    colors: itertools.cycle[Color] = attrs.Factory(
        lambda: itertools.cycle([DEFAULT_COLOR, RED, GREEN])
    )
    max_stories: int = 5
    # When set, every story TickerMessage gets this color/provider
    # (e.g. `font_color = "rainbow"` paints all stories rainbow).
    # When unset (None), fall back to the legacy 3-color rotation
    # (DEFAULT_COLOR / RED / GREEN) so existing configs keep working.
    font_color: Any = attrs.field(default=None, kw_only=True)
    bg_color: Color | None = attrs.field(default=None, kw_only=True)
    font: Font = attrs.field(default=attrs.Factory(lambda: FONT_DEFAULT), kw_only=True)
    feed_title: TickerMessage | None = attrs.field(init=False, default=None)
    feed_stories: list[TickerMessage] = attrs.field(init=False, factory=list)

    def _story_color(self) -> Any:
        """Per-story color: `font_color` if set, else next from the
        legacy cycle. Called once per story in `update()`."""
        if self.font_color is not None:
            return self.font_color
        return next(self.colors)

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
        logger.info("Updating RSS Feed from: %s", self.feed_url)
        async with self.session.get(self.feed_url) as response:
            feed_data = await response.text()
            feed = await asyncio.to_thread(feedparser.parse, feed_data)
            self.feed_title = TickerMessage(
                feed["channel"]["title"],  # type: ignore[index]
                font=self.font,
                font_color=self._story_color(),
                bg_color=self.bg_color,
            )
            self.feed_stories = [
                TickerMessage(
                    item["title"],  # type: ignore[index]
                    font=self.font,
                    font_color=self._story_color(),
                    bg_color=self.bg_color,
                )
                for item in itertools.islice(feed["items"], self.max_stories)  # type: ignore[index]
            ]
        logger.info(
            "RSS %s updated: %d stories",
            self.feed_url,
            len(self.feed_stories),
        )
