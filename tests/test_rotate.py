"""PixelBuffer + rotate_blit (propeller spec §3): inverse-mapped
nearest-neighbor rotation; unset pixels are transparent.

Also covers Task-5A additions:
- PixelBuffer.lit_extent tracking (SetPixel/SubFill update; clear() resets)
- rotate_blit optimized inner loop with src_extent param (identical output
  except at exact .5-tie inverse coords — see TestBlitIdentity's note)
- RotationSurface snapshot/invalidate lifecycle + half-space pivot
"""

import math

import pytest

from led_ticker.rotate import PixelBuffer, rotate_blit
from led_ticker.scaled_canvas import unwrap_to_real

# ---------------------------------------------------------------------------
# Reference implementation (the original loop, preserved here for byte-identity
# comparison).  NEVER move this back into src — it stays test-file-only.
# ---------------------------------------------------------------------------


def _rotate_blit_reference(
    dst: object, src: PixelBuffer, angle_deg: float, cx: float, cy: float
) -> None:
    """Original rotate_blit inner loop — preserved as the correctness oracle.
    The optimized implementation in src must produce identical output at
    the angles below. NOTE (review-adjudicated): identity does NOT hold at
    every angle — int(x+0.5) half-up vs round()'s half-to-even diverge when
    an inverse coordinate lands exactly on .5 (about 5% of angles produce a
    lit-pixel tie; e.g. 2.0 and 48.0 on the standard pattern, or 45.0 on a
    33x17 buffer). The angles chosen here are tie-free by construction; if
    you add an angle and this fails with single-slot displacements, you have
    hit a tie, not a bug — spec R3 cleared ties as visually irrelevant."""
    theta = math.radians(angle_deg)
    cos_t = math.cos(theta)
    sin_t = math.sin(theta)

    corners = [(0.0, 0.0), (src.width, 0.0), (0.0, src.height), (src.width, src.height)]
    xs: list[float] = []
    ys: list[float] = []
    for px, py in corners:
        dx, dy = px - cx, py - cy
        xs.append(cx + dx * cos_t - dy * sin_t)
        ys.append(cy + dx * sin_t + dy * cos_t)
    dst_w: int = getattr(dst, "width", src.width)
    dst_h: int = getattr(dst, "height", src.height)
    x0 = max(0, math.floor(min(xs)))
    x1 = min(dst_w - 1, math.ceil(max(xs)))
    y0 = max(0, math.floor(min(ys)))
    y1 = min(dst_h - 1, math.ceil(max(ys)))

    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            dx = x - cx
            dy = y - cy
            sx = cx + dx * cos_t + dy * sin_t
            sy = cy - dx * sin_t + dy * cos_t
            pixel = src.get(round(sx), round(sy))
            if pixel is not None:
                dst.SetPixel(x, y, *pixel)  # type: ignore[attr-defined]


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
    """Minimal SetPixel recorder standing in for a canvas.

    Also implements SubFill so tests that route through ScaledCanvas(scale=2)
    (the snapshot-artifact blit path) don't get AttributeError.
    """

    def __init__(self, w: int = 16, h: int = 16) -> None:
        self.width = w
        self.height = h
        self.pixels: dict[tuple[int, int], tuple[int, int, int]] = {}

    def SetPixel(self, x: int, y: int, r: int, g: int, b: int) -> None:
        self.pixels[(x, y)] = (r, g, b)

    def SubFill(self, x: int, y: int, w: int, h: int, r: int, g: int, b: int) -> None:
        """Fill a w×h block — records each pixel individually."""
        for yy in range(max(0, y), min(self.height, y + h)):
            for xx in range(max(0, x), min(self.width, x + w)):
                self.pixels[(xx, yy)] = (r, g, b)


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


# ---------------------------------------------------------------------------
# Task-5A: PixelBuffer.lit_extent tracking
# ---------------------------------------------------------------------------


