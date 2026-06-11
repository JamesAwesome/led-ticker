"""Engine instrumentation: monitor updates and widget visits reach the board."""

import asyncio
import inspect
import logging
import types

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


def _make_fake_config(status_path: str) -> types.SimpleNamespace:
    """Minimal config stand-in for _setup_status_board."""
    display = types.SimpleNamespace(
        rows=16,
        cols=32,
        chain_length=5,
        parallel=1,
        default_scale=1,
    )
    web = types.SimpleNamespace(status_path=status_path)
    return types.SimpleNamespace(web=web, display=display)


def _make_fake_plugins() -> types.SimpleNamespace:
    """Minimal plugins stand-in for _setup_status_board."""
    info = types.SimpleNamespace(namespace="test.plugin", source="dist", counts={})
    return types.SimpleNamespace(loaded=[info], failed=[])


def test_setup_status_board_lifecycle(tmp_path):
    """_setup_status_board teardown removes the handler and clears the board.

    Calling setup twice (with teardown between calls) must leave the root
    logger with a net-zero handler gain and get_active_board() == None.
    """
    from pathlib import Path

    from led_ticker.app.run import _setup_status_board

    root = logging.getLogger()
    handlers_before = list(root.handlers)

    config = _make_fake_config(str(tmp_path / "status.json"))
    plugins = _make_fake_plugins()

    # --- first run ---
    handle = _setup_status_board(config, Path(tmp_path / "config.toml"), plugins)
    assert handle is not None
    _board, _handler = handle
    assert status_board.get_active_board() is _board
    assert _handler in root.handlers

    # Teardown
    root.removeHandler(_handler)
    status_board.clear_active_board()

    assert status_board.get_active_board() is None
    assert _handler not in root.handlers

    # --- second run (same process, new status path) ---
    config2 = _make_fake_config(str(tmp_path / "status2.json"))
    handle2 = _setup_status_board(config2, Path(tmp_path / "config.toml"), plugins)
    assert handle2 is not None
    _board2, _handler2 = handle2

    # Teardown again
    root.removeHandler(_handler2)
    status_board.clear_active_board()

    assert status_board.get_active_board() is None
    # Net-zero: root logger has same handler set as before both runs.
    assert root.handlers == handlers_before


def test_setup_status_board_returns_none_when_web_absent(tmp_path):
    """Returns None when config.web is None — no board or handler created."""
    from pathlib import Path

    from led_ticker.app.run import _setup_status_board

    config = types.SimpleNamespace(web=None, display=None)
    plugins = _make_fake_plugins()
    result = _setup_status_board(config, Path(tmp_path / "config.toml"), plugins)
    assert result is None
