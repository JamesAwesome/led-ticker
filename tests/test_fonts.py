"""Tests for led_ticker.fonts."""

import pytest

from led_ticker.fonts import (
    FONT_DEFAULT,
    FONT_DELTA,
    FONT_LABEL,
    FONT_SMALL,
    FONT_VALUE,
    FONT_VALUE_SMALL,
    get_bdf_for,
)
from led_ticker.fonts.bdf_parser import BDFFont


def test_font_default_char_width():
    assert FONT_DEFAULT.CharacterWidth(ord("A")) == 6


def test_font_small_char_width():
    assert FONT_SMALL.CharacterWidth(ord("A")) == 5


def test_font_label_char_width():
    # 7x13 font
    assert FONT_LABEL.CharacterWidth(ord("A")) == 7


def test_font_value_matches_default():
    # Both use 6x12.bdf
    assert FONT_VALUE.CharacterWidth(ord("X")) == FONT_DEFAULT.CharacterWidth(ord("X"))


def test_font_value_small_matches_small():
    # Both use 5x8.bdf
    assert FONT_VALUE_SMALL.CharacterWidth(ord("X")) == FONT_SMALL.CharacterWidth(
        ord("X")
    )


def test_font_delta_char_width():
    # 6x10 font
    assert FONT_DELTA.CharacterWidth(ord("A")) == 6


def test_bdf_lookup_for_each_font():
    for font in (FONT_DEFAULT, FONT_SMALL, FONT_LABEL, FONT_DELTA):
        bdf = get_bdf_for(font)
        assert isinstance(bdf, BDFFont)
        assert "A" in bdf.glyphs


def test_bdf_lookup_unknown_font_raises():
    with pytest.raises(KeyError):
        get_bdf_for(object())


def test_bdf_advance_widths_match_c_fonts():
    """The BDF advance width must agree with the C font's CharacterWidth."""
    for font in (FONT_DEFAULT, FONT_SMALL, FONT_LABEL, FONT_DELTA):
        bdf = get_bdf_for(font)
        for ch in "ABC0123 ":
            if ch in bdf.glyphs:
                assert bdf.glyphs[ch].advance_width == font.CharacterWidth(ord(ch))
