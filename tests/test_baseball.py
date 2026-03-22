"""Tests for the Baseball transition."""

from rgbmatrix import _StubCanvas

from led_ticker.transition import (
    Baseball,
    BaseballAlternating,
    BaseballReverse,
    get_transition_class,
)
from led_ticker.widgets.baseball import (
    BASEBALL_FRAMES,
    SPRITE_SIZE,
    draw_baseball_frame,
    draw_baseball_frame_rtl,
)


class TestBaseballSprite:
    def test_has_four_frames(self):
        assert len(BASEBALL_FRAMES) == 4

    def test_each_frame_has_pixels(self):
        for frame in BASEBALL_FRAMES:
            assert len(frame) > 0

    def test_sprite_pixels_in_bounds(self):
        for frame in BASEBALL_FRAMES:
            for dx, dy, r, g, b in frame:
                assert 0 <= dx < SPRITE_SIZE
                assert 0 <= dy < SPRITE_SIZE
                assert 0 <= r <= 255
                assert 0 <= g <= 255
                assert 0 <= b <= 255

    def test_frames_have_similar_pixel_count(self):
        """All rotation frames should have the same number of pixels (same circle)."""
        counts = [len(f) for f in BASEBALL_FRAMES]
        assert max(counts) - min(counts) == 0


class TestDrawBaseballFrame:
    def test_at_zero_ball_offscreen_left(self):
        canvas = _StubCanvas(width=40, height=16)
        draw_baseball_frame(canvas, 0.0, width=40, height=16)

    def test_at_midpoint_draws_pixels(self):
        canvas = _StubCanvas(width=40, height=16)
        draw_baseball_frame(canvas, 0.5, width=40, height=16)
        assert canvas.count_nonzero() > 0

    def test_blackout_left_of_ball(self):
        canvas = _StubCanvas(width=160, height=16)
        for y in range(16):
            for x in range(160):
                canvas.SetPixel(x, y, 100, 100, 100)
        draw_baseball_frame(canvas, 0.5, width=160, height=16)
        assert canvas.get_pixel(0, 8) == (0, 0, 0)

    def test_no_out_of_bounds(self):
        canvas = _StubCanvas(width=40, height=16)
        for p in [0.0, 0.25, 0.5, 0.75, 1.0]:
            draw_baseball_frame(canvas, p, width=40, height=16)
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
            draw_baseball_frame(canvas, p, width=80, height=16)
            black = sum(1 for v in canvas._pixels.values() if v == (0, 0, 0))
            assert black >= prev_black
            prev_black = black


class TestDrawBaseballFrameRTL:
    def test_at_zero_ball_offscreen_right(self):
        canvas = _StubCanvas(width=40, height=16)
        draw_baseball_frame_rtl(canvas, 0.0, width=40, height=16)

    def test_at_midpoint_draws_pixels(self):
        canvas = _StubCanvas(width=40, height=16)
        draw_baseball_frame_rtl(canvas, 0.5, width=40, height=16)
        assert canvas.count_nonzero() > 0

    def test_blackout_right_of_ball(self):
        canvas = _StubCanvas(width=160, height=16)
        for y in range(16):
            for x in range(160):
                canvas.SetPixel(x, y, 100, 100, 100)
        draw_baseball_frame_rtl(canvas, 0.5, width=160, height=16)
        assert canvas.get_pixel(159, 8) == (0, 0, 0)

    def test_no_out_of_bounds(self):
        canvas = _StubCanvas(width=40, height=16)
        for p in [0.0, 0.25, 0.5, 0.75, 1.0]:
            draw_baseball_frame_rtl(canvas, p, width=40, height=16)
            for x, y in canvas._pixels:
                assert 0 <= x < 40
                assert 0 <= y < 16

    def test_sprite_is_flipped(self):
        canvas_ltr = _StubCanvas(width=160, height=16)
        canvas_rtl = _StubCanvas(width=160, height=16)
        draw_baseball_frame(canvas_ltr, 0.3, width=160, height=16)
        draw_baseball_frame_rtl(canvas_rtl, 0.3, width=160, height=16)
        ltr_pixels = set(canvas_ltr._pixels.keys())
        rtl_pixels = set(canvas_rtl._pixels.keys())
        assert ltr_pixels != rtl_pixels


class TestBaseballTransition:
    def test_registered(self):
        cls = get_transition_class("baseball")
        assert cls is Baseball

    def test_frame_at_draws_to_canvas(self, make_widget):
        pixel_canvas = _StubCanvas(width=40, height=16)
        outgoing = make_widget(40)
        incoming = make_widget(40)
        bb = Baseball()
        result = bb.frame_at(0.5, pixel_canvas, outgoing, incoming)
        assert result is pixel_canvas

    def test_midpoint_draws_outgoing(self, make_widget):
        pixel_canvas = _StubCanvas(width=40, height=16)
        outgoing = make_widget(40)
        incoming = make_widget(40)
        bb = Baseball()
        bb.frame_at(0.3, pixel_canvas, outgoing, incoming)
        assert outgoing.draw.called

    def test_complete_shows_incoming_only(self, make_widget):
        pixel_canvas = _StubCanvas(width=40, height=16)
        outgoing = make_widget(40)
        incoming = make_widget(40)
        bb = Baseball()
        bb.frame_at(1.0, pixel_canvas, outgoing, incoming)
        assert not outgoing.draw.called
        assert incoming.draw.called

    def test_returns_canvas(self, make_widget):
        pixel_canvas = _StubCanvas(width=40, height=16)
        bb = Baseball()
        result = bb.frame_at(0.5, pixel_canvas, make_widget(40), make_widget(40))
        assert result is pixel_canvas


class TestBaseballReverseTransition:
    def test_registered(self):
        cls = get_transition_class("baseball_reverse")
        assert cls is BaseballReverse

    def test_complete_shows_incoming(self, make_widget):
        pixel_canvas = _StubCanvas(width=40, height=16)
        outgoing = make_widget(40)
        incoming = make_widget(40)
        bb = BaseballReverse()
        bb.frame_at(1.0, pixel_canvas, outgoing, incoming)
        assert not outgoing.draw.called
        assert incoming.draw.called

    def test_midpoint_draws_outgoing(self, make_widget):
        pixel_canvas = _StubCanvas(width=40, height=16)
        outgoing = make_widget(40)
        incoming = make_widget(40)
        bb = BaseballReverse()
        bb.frame_at(0.3, pixel_canvas, outgoing, incoming)
        assert outgoing.draw.called


class TestBaseballAlternatingTransition:
    def test_registered(self):
        cls = get_transition_class("baseball_alternating")
        assert cls is BaseballAlternating

    def test_alternates_direction(self, make_widget):
        bb = BaseballAlternating()
        canvas = _StubCanvas(width=40, height=16)
        bb.frame_at(0.0, canvas, make_widget(40), make_widget(40))
        assert bb._index == 0
        bb.frame_at(1.0, canvas, make_widget(40), make_widget(40))
        bb.frame_at(0.0, canvas, make_widget(40), make_widget(40))
        assert bb._index == 1
        bb.frame_at(1.0, canvas, make_widget(40), make_widget(40))
        bb.frame_at(0.0, canvas, make_widget(40), make_widget(40))
        assert bb._index == 0
