#!/usr/bin/env python3 -u
"""Program entrypoint
"""
import os
import sys
import itertools
from datetime import date

import asyncio
import logging

import aiohttp

from async_ticker.async_price_apis import CoinbasePriceMonitor, EtherscanGasMonitor, start_coingecko_monitors, CoinGeckoPriceMonitor
from async_ticker.async_news_feed import RSSFeedMonitor
from async_ticker.async_ticker import AsyncTicker
from async_ticker.widgets import TickerMessage, TickerCountdown, WeatherWidget, LocationData
from async_ticker.frame import LedFrame
from async_ticker.colors import ORANGE, UP_TREND_COLOR, RGB_WHITE, LIME, BROWN, DOWN_TREND_COLOR, RANDOM_COLOR


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

        # monitors.extend([
        #     await CoinbasePriceMonitor.start(symbol, "USD", session) for symbol in coinbase_symbols
        # ])

        feed_monitor_anime = await RSSFeedMonitor.start(session, 'https://www.animenewsnetwork.com/all/rss.xml?ann-edition=us', update_interval=3000)
        feed_monitor_nintendo = await RSSFeedMonitor.start(session, 'https://www.nintendolife.com/feeds/news', update_interval=3000)
        feed_monitor_espn = await RSSFeedMonitor.start(session, 'https://www.espn.com/espn/rss/news', update_interval=3000)

        feed_monitors = itertools.cycle([
            (feed_monitor_nintendo, TickerMessage('Nintendo Life')),
            (feed_monitor_anime, TickerMessage('Anime News Network')),
            (feed_monitor_espn, TickerMessage('ESPN Top Stories')),
        ])

        notif_queue = asyncio.PriorityQueue(maxsize=1)
        # notif_worker = asyncio.create_task(add_test_notif(notif_queue))

        while True:
            feed_monitor, feed_title = next(feed_monitors)

            await AsyncTicker(
                [
                    TickerMessage('May the Rabbit always be with you!', font_color=next(RANDOM_COLOR)),
                    TickerMessage('Always be your bunny best!', font_color=next(RANDOM_COLOR)),
                ],
                led_frame,
                title=TickerMessage('#DevOps News', font_color=next(RANDOM_COLOR)),
                title_delay=5,
                notif_queue=notif_queue,
            ).run_forever_scroll(loop_count=1)

            await AsyncTicker(
                [
                    TickerCountdown('Days Until Spring', date(2025, 3, 20), font_color=next(RANDOM_COLOR)),
                    TickerCountdown('Days Until Summer', date(2025, 6, 20), font_color=next(RANDOM_COLOR)),
                ],
                led_frame,
                title=TickerMessage('Count Downs', font_color=next(RANDOM_COLOR)),
                title_delay=5,
                notif_queue=notif_queue,
            ).run_forever_scroll(loop_count=2)

            await AsyncTicker(
                monitors,
                led_frame,
                title=TickerMessage('Cryptocurrency/USD'),
                title_delay=5,
                notif_queue=notif_queue,
            ).run_forever_scroll(loop_count=2)

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
            [],[]
        )
    )
