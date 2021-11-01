#!/usr/bin/env python3 -u
"""Async Price APIs

Async price monitor widgets
"""

from datetime import date

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
