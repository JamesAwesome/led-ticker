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

# Matrix-tuned palette. Saturated where saturation lands well on the
# real panel; pastel/dark values were retired because LED matrices
# wash pastels toward white and crush near-blacks to invisible.
RED: Color = _color(255, 40, 40)
GREEN: Color = _color(46, 200, 46)
BLUE: Color = _color(40, 100, 255)
YELLOW: Color = _color(255, 220, 0)
ORANGE: Color = _color(255, 140, 0)
PURPLE: Color = _color(160, 60, 200)
CYAN: Color = _color(0, 220, 220)
PINK: Color = _color(240, 70, 200)

# Legacy constants — removed in a later task once dependents migrate:
UP_TREND_COLOR: Color = _color(46, 139, 87)
DOWN_TREND_COLOR: Color = _color(194, 24, 7)
NEUTRAL_TREND_COLOR: Color = _color(180, 180, 180)  # gray for 0% / unknown

LIME: Color = _color(0, 255, 0)

RANDOM_COLOR: itertools.cycle[Color] = itertools.cycle(
    [
        PURPLE,
        LIME,
        ORANGE,
        UP_TREND_COLOR,
        DOWN_TREND_COLOR,
    ]
)