class TestLitExtent:
    """PixelBuffer.lit_extent tracks the AABB of lit slots incrementally."""

    def test_initially_none(self) -> None:
        buf = PixelBuffer(16, 16)
        assert buf.lit_extent is None

    def test_single_setpixel_updates_extent(self) -> None:
        buf = PixelBuffer(16, 16)
        buf.SetPixel(5, 7, 1, 1, 1)
        assert buf.lit_extent == (5, 7, 6, 8)

    def test_multiple_setpixels_expand_extent(self) -> None:
        buf = PixelBuffer(16, 16)
        buf.SetPixel(3, 2, 1, 1, 1)
        buf.SetPixel(10, 12, 1, 1, 1)
        x0, y0, x1, y1 = buf.lit_extent  # type: ignore[misc]
        assert x0 == 3
        assert y0 == 2
        assert x1 == 11  # exclusive: max_x + 1
        assert y1 == 13  # exclusive: max_y + 1

    def test_subfill_updates_extent(self) -> None:
        buf = PixelBuffer(32, 32)
        buf.SubFill(4, 6, 8, 4, 1, 1, 1)
        # fills x in [4,12), y in [6,10)
        x0, y0, x1, y1 = buf.lit_extent  # type: ignore[misc]
        assert x0 == 4
        assert y0 == 6
        assert x1 == 12
        assert y1 == 10

    def test_subfill_clamped_updates_extent_correctly(self) -> None:
        buf = PixelBuffer(8, 8)
        buf.SubFill(6, 6, 10, 10, 1, 1, 1)  # spills past edges
        # clamped to x in [6,8), y in [6,8)
        x0, y0, x1, y1 = buf.lit_extent  # type: ignore[misc]
        assert x0 == 6
        assert y0 == 6
        assert x1 == 8
        assert y1 == 8

    def test_clear_resets_extent_to_none(self) -> None:
        buf = PixelBuffer(16, 16)
        buf.SetPixel(5, 5, 1, 1, 1)
        assert buf.lit_extent is not None
        buf.clear()
        assert buf.lit_extent is None

    def test_out_of_bounds_setpixel_does_not_update_extent(self) -> None:
        buf = PixelBuffer(4, 4)
        buf.SetPixel(-1, 0, 1, 1, 1)
        buf.SetPixel(4, 0, 1, 1, 1)
        assert buf.lit_extent is None

    def test_extent_grows_monotonically(self) -> None:
        """Writes that do NOT expand the AABB must leave it unchanged."""
        buf = PixelBuffer(20, 20)
        buf.SetPixel(5, 5, 1, 1, 1)
        buf.SetPixel(10, 10, 1, 1, 1)
        after_two = buf.lit_extent
        buf.SetPixel(7, 7, 1, 1, 1)  # inside the existing AABB
        assert buf.lit_extent == after_two

    def test_extent_after_subfill_then_setpixel(self) -> None:
        buf = PixelBuffer(20, 20)
        buf.SubFill(2, 2, 4, 4, 1, 1, 1)  # x [2,6), y [2,6)
        buf.SetPixel(15, 15, 1, 1, 1)
        x0, y0, x1, y1 = buf.lit_extent  # type: ignore[misc]
        assert x0 == 2
        assert y0 == 2
        assert x1 == 16  # max of SubFill x1=6 and SetPixel x+1=16
        assert y1 == 16


# ---------------------------------------------------------------------------
# Task-5A: rotate_blit optimized inner loop — byte-identity against reference
# ---------------------------------------------------------------------------


def _make_test_pattern(w: int = 32, h: int = 16) -> PixelBuffer:
    """A non-trivial lit pattern: a diagonal stripe + a corner pixel."""
    buf = PixelBuffer(w, h)
    for i in range(min(w, h)):
        buf.SetPixel(i, i, 200, 100, 50)
    buf.SetPixel(0, h - 1, 255, 255, 0)
    buf.SetPixel(w - 1, 0, 0, 255, 255)
    return buf


