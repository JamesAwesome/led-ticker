"""Tests for the Sailor Moon wand transition."""

from rgbmatrix import _StubCanvas

from led_ticker.transitions import (
    SailorMoon,
    SailorMoonAlternating,
    SailorMoonReverse,
    get_transition_class,
)
from led_ticker.transitions.sailor_moon import (
    MOON_STICK,
    WAND_WIDTH,
    draw_sailor_moon_frame,
    draw_sailor_moon_frame_rtl,
)


class TestMoonStickSprite:
    def test_sprite_has_pixels(self):
        assert len(MOON_STICK) > 0

    def test_sprite_pixels_in_bounds(self):
        for dx, dy, r, g, b in MOON_STICK:
            assert 0 <= dx < WAND_WIDTH
            assert 0 <= dy < 16
            assert 0 <= r <= 255
            assert 0 <= g <= 255
            assert 0 <= b <= 255


class TestDrawSailorMoonFrame:
    def test_at_zero_wand_offscreen(self):
        canvas = _StubCanvas(width=40, height=16)
        draw_sailor_moon_frame(canvas, 0.0, width=40, height=16)

    def test_at_midpoint_draws_pixels(self):
        canvas = _StubCanvas(width=40, height=16)
        draw_sailor_moon_frame(canvas, 0.5, width=40, height=16)
        assert canvas.count_nonzero() > 0

    def test_sparkle_zone_has_colored_pixels(self):
        """Sparkle region should contain non-black pixels."""
        canvas = _StubCanvas(width=160, height=16)
        draw_sailor_moon_frame(canvas, 0.5, width=160, height=16)
        found_colors = set()
        for (_x, _y), color in canvas._pixels.items():
            if color != (0, 0, 0):
                found_colors.add(color)
        # Should have sparkle colors (gold, pink, white, or magenta)
        assert len(found_colors) >= 2

    def test_blackout_zone_is_black(self):
        """Area well behind the sparkle trail should be blacked out."""
        canvas = _StubCanvas(width=160, height=16)
        draw_sailor_moon_frame(canvas, 0.7, width=160, height=16)
        # Far left should be black
        for y in range(16):
            pixel = canvas._pixels.get((0, y), (0, 0, 0))
            assert pixel == (0, 0, 0), f"Expected black at (0, {y}), got {pixel}"

    def test_no_out_of_bounds(self):
        canvas = _StubCanvas(width=40, height=16)
        for p in [0.0, 0.25, 0.5, 0.75, 1.0]:
            draw_sailor_moon_frame(canvas, p, width=40, height=16)
            for x, y in canvas._pixels:
                assert 0 <= x < 40
                assert 0 <= y < 16

    def test_progressive_coverage(self):
        """Later progress should have more coverage than early progress."""
        canvas_early = _StubCanvas(width=80, height=16)
        canvas_late = _StubCanvas(width=80, height=16)
        draw_sailor_moon_frame(canvas_early, 0.2, width=80, height=16)
        draw_sailor_moon_frame(canvas_late, 0.8, width=80, height=16)
        assert canvas_late.count_nonzero() > canvas_early.count_nonzero()

    def test_sparkle_twinkle(self):
        """Sparkle pattern should differ between adjacent progress values."""
        canvas_a = _StubCanvas(width=160, height=16)
        canvas_b = _StubCanvas(width=160, height=16)
        draw_sailor_moon_frame(canvas_a, 0.50, width=160, height=16)
        draw_sailor_moon_frame(canvas_b, 0.51, width=160, height=16)
        # Pixels should differ due to twinkle
        assert canvas_a._pixels != canvas_b._pixels


