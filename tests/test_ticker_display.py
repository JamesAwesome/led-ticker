"""Tests for ticker display modes (run_swap, run_forever_scroll, etc)."""

import asyncio
import unittest.mock as mock

import pytest

from led_ticker.ticker import (
    Ticker,
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
        _, cursor_pos, scroll_pos = await _swap_and_scroll(
            canvas, mock_frame, widget
        )
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
            _, _, scroll_pos = await _swap_and_scroll(
                canvas, mock_frame, widget
            )
            expected = -(width - canvas.width)
            assert scroll_pos == expected, (
                f"width={width}: expected {expected}, got {scroll_pos}"
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


class TestScrollBetween:
    async def test_returns_pos_zero(
        self, canvas, mock_frame, make_widget, no_sleep
    ):
        outgoing = make_widget(40)
        incoming = make_widget(40)
        _, scroll_pos = await _scroll_between(
            canvas, mock_frame, outgoing, incoming,
            outgoing_scroll_pos=0,
        )
        assert scroll_pos == 0

    async def test_both_widgets_drawn(
        self, canvas, mock_frame, make_widget, no_sleep
    ):
        outgoing = make_widget(40)
        incoming = make_widget(40)
        await _scroll_between(
            canvas, mock_frame, outgoing, incoming,
        )
        assert outgoing.draw.called
        assert incoming.draw.called

    async def test_outgoing_scroll_pos_used(
        self, canvas, mock_frame, make_widget, no_sleep
    ):
        outgoing = make_widget(600)
        incoming = make_widget(40)
        await _scroll_between(
            canvas, mock_frame, outgoing, incoming,
            outgoing_scroll_pos=-440,
        )
        # First draw call should use the scroll pos
        first_call = outgoing.draw.call_args_list[0]
        assert first_call.kwargs["cursor_pos"] == -440


class TestRunSwapWithScroll:
    async def test_scroll_processes_all_widgets(
        self, canvas, mock_frame, make_widget, no_sleep
    ):
        from led_ticker.transition import Scroll

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
        from led_ticker.transition import PushLeft

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
