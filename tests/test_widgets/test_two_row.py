"""Tests for the TwoRowMessage widget (held top, scrolling bottom)."""

from __future__ import annotations

import unittest.mock as mock

import pytest

from led_ticker.fonts import FONT_SMALL
from led_ticker.widget import Widget
from led_ticker.widgets import get_widget_class
from led_ticker.widgets.two_row import TwoRowMessage


class TestRegistration:
    def test_registered_as_two_row(self):
        assert get_widget_class("two_row") is TwoRowMessage

    def test_conforms_to_widget_protocol(self):
        w = TwoRowMessage(top_text="A", bottom_text="B")
        assert isinstance(w, Widget)


class TestDraw:
    def test_returns_canvas_and_cursor(self, canvas):
        w = TwoRowMessage(
            top_text="@brand",
            bottom_text="hello world this is a long message",
            font=FONT_SMALL,
        )
        result, cursor = w.draw(canvas)
        assert result is canvas
        assert cursor > 0

    def test_top_text_drawn_at_fixed_position_regardless_of_cursor(
        self, canvas, monkeypatch
    ):
        """Regression: as cursor_pos decreases (bottom row scrolls left),
        the top row's draw call must use the SAME x position every frame
        — that's the "held" contract.
        """
        from led_ticker.widgets import two_row as tr

        captured: list[tuple[int, int]] = []

        def fake_draw_with_emoji(canvas, font, x, y, color, text, emoji_y=None, **kw):
            captured.append((x, y))
            return 50  # advance width — value doesn't matter for this test

        monkeypatch.setattr(tr, "draw_with_emoji", fake_draw_with_emoji)

        w = TwoRowMessage(
            top_text="HELD",
            bottom_text="this scrolls",
            font=FONT_SMALL,
            top_center=True,
            bottom_align="left",  # pin so the cursor-tracks-pos test isn't
            # confounded by centering when the text happens to fit.
        )

        # Frame 1: bottom at pos=0
        w.draw(canvas, cursor_pos=0)
        # Frame 2: bottom at pos=-50 (scrolled left)
        w.draw(canvas, cursor_pos=-50)
        # Frame 3: bottom at pos=-100
        w.draw(canvas, cursor_pos=-100)

        # Pull out the top-row x positions (every odd-index call is bottom).
        # Each draw() makes 2 calls: top, then bottom. The TOP x must be
        # identical across frames; the BOTTOM x should match cursor_pos.
        top_xs = [captured[i][0] for i in range(0, len(captured), 2)]
        bottom_xs = [captured[i][0] for i in range(1, len(captured), 2)]

        assert len(set(top_xs)) == 1, (
            f"top_x changed across frames: {top_xs}. The held top row "
            "should not move when the bottom row scrolls."
        )
        assert bottom_xs == [
            0,
            -50,
            -100,
        ], f"bottom_x didn't track cursor_pos: {bottom_xs}"

    def test_top_and_bottom_use_different_baselines(self, canvas, monkeypatch):
        """Top row's text should render in the top half (low y), bottom row
        in the bottom half (high y). Catches a regression where both rows
        accidentally render at the same y baseline.
        """
        from led_ticker.widgets import two_row as tr

        captured_y: list[int] = []

        def fake_draw_with_emoji(canvas, font, x, y, color, text, emoji_y=None, **kw):
            captured_y.append(y)
            return 30

        monkeypatch.setattr(tr, "draw_with_emoji", fake_draw_with_emoji)

        w = TwoRowMessage(top_text="T", bottom_text="B", font=FONT_SMALL)
        w.draw(canvas, cursor_pos=0)

        # Two calls per draw (top then bottom). Top y < bottom y.
        assert len(captured_y) == 2
        top_y, bottom_y = captured_y
        assert (
            top_y < bottom_y
        ), f"top_y={top_y} should be less than bottom_y={bottom_y}"
        assert (
            top_y <= 8 and bottom_y >= 8
        ), f"Rows aren't split top/bottom: top_y={top_y} bottom_y={bottom_y}"

    def test_emoji_y_passed_per_row(self, canvas, monkeypatch):
        """Top emoji should sit in rows 0-7; bottom emoji in rows 8-15."""
        from led_ticker.widgets import two_row as tr

        captured: list[int | None] = []

        def fake_draw_with_emoji(canvas, font, x, y, color, text, emoji_y=None, **kw):
            captured.append(emoji_y)
            return 30

        monkeypatch.setattr(tr, "draw_with_emoji", fake_draw_with_emoji)

        w = TwoRowMessage(top_text=":instagram: a", bottom_text=":email: b")
        w.draw(canvas)

        # Each row passes emoji_y; not None
        assert captured[0] is not None
        assert captured[1] is not None
        assert captured[0] < captured[1]

    def test_returned_cursor_reflects_bottom_width_only(self, canvas):
        """`_swap_and_scroll` keys off the returned cursor to decide whether
        to scroll. For two_row, that should be the BOTTOM row's right edge
        (the held top row doesn't drive scroll behavior).
        """
        # Bottom is much longer than top — cursor should reflect bottom.
        w = TwoRowMessage(
            top_text="X",
            bottom_text="this is a very long bottom row that overflows",
            font=FONT_SMALL,
        )
        _, cursor = w.draw(canvas, cursor_pos=0)
        # 45 chars * 5 px = 225 + 6 padding = 231. canvas.width = 160.
        assert cursor > canvas.width

    def test_padding_added_to_returned_cursor(self, canvas):
        w = TwoRowMessage(
            top_text="x",
            bottom_text="ab",  # 2 chars * 5 px = 10
            font=FONT_SMALL,
            padding=20,
        )
        _, cursor = w.draw(canvas, cursor_pos=0)
        # bottom_width (10) + padding (20) = 30
        assert cursor == 30


