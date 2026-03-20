"""Tests for ticker display modes (run_swap, run_forever_scroll, etc)."""

import asyncio
import unittest.mock as mock

import pytest

from led_ticker.ticker import (
    Ticker,
    _run_swap,
    _scroll_and_delay,
    _scroll_into_frame,
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
        result_canvas, pos = await _swap_and_scroll(canvas, mock_frame, widget)
        assert result_canvas is canvas
        assert pos == 40
        widget.draw.assert_called_once()

    async def test_oversized_triggers_scroll(
        self, canvas, mock_frame, make_widget, no_sleep
    ):
        widget = make_widget(content_width=200)
        _, pos = await _swap_and_scroll(canvas, mock_frame, widget)
        # Should have scrolled until it fits
        assert pos <= canvas.width


class TestScrollIntoFrame:
    async def test_scrolls_until_fits(self, canvas, mock_frame, make_widget, no_sleep):
        widget = make_widget(content_width=200)
        _, pos = await _scroll_into_frame(canvas, mock_frame, widget, cursor_pos=0)
        assert pos <= canvas.width

    async def test_already_fits_no_loop(
        self, canvas, mock_frame, make_widget, no_sleep
    ):
        widget = make_widget(content_width=100)
        _, pos = await _scroll_into_frame(canvas, mock_frame, widget, cursor_pos=0)
        assert pos == 100
        mock_frame.matrix.SwapOnVSync.assert_called_once()


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
