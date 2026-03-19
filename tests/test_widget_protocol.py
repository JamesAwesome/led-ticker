"""Tests for led_ticker.widget protocols and run_monitor_loop."""

import asyncio
import contextlib
import unittest.mock as mock

from led_ticker.widget import AsyncWidget, Widget, run_monitor_loop


class SimpleWidget:
    """A minimal Widget implementation for testing."""

    def draw(self, canvas, cursor_pos=0, **kwargs):
        return canvas, cursor_pos + 10


class SimpleAsyncWidget:
    """A minimal AsyncWidget implementation for testing."""

    def __init__(self):
        self.update_count = 0

    def draw(self, canvas, cursor_pos=0, **kwargs):
        return canvas, cursor_pos + 10

    async def update(self):
        self.update_count += 1


def test_widget_protocol_conformance():
    w = SimpleWidget()
    assert isinstance(w, Widget)


def test_async_widget_protocol_conformance():
    w = SimpleAsyncWidget()
    assert isinstance(w, AsyncWidget)
    assert isinstance(w, Widget)


def test_non_widget_does_not_match():
    assert not isinstance("not a widget", Widget)
    assert not isinstance(42, Widget)


def test_widget_draw_returns_tuple():
    w = SimpleWidget()
    canvas = mock.Mock()
    result = w.draw(canvas, cursor_pos=5)
    assert result == (canvas, 15)


async def test_run_monitor_loop_calls_update():
    w = SimpleAsyncWidget()

    task = asyncio.create_task(run_monitor_loop(w, interval=0.05, splay=False))
    await asyncio.sleep(0.15)
    task.cancel()

    with contextlib.suppress(asyncio.CancelledError):
        await task

    assert w.update_count >= 2


async def test_run_monitor_loop_survives_update_error():
    w = SimpleAsyncWidget()
    original_update = w.update

    call_count = 0

    async def flaky_update():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise ValueError("Transient error")
        await original_update()

    w.update = flaky_update

    task = asyncio.create_task(run_monitor_loop(w, interval=0.05, splay=False))
    await asyncio.sleep(0.2)
    task.cancel()

    with contextlib.suppress(asyncio.CancelledError):
        await task

    # Should have continued past the error
    assert call_count >= 2
    assert w.update_count >= 1
