"""Tests for the TwoRowMessage widget (held top, scrolling bottom)."""

from __future__ import annotations

import unittest.mock as mock

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
