"""Trend colors for crypto widgets.

These were previously global in `led_ticker.colors` but are
crypto-specific (positive/negative/neutral price movement). The
generic palette in `led_ticker.colors` should not encode crypto
semantics.

Constants are constructed lazily via PEP 562 `__getattr__` (same
pattern as `led_ticker.colors`): importing this module is a no-op
against the rgbmatrix library.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from led_ticker.colors import lazy_palette

if TYPE_CHECKING:
    from led_ticker._types import Color


_trend_palette = lazy_palette(
    {
        "UP_TREND_COLOR": (46, 200, 46),
        "DOWN_TREND_COLOR": (194, 24, 7),
        "NEUTRAL_TREND_COLOR": (180, 180, 180),
    }
)


def __getattr__(name: str) -> Color:
    return _trend_palette(name)
