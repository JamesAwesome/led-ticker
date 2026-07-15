import asyncio
import importlib
from pathlib import Path
from types import SimpleNamespace

import pytest

import led_ticker.app.run as _run_mod_alias  # noqa: F401 — side-effect: registers module in sys.modules

run_mod = importlib.import_module("led_ticker.app.run")


def _frame():
    # Minimal duck-type for _respawn_schedule: exposes a settable `brightness`
    # attribute (led_frame.brightness = level after the backend refactor).
    return SimpleNamespace(brightness=100)


def _cfg(*, enabled, brightness=100, tz="UTC", display_tz=""):
    sched = SimpleNamespace(enabled=enabled, timezone=tz, windows=[])
    return SimpleNamespace(
        display=SimpleNamespace(
            schedule=sched, brightness=brightness, timezone=display_tz
        )
    )


async def test_respawn_schedule_disabled_sets_base_and_returns_none():
    frame = _frame()
    old = asyncio.ensure_future(asyncio.sleep(3600))
    task = await run_mod._respawn_schedule(
        old, _cfg(enabled=False, brightness=40), frame
    )
    assert task is None
    assert frame.brightness == 40
    assert old.cancelled() or old.cancelling()


async def test_respawn_schedule_enabled_spawns_and_cancels_old():
    frame = _frame()
    old = asyncio.ensure_future(asyncio.sleep(3600))
    task = await run_mod._respawn_schedule(old, _cfg(enabled=True), frame)
    assert task is not None and not task.done()
    assert old.cancelled() or old.cancelling()
    task.cancel()


async def test_respawn_schedule_sets_module_clock_from_display_timezone():
    """Fix F.1b (2026-07-15): _respawn_schedule must call
    schedule.set_schedule_timezone with [display] timezone (not the
    brightness-scheduler's own [display.schedule] timezone) so visibility
    schedules pick up a hot-reloaded (or boot-time) timezone change. Uses
    the real led_ticker.schedule module clock — reset in a finally so this
    test doesn't leak global state into later tests."""
    import led_ticker.schedule as _schedule_mod

    frame = _frame()
    cfg = _cfg(enabled=False, display_tz="America/Chicago")
    try:
        await run_mod._respawn_schedule(None, cfg, frame)
        assert str(_schedule_mod._SCHEDULE_TZ) == "America/Chicago"
    finally:
        _schedule_mod.set_schedule_timezone("")


async def test_build_widget_guarded_skips_on_build_error(monkeypatch):
    async def boom(*a, **k):
        raise ValueError("bad widget cfg")

    monkeypatch.setattr(run_mod, "_build_widget", boom)
    cache, tasks = {}, {}
    out = await run_mod._build_widget_guarded(
        {"type": "message", "text": "x"},
        session=None,
        config_dir=None,
        default_bg_color=None,
        panel_h_for_warning=None,
        coercion_collector=[],
        widget_cache=cache,
        widget_tasks=tasks,
    )
    assert out is None  # skipped, not raised
    assert cache == {} and tasks == {}  # not cached


async def test_build_widget_guarded_caches_on_success(monkeypatch):
    sentinel = object()

    async def ok(*a, **k):
        return sentinel

    monkeypatch.setattr(run_mod, "_build_widget", ok)
    cache, tasks = {}, {}
    cfg = {"type": "message", "text": "x"}
    out = await run_mod._build_widget_guarded(
        cfg,
        session=None,
        config_dir=None,
        default_bg_color=None,
        panel_h_for_warning=None,
        coercion_collector=[],
        widget_cache=cache,
        widget_tasks=tasks,
    )
    assert out is sentinel
    assert len(cache) == 1 and len(tasks) == 1  # cached + sink recorded


def test_run_wires_the_reload_sequence():
    import inspect

    src = inspect.getsource(run_mod.run)
    assert "ConfigWatcher(" in src  # watcher created
    # The detect-and-apply logic lives in _detect_and_apply_reload (not inlined):
    assert "_detect_and_apply_reload(" in src  # reload gate delegated to helper
    assert "_build_widget_guarded(" in src  # cache-miss build goes through the guard
    assert "_build_title_guarded(" in src  # title build goes through the guard
    # The helper itself must contain the reload primitives:
    helper_src = inspect.getsource(run_mod._detect_and_apply_reload)
    assert "load_and_validate(" in helper_src  # validate gate
    assert "_apply_reload(" in helper_src  # the swap
    assert "record_reload(" in helper_src  # status surfacing


