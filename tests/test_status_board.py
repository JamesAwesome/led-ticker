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
    "disabled_widgets",
    "plugin_reconcile",
    "last_reload",
    "config_validation",
    "section",
    "widget",
    "monitors",
    "swap_count",
    "overlays",
    "log_tail",
    "build",
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
    assert snap["schema"] == SCHEMA_VERSION == 9
    assert "disabled_widgets" in snap


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
    status_board.record_section(
        index=0, total=1, mode="slideshow", title="", widget_count=0
    )


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
        # register_monitor first (realistic path), then update — monitors is the
        # public dict serialized in snapshot as "monitors" list since schema 9.
        status_board.register_monitor("RSS BBC", "widget", 60)
        status_board.record_monitor_update("RSS BBC")
        assert "RSS BBC" in board.monitors
        assert board.monitors["RSS BBC"]["last_ok"] is not None
    finally:
        status_board.clear_active_board()


def test_record_monitor_update_self_heals_unregistered(tmp_path):
    """record_monitor_update on a name not in monitors.setdefault-materialises
    the row (mirrors record_monitor_error's self-heal behaviour)."""
    board = _board(tmp_path)
    status_board.set_active_board(board)
    try:
        # Deliberately skip register_monitor — update arrives for an unknown name.
        status_board.record_monitor_update("ghost.feed")
        assert "ghost.feed" in board.monitors, "self-heal: row should be created"
        entry = board.monitors["ghost.feed"]
        assert entry["last_ok"] is not None, "last_ok should be set"
        assert entry["error"] is None, "error should be None on first success"
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
            index=1, total=3, mode="slideshow", title="news", widget_count=4
        )
        on_disk = json.loads((tmp_path / "status.json").read_text())
        assert on_disk["section"]["mode"] == "slideshow"
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
            mode="slideshow",
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


def test_record_disabled_widget_appears_in_snapshot(tmp_path):
    from types import SimpleNamespace

    from led_ticker import status_board

    board = StatusBoard(path=tmp_path / "status.json")
    status_board.set_active_board(board)
    try:
        status_board.record_disabled_widget(
            SimpleNamespace(text="hi"), "ValueError: boom"
        )
    finally:
        status_board.clear_active_board()
    snap = board.snapshot()
    assert snap["disabled_widgets"], "expected a disabled widget entry"
    entry = snap["disabled_widgets"][0]
    assert entry["error"] == "ValueError: boom"
    # richer entry: uses _widget_summary → has "type" and "summary" keys
    assert "type" in entry
    assert "summary" in entry
    assert entry["summary"] == "hi"


def test_record_disabled_widget_dedups_by_label_and_error(tmp_path):
    from types import SimpleNamespace

    from led_ticker import status_board

    board = StatusBoard(path=tmp_path / "status.json")
    status_board.set_active_board(board)
    try:
        w = SimpleNamespace(text="hi")
        status_board.record_disabled_widget(w, "ValueError: boom")
        status_board.record_disabled_widget(w, "ValueError: boom")
    finally:
        status_board.clear_active_board()
    assert len(board.snapshot()["disabled_widgets"]) == 1


def test_record_disabled_widget_no_board_is_noop():
    """record_disabled_widget with no active board must return without error."""
    from types import SimpleNamespace

    status_board.clear_active_board()
    # Must not raise
    status_board.record_disabled_widget(SimpleNamespace(text="something"), "oops")


def test_record_disabled_widget_publish_raises_does_not_propagate(tmp_path):
    """If the board's publish() raises, record_disabled_widget must swallow it."""
    from types import SimpleNamespace
    from unittest.mock import patch

    from led_ticker.status_board import StatusBoard

    board = StatusBoard(path=tmp_path / "status.json")
    status_board.set_active_board(board)
    try:
        # Patch at the CLASS level (attrs instances are read-only; class-level
        # patch affects this instance's method lookup).
        with patch.object(
            StatusBoard, "publish", side_effect=RuntimeError("disk full")
        ):
            # Must not propagate
            status_board.record_disabled_widget(SimpleNamespace(text="x"), "boom")
    finally:
        status_board.clear_active_board()


