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

        monitors.extend([
            await CoinbasePriceMonitor.start(symbol, "USD", session) for symbol in coinbase_symbols
        ])

        monitors.extend(iter([await CoinGeckoPriceMonitor.start('POOL', 'pooltogether', 'USD', session)]))
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

        weather_nyc = await WeatherWidget.start(session, LocationData('40.738480', '-73.989929'), 'New York City', units='imperial', font_color=next(RANDOM_COLOR))
        weather_ord = await WeatherWidget.start(session, LocationData('41.878113', '-87.629799'), 'Chicago', units='imperial', font_color=next(RANDOM_COLOR))
        weather_lax = await WeatherWidget.start(session, LocationData('34.090679', '-118.371750'), 'Los Angeles', units='imperial', font_color=next(RANDOM_COLOR))

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
                    TickerMessage('#DevOps Squad is the best Squad', font_color=UP_TREND_COLOR),
                ],
                led_frame,
                title=TickerMessage('Hello Chief!', font_color=LIME),
                title_delay=5,
                notif_queue=notif_queue,
            ).run_forever_scroll(loop_count=1)

            await AsyncTicker(
                [
                    weather_nyc,
                    weather_ord,
                    weather_lax,
                    weather_sfo,
                ],
                led_frame,
                title=TickerMessage('Chief Flagship Weather', font_color=LIME),
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
            ["ETH", "ADA", "SOL", "DOT", "SUSHI", "COMP", "MATIC", "CRV", "GRT", "BTC", "LINK", "XLM"],
            ["ORCA", "SAMO", "AVAX"]
        )
    )
