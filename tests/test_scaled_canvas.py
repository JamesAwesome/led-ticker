"""Tests for the ScaledCanvas wrapper used by the bigsign rendering path."""

from __future__ import annotations

from rgbmatrix import RGBMatrix, RGBMatrixOptions

from led_ticker.scaled_canvas import ScaledCanvas


def _make_real_canvas(real_w: int = 256, real_h: int = 64):
    options = RGBMatrixOptions()
    options.cols = real_w
    options.rows = real_h
    options.chain_length = 1
    matrix = RGBMatrix(options=options)
    return matrix.CreateFrameCanvas()


def test_logical_dimensions_at_scale_4():
    real = _make_real_canvas(real_w=256, real_h=64)
    sc = ScaledCanvas(real, scale=4)
    assert sc.width == 64  # 256 // 4
    assert sc.height == 16
    assert sc.scale == 4


def test_logical_dimensions_at_scale_2_letterbox():
    real = _make_real_canvas(real_w=256, real_h=64)
    sc = ScaledCanvas(real, scale=2)
    assert sc.width == 128
    assert sc.height == 16


def test_setpixel_paints_block_at_scale_4_no_letterbox():
    real = _make_real_canvas(real_w=256, real_h=64)
    sc = ScaledCanvas(real, scale=4)
    sc.SetPixel(0, 0, 255, 0, 0)
    # y_offset = (64 - 16*4) // 2 = 0; paint a 4x4 block at real (0,0)..(3,3)
    for y in range(4):
        for x in range(4):
            assert real.get_pixel(x, y) == (255, 0, 0)
    # Outside the block: still black
    assert real.get_pixel(4, 0) == (0, 0, 0)
    assert real.get_pixel(0, 4) == (0, 0, 0)


def test_setpixel_centers_at_scale_2():
    real = _make_real_canvas(real_w=256, real_h=64)
    sc = ScaledCanvas(real, scale=2)
    # y_offset = (64 - 16*2) // 2 = 16
    sc.SetPixel(0, 0, 255, 0, 0)
    # 2x2 block at real (0, 16)..(1, 17)
    assert real.get_pixel(0, 16) == (255, 0, 0)
    assert real.get_pixel(1, 17) == (255, 0, 0)
    # Above and below the block: black (letterbox)
    assert real.get_pixel(0, 15) == (0, 0, 0)
    assert real.get_pixel(0, 18) == (0, 0, 0)


def test_setpixel_at_logical_y_15_lands_at_bottom_at_scale_4():
    real = _make_real_canvas(real_w=256, real_h=64)
    sc = ScaledCanvas(real, scale=4)
    sc.SetPixel(0, 15, 0, 255, 0)
    # y=15 logical → real y in [60,63]
    assert real.get_pixel(0, 60) == (0, 255, 0)
    assert real.get_pixel(0, 63) == (0, 255, 0)


def test_clear_clears_underlying_canvas():
    real = _make_real_canvas()
    sc = ScaledCanvas(real, scale=4)
    sc.SetPixel(0, 0, 255, 0, 0)
    sc.Clear()
    assert real.get_pixel(0, 0) == (0, 0, 0)
