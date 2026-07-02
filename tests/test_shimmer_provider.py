"""Tests for the Shimmer color provider."""

import math

import pytest
from rgbmatrix.graphics import Color

from led_ticker.color_providers import Shimmer


class TestShimmerConstruction:
    def test_defaults(self):
        p = Shimmer(base_color=Color(60, 60, 80), shimmer_color=Color(255, 255, 255))
        assert p.speed == 14.0
        assert p.width == 8.0
        assert p.pause == 0.5

    def test_explicit_params(self):
        p = Shimmer(
            base_color=Color(10, 10, 20),
            shimmer_color=Color(200, 200, 255),
            speed=10.0,
            width=5.0,
            pause=1.0,
        )
        assert p.speed == 10.0
        assert p.width == 5.0
        assert p.pause == 1.0

    def test_speed_zero_raises(self):
        with pytest.raises(ValueError, match="speed"):
            Shimmer(
                base_color=Color(0, 0, 0), shimmer_color=Color(255, 255, 255), speed=0
            )

    def test_speed_negative_raises(self):
        with pytest.raises(ValueError, match="speed"):
            Shimmer(
                base_color=Color(0, 0, 0), shimmer_color=Color(255, 255, 255), speed=-1
            )

    def test_width_zero_raises(self):
        with pytest.raises(ValueError, match="width"):
            Shimmer(
                base_color=Color(0, 0, 0), shimmer_color=Color(255, 255, 255), width=0
            )

    def test_pause_negative_raises(self):
        with pytest.raises(ValueError, match="pause"):
            Shimmer(
                base_color=Color(0, 0, 0),
                shimmer_color=Color(255, 255, 255),
                pause=-0.1,
            )

    def test_pause_zero_is_valid(self):
        p = Shimmer(
            base_color=Color(0, 0, 0), shimmer_color=Color(255, 255, 255), pause=0
        )
        assert p.pause == 0


class TestShimmerClassAttributes:
    def test_per_char_is_true(self):
        assert Shimmer.per_char is True

    def test_frame_invariant_is_false(self):
        assert Shimmer.frame_invariant is False

    def test_restart_on_visit_is_false(self):
        assert Shimmer.restart_on_visit is False


