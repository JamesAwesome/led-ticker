#!/usr/bin/env python3

import itertools

from rgbmatrix import graphics


RGB_WHITE = graphics.Color(255, 255, 255)

DEFAULT_COLOR = graphics.Color(255, 255, 0)

UP_TREND_COLOR = graphics.Color(46, 139, 87)
DOWN_TREND_COLOR = graphics.Color(194, 24, 7)

LIME =  graphics.Color(0, 255, 0)
ORANGE = graphics.Color(255, 215, 0)

BROWN = graphics.Color(139, 69, 19)
PURPLE = graphics.Color(230, 230, 250)
RANDOM_COLOR = itertools.cycle([
    PURPLE,
    LIME,
    ORANGE,
    UP_TREND_COLOR,
    DOWN_TREND_COLOR,
])