def test_run_guards_inter_section_transition():
    """The inter-section entry run_transition() call must pass breaker=render_breaker.

    Without this, a widget raising during a section-boundary transition bypasses
    the circuit breaker and freezes the panel.  The behavioral freeze-safety is
    already proven by test_run_transition_survives_faulty_incoming; this is the
    wiring tripwire that keeps the call site from regressing.

    The previous substring assertion (`"breaker=render_breaker" in src`) was
    vacuous: `run()` also contains `render_breaker=render_breaker` (in the
    _apply_reload call), and `"breaker=render_breaker"` is a substring of
    `"render_breaker=render_breaker"`.  Removing `breaker=render_breaker` from
    the run_transition call left the test passing — so it did NOT catch the
    regression it existed for.  The AST walk below is the real guard.
    """
    import ast
    import importlib
    import inspect
    import textwrap

    run_mod = importlib.import_module("led_ticker.app.run")
    src = textwrap.dedent(inspect.getsource(run_mod.run))
    tree = ast.parse(src)
    calls = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "run_transition"
    ]
    assert calls, "no run_transition( call found in run()"
    # every run_transition call in run() must pass the breaker (freeze-safety wiring)
    assert all(any(k.arg == "breaker" for k in c.keywords) for c in calls), (
        "a run_transition() call in run() is missing breaker= — the inter-section "
        "transition would be unguarded (panel-freeze regression)"
    )


async def test_build_title_guarded_returns_none_on_error(monkeypatch):
    async def boom(*a, **k):
        raise ValueError("no such font xyz")

    monkeypatch.setattr(run_mod, "_build_title", boom)
    result = await run_mod._build_title_guarded(
        {"text": "bad title", "font": "no_such_font_xyz"},
        session=None,
        config_dir=None,
        default_bg_color=None,
        panel_h_for_warning=None,
    )
    assert result is None  # error suppressed, not propagated


async def test_build_title_guarded_returns_widget_on_success(monkeypatch):
    sentinel = object()

    async def ok(*a, **k):
        return sentinel

    monkeypatch.setattr(run_mod, "_build_title", ok)
    result = await run_mod._build_title_guarded(
        {"text": "hello"},
        session=None,
        config_dir=None,
        default_bg_color=None,
        panel_h_for_warning=None,
    )
    assert result is sentinel


async def test_build_widget_guarded_cancels_sink_tasks_on_build_error(monkeypatch):
    """When _build_widget raises after spawning background tasks, _build_widget_guarded
    must cancel those tasks and return None without caching anything."""
    captured_tasks: list[asyncio.Task] = []

    async def boom_after_spawn(*a, **k):
        task = run_mod.spawn_tracked(asyncio.sleep(3600))
        captured_tasks.append(task)
        raise ValueError("widget build failed mid-flight")

    monkeypatch.setattr(run_mod, "_build_widget", boom_after_spawn)
    cache, tasks = {}, {}
    result = await run_mod._build_widget_guarded(
        {"type": "message", "text": "x"},
        session=None,
        config_dir=None,
        default_bg_color=None,
        panel_h_for_warning=None,
        coercion_collector=[],
        widget_cache=cache,
        widget_tasks=tasks,
    )
    assert result is None  # build error suppressed
    assert cache == {} and tasks == {}  # nothing cached
    await asyncio.sleep(0)  # let cancellation propagate
    assert len(captured_tasks) == 1
    assert captured_tasks[0].cancelled() or captured_tasks[0].cancelling()


# ---------------------------------------------------------------------------
# _detect_and_apply_reload helper tests
# ---------------------------------------------------------------------------


def _new_config():
    # Minimal stand-in: the helper only reads .between_sections, .sections,
    # and optionally ._coerce_warnings.
    return SimpleNamespace(between_sections=None, sections=[], _coerce_warnings=[])


