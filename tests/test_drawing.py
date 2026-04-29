"""Tests for led_ticker.drawing helpers."""

from led_ticker.drawing import Region, compute_cursor, find_center, get_text_width
from led_ticker.fonts import FONT_DEFAULT


def test_region_full_canvas_defaults():
    r = Region(0, 0, 160, 16)
    assert r.x == 0
    assert r.y == 0
    assert r.width == 160
    assert r.height == 16


def test_region_subregion():
    r = Region(10, 4, 80, 8)
    assert r.x == 10
    assert r.y == 4
    assert r.width == 80
    assert r.height == 8


def test_get_text_width_with_padding():
    assert get_text_width(FONT_DEFAULT, " ") == 12  # 6px char + 6px padding


def test_get_text_width_no_padding():
    assert get_text_width(FONT_DEFAULT, " ", padding=0) == 6


def test_get_text_width_multi_char():
    assert get_text_width(FONT_DEFAULT, "abc", padding=0) == 18  # 3 * 6px


def test_find_center():
    assert find_center(160, 6) == 77.0


def test_find_center_wide_content():
    assert find_center(160, 160) == 0.0


def test_compute_cursor_centered():
    cursor, end_pad = compute_cursor(
        canvas_width=160, content_width=100, cursor_pos=0, padding=6, center=True
    )
    # center_pos = 160/2 - floor(100/2) = 80 - 50 = 30
    assert cursor == 30
    assert end_pad == 160 - (30 + 100)  # 30


def test_compute_cursor_not_centered():
    cursor, end_pad = compute_cursor(
        canvas_width=160, content_width=100, cursor_pos=0, padding=6, center=False
    )
    assert cursor == 0
    assert end_pad == 6


def test_compute_cursor_overflow_stays_at_cursor():
    """When content is wider than canvas, centering is skipped."""
    cursor, end_pad = compute_cursor(
        canvas_width=160, content_width=200, cursor_pos=5, padding=6, center=True
    )
    assert cursor == 5
    assert end_pad == 6
