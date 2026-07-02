"""PixelBuffer + rotate_blit (propeller spec §3): inverse-mapped
nearest-neighbor rotation; unset pixels are transparent."""

from led_ticker.rotate import PixelBuffer, rotate_blit
from led_ticker.scaled_canvas import unwrap_to_real


def _buf_with_pixel(w: int, h: int, x: int, y: int) -> PixelBuffer:
    buf = PixelBuffer(w, h)
    buf.SetPixel(x, y, 255, 0, 0)
    return buf


class TestPixelBuffer:
    def test_set_and_get(self) -> None:
        buf = PixelBuffer(8, 8)
        buf.SetPixel(2, 3, 10, 20, 30)
        assert buf.get(2, 3) == (10, 20, 30)
        assert buf.get(0, 0) is None  # unset = transparent

    def test_out_of_bounds_setpixel_ignored(self) -> None:
        buf = PixelBuffer(4, 4)
        buf.SetPixel(-1, 0, 1, 1, 1)
        buf.SetPixel(4, 0, 1, 1, 1)
        buf.SetPixel(0, 99, 1, 1, 1)
        assert all(buf.get(x, y) is None for x in range(4) for y in range(4))

    def test_unwrap_to_real_identity(self) -> None:
        """PM round-2 finding 11: the no-`.real` base case of
        unwrap_to_real must return the buffer itself."""
        buf = PixelBuffer(4, 4)
        assert unwrap_to_real(buf) is buf


class _RecordingDst:
    """Minimal SetPixel recorder standing in for a canvas."""

    def __init__(self, w: int = 16, h: int = 16) -> None:
        self.width = w
        self.height = h
        self.pixels: dict[tuple[int, int], tuple[int, int, int]] = {}

    def SetPixel(self, x: int, y: int, r: int, g: int, b: int) -> None:
        self.pixels[(x, y)] = (r, g, b)


class TestRotateBlit:
    def test_90_degrees_exact_permutation(self) -> None:
        """A pixel at (cx+3, cy) rotated 90 deg clockwise about (cx, cy)
        lands at (cx, cy+3)."""
        src = _buf_with_pixel(16, 16, 11, 8)  # (cx+3, cy) with cx=8, cy=8
        dst = _RecordingDst()
        rotate_blit(dst, src, 90.0, 8.0, 8.0)
        assert dst.pixels.get((8, 11)) == (255, 0, 0)

    def test_180_degrees_exact(self) -> None:
        src = _buf_with_pixel(16, 16, 11, 8)
        dst = _RecordingDst()
        rotate_blit(dst, src, 180.0, 8.0, 8.0)
        assert dst.pixels.get((5, 8)) == (255, 0, 0)

    def test_270_degrees_exact(self) -> None:
        src = _buf_with_pixel(16, 16, 11, 8)
        dst = _RecordingDst()
        rotate_blit(dst, src, 270.0, 8.0, 8.0)
        assert dst.pixels.get((8, 5)) == (255, 0, 0)

    def test_center_pixel_invariant_at_any_angle(self) -> None:
        for angle in (0.0, 33.0, 45.0, 137.5, 359.0):
            src = _buf_with_pixel(16, 16, 8, 8)  # exactly the center
            dst = _RecordingDst()
            rotate_blit(dst, src, angle, 8.0, 8.0)
            assert dst.pixels.get((8, 8)) == (255, 0, 0), f"angle={angle}"

    def test_transparency_never_paints_unset(self) -> None:
        """Unset src pixels must not overwrite dst — dst records NOTHING
        outside the rotated lit pixel."""
        src = _buf_with_pixel(16, 16, 11, 8)
        dst = _RecordingDst()
        rotate_blit(dst, src, 45.0, 8.0, 8.0)
        assert (
            0 < len(dst.pixels) <= 4
        )  # the one lit pixel (nearest-neighbor spread), nothing else

    def test_all_painted_pixels_in_dst_bounds(self) -> None:
        src = PixelBuffer(16, 16)
        for x in range(16):
            src.SetPixel(x, 8, 200, 200, 200)  # full-width line
        dst = _RecordingDst(16, 16)
        for angle in (17.0, 45.0, 90.0, 245.0):
            rotate_blit(dst, src, angle, 8.0, 8.0)
        assert all(0 <= x < 16 and 0 <= y < 16 for (x, y) in dst.pixels)


