"""Tests for tools/gif_plan/widgets.py — per-widget math helpers."""

from __future__ import annotations

from PIL import Image as PILImage
from tools.gif_plan.widgets import (
    canvas_width_logical,
    estimate_content_width_logical,
    gif_visit_ms,
    image_visit_ms,
    ticker_message_visit_ms,
    two_row_visit_ms,
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


class TestTickerMessageVisitMs:
    def test_static_text_fits_uses_hold_time(self):
        # Text fits → static hold. 4 seconds × 1000 = 4000 ms.
        widget = {"type": "message", "text": "HI", "font": "5x8"}
        section = {"hold_time": 4.0, "scroll_step_ms": 25}
        assert ticker_message_visit_ms(widget, section, canvas_w=160) == 4000

    def test_overflow_scrolls_one_pass(self):
        # text width = 160 (assume), canvas = 160 → pass = (160+160)×25 = 8000.
        widget = {
            "type": "message",
            # 32 chars × 5 = 160 (overflows 160 canvas, since 160 < 161).
            "text": "x" * 33,  # 33 × 5 = 165 px overflow
            "font": "5x8",
        }
        section = {"hold_time": 2.0, "scroll_step_ms": 25}
        result = ticker_message_visit_ms(widget, section, canvas_w=160)
        # Pass duration = (160 + 165) × 25 = 8125 ms; > hold so wins.
        # But we also add the hold to the total for pre+post-scroll pause.
        # Spec: pass_ms only; the engine's hold_time happens around it
        # but for "did the gif capture the full scroll" the pass is
        # what matters. Use pass_ms as the visit floor.
        assert result == 8125

    def test_text_wrap_uses_max_of_loops_or_hold(self):
        # text_wrap=true: max(text_loops × cycle_ms, hold × 1000).
        widget = {
            "type": "message",
            "text": "BREAK",  # 5 chars × 5 = 25 px
            "font": "5x8",
            "text_wrap": True,
            "text_separator": " • ",  # 3 chars × 5 = 15 px (approx)
            "text_loops": 3,
        }
        section = {"hold_time": 1.0, "scroll_step_ms": 25}
        # cycle = 25 + 15 = 40 px. 3 × 40 × 25 = 3000 ms. hold=1000ms.
        # max(3000, 1000) = 3000.
        result = ticker_message_visit_ms(widget, section, canvas_w=160)
        assert result == 3000

    def test_text_wrap_hold_wins_over_short_loops(self):
        widget = {
            "type": "message",
            "text": "HI",
            "font": "5x8",
            "text_wrap": True,
            "text_separator": " • ",
            "text_loops": 1,
        }
        section = {"hold_time": 10.0, "scroll_step_ms": 25}
        # cycle = 10 + 15 = 25 px. 1 × 25 × 25 = 625 ms. hold=10000ms.
        # max = 10000.
        result = ticker_message_visit_ms(widget, section, canvas_w=160)
        assert result == 10000


class TestTwoRowVisitMs:
    def _section(self, **kw):
        base = {"hold_time": 5.0, "scroll_step_ms": 25}
        base.update(kw)
        return base

    def test_default_short_bottom_fits_uses_hold(self):
        widget = {
            "type": "two_row",
            "top_text": "TOP",
            "bottom_text": "HI",  # fits 160 canvas
            "font": "5x8",
        }
        result = two_row_visit_ms(widget, self._section(), canvas_w=160)
        # Static bottom → hold_time × 1000.
        assert result == 5000

    def test_default_overflow_bottom_scrolls_one_pass(self):
        widget = {
            "type": "two_row",
            "top_text": "TOP",
            "bottom_text": "x" * 40,  # 40 × 5 = 200 px overflow
            "font": "5x8",
        }
        result = two_row_visit_ms(widget, self._section(), canvas_w=160)
        # pass = (160 + 200) × 25 = 9000 ms.
        assert result == 9000

    def test_wrap_uses_max_of_loops_or_hold(self):
        widget = {
            "type": "two_row",
            "top_text": "TOP",
            "bottom_text": "tap",  # 3 × 5 = 15 px
            "font": "5x8",
            "bottom_text_wrap": True,
            "bottom_text_separator": " * ",  # 3 × 5 = 15 px
            "bottom_text_loops": 3,
        }
        result = two_row_visit_ms(widget, self._section(hold_time=1.0), canvas_w=160)
        # cycle = 15+15 = 30. 3 × 30 × 25 = 2250 ms. hold=1000. max=2250.
        assert result == 2250

    def test_scroll_through_uses_max_of_loops_or_hold(self):
        widget = {
            "type": "two_row",
            "top_text": "TOP",
            "bottom_text": "x" * 40,  # 200 px
            "font": "5x8",
            "bottom_text_scroll": "scroll_through",
            "bottom_text_loops": 2,
        }
        result = two_row_visit_ms(widget, self._section(hold_time=1.0), canvas_w=160)
        # cycle = 160 + 200 = 360. 2 × 360 × 25 = 18000 ms. hold=1000.
        # max = 18000.
        assert result == 18000

    def test_scroll_through_hold_wins(self):
        widget = {
            "type": "two_row",
            "top_text": "TOP",
            "bottom_text": "HI",  # 10 px
            "font": "5x8",
            "bottom_text_scroll": "scroll_through",
            # No loops → defaults to 1.
        }
        result = two_row_visit_ms(widget, self._section(hold_time=20.0), canvas_w=160)
        # cycle = 160 + 10 = 170. 1 × 170 × 25 = 4250 ms. hold=20000.
        # max = 20000.
        assert result == 20000


class TestImageVisitMs:
    def test_no_text_uses_hold_seconds(self):
        widget = {"type": "image", "path": "x.png", "hold_seconds": 6.0}
        section = {"scroll_step_ms": 25}
        assert image_visit_ms(widget, section, canvas_w=160) == 6000

    def test_with_bottom_text_scroll_through(self):
        widget = {
            "type": "image",
            "path": "x.png",
            "hold_seconds": 8.0,
            "top_text": "TOP",
            "bottom_text": "HI",  # 10 px
            "bottom_text_scroll": "scroll_through",
        }
        section = {"scroll_step_ms": 25}
        # cycle = 160+10 = 170. 1 × 170 × 25 = 4250 ms. hold=8000ms.
        # max = 8000.
        assert image_visit_ms(widget, section, canvas_w=160) == 8000

    def test_image_default_hold_seconds_is_five(self):
        """Configs that omit hold_seconds default to 5.0 (matches StillImage)."""
        widget = {"type": "image", "path": "x.png"}
        section = {"scroll_step_ms": 25}
        assert image_visit_ms(widget, section, canvas_w=160) == 5000


class TestGifVisitMs:
    def test_unresolvable_path_uses_fallback(self):
        widget = {
            "type": "gif",
            "path": "/nonexistent/path.gif",
            "gif_loops": 3,
        }
        section = {"scroll_step_ms": 25}
        # Fallback: 100ms × n_frames assumed = 100 × 10 = 1000 per loop
        # × 3 loops = 3000. Implementation falls back to 100×10 estimate.
        result = gif_visit_ms(widget, section, canvas_w=160)
        assert result > 0
        # Emits a warning via the caller; visit just doesn't crash.

    def test_gif_loops_zero_uses_section_hold_time(self, tmp_path):
        # Create a real tiny gif so the path resolves.
        gif_path = tmp_path / "tiny.gif"
        frames = [
            PILImage.new("RGB", (8, 8), (255, 0, 0)),
            PILImage.new("RGB", (8, 8), (0, 255, 0)),
        ]
        frames[0].save(
            gif_path, save_all=True, append_images=frames[1:], duration=100, loop=0
        )
        widget = {
            "type": "gif",
            "path": str(gif_path),
            "gif_loops": 0,
        }
        # gif widget has NO hold_seconds field — engine reads section.hold_time
        # when gif_loops=0 (PR-64 behavior).
        section = {"scroll_step_ms": 25, "hold_time": 5.0}
        assert gif_visit_ms(widget, section, canvas_w=160) == 5000

    def test_gif_loops_positive_uses_frame_sum(self, tmp_path):
        gif_path = tmp_path / "tiny.gif"
        frames = [
            PILImage.new("RGB", (8, 8), (255, 0, 0)),
            PILImage.new("RGB", (8, 8), (0, 255, 0)),
        ]
        # 2 frames × 100ms each = 200ms per loop × 3 loops = 600ms.
        frames[0].save(
            gif_path, save_all=True, append_images=frames[1:], duration=100, loop=0
        )
        widget = {"type": "gif", "path": str(gif_path), "gif_loops": 3}
        section = {"scroll_step_ms": 25}
        assert gif_visit_ms(widget, section, canvas_w=160) == 600

    def test_gif_default_gif_loops_is_one(self, tmp_path):
        """Configs that omit gif_loops default to 1 (matches GifPlayer)."""
        gif_path = tmp_path / "tiny.gif"
        frames = [PILImage.new("RGB", (8, 8), (255, 0, 0))]
        frames[0].save(gif_path, save_all=True, duration=200, loop=0)
        widget = {"type": "gif", "path": str(gif_path)}  # no gif_loops
        section = {"scroll_step_ms": 25}
        # 1 frame × 200ms × 1 loop = 200.
        assert gif_visit_ms(widget, section, canvas_w=160) == 200