def test_record_reload_success_appears_in_snapshot(tmp_path):
    from led_ticker import status_board

    board = StatusBoard(path=tmp_path / "status.json")
    status_board.set_active_board(board)
    try:
        status_board.record_reload(
            ok=True, ts="2026-06-20T10:00:00", restart_required=["display.rows"]
        )
    finally:
        status_board.clear_active_board()
    lr = board.snapshot()["last_reload"]
    assert lr["ok"] is True
    assert lr["at"] == "2026-06-20T10:00:00"
    assert lr["restart_required"] == ["display.rows"]


def test_record_reload_failure_carries_error(tmp_path):
    from led_ticker import status_board

    board = StatusBoard(path=tmp_path / "status.json")
    status_board.set_active_board(board)
    try:
        status_board.record_reload(ok=False, ts="t", error="section 2: bad widget")
    finally:
        status_board.clear_active_board()
    lr = board.snapshot()["last_reload"]
    assert lr["ok"] is False
    assert lr["error"] == "section 2: bad widget"


def test_clear_disabled_widgets_empties_the_list(tmp_path):
    from types import SimpleNamespace

    from led_ticker import status_board

    board = StatusBoard(path=tmp_path / "status.json")
    status_board.set_active_board(board)
    try:
        status_board.record_disabled_widget(SimpleNamespace(text="x"), "boom")
        assert board.snapshot()["disabled_widgets"]  # populated
        status_board.clear_disabled_widgets()
    finally:
        status_board.clear_active_board()
    assert board.snapshot()["disabled_widgets"] == []


def test_record_reload_never_raises_without_active_board():
    from led_ticker import status_board

    status_board.clear_active_board()
    status_board.record_reload(ok=True, ts="t")  # must not raise
    status_board.clear_disabled_widgets()  # must not raise


def test_record_config_validation_populates_field(tmp_path):
    from led_ticker.status_board import (
        clear_active_board,
        record_config_validation,
        set_active_board,
    )

    board = _board(tmp_path)
    set_active_board(board)
    try:
        record_config_validation(
            errors=[
                {
                    "rule": 1,
                    "location": "section[0]",
                    "message": "bad",
                    "fix": "fix it",
                }
            ],
            warnings=[],
            ts="2026-06-22T13:00:00",
        )
        cv = board.snapshot()["config_validation"]
        assert cv["at"] == "2026-06-22T13:00:00"
        assert cv["errors"][0]["message"] == "bad"
        assert cv["warnings"] == []
    finally:
        clear_active_board()


def test_record_config_validation_no_active_board_is_noop(tmp_path):
    from led_ticker.status_board import clear_active_board, record_config_validation

    clear_active_board()
    # Must not raise with no active board.
    record_config_validation(errors=[], warnings=[], ts="2026-06-22T13:00:00")


def test_reconcile_recorded_in_snapshot(tmp_path):
    from led_ticker import status_board
    from led_ticker.plugin_reconcile import PluginAction

    board = _board(tmp_path)
    status_board._ACTIVE = board
    try:
        status_board.record_plugin_reconcile(
            [PluginAction("rss", "installed", "0.2.0")]
        )
        snap = board.snapshot()
        assert snap["schema"] == SCHEMA_VERSION
        assert snap["plugin_reconcile"][0]["namespace"] == "rss"
        assert snap["plugin_reconcile"][0]["action"] == "installed"
        assert snap["plugin_reconcile"][0]["detail"] == "0.2.0"
    finally:
        status_board.clear_active_board()


def test_record_plugin_reconcile_no_board_is_noop():
    from led_ticker import status_board
    from led_ticker.plugin_reconcile import PluginAction

    status_board.clear_active_board()
    # Must not raise with no active board.
    status_board.record_plugin_reconcile([PluginAction("rss", "installed", "0.2.0")])