class _Watcher:
    def __init__(self, changed):
        self._changed = changed

    def changed(self):
        return self._changed


@pytest.fixture
def _patched_reload(monkeypatch):
    calls = {"record": []}
    monkeypatch.setattr(
        run_mod, "_build_trans_obj_guarded", lambda cfg: "TRANS", raising=True
    )

    async def _fake_apply(*a, **k):
        # (schedule_task, source_refresh_task, restart_required)
        return ("SCHED", None, [])

    monkeypatch.setattr(run_mod._reload, "_apply_reload", _fake_apply, raising=True)

    def _rec(*, ok, ts, error="", restart_required=None):
        calls["record"].append(
            {"ok": ok, "error": error, "restart_required": restart_required}
        )

    monkeypatch.setattr(run_mod.status_board, "record_reload", _rec, raising=True)
    return calls


async def test_detect_no_change_returns_none(_patched_reload):
    async def _lv(p):  # not reached when watcher reports no change
        raise AssertionError("load_and_validate should not run")

    res = await run_mod._detect_and_apply_reload(
        watcher=_Watcher(False),
        config_path=None,
        config=_new_config(),
        widget_cache={},
        widget_tasks={},
        render_breaker=None,
        schedule_task=None,
        source_refresh_task=None,
        led_frame=None,
    )
    assert res is None
    assert _patched_reload["record"] == []


async def test_detect_applies_valid_reload(monkeypatch, _patched_reload):
    new_cfg = _new_config()

    async def _lv(p):
        return (new_cfg, [], False)  # (config, errors, transient)

    monkeypatch.setattr(run_mod._reload, "load_and_validate", _lv, raising=True)
    res = await run_mod._detect_and_apply_reload(
        watcher=_Watcher(True),
        config_path=None,
        config=_new_config(),
        widget_cache={},
        widget_tasks={},
        render_breaker=None,
        schedule_task=None,
        source_refresh_task=None,
        led_frame=None,
    )
    assert res is not None
    assert res.config is new_cfg
    assert res.default_section_trans == "TRANS"
    assert res.schedule_task == "SCHED"
    assert _patched_reload["record"][-1]["ok"] is True


async def test_detect_rejected_reload_returns_none_records_failure(
    monkeypatch, _patched_reload
):
    async def _lv(p):
        return (None, ["boom"], False)

    monkeypatch.setattr(run_mod._reload, "load_and_validate", _lv, raising=True)
    res = await run_mod._detect_and_apply_reload(
        watcher=_Watcher(True),
        config_path=None,
        config=_new_config(),
        widget_cache={},
        widget_tasks={},
        render_breaker=None,
        schedule_task=None,
        source_refresh_task=None,
        led_frame=None,
    )
    assert res is None
    assert _patched_reload["record"][-1]["ok"] is False
    assert _patched_reload["record"][-1]["error"] == "boom"


async def test_detect_transient_returns_none_no_record(monkeypatch, _patched_reload):
    async def _lv(p):
        return (None, [], True)  # mid-write

    monkeypatch.setattr(run_mod._reload, "load_and_validate", _lv, raising=True)
    res = await run_mod._detect_and_apply_reload(
        watcher=_Watcher(True),
        config_path=None,
        config=_new_config(),
        widget_cache={},
        widget_tasks={},
        render_breaker=None,
        schedule_task=None,
        source_refresh_task=None,
        led_frame=None,
    )
    assert res is None
    assert _patched_reload["record"] == []


# ---------------------------------------------------------------------------
# Source-scan tripwire: reload must be detected per-section, not once per cycle
# ---------------------------------------------------------------------------


