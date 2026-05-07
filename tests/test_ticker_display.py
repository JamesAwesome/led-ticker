"""Tests for ticker display modes (run_swap, run_forever_scroll, etc)."""

import asyncio
import unittest.mock as mock

import pytest

from led_ticker.scaled_canvas import ScaledCanvas
from led_ticker.ticker import (
    Ticker,
    _play_widget,
    _run_swap,
    _scroll_and_delay,
    _scroll_between,
    _show_one,
    _swap_and_scroll,
)


@pytest.fixture
def no_sleep(monkeypatch):
    """Patch asyncio.sleep in ticker module to be instant."""
    _real_sleep = asyncio.sleep

    async def _fast(seconds):
        await _real_sleep(0)  # yield control but don't wait

    monkeypatch.setattr("led_ticker.ticker.asyncio.sleep", _fast)


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
        result_canvas, pos, scroll_pos = await _swap_and_scroll(
            canvas, mock_frame, widget
        )
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
        await _swap_and_scroll(canvas, mock_frame, widget)
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
        await _swap_and_scroll(canvas, mock_frame, widget)
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
        await _swap_and_scroll(canvas, mock_frame, widget)
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
        widget = make_widget(content_width=600)
        _, cursor_pos, scroll_pos = await _swap_and_scroll(canvas, mock_frame, widget)
        assert cursor_pos == 600
        # stop_pos = -(600 - 160) = -440
        assert scroll_pos == -440

    async def test_scroll_pos_zero_for_short_text(
        self,
        canvas,
        mock_frame,
        make_widget,
        no_sleep,
    ):
        """Short text that fits on screen returns scroll_pos=0."""
        widget = make_widget(content_width=100)
        _, _, scroll_pos = await _swap_and_scroll(canvas, mock_frame, widget)
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
            _, _, scroll_pos = await _swap_and_scroll(canvas, mock_frame, widget)
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
        widget = make_widget(content_width=600)
        widget.padding = 6  # simulate real widget padding
        _, _, scroll_pos = await _swap_and_scroll(canvas, mock_frame, widget)
        # stop_pos = -(600 - 160) + 6 = -434
        assert scroll_pos == -434

    async def test_stop_pos_no_padding_attribute(
        self,
        canvas,
        mock_frame,
        make_widget,
        no_sleep,
    ):
        """Widget without padding attribute defaults to 0 adjustment."""
        widget = make_widget(content_width=600)
        _, _, scroll_pos = await _swap_and_scroll(canvas, mock_frame, widget)
        # stop_pos = -(600 - 160) - 0 = -440
        assert scroll_pos == -440


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
        await _swap_and_scroll(
            canvas, mock_frame, widget, skip_initial_draw=True, hold_time=0.05
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
        await _swap_and_scroll(canvas, mock_frame, widget, hold_time=0.05)
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
        await _swap_and_scroll(
            canvas, mock_frame, widget, hold_time=3.0, continuous=True
        )
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

        widget = make_widget(content_width=200)
        await _swap_and_scroll(
            canvas, mock_frame, widget, hold_time=0.1, continuous=False
        )
        # With the tick loop, hold_time=0.1s produces 2 ticks (max(1, 100//50))
        # per hold phase, each sleeping ENGINE_TICK_MS/1000 = 0.05s.
        # For an overflow widget: pre-scroll hold + post-scroll hold → 4 tick sleeps
        # plus per-pixel scroll sleeps. Verify tick-sized sleeps appear (not the
        # old bare hold_time sleep).
        tick_s = ENGINE_TICK_MS / 1000
        assert tick_s in sleep_calls, (
            f"Expected tick-sized sleeps ({tick_s}s) in sleep_calls; "
            f"got {sleep_calls}"
        )
        # No single sleep should equal the full hold_time (old bare sleep gone).
        assert (
            0.1 not in sleep_calls
        ), f"hold_time bare sleep must not appear; sleep_calls={sleep_calls}"


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
        await _swap_and_scroll(canvas, swapping_frame, widget)

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
        _, pos = await _scroll_and_delay(
            canvas, mock_frame, widget, delay=0, cursor_pos=5
        )
        assert pos > 0
        assert widget.draw.call_count >= 5

    async def test_cursor_zero_no_scroll_loop(
        self, canvas, mock_frame, make_widget, no_sleep
    ):
        widget = make_widget(content_width=40)
        _, pos = await _scroll_and_delay(
            canvas, mock_frame, widget, delay=0, cursor_pos=0
        )
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

        def _advance():
            widget._advance_frame_count += 1

        widget.advance_frame.side_effect = _advance

        # cursor_pos=5 → 5 scroll-in iterations + 1 post-scroll tick (delay=0).
        await _scroll_and_delay(canvas, mock_frame, widget, delay=0, cursor_pos=5)

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

        def _advance():
            widget._advance_frame_count += 1

        widget.advance_frame.side_effect = _advance

        # delay=0.5s @ ENGINE_TICK_MS=50ms → 10 ticks expected.
        await _scroll_and_delay(canvas, mock_frame, widget, delay=0.5, cursor_pos=0)

        assert widget._advance_frame_count == 10


class TestScrollOneByOne:
    """forever_scroll mode with queue length 1 routes through
    _scroll_one_by_one. The redraw loop must advance frame per tick
    or animated providers (rainbow, color_cycle) freeze."""

    async def test_advances_frame_per_tick(self, canvas, mock_frame, no_sleep):
        """Hardware bug: smoke §17 (RSS feed + rainbow) rendered as
        a static gradient because _scroll_one_by_one's while loop
        never advanced the widget's frame counter."""
        from led_ticker.ticker import _scroll_one_by_one

        widget = mock.Mock()
        # Widget is 5 wide; scrolls until final_pos < 0. Starting at
        # cursor_pos=0, final_pos = 5 first tick, then cursor_pos
        # decrements toward -∞. Loop breaks when widget.draw returns
        # final_pos < 0 AND queue is empty.
        widget.draw.side_effect = lambda c, cursor_pos=0: (c, cursor_pos + 5)
        widget._advance_frame_count = 0

        def _advance():
            widget._advance_frame_count += 1

        widget.advance_frame.side_effect = _advance

        queue = asyncio.Queue()
        await queue.put(widget)

        await _scroll_one_by_one(canvas, mock_frame, queue, scroll_speed=0)

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
        from led_ticker.ticker import _scroll_side_by_side

        draw_positions: list[int] = []
        widget = mock.Mock()

        def _draw(c, cursor_pos=0):
            draw_positions.append(cursor_pos)
            return (c, cursor_pos + 30)

        widget.draw.side_effect = _draw
        widget.bg_color = None

        queue = asyncio.Queue()
        await queue.put(widget)

        await _scroll_side_by_side(
            canvas, mock_frame, queue, scroll_speed=0, hold_at_end=0.2
        )

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
        from led_ticker.ticker import _scroll_side_by_side

        widget = mock.Mock()
        widget.draw.side_effect = lambda c, cursor_pos=0: (c, cursor_pos + 30)
        widget._advance_frame_count = 0
        widget.bg_color = None

        def _advance():
            widget._advance_frame_count += 1

        widget.advance_frame.side_effect = _advance

        queue = asyncio.Queue()
        await queue.put(widget)

        # hold_at_end=0.5s @ ENGINE_TICK_MS=50ms → ≥10 hold ticks
        # expected, plus a small number of scroll-in ticks before
        # the hold begins.
        await _scroll_side_by_side(
            canvas, mock_frame, queue, scroll_speed=0, hold_at_end=0.5
        )

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
        from led_ticker.ticker import _scroll_side_by_side

        def _make_widget(width: int):
            w = mock.Mock()
            w.draw.side_effect = lambda c, cursor_pos=0: (c, cursor_pos + width)
            w._advance_frame_count = 0
            w.bg_color = None

            def _advance():
                w._advance_frame_count += 1

            w.advance_frame.side_effect = _advance
            return w

        w1 = _make_widget(40)
        w2 = _make_widget(40)
        queue = asyncio.Queue()
        await queue.put(w1)
        await queue.put(w2)

        await _scroll_side_by_side(
            canvas, mock_frame, queue, scroll_speed=0, hold_at_end=0
        )

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
        await _run_swap(canvas, mock_frame, q)
        assert w1.draw.called
        assert w2.draw.called

    async def test_single_widget(self, canvas, mock_frame, make_widget, no_sleep):
        q = asyncio.Queue()
        w = make_widget(40)
        await q.put(w)
        await _run_swap(canvas, mock_frame, q)
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

            async def play(self, real_canvas, frame, loop_count=1):
                self.play_calls.append(loop_count)
                return real_canvas

        widget = _PlayOnly()
        q = asyncio.Queue()
        await q.put(widget)
        await _run_swap(canvas, mock_frame, q)

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

            async def play(self, real_canvas, frame, loop_count=1):
                return frame.matrix.SwapOnVSync(real_canvas)

        real = _StubCanvas(width=256, height=64)
        mock_frame.matrix.SwapOnVSync.return_value = _StubCanvas(width=256, height=64)
        widget = _Recorder()

        # Wrapped (bigsign): scale should propagate
        await _play_widget(ScaledCanvas(real, scale=4), mock_frame, widget)
        assert widget._logical_scale == 4

        # Unwrapped (small sign): scale should reset to 1
        await _play_widget(_StubCanvas(width=160, height=16), mock_frame, widget)
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

            async def play(self, real_canvas, frame, loop_count=1):
                self.received_canvas = real_canvas
                # Pretend SwapOnVSync gave us a fresh back-buffer
                return frame.matrix.SwapOnVSync(real_canvas)

        real = _StubCanvas(width=256, height=64)
        new_real = _StubCanvas(width=256, height=64)
        mock_frame.matrix.SwapOnVSync.return_value = new_real

        wrapper = ScaledCanvas(real, scale=4)
        widget = _Recorder()

        out = await _play_widget(wrapper, mock_frame, widget)

        # Same wrapper returned, now pointing at the new back-buffer
        assert out is wrapper
        assert wrapper.real is new_real
        # Widget got the unwrapped real canvas, not the ScaledCanvas
        assert widget.received_canvas is real

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

            async def play(self, real_canvas, frame, loop_count=1):
                self.played += 1
                return real_canvas

        title = make_widget(40)
        gif = _PlayWidget()
        q = asyncio.Queue()
        await q.put(title)
        await q.put(gif)
        await _run_swap(canvas, mock_frame, q)

        assert title.draw.called
        assert gif.played == 1


class TestScrollBetween:
    async def test_returns_pos_zero(self, canvas, mock_frame, make_widget, no_sleep):
        outgoing = make_widget(40)
        incoming = make_widget(40)
        _, scroll_pos = await _scroll_between(
            canvas,
            mock_frame,
            outgoing,
            incoming,
            outgoing_scroll_pos=0,
        )
        assert scroll_pos == 0

    async def test_both_widgets_drawn(self, canvas, mock_frame, make_widget, no_sleep):
        outgoing = make_widget(40)
        incoming = make_widget(40)
        await _scroll_between(
            canvas,
            mock_frame,
            outgoing,
            incoming,
        )
        assert outgoing.draw.called
        assert incoming.draw.called

    async def test_outgoing_scroll_pos_used(
        self, canvas, mock_frame, make_widget, no_sleep
    ):
        outgoing = make_widget(600)
        incoming = make_widget(40)
        await _scroll_between(
            canvas,
            mock_frame,
            outgoing,
            incoming,
            outgoing_scroll_pos=-440,
        )
        # First draw call should use the scroll pos
        first_call = outgoing.draw.call_args_list[0]
        assert first_call.kwargs["cursor_pos"] == -440

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

        await _scroll_between(canvas, mock_frame, outgoing, incoming)

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
        incoming._frame_count = 99  # simulate previous-visit-end state
        seen_frame_counts: list[int] = []

        def _draw(c, cursor_pos=0, **kw):
            seen_frame_counts.append(incoming._frame_count)
            return (c, cursor_pos + 40)

        incoming.draw.side_effect = _draw

        def _reset():
            incoming._frame_count = 0

        incoming.reset_frame.side_effect = _reset

        outgoing = mock.Mock()
        outgoing.draw.side_effect = lambda c, cursor_pos=0: (c, cursor_pos + 40)

        await _scroll_between(canvas, mock_frame, outgoing, incoming)

        assert seen_frame_counts, "incoming.draw never called"
        assert all(f == 0 for f in seen_frame_counts), (
            f"Expected _frame_count == 0 throughout _scroll_between; "
            f"got {seen_frame_counts}. Reset must fire before the "
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

        with pytest.raises(RuntimeError):
            await _scroll_between(canvas, mock_frame, outgoing, incoming)

        outgoing.resume_frame.assert_called_once()
        incoming.resume_frame.assert_called_once()


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
        trans.transition_obj = Scroll()
        trans.duration = 4.0
        trans.easing = "linear"
        await _run_swap(canvas, mock_frame, q, transition=trans)
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
        trans.transition_obj = PushLeft()
        trans.duration = 0.5
        trans.easing = "linear"
        await _run_swap(canvas, mock_frame, q, transition=trans)
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

        from led_ticker.ticker import _swap_and_scroll

        canvas = mock_mod.MagicMock()
        canvas.width = 160
        canvas.height = 16
        widget = mock_mod.MagicMock()
        widget.bg_color = None
        widget.draw.return_value = (canvas, 100)

        await _swap_and_scroll(canvas, mock_frame, widget, hold_time=0.0)

        canvas.Clear.assert_called()
        canvas.Fill.assert_not_called()

    @pytest.mark.asyncio
    async def test_bg_color_set_calls_fill(self, mock_frame):
        import unittest.mock as mock_mod

        from rgbmatrix.graphics import Color

        from led_ticker.ticker import _swap_and_scroll

        canvas = mock_mod.MagicMock()
        canvas.width = 160
        canvas.height = 16
        widget = mock_mod.MagicMock()
        widget.bg_color = Color(70, 80, 90)
        widget.draw.return_value = (canvas, 100)

        await _swap_and_scroll(canvas, mock_frame, widget, hold_time=0.0)

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

        from led_ticker.ticker import _swap_and_scroll

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

            def advance_frame(self):
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
        await _swap_and_scroll(canvas, swapping_frame, widget, hold_time=0.5)

        # Allow some slop; expect roughly 10 draws / advances
        assert widget.draw_calls >= 8
        assert widget.advance_calls >= 8
        assert widget._frame_count >= 8

    @pytest.mark.asyncio
    async def test_scrolling_text_advances_frame_per_tick(self, swapping_frame):
        """Scroll branch also calls advance_frame per tick so providers
        animate during scroll-to-end."""
        from rgbmatrix import _StubCanvas

        from led_ticker.ticker import _swap_and_scroll

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

            def advance_frame(self):
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

        await _swap_and_scroll(
            canvas, swapping_frame, widget, hold_time=0.05, scroll_speed=0.001
        )

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

        from led_ticker.ticker import _swap_and_scroll

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
        await _swap_and_scroll(canvas, swapping_frame, widget, hold_time=0.1)


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

            def advance_frame(self):
                self._frame_count += 1

            @property
            def bg_color(self):
                return None

        widget = _SpyWidget()
        canvas = _StubCanvas(width=160, height=16)
        swapping_frame.matrix.SwapOnVSync.return_value = _StubCanvas(
            width=160, height=16
        )

        await _show_one(canvas, swapping_frame, widget, hold_time=0.1)

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
        await _show_one(canvas, swapping_frame, widget, hold_time=0.1)


class TestShouldResetFrame:
    """`_should_reset_frame()` returns True iff every effect on the
    widget either has `restart_on_visit = True` (the default) or
    omits the attribute entirely. ANY effect with explicit
    `restart_on_visit = False` blocks the reset — favors continuity
    for animated chases that should advance smoothly across
    loop_count boundaries."""

    def test_no_effects_resets(self):
        """Widget with no effect attributes — falls through every
        check, returns True."""
        from led_ticker.ticker import _should_reset_frame

        class _Widget:
            pass

        assert _should_reset_frame(_Widget()) is True

    def test_continuous_color_provider_blocks_reset(self):
        """font_color with `restart_on_visit = False` → False."""
        from led_ticker.ticker import _should_reset_frame

        class _Provider:
            restart_on_visit = False

        class _Widget:
            font_color = _Provider()

        assert _should_reset_frame(_Widget()) is False

    def test_continuous_border_blocks_reset(self):
        """border with `restart_on_visit = False` → False."""
        from led_ticker.ticker import _should_reset_frame

        class _Border:
            restart_on_visit = False

        class _Widget:
            border = _Border()

        assert _should_reset_frame(_Widget()) is False

    def test_typewriter_alone_resets(self):
        """animation with `restart_on_visit = True` (default
        behavior for Typewriter) and no other effects → True."""
        from led_ticker.ticker import _should_reset_frame

        class _Animation:
            restart_on_visit = True

        class _Widget:
            animation = _Animation()

        assert _should_reset_frame(_Widget()) is True

    def test_unknown_effect_class_keeps_default_true(self):
        """Effect that simply doesn't set restart_on_visit → uses
        getattr default of True. Back-compat path for any third-
        party / unknown effect class."""
        from led_ticker.ticker import _should_reset_frame

        class _CustomEffect:
            pass  # no restart_on_visit attribute

        class _Widget:
            font_color = _CustomEffect()

        assert _should_reset_frame(_Widget()) is True
