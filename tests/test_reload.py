import asyncio
import os
import time

from led_ticker import reload as rl
from led_ticker.config import load_config
from led_ticker.render_breaker import RenderBreaker


def _write(path, body):
    path.write_text(body)
    return path


_MIN = '[display]\nrows = 16\ncols = 32\n\n[[playlist.section]]\nmode = "slideshow"\n'


def test_watcher_no_change_when_unchanged(tmp_path):
    p = _write(tmp_path / "c.toml", _MIN)
    w = rl.ConfigWatcher(p)
    assert w.changed() is False


def test_watcher_detects_content_change(tmp_path):
    p = _write(tmp_path / "c.toml", _MIN)
    w = rl.ConfigWatcher(p)
    p.write_text(_MIN + "\n# edited\n")
    os.utime(p, (time.time() + 5, time.time() + 5))  # ensure mtime advances
    assert w.changed() is True


def test_watcher_ignores_noop_touch(tmp_path):
    p = _write(tmp_path / "c.toml", _MIN)
    w = rl.ConfigWatcher(p)
    os.utime(p, (time.time() + 5, time.time() + 5))  # mtime bump, identical bytes
    assert w.changed() is False


def test_watcher_disabled_never_changes(tmp_path):
    p = _write(tmp_path / "c.toml", _MIN)
    w = rl.ConfigWatcher(p, enabled=False)
    p.write_text(_MIN + "\n# edited\n")
    os.utime(p, (time.time() + 5, time.time() + 5))
    assert w.changed() is False


def test_watcher_missing_file_no_change(tmp_path):
    p = _write(tmp_path / "c.toml", _MIN)
    w = rl.ConfigWatcher(p)
    p.unlink()
    assert w.changed() is False  # no raise


def test_watcher_vanished_then_restored_is_detected(tmp_path):
    """A file deleted mid-check must not advance _last_mtime; a later
    restore with new content must still be detected on the next poll."""
    p = _write(tmp_path / "c.toml", _MIN)
    w = rl.ConfigWatcher(p)
    # Simulate: file vanishes between stat and hash (unlink after we grab a new mtime)
    p.unlink()
    assert w.changed() is False  # vanished → no advance
    # Restore with different content and a future mtime
    _write(p, _MIN + "\n# restored\n")
    os.utime(p, (time.time() + 10, time.time() + 10))
    assert w.changed() is True  # restored file detected


async def test_load_and_validate_valid(tmp_path):
    p = _write(tmp_path / "c.toml", _MIN)
    cfg, errors, transient = await rl.load_and_validate(p)
    assert cfg is not None and errors == [] and transient is False


async def test_load_and_validate_invalid_returns_string_errors(tmp_path):
    # A config that fails validation: rule 1 (content_height × scale > panel height).
    # rows=8 → panel_h=8; content_height=20 → 20 > 8 → error.
    # Uses [[playlist.section]] (the correct TOML key load_config reads).
    bad = (
        "[display]\nrows = 8\ncols = 32\n\n"
        '[[playlist.section]]\nmode = "slideshow"\ncontent_height = 20\n'
    )
    p = _write(tmp_path / "c.toml", bad)
    cfg, errors, transient = await rl.load_and_validate(p)
    assert cfg is None and transient is False
    assert errors and all(isinstance(e, str) for e in errors)
    # Contract: errors are formatted as "location: message"
    assert any(":" in e for e in errors)


async def test_load_and_validate_missing_file_is_transient(tmp_path):
    cfg, errors, transient = await rl.load_and_validate(tmp_path / "gone.toml")
    assert cfg is None and errors == [] and transient is True


def test_nonreloadable_changed_hardware_field(tmp_path):
    a = load_config(_write(tmp_path / "a.toml", _MIN))
    b_toml = (
        '[display]\nrows = 32\ncols = 32\n\n[[playlist.section]]\nmode = "slideshow"\n'
    )
    b = load_config(_write(tmp_path / "b.toml", b_toml))
    assert "display.rows" in rl.nonreloadable_changed(a, b)


