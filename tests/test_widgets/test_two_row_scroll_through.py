"""Tests for bottom_text_scroll on TwoRowMessage widget.

The bottom_text_scroll field is an enum that picks the bottom row's
scroll style when its content overflows (or — for "scroll_through" —
even when it doesn't):

  "marquee"        Default. Current behavior: held at bottom_align
                   when text fits; cursor-driven single-pass scroll
                   when it overflows; or seamless tile when paired
                   with bottom_text_wrap=True.

  "scroll_through" New. Always scroll, regardless of overflow. Text
                   starts fully off the right edge (bottom_x =
                   canvas.width) and ends fully off the left edge
                   (bottom_x + bottom_width < 0). One pass per visit.
                   bottom_align is ignored. Mutually exclusive with
                   bottom_text_wrap=True.
"""

from __future__ import annotations

import pytest

from led_ticker.widgets.two_row import TwoRowMessage


def _two_row(**kwargs):
    defaults = dict(top_text="TOP", bottom_text="bottom scrolling")
    defaults.update(kwargs)
    return TwoRowMessage(**defaults)


class TestBottomTextScrollDefaults:
    def test_field_defaults_to_marquee(self):
        w = _two_row()
        assert w.bottom_text_scroll == "marquee"

    def test_marquee_explicit_accepted(self):
        w = _two_row(bottom_text_scroll="marquee")
        assert w.bottom_text_scroll == "marquee"

    def test_scroll_through_accepted(self):
        w = _two_row(bottom_text_scroll="scroll_through")
        assert w.bottom_text_scroll == "scroll_through"


class TestBottomTextScrollValidation:
    def test_unknown_value_raises_with_valid_options_listed(self):
        with pytest.raises(ValueError, match="bottom_text_scroll") as exc_info:
            _two_row(bottom_text_scroll="bogus")
        # Error message should list both valid options so the user
        # doesn't have to read the source to find them.
        msg = str(exc_info.value)
        assert "marquee" in msg
        assert "scroll_through" in msg
        assert "bogus" in msg

    def test_scroll_through_with_wrap_true_refused(self):
        """Mutex rule: bottom_text_wrap=True is the seamless tiled
        marquee; bottom_text_scroll='scroll_through' is the
        offscreen-to-offscreen single pass. Pick one."""
        with pytest.raises(
            ValueError,
            match=r"bottom_text_scroll=.scroll_through.*bottom_text_wrap=True",
        ):
            _two_row(
                bottom_text_scroll="scroll_through",
                bottom_text_wrap=True,
            )

    def test_scroll_through_with_empty_bottom_text_refused(self):
        """Nothing to scroll through — same defensive guard as
        bottom_text_wrap=True with empty bottom_text."""
        with pytest.raises(
            ValueError,
            match=r"bottom_text_scroll=.scroll_through.*non-empty bottom_text",
        ):
            TwoRowMessage(
                top_text="TOP",
                bottom_text="",
                bottom_text_scroll="scroll_through",
            )

    def test_marquee_with_wrap_true_still_accepted(self):
        """The default value of bottom_text_scroll must not break
        existing configs that set bottom_text_wrap=True."""
        w = _two_row(
            bottom_text_scroll="marquee",
            bottom_text_wrap=True,
            bottom_text_separator=" * ",
        )
        assert w.bottom_text_scroll == "marquee"
        assert w.bottom_text_wrap is True

    def test_loops_with_scroll_through_gets_direct_error(self):
        """Combined: bottom_text_loops>0 + bottom_text_scroll=scroll_through
        must give an error that mentions scroll_through, not bounce the
        user through 'requires wrap=True' → 'wrap mutex with scroll_through'."""
        with pytest.raises(ValueError) as exc_info:
            _two_row(
                bottom_text_loops=3,
                bottom_text_scroll="scroll_through",
            )
        msg = str(exc_info.value)
        # Error must mention both fields so user sees the actual conflict
        # rather than being led to add bottom_text_wrap=True (which would
        # then fail the scroll_through mutex).
        assert "bottom_text_loops" in msg, (
            f"Combined-error message should mention bottom_text_loops; " f"got: {msg!r}"
        )
        assert "scroll_through" in msg, (
            f"Combined-error message should mention scroll_through "
            f"(not just bounce user through wrap-requirement chain); "
            f"got: {msg!r}"
        )


