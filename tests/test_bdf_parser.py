"""Tests for the pure-Python BDF parser used by ScaledCanvas."""

from __future__ import annotations

import textwrap
from pathlib import Path

from led_ticker.fonts.bdf_parser import BDFFont, parse_bdf

FONTS_DIR = Path(__file__).resolve().parents[1] / "src" / "led_ticker" / "fonts"

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


def test_parse_bundled_5x8_font():
    text = (FONTS_DIR / "5x8.bdf").read_text()
    font = parse_bdf(text)
    assert "A" in font.glyphs
    assert "0" in font.glyphs
    assert " " in font.glyphs
    assert font.bbx_width == 5
    assert font.bbx_height == 8
    assert font.glyphs["A"].advance_width == 5


def test_parse_bundled_5x8_glyph_A_bitmap():
    """Spot-check glyph A bitmap matches the BDF source."""
    text = (FONTS_DIR / "5x8.bdf").read_text()
    font = parse_bdf(text)
    bitmap = font.glyphs["A"].bitmap
    # 5x8.bdf rows for 'A':
    # 00 → 0,0,0,0,0
    # 60 → 0,1,1,0,0
    # 90 → 1,0,0,1,0
    # 90 → 1,0,0,1,0
    # F0 → 1,1,1,1,0
    # 90 → 1,0,0,1,0
    # 90 → 1,0,0,1,0
    # 00 → 0,0,0,0,0
    assert len(bitmap) == 8
    assert bitmap[0] == [False] * 5
    assert bitmap[1] == [False, True, True, False, False]
    assert bitmap[4] == [True, True, True, True, False]


def test_parse_bundled_7x13_font():
    text = (FONTS_DIR / "7x13.bdf").read_text()
    font = parse_bdf(text)
    assert font.bbx_height == 13
    assert font.bbx_width == 7
    assert font.glyphs["A"].advance_width == 7
