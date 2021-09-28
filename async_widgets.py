#!/usr/bin/env python3 -u
"""Async Price APIs

Async price monitor widgets
"""
import itertools
import asyncio
import logging
import json
from datetime import date, timedelta
from random import randint
import math

import aiohttp
import attr

from rgbmatrix import graphics

FONT_DEFAULT = graphics.Font()
FONT_DEFAULT.LoadFont("fonts/6x12.bdf")

FONT_SMALL = graphics.Font()
FONT_SMALL.LoadFont("fonts/5x8.bdf")

DEFAULT_COLOR = graphics.Color(255, 255, 0)
UP_TREND_COLOR = graphics.Color(46, 139, 87)
DOWN_TREND_COLOR = graphics.Color(194, 24, 7)


def _get_change_width(font_change, change_word, padding=6):
    """get the width of font text + padding"""
    change_width = (
        sum([font_change.CharacterWidth(ord(c)) for c in change_word]) + padding
    )

    return change_width


def _find_center(canvas, change_width):
    return (canvas.width / 2) - math.floor(change_width / 2)


@attr.s
class TickerMessage:
    """An generic txt message"""

    message = attr.ib(type=str)
    font = attr.ib(default=FONT_DEFAULT)
    font_color = attr.ib(default=DEFAULT_COLOR)
    center = attr.ib(default=True)
    padding = attr.ib(type=int, default=6)

    def draw(self, canvas, cursor_pos=3, ticker_mode='swap', **kwargs):
        """draw this monitor to a canvas"""
        # Draw the elements on the canvas
        if self.center and ticker_mode == 'swap':
            change_width = _get_change_width(self.font, self.message, padding=0)

            if change_width > canvas.width:
                cursor_pos = cursor_pos

            else:
                cursor_pos = (canvas.width / 2) - math.floor(change_width / 2)

        cursor_pos += graphics.DrawText(
            canvas, self.font, cursor_pos, 12, self.font_color, self.message
        )

        return canvas, (cursor_pos + self.padding)

@attr.s
class TickerTitle:
    """An generic txt message"""

    message = attr.ib(type=str)
    font = attr.ib(default=FONT_DEFAULT)
    font_color = attr.ib(default=DEFAULT_COLOR)
    center = attr.ib(default=True)
    transition = attr.ib(default='scroll_left')
    padding = attr.ib(default=6)

    async def run(self, frame, canvas, hold_time=3):
        """Swap between all running monitors"""
        logging.info("Running title with hold time %s...", hold_time)

        # Figure out where pos should be
        change_width = _get_change_width(self.font, self.message, padding=0)

        # Default position
        pos = 3
        if self.center:
            if change_width > canvas.width:
                pos = 3
            else:
                pos = _find_center(canvas, change_width)

        canvas, cursor_pos = self.draw(canvas, pos, center=self.center)

        if (cursor_pos + 3) > canvas.width:
            frame.matrix.SwapOnVSync(canvas)
            await asyncio.sleep(2)

        while (cursor_pos + 3) > canvas.width:
            canvas.Clear()
            pos -= 1
            canvas, cursor_pos = self.draw(canvas, pos)
            await asyncio.sleep(0.05)
            frame.matrix.SwapOnVSync(canvas)

        frame.matrix.SwapOnVSync(canvas)
        await asyncio.sleep(hold_time)

        if self.transition == 'scroll_left':
            while cursor_pos + change_width > 0:
                canvas.Clear()
                pos -= 1
                canvas, cursor_pos = self.draw(canvas, pos, center=False)
                await asyncio.sleep(0.05)
                frame.matrix.SwapOnVSync(canvas)

        canvas.Clear()

        return canvas, cursor_pos

    def draw(self, canvas, cursor_pos=3, **kwargs):
        """draw this monitor to a canvas"""
        # Draw the elements on the canvas

        cursor_pos += graphics.DrawText(
            canvas, self.font, cursor_pos, 12, self.font_color, self.message
        )

        return canvas, (cursor_pos + self.padding)