class TestForcesOffscreenScrollProperty:
    """Engine cooperation signal — parallel to `wraps_forever`. True only
    when bottom_text_scroll='scroll_through' AND bottom_text is non-empty.
    `_swap_and_scroll` uses this to pick the dedicated scroll-through
    branch (no pre/post holds, decrement pos until fully offscreen left)."""

    def test_false_by_default(self):
        w = _two_row()
        assert w.forces_offscreen_scroll is False

    def test_true_when_scroll_through_set(self):
        w = _two_row(bottom_text_scroll="scroll_through")
        assert w.forces_offscreen_scroll is True

    def test_false_when_bottom_empty_post_construction(self):
        """Defensive: if bottom_text is mutated to '' after construction
        (validation would normally reject this), forces_offscreen_scroll
        should still report False so the engine doesn't spin forever."""
        w = _two_row(bottom_text_scroll="scroll_through")
        w.bottom_text = ""
        assert w.forces_offscreen_scroll is False


class TestScrollThroughDraw:
    """In scroll_through mode, the bottom row is positioned at
    bottom_x = canvas.width + cursor_pos:

        cursor_pos =  0   → bottom_x = canvas.width   (fully off right)
        cursor_pos = -50  → bottom_x = canvas.width - 50
        cursor_pos = -(canvas.width + bottom_width)  → fully off left

    bottom_align is ignored (no "held" path in this mode). Top row is
    still held at its computed top_align position.
    """

    def _capture_draws(self, monkeypatch):
        from led_ticker.widgets import two_row as tr

        captured: list[tuple[int, int]] = []  # (x, y) per draw_with_emoji call

        def fake_draw_with_emoji(canvas, font, x, y, color, text, **kw):
            captured.append((x, y))
            return 50

        monkeypatch.setattr(tr, "draw_with_emoji", fake_draw_with_emoji)
        return captured

    def test_at_cursor_zero_bottom_drawn_fully_offscreen_right(
        self, canvas, monkeypatch
    ):
        captured = self._capture_draws(monkeypatch)
        w = TwoRowMessage(
            top_text="TOP",
            bottom_text="some scrolling content here",
            bottom_text_scroll="scroll_through",
        )
        w.draw(canvas, cursor_pos=0)
        # Two draw_with_emoji calls expected — top then bottom.
        assert len(captured) == 2, captured
        bottom_x = captured[1][0]
        assert bottom_x == canvas.width, (
            f"scroll_through must start bottom row at canvas.width "
            f"({canvas.width}); got {bottom_x}"
        )

    def test_negative_cursor_moves_bottom_left(self, canvas, monkeypatch):
        captured = self._capture_draws(monkeypatch)
        w = TwoRowMessage(
            top_text="TOP",
            bottom_text="some scrolling content here",
            bottom_text_scroll="scroll_through",
        )
        w.draw(canvas, cursor_pos=-50)
        bottom_x = captured[1][0]
        # cursor_pos=-50 puts the bottom row 50px left of canvas.width.
        assert bottom_x == canvas.width - 50, (
            f"scroll_through expected bottom_x={canvas.width - 50} at "
            f"cursor_pos=-50; got {bottom_x}"
        )

    def test_bottom_align_ignored_in_scroll_through(self, canvas, monkeypatch):
        """Even with `bottom_align='center'` and short text that would
        normally fit, scroll_through forces the offscreen start — not
        the centered held position."""
        captured = self._capture_draws(monkeypatch)
        w = TwoRowMessage(
            top_text="TOP",
            bottom_text="hi",  # short — would normally center
            bottom_align="center",
            bottom_text_scroll="scroll_through",
        )
        w.draw(canvas, cursor_pos=0)
        bottom_x = captured[1][0]
        assert bottom_x == canvas.width, (
            f"scroll_through must ignore bottom_align; expected "
            f"bottom_x={canvas.width}, got {bottom_x}"
        )

    def test_top_row_still_held_in_scroll_through(self, canvas, monkeypatch):
        """Top row continues to draw at the same x regardless of
        cursor_pos — only bottom scrolls."""
        captured = self._capture_draws(monkeypatch)
        w = TwoRowMessage(
            top_text="TOP",
            bottom_text="some long bottom text here",
            bottom_text_scroll="scroll_through",
        )
        w.draw(canvas, cursor_pos=0)
        top_x_a = captured[0][0]
        captured.clear()
        w.draw(canvas, cursor_pos=-100)
        top_x_b = captured[0][0]
        assert top_x_a == top_x_b, (
            f"Top row x must be stable across scroll ticks; "
            f"got {top_x_a} then {top_x_b}"
        )

    def test_returned_cursor_signals_full_offscreen_travel(self, canvas):
        """The widget's returned cursor_pos must let the engine compute
        a stop position equal to -(canvas.width + bottom_width).

        Engine math: stop_pos = -(returned_cursor - canvas.width) + padding.
        We want stop_pos = -(canvas.width + bottom_width).
        Solving: returned_cursor = 2*canvas.width + bottom_width + padding.

        Test guards against drift in either the widget formula or the
        engine formula. Widget reports a cursor_pos that ANCHORS the
        engine's stop math to the right total travel.
        """
        w = TwoRowMessage(
            top_text="TOP",
            bottom_text="content",
            bottom_text_scroll="scroll_through",
        )
        _, cursor = w.draw(canvas, cursor_pos=0)
        # bottom_width is cached on first draw — read it now.
        bottom_width = w._bottom_width
        expected = 2 * canvas.width + bottom_width + w.padding
        assert cursor == expected, (
            f"scroll_through must return cursor={expected} so the engine's "
            f"stop math (-(cursor-width)+padding) lands at "
            f"-(canvas.width + bottom_width); got {cursor}"
        )