def test_reload_detected_per_section_not_only_per_cycle():
    import inspect

    src = inspect.getsource(run_mod)
    # Count only CALL sites: the two real calls use `await`; the function
    # definition is `async def _detect_and_apply_reload(` and is excluded.
    # Loose `_detect_and_apply_reload(` would also match the definition, so a
    # deleted call site could still satisfy it — `await` ties to invocation.
    assert src.count("await _detect_and_apply_reload(") == 2, (
        "reload helper must be invoked at exactly two call sites: per-cycle "
        "(cycle top) and per-section (inside the section loop)"
    )
    marker = "for section_index, section in enumerate(config.sections):"
    assert marker in src
    section_region = src[src.index(marker) :]
    assert "await _detect_and_apply_reload(" in section_region, (
        "per-section reload check is missing — the bug was: reload only "
        "detected once per full playlist cycle"
    )
    # The per-section reload must break to restart the cycle on the new config.
    # Tie the break to the reload guard so a stray unrelated break can't
    # satisfy it: slice from the guard to record_section and assert break is
    # inside that guard block.
    region_before_record = section_region[: section_region.index("record_section")]
    guard = "if _reload_res is not None:"
    assert guard in region_before_record, (
        "per-section reload guard is missing — expected `if _reload_res is "
        "not None:` before record_section"
    )
    guard_block = region_before_record[region_before_record.index(guard) :]
    assert "break" in guard_block, (
        "the per-section reload must break (to restart the cycle on the new "
        "config) from inside the `if _reload_res is not None:` guard"
    )


# ---------------------------------------------------------------------------
# Behavioral run-loop test: per-section reload swaps in the new config and
# restarts the cycle against it. Complements the source-scan above — the
# source-scan proves the call site exists; this proves the runtime behavior
# (the spy is invoked from inside the section loop AND the swapped-in
# _ReloadResult.config is what the next cycle runs against).
# ---------------------------------------------------------------------------


class _StopApp(Exception):
    """Sentinel raised from the spy to break out of run()'s `while True`."""


async def test_per_section_reload_swaps_config_and_restarts_cycle(monkeypatch):
    from unittest import mock

    from led_ticker.config import (
        AppConfig,
        DisplayConfig,
        SectionConfig,
        TransitionConfig,
    )

    def _section(text):
        return SectionConfig(mode="slideshow", title={"text": text}, widgets=[])

    # Initial config: 2 sections A + B. Reload target: 1 different section C.
    orig_cfg = AppConfig(
        display=DisplayConfig(rows=16, cols=32, chain_length=5),
        sections=[_section("A"), _section("B")],
        between_sections=TransitionConfig(type="cut"),
    )
    new_cfg = AppConfig(
        display=DisplayConfig(rows=16, cols=32, chain_length=5),
        sections=[_section("C")],
        between_sections=TransitionConfig(type="cut"),
    )

    sentinel_trans = object()
    sentinel_sched = object()
    reload_result = run_mod._ReloadResult(
        config=new_cfg,
        default_section_trans=sentinel_trans,
        schedule_task=sentinel_sched,
        source_refresh_task=None,
    )

    seen_configs: list = []

    async def _spy(*, config, **kwargs):
        seen_configs.append(config)
        n = len(seen_configs)
        if n == 1:
            return None  # cycle-1 top: no change
        if n == 2:
            return reload_result  # cycle-1, first section: reload → break
        raise _StopApp("captured cycle-2 top")  # cycle-2 top now on new config

    spy = mock.AsyncMock(side_effect=_spy)
    monkeypatch.setattr(run_mod, "_detect_and_apply_reload", spy)

    # A Ticker that, if ever reached, records the section it ran (it should
    # NOT be reached on cycle 1 because the reload breaks at section A before
    # any section is rendered, and cycle 2 raises _StopApp at the top).
    ran_sections: list = []

    class _SpyTicker:
        def __init__(self, *args, **kwargs):
            ran_sections.append(kwargs.get("monitors"))
            self.last_scroll_pos = 0

        async def run_slideshow(self, **kw):
            pass

    with (
        mock.patch.object(run_mod, "load_config", return_value=orig_cfg),
        mock.patch.object(
            run_mod,
            "build_frame_from_config",
            return_value=mock.Mock(
                **{
                    "get_clean_canvas.return_value": mock.Mock(height=16, width=160),
                    "overlay_hooks": [],
                }
            ),
        ),
        mock.patch.object(run_mod, "_configure_user_font_dir"),
        mock.patch.object(run_mod, "Ticker", _SpyTicker),
        pytest.raises(_StopApp),
    ):
        await run_mod.run(Path("ignored.toml"))

    # (a) The helper ran at the cycle top AND inside the section loop: the
    # outer loop calls it exactly once before entering the for-loop, so a
    # second call within the same cycle is necessarily the per-section call.
    assert spy.call_count >= 3, (
        f"reload helper must run per-cycle AND per-section; got {spy.call_count} calls"
    )

    # (b) Behavioral proof the source-scan can't give: calls 1 and 2 ran
    # against the ORIGINAL config; call 3 (next cycle top) ran against the
    # NEW config that was swapped in from _ReloadResult.config — i.e. the
    # reload broke the section loop and restarted the cycle on the new config.
    assert seen_configs[0] is orig_cfg
    assert seen_configs[1] is orig_cfg
    assert seen_configs[2] is new_cfg, (
        "the per-section _ReloadResult.config was not swapped in / the cycle "
        "did not restart against the new config"
    )

    # (c) Section B never rendered: the reload broke at section A on cycle 1,
    # and cycle 2 raised before any section. Ticker was never constructed.
    assert ran_sections == [], (
        f"no section should have reached Ticker (reload broke at section A "
        f"before render, cycle 2 stopped at top); got {ran_sections!r}"
    )


