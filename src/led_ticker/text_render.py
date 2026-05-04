"""Unified text-drawing helper that picks the right rendering path.

For a real `RGBMatrix` canvas (existing sign), forwards to `graphics.DrawText`
unchanged. For a `ScaledCanvas` (bigsign at scale > 1), uses the pure-Python
BDF rasterizer. For a `HiresFont`, uses the per-glyph hi-res renderer
that paints to the unwrapped real canvas at native physical resolution.
"""

from __future__ import annotations

from typing import Any

from led_ticker._compat import require_graphics
from led_ticker.fonts import get_bdf_for
from led_ticker.fonts.hires_loader import HiresFont
from led_ticker.scaled_canvas import ScaledCanvas, unwrap_to_real

_graphics = require_graphics()


def draw_text(canvas: Any, font: Any, x: int, y: int, color: Any, text: str) -> int:
    """Draw `text` at (x, y) baseline. Returns total advance width."""
    if isinstance(font, HiresFont):
        return _draw_hires_text(canvas, font, x, y, color, text)
    if isinstance(canvas, ScaledCanvas):
        bdf = get_bdf_for(font)
        return canvas.draw_bdf_text(bdf, x, y, color, text)
    return _graphics.DrawText(canvas, font, x, y, color, text)


def _draw_hires_text(
    canvas: Any, font: HiresFont, x: int, y: int, color: Any, text: str
) -> int:
    """Paint hi-res glyphs at native physical resolution.

    `(x, y)` are LOGICAL coords (consistent with BDF callers). The
    renderer multiplies by canvas scale (and adds the wrapper's
    y-offset) to get real pixel coords, then paints glyph pixels
    directly to the unwrapped real canvas — bypasses the wrapper's
    4×4 block expansion. Out-of-bounds pixels clip silently.
    """
    real = unwrap_to_real(canvas)
    scale = getattr(canvas, "scale", 1)
    y_offset = getattr(canvas, "_y_offset", 0)
    real_baseline_y = y * scale + y_offset
    real_x = x * scale

    set_px = real.SetPixel
    panel_w = real.width
    panel_h = real.height
    r, g, b = color.red, color.green, color.blue

    cursor_x = real_x
    fallback = font.glyphs.get("?")
    for ch in text:
        glyph = font.glyphs.get(ch, fallback)
        if glyph is None:
            continue
        gx0 = cursor_x + glyph.bearing_x
        gy0 = real_baseline_y - glyph.bearing_y
        for dx, dy in glyph.lit:
            px = gx0 + dx
            py = gy0 + dy
            if 0 <= px < panel_w and 0 <= py < panel_h:
                set_px(px, py, r, g, b)
        cursor_x += glyph.advance
    return cursor_x - real_x
