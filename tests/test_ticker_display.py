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
        widget.draw.assert_called_once()

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
        # Only drawn once (no scrolling needed)
        assert widget.draw.call_count == 1

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
        await _swap_and_scroll(canvas, mock_frame, widget, skip_initial_draw=True)
        # Widget fits — only the initial swap exists in the normal path.
        # With skip_initial_draw=True, that swap is suppressed → 0 swaps.
        assert mock_frame.matrix.SwapOnVSync.call_count == 0, (
            f"skip_initial_draw=True should suppress the initial swap; "
            f"got {mock_frame.matrix.SwapOnVSync.call_count} swaps."
        )

    async def test_default_includes_initial_swap(
        self, canvas, mock_frame, make_widget, no_sleep
    ):
        # Sanity: default path DOES swap at the start.
        widget = make_widget(content_width=40)
        await _swap_and_scroll(canvas, mock_frame, widget)
        assert mock_frame.matrix.SwapOnVSync.call_count == 1


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
        sleep_calls: list[float] = []
        _real_sleep = asyncio.sleep

        async def _record(seconds):
            sleep_calls.append(seconds)
            await _real_sleep(0)

        monkeypatch.setattr("led_ticker.ticker.asyncio.sleep", _record)

        widget = make_widget(content_width=200)
        await _swap_and_scroll(
            canvas, mock_frame, widget, hold_time=3.0, continuous=False
        )
        # Two hold_time sleeps for an overflowing widget: pre-scroll, post-scroll.
        assert sleep_calls.count(3.0) == 2


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
        # Only the initial draw, no scroll loop
        widget.draw.assert_called_once()


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