class TestScrollThroughEngineIntegration:
    """`_swap_and_scroll` integration: scroll_through widgets must
    skip pre/post holds entirely. The signal is the count of
    cursor_pos=0 draws — without holds, only the initial entry-draw
    happens at pos=0; the scroll loop decrements pos *before* its
    first draw, so all subsequent draws use negative cursor_pos. A
    pre-scroll hold loop would draw at pos=0 once per tick, blowing
    that count past 1.

    These tests use a tiny fake widget to keep them fast and focused
    on the engine branch, not widget internals."""

    def _fake_scroll_through_widget(self, bottom_width=200, canvas_width=160):
        """Minimal widget mimicking TwoRowMessage's scroll_through
        engine contract."""
        import unittest.mock as mock

        widget = mock.Mock(
            spec_set=[
                "draw",
                "forces_offscreen_scroll",
                "wraps_forever",
                "bg_color",
                "padding",
                "_bottom_width",
            ]
        )
        widget.forces_offscreen_scroll = True
        widget.wraps_forever = False
        widget.bg_color = None
        widget.padding = 6
        widget._bottom_width = bottom_width
        # Returned cursor: anchors stop math to -(canvas.width + bw).
        widget.draw.side_effect = lambda c, cursor_pos=0, **kw: (
            c,
            2 * canvas_width + bottom_width + 6,
        )
        return widget

    @pytest.mark.asyncio
    async def test_scroll_through_only_one_draw_at_cursor_zero(
        self, swapping_frame, monkeypatch
    ):
        """The engine branch must skip the pre-scroll hold loop. The
        only draw with cursor_pos=0 should be the initial entry draw
        — the scroll loop decrements pos before its first draw, so
        every subsequent draw has cursor_pos < 0.

        Without the engine branch, the standard scroll path runs a
        pre-hold loop that redraws with cursor_pos=pos=0 once per tick,
        making this count > 1 for any non-zero hold_time."""

        # No-op sleep so the test doesn't dwell during any hold loops.
        async def _no_sleep(_):
            return None

        monkeypatch.setattr("asyncio.sleep", _no_sleep)

        from led_ticker.ticker import _swap_and_scroll

        widget = self._fake_scroll_through_widget(bottom_width=200, canvas_width=160)
        canvas = swapping_frame.get_clean_canvas.return_value
        await _swap_and_scroll(
            canvas,
            swapping_frame,
            widget,
            scroll_speed=0.0,
            hold_time=1.0,  # Non-trivial: pre-hold loop would fire 20 ticks.
        )
        zero_pos_draws = [
            call
            for call in widget.draw.call_args_list
            if call.kwargs.get("cursor_pos", call.args[1] if len(call.args) > 1 else 0)
            == 0
        ]
        assert len(zero_pos_draws) == 1, (
            f"scroll_through must skip pre-scroll hold. Expected 1 draw "
            f"at cursor_pos=0 (the initial entry draw); got {len(zero_pos_draws)}. "
            f"Likely the pre-hold loop wasn't skipped."
        )

    @pytest.mark.asyncio
    async def test_scroll_through_final_pos_clears_left_edge(
        self, swapping_frame, monkeypatch
    ):
        """The scroll loop must travel at LEAST -(canvas.width +
        bottom_width) so the bottom row clears the left edge. With
        widget bottom_width=200 + canvas.width=160, final pos must be
        <= -360."""

        async def _no_sleep(_):
            return None

        monkeypatch.setattr("asyncio.sleep", _no_sleep)

        from led_ticker.ticker import _swap_and_scroll

        widget = self._fake_scroll_through_widget(bottom_width=200, canvas_width=160)
        canvas = swapping_frame.get_clean_canvas.return_value
        _, _, final_pos = await _swap_and_scroll(
            canvas,
            swapping_frame,
            widget,
            scroll_speed=0.0,
            hold_time=0.0,
        )
        assert final_pos <= -(canvas.width + 200), (
            f"scroll_through must scroll bottom row fully off the left edge; "
            f"final pos={final_pos}, expected <= {-(canvas.width + 200)}"
        )


