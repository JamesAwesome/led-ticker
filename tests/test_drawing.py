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


class TestGetTextWidthHiresFont:
    def test_hires_font_sums_advances(self):
        from led_ticker.drawing import get_text_width
        from led_ticker.fonts import resolve_font

        font = resolve_font("Inter-Regular", 24)
        width = get_text_width(font, "ABC", padding=0)
        # Sum of glyph advances for A, B, C — should be positive.
        assert width > 0
        # And consistent: same call returns same result.
        assert get_text_width(font, "ABC", padding=0) == width

    def test_hires_font_padding_added(self):
        from led_ticker.drawing import get_text_width
        from led_ticker.fonts import resolve_font

        font = resolve_font("Inter-Regular", 24)
        no_pad = get_text_width(font, "X", padding=0)
        with_pad = get_text_width(font, "X", padding=6)
        assert with_pad == no_pad + 6

    def test_hires_font_empty_string(self):
        from led_ticker.drawing import get_text_width
        from led_ticker.fonts import resolve_font

        font = resolve_font("Inter-Regular", 24)
        assert get_text_width(font, "", padding=0) == 0

    def test_hires_font_unknown_char_uses_fallback(self):
        from led_ticker.drawing import get_text_width
        from led_ticker.fonts import resolve_font

        font = resolve_font("Inter-Regular", 24)
        # 'Ω' not in rasterized set — uses '?' advance.
        omega_width = get_text_width(font, "Ω", padding=0)
        question_width = get_text_width(font, "?", padding=0)
        assert omega_width == question_width

    def test_bdf_font_path_unchanged(self):
        """Existing BDF behavior preserved."""
        from led_ticker.drawing import get_text_width
        from led_ticker.fonts import FONT_DEFAULT

        # FONT_DEFAULT is 6×12 — 'A' is 6 wide.
        width = get_text_width(FONT_DEFAULT, "A", padding=0)
        assert width == 6