class TestColors:
    def test_top_and_bottom_colors_independent(self, canvas, monkeypatch):
        from led_ticker.widgets import two_row as tr

        captured_colors: list = []

        def fake_draw_with_emoji(canvas, font, x, y, color, text, emoji_y=None, **kw):
            captured_colors.append(color)
            return 30

        monkeypatch.setattr(tr, "draw_with_emoji", fake_draw_with_emoji)

        top_c = mock.Mock(name="top_color")
        bot_c = mock.Mock(name="bot_color")
        w = TwoRowMessage(
            top_text="A",
            bottom_text="B",
            top_color=top_c,
            bottom_color=bot_c,
        )
        w.draw(canvas)

        assert captured_colors == [top_c, bot_c]


class TestAlignment:
    def test_top_align_left(self, canvas, monkeypatch):
        from led_ticker.widgets import two_row as tr

        captured_xs: list[int] = []

        def fake(canvas, font, x, y, color, text, emoji_y=None, **kw):
            captured_xs.append(x)
            return 50

        monkeypatch.setattr(tr, "draw_with_emoji", fake)
        w = TwoRowMessage(top_text="hi", bottom_text="x", top_align="left")
        w.draw(canvas, cursor_pos=0)
        assert captured_xs[0] == 0  # top row at left edge

    def test_top_align_right(self, canvas, monkeypatch):
        from led_ticker.widgets import two_row as tr

        captured_xs: list[int] = []

        def fake(canvas, font, x, y, color, text, emoji_y=None, **kw):
            captured_xs.append(x)
            return 50

        monkeypatch.setattr(tr, "draw_with_emoji", fake)
        w = TwoRowMessage(top_text="hi", bottom_text="x", top_align="right")
        w.draw(canvas, cursor_pos=0)
        # top_width is real measure_width("hi"), but the test stub canvas
        # is 160 wide. Right-aligned x should be canvas.width - top_width.
        assert captured_xs[0] > 100

    def test_top_align_center_explicit(self, canvas, monkeypatch):
        from led_ticker.widgets import two_row as tr

        captured_xs: list[int] = []

        def fake(canvas, font, x, y, color, text, emoji_y=None, **kw):
            captured_xs.append(x)
            return 50

        monkeypatch.setattr(tr, "draw_with_emoji", fake)
        w = TwoRowMessage(top_text="hi", bottom_text="x", top_align="center")
        w.draw(canvas, cursor_pos=0)
        # Centered: x > 0 but < right_edge_x
        assert 0 < captured_xs[0] < canvas.width

    def test_legacy_top_center_false_maps_to_left(self):
        # Backwards-compat: top_center=False from old configs still works.
        w = TwoRowMessage(top_text="x", bottom_text="y", top_center=False)
        assert w.top_align == "left"

    def test_legacy_top_center_true_maps_to_center(self):
        w = TwoRowMessage(top_text="x", bottom_text="y", top_center=True)
        assert w.top_align == "center"


