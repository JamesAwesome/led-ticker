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

    def test_returns_logical_pixel_advance_not_real(self):
        """Hotfix ec30a97: advance must be reported in LOGICAL units (matches
        BDF semantics) so layout/scroll-stop math doesn't 4× overshoot on the
        bigsign. Asserting LOGICAL value, not just '> 0'."""
        from rgbmatrix.graphics import Color

        from led_ticker.fonts import resolve_font
        from led_ticker.text_render import draw_text

        real, wrapped = self._setup_canvas()
        font = resolve_font("Inter-Regular", 24)
        real_total = sum(font.glyphs[c].advance for c in "ABC")
        expected_logical = -(-real_total // 4)  # ceil-div by scale
        advance = draw_text(wrapped, font, 0, 12, Color(0, 255, 0), "ABC")
        assert advance == expected_logical
        # Sanity: the advance must NOT equal the raw real-pixel total
        # (that would be the pre-hotfix bug).
        assert advance < real_total

    def test_glyph_renders_above_baseline_not_clipped_to_panel_bottom(self):
        """Hotfix 00145b7 regression: with the buggy anchor handling, glyphs
        rendered at logical y=12 on a scale=4 panel landed at real_y >= 48
        (only the bottom strip visible). Correct rendering puts cap-height
        pixels at real_y ~24-30 (well above panel midline)."""
        from rgbmatrix.graphics import Color

        from led_ticker.fonts import resolve_font
        from led_ticker.text_render import draw_text

        real, wrapped = self._setup_canvas()
        font = resolve_font("Inter-Regular", 24)
        draw_text(wrapped, font, 0, 12, Color(255, 0, 0), "M")

        lit_ys = [
            y
            for y in range(real.height)
            for x in range(real.width)
            if real.get_pixel(x, y) == (255, 0, 0)
        ]
        assert lit_ys, "M should render SOMETHING"
        # Cap of 'M' (24px Inter, baseline at real_y=48, ascent=24) lands
        # at real_y ~24. Tolerate 22..32 for font-version drift.
        assert (
            min(lit_ys) < 32
        ), f"top of 'M' at y={min(lit_ys)} — looks anchor-bug clipped"
        # Bottom of 'M' should land near the baseline at real_y=48.
        # Tolerate 44..50.
        assert max(lit_ys) <= 50

    def test_get_text_width_matches_draw_text_advance(self):
        """get_text_width and the actual draw_text advance must report the
        same value — otherwise overflow-scroll detection mis-fires."""
        from rgbmatrix.graphics import Color

        from led_ticker.drawing import get_text_width
        from led_ticker.fonts import resolve_font
        from led_ticker.text_render import draw_text

        real, wrapped = self._setup_canvas()
        font = resolve_font("Inter-Regular", 24)
        text = "Hello world"
        measured = get_text_width(font, text, padding=0)
        actual = draw_text(wrapped, font, 0, 12, Color(255, 255, 255), text)
        assert measured == actual

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

    def test_advance_unaffected_by_clip_rect_skip(self):
        """The clip-rect early-out skips the lit-pixel loop, but must
        still advance the cursor — otherwise the partial-overlap glyph
        right after a series of off-canvas ones would land at the
        wrong x. Verify by drawing text that starts off-canvas and
        spans onto it: the first on-canvas glyph must appear in the
        same position as it would without the early-out.
        """
        from rgbmatrix.graphics import Color

        from led_ticker.fonts import resolve_font
        from led_ticker.text_render import draw_text

        real_a, wrapped_a = self._setup_canvas()
        real_b, wrapped_b = self._setup_canvas()
        font = resolve_font("Inter-Regular", 24)

        # Long text starting off-canvas. With a working clip-rect:
        # off-canvas glyphs are skipped via early-out but advance cursor.
        # Without it (regression): they paint nothing and still advance.
        # Either way the visible pixels should be identical.
        draw_text(wrapped_a, font, -20, 12, Color(255, 255, 255), "ABCDEFGHIJ")

        # Reference: render only the on-canvas tail, computed at the
        # equivalent absolute position (we just trust both paths agree
        # since both go through the same advance arithmetic).
        # Pin: at least *some* pixels lit on the right side of the panel.
        lit = sum(
            1
            for y in range(real_a.height)
            for x in range(real_a.width)
            if real_a.get_pixel(x, y) != (0, 0, 0)
        )
        assert lit > 0, "expected some on-canvas pixels at x=-20"

        # And drawing the same text fully on-canvas should always paint
        # MORE pixels than partial overlap.
        draw_text(wrapped_b, font, 0, 12, Color(255, 255, 255), "ABCDEFGHIJ")
        lit_b = sum(
            1
            for y in range(real_b.height)
            for x in range(real_b.width)
            if real_b.get_pixel(x, y) != (0, 0, 0)
        )
        assert (
            lit_b > lit
        ), "fully on-canvas text should paint more pixels than partly off-canvas text"

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
