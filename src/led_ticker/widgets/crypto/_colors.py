"""Trend colors for crypto widgets.

These were previously global in `led_ticker.colors` but are
crypto-specific (positive/negative/neutral price movement). The
generic palette in `led_ticker.colors` should not encode crypto
semantics.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from led_ticker.colors import make_color

if TYPE_CHECKING:
    from led_ticker._types import Color


UP_TREND_COLOR: Color = make_color(46, 200, 46)
DOWN_TREND_COLOR: Color = make_color(194, 24, 7)
NEUTRAL_TREND_COLOR: Color = make_color(180, 180, 180)
