"""Engine instrumentation: monitor updates and widget visits reach the board."""

import asyncio
import contextlib
import inspect
import logging
import types

import pytest

from led_ticker import status_board
from led_ticker.status_board import StatusBoard
from led_ticker.widget import run_monitor_loop


class _OneShotMonitor:
    """Updatable that succeeds once then cancels its own loop.

    Mirrors a real Container: has ``feed_stories`` + ``update()`` but NO
    ``.draw`` — verifying the container-shape registration path (Finding 1).
    """

    name = "RSS BBC"
    feed_stories: list = []

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
        # schema 9: monitor data lives in board.monitors, not board.monitor_updates
        assert "RSS BBC" in board.monitors
    finally:
        task.cancel()
        status_board.clear_active_board()


@pytest.mark.asyncio
async def test_run_monitor_loop_falls_back_to_class_name(tmp_path):
    board = StatusBoard(path=tmp_path / "status.json")
    status_board.set_active_board(board)

    class Nameless:
        feed_stories: list = []

        def __init__(self):
            self.updated = asyncio.Event()

        async def update(self):
            self.updated.set()

    monitor = Nameless()
    task = asyncio.create_task(run_monitor_loop(monitor, 0.01, splay=False))
    try:
        await asyncio.wait_for(monitor.updated.wait(), timeout=2)
        await asyncio.sleep(0.05)
        # schema 9: monitor data lives in board.monitors, not board.monitor_updates
        assert "Nameless" in board.monitors
    finally:
        task.cancel()
        status_board.clear_active_board()


@pytest.mark.asyncio
async def test_register_on_entry_and_error_with_retry(tmp_path):
    import led_ticker.status_board as sb

    board = sb.StatusBoard(path=tmp_path / "s.json")
    sb.set_active_board(board)

    class _FailingWidget:
        name = "flaky"
        feed_stories: list = []

        async def update(self):
            raise ValueError("boom")

    try:
        task = asyncio.create_task(
            run_monitor_loop(_FailingWidget(), 0.01, splay=False, immediate=True)
        )
        for _ in range(30):
            await asyncio.sleep(0)
            if board.monitors.get("flaky", {}).get("error"):
                break
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        m = board.monitors["flaky"]
        assert m["kind"] == "widget"
        err = m["error"]
        assert err and "boom" in err["message"] and err["consecutive"] >= 1
        assert err["retry_in"] > 0  # the backoff hint
    finally:
        sb.set_active_board(None)


@pytest.mark.asyncio
async def test_busy_light_like_not_registered(tmp_path):
    import led_ticker.status_board as sb

    board = sb.StatusBoard(path=tmp_path / "s.json")
    sb.set_active_board(board)

    class _BusyLike:  # no .draw, no .feed_stories, no .polled -> not a monitor
        name = "busy"

        async def update(self): ...

    try:
        task = asyncio.create_task(
            run_monitor_loop(_BusyLike(), 0.01, splay=False, immediate=True)
        )
        for _ in range(10):
            await asyncio.sleep(0)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        assert "busy" not in board.monitors
    finally:
        sb.set_active_board(None)


@pytest.mark.asyncio
async def test_container_widget_registers(tmp_path):
    """Container monitors (feed_stories + update, NO .draw) must appear in
    board.monitors — verifies Finding 1 fix in run_monitor_loop."""
    import led_ticker.status_board as sb

    board = sb.StatusBoard(path=tmp_path / "s.json")
    sb.set_active_board(board)

    class _Container:  # mirrors rss.feed / calendar.events shape
        name = "RSS BBC"
        feed_stories: list = []

        def __init__(self):
            self.updated = asyncio.Event()

        async def update(self):
            self.updated.set()

    monitor = _Container()
    try:
        task = asyncio.create_task(run_monitor_loop(monitor, 0.01, splay=False))
        await asyncio.wait_for(monitor.updated.wait(), timeout=2)
        await asyncio.sleep(0.05)  # let the post-update record run
        entry = board.monitors.get("RSS BBC")
        assert entry is not None, (
            "Container widget (feed_stories + update, no .draw) must be "
            "registered in board.monitors"
        )
        assert entry["kind"] == "widget"
    finally:
        task.cancel()
        sb.set_active_board(None)


