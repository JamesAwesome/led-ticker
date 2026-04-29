"""Tests for the ScaledCanvas wrapper used by the bigsign rendering path."""

from __future__ import annotations

import pytest
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


def test_scale_is_frozen():
    """scale should not change after construction (only .real mutates)."""
    import attrs as _attrs

    real = _make_real_canvas()
    sc = ScaledCanvas(real, scale=4)
    with pytest.raises(_attrs.exceptions.FrozenAttributeError):
        sc.scale = 2


def test_content_height_is_frozen():
    import attrs as _attrs

    real = _make_real_canvas()
    sc = ScaledCanvas(real, scale=4)
    with pytest.raises(_attrs.exceptions.FrozenAttributeError):
        sc.content_height = 32


def test_real_is_mutable():
    """real must remain mutable so _swap can rewire after SwapOnVSync."""
    real_a = _make_real_canvas()
    real_b = _make_real_canvas()
    sc = ScaledCanvas(real_a, scale=4)
    sc.real = real_b  # Should not raise
    assert sc.real is real_b


def test_draw_bdf_text_advance_for_single_char():
    from led_ticker.fonts import FONT_SMALL, get_bdf_for

    real = _make_real_canvas(real_w=256, real_h=64)
    sc = ScaledCanvas(real, scale=4)
    bdf = get_bdf_for(FONT_SMALL)  # 5x8 advance = 5
    advance = sc.draw_bdf_text(bdf, x=0, y=8, color=(255, 0, 0), text="A")
    assert advance == 5


def test_draw_bdf_text_advance_for_multichar():
    from led_ticker.fonts import FONT_SMALL, get_bdf_for

    real = _make_real_canvas(real_w=256, real_h=64)
    sc = ScaledCanvas(real, scale=4)
    bdf = get_bdf_for(FONT_SMALL)
    advance = sc.draw_bdf_text(bdf, x=0, y=8, color=(0, 255, 0), text="ABC")
    assert advance == 15  # 3 chars × 5


def test_draw_bdf_text_paints_some_glyph_pixels():
    """Spot check that 'A' actually produces lit pixels in the right region."""
    from led_ticker.fonts import FONT_SMALL, get_bdf_for

    real = _make_real_canvas(real_w=256, real_h=64)
    sc = ScaledCanvas(real, scale=4)
    bdf = get_bdf_for(FONT_SMALL)
    sc.draw_bdf_text(bdf, x=0, y=8, color=(255, 0, 0), text="A")
    # 5x8 'A' bitmap row index 1 has bits "01100" — column 1 lit at logical y in
    # the top half. With scale=4, that block lands somewhere in real (4..7, ?..?).
    found = False
    for ry in range(64):
        for rx in range(20):
            if real.get_pixel(rx, ry) == (255, 0, 0):
                found = True
                break
        if found:
            break
    assert found


def test_draw_bdf_text_unknown_glyph_advances_default_width():
    from led_ticker.fonts import FONT_SMALL, get_bdf_for

    real = _make_real_canvas()
    sc = ScaledCanvas(real, scale=4)
    bdf = get_bdf_for(FONT_SMALL)
    # Use a Unicode char unlikely to be in 5x8.bdf
    advance = sc.draw_bdf_text(bdf, x=0, y=8, color=(0, 0, 255), text="香")
    # Should still advance by something positive (font default width)
    assert advance > 0