# ---------------------------------------------------------------------------
# Fix F.4 (2026-07-15): reload-mid-cycle wiring through the REAL run() loop.
# Complements test_per_section_reload_swaps_config_and_restarts_cycle above
# (which proves the config swap) with the dark-path interaction: a
# per-section reload must pin `_any_section_ran = True` BEFORE the `break`
# that restarts the cycle, even when every section seen so far that cycle
# was empty/scheduled-out — otherwise the next `_idle_when_all_scheduled_out`
# call would wrongly conclude the whole cycle was dark.
# ---------------------------------------------------------------------------


async def test_reload_mid_cycle_pins_any_section_ran_no_false_dark(monkeypatch, caplog):
    """(a) A reload occurring while the sections seen so far this cycle were
    all empty (no title, no widgets) must NOT cause the following cycle's
    idle check to log "panel dark" / blank the panel — the reload's `break`
    sets `_any_section_ran = True` first, so the cycle it cut short is not
    mistaken for an all-scheduled-out cycle."""
    import logging
    from unittest import mock

    from led_ticker.config import (
        AppConfig,
        DisplayConfig,
        SectionConfig,
        TransitionConfig,
    )

    def _empty_section():
        return SectionConfig(mode="slideshow", title=None, widgets=[])

    orig_cfg = AppConfig(
        display=DisplayConfig(rows=16, cols=32, chain_length=5),
        sections=[_empty_section(), _empty_section()],
        between_sections=TransitionConfig(type="cut"),
    )
    new_cfg = AppConfig(
        display=DisplayConfig(rows=16, cols=32, chain_length=5),
        sections=[_empty_section()],
        between_sections=TransitionConfig(type="cut"),
    )
    reload_result = run_mod._ReloadResult(
        config=new_cfg,
        default_section_trans=None,
        schedule_task=None,
        source_refresh_task=None,
    )

    class _StopApp(Exception):
        pass

    calls = {"n": 0}

    async def _spy(*, config, **kwargs):
        calls["n"] += 1
        n = calls["n"]
        if n == 1:
            return None  # cycle-1 top: no change
        if n == 2:
            return None  # section A (empty): no reload here
        if n == 3:
            return reload_result  # section B: reload -> break
        if n == 4:
            return None  # cycle-2 top: no change
        raise _StopApp("captured cycle-2 first section")

    # NOTE: asyncio.sleep is deliberately NOT patched here (unlike the
    # _idle_when_all_scheduled_out unit tests) — patching it globally would
    # also fast-forward the unrelated 1 Hz source-refresh background task
    # (spawn_source_refresh) that run() starts, turning it into a real
    # busy-loop for the lifetime of the test. This test's main path never
    # reaches a real sleep anyway (both idle checks see any_section_ran=True).
    monkeypatch.setattr(
        run_mod, "_detect_and_apply_reload", mock.AsyncMock(side_effect=_spy)
    )

    frame = mock.Mock(
        **{
            "get_clean_canvas.return_value": mock.Mock(height=16, width=160),
            "overlay_hooks": [],
        }
    )

    with (
        mock.patch.object(run_mod, "load_config", return_value=orig_cfg),
        mock.patch.object(run_mod, "build_frame_from_config", return_value=frame),
        mock.patch.object(run_mod, "_configure_user_font_dir"),
        caplog.at_level(logging.INFO),
        pytest.raises(_StopApp),
    ):
        await run_mod.run(Path("ignored.toml"))

    assert not any("panel dark" in r.getMessage() for r in caplog.records)
    frame.get_clean_canvas.assert_not_called()


