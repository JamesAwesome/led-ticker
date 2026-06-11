"""Engine instrumentation: monitor updates and widget visits reach the board."""

import asyncio
import inspect

import pytest

from led_ticker import status_board
from led_ticker.status_board import StatusBoard
from led_ticker.widget import run_monitor_loop


class _OneShotMonitor:
    """Updatable that succeeds once then cancels its own loop."""

    name = "RSS BBC"

    def __init__(self):
        self.updated = asyncio.Event()

    async def update(self):
        self.updated.set()


@pytest.mark.asyncio
async def test_run_monitor_loop_records_update(tmp_path):
    board = StatusBoard(path=tmp_path / "status.json")
    status_board.set_active_board(board)
    monitor = _OneShotMonitor()
    task = asyncio.create_task(run_monitor_loop(monitor, 0.01, splay=False))
    try:
        await asyncio.wait_for(monitor.updated.wait(), timeout=2)
        await asyncio.sleep(0.05)  # let the post-update record run
        assert "RSS BBC" in board.monitor_updates
    finally:
        task.cancel()
        status_board.clear_active_board()


@pytest.mark.asyncio
async def test_run_monitor_loop_falls_back_to_class_name(tmp_path):
    board = StatusBoard(path=tmp_path / "status.json")
    status_board.set_active_board(board)

    class Nameless:
        def __init__(self):
            self.updated = asyncio.Event()

        async def update(self):
            self.updated.set()

    monitor = Nameless()
    task = asyncio.create_task(run_monitor_loop(monitor, 0.01, splay=False))
    try:
        await asyncio.wait_for(monitor.updated.wait(), timeout=2)
        await asyncio.sleep(0.05)
        assert "Nameless" in board.monitor_updates
    finally:
        task.cancel()
        status_board.clear_active_board()


def test_show_one_calls_record_widget_visit():
    """AST-free behavioral check: _show_one's body invokes the module hook."""
    from led_ticker import ticker as ticker_mod

    src = inspect.getsource(ticker_mod.Ticker._show_one)
    assert "record_widget_visit" in src, (
        "Ticker._show_one must call status_board.record_widget_visit(widget) "
        "so the web UI's now-playing pane tracks swap-mode visits."
    )
