"""Font loading for LED display with generic naming.

Each loaded font is paired with a Python-side `BDFFont` (via `get_bdf_for()`)
so the bigsign rendering path can rasterize text without going through the
C-only `graphics.DrawText`.
"""

from __future__ import annotations

import os

from led_ticker._compat import require_graphics
from led_ticker._types import Font
from led_ticker.fonts.bdf_parser import BDFFont, parse_bdf

_graphics = require_graphics()
FONT_DIR: str = os.path.dirname(os.path.realpath(__file__))

_BDF_BY_ID: dict[int, BDFFont] = {}


def _load_font(filename: str) -> Font:
    path = os.path.join(FONT_DIR, filename)
    c_font = _graphics.Font()
    c_font.LoadFont(path)
    with open(path) as f:
        bdf = parse_bdf(f.read())
    _BDF_BY_ID[id(c_font)] = bdf
    return c_font


def get_bdf_for(font: Font) -> BDFFont:
    """Return the parsed BDF data for a font previously loaded via _load_font."""
    return _BDF_BY_ID[id(font)]


# Generic font names (replacing crypto-specific FONT_PRICE, FONT_SYMBOL, etc.)
FONT_DEFAULT: Font = _load_font("6x12.bdf")
FONT_SMALL: Font = _load_font("5x8.bdf")
FONT_LABEL: Font = _load_font("7x13.bdf")  # was FONT_SYMBOL
FONT_VALUE: Font = FONT_DEFAULT  # alias — same as 6x12.bdf
FONT_VALUE_SMALL: Font = FONT_SMALL  # alias — same as 5x8.bdf
FONT_DELTA: Font = _load_font("6x10.bdf")  # was FONT_CHANGE
