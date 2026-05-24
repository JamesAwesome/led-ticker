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


class TestContentHeightCeiling:
    """Regression: `content_height * scale > panel_h_real` causes a
    negative `_y_offset`, silently clipping content near the logical
    canvas edges. Hardware-discovered (`:instagram:` emoji clipping
    4-8 real px on bigsign with content_height=20 + scale=4 on a
    64-real-row panel). The wrapper now hard-fails at construction
    so misconfigured sections surface immediately.
    """

    def test_overflowing_content_height_raises(self):
        # Bigsign-shape: 256×64 real panel.
        real = _make_real_canvas(real_w=256, real_h=64)
        # 20 × 4 = 80 > 64 → would overflow.
        with pytest.raises(ValueError, match="exceeds the real panel height"):
            ScaledCanvas(real, scale=4, content_height=20)

    def test_exact_fit_passes(self):
        """16 × 4 = 64 exactly matches the panel — must construct OK."""
        real = _make_real_canvas(real_w=256, real_h=64)
        sc = ScaledCanvas(real, scale=4, content_height=16)
        assert sc.y_offset_real == 0

    def test_under_fit_passes_with_letterbox(self):
        """8 × 4 = 32 < 64 — letterboxes (16 real rows top + bottom)."""
        real = _make_real_canvas(real_w=256, real_h=64)
        sc = ScaledCanvas(real, scale=4, content_height=8)
        assert sc.y_offset_real == 16

    def test_nested_wrapper_uses_innermost_real_height(self):
        """Cross-scale dissolves wrap a wrapper. The validation must
        peel through to the genuine panel height, not the inner
        wrapper's logical content_height (which would be ambiguous)."""
        real = _make_real_canvas(real_w=256, real_h=64)
        inner = ScaledCanvas(real, scale=2, content_height=32)
        # Wrapping with scale=4 + content_height=16: 16×4=64, fits the
        # 64-row panel even though `inner.height` is 32 (logical).
        outer = ScaledCanvas(inner, scale=4, content_height=16)
        assert outer.scale == 4

    def test_error_message_suggests_max_content_height(self):
        real = _make_real_canvas(real_w=256, real_h=64)
        with pytest.raises(ValueError) as exc_info:
            ScaledCanvas(real, scale=4, content_height=24)
        # 64 // 4 = 16
        assert "content_height ≤ 16" in str(exc_info.value)


def test_y_offset_real_attribute_name_at_scale_2():
    real = _make_real_canvas(real_w=256, real_h=64)
    sc = ScaledCanvas(real, scale=2)
    # y_offset_real = (64 - 16*2) // 2 = 16
    assert sc.y_offset_real == 16


def test_y_offset_real_attribute_name_at_scale_4_no_letterbox():
    real = _make_real_canvas(real_w=256, real_h=64)
    sc = ScaledCanvas(real, scale=4)
    # y_offset_real = (64 - 16*4) // 2 = 0
    assert sc.y_offset_real == 0


def test_no_private_y_offset():
    real = _make_real_canvas(real_w=256, real_h=64)
    sc = ScaledCanvas(real, scale=4)
    assert not hasattr(sc, "_y_offset"), "_y_offset must be gone after rename"


def test_paint_hires_scaled_canvas_no_letterbox():
    real = _make_real_canvas(real_w=256, real_h=64)
    sc = ScaledCanvas(real, scale=4)
    calls: list[tuple] = []
    from led_ticker.scaled_canvas import paint_hires

    paint_hires(sc, lambda r, s, y: calls.append((r, s, y)))
    assert calls == [(real, 4, 0)]  # scale=4, y_offset_real=(64-64)//2=0


def test_paint_hires_scaled_canvas_with_letterbox():
    real = _make_real_canvas(real_w=256, real_h=64)
    sc = ScaledCanvas(real, scale=2)  # y_offset_real = (64 - 32) // 2 = 16
    calls: list[tuple] = []
    from led_ticker.scaled_canvas import paint_hires

    paint_hires(sc, lambda r, s, y: calls.append((r, s, y)))
    assert calls == [(real, 2, 16)]


def test_safe_scale_matches_isinstance_for_scaled_canvas():
    from led_ticker.drawing import safe_scale

    real = _make_real_canvas(real_w=256, real_h=64)
    sc = ScaledCanvas(real, scale=4)
    assert safe_scale(sc) > 1
    assert safe_scale(real) == 1


def test_paint_hires_plain_canvas():
    real = _make_real_canvas(real_w=256, real_h=64)
    calls: list[tuple] = []
    from led_ticker.scaled_canvas import paint_hires

    paint_hires(real, lambda r, s, y: calls.append((r, s, y)))
    assert calls == [(real, 1, 0)]


def test_rebind_innermost_single_wrapper():
    real_a = _make_real_canvas(real_w=256, real_h=64)
    real_b = _make_real_canvas(real_w=256, real_h=64)
    sc = ScaledCanvas(real_a, scale=4)
    sc.rebind_innermost(real_b)
    assert sc.real is real_b


def test_rebind_innermost_nested_wrappers():
    real_a = _make_real_canvas(real_w=256, real_h=64)
    real_b = _make_real_canvas(real_w=256, real_h=64)
    inner = ScaledCanvas(real_a, scale=4)
    # Outer wraps inner — __attrs_post_init__ peels to real_a (64px) for validation.
    outer = ScaledCanvas(inner, scale=4, content_height=16)
    outer.rebind_innermost(real_b)
    assert inner.real is real_b  # deepest wrapper updated
    assert outer.real is inner  # outer unchanged


def test_rebind_innermost_does_not_change_outer_real_on_nesting():
    real_a = _make_real_canvas(real_w=256, real_h=64)
    real_b = _make_real_canvas(real_w=256, real_h=64)
    inner = ScaledCanvas(real_a, scale=4)
    outer = ScaledCanvas(inner, scale=4, content_height=16)
    outer.rebind_innermost(real_b)
    assert outer.real is inner  # outer still points at inner


def test_subfill_paints_scaled_block_at_scale_4():
    real = _make_real_canvas(real_w=256, real_h=64)
    sc = ScaledCanvas(real, scale=4)
    # Logical (2, 1) size 3×2 → real (8, 4) size 12×8 (no letterbox at scale=4)
    sc.SubFill(2, 1, 3, 2, 255, 0, 0)
    for y in range(4, 12):
        for x in range(8, 20):
            assert real.get_pixel(x, y) == (255, 0, 0), f"pixel ({x},{y}) not red"
    assert real.get_pixel(7, 4) == (0, 0, 0)  # left edge — not painted
    assert real.get_pixel(20, 4) == (0, 0, 0)  # right edge — not painted
    assert real.get_pixel(8, 3) == (0, 0, 0)  # top edge — not painted
    assert real.get_pixel(8, 12) == (0, 0, 0)  # bottom edge — not painted


def test_subfill_respects_y_offset_at_scale_2():
    real = _make_real_canvas(real_w=256, real_h=64)
    sc = ScaledCanvas(real, scale=2)
    # y_offset = (64 - 16*2) // 2 = 16 (letterbox)
    sc.SubFill(0, 0, 1, 1, 0, 255, 0)
    # Logical (0,0) 1×1 → real (0, 16) 2×2
    assert real.get_pixel(0, 16) == (0, 255, 0)
    assert real.get_pixel(1, 17) == (0, 255, 0)
    assert real.get_pixel(0, 15) == (0, 0, 0)  # letterbox above
    assert real.get_pixel(0, 18) == (0, 0, 0)  # outside below
