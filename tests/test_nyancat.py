"""Tests for the Nyan Cat transition."""

from rgbmatrix import _StubCanvas

from led_ticker.transition import NyanCat, get_transition_class
from led_ticker.widgets.nyancat import (
    NYAN_CAT,
    RAINBOW,
    SPRITE_WIDTH,
    draw_nyan_frame,
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

    def test_draws_both_widgets(self, make_widget):
        pixel_canvas = _StubCanvas(width=40, height=16)
        outgoing = make_widget(40)
        incoming = make_widget(40)
        nyan = NyanCat()
        nyan.frame_at(0.3, pixel_canvas, outgoing, incoming)
        assert outgoing.draw.called
        assert incoming.draw.called

    def test_complete_shows_incoming_only(self, make_widget):
        """At t=1.0, only incoming should be drawn."""
        pixel_canvas = _StubCanvas(width=40, height=16)
        outgoing = make_widget(40)
        incoming = make_widget(40)
        nyan = NyanCat()
        nyan.frame_at(1.0, pixel_canvas, outgoing, incoming)
        assert not outgoing.draw.called
        assert incoming.draw.called
