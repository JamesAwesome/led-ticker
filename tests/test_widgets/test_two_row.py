"""Tests for the TwoRowMessage widget (held top, scrolling bottom)."""

from __future__ import annotations

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
            top_align="center",
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
        assert top_y < bottom_y, (
            f"top_y={top_y} should be less than bottom_y={bottom_y}"
        )
        assert top_y <= 8 and bottom_y >= 8, (
            f"Rows aren't split top/bottom: top_y={top_y} bottom_y={bottom_y}"
        )

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
        from rgbmatrix.graphics import Color

        from led_ticker.widgets import two_row as tr

        captured_providers: list = []

        def fake_draw_with_emoji(canvas, font, x, y, color, text, emoji_y=None, **kw):
            captured_providers.append(color)
            return 30

        monkeypatch.setattr(tr, "draw_with_emoji", fake_draw_with_emoji)

        top_c = Color(255, 0, 0)
        bot_c = Color(0, 0, 255)
        w = TwoRowMessage(
            top_text="A",
            bottom_text="B",
            top_color=top_c,
            bottom_color=bot_c,
        )
        w.draw(canvas)

        # TwoRowMessage now passes the provider directly to
        # draw_with_emoji (so per-char effects survive emoji boundaries).
        # The captured values are _ConstantColor wrappers; materialize
        # via color_for to recover the underlying Color.
        assert len(captured_providers) == 2
        top_color = captured_providers[0].color_for(0, 0, 1)
        bot_color = captured_providers[1].color_for(0, 0, 1)
        assert top_color.red == 255 and top_color.green == 0
        assert bot_color.red == 0 and bot_color.blue == 255


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

    def test_legacy_top_center_false_maps_to_left_with_warning(self):
        """Backwards-compat: top_center=False still maps to top_align='left',
        but emits a DeprecationWarning so the canonical knob surfaces."""
        with pytest.warns(DeprecationWarning, match="top_center"):
            w = TwoRowMessage(top_text="x", bottom_text="y", top_center=False)
        assert w.top_align == "left"

    def test_legacy_top_center_true_maps_to_center_with_warning(self):
        with pytest.warns(DeprecationWarning, match="top_center"):
            w = TwoRowMessage(top_text="x", bottom_text="y", top_center=True)
        assert w.top_align == "center"

    def test_top_center_overrides_top_align_with_warning(self):
        """`top_center` STILL silently wins over `top_align` if both are
        set (preserving prior behavior), but the deprecation warning
        makes the override visible. Catches the silent-override pitfall
        the post-merge review flagged."""
        with pytest.warns(DeprecationWarning, match="top_center"):
            w = TwoRowMessage(
                top_text="x",
                bottom_text="y",
                top_align="right",  # would be overridden
                top_center=True,
            )
        assert w.top_align == "center", "top_center=True still overrides"

    def test_top_center_none_emits_no_warning(self):
        """Default (no top_center) — no deprecation warning fires."""
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("error")  # any warning → error
            TwoRowMessage(top_text="x", bottom_text="y")  # should not raise


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

    def test_height_20_produces_no_gap(self, monkeypatch):
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
        # 20-tall canvas: each half is 10 rows. The emoji cap is raised to
        # max(8, 10) = 10 so row_layout centers a 10-row sprite in the
        # 10-row band: (10 - 10) // 2 = 0. The sprite anchors at the
        # band's top edge — no centering gap, rows touch exactly.
        assert top_emoji == 0  # top band: sprite anchors at band top (row 0)
        assert bot_emoji == 10  # bottom band: sprite anchors at band top (row 10)
        assert bot_emoji - (top_emoji + 10) == 0  # bands touch — no gap


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
        assert call_count == 2, (
            f"measure_width called {call_count}× over 20 frames — caching broken"
        )


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
        w = TwoRowMessage(top_text="@firebird", bottom_text="hi", font=font)
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

    # `test_bdf_font_still_accepted` and
    # `test_hires_baseline_centers_within_top_half` removed in the
    # consolidation pass: the first only checked construction
    # succeeds (covered by every other TwoRowMessage test that uses
    # BDF FONT_SMALL); the second overlapped with
    # `test_asymmetric_split_baselines_in_correct_bands` below.


