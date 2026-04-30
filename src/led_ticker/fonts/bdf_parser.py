"""Pure-Python BDF font parser for scaled rendering on the bigsign.

BDF (Bitmap Distribution Format) is a plain-text font format. We parse only
the fields we need: per-glyph bitmap, advance width, and bounding box.

The existing C font path (`graphics.DrawText`) handles `scale = 1`; this
parser backs the `scale > 1` path via `ScaledCanvas`.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field


@dataclass
class BDFGlyph:
    char: str
    bitmap: list[list[bool]]
    advance_width: int
    bbx_width: int
    bbx_height: int
    bbx_xoff: int
    bbx_yoff: int
    # Pre-computed flat list of (col, row) for set bits in `bitmap`.
    # The rasterizer iterates this directly instead of branching every
    # column — most cells in a typical glyph are unlit, so we save the
    # `if bit:` check and the enumerate() overhead per row × cell.
    lit_pixels: list[tuple[int, int]] = field(default_factory=list)


@dataclass
class BDFFont:
    bbx_width: int
    bbx_height: int
    ascent: int
    glyphs: dict[str, BDFGlyph] = field(default_factory=dict)


def parse_bdf(text: str) -> BDFFont:
    """Parse a BDF font file's text into a `BDFFont`."""
    lines: Iterator[str] = iter(text.splitlines())
    bbx_w = bbx_h = ascent = 0
    glyphs: dict[str, BDFGlyph] = {}

    for line in lines:
        parts = line.split()
        if not parts:
            continue
        key = parts[0]
        if key == "FONTBOUNDINGBOX":
            bbx_w = int(parts[1])
            bbx_h = int(parts[2])
        elif key == "FONT_ASCENT":
            ascent = int(parts[1])
        elif key == "STARTCHAR":
            glyph = _parse_glyph(lines)
            if glyph is not None:
                glyphs[glyph.char] = glyph

    return BDFFont(
        bbx_width=bbx_w,
        bbx_height=bbx_h,
        ascent=ascent,
        glyphs=glyphs,
    )


def _parse_glyph(lines: Iterator[str]) -> BDFGlyph | None:
    encoding: int | None = None
    advance = 0
    bbx_w = bbx_h = bbx_xoff = bbx_yoff = 0
    bitmap_rows: list[list[bool]] = []
    in_bitmap = False

    for line in lines:
        parts = line.split()
        if not parts:
            continue
        key = parts[0]
        if key == "ENCODING":
            encoding = int(parts[1])
        elif key == "DWIDTH":
            advance = int(parts[1])
        elif key == "BBX":
            bbx_w = int(parts[1])
            bbx_h = int(parts[2])
            bbx_xoff = int(parts[3])
            bbx_yoff = int(parts[4])
        elif key == "BITMAP":
            in_bitmap = True
        elif key == "ENDCHAR":
            break
        elif in_bitmap:
            row = _hex_row_to_bools(parts[0], bbx_w)
            bitmap_rows.append(row)

    if encoding is None or encoding < 0:
        return None

    lit_pixels: list[tuple[int, int]] = [
        (col, row)
        for row, row_bits in enumerate(bitmap_rows)
        for col, bit in enumerate(row_bits)
        if bit
    ]

    return BDFGlyph(
        char=chr(encoding),
        bitmap=bitmap_rows,
        advance_width=advance,
        bbx_width=bbx_w,
        bbx_height=bbx_h,
        bbx_xoff=bbx_xoff,
        bbx_yoff=bbx_yoff,
        lit_pixels=lit_pixels,
    )


def _hex_row_to_bools(hex_str: str, bit_count: int) -> list[bool]:
    """Convert a BDF hex row (e.g. 'A0') to a list of bools, MSB first."""
    n_hex = len(hex_str)
    value = int(hex_str, 16)
    total_bits = n_hex * 4
    bools = [(value >> (total_bits - 1 - i)) & 1 == 1 for i in range(total_bits)]
    return bools[:bit_count]