async def test_scheduled_out_section_reaches_dark_path_via_run_loop(
    monkeypatch, caplog
):
    """(b) The complementary wiring proof: a section with no title and no
    widgets, run through the REAL run() loop (not the hand-simulated
    `_idle_when_all_scheduled_out` unit tests), must actually reach the
    dark path — "panel dark" logged, a clean canvas fetched and swapped —
    once the debounce (deep-dive-2 Fix 1: the FIRST all-out cycle is a
    no-op debounce; only the SECOND consecutive all-out cycle commits)
    has run its course."""
    import logging
    from unittest import mock

    from led_ticker.config import (
        AppConfig,
        DisplayConfig,
        SectionConfig,
        TransitionConfig,
    )

    cfg = AppConfig(
        display=DisplayConfig(rows=16, cols=32, chain_length=5),
        sections=[SectionConfig(mode="slideshow", title=None, widgets=[])],
        between_sections=TransitionConfig(type="cut"),
    )

    class _StopApp(Exception):
        pass

    calls = {"n": 0}

    async def _spy(*, config, **kwargs):
        calls["n"] += 1
        # Reload checks fire twice per cycle (outer top + one per section;
        # this config has exactly one section): call 1 = cycle-1 outer top,
        # call 2 = cycle-1 section. Cycle 1's idle check (before call 1's
        # section pass) is quiet (initial any_section_ran=True); the
        # section itself has no content, so any_section_ran is False
        # entering cycle 2. Call 3 = cycle-2 outer top; cycle 2's idle
        # check is the debounce no-op (first all-out cycle). Call 4 =
        # cycle-2 section, again no content. Call 5 = cycle-3 outer top;
        # cycle 3's idle check is the REAL dark commit (second consecutive
        # all-out cycle) — fetch + blank + "panel dark" log happen between
        # calls 5 and 6, so stopping at call 6 observes it.
        if calls["n"] >= 6:
            raise _StopApp("observed dark path")
        return None

    # NOTE: asyncio.sleep is deliberately NOT patched (see the sibling test
    # above) — the dark path's real `await asyncio.sleep(1.0)` is on this
    # test's critical path and is harmless to let run for real; patching it
    # globally would turn run()'s unrelated 1 Hz source-refresh background
    # task into a real busy-loop for the test's lifetime.
    monkeypatch.setattr(
        run_mod, "_detect_and_apply_reload", mock.AsyncMock(side_effect=_spy)
    )

    frame = mock.Mock(
        **{
            "get_clean_canvas.return_value": mock.Mock(height=16, width=160),
            "overlay_hooks": [],
        }
    )

    with (
        mock.patch.object(run_mod, "load_config", return_value=cfg),
        mock.patch.object(run_mod, "build_frame_from_config", return_value=frame),
        mock.patch.object(run_mod, "_configure_user_font_dir"),
        caplog.at_level(logging.INFO),
        pytest.raises(_StopApp),
    ):
        await run_mod.run(Path("ignored.toml"))

    assert any("panel dark" in r.getMessage() for r in caplog.records)
    frame.get_clean_canvas.assert_called()
    frame.swap.assert_any_call(frame.get_clean_canvas.return_value)


# ---------------------------------------------------------------------------
# Deep-dive-2 Fix 3 (2026-07-15): a hot-reload landing a zero-section config
# WHILE the panel is dark must not stop the swap loop. `_idle_on_empty_
# playlist` returning `_idled=True` used to `continue` before the dark-idle
# canvas got a chance to cycle — swaps (and anything riding on them, like
# busy_light and the status board's swap_count liveness counter) stalled
# for as long as the playlist stayed empty.
# ---------------------------------------------------------------------------


