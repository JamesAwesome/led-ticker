"""Tests for the hi-res transition registry, loader, and renderer."""

from __future__ import annotations

import unittest.mock as _mock_mod

import pytest


class TestHiresRegistry:
    def test_registry_has_exactly_four_entries(self):
        from led_ticker.transitions._hires_registry import HIRES_REGISTRY

        assert set(HIRES_REGISTRY.keys()) == {
            "nyancat",
            "nyancat_reverse",
            "pokeball",
            "pokeball_reverse",
        }

    def test_nyancat_uses_webp_no_flip(self):
        from led_ticker.transitions._hires_registry import HIRES_REGISTRY

        spec = HIRES_REGISTRY["nyancat"]
        assert spec.sprite_path.name == "nyancat.webp"
        assert spec.flip_horizontal is False

    def test_nyancat_reverse_uses_same_file_with_flip(self):
        from led_ticker.transitions._hires_registry import HIRES_REGISTRY

        base = HIRES_REGISTRY["nyancat"]
        rev = HIRES_REGISTRY["nyancat_reverse"]
        assert rev.sprite_path == base.sprite_path
        assert rev.flip_horizontal is True

    def test_pokeball_uses_gif_no_flip(self):
        from led_ticker.transitions._hires_registry import HIRES_REGISTRY

        spec = HIRES_REGISTRY["pokeball"]
        assert spec.sprite_path.name == "pokeball.gif"
        assert spec.flip_horizontal is False

    def test_pokeball_reverse_uses_same_file_with_flip(self):
        from led_ticker.transitions._hires_registry import HIRES_REGISTRY

        base = HIRES_REGISTRY["pokeball"]
        rev = HIRES_REGISTRY["pokeball_reverse"]
        assert rev.sprite_path == base.sprite_path
        assert rev.flip_horizontal is True

    def test_sprite_paths_are_absolute_and_exist(self):
        from led_ticker.transitions._hires_registry import HIRES_REGISTRY

        for name, spec in HIRES_REGISTRY.items():
            assert spec.sprite_path.is_absolute(), f"{name} path not absolute"
            assert spec.sprite_path.exists(), f"{name} sprite file missing"


class _StubColor:
    def __init__(self, r, g, b):
        self.red = r
        self.green = g
        self.blue = b


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
    def test_returns_none_for_unregistered_name(self):
        from led_ticker.transitions._hires_loader import load_hires

        assert load_hires("not_a_real_transition") is None

    def test_decodes_tiny_sprite(self, tmp_path, monkeypatch):
        from led_ticker.transitions import _hires_registry
        from led_ticker.transitions._hires_loader import load_hires
        from led_ticker.transitions._hires_registry import HiresSpec

        path = _make_tiny_sprite(tmp_path)
        monkeypatch.setitem(
            _hires_registry.HIRES_REGISTRY,
            "test_sprite",
            HiresSpec(sprite_path=path, flip_horizontal=False),
        )
        frames = load_hires("test_sprite")
        assert frames is not None
        # Source is 8x8; scaled to fit panel_h=64 -> 64x64 (no width change since w==h).
        assert frames.height == 64
        assert frames.width == 64
        assert len(frames.durations_ms) == 2
        assert frames.total_loop_ms == sum(frames.durations_ms)
        assert len(frames.non_black) == 2
        # The 4x4 block at (0,0) becomes 32x32 at scale 8x; expect ~1024 lit pixels.
        assert len(frames.non_black[0]) == 32 * 32

    def test_caches_decoded_frames(self, tmp_path, monkeypatch):
        from led_ticker.transitions import _hires_registry
        from led_ticker.transitions._hires_loader import load_hires
        from led_ticker.transitions._hires_registry import HiresSpec

        path = _make_tiny_sprite(tmp_path)
        monkeypatch.setitem(
            _hires_registry.HIRES_REGISTRY,
            "test_sprite",
            HiresSpec(sprite_path=path, flip_horizontal=False),
        )
        first = load_hires("test_sprite")
        second = load_hires("test_sprite")
        assert first is second  # @functools.cache returns the same object

    def test_flip_horizontal_mirrors_pixel_x(self, tmp_path, monkeypatch):
        from led_ticker.transitions import _hires_registry
        from led_ticker.transitions._hires_loader import load_hires
        from led_ticker.transitions._hires_registry import HiresSpec

        path = _make_tiny_sprite(tmp_path)
        monkeypatch.setitem(
            _hires_registry.HIRES_REGISTRY,
            "base",
            HiresSpec(sprite_path=path, flip_horizontal=False),
        )
        monkeypatch.setitem(
            _hires_registry.HIRES_REGISTRY,
            "flipped",
            HiresSpec(sprite_path=path, flip_horizontal=True),
        )
        base = load_hires("base")
        flipped = load_hires("flipped")
        assert base is not None and flipped is not None

        # In base, lit pixels are at x in [0, 32); in flipped at x in [width-32, width).
        base_xs = {x for (x, y, r, g, b) in base.non_black[0]}
        flipped_xs = {x for (x, y, r, g, b) in flipped.non_black[0]}
        assert max(base_xs) < base.width // 2
        assert min(flipped_xs) >= flipped.width // 2