class TestShimmerColorFor:
    """color_for behavior: center of spot, edge, outside, pause period."""

    def _make(self, **kwargs):
        return Shimmer(
            base_color=Color(0, 0, 0),
            shimmer_color=Color(255, 255, 255),
            **kwargs,
        )

    def test_center_of_spot_is_brighter_than_base(self):
        """char at spot center should be significantly brighter than base."""
        # With speed=10, width=4, pause=0, total_chars=10:
        # travel = 10 + 4 = 14; sweep_frames = 14/10 * 20 = 28 frames
        # center(t) = -2 + (t/28)*14; center == 0 when t = 28*2/14 = 4
        p = self._make(speed=10.0, width=4.0, pause=0)
        # frame=4: center=0.0, char_index=0 → d=0 → factor=1.0 → full shimmer
        c = p.color_for(frame=4, char_index=0, total_chars=10)
        assert c.red > 200, f"center char should be near shimmer color, got r={c.red}"
        assert c.green > 200
        assert c.blue > 200

    def test_outside_spot_returns_base(self):
        """char outside the spot width returns base color exactly."""
        p = self._make(speed=10.0, width=2.0, pause=0)
        # travel=12, sweep_frames=24, frame=0 → center=-1.0, half_width=1.0
        # char_index=5 → d=6.0, 6.0 >= 1.0 → returns base
        c = p.color_for(frame=0, char_index=5, total_chars=10)
        assert (c.red, c.green, c.blue) == (0, 0, 0)

    def test_during_pause_returns_base(self):
        """During the pause period every char returns base color."""
        # speed=10, width=4, pause=1.0, total_chars=10
        # travel=14, sweep_frames = 14/10 * 20 = 28; pause_frames = 20; cycle = 48
        # frame=40 → t=40, 40 >= 28 → in pause
        p = self._make(speed=10.0, width=4.0, pause=1.0)
        for char_index in range(10):
            c = p.color_for(frame=40, char_index=char_index, total_chars=10)
            rgb = (c.red, c.green, c.blue)
            assert rgb == (
                0,
                0,
                0,
            ), f"char {char_index}: expected base during pause, got {rgb}"

    def test_edge_of_spot_is_darker_than_center(self):
        """char at edge of spot (d = half_width - epsilon) is dimmer than center."""
        p = self._make(speed=10.0, width=4.0, pause=0)
        # travel=14, sweep_frames=28; center==0 when frame=4 (see test_center above)
        # frame=4, center=0, half_width=2
        c_center = p.color_for(frame=4, char_index=0, total_chars=10)
        # char_index=1 → d=1, still inside (1 < 2); factor = 0.5 + 0.5*cos(π/2) = 0.5
        c_edge = p.color_for(frame=4, char_index=1, total_chars=10)
        assert c_center.red > c_edge.red, "center should be brighter than edge"

    def test_different_chars_get_different_colors_during_sweep(self):
        """Two chars at different distances from the spot center differ."""
        p = self._make(speed=10.0, width=8.0, pause=0)
        # travel=18, sweep_frames=36
        # frame=8: center=-4+(8/36)*18=-4+4=0
        # char0: d=0 → factor=1; char3: d=3 → factor<1
        c0 = p.color_for(frame=8, char_index=0, total_chars=10)
        c3 = p.color_for(frame=8, char_index=3, total_chars=10)
        assert (c0.red, c0.green, c0.blue) != (c3.red, c3.green, c3.blue)

    def test_total_chars_one_does_not_divide_by_zero(self):
        """Single-char text must not raise ZeroDivisionError."""
        p = self._make(speed=10.0, width=4.0, pause=0)
        # Should not raise
        c = p.color_for(frame=0, char_index=0, total_chars=1)
        assert c is not None
        assert isinstance(c, Color)

    def test_cycle_repeats(self):
        """After one full cycle, frame 0 and frame cycle_end give same output."""
        # speed=10, width=4, pause=0, total_chars=10:
        # travel=14, sweep_frames=14/10*20=28, cycle=28
        p = self._make(speed=10.0, width=4.0, pause=0)
        c_start = p.color_for(frame=0, char_index=0, total_chars=10)
        c_cycle = p.color_for(frame=28, char_index=0, total_chars=10)
        assert (c_start.red, c_start.green, c_start.blue) == (
            c_cycle.red,
            c_cycle.green,
            c_cycle.blue,
        )

    def test_colored_base_and_shimmer(self):
        """With non-black base and non-white shimmer, interpolation is correct."""
        p = Shimmer(
            base_color=Color(100, 0, 0),  # dark red
            shimmer_color=Color(255, 255, 0),  # yellow
            speed=10.0,
            width=4.0,
            pause=0,
        )
        # travel=14, sweep=28; center=0 at frame=4 → char_index=0 d=0 → factor=1.0
        c = p.color_for(frame=4, char_index=0, total_chars=10)
        assert c.red == 255
        assert c.green == 255
        assert c.blue == 0


