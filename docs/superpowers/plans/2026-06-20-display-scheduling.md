# Display Scheduling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Schedule panel brightness by time of day (bright day / dim evening / dark overnight) via TOML windows, applied live by a supervised asyncio ticker that sets `matrix.brightness` — no render-loop changes.

**Architecture:** Config dataclasses (`ScheduleConfig`/`ScheduleWindow`) feed a pure `Scheduler` (`brightness_for(now, base)`). A supervised 30 s ticker in `run.py` writes `led_frame.matrix.brightness`. `validate` checks the schedule and prints a resolved summary. Off = brightness 0 (panel dark), engine untouched.

**Tech Stack:** Python 3.14, stdlib `zoneinfo`/`datetime`, attrs, pytest. Astro/Starlight for docs.

## Global Constraints

- Worktree: `/Users/james/projects/github/jamesawesome/led-ticker-worktrees/display-scheduling`, branch `feat/display-scheduling` (based on `origin/main` @ a617466). **Run `git branch --show-current` before editing; abort if it prints `main`.**
- Run `make dev` (or `uv sync --extra dev`) once before the first commit; tests run with `PYTHONPATH=tests/stubs uv run pytest`.
- Lint/format: `uv run --extra dev ruff check src/ tests/` + `uv run --extra dev ruff format src/ tests/` (line length 88). Types: `uv run --extra dev pyright src/`.
- No `from __future__ import annotations` in `src/` (PEP 649 / project rule). Tests may use modern generics natively (3.14).
- `git add` new files (check `git status` for `??`). Commit trailer on every commit: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>` and `Claude-Session: https://claude.ai/code/session_01P7r9q2YjKvWBsTSfdPotAh`.
- Behavior contract (from spec): brightness window = `start`/`end` `"HH:MM"` 24h local; `start` inclusive, `end` exclusive; `start > end` wraps past midnight; `brightness` 0–100 (0 = off/dark); optional `days` (`mon`..`sun`, lowercased, empty = every day); **wrap window owned by its start day**; **last matching window wins**; outside all windows → base `[display] brightness`.
- The schedule applies via `matrix.brightness` only — do NOT pause/clear the render loop, do NOT touch the engine. The rgbmatrix stub has a settable `.brightness` attribute (`tests/stubs/rgbmatrix/__init__.py`).

---

### Task 1: Config dataclasses + loader (`config.py`)

**Files:**
- Modify: `src/led_ticker/config.py` (add `ScheduleWindow`, `ScheduleConfig`; add `schedule` field to `DisplayConfig`; add `_coerce_schedule`; wire into `_coerce_display`)
- Test: `tests/test_config_schedule.py`

**Interfaces:**
- Produces: `ScheduleWindow(start: str, end: str, brightness: int, days: list[str])`; `ScheduleConfig(enabled: bool, timezone: str, windows: list[ScheduleWindow])`; `DisplayConfig.schedule: ScheduleConfig`.

- [ ] **Step 1: Write failing config-load tests**

Create `tests/test_config_schedule.py`:

```python
import textwrap
from pathlib import Path

from led_ticker.config import ScheduleConfig, ScheduleWindow, load_config


def _write(tmp_path, body):
    p = tmp_path / "config.toml"
    p.write_text(textwrap.dedent(body))
    return p


def test_schedule_absent_defaults_to_disabled(tmp_path):
    cfg = load_config(_write(tmp_path, "[display]\nrows=16\ncols=64\n"))
    assert isinstance(cfg.display.schedule, ScheduleConfig)
    assert cfg.display.schedule.enabled is False
    assert cfg.display.schedule.windows == []


def test_schedule_parses_windows_and_lowercases_days(tmp_path):
    cfg = load_config(
        _write(
            tmp_path,
            """
            [display]
            rows = 16
            cols = 64

            [display.schedule]
            enabled = true
            timezone = "America/New_York"

            [[display.schedule.windows]]
            start = "07:00"
            end = "18:00"
            brightness = 100

            [[display.schedule.windows]]
            start = "23:00"
            end = "07:00"
            brightness = 0
            days = ["Fri", "SAT"]
            """,
        )
    )
    s = cfg.display.schedule
    assert s.enabled is True
    assert s.timezone == "America/New_York"
    assert len(s.windows) == 2
    assert s.windows[0] == ScheduleWindow(
        start="07:00", end="18:00", brightness=100, days=[]
    )
    assert s.windows[1].days == ["fri", "sat"]  # lowercased
```

- [ ] **Step 2: Run them — expect failure**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_config_schedule.py -q`
Expected: FAIL — `ImportError: cannot import name 'ScheduleConfig'`.

- [ ] **Step 3: Add the dataclasses + loader**

In `src/led_ticker/config.py`, add these dataclasses immediately ABOVE `class DisplayConfig` (they must be defined first since `DisplayConfig` references `ScheduleConfig`):

```python
@dataclass
class ScheduleWindow:
    start: str  # "HH:MM" 24h local wall-clock
    end: str  # "HH:MM"; start > end wraps past midnight
    brightness: int  # 0–100; 0 = off/dark
    days: list[str] = field(default_factory=list)  # mon..sun; empty = every day


