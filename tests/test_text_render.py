"""Tests for the draw_text() dispatcher."""

from __future__ import annotations

import unittest.mock as mock_mod

import pytest  # noqa: F401
from rgbmatrix import RGBMatrix, RGBMatrixOptions, graphics

from led_ticker.fonts import FONT_SMALL
from led_ticker.scaled_canvas import ScaledCanvas
from led_ticker.text_render import draw_text


def _real_canvas(real_w: int = 160, real_h: int = 16):
    options = RGBMatrixOptions()
    options.cols = real_w
    options.rows = real_h
    options.chain_length = 1
    matrix = RGBMatrix(options=options)
    return matrix.CreateFrameCanvas()


def test_draw_text_on_real_canvas_uses_graphics_drawtext():
    real = _real_canvas()
    color = graphics.Color(255, 0, 0)
    advance = draw_text(real, FONT_SMALL, 0, 8, color, "A")
    assert advance > 0


def test_draw_text_on_scaled_canvas_uses_bdf_path():
    real = _real_canvas(real_w=256, real_h=64)
    sc = ScaledCanvas(real, scale=4)
    advance = draw_text(sc, FONT_SMALL, 0, 8, (0, 255, 0), "A")
    assert advance == 5


class TestDrawTextDispatch:
    def test_bdf_font_with_mock_canvas_uses_graphics_DrawText(self):
        """Real C canvas (Mock proxy) goes through graphics.DrawText."""
        from led_ticker.fonts import FONT_DEFAULT
        from led_ticker.text_render import draw_text

        canvas = mock_mod.MagicMock()
        with mock_mod.patch("led_ticker.text_render._graphics") as gfx:
            gfx.DrawText.return_value = 42
            result = draw_text(canvas, FONT_DEFAULT, 0, 12, "color", "hi")
            gfx.DrawText.assert_called_once()
            assert result == 42

    def test_hires_font_dispatches_to_hires_path(self):
        """HiresFont triggers _draw_hires_text, NOT graphics.DrawText."""
        from rgbmatrix import RGBMatrix, RGBMatrixOptions
        from rgbmatrix.graphics import Color

        from led_ticker.fonts import resolve_font
        from led_ticker.scaled_canvas import ScaledCanvas
        from led_ticker.text_render import draw_text

        font = resolve_font("Inter-Regular", 24)

        opts = RGBMatrixOptions()
        opts.cols = 256
        opts.rows = 64
        opts.chain_length = 1
        opts.parallel = 1
        real = RGBMatrix(options=opts).CreateFrameCanvas()
        wrapped = ScaledCanvas(real, scale=4, content_height=16)

        with mock_mod.patch("led_ticker.text_render._graphics") as gfx:
            draw_text(wrapped, font, 0, 12, Color(255, 255, 255), "Hi")
            gfx.DrawText.assert_not_called()

        # The hires path paints to the REAL canvas at native pixels.
        # Lit pixel count should be > 0 (we drew "Hi" at 24px).
        lit = sum(
            1
            for y in range(real.height)
            for x in range(real.width)
            if real.get_pixel(x, y) != (0, 0, 0)
        )
        assert lit > 0


class TestDrawHiresText:
    def _setup_canvas(self, scale=4, content_height=16):
        from rgbmatrix import RGBMatrix, RGBMatrixOptions

        from led_ticker.scaled_canvas import ScaledCanvas

        opts = RGBMatrixOptions()
        opts.cols = 256
        opts.rows = 64
        opts.chain_length = 1
        opts.parallel = 1
        real = RGBMatrix(options=opts).CreateFrameCanvas()
        wrapped = ScaledCanvas(real, scale=scale, content_height=content_height)
        return real, wrapped

    def test_paints_to_unwrapped_real_canvas(self):
        """Hires text bypasses the wrapper's 4×4 block expansion."""
        from rgbmatrix.graphics import Color

        from led_ticker.fonts import resolve_font
        from led_ticker.text_render import draw_text

        real, wrapped = self._setup_canvas()
        font = resolve_font("Inter-Regular", 24)
        draw_text(wrapped, font, 0, 12, Color(255, 0, 0), "M")

        # Find lit red pixels and confirm they're NOT block-expanded
        # (i.e., not arranged in 4×4 grids of identical color).
        lit = [
            (x, y)
            for y in range(real.height)
            for x in range(real.width)
            if real.get_pixel(x, y) == (255, 0, 0)
        ]
        assert len(lit) > 10  # 'M' at 24px has many pixels

        # Native rendering has lit pixels at non-multiple-of-4 coords.
        # Block-expanded rendering would have lit only at x % 4 == 0
        # boundaries with each lit pixel filling a 4x4 region.
        non_block_aligned = sum(1 for x, _ in lit if x % 4 != 0)
        assert (
            non_block_aligned > 0
        ), "looks block-expanded — hires path didn't bypass wrapper"

    def test_returns_advance_width(self):
        from rgbmatrix.graphics import Color

        from led_ticker.fonts import resolve_font
        from led_ticker.text_render import draw_text

        _, wrapped = self._setup_canvas()
        font = resolve_font("Inter-Regular", 24)
        advance = draw_text(wrapped, font, 0, 12, Color(0, 255, 0), "ABC")
        # Three glyphs at 24px should advance ~30-50 real pixels total.
        assert advance > 0
        assert advance < 200  # not absurdly wide

    def test_clips_x_out_of_panel(self):
        """Glyph painted off the right edge clips silently (no crash)."""
        from rgbmatrix.graphics import Color

        from led_ticker.fonts import resolve_font
        from led_ticker.text_render import draw_text

        real, wrapped = self._setup_canvas()
        font = resolve_font("Inter-Regular", 24)
        # logical x=1000 → real x=4000 (past 256 panel_w).
        draw_text(wrapped, font, 1000, 12, Color(0, 0, 255), "ABC")
        # No pixels lit anywhere on the panel.
        for y in range(real.height):
            for x in range(real.width):
                assert real.get_pixel(x, y) == (0, 0, 0)

    def test_unknown_char_falls_back_to_question_mark(self):
        """Characters not in the rasterized set use the '?' glyph."""
        from rgbmatrix.graphics import Color

        from led_ticker.fonts import resolve_font
        from led_ticker.text_render import draw_text

        real, wrapped = self._setup_canvas()
        font = resolve_font("Inter-Regular", 24)
        # 'Ω' isn't in EXTENDED_LATIN — should render as '?'.
        draw_text(wrapped, font, 10, 12, Color(255, 255, 255), "Ω")
        lit = sum(
            1
            for y in range(real.height)
            for x in range(real.width)
            if real.get_pixel(x, y) == (255, 255, 255)
        )
        # '?' has fewer pixels than Inter's 'Ω' glyph would have, but
        # both are non-empty. Just assert SOMETHING was painted.
        assert lit > 0