class TestShimmerEnvelopeAndTiming:
    """New tests: glide-in/out envelope + true-FPS constant."""

    def _make(self, **kwargs):
        return Shimmer(
            base_color=Color(0, 0, 0),
            shimmer_color=Color(255, 255, 255),
            **kwargs,
        )

    def test_sweep_enters_and_exits_gradually(self):
        """At frame 1 (first engine tick) char 0 must barely shimmer (< 15% of peak
        factor). Symmetric check at the last sweep frame for the last char.
        Exact-zero pins at t=0 and t=sweep (spot fully off-screen on both ends).
        """
        # speed=14 (default), width=8 (default), pause=0, total_chars=10
        # travel=18, sweep_frames=18/14*20≈25.71
        p = self._make(speed=14.0, width=8.0, pause=0)
        total_chars = 10
        chars = total_chars
        half_width = 4.0
        sweep_frames = (chars + 8.0) / 14.0 * 20.0  # ≈ 25.71

        # --- t=0: center=-4, char_index=0 d=4 >= 4 → factor=0 → exact base ---
        c_t0 = p.color_for(frame=0, char_index=0, total_chars=total_chars)
        assert (c_t0.red, c_t0.green, c_t0.blue) == (0, 0, 0), (
            "At t=0 the spot is fully off-screen left; char 0 must see base color"
        )

        # --- frame=1 (first tick): center=-4+(1/sweep)*18 ≈ -3.30 ---
        # char_index=0: d≈3.30, factor=0.5+0.5*cos(π*3.30/4)
        center_1 = -half_width + (1.0 / sweep_frames) * (chars + 8.0)
        d_1 = abs(0 - center_1)
        if d_1 < half_width:
            factor_1 = 0.5 + 0.5 * math.cos(math.pi * d_1 / half_width)
        else:
            factor_1 = 0.0
        c_f1 = p.color_for(frame=1, char_index=0, total_chars=total_chars)
        if factor_1 == 0.0:
            assert (c_f1.red, c_f1.green, c_f1.blue) == (0, 0, 0)
        else:
            # The factor at frame 1 must be < 0.15 of peak (antagonist: ≈ 0.074)
            assert factor_1 < 0.15, (
                f"frame=1 char_0 factor={factor_1:.4f} must be < 0.15; "
                "envelope not gliding in gradually"
            )
            # Cross-check the returned color channel lines up with the factor
            expected_r = int(factor_1 * 255)
            assert abs(c_f1.red - expected_r) <= 1, (
                f"frame=1 red={c_f1.red} expected≈{expected_r}"
            )

        # --- symmetric exit: last char at (sweep_frames-1) ---
        last_char = total_chars - 1  # = 9
        frame_near_end = int(sweep_frames) - 1  # last integer frame inside sweep
        center_end = -half_width + (frame_near_end / sweep_frames) * (chars + 8.0)
        d_end = abs(last_char - center_end)
        if d_end < half_width:
            factor_end = 0.5 + 0.5 * math.cos(math.pi * d_end / half_width)
        else:
            factor_end = 0.0
        c_fend = p.color_for(
            frame=frame_near_end, char_index=last_char, total_chars=total_chars
        )
        if factor_end == 0.0:
            assert (c_fend.red, c_fend.green, c_fend.blue) == (0, 0, 0)
        else:
            assert factor_end < 0.15, (
                f"frame={frame_near_end} char_{last_char} factor={factor_end:.4f} "
                "must be < 0.15; envelope not gliding out gradually"
            )

        # --- t=sweep: spot fully off-screen right → base.
        # Use a separate shimmer with integer sweep_frames for an exact pin:
        # speed=10, width=2, chars=8 → travel=10, sweep=10/10*20=20 (exact)
        p_int = self._make(speed=10.0, width=2.0, pause=1.0)
        # frame=20 → t = 20 % (20 + 20) = 20 = sweep_frames → in pause → base
        c_tsweep = p_int.color_for(frame=20, char_index=0, total_chars=8)
        assert (c_tsweep.red, c_tsweep.green, c_tsweep.blue) == (0, 0, 0), (
            "At t=sweep_frames the spot exits the text; must return base"
        )

    def test_pause_duration_matches_configured_seconds(self):
        """pause=0.8 s → 0.8 * 20 = 16 pause_frames (pins the 20-fps fix)."""
        p = self._make(speed=14.0, width=8.0, pause=0.8)
        sweep_frames, cycle_frames = p._cycle_geometry(10)
        pause_frames = cycle_frames - sweep_frames
        assert pause_frames == pytest.approx(16.0), (
            f"pause=0.8 s at 20 fps must give 16 pause_frames, got {pause_frames:.3f}"
        )

    def test_speed_is_true_chars_per_second(self):
        """travel/speed * 20 == sweep_frames for a range of params."""
        for speed, width, chars in [(14.0, 8.0, 10), (10.0, 4.0, 20), (5.0, 2.0, 5)]:
            p = self._make(speed=speed, width=width, pause=0)
            expected = (chars + width) / speed * 20.0
            sweep_frames, _ = p._cycle_geometry(chars)
            assert sweep_frames == pytest.approx(expected), (
                f"speed={speed} width={width} chars={chars}: "
                f"sweep_frames={sweep_frames:.4f} expected={expected:.4f}"
            )

    def test_pause_guard_boundary_below_never_defers(self):
        """pause=0.04 s → 0.04*20=0.8 pause_frames < 1 → never defers.
        (At old FPS=30 this would have been 0.04*30=1.2 frames ≥ 1 and DID defer.)
        """
        from led_ticker.color_providers import _SHIMMER_FPS

        p = self._make(speed=14.0, width=8.0, pause=0.04)
        # Confirm the guard triggers
        _, cycle_frames = p._cycle_geometry(20)
        sweep_frames, _ = p._cycle_geometry(20)
        pause_frames = cycle_frames - sweep_frames
        assert pause_frames < 1.0, (
            f"pause=0.04 at {_SHIMMER_FPS} fps should give < 1 pause_frame; "
            f"got {pause_frames:.3f}"
        )
        for frame in range(0, 200, 7):
            assert p.frames_to_rest(frame, 20) == 0

    def test_pause_guard_boundary_above_defers_normally(self):
        """pause=0.06 s → 0.06*20=1.2 pause_frames ≥ 1 → defers normally."""
        from led_ticker.color_providers import _SHIMMER_FPS

        p = self._make(speed=14.0, width=8.0, pause=0.06)
        sweep_frames, cycle_frames = p._cycle_geometry(20)
        pause_frames = cycle_frames - sweep_frames
        assert pause_frames >= 1.0, (
            f"pause=0.06 at {_SHIMMER_FPS} fps should give >= 1 pause_frame; "
            f"got {pause_frames:.3f}"
        )
        # At least one frame inside the sweep should report non-zero
        defers = [p.frames_to_rest(f, 20) for f in range(0, int(sweep_frames))]
        assert any(d > 0 for d in defers), (
            "pause=0.06 should yield at least one frame that defers"
        )


