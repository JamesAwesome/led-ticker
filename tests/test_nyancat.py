"""Tests for the Nyan Cat transition."""

from rgbmatrix import _StubCanvas

from led_ticker.transitions import (
    NyanCat,
    NyanCatAlternating,
    NyanCatReverse,
    get_transition_class,
)
from led_ticker.transitions.nyancat import (
    NYAN_CAT,
    RAINBOW,
    RAINBOW_TOP_Y,
    SPRITE_WIDTH,
    draw_nyan_frame,
    draw_nyan_frame_rtl,
)


class TestNyanCatSprite:
    def test_sprite_has_pixels(self):
        assert len(NYAN_CAT) > 0

    def test_sprite_pixels_in_bounds(self):
        for dx, dy, r, g, b in NYAN_CAT:
            assert 0 <= dx < SPRITE_WIDTH
            assert 0 <= dy < 10
            assert 0 <= r <= 255
            assert 0 <= g <= 255
            assert 0 <= b <= 255

    def test_rainbow_has_six_colors(self):
        assert len(RAINBOW) == 6


class TestDrawNyanFrame:
    def test_at_zero_cat_offscreen_left(self):
        canvas = _StubCanvas(width=40, height=16)
        draw_nyan_frame(canvas, 0.0, width=40, height=16)
        # Cat is at x=-12, mostly offscreen. Some pixels
        # may be visible if sprite overlaps x=0.
        # Rainbow trail_end = -12, so no rainbow visible either.

    def test_at_midpoint_draws_pixels(self):
        canvas = _StubCanvas(width=40, height=16)
        draw_nyan_frame(canvas, 0.5, width=40, height=16)
        assert canvas.count_nonzero() > 0

    def test_at_one_cat_offscreen_right(self):
        canvas = _StubCanvas(width=40, height=16)
        draw_nyan_frame(canvas, 1.0, width=40, height=16)
        # Rainbow should fill most of the canvas
        assert canvas.count_nonzero() > 0

    def test_rainbow_colors_present_at_midpoint(self):
        canvas = _StubCanvas(width=160, height=16)
        draw_nyan_frame(canvas, 0.5, width=160, height=16)
        # Check that rainbow stripe colors appear
        found_colors = set()
        for (_x, _y), color in canvas._pixels.items():
            if color != (0, 0, 0):
                found_colors.add(color)
        # Should have at least some rainbow colors
        rainbow_set = {tuple(c) for c in RAINBOW}
        assert len(found_colors & rainbow_set) >= 3

    def test_no_out_of_bounds(self):
        canvas = _StubCanvas(width=40, height=16)
        for p in [0.0, 0.25, 0.5, 0.75, 1.0]:
            draw_nyan_frame(canvas, p, width=40, height=16)
            for x, y in canvas._pixels:
                assert 0 <= x < 40
                assert 0 <= y < 16

    def test_progressive_coverage(self):
        """More pixels drawn as progress increases."""
        prev_count = 0
        for step in range(1, 11):
            p = step / 10.0
            canvas = _StubCanvas(width=80, height=16)
            draw_nyan_frame(canvas, p, width=80, height=16)
            count = canvas.count_nonzero()
            assert count >= prev_count
            prev_count = count


class TestNyanCatTransition:
    def test_registered(self):
        cls = get_transition_class("nyancat")
        assert cls is NyanCat

    def test_frame_at_draws_to_canvas(self, make_widget):
        pixel_canvas = _StubCanvas(width=40, height=16)
        outgoing = make_widget(40)
        incoming = make_widget(40)
        nyan = NyanCat()
        result = nyan.frame_at(0.5, pixel_canvas, outgoing, incoming)
        assert result is pixel_canvas

    def test_midpoint_draws_outgoing(self, make_widget):
        pixel_canvas = _StubCanvas(width=40, height=16)
        outgoing = make_widget(40)
        incoming = make_widget(40)
        nyan = NyanCat()
        nyan.frame_at(0.3, pixel_canvas, outgoing, incoming)
        # Cat is still on-screen, so outgoing is drawn as base
        assert outgoing.draw.called

    def test_complete_shows_incoming_only(self, make_widget):
        """At t=1.0, only incoming should be drawn."""
        pixel_canvas = _StubCanvas(width=40, height=16)
        outgoing = make_widget(40)
        incoming = make_widget(40)
        nyan = NyanCat()
        nyan.frame_at(1.0, pixel_canvas, outgoing, incoming)
        assert not outgoing.draw.called
        assert incoming.draw.called

    def test_no_early_cut_after_cat_exits(self, make_widget):
        """Outgoing should still be drawn after cat exits right edge."""
        pixel_canvas = _StubCanvas(width=40, height=16)
        outgoing = make_widget(40)
        incoming = make_widget(40)
        nyan = NyanCat()
        # At t=0.7, cat has exited right but rainbow still filling
        nyan.frame_at(0.7, pixel_canvas, outgoing, incoming)
        assert outgoing.draw.called
        assert not incoming.draw.called