def test_nonreloadable_changed_section_only_is_empty(tmp_path):
    a = load_config(_write(tmp_path / "a.toml", _MIN))
    extra = '[[playlist.section.widget]]\ntype = "message"\ntext = "hi"\n'
    b = load_config(_write(tmp_path / "b.toml", _MIN + extra))
    # Both configs have a real section; only sections differ, not display.
    assert a.sections and b.sections, "fixture must produce non-empty sections"
    # Verify the configs' sections actually differ (b has an extra widget)
    assert len(a.sections[0].widgets) == 0 and len(b.sections[0].widgets) == 1
    # A genuine section-only edit is fully reloadable (no restart required)
    assert rl.nonreloadable_changed(a, b) == []


def test_nonreloadable_changed_brightness_is_reloadable(tmp_path):
    a = load_config(_write(tmp_path / "a.toml", _MIN))
    b_toml = (
        "[display]\nrows = 16\ncols = 32\nbrightness = 50\n\n"
        '[[playlist.section]]\nmode = "slideshow"\n'
    )
    b = load_config(_write(tmp_path / "b.toml", b_toml))
    assert "display.brightness" not in rl.nonreloadable_changed(a, b)


def test_every_frame_field_is_restart_required():
    """Drift guard: every display.* field build_frame_from_config consumes must be
    restart-required (NOT in RELOADABLE_DISPLAY_FIELDS), so a future frame field can
    never be silently treated as hot-reloadable.

    frame_fields is DERIVED from build_frame_from_config's source via regex so a new
    frame field added to the function but forgotten in this set can't slip through.
    brightness is excluded: it is consumed by build_frame_from_config (initial LED
    brightness) AND listed in RELOADABLE_DISPLAY_FIELDS (hot-reload adjusts it live).
    """
    import inspect
    import re
    from dataclasses import fields

    from led_ticker.app.factories import build_frame_from_config
    from led_ticker.config import DisplayConfig

    src = inspect.getsource(build_frame_from_config)
    # Extract every `display.<name>` reference from the function body.
    frame_fields = set(re.findall(r"display\.(\w+)", src)) - {"brightness"}

    declared = {f.name for f in fields(DisplayConfig)}
    # derived set must be non-trivially large (catches regex failure)
    assert len(frame_fields) >= 15, f"derived frame_fields too small: {frame_fields}"
    # every derived field must actually exist on DisplayConfig (catches renames)
    assert frame_fields <= declared, frame_fields - declared
    # and none of them may be reloadable
    assert frame_fields.isdisjoint(rl.RELOADABLE_DISPLAY_FIELDS)


# ---------------------------------------------------------------------------
# _apply_reload tests
# ---------------------------------------------------------------------------

_DISPLAY = "[display]\nrows=16\ncols=32\n\n"


