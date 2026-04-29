"""Tests for the draw_text() dispatcher."""

from __future__ import annotations

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