class TestPerRowFonts:
    """`top_font` / `bottom_font` allow per-row font overrides; both
    default to None and fall back to `font`. Setting just one allows
    e.g. a bold handle on top + a thinner promo line below."""

    def test_top_font_falls_back_to_font_when_unset(self):
        from led_ticker.fonts import FONT_DEFAULT

        w = TwoRowMessage(top_text="hi", bottom_text="bye", font=FONT_DEFAULT)
        assert w._font_for_row(0) is FONT_DEFAULT
        assert w._font_for_row(1) is FONT_DEFAULT

    def test_top_font_overrides_font(self):
        from led_ticker.fonts import FONT_DEFAULT, FONT_LABEL

        w = TwoRowMessage(
            top_text="hi",
            bottom_text="bye",
            font=FONT_DEFAULT,
            top_font=FONT_LABEL,
        )
        assert w._font_for_row(0) is FONT_LABEL
        assert w._font_for_row(1) is FONT_DEFAULT

    def test_both_per_row_fonts_set(self):
        from led_ticker.fonts import FONT_LABEL, FONT_SMALL

        w = TwoRowMessage(
            top_text="hi",
            bottom_text="bye",
            top_font=FONT_LABEL,
            bottom_font=FONT_SMALL,
        )
        assert w._font_for_row(0) is FONT_LABEL
        assert w._font_for_row(1) is FONT_SMALL

    def test_per_row_hires_fonts(self):
        """Common case: bold hires on top, regular hires below — same
        family, different weight per row."""
        from led_ticker.fonts import resolve_font
        from led_ticker.fonts.hires_loader import HiresFont

        bold = resolve_font("Inter-Bold", 12)
        regular = resolve_font("Inter-Regular", 12)
        w = TwoRowMessage(
            top_text="HEADLINE",
            bottom_text="subtitle",
            top_font=bold,
            bottom_font=regular,
        )
        assert isinstance(w._font_for_row(0), HiresFont)
        assert w._font_for_row(0).name == "Inter-Bold"
        assert w._font_for_row(1).name == "Inter-Regular"

    def test_oversized_per_row_font_raises_at_draw(self, canvas):
        """Per-row fit guard runs against each row's font, not just
        `self.font`. If only the bottom_font is too tall, draw() raises
        and the message identifies which row."""
        import pytest

        from led_ticker.fonts import FONT_SMALL, resolve_font

        too_big = resolve_font("Inter-Regular", 40)  # ~46 logical line height
        w = TwoRowMessage(
            top_text="ok",
            bottom_text="too big",
            font=FONT_SMALL,
            bottom_font=too_big,
        )
        with pytest.raises(ValueError, match="bottom font"):
            w.draw(canvas)

    @pytest.mark.asyncio
    async def test_build_widget_resolves_per_row_font_kwargs(self):
        """End-to-end: TOML can name `top_font` / `bottom_font` (with
        their own _size and _threshold) and `_build_widget` resolves
        each into a font object before constructing the widget."""
        import unittest.mock as _mock

        from led_ticker.app import _build_widget
        from led_ticker.fonts.hires_loader import HiresFont

        cfg = {
            "type": "two_row",
            "top_text": "@firebird",
            "bottom_text": "follow us",
            "top_font": "Inter-Bold",
            "top_font_size": 16,
            "bottom_font": "Inter-Regular",
            "bottom_font_size": 12,
        }
        widget = await _build_widget(cfg, session=_mock.Mock())
        assert isinstance(widget.top_font, HiresFont)
        assert widget.top_font.name == "Inter-Bold"
        assert widget.top_font.size == 16
        assert isinstance(widget.bottom_font, HiresFont)
        assert widget.bottom_font.name == "Inter-Regular"
        assert widget.bottom_font.size == 12


