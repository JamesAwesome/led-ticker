"""Tests for engine cooperation with widgets that wrap forever."""

from __future__ import annotations

import pytest


class _StubWrapsForeverWidget:
    """Minimal widget that signals `wraps_forever=True`. draw() returns
    a small cursor_pos to simulate normal scrolling — without engine
    cooperation, the loop would terminate quickly."""

    def __init__(self):
        self.draw_calls = 0
        self.cursor_positions: list[int] = []
        self.bg_color = None
        self.wraps_forever = True

    def draw(self, canvas, cursor_pos=0, **kwargs):
        self.draw_calls += 1
        self.cursor_positions.append(cursor_pos)
        # Return cursor_pos+10 — small positive, simulating a content
        # width. Without wraps_forever cooperation, the engine would
        # think the content fits the canvas (cursor_pos returned is
        # small) and take the held branch — but that's also OK for
        # this test since either branch needs to honor hold_time.
        return canvas, 10


class _StubFiniteWidget:
    """Normal widget — finite scroll, no wraps_forever attribute."""

    def __init__(self):
        self.draw_calls = 0
        self.bg_color = None

    def draw(self, canvas, cursor_pos=0, **kwargs):
        self.draw_calls += 1
        return canvas, 200  # > test canvas.width to trigger scroll


def _make_test_canvas():
    from rgbmatrix import RGBMatrix, RGBMatrixOptions

    opts = RGBMatrixOptions()
    opts.cols = 160
    opts.rows = 16
    opts.chain_length = 1
    return RGBMatrix(options=opts).CreateFrameCanvas()


class TestWrapsForeverRespected:
    @pytest.mark.asyncio
    async def test_wraps_forever_widget_runs_for_hold_time(self, mocker):
        """A widget with wraps_forever=True should be drawn for the
        full hold_time, NOT terminate based on cursor_pos."""
        from led_ticker.ticker import _swap_and_scroll

        widget = _StubWrapsForeverWidget()
        canvas = _make_test_canvas()
        frame = mocker.MagicMock()
        frame.matrix.SwapOnVSync.side_effect = lambda c: c
        mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

        await _swap_and_scroll(canvas, frame, widget, scroll_speed=0.05, hold_time=0.5)

        # hold_time=0.5s at ENGINE_TICK_MS=50ms → ~10 ticks minimum.
        assert widget.draw_calls >= 10, (
            f"wraps_forever widget should draw for hold_time; "
            f"got {widget.draw_calls} calls"
        )

    @pytest.mark.asyncio
    async def test_finite_widget_unaffected(self, mocker):
        """Widgets without wraps_forever attribute behave as before."""
        from led_ticker.ticker import _swap_and_scroll

        widget = _StubFiniteWidget()
        canvas = _make_test_canvas()
        frame = mocker.MagicMock()
        frame.matrix.SwapOnVSync.side_effect = lambda c: c
        mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

        await _swap_and_scroll(canvas, frame, widget, scroll_speed=0.05, hold_time=0.5)

        # Finite widget should terminate (no infinite loop). Exact
        # draw_calls depends on scroll path; just confirm it ran.
        assert widget.draw_calls > 0

    @pytest.mark.asyncio
    async def test_wraps_forever_widget_scrolls_pos(self, mocker):
        """A widget with wraps_forever=True should have cursor_pos
        decremented across ticks (engine drives the marquee), NOT
        held at pos=0 like the held-text branch."""
        from led_ticker.ticker import _swap_and_scroll

        widget = _StubWrapsForeverWidget()
        canvas = _make_test_canvas()
        frame = mocker.MagicMock()
        frame.matrix.SwapOnVSync.side_effect = lambda c: c
        mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

        await _swap_and_scroll(canvas, frame, widget, scroll_speed=0.05, hold_time=0.5)

        # cursor_positions should contain a range of decreasing values
        # (engine advances pos). If the held branch ran instead, every
        # value would be 0.
        assert len(set(widget.cursor_positions)) > 1, (
            f"engine must advance cursor_pos across ticks; "
            f"got constant positions: {widget.cursor_positions[:5]}"
        )
        assert min(widget.cursor_positions) < 0, (
            f"pos must decrement (marquee scroll); got "
            f"min={min(widget.cursor_positions)}"
        )

    @pytest.mark.asyncio
    async def test_wraps_forever_widget_bounded_by_hold_time(self, mocker):
        """hold_time still bounds wraps_forever — not actually infinite."""
        from led_ticker.ticker import _swap_and_scroll

        widget = _StubWrapsForeverWidget()
        canvas = _make_test_canvas()
        frame = mocker.MagicMock()
        frame.matrix.SwapOnVSync.side_effect = lambda c: c
        mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

        await _swap_and_scroll(canvas, frame, widget, scroll_speed=0.05, hold_time=0.1)

        # 0.1s hold ≈ 2 ticks at 50ms.
        assert (
            1 <= widget.draw_calls < 100
        ), f"Bounded by hold_time; got {widget.draw_calls}"
