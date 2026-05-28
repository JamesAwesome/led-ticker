"""Tests for led_ticker.widget protocols and run_monitor_loop."""

import asyncio
import contextlib
import unittest.mock as mock

import pytest

from led_ticker.widget import (
    _MAX_BACKOFF,
    _MIN_BACKOFF,
    Playable,
    Updatable,
    Widget,
    run_monitor_loop,
)


def test_run_transition_accepts_region_kwarg():
    """run_transition must accept a Region kwarg (no behavior change)."""
    import inspect

    from led_ticker.transitions import run_transition

    sig = inspect.signature(run_transition)
    assert "region" in sig.parameters


class SimpleWidget:
    """A minimal Widget implementation for testing."""

    def draw(self, canvas, cursor_pos=0, *, y_offset=0, font_color=None):
        return canvas, cursor_pos + 10


class SimpleAsyncWidget:
    """A minimal AsyncWidget implementation for testing."""

    def __init__(self):
        self.update_count = 0

    def draw(self, canvas, cursor_pos=0, *, y_offset=0, font_color=None):
        return canvas, cursor_pos + 10

    async def update(self):
        self.update_count += 1


def test_widget_protocol_conformance():
    w = SimpleWidget()
    assert isinstance(w, Widget)


def test_async_widget_protocol_conformance():
    w = SimpleAsyncWidget()
    assert isinstance(w, Widget)
    assert isinstance(w, Updatable)


def test_non_widget_does_not_match():
    assert not isinstance("not a widget", Widget)
    assert not isinstance(42, Widget)


def test_gifplayer_satisfies_playable_protocol():
    from led_ticker.widgets.gif import GifPlayer

    widget = GifPlayer(path="nonexistent.gif")
    assert isinstance(widget, Playable)


def test_widget_draw_returns_tuple():
    w = SimpleWidget()
    canvas = mock.Mock()
    result = w.draw(canvas, cursor_pos=5)
    assert result == (canvas, 15)


async def test_run_monitor_loop_calls_update():
    w = SimpleAsyncWidget()

    task = asyncio.create_task(
        run_monitor_loop(w, interval=0.05, splay=False),
    )
    await asyncio.sleep(0.15)
    task.cancel()

    with contextlib.suppress(asyncio.CancelledError):
        await task

    assert w.update_count >= 2


async def test_run_monitor_loop_survives_update_error(monkeypatch):
    """After an error, the loop backs off but continues."""
    _real_sleep = asyncio.sleep
    sleep_durations = []

    async def _recording_sleep(seconds):
        sleep_durations.append(seconds)
        await _real_sleep(0)

    monkeypatch.setattr("led_ticker.widget.asyncio.sleep", _recording_sleep)

    w = SimpleAsyncWidget()
    call_count = 0
    original_update = w.update

    async def flaky_update():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise ValueError("Transient error")
        await original_update()

    w.update = flaky_update

    task = asyncio.create_task(
        run_monitor_loop(w, interval=0.05, splay=False),
    )
    # Let a few iterations run
    for _ in range(10):
        await _real_sleep(0)
    task.cancel()

    with contextlib.suppress(asyncio.CancelledError):
        await task

    assert call_count >= 2
    assert w.update_count >= 1


async def test_backoff_increases_on_consecutive_errors(monkeypatch):
    """Consecutive errors should produce increasing backoff durations."""
    _real_sleep = asyncio.sleep
    sleep_durations = []

    async def _recording_sleep(seconds):
        sleep_durations.append(seconds)
        await _real_sleep(0)

    monkeypatch.setattr("led_ticker.widget.asyncio.sleep", _recording_sleep)

    w = SimpleAsyncWidget()
    error_count = 0

    async def always_fail():
        nonlocal error_count
        error_count += 1
        raise ValueError("API down")

    w.update = always_fail

    task = asyncio.create_task(
        run_monitor_loop(w, interval=0.05, splay=False),
    )
    # Let several error cycles run
    for _ in range(20):
        await _real_sleep(0)
    task.cancel()

    with contextlib.suppress(asyncio.CancelledError):
        await task

    assert error_count >= 3

    # First sleep is the normal interval (0.05)
    assert sleep_durations[0] == 0.05
    # After first error, backoff should be _MIN_BACKOFF (60)
    assert sleep_durations[1] == _MIN_BACKOFF
    # After second error, backoff doubles (120)
    assert sleep_durations[2] == _MIN_BACKOFF * 2


async def test_backoff_caps_at_max(monkeypatch):
    """Backoff should never exceed _MAX_BACKOFF."""
    _real_sleep = asyncio.sleep
    sleep_durations = []

    async def _recording_sleep(seconds):
        sleep_durations.append(seconds)
        await _real_sleep(0)

    monkeypatch.setattr("led_ticker.widget.asyncio.sleep", _recording_sleep)

    w = SimpleAsyncWidget()

    async def always_fail():
        raise ValueError("API down")

    w.update = always_fail

    task = asyncio.create_task(
        run_monitor_loop(w, interval=0.05, splay=False),
    )
    for _ in range(50):
        await _real_sleep(0)
    task.cancel()

    with contextlib.suppress(asyncio.CancelledError):
        await task

    # All backoff durations should be <= _MAX_BACKOFF
    backoff_sleeps = [d for d in sleep_durations if d > 1]
    for d in backoff_sleeps:
        assert d <= _MAX_BACKOFF


