"""Tests for ticker display modes (run_swap, run_forever_scroll, etc)."""

import asyncio
import unittest.mock as mock

import pytest

from led_ticker.scaled_canvas import ScaledCanvas
from led_ticker.ticker import (
    Ticker,
)


class TestFromRssFeed:
    def test_uses_feed_title(self, mock_frame):
        feed = mock.Mock()
        feed.feed_title = "CNN"
        feed.feed_stories = [mock.Mock(), mock.Mock()]
        ticker = Ticker.from_rss_feed(feed, mock_frame)
        assert ticker.title == "CNN"
        assert ticker.monitors == feed.feed_stories

    def test_uses_custom_title(self, mock_frame):
        feed = mock.Mock()
        feed.feed_title = "CNN"
        feed.feed_stories = []
        ticker = Ticker.from_rss_feed(feed, mock_frame, custom_title="Breaking")
        assert ticker.title == "Breaking"

    def test_passes_notif_queue(self, mock_frame):
        feed = mock.Mock(feed_title="T", feed_stories=[])
        q = asyncio.Queue()
        ticker = Ticker.from_rss_feed(feed, mock_frame, notif_queue=q)
        assert ticker.notif_queue is q


class TestSwapAndScroll:
    async def test_fits_in_canvas(self, canvas, mock_frame, make_widget, no_sleep):
        widget = make_widget(content_width=40)
        ticker = Ticker(monitors=[], frame=mock_frame)
        result_canvas, pos, scroll_pos = await ticker._swap_and_scroll(canvas, widget)
        assert result_canvas is canvas
        assert pos == 40
        assert scroll_pos == 0  # no scrolling needed
        # Tick loop calls draw multiple times during hold (once per ENGINE_TICK_MS).
        assert widget.draw.call_count >= 1

    async def test_oversized_triggers_scroll(
        self,
        canvas,
        mock_frame,
        make_widget,
        no_sleep,
    ):
        widget = make_widget(content_width=200)
        ticker = Ticker(monitors=[], frame=mock_frame)
        await ticker._swap_and_scroll(canvas, widget)
        # Should have scrolled the full text (many draw calls)
        assert widget.draw.call_count > 10


class TestSwapAndScrollOverflow:
    async def test_oversized_scrolls_full_text(
        self,
        canvas,
        mock_frame,
        make_widget,
        no_sleep,
    ):
        widget = make_widget(content_width=200)
        ticker = Ticker(monitors=[], frame=mock_frame)
        await ticker._swap_and_scroll(canvas, widget)
        # Should have called draw many times to scroll the full text
        assert widget.draw.call_count > 10

    async def test_fits_on_screen_no_scroll(
        self,
        canvas,
        mock_frame,
        make_widget,
        no_sleep,
    ):
        widget = make_widget(content_width=100)
        ticker = Ticker(monitors=[], frame=mock_frame)
        await ticker._swap_and_scroll(canvas, widget)
        # Tick loop calls draw multiple times during the held-text hold;
        # no scroll draw calls occur since the text fits.
        assert widget.draw.call_count >= 1

    async def test_scroll_stops_at_last_visible_pixel(
        self,
        canvas,
        mock_frame,
        make_widget,
        no_sleep,
    ):
        """For 600px text on 160px canvas, scroll stops at pos=-440."""
        content_width = 600
        widget = make_widget(content_width=content_width)
        ticker = Ticker(monitors=[], frame=mock_frame)
        _, cursor_pos, scroll_pos = await ticker._swap_and_scroll(canvas, widget)
        assert cursor_pos == content_width
        # stop_pos = -(content_width - canvas.width)
        expected_stop = -(content_width - canvas.width)
        assert scroll_pos == expected_stop, (
            f"Expected scroll stop at {expected_stop} "
            f"(content_width={content_width}, canvas.width={canvas.width})"
        )

    async def test_scroll_pos_zero_for_short_text(
        self,
        canvas,
        mock_frame,
        make_widget,
        no_sleep,
    ):
        """Short text that fits on screen returns scroll_pos=0."""
        widget = make_widget(content_width=100)
        ticker = Ticker(monitors=[], frame=mock_frame)
        _, _, scroll_pos = await ticker._swap_and_scroll(canvas, widget)
        assert scroll_pos == 0

    async def test_scroll_stop_position_math(
        self,
        canvas,
        mock_frame,
        make_widget,
        no_sleep,
    ):
        """Verify stop_pos formula: -(content_width - canvas_width)."""
        for width in [200, 320, 500, 1000]:
            widget = make_widget(content_width=width)
            ticker = Ticker(monitors=[], frame=mock_frame)
            _, _, scroll_pos = await ticker._swap_and_scroll(canvas, widget)
            expected = -(width - canvas.width)
            assert (
                scroll_pos == expected
            ), f"width={width}: expected {expected}, got {scroll_pos}"

    async def test_stop_pos_accounts_for_padding(
        self,
        canvas,
        mock_frame,
        make_widget,
        no_sleep,
    ):
        """Widget with padding scrolls further left so text is flush."""
        content_width = 600
        padding = 6
        widget = make_widget(content_width=content_width)
        widget.padding = padding  # simulate real widget padding
        ticker = Ticker(monitors=[], frame=mock_frame)
        _, _, scroll_pos = await ticker._swap_and_scroll(canvas, widget)
        # stop_pos = -(content_width - canvas.width) + padding
        expected_stop = -(content_width - canvas.width) + padding
        msg = (
            f"Expected scroll stop at {expected_stop} "
            f"(w={content_width}, c={canvas.width}, p={padding})"
        )
        assert scroll_pos == expected_stop, msg

    async def test_stop_pos_no_padding_attribute(
        self,
        canvas,
        mock_frame,
        make_widget,
        no_sleep,
    ):
        """Widget without padding attribute defaults to 0 adjustment."""
        content_width = 600
        widget = make_widget(content_width=content_width)
        ticker = Ticker(monitors=[], frame=mock_frame)
        _, _, scroll_pos = await ticker._swap_and_scroll(canvas, widget)
        # stop_pos = -(content_width - canvas.width) (no padding adjustment)
        expected_stop = -(content_width - canvas.width)
        assert scroll_pos == expected_stop, (
            f"Expected scroll stop at {expected_stop} "
            f"(content_width={content_width}, canvas.width={canvas.width})"
        )


class TestSwapAndScrollSkipInitialDraw:
    """Regression: _swap_and_scroll(skip_initial_draw=True) skips the FIRST
    SwapOnVSync because the caller (a transition or a scroll-between) just
    put this widget on screen at t=1.0. Without this, the panel goes blank
    for one frame between transition end and section start.
    """

    async def test_skip_initial_draw_omits_first_swap(
        self, canvas, mock_frame, make_widget, no_sleep
    ):
        widget = make_widget(content_width=40)
        ticker = Ticker(monitors=[], frame=mock_frame)
        await ticker._swap_and_scroll(
            canvas, widget, skip_initial_draw=True, hold_time=0.05
        )
        # skip_initial_draw=True suppresses the initial swap; the tick loop
        # still runs for the hold. Verify that fewer swaps occurred vs the
        # default path.  Concrete: hold_time=0.05 → 1 tick → 1 swap (no initial).
        assert mock_frame.matrix.SwapOnVSync.call_count == 1, (
            f"skip_initial_draw=True should suppress only the initial swap; "
            f"got {mock_frame.matrix.SwapOnVSync.call_count} swaps."
        )

    async def test_default_includes_initial_swap(
        self, canvas, mock_frame, make_widget, no_sleep
    ):
        # Default path includes the initial swap + tick loop swaps.
        # With hold_time=0.05 → 1 tick → total 2 swaps (initial + 1 tick).
        widget = make_widget(content_width=40)
        ticker = Ticker(monitors=[], frame=mock_frame)
        await ticker._swap_and_scroll(canvas, widget, hold_time=0.05)
        assert mock_frame.matrix.SwapOnVSync.call_count == 2


