"""Font loading for LED display with generic naming."""

import os

from led_ticker._compat import require_graphics

_graphics = require_graphics()
FONT_DIR = os.path.dirname(os.path.realpath(__file__))


def _load_font(filename):
    font = _graphics.Font()
    font.LoadFont(os.path.join(FONT_DIR, filename))
    return font


# Generic font names (replacing crypto-specific FONT_PRICE, FONT_SYMBOL, etc.)
FONT_DEFAULT = _load_font("6x12.bdf")
FONT_SMALL = _load_font("5x8.bdf")
FONT_LABEL = _load_font("7x13.bdf")  # was FONT_SYMBOL
FONT_VALUE = FONT_DEFAULT  # alias — same as 6x12.bdf
FONT_VALUE_SMALL = FONT_SMALL  # alias — same as 5x8.bdf
FONT_DELTA = _load_font("6x10.bdf")  # was FONT_CHANGE
