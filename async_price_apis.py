#!/usr/bin/env python3 -u
"""Async Price APIs

Async price monitor widgets
"""
import itertools
import asyncio
import logging
import json
from datetime import date, timedelta
from random import randint
import math

import aiohttp
import attr

from rgbmatrix import graphics

GAS_BANNER = "Gas(gwei):"

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


def _find_center(canvas, change_width):
    return (canvas.width / 2) - math.floor(change_width / 2)


def _get_change_color(change_str):
    """choose the color for the price change"""
    if change_str.startswith("-"):
        return DOWN_TREND_COLOR

    return UP_TREND_COLOR


def _get_gas_price_color(price):
    if int(price) <= 50:
        return UP_TREND_COLOR

    if int(price) <= 70:
        return OK_GAS_COLOR

    return DOWN_TREND_COLOR


def _get_price_font(price_str):
    """choose big or small font for the price"""
    if len(price_str) > 10:
        return FONT_PRICE_SMALL

    return FONT_PRICE


@attr.s
class EtherscanGasMonitor:
    """Monit gas prices"""

    session = attr.ib()
    api_key = attr.ib()
    price_data = attr.ib(init=False)

    async def update(self):
        """update price information"""
        logging.info("Updating gas prices")

        params = {"module": "gastracker", "action": "gasoracle", "apikey": self.api_key}

        async with self.session.get(ETHERSCAN_API, params=params) as response:
            gas_price_data = await response.json()

            self.price_data = {
                "Low": gas_price_data["result"]["SafeGasPrice"],
                "Avg": gas_price_data["result"]["ProposeGasPrice"],
                "High": gas_price_data["result"]["FastGasPrice"],
            }

        return self

    @classmethod
    async def start(cls, session, api_key, update_interval=300, splay=True):
        """init and run this monitor"""
        if splay:
            update_interval += randint(0, 60)

        gas_price_monitor = await cls(session, api_key=api_key).update()
        asyncio.create_task(gas_price_monitor.monitor(update_interval))

        return gas_price_monitor

    async def monitor(self, update_interval):
        """update self in a loop"""
        while True:
            await asyncio.sleep(update_interval)
            await self.update()

    def draw(self, canvas, cursor_pos=3, **kwargs):
        """draw this monitor to a canvas"""

        # Draw the elements on the canvas
        graphics.DrawText(
            canvas, FONT_SYMBOL, cursor_pos, 12, DEFAULT_COLOR, GAS_BANNER
        )

        cursor_pos += _get_change_width(FONT_SYMBOL, GAS_BANNER)

        for price_type, price in self.price_data.items():

            price_type_msg = f"{price_type}:"
            graphics.DrawText(
                canvas, FONT_SYMBOL, cursor_pos, 12, DEFAULT_COLOR, price_type_msg
            )

            cursor_pos += _get_change_width(FONT_SYMBOL, price_type_msg, padding=3)

            graphics.DrawText(
                canvas, FONT_PRICE, cursor_pos, 12, _get_gas_price_color(price), price
            )

            cursor_pos += _get_change_width(FONT_PRICE, price, padding=3)

        cursor_pos += 3
        return canvas, cursor_pos


@attr.s
class CoinbasePriceMonitor:
    """An asynchronous crypto monitor widget to be used with AsyncTicker

    Uses coinbases API
    """

    symbol = attr.ib(type=str)
    currency = attr.ib(type=str)
    session = attr.ib()
    center = attr.ib(default=True)
    padding = attr.ib(default=6)
    price = attr.ib(type=float, init=False)
    yesterdays_price = attr.ib(type=float, init=False)
    change_24h = attr.ib(type=float, init=False)
    spot_url = attr.ib(type=str, init=False)

    def __attrs_post_init__(self):
        self.spot_url = f"{COINBASE_API}/v2/prices/{self.symbol}-{self.currency}/spot"

    @classmethod
    async def start(cls, symbol, currency, session, update_interval=300, splay=True, center=True): # pylint: disable=R0913
        """init and run this monitor"""
        if splay:
            update_interval += randint(0, 120)

        price_monitor = await cls(symbol, currency, session).update()
        asyncio.create_task(price_monitor.monitor(update_interval))
        return price_monitor

    async def monitor(self, update_interval):
        """update self in a loop"""
        while True:
            await asyncio.sleep(update_interval)
            await self.update()

    async def update(self):
        """update price information"""
        logging.info("Updating monitor for %s via CoinBase", self.symbol)
        self.price = await self.get_spot_price()

        self.yesterdays_price = await self.get_yesterdays_price()

        self.change_24h = (
            (self.price - self.yesterdays_price) / self.yesterdays_price
        ) * 100

        return self

    async def get_spot_price(self, spot_date=None):
        """get a spot price from the coinbase api, defaults to current"""
        params = {}

        if spot_date:
            params["date"] = str(spot_date)

        async with self.session.get(self.spot_url, params=params) as response:
            price_data = await response.json()
            spot_price = float(price_data.get("data", {}).get("amount"))

        return spot_price

    async def get_yesterdays_price(self):
        """get yesterdays spot price from the coinbase api"""
        yesterday = date.today() - timedelta(days=1)
        yesterdays_price = await self.get_spot_price(spot_date=yesterday)

        return yesterdays_price

    def draw(self, canvas, cursor_pos=0, **kwargs):
        """draw this monitor to a canvas"""
        end_padding = self.padding
        change_str = f"{self.change_24h:.2f}%"
        price_str = f"{self.price:.4f}"

        change_color = _get_change_color(change_str)
        font_price = _get_price_font(price_str)

        change_width = sum([
            _get_change_width(FONT_SYMBOL, self.symbol),
            _get_change_width(font_price, price_str),
            _get_change_width(FONT_CHANGE, change_str, padding=0),
        ])

        if self.center:
            if change_width > canvas.width:
                cursor_pos = cursor_pos

            else:
                center_pos = _find_center(canvas, change_width)
                end_padding = canvas.width - (center_pos + change_width)
                cursor_pos += center_pos

        # Draw the elements on the canvas
        cursor_pos += graphics.DrawText(
            canvas, FONT_SYMBOL, cursor_pos, 12, DEFAULT_COLOR, self.symbol
        )

        cursor_pos += self.padding
        cursor_pos += graphics.DrawText(
            canvas, font_price, cursor_pos, 12, DEFAULT_COLOR, price_str
        )

        cursor_pos += self.padding
        cursor_pos += graphics.DrawText(
            canvas, FONT_CHANGE, cursor_pos, 12, change_color, change_str
        )

        cursor_pos += end_padding

        logging.info(cursor_pos)

        return canvas, cursor_pos


