"""Tests for color_providers module."""

from __future__ import annotations

import pytest
from rgbmatrix.graphics import Color

from led_ticker.color_providers import Random, _ConstantColor


class TestConstantColor:
    """`_ConstantColor` wraps a graphics.Color and always returns it
    regardless of frame / char_index. `per_char = False`."""

    def test_color_for_returns_wrapped_color(self):
        c = Color(255, 100, 50)
        provider = _ConstantColor(c)
        assert provider.color_for(0, 0, 1) is c

    def test_color_for_ignores_frame_and_index(self):
        c = Color(10, 20, 30)
        provider = _ConstantColor(c)
        assert provider.color_for(0, 0, 1) is c
        assert provider.color_for(99, 5, 100) is c


class TestRandom:
    """`Random` picks a single color when constructed and returns it
    for every call. Stable per-instance, NOT per-frame (matches the
    existing 'random' sentinel semantic where each visit gets one
    color, not a flicker)."""

    def test_color_for_stable_across_calls(self):
        provider = Random()
        c1 = provider.color_for(0, 0, 1)
        c2 = provider.color_for(50, 3, 10)
        assert c1.red == c2.red
        assert c1.green == c2.green
        assert c1.blue == c2.blue

    def test_two_instances_can_differ(self):
        """Two separately-constructed Random providers can differ
        (probabilistic; rerun if both happen to pick same color)."""
        # Sample many to make collision astronomically unlikely
        samples = [Random().color_for(0, 0, 1) for _ in range(20)]
        rgbs = {(s.red, s.green, s.blue) for s in samples}
        assert len(rgbs) > 1, "all 20 Random instances picked the same color"


class TestRainbow:
    """Per-character hue offset, advancing per frame."""

    def test_per_char_is_true(self):
        from led_ticker.color_providers import Rainbow

        assert Rainbow().per_char is True

    def test_frame_zero_char_zero_returns_hue_zero(self):
        from led_ticker.color_providers import Rainbow

        provider = Rainbow(speed=8, char_offset=30)
        c = provider.color_for(0, 0, 10)
        # hue = 0 → red (255, 0, 0)
        assert c.red == 255
        assert c.green == 0
        assert c.blue == 0

    def test_char_offset_shifts_hue(self):
        from led_ticker.color_providers import Rainbow

        provider = Rainbow(speed=8, char_offset=30)
        c0 = provider.color_for(0, 0, 10)
        c1 = provider.color_for(0, 1, 10)
        # Different chars, same frame → different hues
        assert (c0.red, c0.green, c0.blue) != (c1.red, c1.green, c1.blue)

    def test_frame_advances_hue(self):
        from led_ticker.color_providers import Rainbow

        provider = Rainbow(speed=8, char_offset=30)
        c0 = provider.color_for(0, 0, 10)
        c10 = provider.color_for(10, 0, 10)
        assert (c0.red, c0.green, c0.blue) != (c10.red, c10.green, c10.blue)


class TestColorCycle:
    """Whole-string hue rotation; char_index ignored."""

    def test_per_char_is_false(self):
        from led_ticker.color_providers import ColorCycle

        assert ColorCycle().per_char is False

    def test_char_index_ignored(self):
        from led_ticker.color_providers import ColorCycle

        provider = ColorCycle(speed=5)
        c0 = provider.color_for(10, 0, 5)
        c4 = provider.color_for(10, 4, 5)
        assert (c0.red, c0.green, c0.blue) == (c4.red, c4.green, c4.blue)

    def test_frame_advances_hue(self):
        from led_ticker.color_providers import ColorCycle

        provider = ColorCycle(speed=5)
        c0 = provider.color_for(0, 0, 1)
        c10 = provider.color_for(10, 0, 1)
        assert (c0.red, c0.green, c0.blue) != (c10.red, c10.green, c10.blue)


