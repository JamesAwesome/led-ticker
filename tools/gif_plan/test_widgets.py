"""Tests for tools/gif_plan/widgets.py — per-widget math helpers."""

from __future__ import annotations

from PIL import Image as PILImage
from tools.gif_plan.widgets import (
    _single_row_floor_ticks,
    _single_row_scrolls,
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
        # text width = 165, canvas = 160 → scroll traverses 5 px overflow.
        widget = {
            "type": "message",
            # 33 chars × 5 = 165 px (overflows 160 canvas by 5 px).
            "text": "x" * 33,
            "font": "5x8",
        }
        section = {"hold_time": 2.0, "scroll_step_ms": 25}
        result = ticker_message_visit_ms(widget, section, canvas_w=160)
        # Engine `_swap_and_scroll` overflow branch: pre-scroll hold +
        # scroll + post-scroll hold. Scroll = (165 - 160) × 25 = 125 ms;
        # hold = 2000 ms each side. Total = 2000 + 125 + 2000 = 4125 ms.
        assert result == 4125

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
            "bottom_text": "x" * 40,  # 40 × 5 = 200 px (40 px overflow)
            "font": "5x8",
        }
        result = two_row_visit_ms(widget, self._section(), canvas_w=160)
        # Engine `_swap_and_scroll` overflow branch: pre-scroll hold +
        # scroll + post-scroll hold. Scroll = (200 - 160) × 25 = 1000 ms;
        # hold = 5000 ms each side. Total = 5000 + 1000 + 5000 = 11000 ms.
        assert result == 11000

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

    def test_scroll_through_hold_rounds_up_to_whole_cycles(self):
        widget = {
            "type": "two_row",
            "top_text": "TOP",
            "bottom_text": "HI",  # 10 px @ 5x8
            "font": "5x8",
            "bottom_text_scroll": "scroll_through",
            # No loops → loops_floor defaults to 1.
        }
        result = two_row_visit_ms(widget, self._section(hold_time=20.0), canvas_w=160)
        # Engine (`_swap_and_scroll`): cycle_width = 160 + 10 = 170;
        # hold_ticks = 20000 // 25 = 800; n_passes = max(1,
        # ceil(800/170)=5) = 5 — the hold is rounded UP to 5 whole
        # cycles, NOT left at the raw 20000. 5 × 170 × 25 = 21250.
        assert result == 21250


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
        # Image two-row overlay ticks on the WIDGET's scroll_speed_ms
        # (default 50), NOT the section's scroll_step_ms, and the bottom
        # row inherits the image FONT_DEFAULT (6x12): "HI" = 2×6 = 12 px.
        # cycle = 160+12 = 172. 1 × 172 × 50 = 8600 ms. hold=8000 ms.
        # max = 8600.
        assert image_visit_ms(widget, section, canvas_w=160) == 8600

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
        # Fallback: 100ms × 10 assumed frames = 1000 ms per loop
        # × 3 loops = 3000 ms (no text → no marquee floor).
        result = gif_visit_ms(widget, section, canvas_w=160)
        assert result == 3000

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


class TestSingleRowScrolls:
    """`_single_row_scrolls` resolves text_align=auto via image_align."""

    def test_no_text_does_not_scroll(self):
        assert _single_row_scrolls({"type": "image"}) is False

    def test_bottom_text_is_two_row_not_single_row(self):
        assert _single_row_scrolls({"text": "hi", "bottom_text": "x"}) is False

    def test_default_center_image_scrolls_via_auto(self):
        # text_align defaults to "auto"; image_align defaults to
        # "center" → AUTO resolves to "scroll_over" → scrolls.
        assert _single_row_scrolls({"text": "hi"}) is True

    def test_auto_left_image_does_not_scroll(self):
        # image_align="left" → AUTO → "right" (static), not a marquee.
        assert _single_row_scrolls({"text": "hi", "image_align": "left"}) is False

    def test_explicit_scroll_aligns_scroll(self):
        assert _single_row_scrolls({"text": "hi", "text_align": "scroll"}) is True

    def test_explicit_left_align_does_not_scroll(self):
        assert _single_row_scrolls({"text": "hi", "text_align": "left"}) is False


class TestSingleRowFloorTicks:
    """`_single_row_floor_ticks` mirrors `_play_with_text`'s marquee floor."""

    def test_non_wrap_is_canvas_plus_text_width(self):
        # "ABCDE" @ 5x8 = 25 px; non-wrap loop = canvas_w + text_w.
        w = {"text": "ABCDE", "font": "5x8"}
        assert _single_row_floor_ticks(w, canvas_w=160, scale=1) == 185

    def test_text_loops_multiplies_the_floor(self):
        w = {"text": "ABCDE", "font": "5x8", "text_loops": 3}
        assert _single_row_floor_ticks(w, canvas_w=160, scale=1) == 555

    def test_wrap_mode_is_text_plus_separator(self):
        # wrap loop = text_w (25) + sep_w (" * " @ 5x8 = 15) = 40.
        w = {
            "text": "ABCDE",
            "font": "5x8",
            "text_wrap": True,
            "text_separator": " * ",
        }
        assert _single_row_floor_ticks(w, canvas_w=160, scale=1) == 40