async def test_backoff_resets_on_success(monkeypatch):
    """After a successful update, backoff resets to normal interval."""
    _real_sleep = asyncio.sleep
    sleep_durations = []

    async def _recording_sleep(seconds):
        sleep_durations.append(seconds)
        await _real_sleep(0)

    monkeypatch.setattr("led_ticker.widget.asyncio.sleep", _recording_sleep)

    w = SimpleAsyncWidget()
    call_count = 0
    original_update = w.update

    async def fail_then_succeed():
        nonlocal call_count
        call_count += 1
        if call_count <= 2:
            raise ValueError("Temporary failure")
        await original_update()

    w.update = fail_then_succeed

    task = asyncio.create_task(
        run_monitor_loop(w, interval=0.05, splay=False),
    )
    for _ in range(30):
        await _real_sleep(0)
    task.cancel()

    with contextlib.suppress(asyncio.CancelledError):
        await task

    # After recovery, should see the normal interval again
    # Pattern: 0.05 (normal), 60 (1st error backoff), 120 (2nd),
    # then 0.05 (success resets)
    assert call_count >= 3
    assert w.update_count >= 1
    # The interval after recovery should be normal (0.05)
    normal_intervals = [d for d in sleep_durations if d == 0.05]
    assert len(normal_intervals) >= 2  # initial + post-recovery


def test_widget_draw_rejects_unknown_kwargs():
    from led_ticker.frame import LedFrame
    from led_ticker.widgets.message import TickerMessage

    msg = TickerMessage(text="hi")
    frame = LedFrame(led_cols=32, led_chain_length=5)
    canvas = frame.get_clean_canvas()
    with pytest.raises(TypeError):
        msg.draw(canvas, cursor_pos=0, region="should-fail")


class TestFrameAwareWidgetProtocol:
    def test_frame_aware_widget_protocol_exported(self):
        from led_ticker.widget import FrameAwareWidget

        assert FrameAwareWidget is not None

    def test_ticker_message_satisfies_frame_aware_widget(self):
        from led_ticker.widget import FrameAwareWidget
        from led_ticker.widgets.message import TickerMessage

        w = TickerMessage(text="hi")
        assert isinstance(w, FrameAwareWidget)

    def test_plain_widget_does_not_satisfy_frame_aware_widget(self):
        from led_ticker.widget import FrameAwareWidget

        class PlainWidget:
            def draw(self, canvas, cursor_pos=0, *, y_offset=0, font_color=None):
                return canvas, cursor_pos

        assert not isinstance(PlainWidget(), FrameAwareWidget)


def test_container_protocol_recognizes_mlb_monitor() -> None:
    """MLBScoreMonitor exposes feed_stories — must satisfy Container."""
    from unittest.mock import MagicMock

    from led_ticker.widget import Container
    from led_ticker.widgets.mlb import MLBScoreMonitor

    # Build with attrs.define defaults — feed_stories factory=list satisfies the field
    monitor = MLBScoreMonitor(session=MagicMock(), team="NYM")
    assert isinstance(monitor, Container)


def test_container_protocol_recognizes_rss_monitor() -> None:
    from unittest.mock import MagicMock

    from led_ticker.widget import Container
    from led_ticker.widgets.rss_feed import RSSFeedMonitor

    monitor = RSSFeedMonitor(session=MagicMock(), feed_url="http://example.com/feed")
    assert isinstance(monitor, Container)


def test_container_protocol_recognizes_standings_monitor() -> None:
    from unittest.mock import MagicMock

    from led_ticker.widget import Container
    from led_ticker.widgets.mlb_standings import MLBStandingsMonitor

    monitor = MLBStandingsMonitor(session=MagicMock(), teams=["NYM"])
    assert isinstance(monitor, Container)


def test_container_protocol_recognizes_pool_monitor() -> None:
    """PoolMonitor exposes feed_stories — must satisfy Container so the
    engine re-expands its cycle screens per pass (same path as MLB / RSS /
    standings; this is what gives pool live-refresh for free)."""
    from unittest.mock import MagicMock

    from led_ticker.widget import Container
    from led_ticker.widgets.pool import PoolMonitor

    monitor = PoolMonitor(session=MagicMock())
    assert isinstance(monitor, Container)


def test_container_protocol_rejects_plain_widget() -> None:
    """TickerMessage has no feed_stories — must NOT satisfy Container."""
    from led_ticker.widget import Container
    from led_ticker.widgets.message import TickerMessage

    msg = TickerMessage("hello")
    assert not isinstance(msg, Container)
