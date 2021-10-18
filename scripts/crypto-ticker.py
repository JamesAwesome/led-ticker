#!/usr/bin/env python3 -u
"""Program entrypoint
"""
import os
import sys
import itertools

import asyncio
import logging

import aiohttp

from async_ticker.async_price_apis import CoinbasePriceMonitor, EtherscanGasMonitor, start_coingecko_monitors
from async_ticker.async_news_feed import RSSFeedMonitor
from async_ticker.async_ticker import AsyncTicker
from async_ticker.widgets import TickerMessage
from async_ticker.frame import LedFrame
from async_ticker.colors import ORANGE


logger = logging.getLogger()
logger.setLevel(logging.INFO)
handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)

async def add_test_notif(notif_queue, sleep=30):
    logging.info('starting test notif coroutine')
    while True:
        await asyncio.sleep(sleep)
        await notif_queue.put(TickerMessage('Test Notif', center=False))
        logging.info('Added to notif queue...')


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
        monitors = []

        monitors.extend([
            await CoinbasePriceMonitor.start(symbol, "USD", session) for symbol in coinbase_symbols
        ])

        monitors.extend(await start_coingecko_monitors(coingecko_symbols, 'USD', session))

        gas_price_monitor = await EtherscanGasMonitor.start(
            session, api_key=os.getenv("ETHERSCAN_API_KEY")
        )

        monitors.extend([
            gas_price_monitor,
        ])

        feed_monitor_news = await RSSFeedMonitor.start(session, 'https://cointelegraph.com/editors_pick_rss', update_interval=3000)
        feed_monitor_altcoin = await RSSFeedMonitor.start(session, 'https://cointelegraph.com/rss/tag/altcoin', update_interval=3000)
        feed_monitor_hodl = await RSSFeedMonitor.start(session, 'https://dailyhodl.com/feed/', update_interval=3000)
        feed_monitor_coindesk = await RSSFeedMonitor.start(session, 'https://www.coindesk.com/arc/outboundfeeds/rss/?outputType=xml', update_interval=3000)


        feed_monitors = itertools.cycle([
            (feed_monitor_news, None),
            (feed_monitor_altcoin, TickerMessage('Cointelegraph.com Altcoins')),
            (feed_monitor_hodl, None),
            (feed_monitor_coindesk, None),
        ])

        notif_queue = asyncio.PriorityQueue(maxsize=1)
        # notif_worker = asyncio.create_task(add_test_notif(notif_queue))

        while True:
            feed_monitor, feed_title = next(feed_monitors)

            await AsyncTicker(
                [
                    TickerMessage('Hello Chief!'),
                ],
                led_frame,
                notif_queue=notif_queue,
            ).run_forever_scroll(loop_count=1)

            await AsyncTicker(
                monitors,
                led_frame,
                title=TickerMessage('Cryptocurrency/USD'),
                title_delay=5,
                notif_queue=notif_queue,
            ).run_forever_scroll(loop_count=2)

            await AsyncTicker(
                [
                    TickerMessage('Happy Halloween!', font_color=ORANGE)
                ],
                led_frame,
                notif_queue=notif_queue,
            ).run_forever_scroll(loop_count=1)

            await AsyncTicker.from_rss_feed(
                feed_monitor,
                led_frame,
                custom_title=feed_title,
                title_delay=5,
                notif_queue=notif_queue,
            ).run_forever_scroll(loop_count=1)


if __name__ == "__main__":
    asyncio.run(
        main(
            ["ETH", "BTC", "XLM", "SOL", "ADA", "COMP", "SUSHI"],
            ["ORCA", "SAMO"]
        )
    )