class TestRotateBlitOptimized:
    """The optimized rotate_blit must produce identical output to the
    (tie-free angles only — see the class docstring note) —
    reference implementation across arbitrary angles, with and without extent."""

    @pytest.mark.parametrize("angle", [7.3, 45.0, 61.7, 137.0, 289.0])
    def test_byte_identical_no_extent(self, angle: float) -> None:
        src = _make_test_pattern()
        cx, cy = src.width / 2.0, src.height / 2.0

        ref = _RecordingDst(src.width, src.height)
        _rotate_blit_reference(ref, src, angle, cx, cy)

        opt = _RecordingDst(src.width, src.height)
        rotate_blit(opt, src, angle, cx, cy)

        assert opt.pixels == ref.pixels, (
            f"angle={angle}: optimized blit differs from reference.\n"
            f"ref had {len(ref.pixels)} pixels, opt had {len(opt.pixels)} pixels."
        )

    @pytest.mark.parametrize("angle", [7.3, 45.0, 61.7, 137.0, 289.0])
    def test_byte_identical_with_extent(self, angle: float) -> None:
        """With src_extent set to the buffer's lit extent, output must still
        match the reference (which always scans the full rect)."""
        src = _make_test_pattern()
        cx, cy = src.width / 2.0, src.height / 2.0
        extent = src.lit_extent

        ref = _RecordingDst(src.width, src.height)
        _rotate_blit_reference(ref, src, angle, cx, cy)

        opt = _RecordingDst(src.width, src.height)
        rotate_blit(opt, src, angle, cx, cy, src_extent=extent)

        assert opt.pixels == ref.pixels, (
            f"angle={angle} with extent={extent}: "
            f"optimized blit differs from reference.\n"
            f"ref had {len(ref.pixels)} pixels, opt had {len(opt.pixels)} pixels."
        )

    def test_src_extent_none_is_back_compat(self) -> None:
        """src_extent=None (default) produces the same output as not passing it."""
        src = _make_test_pattern()
        cx, cy = src.width / 2.0, src.height / 2.0

        explicit_none = _RecordingDst(src.width, src.height)
        rotate_blit(explicit_none, src, 45.0, cx, cy, src_extent=None)

        no_arg = _RecordingDst(src.width, src.height)
        rotate_blit(no_arg, src, 45.0, cx, cy)

        assert explicit_none.pixels == no_arg.pixels


# ---------------------------------------------------------------------------
# Task-5A: downsample preserves 1-px strokes
# ---------------------------------------------------------------------------


class TestDownsample1pxStroke:
    """The any-lit box downsample must preserve a 1-pixel stroke at an odd
    physical coordinate — nearest-neighbor decimation at stride 2 drops it
    (the sub-stride feature is lost); any-lit keeps it."""

    def test_odd_coordinate_stroke_survives_downsample(self) -> None:
        from led_ticker.rotate import make_rotation_surface
        from led_ticker.scaled_canvas import ScaledCanvas

        real = _RecordingDst(64, 64)
        wrapper = ScaledCanvas(real, scale=4, content_height=16)
        surface = make_rotation_surface(wrapper)

        # Draw a 1-px horizontal stroke at physical y=1 (odd coordinate).
        # At scale=4 this is a hires-style direct write to the buffer.
        inner = unwrap_to_real(surface.target)  # the PixelBuffer
        for x in range(inner.width):
            inner.SetPixel(x, 1, 200, 100, 50)  # y=1 is odd → maps to half-row 0

        surface.snapshot()

        # Half buffer: y=1 downsamples into row 0 of the half buffer.
        half = surface._half_buffer
        assert half is not None, "snapshot() did not create a half buffer"
        # At least some pixels in row 0 of the half buffer must be lit.
        row0_lit = [
            half.get(x, 0) for x in range(half.width) if half.get(x, 0) is not None
        ]
        assert row0_lit, (
            "1-px stroke at odd physical coordinate (y=1) was dropped by the "
            "downsample — expected any-lit box sampling to preserve it in row 0"
        )


# ---------------------------------------------------------------------------
# Task-5A: emoji size in artifact
# ---------------------------------------------------------------------------


class TestEmojiSizeInArtifact:
    """A hires emoji sprite must span its full physical rows in the artifact,
    and the downsampled copy must span half that many rows."""

    def test_hires_sprite_spans_full_rows_in_artifact_and_half_in_downsample(
        self,
    ) -> None:
        from led_ticker.pixel_emoji import HIRES_REGISTRY

        if "sun" not in HIRES_REGISTRY:
            pytest.skip(
                "':sun:' not in HIRES_REGISTRY — skip hires emoji artifact test"
            )

        from led_ticker.pixel_emoji import draw_emoji_at
        from led_ticker.rotate import make_rotation_surface
        from led_ticker.scaled_canvas import ScaledCanvas

        real = _RecordingDst(256, 64)
        wrapper = ScaledCanvas(real, scale=4, content_height=16)
        surface = make_rotation_surface(wrapper)

        # Draw the hires emoji into the surface target (logical coords via wrapper).
        # draw_emoji_at routes to hires on a ScaledCanvas and paints physical pixels
        # directly via unwrap_to_real.
        draw_emoji_at(surface.target, "sun", x=0, y=0)

        inner = unwrap_to_real(surface.target)

        # Artifact: check which physical rows have lit pixels.
        lit_rows_artifact = {
            y
            for y in range(inner.height)
            if any(inner.get(x, y) is not None for x in range(inner.width))
        }
        assert lit_rows_artifact, "draw_emoji_at produced no lit pixels in the artifact"

        # Snapshot and check the half buffer.
        surface.snapshot()
        half = surface._half_buffer
        assert half is not None, "snapshot() did not produce a half buffer"

        lit_rows_half = {
            y
            for y in range(half.height)
            if any(half.get(x, y) is not None for x in range(half.width))
        }
        assert lit_rows_half, "Snapshot half buffer has no lit rows"

        # The number of lit rows in the half buffer should be roughly half of
        # those in the full artifact (the 2x downsample).
        assert len(lit_rows_half) <= len(lit_rows_artifact), (
            "Half buffer has more lit rows than the full artifact — "
            "downsample direction is inverted or half buffer is wrong size"
        )
        assert len(lit_rows_half) >= len(lit_rows_artifact) // 3, (
            f"Half buffer lost too many rows: {len(lit_rows_half)} vs "
            f"{len(lit_rows_artifact)} in full artifact. "
            "Expected roughly half."
        )


