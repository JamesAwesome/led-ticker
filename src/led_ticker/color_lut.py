"""Precomputed 360-entry full-saturation hue → Color table.

Shared by Rainbow, ColorCycle (color_providers) and RainbowChaseBorder,
ColorCycleBorder (borders) to replace per-call colorsys.hsv_to_rgb +
graphics.Color() allocations in every hot render loop.

The table is built lazily on first use (avoids import-time graphics
initialization). 360 entries at 1° resolution covers all integer-degree
hue arithmetic used by the built-in providers and border effects.
"""

import colorsys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from led_ticker._types import Color

_HUE_TABLE: list[Color] | None = None


def hue_color(hue_degrees: float) -> Color:
    """Return the precomputed Color for the given hue (0–360).

    Uses integer-degree (1°) precision — `int(hue_degrees) % 360` is the
    table index. Floating-point hues are truncated, not rounded: 119.9°
    and 119.0° both map to LUT[119]. For all built-in callers (Rainbow,
    ColorCycle, RainbowChaseBorder) the index is already an integer, so
    no precision is lost.
    """
    global _HUE_TABLE
    if _HUE_TABLE is None:
        from led_ticker._compat import require_graphics

        graphics = require_graphics()
        table: list[Color] = []
        for h in range(360):
            r, g, b = colorsys.hsv_to_rgb(h / 360.0, 1.0, 1.0)
            table.append(graphics.Color(int(r * 255), int(g * 255), int(b * 255)))
        _HUE_TABLE = table  # atomic assignment — no partial-state reads
    return _HUE_TABLE[int(hue_degrees) % 360]