async def _get_coingecko_coin_list(session):
    logging.info('Fetching CoinGecko coin list...')
    headers = {'Accept': 'application/json' }

    async with session.get(COINGECKO_COIN_LIST, headers=headers) as response:
        coin_list = await response.json()
        return coin_list


def _find_coingecko_symbol_id(coin_list, symbol):
    for coin_meta in coin_list:
        if symbol.lower() == coin_meta['symbol']:
            return coin_meta['id']


async def start_coingecko_monitors(symbols, currency, session, **kwargs):
    coin_list = await _get_coingecko_coin_list(session)

    symbol_map = {}
    for symbol in symbols:
        symbol_id = _find_coingecko_symbol_id(coin_list, symbol)
        symbol_map[symbol] = symbol_id

    monitors = [
        await CoinGeckoPriceMonitor.start(symbol, symbol_id, currency, session, **kwargs) for symbol, symbol_id in symbol_map.items()
    ]

    return monitors


@attr.s
class CoinGeckoPriceMonitor:
    """Monitors price information from coingecko's api"""
    symbol = attr.ib(type=str)
    symbol_id = attr.ib(type=str)
    currency = attr.ib(type=str)
    session = attr.ib()
    price_data = attr.ib(init=False)

    def __attrs_post_init__(self):
        self.spot_url = f"{COINBASE_API}/v2/prices/{self.symbol}-{self.currency}/spot"

    @classmethod
    async def start(cls, symbol, symbol_id, currency, session, update_interval=300, splay=True): # pylint: disable=R0913
        """init and run this monitor"""
        if splay:
            update_interval += randint(0, 120)

        price_monitor = await cls(symbol, symbol_id, currency, session).update()

        asyncio.create_task(price_monitor.monitor(update_interval))

        return price_monitor

    async def monitor(self, update_interval):
        """update self in a loop"""
        while True:
            await asyncio.sleep(update_interval)
            await self.update()

    async def update(self):
        """Fetch new price data from the CoinGecko API"""
        logging.info("Updating monitor for %s via CoinBase", self.symbol)

        params = {
            'ids': [self.symbol_id],
            'vs_currencies': self.currency,
            'include_24hr_change': 'true',
        }

        async with self.session.get(COINGECKO_PRICE_API, params=params) as response:
            price_data = await response.json()
            cur = self.currency.lower()
            cur_change = f"{cur}_24h_change"

            for coin_id, data in price_data.items():
                try:
                    price = f"{data[cur]:,.4f}"
                    change_24h = f"{data[cur_change]:.2f}%"
                except (KeyError, TypeError):
                    logging.warn(f'api data not complete for {0}: {1}', coin_id, data)
                    continue

                self.price_data = {
                    'price': price, 'change_24h': change_24h
                }

        return self

    def draw(self, canvas, cursor_pos=3, **kwargs):
        """draw this monitor to a canvas"""
        change_str = self.price_data['change_24h']
        price_str = self.price_data['price']

        change_color = _get_change_color(change_str)
        font_price = _get_price_font(price_str)

        # Draw the elements on the canvas
        graphics.DrawText(
            canvas, FONT_SYMBOL, cursor_pos, 12, DEFAULT_COLOR, self.symbol
        )

        price_x = cursor_pos + _get_change_width(FONT_SYMBOL, self.symbol)

        graphics.DrawText(canvas, font_price, price_x, 12, DEFAULT_COLOR, price_str)

        change_x = price_x + _get_change_width(font_price, price_str)

        graphics.DrawText(canvas, FONT_CHANGE, change_x, 12, change_color, change_str)

        cursor_pos = change_x + _get_change_width(FONT_CHANGE, change_str)

        return canvas, cursor_pos


async def print_value(price_monitors):
    """test print values to stdout"""
    while True:
        for price_monitor in itertools.cycle(price_monitors):
            print(json.dumps(price_monitor.price_data))

            await asyncio.sleep(2)


async def main():
    """test run some monitors"""
    async with aiohttp.ClientSession() as session:

        price_monitors = await start_coingecko_monitors(['ETH', 'SOL', 'ORCA'], 'USD', session, update_interval=30, splay=False)

        await asyncio.gather(print_value(price_monitors))


if __name__ == "__main__":
    asyncio.run(main())