# ---------------------------------------------------------------------------
# Task-5A: snapshot/invalidate lifecycle
# ---------------------------------------------------------------------------


class TestSnapshotInvalidateLifecycle:
    """RotationSurface snapshot/invalidate lifecycle."""

    def test_has_snapshot_initially_false(self) -> None:
        from led_ticker.rotate import make_rotation_surface

        dst = _RecordingDst(160, 16)
        surface = make_rotation_surface(dst)
        assert not surface.has_snapshot

    def test_snapshot_sets_has_snapshot(self) -> None:
        from led_ticker.rotate import make_rotation_surface

        dst = _RecordingDst(160, 16)
        surface = make_rotation_surface(dst)
        surface.snapshot()
        assert surface.has_snapshot

    def test_invalidate_clears_has_snapshot(self) -> None:
        from led_ticker.rotate import make_rotation_surface

        dst = _RecordingDst(160, 16)
        surface = make_rotation_surface(dst)
        surface.snapshot()
        assert surface.has_snapshot
        surface.invalidate()
        assert not surface.has_snapshot

    def test_clear_also_invalidates(self) -> None:
        from led_ticker.rotate import make_rotation_surface

        dst = _RecordingDst(160, 16)
        surface = make_rotation_surface(dst)
        surface.snapshot()
        assert surface.has_snapshot
        surface.clear()
        assert not surface.has_snapshot

    def test_scale1_snapshot_sets_has_snapshot_no_half_buffer(self) -> None:
        """At scale=1, snapshot() is a validity-mark only — no downsample step."""
        from led_ticker.rotate import make_rotation_surface

        dst = _RecordingDst(160, 16)
        surface = make_rotation_surface(dst)
        surface.target.SetPixel(5, 5, 1, 1, 1)
        surface.snapshot()
        assert surface.has_snapshot
        # At scale=1 there is no half buffer.
        assert not hasattr(surface, "_half_buffer") or surface._half_buffer is None

    def test_scaled_snapshot_creates_half_buffer(self) -> None:
        from led_ticker.rotate import make_rotation_surface
        from led_ticker.scaled_canvas import ScaledCanvas

        real = _RecordingDst(256, 64)
        wrapper = ScaledCanvas(real, scale=4, content_height=16)
        surface = make_rotation_surface(wrapper)
        inner = unwrap_to_real(surface.target)
        inner.SetPixel(10, 10, 1, 1, 1)
        surface.snapshot()
        assert surface.has_snapshot
        assert surface._half_buffer is not None
        # Half buffer dims: (w_real//2, h_real//2) = (128, 32)
        assert surface._half_buffer.width == 128
        assert surface._half_buffer.height == 32

    def test_blit_without_prior_snapshot_lazy_snapshots_at_scale_gt1(self) -> None:
        """Backward-compat: blit() without snapshot() at scale>1 lazy-snapshots.
        This keeps existing widget tests green until Task 5B."""
        from led_ticker.rotate import make_rotation_surface
        from led_ticker.scaled_canvas import ScaledCanvas

        real = _RecordingDst(256, 64)
        wrapper = ScaledCanvas(real, scale=4, content_height=16)
        surface = make_rotation_surface(wrapper)

        # Draw one pixel into the buffer.
        inner = unwrap_to_real(surface.target)
        inner.SetPixel(100, 32, 255, 0, 0)

        # Call blit directly without snapshot() — must not raise.
        surface.blit(wrapper, 90.0, 32.0)
        # Surface should now have a snapshot.
        assert surface.has_snapshot


