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


def _event_recorder(monkeypatch):
    """Record sleeps + update() calls in order (mock sleep is instant)."""
    _real_sleep = asyncio.sleep
    events: list[tuple[str, float | None]] = []

    async def _recording_sleep(seconds):
        events.append(("sleep", seconds))
        await _real_sleep(0)

    monkeypatch.setattr("led_ticker.widget.asyncio.sleep", _recording_sleep)
    return events, _real_sleep


async def test_immediate_updates_before_first_interval_wait(monkeypatch):
    """immediate=True: the first update() runs BEFORE the initial interval wait,
    so a polled source shows real data within one request instead of after a
    full `interval`."""
    events, _real_sleep = _event_recorder(monkeypatch)
    w = SimpleAsyncWidget()
    orig = w.update

    async def _tracked_update():
        events.append(("update", None))
        await orig()

    w.update = _tracked_update

    task = asyncio.create_task(
        run_monitor_loop(w, interval=999, splay=False, immediate=True),
    )
    for _ in range(5):
        await _real_sleep(0)
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task

    # The very first thing is an update — not a 999s wait.
    assert events[0] == ("update", None)
    assert w.update_count >= 1


async def test_default_waits_interval_before_first_update(monkeypatch):
    """immediate defaults False (unchanged): the loop waits `interval` before the
    first update. Data widgets rely on this — they eager-fetch in start() first,
    so an immediate first cycle would double-fetch."""
    events, _real_sleep = _event_recorder(monkeypatch)
    w = SimpleAsyncWidget()
    orig = w.update

    async def _tracked_update():
        events.append(("update", None))
        await orig()

    w.update = _tracked_update

    task = asyncio.create_task(
        run_monitor_loop(w, interval=999, splay=False),
    )
    for _ in range(5):
        await _real_sleep(0)
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task

    # First event is the interval wait; update hasn't fired yet.
    assert events[0] == ("sleep", 999)


async def test_immediate_first_fetch_failure_backs_off_not_busy_loops(monkeypatch):
    """immediate=True + a failing first fetch must engage backoff on the next
    cycle (not re-skip the wait via the first-cycle flag) — no busy-loop."""
    events, _real_sleep = _event_recorder(monkeypatch)
    w = SimpleAsyncWidget()

    async def _always_fail():
        events.append(("update", None))
        raise ValueError("API down")

    w.update = _always_fail

    task = asyncio.create_task(
        run_monitor_loop(w, interval=999, splay=False, immediate=True),
    )
    for _ in range(12):
        await _real_sleep(0)
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task

    # First cycle: immediate update (no wait). Then every failing cycle backs
    # off — exactly one sleep per update, so it never spins.
    assert events[0] == ("update", None)
    sleeps = [e for e in events if e[0] == "sleep"]
    updates = [e for e in events if e[0] == "update"]
    assert sleeps and sleeps[0][1] == _MIN_BACKOFF  # first wait is a backoff, not 999
    assert abs(len(updates) - len(sleeps)) <= 1  # one wait per cycle — no busy-loop


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
    from led_ticker.backends.rgbmatrix import RgbMatrixBackend
    from led_ticker.frame import LedFrame
    from led_ticker.widgets.message import TickerMessage

    msg = TickerMessage(text="hi")
    backend = RgbMatrixBackend(led_cols=32, led_chain_length=5)
    frame = LedFrame(backend=backend)
    frame.setup()
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


def test_container_protocol_recognizes_feed_monitor() -> None:
    from led_ticker.widget import Container

    class _FakeFeed:
        feed_stories: list = []

    assert isinstance(_FakeFeed(), Container)


def test_container_protocol_rejects_plain_widget() -> None:
    """TickerMessage has no feed_stories — must NOT satisfy Container."""
    from led_ticker.widget import Container
    from led_ticker.widgets.message import TickerMessage

    msg = TickerMessage("hello")
    assert not isinstance(msg, Container)