class TestDrawSailorMoonFrameRTL:
    def test_at_zero_wand_offscreen(self):
        canvas = _StubCanvas(width=40, height=16)
        draw_sailor_moon_frame_rtl(canvas, 0.0, width=40, height=16)

    def test_at_midpoint_draws_pixels(self):
        canvas = _StubCanvas(width=40, height=16)
        draw_sailor_moon_frame_rtl(canvas, 0.5, width=40, height=16)
        assert canvas.count_nonzero() > 0

    def test_sprite_is_flipped(self):
        """RTL sprite should be at different positions than LTR."""
        canvas_ltr = _StubCanvas(width=160, height=16)
        canvas_rtl = _StubCanvas(width=160, height=16)
        draw_sailor_moon_frame(canvas_ltr, 0.3, width=160, height=16)
        draw_sailor_moon_frame_rtl(canvas_rtl, 0.3, width=160, height=16)
        ltr_pixels = set(canvas_ltr._pixels.keys())
        rtl_pixels = set(canvas_rtl._pixels.keys())
        assert ltr_pixels != rtl_pixels

    def test_blackout_zone_is_black_rtl(self):
        """Right edge should be blacked out when wand is mid-screen."""
        canvas = _StubCanvas(width=160, height=16)
        draw_sailor_moon_frame_rtl(canvas, 0.7, width=160, height=16)
        for y in range(16):
            pixel = canvas._pixels.get((159, y), (0, 0, 0))
            assert pixel == (0, 0, 0), f"Expected black at (159, {y}), got {pixel}"

    def test_no_out_of_bounds(self):
        canvas = _StubCanvas(width=40, height=16)
        for p in [0.0, 0.25, 0.5, 0.75, 1.0]:
            draw_sailor_moon_frame_rtl(canvas, p, width=40, height=16)
            for x, y in canvas._pixels:
                assert 0 <= x < 40
                assert 0 <= y < 16


class TestSailorMoonTransition:
    def test_registered(self):
        cls = get_transition_class("sailor_moon")
        assert cls is SailorMoon

    def test_frame_at_draws_to_canvas(self, make_widget):
        pixel_canvas = _StubCanvas(width=40, height=16)
        outgoing = make_widget(40)
        incoming = make_widget(40)
        sm = SailorMoon()
        result = sm.frame_at(0.5, pixel_canvas, outgoing, incoming)
        assert result is pixel_canvas

    def test_midpoint_draws_outgoing(self, make_widget):
        pixel_canvas = _StubCanvas(width=40, height=16)
        outgoing = make_widget(40)
        incoming = make_widget(40)
        sm = SailorMoon()
        sm.frame_at(0.3, pixel_canvas, outgoing, incoming)
        assert outgoing.draw.called
        assert not incoming.draw.called

    def test_complete_shows_incoming_only(self, make_widget):
        pixel_canvas = _StubCanvas(width=40, height=16)
        outgoing = make_widget(40)
        incoming = make_widget(40)
        sm = SailorMoon()
        sm.frame_at(1.0, pixel_canvas, outgoing, incoming)
        assert not outgoing.draw.called
        assert incoming.draw.called


class TestSailorMoonReverseTransition:
    def test_registered(self):
        cls = get_transition_class("sailor_moon_reverse")
        assert cls is SailorMoonReverse

    def test_at_one_shows_incoming(self, make_widget):
        pixel_canvas = _StubCanvas(width=40, height=16)
        outgoing = make_widget(40)
        incoming = make_widget(40)
        sm = SailorMoonReverse()
        sm.frame_at(1.0, pixel_canvas, outgoing, incoming)
        assert not outgoing.draw.called
        assert incoming.draw.called

    def test_midpoint_draws_outgoing(self, make_widget):
        pixel_canvas = _StubCanvas(width=40, height=16)
        outgoing = make_widget(40)
        incoming = make_widget(40)
        sm = SailorMoonReverse()
        sm.frame_at(0.3, pixel_canvas, outgoing, incoming)
        assert outgoing.draw.called
        assert not incoming.draw.called


