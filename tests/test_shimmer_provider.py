"""Tests for the Shimmer color provider."""

from __future__ import annotations

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
        # sweep_frames = 10/10 * 30 = 30 frames
        # center at frame 0 → char 0
        p = self._make(speed=10.0, width=4.0, pause=0)
        # frame=0, center=0.0, char_index=0 → d=0 → factor=1.0 → full shimmer
        c = p.color_for(frame=0, char_index=0, total_chars=10)
        assert c.red > 200, f"center char should be near shimmer color, got r={c.red}"
        assert c.green > 200
        assert c.blue > 200

    def test_outside_spot_returns_base(self):
        """char outside the spot width returns base color exactly."""
        p = self._make(speed=10.0, width=2.0, pause=0)
        # sweep_frames=30, frame=0 → center=0, half_width=1.0
        # char_index=5 → d=5, 5 >= 1.0 → returns base
        c = p.color_for(frame=0, char_index=5, total_chars=10)
        assert (c.red, c.green, c.blue) == (0, 0, 0)

    def test_during_pause_returns_base(self):
        """During the pause period every char returns base color."""
        # speed=10, pause=1.0, total_chars=10
        # sweep_frames = 10/10 * 30 = 30; pause_frames = 30; cycle = 60
        # frame=45 → t=45, 45 >= 30 → in pause
        p = self._make(speed=10.0, width=4.0, pause=1.0)
        for char_index in range(10):
            c = p.color_for(frame=45, char_index=char_index, total_chars=10)
            rgb = (c.red, c.green, c.blue)
            assert rgb == (
                0,
                0,
                0,
            ), f"char {char_index}: expected base during pause, got {rgb}"

    def test_edge_of_spot_is_darker_than_center(self):
        """char at edge of spot (d = half_width - epsilon) is dimmer than center."""
        p = self._make(speed=10.0, width=4.0, pause=0)
        # frame=0, center=0, half_width=2
        c_center = p.color_for(frame=0, char_index=0, total_chars=10)
        # char_index=1 → d=1, still inside (1 < 2); factor = 0.5 + 0.5*cos(π/2) = 0.5
        c_edge = p.color_for(frame=0, char_index=1, total_chars=10)
        assert c_center.red > c_edge.red, "center should be brighter than edge"

    def test_different_chars_get_different_colors_during_sweep(self):
        """Two chars at different distances from the spot center differ."""
        p = self._make(speed=10.0, width=8.0, pause=0)
        # frame=0: center=0; both chars 0 and 3 are inside, but d differs
        c0 = p.color_for(frame=0, char_index=0, total_chars=10)
        c3 = p.color_for(frame=0, char_index=3, total_chars=10)
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
        # speed=10, pause=0, total_chars=10: sweep_frames=30, cycle=30
        p = self._make(speed=10.0, width=4.0, pause=0)
        c_start = p.color_for(frame=0, char_index=0, total_chars=10)
        c_cycle = p.color_for(frame=30, char_index=0, total_chars=10)
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
        # frame=0, char_index=0 → factor=1.0 → full shimmer
        c = p.color_for(frame=0, char_index=0, total_chars=10)
        assert c.red == 255
        assert c.green == 255
        assert c.blue == 0


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
