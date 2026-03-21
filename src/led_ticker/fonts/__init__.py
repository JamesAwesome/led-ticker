"""Font loading for LED display with generic naming."""

from __future__ import annotations

import os

from led_ticker._compat import require_graphics
from led_ticker._types import Font

_graphics = require_graphics()
FONT_DIR: str = os.path.dirname(os.path.realpath(__file__))


def _load_font(filename: str) -> Font:
    font = _graphics.Font()
    font.LoadFont(os.path.join(FONT_DIR, filename))
    return font


# Generic font names (replacing crypto-specific FONT_PRICE, FONT_SYMBOL, etc.)
FONT_DEFAULT: Font = _load_font("6x12.bdf")
FONT_SMALL: Font = _load_font("5x8.bdf")
FONT_LABEL: Font = _load_font("7x13.bdf")  # was FONT_SYMBOL
FONT_VALUE: Font = FONT_DEFAULT  # alias — same as 6x12.bdf
FONT_VALUE_SMALL: Font = FONT_SMALL  # alias — same as 5x8.bdf
FONT_DELTA: Font = _load_font("6x10.bdf")  # was FONT_CHANGE