class TestShimmerCoercion:
    """_coerce_color_provider wiring for shimmer style."""

    def _coerce(self, value):
        from led_ticker.app.coercion import _coerce_color_provider

        return _coerce_color_provider(value)

    def test_basic_shimmer_dict(self):
        """Minimal dict returns a Shimmer instance."""
        from led_ticker.color_providers import Shimmer

        p = self._coerce({"style": "shimmer"})
        assert isinstance(p, Shimmer)

    def test_defaults_applied(self):
        """Absent base/shimmer get their documented defaults."""
        from led_ticker.color_providers import Shimmer

        p = self._coerce({"style": "shimmer"})
        assert isinstance(p, Shimmer)
        assert (p._base.red, p._base.green, p._base.blue) == (60, 60, 80)
        assert (p._shimmer.red, p._shimmer.green, p._shimmer.blue) == (255, 255, 255)
        assert p.speed == 14.0
        assert p.width == 8.0
        assert p.pause == 0.5

    def test_base_rgb_list(self):
        p = self._coerce({"style": "shimmer", "base": [100, 50, 200]})
        assert (p._base.red, p._base.green, p._base.blue) == (100, 50, 200)

    def test_shimmer_rgb_list(self):
        p = self._coerce({"style": "shimmer", "shimmer": [255, 220, 100]})
        assert (p._shimmer.red, p._shimmer.green, p._shimmer.blue) == (255, 220, 100)

    def test_base_string_white(self):
        p = self._coerce({"style": "shimmer", "base": "white"})
        assert (p._base.red, p._base.green, p._base.blue) == (255, 255, 255)

    def test_shimmer_string_gold(self):
        p = self._coerce({"style": "shimmer", "shimmer": "gold"})
        assert (p._shimmer.red, p._shimmer.green, p._shimmer.blue) == (255, 200, 50)

    def test_shimmer_string_blue(self):
        p = self._coerce({"style": "shimmer", "shimmer": "blue"})
        assert (p._shimmer.red, p._shimmer.green, p._shimmer.blue) == (100, 180, 255)

    def test_shimmer_string_cyan(self):
        p = self._coerce({"style": "shimmer", "shimmer": "cyan"})
        assert (p._shimmer.red, p._shimmer.green, p._shimmer.blue) == (0, 220, 220)

    def test_unknown_base_shorthand_raises(self):
        with pytest.raises(ValueError, match="unknown"):
            self._coerce({"style": "shimmer", "base": "magenta"})

    def test_unknown_shimmer_shorthand_raises(self):
        with pytest.raises(ValueError, match="unknown"):
            self._coerce({"style": "shimmer", "shimmer": "magenta"})

    def test_custom_speed_width_pause(self):
        p = self._coerce(
            {
                "style": "shimmer",
                "speed": 20.0,
                "width": 5.0,
                "pause": 1.5,
            }
        )
        assert p.speed == 20.0
        assert p.width == 5.0
        assert p.pause == 1.5

    def test_unknown_kwarg_raises(self):
        with pytest.raises(ValueError, match="unknown"):
            self._coerce({"style": "shimmer", "bogus": 42})

    def test_invalid_base_rgb_raises(self):
        with pytest.raises(ValueError):
            self._coerce({"style": "shimmer", "base": [300, 0, 0]})

    def test_invalid_shimmer_rgb_raises(self):
        with pytest.raises(ValueError):
            self._coerce({"style": "shimmer", "shimmer": [0, 0, -1]})

    def test_all_four_shorthands_resolve(self):
        """Each shorthand resolves for both base= and shimmer= slots."""
        from led_ticker.app.coercion import _SHIMMER_COLOR_SHORTHANDS

        for name in _SHIMMER_COLOR_SHORTHANDS:
            p = self._coerce({"style": "shimmer", "shimmer": name})
            expected = _SHIMMER_COLOR_SHORTHANDS[name]
            assert (
                p._shimmer.red,
                p._shimmer.green,
                p._shimmer.blue,
            ) == expected, f"shimmer shorthand {name!r} did not resolve to {expected}"

        for name in _SHIMMER_COLOR_SHORTHANDS:
            p = self._coerce({"style": "shimmer", "base": name})
            expected = _SHIMMER_COLOR_SHORTHANDS[name]
            assert (
                p._base.red,
                p._base.green,
                p._base.blue,
            ) == expected, f"base shorthand {name!r} did not resolve to {expected}"

    def test_base_color_internal_name_rejected(self):
        """base_color (internal kwarg name) is rejected with a clear error."""
        with pytest.raises(ValueError, match="base_color"):
            self._coerce({"style": "shimmer", "base_color": [255, 0, 0]})

    def test_shimmer_color_internal_name_rejected(self):
        """shimmer_color (internal kwarg name) is rejected with a clear error."""
        with pytest.raises(ValueError, match="shimmer_color"):
            self._coerce({"style": "shimmer", "shimmer_color": [255, 0, 0]})

    def test_shimmer_string_shorthand_plain(self):
        """Plain string 'shimmer' resolves to a Shimmer instance with defaults."""
        from led_ticker.color_providers import Shimmer

        p = self._coerce("shimmer")
        assert isinstance(p, Shimmer)