async def test_apply_reload_evicts_changed_keeps_unchanged(tmp_path):
    # config A: one message widget "keep" + one "drop"
    a = load_config(
        _write(
            tmp_path / "a.toml",
            _DISPLAY + '[[playlist.section]]\nmode = "slideshow"\n'
            '[[playlist.section.widget]]\ntype="message"\ntext="keep"\n'
            '[[playlist.section.widget]]\ntype="message"\ntext="drop"\n',
        )
    )
    # config B: "keep" stays, "drop" removed
    b = load_config(
        _write(
            tmp_path / "b.toml",
            _DISPLAY + '[[playlist.section]]\nmode = "slideshow"\n'
            '[[playlist.section.widget]]\ntype="message"\ntext="keep"\n',
        )
    )

    from types import SimpleNamespace

    from led_ticker.app.factories import _cache_key

    keep_key = _cache_key(dict(a.sections[0].widgets[0]))
    drop_key = _cache_key(dict(a.sections[0].widgets[1]))

    keep_task = asyncio.ensure_future(asyncio.sleep(3600))
    drop_task = asyncio.ensure_future(asyncio.sleep(3600))
    widget_cache = {keep_key: object(), drop_key: object()}
    widget_tasks = {keep_key: {keep_task}, drop_key: {drop_task}}
    keep_widget = widget_cache[keep_key]

    breaker = RenderBreaker()
    breaker.trip(SimpleNamespace(text="x"), ValueError("boom"))

    respawned = []

    async def fake_respawn(old_task, cfg):
        respawned.append(cfg)
        return "NEW_SCHEDULE_TASK"

    new_sched, _new_src_task, restart = await rl._apply_reload(
        b,
        old_config=a,
        widget_cache=widget_cache,
        widget_tasks=widget_tasks,
        render_breaker=breaker,
        schedule_task="OLD",
        respawn_schedule=fake_respawn,
    )

    # unchanged widget + its task survive; removed widget + task evicted/cancelled
    assert keep_key in widget_cache and widget_cache[keep_key] is keep_widget
    assert drop_key not in widget_cache and drop_key not in widget_tasks
    # cancel requested — allow a tick to settle then check cancelled()
    await asyncio.sleep(0)
    assert drop_task.cancelled()
    assert not keep_task.cancelled()
    keep_task.cancel()
    # breaker reset + schedule respawned + no restart_required (section-only change)
    assert breaker.disabled == {}
    assert new_sched == "NEW_SCHEDULE_TASK" and respawned == [b]
    assert restart == []


def test_config_hash_matches_sha256(tmp_path):
    import hashlib

    from led_ticker.reload import config_hash

    p = tmp_path / "c.toml"
    p.write_bytes(b"[display]\nrows = 16\n")
    assert config_hash(p) == hashlib.sha256(b"[display]\nrows = 16\n").hexdigest()


def test_config_hash_missing_file_is_none(tmp_path):
    from led_ticker.reload import config_hash

    assert config_hash(tmp_path / "nope.toml") is None


async def test_apply_reload_reports_restart_required(tmp_path):
    a = load_config(
        _write(
            tmp_path / "a.toml",
            _DISPLAY + '[[playlist.section]]\nmode = "slideshow"\n',
        )
    )
    b = load_config(
        _write(
            tmp_path / "b.toml",
            '[display]\nrows=32\ncols=32\n\n[[playlist.section]]\nmode = "slideshow"\n',
        )
    )

    async def fake_respawn(old_task, cfg):
        return None

    _, _new_src_task, restart = await rl._apply_reload(
        b,
        old_config=a,
        widget_cache={},
        widget_tasks={},
        render_breaker=RenderBreaker(),
        schedule_task=None,
        respawn_schedule=fake_respawn,
    )
    assert "display.rows" in restart


# ---------------------------------------------------------------------------
# Task 8: source-registry hot-reload tests
# ---------------------------------------------------------------------------

_DISPLAY_WITH_SOURCE = _DISPLAY + '[[source]]\nid = "clock.now"\ntype = "clock"\n\n'
_DISPLAY_WITH_SOURCE_B = (
    _DISPLAY + '[[source]]\nid = "brand.tag"\ntype = "static"\nvalue = "hello"\n\n'
)
_SECTION = '[[playlist.section]]\nmode = "slideshow"\n'


async def test_apply_reload_swaps_registry_atomically(tmp_path):
    """After _apply_reload the global registry is a NEW object (not the old one)."""
    from led_ticker.sources import DataRegistry, get_data_registry, set_data_registry

    # Seed an "old" registry as the global
    old_reg = DataRegistry()
    set_data_registry(old_reg)

    a = load_config(_write(tmp_path / "a.toml", _DISPLAY_WITH_SOURCE + _SECTION))
    b = load_config(_write(tmp_path / "b.toml", _DISPLAY_WITH_SOURCE_B + _SECTION))

    async def fake_respawn(old_task, cfg):
        return None

    await rl._apply_reload(
        b,
        old_config=a,
        widget_cache={},
        widget_tasks={},
        render_breaker=RenderBreaker(),
        schedule_task=None,
        respawn_schedule=fake_respawn,
        source_refresh_task=None,
    )

    new_reg = get_data_registry()
    assert new_reg is not old_reg, "registry must be a new object, not the old one"
    # The new registry must contain the source from config B, not config A
    assert new_reg.get("brand.tag") is not None
    assert new_reg.get("clock.now") is None