@dataclass
class ScheduleConfig:
    enabled: bool = False
    timezone: str = ""  # IANA (zoneinfo); empty = system local
    windows: list[ScheduleWindow] = field(default_factory=list)
```

Add a `schedule` field to `DisplayConfig` (anywhere among its fields, e.g. after `led_rgb_sequence`):

```python
    schedule: "ScheduleConfig" = field(default_factory=ScheduleConfig)
```

Add the schedule parser ABOVE `_coerce_display`:

```python
def _coerce_schedule(raw: dict[str, Any]) -> "ScheduleConfig":
    """Build ScheduleConfig from the raw [display.schedule] table. Permissive:
    values pass through (validation reports bad shapes); day names lowercased."""
    windows: list[ScheduleWindow] = []
    for w in raw.get("windows", []) or []:
        raw_days = w.get("days", [])
        days = (
            [str(d).lower() for d in raw_days] if isinstance(raw_days, list) else raw_days
        )
        windows.append(
            ScheduleWindow(
                start=w.get("start", ""),
                end=w.get("end", ""),
                brightness=w.get("brightness", 100),
                days=days,
            )
        )
    return ScheduleConfig(
        enabled=bool(raw.get("enabled", False)),
        timezone=raw.get("timezone", ""),
        windows=windows,
    )
```

In `_coerce_display`, the generic passthrough loop iterates `set(defaults) - _DISPLAY_INT_FIELDS`, which would mishandle the nested `schedule` (its field default is `MISSING` via default_factory). Exclude it and build it explicitly. Change the passthrough loop + return:

```python
    # String / bool fields pass through without coercion. `schedule` is a nested
    # dataclass — built separately below, never via the int/passthrough loops.
    for name in set(defaults) - _DISPLAY_INT_FIELDS - {"schedule"}:
        kwargs[name] = display_raw.get(name, defaults[name])
    kwargs["schedule"] = _coerce_schedule(display_raw.get("schedule", {}) or {})
    return DisplayConfig(**kwargs)
```

(Confirm `Any` and `field` are already imported in config.py — they are, per the existing dataclasses.)

- [ ] **Step 4: Run tests — expect pass**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_config_schedule.py -q`
Expected: PASS (2 tests).

- [ ] **Step 5: Lint + typecheck + commit**

```bash
uv run --extra dev ruff check src/ tests/ && uv run --extra dev ruff format src/ tests/ && uv run --extra dev pyright src/
git add src/led_ticker/config.py tests/test_config_schedule.py
git commit -m "feat(schedule): ScheduleConfig/ScheduleWindow config + loader

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01P7r9q2YjKvWBsTSfdPotAh"
```

---

### Task 2: Pure Scheduler + summary (`schedule.py`)

**Files:**
- Create: `src/led_ticker/schedule.py`
- Test: `tests/test_schedule.py`

**Interfaces:**
- Consumes: `ScheduleConfig`/`ScheduleWindow` (duck-typed — reads `cfg.enabled`/`cfg.timezone`/`cfg.windows[].start/.end/.brightness/.days`; no import needed at runtime).
- Produces:
  - `to_minutes(hhmm: str) -> int | None` — minutes since midnight, or None if malformed.
  - `Scheduler` (frozen attrs) with `from_config(cfg) -> Scheduler`, `brightness_for(now: datetime, base: int) -> int`, and `_active_index(minutes: int, weekday: int) -> int | None`.
  - `unreachable_window_indices(cfg) -> list[int]` — windows that can never be the effective one (for a validate warning).
  - `format_schedule_summary(cfg, base: int) -> list[str]` — human lines.

- [ ] **Step 1: Write the failing test matrix**

Create `tests/test_schedule.py`:

