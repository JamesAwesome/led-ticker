"""Etherscan gas price monitor widget."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Self

import aiohttp
import attrs

from led_ticker._compat import require_graphics
from led_ticker._types import Canvas, Color, DrawResult
from led_ticker.color_providers import ColorProvider, _ConstantColor
from led_ticker.colors import DEFAULT_COLOR
from led_ticker.drawing import compute_baseline, get_text_width
from led_ticker.fonts import FONT_LABEL, FONT_VALUE
from led_ticker.text_render import draw_text
from led_ticker.widget import run_monitor_loop
from led_ticker.widgets import register
from led_ticker.widgets._frame_aware import _FrameAware
from led_ticker.widgets.crypto._colors import DOWN_TREND_COLOR, UP_TREND_COLOR

ETHERSCAN_API: str = "https://api.etherscan.io/api"
GAS_BANNER: str = "Gas(gwei):"

OK_GAS_COLOR: Color | None = None  # lazy-initialized


def _get_ok_gas_color() -> Color:
    global OK_GAS_COLOR
    if OK_GAS_COLOR is None:
        graphics = require_graphics()
        OK_GAS_COLOR = graphics.Color(255, 255, 100)
    return OK_GAS_COLOR


def _get_gas_price_color(price: str) -> Color:
    try:
        gwei = float(price)
    except (ValueError, TypeError):
        return DEFAULT_COLOR
    if gwei <= 50:
        return UP_TREND_COLOR
    if gwei <= 70:
        return _get_ok_gas_color()
    return DOWN_TREND_COLOR


@register("etherscan")
@attrs.define
class EtherscanGasMonitor(_FrameAware):
    """Ethereum gas price monitor using the Etherscan API."""

    session: aiohttp.ClientSession
    api_key: str
    padding: int = 0  # no end_padding; uses hardcoded padding in segments
    hold_time: float = 0.0
    bg_color: Color | None = attrs.field(default=None, kw_only=True)
    font_color: Color | ColorProvider = attrs.field(default=None, kw_only=True)
    price_data: dict[str, str] = attrs.field(init=False, factory=dict)

    def __attrs_post_init__(self) -> None:
        if self.font_color is None:
            self.font_color = _ConstantColor(DEFAULT_COLOR)
        elif not hasattr(self.font_color, "color_for"):
            self.font_color = _ConstantColor(self.font_color)

    @classmethod
    async def start(
        cls,
        session: aiohttp.ClientSession,
        api_key: str,
        update_interval: int = 300,
        **kwargs: Any,
    ) -> Self:
        # Filter kwargs to only attrs-declared fields so unknown keys
        # (`padding`, `extra_param`, etc. — historically allowed in
        # config and silently dropped by `start()`) don't reach
        # `cls.__init__()` where attrs would raise on them.
        valid = {f.name for f in attrs.fields(cls)}
        widget = cls(
            session=session,
            api_key=api_key,
            **{k: v for k, v in kwargs.items() if k in valid},
        )
        await widget.update()
        asyncio.create_task(run_monitor_loop(widget, update_interval))
        return widget

    async def update(self) -> None:
        logging.info("Updating gas prices")
        params: dict[str, str] = {
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

    def draw(
        self,
        canvas: Canvas,
        cursor_pos: int = 0,
        *,
        y_offset: int = 0,
        font_color: Any = None,
    ) -> DrawResult:
        # FONT_LABEL and FONT_VALUE share the same canonical BDF baseline
        # (both 12-tall cells); compute once at canvas resolution.
        baseline_y = compute_baseline(FONT_LABEL, canvas, valign="center") + y_offset
        label_color = self.font_color.color_for(self.frame_for("font_color"), 0, 1)

        draw_text(canvas, FONT_LABEL, cursor_pos, baseline_y, label_color, GAS_BANNER)
        cursor_pos += get_text_width(FONT_LABEL, GAS_BANNER, padding=6, canvas=canvas)

        for price_type, price in self.price_data.items():
            price_type_msg = f"{price_type}:"
            draw_text(
                canvas,
                FONT_LABEL,
                cursor_pos,
                baseline_y,
                label_color,
                price_type_msg,
            )
            cursor_pos += get_text_width(
                FONT_LABEL, price_type_msg, padding=3, canvas=canvas
            )

            draw_text(
                canvas,
                FONT_VALUE,
                cursor_pos,
                baseline_y,
                _get_gas_price_color(price),
                price,
            )
            cursor_pos += get_text_width(FONT_VALUE, price, padding=3, canvas=canvas)

        cursor_pos += 3
        return canvas, cursor_pos
