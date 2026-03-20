"""Etherscan gas price monitor widget."""

import asyncio
import logging

import attrs

from led_ticker._compat import require_graphics
from led_ticker.colors import DEFAULT_COLOR, DOWN_TREND_COLOR, UP_TREND_COLOR
from led_ticker.drawing import get_text_width
from led_ticker.fonts import FONT_LABEL, FONT_VALUE
from led_ticker.widget import run_monitor_loop
from led_ticker.widgets import register

ETHERSCAN_API = "https://api.etherscan.io/api"
GAS_BANNER = "Gas(gwei):"

OK_GAS_COLOR = None  # lazy-initialized


def _get_ok_gas_color():
    global OK_GAS_COLOR
    if OK_GAS_COLOR is None:
        graphics = require_graphics()
        OK_GAS_COLOR = graphics.Color(255, 255, 100)
    return OK_GAS_COLOR


def _get_gas_price_color(price):
    if int(price) <= 50:
        return UP_TREND_COLOR
    if int(price) <= 70:
        return _get_ok_gas_color()
    return DOWN_TREND_COLOR


@register("etherscan")
@attrs.define
class EtherscanGasMonitor:
    """Ethereum gas price monitor using the Etherscan API."""

    session: object
    api_key: str
    price_data: dict = attrs.field(init=False, factory=dict)

    @classmethod
    async def start(cls, session, api_key, update_interval=300, **kwargs):
        widget = cls(session=session, api_key=api_key)
        await widget.update()
        asyncio.create_task(run_monitor_loop(widget, update_interval))
        return widget

    async def update(self):
        logging.info("Updating gas prices")
        params = {
            "module": "gastracker",
            "action": "gasoracle",
            "apikey": self.api_key,
        }
        async with self.session.get(ETHERSCAN_API, params=params) as response:
            gas_price_data = await response.json()
            result = gas_price_data.get("result")
            if not isinstance(result, dict):
                raise ValueError(
                    f"Etherscan API error: {gas_price_data.get('message', result)}"
                )
            self.price_data = {
                "Low": result["SafeGasPrice"],
                "Avg": result["ProposeGasPrice"],
                "High": result["FastGasPrice"],
            }

    def draw(self, canvas, cursor_pos=0, **kwargs):
        graphics = require_graphics()

        graphics.DrawText(
            canvas, FONT_LABEL, cursor_pos, 12, DEFAULT_COLOR, GAS_BANNER
        )
        cursor_pos += get_text_width(FONT_LABEL, GAS_BANNER)

        for price_type, price in self.price_data.items():
            price_type_msg = f"{price_type}:"
            graphics.DrawText(
                canvas, FONT_LABEL, cursor_pos, 12, DEFAULT_COLOR, price_type_msg
            )
            cursor_pos += get_text_width(FONT_LABEL, price_type_msg, padding=3)

            graphics.DrawText(
                canvas, FONT_VALUE, cursor_pos, 12, _get_gas_price_color(price), price
            )
            cursor_pos += get_text_width(FONT_VALUE, price, padding=3)

        cursor_pos += 3
        return canvas, cursor_pos
