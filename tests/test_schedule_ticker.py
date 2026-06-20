import asyncio
import contextlib
import importlib
import logging
from types import SimpleNamespace

import pytest

import led_ticker.app.run as _run_mod_alias  # noqa: F401 — side-effect: registers module in sys.modules

run_mod = importlib.import_module("led_ticker.app.run")

from led_ticker.config import ScheduleConfig, ScheduleWindow  # noqa: E402
from led_ticker.schedule import Scheduler  # noqa: E402


def _frame():
    return SimpleNamespace(matrix=SimpleNamespace(brightness=100))


def _sched(*windows):
    return Scheduler.from_config(ScheduleConfig(enabled=True, windows=list(windows)))


def _w(start, end, brightness):
    return ScheduleWindow(start=start, end=end, brightness=brightness, days=[])


async def _run_once(coro_fn):
    """Run a _schedule_ticker with a huge interval so only the immediate apply()
    fires, then cancel."""
    task = asyncio.ensure_future(coro_fn())
    await asyncio.sleep(0)  # let the immediate apply() run
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


def test_ticker_applies_brightness_immediately(monkeypatch):
    frame = _frame()
    sched = _sched(_w("00:00", "23:59", 42))

    async def go():
        await run_mod._schedule_ticker(frame, sched, None, 100, interval=10_000)

    asyncio.run(_run_once(go))
    assert frame.matrix.brightness == 42  # applied on frame 1, no sleep needed


def test_override_provider_wins(monkeypatch):
    frame = _frame()
    sched = _sched(_w("00:00", "23:59", 42))

    async def go():
        await run_mod._schedule_ticker(
            frame, sched, None, 100, override=lambda: 7, interval=10_000
        )

    asyncio.run(_run_once(go))
    assert frame.matrix.brightness == 7  # override beats the schedule


def test_logs_only_on_change(monkeypatch, caplog):
    frame = _frame()
    sched = _sched(_w("00:00", "23:59", 42))
    with caplog.at_level(logging.INFO):

        async def go():
            await run_mod._schedule_ticker(frame, sched, None, 100, interval=10_000)

        asyncio.run(_run_once(go))
    msgs = [r.message for r in caplog.records if "brightness ->" in r.message]
    assert len(msgs) == 1 and "42" in msgs[0]


def test_transient_exception_does_not_kill_ticker(monkeypatch):
    frame = _frame()

    class Boom:
        def __init__(self):
            self.calls = 0

        def brightness_for(self, now, base):
            self.calls += 1
            raise RuntimeError("transient")

    boom = Boom()

    async def go():
        # interval tiny so the loop ticks a few times; it must NOT propagate
        task = asyncio.ensure_future(
            run_mod._schedule_ticker(frame, boom, None, 100, interval=0.001)
        )
        await asyncio.sleep(0.02)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    asyncio.run(go())
    assert boom.calls >= 2  # kept ticking despite raises
    assert frame.matrix.brightness == 100  # never written (stayed at construct value)


def test_supervised_resets_to_base_on_fatal(monkeypatch, caplog):
    frame = _frame()
    frame.matrix.brightness = 0  # simulate stuck-dark before the crash

    class Fatal:
        def brightness_for(self, now, base):
            raise RuntimeError("fatal")

    # Make the inner apply() re-raise by monkeypatching _schedule_ticker to one
    # that propagates — simplest: call _supervised_schedule with a scheduler whose
    # from-loop raise escapes. Here we force the supervised path by patching
    # _schedule_ticker to raise.
    async def boom(*a, **k):
        raise RuntimeError("fatal")

    monkeypatch.setattr(run_mod, "_schedule_ticker", boom)
    with caplog.at_level(logging.WARNING):
        asyncio.run(run_mod._supervised_schedule(frame, Fatal(), None, 55))
    assert frame.matrix.brightness == 55  # reset to base
    assert any("schedul" in r.message.lower() for r in caplog.records)


def test_base_matches_frame_brightness_source():
    # The wiring passes config.display.brightness as base AND as led_brightness.
    # Guard against a future edit that diverges them.
    import inspect

    src = inspect.getsource(run_mod.run)
    assert "config.display.brightness" in src  # used as base in the spawn
    # build_frame_from_config maps display.brightness -> LedFrame(led_brightness=)
    from led_ticker.app import factories

    fsrc = inspect.getsource(factories)
    assert "led_brightness=display.brightness" in fsrc