async def test_reload_to_empty_playlist_while_dark_keeps_cycling_swap(
    monkeypatch, caplog
):
    """Once the panel has committed to the dark state (past the debounce),
    a reload to a zero-section config must keep swapping the SAME dark
    canvas once per idled iteration — and must NOT fetch a new clean
    canvas."""
    import logging
    from unittest import mock

    from led_ticker.config import (
        AppConfig,
        DisplayConfig,
        SectionConfig,
        TransitionConfig,
    )

    cfg = AppConfig(
        display=DisplayConfig(rows=16, cols=32, chain_length=5),
        sections=[SectionConfig(mode="slideshow", title=None, widgets=[])],
        between_sections=TransitionConfig(type="cut"),
    )
    empty_cfg = AppConfig(
        display=DisplayConfig(rows=16, cols=32, chain_length=5),
        sections=[],
        between_sections=TransitionConfig(type="cut"),
    )
    reload_result = run_mod._ReloadResult(
        config=empty_cfg,
        default_section_trans=None,
        schedule_task=None,
        source_refresh_task=None,
    )

    class _StopApp(Exception):
        pass

    calls = {"n": 0}

    async def _spy(*, config, **kwargs):
        calls["n"] += 1
        n = calls["n"]
        # Calls 1-6 replay the debounce -> real dark commit sequence from
        # test_scheduled_out_section_reaches_dark_path_via_run_loop (cycles
        # 1-3, each with one outer-top + one section-level reload check).
        # Call 7 (cycle 4's outer-top check) lands the zero-section config
        # WHILE the panel is already dark — this is the scenario under
        # test. Calls 8+ are cycle 5+'s outer-top checks (config already
        # empty, no section-level checks fire since the section loop is
        # never entered); we let two of those idled-while-dark iterations
        # happen before stopping.
        if n == 7:
            return reload_result
        if n >= 9:
            raise _StopApp("observed post-reload idled-while-dark cycles")
        return None

    # NOTE: asyncio.sleep is deliberately NOT patched (see the sibling
    # tests above) — this path's real sleeps are on the critical path and
    # harmless to let run for real.
    monkeypatch.setattr(
        run_mod, "_detect_and_apply_reload", mock.AsyncMock(side_effect=_spy)
    )

    frame = mock.Mock(
        **{
            "get_clean_canvas.return_value": mock.Mock(height=16, width=160),
            "overlay_hooks": [],
        }
    )

    with (
        mock.patch.object(run_mod, "load_config", return_value=cfg),
        mock.patch.object(run_mod, "build_frame_from_config", return_value=frame),
        mock.patch.object(run_mod, "_configure_user_font_dir"),
        caplog.at_level(logging.INFO),
        pytest.raises(_StopApp),
    ):
        await run_mod.run(Path("ignored.toml"))

    # Exactly one fetch (the real dark commit, cycle 3) across the whole
    # sequence, including the post-reload idled-while-dark cycles.
    frame.get_clean_canvas.assert_called_once()
    # Swap ran for: the real dark commit (1) + two idled-while-dark cycles
    # after the reload landed the empty playlist (2) = 3 total.
    assert frame.swap.call_count == 3
    assert any("panel dark" in r.getMessage() for r in caplog.records)
    assert any(
        "no sections" in r.getMessage() for r in caplog.records
    )  # empty-playlist warning still fires


# ---------------------------------------------------------------------------
# build_source_registry — startup guard (asymmetric with reload)
# ---------------------------------------------------------------------------


