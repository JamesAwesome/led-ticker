"""Tests for the pure-Python BDF parser used by ScaledCanvas."""

from __future__ import annotations

import textwrap

from led_ticker.fonts.bdf_parser import BDFFont, parse_bdf

SYNTHETIC_BDF = textwrap.dedent(
    """\
    STARTFONT 2.1
    FONT -synthetic-3x3
    SIZE 3 75 75
    FONTBOUNDINGBOX 3 3 0 0
    STARTPROPERTIES 1
    FONT_ASCENT 3
    ENDPROPERTIES
    CHARS 1
    STARTCHAR A
    ENCODING 65
    SWIDTH 600 0
    DWIDTH 3 0
    BBX 3 3 0 0
    BITMAP
    A0
    40
    A0
    ENDCHAR
    ENDFONT
    """
)


def test_parse_synthetic_bdf_returns_bdf_font():
    font = parse_bdf(SYNTHETIC_BDF)
    assert isinstance(font, BDFFont)
    assert "A" in font.glyphs
    assert font.bbx_height == 3


def test_parse_synthetic_bdf_glyph_bitmap():
    font = parse_bdf(SYNTHETIC_BDF)
    glyph_a = font.glyphs["A"]
    # 0xA0 = 1010 0000, top 3 bits = 1, 0, 1
    # 0x40 = 0100 0000, top 3 bits = 0, 1, 0
    # 0xA0 = 1010 0000, top 3 bits = 1, 0, 1
    assert glyph_a.bitmap == [
        [True, False, True],
        [False, True, False],
        [True, False, True],
    ]


def test_parse_synthetic_bdf_advance_width():
    font = parse_bdf(SYNTHETIC_BDF)
    assert font.glyphs["A"].advance_width == 3
