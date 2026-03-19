"""Tests for led_ticker.fonts."""

from led_ticker.fonts import (
    FONT_DEFAULT,
    FONT_DELTA,
    FONT_LABEL,
    FONT_SMALL,
    FONT_VALUE,
    FONT_VALUE_SMALL,
)


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
    assert (
        FONT_VALUE_SMALL.CharacterWidth(ord("X"))
        == FONT_SMALL.CharacterWidth(ord("X"))
    )


def test_font_delta_char_width():
    # 6x10 font
    assert FONT_DELTA.CharacterWidth(ord("A")) == 6
