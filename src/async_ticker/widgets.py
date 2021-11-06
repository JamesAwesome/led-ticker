#!/usr/bin/env python3 -u
"""Async Price APIs

Async price monitor widgets
"""

import asyncio

from copy import deepcopy
from collections import namedtuple
from datetime import date

import aiohttp
import attr
from rgbmatrix import graphics

from async_ticker.colors import (
    RGB_WHITE,
    DEFAULT_COLOR,
    UP_TREND_COLOR,
    DOWN_TREND_COLOR,
)
from async_ticker.fonts import FONT_DEFAULT, FONT_SMALL
from async_ticker.helpers import get_text_width, find_center


@attr.s
class TickerMessage:
    """An generic txt message"""

    message = attr.ib(type=str)
    font = attr.ib(default=FONT_DEFAULT)
    font_color = attr.ib(default=DEFAULT_COLOR)
    center = attr.ib(default=True)
    padding = attr.ib(type=int, default=6)

    def draw(self, canvas, cursor_pos=0, font_color=None, **kwargs):
        """draw this monitor to a canvas"""
        # Draw the elements on the canvas
        font_color = font_color if font_color else self.font_color

        change_width = get_text_width(self.font, self.message, padding=0)
        end_padding = self.padding

        if self.center:
            if change_width > canvas.width:
                cursor_pos = cursor_pos

            else:
                center_pos = find_center(canvas, change_width)
                end_padding = canvas.width - (center_pos + change_width)
                cursor_pos += center_pos

        cursor_pos += graphics.DrawText(
            canvas, self.font, cursor_pos, 12, font_color, self.message
        )

        cursor_pos += end_padding

        return canvas, cursor_pos


@attr.s
class TickerCountdown:
    """An generic countdown"""

    message = attr.ib(type=str)
    countdown_date = attr.ib()
    font = attr.ib(default=FONT_DEFAULT)
    font_color = attr.ib(default=DEFAULT_COLOR)
    center = attr.ib(default=True)
    padding = attr.ib(type=int, default=6)

    def draw(self, canvas, cursor_pos=0, font_color=None, **kwargs):
        """draw this monitor to a canvas"""
        # Draw the elements on the canvas
        today = date.today()
        days_until = (self.countdown_date - today).days

        font_color = font_color if font_color else self.font_color

        change_width = get_text_width(self.font, self.message, padding=0)
        end_padding = self.padding

        if self.center:
            if change_width > canvas.width:
                cursor_pos = cursor_pos

            else:
                center_pos = find_center(canvas, change_width)
                end_padding = canvas.width - (center_pos + change_width)
                cursor_pos += center_pos

        cursor_pos += graphics.DrawText(
            canvas, self.font, cursor_pos, 12, font_color, f'{self.message}: {days_until}'
        )

        cursor_pos += end_padding

        return canvas, cursor_pos

LocationData = namedtuple('lat', 'lon')

OPENWEATHERMAP_URL = 'https://api.openweathermap.org/data/2.5/onecall'

DEFAULT_WEATHER_PARAMS = {
    "units": "imperial",
    "exclude": [
        'minutely',
        'hourly',
        'daily',
        'alerts'
    ],
    'appid': os.getenv("OPENWEATHERMAP_API_KEY"),
}

@attr.s
class WeatherWidget:
    session = attr.ib()
    location = attr.ib(type=LocationData)
    message = attr.ib(type=str)
    units = attr.ib(type=str, default='imperial')
    font = attr.ib(default=FONT_DEFAULT)
    font_color = attr.ib(default=DEFAULT_COLOR)
    font_color_temp = attr.ib(default=RGB_WHITE)
    center = attr.ib(default=True)
    padding = attr.ib(type=int, default=6)
    unit_symbol = attr.ib(init=False)
    weather_params = attr.ib(init=False)
    current_temp = attr.ib(init=False)

    def __attrs_post_init__():
        self.weather_params = DEFAULT_WEATHER_PARAMS.deepcopy()
        self.weather_params['units'] = self.units
        self.weather_params['lat'] = self.location.lat
        self.weather_params['lon'] = self.location.lon

        if self.units == 'imperial':
            self.unit_symbol = 'f'

        if self.units == 'metric':
            self.unit_symbol = 'c'

    @classmethod
    async def start(cls, *args, **kwargs):
        """init and run this monitor"""
        update_interval = 1800
        update_interval += randint(0, 600)

        weather_monitor = await cls(**args, **kwargs).update()
        asyncio.create_task(weather_monitor.monitor(update_interval))

        return weather_monitor

    async def update(self):
        """update weather information"""
        logging.info(f"Updating weather for: {self.location}")

        async with self.session.get(OPENWEATHERMAP_URL, params=self.weather_params) as response:
            res_json = await response.json()
            self.current_temp = res_json['current']['temp']

        return self

    async def monitor(self, update_interval):
        """update self in a loop"""
        while True:
            await asyncio.sleep(update_interval)
            await self.update()

    def draw(self, canvas, cursor_pos=0, font_color=None, **kwargs):
        """draw this monitor to a canvas"""
        # Draw the elements on the canvas
        font_color = font_color if font_color else self.font_color

        change_width = get_text_width(
            self.font, f"{self.message}: {self.current_temp}{self.unit_symbol}", padding=0
        )

        end_padding = self.padding

        if self.center:
            if change_width > canvas.width:
                cursor_pos = cursor_pos

            else:
                center_pos = find_center(canvas, change_width)
                end_padding = canvas.width - (center_pos + change_width)
                cursor_pos += center_pos

        cursor_pos += graphics.DrawText(
            canvas, self.font, cursor_pos, 12, self.font_color, f'{self.message}: '
        )

        cursor_pos += graphics.DrawText(
            canvas, self.font, cursor_pos, 12, self.font_color_temp, f'{self.current_temp}{self.unit_symbol}'
        )

        cursor_pos += end_padding

        return canvas, cursor_pos
