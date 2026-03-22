"""Tests for the Pokeball transition."""

from rgbmatrix import _StubCanvas

from led_ticker.transition import Pokeball, get_transition_class
from led_ticker.widgets.pokeball import (
    POKEBALL_FRAMES,
    SPRITE_SIZE,
    draw_pokeball_frame,
)


class TestPokeballSprite:
    def test_has_four_frames(self):
        assert len(POKEBALL_FRAMES) == 4

    def test_each_frame_has_pixels(self):
        for frame in POKEBALL_FRAMES:
            assert len(frame) > 0

    def test_sprite_pixels_in_bounds(self):
        for frame in POKEBALL_FRAMES:
            for dx, dy, r, g, b in frame:
                assert 0 <= dx < SPRITE_SIZE
                assert 0 <= dy < SPRITE_SIZE
                assert 0 <= r <= 255
                assert 0 <= g <= 255
                assert 0 <= b <= 255

    def test_frames_have_similar_pixel_count(self):
        """All rotation frames should have roughly the same number of pixels."""
        counts = [len(f) for f in POKEBALL_FRAMES]
        assert max(counts) - min(counts) <= 5


class TestDrawPokeballFrame:
    def test_at_zero_ball_offscreen_left(self):
        canvas = _StubCanvas(width=40, height=16)
        draw_pokeball_frame(canvas, 0.0, width=40, height=16)

    def test_at_midpoint_draws_pixels(self):
        canvas = _StubCanvas(width=40, height=16)
        draw_pokeball_frame(canvas, 0.5, width=40, height=16)
        assert canvas.count_nonzero() > 0

    def test_blackout_left_of_ball(self):
        canvas = _StubCanvas(width=40, height=16)
        # Pre-fill canvas to simulate outgoing text
        for y in range(16):
            for x in range(40):
                canvas.SetPixel(x, y, 100, 100, 100)
        draw_pokeball_frame(canvas, 0.5, width=40, height=16)
        # Pixels well to the left of the ball should be black
        assert canvas.get_pixel(0, 8) == (0, 0, 0)

    def test_no_out_of_bounds(self):
        canvas = _StubCanvas(width=40, height=16)
        for p in [0.0, 0.25, 0.5, 0.75, 1.0]:
            draw_pokeball_frame(canvas, p, width=40, height=16)
            for x, y in canvas._pixels:
                assert 0 <= x < 40
                assert 0 <= y < 16

    def test_progressive_blackout(self):
        """More left-side pixels blacked out as progress increases."""
        prev_black = 0
        for step in range(1, 11):
            p = step / 10.0
            canvas = _StubCanvas(width=80, height=16)
            for y in range(16):
                for x in range(80):
                    canvas.SetPixel(x, y, 100, 100, 100)
            draw_pokeball_frame(canvas, p, width=80, height=16)
            black = sum(1 for v in canvas._pixels.values() if v == (0, 0, 0))
            assert black >= prev_black
            prev_black = black


class TestPokeballTransition:
    def test_registered(self):
        cls = get_transition_class("pokeball")
        assert cls is Pokeball

    def test_frame_at_draws_to_canvas(self, make_widget):
        pixel_canvas = _StubCanvas(width=40, height=16)
        outgoing = make_widget(40)
        incoming = make_widget(40)
        poke = Pokeball()
        result = poke.frame_at(0.5, pixel_canvas, outgoing, incoming)
        assert result is pixel_canvas

    def test_midpoint_draws_outgoing(self, make_widget):
        pixel_canvas = _StubCanvas(width=40, height=16)
        outgoing = make_widget(40)
        incoming = make_widget(40)
        poke = Pokeball()
        poke.frame_at(0.3, pixel_canvas, outgoing, incoming)
        assert outgoing.draw.called

    def test_complete_shows_incoming_only(self, make_widget):
        pixel_canvas = _StubCanvas(width=40, height=16)
        outgoing = make_widget(40)
        incoming = make_widget(40)
        poke = Pokeball()
        poke.frame_at(1.0, pixel_canvas, outgoing, incoming)
        assert not outgoing.draw.called
        assert incoming.draw.called

    def test_returns_canvas(self, make_widget):
        pixel_canvas = _StubCanvas(width=40, height=16)
        poke = Pokeball()
        result = poke.frame_at(0.5, pixel_canvas, make_widget(40), make_widget(40))
        assert result is pixel_canvas