class TestRenderHiresFrame:
    def _setup(self, tmp_path, monkeypatch):
        """Register a fixture sprite and return (real_canvas, scaled_canvas, name)."""
        from rgbmatrix import RGBMatrix, RGBMatrixOptions

        from led_ticker.scaled_canvas import ScaledCanvas
        from led_ticker.transitions import _hires_registry
        from led_ticker.transitions._hires_registry import HiresSpec

        path = _make_tiny_sprite(tmp_path)
        monkeypatch.setitem(
            _hires_registry.HIRES_REGISTRY,
            "test_sprite",
            HiresSpec(sprite_path=path, flip_horizontal=False),
        )
        opts = RGBMatrixOptions()
        opts.cols = 256
        opts.rows = 64
        opts.chain_length = 1
        opts.parallel = 1
        real = RGBMatrix(options=opts).CreateFrameCanvas()
        wrapped = ScaledCanvas(real, scale=4, content_height=16)
        return real, wrapped, "test_sprite"

    def test_paints_to_unwrapped_real_canvas(self, tmp_path, monkeypatch):
        from led_ticker.transitions._hires_loader import render_hires_frame

        real, wrapped, name = self._setup(tmp_path, monkeypatch)
        outgoing = _mock_mod.MagicMock()
        incoming = _mock_mod.MagicMock()
        render_hires_frame(0.5, wrapped, outgoing, incoming, name, duration_ms=500)

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

    def test_snaps_to_incoming_above_threshold(self, tmp_path, monkeypatch):
        from led_ticker.transitions._hires_loader import render_hires_frame

        real, wrapped, name = self._setup(tmp_path, monkeypatch)
        outgoing = _mock_mod.MagicMock()
        incoming = _mock_mod.MagicMock()
        render_hires_frame(0.96, wrapped, outgoing, incoming, name, duration_ms=500)
        incoming.draw.assert_called_once()

    def test_does_not_snap_below_threshold(self, tmp_path, monkeypatch):
        from led_ticker.transitions._hires_loader import render_hires_frame

        real, wrapped, name = self._setup(tmp_path, monkeypatch)
        outgoing = _mock_mod.MagicMock()
        incoming = _mock_mod.MagicMock()
        render_hires_frame(0.5, wrapped, outgoing, incoming, name, duration_ms=500)
        incoming.draw.assert_not_called()

    def test_clips_pixels_outside_panel_width(self, tmp_path, monkeypatch):
        from led_ticker.transitions._hires_loader import render_hires_frame

        real, wrapped, name = self._setup(tmp_path, monkeypatch)
        outgoing = _mock_mod.MagicMock()
        incoming = _mock_mod.MagicMock()
        # At t=0, sprite_x = -sprite.width -- sprite is fully off-left.
        # All sprite pixels have rx < 0, so the clip guard discards them all.
        # The real canvas should have zero lit pixels (outgoing mock draws nothing).
        render_hires_frame(0.0, wrapped, outgoing, incoming, name, duration_ms=500)
        assert real.count_nonzero() == 0

    def test_unknown_registry_name_returns_canvas_unchanged(
        self, tmp_path, monkeypatch
    ):
        from led_ticker.transitions._hires_loader import render_hires_frame

        real, wrapped, _ = self._setup(tmp_path, monkeypatch)
        outgoing = _mock_mod.MagicMock()
        incoming = _mock_mod.MagicMock()
        result = render_hires_frame(
            0.5, wrapped, outgoing, incoming, "not_in_registry", duration_ms=500
        )
        assert result is wrapped
        outgoing.draw.assert_not_called()