class TestNyanCatRainbowCoverage:
    def test_rainbow_covers_left_edge_near_end(self):
        """At t=0.99, rainbow should cover x=0."""
        canvas = _StubCanvas(width=160, height=16)
        draw_nyan_frame(canvas, 0.99, width=160, height=16)
        # Check a rainbow row at x=0
        y = RAINBOW_TOP_Y
        pixel = canvas._pixels.get((0, y))
        assert pixel is not None and pixel != (0, 0, 0)

    def test_rainbow_covers_full_width_at_end(self):
        """At t=1.0, rainbow should cover x=0 to x=width-1."""
        canvas = _StubCanvas(width=80, height=16)
        draw_nyan_frame(canvas, 1.0, width=80, height=16)
        y = RAINBOW_TOP_Y
        for x in [0, 20, 40, 60, 79]:
            pixel = canvas._pixels.get((x, y))
            assert pixel is not None and pixel != (0, 0, 0), f"Rainbow missing at x={x}"


class TestDrawNyanFrameRTL:
    def test_at_zero_cat_offscreen_right(self):
        canvas = _StubCanvas(width=40, height=16)
        draw_nyan_frame_rtl(canvas, 0.0, width=40, height=16)
        # Cat is at x=40, offscreen right. No rainbow visible.

    def test_at_midpoint_draws_pixels(self):
        canvas = _StubCanvas(width=40, height=16)
        draw_nyan_frame_rtl(canvas, 0.5, width=40, height=16)
        assert canvas.count_nonzero() > 0

    def test_rainbow_covers_right_edge_near_end(self):
        """RTL rainbow should cover x=width-1 near end."""
        canvas = _StubCanvas(width=80, height=16)
        draw_nyan_frame_rtl(canvas, 0.99, width=80, height=16)
        y = RAINBOW_TOP_Y
        pixel = canvas._pixels.get((79, y))
        assert pixel is not None and pixel != (0, 0, 0)

    def test_sprite_is_flipped(self):
        """RTL sprite should be horizontally mirrored."""
        canvas_ltr = _StubCanvas(width=160, height=16)
        canvas_rtl = _StubCanvas(width=160, height=16)
        draw_nyan_frame(canvas_ltr, 0.3, width=160, height=16)
        draw_nyan_frame_rtl(canvas_rtl, 0.3, width=160, height=16)
        # Sprites at different x positions — pixel sets differ
        ltr_pixels = set(canvas_ltr._pixels.keys())
        rtl_pixels = set(canvas_rtl._pixels.keys())
        assert ltr_pixels != rtl_pixels

    def test_no_out_of_bounds(self):
        canvas = _StubCanvas(width=40, height=16)
        for p in [0.0, 0.25, 0.5, 0.75, 1.0]:
            draw_nyan_frame_rtl(canvas, p, width=40, height=16)
            for x, y in canvas._pixels:
                assert 0 <= x < 40
                assert 0 <= y < 16


class TestNyanCatReverseTransition:
    def test_registered(self):
        cls = get_transition_class("nyancat_reverse")
        assert cls is NyanCatReverse

    def test_at_one_shows_incoming(self, make_widget):
        pixel_canvas = _StubCanvas(width=40, height=16)
        outgoing = make_widget(40)
        incoming = make_widget(40)
        nyan = NyanCatReverse()
        nyan.frame_at(1.0, pixel_canvas, outgoing, incoming)
        assert not outgoing.draw.called
        assert incoming.draw.called

    def test_midpoint_draws_outgoing(self, make_widget):
        pixel_canvas = _StubCanvas(width=40, height=16)
        outgoing = make_widget(40)
        incoming = make_widget(40)
        nyan = NyanCatReverse()
        nyan.frame_at(0.3, pixel_canvas, outgoing, incoming)
        assert outgoing.draw.called
        assert not incoming.draw.called


