import asyncio
import importlib
from types import SimpleNamespace

import led_ticker.app.run as _run_mod_alias  # noqa: F401 — side-effect: registers module in sys.modules

run_mod = importlib.import_module("led_ticker.app.run")


class _FakeMatrix:
    def __init__(self):
        self.brightness = 100


def _frame():
    return SimpleNamespace(matrix=_FakeMatrix())


def _cfg(*, enabled, brightness=100, tz="UTC"):
    sched = SimpleNamespace(enabled=enabled, timezone=tz, windows=[])
    return SimpleNamespace(
        display=SimpleNamespace(schedule=sched, brightness=brightness)
    )


async def test_respawn_schedule_disabled_sets_base_and_returns_none():
    frame = _frame()
    old = asyncio.ensure_future(asyncio.sleep(3600))
    task = await run_mod._respawn_schedule(
        old, _cfg(enabled=False, brightness=40), frame
    )
    assert task is None
    assert frame.matrix.brightness == 40
    assert old.cancelled() or old.cancelling()


async def test_respawn_schedule_enabled_spawns_and_cancels_old():
    frame = _frame()
    old = asyncio.ensure_future(asyncio.sleep(3600))
    task = await run_mod._respawn_schedule(old, _cfg(enabled=True), frame)
    assert task is not None and not task.done()
    assert old.cancelled() or old.cancelling()
    task.cancel()


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
    assert "load_and_validate(" in src  # validate gate
    assert "_apply_reload(" in src  # the swap
    assert "record_reload(" in src  # status surfacing
    assert "_build_widget_guarded(" in src  # cache-miss build goes through the guard
    assert "_build_title_guarded(" in src  # title build goes through the guard


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
