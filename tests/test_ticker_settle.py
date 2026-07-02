"""Settle-to-rest at the hold->transition handoff (#305): after the hold,
the engine extends by frames_to_transition_ready() ticks -- all-or-nothing
against MAX_SETTLE_TICKS -- so transitions land at animation rest points."""

import unittest.mock as mock

import attrs

from led_ticker.ticker import MAX_SETTLE_TICKS, Ticker
from led_ticker.widgets._frame_aware import FrameAwareBase


@attrs.define
class _SettleWidget(FrameAwareBase):
    """Held-text widget reporting a fixed frames-to-rest. Draw is
    fits-on-screen (cursor_pos < canvas.width) so _swap_and_scroll takes
    the held-only branch."""

    remaining: int = 0
    draw_calls: int = attrs.field(init=False, default=0)
    ready_calls: int = attrs.field(init=False, default=0)

    def draw(self, canvas, cursor_pos=0, *, y_offset=0, font_color=None):
        self.draw_calls += 1
        return canvas, 10  # fits: 10 < canvas.width

    def frames_to_transition_ready(self) -> int:
        self.ready_calls += 1
        return self.remaining


@attrs.define
class _RaisingReadyWidget(FrameAwareBase):
    draw_calls: int = attrs.field(init=False, default=0)

    def draw(self, canvas, cursor_pos=0, *, y_offset=0, font_color=None):
        self.draw_calls += 1
        return canvas, 10

    def frames_to_transition_ready(self) -> int:
        raise RuntimeError("boom")


@attrs.define
class _PlainWidget(FrameAwareBase):
    """No frames_to_transition_ready -- must behave byte-identically to
    today (hold ticks only)."""

    draw_calls: int = attrs.field(init=False, default=0)

    def draw(self, canvas, cursor_pos=0, *, y_offset=0, font_color=None):
        self.draw_calls += 1
        return canvas, 10


# N_HOLD ticks for hold_time=0.2s: max(1, int(200) // 50) = 4
_HOLD_TIME = 0.2
_N_HOLD = 4  # max(1, int(0.2 * 1000) // 50) = max(1, 200 // 50) = 4

# _swap_and_scroll always does one initial draw+swap before entering _hold_ticks,
# so total draw_calls = 1 (initial) + _N_HOLD (hold ticks) [+ settle ticks].
_INITIAL_DRAW = 1