class TestGifTwoRowSourceDuration:
    """Regression: the gif two-row overlay must use the gif's
    sum(durations)×gif_loops as the n_ticks source — NOT the section
    hold_time. (`_image_base.py:1199-1200`.)"""

    def test_fits_uses_gif_duration_not_section_hold(self, tmp_path):
        gif_path = tmp_path / "g.gif"
        PILImage.new("RGB", (8, 8), (1, 2, 3)).save(
            gif_path, save_all=True, duration=100, loop=0
        )
        # 1 frame × 100ms × 50 loops = 5000 ms of gif playback.
        widget = {
            "type": "gif",
            "path": str(gif_path),
            "gif_loops": 50,
            "top_text": "TOP",
            "bottom_text": "HI",  # fits 160 → no marquee, held for source
        }
        section = {"scroll_step_ms": 25}  # NO hold_time → engine default 3.0
        # Must be the gif duration (5000), NOT _section_hold_ms (3000).
        assert gif_visit_ms(widget, section, canvas_w=160) == 5000

    def test_long_gif_source_floors_the_marquee(self, tmp_path):
        gif_path = tmp_path / "g.gif"
        PILImage.new("RGB", (8, 8), (1, 2, 3)).save(
            gif_path, save_all=True, duration=100, loop=0
        )
        # 100ms × 1000 loops = 100000 ms source. Bottom overflows so
        # the engine runs max(source_ticks, marquee). Marquee =
        # (160 + 40×6) × 50 = 20000; source 100000 dominates.
        widget = {
            "type": "gif",
            "path": str(gif_path),
            "gif_loops": 1000,
            "top_text": "TOP",
            "bottom_text": "x" * 40,  # 240 px @ FONT_DEFAULT 6x12
        }
        section = {}
        assert gif_visit_ms(widget, section, canvas_w=160) == 100000


class TestTwoRowOverlayLoopField:
    """The image/gif overlay loop floor is the widget's `text_loops`
    (`_image_base.py:1549,1555`); standalone TwoRowMessage uses
    `bottom_text_loops` (two_row.py)."""

    def test_overlay_applies_text_loops_multiplier(self):
        widget = {
            "type": "image",
            "path": "x.png",
            "top_text": "TOP",
            "bottom_text": "x" * 40,  # 240 px @ 6x12, overflows 160
            "text_loops": 3,
        }
        section = {"scroll_step_ms": 25}  # ignored — overlay uses 50
        # loops=max(1,3)=3; 3 × (160+240) × 50 = 60000; hold (default
        # hold_seconds 5.0) = 5000 → max = 60000.
        assert image_visit_ms(widget, section, canvas_w=160) == 60000

    def test_overlay_uses_text_loops_not_bottom_text_loops(self):
        widget = {
            "type": "image",
            "path": "x.png",
            "top_text": "TOP",
            "bottom_text": "x" * 40,
            "text_loops": 2,
            "bottom_text_loops": 99,  # standalone-only field; ignored here
        }
        section = {"scroll_step_ms": 25}
        # text_loops=2 wins: 2 × 400 × 50 = 40000 (not 99-based).
        assert image_visit_ms(widget, section, canvas_w=160) == 40000

    def test_standalone_uses_bottom_text_loops_not_text_loops(self):
        widget = {
            "type": "two_row",
            "top_text": "TOP",
            "bottom_text": "x" * 40,  # 200 px @ FONT_SMALL 5x8
            "font": "5x8",
            "bottom_text_scroll": "scroll_through",
            "bottom_text_loops": 2,
            "text_loops": 99,  # overlay-only field; ignored for standalone
        }
        section = {"hold_time": 1.0, "scroll_step_ms": 25}
        # bottom_text_loops=2 wins: 2 × (160+200) × 25 = 18000.
        assert two_row_visit_ms(widget, section, canvas_w=160) == 18000


class TestExplicitHoldTimeZero:
    """An explicit `hold_time = 0` is honoured, NOT coerced to the
    SectionConfig default of 3.0s."""

    def test_message_hold_time_zero(self):
        widget = {"type": "message", "text": "HI", "font": "5x8"}
        section = {"hold_time": 0, "scroll_step_ms": 25}
        # Fits, hold_time explicitly 0 → 0 ms (default would be 3000).
        assert ticker_message_visit_ms(widget, section, canvas_w=160) == 0