class TestBuildSourceRegistry:
    """build_source_registry must skip-and-log bad sources rather than raising."""

    def _good_source_cfg(self):
        from led_ticker.config import SourceConfig

        return SourceConfig(
            id="good",
            type="static",
            raw={"id": "good", "type": "static", "value": "hello"},
        )

    def _bad_source_cfg(self):
        """An unknown type → build_source raises ValueError."""
        from led_ticker.config import SourceConfig

        return SourceConfig(
            id="bad",
            type="no_such_type_xyz",
            raw={"id": "bad", "type": "no_such_type_xyz"},
        )

    def test_bad_source_is_skipped_not_raised(self):
        """A [[source]] that makes build_source raise does NOT propagate out of
        build_source_registry — the helper logs-and-skips, the panel keeps booting."""
        registry = run_mod.build_source_registry([self._bad_source_cfg()], session=None)
        # Registry is empty (bad source skipped), but no exception was raised.
        from led_ticker.sources import DataRegistry

        assert isinstance(registry, DataRegistry)
        assert registry.ids() == set()  # no source landed

    def test_good_sources_survive_a_bad_peer(self):
        """The good source(s) in a mixed list are still registered even when a peer
        fails — the panel boots with the working sources."""
        registry = run_mod.build_source_registry(
            [self._bad_source_cfg(), self._good_source_cfg()], session=None
        )
        assert registry.get("good") is not None
        assert registry.get("bad") is None

    def test_bad_source_is_logged_at_error(self, caplog):
        """Skipped sources are logged at ERROR level with the source id and type."""
        import logging

        with caplog.at_level(logging.ERROR):
            run_mod.build_source_registry([self._bad_source_cfg()], session=None)
        assert any(
            "no_such_type_xyz" in r.message and r.levelno == logging.ERROR
            for r in caplog.records
        ), f"expected ERROR log mentioning the bad source type; got: {caplog.records}"

    def test_unexpected_kwarg_from_polled_source_is_skipped(self, monkeypatch):
        """A PolledDataSource whose constructor rejects an unexpected kwarg is
        skip-and-logged, not raised.  Covers the generic **kwargs passthrough path."""
        import attrs

        from led_ticker.config import SourceConfig
        from led_ticker.sources import _PLUGIN_SOURCE_TYPES, PolledDataSource

        @attrs.define(eq=False)
        class _StrictFake(PolledDataSource):
            # Only accepts `location`; an unexpected kwarg raises TypeError.
            location: str = ""

            async def update(self) -> None: ...

        _PLUGIN_SOURCE_TYPES["acme.strict"] = _StrictFake
        try:
            cfg = SourceConfig(
                id="s",
                type="acme.strict",
                raw={
                    "id": "s",
                    "type": "acme.strict",
                    "location": "NYC",
                    "unexpected_extra_key": "boom",  # no matching attr → TypeError
                },
            )
            # Should not raise:
            registry = run_mod.build_source_registry([cfg], session=None)
            assert registry.get("s") is None  # was skipped
        finally:
            _PLUGIN_SOURCE_TYPES.pop("acme.strict", None)


@pytest.mark.asyncio
async def test_idle_on_empty_playlist_idles_and_warns_once(monkeypatch, caplog):
    """An empty playlist idles (1s sleep, NOT a busy-loop) and warns once."""
    import logging

    slept = []

    async def _fake_sleep(s):
        slept.append(s)

    monkeypatch.setattr(run_mod.asyncio, "sleep", _fake_sleep)

    with caplog.at_level(logging.WARNING):
        idled, warned = await run_mod._idle_on_empty_playlist([], False)
    assert idled is True and warned is True
    assert slept == [1.0]  # idled once, did not busy-spin
    assert any("no sections" in r.getMessage() for r in caplog.records)

    # Already warned -> idles again but does NOT re-log.
    caplog.clear()
    with caplog.at_level(logging.WARNING):
        idled2, warned2 = await run_mod._idle_on_empty_playlist([], True)
    assert idled2 is True and warned2 is True
    assert not any("no sections" in r.getMessage() for r in caplog.records)


@pytest.mark.asyncio
async def test_idle_on_empty_playlist_passthrough_when_sections_present(monkeypatch):
    """With sections present: no idle, no log, and the warned flag resets."""
    slept = []

    async def _fake_sleep(s):
        slept.append(s)

    monkeypatch.setattr(run_mod.asyncio, "sleep", _fake_sleep)
    idled, warned = await run_mod._idle_on_empty_playlist(["section"], True)
    assert idled is False and warned is False  # resets so a later empty re-warns
    assert slept == []  # no idle when there is content to render
