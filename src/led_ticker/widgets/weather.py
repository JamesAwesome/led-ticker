"""Weather widget using WeatherAPI.com."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Self

import aiohttp
import attrs

from led_ticker._types import Canvas, Color, DrawResult, Font
from led_ticker.colors import DEFAULT_COLOR, RGB_WHITE
from led_ticker.drawing import compute_cursor, get_text_width
from led_ticker.fonts import FONT_DEFAULT
from led_ticker.text_render import draw_text
from led_ticker.widget import run_monitor_loop
from led_ticker.widgets import register

WEATHERAPI_URL: str = "https://api.weatherapi.com/v1/current.json"


@register("weather")
@attrs.define
class WeatherWidget:
    """Current weather display widget."""

    session: aiohttp.ClientSession
    location: str  # query string: "New York", "10001", "40.71,-74.01"
    message: str
    units: str = "imperial"
    font: Font = attrs.Factory(lambda: FONT_DEFAULT)
    font_color: Color = attrs.Factory(lambda: DEFAULT_COLOR)
    font_color_temp: Color = attrs.Factory(lambda: RGB_WHITE)
    center: bool = True
    padding: int = 6
    show_icon: bool = True
    unit_symbol: str = attrs.field(init=False, default="")
    current_temp: int = attrs.field(init=False, default=0)
    weather: str = attrs.field(init=False, default="")

    def __attrs_post_init__(self) -> None:
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
    async def start(
        cls, *args: Any, update_interval: int = 10800, **kwargs: Any
    ) -> Self:
        widget = cls(*args, **kwargs)
        try:
            await widget.update()
        except Exception:
            logging.exception(
                "Weather initial update failed for %s, will retry in background",
                widget.location,
            )
        asyncio.create_task(run_monitor_loop(widget, update_interval))
        return widget

    async def update(self) -> None:
        logging.info("Updating weather for: %s", self.location)
        api_key = os.getenv("WEATHERAPI_KEY", "")
        if not api_key:
            raise ValueError("WEATHERAPI_KEY not set. Add it to your .env file.")
        params = {
            "key": api_key,
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

    def draw(self, canvas: Canvas, cursor_pos: int = 0, **kwargs: Any) -> DrawResult:
        y_offset: int = kwargs.get("y_offset", 0)

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

        cursor_pos += draw_text(
            canvas,
            self.font,
            cursor_pos,
            12 + y_offset,
            self.font_color,
            label_text,
        )

        if self.show_icon:
            from led_ticker.widgets.weather_icons import (
                draw_weather_icon,
            )

            cursor_pos = draw_weather_icon(
                canvas,
                self.weather,
                int(cursor_pos),
                y_offset=4 + y_offset,
            )
        else:
            cursor_pos += draw_text(
                canvas,
                self.font,
                cursor_pos,
                12 + y_offset,
                self.font_color,
                f"{self.weather} ",
            )

        cursor_pos += draw_text(
            canvas,
            self.font,
            cursor_pos,
            12 + y_offset,
            self.font_color_temp,
            temp_text,
        )
        cursor_pos += end_padding

        return canvas, cursor_pos
