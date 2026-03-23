"""Tests for the Pac-Man transition."""

from rgbmatrix import _StubCanvas

from led_ticker.transition import (
    Pacman,
    PacmanAlternating,
    PacmanReverse,
    get_transition_class,
)
from led_ticker.widgets.pacman import (
    GHOST_FRAMES,
    GHOST_HEIGHT,
    GHOST_WIDTH,
    NUM_GHOSTS,
    PACMAN_FRAMES,
    PACMAN_SIZE,
    draw_pacman_frame,
    draw_pacman_frame_rtl,
)


class TestPacmanSprite:
    def test_has_four_frames(self):
        # closed, half, open, half
        assert len(PACMAN_FRAMES) == 4

    def test_each_frame_has_pixels(self):
        for frame in PACMAN_FRAMES:
            assert len(frame) > 0

    def test_sprite_pixels_in_bounds(self):
        for frame in PACMAN_FRAMES:
            for dx, dy, r, g, b in frame:
                assert 0 <= dx < PACMAN_SIZE, f"dx={dx} out of bounds"
                assert 0 <= dy < PACMAN_SIZE, f"dy={dy} out of bounds"
                assert 0 <= r <= 255
                assert 0 <= g <= 255
                assert 0 <= b <= 255


class TestGhostSprite:
    def test_has_three_ghosts(self):
        assert len(GHOST_FRAMES) == NUM_GHOSTS

    def test_each_ghost_has_two_frames(self):
        for ghost in GHOST_FRAMES:
            assert len(ghost) == 2

    def test_ghost_pixels_in_bounds(self):
        for ghost in GHOST_FRAMES:
            for frame in ghost:
                for dx, dy, r, g, b in frame:
                    assert 0 <= dx < GHOST_WIDTH, f"dx={dx} out of bounds"
                    assert 0 <= dy < GHOST_HEIGHT, f"dy={dy} out of bounds"
                    assert 0 <= r <= 255
                    assert 0 <= g <= 255
                    assert 0 <= b <= 255

    def test_each_frame_has_pixels(self):
        for ghost in GHOST_FRAMES:
            for frame in ghost:
                assert len(frame) > 0


class TestDrawPacmanFrame:
    def test_at_zero_group_offscreen_left(self):
        canvas = _StubCanvas(width=40, height=16)
        draw_pacman_frame(canvas, 0.0, width=40, height=16)

    def test_at_midpoint_draws_pixels(self):
        canvas = _StubCanvas(width=160, height=16)
        draw_pacman_frame(canvas, 0.5, width=160, height=16)
        assert canvas.count_nonzero() > 0

    def test_blackout_left_of_pacman(self):
        canvas = _StubCanvas(width=160, height=16)
        for y in range(16):
            for x in range(160):
                canvas.SetPixel(x, y, 100, 100, 100)
        draw_pacman_frame(canvas, 0.5, width=160, height=16)
        assert canvas.get_pixel(0, 8) == (0, 0, 0)

    def test_no_out_of_bounds(self):
        canvas = _StubCanvas(width=40, height=16)
        for p in [0.0, 0.25, 0.5, 0.75, 1.0]:
            draw_pacman_frame(canvas, p, width=40, height=16)
            for x, y in canvas._pixels:
                assert 0 <= x < 40
                assert 0 <= y < 16

    def test_progressive_blackout(self):
        prev_black = 0
        for step in range(1, 11):
            p = step / 10.0
            canvas = _StubCanvas(width=160, height=16)
            for y in range(16):
                for x in range(160):
                    canvas.SetPixel(x, y, 100, 100, 100)
            draw_pacman_frame(canvas, p, width=160, height=16)
            black = sum(1 for v in canvas._pixels.values() if v == (0, 0, 0))
            assert black >= prev_black
            prev_black = black