class TestAsymmetricRowSplit:
    """`top_row_height` overrides the default 50/50 vertical split so the
    top can be a small tag and the bottom a larger marquee. Default
    `None` preserves the legacy split — existing tests above already
    pin that path, so this class only exercises the override behavior."""

    # `test_default_split_unchanged_when_top_row_height_is_none` removed
    # in the consolidation pass — it only checked attrs default
    # propagation, which is covered by the asymmetric tests below
    # (each uses `top_row_height=N` explicitly so the default path is
    # implicitly exercised by every legacy test elsewhere).

    def test_top_row_height_zero_raises_at_construction(self):
        import pytest

        with pytest.raises(ValueError, match="top_row_height"):
            TwoRowMessage(top_text="A", bottom_text="B", top_row_height=0)

    def test_top_row_height_negative_raises_at_construction(self):
        import pytest

        with pytest.raises(ValueError, match="top_row_height"):
            TwoRowMessage(top_text="A", bottom_text="B", top_row_height=-3)

    def test_top_row_height_full_canvas_raises_at_draw(self, canvas):
        """top_row_height >= canvas.height leaves no room for the
        bottom row — must raise at draw time (canvas isn't known at
        construction)."""
        import pytest

        # canvas fixture: height=16. top_row_height=16 is exactly the
        # canvas height — bottom would get 0 rows.
        w = TwoRowMessage(
            top_text="A", bottom_text="B", top_row_height=16, font=FONT_SMALL
        )
        with pytest.raises(ValueError, match="leaves no room"):
            w.draw(canvas)

    def test_text_y_offset_shifts_top_text(self, canvas, monkeypatch):
        """`top_text_y_offset` nudges the top text baseline. Independent
        of `top_emoji_y_offset` — set both to shift the whole row, or
        one for emoji-text vertical alignment tuning."""
        from led_ticker.widgets import two_row as tr

        captured_y: list[int] = []

        def fake(canvas, font, x, y, color, text, emoji_y=None, **kw):
            captured_y.append(y)
            return 30

        monkeypatch.setattr(tr, "draw_with_emoji", fake)

        # Reference: no offsets.
        w0 = TwoRowMessage(top_text="A", bottom_text="B", font=FONT_SMALL)
        w0.draw(canvas)
        ref_top_y, ref_bot_y = captured_y[:2]

        # Top text only down 2.
        captured_y.clear()
        w1 = TwoRowMessage(
            top_text="A", bottom_text="B", font=FONT_SMALL, top_text_y_offset=2
        )
        w1.draw(canvas)
        assert captured_y[0] == ref_top_y + 2
        assert captured_y[1] == ref_bot_y  # bottom unchanged

    def test_text_and_emoji_offsets_compose_to_shift_whole_row(
        self, canvas, monkeypatch
    ):
        """Setting both `top_text_y_offset` AND `top_emoji_y_offset` to
        the same value shifts the whole row together — text and emoji
        move in lockstep. (This is the documented "shift whole row"
        recipe in the docstring.)"""
        from led_ticker.widgets import two_row as tr

        captured: list[tuple[int, int | None]] = []

        def fake(canvas, font, x, y, color, text, emoji_y=None, **kw):
            captured.append((y, emoji_y))
            return 30

        monkeypatch.setattr(tr, "draw_with_emoji", fake)

        w0 = TwoRowMessage(top_text=":star: hi", bottom_text="b", font=FONT_SMALL)
        w0.draw(canvas)
        ref_text_y, ref_emoji_y = captured[0]

        captured.clear()
        w1 = TwoRowMessage(
            top_text=":star: hi",
            bottom_text="b",
            font=FONT_SMALL,
            top_text_y_offset=1,
            top_emoji_y_offset=1,
        )
        w1.draw(canvas)
        new_text_y, new_emoji_y = captured[0]
        assert new_text_y == ref_text_y + 1
        assert new_emoji_y == ref_emoji_y + 1

    def test_text_offset_alone_doesnt_move_emoji(self, canvas, monkeypatch):
        """True independence: setting `top_text_y_offset` ONLY moves
        the text — the emoji stays at its computed position. (The
        review caught the prior test was misnamed; it asserted
        composition, not independence.)"""
        from led_ticker.widgets import two_row as tr

        captured: list[tuple[int, int | None]] = []

        def fake(canvas, font, x, y, color, text, emoji_y=None, **kw):
            captured.append((y, emoji_y))
            return 30

        monkeypatch.setattr(tr, "draw_with_emoji", fake)

        # Reference baseline.
        w0 = TwoRowMessage(top_text=":star: hi", bottom_text="b", font=FONT_SMALL)
        w0.draw(canvas)
        ref_text_y, ref_emoji_y = captured[0]

        # Set ONLY text offset; emoji_y must NOT change.
        captured.clear()
        w1 = TwoRowMessage(
            top_text=":star: hi",
            bottom_text="b",
            font=FONT_SMALL,
            top_text_y_offset=2,
        )
        w1.draw(canvas)
        new_text_y, new_emoji_y = captured[0]
        assert new_text_y == ref_text_y + 2
        assert new_emoji_y == ref_emoji_y, (
            f"emoji_y moved when only text_y_offset was set: "
            f"ref={ref_emoji_y} now={new_emoji_y}"
        )

    def test_extreme_negative_text_y_offset_does_not_crash(self, canvas, monkeypatch):
        """A user can set `top_text_y_offset = -50` (way past the
        panel top) — the visible portion still renders, it doesn't
        crash. The panel renderer hard-clips negative coords; the
        widget just hands draw_with_emoji a negative y and lets the
        underlying renderer / panel boundary handle the clip.

        This is the documented contract ("negative shifts up; text
        ascender may clip the panel edge") — pin it.
        """
        from led_ticker.widgets import two_row as tr

        captured_y: list[int] = []

        def fake(canvas, font, x, y, color, text, emoji_y=None, **kw):
            captured_y.append(y)
            return 30

        monkeypatch.setattr(tr, "draw_with_emoji", fake)

        w = TwoRowMessage(
            top_text="A",
            bottom_text="B",
            font=FONT_SMALL,
            top_text_y_offset=-50,  # extreme negative
        )
        w.draw(canvas)  # must not raise
        # Top y must be the offset baseline, even when far negative.
        assert captured_y[0] < 0, (
            f"expected top_text_y to be negative, got {captured_y[0]}"
        )

    def test_emoji_offset_alone_doesnt_move_text(self, canvas, monkeypatch):
        """Mirror of `test_text_offset_alone_doesnt_move_emoji`: setting
        ONLY `top_emoji_y_offset` shifts the emoji without touching
        the text baseline."""
        from led_ticker.widgets import two_row as tr

        captured: list[tuple[int, int | None]] = []

        def fake(canvas, font, x, y, color, text, emoji_y=None, **kw):
            captured.append((y, emoji_y))
            return 30

        monkeypatch.setattr(tr, "draw_with_emoji", fake)

        w0 = TwoRowMessage(top_text=":star: hi", bottom_text="b", font=FONT_SMALL)
        w0.draw(canvas)
        ref_text_y, ref_emoji_y = captured[0]

        captured.clear()
        w1 = TwoRowMessage(
            top_text=":star: hi",
            bottom_text="b",
            font=FONT_SMALL,
            top_emoji_y_offset=2,
        )
        w1.draw(canvas)
        new_text_y, new_emoji_y = captured[0]
        assert new_emoji_y == ref_emoji_y + 2
        assert new_text_y == ref_text_y, (
            f"text_y moved when only emoji_y_offset was set: "
            f"ref={ref_text_y} now={new_text_y}"
        )

    def test_emoji_y_offset_shifts_top_emoji(self, canvas, monkeypatch):
        """`top_emoji_y_offset` nudges the top emoji vertically. Negative
        moves it up (toward text-center alignment when emoji is taller
        than band; may clip panel edge). Positive moves it down."""
        from led_ticker.widgets import two_row as tr

        captured: list[int | None] = []

        def fake(canvas, font, x, y, color, text, emoji_y=None, **kw):
            captured.append(emoji_y)
            return 30

        monkeypatch.setattr(tr, "draw_with_emoji", fake)

        # Baseline: emoji_y for top row with no offset.
        w0 = TwoRowMessage(
            top_text=":instagram: tag",
            bottom_text="b",
            font=FONT_SMALL,
        )
        w0.draw(canvas)
        baseline_top_emoji = captured[0]

        # With offset = -2, top emoji should be 2 logical rows higher.
        captured.clear()
        w1 = TwoRowMessage(
            top_text=":instagram: tag",
            bottom_text="b",
            font=FONT_SMALL,
            top_emoji_y_offset=-2,
        )
        w1.draw(canvas)
        assert captured[0] == baseline_top_emoji - 2

        # With offset = +3, 3 logical rows lower.
        captured.clear()
        w2 = TwoRowMessage(
            top_text=":instagram: tag",
            bottom_text="b",
            font=FONT_SMALL,
            top_emoji_y_offset=3,
        )
        w2.draw(canvas)
        assert captured[0] == baseline_top_emoji + 3

    def test_emoji_y_offset_shifts_bottom_emoji_independently(
        self, canvas, monkeypatch
    ):
        """`bottom_emoji_y_offset` doesn't affect the top row, and
        vice versa."""
        from led_ticker.widgets import two_row as tr

        captured: list[int | None] = []

        def fake(canvas, font, x, y, color, text, emoji_y=None, **kw):
            captured.append(emoji_y)
            return 30

        monkeypatch.setattr(tr, "draw_with_emoji", fake)

        # Reference: no offsets.
        w0 = TwoRowMessage(
            top_text=":star:",
            bottom_text=":heart:",
            font=FONT_SMALL,
        )
        w0.draw(canvas)
        ref_top, ref_bot = captured[:2]

        # Only bottom offset; top must stay put.
        captured.clear()
        w1 = TwoRowMessage(
            top_text=":star:",
            bottom_text=":heart:",
            font=FONT_SMALL,
            bottom_emoji_y_offset=-1,
        )
        w1.draw(canvas)
        top1, bot1 = captured[:2]
        assert top1 == ref_top
        assert bot1 == ref_bot - 1

    def test_emoji_y_clamped_to_band_top_for_small_bands(self):
        """Regression: with `band_height < _EMOJI_ROW_CAP = 8`, the
        centered formula produced negative `emoji_y` relative to the
        canvas, clipping the top of the sprite. Clamp to band_offset
        so the emoji top is at least the band's top edge.

        User-reported case: top_row_height=5 with `:instagram:` in
        top_text → emoji_y was -2, clipping ~8 real px at scale=4.
        """
        from types import SimpleNamespace

        from led_ticker.widgets.two_row import _row_layout

        c = SimpleNamespace(height=16, scale=4, width=64)
        # Top band 5 logical rows < 8 emoji cap.
        _, top_emoji_y = _row_layout(c, FONT_SMALL, band_height=5, band_offset=0)
        assert top_emoji_y >= 0, (
            f"emoji_y={top_emoji_y} clips above the canvas top — "
            "should be clamped to >= band_offset (0)"
        )
        # Bottom band 11 rows >= 8 cap → centered, no clamp needed.
        _, bot_emoji_y = _row_layout(c, FONT_SMALL, band_height=11, band_offset=5)
        # Bottom should be in band 5..15 (centered: 5 + (11-8)//2 = 6).
        assert 5 <= bot_emoji_y < 16

    def test_asymmetric_split_baselines_in_correct_bands(self):
        """top_row_height=4 on a 16-row canvas → top in rows 0..3,
        bottom in rows 4..15. Row baselines must land in their bands.
        """
        from types import SimpleNamespace

        from led_ticker.widgets.two_row import _row_layout

        c = SimpleNamespace(height=16, scale=1, width=160)
        # Top band: 4 rows starting at offset 0.
        top_baseline, top_emoji = _row_layout(
            c, FONT_SMALL, band_height=4, band_offset=0
        )
        # Bottom band: 12 rows starting at offset 4.
        bot_baseline, bot_emoji = _row_layout(
            c, FONT_SMALL, band_height=12, band_offset=4
        )
        # Top row's content stays within rows 0..3 (band_height=4 with
        # 5×8 BDF font is tight — line_height=8 > band — but _row_layout
        # itself doesn't enforce fit; that's draw()'s job. We're just
        # checking the math threads through correctly: baseline relative
        # to band offset.).
        assert top_baseline >= 0
        # Bottom row baseline must be in the bottom band (>= 4).
        assert bot_baseline >= 4
        # And they're in distinct bands.
        assert bot_baseline > top_baseline

    def test_asymmetric_split_works_end_to_end_through_draw(self, canvas, monkeypatch):
        """End-to-end through `draw()`: canvas.height=16, top_row_height=4,
        with FONT_SMALL on top (line_height=8 — too tall for 4-row band)
        should raise; switching top to a font that fits should succeed.
        Verifies the per-row fit-check uses the asymmetric heights.
        """
        import pytest

        from led_ticker.widgets import two_row as tr

        # Stub out actual drawing — we only care about the fit-check.
        monkeypatch.setattr(
            tr,
            "draw_with_emoji",
            lambda canvas, font, x, y, color, text, **kw: 30,
        )
        # Top: FONT_SMALL (line_height=8) in a 4-row band → too big.
        w = TwoRowMessage(
            top_text="A",
            bottom_text="B",
            font=FONT_SMALL,
            top_row_height=4,
        )
        with pytest.raises(ValueError, match="top font line-height.*4 rows"):
            w.draw(canvas)

    def test_asymmetric_bottom_band_takes_remainder(self, monkeypatch):
        """The bottom band's height is `canvas.height - top_row_height`
        — verify by configuring a bottom font that fits in 12 rows but
        NOT in 6, then run the same widget twice with different
        top_row_height values:

          top_row_height=4  → bottom_h=12 → bottom font fits → succeeds
          top_row_height=10 → bottom_h=6  → bottom font too tall → raises

        Pre-fix the test only exercised the top check; the bottom-band
        remainder math went untested.
        """
        import pytest
        from rgbmatrix import RGBMatrix, RGBMatrixOptions

        from led_ticker.fonts import resolve_font
        from led_ticker.scaled_canvas import ScaledCanvas
        from led_ticker.widgets import two_row as tr

        monkeypatch.setattr(
            tr,
            "draw_with_emoji",
            lambda canvas, font, x, y, color, text, **kw: 30,
        )

        # Bigsign-shape canvas: 256×64 real, wrapped at scale=4 with
        # content_height=16 → 16 logical rows, scale-aware fit-check.
        opts = RGBMatrixOptions()
        opts.cols = 64
        opts.rows = 32
        opts.chain_length = 8
        opts.parallel = 1
        opts.pixel_mapper_config = "U-mapper"
        real = RGBMatrix(options=opts).CreateFrameCanvas()
        canvas = ScaledCanvas(real, scale=4, content_height=16)

        # Inter @ 8: line_height ~10 real / scale=4 = 3 logical → fits
        # ANY band size we try here. Use as top font so the top check
        # never fails.
        top_font = resolve_font("Inter-Regular", 8)
        # Inter @ 28: line_height ~34 real / 4 = 9 logical → fits a
        # 12-row bottom band (top_row_height=4) but NOT a 6-row one
        # (top_row_height=10). Pivots on the bottom_h math.
        bottom_font = resolve_font("Inter-Regular", 28)

        # Case A: top_row_height=4 → bottom_h=12. Both rows fit → succeeds.
        w_pass = TwoRowMessage(
            top_text="A",
            bottom_text="B",
            top_font=top_font,
            bottom_font=bottom_font,
            top_row_height=4,
        )
        w_pass.draw(canvas)  # must not raise

        # Case B: top_row_height=10 → bottom_h=6. Bottom font too tall
        # (9 logical > 6 logical band). The error must name the bottom
        # row AND the actual band size (6), not the top row.
        w_fail = TwoRowMessage(
            top_text="A",
            bottom_text="B",
            top_font=top_font,
            bottom_font=bottom_font,
            top_row_height=10,
        )
        with pytest.raises(ValueError, match=r"bottom font line-height.*6 rows"):
            w_fail.draw(canvas)

    def test_asymmetric_bg_bands_use_split_divider(self, monkeypatch):
        """top_bg_color paints rows 0..top_row_height; bottom_bg_color
        paints top_row_height..canvas_height. Verify the divider tracks
        the asymmetric split, not the hardcoded canvas.height // 2.
        """
        from rgbmatrix import RGBMatrix, RGBMatrixOptions
        from rgbmatrix.graphics import Color

        from led_ticker.widgets import two_row as tr

        # 64×20 stub canvas — 20-tall lets us pick top_row_height=8
        # (asymmetric vs the default 10) with FONT_SMALL fitting both
        # bands (line_height=8 ≤ 8 ≤ 12).
        opts = RGBMatrixOptions()
        opts.cols = 64
        opts.rows = 20
        opts.chain_length = 1
        opts.parallel = 1
        c = RGBMatrix(options=opts).CreateFrameCanvas()

        # Stub out text rendering — we only care about the bg bands.
        monkeypatch.setattr(
            tr,
            "draw_with_emoji",
            lambda canvas, font, x, y, color, text, **kw: 0,
        )

        red = Color(255, 0, 0)
        blue = Color(0, 0, 255)
        w = TwoRowMessage(
            top_text="A",
            bottom_text="B",
            font=FONT_SMALL,
            top_bg_color=red,
            bottom_bg_color=blue,
            top_row_height=8,  # divider at row 8, NOT at 10 (50/50 default)
        )
        w.draw(c)

        # Rows 0..7 should be red.
        for y in range(0, 8):
            for x in range(c.width):
                assert c.get_pixel(x, y) == (255, 0, 0), f"({x},{y}) expected red"
        # Rows 8..19 should be blue.
        for y in range(8, c.height):
            for x in range(c.width):
                assert c.get_pixel(x, y) == (0, 0, 255), f"({x},{y}) expected blue"


