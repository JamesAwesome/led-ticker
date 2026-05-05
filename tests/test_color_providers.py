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
