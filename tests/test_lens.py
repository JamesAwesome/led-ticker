"""LensSpec + build_lens_maps + lens_blit (fisheye spec §1–§2).

All tests are TDD — written before the implementation. Test structure mirrors
test_rotate.py conventions (class-grouped, no fixtures for simple cases).
"""

import math

import pytest

from led_ticker.animations import AnimationFrame, LensSpec
from led_ticker.rotate import LensMaps, PixelBuffer, build_lens_maps, lens_blit

# ---------------------------------------------------------------------------
# LensSpec validation
# ---------------------------------------------------------------------------


class TestLensSpecValidation:
    def test_defaults_are_valid(self) -> None:
        spec = LensSpec()
        assert spec.magnify == 1.3
        assert spec.edge_squeeze == 0.6
        assert spec.profile == "cosine"

    def test_custom_valid(self) -> None:
        spec = LensSpec(magnify=2.0, edge_squeeze=0.5, profile="cosine")
        assert spec.magnify == 2.0

    # magnify
    def test_magnify_not_a_number_raises(self) -> None:
        with pytest.raises(ValueError, match="magnify must be a number"):
            LensSpec(magnify="1.3")  # type: ignore[arg-type]

    def test_magnify_bool_rejected(self) -> None:
        # bool is an int subclass — must be excluded explicitly.
        with pytest.raises(ValueError, match="magnify must be a number"):
            LensSpec(magnify=True)  # type: ignore[arg-type]

    def test_magnify_none_raises(self) -> None:
        with pytest.raises(ValueError, match="magnify must be a number"):
            LensSpec(magnify=None)  # type: ignore[arg-type]

    # edge_squeeze
    def test_edge_squeeze_not_a_number_raises(self) -> None:
        with pytest.raises(ValueError, match="edge_squeeze must be a number"):
            LensSpec(edge_squeeze="0.6")  # type: ignore[arg-type]

    def test_edge_squeeze_bool_rejected(self) -> None:
        with pytest.raises(ValueError, match="edge_squeeze must be a number"):
            LensSpec(edge_squeeze=False)  # type: ignore[arg-type]

    def test_edge_squeeze_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="edge_squeeze must be > 0"):
            LensSpec(edge_squeeze=0.0)

    def test_edge_squeeze_negative_raises(self) -> None:
        with pytest.raises(ValueError, match="edge_squeeze must be > 0"):
            LensSpec(edge_squeeze=-0.1)

    # magnify >= edge_squeeze constraint
    def test_magnify_less_than_edge_squeeze_raises(self) -> None:
        with pytest.raises(ValueError, match="magnify must be >= edge_squeeze"):
            LensSpec(magnify=0.4, edge_squeeze=0.6)

    def test_magnify_equal_to_edge_squeeze_ok(self) -> None:
        # Degenerate: uniform scale (no lens effect) — valid.
        spec = LensSpec(magnify=1.0, edge_squeeze=1.0)
        assert spec.magnify == spec.edge_squeeze

    # profile
    def test_unknown_profile_raises(self) -> None:
        with pytest.raises(ValueError, match="profile must be one of"):
            LensSpec(profile="spherical")

    def test_profile_case_sensitive(self) -> None:
        with pytest.raises(ValueError, match="profile must be one of"):
            LensSpec(profile="Cosine")

    # frozen
    def test_frozen_raises_on_mutation(self) -> None:
        spec = LensSpec()
        with pytest.raises((AttributeError, TypeError)):
            spec.magnify = 2.0  # type: ignore[misc]

    # hashable (required for @functools.cache key)
    def test_hashable(self) -> None:
        spec = LensSpec(magnify=1.3, edge_squeeze=0.6)
        assert hash(spec) == hash(LensSpec(magnify=1.3, edge_squeeze=0.6))


# ---------------------------------------------------------------------------
# build_lens_maps — LUT properties
# ---------------------------------------------------------------------------


