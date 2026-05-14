"""Tests for bottom_text_wrap on TwoRowMessage widget."""

from __future__ import annotations

import pytest

from led_ticker.widgets.two_row import TwoRowMessage


def _two_row(**kwargs):
    defaults = dict(top_text="TOP", bottom_text="bottom marquee")
    defaults.update(kwargs)
    return TwoRowMessage(**defaults)


class TestBottomTextWrapDefaults:
    def test_bottom_text_wrap_defaults_false(self):
        w = _two_row()
        assert w.bottom_text_wrap is False

    def test_bottom_text_separator_defaults_none(self):
        w = _two_row()
        assert w.bottom_text_separator is None

    def test_bottom_text_separator_color_defaults_none(self):
        w = _two_row()
        assert w.bottom_text_separator_color is None


class TestWrapsForeverProperty:
    """The cooperation contract with `_swap_and_scroll`. True only
    when bottom_text_wrap=True AND bottom_text is non-empty."""

    def test_wraps_forever_false_by_default(self):
        w = _two_row()
        assert w.wraps_forever is False

    def test_wraps_forever_true_when_wrap_enabled(self):
        w = _two_row(bottom_text_wrap=True)
        assert w.wraps_forever is True

    def test_wraps_forever_false_when_bottom_empty(self):
        """bottom_text='' is refused at validation, but defensively
        wraps_forever should be False if it slips through (e.g.,
        attribute set after construction)."""
        w = _two_row(bottom_text_wrap=True)
        w.bottom_text = ""
        assert w.wraps_forever is False


class TestBottomTextWrapValidation:
    def test_wrap_requires_non_empty_bottom_text(self):
        with pytest.raises(
            ValueError,
            match="bottom_text_wrap=True requires non-empty bottom_text",
        ):
            TwoRowMessage(top_text="TOP", bottom_text="", bottom_text_wrap=True)

    def test_separator_without_wrap_refused(self):
        with pytest.raises(
            ValueError, match="bottom_text_separator.*requires bottom_text_wrap"
        ):
            _two_row(bottom_text_separator=" * ")

    def test_separator_color_without_wrap_refused(self):
        with pytest.raises(
            ValueError,
            match="bottom_text_separator_color.*requires bottom_text_wrap",
        ):
            _two_row(bottom_text_separator_color=(255, 0, 0))

    def test_wrap_accepted_with_bottom_text(self):
        w = _two_row(bottom_text_wrap=True)
        assert w.bottom_text_wrap is True


