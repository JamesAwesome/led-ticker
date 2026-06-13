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
    """Production setup + production teardown leave no residue.

    Calling _setup_status_board twice, with _teardown_status_board between
    calls, must leave the root logger with a net-zero handler gain and
    get_active_board() == None. Hand-rolled removeHandler calls would pass
    even if the production teardown were broken — so this test only uses
    the production helpers.
    """
    from pathlib import Path

    from led_ticker.app.run import _setup_status_board, _teardown_status_board

    root = logging.getLogger()
    handlers_before = list(root.handlers)

    config = _make_fake_config(str(tmp_path / "status.json"))
    plugins = _make_fake_plugins()

    # --- first cycle ---
    handle = _setup_status_board(config, Path(tmp_path / "config.toml"), plugins)
    assert handle is not None
    _board, _handler = handle
    assert status_board.get_active_board() is _board
    assert _handler in root.handlers

    _teardown_status_board(handle)
    assert status_board.get_active_board() is None
    assert _handler not in root.handlers

    # --- second cycle (same process, new status path) ---
    config2 = _make_fake_config(str(tmp_path / "status2.json"))
    handle2 = _setup_status_board(config2, Path(tmp_path / "config.toml"), plugins)
    assert handle2 is not None

    _teardown_status_board(handle2)
    assert status_board.get_active_board() is None
    # Net-zero: root logger has same handler set as before both cycles.
    assert root.handlers == handlers_before

    # Teardown with None (the [web]-absent handle) must be a no-op.
    _teardown_status_board(None)
    assert root.handlers == handlers_before


def test_run_teardown_is_adjacent_to_setup():
    """Tripwire: teardown must be reachable on ALL exits of run().

    The cancellation-safety of the status-board lifecycle depends on the
    `try:` starting on the line immediately after `_setup_status_board(...)`
    is assigned — any statement between them (an await, a builder call)
    re-opens the leak where an early exception or cancellation skips the
    `finally`. Keep setup adjacent to try.
    """
    from led_ticker.app.run import run

    src = inspect.getsource(run)
    assert "_teardown_status_board(_status_handle)" in src, (
        "run() must tear down via _teardown_status_board(_status_handle) in "
        "a finally block."
    )
    lines = [ln.strip() for ln in src.splitlines()]
    setup_idx = next(i for i, ln in enumerate(lines) if "_setup_status_board(" in ln)
    following = [ln for ln in lines[setup_idx + 1 :] if ln and not ln.startswith("#")]
    assert following and following[0] == "try:", (
        "teardown must be reachable on all exits — keep the "
        "`_status_handle = _setup_status_board(...)` assignment immediately "
        "before the `try:` whose finally calls _teardown_status_board."
    )


def test_setup_status_board_returns_none_when_web_absent(tmp_path):
    """Returns None when config.web is None — no board or handler created."""
    from pathlib import Path

    from led_ticker.app.run import _setup_status_board

    config = types.SimpleNamespace(web=None, display=None)
    plugins = _make_fake_plugins()
    result = _setup_status_board(config, Path(tmp_path / "config.toml"), plugins)
    assert result is None


def test_setup_runs_before_frame_build():
    """Tripwire: the status dir must be prepared while still root.

    rgbmatrix drops privileges (root -> daemon) inside RGBMatrix(), i.e.
    during build_frame_from_config. _setup_status_board (which mkdirs and
    chmods the status dir) must therefore run BEFORE the frame is built,
    or every post-startup publish fails EACCES on the root-owned dir —
    the longboi hardware-validation failure of 2026-06-11.
    """
    from led_ticker.app.run import run

    src = inspect.getsource(run)
    setup_at = src.index("_setup_status_board(")
    frame_at = src.index("build_frame_from_config(")
    assert setup_at < frame_at, (
        "_setup_status_board must precede build_frame_from_config — the "
        "matrix library drops root during frame construction and the "
        "status dir must be prepared (mkdir + chmod) before that."
    )


async def test_heartbeat_keeps_file_fresh_without_events(tmp_path):
    """The staleness verdict must measure process liveness, not event
    frequency: a widget held longer than 3x min_interval used to flip the
    page to 'stale' while the panel was happily playing (longboi standings
    finding, 2026-06-11). The heartbeat republishes at the throttle cadence
    and exits once the board is deactivated or disabled."""
    import json

    from led_ticker.app.run import _status_heartbeat

    board = StatusBoard(path=tmp_path / "status.json", min_interval=0.05)
    status_board.set_active_board(board)
    task = asyncio.create_task(_status_heartbeat(board))
    try:
        await asyncio.sleep(0.3)
        first = json.loads((tmp_path / "status.json").read_text())["published_at"]
        await asyncio.sleep(0.2)
        second = json.loads((tmp_path / "status.json").read_text())["published_at"]
        assert second > first, "file must keep refreshing with zero record_* events"
    finally:
        status_board.clear_active_board()
        await asyncio.wait_for(task, timeout=2)


def test_run_spawns_heartbeat():
    from led_ticker.app.run import run

    src = inspect.getsource(run)
    assert "spawn_tracked(_status_heartbeat" in src, (
        "run() must spawn the status heartbeat — without it any widget held "
        "longer than 3x min_interval shows a false 'stale' on the page."
    )