```python
from datetime import datetime
from zoneinfo import ZoneInfo

from led_ticker.config import ScheduleConfig, ScheduleWindow
from led_ticker.schedule import (
    Scheduler,
    format_schedule_summary,
    to_minutes,
    unreachable_window_indices,
)

MON, FRI, SAT, SUN = 0, 4, 5, 6  # datetime.weekday()


def _sched(*windows):
    return Scheduler.from_config(
        ScheduleConfig(enabled=True, windows=list(windows))
    )


def _w(start, end, brightness, days=None):
    return ScheduleWindow(start=start, end=end, brightness=brightness, days=days or [])


def _at(weekday, hh, mm):
    # 2026-06-15 is a Monday; add weekday days to land on the target weekday.
    return datetime(2026, 6, 15 + weekday, hh, mm)


def test_to_minutes():
    assert to_minutes("00:00") == 0
    assert to_minutes("07:30") == 450
    assert to_minutes("23:59") == 1439
    assert to_minutes("24:00") is None
    assert to_minutes("7:00") is None  # must be zero-padded HH
    assert to_minutes("aa:bb") is None


def test_outside_all_windows_returns_base():
    s = _sched(_w("07:00", "18:00", 100))
    assert s.brightness_for(_at(MON, 6, 0), base=60) == 60


def test_in_window_returns_its_brightness():
    s = _sched(_w("07:00", "18:00", 100))
    assert s.brightness_for(_at(MON, 12, 0), base=60) == 100


def test_boundaries_start_inclusive_end_exclusive():
    s = _sched(_w("07:00", "18:00", 100))
    assert s.brightness_for(_at(MON, 7, 0), base=60) == 100  # start inclusive
    assert s.brightness_for(_at(MON, 18, 0), base=60) == 60  # end exclusive


def test_midnight_wrap_both_halves():
    s = _sched(_w("23:00", "07:00", 0))
    assert s.brightness_for(_at(MON, 23, 30), base=60) == 0  # pre-midnight half
    assert s.brightness_for(_at(MON, 2, 0), base=60) == 0  # post-midnight half
    assert s.brightness_for(_at(MON, 12, 0), base=60) == 60  # midday → base


def test_days_filter_non_wrap():
    s = _sched(_w("09:00", "17:00", 100, days=["mon", "tue", "wed", "thu", "fri"]))
    assert s.brightness_for(_at(FRI, 12, 0), base=60) == 100
    assert s.brightness_for(_at(SAT, 12, 0), base=60) == 60  # weekend → base


def test_wrap_window_owned_by_start_day():
    # Fri 23:00 → Sat 07:00 active; Sat-night not (days=[fri]).
    s = _sched(_w("23:00", "07:00", 0, days=["fri"]))
    assert s.brightness_for(_at(FRI, 23, 30), base=60) == 0  # Fri night
    assert s.brightness_for(_at(SAT, 2, 0), base=60) == 0  # Sat early AM = Fri's tail
    assert s.brightness_for(_at(SAT, 23, 30), base=60) == 60  # Sat night NOT owned
    assert s.brightness_for(_at(SUN, 2, 0), base=60) == 60  # Sun early AM NOT owned


def test_last_matching_window_wins():
    s = _sched(
        _w("07:00", "23:00", 100),  # general
        _w("12:00", "13:00", 30),  # lunch override (later → wins)
    )
    assert s.brightness_for(_at(MON, 12, 30), base=60) == 30
    assert s.brightness_for(_at(MON, 9, 0), base=60) == 100


def test_unreachable_window_detected():
    cfg = ScheduleConfig(
        enabled=True,
        windows=[
            _w("12:00", "13:00", 30),  # fully covered by the next, same days
            _w("07:00", "23:00", 100),
        ],
    )
    # window 0 (12–13) is shadowed by window 1 (07–23) which comes later → wins always
    assert unreachable_window_indices(cfg) == [0]


def test_brightness_for_is_tz_aware():
    # A tz-aware now resolves by its LOCAL wall clock, not UTC.
    s = _sched(_w("07:00", "18:00", 100))
    ny = ZoneInfo("America/New_York")
    # 12:00 local NY is in-window regardless of UTC offset/DST
    assert s.brightness_for(datetime(2026, 6, 15, 12, 0, tzinfo=ny), base=60) == 100


def test_summary_lines():
    cfg = ScheduleConfig(
        enabled=True,
        timezone="America/New_York",
        windows=[_w("23:00", "07:00", 0)],
    )
    lines = format_schedule_summary(cfg, base=60)
    text = "\n".join(lines)
    assert "America/New_York" in text
    assert "overnight" in text  # wrap annotated
    assert "0%" in text and "dark" in text
    assert "base" in text  # base fallback shown
```

- [ ] **Step 2: Run — expect failure**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_schedule.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'led_ticker.schedule'`.

- [ ] **Step 3: Implement `schedule.py`**

Create `src/led_ticker/schedule.py`:

```python
"""Time-of-day brightness scheduling (pure logic).

A Scheduler resolves the panel brightness for a given local datetime from a list
of brightness windows. No hardware or asyncio dependency — the run loop calls
brightness_for() and assigns the result to matrix.brightness.
"""

import re
from datetime import datetime

import attrs

_DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")  # index == datetime.weekday()
_HHMM = re.compile(r"^([0-9]{2}):([0-9]{2})$")


def to_minutes(hhmm: str) -> int | None:
    """Minutes since midnight for a zero-padded 'HH:MM' (0–23/0–59), else None."""
    if not isinstance(hhmm, str):
        return None
    m = _HHMM.match(hhmm)
    if not m:
        return None
    hh, mm = int(m.group(1)), int(m.group(2))
    if hh > 23 or mm > 59:
        return None
    return hh * 60 + mm


