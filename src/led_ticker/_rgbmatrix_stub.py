"""Minimal stub for rgbmatrix.graphics — used when the real library isn't installed.

Provides Color, Font, and DrawText with the same API surface as the real
rgbmatrix C extension. This lets non-drawing operations (config loading,
validation, font metric queries) work on any machine without a Pi or any
PYTHONPATH tricks.

`DrawText` rasterizes BDF glyphs by reusing the same pure-Python BDF parser
that backs the bigsign rendering path — so non-Pi runs (gif renderer for
the docs site, validate path) produce visually-correct text instead of
the placeholder "horizontal band of pixels" the older stub used. Color
and bounding-box behavior matches `graphics.DrawText` (x is left edge, y
is baseline; glyphs draw above the baseline).
"""

from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from led_ticker.fonts.bdf_parser import BDFFont


class Color:
    def __init__(self, r: int = 0, g: int = 0, b: int = 0) -> None:
        self.red = r
        self.green = g
        self.blue = b

    def __repr__(self) -> str:
        return f"Color({self.red}, {self.green}, {self.blue})"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Color):
            return (self.red, self.green, self.blue) == (
                other.red,
                other.green,
                other.blue,
            )
        return NotImplemented

    def __hash__(self) -> int:
        return hash((self.red, self.green, self.blue))


class Font:
    def __init__(self) -> None:
        self._char_widths: dict[int, int] = {}
        self._default_width = 6
        self._bbx_height = 12
        # Parsed BDF data — populated by LoadFont, used by module-level
        # DrawText. None when no font has been loaded (defensive).
        self._bdf: BDFFont | None = None

    def LoadFont(self, path: str) -> None:
        # Lazy-import bdf_parser to avoid a circular import: this stub
        # is loaded by `_compat`, which is imported by every led_ticker
        # module — including `fonts/__init__.py` (which itself goes
        # through `_compat` to grab graphics). Importing the parser at
        # function-call time runs after init resolution settles.
        from led_ticker.fonts.bdf_parser import parse_bdf

        if not os.path.exists(path):
            return
        # Read once, parse once. The bdf_parser is the same one the
        # bigsign uses, so glyphs/lit_pixels are computed identically.
        with open(path) as f:
            content = f.read()
        self._bdf = parse_bdf(content)

        # CharacterWidth() reads from this dict (test stub contract).
        # Map BDFGlyph.advance_width back into the per-char width table.
        self._char_widths = {
            ord(g.char): g.advance_width for g in self._bdf.glyphs.values()
        }
        self._bbx_height = self._bdf.bbx_height
        self._default_width = self._bdf.bbx_width

        # Some legacy callers / test stubs derived the default width from
        # the filename (e.g., 6x12.bdf → 6). Preserve that for back-compat.
        m = re.match(r"(\d+)x\d+\.bdf", os.path.basename(path))
        if m:
            self._default_width = int(m.group(1))

    def CharacterWidth(self, char_code: int) -> int:
        return self._char_widths.get(char_code, self._default_width)

    @property
    def height(self) -> int:
        return self._bbx_height


def DrawText(
    canvas: Any,
    font: Font,
    x: int,
    y: int,
    color: Color,
    text: str,
) -> int:
    """Mirror `graphics.DrawText` — return the advance width and, when given
    a real canvas + RGB color, paint each lit BDF pixel with SetPixel.

    Same logic as `ScaledCanvas.draw_bdf_text` but at scale=1: x is the
    left edge, y is the baseline, glyphs draw above the baseline.
    """
    width = sum(font.CharacterWidth(ord(c)) for c in text)
    if (
        canvas is None
        or not hasattr(canvas, "SetPixel")
        or not hasattr(color, "red")
        or font._bdf is None
    ):
        return width

    r, g, b = color.red, color.green, color.blue
    set_pixel = canvas.SetPixel
    glyphs = font._bdf.glyphs
    fallback_width = font._bdf.bbx_width
    cx = int(x)
    base_y = int(y)
    for ch in text:
        glyph = glyphs.get(ch)
        if glyph is None:
            cx += fallback_width
            continue
        top_y = base_y - glyph.bbx_height - glyph.bbx_yoff
        base_x = cx + glyph.bbx_xoff
        for col, row in glyph.lit_pixels:
            set_pixel(base_x + col, top_y + row, r, g, b)
        cx += glyph.advance_width
    return width
