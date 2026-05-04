"""Tests for the canvas reset / fill-band helpers."""

from __future__ import annotations

import unittest.mock as mock

import pytest
from PIL import Image
from rgbmatrix import RGBMatrix, RGBMatrixOptions

from led_ticker.widgets._image_fit import (
    ALPHA_BINARIZE_THRESHOLD,
    fill_band,
    flatten_onto_black,
    reset_canvas,
)


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

    def test_fill_band_through_scaled_canvas_paints_blocks(self):
        """fill_band on a ScaledCanvas(scale=2) wrapper paints 2×2 blocks
        on the real canvas. This is the architectural property the helper
        relies on — TwoRowMessage row bands at scale=4 on the bigsign work
        only because SetPixel goes through the wrapper's block expansion."""
        from led_ticker.scaled_canvas import ScaledCanvas

        opts = RGBMatrixOptions()
        opts.cols = 16
        opts.rows = 8
        opts.chain_length = 1
        opts.parallel = 1
        real = RGBMatrix(options=opts).CreateFrameCanvas()
        # scale=2, content_height=4: _y_offset = (8 - 4*2) // 2 = 0 (no letterbox)
        wrapper = ScaledCanvas(real, scale=2, content_height=4)

        color = _StubColor(255, 0, 128)
        fill_band(wrapper, 0, 2, color)  # logical rows 0-1 → real rows 0-3 (2x2 blocks)

        # Logical row 0 fills real rows 0-1 across all 16 real cols.
        # Logical row 1 fills real rows 2-3 across all 16 real cols.
        for ry in range(0, 4):
            for rx in range(real.width):
                assert real.get_pixel(rx, ry) == (
                    255,
                    0,
                    128,
                ), f"real ({rx},{ry}) should be magenta"
        # Real rows 4-7 must be untouched (not covered by logical rows 0-1).
        for ry in range(4, real.height):
            for rx in range(real.width):
                assert real.get_pixel(rx, ry) == (
                    0,
                    0,
                    0,
                ), f"real ({rx},{ry}) should be unset"


class TestAlphaBinarization:
    """`flatten_onto_black` binarizes the alpha channel so anti-aliased
    edges don't bleed into near-black RGB. Pre-fix, edge pixels survived
    `scan_non_black` and painted a halo over scrolling text. Post-fix,
    they collapse to pure (0,0,0) and are correctly skipped.
    """

    def test_threshold_at_natural_midpoint(self):
        """Default threshold matches font binarization (50% intensity)."""
        assert ALPHA_BINARIZE_THRESHOLD == 128

    def test_alpha_above_threshold_pastes_full_color(self):
        """A yellow pixel at alpha=255 must come through unchanged."""
        rgba = Image.new("RGBA", (4, 4), (255, 255, 0, 255))
        out = flatten_onto_black(rgba, 4, 4, 0, 0)
        assert out.getpixel((0, 0)) == (255, 255, 0)

    def test_alpha_below_threshold_collapses_to_black(self):
        """A yellow pixel at alpha=20 (typical anti-aliased edge) must
        become pure (0,0,0) so `scan_non_black` skips it. Pre-fix this
        pixel would have been ~(20, 20, 0) — surviving in `_non_black`
        and painting over scrolling text behind it.
        """
        rgba = Image.new("RGBA", (4, 4), (255, 255, 0, 20))
        out = flatten_onto_black(rgba, 4, 4, 0, 0)
        assert out.getpixel((0, 0)) == (0, 0, 0)

    def test_alpha_exactly_at_threshold_pastes_opaque(self):
        """Threshold is inclusive — alpha == 128 → fully opaque."""
        rgba = Image.new("RGBA", (4, 4), (200, 100, 50, 128))
        out = flatten_onto_black(rgba, 4, 4, 0, 0)
        assert out.getpixel((0, 0)) == (200, 100, 50)

    def test_alpha_one_below_threshold_pastes_transparent(self):
        """Threshold is exclusive on the low side — alpha == 127 → off."""
        rgba = Image.new("RGBA", (4, 4), (200, 100, 50, 127))
        out = flatten_onto_black(rgba, 4, 4, 0, 0)
        assert out.getpixel((0, 0)) == (0, 0, 0)

    def test_silhouette_has_no_near_black_halo(self):
        """End-to-end shape: an opaque circle on transparent background
        should produce ONLY (0,0,0) outside the silhouette and ONLY
        non-black inside it — no intermediate edge values.
        """
        # Build a 10×10 RGBA with a sharp opaque center and
        # anti-aliased edges (alpha 0..200).
        rgba = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
        for y in range(10):
            for x in range(10):
                # A "fake anti-aliased" gradient: alpha increases toward
                # the centre. Lots of low-alpha edge pixels — the worst
                # case for the old code.
                cx, cy = 4.5, 4.5
                dist = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5
                a = max(0, int(200 - dist * 50))
                rgba.putpixel((x, y), (255, 0, 0, a))

        out = flatten_onto_black(rgba, 10, 10, 0, 0)
        # Inspect every pixel: must be either pure (0,0,0) or full red
        # (255, 0, 0). No intermediate alpha-blended values.
        seen: set[tuple[int, int, int]] = set()
        for y in range(10):
            for x in range(10):
                seen.add(out.getpixel((x, y)))
        # Subset of {(0,0,0), (255,0,0)} — no halo values like (50,0,0).
        assert seen <= {(0, 0, 0), (255, 0, 0)}, (
            f"binarized output should only have pure black or pure red "
            f"(no intermediate alpha-blended halo values); got {seen}"
        )

    def test_non_rgba_image_pastes_unchanged(self):
        """Plain RGB images skip the alpha branch entirely."""
        rgb = Image.new("RGB", (4, 4), (100, 200, 50))
        out = flatten_onto_black(rgb, 4, 4, 0, 0)
        assert out.getpixel((0, 0)) == (100, 200, 50)
