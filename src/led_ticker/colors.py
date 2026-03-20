"""RGB color definitions for LED display."""

import itertools

from led_ticker._compat import require_graphics


def _color(r, g, b):
    """Create a color, using real graphics.Color when available."""
    g_mod = require_graphics()
    return g_mod.Color(r, g, b)


RGB_WHITE = _color(255, 255, 255)

DEFAULT_COLOR = _color(255, 255, 0)

UP_TREND_COLOR = _color(46, 139, 87)
DOWN_TREND_COLOR = _color(194, 24, 7)

LIME = _color(0, 255, 0)
ORANGE = _color(255, 215, 0)

BROWN = _color(139, 69, 19)
PURPLE = _color(221, 160, 221)

RANDOM_COLOR = itertools.cycle(
    [
        PURPLE,
        LIME,
        ORANGE,
        UP_TREND_COLOR,
        DOWN_TREND_COLOR,
    ]
)
