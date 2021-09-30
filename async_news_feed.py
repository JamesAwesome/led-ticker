#!/usr/bin/env python3 -u
"""Async RSS Ticker Widgets"""

import itertools
import asyncio
import logging
from random import randint

import aiohttp
import attr

from rgbmatrix import graphics

FONT_SYMBOL = graphics.Font()
FONT_SYMBOL.LoadFont("fonts/7x13.bdf")

FONT_PRICE = graphics.Font()
FONT_PRICE.LoadFont("fonts/6x12.bdf")

FONT_PRICE_SMALL = graphics.Font()
FONT_PRICE_SMALL.LoadFont("fonts/5x8.bdf")

FONT_CHANGE = graphics.Font()
FONT_CHANGE.LoadFont("fonts/6x10.bdf")

DEFAULT_COLOR = graphics.Color(255, 255, 0)
UP_TREND_COLOR = graphics.Color(46, 139, 87)
DOWN_TREND_COLOR = graphics.Color(194, 24, 7)

OK_GAS_COLOR = graphics.Color(255, 255, 100)

COINBASE_API = "https://api.coinbase.com"

COINGECKO_API = 'https://api.coingecko.com/api/v3'
COINGECKO_COIN_LIST = f'{COINGECKO_API}/coins/list'
COINGECKO_PRICE_API = f'{COINGECKO_API}/simple/price'

ETHERSCAN_API = "https://api.etherscan.io/api"


def _get_change_width(font_change, change_word, padding=6):
    """get the width of font text + padding"""
    change_width = (
        sum([font_change.CharacterWidth(ord(c)) for c in change_word]) + padding
    )

    return change_width


@attr.s
class RSSFeedMonitor:
    """Monit gas prices"""

    session = attr.ib()
    feed_url = attr.ib()
    padding = attr.ib(default=6)
    feed_stories = attr.ib(init=False)

    async def update(self):
        """update price information"""
        logging.info(f"Updating RSS Feed from: {self.feed_url}")

        async with self.session.get(self.feed_url) as response:
            feed_data = await response.body()
            feed = feedparser.parse(feed_data)
            self.feed_stories = itertools.cycle([item['title'] for item in feed['items']])

        return self

    @classmethod
    async def start(cls, session, feed_url, update_interval=1800, splay=True):
        """init and run this monitor"""
        if splay:
            update_interval += randint(0, 60)

        feed_monitor = await cls(session, feed_url=feed_url).update()
        asyncio.create_task(feed_monitor.monitor(update_interval))

        return feed_moitor

    async def monitor(self, update_interval):
        """update self in a loop"""
        while True:
            await asyncio.sleep(update_interval)
            await self.update()

    def draw(self, canvas, cursor_pos=3):
        """draw this monitor to a canvas"""

        story = next(self.feed_stories)

        cursor_pos += graphics.DrawText(
            canvas, FONT_SYMBOL, cursor_pos, 12, DEFAULT_COLOR, story
        )

        return canvas, (cursor_pos + self.padding)