def test_setup_publishes_plugin_names(tmp_path):
    from pathlib import Path

    from led_ticker.app.run import _setup_status_board, _teardown_status_board

    config = _make_fake_config(str(tmp_path / "status.json"))
    info = types.SimpleNamespace(
        namespace="baseball",
        source="entry-point",
        counts={"widgets": 2, "emojis": 1},
        names={
            "widgets": ["baseball.scores", "baseball.standings"],
            "emojis": ["baseball.ball"],
        },
    )
    plugins = types.SimpleNamespace(loaded=[info], failed=[])
    handle = _setup_status_board(config, Path(tmp_path / "config.toml"), plugins)
    try:
        board, _ = handle
        assert board.plugins[0]["names"]["emojis"] == ["baseball.ball"]
    finally:
        _teardown_status_board(handle)


def test_setup_tolerates_nameless_plugin_info(tmp_path):
    """v1.0-shaped PluginInfo (no names attr) must not break setup."""
    from pathlib import Path

    from led_ticker.app.run import _setup_status_board, _teardown_status_board

    config = _make_fake_config(str(tmp_path / "status.json"))
    handle = _setup_status_board(
        config, Path(tmp_path / "config.toml"), _make_fake_plugins()
    )
    try:
        board, _ = handle
        assert board.plugins[0]["names"] == {}
    finally:
        _teardown_status_board(handle)


def test_setup_preview_installs_tee_when_web_present(tmp_path):
    from led_ticker.app.run import _setup_preview
    from led_ticker.frame import LedFrame

    config = _make_fake_config(str(tmp_path / "status.json"))
    frame = LedFrame(led_cols=32, led_chain_length=1)
    tee = _setup_preview(config, frame)
    assert tee is not None
    assert frame.get_clean_canvas() is tee


def test_setup_preview_none_when_web_absent(tmp_path):
    import types as _types

    from led_ticker.app.run import _setup_preview
    from led_ticker.frame import LedFrame

    config = _types.SimpleNamespace(web=None, display=None)
    frame = LedFrame(led_cols=32, led_chain_length=1)
    assert _setup_preview(config, frame) is None
    canvas = frame.get_clean_canvas()
    assert not hasattr(canvas, "mirror")  # raw canvas, no tee


@pytest.mark.asyncio
async def test_heartbeat_toggles_mirror_from_marker(tmp_path):
    import asyncio as _asyncio

    from led_ticker.app.run import _status_heartbeat
    from led_ticker.frame import LedFrame
    from led_ticker.preview import PreviewTee

    board = StatusBoard(path=tmp_path / "status.json", min_interval=0.05)
    frame = LedFrame(led_cols=32, led_chain_length=1)
    tee = PreviewTee(
        hw=frame.matrix.CreateFrameCanvas(),
        width=32,
        height=16,
        frame_path=tmp_path / "preview.bin",
    )
    status_board.set_active_board(board)
    task = _asyncio.create_task(_status_heartbeat(board, tee=tee, marker_ttl=0.2))
    try:
        marker = tmp_path / "preview-requested"
        marker.touch()
        await _asyncio.sleep(0.15)
        assert tee.mirror is True  # fresh marker -> mirroring on
        await _asyncio.sleep(0.4)  # let the marker age past ttl
        assert tee.mirror is False  # stale -> off
    finally:
        status_board.clear_active_board()
        await _asyncio.wait_for(task, timeout=2)


def test_setup_preview_sizes_from_mapped_canvas_not_config_math(tmp_path):
    """Review-team critical: pixel_mapper_config reshapes the real canvas
    (bigsign Remap). The tee MUST take the canvas's dimensions — config
    arithmetic (cols*chain x rows*parallel) is wrong under any mapper and
    makes ScaledCanvas's panel-height check crash the display at the first
    wrap. The stub honors U-mapper, which reshapes exactly like this."""
    from led_ticker.app.run import _setup_preview
    from led_ticker.frame import LedFrame

    frame = LedFrame(
        led_rows=32,
        led_cols=64,
        led_chain_length=8,
        led_parallel=1,
        led_pixel_mapper_config="U-mapper",
    )
    config = _make_fake_config(str(tmp_path / "status.json"))
    config.display = types.SimpleNamespace(
        rows=32, cols=64, chain_length=8, parallel=1, default_scale=4
    )
    tee = _setup_preview(config, frame)
    # U-mapper folds 1x8 into 2x4: 256 wide x 64 tall — NOT 512x32.
    assert (tee.width, tee.height) == (256, 64)


async def test_heartbeat_exit_turns_mirror_off(tmp_path):
    """Review-team finding: the heartbeat is the only owner of set_watched —
    its exit (board self-disable / teardown) must not strand the mirror ON
    paying the watched tax forever."""
    import asyncio as _asyncio

    from led_ticker.app.run import _status_heartbeat
    from led_ticker.frame import LedFrame
    from led_ticker.preview import PreviewTee

    board = StatusBoard(path=tmp_path / "status.json", min_interval=0.05)
    frame = LedFrame(led_cols=32, led_chain_length=1)
    tee = PreviewTee(
        hw=frame.matrix.CreateFrameCanvas(),
        width=32,
        height=16,
        frame_path=tmp_path / "preview.bin",
    )
    status_board.set_active_board(board)
    task = _asyncio.create_task(_status_heartbeat(board, tee=tee, marker_ttl=10.0))
    (tmp_path / "preview-requested").touch()
    await _asyncio.sleep(0.15)
    assert tee.mirror is True
    status_board.clear_active_board()  # heartbeat exits on next beat
    await _asyncio.wait_for(task, timeout=2)
    assert tee.mirror is False  # not stranded
