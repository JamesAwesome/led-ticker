"""Tests for the canvas reset / fill-band helpers."""

from __future__ import annotations

import unittest.mock as mock

import pytest
from rgbmatrix import RGBMatrix, RGBMatrixOptions

from led_ticker.widgets._image_fit import fill_band, reset_canvas


class _StubColor:
    """Stand-in for graphics.Color (just RGB attrs)."""

    def __init__(self, r: int, g: int, b: int) -> None:
        self.red = r
        self.green = g
        self.blue = b


def _make_canvas(width: int = 160, height: int = 16):
    """Return a real _StubCanvas (pixel-tracking, not a Mock)."""
    opts = RGBMatrixOptions()
    opts.cols = width
    opts.rows = height
    opts.chain_length = 1
    opts.parallel = 1
    return RGBMatrix(options=opts).CreateFrameCanvas()


@pytest.fixture
def canvas():
    """Pixel-tracking stub canvas for fill_band assertions."""
    return _make_canvas()


class TestResetCanvas:
    def test_none_calls_clear(self):
        canvas = mock.Mock()
        reset_canvas(canvas, None)
        canvas.Clear.assert_called_once_with()
        canvas.Fill.assert_not_called()

    def test_color_calls_fill_with_rgb(self):
        canvas = mock.Mock()
        reset_canvas(canvas, _StubColor(10, 20, 30))
        canvas.Fill.assert_called_once_with(10, 20, 30)
        canvas.Clear.assert_not_called()

    def test_explicit_black_uses_fill_not_clear(self):
        """bg_color = (0,0,0) is 'set' — Fill(0,0,0), not Clear()."""
        canvas = mock.Mock()
        reset_canvas(canvas, _StubColor(0, 0, 0))
        canvas.Fill.assert_called_once_with(0, 0, 0)
        canvas.Clear.assert_not_called()


class TestFillBand:
    def test_fills_only_specified_rows(self, canvas):
        """fill_band(canvas, 4, 8, color) writes y in [4, 8) — not row 3, not row 8."""
        color = _StubColor(255, 0, 128)
        fill_band(canvas, 4, 8, color)

        # Rows 0-3 untouched.
        for y in range(0, 4):
            for x in range(canvas.width):
                assert canvas.get_pixel(x, y) == (0, 0, 0), f"row {y} should be unset"
        # Rows 4-7 filled.
        for y in range(4, 8):
            for x in range(canvas.width):
                assert canvas.get_pixel(x, y) == (
                    255,
                    0,
                    128,
                ), f"row {y} should be filled"
        # Row 8 untouched.
        for x in range(canvas.width):
            assert canvas.get_pixel(x, 8) == (0, 0, 0), "row 8 should be unset"

    def test_fills_full_width(self, canvas):
        color = _StubColor(50, 60, 70)
        fill_band(canvas, 0, 1, color)
        for x in range(canvas.width):
            assert canvas.get_pixel(x, 0) == (50, 60, 70)

    def test_empty_band_is_no_op(self, canvas):
        color = _StubColor(99, 99, 99)
        fill_band(canvas, 5, 5, color)  # y_end == y_start
        # Nothing painted.
        assert all(
            v == (0, 0, 0)
            for v in (
                canvas.get_pixel(x, y)
                for y in range(canvas.height)
                for x in range(canvas.width)
            )
        )