class TestPixelBufferSubFill:
    def test_subfill_fills_exact_block(self) -> None:
        buf = PixelBuffer(8, 8)
        buf.SubFill(2, 3, 2, 2, 9, 8, 7)
        filled = {(x, y) for x in range(8) for y in range(8) if buf.get(x, y)}
        assert filled == {(2, 3), (3, 3), (2, 4), (3, 4)}
        assert buf.get(2, 3) == (9, 8, 7)

    def test_subfill_clamps_out_of_bounds(self) -> None:
        buf = PixelBuffer(4, 4)
        buf.SubFill(3, 3, 4, 4, 1, 1, 1)  # spills past both edges
        filled = {(x, y) for x in range(4) for y in range(4) if buf.get(x, y)}
        assert filled == {(3, 3)}
        buf2 = PixelBuffer(4, 4)
        buf2.SubFill(-2, -2, 3, 3, 1, 1, 1)  # negative origin clamps
        filled2 = {(x, y) for x in range(4) for y in range(4) if buf2.get(x, y)}
        assert filled2 == {(0, 0)}

    def test_clear_resets_all_slots(self) -> None:
        buf = PixelBuffer(4, 4)
        buf.SubFill(0, 0, 4, 4, 5, 5, 5)
        buf.clear()
        assert all(buf.get(x, y) is None for x in range(4) for y in range(4))


class TestWrappedBufferDraw:
    def test_scaled_canvas_over_buffer_draws_bdf_text(self) -> None:
        """Regression pin for spec §1b: ScaledCanvas writes route through
        real.SubFill — a bare PixelBuffer AttributeError'd here before
        this task. BDF text through the wrapper must land as scale-sized
        blocks in the buffer."""
        from led_ticker.fonts import FONT_DEFAULT, get_bdf_for
        from led_ticker.scaled_canvas import ScaledCanvas

        buf = PixelBuffer(64 * 4, 16 * 4)  # panel-shaped, scale 4
        wrapper = ScaledCanvas(buf, scale=4, content_height=16)
        bdf = get_bdf_for(FONT_DEFAULT)
        wrapper.draw_bdf_text(bdf, 0, 12, (255, 255, 255), "HI")
        lit = [
            (x, y) for x in range(buf.width) for y in range(buf.height) if buf.get(x, y)
        ]
        assert lit, "wrapped BDF draw painted nothing"