class TestSwapAndScrollContinuous:
    """Regression: continuous=True skips the hold_time sleeps for overflow
    widgets. Used by the scroll transition in _run_swap to keep one
    seamless 1px/frame stream across widget boundaries.
    """

    async def test_continuous_skips_holds_for_overflow(
        self, canvas, mock_frame, make_widget, monkeypatch
    ):
        sleep_calls: list[float] = []
        _real_sleep = asyncio.sleep

        async def _record(seconds):
            sleep_calls.append(seconds)
            await _real_sleep(0)

        monkeypatch.setattr("led_ticker.ticker.asyncio.sleep", _record)

        widget = make_widget(content_width=200)  # overflows 160-wide canvas
        ticker = Ticker(monitors=[], frame=mock_frame)
        await ticker._swap_and_scroll(canvas, widget, hold_time=3.0, continuous=True)
        # No 3-second hold_time sleeps should appear when continuous=True.
        assert (
            3.0 not in sleep_calls
        ), f"continuous=True must skip hold_time sleeps; sleep_calls={sleep_calls}"

    async def test_non_continuous_includes_holds(
        self, canvas, mock_frame, make_widget, monkeypatch
    ):
        from led_ticker.ticker import ENGINE_TICK_MS

        sleep_calls: list[float] = []
        _real_sleep = asyncio.sleep

        async def _record(seconds):
            sleep_calls.append(seconds)
            await _real_sleep(0)

        monkeypatch.setattr("led_ticker.ticker.asyncio.sleep", _record)

        # Zero elapsed work time → max(0.0, tick_s - 0.0) = tick_s exactly,
        # so the existing `tick_s in sleep_calls` assertion stays valid.
        mock_loop = mock.Mock()
        mock_loop.time.return_value = 0.0
        monkeypatch.setattr(
            "led_ticker.ticker.asyncio.get_running_loop", lambda: mock_loop
        )

        widget = make_widget(content_width=200)
        ticker = Ticker(monitors=[], frame=mock_frame)
        await ticker._swap_and_scroll(canvas, widget, hold_time=0.1, continuous=False)
        # With the tick loop, hold_time=0.1s produces 2 ticks (max(1, 100//50))
        # per hold phase, each sleeping ENGINE_TICK_MS/1000 = 0.05s.
        # For an overflow widget: pre-scroll hold + post-scroll hold → 4 tick sleeps
        # plus per-pixel scroll sleeps. Verify tick-sized sleeps appear (not the
        # old bare hold_time sleep).
        tick_s = ENGINE_TICK_MS / 1000
        assert (
            tick_s in sleep_calls
        ), f"Expected tick-sized sleeps ({tick_s}s) in sleep_calls; got {sleep_calls}"
        # No single sleep should equal the full hold_time (old bare sleep gone).
        assert (
            0.1 not in sleep_calls
        ), f"hold_time bare sleep must not appear; sleep_calls={sleep_calls}"


class TestTickDriftCompensation:
    """Tick loops must subtract elapsed work time from the sleep so the
    panel animates at a steady ENGINE_TICK_MS cadence even when draw +
    swap take measurable time (C3). Each tick calls loop.time() twice:
    once at t0 = loop.time() and once inside the max() subtraction.
    """

    async def test_swap_and_scroll_held_text_subtracts_work_time(
        self, canvas, mock_frame, make_widget, monkeypatch
    ):
        from led_ticker.ticker import ENGINE_TICK_MS

        sleep_calls: list[float] = []

        async def _record(seconds: float) -> None:
            sleep_calls.append(seconds)

        monkeypatch.setattr("led_ticker.ticker.asyncio.sleep", _record)

        # Simulate 30 ms of work per tick: loop.time() returns alternating
        # 0.000 (t0) and 0.030 (after work). Each tick consumes two values.
        tick_times = iter([0.000, 0.030] * 100)
        mock_loop = mock.Mock()
        mock_loop.time.side_effect = lambda: next(tick_times)
        monkeypatch.setattr(
            "led_ticker.ticker.asyncio.get_running_loop", lambda: mock_loop
        )

        widget = make_widget(content_width=40)  # fits canvas → held-text branch
        ticker = Ticker(monitors=[], frame=mock_frame)
        await ticker._swap_and_scroll(canvas, widget, hold_time=0.05)

        tick_s = ENGINE_TICK_MS / 1000  # 0.05
        expected = tick_s - 0.030  # 0.020
        assert sleep_calls, "no sleep calls recorded"
        assert all(
            abs(s - expected) < 1e-9 for s in sleep_calls
        ), f"expected {expected}s sleeps (drift-compensated), got {sleep_calls}"

    async def test_scroll_and_delay_subtracts_work_time(
        self, canvas, mock_frame, make_widget, no_sleep, monkeypatch
    ):
        from led_ticker.ticker import ENGINE_TICK_MS

        sleep_calls: list[float] = []

        async def _record(seconds: float) -> None:
            sleep_calls.append(seconds)

        monkeypatch.setattr("led_ticker.ticker.asyncio.sleep", _record)

        tick_times = iter([0.000, 0.020] * 100)  # 20 ms work per tick
        mock_loop = mock.Mock()
        mock_loop.time.side_effect = lambda: next(tick_times)
        monkeypatch.setattr(
            "led_ticker.ticker.asyncio.get_running_loop", lambda: mock_loop
        )

        widget = make_widget(content_width=40)
        ticker = Ticker(monitors=[], frame=mock_frame)
        canvas_result, _ = await ticker._scroll_and_delay(canvas, widget, delay=0.1)

        tick_s = ENGINE_TICK_MS / 1000  # 0.05
        expected = tick_s - 0.020  # 0.030
        assert sleep_calls, "no sleep calls recorded"
        assert all(
            abs(s - expected) < 1e-9 for s in sleep_calls
        ), f"expected {expected}s sleeps, got {sleep_calls}"


class TestSwapOnVSyncCapture:
    """Regression: every SwapOnVSync call's return value must be captured
    (CLAUDE.md constraint #1). On real hardware the return is the previous
    front buffer (a DIFFERENT object) which becomes the new back buffer.
    Dropping it draws on the actively-displayed buffer, causing tearing.

    The default mock_frame returns the same canvas, so dropping the
    capture is invisible. swapping_frame rotates between two distinct
    canvas objects so the bug is detectable: count distinct canvases
    seen by widget.draw — if < 2, capture was dropped somewhere.
    """

    async def test_swap_and_scroll_captures_return(
        self, swapping_frame, make_widget, no_sleep
    ):
        widget = make_widget(content_width=200)  # overflow → multiple frames
        canvas = swapping_frame.get_clean_canvas()
        ticker = Ticker(monitors=[], frame=swapping_frame)
        await ticker._swap_and_scroll(canvas, widget)

        canvas_args = {id(call.args[0]) for call in widget.draw.call_args_list}
        assert len(canvas_args) >= 2, (
            "widget.draw was called with only one canvas object — "
            "production code likely dropped a SwapOnVSync return value."
        )

    async def test_run_transition_captures_return(
        self, swapping_frame, make_widget, no_sleep
    ):
        from led_ticker.transitions import Cut, run_transition

        outgoing = make_widget(40)
        incoming = make_widget(40)
        canvas = swapping_frame.get_clean_canvas()

        await run_transition(
            canvas,
            swapping_frame,
            outgoing,
            incoming,
            transition=Cut(),
            duration=0.5,
            scroll_speed=0.05,
        )
        # Outgoing/incoming each get drawn at distinct frames.
        # If capture is dropped, every call sees canvas_a only.
        all_args = [call.args[0] for call in outgoing.draw.call_args_list] + [
            call.args[0] for call in incoming.draw.call_args_list
        ]
        distinct = {id(c) for c in all_args}
        assert len(distinct) >= 2, (
            f"All transition draws happened on one canvas (id count={len(distinct)}) "
            "— likely a dropped SwapOnVSync return."
        )


