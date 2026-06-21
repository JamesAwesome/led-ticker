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
