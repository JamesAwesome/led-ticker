"""Tests for tools/gif_plan/widgets.py — per-widget math helpers."""

from __future__ import annotations

from tools.gif_plan.widgets import (
    canvas_width_logical,
    estimate_content_width_logical,
)


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


class TestContentWidth:
    def test_bdf_5x8_simple_text(self):
        # 5x8 BDF: 5 px/char × "HELLO" (5 chars) = 25.
        assert estimate_content_width_logical("HELLO", font="5x8") == 25

    def test_bdf_6x12_simple_text(self):
        # 6x12: 6 px/char × "HELLO" = 30.
        assert estimate_content_width_logical("HELLO", font="6x12") == 30

    def test_inline_emoji_counts_as_8(self):
        # ":heart: HI" → emoji is 8 px + " HI" is 3 chars × 5 = 15
        # at 5x8 font. Total 23.
        result = estimate_content_width_logical(":heart: HI", font="5x8")
        assert result == 23

    def test_multiple_inline_emoji(self):
        # ":a::b:" → two 8-px sprites = 16 (no characters between).
        result = estimate_content_width_logical(":a::b:", font="5x8")
        assert result == 16

    def test_hires_font_uses_size_times_055(self):
        # Inter-Bold @ font_size=22, "HI" (2 chars).
        # Per-char width ≈ ceil(22 × 0.55) = 13. "HI" = 26.
        result = estimate_content_width_logical("HI", font="Inter-Bold", font_size=22)
        assert result == 26

    def test_unknown_font_falls_back_to_6_per_char(self):
        # Unknown BDF alias → 6 px/char default.
        assert estimate_content_width_logical("HELLO", font="weird") == 30

    def test_empty_text_zero_width(self):
        assert estimate_content_width_logical("", font="5x8") == 0