class TestScrollAndDelay:
    async def test_scrolls_from_cursor_to_zero(
        self, canvas, mock_frame, make_widget, no_sleep
    ):
        widget = make_widget(content_width=40)
        ticker = Ticker(monitors=[], frame=mock_frame)
        _, pos = await ticker._scroll_and_delay(canvas, widget, delay=0, cursor_pos=5)
        assert pos > 0
        assert widget.draw.call_count >= 5

    async def test_cursor_zero_no_scroll_loop(
        self, canvas, mock_frame, make_widget, no_sleep
    ):
        widget = make_widget(content_width=40)
        ticker = Ticker(monitors=[], frame=mock_frame)
        _, pos = await ticker._scroll_and_delay(canvas, widget, delay=0, cursor_pos=0)
        # Initial draw + the post-scroll hold tick loop's draw
        # (n_ticks=max(1, 0//50)=1) — 2 calls total. Without the tick
        # loop this would be 1.
        assert widget.draw.call_count == 2

    async def test_scroll_in_loop_advances_frame_per_tick(
        self, canvas, mock_frame, no_sleep
    ):
        """Tripwire: the scroll-in loop (`while pos > 0`) must advance
        the frame counter per tick so animated title providers
        animate during scroll-in, matching the post-scroll hold and
        `_swap_and_scroll`'s scroll branch. Without this, a rainbow
        title freezes during scroll-in then animates after landing.
        """
        widget = mock.Mock()
        widget.draw.side_effect = lambda c, cursor_pos=0, **kw: (c, cursor_pos + 40)
        widget._advance_frame_count = 0

        def _advance(**kwargs):
            widget._advance_frame_count += 1

        widget.advance_frame.side_effect = _advance

        ticker = Ticker(monitors=[], frame=mock_frame)
        # cursor_pos=5 → 5 scroll-in iterations + 1 post-scroll tick (delay=0).
        await ticker._scroll_and_delay(canvas, widget, delay=0, cursor_pos=5)

        assert widget._advance_frame_count == 6, (
            f"Expected 6 advance_frame calls (5 scroll-in + 1 post-scroll); "
            f"got {widget._advance_frame_count}"
        )

    async def test_post_scroll_hold_advances_frame_per_tick(
        self, canvas, mock_frame, no_sleep
    ):
        """Tripwire (I3): the post-scroll hold must run a tick loop
        calling `advance_frame` per tick, so animated title providers
        (color_cycle, rainbow) actually animate during the delay.

        Without this, an animated title held at pos=0 freezes on the
        visit-initial frame for the full delay — affects
        forever_scroll / infini_scroll modes that go through
        `_scroll_and_delay` rather than `_swap_and_scroll`.
        """
        # Build a widget that exposes advance_frame and counts calls.
        widget = mock.Mock()
        widget.draw.side_effect = lambda c, cursor_pos=0, **kw: (c, cursor_pos + 40)
        widget._advance_frame_count = 0

        def _advance(**kwargs):
            widget._advance_frame_count += 1

        widget.advance_frame.side_effect = _advance

        ticker = Ticker(monitors=[], frame=mock_frame)
        # delay=0.5s @ ENGINE_TICK_MS=50ms → 10 ticks expected.
        await ticker._scroll_and_delay(canvas, widget, delay=0.5, cursor_pos=0)

        assert widget._advance_frame_count == 10


class TestScrollOneByOne:
    """forever_scroll mode with queue length 1 routes through
    _scroll_one_by_one. The redraw loop must advance frame per tick
    or animated providers (rainbow, color_cycle) freeze."""

    async def test_advances_frame_per_tick(self, canvas, mock_frame, no_sleep):
        """Hardware bug: smoke §17 (RSS feed + rainbow) rendered as
        a static gradient because _scroll_one_by_one's while loop
        never advanced the widget's frame counter."""
        widget = mock.Mock()
        # Widget is 5 wide; scrolls until final_pos < 0. Starting at
        # cursor_pos=0, final_pos = 5 first tick, then cursor_pos
        # decrements toward -∞. Loop breaks when widget.draw returns
        # final_pos < 0 AND queue is empty.
        widget.draw.side_effect = lambda c, cursor_pos=0: (c, cursor_pos + 5)
        widget._advance_frame_count = 0

        def _advance(**kwargs):
            widget._advance_frame_count += 1

        widget.advance_frame.side_effect = _advance

        queue = asyncio.Queue()
        await queue.put(widget)

        ticker = Ticker(
            monitors=[], frame=mock_frame, notif_queue=queue, scroll_speed=0
        )
        await ticker._scroll_one_by_one(canvas)

        # Loop ran for ~6 ticks before final_pos < 0 broke it (cursor=0,-1,-2,...).
        # advance_frame must have been called once per tick — at minimum 1.
        assert widget._advance_frame_count >= 1, (
            f"Expected ≥1 advance_frame calls; got "
            f"{widget._advance_frame_count}. _scroll_one_by_one redraws "
            f"the widget per tick but isn't calling "
            f"_advance_frame_if_supported — animated providers freeze."
        )
        # Sanity: should match the draw call count (one advance per draw).
        assert widget._advance_frame_count == widget.draw.call_count