@attrs.define(frozen=True)
class _Window:
    start: int  # minutes since midnight
    end: int
    brightness: int
    days: frozenset[int]  # weekday ints; empty = every day


def _day_ok(days: frozenset[int], weekday: int) -> bool:
    return not days or weekday in days


@attrs.define(frozen=True)
class Scheduler:
    windows: tuple[_Window, ...]

    @classmethod
    def from_config(cls, cfg) -> "Scheduler":
        out: list[_Window] = []
        for w in cfg.windows:
            start = to_minutes(w.start)
            end = to_minutes(w.end)
            if start is None or end is None:
                continue  # malformed → skipped here; validate.py reports it
            days = frozenset(
                _DAYS.index(d) for d in (w.days or []) if d in _DAYS
            )
            out.append(_Window(start, end, int(w.brightness), days))
        return cls(windows=tuple(out))

    def _active_index(self, minutes: int, weekday: int) -> int | None:
        """Index of the last matching window (last-wins), or None."""
        winner: int | None = None
        for i, w in enumerate(self.windows):
            if w.start < w.end:  # same-day window
                active = w.start <= minutes < w.end and _day_ok(w.days, weekday)
            else:  # wraps past midnight — "owned by start day"
                if minutes >= w.start:  # pre-midnight portion, owned by today
                    active = _day_ok(w.days, weekday)
                elif minutes < w.end:  # post-midnight tail, owned by YESTERDAY
                    active = _day_ok(w.days, (weekday - 1) % 7)
                else:
                    active = False
            if active:
                winner = i
        return winner

    def brightness_for(self, now: datetime, base: int) -> int:
        idx = self._active_index(now.hour * 60 + now.minute, now.weekday())
        return base if idx is None else self.windows[idx].brightness


def unreachable_window_indices(cfg) -> list[int]:
    """Indices of windows that can never be the effective window (fully shadowed
    by later same-coverage windows). Computed by sampling every minute of a full
    week (10080 samples; trivial) and noting which windows never win."""
    sched = Scheduler.from_config(cfg)
    if not sched.windows:
        return []
    winners: set[int] = set()
    has_active: set[int] = set()
    for weekday in range(7):
        for minutes in range(1440):
            # which windows are active at this instant (ignoring last-wins)?
            for i, w in enumerate(sched.windows):
                if w.start < w.end:
                    a = w.start <= minutes < w.end and _day_ok(w.days, weekday)
                else:
                    a = (minutes >= w.start and _day_ok(w.days, weekday)) or (
                        minutes < w.end and _day_ok(w.days, (weekday - 1) % 7)
                    )
                if a:
                    has_active.add(i)
            idx = sched._active_index(minutes, weekday)
            if idx is not None:
                winners.add(idx)
    return sorted(i for i in has_active if i not in winners)


def _days_label(days: list[str]) -> str:
    if not days:
        return "every day"
    order = {d: i for i, d in enumerate(_DAYS)}
    titled = sorted((d for d in days if d in _DAYS), key=lambda d: order[d])
    return ",".join(d.capitalize() for d in titled)


def format_schedule_summary(cfg, base: int) -> list[str]:
    """Human-readable resolution of the schedule for `led-ticker validate`."""
    tz = cfg.timezone or "system local"
    lines = [f"display schedule ({tz}), base {base}%:"]
    for w in cfg.windows:
        wrap = " (overnight)" if (to_minutes(w.start) or 0) > (to_minutes(w.end) or 0) else ""
        dark = "  (dark)" if int(w.brightness) == 0 else ""
        lines.append(
            f"  {_days_label(w.days):<11} {w.start}–{w.end}{wrap} "
            f"→ {int(w.brightness)}%{dark}"
        )
    lines.append(f"  otherwise → {base}% (base)")
    return lines
```

- [ ] **Step 4: Run — expect pass**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_schedule.py -q`
Expected: PASS (all). If `test_wrap_window_owned_by_start_day` fails, re-check the `(weekday - 1) % 7` ownership in `_active_index`.

- [ ] **Step 5: Lint + typecheck + commit**

```bash
uv run --extra dev ruff check src/ tests/ && uv run --extra dev ruff format src/ tests/ && uv run --extra dev pyright src/
git add src/led_ticker/schedule.py tests/test_schedule.py
git commit -m "feat(schedule): pure Scheduler.brightness_for + summary + shadow detection

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01P7r9q2YjKvWBsTSfdPotAh"
```

---

### Task 3: Supervised schedule ticker + wiring (`app/run.py`)

**Files:**
- Modify: `src/led_ticker/app/run.py` (add `_SCHEDULE_TICK_SECONDS`, `_schedule_ticker`, `_supervised_schedule`; wire into `run()`)
- Test: `tests/test_schedule_ticker.py`