class TestRowSpacing:
    def test_height_16_no_gap_between_rows(self, monkeypatch):
        # 16-tall canvas: rows are immediately adjacent (legacy behavior).
        import unittest.mock as m

        canvas = m.Mock()
        canvas.width = 160
        canvas.height = 16

        from led_ticker.widgets import two_row as tr

        captured: list[tuple[int, int]] = []

        def fake(canvas, font, x, y, color, text, emoji_y=None, **kw):
            captured.append((y, emoji_y))
            return 30

        monkeypatch.setattr(tr, "draw_with_emoji", fake)
        w = TwoRowMessage(top_text="A", bottom_text="B")
        w.draw(canvas)
        (top_baseline, top_emoji), (bot_baseline, bot_emoji) = captured
        # Top row uses rows 0-7, bottom uses rows 8-15. No gap.
        assert top_emoji == 0
        assert bot_emoji == 8
        assert bot_emoji - (top_emoji + 8) == 0  # rows touch

    def test_height_20_produces_gap(self, monkeypatch):
        import unittest.mock as m

        canvas = m.Mock()
        canvas.width = 160
        canvas.height = 20  # taller logical canvas with breathing room

        from led_ticker.widgets import two_row as tr

        captured: list[tuple[int, int]] = []

        def fake(canvas, font, x, y, color, text, emoji_y=None, **kw):
            captured.append((y, emoji_y))
            return 30

        monkeypatch.setattr(tr, "draw_with_emoji", fake)
        w = TwoRowMessage(top_text="A", bottom_text="B")
        w.draw(canvas)
        (_, top_emoji), (_, bot_emoji) = captured
        # 20-tall canvas: each half is 10 rows. 8-tall glyph centered in
        # each half gives 1 row above + 1 row below per half. Gap between
        # rows = (top half bottom margin) + (bottom half top margin) = 2.
        assert top_emoji == 1  # 1 row of top margin
        assert bot_emoji == 11  # half (10) + 1 row
        assert bot_emoji - (top_emoji + 8) == 2  # 2-row gap between glyphs