class TestScrollSideBySide:
    """forever_scroll mode with queue length > 1 routes through
    _scroll_side_by_side. The outer redraw loop must advance frame
    on every UNIQUE buffered widget per tick — not zero (frozen)
    and not multiple times per tick (over-advance from duplicates).
    """

    def test_side_by_side_default_separator_paints_hires_circle_on_bigsign(self):
        """At scale=4 with two widgets, the default buffer separator
        renders as a hi-res circle (SetPixel on real canvas), not as
        chunky BDF '•'. Tripwire that DEFAULT_BUFFER_MSG.draw routes
        through _draw_hires_circle."""
        from unittest.mock import MagicMock

        from led_ticker.ticker import DEFAULT_BUFFER_MSG

        real = MagicMock()
        real.width, real.height = 256, 64
        canvas = ScaledCanvas(real, scale=4, content_height=16)

        out, cursor = DEFAULT_BUFFER_MSG.draw(canvas, cursor_pos=0)

        # Hi-res circle path: SetPixel called many times on real canvas
        # (not on the wrapper).
        assert (
            real.SetPixel.call_count > 700
        ), f"expected disk paint (~800 pixels), got {real.SetPixel.call_count}"
        # Logical advance matches the disk helper's contract.
        assert cursor == 10

    async def test_end_of_scroll_hold_redraws_at_same_position(
        self, canvas, mock_frame, no_sleep
    ):
        """Tripwire: the hold loop must redraw at the SAME cursor_pos
        as the just-drawn final scroll frame — not one pixel left.
        Off-by-one surfaces as a 1px visual snap when scrolling stops
        at the held end-position. Hardware-observed bug: §17 RSS feed
        snapped left when text came to rest.

        Test setup: widget_width=30, canvas.width=160 (mock_frame's
        default canvas) — mon_0_end_pos=30 ≤ 160 on the FIRST outer
        iter, so the hold condition fires immediately with no
        scroll-in. Every draw afterward is part of the hold and must
        be at the SAME cursor_pos as the initial held-position draw.
        """
        draw_positions: list[int] = []
        widget = mock.Mock()

        def _draw(c, cursor_pos=0):
            draw_positions.append(cursor_pos)
            return (c, cursor_pos + 30)

        widget.draw.side_effect = _draw
        widget.bg_color = None

        queue = asyncio.Queue()
        await queue.put(widget)

        ticker = Ticker(
            monitors=[], frame=mock_frame, notif_queue=queue, scroll_speed=0
        )
        await ticker._scroll_side_by_side(canvas, hold_at_end=0.2)

        # First draw establishes the held end-position; every hold
        # tick must redraw at that same pos. Variation = visual snap.
        assert (
            len(draw_positions) >= 2
        ), f"Hold loop didn't run; only got {draw_positions} draws."
        assert all(p == draw_positions[0] for p in draw_positions), (
            f"Visual snap detected — draws are not all at the held "
            f"position. First (held) draw at cursor_pos={draw_positions[0]}, "
            f"subsequent draws at {draw_positions[1:5]}... The hold "
            f"loop should redraw at `held_pos`, not `held_pos - 1`."
        )

    async def test_end_of_scroll_hold_advances_frame_per_tick(
        self, canvas, mock_frame, no_sleep
    ):
        """Tripwire: when _scroll_side_by_side reaches its end-of-scroll
        hold (queue exhausted, single widget visible), the widget's
        frame counter must continue ticking during the hold so animated
        providers (rainbow, color_cycle) keep sweeping. Without this,
        the rainbow freezes the moment the text stops moving — visible
        on hardware as smoke §17 RSS feed."""
        widget = mock.Mock()
        widget.draw.side_effect = lambda c, cursor_pos=0: (c, cursor_pos + 30)
        widget._advance_frame_count = 0
        widget.bg_color = None

        def _advance(**kwargs):
            widget._advance_frame_count += 1

        widget.advance_frame.side_effect = _advance

        queue = asyncio.Queue()
        await queue.put(widget)

        # hold_at_end=0.5s @ ENGINE_TICK_MS=50ms → ≥10 hold ticks
        # expected, plus a small number of scroll-in ticks before
        # the hold begins.
        ticker = Ticker(
            monitors=[], frame=mock_frame, notif_queue=queue, scroll_speed=0
        )
        await ticker._scroll_side_by_side(canvas, hold_at_end=0.5)

        assert widget._advance_frame_count >= 10, (
            f"Expected ≥10 advance_frame calls covering the 0.5s "
            f"end-of-scroll hold; got {widget._advance_frame_count}. "
            f"The hold is a single sleep — animated providers freeze "
            f"during the held end-state."
        )

    async def test_advances_each_widget_once_per_tick(
        self, canvas, mock_frame, no_sleep
    ):
        """Tripwire: _scroll_side_by_side redraws every buffered
        widget per tick. Animated providers (rainbow, color_cycle)
        on any of them must animate. Without per-tick advance, all
        scrolling stories freeze on their visit-initial hue."""

        def _make_widget(width: int):
            w = mock.Mock()
            w.draw.side_effect = lambda c, cursor_pos=0: (c, cursor_pos + width)
            w._advance_frame_count = 0
            w.bg_color = None

            def _advance(**kwargs):
                w._advance_frame_count += 1

            w.advance_frame.side_effect = _advance
            return w

        w1 = _make_widget(40)
        w2 = _make_widget(40)
        queue = asyncio.Queue()
        await queue.put(w1)
        await queue.put(w2)

        ticker = Ticker(
            monitors=[], frame=mock_frame, notif_queue=queue, scroll_speed=0
        )
        await ticker._scroll_side_by_side(canvas, hold_at_end=0)

        # Both widgets should have been advanced. Not asserting an
        # exact count — the loop runs many ticks scrolling everything
        # off-canvas — but each unique widget must see at least 1
        # advance per tick it was buffered.
        assert w1._advance_frame_count >= 1, (
            "w1 never advanced. Side-by-side scroll isn't ticking the "
            "frame counter — animated providers freeze."
        )
        assert (
            w2._advance_frame_count >= 1
        ), f"w2 never advanced (got {w2._advance_frame_count} calls)."


class TestRunSwap:
    async def test_processes_all_widgets(
        self, canvas, mock_frame, make_widget, no_sleep
    ):
        q = asyncio.Queue()
        w1 = make_widget(40)
        w2 = make_widget(40)
        await q.put(w1)
        await q.put(w2)
        ticker = Ticker(monitors=[], frame=mock_frame, notif_queue=q)
        await ticker._run_swap(canvas)
        assert w1.draw.called
        assert w2.draw.called

    async def test_single_widget(self, canvas, mock_frame, make_widget, no_sleep):
        q = asyncio.Queue()
        w = make_widget(40)
        await q.put(w)
        ticker = Ticker(monitors=[], frame=mock_frame, notif_queue=q)
        await ticker._run_swap(canvas)
        assert w.draw.called


class TestRunSwapPlayDispatch:
    """run_swap dispatches to widget.play() when the class declares it."""

    async def test_play_widget_invoked_instead_of_draw(
        self, canvas, mock_frame, no_sleep
    ):
        class _PlayOnly:
            def __init__(self):
                self.draw_called = False
                self.play_calls: list[int] = []
                self.gif_loops = 3

            def draw(self, canvas, cursor_pos=0, **kwargs):
                self.draw_called = True
                return canvas, canvas.width

            async def play(self, real_canvas, frame, loop_count=1, **kwargs):
                self.play_calls.append(loop_count)
                return real_canvas

        widget = _PlayOnly()
        q = asyncio.Queue()
        await q.put(widget)
        ticker = Ticker(monitors=[], frame=mock_frame, notif_queue=q)
        await ticker._run_swap(canvas)

        # play() ran with gif_loops=3; draw() was not invoked
        assert widget.play_calls == [3]
        assert not widget.draw_called

    async def test_play_widget_stashes_logical_scale_on_widget(self, mock_frame):
        """`_play_widget` peels the ScaledCanvas before handing the raw
        canvas to widget.play(), but image widgets need the wrapper's
        scale to interpret logical-unit knobs (`top_row_height`). The
        ticker stashes `wrapper.scale` on `widget._logical_scale`
        before unwrapping; widgets that don't declare the field are
        left alone."""
        from rgbmatrix import _StubCanvas

        class _Recorder:
            _logical_scale = 1  # declares the field — should be set

            async def play(self, real_canvas, frame, loop_count=1, **kwargs):
                return frame.matrix.SwapOnVSync(real_canvas)

        real = _StubCanvas(width=256, height=64)
        mock_frame.matrix.SwapOnVSync.return_value = _StubCanvas(width=256, height=64)
        widget = _Recorder()

        # Wrapped (bigsign): scale should propagate
        ticker = Ticker(monitors=[], frame=mock_frame)
        await ticker._play_widget(ScaledCanvas(real, scale=4), widget)
        assert widget._logical_scale == 4

        # Unwrapped (small sign): scale should reset to 1
        await ticker._play_widget(_StubCanvas(width=160, height=16), widget)
        assert widget._logical_scale == 1

    async def test_play_widget_preserves_scaled_wrapper(self, mock_frame):
        """When the canvas is a ScaledCanvas, _play_widget unwraps for
        the widget but re-anchors the wrapper to the new back-buffer
        afterwards so subsequent draws stay scaled.

        Uses _StubCanvas (the real test stub) instead of MagicMock so
        any attribute access beyond width/height inside _play_widget
        would surface here rather than silently no-op'ing as a Mock."""
        from rgbmatrix import _StubCanvas

        class _Recorder:
            def __init__(self):
                self.received_canvas = None

            async def play(self, real_canvas, frame, loop_count=1, **kwargs):
                self.received_canvas = real_canvas
                # Pretend SwapOnVSync gave us a fresh back-buffer
                return frame.matrix.SwapOnVSync(real_canvas)

        real = _StubCanvas(width=256, height=64)
        new_real = _StubCanvas(width=256, height=64)
        mock_frame.matrix.SwapOnVSync.return_value = new_real

        wrapper = ScaledCanvas(real, scale=4)
        widget = _Recorder()

        ticker = Ticker(monitors=[], frame=mock_frame)
        out = await ticker._play_widget(wrapper, widget)

        # Same wrapper returned, now pointing at the new back-buffer
        assert out is wrapper
        assert wrapper.real is new_real
        # Widget got the unwrapped real canvas, not the ScaledCanvas
        assert widget.received_canvas is real

    async def test_play_widget_passes_hold_time_to_widget(self, mock_frame):
        """_play_widget threads section_hold_time → widget.play(hold_time=...)."""
        from rgbmatrix import _StubCanvas

        received: dict = {}

        class _HoldCapture:
            async def play(self, real_canvas, frame, loop_count=1, **kwargs):
                received["hold_time"] = kwargs.get("hold_time")
                return frame.matrix.SwapOnVSync(real_canvas)

        plain_canvas = _StubCanvas(width=160, height=16)
        mock_frame.matrix.SwapOnVSync.return_value = _StubCanvas(width=160, height=16)
        widget = _HoldCapture()

        ticker = Ticker(monitors=[], frame=mock_frame)
        await ticker._play_widget(plain_canvas, widget, section_hold_time=8.0)

        assert received.get("hold_time") == 8.0

    async def test_title_then_gif_uses_both_paths(
        self, canvas, mock_frame, make_widget, no_sleep
    ):
        """Title (TickerMessage-like) takes the swap-and-scroll path,
        gif (with play()) takes the play() path. Both run inside the
        same _run_swap call."""

        class _PlayWidget:
            def __init__(self):
                self.played = 0
                self.gif_loops = 1

            def draw(self, canvas, cursor_pos=0, **kwargs):
                return canvas, canvas.width

            async def play(self, real_canvas, frame, loop_count=1, **kwargs):
                self.played += 1
                return real_canvas

        title = make_widget(40)
        gif = _PlayWidget()
        q = asyncio.Queue()
        await q.put(title)
        await q.put(gif)
        ticker = Ticker(monitors=[], frame=mock_frame, notif_queue=q)
        await ticker._run_swap(canvas)

        assert title.draw.called
        assert gif.played == 1


