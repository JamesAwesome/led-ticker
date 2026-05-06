"""Weather widget using WeatherAPI.com."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Self

import aiohttp
import attrs

from led_ticker._types import Canvas, Color, DrawResult, Font
from led_ticker.color_providers import ColorProvider, _ConstantColor
from led_ticker.colors import DEFAULT_COLOR, RGB_WHITE
from led_ticker.drawing import compute_baseline, compute_cursor, get_text_width
from led_ticker.fonts import FONT_DEFAULT
from led_ticker.text_render import draw_text, draw_text_per_char
from led_ticker.widget import run_monitor_loop
from led_ticker.widgets import register
from led_ticker.widgets._frame_aware import _FrameAware

WEATHERAPI_URL: str = "https://api.weatherapi.com/v1/current.json"


@register("weather")
@attrs.define
class WeatherWidget(_FrameAware):
    """Current weather display widget."""

    session: aiohttp.ClientSession
    location: str  # query string: "New York", "10001", "40.71,-74.01"
    message: str
    units: str = "imperial"
    font: Font = attrs.Factory(lambda: FONT_DEFAULT)
    font_color: Color | ColorProvider = attrs.Factory(lambda: DEFAULT_COLOR)
    # WeatherWidget keeps two color knobs: `font_color` for the label
    # (e.g. "Brooklyn:") and `font_color_temp` for the temperature
    # value (e.g. "64°F"). They're separate so a config can color the
    # label with an effect (`font_color = "rainbow"`) while keeping
    # the temp value in a steady high-contrast color (default white).
    # If you want the temp to also use the effect, set them both:
    #   font_color = "rainbow"
    #   font_color_temp = "rainbow"
    font_color_temp: Color | ColorProvider = attrs.Factory(lambda: RGB_WHITE)
    bg_color: Color | None = attrs.field(default=None, kw_only=True)
    center: bool = True
    padding: int = 6
    show_icon: bool = True
    unit_symbol: str = attrs.field(init=False, default="")
    current_temp: int = attrs.field(init=False, default=0)
    weather: str = attrs.field(init=False, default="")

    def __attrs_post_init__(self) -> None:
        # Coerce raw graphics.Color into _ConstantColor for uniform
        # provider dispatch in draw(). _build_widget already does this
        # for TOML configs; this handles direct construction (test
        # paths, programmatic instantiation).
        if not hasattr(self.font_color, "color_for"):
            self.font_color = _ConstantColor(self.font_color)
        if not hasattr(self.font_color_temp, "color_for"):
            self.font_color_temp = _ConstantColor(self.font_color_temp)

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
        label_text = f"{self.message}: "

        # Resolve the icon slug once and read its actual rendered footprint
        # via `measure_emoji_at` — keeps layout in sync with whichever
        # variant `draw_emoji_at` will pick (lowres on plain canvas,
        # hires-when-available on a ScaledCanvas, falling back to lowres
        # for slugs without a HIRES_REGISTRY entry like `partly_cloudy`).
        # Reading the footprint dynamically scales correctly across
        # per-section `scale` overrides — at scale=2 a hires sprite is 16
        # logical wide, and a hardcoded `8` here would let the temperature
        # text overlap the icon.
        if self.show_icon:
            from led_ticker.pixel_emoji import measure_emoji_at
            from led_ticker.widgets.weather_icons import _match_condition

            content_width = (
                get_text_width(self.font, label_text, padding=0, canvas=canvas)
                + measure_emoji_at(canvas, _match_condition(self.weather))
                + get_text_width(self.font, temp_text, padding=0, canvas=canvas)
            )
        else:
            condition_text = f"{self.weather} "
            content_width = get_text_width(
                self.font,
                f"{label_text}{condition_text}{temp_text}",
                padding=0,
                canvas=canvas,
            )

        cursor_pos, end_padding = compute_cursor(
            canvas.width,
            content_width,
            cursor_pos,
            self.padding,
            self.center,
        )

        baseline_y = compute_baseline(self.font, canvas, valign="center") + y_offset

        cursor_pos += self._draw_segment(
            canvas, cursor_pos, baseline_y, self.font_color, label_text
        )

        if self.show_icon:
            from led_ticker.pixel_emoji import draw_emoji_at
            from led_ticker.widgets.weather_icons import _match_condition

            # Anchor the 8-row-tall emoji's bottom to the text baseline,
            # matching `draw_with_emoji`'s unified formula (`iy = y - 8`).
            # For BDF this evaluates to 4 (matching the legacy hardcoded
            # value); for HiresFont it tracks the shifted baseline so
            # the icon stays on the same line as the text.
            cursor_pos += draw_emoji_at(
                canvas,
                _match_condition(self.weather),
                int(cursor_pos),
                baseline_y - 8,
            )
        else:
            cursor_pos += self._draw_segment(
                canvas, cursor_pos, baseline_y, self.font_color, f"{self.weather} "
            )

        cursor_pos += self._draw_segment(
            canvas, cursor_pos, baseline_y, self.font_color_temp, temp_text
        )
        cursor_pos += end_padding

        return canvas, cursor_pos

    def _draw_segment(
        self,
        canvas: Canvas,
        x: int,
        baseline_y: int,
        provider: ColorProvider,
        text: str,
    ) -> int:
        """Render one weather text segment (label / condition / temp).

        Per-char providers (rainbow / gradient) iterate chars via
        `draw_text_per_char` so each char renders with its own hue.
        Whole-string providers (constant / color_cycle / random)
        materialize once and use `draw_text`. Mirrors the per-char
        dispatch in `TickerCountdown.draw` and image widgets'
        `_draw_text` — without it, `font_color = "rainbow"` on
        weather collapsed the label / condition / temp to a single
        sweeping hue.
        """
        if provider.per_char:
            return draw_text_per_char(
                canvas,
                self.font,
                x,
                baseline_y,
                text,
                lambda idx, total: provider.color_for(self._frame_count, idx, total),
            )
        color = provider.color_for(self._frame_count, 0, len(text) if text else 1)
        return draw_text(canvas, self.font, x, baseline_y, color, text)
