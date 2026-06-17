"""Tests for the hi-res transition loader and renderer.

The built-in nyancat/pokeball entries in the old _hires_registry.py were removed when
those transitions were extracted to the led-ticker-arcade plugin. The tests below cover
the retained public infrastructure (HiresSpec, load_hires, render_hires_frame) using
tmp_path sprites — no production sprites needed.
"""

from __future__ import annotations

import unittest.mock as _mock_mod

import pytest


def _make_tiny_sprite(tmp_path, *, n_frames=2, size=(8, 8), durations=(50, 100)):
    """Generate a tiny transparent GIF: a magenta filled square + alpha."""
    from PIL import Image

    frames = []
    for i in range(n_frames):
        img = Image.new("RGBA", size, (0, 0, 0, 0))
        # paint a 4x4 colored block in the upper-left so non-black-pixel
        # counting is predictable
        color = (255, 0, 128, 255) if i == 0 else (0, 255, 200, 255)
        for y in range(4):
            for x in range(4):
                img.putpixel((x, y), color)
        frames.append(img)
    path = tmp_path / "tiny.gif"
    frames[0].save(
        path,
        save_all=True,
        append_images=frames[1:],
        duration=list(durations[:n_frames]),
        loop=0,
        disposal=2,
    )
    return path


@pytest.fixture(autouse=True)
def _clear_loader_cache():
    """Ensure load_hires's @functools.cache is cleared between tests so
    monkeypatched registry entries don't leak."""
    from led_ticker.transitions._hires_loader import load_hires

    load_hires.cache_clear()
    yield
    load_hires.cache_clear()


class TestFrameForElapsed:
    def test_picks_first_frame_at_zero(self):
        from led_ticker.transitions._hires_loader import _frame_for_elapsed

        assert _frame_for_elapsed(0, durations=[100, 100, 100]) == 0

    def test_picks_second_frame_after_first_duration(self):
        from led_ticker.transitions._hires_loader import _frame_for_elapsed

        # 0 .. <100 = frame 0; 100 .. <200 = frame 1
        assert _frame_for_elapsed(99, durations=[100, 100, 100]) == 0
        assert _frame_for_elapsed(100, durations=[100, 100, 100]) == 1
        assert _frame_for_elapsed(199, durations=[100, 100, 100]) == 1
        assert _frame_for_elapsed(200, durations=[100, 100, 100]) == 2

    def test_wraps_at_total_loop_ms(self):
        from led_ticker.transitions._hires_loader import _frame_for_elapsed

        # total = 300; elapsed=350 -> pos=50 -> frame 0
        assert _frame_for_elapsed(350, durations=[100, 100, 100]) == 0


class TestLoadHires:
    def test_decodes_tiny_sprite(self, tmp_path):
        from led_ticker.transitions._hires_loader import HiresSpec, load_hires

        path = _make_tiny_sprite(tmp_path)
        spec = HiresSpec(sprite_path=path, flip_horizontal=False)
        frames = load_hires(spec)
        # Source is 8x8; scaled to fit panel_h=64 -> 64x64 (no width change since w==h).
        assert frames.height == 64
        assert frames.width == 64
        assert len(frames.durations_ms) == 2
        assert frames.total_loop_ms == sum(frames.durations_ms)
        assert len(frames.non_black) == 2
        # The 4x4 block at (0,0) becomes 32x32 at scale 8x; expect ~1024 lit pixels.
        assert len(frames.non_black[0]) == 32 * 32

    def test_caches_decoded_frames(self, tmp_path):
        from led_ticker.transitions._hires_loader import HiresSpec, load_hires

        path = _make_tiny_sprite(tmp_path)
        spec = HiresSpec(sprite_path=path, flip_horizontal=False)
        first = load_hires(spec)
        second = load_hires(spec)
        assert first is second  # @functools.cache returns the same object

    def test_flip_horizontal_mirrors_pixel_x(self, tmp_path):
        from led_ticker.transitions._hires_loader import HiresSpec, load_hires

        path = _make_tiny_sprite(tmp_path)
        base_spec = HiresSpec(sprite_path=path, flip_horizontal=False)
        flipped_spec = HiresSpec(sprite_path=path, flip_horizontal=True)
        base = load_hires(base_spec)
        flipped = load_hires(flipped_spec)

        # In base, lit pixels are at x in [0, 32); in flipped at x in [width-32, width).
        base_xs = {x for (x, y, r, g, b) in base.non_black[0]}
        flipped_xs = {x for (x, y, r, g, b) in flipped.non_black[0]}
        assert max(base_xs) < base.width // 2
        assert min(flipped_xs) >= flipped.width // 2

    def test_decodes_animated_webp_durations(self, tmp_path):
        """Regression: animated WebP populates `info["duration"]` only after
        `convert("RGBA")` forces frame decode. Locks in that ordering — a
        future refactor that reads `info` before `convert` would default
        every frame to 50ms here."""
        from PIL import Image

        from led_ticker.transitions._hires_loader import HiresSpec, load_hires

        # Build a 2-frame animated WebP with non-default durations (100ms, 250ms).
        frames = []
        for i in range(2):
            img = Image.new("RGBA", (8, 8), (0, 0, 0, 0))
            for y in range(4):
                for x in range(4):
                    img.putpixel(
                        (x, y),
                        (255, 0, 128, 255) if i == 0 else (0, 255, 200, 255),
                    )
            frames.append(img)
        path = tmp_path / "animated.webp"
        frames[0].save(
            path,
            format="WebP",
            save_all=True,
            append_images=frames[1:],
            duration=[100, 250],
            lossless=True,
        )

        spec = HiresSpec(sprite_path=path, flip_horizontal=False)
        decoded = load_hires(spec)
        assert len(decoded.durations_ms) == 2
        # Both should be the meaningful values we set, NOT the 50ms fallback.
        # (Pillow may round so check non-default rather than exact equality.)
        assert decoded.durations_ms[0] != 50, (
            "first frame got the 50ms fallback duration — convert() must "
            "happen before info.get('duration')"
        )
        assert decoded.durations_ms[1] != 50
        # And they should reflect the configured non-equal pair (a Pillow
        # quirk that wrote both as identical would still be a regression).
        assert decoded.durations_ms[0] != decoded.durations_ms[1]


