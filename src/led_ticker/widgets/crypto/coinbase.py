"""Coinbase price monitor widget."""

from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta
from typing import Any, Self

import aiohttp
import attrs

from led_ticker._types import Canvas, Color, DrawResult, Font
from led_ticker.color_providers import ColorProvider, _ConstantColor
from led_ticker.colors import DEFAULT_COLOR
from led_ticker.drawing import compute_baseline, compute_cursor, get_text_width
from led_ticker.fonts import FONT_DELTA, FONT_LABEL, FONT_VALUE, FONT_VALUE_SMALL
from led_ticker.text_render import draw_text
from led_ticker.widget import run_monitor_loop
from led_ticker.widgets import register
from led_ticker.widgets._frame_aware import _FrameAware
from led_ticker.widgets.crypto._colors import (
    DOWN_TREND_COLOR,
    NEUTRAL_TREND_COLOR,
    UP_TREND_COLOR,
)

COINBASE_API: str = "https://api.coinbase.com"


def _get_change_color(change_str: str) -> Color:
    try:
        value = float(change_str.rstrip("%"))
    except (ValueError, AttributeError):
        return NEUTRAL_TREND_COLOR
    if value < 0:
        return DOWN_TREND_COLOR
    if value > 0:
        return UP_TREND_COLOR
    return NEUTRAL_TREND_COLOR


def _get_price_font(price_str: str) -> Font:
    if len(price_str) > 10:
        return FONT_VALUE_SMALL
    return FONT_VALUE


@register("coinbase")
@attrs.define
class CoinbasePriceMonitor(_FrameAware):
    """Crypto price monitor using the Coinbase API."""

    symbol: str
    currency: str
    session: aiohttp.ClientSession
    center: bool = True
    padding: int = 6
    hold_time: float = 0.0
    bg_color: Color | None = attrs.field(default=None, kw_only=True)
    font_color: Color | ColorProvider = attrs.field(default=None, kw_only=True)
    price: float = attrs.field(init=False, default=0.0)
    yesterdays_price: float = attrs.field(init=False, default=0.0)
    change_24h: float = attrs.field(init=False, default=0.0)
    spot_url: str = attrs.field(init=False, default="")

    def __attrs_post_init__(self) -> None:
        self.spot_url = f"{COINBASE_API}/v2/prices/{self.symbol}-{self.currency}/spot"
        if self.font_color is None:
            self.font_color = _ConstantColor(DEFAULT_COLOR)
        elif not hasattr(self.font_color, "color_for"):
            self.font_color = _ConstantColor(self.font_color)

    @classmethod
    async def start(
        cls,
        symbol: str,
        currency: str,
        session: aiohttp.ClientSession,
        update_interval: int = 300,
        center: bool = True,
        **kwargs: Any,
    ) -> Self:
        # Filter kwargs to only attrs-declared fields so unknown keys
        # (historically allowed in config and silently dropped by
        # `start()`) don't reach `cls.__init__()` where attrs would
        # raise on them.
        valid = {f.name for f in attrs.fields(cls)}
        widget = cls(
            symbol=symbol,
            currency=currency,
            session=session,
            center=center,
            **{k: v for k, v in kwargs.items() if k in valid},
        )
        await widget.update()
        asyncio.create_task(run_monitor_loop(widget, update_interval))
        return widget

    async def update(self) -> None:
        logging.info("Updating monitor for %s via Coinbase", self.symbol)
        self.price = await self.get_spot_price()
        self.yesterdays_price = await self.get_yesterdays_price()
        if self.yesterdays_price != 0:
            self.change_24h = (
                (self.price - self.yesterdays_price) / self.yesterdays_price
            ) * 100
        else:
            self.change_24h = 0.0

    async def get_spot_price(self, spot_date: date | None = None) -> float:
        params: dict[str, str] = {}
        if spot_date:
            params["date"] = str(spot_date)
        async with self.session.get(self.spot_url, params=params) as response:
            price_data = await response.json()
            amount = price_data.get("data", {}).get("amount")
            if amount is None:
                raise KeyError("Missing 'amount' in Coinbase API response")
            return float(amount)

    async def get_yesterdays_price(self) -> float:
        yesterday = date.today() - timedelta(days=1)
        return await self.get_spot_price(spot_date=yesterday)

    def draw(
        self,
        canvas: Canvas,
        cursor_pos: int = 0,
        *,
        y_offset: int = 0,
        font_color: Any = None,
    ) -> DrawResult:
        change_str = f"{self.change_24h:.2f}%"
        price_str = f"{self.price:.4f}"
        return _draw_price_ticker(
            canvas,
            self.symbol,
            price_str,
            change_str,
            cursor_pos=cursor_pos,
            center=self.center,
            padding=self.padding,
            end_padding=self.padding,
            y_offset=y_offset,
            font_color=self.font_color,
            frame_count=self.frame_for("font_color"),
        )


def _draw_price_ticker(
    canvas: Canvas,
    symbol: str,
    price_str: str,
    change_str: str,
    cursor_pos: int = 0,
    center: bool = True,
    padding: int = 6,
    end_padding: int = 6,
    y_offset: int = 0,
    font_color: ColorProvider | None = None,
    frame_count: int = 0,
) -> DrawResult:
    change_color = _get_change_color(change_str)
    font_price = _get_price_font(price_str)
    label_color = (
        font_color.color_for(frame_count, 0, 1)
        if font_color is not None
        else DEFAULT_COLOR
    )

    content_width = (
        get_text_width(FONT_LABEL, symbol, padding=6, canvas=canvas)
        + get_text_width(font_price, price_str, padding=6, canvas=canvas)
        + get_text_width(FONT_DELTA, change_str, padding=0, canvas=canvas)
    )

    cursor_pos, end_padding = compute_cursor(
        canvas.width, content_width, cursor_pos, end_padding, center
    )

    baseline_y = compute_baseline(FONT_LABEL, canvas, valign="center") + y_offset
    cursor_pos += draw_text(
        canvas, FONT_LABEL, cursor_pos, baseline_y, label_color, symbol
    )
    cursor_pos += padding
    cursor_pos += draw_text(
        canvas, font_price, cursor_pos, baseline_y, label_color, price_str
    )
    cursor_pos += padding
    cursor_pos += draw_text(
        canvas, FONT_DELTA, cursor_pos, baseline_y, change_color, change_str
    )
    cursor_pos += end_padding

    return canvas, cursor_pos