**Interfaces:**
- Consumes: `Scheduler` (Task 2), `LedFrame.matrix.brightness`, `spawn_tracked` (already imported in run.py from `led_ticker.widget`).
- Produces: `_schedule_ticker(led_frame, scheduler, tz, base, *, override=None, interval=_SCHEDULE_TICK_SECONDS)` and `_supervised_schedule(led_frame, scheduler, tz, base, *, override=None)`.

- [ ] **Step 1: Write failing ticker tests**

Create `tests/test_schedule_ticker.py`:

```python
import asyncio
import logging
from datetime import datetime
from types import SimpleNamespace

import pytest

from led_ticker.app import run as run_mod
from led_ticker.config import ScheduleConfig, ScheduleWindow
from led_ticker.schedule import Scheduler


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
        await run_mod._schedule_ticker(
            frame, sched, None, 100, interval=10_000
        )

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
        try:
            await task
        except asyncio.CancelledError:
            pass

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
```

- [ ] **Step 2: Run — expect failure**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_schedule_ticker.py -q`
Expected: FAIL — `AttributeError: module 'led_ticker.app.run' has no attribute '_schedule_ticker'`.

- [ ] **Step 3: Implement the ticker + supervised wrapper**

In `src/led_ticker/app/run.py`, near `_ttl_ticker` (top of the file), add:

```python
_SCHEDULE_TICK_SECONDS = 30.0


async def _schedule_ticker(
    led_frame: Any,
    scheduler: Any,
    tz: Any,
    base: int,
    *,
    override: Any = None,
    interval: float = _SCHEDULE_TICK_SECONDS,
) -> None:
    """Set matrix.brightness from the schedule every `interval` seconds.

    Applies immediately (correct on frame 1), logs only on change, and guards
    each tick so a transient exception keeps the ticker alive. `override`, when
    given, is a `Callable[[], int | None]` whose non-None value wins over the
    schedule (forward-looking seam for a future webhook)."""
    from datetime import datetime

    last: int | None = None

    def apply() -> None:
        nonlocal last
        try:
            o = override() if override is not None else None
            level = (
                o if o is not None else scheduler.brightness_for(datetime.now(tz), base)
            )
        except Exception:
            logging.exception("schedule: brightness compute failed; holding")
            return
        led_frame.matrix.brightness = level
        if level != last:
            logging.info("schedule: brightness -> %d", level)
            last = level

    apply()
    while True:
        await asyncio.sleep(interval)
        apply()


async def _supervised_schedule(
    led_frame: Any,
    scheduler: Any,
    tz: Any,
    base: int,
    *,
    override: Any = None,
) -> None:
    """Run the schedule ticker; on a fatal error, reset brightness to base and
    log (a crashed scheduler must never leave the panel stuck dark)."""
    try:
        await _schedule_ticker(led_frame, scheduler, tz, base, override=override)
    except asyncio.CancelledError:
        raise
    except Exception:
        logging.warning(
            "schedule ticker crashed; resetting brightness to base %d", base,
            exc_info=True,
        )
        try:
            led_frame.matrix.brightness = base
        except Exception:
            logging.exception("schedule: failed to reset brightness to base")
```

Wire into `run()` — right AFTER the plugin-overlay block and BEFORE the status-board heartbeat spawn (where `led_frame` exists), add:

```python
        if config.display.schedule.enabled:
            from zoneinfo import ZoneInfo  # noqa: PLC0415

            from led_ticker.schedule import Scheduler  # noqa: PLC0415

            sched = Scheduler.from_config(config.display.schedule)
            sched_tz = (
                ZoneInfo(config.display.schedule.timezone)
                if config.display.schedule.timezone
                else None
            )
            spawn_tracked(
                _supervised_schedule(
                    led_frame, sched, sched_tz, config.display.brightness
                )
            )
```

(`config.display.brightness` is `base` — the same value `build_frame_from_config` passes to `LedFrame(led_brightness=…)`, so "no window" resolves to the startup brightness.)

- [ ] **Step 4: Run the ticker tests + base-consistency check**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_schedule_ticker.py -q`
Expected: PASS.

