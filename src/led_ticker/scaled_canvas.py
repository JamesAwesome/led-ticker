"""Scaled-canvas wrapper for the bigsign rendering path.

Wraps a real `RGBMatrix` canvas. Callers always work in a 16-tall logical
canvas; the wrapper paints `scale × scale` blocks and vertically centers
the logical canvas inside the real canvas.

Used only when `scale > 1`. At `scale = 1` the existing sign uses the real
canvas directly without a wrapper.
"""

from __future__ import annotations

from typing import Any

import attrs

CONTENT_HEIGHT = 16


@attrs.define
class ScaledCanvas:
    """Wraps a real canvas; exposes a `content_height`-tall logical canvas.

    `real` is mutable so `_swap()` in ticker.py can rewire the wrapper to
    point at the new back-buffer canvas after each `SwapOnVSync`.
    `scale` and `content_height` are frozen — they're set at construction
    and never change for the lifetime of the wrapper.
    """

    real: Any
    scale: int = attrs.field(default=1, on_setattr=attrs.setters.frozen)
    content_height: int = attrs.field(
        default=CONTENT_HEIGHT, on_setattr=attrs.setters.frozen
    )

    @property
    def width(self) -> int:
        return self.real.width // self.scale

    @property
    def height(self) -> int:
        return self.content_height

    @property
    def _y_offset(self) -> int:
        return (self.real.height - self.content_height * self.scale) // 2

    def Clear(self) -> None:
        self.real.Clear()

    def Fill(self, r: int, g: int, b: int) -> None:
        """Fill the entire underlying canvas (including any letterbox).

        Used by `color_flash` and other full-canvas transition effects.
        Letterbox bands are filled too so the whole panel flashes.
        """
        self.real.Fill(r, g, b)

    def SetPixel(self, x: int, y: int, r: int, g: int, b: int) -> None:
        rx = x * self.scale
        ry = y * self.scale + self._y_offset
        for dy in range(self.scale):
            for dx in range(self.scale):
                self.real.SetPixel(rx + dx, ry + dy, r, g, b)

    def draw_bdf_text(self, bdf, x: int, y: int, color, text: str) -> int:
        """Draw `text` at logical (x, y) baseline. Returns total advance width.

        Mirrors `graphics.DrawText`: x is the left edge and y is the baseline
        (BDF glyphs draw above the baseline coordinate).
        """
        if isinstance(color, tuple):
            r, g, b = color
        else:
            r, g, b = color.red, color.green, color.blue
        cx = x
        for ch in text:
            glyph = bdf.glyphs.get(ch)
            if glyph is None:
                cx += bdf.bbx_width
                continue
            top_y = y - glyph.bbx_height - glyph.bbx_yoff
            for row_idx, row in enumerate(glyph.bitmap):
                py = top_y + row_idx
                for col_idx, bit in enumerate(row):
                    if bit:
                        self.SetPixel(cx + glyph.bbx_xoff + col_idx, py, r, g, b)
            cx += glyph.advance_width
        return cx - x