class TestColorCycleRange:
    """color_cycle with from_hue/to_hue restricts the sweep to a hue arc."""

    def test_no_range_full_wheel_unchanged(self):
        """Without from/to the provider behaves exactly as before."""
        import colorsys

        from led_ticker.color_providers import ColorCycle

        provider = ColorCycle(speed=5)
        for frame in [0, 10, 36, 72]:
            c = provider.color_for(frame, 0, 1)
            expected_hue = ((frame * 5) % 360) / 360
            er, eg, eb = (
                int(x * 255) for x in colorsys.hsv_to_rgb(expected_hue, 1.0, 1.0)
            )
            assert (c.red, c.green, c.blue) == (er, eg, eb)

    def test_range_starts_at_from_hue(self):
        """Frame 0 should produce from_hue exactly."""
        import colorsys

        from led_ticker.color_providers import ColorCycle

        # Red (hue=0°) → Green (hue=120°), forward arc
        provider = ColorCycle(speed=5, from_hue=0.0, to_hue=120.0)
        c = provider.color_for(0, 0, 1)
        er, eg, eb = (int(x * 255) for x in colorsys.hsv_to_rgb(0.0, 1.0, 1.0))
        assert (c.red, c.green, c.blue) == (er, eg, eb)

    def test_forward_arc_stays_in_range(self):
        """Red→Green (120° forward): hues should stay in [0°, 120°]."""
        import colorsys

        from led_ticker.color_providers import ColorCycle

        provider = ColorCycle(speed=1, from_hue=0.0, to_hue=120.0)
        for frame in range(200):
            c = provider.color_for(frame, 0, 1)
            h, _, _ = colorsys.rgb_to_hsv(c.red / 255, c.green / 255, c.blue / 255)
            hue_deg = h * 360
            assert 0 <= hue_deg <= 120.0 or hue_deg == 0.0, (
                f"frame {frame}: hue {hue_deg:.1f}° outside [0°, 120°]"
            )

    def test_shorter_arc_red_to_blue(self):
        """Red (0°) → Blue (240°): shorter arc = 120° backward through magenta.

        The hue should stay in [240°, 360°] (magenta/violet band), never
        passing through yellow/green/cyan (the longer 240° forward arc)."""
        import colorsys

        from led_ticker.color_providers import ColorCycle

        provider = ColorCycle(speed=1, from_hue=0.0, to_hue=240.0)
        for frame in range(1, 150):
            c = provider.color_for(frame, 0, 1)
            h, _, _ = colorsys.rgb_to_hsv(c.red / 255, c.green / 255, c.blue / 255)
            hue_deg = h * 360
            # Backward arc: hue decreases from 0° → 360°/300°/240°
            # In [240, 360] or back at 0 (frame 0 only)
            in_backward_band = hue_deg >= 240.0 or hue_deg == 0.0
            assert in_backward_band, (
                f"frame {frame}: hue {hue_deg:.1f}° — expected shorter arc "
                f"(magenta band 240–360°), got yellow/green/cyan"
            )

    def test_range_wraps_back_to_start(self):
        """After one full arc traversal the hue should return to from_hue."""

        from led_ticker.color_providers import ColorCycle

        # 120° arc, speed=1 → 120 frames per cycle
        provider = ColorCycle(speed=1, from_hue=0.0, to_hue=120.0)
        c_start = provider.color_for(0, 0, 1)
        c_wrap = provider.color_for(120, 0, 1)
        assert (c_start.red, c_start.green, c_start.blue) == (
            c_wrap.red,
            c_wrap.green,
            c_wrap.blue,
        )


