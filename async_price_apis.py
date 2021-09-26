#!/usr/bin/env python3 -u

import sys
import itertools
import asyncio
import aiohttp
import logging
import json
from datetime import date, timedelta

import attr
from rgbmatrix import RGBMatrix, RGBMatrixOptions, graphics


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


COINBASE_API = "https://api.coinbase.com"


@attr.s
class AsyncPriceMonitor(object):
    symbol = attr.ib(type=str)
    currency = attr.ib(type=str)
    session = attr.ib()
    update_interval = attr.ib(type=int, default=300)
    price = attr.ib(type=float, init=False)
    yesterdays_price = attr.ib(type=float, init=False)
    change_24h = attr.ib(type=float, init=False)
    change_str = attr.ib(type=str, init=False)
    price_str = attr.ib(type=str, init=False)

    def __attrs_post_init__(self):
        self.spot_url = f"{COINBASE_API}/v2/prices/{self.symbol}-{self.currency}/spot"

    @classmethod
    async def start(cls, symbol, currency, session, update_interval):
        price_monitor = await cls(symbol, currency, session, update_interval).update()
        asyncio.create_task(price_monitor.monitor())
        return price_monitor

    async def monitor(self):
        while True:
            await asyncio.sleep(self.update_interval)
            await self.update()

    async def update(self):
        logging.info(f"Updating monitor for {self.symbol}")
        self.price = await self.get_spot_price()
        self.price_str = f"{self.price:.4f}"

        self.yesterdays_price = await self.get_yesterdays_price()

        self.change_24h = (
            (self.price - self.yesterdays_price) / self.yesterdays_price
        ) * 100
        self.change_str = f"{self.change_24h:.2f}%"

        return self

    async def get_spot_price(self, spot_date=None):
        params = {}

        if spot_date:
            params["date"] = str(spot_date)

        async with self.session.get(self.spot_url, params=params) as response:
            price_data = await response.json()
            spot_price = float(price_data.get("data", {}).get("amount"))

        return spot_price

    async def get_yesterdays_price(self):
        yesterday = date.today() - timedelta(days=1)
        yesterdays_price = await self.get_spot_price(spot_date=yesterday)

        return yesterdays_price

    def _get_change_width(self, font_change, change_word, padding=6):
        change_width = (
            sum([font_change.CharacterWidth(ord(c)) for c in change_word]) + padding
        )

        return change_width

    def _get_change_color(self, change_str):
        if change_str.startswith("-"):
            return DOWN_TREND_COLOR

        return UP_TREND_COLOR

    def _get_price_font(self, price_str):
        if len(price_str) > 10:
            return FONT_PRICE_SMALL

        return FONT_PRICE

    def draw(self, canvas, cursor_pos=3):

        change_color = self._get_change_color(self.change_str)
        font_price = self._get_price_font(self.price_str)

        # Draw the elements on the canvas
        graphics.DrawText(
            canvas, FONT_SYMBOL, cursor_pos, 12, DEFAULT_COLOR, self.symbol
        )

        price_x = cursor_pos + self._get_change_width(FONT_SYMBOL, self.symbol)

        graphics.DrawText(
            canvas, font_price, price_x, 12, DEFAULT_COLOR, self.price_str
        )

        change_x = price_x + self._get_change_width(font_price, self.price_str)

        graphics.DrawText(
            canvas, FONT_CHANGE, change_x, 12, change_color, self.change_str
        )

        cursor_pos = change_x + self._get_change_width(FONT_CHANGE, self.change_str)

        return canvas, cursor_pos


async def print_value(price_monitors):
    while True:
        for price_monitor in itertools.cycle(price_monitors):
            print(
                json.dumps(
                    {
                        "symbol": price_monitor.symbol,
                        "currency": price_monitor.currency,
                        "price": f"{price_monitor.price:.4f}",
                        "change_24h": f"{price_monitor.change_24h:.2f}%",
                    }
                )
            )

            await asyncio.sleep(1)


async def main():
    async with aiohttp.ClientSession() as session:

        price_monitors = await asyncio.gather(
            AsyncPriceMonitor.start("ETH", "USD", session, 30),
            AsyncPriceMonitor.start("ADA", "USD", session, 30),
            AsyncPriceMonitor.start("SUSHI", "USD", session, 30),
        )

        await asyncio.gather(print_value(price_monitors))


if __name__ == "__main__":
    asyncio.run(main())