def test_snapshot_carries_build_ref(tmp_path, monkeypatch):
    monkeypatch.setenv("LED_TICKER_BUILD_REF", "feat/x@abc1234")
    snap = _board(tmp_path).snapshot()
    assert snap["build"] == "feat/x@abc1234"


# --- Task 1: monitors roster + register/error/clear + _monitor_name -----------


def test_monitor_name_prefers_id_then_name_then_class():
    from led_ticker.status_board import _monitor_name

    class _Src:  # a source: has .id
        id = "weather.nyc"

    class _Wid:  # a widget with a .name
        name = "RSS BBC"

    class _Bare:
        pass

    assert _monitor_name(_Src()) == "weather.nyc"
    assert _monitor_name(_Wid()) == "RSS BBC"
    assert _monitor_name(_Bare()) == "_Bare"


def test_register_record_update_and_error(tmp_path):
    import led_ticker.status_board as sb

    board = sb.StatusBoard(path=tmp_path / "s.json")
    sb.set_active_board(board)
    try:
        sb.register_monitor("weather.nyc", "source", 1800)
        assert board.monitors["weather.nyc"] == {
            "kind": "source",
            "interval": 1800,
            "last_ok": None,
            "error": None,
        }
        sb.record_monitor_error("weather.nyc", "401 Unauthorized", 3, 240.0)
        assert board.monitors["weather.nyc"]["error"] == {
            "message": "401 Unauthorized",
            "consecutive": 3,
            "at": board.monitors["weather.nyc"]["error"]["at"],
            "retry_in": 240.0,
        }
        sb.record_monitor_update("weather.nyc")
        assert board.monitors["weather.nyc"]["last_ok"] is not None
        assert board.monitors["weather.nyc"]["error"] is None  # cleared on success
    finally:
        sb.clear_active_board()


def test_register_monitor_name_collision_suffixes(tmp_path):
    import led_ticker.status_board as sb

    board = sb.StatusBoard(path=tmp_path / "s.json")
    sb.set_active_board(board)
    try:
        n1 = sb.register_monitor("WeatherCurrentMonitor", "widget", 10800)
        n2 = sb.register_monitor("WeatherCurrentMonitor", "widget", 10800)
        assert n1 == "WeatherCurrentMonitor"
        assert n2 == "WeatherCurrentMonitor#2"
        assert set(board.monitors) == {
            "WeatherCurrentMonitor",
            "WeatherCurrentMonitor#2",
        }
    finally:
        sb.clear_active_board()


def test_clear_monitors(tmp_path):
    import led_ticker.status_board as sb

    board = sb.StatusBoard(path=tmp_path / "s.json")
    sb.set_active_board(board)
    try:
        sb.register_monitor("a", "source", 60)
        sb.register_monitor("b", "widget", 60)
        sb.clear_monitors()
        assert board.monitors == {}
    finally:
        sb.clear_active_board()


# --- Task 2: snapshot schema 8->9 — monitors[] replaces top-level monitor_updates ---


def test_snapshot_serializes_monitors_not_monitor_updates(tmp_path):
    import led_ticker.status_board as sb

    board = sb.StatusBoard(path=tmp_path / "s.json")
    sb.set_active_board(board)
    try:
        sb.register_monitor("weather.nyc", "source", 1800)
        sb.record_monitor_update("weather.nyc")
        snap = board.snapshot()
        assert "monitor_updates" not in snap
        entries = {m["name"]: m for m in snap["monitors"]}
        assert entries["weather.nyc"]["kind"] == "source"
        assert entries["weather.nyc"]["interval"] == 1800
        assert entries["weather.nyc"]["last_ok"] is not None
        assert entries["weather.nyc"]["error"] is None
    finally:
        sb.set_active_board(None)
