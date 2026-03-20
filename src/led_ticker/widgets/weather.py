"""Weather widget using WeatherAPI.com."""

import asyncio
import logging
import os

import attrs

from led_ticker._compat import require_graphics
from led_ticker.colors import DEFAULT_COLOR, RGB_WHITE
from led_ticker.drawing import compute_cursor, get_text_width
from led_ticker.fonts import FONT_DEFAULT
from led_ticker.widget import run_monitor_loop
from led_ticker.widgets import register

WEATHERAPI_URL = "https://api.weatherapi.com/v1/current.json"
WEATHERAPI_KEY = os.getenv("WEATHERAPI_KEY", "")


@register("weather")
@attrs.define
class WeatherWidget:
    """Current weather display widget."""

    session: object
    location: str  # query string: "New York", "10001", "40.71,-74.01"
    message: str
    units: str = "imperial"
    font: object = attrs.Factory(lambda: FONT_DEFAULT)
    font_color: object = attrs.Factory(lambda: DEFAULT_COLOR)
    font_color_temp: object = attrs.Factory(lambda: RGB_WHITE)
    center: bool = True
    padding: int = 6
    show_icon: bool = True
    unit_symbol: str = attrs.field(init=False, default="")
    current_temp: int = attrs.field(init=False, default=0)
    weather: str = attrs.field(init=False, default="")

    def __attrs_post_init__(self):
        # Support dict location from TOML: {lat = 40.71, lon = -74.01}
        if isinstance(self.location, dict):
            lat = self.location.get("lat", 0)
            lon = self.location.get("lon", 0)
            self.location = f"{lat},{lon}"

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
        params = {
            "key": WEATHERAPI_KEY,
            "q": self.location,
        }
        async with self.session.get(
            WEATHERAPI_URL,
            params=params,
        ) as response:
            data = await response.json()

            # WeatherAPI returns {"error": {...}} on failure
            if "error" in data:
                code = data["error"].get("code", "?")
                msg = data["error"].get("message", "Unknown error")
                raise ValueError(f"WeatherAPI error {code}: {msg}")

            current = data["current"]
            if self.units == "imperial":
                self.current_temp = int(current["temp_f"])
            else:
                self.current_temp = int(current["temp_c"])
            self.weather = current["condition"]["text"]

    def draw(self, canvas, cursor_pos=0, **kwargs):
        graphics = require_graphics()

        temp_text = f"{self.current_temp}{self.unit_symbol}"
        if self.show_icon:
            label_text = f"{self.message}: "
            # Icon replaces the condition text
            full_width = (
                get_text_width(self.font, label_text, padding=0)
                + 10  # icon width (8) + padding (2)
                + get_text_width(self.font, temp_text, padding=0)
            )
        else:
            label_text = f"{self.message}: "
            condition_text = f"{self.weather} "
            full_width = get_text_width(
                self.font,
                f"{label_text}{condition_text}{temp_text}",
                padding=0,
            )

        cursor_pos, end_padding = compute_cursor(
            canvas.width,
            full_width,
            cursor_pos,
            self.padding,
            self.center,
        )

        cursor_pos += graphics.DrawText(
            canvas,
            self.font,
            cursor_pos,
            12,
            self.font_color,
            label_text,
        )

        if self.show_icon:
            from led_ticker.widgets.weather_icons import (
                draw_weather_icon,
            )

            cursor_pos = draw_weather_icon(
                canvas, self.weather, int(cursor_pos),
            )
        else:
            cursor_pos += graphics.DrawText(
                canvas,
                self.font,
                cursor_pos,
                12,
                self.font_color,
                f"{self.weather} ",
            )

        cursor_pos += graphics.DrawText(
            canvas,
            self.font,
            cursor_pos,
            12,
            self.font_color_temp,
            temp_text,
        )
        cursor_pos += end_padding

        return canvas, cursor_pos