class TestScrollBetween:
    async def test_returns_pos_zero(self, canvas, mock_frame, make_widget, no_sleep):
        outgoing = make_widget(40)
        incoming = make_widget(40)
        ticker = Ticker(monitors=[], frame=mock_frame)
        _, scroll_pos = await ticker._scroll_between(
            canvas,
            outgoing,
            incoming,
            outgoing_scroll_pos=0,
        )
        assert scroll_pos == 0

    async def test_both_widgets_drawn(self, canvas, mock_frame, make_widget, no_sleep):
        outgoing = make_widget(40)
        incoming = make_widget(40)
        ticker = Ticker(monitors=[], frame=mock_frame)
        await ticker._scroll_between(
            canvas,
            outgoing,
            incoming,
        )
        assert outgoing.draw.called
        assert incoming.draw.called

    async def test_outgoing_scroll_pos_used(
        self, canvas, mock_frame, make_widget, no_sleep
    ):
        outgoing_width = 600
        outgoing = make_widget(outgoing_width)
        incoming = make_widget(40)
        ticker = Ticker(monitors=[], frame=mock_frame)
        # Calculate expected scroll pos: -(content_width - canvas.width)
        expected_scroll_pos = -(outgoing_width - canvas.width)
        await ticker._scroll_between(
            canvas,
            outgoing,
            incoming,
            outgoing_scroll_pos=expected_scroll_pos,
        )
        # First draw call should use the scroll pos
        first_call = outgoing.draw.call_args_list[0]
        assert first_call.kwargs["cursor_pos"] == expected_scroll_pos, (
            f"Expected cursor_pos at {expected_scroll_pos} "
            f"(outgoing_width={outgoing_width}, canvas.width={canvas.width})"
        )

    async def test_pauses_and_resumes_frame_on_both_widgets(
        self, canvas, mock_frame, no_sleep
    ):
        """Tripwire: _scroll_between is a transition compositor.
        Frame must be paused on both widgets during the transition
        (matches run_transition's contract) so animated providers
        don't drift their phase by ~166 compositor ticks. After the
        transition ends, frame must be resumed so the held-text loop
        can tick normally."""
        outgoing = mock.Mock()
        outgoing.draw.side_effect = lambda c, cursor_pos=0: (c, cursor_pos + 40)
        incoming = mock.Mock()
        incoming.draw.side_effect = lambda c, cursor_pos=0: (c, cursor_pos + 40)

        ticker = Ticker(monitors=[], frame=mock_frame)
        await ticker._scroll_between(canvas, outgoing, incoming)

        outgoing.pause_frame.assert_called_once()
        outgoing.resume_frame.assert_called_once()
        incoming.pause_frame.assert_called_once()
        incoming.resume_frame.assert_called_once()

    async def test_resets_incoming_frame_counter_during_scroll_in(
        self, canvas, mock_frame, no_sleep
    ):
        """Tripwire: incoming widget's _frame_count must be reset to 0
        before the bullet-scroll transition's first compositor frame
        fires. Without this, on loop iteration 2+ the widget's
        previous-visit-end state (typewriter complete, color_cycle
        mid-rotation, rainbow mid-sweep) renders during the scroll-in
        and snaps when the section begins. Mirrors run_transition's
        same-shape fix.
        """
        incoming = mock.Mock()
        call_log: list[str] = []

        def _draw(c, cursor_pos=0, **kw):
            call_log.append("draw")
            return (c, cursor_pos + 40)

        incoming.draw.side_effect = _draw

        def _reset():
            call_log.append("reset")

        incoming.reset_frame.side_effect = _reset

        outgoing = mock.Mock()
        outgoing.draw.side_effect = lambda c, cursor_pos=0: (c, cursor_pos + 40)

        ticker = Ticker(monitors=[], frame=mock_frame)
        await ticker._scroll_between(canvas, outgoing, incoming)

        assert "draw" in call_log, "incoming.draw never called"
        assert call_log[0] == "reset", (
            f"Expected reset_frame to fire before first draw; "
            f"got call order: {call_log[:5]}. Reset must fire before the "
            f"compositor's first draw of incoming, otherwise "
            f"frame-aware widgets render their previous-visit-end "
            f"state during the bullet-scroll."
        )
        incoming.reset_frame.assert_called_once()

    async def test_resume_frame_called_even_on_exception(
        self, canvas, mock_frame, no_sleep
    ):
        """Resume must be called via try/finally so a swap exception
        mid-transition can't leave widgets stuck in pause."""
        outgoing = mock.Mock()
        outgoing.draw.side_effect = lambda c, cursor_pos=0: (c, cursor_pos + 40)
        incoming = mock.Mock()
        # Force an exception during the loop.
        mock_frame.matrix.SwapOnVSync.side_effect = RuntimeError("simulated")

        ticker = Ticker(monitors=[], frame=mock_frame)
        with pytest.raises(RuntimeError):
            await ticker._scroll_between(canvas, outgoing, incoming)

        outgoing.resume_frame.assert_called_once()
        incoming.resume_frame.assert_called_once()