async def test_apply_reload_cancels_old_ticker_and_spawns_new(tmp_path):
    """Old source-refresh task is cancelled; a new one is spawned."""
    from led_ticker.sources import DataRegistry, get_data_registry, set_data_registry

    old_reg = DataRegistry()
    set_data_registry(old_reg)

    a = load_config(_write(tmp_path / "a.toml", _DISPLAY_WITH_SOURCE + _SECTION))
    b = load_config(_write(tmp_path / "b.toml", _DISPLAY_WITH_SOURCE_B + _SECTION))

    old_refresh_task = asyncio.ensure_future(asyncio.sleep(3600))

    async def fake_respawn(old_task, cfg):
        return None

    _new_sched, new_src_task, _ = await rl._apply_reload(
        b,
        old_config=a,
        widget_cache={},
        widget_tasks={},
        render_breaker=RenderBreaker(),
        schedule_task=None,
        respawn_schedule=fake_respawn,
        source_refresh_task=old_refresh_task,
    )

    await asyncio.sleep(0)  # let cancellation propagate
    assert old_refresh_task.cancelled(), "old source-refresh task must be cancelled"

    # spawn_source_refresh now returns a LIST of handles (1 Hz sync task + one per
    # polled source). A new non-empty list is returned and is not the old single task.
    assert isinstance(new_src_task, list) and len(new_src_task) > 0
    assert new_src_task is not old_refresh_task
    for t in new_src_task:
        t.cancel()  # clean up

    # The new registry must have been spawned a refresh task (verify via registry)
    assert get_data_registry().get("brand.tag") is not None


async def test_apply_reload_removed_source_absent_from_new_registry(tmp_path):
    """A source id removed in new config must not appear in the new registry."""
    from led_ticker.sources import DataRegistry, get_data_registry, set_data_registry

    old_reg = DataRegistry()
    set_data_registry(old_reg)

    a = load_config(_write(tmp_path / "a.toml", _DISPLAY_WITH_SOURCE + _SECTION))
    # Config B has NO [[source]] blocks
    b = load_config(_write(tmp_path / "b.toml", _DISPLAY + _SECTION))

    async def fake_respawn(old_task, cfg):
        return None

    await rl._apply_reload(
        b,
        old_config=a,
        widget_cache={},
        widget_tasks={},
        render_breaker=RenderBreaker(),
        schedule_task=None,
        respawn_schedule=fake_respawn,
        source_refresh_task=None,
    )

    new_reg = get_data_registry()
    # Removed source id must not appear in the new registry
    assert new_reg.get("clock.now") is None


async def test_apply_reload_no_sources_still_works(tmp_path):
    """A reload with no [[source]] blocks at all completes without crashing."""
    from led_ticker.sources import DataRegistry, get_data_registry, set_data_registry

    old_reg = DataRegistry()
    set_data_registry(old_reg)

    a = load_config(_write(tmp_path / "a.toml", _DISPLAY + _SECTION))
    b = load_config(_write(tmp_path / "b.toml", _DISPLAY + _SECTION))

    async def fake_respawn(old_task, cfg):
        return None

    # Must not raise
    await rl._apply_reload(
        b,
        old_config=a,
        widget_cache={},
        widget_tasks={},
        render_breaker=RenderBreaker(),
        schedule_task=None,
        respawn_schedule=fake_respawn,
        source_refresh_task=None,
    )

    new_reg = get_data_registry()
    # A brand-new empty registry is swapped in
    assert new_reg is not old_reg
    assert list(new_reg.ids()) == []