class TestRotationSurface:
    def test_scale1_target_is_bare_buffer(self) -> None:
        from led_ticker.rotate import make_rotation_surface

        dst = _RecordingDst(160, 16)
        surface = make_rotation_surface(dst)
        assert isinstance(surface.target, PixelBuffer)
        assert (surface.target.width, surface.target.height) == (160, 16)

    def test_scaled_target_is_panel_shaped_wrapper(self) -> None:
        from led_ticker.rotate import make_rotation_surface
        from led_ticker.scaled_canvas import ScaledCanvas

        real = _RecordingDst(256, 64)
        wrapper = ScaledCanvas(real, scale=4, content_height=16)
        surface = make_rotation_surface(wrapper)
        assert isinstance(surface.target, ScaledCanvas)
        inner = surface.target.real
        assert isinstance(inner, PixelBuffer)
        assert (inner.width, inner.height) == (256, 64)
        assert surface.target.scale == 4
        assert surface.target.content_height == 16

    def test_scale1_blit_matches_v1_rotate_blit(self) -> None:
        """Byte-identity: surface.blit == direct rotate_blit at scale 1."""
        from led_ticker.rotate import make_rotation_surface

        direct_src = _buf_with_pixel(16, 16, 11, 8)
        direct_dst = _RecordingDst()
        rotate_blit(direct_dst, direct_src, 90.0, 8.0, 8.0)

        dst = _RecordingDst()
        surface = make_rotation_surface(dst)
        surface.target.SetPixel(11, 8, 255, 0, 0)
        surface.blit(dst, 90.0, 8.0)
        assert dst.pixels == direct_dst.pixels

    def test_scaled_blit_is_physical_granularity(self) -> None:
        """A 45-deg physical rotation must NOT be constant over each
        scale-x-scale block (that would mean logical-then-expanded)."""
        from led_ticker.rotate import make_rotation_surface
        from led_ticker.scaled_canvas import ScaledCanvas

        real = _RecordingDst(64, 64)
        wrapper = ScaledCanvas(real, scale=4, content_height=16)
        surface = make_rotation_surface(wrapper)
        # a full logical row through the wrapper -> 4px-tall physical bar
        for x in range(16):
            surface.target.SetPixel(x, 8, 200, 200, 200)
        surface.blit(wrapper, 45.0, 8.0)
        # group painted physical pixels by their 4x4 logical block; at
        # 45 deg some blocks MUST be partially lit (physical granularity)
        from collections import defaultdict

        blocks: dict[tuple[int, int], int] = defaultdict(int)
        for x, y in real.pixels:
            blocks[(x // 4, y // 4)] += 1
        assert any(0 < n < 16 for n in blocks.values()), (
            "every touched block fully lit — rotation happened at logical, "
            "not physical, granularity"
        )

    def test_scaled_pivot_maps_continuously(self) -> None:
        """180-deg physical rotation maps lit pixels through
        (x, y) -> (2*cx_phys - 1 - x, 2*cy_phys - 1 - y)-ish reflection;
        assert against the exact inverse-map: a pixel at physical
        (px, py) lands where the inverse of R(180) about
        (cx_logical*scale, h_real/2) sends it. Simplest exact check:
        one lit physical pixel, assert its single rotated position."""
        from led_ticker.rotate import make_rotation_surface
        from led_ticker.scaled_canvas import ScaledCanvas

        real = _RecordingDst(64, 64)
        wrapper = ScaledCanvas(real, scale=4, content_height=16)
        surface = make_rotation_surface(wrapper)
        inner = surface.target.real
        inner.SetPixel(44, 32, 255, 0, 0)  # physical coords, direct
        surface.blit(wrapper, 180.0, 8.0)  # cx_phys = 32.0, cy_phys = 32.0
        assert real.pixels.get((20, 32)) == (255, 0, 0)  # 2*32-44=20, 2*32-32=32

    def test_reuse_two_cycles_no_bleed(self) -> None:
        """Construct-once contract: clear() between frames — frame 2's
        output contains nothing from frame 1."""
        from led_ticker.rotate import make_rotation_surface

        dst1 = _RecordingDst()
        surface = make_rotation_surface(dst1)
        surface.target.SetPixel(11, 8, 255, 0, 0)
        surface.blit(dst1, 0.1, 8.0)
        assert dst1.pixels

        surface.clear()
        dst2 = _RecordingDst()
        surface.target.SetPixel(4, 2, 0, 255, 0)
        surface.blit(dst2, 0.1, 8.0)
        reds = [p for p in dst2.pixels.values() if p == (255, 0, 0)]
        assert not reds, "frame 1 content bled into frame 2"

    def test_matches_validates_cache(self) -> None:
        from led_ticker.rotate import make_rotation_surface
        from led_ticker.scaled_canvas import ScaledCanvas

        dst = _RecordingDst(160, 16)
        surface = make_rotation_surface(dst)
        assert surface.matches(dst)
        assert not surface.matches(_RecordingDst(320, 16))
        real = _RecordingDst(256, 64)
        wrapper = ScaledCanvas(real, scale=4, content_height=16)
        assert not surface.matches(wrapper)
        scaled_surface = make_rotation_surface(wrapper)
        assert scaled_surface.matches(wrapper)

    def test_matches_rejects_content_height_change(self) -> None:
        """Antagonist plan-review finding 1: widgets are shared across
        sections while content_height is section-level — a surface built
        at content_height=16 must NOT match a content_height=8 wrapper
        over the same real canvas (different y_offset_real centering)."""
        from led_ticker.rotate import make_rotation_surface
        from led_ticker.scaled_canvas import ScaledCanvas

        real = _RecordingDst(256, 64)
        wrapper16 = ScaledCanvas(real, scale=4, content_height=16)
        wrapper8 = ScaledCanvas(real, scale=4, content_height=8)
        surface = make_rotation_surface(wrapper16)
        assert surface.matches(wrapper16)
        assert not surface.matches(wrapper8)