class TestGradient:
    """Linear left-to-right; char_index spaces hues; frame ignored."""

    def test_per_char_is_true(self):
        from rgbmatrix.graphics import Color

        from led_ticker.color_providers import Gradient

        assert (
            Gradient(from_color=Color(0, 0, 0), to_color=Color(255, 255, 255)).per_char
            is True
        )

    def test_char_zero_returns_from(self):
        from rgbmatrix.graphics import Color

        from led_ticker.color_providers import Gradient

        provider = Gradient(from_color=Color(255, 0, 0), to_color=Color(0, 0, 255))
        c = provider.color_for(0, 0, 5)
        assert (c.red, c.green, c.blue) == (255, 0, 0)

    def test_last_char_returns_to(self):
        from rgbmatrix.graphics import Color

        from led_ticker.color_providers import Gradient

        provider = Gradient(from_color=Color(255, 0, 0), to_color=Color(0, 0, 255))
        # total_chars = 5, so char_index = 4 is the last char
        c = provider.color_for(0, 4, 5)
        assert (c.red, c.green, c.blue) == (0, 0, 255)

    def test_middle_interpolates(self):
        from rgbmatrix.graphics import Color

        from led_ticker.color_providers import Gradient

        provider = Gradient(from_color=Color(255, 0, 0), to_color=Color(0, 0, 255))
        # char_index = 2 of 5 → interpolation factor 0.5
        c = provider.color_for(0, 2, 5)
        assert 100 < c.red < 200
        assert c.green == 0
        assert 50 < c.blue < 150

    def test_frame_ignored(self):
        from rgbmatrix.graphics import Color

        from led_ticker.color_providers import Gradient

        provider = Gradient(from_color=Color(255, 0, 0), to_color=Color(0, 0, 255))
        c0 = provider.color_for(0, 1, 5)
        c100 = provider.color_for(100, 1, 5)
        assert (c0.red, c0.green, c0.blue) == (c100.red, c100.green, c100.blue)

    def test_total_chars_one_returns_from(self):
        """Edge case: single char → just return `from`."""
        from rgbmatrix.graphics import Color

        from led_ticker.color_providers import Gradient

        provider = Gradient(from_color=Color(255, 0, 0), to_color=Color(0, 0, 255))
        c = provider.color_for(0, 0, 1)
        assert (c.red, c.green, c.blue) == (255, 0, 0)


class TestFrameInvariantFlag:
    """Pin the `frame_invariant` class attribute on every provider.

    The flag drives the static-text fast path in
    `_BaseImageWidget._play_with_text`: True providers paint once and
    sleep; False providers force the per-tick render loop. Wrong
    values silently regress hardware behavior — frame_invariant=True
    on Rainbow would freeze the rainbow on a static image; False on
    Gradient would burn CPU re-rendering the same gradient every
    50ms tick.
    """

    def test_constant_color_is_frame_invariant(self):
        from rgbmatrix.graphics import Color

        from led_ticker.color_providers import _ConstantColor

        assert _ConstantColor(Color(0, 0, 0)).frame_invariant is True

    def test_random_is_frame_invariant(self):
        from led_ticker.color_providers import Random

        assert Random().frame_invariant is True

    def test_gradient_is_frame_invariant(self):
        from rgbmatrix.graphics import Color

        from led_ticker.color_providers import Gradient

        provider = Gradient(from_color=Color(255, 0, 0), to_color=Color(0, 0, 255))
        assert provider.frame_invariant is True

    def test_rainbow_is_not_frame_invariant(self):
        from led_ticker.color_providers import Rainbow

        assert Rainbow().frame_invariant is False

    def test_color_cycle_is_not_frame_invariant(self):
        from led_ticker.color_providers import ColorCycle

        assert ColorCycle().frame_invariant is False