class TestTwoRowBgColor:
    @pytest.fixture
    def bg_canvas(self):
        """Pixel-tracking stub canvas for bg-band assertions."""
        from rgbmatrix import RGBMatrix, RGBMatrixOptions

        opts = RGBMatrixOptions()
        opts.cols = 160
        opts.rows = 16
        opts.chain_length = 1
        opts.parallel = 1
        return RGBMatrix(options=opts).CreateFrameCanvas()

    def test_default_bg_fields_are_none(self):
        w = TwoRowMessage(top_text="A", bottom_text="B")
        assert w.bg_color is None
        assert w.top_bg_color is None
        assert w.bottom_bg_color is None

    def test_top_bg_color_paints_only_top_band(self, bg_canvas):
        """top_bg_color fills rows 0..(h//2) with the bg color; rows
        h//2..h are not filled by the band painter (orchestrator may
        Clear them)."""
        from rgbmatrix.graphics import Color

        bg = Color(255, 0, 128)
        w = TwoRowMessage(
            top_text="",  # empty so we only see the bg paint
            bottom_text="",
            top_bg_color=bg,
        )
        # canvas fixture is 160x16 (small sign default). Half = 8.
        bg_canvas.Clear()
        w.draw(bg_canvas, cursor_pos=0)
        h = bg_canvas.height
        mid = h // 2
        # Top band (rows 0..mid-1) should be magenta.
        for y in range(0, mid):
            for x in range(bg_canvas.width):
                assert bg_canvas.get_pixel(x, y) == (255, 0, 128), (
                    f"top band: row {y} should be magenta, "
                    f"got {bg_canvas.get_pixel(x, y)}"
                )
        # Bottom band (rows mid..h-1) should be untouched (black).
        for y in range(mid, h):
            for x in range(bg_canvas.width):
                assert bg_canvas.get_pixel(x, y) == (0, 0, 0), (
                    f"bottom band: row {y} should be unset, "
                    f"got {bg_canvas.get_pixel(x, y)}"
                )

    def test_bottom_bg_color_paints_only_bottom_band(self, bg_canvas):
        from rgbmatrix.graphics import Color

        bg = Color(20, 200, 50)
        w = TwoRowMessage(top_text="", bottom_text="", bottom_bg_color=bg)
        bg_canvas.Clear()
        w.draw(bg_canvas, cursor_pos=0)
        h = bg_canvas.height
        mid = h // 2
        for y in range(0, mid):
            for x in range(bg_canvas.width):
                assert bg_canvas.get_pixel(x, y) == (0, 0, 0)
        for y in range(mid, h):
            for x in range(bg_canvas.width):
                assert bg_canvas.get_pixel(x, y) == (20, 200, 50)

    def test_both_bands_paint_independently(self, bg_canvas):
        from rgbmatrix.graphics import Color

        top_bg = Color(255, 0, 0)
        bottom_bg = Color(0, 0, 255)
        w = TwoRowMessage(
            top_text="",
            bottom_text="",
            top_bg_color=top_bg,
            bottom_bg_color=bottom_bg,
        )
        bg_canvas.Clear()
        w.draw(bg_canvas, cursor_pos=0)
        h = bg_canvas.height
        mid = h // 2
        # spot-check center of each band
        assert bg_canvas.get_pixel(bg_canvas.width // 2, mid // 2) == (255, 0, 0)
        assert bg_canvas.get_pixel(bg_canvas.width // 2, mid + (h - mid) // 2) == (
            0,
            0,
            255,
        )

    def test_per_row_bg_overrides_widget_bg_visually(self, bg_canvas):
        """The widget's own `bg_color` is applied by the orchestrator
        (canvas already filled when draw() runs). Per-row bands paint
        on top — verify they win on their respective half."""
        from rgbmatrix.graphics import Color

        from led_ticker.widgets._image_fit import reset_canvas

        widget_bg = Color(50, 50, 50)
        top_bg = Color(255, 0, 0)
        w = TwoRowMessage(
            top_text="",
            bottom_text="",
            bg_color=widget_bg,
            top_bg_color=top_bg,
        )

        # Simulate orchestrator: reset_canvas with widget.bg_color, then draw.
        reset_canvas(bg_canvas, w.bg_color)
        w.draw(bg_canvas, cursor_pos=0)

        h = bg_canvas.height
        mid = h // 2
        # Top band: top_bg wins.
        assert bg_canvas.get_pixel(0, 0) == (255, 0, 0)
        # Bottom band: widget_bg shows through (no bottom_bg_color).
        assert bg_canvas.get_pixel(0, mid) == (50, 50, 50)


class TestWidthCaching:
    def test_width_computed_once(self, canvas, monkeypatch):
        # measure_width hits the font's CharacterWidth (a C call on real
        # hardware). For static text the width never changes — cache it.
        from led_ticker.widgets import two_row as tr

        call_count = 0
        real_measure = tr.measure_width

        def counting_measure(font, text, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            return real_measure(font, text, *args, **kwargs)

        monkeypatch.setattr(tr, "measure_width", counting_measure)

        w = TwoRowMessage(top_text="aaa", bottom_text="bbb", font=FONT_SMALL)
        for _ in range(20):
            w.draw(canvas, cursor_pos=0)

        # 2 calls total: one for top width, one for bottom width. Cached
        # for every subsequent frame.
        assert (
            call_count == 2
        ), f"measure_width called {call_count}× over 20 frames — caching broken"


class TestHiresFontSupport:
    """TwoRowMessage now supports hi-res fonts via `compute_baseline` on
    a half-canvas. Both rows derive their baseline + emoji_y from the
    font's metrics so any (font, font_size) combo that fits within a
    half-canvas works.
    """

    def test_hires_font_accepted_at_construction(self):
        """Constructor no longer rejects hi-res fonts — the row layout
        is font-aware now."""
        from led_ticker.fonts import resolve_font
        from led_ticker.fonts.hires_loader import HiresFont

        font = resolve_font("Inter-Regular", 24)
        assert isinstance(font, HiresFont)
        w = TwoRowMessage(top_text="@MoonBunny", bottom_text="hi", font=font)
        assert w.font is font

    def test_hires_font_too_large_raises_at_draw(self, canvas):
        """When the font's logical line-height exceeds half the canvas,
        draw() raises with a clear message pointing at the fix.
        Inter@40 line_height ~46 real → 12 logical at scale=4. Half of
        a 16-row canvas is 8 logical rows — doesn't fit.
        """
        import pytest

        from led_ticker.fonts import resolve_font

        font = resolve_font("Inter-Regular", 40)
        w = TwoRowMessage(top_text="hi", bottom_text="bye", font=font)
        # canvas fixture: width=160, height=16, .scale=Mock()
        # compute_baseline tolerates non-int scale (treats as 1), so
        # font_lh_logical for Inter@40 is the full ~46 logical px on
        # this canvas. Half=8, doesn't fit.
        with pytest.raises(ValueError, match="line-height"):
            w.draw(canvas)

    def test_bdf_font_still_accepted(self):
        from led_ticker.fonts import FONT_DEFAULT

        # 6×12 is BDF; widget accepts it. On the standard 16-row canvas
        # half=8, font_lh=12 — would raise at draw() because 12 > 8.
        # FONT_SMALL (5×8) is the canonical pairing.
        w = TwoRowMessage(top_text="hi", bottom_text="bye", font=FONT_DEFAULT)
        assert w.font is FONT_DEFAULT

    def test_hires_baseline_centers_within_top_half(self):
        """The hires top-row baseline lands inside the top half of the
        canvas (so the glyph doesn't cross the row divider). Pin the
        bound rather than the exact value to tolerate metric variance.
        """
        from types import SimpleNamespace

        from led_ticker.fonts import resolve_font
        from led_ticker.widgets.two_row import _row_layout

        font = resolve_font("Inter-Regular", 16)
        # Bigsign-shape canvas: 20 logical rows at scale=4.
        c = SimpleNamespace(height=20, scale=4, width=64)
        top_baseline, _ = _row_layout(c, font, row_index=0)
        bottom_baseline, _ = _row_layout(c, font, row_index=1)
        # Top baseline must sit in rows 0..9 (top half = 10 rows).
        assert 0 < top_baseline < 10, top_baseline
        # Bottom baseline must sit in the bottom half (rows 10..19).
        assert 10 <= bottom_baseline < 20, bottom_baseline
        # And the bottom baseline = top + half (consistent split).
        assert bottom_baseline - top_baseline == 10