class TestRenderHiresTrail:
    def _setup_with_trail(self, tmp_path, monkeypatch, *, trail, flip_horizontal=False):
        from rgbmatrix import RGBMatrix, RGBMatrixOptions

        from led_ticker.scaled_canvas import ScaledCanvas
        from led_ticker.transitions import _hires_registry
        from led_ticker.transitions._hires_registry import HiresSpec

        path = _make_tiny_sprite(tmp_path)
        monkeypatch.setitem(
            _hires_registry.HIRES_REGISTRY,
            "test_sprite",
            HiresSpec(
                sprite_path=path,
                flip_horizontal=flip_horizontal,
                trail=trail,
            ),
        )
        opts = RGBMatrixOptions()
        opts.cols = 256
        opts.rows = 64
        opts.chain_length = 1
        opts.parallel = 1
        real = RGBMatrix(options=opts).CreateFrameCanvas()
        wrapped = ScaledCanvas(real, scale=4, content_height=16)
        return real, wrapped, "test_sprite"

    def test_no_trail_does_not_paint_behind_sprite(self, tmp_path, monkeypatch):
        from led_ticker.transitions._hires_loader import render_hires_frame

        real, wrapped, name = self._setup_with_trail(
            tmp_path, monkeypatch, trail="none"
        )
        outgoing = _mock_mod.MagicMock()
        incoming = _mock_mod.MagicMock()
        # At t=0.5, sprite is roughly mid-screen.
        render_hires_frame(0.5, wrapped, outgoing, incoming, name, duration_ms=500)
        # No trail painted: pixels in the trail region (x=0..sprite_x) should
        # be untouched (still black from the canvas's initial state since
        # outgoing is a Mock that doesn't paint).
        # We can't precisely assert "untouched" without geometry; we assert
        # that NO non-black pixel exists at x=0 (left edge), which is the
        # leftmost trail pixel.
        for y in range(real.height):
            assert real.get_pixel(0, y) == (0, 0, 0)

    def test_black_trail_erases_outgoing_in_trail_region(self, tmp_path, monkeypatch):
        from led_ticker.transitions._hires_loader import render_hires_frame

        real, wrapped, name = self._setup_with_trail(
            tmp_path, monkeypatch, trail="black"
        )
        # Pre-paint outgoing as a fully-lit canvas (red everywhere) so we can
        # verify the trail erases.
        for y in range(real.height):
            for x in range(real.width):
                real.SetPixel(x, y, 255, 0, 0)

        outgoing = _mock_mod.MagicMock()
        incoming = _mock_mod.MagicMock()
        render_hires_frame(0.5, wrapped, outgoing, incoming, name, duration_ms=500)

        # At t=0.5: sprite_x is roughly in the middle. Pixels at x=0 (far
        # left, well within the trail region) should now be black.
        assert real.get_pixel(0, 0) == (0, 0, 0)
        assert real.get_pixel(0, real.height // 2) == (0, 0, 0)
        # Pixels at x=panel_w-1 (far right, beyond the sprite) should still
        # be the original red -- trail doesn't extend right of the sprite.
        assert real.get_pixel(real.width - 1, 0) == (255, 0, 0)

    def test_rainbow_trail_paints_six_horizontal_stripes(self, tmp_path, monkeypatch):
        from led_ticker.transitions._hires_loader import (
            _RAINBOW_TRAIL_COLORS,
            render_hires_frame,
        )

        real, wrapped, name = self._setup_with_trail(
            tmp_path, monkeypatch, trail="rainbow"
        )
        outgoing = _mock_mod.MagicMock()
        incoming = _mock_mod.MagicMock()
        render_hires_frame(0.5, wrapped, outgoing, incoming, name, duration_ms=500)

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

    def test_reverse_trail_extends_from_sprite_to_right_edge(
        self, tmp_path, monkeypatch
    ):
        """For flip_horizontal=True, the trail goes from the sprite's right
        edge to the panel's right edge (not from the left edge)."""
        from led_ticker.transitions._hires_loader import render_hires_frame

        real, wrapped, name = self._setup_with_trail(
            tmp_path,
            monkeypatch,
            trail="black",
            flip_horizontal=True,
        )
        # Pre-paint canvas red.
        for y in range(real.height):
            for x in range(real.width):
                real.SetPixel(x, y, 255, 0, 0)

        outgoing = _mock_mod.MagicMock()
        incoming = _mock_mod.MagicMock()
        render_hires_frame(0.5, wrapped, outgoing, incoming, name, duration_ms=500)

        # Reverse direction: at t=0.5, sprite is mid-screen moving left.
        # Pixels at x=panel_w-1 (rightmost) should be black (trail).
        # Pixels at x=0 (leftmost) should still be red (no trail painted there).
        assert real.get_pixel(real.width - 1, 0) == (0, 0, 0)
        assert real.get_pixel(0, 0) == (255, 0, 0)

    def test_production_nyancat_has_rainbow_trail(self):
        """Sanity check that the production registry entries have the
        right trail kinds wired up."""
        from led_ticker.transitions._hires_registry import HIRES_REGISTRY

        assert HIRES_REGISTRY["nyancat"].trail == "rainbow"
        assert HIRES_REGISTRY["nyancat_reverse"].trail == "rainbow"
        assert HIRES_REGISTRY["pokeball"].trail == "black"
        assert HIRES_REGISTRY["pokeball_reverse"].trail == "black"


@pytest.mark.parametrize(
    "name", ["nyancat", "nyancat_reverse", "pokeball", "pokeball_reverse"]
)
def test_production_sprite_loads_and_fits(name):
    """Smoke test: each registered production sprite decodes successfully,
    fits within the bigsign panel, and has at least one non-black pixel."""
    from led_ticker.transitions._hires_loader import load_hires

    frames = load_hires(name)
    assert frames is not None, f"{name} not in registry"
    assert frames.height <= 64, f"{name} height {frames.height} exceeds panel_h"
    assert frames.width <= 256, f"{name} width {frames.width} exceeds panel_w"
    assert len(frames.durations_ms) >= 1
    assert any(
        len(f) > 0 for f in frames.non_black
    ), f"{name} has no non-black pixels in any frame"