@pytest.mark.asyncio
async def test_status_error_never_escapes_loop(tmp_path, monkeypatch):
    import led_ticker.status_board as sb

    board = sb.StatusBoard(path=tmp_path / "s.json")
    sb.set_active_board(board)

    def _boom(*a, **k):
        raise RuntimeError("board down")

    # If the raising recorder reached the loop unwrapped it would kill it.
    monkeypatch.setattr(sb, "record_monitor_error", _boom)

    class _Flaky:
        name = "x"
        feed_stories: list = []

        async def update(self):
            raise ValueError("nope")

    try:
        task = asyncio.create_task(
            run_monitor_loop(_Flaky(), 0.01, splay=False, immediate=True)
        )
        for _ in range(10):
            await asyncio.sleep(0)
        assert not task.done()  # loop survived a raising recorder
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
    finally:
        sb.set_active_board(None)


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
    """Tripwire: privilege drop happens in backend.setup(), not build_frame_from_config.



    The RgbMatrixBackend constructs RGBMatrix() inside led_frame.setup()
    (one step after build_frame_from_config in run.py), which is where
    rgbmatrix drops root -> daemon. All pre-drop work — status-board setup,
    startup validation — must therefore precede led_frame.setup(), not merely
    build_frame_from_config.

    Additionally, led_frame.setup() must precede _setup_preview (which
    requires a live backend to size the preview canvas from the real matrix)
    and the brightness scheduler spawn (_respawn_schedule / _schedule start).

    Ordering asserted (all source-index checks against run()):
      _setup_status_board   <  led_frame.setup(
      _run_startup_validation  <  led_frame.setup(
      led_frame.setup(      <  _setup_preview(
      led_frame.setup(      <  _respawn_schedule(
    """
    from led_ticker.app.run import run

    src = inspect.getsource(run)
    setup_board_at = src.index("_setup_status_board(")
    validation_at = src.index("_run_startup_validation(")
    frame_setup_at = src.index("led_frame.setup(")
    preview_at = src.index("_setup_preview(")
    respawn_at = src.index("_respawn_schedule(")

    assert setup_board_at < frame_setup_at, (
        "_setup_status_board must precede led_frame.setup() — the backend "
        "constructs RGBMatrix() inside setup(), dropping root, and "
        "prepare_dir needs root to open the status directory."
    )
    assert validation_at < frame_setup_at, (
        "_run_startup_validation must precede led_frame.setup() — startup "
        "validation runs pre-drop so validator errors are visible before "
        "privileges are surrendered."
    )
    assert frame_setup_at < preview_at, (
        "led_frame.setup() must precede _setup_preview() — preview setup "
        "calls led_frame.create_canvas(), which requires a live backend."
    )
    assert frame_setup_at < respawn_at, (
        "led_frame.setup() must precede _respawn_schedule() — the scheduler "
        "sets led_frame.brightness, which requires a live backend."
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
    import re

    from led_ticker.app.run import run

    # Regex tolerates ruff wrapping the call across lines (whitespace between
    # `spawn_tracked(` and `_status_heartbeat`) — still fails if the spawn is
    # removed, just not on cosmetic reflow.
    src = inspect.getsource(run)
    assert re.search(r"spawn_tracked\(\s*_status_heartbeat", src), (
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
    from led_ticker.backends.rgbmatrix import RgbMatrixBackend
    from led_ticker.frame import LedFrame

    config = _make_fake_config(str(tmp_path / "status.json"))
    frame = LedFrame(backend=RgbMatrixBackend(led_cols=32, led_chain_length=1))
    frame.setup()
    tee = _setup_preview(config, frame)
    assert tee is not None
    assert frame.get_clean_canvas() is tee


def test_setup_preview_none_when_web_absent(tmp_path):
    import types as _types

    from led_ticker.app.run import _setup_preview
    from led_ticker.backends.rgbmatrix import RgbMatrixBackend
    from led_ticker.frame import LedFrame

    config = _types.SimpleNamespace(web=None, display=None)
    frame = LedFrame(backend=RgbMatrixBackend(led_cols=32, led_chain_length=1))
    frame.setup()
    assert _setup_preview(config, frame) is None
    canvas = frame.get_clean_canvas()
    assert not hasattr(canvas, "mirror")  # raw canvas, no tee


@pytest.mark.asyncio
async def test_heartbeat_toggles_mirror_from_marker(tmp_path):
    import asyncio as _asyncio

    from led_ticker.app.run import _status_heartbeat
    from led_ticker.backends.rgbmatrix import RgbMatrixBackend
    from led_ticker.frame import LedFrame
    from led_ticker.preview import PreviewTee

    board = StatusBoard(path=tmp_path / "status.json", min_interval=0.05)
    frame = LedFrame(backend=RgbMatrixBackend(led_cols=32, led_chain_length=1))
    frame.setup()
    tee = PreviewTee(
        hw=frame.create_canvas(),
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
    from led_ticker.backends.rgbmatrix import RgbMatrixBackend
    from led_ticker.frame import LedFrame

    frame = LedFrame(
        backend=RgbMatrixBackend(
            led_rows=32,
            led_cols=64,
            led_chain_length=8,
            led_parallel=1,
            led_pixel_mapper_config="U-mapper",
        )
    )
    frame.setup()
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
    from led_ticker.backends.rgbmatrix import RgbMatrixBackend
    from led_ticker.frame import LedFrame
    from led_ticker.preview import PreviewTee

    board = StatusBoard(path=tmp_path / "status.json", min_interval=0.05)
    frame = LedFrame(backend=RgbMatrixBackend(led_cols=32, led_chain_length=1))
    frame.setup()
    tee = PreviewTee(
        hw=frame.create_canvas(),
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


async def test_heartbeat_pulls_busy_state(tmp_path):
    import asyncio as _asyncio

    from led_ticker.app.run import _status_heartbeat
    from led_ticker.busy_light import BusyLight

    board = StatusBoard(path=tmp_path / "status.json", min_interval=0.05)
    busy = BusyLight(file_path="/x")
    busy.set_busy(True, now=__import__("time").monotonic(), ttl=600.0)
    status_board.set_active_board(board)
    task = _asyncio.create_task(_status_heartbeat(board, busy=busy, busy_source="http"))
    try:
        await _asyncio.sleep(0.15)
        snap = board.snapshot()["overlays"]["busy"]
        assert snap["enabled"] is True
        assert snap["active"] is True
        assert snap["source"] == "http"
        assert snap["ttl_remaining"] is not None and snap["ttl_remaining"] > 0
    finally:
        status_board.clear_active_board()
        await _asyncio.wait_for(task, timeout=2)


async def test_heartbeat_busy_none_leaves_default(tmp_path):
    import asyncio as _asyncio

    from led_ticker.app.run import _status_heartbeat

    board = StatusBoard(path=tmp_path / "status.json", min_interval=0.05)
    status_board.set_active_board(board)
    task = _asyncio.create_task(_status_heartbeat(board, busy=None))
    try:
        await _asyncio.sleep(0.15)
        # busy=None: heartbeat records nothing; the board's default stands.
        assert board.snapshot()["overlays"]["busy"] == {"enabled": False}
    finally:
        status_board.clear_active_board()
        await _asyncio.wait_for(task, timeout=2)


def test_run_spawns_heartbeat_after_busy_setup():
    # The heartbeat needs the busy object, which is created by
    # _start_busy_light. Source-order tripwire: the heartbeat spawn must come
    # AFTER the busy-light setup call, or busy doesn't exist yet at the spawn.
    import inspect
    import re

    from led_ticker.app.run import run

    src = inspect.getsource(run)
    busy_at = src.index("_start_busy_light(")
    # Regex so the lookup survives ruff wrapping spawn_tracked(...) over lines.
    spawn_match = re.search(r"spawn_tracked\(\s*_status_heartbeat", src)
    assert spawn_match is not None, "run() must spawn the heartbeat"
    assert busy_at < spawn_match.start(), (
        "heartbeat spawn must follow _start_busy_light so the busy object "
        "exists and can be threaded into the heartbeat."
    )


def test_run_builds_overlay_roster_in_source():
    # The roster must be assembled in run() and handed to set_overlay_roster.
    import inspect

    from led_ticker.app.run import run

    src = inspect.getsource(run)
    assert "set_overlay_roster(" in src
    assert '"kind": "core"' in src  # busy_light entry synthesized in run()
    assert '"kind": "plugin"' in src  # plugin overlay entries


def test_reconcile_runs_before_load_plugins_and_frame_build():
    """Tripwire: reconcile must run before plugin load and before the frame drop-root.

    plugin_reconcile.reconcile(...) + apply_to_syspath(...) must appear in
    run() BEFORE _load_plugins_for_config(...) (so reconciled packages are
    importable when plugins load), and _load_plugins_for_config must appear
    BEFORE build_frame_from_config (constraint #13 — root drops during frame
    construction). This is a source-order assertion mirroring the style of
    test_setup_runs_before_frame_build.
    """
    import inspect

    from led_ticker.app.run import run

    src = inspect.getsource(run)
    reconcile_at = src.index("plugin_reconcile.reconcile(")
    apply_at = src.index("apply_to_syspath(")
    load_plugins_at = src.index("_load_plugins_for_config(")
    setup_board_at = src.index("_setup_status_board(")
    record_at = src.index("record_plugin_reconcile(")
    frame_at = src.index("build_frame_from_config(")

    assert reconcile_at < load_plugins_at, (
        "plugin_reconcile.reconcile(...) must appear in run() BEFORE "
        "_load_plugins_for_config(...) so reconciled packages are importable "
        "when plugins load."
    )
    assert apply_at < load_plugins_at, (
        "apply_to_syspath(...) must appear in run() BEFORE "
        "_load_plugins_for_config(...) so the volume venv site-packages are on "
        "sys.path before entry-point discovery."
    )
    assert reconcile_at < apply_at, (
        "apply_to_syspath in run() must follow reconcile() — reconcile already "
        "handles the internal apply for volume targets; the outer call is a "
        "belt-and-suspenders guard for the local-venv path and must not precede "
        "the reconcile."
    )
    assert load_plugins_at < frame_at, (
        "_load_plugins_for_config must precede build_frame_from_config — the "
        "matrix library drops root during frame construction (constraint #13)."
    )
    assert setup_board_at < record_at < frame_at, (
        "record_plugin_reconcile(...) must appear after _setup_status_board(...) "
        "and before build_frame_from_config(...) so the board is ready to "
        "receive reconcile event records."
    )


def test_reconcile_prologue_never_raises():
    """Tripwire (constraint #1): the reconcile prologue in run() — resolve_target,
    reconcile, apply_to_syspath — must all sit inside a try that ACTUALLY HANDLES
    the raise (>=1 ``except`` handler) so a raise on the dark-panel prologue
    (before build_frame_from_config) cannot freeze the panel. reconcile() guards
    its own body, but resolve_target/apply_to_syspath run outside that guard.

    A bare ``try: ... finally:`` with no ``except`` would let the exception
    propagate and freeze the panel while still placing the calls inside a Try
    node, so it is NOT sufficient to assert "inside a Try" — the enclosing Try
    must have a non-empty ``.handlers``. AST-verify each required call is a
    descendant of a Try node whose ``.handlers`` is non-empty."""
    import ast
    import inspect

    from led_ticker.app.run import run

    tree = ast.parse(inspect.getsource(run))

    # For each call, record whether it is lexically inside a Try whose body has at
    # least one `except` handler. A call seen inside an except-less Try (e.g. a
    # try/finally) is recorded with has_except=False unless ALSO covered by a
    # handled Try — we take the strongest coverage seen (any handled Try wins).
    coverage: dict[str, bool] = {}

    class _Visitor(ast.NodeVisitor):
        def visit_Try(self, node: ast.Try) -> None:
            has_except = len(node.handlers) >= 1
            for stmt in node.body:
                for sub in ast.walk(stmt):
                    if isinstance(sub, ast.Call):
                        name = ast.unparse(sub.func)
                        coverage[name] = coverage.get(name, False) or has_except
            self.generic_visit(node)

    _Visitor().visit(tree)

    for needed in (
        "plugin_reconcile.resolve_target",
        "plugin_reconcile.reconcile",
        "plugin_reconcile.apply_to_syspath",
    ):
        assert needed in coverage, (
            f"{needed}(...) must run inside a try/except in run() — a raise on "
            "the reconcile prologue freezes the panel (constraint #1)."
        )
        assert coverage[needed], (
            f"{needed}(...) is inside a Try with NO except handler (a bare "
            "try/finally) — an exception would still propagate and freeze the "
            "panel. It must sit inside a try that has at least one `except` "
            "(constraint #1)."
        )


class TestConsumeRestartMarker:
    """Unit tests for _consume_restart_marker — delete-before-exit helper."""

    def test_consume_restart_marker_detects_and_deletes(self, tmp_path):
        from led_ticker.app.run import _consume_restart_marker

        m = tmp_path / "restart-requested"
        m.write_text("")
        assert _consume_restart_marker(m) is True
        assert not m.exists()  # deleted BEFORE the caller exits — loop-safety

    def test_consume_restart_marker_absent_is_false(self, tmp_path):
        from led_ticker.app.run import _consume_restart_marker

        assert _consume_restart_marker(tmp_path / "restart-requested") is False

    def test_restart_checked_per_section_not_only_per_playlist(self):
        """FIX A: the restart marker must be consumed at LEAST per-section, not
        only once per full playlist cycle. Source-scan run() for the
        per-section check (`_restart_requested()` inside the
        `for section_index, section` loop)."""
        import inspect

        from led_ticker.app.run import run

        src = inspect.getsource(run)
        lines = src.splitlines()
        for_idx = next(
            i for i, ln in enumerate(lines) if "for section_index, section" in ln
        )
        # The for-section loop body (the next ~45 lines) must contain a
        # restart check + sys.exit, so latency is one section not a playlist.
        # (The per-section config-reload check now precedes the restart check
        # in the loop body, so the window spans both.)
        body = "\n".join(lines[for_idx : for_idx + 45])
        assert "_restart_requested()" in body, (
            "run() must check the restart marker inside the for-section loop "
            "(per-section), not only at the top of the outer while-True "
            "(per-playlist) — otherwise restart 'frequently fails' until the "
            "playlist cycles back around."
        )
        assert "sys.exit(0)" in body, (
            "the per-section restart check must exit cleanly via sys.exit(0)"
        )

    def test_ticker_per_tick_restart_check_wired(self):
        """FIX A (better): the Ticker receives a per-tick restart_check so a
        restart unwinds within ~one engine tick, and run() catches the
        resulting RestartRequested with a clean sys.exit(0)."""
        import inspect

        from led_ticker.app.run import run

        src = inspect.getsource(run)
        assert '"restart_check": _restart_requested' in src, (
            "Ticker must be constructed with restart_check=_restart_requested "
            "for second-level restart responsiveness"
        )
        assert "except RestartRequested:" in src, (
            "run() must catch RestartRequested raised by the per-tick hook"
        )

    def test_restart_check_consumes_before_exit(self):
        """Loop-safety: _restart_requested calls _consume_restart_marker, which
        deletes the marker BEFORE signalling — so the restarted process can't
        re-read it and exit again."""
        import inspect

        from led_ticker.app.run import run

        src = inspect.getsource(run)
        assert "_consume_restart_marker(_restart_marker)" in src, (
            "_restart_requested must consume (delete) the marker via "
            "_consume_restart_marker before returning True"
        )


# --- Task 3: type + value propagation through run_monitor_loop ---------------


@pytest.mark.asyncio
async def test_run_monitor_loop_records_type_for_polled_source(tmp_path):
    """A polled source registered in _PLUGIN_SOURCE_TYPES appears with its
    type name in the monitor entry after a successful update."""
    import asyncio

    from led_ticker.sources import _PLUGIN_SOURCE_TYPES, PolledDataSource
    from led_ticker.status_board import StatusBoard

    class _FakeWeather(PolledDataSource):
        polled = True
        id = "fake_weather_src"

        def __init__(self):
            super().__init__(id="fake_weather_src", interval=60)
            self.updated = asyncio.Event()
            self._current = "72°F Sunny"

        async def update(self) -> None:
            self.updated.set()

    _PLUGIN_SOURCE_TYPES["acme.weather"] = _FakeWeather
    board = StatusBoard(path=tmp_path / "status.json")
    status_board.set_active_board(board)
    monitor = _FakeWeather()
    try:
        task = asyncio.create_task(
            run_monitor_loop(monitor, 0.01, splay=False, immediate=True)
        )
        await asyncio.wait_for(monitor.updated.wait(), timeout=2)
        await asyncio.sleep(0.05)
        entry = board.monitors.get(monitor.id)
        assert entry is not None, "polled source must be in monitors"
        assert entry["type"] == "acme.weather", (
            f"type should be 'acme.weather', got {entry['type']!r}"
        )
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
    finally:
        _PLUGIN_SOURCE_TYPES.pop("acme.weather", None)
        status_board.clear_active_board()


@pytest.mark.asyncio
async def test_run_monitor_loop_records_value_for_source_with_current(tmp_path):
    """After a successful update, record_monitor_update is called with the
    source's .current value, so the monitor entry carries it."""
    import asyncio

    from led_ticker.sources import _PLUGIN_SOURCE_TYPES, PolledDataSource
    from led_ticker.status_board import StatusBoard

    class _FakeWeather(PolledDataSource):
        polled = True

        def __init__(self):
            super().__init__(id="fake_weather_val", interval=60)
            self.updated = asyncio.Event()
            self.current = "72°F Sunny"

        async def update(self) -> None:
            self.updated.set()

    _PLUGIN_SOURCE_TYPES["acme.weather2"] = _FakeWeather
    board = StatusBoard(path=tmp_path / "status.json")
    status_board.set_active_board(board)
    monitor = _FakeWeather()
    try:
        task = asyncio.create_task(
            run_monitor_loop(monitor, 0.01, splay=False, immediate=True)
        )
        await asyncio.wait_for(monitor.updated.wait(), timeout=2)
        await asyncio.sleep(0.05)
        entry = board.monitors.get(monitor.id)
        assert entry is not None
        assert entry["value"] == "72°F Sunny", (
            f"value should be '72°F Sunny', got {entry['value']!r}"
        )
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
    finally:
        _PLUGIN_SOURCE_TYPES.pop("acme.weather2", None)
        status_board.clear_active_board()


@pytest.mark.asyncio
async def test_raising_monitor_value_does_not_count_as_update_failure(
    tmp_path, monkeypatch
):
    """A raise in _monitor_value on a SUCCESSFUL update must NOT bump
    consecutive_errors or record a monitor error.

    Before the else-clause fix, _monitor_value and record_monitor_update sat
    inside the same try that wrapped update() — a raise there would hit the
    except branch, increment consecutive_errors, and log "Error updating" even
    though update() itself succeeded.
    """
    import asyncio

    import led_ticker.status_board as sb
    from led_ticker.status_board import StatusBoard

    board = StatusBoard(path=tmp_path / "status.json")
    sb.set_active_board(board)

    class _GoodWidget:
        name = "good_widget"
        feed_stories: list = []

        def __init__(self):
            self.updated = asyncio.Event()

        async def update(self) -> None:
            self.updated.set()

    def _exploding_value(obj: object) -> str:
        raise RuntimeError("value compute exploded")

    monkeypatch.setattr(sb, "_monitor_value", _exploding_value)

    monitor = _GoodWidget()
    try:
        task = asyncio.create_task(
            run_monitor_loop(monitor, 0.01, splay=False, immediate=True)
        )
        await asyncio.wait_for(monitor.updated.wait(), timeout=2)
        await asyncio.sleep(0.05)  # let the post-update else branch run

        entry = board.monitors.get("good_widget")
        assert entry is not None, "monitor must be registered"
        assert entry.get("error") is None, (
            "a raise in _monitor_value must NOT record a monitor error "
            "(the update itself succeeded)"
        )
        # The loop must still be running — it did not crash.
        assert not task.done(), "loop must survive a raising _monitor_value"
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
    finally:
        sb.set_active_board(None)


@pytest.mark.asyncio
async def test_run_monitor_loop_records_value_for_container(tmp_path):
    """After a successful Container update, value reflects 'N items'."""
    import asyncio

    from led_ticker.status_board import StatusBoard

    class _FakeContainer:
        name = "RSS Fake"
        feed_stories: list = []

        def __init__(self):
            self.updated = asyncio.Event()
            self.feed_stories = ["story1", "story2"]

        async def update(self) -> None:
            self.updated.set()

    board = StatusBoard(path=tmp_path / "status.json")
    status_board.set_active_board(board)
    monitor = _FakeContainer()
    try:
        task = asyncio.create_task(
            run_monitor_loop(monitor, 0.01, splay=False, immediate=True)
        )
        await asyncio.wait_for(monitor.updated.wait(), timeout=2)
        await asyncio.sleep(0.05)
        entry = board.monitors.get("RSS Fake")
        assert entry is not None
        assert entry["value"] == "2 items", (
            f"value should be '2 items', got {entry['value']!r}"
        )
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
    finally:
        status_board.clear_active_board()
