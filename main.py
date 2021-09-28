#!/usr/bin/env python3 -u
"""Program entrypoint
"""
import os
import sys

import asyncio
import logging

import aiohttp

from async_price_apis import CoinbasePriceMonitor, EtherscanGasMonitor, start_coingecko_monitors
from async_ticker import AsyncTicker
from async_widgets import TickerMessage
from frame import LedFrame


logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.DEBUG)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)


async def main(coinbase_symbols, coingecko_symbols):
    """Run the monitors and ticker"""
    led_frame = LedFrame(
        led_rows=16,
        led_cols=32,
        led_chain=5,
        led_slowdown_gpio=2,
        led_brightness=60,
    )

    async with aiohttp.ClientSession() as session:
        monitors = [TickerMessage('Test '* 10)]

        monitors.extend([
            await CoinbasePriceMonitor.start(symbol, "USD", session) for symbol in coinbase_symbols
        ])

        monitors.extend(await start_coingecko_monitors(coingecko_symbols, 'USD', session))

        gas_price_monitor = await EtherscanGasMonitor.start(
            session, api_key=os.getenv("ETHERSCAN_API_KEY")
        )

        monitors.append(gas_price_monitor)

        await AsyncTicker(monitors, led_frame).run_forever_scroll()


if __name__ == "__main__":
    asyncio.run(
        main(
            ["ETH", "BTC", "XLM", "SOL", "ADA", "COMP", "SUSHI"],
            ["ORCA", "SAMO"]
        )
    )