class TestBuildLensMapsProperties:
    """Test the LUT invariants for two canonical param sets.

    (1.3, 0.6, "cosine", W=64) and (2.0, 0.5, "cosine", W=256).
    """

    @pytest.fixture(
        params=[
            (1.3, 0.6, "cosine", 64),
            (2.0, 0.5, "cosine", 256),
        ],
        ids=["default_w64", "wide_w256"],
    )
    def maps_and_params(self, request):  # type: ignore[no-untyped-def]
        magnify, edge_squeeze, profile, w = request.param
        spec = LensSpec(magnify=magnify, edge_squeeze=edge_squeeze, profile=profile)
        maps = build_lens_maps(spec, w)
        return maps, spec, w

    def test_x_lut_length_is_w_plus_one(self, maps_and_params) -> None:  # type: ignore[no-untyped-def]
        maps, spec, w = maps_and_params
        assert len(maps.x_lut) == w + 1

    def test_vscale_length_is_w(self, maps_and_params) -> None:  # type: ignore[no-untyped-def]
        maps, spec, w = maps_and_params
        assert len(maps.vscale) == w

    def test_x_lut_first_is_zero(self, maps_and_params) -> None:  # type: ignore[no-untyped-def]
        maps, spec, w = maps_and_params
        assert maps.x_lut[0] == 0.0

    def test_x_lut_last_equals_total_src_span(self, maps_and_params) -> None:  # type: ignore[no-untyped-def]
        """Edge-convention pin: x_lut[W] == total_src_span EXACTLY."""
        maps, spec, w = maps_and_params
        assert maps.x_lut[w] == maps.total_src_span

    def test_x_lut_last_equals_sum_of_inv_vscale(self, maps_and_params) -> None:  # type: ignore[no-untyped-def]
        """x_lut is the cumulative sum of 1/s(x): x_lut[W] == sum(1/s)."""
        maps, spec, w = maps_and_params
        expected_sum = sum(1.0 / s for s in maps.vscale)
        assert maps.x_lut[w] == pytest.approx(expected_sum)

    def test_x_lut_strictly_monotone_increasing(self, maps_and_params) -> None:  # type: ignore[no-untyped-def]
        """No fold-over — the cumulative integral is strictly increasing
        because s > 0 implies 1/s > 0 implies each step > 0."""
        maps, spec, w = maps_and_params
        for i in range(w):
            assert maps.x_lut[i + 1] > maps.x_lut[i], (
                f"x_lut not strictly increasing at index {i}"
            )

    def test_x_lut_symmetry(self, maps_and_params) -> None:  # type: ignore[no-untyped-def]
        """Symmetry: x_lut[k] + x_lut[W-k] == total_src_span for all k."""
        maps, spec, w = maps_and_params
        total = maps.total_src_span
        for k in range(w + 1):
            assert maps.x_lut[k] + maps.x_lut[w - k] == pytest.approx(total), (
                f"Symmetry broken at k={k}"
            )

    def test_vscale_peak_at_center_near_magnify(self, maps_and_params) -> None:  # type: ignore[no-untyped-def]
        """Center column(s) have vscale close to magnify (profile discretization)."""
        maps, spec, w = maps_and_params
        # The center is between columns (w-1)/2 and w/2 for even w.
        center = w // 2
        # Allow ±2% — profile discretization at coarse panels (w=64).
        assert maps.vscale[center - 1] == pytest.approx(spec.magnify, rel=0.03)
        assert maps.vscale[center] == pytest.approx(spec.magnify, rel=0.03)

    def test_vscale_edges_near_edge_squeeze(self, maps_and_params) -> None:  # type: ignore[no-untyped-def]
        """First and last columns have vscale close to edge_squeeze."""
        maps, spec, w = maps_and_params
        # d at x=0 → 0.5/0.5*(w/2) just shy of 1 — not exactly edge_squeeze.
        # Allow ±3% for the single-edge-column deviation.
        assert maps.vscale[0] == pytest.approx(spec.edge_squeeze, rel=0.04)
        assert maps.vscale[w - 1] == pytest.approx(spec.edge_squeeze, rel=0.04)


