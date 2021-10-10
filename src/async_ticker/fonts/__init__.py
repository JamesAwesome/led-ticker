#!/usr/bin/env python3

import os
from rgbmatrix import graphics

FONT_DIR = os.path.dirname(os.path.realpath(__file__))

FONT_DEFAULT = graphics.Font()
FONT_DEFAULT.LoadFont(os.path.join(FONT_DIR, "6x12.bdf"))

FONT_SMALL = graphics.Font()
FONT_SMALL.LoadFont(os.path.join(FONT_DIR, "5x8.bdf"))

FONT_SYMBOL = graphics.Font()
FONT_SYMBOL.LoadFont(os.path.join(FONT_DIR, "7x13.bdf"))

FONT_PRICE = graphics.Font()
FONT_PRICE.LoadFont(os.path.join(FONT_DIR, "6x12.bdf"))

FONT_PRICE_SMALL = graphics.Font()
FONT_PRICE_SMALL.LoadFont(os.path.join(FONT_DIR, "5x8.bdf"))

FONT_CHANGE = graphics.Font()
FONT_CHANGE.LoadFont(os.path.join(FONT_DIR, "6x10.bdf"))