class TestDrawScrollFrame:
    """Unit tests for the private _draw_scroll_frame helper."""

    def _make_canvas(self, w=64, h=16):
        from rgbmatrix import RGBMatrix, RGBMatrixOptions

        options = RGBMatrixOptions()
        options.cols = w
        options.rows = h
        options.chain_length = 1
        return RGBMatrix(options=options).CreateFrameCanvas()

    def test_clear_start_blacks_out_tail_region(self):
        """Pixels from clear_start to w-1 must be black after _draw_scroll_frame."""
        from unittest.mock import MagicMock

        from led_ticker.ticker import _draw_scroll_frame

        canvas = self._make_canvas(w=64, h=16)
        for y in range(16):
            for x in range(32, 64):
                canvas.SetPixel(x, y, 255, 0, 0)

        outgoing = MagicMock()
        outgoing.draw.return_value = (canvas, 0)
        incoming = MagicMock()
        incoming.draw.return_value = (canvas, 0)

        _draw_scroll_frame(
            canvas,
            outgoing,
            incoming,
            outgoing_pos=-64,
            bullet_x=-64,
            incoming_pos=200,
            clear_start=32,
        )

        for y in range(16):
            for x in range(32, 64):
                assert canvas.get_pixel(x, y) == (
                    0,
                    0,
                    0,
                ), f"pixel ({x},{y}) not cleared"

    def test_clear_start_zero_blacks_entire_canvas(self):
        from unittest.mock import MagicMock

        from led_ticker.ticker import _draw_scroll_frame

        canvas = self._make_canvas(w=64, h=16)
        for y in range(16):
            for x in range(64):
                canvas.SetPixel(x, y, 0, 0, 255)

        outgoing = MagicMock()
        outgoing.draw.return_value = (canvas, 0)
        incoming = MagicMock()
        incoming.draw.return_value = (canvas, 0)

        _draw_scroll_frame(
            canvas,
            outgoing,
            incoming,
            outgoing_pos=-64,
            bullet_x=-64,
            incoming_pos=200,
            clear_start=0,
        )

        for y in range(16):
            for x in range(64):
                assert canvas.get_pixel(x, y) == (
                    0,
                    0,
                    0,
                ), f"pixel ({x},{y}) not cleared"

    def test_no_clear_when_clear_start_equals_width(self):
        """clear_start == w means nothing to clear; existing pixels survive."""
        from unittest.mock import MagicMock

        from led_ticker.ticker import _draw_scroll_frame

        canvas = self._make_canvas(w=64, h=16)
        canvas.SetPixel(63, 0, 255, 0, 0)

        outgoing = MagicMock()
        outgoing.draw.return_value = (canvas, 0)
        incoming = MagicMock()
        incoming.draw.return_value = (canvas, 0)

        _draw_scroll_frame(
            canvas,
            outgoing,
            incoming,
            outgoing_pos=-64,
            bullet_x=-64,
            incoming_pos=200,
            clear_start=64,
        )

        assert canvas.get_pixel(63, 0) == (255, 0, 0)


class TestRunSwapWithScroll:
    async def test_scroll_processes_all_widgets(
        self, canvas, mock_frame, make_widget, no_sleep
    ):
        from led_ticker.transitions import Scroll

        q = asyncio.Queue()
        w1 = make_widget(40)
        w2 = make_widget(40)
        w3 = make_widget(40)
        await q.put(w1)
        await q.put(w2)
        await q.put(w3)
        trans = mock.Mock()
        trans.duration = 4.0
        trans.easing = "linear"
        ticker = Ticker(
            monitors=[],
            frame=mock_frame,
            notif_queue=q,
            transition_config=trans,
            transition_fn=Scroll(),
        )
        await ticker._run_swap(canvas)
        assert w1.draw.called
        assert w2.draw.called
        assert w3.draw.called

    async def test_normal_transition_unaffected(
        self, canvas, mock_frame, make_widget, no_sleep
    ):
        """Non-scroll transitions still use run_transition + hold."""
        from led_ticker.transitions import PushLeft

        q = asyncio.Queue()
        w1 = make_widget(40)
        w2 = make_widget(40)
        await q.put(w1)
        await q.put(w2)
        trans = mock.Mock()
        trans.duration = 0.5
        trans.easing = "linear"
        ticker = Ticker(
            monitors=[],
            frame=mock_frame,
            notif_queue=q,
            transition_config=trans,
            transition_fn=PushLeft(),
        )
        await ticker._run_swap(canvas)
        assert w1.draw.called
        assert w2.draw.called


class TestTickerRunSwap:
    async def test_run_swap_terminates(self, mock_frame, make_widget, no_sleep):
        w1 = make_widget(40)
        q = asyncio.Queue()
        ticker = Ticker(monitors=[w1], frame=mock_frame, notif_queue=q)
        await ticker.run_swap(loop_count=1)
        assert w1.draw.called


class TestTickerRunForeverScroll:
    async def test_default_start_pos_is_canvas_width(
        self, mock_frame, make_widget, no_sleep
    ):
        w = make_widget(content_width=10)
        q = asyncio.Queue()
        ticker = Ticker(monitors=[w], frame=mock_frame, notif_queue=q)
        await ticker.run_forever_scroll(loop_count=1)
        # Widget should have been drawn
        assert w.draw.called

    async def test_start_pos_used_as_value(self, mock_frame, make_widget, no_sleep):
        """start_pos=50 should use 50 as cursor (not just as boolean)."""
        w = make_widget(content_width=10)
        q = asyncio.Queue()
        ticker = Ticker(monitors=[w], frame=mock_frame, notif_queue=q)
        await ticker.run_forever_scroll(loop_count=1, start_pos=50)
        assert w.draw.called


class TestTickerRunInfiniScroll:
    async def test_terminates_with_finite_loop(self, mock_frame, make_widget, no_sleep):
        w = make_widget(content_width=10)
        q = asyncio.Queue()
        ticker = Ticker(monitors=[w], frame=mock_frame, notif_queue=q)
        await ticker.run_infini_scroll(loop_count=1)
        assert w.draw.called


class TestSwapAndScrollUsesResetCanvas:
    @pytest.mark.asyncio
    async def test_no_bg_calls_clear(self, mock_frame):
        import unittest.mock as mock_mod

        canvas = mock_mod.MagicMock()
        canvas.width = 160
        canvas.height = 16
        widget = mock_mod.MagicMock()
        widget.bg_color = None
        widget.draw.return_value = (canvas, 100)

        ticker = Ticker(monitors=[], frame=mock_frame)
        await ticker._swap_and_scroll(canvas, widget, hold_time=0.0)

        canvas.Clear.assert_called()
        canvas.Fill.assert_not_called()

    @pytest.mark.asyncio
    async def test_bg_color_set_calls_fill(self, mock_frame):
        import unittest.mock as mock_mod

        from rgbmatrix.graphics import Color

        canvas = mock_mod.MagicMock()
        canvas.width = 160
        canvas.height = 16
        widget = mock_mod.MagicMock()
        widget.bg_color = Color(70, 80, 90)
        widget.draw.return_value = (canvas, 100)

        ticker = Ticker(monitors=[], frame=mock_frame)
        await ticker._swap_and_scroll(canvas, widget, hold_time=0.0)

        canvas.Clear.assert_not_called()
        canvas.Fill.assert_called_with(70, 80, 90)