class TestTwoRowWrapDrawRendersMultipleCopies:
    """draw() in wrap mode renders multiple copies of bottom_text
    in a single call. Engine drives cursor_pos; widget treats it
    modularly via `cursor_pos % cycle_width`."""

    def test_draw_renders_multiple_bottom_copies(self, mocker):
        """At cursor_pos=0, the widget should render >=2 copies of
        bottom_text on a 64px canvas with short bottom_text + separator."""
        from rgbmatrix import RGBMatrix, RGBMatrixOptions

        opts = RGBMatrixOptions()
        opts.cols = 64
        opts.rows = 32
        opts.chain_length = 1
        canvas = RGBMatrix(options=opts).CreateFrameCanvas()

        w = TwoRowMessage(
            top_text="TOP",
            bottom_text="Hi",
            bottom_text_wrap=True,
            bottom_text_separator=" * ",
        )

        import led_ticker.widgets.two_row as tr_mod

        draws: list[tuple[int, str]] = []
        real_draw = tr_mod.draw_text

        def _capture(c, font, x, y, color, text):
            draws.append((x, text))
            return real_draw(c, font, x, y, color, text)

        mocker.patch.object(tr_mod, "draw_text", side_effect=_capture)
        w.draw(canvas, cursor_pos=0)

        hi_xs = sorted(x for (x, t) in draws if t == "Hi")
        assert (
            len(hi_xs) >= 2
        ), f"Expected >=2 copies of 'Hi'; got {len(hi_xs)} at xs={hi_xs}"

    def test_draw_modulates_cursor_pos(self, mocker):
        """Calling draw() with cursor_pos=0 vs cursor_pos=-cycle_width
        must produce IDENTICAL x positions for the bottom-row copies.
        Verifies the modular `cursor_pos % cycle_width` semantics.

        A weaker version of this test only compared copy counts, which
        was tautological — n_copies depends only on canvas_w and
        cycle_width, not cursor_pos. A regression that pinned
        scroll_pos=0 regardless of cursor_pos would pass that check
        but break wrap. The identity-comparison form catches it."""
        from rgbmatrix import RGBMatrix, RGBMatrixOptions

        opts = RGBMatrixOptions()
        opts.cols = 64
        opts.rows = 32
        opts.chain_length = 1
        canvas = RGBMatrix(options=opts).CreateFrameCanvas()

        w = TwoRowMessage(
            top_text="TOP",
            bottom_text="Hi",
            bottom_text_wrap=True,
            bottom_text_separator=" * ",
        )

        import led_ticker.widgets.two_row as tr_mod

        # Capture the ORIGINAL draw_text once, before any patch, so both
        # captures pass through to the real function without chaining.
        # Otherwise sequential `mocker.patch.object` calls stack and the
        # second capturer's `real` points at the first mock — second
        # draw's calls bleed into the first capture list.
        original_draw_text = tr_mod.draw_text

        draws_a: list[tuple[int, str]] = []
        draws_b: list[tuple[int, str]] = []

        def make_capturer(target):
            def _capture(c, font, x, y, color, text):
                target.append((x, text))
                return original_draw_text(c, font, x, y, color, text)

            return _capture

        # First call learns cycle_width (returned as the stride).
        mocker.patch.object(tr_mod, "draw_text", side_effect=make_capturer(draws_a))
        _, cycle_width = w.draw(canvas, cursor_pos=0)
        assert cycle_width > 0, "Wrap mode must return a positive cycle_width"

        # Second call at cursor_pos = -cycle_width. Since
        # cursor_pos % cycle_width should be 0 again, the x positions
        # of bottom-text copies must be IDENTICAL to draws_a.
        mocker.patch.object(tr_mod, "draw_text", side_effect=make_capturer(draws_b))
        w.draw(canvas, cursor_pos=-cycle_width)

        hi_xs_a = sorted(x for (x, t) in draws_a if t == "Hi")
        hi_xs_b = sorted(x for (x, t) in draws_b if t == "Hi")
        assert hi_xs_a == hi_xs_b, (
            f"Modular wrap at cursor_pos=-{cycle_width} must yield "
            f"IDENTICAL x positions to cursor_pos=0; got "
            f"xs_a={hi_xs_a}, xs_b={hi_xs_b}"
        )

    def test_draw_top_row_held_during_wrap(self, mocker):
        """Top row stays at its top_align position regardless of
        cursor_pos. One draw per call."""
        from rgbmatrix import RGBMatrix, RGBMatrixOptions

        opts = RGBMatrixOptions()
        opts.cols = 64
        opts.rows = 32
        opts.chain_length = 1
        canvas = RGBMatrix(options=opts).CreateFrameCanvas()

        w = TwoRowMessage(
            top_text="TOP",
            top_align="left",
            bottom_text="Hi",
            bottom_text_wrap=True,
            bottom_text_separator=" * ",
        )

        import led_ticker.widgets.two_row as tr_mod

        draws: list[tuple[int, str]] = []
        real_draw = tr_mod.draw_text

        def _capture(c, font, x, y, color, text):
            draws.append((x, text))
            return real_draw(c, font, x, y, color, text)

        mocker.patch.object(tr_mod, "draw_text", side_effect=_capture)
        w.draw(canvas, cursor_pos=0)

        top_xs = [x for (x, t) in draws if t == "TOP"]
        assert len(top_xs) == 1, f"Top row should draw exactly once; got xs={top_xs}"


class TestBottomTextLoops:
    """Tests for the bottom_text_loops field."""

    def test_bottom_text_loops_defaults_to_zero(self):
        """bottom_text_loops should default to 0."""
        w = _two_row()
        assert w.bottom_text_loops == 0

    def test_bottom_text_loops_with_wrap_constructs_cleanly(self):
        """bottom_text_loops > 0 is accepted when bottom_text_wrap=True."""
        w = _two_row(bottom_text_wrap=True, bottom_text_loops=2)
        assert w.bottom_text_loops == 2
        assert w.bottom_text_wrap is True

    def test_bottom_text_loops_without_wrap_or_scroll_through_raises(self):
        """bottom_text_loops > 0 requires either bottom_text_wrap=True
        (seamless tile) OR bottom_text_scroll='scroll_through' (repeat
        the offscreen pass N times). Both compose; the rejection still
        fires when neither is set."""
        with pytest.raises(
            ValueError,
            match=r"bottom_text_loops=.*requires.*(bottom_text_wrap|scroll_through)",
        ):
            _two_row(bottom_text_loops=1)

    def test_bottom_text_loops_negative_raises(self):
        """bottom_text_loops < 0 raises."""
        with pytest.raises(ValueError, match="bottom_text_loops must be >= 0"):
            _two_row(bottom_text_loops=-1)

    def test_bottom_text_loops_bool_raises(self):
        """bool is an int subclass in Python — without an explicit guard,
        `bottom_text_loops = true` would silently behave as loops=1. The
        post-init check rejects bool to surface the mistake."""
        with pytest.raises(ValueError, match="must be an integer"):
            _two_row(
                bottom_text_loops=True,  # type: ignore[arg-type]
                bottom_text_wrap=True,
            )