class TestSingleRowScrollingCaption:
    """image/gif with `text` and a resolved scroll alignment runs
    `_play_with_text`'s marquee floor at the WIDGET scroll_speed_ms."""

    def test_image_single_row_scroll_marquee_floor(self):
        widget = {
            "type": "image",
            "path": "x.png",
            "text": "A" * 10,  # 10 × 6 (FONT_DEFAULT) = 60 px
            # text_align defaults "auto"; image_align defaults "center"
            # → "scroll_over" → scrolls.
        }
        section = {"scroll_step_ms": 25}  # ignored — overlay uses 50
        # tick=50; source_ticks = max(1, 5000//50)=100 (hold_seconds
        # default 5.0). floor = max(1,0→1)×(160+60)=220. max → 220.
        # 220 × 50 = 11000.
        assert image_visit_ms(widget, section, canvas_w=160) == 11000

    def test_gif_single_row_scroll_marquee_floor(self, tmp_path):
        gif_path = tmp_path / "g.gif"
        PILImage.new("RGB", (8, 8), (1, 2, 3)).save(
            gif_path, save_all=True, duration=100, loop=0
        )
        widget = {
            "type": "gif",
            "path": str(gif_path),
            "gif_loops": 3,  # source = 300ms
            "text": "A" * 10,  # 60 px @ 6x12
        }
        section = {}
        # source_ticks = max(1, 300//50)=6; floor = (160+60)=220.
        # max(6,220) × 50 = 11000.
        assert gif_visit_ms(widget, section, canvas_w=160) == 11000

    def test_image_static_align_does_not_marquee(self):
        widget = {
            "type": "image",
            "path": "x.png",
            "text": "A" * 10,
            "text_align": "left",  # static — no marquee floor
            "hold_seconds": 4.0,
        }
        assert image_visit_ms(widget, {}, canvas_w=160) == 4000


class TestTwoRowOverlayWrap:
    """`include_pre_post_hold=False` + bottom_text_wrap: engine floors
    n_ticks to max(1, text_loops) × (bottom_w + sep_w)."""

    def test_image_overlay_wrap_applies_text_loops(self):
        widget = {
            "type": "image",
            "path": "x.png",
            "top_text": "TOP",
            "bottom_text": "AB",  # 12 px @ FONT_DEFAULT 6x12
            "bottom_text_wrap": True,
            "bottom_text_separator": " * ",  # 18 px @ 6x12
            "text_loops": 2,
            "hold_seconds": 1.0,  # source = 1000ms
        }
        section = {"scroll_step_ms": 25}  # ignored — overlay uses 50
        # cycle = (12+18)×50 = 1500; loops = max(1,2)=2 → 3000;
        # max(3000, source 1000) = 3000.
        assert image_visit_ms(widget, section, canvas_w=160) == 3000


class TestGifLoopsZeroWithBottomText:
    """gif_loops=0 + bottom_text: source = section hold_time, fed into
    the overlay max(marquee, source)."""

    def test_fits_uses_section_hold_as_source(self, tmp_path):
        gif_path = tmp_path / "g.gif"
        PILImage.new("RGB", (8, 8), (1, 2, 3)).save(
            gif_path, save_all=True, duration=100, loop=0
        )
        widget = {
            "type": "gif",
            "path": str(gif_path),
            "gif_loops": 0,
            "top_text": "TOP",
            "bottom_text": "HI",  # 12 px @ 6x12, fits → held for source
        }
        section = {"hold_time": 4.0}
        assert gif_visit_ms(widget, section, canvas_w=160) == 4000

    def test_overflow_marquee_floors_section_hold_source(self, tmp_path):
        gif_path = tmp_path / "g.gif"
        PILImage.new("RGB", (8, 8), (1, 2, 3)).save(
            gif_path, save_all=True, duration=100, loop=0
        )
        widget = {
            "type": "gif",
            "path": str(gif_path),
            "gif_loops": 0,
            "top_text": "TOP",
            "bottom_text": "x" * 40,  # 240 px @ 6x12 > 160
        }
        section = {"hold_time": 1.0}  # source = 1000ms
        # loops=max(1,0)=1; marquee = (160+240)×50 = 20000;
        # max(20000, source 1000) = 20000.
        assert gif_visit_ms(widget, section, canvas_w=160) == 20000


class TestHiresWidthScaleConversion:
    """Hi-res font width is real-pixel; ceil-divided by section scale to
    land on the logical-pixel basis (mirrors drawing.get_text_width)."""

    def test_hires_width_scale_one(self):
        # cell_w_real = ceil(20 × 0.55) = 11; 4 chars × 11 = 44.
        assert estimate_content_width_logical("ABCD", "Inter", 20, 1) == 44

    def test_hires_width_scale_four_ceil_divides(self):
        # 44 real px ÷ scale 4 → ceil(44/4) = 11 logical px.
        assert estimate_content_width_logical("ABCD", "Inter", 20, 4) == 11

    def test_single_row_floor_uses_scaled_width(self):
        w = {"text": "ABCD", "font": "Inter", "font_size": 20}
        # scale=4 → text_w 11 logical; non-wrap floor = 160 + 11 = 171.
        assert _single_row_floor_ticks(w, canvas_w=160, scale=4) == 171