class TestSettleToRest:
    async def test_settle_extends_by_exactly_remaining(self, mock_frame, no_sleep):
        """After the base hold (N_HOLD ticks) the engine appends exactly
        `remaining` settle ticks when remaining <= MAX_SETTLE_TICKS."""
        canvas = mock_frame.get_clean_canvas()
        widget = _SettleWidget(remaining=5)
        ticker = Ticker(monitors=[], frame=mock_frame)
        await ticker._swap_and_scroll(canvas, widget, hold_time=_HOLD_TIME)
        # Total draws = 1 (initial) + N_HOLD (base hold) + 5 (settle)
        expected = _INITIAL_DRAW + _N_HOLD + 5
        assert widget.draw_calls == expected, (
            f"Expected {expected} draw calls (initial={_INITIAL_DRAW} + "
            f"base={_N_HOLD} + settle=5), got {widget.draw_calls}"
        )

    async def test_over_cap_extends_zero(self, mock_frame, no_sleep):
        """All-or-nothing: remaining > MAX_SETTLE_TICKS -> NO extension."""
        canvas = mock_frame.get_clean_canvas()
        widget = _SettleWidget(remaining=MAX_SETTLE_TICKS + 1)
        ticker = Ticker(monitors=[], frame=mock_frame)
        await ticker._swap_and_scroll(canvas, widget, hold_time=_HOLD_TIME)
        # Total draws = 1 (initial) + N_HOLD (base hold); no settle added
        expected = _INITIAL_DRAW + _N_HOLD
        assert widget.draw_calls == expected, (
            f"Over-cap should extend zero; expected {expected} draw calls, "
            f"got {widget.draw_calls} (remaining={MAX_SETTLE_TICKS + 1} > cap)"
        )

    async def test_raising_ready_extends_zero_no_crash(self, mock_frame, no_sleep):
        """A frames_to_transition_ready() that raises must not crash the engine
        and must not add any settle ticks (defensive -> 0)."""
        canvas = mock_frame.get_clean_canvas()
        widget = _RaisingReadyWidget()
        ticker = Ticker(monitors=[], frame=mock_frame)
        # Must not raise
        await ticker._swap_and_scroll(canvas, widget, hold_time=_HOLD_TIME)
        # No settle extension -- initial + base hold only
        expected = _INITIAL_DRAW + _N_HOLD
        assert widget.draw_calls == expected, (
            f"Raising readiness should extend zero; expected {expected}, "
            f"got {widget.draw_calls}"
        )

    async def test_breaker_disabled_skips_settle(self, mock_frame, no_sleep):
        """A breaker-tripped widget gets NO settle extension, and
        frames_to_transition_ready is never even called (settle skipped entirely)."""
        canvas = mock_frame.get_clean_canvas()
        widget = _SettleWidget(remaining=5)
        ticker = Ticker(monitors=[], frame=mock_frame)

        # Trip the widget's breaker before the call
        ticker.breaker.trip(widget, Exception("tripped for test"))
        assert ticker.breaker.is_disabled(widget)

        # Record ready_calls before the run
        calls_before = widget.ready_calls
        await ticker._swap_and_scroll(canvas, widget, hold_time=_HOLD_TIME)

        # The tripped widget's draw() is short-circuited by _safe_draw, so
        # draw_calls stays at 0. What we MUST assert is that settle was skipped.
        assert widget.ready_calls == calls_before, (
            "frames_to_transition_ready must not be called for a breaker-tripped "
            f"widget (ready_calls changed from {calls_before} to {widget.ready_calls})"
        )

    async def test_widget_without_method_unchanged(self, mock_frame, no_sleep):
        """A widget with no frames_to_transition_ready behaves exactly as
        before: only the base hold ticks fire (zero settle)."""
        canvas = mock_frame.get_clean_canvas()
        widget = _PlainWidget()
        ticker = Ticker(monitors=[], frame=mock_frame)
        await ticker._swap_and_scroll(canvas, widget, hold_time=_HOLD_TIME)
        expected = _INITIAL_DRAW + _N_HOLD
        assert widget.draw_calls == expected, (
            f"Widget without frames_to_transition_ready should draw exactly "
            f"{expected} times (initial={_INITIAL_DRAW} + hold={_N_HOLD}); "
            f"got {widget.draw_calls}"
        )

    async def test_settle_ticks_advance_frames(self, mock_frame, no_sleep):
        """Settle reuses _hold_ticks, which calls _advance_frame_if_supported
        per tick (constraint #12). After a run with remaining=3, _frame_count
        must reflect N_HOLD + 3 advances."""
        canvas = mock_frame.get_clean_canvas()
        remaining = 3
        widget = _SettleWidget(remaining=remaining)
        ticker = Ticker(monitors=[], frame=mock_frame)
        await ticker._swap_and_scroll(canvas, widget, hold_time=_HOLD_TIME)

        expected_advances = _N_HOLD + remaining
        assert widget._frame_count == expected_advances, (
            f"Expected _frame_count={expected_advances} after {_N_HOLD} base ticks "
            f"+ {remaining} settle ticks; got {widget._frame_count}. "
            "Settle must reuse _hold_ticks which calls _advance_frame_if_supported "
            "per tick (constraint #12)."
        )

    async def test_settle_skipped_when_continuous(self, mock_frame, no_sleep):
        """When continuous=True the settle block must not run (it is guarded
        by `not continuous`). This avoids jitter in seamless ticker streams."""
        canvas = mock_frame.get_clean_canvas()
        ticker = Ticker(monitors=[], frame=mock_frame)
        # continuous=True -> settle skipped; widget is small (10 < 160) so it
        # takes the else/held-only branch. But continuous skips that hold too,
        # so _hold_ticks is never called at all for short widgets.
        # Actually for the held-only (cursor_pos <= canvas.width) branch,
        # the hold is NOT gated by continuous -- the else branch always holds.
        # Only the overflow branch's pre-scroll and post-scroll holds are
        # skipped by continuous. Use an overflow widget for this test.
        overflow_widget = mock.Mock()
        overflow_widget.draw.side_effect = lambda c, cursor_pos=0, **kw: (
            c,
            cursor_pos + 200,
        )
        overflow_widget.frames_to_transition_ready = mock.Mock(return_value=5)
        await ticker._swap_and_scroll(
            canvas, overflow_widget, hold_time=_HOLD_TIME, continuous=True
        )
        # continuous=True skips the settle block via `not continuous`
        overflow_widget.frames_to_transition_ready.assert_not_called()

    async def test_max_settle_ticks_constant(self):
        """MAX_SETTLE_TICKS is ~1 s of ticks: 1000 // ENGINE_TICK_MS."""
        from led_ticker.constants import ENGINE_TICK_MS

        assert MAX_SETTLE_TICKS == 1000 // ENGINE_TICK_MS
        # At ENGINE_TICK_MS=50 that's 20 ticks
        assert MAX_SETTLE_TICKS > 0

    async def test_settle_captures_swap_return(self, swapping_frame, no_sleep):
        """Constraint #1 regression: the settle block must capture the canvas
        returned by _hold_ticks (``canvas, _ = await self._hold_ticks(...)``).

        _hold_ticks performs N swaps internally and returns the last
        back-buffer.  If the settle block drops that return value the canvas
        variable in _swap_and_scroll is stale — it still points at the canvas
        that was current before the settle phase began.  _swap_and_scroll then
        returns that stale canvas to _show_one, which hands it to the
        transition as the outgoing back-buffer.  The transition draws the next
        section's content onto the displayed front-buffer: tearing / corruption
        (constraint #1).

        swapping_frame alternates between canvas_a (start) and canvas_b.  With
        `_N_HOLD` base ticks + `remaining` settle ticks the last swap inside
        _hold_ticks leaves one of {canvas_a, canvas_b} as the new back-buffer
        (whichever id is *not* the last one displayed).  If the capture is
        dropped, _swap_and_scroll returns the pre-settle canvas_a regardless of
        how many settle ticks ran.  We verify that the returned canvas is NOT
        always canvas_a.
        """
        widget = _SettleWidget(remaining=3)
        canvas = swapping_frame.get_clean_canvas()  # canvas_a
        ticker = Ticker(monitors=[], frame=swapping_frame)
        returned_canvas, _, _ = await ticker._swap_and_scroll(
            canvas, widget, hold_time=_HOLD_TIME
        )

        # Swap sequence with _HOLD_TIME=0.2 s and remaining=3:
        #   initial draw+swap (#1):   a -> b  (outer canvas = b)
        #   base _hold_ticks (4 ticks, swaps #2-5):
        #     #2 b->a, #3 a->b, #4 b->a, #5 a->b  => return canvas_b
        #     outer canvas = b (captured at line 684)
        #   settle _hold_ticks (3 ticks, swaps #6-8):
        #     #6 b->a, #7 a->b, #8 b->a  => return canvas_a
        #     WITH capture:   outer canvas = a  <- correct
        #     WITHOUT capture: outer canvas stays b <- mutation bug
        #
        # So the correctly-captured path returns canvas_a; the dropped-capture
        # mutation returns canvas_b.
        canvas_a = swapping_frame._canvas_a
        assert returned_canvas is canvas_a, (
            f"_swap_and_scroll returned {returned_canvas!r} instead of canvas_a.  "
            "After 1 initial + 4 base + 3 settle swaps the back-buffer must be "
            "canvas_a.  Getting canvas_b means the settle block dropped the "
            "_hold_ticks return value (constraint #1)."
        )
