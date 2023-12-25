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

        feed_monitor_apple = await RSSFeedMonitor.start(session, 'https://rss.applemarketingtools.com/api/v2/us/music/most-played/10/albums.rss', update_interval=3000)
        feed_monitor_nintendo = await RSSFeedMonitor.start(session, 'https://www.nintendolife.com/feeds/news', update_interval=3000)
        feed_monitor_hodl = await RSSFeedMonitor.start(session, 'https://dailyhodl.com/feed/', update_interval=3000)

        weather_lon = await WeatherWidget.start(session, LocationData('65.507200', '-0.127600'), 'London', units='metric', font_color=next(RANDOM_COLOR))
        weather_nyc = await WeatherWidget.start(session, LocationData('40.738480', '-73.989929'), 'New York City', units='imperial', font_color=next(RANDOM_COLOR))
        weather_ord = await WeatherWidget.start(session, LocationData('41.878113', '-87.629799'), 'Chicago', units='imperial', font_color=next(RANDOM_COLOR))
        weather_lax = await WeatherWidget.start(session, LocationData('34.090679', '-118.371750'), 'Los Angeles', units='imperial', font_color=next(RANDOM_COLOR))
        weather_sfx = await WeatherWidget.start(session, LocationData('37.774900', '-122.419400'), 'San Francisco', units='imperial', font_color=next(RANDOM_COLOR))

        feed_monitors = itertools.cycle([
            (feed_monitor_news, TickerMessage('Nintendo Life')),
            (feed_monitor_apple, TickerMessage('Apple | Top Albums'))
            (feed_monitor_hodl, None),
        ])

        notif_queue = asyncio.PriorityQueue(maxsize=1)
        # notif_worker = asyncio.create_task(add_test_notif(notif_queue))

        while True:
            feed_monitor, feed_title = next(feed_monitors)

            await AsyncTicker(
                [
                    TickerMessage('Speed up your Pipelines with GitLab Private Runners: https://chief.link/gitlab', font_color=next(RANDOM_COLOR)),
                    TickerMessage('Learn to make short links at: https://chief.link/shortlinks', font_color=next(RANDOM_COLOR)),
                    TickerMessage('Connect to our AWS VPC!: https://chief.link/aws-vpn', font_color=next(RANDOM_COLOR)),
                    TickerMessage('Check out DevOps Tube for how-to videos: https://chief.link/devops-tube', font_color=next(RANDOM_COLOR)),
                    TickerMessage('Log into AWS at: https://chief.link/aws-console', font_color=next(RANDOM_COLOR)),
                    TickerMessage('Terraform the world around you: https://chief.link/terraform-101', font_color=next(RANDOM_COLOR)),
                    TickerMessage('Got Tech Questions? https://chief.link/tech-support', font_color=next(RANDOM_COLOR)),
                    TickerMessage('Local Rabbit wins award for time-travel!', font_color=next(RANDOM_COLOR)),
                ],
                led_frame,
                title=TickerMessage('#DevOps News', font_color=next(RANDOM_COLOR)),
                title_delay=5,
                notif_queue=notif_queue,
            ).run_forever_scroll(loop_count=1)

            await AsyncTicker(
                [
                    TickerCountdown('Days Until Heroku Contract Expires', date(2023, 3, 27), font_color=DOWN_TREND_COLOR),
                ],
                led_frame,
                title=TickerMessage('Count Downs', font_color=next(RANDOM_COLOR)),
                title_delay=5,
                notif_queue=notif_queue,
            ).run_forever_scroll(loop_count=2)

            await AsyncTicker(
                [
                    weather_lon,
                    weather_nyc,
                    weather_ord,
                    weather_lax,
                    weather_sfx,
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
            ["ETH", "ADA", "SOL", "DOT", "SUSHI", "COMP", "MATIC", "CRV", "GRT", "BTC", "LINK", "XLM"],[],
        )
    )
