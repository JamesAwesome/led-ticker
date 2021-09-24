#!/usr/bin/env python3 -u

import sys
import itertools

import asyncio
import aiohttp

import os
import json
import argparse
import logging

from datetime import date
from datetime import timedelta

import attr

COINBASE_API = 'https://api.coinbase.com'

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

@attr.s
class AsyncPriceMonitor(object):
    symbol = attr.ib(type=str)
    currency = attr.ib(type=str)
    session = attr.ib()
    update_interval = attr.ib(type=int, default=300)
    price = attr.ib(type=float, init=False)
    yesterdays_price = attr.ib(type=float, init=False)
    change_24h = attr.ib(type=float, init=False)

    def __attrs_post_init__(self):
        self.spot_url = f'{COINBASE_API}/v2/prices/{self.symbol}-{self.currency}/spot'

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
        logger.info(f'Updating monitor for {self.symbol}')
        self.price = await self.get_spot_price()
        self.yesterdays_price = await self.get_yesterdays_price()
        self.change_24h = ((self.price - self.yesterdays_price) / self.yesterdays_price) * 100
        return self

    async def get_spot_price(self, spot_date=None):
        params = {}

        if spot_date:
            params['date'] = str(spot_date)

        async with self.session.get(self.spot_url, params=params) as response:
            price_data = await response.json()
            spot_price = float(price_data.get('data', {}).get('amount'))

        return spot_price

    async def get_yesterdays_price(self):
        yesterday = date.today() - timedelta(days = 1)
        yesterdays_price = await self.get_spot_price(spot_date=yesterday)

        return yesterdays_price


async def print_value(price_monitors):
    while True:
        for price_monitor in itertools.cycle(price_monitors):
            print(json.dumps({
                'symbol': price_monitor.symbol,
                'currency': price_monitor.currency,
                'price': f'{price_monitor.price:.4f}',
                'change_24h': f'{price_monitor.change_24h:.2f}%',
            }))

            await asyncio.sleep(1)


async def main():
    async with aiohttp.ClientSession() as session:

        price_monitors = await asyncio.gather(
            AsyncPriceMonitor.start('ETH', 'USD', session, 30),
            AsyncPriceMonitor.start('ADA', 'USD', session, 30),
            AsyncPriceMonitor.start('SUSHI', 'USD', session, 30),
        )

        await asyncio.gather(
            print_value(price_monitors)
        )

if __name__ == "__main__":
    asyncio.run(main())
