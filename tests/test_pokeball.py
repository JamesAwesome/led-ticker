"""Tests for the Pokeball transition."""

from rgbmatrix import _StubCanvas

from led_ticker.transitions import (
    Pokeball,
    PokeballAlternating,
    PokeballReverse,
    get_transition_class,
)
from led_ticker.transitions.pokeball import (
    PIKACHU_FRAMES,
    PIKACHU_HEIGHT,
    PIKACHU_WIDTH,
    POKEBALL_FRAMES,
    SPRITE_SIZE,
    draw_pokeball_frame,
    draw_pokeball_frame_rtl,
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


class TestPikachuSprite:
    def test_has_four_frames(self):
        assert len(PIKACHU_FRAMES) == 4

    def test_each_frame_has_pixels(self):
        for frame in PIKACHU_FRAMES:
            assert len(frame) > 0

    def test_sprite_pixels_in_bounds(self):
        for frame in PIKACHU_FRAMES:
            for dx, dy, r, g, b in frame:
                assert 0 <= dx < PIKACHU_WIDTH, f"dx={dx} out of bounds"
                assert 0 <= dy < PIKACHU_HEIGHT, f"dy={dy} out of bounds"
                assert 0 <= r <= 255
                assert 0 <= g <= 255
                assert 0 <= b <= 255

    def test_frames_have_reasonable_pixel_count(self):
        """Frames have different body sizes but should all be substantial."""
        for frame in PIKACHU_FRAMES:
            assert len(frame) > 50


class TestDrawPokeballFrame:
    def test_at_zero_ball_offscreen_left(self):
        canvas = _StubCanvas(width=40, height=16)
        draw_pokeball_frame(canvas, 0.0, width=40, height=16)

    def test_at_midpoint_draws_pixels(self):
        canvas = _StubCanvas(width=40, height=16)
        draw_pokeball_frame(canvas, 0.5, width=40, height=16)
        assert canvas.count_nonzero() > 0

    def test_blackout_left_of_ball(self):
        canvas = _StubCanvas(width=160, height=16)
        # Pre-fill canvas to simulate outgoing text
        for y in range(16):
            for x in range(160):
                canvas.SetPixel(x, y, 100, 100, 100)
        draw_pokeball_frame(canvas, 0.5, width=160, height=16)
        # Pixels well to the left of both pokeball and pikachu should be black
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


class TestDrawPokeballFrameRTL:
    def test_at_zero_ball_offscreen_right(self):
        canvas = _StubCanvas(width=40, height=16)
        draw_pokeball_frame_rtl(canvas, 0.0, width=40, height=16)

    def test_at_midpoint_draws_pixels(self):
        canvas = _StubCanvas(width=40, height=16)
        draw_pokeball_frame_rtl(canvas, 0.5, width=40, height=16)
        assert canvas.count_nonzero() > 0

    def test_blackout_right_of_ball(self):
        canvas = _StubCanvas(width=160, height=16)
        for y in range(16):
            for x in range(160):
                canvas.SetPixel(x, y, 100, 100, 100)
        draw_pokeball_frame_rtl(canvas, 0.5, width=160, height=16)
        assert canvas.get_pixel(159, 8) == (0, 0, 0)

    def test_no_out_of_bounds(self):
        canvas = _StubCanvas(width=40, height=16)
        for p in [0.0, 0.25, 0.5, 0.75, 1.0]:
            draw_pokeball_frame_rtl(canvas, p, width=40, height=16)
            for x, y in canvas._pixels:
                assert 0 <= x < 40
                assert 0 <= y < 16

    def test_sprite_is_flipped(self):
        canvas_ltr = _StubCanvas(width=160, height=16)
        canvas_rtl = _StubCanvas(width=160, height=16)
        draw_pokeball_frame(canvas_ltr, 0.3, width=160, height=16)
        draw_pokeball_frame_rtl(canvas_rtl, 0.3, width=160, height=16)
        ltr_pixels = set(canvas_ltr._pixels.keys())
        rtl_pixels = set(canvas_rtl._pixels.keys())
        assert ltr_pixels != rtl_pixels


class TestPokeballReverseTransition:
    def test_registered(self):
        cls = get_transition_class("pokeball_reverse")
        assert cls is PokeballReverse

    def test_complete_shows_incoming(self, make_widget):
        pixel_canvas = _StubCanvas(width=40, height=16)
        outgoing = make_widget(40)
        incoming = make_widget(40)
        poke = PokeballReverse()
        poke.frame_at(1.0, pixel_canvas, outgoing, incoming)
        assert not outgoing.draw.called
        assert incoming.draw.called

    def test_midpoint_draws_outgoing(self, make_widget):
        pixel_canvas = _StubCanvas(width=40, height=16)
        outgoing = make_widget(40)
        incoming = make_widget(40)
        poke = PokeballReverse()
        poke.frame_at(0.3, pixel_canvas, outgoing, incoming)
        assert outgoing.draw.called


class TestPokeballAlternatingTransition:
    def test_registered(self):
        cls = get_transition_class("pokeball_alternating")
        assert cls is PokeballAlternating

    def test_alternates_direction(self, make_widget):
        poke = PokeballAlternating()
        canvas = _StubCanvas(width=40, height=16)
        # First cycle — t drops below last_t (1.0), advances to index 0
        poke.frame_at(0.0, canvas, make_widget(40), make_widget(40))
        assert poke._index == 0
        poke.frame_at(1.0, canvas, make_widget(40), make_widget(40))
        # Second cycle — t drops again, advances to index 1
        poke.frame_at(0.0, canvas, make_widget(40), make_widget(40))
        assert poke._index == 1
        poke.frame_at(1.0, canvas, make_widget(40), make_widget(40))
        # Third cycle — wraps back to 0
        poke.frame_at(0.0, canvas, make_widget(40), make_widget(40))
        assert poke._index == 0


class TestPokeballDispatch:
    def test_mock_canvas_takes_lowres_path(self):
        import unittest.mock as mock_mod

        from led_ticker.transitions.pokeball import Pokeball

        canvas = mock_mod.MagicMock()
        canvas.width = 160
        canvas.height = 16
        outgoing = mock_mod.MagicMock()
        incoming = mock_mod.MagicMock()
        pb = Pokeball()
        with (
            mock_mod.patch.object(
                pb, "_frame_at_lowres", wraps=pb._frame_at_lowres
            ) as lowres,
            mock_mod.patch.object(
                pb, "_frame_at_hires", wraps=pb._frame_at_hires
            ) as hires,
        ):
            pb.frame_at(0.5, canvas, outgoing, incoming)
            lowres.assert_called_once()
            hires.assert_not_called()

    def test_scaled_canvas_takes_hires_path(self):
        import unittest.mock as mock_mod

        from rgbmatrix import RGBMatrix, RGBMatrixOptions

        from led_ticker.scaled_canvas import ScaledCanvas
        from led_ticker.transitions.pokeball import Pokeball

        opts = RGBMatrixOptions()
        opts.cols = 256
        opts.rows = 64
        opts.chain_length = 1
        opts.parallel = 1
        real = RGBMatrix(options=opts).CreateFrameCanvas()
        wrapped = ScaledCanvas(real, scale=4, content_height=16)
        outgoing = mock_mod.MagicMock()
        incoming = mock_mod.MagicMock()
        pb = Pokeball()
        with (
            mock_mod.patch.object(
                pb, "_frame_at_lowres", wraps=pb._frame_at_lowres
            ) as lowres,
            mock_mod.patch.object(
                pb, "_frame_at_hires", wraps=pb._frame_at_hires
            ) as hires,
        ):
            pb.frame_at(0.5, wrapped, outgoing, incoming, duration_ms=500)
            hires.assert_called_once()
            lowres.assert_not_called()

    def test_pokeball_registry_name(self):
        from led_ticker.transitions.pokeball import Pokeball

        assert Pokeball._registry_name == "pokeball"

    def test_pokeball_reverse_registry_name(self):
        from led_ticker.transitions.pokeball import PokeballReverse

        assert PokeballReverse._registry_name == "pokeball_reverse"

    def test_show_pikachu_kwarg_preserved(self):
        """The existing show_pikachu constructor kwarg still works."""
        from led_ticker.transitions.pokeball import Pokeball

        p1 = Pokeball(show_pikachu=False)
        assert p1._show_pikachu is False
        p2 = Pokeball(show_pikachu=True)
        assert p2._show_pikachu is True

    def test_min_frames_preserved(self):
        from led_ticker.transitions.pokeball import Pokeball

        assert Pokeball.min_frames == 40