class TestSailorMoonAlternating:
    def test_registered(self):
        cls = get_transition_class("sailor_moon_alternating")
        assert cls is SailorMoonAlternating

    def test_alternates_direction(self, make_widget):
        pixel_canvas = _StubCanvas(width=160, height=16)
        outgoing = make_widget(40)
        incoming = make_widget(40)
        alt = SailorMoonAlternating()

        # First cycle: LTR
        alt.frame_at(0.0, pixel_canvas, outgoing, incoming)
        canvas_a = dict(pixel_canvas._pixels)

        # Complete first cycle
        alt.frame_at(1.0, pixel_canvas, outgoing, incoming)

        # Second cycle: RTL (t resets to 0)
        pixel_canvas = _StubCanvas(width=160, height=16)
        alt.frame_at(0.3, pixel_canvas, outgoing, incoming)
        canvas_b = dict(pixel_canvas._pixels)

        # Different directions should produce different pixel patterns
        assert canvas_a != canvas_b


# --- scale_switch_at ---


class TestScaleSwitchAt:
    """Tripwire: sailor moon variants must set scale_switch_at=0.0 so the
    canvas is re-wrapped to the incoming scale BEFORE the first frame.
    This keeps the wand sprite physically consistent throughout a cross-scale
    transition (e.g. scale=2 → scale=4) with no snap at t=0.5.
    """

    def test_sailor_moon_switches_at_zero(self):
        assert SailorMoon.scale_switch_at == 0.0

    def test_sailor_moon_reverse_switches_at_zero(self):
        assert SailorMoonReverse.scale_switch_at == 0.0

    def test_sailor_moon_alternating_switches_at_zero(self):
        assert SailorMoonAlternating.scale_switch_at == 0.0

    async def test_run_transition_uses_incoming_scale_from_first_frame(
        self, make_widget, monkeypatch
    ):
        """run_transition must use incoming_scale from frame 0 when the
        transition sets scale_switch_at=0.0.

        Scenario: outgoing section has scale=2, incoming section has scale=4.
        With scale_switch_at=0.0 the canvas is re-wrapped at scale=4 before
        the loop starts, so every frame_at call sees a scale=4 canvas.
        The wand sprite is then physically consistent throughout.
        """
        import asyncio
        import unittest.mock as mock

        from rgbmatrix import RGBMatrix, RGBMatrixOptions

        from led_ticker.scaled_canvas import ScaledCanvas
        from led_ticker.transitions import run_transition

        monkeypatch.setattr(asyncio, "sleep", mock.AsyncMock())

        opts = RGBMatrixOptions()
        opts.cols = 64
        opts.rows = 32
        opts.chain_length = 8
        opts.parallel = 1
        opts.pixel_mapper_config = "U-mapper"
        real_canvas = RGBMatrix(options=opts).CreateFrameCanvas()

        outgoing_canvas = ScaledCanvas(real_canvas, scale=2, content_height=32)

        frame = mock.Mock()
        frame.matrix.CreateFrameCanvas.return_value = real_canvas
        # SwapOnVSync receives the underlying real canvas and must return a
        # physical canvas (not a wrapper); _swap then rewires wrapper.real.
        frame.swap.return_value = real_canvas

        outgoing = make_widget(40)
        incoming = make_widget(40)
        sm = SailorMoon()

        canvas_scales_seen: list[int] = []
        original_frame_at = sm.frame_at

        def tracking_frame_at(t, canvas, out, inc, **kwargs):
            canvas_scales_seen.append(getattr(canvas, "scale", 1))
            return original_frame_at(t, canvas, out, inc, **kwargs)

        sm.frame_at = tracking_frame_at

        await run_transition(
            outgoing_canvas,
            frame,
            outgoing,
            incoming,
            transition=sm,
            duration=0.4,
            incoming_scale=4,
            incoming_content_height=16,
        )

        # Every frame_at call should have seen a canvas at scale=4 (incoming),
        # never scale=2, because scale_switch_at=0.0.
        assert all(
            s == 4 for s in canvas_scales_seen
        ), f"Expected all frames at scale=4, got: {canvas_scales_seen}"
