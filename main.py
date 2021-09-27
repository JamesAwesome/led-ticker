#!/usr/bin/env python3 -u
"""Program entrypoint
"""
import os
import sys

import asyncio
import logging

import aiohttp

from async_price_apis import AsyncPriceMonitor, AsyncGasMonitor
from async_ticker import AsyncTicker
from frame import LedFrame


logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.DEBUG)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)


async def main(tickers):
    """Run the monitors and ticker"""
    led_frame = LedFrame(
        led_rows=16,
        led_cols=32,
        led_chain=5,
        led_slowdown_gpio=2,
        led_brightness=60,
    )

    async with aiohttp.ClientSession() as session:
        price_monitors = [
            await AsyncPriceMonitor.start(ticker, "USD", session) for ticker in tickers
        ]

        gas_price_monitor = await AsyncGasMonitor.start(
            session, api_key=os.getenv("ETHERSCAN_API_KEY")
        )
        price_monitors.append(gas_price_monitor)

        await AsyncTicker(price_monitors, led_frame).run_forever_scroll()


if __name__ == "__main__":
    asyncio.run(
        main(
            [
                "ETH",
                "BTC",
                "XLM",
                "SOL",
                "ORCA",
                "ADA",
                "COMP",
                "SUSHI",
            ]
        )
    )