class TestDrawPacmanFrameRTL:
    def test_at_zero_group_offscreen_right(self):
        canvas = _StubCanvas(width=40, height=16)
        draw_pacman_frame_rtl(canvas, 0.0, width=40, height=16)

    def test_at_midpoint_draws_pixels(self):
        canvas = _StubCanvas(width=160, height=16)
        draw_pacman_frame_rtl(canvas, 0.5, width=160, height=16)
        assert canvas.count_nonzero() > 0

    def test_blackout_right_of_pacman(self):
        canvas = _StubCanvas(width=160, height=16)
        for y in range(16):
            for x in range(160):
                canvas.SetPixel(x, y, 100, 100, 100)
        draw_pacman_frame_rtl(canvas, 0.5, width=160, height=16)
        assert canvas.get_pixel(159, 8) == (0, 0, 0)

    def test_no_out_of_bounds(self):
        canvas = _StubCanvas(width=40, height=16)
        for p in [0.0, 0.25, 0.5, 0.75, 1.0]:
            draw_pacman_frame_rtl(canvas, p, width=40, height=16)
            for x, y in canvas._pixels:
                assert 0 <= x < 40
                assert 0 <= y < 16

    def test_sprite_is_flipped(self):
        canvas_ltr = _StubCanvas(width=160, height=16)
        canvas_rtl = _StubCanvas(width=160, height=16)
        draw_pacman_frame(canvas_ltr, 0.3, width=160, height=16)
        draw_pacman_frame_rtl(canvas_rtl, 0.3, width=160, height=16)
        ltr_pixels = set(canvas_ltr._pixels.keys())
        rtl_pixels = set(canvas_rtl._pixels.keys())
        assert ltr_pixels != rtl_pixels


class TestPacmanTransition:
    def test_registered(self):
        cls = get_transition_class("pacman")
        assert cls is Pacman

    def test_frame_at_draws_to_canvas(self, make_widget):
        pixel_canvas = _StubCanvas(width=160, height=16)
        outgoing = make_widget(160)
        incoming = make_widget(160)
        pm = Pacman()
        result = pm.frame_at(0.5, pixel_canvas, outgoing, incoming)
        assert result is pixel_canvas

    def test_midpoint_draws_outgoing(self, make_widget):
        pixel_canvas = _StubCanvas(width=160, height=16)
        outgoing = make_widget(160)
        incoming = make_widget(160)
        pm = Pacman()
        pm.frame_at(0.3, pixel_canvas, outgoing, incoming)
        assert outgoing.draw.called

    def test_complete_shows_incoming_only(self, make_widget):
        pixel_canvas = _StubCanvas(width=160, height=16)
        outgoing = make_widget(160)
        incoming = make_widget(160)
        pm = Pacman()
        pm.frame_at(1.0, pixel_canvas, outgoing, incoming)
        assert not outgoing.draw.called
        assert incoming.draw.called

    def test_returns_canvas(self, make_widget):
        pixel_canvas = _StubCanvas(width=160, height=16)
        pm = Pacman()
        result = pm.frame_at(0.5, pixel_canvas, make_widget(160), make_widget(160))
        assert result is pixel_canvas


class TestPacmanReverseTransition:
    def test_registered(self):
        cls = get_transition_class("pacman_reverse")
        assert cls is PacmanReverse

    def test_complete_shows_incoming(self, make_widget):
        pixel_canvas = _StubCanvas(width=160, height=16)
        outgoing = make_widget(160)
        incoming = make_widget(160)
        pm = PacmanReverse()
        pm.frame_at(1.0, pixel_canvas, outgoing, incoming)
        assert not outgoing.draw.called
        assert incoming.draw.called

    def test_midpoint_draws_outgoing(self, make_widget):
        pixel_canvas = _StubCanvas(width=160, height=16)
        outgoing = make_widget(160)
        incoming = make_widget(160)
        pm = PacmanReverse()
        pm.frame_at(0.3, pixel_canvas, outgoing, incoming)
        assert outgoing.draw.called


class TestPacmanAlternatingTransition:
    def test_registered(self):
        cls = get_transition_class("pacman_alternating")
        assert cls is PacmanAlternating

    def test_alternates_direction(self, make_widget):
        pm = PacmanAlternating()
        canvas = _StubCanvas(width=160, height=16)
        pm.frame_at(0.0, canvas, make_widget(160), make_widget(160))
        assert pm._index == 0
        pm.frame_at(1.0, canvas, make_widget(160), make_widget(160))
        pm.frame_at(0.0, canvas, make_widget(160), make_widget(160))
        assert pm._index == 1
        pm.frame_at(1.0, canvas, make_widget(160), make_widget(160))
        pm.frame_at(0.0, canvas, make_widget(160), make_widget(160))
        assert pm._index == 0