class TestTotalSrcSpan:
    def test_total_src_span_at_least_panel_width(self) -> None:
        """Antagonist-verified: mean(1/s) >= 1 at the defaults → span ≥ W."""
        spec = LensSpec(magnify=1.3, edge_squeeze=0.6)
        maps = build_lens_maps(spec, 128)
        assert maps.total_src_span >= 128

    def test_total_src_span_matches_field(self) -> None:
        """total_src_span field == x_lut[-1] (the LensMaps redundancy is
        intentional — callers read the field, not the LUT tail)."""
        spec = LensSpec()
        maps = build_lens_maps(spec, 64)
        assert maps.total_src_span == maps.x_lut[64]

    def test_cache_returns_same_object(self) -> None:
        """@functools.cache: same spec + panel_w → same LensMaps object."""
        spec = LensSpec(magnify=1.3, edge_squeeze=0.6)
        m1 = build_lens_maps(spec, 64)
        m2 = build_lens_maps(spec, 64)
        assert m1 is m2

    def test_different_panel_w_different_object(self) -> None:
        spec = LensSpec()
        m64 = build_lens_maps(spec, 64)
        m128 = build_lens_maps(spec, 128)
        assert m64 is not m128


# ---------------------------------------------------------------------------
# LensMaps is a frozen dataclass (tuple fields)
# ---------------------------------------------------------------------------


class TestLensMapsShape:
    def test_lens_maps_fields_are_tuples(self) -> None:
        spec = LensSpec(magnify=1.3, edge_squeeze=0.6)
        maps = build_lens_maps(spec, 32)
        assert isinstance(maps.x_lut, tuple)
        assert isinstance(maps.vscale, tuple)
        # LensMaps is the frozen dataclass returned by build_lens_maps.
        assert isinstance(maps, LensMaps)

    def test_lens_maps_frozen(self) -> None:
        spec = LensSpec()
        maps = build_lens_maps(spec, 32)
        with pytest.raises((AttributeError, TypeError)):
            maps.x_lut = ()  # type: ignore[misc]


# ---------------------------------------------------------------------------
# lens_blit
# ---------------------------------------------------------------------------


def _solid_strip(
    w: int, h: int, color: tuple[int, int, int] = (200, 100, 50)
) -> PixelBuffer:
    """A fully-lit rectangular buffer — used for completeness and identity tests."""
    buf = PixelBuffer(w, h)
    for y in range(h):
        for x in range(w):
            buf.SetPixel(x, y, *color)
    return buf


class TestLensBlitIdentity:
    """Degenerate lens: magnify == edge_squeeze == 1.0 → 1:1 mapping."""

    def test_identity_lens_lut_properties(self) -> None:
        """With a degenerate lens (all s=1), vscale == 1 and span == w."""
        w = 32
        spec = LensSpec(magnify=1.0, edge_squeeze=1.0)
        maps = build_lens_maps(spec, w)

        # All vscale values should be 1.0.
        assert all(s == pytest.approx(1.0) for s in maps.vscale)
        # total_src_span should equal w.
        assert maps.total_src_span == pytest.approx(w)

    def test_identity_lens_constant_color_strip(self) -> None:
        """With a constant-color src (oversized by 1 to absorb rounding at the
        right edge), every dst pixel should reproduce that color.

        Midpoint sampling at identity: col x samples src at (x+0.5), which
        rounds to x+1 via int(sx + 0.5) truncation.  Making the src one
        column wider than the dst ensures col w-1 (sampling src col w) is
        in-bounds.  The color is uniform so the column chosen doesn't matter.
        """
        w, h = 32, 8
        spec = LensSpec(magnify=1.0, edge_squeeze=1.0)
        maps = build_lens_maps(spec, w)

        # Src is w+1 wide — absorbs the right-edge rounding offset.
        color = (123, 45, 67)
        src = _solid_strip(w + 1, h, color=color)

        dst = PixelBuffer(w, h)
        # At identity, total_src_span == w, src_x0 = 0.
        lens_blit(dst, src, maps, src_x0=0.0, cy=h / 2.0)

        # Every dst pixel should have the same color (all src pixels are identical).
        for y in range(h):
            for x in range(w):
                dst_color = dst.get(x, y)
                assert dst_color is not None, (
                    f"dst ({x}, {y}) unexpectedly unlit with identity lens"
                )
                assert dst_color == color, f"color mismatch at ({x}, {y})"


