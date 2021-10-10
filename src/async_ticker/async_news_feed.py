#!/usr/bin/env python3 -u
"""Async RSS Ticker Widgets"""

import itertools
import asyncio
import logging
from random import randint

import feedparser
import aiohttp
import attr

from rgbmatrix import graphics

from async_ticker.widgets import TickerMessage

from async_ticker.fonts import (
    FONT_SYMBOL,
    FONT_PRICE,
    FONT_PRICE_SMALL,
    FONT_CHANGE,
)

from async_ticker.colors import (
    RGB_WHITE,
    DEFAULT_COLOR,
    UP_TREND_COLOR,
    DOWN_TREND_COLOR,
)

from async_ticker.helpers import get_text_width


COINBASE_API = "https://api.coinbase.com"

COINGECKO_API = 'https://api.coingecko.com/api/v3'
COINGECKO_COIN_LIST = f'{COINGECKO_API}/coins/list'
COINGECKO_PRICE_API = f'{COINGECKO_API}/simple/price'

ETHERSCAN_API = "https://api.etherscan.io/api"


@attr.s
class RSSFeedMonitor:
    """Monit gas prices"""

    session = attr.ib()
    feed_url = attr.ib()
    padding = attr.ib(default=6)
    colors = attr.ib(default=itertools.cycle([DEFAULT_COLOR, DOWN_TREND_COLOR, UP_TREND_COLOR]))
    max_stories = attr.ib(default=5)
    feed_title = attr.ib(init=False)
    feed_stories = attr.ib(init=False)

    @classmethod
    async def start(cls, session, feed_url, update_interval=1800, splay=True):
        """init and run this monitor"""
        if splay:
            update_interval += randint(0, 60)

        feed_monitor = await cls(session, feed_url=feed_url).update()
        asyncio.create_task(feed_monitor.monitor(update_interval))

        return feed_monitor

    async def update(self):
        """update price information"""
        logging.info(f"Updating RSS Feed from: {self.feed_url}")

        async with self.session.get(self.feed_url) as response:
            feed_data = await response.text()
            feed = feedparser.parse(feed_data)
            self.feed_title = TickerMessage(feed['channel']['title'], font_color=next(self.colors))
            self.feed_stories = list(itertools.islice(
                [TickerMessage(item['title'], font_color=next(self.colors)) for item in feed['items']],
                self.max_stories,
            ))

        return self

    async def monitor(self, update_interval):
        """update self in a loop"""
        while True:
            await asyncio.sleep(update_interval)
            await self.update()