async def test_apply_reload_bad_source_type_does_not_crash(tmp_path):
    """CRITICAL crash-safety: if build_source raises (e.g. unknown source type),
    _apply_reload must NOT raise, the global registry must remain the old one
    (identity unchanged), and the old refresh task must NOT be cancelled.

    This is the runtime safety net for live reloads where validate is opt-in.
    Fails before the fix (ValueError propagates); passes after.
    """
    import types

    from led_ticker.config import SourceConfig
    from led_ticker.sources import DataRegistry, get_data_registry, set_data_registry

    # Seed an "old" registry as the global
    old_reg = DataRegistry()
    set_data_registry(old_reg)

    # Build a base config via load_config, then inject a bad SourceConfig
    # directly — bypassing load_config so validation doesn't block it.
    base_cfg = load_config(_write(tmp_path / "base.toml", _DISPLAY + _SECTION))
    bad_source = SourceConfig(id="bad.src", type="no_such_type")
    # Construct a new_config with the bad source spliced in (SimpleNamespace wraps it
    # so _apply_reload's new_config.sources iteration hits our planted bad entry).
    new_config = types.SimpleNamespace(
        sections=base_cfg.sections,
        sources=[bad_source],
        display=base_cfg.display,
        busy_light=base_cfg.busy_light,
        plugins=base_cfg.plugins,
        web=getattr(base_cfg, "web", None),
    )

    old_refresh_task = asyncio.ensure_future(asyncio.sleep(3600))

    async def fake_respawn(old_task, cfg):
        return "SCHEDULE_TASK"

    # Must NOT raise despite the unknown source type
    new_sched, returned_src_task, _ = await rl._apply_reload(
        new_config,
        old_config=base_cfg,
        widget_cache={},
        widget_tasks={},
        render_breaker=RenderBreaker(),
        schedule_task=None,
        respawn_schedule=fake_respawn,
        source_refresh_task=old_refresh_task,
    )

    # Registry identity must be unchanged — old registry kept live
    assert get_data_registry() is old_reg, (
        "bad source type must NOT swap in a new (empty) registry"
    )

    # Old refresh task must NOT be cancelled — it's still the live ticker
    await asyncio.sleep(0)
    assert not old_refresh_task.cancelled(), (
        "old source-refresh task must remain live after a failed source rebuild"
    )

    # The returned task handle must be the original (unchanged) so the caller
    # can still cancel it on the next reload
    assert returned_src_task is old_refresh_task

    # Cleanup
    old_refresh_task.cancel()


# ---------------------------------------------------------------------------
# Task 5: list-of-handles hot-reload tests
# ---------------------------------------------------------------------------


async def test_apply_reload_cancels_all_handles_in_old_list(tmp_path):
    """When source_refresh_task is a LIST (Task 5 shape), every handle must be
    cancelled on a successful reload and a NEW list must be returned."""
    from led_ticker.sources import DataRegistry, set_data_registry

    old_reg = DataRegistry()
    set_data_registry(old_reg)

    a = load_config(_write(tmp_path / "a.toml", _DISPLAY_WITH_SOURCE + _SECTION))
    b = load_config(_write(tmp_path / "b.toml", _DISPLAY_WITH_SOURCE_B + _SECTION))

    # Simulate the Task 5 shape: old source_refresh_task is a LIST of handles
    old_handle_1 = asyncio.ensure_future(asyncio.sleep(3600))
    old_handle_2 = asyncio.ensure_future(asyncio.sleep(3600))
    old_task_list = [old_handle_1, old_handle_2]

    async def fake_respawn(old_task, cfg):
        return None

    _new_sched, new_src_tasks, _ = await rl._apply_reload(
        b,
        old_config=a,
        widget_cache={},
        widget_tasks={},
        render_breaker=RenderBreaker(),
        schedule_task=None,
        respawn_schedule=fake_respawn,
        source_refresh_task=old_task_list,
    )

    await asyncio.sleep(0)  # let cancellations propagate
    assert old_handle_1.cancelled(), "handle 1 in old list must be cancelled"
    assert old_handle_2.cancelled(), "handle 2 in old list must be cancelled"

    # spawn_source_refresh returns a list; verify new result is a non-empty list
    assert isinstance(new_src_tasks, list) and len(new_src_tasks) > 0
    assert new_src_tasks is not old_task_list
    for t in new_src_tasks:
        t.cancel()