class TestNyanCatDispatch:
    def test_mock_canvas_takes_lowres_path(self):
        """Mock isn't a ScaledCanvas → lowres path. Existing behavior preserved."""
        import unittest.mock as mock_mod

        from led_ticker.transitions.nyancat import NyanCat

        canvas = mock_mod.MagicMock()
        canvas.width = 160
        canvas.height = 16
        outgoing = mock_mod.MagicMock()
        incoming = mock_mod.MagicMock()

        nc = NyanCat()
        # Spy on both branches.
        with (
            mock_mod.patch.object(
                nc, "_frame_at_lowres", wraps=nc._frame_at_lowres
            ) as lowres,
            mock_mod.patch.object(
                nc, "_frame_at_hires", wraps=nc._frame_at_hires
            ) as hires,
        ):
            nc.frame_at(0.5, canvas, outgoing, incoming)
            lowres.assert_called_once()
            hires.assert_not_called()

    def test_scaled_canvas_with_registered_name_takes_hires_path(self):
        import unittest.mock as mock_mod

        from rgbmatrix import RGBMatrix, RGBMatrixOptions

        from led_ticker.scaled_canvas import ScaledCanvas
        from led_ticker.transitions.nyancat import NyanCat

        opts = RGBMatrixOptions()
        opts.cols = 256
        opts.rows = 64
        opts.chain_length = 1
        opts.parallel = 1
        real = RGBMatrix(options=opts).CreateFrameCanvas()
        wrapped = ScaledCanvas(real, scale=4, content_height=16)

        outgoing = mock_mod.MagicMock()
        incoming = mock_mod.MagicMock()
        nc = NyanCat()

        with (
            mock_mod.patch.object(
                nc, "_frame_at_lowres", wraps=nc._frame_at_lowres
            ) as lowres,
            mock_mod.patch.object(
                nc, "_frame_at_hires", wraps=nc._frame_at_hires
            ) as hires,
        ):
            nc.frame_at(0.5, wrapped, outgoing, incoming, duration_ms=500)
            hires.assert_called_once()
            lowres.assert_not_called()

    def test_nyancat_registry_name(self):
        from led_ticker.transitions.nyancat import NyanCat

        assert NyanCat._registry_name == "nyancat"

    def test_nyancat_reverse_registry_name(self):
        from led_ticker.transitions.nyancat import NyanCatReverse

        assert NyanCatReverse._registry_name == "nyancat_reverse"

    def test_t_above_one_snaps_to_incoming_in_either_path(self):
        """The early-return at t>=1.0 runs before dispatch, so both paths
        end on incoming.draw at t=1.0."""
        import unittest.mock as mock_mod

        from led_ticker.transitions.nyancat import NyanCat

        canvas = mock_mod.MagicMock()
        outgoing = mock_mod.MagicMock()
        incoming = mock_mod.MagicMock()
        NyanCat().frame_at(1.0, canvas, outgoing, incoming)
        incoming.draw.assert_called_once()


class TestNyanCatAlternatingDelegatesToHires:
    def test_alternating_picks_hires_when_scaled_canvas(self):
        """nyancat_alternating dispatches each call to base/reverse,
        which then independently pick hires on a ScaledCanvas."""
        import unittest.mock as mock_mod

        from rgbmatrix import RGBMatrix, RGBMatrixOptions

        from led_ticker.scaled_canvas import ScaledCanvas
        from led_ticker.transitions.nyancat import NyanCatAlternating

        opts = RGBMatrixOptions()
        opts.cols = 256
        opts.rows = 64
        opts.chain_length = 1
        opts.parallel = 1
        real = RGBMatrix(options=opts).CreateFrameCanvas()
        wrapped = ScaledCanvas(real, scale=4, content_height=16)
        outgoing = mock_mod.MagicMock()
        incoming = mock_mod.MagicMock()

        alt = NyanCatAlternating()
        # First swap: forward variant.
        with mock_mod.patch.object(
            alt._transitions[0],
            "_frame_at_hires",
            wraps=alt._transitions[0]._frame_at_hires,
        ) as fwd_hires:
            alt.frame_at(0.5, wrapped, outgoing, incoming, duration_ms=500)
            fwd_hires.assert_called_once()


# --- scale_switch_at ---


class TestScaleSwitchAt:
    """Tripwire: nyancat variants must set scale_switch_at=SNAP_THRESHOLD so
    the outgoing widget is drawn at its native scale during the trail phase.
    See pokeball.py TestScaleSwitchAt for the full rationale.
    """

    def test_nyancat_switches_at_snap_threshold(self):
        from led_ticker.transitions._hires_loader import SNAP_THRESHOLD

        assert NyanCat.scale_switch_at == SNAP_THRESHOLD

    def test_nyancat_reverse_switches_at_snap_threshold(self):
        from led_ticker.transitions._hires_loader import SNAP_THRESHOLD

        assert NyanCatReverse.scale_switch_at == SNAP_THRESHOLD

    def test_nyancat_alternating_switches_at_snap_threshold(self):
        from led_ticker.transitions._hires_loader import SNAP_THRESHOLD

        assert NyanCatAlternating.scale_switch_at == SNAP_THRESHOLD
