"""Tests for StatusBoard publishing: schema, atomicity, throttle, self-disable."""

import asyncio
import json
import logging as _logging

from led_ticker import status_board
from led_ticker.status_board import SCHEMA_VERSION, StatusBoard

# The status.json contract. If this set changes, SCHEMA_VERSION must bump —
# the sidecar names a mismatch instead of misrendering.
EXPECTED_TOP_LEVEL_KEYS = {
    "schema",
    "published_at",
    "min_interval",
    "started_at",
    "hostname",
    "config_path",
    "geometry",
    "plugins",
    "failed_plugins",
    "section",
    "widget",
    "monitor_updates",
    "log_tail",
}


def _board(tmp_path, **kw):
    return StatusBoard(path=tmp_path / "status.json", **kw)


def test_schema_tripwire(tmp_path):
    snap = _board(tmp_path).snapshot()
    assert set(snap.keys()) == EXPECTED_TOP_LEVEL_KEYS, (
        "status.json field set changed. Update EXPECTED_TOP_LEVEL_KEYS AND bump "
        "SCHEMA_VERSION in src/led_ticker/status_board.py (the sidecar refuses "
        "schemas it doesn't know)."
    )
    assert snap["schema"] == SCHEMA_VERSION == 1


def test_publish_roundtrip(tmp_path):
    board = _board(tmp_path)
    board.config_path = "/code/config/config.toml"
    board.publish(force=True)
    on_disk = json.loads((tmp_path / "status.json").read_text())
    assert on_disk["schema"] == SCHEMA_VERSION
    assert on_disk["config_path"] == "/code/config/config.toml"
    assert on_disk["published_at"] > 0


def test_publish_is_atomic_no_tmp_left_behind(tmp_path):
    board = _board(tmp_path)
    board.publish(force=True)
    leftovers = [p.name for p in tmp_path.iterdir() if p.name != "status.json"]
    assert leftovers == []


def test_publish_creates_parent_dir(tmp_path):
    board = StatusBoard(path=tmp_path / "deep" / "nested" / "status.json")
    board.publish(force=True)
    assert (tmp_path / "deep" / "nested" / "status.json").exists()


def test_throttle_drops_writes_inside_interval(tmp_path):
    board = _board(tmp_path, min_interval=3600.0)  # nothing un-forced can land twice
    board.publish(force=True)
    first = (tmp_path / "status.json").read_text()
    board.config_path = "/changed"
    board.publish(force=False)  # inside interval, no loop running -> dropped (dirty)
    assert (tmp_path / "status.json").read_text() == first
    board.publish(force=True)  # force always writes
    on_disk = json.loads((tmp_path / "status.json").read_text())
    assert on_disk["config_path"] == "/changed"


async def test_throttle_flushes_dirty_state_via_loop(tmp_path):
    board = _board(tmp_path, min_interval=0.05)
    board.publish(force=True)
    board.config_path = "/late"
    board.publish(force=False)  # gated -> schedules a delayed flush
    await asyncio.sleep(0.15)
    assert json.loads((tmp_path / "status.json").read_text())["config_path"] == "/late"


def test_publish_failure_disables_silently(tmp_path, caplog):
    board = StatusBoard(path=tmp_path)  # a directory: os.replace onto it fails
    board.publish(force=True)  # must NOT raise
    assert board.disabled is True
    board.publish(force=True)  # subsequent calls are no-ops, still no raise
    assert "disabling" in caplog.text


def test_module_record_functions_noop_without_active_board():
    status_board.clear_active_board()
    # Must not raise when no board is active.
    status_board.record_monitor_update("RSSFeedMonitor")
    status_board.record_widget_visit(object())
    status_board.record_section(index=0, total=1, mode="swap", title="", widget_count=0)


def test_log_handler_captures_warning_and_bounds(tmp_path):
    from led_ticker.status_board import LOG_TAIL_MAX, StatusLogHandler

    board = _board(tmp_path)
    handler = StatusLogHandler(board)
    log = _logging.getLogger("test.status.tail")
    log.addHandler(handler)
    try:
        log.info("invisible")  # below handler level
        for i in range(LOG_TAIL_MAX + 10):
            log.warning("warn %d", i)
    finally:
        log.removeHandler(handler)
    assert len(board.log_tail) == LOG_TAIL_MAX
    assert board.log_tail[-1]["message"] == f"warn {LOG_TAIL_MAX + 9}"
    assert board.log_tail[-1]["level"] == "WARNING"
    assert all(e["message"] != "invisible" for e in board.log_tail)


def test_log_handler_survives_disabled_board(tmp_path):
    from led_ticker.status_board import StatusLogHandler

    board = _board(tmp_path)
    board.disabled = True
    handler = StatusLogHandler(board)
    log = _logging.getLogger("test.status.disabled")
    log.addHandler(handler)
    try:
        log.warning("must not raise")  # publish is a no-op; emit must not raise
    finally:
        log.removeHandler(handler)


def test_record_monitor_update_with_active_board(tmp_path):
    board = _board(tmp_path)
    status_board.set_active_board(board)
    try:
        status_board.record_monitor_update("RSS BBC")
        assert "RSS BBC" in board.monitor_updates
        assert board.monitor_updates["RSS BBC"] > 0
    finally:
        status_board.clear_active_board()


def test_record_section_publishes_immediately(tmp_path):
    board = _board(tmp_path, min_interval=3600.0)
    status_board.set_active_board(board)
    try:
        # Advance _last_publish so it's non-zero — the throttle window is now
        # 3600 s in the future.  Only force=True inside record_section can land.
        board.publish(force=True)
        status_board.record_section(
            index=1, total=3, mode="swap", title="news", widget_count=4
        )
        on_disk = json.loads((tmp_path / "status.json").read_text())
        assert on_disk["section"]["mode"] == "swap"
        assert on_disk["section"]["index"] == 1
    finally:
        status_board.clear_active_board()


def test_widget_summary_shapes(tmp_path):
    class FakeText:
        text = "Hello world " * 20  # > 80 chars

    class FakePath:
        path = "/code/assets/cat.gif"

    class Bare:
        pass

    board = _board(tmp_path)
    status_board.set_active_board(board)
    try:
        status_board.record_widget_visit(FakeText())
        assert board.widget["type"] == "FakeText"
        assert len(board.widget["summary"]) == 80

        status_board.record_widget_visit(FakePath())
        assert board.widget["summary"] == "/code/assets/cat.gif"

        status_board.record_widget_visit(Bare())
        assert board.widget == {"type": "Bare", "summary": ""}
    finally:
        status_board.clear_active_board()