async def test_apply_reload_bad_source_keeps_old_task_list_intact(tmp_path):
    """CRITICAL: if build_source raises, _apply_reload must NOT cancel ANY
    handle in the old list — all old handles must remain live."""
    import types

    from led_ticker.config import SourceConfig
    from led_ticker.sources import DataRegistry, get_data_registry, set_data_registry

    old_reg = DataRegistry()
    set_data_registry(old_reg)

    base_cfg = load_config(_write(tmp_path / "base.toml", _DISPLAY + _SECTION))
    bad_source = SourceConfig(id="bad.src", type="no_such_type")
    new_config = types.SimpleNamespace(
        sections=base_cfg.sections,
        sources=[bad_source],
        display=base_cfg.display,
        busy_light=base_cfg.busy_light,
        plugins=base_cfg.plugins,
        web=getattr(base_cfg, "web", None),
    )

    # Simulate the Task 5 shape: old source_refresh_task is a LIST of handles
    old_handle_1 = asyncio.ensure_future(asyncio.sleep(3600))
    old_handle_2 = asyncio.ensure_future(asyncio.sleep(3600))
    old_task_list = [old_handle_1, old_handle_2]

    async def fake_respawn(old_task, cfg):
        return "SCHEDULE_TASK"

    _new_sched, returned_tasks, _ = await rl._apply_reload(
        new_config,
        old_config=base_cfg,
        widget_cache={},
        widget_tasks={},
        render_breaker=RenderBreaker(),
        schedule_task=None,
        respawn_schedule=fake_respawn,
        source_refresh_task=old_task_list,
    )

    await asyncio.sleep(0)
    # Old registry identity must be unchanged
    assert get_data_registry() is old_reg

    # Neither old handle must be cancelled — they're still the live tickers
    assert not old_handle_1.cancelled(), (
        "handle 1 must remain live after failed rebuild"
    )
    assert not old_handle_2.cancelled(), (
        "handle 2 must remain live after failed rebuild"
    )

    # The returned value must be the original list (unchanged)
    assert returned_tasks is old_task_list

    # Cleanup
    old_handle_1.cancel()
    old_handle_2.cancel()


async def test_apply_reload_session_passed_to_build_source(tmp_path):
    """The session kwarg received by _apply_reload must be forwarded to
    build_source so polled sources get the shared aiohttp.ClientSession."""
    from unittest.mock import patch

    from led_ticker.sources import DataRegistry, set_data_registry

    old_reg = DataRegistry()
    set_data_registry(old_reg)

    base_cfg = load_config(
        _write(tmp_path / "base.toml", _DISPLAY_WITH_SOURCE + _SECTION)
    )

    async def fake_respawn(old_task, cfg):
        return None

    sentinel_session = object()
    captured_sessions: list = []

    import led_ticker.app.factories as _factories

    original_build_source = _factories.build_source

    def patched_build_source(cfg, session=None):
        captured_sessions.append(session)
        return original_build_source(cfg, session=session)

    # Patch in the factories module so the local import inside _apply_reload picks
    # it up (the function does `from led_ticker.app.factories import build_source`
    # on each call, binding to the module's current attribute at that moment).
    with patch.object(_factories, "build_source", patched_build_source):
        await rl._apply_reload(
            base_cfg,
            old_config=base_cfg,
            widget_cache={},
            widget_tasks={},
            render_breaker=RenderBreaker(),
            schedule_task=None,
            respawn_schedule=fake_respawn,
            source_refresh_task=None,
            session=sentinel_session,
        )

    # Every build_source call must have received the sentinel session
    assert len(captured_sessions) > 0
    assert all(s is sentinel_session for s in captured_sessions), (
        "expected sentinel session for all build_source calls, "
        f"got: {captured_sessions}"
    )
