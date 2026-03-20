"""Weather widget using OpenWeatherMap API."""

import asyncio
import logging
import os
from collections import namedtuple
from copy import deepcopy

import attrs

from led_ticker._compat import require_graphics
from led_ticker.colors import DEFAULT_COLOR, RGB_WHITE
from led_ticker.drawing import compute_cursor, get_text_width
from led_ticker.fonts import FONT_DEFAULT
from led_ticker.widget import run_monitor_loop
from led_ticker.widgets import register

LocationData = namedtuple("LocationData", ("lat", "lon"))

OPENWEATHERMAP_URL = "https://api.openweathermap.org/data/2.5/onecall"

DEFAULT_WEATHER_PARAMS = {
    "units": "imperial",
    "exclude": ["minutely", "hourly", "daily", "alerts"],
    "appid": os.getenv("OPENWEATHERMAP_API_KEY"),
}


@register("weather")
@attrs.define
class WeatherWidget:
    """Current weather display widget."""

    session: object
    location: LocationData
    message: str
    units: str = "imperial"
    font: object = attrs.Factory(lambda: FONT_DEFAULT)
    font_color: object = attrs.Factory(lambda: DEFAULT_COLOR)
    font_color_temp: object = attrs.Factory(lambda: RGB_WHITE)
    center: bool = True
    padding: int = 6
    unit_symbol: str = attrs.field(init=False, default="")
    weather_params: dict = attrs.field(init=False, factory=dict)
    current: dict = attrs.field(init=False, factory=dict)
    current_temp: int = attrs.field(init=False, default=0)
    weather: str = attrs.field(init=False, default="")

    def __attrs_post_init__(self):
        # TOML parses location as a dict; convert to namedtuple
        if isinstance(self.location, dict):
            self.location = LocationData(**self.location)

        self.weather_params = deepcopy(DEFAULT_WEATHER_PARAMS)
        self.weather_params["units"] = self.units
        self.weather_params["lat"] = self.location.lat
        self.weather_params["lon"] = self.location.lon

        if self.units == "imperial":
            self.unit_symbol = "F"
        elif self.units == "metric":
            self.unit_symbol = "C"

    @classmethod
    async def start(cls, *args, update_interval=10800, **kwargs):
        widget = cls(*args, **kwargs)
        await widget.update()
        asyncio.create_task(run_monitor_loop(widget, update_interval))
        return widget

    async def update(self):
        logging.info("Updating weather for: %s", self.location)
        async with self.session.get(
            OPENWEATHERMAP_URL, params=self.weather_params,
        ) as response:
            res_json = await response.json()
            self.current = res_json
            self.current_temp = int(res_json["current"]["temp"])
            self.weather = res_json["current"]["weather"][0]["main"]

    def draw(self, canvas, cursor_pos=0, **kwargs):
        graphics = require_graphics()

        full_text = (
            f"{self.message}: {self.weather} "
            f"{self.current_temp}{self.unit_symbol}"
        )
        content_width = get_text_width(self.font, full_text, padding=0)
        cursor_pos, end_padding = compute_cursor(
            canvas.width, content_width, cursor_pos, self.padding, self.center
        )

        cursor_pos += graphics.DrawText(
            canvas, self.font, cursor_pos, 12, self.font_color, f"{self.message}: "
        )
        cursor_pos += graphics.DrawText(
            canvas, self.font, cursor_pos, 12, self.font_color_temp,
            f"{self.weather} {self.current_temp}{self.unit_symbol}",
        )
        cursor_pos += end_padding

        return canvas, cursor_pos