class TestSwapAndScrollEngineTick:
    """`_swap_and_scroll`'s held-text branch must call `draw +
    advance_frame` repeatedly during `hold_time` so frame-aware
    widgets actually animate. The scroll branch must also call
    advance_frame per tick."""

    @pytest.mark.asyncio
    async def test_held_text_calls_draw_multiple_times_during_hold(
        self, swapping_frame
    ):
        """Held text → engine ticks at 50ms; draw fires ~hold_time/0.05
        times. Spy on widget.draw to assert it does."""
        from rgbmatrix import _StubCanvas

        class _SpyWidget:
            def __init__(self):
                self.draw_calls = 0
                self.advance_calls = 0
                self._frame_count = 0
                self._frame_paused = False

            def draw(self, canvas, cursor_pos=0, **kwargs):
                self.draw_calls += 1
                # Return cursor_pos < canvas.width so it stays in held branch
                return canvas, 5

            def advance_frame(self, *, visit_id=None):
                self.advance_calls += 1
                self._frame_count += 1

            def reset_frame(self):
                self._frame_count = 0

            @property
            def bg_color(self):
                return None

        widget = _SpyWidget()
        canvas = _StubCanvas(width=160, height=16)
        swapping_frame.matrix.SwapOnVSync.return_value = _StubCanvas(
            width=160, height=16
        )

        # hold_time = 0.5s with tick_ms = 50 → ~10 ticks
        ticker = Ticker(monitors=[], frame=swapping_frame)
        await ticker._swap_and_scroll(canvas, widget, hold_time=0.5)

        # Allow some slop; expect roughly 10 draws / advances
        assert widget.draw_calls >= 8
        assert widget.advance_calls >= 8

    @pytest.mark.asyncio
    async def test_scrolling_text_advances_frame_per_tick(self, swapping_frame):
        """Scroll branch also calls advance_frame per tick so providers
        animate during scroll-to-end."""
        from rgbmatrix import _StubCanvas

        class _SpyWidget:
            def __init__(self):
                self.draw_calls = 0
                self.advance_calls = 0
                self._frame_count = 0
                self._frame_paused = False

            def draw(self, canvas, cursor_pos=0, **kwargs):
                self.draw_calls += 1
                # Return cursor_pos > canvas.width to trigger scroll
                return canvas, 200

            def advance_frame(self, *, visit_id=None):
                self.advance_calls += 1
                self._frame_count += 1

            def reset_frame(self):
                self._frame_count = 0

            @property
            def bg_color(self):
                return None

            @property
            def padding(self):
                return 0

        widget = _SpyWidget()
        canvas = _StubCanvas(width=160, height=16)
        swapping_frame.matrix.SwapOnVSync.return_value = _StubCanvas(
            width=160, height=16
        )

        ticker = Ticker(monitors=[], frame=swapping_frame, scroll_speed=0.001)
        await ticker._swap_and_scroll(canvas, widget, hold_time=0.05)

        # Should have many draws (one per scroll px) AND advance_frame per tick
        assert widget.advance_calls > 0
        assert (
            widget.advance_calls == widget.draw_calls
            or widget.advance_calls >= widget.draw_calls - 2
        )

    @pytest.mark.asyncio
    async def test_widget_without_advance_frame_method_does_not_crash(
        self, swapping_frame
    ):
        """Older widgets that don't yet have the _FrameAware mixin must
        not crash _swap_and_scroll. The orchestrator uses hasattr or
        a duck-type check."""
        from rgbmatrix import _StubCanvas

        class _NoAdvance:
            def draw(self, canvas, cursor_pos=0, **kwargs):
                return canvas, 5

            @property
            def bg_color(self):
                return None

        widget = _NoAdvance()
        canvas = _StubCanvas(width=160, height=16)
        swapping_frame.matrix.SwapOnVSync.return_value = _StubCanvas(
            width=160, height=16
        )

        # Should complete without AttributeError
        ticker = Ticker(monitors=[], frame=swapping_frame)
        await ticker._swap_and_scroll(canvas, widget, hold_time=0.1)


class TestShowOneResetsFrame:
    """`_show_one` must call `widget.reset_frame()` at the start of each
    visit so frame-aware effects (typewriter, color providers) restart
    on every visit instead of carrying state across loop iterations."""

    async def test_reset_frame_called_on_widget_with_mixin(
        self, swapping_frame, no_sleep
    ):
        from rgbmatrix import _StubCanvas

        class _SpyWidget:
            def __init__(self):
                self._frame_count = 99  # pretend a previous visit happened
                self._frame_paused = False
                self.reset_called = False

            def draw(self, canvas, cursor_pos=0, **kwargs):
                return canvas, 5

            def reset_frame(self):
                self._frame_count = 0
                self.reset_called = True

            def advance_frame(self, *, visit_id=None):
                self._frame_count += 1

            @property
            def bg_color(self):
                return None

        widget = _SpyWidget()
        canvas = _StubCanvas(width=160, height=16)
        swapping_frame.matrix.SwapOnVSync.return_value = _StubCanvas(
            width=160, height=16
        )

        ticker = Ticker(monitors=[], frame=swapping_frame)
        await ticker._show_one(canvas, widget, hold_time=0.1)

        assert widget.reset_called

    async def test_widget_without_reset_frame_does_not_crash(
        self, swapping_frame, no_sleep
    ):
        """Defensive: widgets without _FrameAware mixin must not crash."""
        from rgbmatrix import _StubCanvas

        class _NoMixin:
            def draw(self, canvas, cursor_pos=0, **kwargs):
                return canvas, 5

            @property
            def bg_color(self):
                return None

        widget = _NoMixin()
        canvas = _StubCanvas(width=160, height=16)
        swapping_frame.matrix.SwapOnVSync.return_value = _StubCanvas(
            width=160, height=16
        )

        # Should complete without AttributeError
        ticker = Ticker(monitors=[], frame=swapping_frame)
        await ticker._show_one(canvas, widget, hold_time=0.1)

    async def test_show_one_calls_reset_frame_unconditionally(
        self, swapping_frame, no_sleep
    ):
        """`_show_one` always calls `reset_frame()` — the per-effect
        semantics (continuous vs restart) live inside
        `_FrameAware.reset_frame`, not in the engine gate.
        Replacing the old `test_show_one_skips_reset_when_border_is_continuous`
        which tested the removed `_should_reset_frame` gate."""
        from rgbmatrix import _StubCanvas

        class _ContinuousBorder:
            restart_on_visit = False

        class _SpyWidget:
            def __init__(self):
                self._frame_count = 42
                self._frame_paused = False
                self.reset_called = False
                self.border = _ContinuousBorder()

            def draw(self, canvas, cursor_pos=0, **kwargs):
                return canvas, 5

            def reset_frame(self):
                self._frame_count = 0
                self.reset_called = True

            def advance_frame(self, *, visit_id=None):
                self._frame_count += 1

            @property
            def bg_color(self):
                return None

        widget = _SpyWidget()
        canvas = _StubCanvas(width=160, height=16)
        swapping_frame.matrix.SwapOnVSync.return_value = _StubCanvas(
            width=160, height=16
        )

        ticker = Ticker(monitors=[], frame=swapping_frame)
        await ticker._show_one(canvas, widget, hold_time=0.1)

        # reset_frame() is always called — per-effect semantics live
        # inside _FrameAware.reset_frame, not in _show_one
        assert widget.reset_called, (
            "_show_one must call reset_frame() unconditionally; "
            "per-effect continuity is handled by reset_frame() itself"
        )

    async def test_show_one_resets_for_typewriter_widget(
        self, swapping_frame, no_sleep
    ):
        """Widget with only Typewriter (default restart_on_visit=True
        behavior) should still get reset on entry — preserves
        today's retype-each-loop semantics."""
        from rgbmatrix import _StubCanvas

        class _TypewriterAnim:
            restart_on_visit = True  # explicit default

        class _SpyWidget:
            def __init__(self):
                self._frame_count = 99
                self._frame_paused = False
                self.reset_called = False
                self.animation = _TypewriterAnim()

            def draw(self, canvas, cursor_pos=0, **kwargs):
                return canvas, 5

            def reset_frame(self):
                self._frame_count = 0
                self.reset_called = True

            def advance_frame(self, *, visit_id=None):
                self._frame_count += 1

            @property
            def bg_color(self):
                return None

        widget = _SpyWidget()
        canvas = _StubCanvas(width=160, height=16)
        swapping_frame.matrix.SwapOnVSync.return_value = _StubCanvas(
            width=160, height=16
        )

        ticker = Ticker(monitors=[], frame=swapping_frame)
        await ticker._show_one(canvas, widget, hold_time=0.1)

        assert widget.reset_called, (
            "Typewriter (restart_on_visit=True) must still trigger "
            "the reset — preserves retype-each-loop semantics"
        )


