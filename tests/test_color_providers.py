"""Tests for color_providers module."""

from __future__ import annotations

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

    def test_per_char_is_false(self):
        provider = _ConstantColor(Color(0, 0, 0))
        assert provider.per_char is False


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

    def test_per_char_is_false(self):
        provider = Random()
        assert provider.per_char is False


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