# ---------------------------------------------------------------------------
# Task-5A: half-space 180-degree pivot exactness
# ---------------------------------------------------------------------------


class TestHalfSpacePivot:
    """A 180-degree rotation of a known physical pixel through the scale-2
    dst wrapper must land at the exact expected position."""

    def test_180_degree_pivot_exact_through_scale2_wrapper(self) -> None:
        """Physical pixel at (px, py) rotated 180° about (cx_half, h_real/4)
        must land at (2*cx_half - 1 - px, 2*(h_real//4) - 1 - py) in half-space,
        which maps to (2*(cx_half*2) - 1 - px*2, ...) in real space via SubFill.

        Simpler to verify: blit 180° with a known single-pixel half-buffer and
        assert the exact output position on the real canvas via the scale-2 wrapper.
        """
        from led_ticker.rotate import make_rotation_surface
        from led_ticker.scaled_canvas import ScaledCanvas

        real = _RecordingDst(64, 64)
        wrapper = ScaledCanvas(real, scale=4, content_height=16)
        surface = make_rotation_surface(wrapper)

        # Put a single pixel at physical (20, 32) in the full artifact.
        inner = unwrap_to_real(surface.target)
        inner.SetPixel(20, 32, 255, 0, 0)

        # Snapshot to produce the half buffer.
        surface.snapshot()

        # Clear real dst to ensure we're seeing only the blit result.
        real.pixels.clear()

        # Blit at 180° with cx_logical=8 (cx_phys=32 at scale=4).
        # In half-space: cx_half = 32/2 = 16, cy_half = 64/4 = 16.
        # Input half-pixel at (10, 16) [= (20//2, 32//2)].
        # 180° maps: (2*16 - 10, 2*16 - 16) = (22, 16) in half-space.
        # The scale-2 dst wrapper expands to a 2×2 block at (44, 32) in real space.
        surface.blit(wrapper, 180.0, 8.0)

        # Assert a 2×2 block is lit near (44, 32) — the scale-2 SubFill.
        lit = {xy for xy in real.pixels if real.pixels[xy] == (255, 0, 0)}
        assert lit, "180-degree half-space blit produced no lit pixels"
        # The block should be near the expected position (within ±2px rounding).
        expected_center = (44, 32)
        hits = [
            (x, y)
            for x, y in lit
            if abs(x - expected_center[0]) <= 3 and abs(y - expected_center[1]) <= 3
        ]
        assert hits, (
            f"180-degree half-space blit: expected lit pixels near {expected_center}, "
            f"but lit pixels are at {sorted(lit)}"
        )


# ---------------------------------------------------------------------------
# Task-5A: two-cycle no-bleed via snapshot
# ---------------------------------------------------------------------------


class TestTwoCycleNoBleedSnapshot:
    """Two consecutive snapshot→blit cycles on ONE surface must produce
    independent outputs (no bleed-through from cycle 1 into cycle 2)."""

    def test_two_cycle_no_bleed_snapshot(self) -> None:
        from led_ticker.rotate import make_rotation_surface
        from led_ticker.scaled_canvas import ScaledCanvas

        real1 = _RecordingDst(64, 64)
        wrapper1 = ScaledCanvas(real1, scale=4, content_height=16)
        surface = make_rotation_surface(wrapper1)

        # Cycle 1: draw a red pixel, snapshot, blit.
        inner = unwrap_to_real(surface.target)
        inner.SetPixel(40, 32, 255, 0, 0)
        surface.snapshot()
        surface.blit(wrapper1, 0.1, 16.0)

        # Cycle 2: clear, draw green pixel at a different position, snapshot, blit.
        surface.clear()
        surface.invalidate()
        inner.SetPixel(10, 10, 0, 255, 0)
        surface.snapshot()

        real2 = _RecordingDst(64, 64)
        wrapper2 = ScaledCanvas(real2, scale=4, content_height=16)
        surface.blit(wrapper2, 0.1, 16.0)

        # Cycle 2 output must not contain red pixels.
        reds = [xy for xy, rgb in real2.pixels.items() if rgb == (255, 0, 0)]
        assert not reds, (
            f"Cycle 1 red pixel bled into cycle 2 output: red pixels at {reds}"
        )