class TestRenderHiresFrame:
    def _setup(self, tmp_path):
        """Build a fixture sprite spec and return (real_canvas, scaled_canvas, spec)."""
        from rgbmatrix import RGBMatrix, RGBMatrixOptions

        from led_ticker.scaled_canvas import ScaledCanvas
        from led_ticker.transitions._hires_loader import HiresSpec

        path = _make_tiny_sprite(tmp_path)
        spec = HiresSpec(sprite_path=path, flip_horizontal=False)
        opts = RGBMatrixOptions()
        opts.cols = 256
        opts.rows = 64
        opts.chain_length = 1
        opts.parallel = 1
        real = RGBMatrix(options=opts).CreateFrameCanvas()
        wrapped = ScaledCanvas(real, scale=4, content_height=16)
        return real, wrapped, spec

    def test_paints_to_unwrapped_real_canvas(self, tmp_path):
        from led_ticker.transitions._hires_loader import render_hires_frame

        real, wrapped, spec = self._setup(tmp_path)
        outgoing = _mock_mod.MagicMock()
        incoming = _mock_mod.MagicMock()
        render_hires_frame(0.5, wrapped, outgoing, incoming, spec, duration_ms=500)

        # The fixture sprite's lit pixels should appear on the REAL canvas
        # (256-wide), not at logical wrapper coordinates (64-wide).
        lit = sum(
            1
            for x in range(real.width)
            for y in range(real.height)
            if real.get_pixel(x, y) != (0, 0, 0)
        )
        assert lit > 0
        # outgoing.draw was called through the wrapper (logical coords).
        outgoing.draw.assert_called_once()
        assert outgoing.draw.call_args.args[0] is wrapped

    def test_snaps_to_incoming_above_threshold(self, tmp_path):
        from led_ticker.transitions._hires_loader import render_hires_frame

        real, wrapped, spec = self._setup(tmp_path)
        outgoing = _mock_mod.MagicMock()
        incoming = _mock_mod.MagicMock()
        render_hires_frame(0.96, wrapped, outgoing, incoming, spec, duration_ms=500)
        incoming.draw.assert_called_once()

    def test_does_not_snap_below_threshold(self, tmp_path):
        from led_ticker.transitions._hires_loader import render_hires_frame

        real, wrapped, spec = self._setup(tmp_path)
        outgoing = _mock_mod.MagicMock()
        incoming = _mock_mod.MagicMock()
        render_hires_frame(0.5, wrapped, outgoing, incoming, spec, duration_ms=500)
        incoming.draw.assert_not_called()

    def test_clips_pixels_outside_panel_width(self, tmp_path):
        from led_ticker.transitions._hires_loader import render_hires_frame

        real, wrapped, spec = self._setup(tmp_path)
        outgoing = _mock_mod.MagicMock()
        incoming = _mock_mod.MagicMock()
        # At t=0, sprite_x = -sprite.width -- sprite is fully off-left.
        # All sprite pixels have rx < 0, so the clip guard discards them all.
        # The real canvas should have zero lit pixels (outgoing mock draws nothing).
        render_hires_frame(0.0, wrapped, outgoing, incoming, spec, duration_ms=500)
        assert real.count_nonzero() == 0