class TestScrollThroughRealWidgetEngineIntegration:
    """End-to-end: a real TwoRowMessage driven through _swap_and_scroll.

    The other engine-integration tests use a Mock widget which fixes
    attribute names + types up-front. That can mask drift between
    the real widget's surface and what the engine reads (e.g., a
    renamed `_bottom_width` or a `forces_offscreen_scroll` that
    silently returns a Mock truthy proxy instead of strict bool).

    This test pipes a REAL widget through the engine and asserts the
    same behavioral contract — if either widget or engine drifts,
    this catches the gap that the mocked tests would miss.
    """

    @pytest.mark.asyncio
    async def test_real_two_row_scroll_through_clears_left_edge(
        self, swapping_frame, monkeypatch
    ):
        from led_ticker.ticker import _swap_and_scroll

        async def _no_sleep(_):
            return None

        monkeypatch.setattr("asyncio.sleep", _no_sleep)

        widget = TwoRowMessage(
            top_text="TOP",
            bottom_text="some real scrolling content",
            bottom_text_scroll="scroll_through",
        )
        canvas = swapping_frame.get_clean_canvas.return_value

        # Real widget needs to measure its bottom_width on first draw.
        _, _, final_pos = await _swap_and_scroll(
            canvas,
            swapping_frame,
            widget,
            scroll_speed=0.0,
            hold_time=1.0,  # Non-trivial: a pre-hold would inflate ticks.
        )

        # After the loop, the bottom row must have travelled at least
        # -(canvas.width + bottom_width) so the last char clears the left
        # edge. _bottom_width is populated on the widget's first draw.
        assert (
            widget._bottom_width > 0
        ), "Widget should have measured _bottom_width on first draw"
        expected = -(canvas.width + widget._bottom_width)
        assert final_pos <= expected, (
            f"Real TwoRowMessage scroll_through must travel to "
            f"pos <= {expected}; got {final_pos}. Widget _bottom_width="
            f"{widget._bottom_width}, canvas.width={canvas.width}."
        )

    @pytest.mark.asyncio
    async def test_real_two_row_scroll_through_skips_holds(
        self, swapping_frame, monkeypatch
    ):
        """Same cursor_pos=0 count check as the mocked test, but with a
        real widget — guards against drift where the real widget's
        `forces_offscreen_scroll` property starts returning a truthy
        Mock-like object instead of strict True.

        Subclasses TwoRowMessage to capture draw() calls — attrs.define
        produces slots-only instances so post-construction monkeypatch
        and mocker.spy both fail.
        """
        from led_ticker.ticker import _swap_and_scroll

        captured: list[int] = []

        class _RecordingTwoRow(TwoRowMessage):
            def draw(self, canvas, cursor_pos=0, **kwargs):
                captured.append(cursor_pos)
                return super().draw(canvas, cursor_pos, **kwargs)

        async def _no_sleep(_):
            return None

        monkeypatch.setattr("asyncio.sleep", _no_sleep)

        widget = _RecordingTwoRow(
            top_text="TOP",
            bottom_text="content here",
            bottom_text_scroll="scroll_through",
        )
        canvas = swapping_frame.get_clean_canvas.return_value
        await _swap_and_scroll(
            canvas, swapping_frame, widget, scroll_speed=0.0, hold_time=1.0
        )

        zero_pos_draws = [pos for pos in captured if pos == 0]
        assert len(zero_pos_draws) == 1, (
            f"Real widget engine path must skip pre-scroll hold; "
            f"expected 1 cursor_pos=0 draw, got {len(zero_pos_draws)}. "
            f"If this is > 1, the `forces_offscreen_scroll` property "
            f"is not being read as strict True by the engine."
        )
