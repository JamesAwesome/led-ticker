"""Unified text-drawing helper that picks the right rendering path.

For a real `RGBMatrix` canvas (existing sign), forwards to `graphics.DrawText`
unchanged. For a `ScaledCanvas` (bigsign at scale > 1), uses the pure-Python
BDF rasterizer. Call sites swap from `graphics.DrawText(...)` to
`draw_text(...)` mechanically.
"""

from __future__ import annotations

from typing import Any

from led_ticker._compat import require_graphics
from led_ticker.fonts import get_bdf_for
from led_ticker.scaled_canvas import ScaledCanvas

_graphics = require_graphics()


def draw_text(canvas: Any, font: Any, x: int, y: int, color: Any, text: str) -> int:
    """Draw `text` at (x, y) baseline. Returns total advance width."""
    if isinstance(canvas, ScaledCanvas):
        bdf = get_bdf_for(font)
        return canvas.draw_bdf_text(bdf, x, y, color, text)
    return _graphics.DrawText(canvas, font, x, y, color, text)
