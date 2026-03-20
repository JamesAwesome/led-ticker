"""Coinbase price monitor widget."""

import asyncio
import logging
from datetime import date, timedelta

import attrs

from led_ticker._compat import require_graphics
from led_ticker.colors import DEFAULT_COLOR, DOWN_TREND_COLOR, UP_TREND_COLOR
from led_ticker.drawing import compute_cursor, get_text_width
from led_ticker.fonts import FONT_DELTA, FONT_LABEL, FONT_VALUE, FONT_VALUE_SMALL
from led_ticker.widget import run_monitor_loop
from led_ticker.widgets import register

COINBASE_API = "https://api.coinbase.com"


def _get_change_color(change_str):
    if change_str.startswith("-"):
        return DOWN_TREND_COLOR
    return UP_TREND_COLOR


def _get_price_font(price_str):
    if len(price_str) > 10:
        return FONT_VALUE_SMALL
    return FONT_VALUE


@register("coinbase")
@attrs.define
class CoinbasePriceMonitor:
    """Crypto price monitor using the Coinbase API."""

    symbol: str
    currency: str
    session: object
    center: bool = True
    padding: int = 6
    price: float = attrs.field(init=False, default=0.0)
    yesterdays_price: float = attrs.field(init=False, default=0.0)
    change_24h: float = attrs.field(init=False, default=0.0)
    spot_url: str = attrs.field(init=False, default="")

    def __attrs_post_init__(self):
        self.spot_url = f"{COINBASE_API}/v2/prices/{self.symbol}-{self.currency}/spot"

    @classmethod
    async def start(
        cls,
        symbol,
        currency,
        session,
        update_interval=300,
        center=True,
        **kwargs,
    ):
        widget = cls(symbol=symbol, currency=currency, session=session, center=center)
        await widget.update()
        asyncio.create_task(run_monitor_loop(widget, update_interval))
        return widget

    async def update(self):
        logging.info("Updating monitor for %s via Coinbase", self.symbol)
        self.price = await self.get_spot_price()
        self.yesterdays_price = await self.get_yesterdays_price()
        if self.yesterdays_price != 0:
            self.change_24h = (
                (self.price - self.yesterdays_price) / self.yesterdays_price
            ) * 100
        else:
            self.change_24h = 0.0

    async def get_spot_price(self, spot_date=None):
        params = {}
        if spot_date:
            params["date"] = str(spot_date)
        async with self.session.get(self.spot_url, params=params) as response:
            price_data = await response.json()
            amount = price_data.get("data", {}).get("amount")
            if amount is None:
                raise KeyError("Missing 'amount' in Coinbase API response")
            return float(amount)

    async def get_yesterdays_price(self):
        yesterday = date.today() - timedelta(days=1)
        return await self.get_spot_price(spot_date=yesterday)

    def draw(self, canvas, cursor_pos=0, **kwargs):
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
            y_offset=kwargs.get("y_offset", 0),
        )


def _draw_price_ticker(
    canvas,
    symbol,
    price_str,
    change_str,
    cursor_pos=0,
    center=True,
    padding=6,
    end_padding=6,
    y_offset=0,
):
    graphics = require_graphics()
    change_color = _get_change_color(change_str)
    font_price = _get_price_font(price_str)

    content_width = sum(
        [
            get_text_width(FONT_LABEL, symbol),
            get_text_width(font_price, price_str),
            get_text_width(FONT_DELTA, change_str, padding=0),
        ]
    )

    cursor_pos, end_padding = compute_cursor(
        canvas.width, content_width, cursor_pos, end_padding, center
    )

    cursor_pos += graphics.DrawText(
        canvas, FONT_LABEL, cursor_pos, 12 + y_offset, DEFAULT_COLOR, symbol
    )
    cursor_pos += padding
    cursor_pos += graphics.DrawText(
        canvas, font_price, cursor_pos, 12 + y_offset, DEFAULT_COLOR, price_str
    )
    cursor_pos += padding
    cursor_pos += graphics.DrawText(
        canvas, FONT_DELTA, cursor_pos, 12 + y_offset, change_color, change_str
    )
    cursor_pos += end_padding

    return canvas, cursor_pos
