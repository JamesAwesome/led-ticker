#!/usr/bin/env python3 -u
"""Program entrypoint
"""
import sys

from random import randint
import asyncio
import logging

import aiohttp

from async_price_apis import AsyncPriceMonitor
from async_ticker import AsyncTicker
from frame import LedFrame


logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.DEBUG)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)


async def main():
    """Run the monitors and ticker
    """
    led_frame = LedFrame(
        led_rows=16,
        led_cols=32,
        led_chain=5,
        led_slowdown_gpio=2,
        led_brightness=60,
    )

    async with aiohttp.ClientSession() as session:

        price_monitors = await asyncio.gather(
            AsyncPriceMonitor.start("ETH", "USD", session, 300 + randint(0, 60)),
            AsyncPriceMonitor.start("BTC", "USD", session, 300 + randint(0, 60)),
            AsyncPriceMonitor.start("XLM", "USD", session, 300 + randint(0, 60)),
            AsyncPriceMonitor.start("SOL", "USD", session, 300 + randint(0, 60)),
            AsyncPriceMonitor.start("ADA", "USD", session, 300 + randint(0, 60)),
            AsyncPriceMonitor.start("SUSHI", "USD", session, 300 + randint(0, 60)),
        )

        await AsyncTicker(price_monitors, led_frame).run_forever_scroll()


if __name__ == "__main__":
    asyncio.run(main())
