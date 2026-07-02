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