Add a base-consistency test to `tests/test_schedule_ticker.py` (proves base == the frame's brightness source):

```python
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
```

Run again: `PYTHONPATH=tests/stubs uv run pytest tests/test_schedule_ticker.py -q` → PASS.

- [ ] **Step 5: Lint + typecheck + commit**

```bash
uv run --extra dev ruff check src/ tests/ && uv run --extra dev ruff format src/ tests/ && uv run --extra dev pyright src/
git add src/led_ticker/app/run.py tests/test_schedule_ticker.py
git commit -m "feat(schedule): supervised brightness ticker + run() wiring

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01P7r9q2YjKvWBsTSfdPotAh"
```

---

### Task 4: Validation + resolved-schedule summary (`validate.py`, `cli.py`)

**Files:**
- Modify: `src/led_ticker/validate.py` (add `_check_schedule`; call it in `validate_config`; add `notes` to `ValidationResult`; populate from `format_schedule_summary`)
- Modify: `src/led_ticker/app/cli.py` (print `result.notes` in the human output path)
- Test: `tests/test_validate_schedule.py`

**Interfaces:**
- Consumes: `to_minutes`, `unreachable_window_indices`, `format_schedule_summary` (Task 2); `ScheduleConfig` (Task 1).
- Produces: `_check_schedule(config) -> list[ValidationIssue]`; `ValidationResult.notes: list[str]`.

- [ ] **Step 1: Write failing validation tests**

Create `tests/test_validate_schedule.py`:

The repo sets `asyncio_mode = "auto"` (pyproject.toml), so async test functions
need NO decorator — a bare `async def test_...` runs. Mirror that here.

```python
import textwrap

from led_ticker.validate import validate_config


def _cfg(tmp_path, body):
    p = tmp_path / "config.toml"
    p.write_text(textwrap.dedent(body))
    return p


def _base(extra):
    return f"[display]\nrows=16\ncols=64\nbrightness=60\n{extra}"


async def _validate(tmp_path, extra):
    return await validate_config(_cfg(tmp_path, _base(extra)))


async def test_bad_timezone_is_error(tmp_path):
    res = await _validate(
        tmp_path,
        '[display.schedule]\nenabled=true\ntimezone="Not/AZone"\n'
        '[[display.schedule.windows]]\nstart="07:00"\nend="18:00"\nbrightness=100\n',
    )
    assert any("timezone" in e.message.lower() for e in res.errors)


async def test_bad_hhmm_and_brightness_are_errors(tmp_path):
    res = await _validate(
        tmp_path,
        "[display.schedule]\nenabled=true\n"
        '[[display.schedule.windows]]\nstart="7am"\nend="18:00"\nbrightness=150\n',
    )
    msgs = " ".join(e.message.lower() for e in res.errors)
    assert "start" in msgs or "hh:mm" in msgs
    assert "brightness" in msgs


async def test_start_equals_end_is_error(tmp_path):
    res = await _validate(
        tmp_path,
        "[display.schedule]\nenabled=true\n"
        '[[display.schedule.windows]]\nstart="08:00"\nend="08:00"\nbrightness=50\n',
    )
    assert any("start" in e.message.lower() and "end" in e.message.lower() for e in res.errors)


async def test_bad_day_is_error(tmp_path):
    res = await _validate(
        tmp_path,
        "[display.schedule]\nenabled=true\n"
        '[[display.schedule.windows]]\nstart="07:00"\nend="18:00"\nbrightness=100\ndays=["funday"]\n',
    )
    assert any("day" in e.message.lower() for e in res.errors)


async def test_enabled_empty_windows_warns(tmp_path):
    res = await _validate(tmp_path, "[display.schedule]\nenabled=true\n")
    assert any("window" in w.message.lower() for w in res.warnings)


async def test_fully_shadowed_window_warns(tmp_path):
    res = await _validate(
        tmp_path,
        "[display.schedule]\nenabled=true\n"
        '[[display.schedule.windows]]\nstart="12:00"\nend="13:00"\nbrightness=30\n'
        '[[display.schedule.windows]]\nstart="07:00"\nend="23:00"\nbrightness=100\n',
    )
    assert any("shadow" in w.message.lower() or "never" in w.message.lower() for w in res.warnings)


async def test_valid_schedule_has_summary_notes(tmp_path):
    res = await _validate(
        tmp_path,
        "[display.schedule]\nenabled=true\n"
        '[[display.schedule.windows]]\nstart="23:00"\nend="07:00"\nbrightness=0\n',
    )
    assert res.valid
    assert any("overnight" in n for n in res.notes)
```


- [ ] **Step 2: Run — expect failure**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_validate_schedule.py -q`
Expected: FAIL (no schedule checks yet; `notes` attribute missing).

- [ ] **Step 3: Implement validation + notes**

In `src/led_ticker/validate.py`:

(a) Add `notes` to `ValidationResult`:

```python
    notes: list[str] = field(default_factory=list)
```

(b) Add `_check_schedule` (place near the other `_check_*` functions). Import the schedule helpers at module top (`from led_ticker.schedule import to_minutes, unreachable_window_indices`):

```python
_VALID_DAYS = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}


