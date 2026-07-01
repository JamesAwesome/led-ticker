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
    # Minimal duck-type for _schedule_ticker / _supervised_schedule: exposes a
    # settable `brightness` property (led_frame.brightness = level).
    return SimpleNamespace(brightness=100)


def _sched(*windows):
    return Scheduler.from_config(ScheduleConfig(enabled=True, windows=list(windows)))


def _w(start, end, brightness):
    return ScheduleWindow(start=start, end=end, brightness=brightness, days=[])


def _run_immediate(monkeypatch, coro_fn):
    """Drive a schedule ticker through exactly its immediate apply(), then stop
    — deterministically.

    ``apply()`` runs synchronously BEFORE the first ``await asyncio.sleep(interval)``,
    so raising CancelledError from that first sleep guarantees apply() already
    completed. This replaces the old ``ensure_future + await sleep(0) + cancel``
    harness, whose apply()-before-cancel ordering relied on a single event-loop
    yield and flaked on starved CI runners (apply not run in time -> brightness
    stuck at base; the lingering/cancelling task also logged during teardown ->
    the 'I/O operation on closed file' flood). No background task, no sleep(0),
    no cancel race — the whole run is synchronous within one asyncio.run.
    """

    async def _stop_at_first_sleep(_seconds):
        raise asyncio.CancelledError

    monkeypatch.setattr(run_mod.asyncio, "sleep", _stop_at_first_sleep)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(coro_fn())


def test_ticker_applies_brightness_immediately(monkeypatch):
    frame = _frame()
    sched = _sched(_w("00:00", "23:59", 42))

    async def go():
        await run_mod._schedule_ticker(frame, sched, None, 100, interval=10_000)

    _run_immediate(monkeypatch, go)
    assert frame.brightness == 42  # applied on frame 1, before any sleep


def test_override_provider_wins(monkeypatch):
    frame = _frame()
    sched = _sched(_w("00:00", "23:59", 42))

    async def go():
        await run_mod._schedule_ticker(
            frame, sched, None, 100, override=lambda: 7, interval=10_000
        )

    _run_immediate(monkeypatch, go)
    assert frame.brightness == 7  # override beats the schedule


def test_logs_only_on_change(monkeypatch, caplog):
    frame = _frame()
    sched = _sched(_w("00:00", "23:59", 42))
    with caplog.at_level(logging.INFO):

        async def go():
            await run_mod._schedule_ticker(frame, sched, None, 100, interval=10_000)

        _run_immediate(monkeypatch, go)
    msgs = [r.message for r in caplog.records if "brightness ->" in r.message]
    # The deterministic single apply logs the change exactly once, to 42.
    assert msgs == ["schedule: brightness -> 42"]


def test_logs_suppressed_across_repeated_same_value_ticks(caplog):
    """Verify that repeated ticks at the same brightness level suppress
    the change log to exactly one, even with multiple iterations."""
    frame = _frame()
    sched = _sched(_w("00:00", "23:59", 42))  # always 42, never changes

    async def go():
        task = asyncio.ensure_future(
            run_mod._schedule_ticker(frame, sched, None, 100, interval=0.001)
        )
        await asyncio.sleep(0.02)  # many ticks at the same level
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    with caplog.at_level(logging.INFO):
        asyncio.run(go())
    changes = [r for r in caplog.records if "brightness ->" in r.message]
    assert len(changes) == 1  # logged once despite many same-value ticks
    assert frame.brightness == 42


def test_transient_exception_does_not_kill_ticker():
    frame = _frame()

    class Boom:
        # Proves the ticker keeps ticking after a transient raise, deterministically:
        # cancel the loop from inside the 2nd compute (no wall-clock dependence — the
        # old sleep-and-count version flaked on loaded CI runners).
        def __init__(self):
            self.calls = 0
            self.task = None

        def brightness_for(self, now, base):
            self.calls += 1
            if self.calls >= 2 and self.task is not None:
                self.task.cancel()  # stop once we've proven it re-ticked
            raise RuntimeError("transient")

    boom = Boom()

    async def go():
        # interval=0 -> ticks as fast as the loop allows; the cancel above bounds it.
        task = asyncio.ensure_future(
            run_mod._schedule_ticker(frame, boom, None, 100, interval=0)
        )
        boom.task = task
        with contextlib.suppress(asyncio.CancelledError):
            await task

    asyncio.run(go())
    assert boom.calls >= 2  # kept ticking despite raises
    assert frame.brightness == 100  # never written (stayed at construct value)


def test_supervised_resets_to_base_on_fatal(monkeypatch, caplog):
    frame = _frame()
    frame.brightness = 0  # simulate stuck-dark before the crash

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
    assert frame.brightness == 55  # reset to base
    assert any("schedul" in r.message.lower() for r in caplog.records)


def test_invalid_timezone_string_does_not_crash_supervised(monkeypatch, caplog):
    """_supervised_schedule with an invalid tz string must not raise.
    It logs a warning and the ticker still applies brightness (FIX 1)."""
    frame = _frame()
    sched = _sched(_w("00:00", "23:59", 42))

    async def go():
        # _supervised_schedule resolves the (invalid) tz + logs, then awaits
        # _schedule_ticker whose immediate apply() runs before the first sleep;
        # the patched sleep then raises CancelledError, which _supervised_schedule
        # re-raises. Deterministic — no ensure_future/sleep(0)/cancel race.
        await run_mod._supervised_schedule(frame, sched, "Not/AZone", 100)

    with caplog.at_level(logging.WARNING):
        _run_immediate(monkeypatch, go)

    assert frame.brightness == 42
    assert any(
        "timezone" in r.message.lower() or "Not/AZone" in r.message
        for r in caplog.records
    )


def test_base_matches_frame_brightness_source():
    # The wiring passes config.display.brightness as base AND as brightness=
    # in the RgbMatrixBackend kwargs. Guard against a future edit that diverges them.
    # Since startup now goes through _respawn_schedule (single spawn site), the
    # brightness reference lives there rather than inline in run().
    import inspect

    respawn_src = inspect.getsource(run_mod._respawn_schedule)
    assert "config.display.brightness" in respawn_src  # used as base in the spawn
    # build_frame_from_config maps display.brightness -> RgbMatrixBackend(brightness=)
    from led_ticker.app import factories

    fsrc = inspect.getsource(factories)
    assert "brightness=display.brightness" in fsrc