class TestLensBlitTransparency:
    def test_unset_src_never_paints(self) -> None:
        """Transparent (None) src pixels must not paint the dst background."""
        w, h = 16, 8
        spec = LensSpec(magnify=1.3, edge_squeeze=0.6)
        maps = build_lens_maps(spec, w)

        # Src is EMPTY.
        src = PixelBuffer(w * 2, h)
        dst = PixelBuffer(w, h)
        # Pre-fill dst with a sentinel color so we can detect painting.
        for y in range(h):
            for x in range(w):
                dst.SetPixel(x, y, 7, 7, 7)

        # After blit into an empty src, dst should remain unchanged.
        lens_blit(dst, src, maps, src_x0=0.0, cy=h / 2.0)

        for y in range(h):
            for x in range(w):
                assert dst.get(x, y) == (7, 7, 7), (
                    f"dst ({x}, {y}) was altered by blit of empty src"
                )


class TestLensBlitCenterAlignment:
    """Center-column alignment: dst center samples src_x0 + total_src_span/2."""

    def test_center_column_maps_to_src_midpoint(self) -> None:
        """For dst column cx_dst = w/2 − 0.5 (left edge of the center column),
        the midpoint sample is src_x0 + (x_lut[cx_dst] + x_lut[cx_dst+1]) / 2.

        The midpoint sample should equal total_src_span / 2 (± 0.5 column) when
        src_x0 == 0 (centered origin).
        """
        w = 64
        spec = LensSpec(magnify=1.3, edge_squeeze=0.6)
        maps = build_lens_maps(spec, w)

        # Center columns (for even w: columns w//2 - 1 and w//2).
        for cx in (w // 2 - 1, w // 2):
            mid = (maps.x_lut[cx] + maps.x_lut[cx + 1]) / 2.0
            # With src_x0 = 0, the sampled src x = mid.
            # Should equal total_src_span/2 ± 0.5.
            assert mid == pytest.approx(maps.total_src_span / 2.0, abs=1.0)


class TestLensBlitVertical:
    def test_center_row_invariant(self) -> None:
        """Row at y == cy maps to sy == cy in src (no vertical shift at center)."""
        w, h = 32, 16
        cy = h / 2.0  # 8.0
        spec = LensSpec(magnify=1.3, edge_squeeze=0.6)
        maps = build_lens_maps(spec, w)

        # src: only center row lit with a unique color.
        src_w = int(math.ceil(maps.total_src_span)) + 1
        src = PixelBuffer(src_w, h)
        center_row = int(cy)  # row 8
        color = (200, 100, 50)
        for x in range(src_w):
            src.SetPixel(x, center_row, *color)

        # Also light a different color one row above (should NOT appear in dst
        # center row due to the invariant).
        for x in range(src_w):
            src.SetPixel(x, center_row - 1, 9, 9, 9)

        dst = PixelBuffer(w, h)
        src_x0 = 0.0
        lens_blit(dst, src, maps, src_x0=src_x0, cy=cy)

        # dst center row should be lit with the center-row color.
        for x in range(w):
            px = dst.get(x, center_row)
            assert px is not None, f"dst center row x={x} unexpectedly unlit"
            assert px == color, f"dst ({x}, {center_row}) = {px!r}, want {color!r}"

    def test_squeezed_column_clips_rows_outside_src(self) -> None:
        """Edge columns (squeezed, vscale < 1) map a taller src band — rows
        whose sy falls outside [0, src.height) are transparent.

        With vscale[0] == edge_squeeze < 1, sy = cy + (y - cy) / vscale[0].
        At the top row (y=0), sy = cy + (0 - cy) / edge_squeeze
                                  = cy - cy / edge_squeeze.
        For cy=8, edge_squeeze=0.6: sy = 8 - 8/0.6 ≈ 8 - 13.3 = -5.3 → OOB.
        """
        w, h = 64, 16
        cy = h / 2.0
        spec = LensSpec(magnify=1.3, edge_squeeze=0.6)
        maps = build_lens_maps(spec, w)

        # src: every pixel lit.
        src_w = int(math.ceil(maps.total_src_span)) + 2
        src = _solid_strip(src_w, h)
        dst = PixelBuffer(w, h)
        lens_blit(dst, src, maps, src_x0=0.0, cy=cy)

        # Top row of the leftmost column should be transparent (sy < 0).
        vscale0 = maps.vscale[0]
        sy_top = cy + (0 - cy) / vscale0
        if sy_top < 0:
            px = dst.get(0, 0)
            assert px is None, (
                f"Expected top-left dst pixel to be transparent (sy={sy_top:.2f}), "
                f"but got {px!r}"
            )


class TestLensBlitCompleteness:
    """Solid strip → every interior dst pixel whose (sx, sy) lands in src is lit.

    This mirrors the rotate_blit "no holes" property: since the map is
    bijective (monotone cumulative integral), nearest-neighbor inverse mapping
    is hole-free.
    """

    def test_solid_strip_lights_all_interior_dst_pixels(self) -> None:
        w, h = 64, 8
        cy = h / 2.0
        spec = LensSpec(magnify=1.3, edge_squeeze=0.6)
        maps = build_lens_maps(spec, w)

        # Src: solid strip tall enough to cover the src-band at all columns.
        # total_src_span ≈ 1.134 * w at the defaults; add generous margin.
        src_w = int(math.ceil(maps.total_src_span)) + 4
        color = (200, 100, 50)
        src = _solid_strip(src_w, h, color=color)

        dst = PixelBuffer(w, h)
        lens_blit(dst, src, maps, src_x0=0.0, cy=cy)

        # For each dst column, compute the y-window [y0, y1) where sy is in-bounds.
        missing: list[tuple[int, int]] = []
        for x in range(w):
            mid_src_x = (maps.x_lut[x] + maps.x_lut[x + 1]) / 2.0
            # Horizontal: src_x0 + mid_src_x = mid_src_x (src_x0=0).
            isx = int(mid_src_x + 0.5)
            if not (0 <= isx < src_w):
                continue
            inv_v = 1.0 / maps.vscale[x]
            for y in range(h):
                sy_f = cy + (y - cy) * inv_v
                isy = int(sy_f + 0.5)
                if 0 <= isy < h:
                    px = dst.get(x, y)
                    if px is None:
                        missing.append((x, y))

        assert missing == [], (
            f"lens_blit left {len(missing)} interior dst pixels unlit: {missing[:5]}"
        )

    def test_full_sweep(self) -> None:
        """Every dst column is lit somewhere (no fully-dark column) for a solid src."""
        w, h = 64, 16
        cy = h / 2.0
        spec = LensSpec(magnify=1.3, edge_squeeze=0.6)
        maps = build_lens_maps(spec, w)

        src_w = int(math.ceil(maps.total_src_span)) + 4
        src = _solid_strip(src_w, h)
        dst = PixelBuffer(w, h)
        lens_blit(dst, src, maps, src_x0=0.0, cy=cy)

        for x in range(w):
            lit = any(dst.get(x, y) is not None for y in range(h))
            assert lit, f"dst column {x} is completely dark"


# ---------------------------------------------------------------------------
# AnimationFrame — lens field
# ---------------------------------------------------------------------------


class TestAnimationFrameLens:
    def test_lens_defaults_to_none(self) -> None:
        frame = AnimationFrame(visible_text="HELLO")
        assert frame.lens is None

    def test_lens_keyword_settable(self) -> None:
        spec = LensSpec(magnify=1.5, edge_squeeze=0.7)
        frame = AnimationFrame(visible_text="HI", lens=spec)
        assert frame.lens is spec

    def test_rotation_only_frame_has_none_lens(self) -> None:
        frame = AnimationFrame(visible_text="TEST", rotation=45.0)
        assert frame.lens is None
        assert frame.rotation == 45.0

    def test_lens_only_frame_has_zero_rotation(self) -> None:
        spec = LensSpec()
        frame = AnimationFrame(visible_text="TEST", lens=spec)
        assert frame.rotation == 0.0
        assert frame.lens is spec

    def test_rotation_and_lens_can_coexist(self) -> None:
        """They CAN coexist in the dataclass (widget integration can raise if
        both are non-default, but the data type doesn't forbid it)."""
        spec = LensSpec()
        frame = AnimationFrame(visible_text="X", rotation=10.0, lens=spec)
        assert frame.rotation == 10.0
        assert frame.lens is spec
