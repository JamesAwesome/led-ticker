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


class TestBlockScaleForFontSize:
    """`block_scale_for_font_size(font, font_size)` returns the integer
    block scale used by `ScaledCanvas` for BDF fonts. HiresFont always
    returns 1 (its rasterizer handles size at construction)."""

    def test_bdf_exact_multiple_returns_scale(self):
        from led_ticker.fonts import block_scale_for_font_size

        # 6x12 cell — cell_h = 12
        assert block_scale_for_font_size(FONT_DEFAULT, 12) == 1
        assert block_scale_for_font_size(FONT_DEFAULT, 24) == 2
        assert block_scale_for_font_size(FONT_DEFAULT, 36) == 3
        assert block_scale_for_font_size(FONT_DEFAULT, 48) == 4

    def test_bdf_round_down_to_nearest_multiple(self):
        from led_ticker.fonts import block_scale_for_font_size

        # 25 → 24 (scale 2); 47 → 36 (scale 3)
        assert block_scale_for_font_size(FONT_DEFAULT, 25) == 2
        assert block_scale_for_font_size(FONT_DEFAULT, 47) == 3

    def test_bdf_below_cell_height_raises(self):
        from led_ticker.fonts import block_scale_for_font_size

        with pytest.raises(ValueError, match="below cell height"):
            block_scale_for_font_size(FONT_DEFAULT, 11)

    def test_bdf_small_font_uses_smaller_cell(self):
        from led_ticker.fonts import block_scale_for_font_size

        # 5x8 cell — cell_h = 8
        assert block_scale_for_font_size(FONT_SMALL, 8) == 1
        assert block_scale_for_font_size(FONT_SMALL, 16) == 2
        # font_size = 7 < 8 → raises
        with pytest.raises(ValueError, match="below cell height"):
            block_scale_for_font_size(FONT_SMALL, 7)

    def test_hires_returns_one_regardless_of_font_size(self):
        from led_ticker.fonts import block_scale_for_font_size, resolve_font

        font = resolve_font("Inter-Regular", 24)
        assert block_scale_for_font_size(font, 24) == 1
        # HiresFont's rasterizer handled the size at construction; the
        # block_scale is always 1 (no wrap-based expansion needed).
        assert block_scale_for_font_size(font, 48) == 1
        assert block_scale_for_font_size(font, 12) == 1

    def test_bdf_zero_or_negative_raises(self):
        from led_ticker.fonts import block_scale_for_font_size

        with pytest.raises(ValueError, match="must be > 0"):
            block_scale_for_font_size(FONT_DEFAULT, 0)
        with pytest.raises(ValueError, match="must be > 0"):
            block_scale_for_font_size(FONT_DEFAULT, -5)
