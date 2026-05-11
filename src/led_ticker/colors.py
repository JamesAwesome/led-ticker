"""RGB color definitions for LED display."""

from __future__ import annotations

import itertools

from led_ticker._compat import require_graphics
from led_ticker._types import Color


def _color(r: int, g: int, b: int) -> Color:
    """Create a color, using real graphics.Color when available."""
    g_mod = require_graphics()
    return g_mod.Color(r, g, b)


RGB_WHITE: Color = _color(255, 255, 255)

DEFAULT_COLOR: Color = _color(255, 255, 0)

UP_TREND_COLOR: Color = _color(46, 139, 87)
DOWN_TREND_COLOR: Color = _color(194, 24, 7)
NEUTRAL_TREND_COLOR: Color = _color(180, 180, 180)  # gray for 0% / unknown

LIME: Color = _color(0, 255, 0)
ORANGE: Color = _color(255, 215, 0)

PURPLE: Color = _color(221, 160, 221)

RANDOM_COLOR: itertools.cycle[Color] = itertools.cycle(
    [
        PURPLE,
        LIME,
        ORANGE,
        UP_TREND_COLOR,
        DOWN_TREND_COLOR,
    ]
)