def _check_schedule(config: "AppConfig") -> list[ValidationIssue]:
    sched = config.display.schedule
    if not sched.enabled:
        return []
    issues: list[ValidationIssue] = []
    if sched.timezone:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        try:
            ZoneInfo(sched.timezone)
        except (ZoneInfoNotFoundError, ValueError):
            issues.append(
                ValidationIssue(
                    rule=None,
                    location="display.schedule.timezone",
                    message=f"timezone {sched.timezone!r} is not a valid IANA timezone name",
                    fix="Use an IANA name like 'America/New_York', or leave it empty for system local time.",
                    severity="error",
                )
            )
    if not sched.windows:
        issues.append(
            ValidationIssue(
                rule=None,
                location="display.schedule",
                message="schedule is enabled but has no windows (no-op; base brightness always applies)",
                fix="Add at least one [[display.schedule.windows]] entry, or set enabled = false.",
                severity="warning",
            )
        )
    for i, w in enumerate(sched.windows):
        loc = f"display.schedule.windows[{i}]"
        s, e = to_minutes(w.start), to_minutes(w.end)
        if s is None:
            issues.append(ValidationIssue(None, loc, f"start {w.start!r} is not a valid 24h HH:MM time", "Use a zero-padded 24-hour time like '07:00'.", "error"))
        if e is None:
            issues.append(ValidationIssue(None, loc, f"end {w.end!r} is not a valid 24h HH:MM time", "Use a zero-padded 24-hour time like '23:00'.", "error"))
        if s is not None and e is not None and s == e:
            issues.append(ValidationIssue(None, loc, "start and end are equal (an empty/ambiguous window)", "Make start and end different times.", "error"))
        if not isinstance(w.brightness, int) or isinstance(w.brightness, bool) or not (0 <= w.brightness <= 100):
            issues.append(ValidationIssue(None, loc, f"brightness {w.brightness!r} must be an integer 0–100 (0 = off)", "Set brightness to a whole number from 0 to 100.", "error"))
        bad_days = [d for d in (w.days or []) if d not in _VALID_DAYS] if isinstance(w.days, list) else [w.days]
        if bad_days:
            issues.append(ValidationIssue(None, loc, f"invalid day name(s) {bad_days!r}", "Use lowercase 3-letter days: mon, tue, wed, thu, fri, sat, sun.", "error"))
    for i in unreachable_window_indices(sched):
        issues.append(
            ValidationIssue(
                rule=None,
                location=f"display.schedule.windows[{i}]",
                message="this window can never take effect — a later window always covers it (last-wins)",
                fix="Reorder it after the broader window, or remove it.",
                severity="warning",
            )
        )
    return issues
```

(c) In `validate_config`, after the existing `errors.extend(...)`/`warnings.extend(...)` calls, split `_check_schedule` results by severity, and populate `notes`:

```python
    _sched_issues = _check_schedule(config)
    errors.extend(i for i in _sched_issues if i.severity == "error")
    warnings.extend(i for i in _sched_issues if i.severity == "warning")
    if config.display.schedule.enabled:
        from led_ticker.schedule import format_schedule_summary

        notes = format_schedule_summary(
            config.display.schedule, config.display.brightness
        )
```

(Find where `ValidationResult(...)` is constructed at the end of `validate_config` and pass `notes=notes`; initialize `notes: list[str] = []` near the top of the function so it's always defined.)

(d) In `src/led_ticker/app/cli.py`, in the `validate` command's HUMAN output path (the non-`--json` branch that prints errors/warnings), after printing issues, print the summary:

```python
    for line in result.notes:
        print(line)
```

(Locate the validate handler's human-output section — where it prints the error/warning lines — and add this after them. Do NOT print notes in the `--json` path; the JSON already serializes the result. If JSON serialization enumerates dataclass fields, confirm `notes` serializes cleanly or is included intentionally.)

- [ ] **Step 4: Run validation tests + full suite**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_validate_schedule.py -q`
Expected: PASS. Then the full suite: `PYTHONPATH=tests/stubs uv run pytest -q` → green (the new `notes` field must not break existing validate/JSON tests; if a JSON-shape test fails, include `notes` in the expected shape).

- [ ] **Step 5: Lint + typecheck + commit**

```bash
uv run --extra dev ruff check src/ tests/ && uv run --extra dev ruff format src/ tests/ && uv run --extra dev pyright src/
git add src/led_ticker/validate.py src/led_ticker/app/cli.py tests/test_validate_schedule.py
git commit -m "feat(schedule): validate schedule + resolved-summary printout

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01P7r9q2YjKvWBsTSfdPotAh"
```

---

### Task 5: Docs + example configs + drift test

**Files:**
- Modify: `docs/site/src/content/docs/concepts/display.mdx` (Scheduling section)
- Modify: `docs/site/src/content/docs/reference/config-options.mdx` (new `[display.schedule]` fields)
- Modify: `tests/test_docs_config_options_drift.py` (keep it green with the new fields)
- Modify: `config/config.example.toml` AND `config/config.bigsign.example.toml` (commented example)
- Test: the drift test above + docs build/lint.

**Interfaces:**
- Consumes: nothing code-facing.