class TestTypewriterPlusRainbowBorderComposition:
    """Per-effect counters let a widget with both Typewriter
    (restart=True) and RainbowChaseBorder (restart=False) get the
    correct behavior on `loop_count > 1`: typewriter retypes each
    loop AND the border chase phase advances continuously.

    This is the win the per-effect counter refactor was designed
    to deliver. Replaces `TestShouldResetFrameComposition` from
    PR #11, which asserted the OPPOSITE (continuous wins, typewriter
    doesn't retype) — that was the documented tradeoff under the
    old shared-counter model."""

    async def test_typewriter_counter_resets_per_loop(self, swapping_frame, no_sleep):
        """The animation's per-effect counter zeros on every visit
        regardless of what other effects are present."""
        from rgbmatrix import _StubCanvas

        class _Typewriter:
            restart_on_visit = True

        class _RainbowBorder:
            restart_on_visit = False

        class _SpyWidget:
            def __init__(self):
                self._frame_count = 0
                self._frame_paused = False
                self._effect_frames = {}
                self.animation = _Typewriter()
                self.border = _RainbowBorder()

            def draw(self, canvas, cursor_pos=0, **kwargs):
                return canvas, 5

            def advance_frame(self, *, visit_id=None):
                if self._frame_paused:
                    return
                self._frame_count += 1
                self._effect_frames["animation"] = (
                    self._effect_frames.get("animation", 0) + 1
                )
                self._effect_frames["border"] = self._effect_frames.get("border", 0) + 1

            def reset_frame(self):
                self._frame_count = 0
                # Typewriter: restart_on_visit=True → zero
                self._effect_frames["animation"] = 0
                # Rainbow border: restart_on_visit=False → unchanged
                # (intentionally not in this dispatch)

            @property
            def bg_color(self):
                return None

        widget = _SpyWidget()
        canvas = _StubCanvas(width=160, height=16)
        swapping_frame.matrix.SwapOnVSync.return_value = _StubCanvas(
            width=160, height=16
        )

        # Run two visits in a row (simulates loop_count > 1)
        ticker = Ticker(monitors=[], frame=swapping_frame)
        await ticker._show_one(canvas, widget, hold_time=0.1)
        animation_frame_after_iter1 = widget._effect_frames["animation"]
        border_frame_after_iter1 = widget._effect_frames["border"]
        assert animation_frame_after_iter1 > 0
        assert border_frame_after_iter1 > 0

        await ticker._show_one(canvas, widget, hold_time=0.1)
        # Typewriter counter zeroed at the start of iter 2, then
        # advanced through iter 2 — should be smaller than the
        # accumulated value from iter 1
        assert widget._effect_frames["animation"] < (
            animation_frame_after_iter1 + border_frame_after_iter1
        )
        # Border counter kept climbing — should be GREATER than iter 1's value
        assert widget._effect_frames["border"] > border_frame_after_iter1

    async def test_widget_frame_count_still_resets(self, swapping_frame, no_sleep):
        """Back-compat: `widget._frame_count` retains today's
        per-visit reset semantic regardless of effect composition.
        Tests that read `_frame_count` directly keep working."""
        from rgbmatrix import _StubCanvas

        class _RainbowBorder:
            restart_on_visit = False

        class _SpyWidget:
            def __init__(self):
                self._frame_count = 99  # mid-something
                self._frame_paused = False
                self._effect_frames = {}
                self.border = _RainbowBorder()

            def draw(self, canvas, cursor_pos=0, **kwargs):
                return canvas, 5

            def advance_frame(self, *, visit_id=None):
                if self._frame_paused:
                    return
                self._frame_count += 1
                self._effect_frames["border"] = self._effect_frames.get("border", 0) + 1

            def reset_frame(self):
                self._frame_count = 0  # primary always resets

            @property
            def bg_color(self):
                return None

        widget = _SpyWidget()
        canvas = _StubCanvas(width=160, height=16)
        swapping_frame.matrix.SwapOnVSync.return_value = _StubCanvas(
            width=160, height=16
        )

        ticker = Ticker(monitors=[], frame=swapping_frame)
        await ticker._show_one(canvas, widget, hold_time=0.1)
        # Iter 2 should see _frame_count reset to 0 at entry, then
        # climbing through the iter — small value, NOT 99 + N
        assert widget._frame_count < 99

    async def test_continuous_border_phase_uninterrupted(
        self, swapping_frame, no_sleep
    ):
        """Rainbow border's per-effect counter is monotonically
        increasing across visits. The chase phase never snaps back."""
        from rgbmatrix import _StubCanvas

        class _RainbowBorder:
            restart_on_visit = False

        class _SpyWidget:
            def __init__(self):
                self._frame_count = 0
                self._frame_paused = False
                self._effect_frames = {}
                self.border = _RainbowBorder()

            def draw(self, canvas, cursor_pos=0, **kwargs):
                return canvas, 5

            def advance_frame(self, *, visit_id=None):
                if self._frame_paused:
                    return
                self._frame_count += 1
                self._effect_frames["border"] = self._effect_frames.get("border", 0) + 1

            def reset_frame(self):
                self._frame_count = 0
                # Border opted out → don't touch its counter

            @property
            def bg_color(self):
                return None

        widget = _SpyWidget()
        canvas = _StubCanvas(width=160, height=16)
        swapping_frame.matrix.SwapOnVSync.return_value = _StubCanvas(
            width=160, height=16
        )

        ticker = Ticker(monitors=[], frame=swapping_frame)
        await ticker._show_one(canvas, widget, hold_time=0.1)
        border_after_iter1 = widget._effect_frames["border"]

        await ticker._show_one(canvas, widget, hold_time=0.1)
        border_after_iter2 = widget._effect_frames["border"]

        # Strictly increasing: iter 2 added more ticks on top of iter 1
        assert border_after_iter2 > border_after_iter1


class TestScrollDriftCompensation:
    """Scroll loops must subtract elapsed draw+swap time from each sleep
    so the actual cadence matches scroll_speed regardless of frame work (S2).
    """

    async def test_scroll_one_by_one_subtracts_work_time(
        self, canvas, mock_frame, monkeypatch
    ):
        """When each tick's draw+swap takes 20ms, sleep should be
        max(0, scroll_speed - 0.020), not the raw scroll_speed."""
        sleep_calls: list[float] = []

        async def _record(seconds: float) -> None:
            sleep_calls.append(seconds)

        monkeypatch.setattr("led_ticker.ticker.asyncio.sleep", _record)

        # Simulate 20ms of work per tick: t0 = 0.000, loop.time()-t0 = 0.020.
        # Each tick consumes two values from the iterator.
        tick_times = iter([0.000, 0.020] * 200)
        mock_loop = mock.Mock()
        mock_loop.time.side_effect = lambda: next(tick_times)
        monkeypatch.setattr(
            "led_ticker.ticker.asyncio.get_running_loop", lambda: mock_loop
        )

        scroll_speed = 0.05
        widget = mock.Mock()
        # Widget is 5px wide; final_pos < 0 once pos goes negative
        widget.draw.side_effect = lambda c, cursor_pos=0, **kw: (
            c,
            cursor_pos + 5,
        )

        queue = asyncio.Queue()
        await queue.put(widget)

        ticker = Ticker(
            monitors=[], frame=mock_frame, scroll_speed=scroll_speed, notif_queue=queue
        )
        await ticker._scroll_one_by_one(canvas)

        expected = scroll_speed - 0.020  # 0.030
        assert sleep_calls, "no sleep calls recorded"
        for s in sleep_calls:
            assert (
                abs(s - expected) < 1e-9
            ), f"expected drift-compensated sleep {expected}s, got {s}"

    async def test_scroll_one_by_one_clamps_to_zero_on_overrun(
        self, canvas, mock_frame, monkeypatch
    ):
        """When work takes longer than scroll_speed, sleep is clamped to 0
        rather than going negative."""
        sleep_calls: list[float] = []

        async def _record(seconds: float) -> None:
            sleep_calls.append(seconds)

        monkeypatch.setattr("led_ticker.ticker.asyncio.sleep", _record)

        # Work takes 80ms per tick — longer than scroll_speed=0.05
        tick_times = iter([0.000, 0.080] * 200)
        mock_loop = mock.Mock()
        mock_loop.time.side_effect = lambda: next(tick_times)
        monkeypatch.setattr(
            "led_ticker.ticker.asyncio.get_running_loop", lambda: mock_loop
        )

        widget = mock.Mock()
        widget.draw.side_effect = lambda c, cursor_pos=0, **kw: (c, cursor_pos + 5)

        queue = asyncio.Queue()
        await queue.put(widget)

        ticker = Ticker(
            monitors=[], frame=mock_frame, scroll_speed=0.05, notif_queue=queue
        )
        await ticker._scroll_one_by_one(canvas)

        assert sleep_calls, "no sleep calls recorded"
        for s in sleep_calls:
            assert s == 0.0, f"expected 0.0 (clamped), got {s}"
