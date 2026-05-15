"""Tests for tools/gif_plan/widgets.py — per-widget math helpers."""

from __future__ import annotations

from tools.gif_plan.widgets import canvas_width_logical


class TestCanvasWidth:
    def test_smallsign_default_scale(self):
        # 5 panels × 32 cols / scale=1 = 160 logical px.
        display = {"cols": 32, "chain": 5, "default_scale": 1}
        section = {}
        assert canvas_width_logical(display, section) == 160

    def test_section_scale_override(self):
        # Section scale=2 halves the logical width.
        display = {"cols": 32, "chain": 5, "default_scale": 1}
        section = {"scale": 2}
        assert canvas_width_logical(display, section) == 80

    def test_default_scale_fallback(self):
        # No section.scale → fall back to display.default_scale.
        display = {"cols": 64, "chain": 8, "default_scale": 4}
        section = {}
        # Naive: (64 × 8) / 4 = 128. This is the v1 caveat — bigsign
        # actual is 64, but pixel_mapper handling is future work.
        assert canvas_width_logical(display, section) == 128

    def test_missing_default_scale_treated_as_one(self):
        # If display omits default_scale, use 1.
        display = {"cols": 32, "chain": 5}
        section = {}
        assert canvas_width_logical(display, section) == 160
