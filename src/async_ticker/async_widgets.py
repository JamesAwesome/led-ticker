#!/usr/bin/env python3 -u
"""Async Price APIs

Async price monitor widgets
"""
import os
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


FONT_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'fonts')
FONT_DEFAULT = graphics.Font()
FONT_DEFAULT.LoadFont(os.path.join(FONT_DIR, "6x12.bdf"))

FONT_SMALL = graphics.Font()
FONT_SMALL.LoadFont(os.path.join(FONT_DIR, "5x8.bdf"))

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

    def draw(self, canvas, cursor_pos=0, font_color=None, **kwargs):
        """draw this monitor to a canvas"""
        # Draw the elements on the canvas

        if font_color:
            font_color = font_color
        else:
            font_color = self.font_color

        change_width = _get_change_width(self.font, self.message, padding=0)
        end_padding = self.padding

        if self.center:
            if change_width > canvas.width:
                cursor_pos = cursor_pos

            else:
                center_pos = _find_center(canvas, change_width)
                end_padding = canvas.width - (center_pos + change_width)
                cursor_pos += center_pos

        cursor_pos += graphics.DrawText(
            canvas, self.font, cursor_pos, 12, font_color, self.message
        )

        cursor_pos += end_padding

        return canvas, cursor_pos