class TestColorProviderBase:
    def test_subclass_without_frame_invariant_raises(self):
        from led_ticker.color_providers import ColorProviderBase

        with pytest.raises(TypeError, match="frame_invariant"):

            class BadProvider(ColorProviderBase):
                per_char = False

                def color_for(self, frame, char_index, total_chars):
                    return None  # pragma: no cover

    def test_subclass_with_class_attribute_ok(self):
        from led_ticker.color_providers import ColorProviderBase

        class GoodProvider(ColorProviderBase):
            per_char = False
            frame_invariant = True

            def color_for(self, frame, char_index, total_chars):
                return None  # pragma: no cover

    def test_subclass_with_property_ok(self):
        from led_ticker.color_providers import ColorProviderBase

        class DynamicProvider(ColorProviderBase):
            per_char = False

            @property
            def frame_invariant(self) -> bool:
                return False

            def color_for(self, frame, char_index, total_chars):
                return None  # pragma: no cover

    def test_existing_providers_satisfy_base(self):
        from led_ticker.color_providers import (
            ColorCycle,
            ColorProviderBase,
            Gradient,
            Rainbow,
            Random,
            Shimmer,
            _ConstantColor,
        )

        for cls in (_ConstantColor, Random, Rainbow, ColorCycle, Gradient, Shimmer):
            assert issubclass(cls, ColorProviderBase), f"{cls.__name__} not a subclass"


class TestContinuousProviderRestartOnVisit:
    """Pin the `restart_on_visit = False` class attribute on
    continuous-phase color providers. Read by `FrameAwareBase.reset_frame`
    in widgets/_frame_aware.py. Catches a future change that flips
    the default."""

    def test_rainbow_restart_on_visit_is_false(self):
        from led_ticker.color_providers import Rainbow

        assert Rainbow.restart_on_visit is False, (
            "Rainbow.restart_on_visit must be False — the chase "
            "phase should advance continuously across loop_count "
            "boundaries within a section"
        )

    def test_color_cycle_restart_on_visit_is_false(self):
        from led_ticker.color_providers import ColorCycle

        assert ColorCycle.restart_on_visit is False, (
            "ColorCycle.restart_on_visit must be False — the cycle "
            "should advance continuously across loop_count boundaries"
        )


class TestColorLUT:
    """Precomputed 360-entry hue → Color table.

    hue_color(deg) must return a pre-built Color object — the same object
    for repeated calls with the same integer degree, no colorsys call
    needed after the first build."""

    def test_hue_color_returns_red_at_zero(self):
        from led_ticker.color_lut import hue_color

        c = hue_color(0)
        assert c.red == 255
        assert c.green == 0
        assert c.blue == 0

    def test_hue_color_same_degree_returns_same_object(self):
        """Core LUT contract: same degree → same pre-built object (not a
        new allocation). Identity check — colorsys is only called once."""
        from led_ticker.color_lut import hue_color

        c1 = hue_color(120)
        c2 = hue_color(120)
        assert c1 is c2, (
            "hue_color should return the same object for the same degree — "
            "LUT is not working"
        )

    def test_hue_color_wraps_at_360(self):
        from led_ticker.color_lut import hue_color

        assert hue_color(0) is hue_color(360)
        assert hue_color(0) is hue_color(720)

    def test_hue_color_float_truncates(self):
        """Float degrees truncate to int — 119.9 and 119.0 both hit LUT[119]."""
        from led_ticker.color_lut import hue_color

        assert hue_color(119.9) is hue_color(119.0)

    def test_rainbow_same_args_returns_same_object(self):
        """Rainbow.color_for with the same (frame, char_index) must return
        the cached Color object, not a freshly-allocated one."""
        from led_ticker.color_providers import Rainbow

        r = Rainbow()
        c1 = r.color_for(frame=5, char_index=2, total_chars=10)
        c2 = r.color_for(frame=5, char_index=2, total_chars=10)
        assert c1 is c2, (
            "Rainbow.color_for should use the LUT — same args → same object"
        )

    def test_color_cycle_same_frame_returns_same_object(self):
        from led_ticker.color_providers import ColorCycle

        cc = ColorCycle(speed=5)
        c1 = cc.color_for(frame=10, char_index=0, total_chars=1)
        c2 = cc.color_for(frame=10, char_index=4, total_chars=1)
        # ColorCycle ignores char_index — same frame → same LUT entry
        assert c1 is c2
