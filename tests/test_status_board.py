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
    "swap_count",
    "overlays",
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
    assert snap["schema"] == SCHEMA_VERSION == 3


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


def test_record_widget_visit_survives_raising_text_property(tmp_path):
    """A widget whose text property raises must not propagate into the engine."""

    class BadWidget:
        @property
        def text(self):
            raise RuntimeError("broken property")

    board = _board(tmp_path)
    status_board.set_active_board(board)
    original_widget = board.widget  # capture before the call
    try:
        # Must not raise
        status_board.record_widget_visit(BadWidget())
        # Board widget field stays unchanged (the failed update was swallowed)
        assert board.widget == original_widget
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


def test_prepare_dir_creates_and_opens_permissions(tmp_path):
    # The rgbmatrix library drops root privileges during matrix
    # construction; prepare_dir runs BEFORE that (as root in production)
    # so the post-drop user can still create/replace files in the dir.
    board = StatusBoard(path=tmp_path / "deep" / "status.json")
    board.prepare_dir()
    mode = (tmp_path / "deep").stat().st_mode & 0o777
    assert mode == 0o777, "status dir must be writable by the post-drop user"


def test_flush_replaces_unwritable_leftover_tmp(tmp_path):
    # A crash between tmp-write and replace can leave a tmp file the
    # (possibly different) next writer can't open. _flush must unlink
    # it first rather than self-disabling on the EACCES.
    board = _board(tmp_path)
    tmp = tmp_path / "status.json.tmp"
    tmp.write_text("stale")
    tmp.chmod(0o444)
    board.publish(force=True)
    assert not board.disabled
    assert (
        json.loads((tmp_path / "status.json").read_text())["schema"] == SCHEMA_VERSION
    )


def test_widget_summary_joins_segments_and_strips_emoji(tmp_path):
    # SegmentMessage-style widgets (used by the data/plugin widgets) carry
    # (text, color) tuples instead of a .text attr — the summary must join
    # them, and panel emoji markup (:slug:) is noise on the web.
    class Seg:
        segments = [
            ("NYY 4", (255, 255, 255)),
            (":baseball.ball:", (255, 0, 0)),
            ("BOS 2", (200, 200, 200)),
        ]

    board = _board(tmp_path)
    status_board.set_active_board(board)
    try:
        status_board.record_widget_visit(Seg())
        assert board.widget == {"type": "Seg", "summary": "NYY 4 BOS 2"}
    finally:
        status_board.clear_active_board()


def test_record_section_strips_emoji_slugs(tmp_path):
    board = _board(tmp_path)
    status_board.set_active_board(board)
    try:
        status_board.record_section(
            index=0,
            total=1,
            mode="swap",
            title=":baseball.ball: MLB Standings :baseball.ball:",
            widget_count=1,
        )
        assert board.section["title"] == "MLB Standings"
    finally:
        status_board.clear_active_board()


def test_record_swap_increments_without_publishing(tmp_path):
    # record_swap runs at frame cadence inside LedFrame.swap() — it must be
    # increment-only: no publish, no file I/O, and a no-op without a board.
    status_board.record_swap()  # no active board: must not raise
    board = _board(tmp_path, min_interval=3600.0)
    status_board.set_active_board(board)
    try:
        for _ in range(5):
            status_board.record_swap()
        assert board.swap_count == 5
        assert not (tmp_path / "status.json").exists()  # nothing was written
    finally:
        status_board.clear_active_board()


def test_snapshot_has_overlays_with_roster_and_busy(tmp_path):
    board = _board(tmp_path)
    snap = board.snapshot()
    assert "overlays" in snap
    assert snap["overlays"] == {"roster": [], "busy": {"enabled": False}}


def test_set_overlay_roster_stores(tmp_path):
    board = _board(tmp_path)
    status_board.set_active_board(board)
    try:
        status_board.set_overlay_roster(
            [
                {"name": "busy_light", "kind": "core"},
                {"name": "acme.clock", "kind": "plugin"},
            ]
        )
        assert board.snapshot()["overlays"]["roster"][1]["name"] == "acme.clock"
    finally:
        status_board.clear_active_board()


def test_record_busy_stores(tmp_path):
    board = _board(tmp_path)
    status_board.set_active_board(board)
    try:
        status_board.record_busy(
            {"enabled": True, "active": True, "source": "http", "ttl_remaining": 12.0}
        )
        assert board.snapshot()["overlays"]["busy"]["active"] is True
    finally:
        status_board.clear_active_board()


def test_overlay_setters_noop_without_active_board(tmp_path):
    status_board.clear_active_board()
    status_board.set_overlay_roster([{"name": "x", "kind": "core"}])  # must not raise
    status_board.record_busy({"enabled": True})  # must not raise


def test_record_busy_does_not_write_file(tmp_path):
    # COST GUARD: record_busy is a pure setter — it must NOT publish/flush.
    # The heartbeat calls board.publish() right after; double-writing would
    # halve the zero-extra-I/O property.
    board = _board(tmp_path)
    status_board.set_active_board(board)
    try:
        status_board.record_busy({"enabled": True, "active": False})
        assert not (tmp_path / "status.json").exists()  # nothing written yet
        board.publish(force=True)
        assert (tmp_path / "status.json").exists()  # the explicit publish writes
    finally:
        status_board.clear_active_board()