class TestTwoRowColorProvider:
    def test_top_color_constant_wrapped_in_post_init(self):
        from rgbmatrix.graphics import Color

        from led_ticker.color_providers import _ConstantColor
        from led_ticker.widgets.two_row import TwoRowMessage

        w = TwoRowMessage(
            top_text="A",
            bottom_text="B",
            top_color=Color(255, 0, 0),
            bottom_color=Color(0, 255, 0),
        )
        assert isinstance(w.top_color, _ConstantColor)
        assert isinstance(w.bottom_color, _ConstantColor)

    def test_provider_passed_through(self):
        from led_ticker.color_providers import Rainbow
        from led_ticker.widgets.two_row import TwoRowMessage

        rainbow = Rainbow()
        w = TwoRowMessage(top_text="A", bottom_text="B", top_color=rainbow)
        assert w.top_color is rainbow

    def test_frame_aware_mixin(self):
        from led_ticker.widgets.two_row import TwoRowMessage

        w = TwoRowMessage(top_text="A", bottom_text="B")
        assert w._frame_count == 0
        w.advance_frame()
        assert w._frame_count == 1


def test_two_row_band_split_honors_content_height_at_scale_1():
    """Regression: _maybe_wrap at scale=1 returns the raw canvas unchanged,
    ignoring content_height. When the real panel is taller than the logical
    content_height (e.g. height=64 real, content_height=16), TwoRowMessage
    sees the full 64-row canvas and splits it 32/32 instead of 8/8.

    The fix: _maybe_wrap must wrap the canvas even at scale=1 when the raw
    canvas height != content_height, so TwoRowMessage always receives a canvas
    whose .height equals content_height.
    """
    import unittest.mock as m

    from led_ticker.ticker import _maybe_wrap
    from led_ticker.widgets._row_layout import resolve_band_heights

    # Simulate a real panel canvas taller than content_height (e.g. a 64px
    # panel running at scale=1 with a 16-row logical content window).
    raw = m.Mock()
    raw.width = 160
    raw.height = 64  # real panel is 64px tall

    canvas = _maybe_wrap(raw, scale=1, content_height=16)
    top_h, _ = resolve_band_heights(canvas.height, None)

    assert top_h == 8, (
        f"top_h={top_h}; expected 8 — _maybe_wrap at scale=1 ignored "
        "content_height=16, so TwoRowMessage split the raw 64-row canvas "
        "into 32/32 instead of 8/8."
    )


class TestRowLayout:
    def test_hires_sprite_anchors_within_full_band(self):
        """Original bug from PR #42: with top_row_height=16 at
        scale=2, the hi-res :instagram: sprite (16 logical tall)
        was placed at emoji_y=4 (centered for an 8-row sprite),
        extending to row 20 — bleeding into the bottom band.

        After the fix: row_layout receives the row's emoji_cap
        as `sprite_logical_height`, so the 16-row sprite anchors
        at emoji_y=0 within the 16-row band. No overlap.
        """
        from types import SimpleNamespace

        from led_ticker.widgets.two_row import _row_layout

        canvas = SimpleNamespace(height=24, scale=2, width=128)
        # Top band = 16 rows, cap = max(8, 16) = 16
        _, top_emoji_y = _row_layout(
            canvas,
            FONT_SMALL,
            band_height=16,
            band_offset=0,
            sprite_logical_height=16,
        )
        assert top_emoji_y == 0, (
            f"top_emoji_y={top_emoji_y}; expected 0 — a 16-row sprite "
            "in a 16-row band should anchor at the band's top edge so "
            "it doesn't bleed into the bottom band starting at row 16."
        )