- [ ] **Step 1: Check what the drift test audits**

Run: `sed -n '1,60p' tests/test_docs_config_options_drift.py` and note exactly how it maps `config-options.mdx` rows to `DisplayConfig`/section dataclass fields (e.g. it scans for a `[display]` field table). The new nested `[display.schedule]` fields (`enabled`, `timezone`, `windows`) must be represented the way the test expects — determine whether it expects each `DisplayConfig` field name to appear (in which case `schedule` must be documented) and whether nested dataclasses are handled or excluded.

- [ ] **Step 2: Add the config-options.mdx rows + make the drift test pass**

Add a `[display.schedule]` subsection to `reference/config-options.mdx` documenting `enabled` (bool, default false), `timezone` (string, default "" = system local), and the `[[display.schedule.windows]]` fields (`start`, `end`, `brightness`, `days`). Then adjust `tests/test_docs_config_options_drift.py` so it accounts for the new `DisplayConfig.schedule` field — either by documenting it in the audited table or by adding `schedule` to the test's known/excluded-nested set (match however the test already handles non-scalar fields; if it has an allowlist of fields-not-in-the-table, add `schedule` there with a comment).

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_docs_config_options_drift.py -q`
Expected: PASS.

- [ ] **Step 3: Write the concepts/display.mdx Scheduling section**

Add a `## Scheduling` section to `docs/site/src/content/docs/concepts/display.mdx` covering, in prose + a TOML example:
- the windows model (`start`/`end`/`brightness`, 0 = off/dark), wrap-past-midnight, `days` (lowercased mon..sun, empty = every day), and **last-matching-window-wins**;
- **"Off" is not a power/sleep mode** — the LEDs go dark (≈0 panel power) but the Pi keeps rendering at full cadence;
- **timezone defaults to system time** — set it explicitly (fresh Pis are often UTC) or windows will be hours off;
- boundaries land within ~30 s; brightness changes are a single step (no fade);
- **a schedule change needs a restart** (no live reload yet);
- that `led-ticker validate` prints the resolved schedule.

- [ ] **Step 4: Add the commented example to BOTH example configs**

In `config/config.example.toml` and `config/config.bigsign.example.toml`, add a commented-out block (so it's copy-paste-discoverable but inert by default):

```toml
# --- Optional: brightness schedule (uncomment + edit to use) ---
# [display.schedule]
# enabled = true
# timezone = "America/New_York"   # set this! defaults to the Pi's system time (often UTC)
#
# [[display.schedule.windows]]
# start = "07:00"
# end = "18:00"
# brightness = 100
#
# [[display.schedule.windows]]
# start = "18:00"
# end = "23:00"
# brightness = 40
#
# [[display.schedule.windows]]
# start = "23:00"            # wraps past midnight
# end = "07:00"
# brightness = 0             # dark — panel off overnight
```

- [ ] **Step 5: Docs lint + commit**

```bash
cd docs/site && pnpm install >/dev/null 2>&1; pnpm run format && pnpm run lint && cd "$(git rev-parse --show-toplevel)"
PYTHONPATH=tests/stubs uv run pytest tests/test_docs_config_options_drift.py -q
git add docs/site/src/content/docs/concepts/display.mdx docs/site/src/content/docs/reference/config-options.mdx tests/test_docs_config_options_drift.py config/config.example.toml config/config.bigsign.example.toml
git commit -m "docs(schedule): scheduling docs, config-options, example configs

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01P7r9q2YjKvWBsTSfdPotAh"
```

---

## Final verification (after all tasks)

- [ ] `PYTHONPATH=tests/stubs uv run pytest -q` — full suite green.
- [ ] `uv run --extra dev ruff check src/ tests/` + `ruff format --check src/ tests/` — clean.
- [ ] `uv run --extra dev pyright src/` — 0 errors.
- [ ] `cd docs/site && pnpm run lint` — clean.
- [ ] Eyeball: `PYTHONPATH=tests/stubs uv run led-ticker validate config/config.example.toml` after temporarily uncommenting the schedule block → prints the resolved-schedule summary.
- [ ] `git status` shows no untracked (`??`) files.
- [ ] Push and open a PR against `main`; wait for CI green before requesting merge.

## Notes / gotchas

- `_active_index` is the single resolution function; `unreachable_window_indices` reuses the same activeness logic — keep them consistent if you change wrap/days semantics.
- Setting `matrix.brightness` from the ticker is safe (single-thread asyncio, atomic attribute write, C reads it on next vsync) — do not add locks.
- Do NOT pause/clear the engine loop (explicit non-goal; brightness-0 only).
- The `override=` seam is forward-looking (future webhook) — leave it wired but unused; don't build the webhook.
- If the existing validate JSON output is shape-tested, the new `notes` field may need including in the expected JSON; check `tests/test_validate*` and `tests/test_app*` for a serialization assertion.
