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

    @pytest.mark.asyncio
    async def test_wraps_forever_honors_custom_scroll_speed(self, mocker):
        """n_ticks must scale with scroll_speed so a faster marquee
        (smaller scroll_speed) doesn't truncate the section's wall-clock
        duration. With hold_time=1.0 and scroll_speed=0.025 (twice as
        fast), n_ticks should ≈ 40 — total wall-clock still 1.0s,
        marquee just ticks faster."""
        from led_ticker.ticker import _swap_and_scroll

        widget = _StubWrapsForeverWidget()
        canvas = _make_test_canvas()
        frame = mocker.MagicMock()
        frame.matrix.SwapOnVSync.side_effect = lambda c: c
        mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

        await _swap_and_scroll(canvas, frame, widget, scroll_speed=0.025, hold_time=1.0)

        # 1.0s / 0.025s per tick = 40 ticks.
        assert 35 <= widget.draw_calls <= 45, (
            f"wraps_forever must honor scroll_speed: hold_time=1.0s + "
            f"scroll_speed=0.025 → ~40 ticks; got {widget.draw_calls}. "
            f"If this is ~20, the engine is computing n_ticks from "
            f"ENGINE_TICK_MS instead of scroll_speed (cuts wall-clock "
            f"duration in half for fast-marquee configs)."
        )


class TestWrapsForeverBottomTextLoops:
    @pytest.mark.asyncio
    async def test_wraps_forever_extends_n_ticks_for_bottom_text_loops(self, mocker):
        """When bottom_text_loops > 0 and N × cycle_width exceeds the
        hold_time-based n_ticks, engine runs the extended count.
        """
        from unittest.mock import MagicMock

        from led_ticker.ticker import _swap_and_scroll

        mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

        # Mock widget: wraps_forever=True, bottom_text_loops=4, cycle_width=10
        # → loops_floor * cycle_width = 40 ticks
        # hold_time=0.5s, scroll_speed=0.05 → 10 ticks from hold_time
        # Final: max(10, 40) = 40 draws expected.
        widget = MagicMock()
        widget.wraps_forever = True
        widget.bottom_text_loops = 4
        widget.bg_color = None
        widget.draw.return_value = (MagicMock(), 10)  # (canvas, cycle_width=10)
        frame = MagicMock()
        frame.matrix.SwapOnVSync = lambda c: c

        await _swap_and_scroll(
            MagicMock(width=128),
            frame,
            widget,
            hold_time=0.5,
            scroll_speed=0.05,
            continuous=False,
        )

        # Expected at least 40 draw calls (4 loops × 10 cycle_width)
        assert widget.draw.call_count >= 40, (
            f"expected >= 40 draws (4 loops × 10 cycle_width), "
            f"got {widget.draw.call_count}"
        )

    @pytest.mark.asyncio
    async def test_wraps_forever_hold_time_wins_when_longer(self, mocker):
        """When hold_time-derived n_ticks exceeds N × cycle_width, the
        longer duration wins (matches max() semantics).
        """
        from unittest.mock import MagicMock

        from led_ticker.ticker import _swap_and_scroll

        mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

        # hold_time=5s, scroll_speed=0.05 → 100 ticks
        # bottom_text_loops=2, cycle_width=10 → 20 ticks
        # max(100, 20) = 100. Don't truncate.
        widget = MagicMock()
        widget.wraps_forever = True
        widget.bottom_text_loops = 2
        widget.bg_color = None
        widget.draw.return_value = (MagicMock(), 10)
        frame = MagicMock()
        frame.matrix.SwapOnVSync = lambda c: c

        await _swap_and_scroll(
            MagicMock(width=128),
            frame,
            widget,
            hold_time=5.0,
            scroll_speed=0.05,
            continuous=False,
        )

        # hold_time gives 100 ticks; bottom_text_loops gives 20; max is 100.
        assert (
            95 <= widget.draw.call_count <= 105
        ), f"expected ~100 draws (hold_time wins), got {widget.draw.call_count}"

    @pytest.mark.asyncio
    async def test_wraps_forever_bottom_text_loops_zero_uses_hold_time_only(
        self, mocker
    ):
        """Regression: bottom_text_loops=0 (default) preserves today's exact
        behavior. n_ticks comes purely from hold_time / scroll_speed.
        """
        from unittest.mock import MagicMock

        from led_ticker.ticker import _swap_and_scroll

        mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

        # hold_time=0.5s, scroll_speed=0.05 → 10 ticks
        widget = MagicMock()
        widget.wraps_forever = True
        widget.bottom_text_loops = 0
        widget.bg_color = None
        widget.draw.return_value = (
            MagicMock(),
            100,
        )  # Big cycle_width — should be IGNORED
        frame = MagicMock()
        frame.matrix.SwapOnVSync = lambda c: c

        await _swap_and_scroll(
            MagicMock(width=128),
            frame,
            widget,
            hold_time=0.5,
            scroll_speed=0.05,
            continuous=False,
        )

        # Should be 11 (1 initial draw + 10 loop ticks from hold_time only;
        # the big cycle_width=100 must NOT trigger extension when loops=0).
        assert widget.draw.call_count == 11, (
            f"expected exactly 11 draws "
            f"(1 initial + 10 hold_time ticks, no extension), "
            f"got {widget.draw.call_count}"
        )