class TestRenderHiresTrail:
    def _setup_with_trail(self, tmp_path, *, trail, flip_horizontal=False):
        from rgbmatrix import RGBMatrix, RGBMatrixOptions

        from led_ticker.scaled_canvas import ScaledCanvas
        from led_ticker.transitions._hires_loader import HiresSpec

        path = _make_tiny_sprite(tmp_path)
        spec = HiresSpec(
            sprite_path=path,
            flip_horizontal=flip_horizontal,
            trail=trail,
        )
        opts = RGBMatrixOptions()
        opts.cols = 256
        opts.rows = 64
        opts.chain_length = 1
        opts.parallel = 1
        real = RGBMatrix(options=opts).CreateFrameCanvas()
        wrapped = ScaledCanvas(real, scale=4, content_height=16)
        return real, wrapped, spec

    def test_no_trail_does_not_paint_behind_sprite(self, tmp_path):
        from led_ticker.transitions._hires_loader import render_hires_frame

        real, wrapped, spec = self._setup_with_trail(tmp_path, trail="none")
        outgoing = _mock_mod.MagicMock()
        incoming = _mock_mod.MagicMock()
        # At t=0.5, sprite is roughly mid-screen.
        render_hires_frame(0.5, wrapped, outgoing, incoming, spec, duration_ms=500)
        # No trail painted: pixels in the trail region (x=0..sprite_x) should
        # be untouched (still black from the canvas's initial state since
        # outgoing is a Mock that doesn't paint).
        # We can't precisely assert "untouched" without geometry; we assert
        # that NO non-black pixel exists at x=0 (left edge), which is the
        # leftmost trail pixel.
        for y in range(real.height):
            assert real.get_pixel(0, y) == (0, 0, 0)

    def test_black_trail_erases_outgoing_in_trail_region(self, tmp_path):
        from led_ticker.transitions._hires_loader import render_hires_frame

        real, wrapped, spec = self._setup_with_trail(tmp_path, trail="black")
        # Pre-paint outgoing as a fully-lit canvas (red everywhere) so we can
        # verify the trail erases.
        for y in range(real.height):
            for x in range(real.width):
                real.SetPixel(x, y, 255, 0, 0)

        outgoing = _mock_mod.MagicMock()
        incoming = _mock_mod.MagicMock()
        render_hires_frame(0.5, wrapped, outgoing, incoming, spec, duration_ms=500)

        # At t=0.5: sprite_x is roughly in the middle. Pixels at x=0 (far
        # left, well within the trail region) should now be black.
        assert real.get_pixel(0, 0) == (0, 0, 0)
        assert real.get_pixel(0, real.height // 2) == (0, 0, 0)
        # Pixels at x=panel_w-1 (far right, beyond the sprite) should still
        # be the original red -- trail doesn't extend right of the sprite.
        assert real.get_pixel(real.width - 1, 0) == (255, 0, 0)

    def test_rainbow_trail_paints_six_horizontal_stripes(self, tmp_path):
        from led_ticker.transitions._hires_loader import (
            _RAINBOW_TRAIL_COLORS,
            render_hires_frame,
        )

        real, wrapped, spec = self._setup_with_trail(tmp_path, trail="rainbow")
        outgoing = _mock_mod.MagicMock()
        incoming = _mock_mod.MagicMock()
        render_hires_frame(0.5, wrapped, outgoing, incoming, spec, duration_ms=500)

        panel_h = real.height
        n_stripes = len(_RAINBOW_TRAIL_COLORS)
        # Sample the center of each stripe at x=0 (far left, within the
        # trail) and verify color matches the registered RAINBOW.
        for stripe_idx, expected_color in enumerate(_RAINBOW_TRAIL_COLORS):
            y_start = stripe_idx * panel_h // n_stripes
            y_end = (
                (stripe_idx + 1) * panel_h // n_stripes
                if stripe_idx < n_stripes - 1
                else panel_h
            )
            sample_y = (y_start + y_end) // 2
            assert real.get_pixel(0, sample_y) == expected_color, (
                f"stripe {stripe_idx} at y={sample_y}: "
                f"expected {expected_color}, got {real.get_pixel(0, sample_y)}"
            )

    def test_reverse_trail_extends_from_sprite_to_right_edge(self, tmp_path):
        """For flip_horizontal=True, the trail goes from the sprite's right
        edge to the panel's right edge (not from the left edge)."""
        from led_ticker.transitions._hires_loader import render_hires_frame

        real, wrapped, spec = self._setup_with_trail(
            tmp_path, trail="black", flip_horizontal=True
        )
        # Pre-paint canvas red.
        for y in range(real.height):
            for x in range(real.width):
                real.SetPixel(x, y, 255, 0, 0)

        outgoing = _mock_mod.MagicMock()
        incoming = _mock_mod.MagicMock()
        render_hires_frame(0.5, wrapped, outgoing, incoming, spec, duration_ms=500)

        # Reverse direction: at t=0.5, sprite is mid-screen moving left.
        # Pixels at x=panel_w-1 (rightmost) should be black (trail).
        # Pixels at x=0 (leftmost) should still be red (no trail painted there).
        assert real.get_pixel(real.width - 1, 0) == (0, 0, 0)
        assert real.get_pixel(0, 0) == (255, 0, 0)

    def test_ltr_trail_fills_full_panel_by_saturation_t(self, tmp_path):
        """At t=TRAIL_SATURATION_T, the LTR trail must reach the rightmost
        column. Guards the 'cut happens before rainbow hits the far edge'
        regression — trail must saturate before snap so the cut happens
        on a fully-covered panel."""
        from led_ticker.transitions._hires_loader import (
            _RAINBOW_TRAIL_COLORS,
            TRAIL_SATURATION_T,
            render_hires_frame,
        )

        real, wrapped, spec = self._setup_with_trail(
            tmp_path, trail="rainbow", flip_horizontal=False
        )
        outgoing = _mock_mod.MagicMock()
        incoming = _mock_mod.MagicMock()
        render_hires_frame(
            TRAIL_SATURATION_T,
            wrapped,
            outgoing,
            incoming,
            spec,
            duration_ms=500,
        )
        # Rightmost column at row 0 should be the first rainbow stripe color.
        assert real.get_pixel(real.width - 1, 0) == _RAINBOW_TRAIL_COLORS[0]

    def test_rtl_trail_fills_full_panel_by_saturation_t(self, tmp_path):
        """Mirror check for RTL."""
        from led_ticker.transitions._hires_loader import (
            _RAINBOW_TRAIL_COLORS,
            TRAIL_SATURATION_T,
            render_hires_frame,
        )

        real, wrapped, spec = self._setup_with_trail(
            tmp_path, trail="rainbow", flip_horizontal=True
        )
        outgoing = _mock_mod.MagicMock()
        incoming = _mock_mod.MagicMock()
        render_hires_frame(
            TRAIL_SATURATION_T,
            wrapped,
            outgoing,
            incoming,
            spec,
            duration_ms=500,
        )
        # Leftmost column at row 0 should be the first rainbow stripe color.
        assert real.get_pixel(0, 0) == _RAINBOW_TRAIL_COLORS[0]

    def test_trail_holds_after_saturation_until_snap(self, tmp_path):
        """Between TRAIL_SATURATION_T and SNAP_THRESHOLD, the trail stays
        fully covering — the 'hold' phase before the cut."""
        from led_ticker.transitions._hires_loader import (
            _RAINBOW_TRAIL_COLORS,
            SNAP_THRESHOLD,
            TRAIL_SATURATION_T,
            render_hires_frame,
        )

        real, wrapped, spec = self._setup_with_trail(
            tmp_path, trail="rainbow", flip_horizontal=False
        )
        outgoing = _mock_mod.MagicMock()
        incoming = _mock_mod.MagicMock()
        # Mid-hold phase
        mid_hold_t = (TRAIL_SATURATION_T + SNAP_THRESHOLD) / 2
        render_hires_frame(
            mid_hold_t,
            wrapped,
            outgoing,
            incoming,
            spec,
            duration_ms=500,
        )
        # Right edge is still covered.
        assert real.get_pixel(real.width - 1, 0) == _RAINBOW_TRAIL_COLORS[0]
        # And incoming wasn't called yet (still pre-snap).
        incoming.draw.assert_not_called()

    def test_rtl_rainbow_trail_holds_after_saturation_until_snap(self, tmp_path):
        """Mirror of test_trail_holds_after_saturation_until_snap, RTL."""
        from led_ticker.transitions._hires_loader import (
            _RAINBOW_TRAIL_COLORS,
            SNAP_THRESHOLD,
            TRAIL_SATURATION_T,
            render_hires_frame,
        )

        real, wrapped, spec = self._setup_with_trail(
            tmp_path, trail="rainbow", flip_horizontal=True
        )
        outgoing = _mock_mod.MagicMock()
        incoming = _mock_mod.MagicMock()
        mid_hold_t = (TRAIL_SATURATION_T + SNAP_THRESHOLD) / 2
        render_hires_frame(
            mid_hold_t,
            wrapped,
            outgoing,
            incoming,
            spec,
            duration_ms=500,
        )
        # Left edge is still covered (RTL trail goes from sprite to right edge,
        # but during hold both ends are covered).
        assert real.get_pixel(0, 0) == _RAINBOW_TRAIL_COLORS[0]
        incoming.draw.assert_not_called()

    def test_ltr_black_trail_fills_full_panel_by_saturation_t(self, tmp_path):
        """Black trail equivalent of the rainbow saturation test."""
        from led_ticker.transitions._hires_loader import (
            TRAIL_SATURATION_T,
            render_hires_frame,
        )

        real, wrapped, spec = self._setup_with_trail(
            tmp_path, trail="black", flip_horizontal=False
        )
        # Pre-paint canvas red so we can detect the trail.
        for y in range(real.height):
            for x in range(real.width):
                real.SetPixel(x, y, 255, 0, 0)

        outgoing = _mock_mod.MagicMock()
        incoming = _mock_mod.MagicMock()
        render_hires_frame(
            TRAIL_SATURATION_T,
            wrapped,
            outgoing,
            incoming,
            spec,
            duration_ms=500,
        )
        # Right edge column should now be black (trail) — original red gone.
        # Sample at row 0 to avoid the procedural pokeball if it's painted.
        assert real.get_pixel(real.width - 1, 0) == (0, 0, 0)

    def test_rtl_black_trail_holds_after_saturation_until_snap(self, tmp_path):
        """RTL black trail mirror."""
        from led_ticker.transitions._hires_loader import (
            SNAP_THRESHOLD,
            TRAIL_SATURATION_T,
            render_hires_frame,
        )

        real, wrapped, spec = self._setup_with_trail(
            tmp_path, trail="black", flip_horizontal=True
        )
        for y in range(real.height):
            for x in range(real.width):
                real.SetPixel(x, y, 255, 0, 0)

        outgoing = _mock_mod.MagicMock()
        incoming = _mock_mod.MagicMock()
        mid_hold_t = (TRAIL_SATURATION_T + SNAP_THRESHOLD) / 2
        render_hires_frame(
            mid_hold_t,
            wrapped,
            outgoing,
            incoming,
            spec,
            duration_ms=500,
        )
        # During RTL hold, the left edge is covered (trail extends from
        # sprite — now off-left — to panel right edge, but at full
        # saturation both ends are covered).
        assert real.get_pixel(0, 0) == (0, 0, 0)
        incoming.draw.assert_not_called()


# ---------------------------------------------------------------------------
# Phase 2 tests: render_hires_frame / load_hires take a HiresSpec directly.
#
# The renderer no longer reaches into a core registry — a spec
# that was never registered still decodes and renders, which is what lets
# an out-of-tree plugin supply its own sprite.
# ---------------------------------------------------------------------------


def _make_sprite(path, frames=2, size=(8, 8)):
    from PIL import Image

    imgs = [Image.new("RGBA", size, (255, 0, 0, 255)) for _ in range(frames)]
    imgs[0].save(path, save_all=True, append_images=imgs[1:], duration=50, loop=0)
    return path


def test_render_hires_frame_signature_takes_spec():
    import inspect

    from led_ticker.transitions._hires_loader import render_hires_frame

    params = list(inspect.signature(render_hires_frame).parameters)
    assert params[:5] == ["t", "canvas", "outgoing", "incoming", "spec"]


def test_load_hires_decodes_an_unregistered_spec(tmp_path):
    from led_ticker.transitions._hires_loader import HiresSpec, load_hires

    sprite = _make_sprite(tmp_path / "s.gif")
    spec = HiresSpec(sprite_path=sprite, flip_horizontal=False, trail="none")
    frames = load_hires(spec)
    assert frames is not None
    assert frames.width > 0 and frames.height > 0


def test_load_hires_caches_on_spec(tmp_path):
    from led_ticker.transitions._hires_loader import HiresSpec, load_hires

    sprite = _make_sprite(tmp_path / "s.gif")
    spec = HiresSpec(sprite_path=sprite, flip_horizontal=False, trail="none")
    assert load_hires(spec) is load_hires(spec)
    flipped = HiresSpec(sprite_path=sprite, flip_horizontal=True, trail="none")
    assert load_hires(flipped) is not load_hires(spec)
