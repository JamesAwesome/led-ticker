# Widget & Section Scheduling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Core-engine time-of-day visibility scheduling: a reserved `schedule = { start, end, days }` field on any widget or section, invisible to widget/plugin code.

**Architecture:** Extract the existing brightness-window matching logic in `schedule.py` into a shared `TimeWindow`; add `VisibilitySchedule` + strict parser + a weakref binding registry; gate widgets in `ticker._expand_sources` (beside `should_display`) and sections in `app/run.py`'s section loop; pop the field at dispatch level in `app/factories.py` so widget constructors never see it.

**Tech Stack:** Python 3.14, attrs, stdlib `zoneinfo`/`weakref`, pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-07-15-widget-scheduling-design.md` (approved).

## Global Constraints

- Work in the worktree `/Users/james/projects/github/jamesawesome/led-ticker-widget-scheduling` on branch `widget-scheduling`. NEVER commit in the primary checkout; verify `pwd` and `git branch --show-current` before any git operation.
- All commands run via `uv run ...` from the worktree root; `make test` = full suite, `make lint` = ruff.
- No `from __future__ import annotations` anywhere (project rule, PEP 649).
- Python 3.14 syntax is allowed (the codebase already uses PEP 758 `except A, B:`).
- Commit messages end with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- `uv run pyright` must pass before push (pre-push check, not part of make test). Annotate untyped C-extension objects as `Any`, not `object`.
- TOML syntax in all docs/tests/examples: sections are `[[playlist.section]]`, widgets are `[[playlist.section.widget]]`.
- Do not delete or rename anything listed in CLAUDE.md "Extracted widgets retain core hooks".

---

### Task 1: Extract `TimeWindow` from `_Window` in `schedule.py`

**Files:**
- Modify: `src/led_ticker/schedule.py:31-53` (`_Window`, `_window_active`)
- Modify: `src/led_ticker/schedule.py:62-87` (`Scheduler.from_config` constructor call), `src/led_ticker/schedule.py:110-122` (`unreachable_window_indices` constructor call)
- Test: `tests/test_schedule.py` (existing — must stay green), new tests appended

**Interfaces:**
- Produces: `TimeWindow` — frozen attrs class with fields `start: int`, `end: int`, `days: frozenset[int]` and method `active_at(minutes: int, weekday: int) -> bool`. Later tasks (2, 8) construct `TimeWindow(start=..., end=..., days=...)` and call `.active_at(...)`.
- `_Window` becomes `class _Window(TimeWindow)` adding `brightness: int` (field order: start, end, days, brightness). `_window_active(w, minutes, weekday)` is kept as a thin delegate so existing callers/tests don't churn.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_schedule.py`:

```python
class TestTimeWindow:
    """Shared window primitive — the same matching logic brightness windows use."""

    def test_same_day_window(self):
        from led_ticker.schedule import TimeWindow

        w = TimeWindow(start=9 * 60, end=17 * 60, days=frozenset())
        assert w.active_at(9 * 60, 0) is True  # 09:00 inclusive
        assert w.active_at(16 * 60 + 59, 0) is True
        assert w.active_at(17 * 60, 0) is False  # end exclusive
        assert w.active_at(8 * 60, 0) is False

    def test_overnight_wrap(self):
        from led_ticker.schedule import TimeWindow

        w = TimeWindow(start=22 * 60, end=6 * 60, days=frozenset())
        assert w.active_at(23 * 60, 0) is True
        assert w.active_at(5 * 60, 0) is True
        assert w.active_at(12 * 60, 0) is False

    def test_wrap_tail_owned_by_previous_day(self):
        from led_ticker.schedule import TimeWindow

        # Window starts Friday 22:00 (weekday 4); the 02:00 tail on Saturday
        # (weekday 5) belongs to Friday's day filter.
        w = TimeWindow(start=22 * 60, end=6 * 60, days=frozenset({4}))
        assert w.active_at(23 * 60, 4) is True  # Fri 23:00
        assert w.active_at(2 * 60, 5) is True  # Sat 02:00 — Friday's tail
        assert w.active_at(2 * 60, 4) is False  # Fri 02:00 — Thursday's tail

    def test_window_subclass_field_order(self):
        from led_ticker.schedule import _Window

        w = _Window(start=0, end=60, days=frozenset(), brightness=50)
        assert (w.start, w.end, w.brightness) == (0, 60, 50)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_schedule.py::TestTimeWindow -v`
Expected: FAIL with `ImportError: cannot import name 'TimeWindow'`

- [ ] **Step 3: Implement**

In `src/led_ticker/schedule.py`, replace the `_Window` / `_day_ok` / `_window_active` block (lines 31–53) with:

```python
def _day_ok(days: frozenset[int], weekday: int) -> bool:
    return not days or weekday in days


@attrs.define(frozen=True)
class TimeWindow:
    """A wall-clock window: start/end minutes since midnight + day filter.

    Shared primitive for brightness windows ([display.schedule]) and
    visibility schedules (widget/section `schedule = {...}`) — one
    implementation of the wrap semantics, so the two features can't drift.
    """

    start: int  # minutes since midnight
    end: int
    days: frozenset[int]  # weekday ints; empty = every day

    def active_at(self, minutes: int, weekday: int) -> bool:
        """Same-day: start<=t<end. Wrap (start>end): pre-midnight part
        (t>=start) owned by today; post-midnight tail (t<end) owned by
        yesterday (weekday-1)%7."""
        if self.start < self.end:
            return self.start <= minutes < self.end and _day_ok(self.days, weekday)
        if minutes >= self.start:
            return _day_ok(self.days, weekday)
        if minutes < self.end:
            return _day_ok(self.days, (weekday - 1) % 7)
        return False


@attrs.define(frozen=True)
class _Window(TimeWindow):
    brightness: int


def _window_active(w: TimeWindow, minutes: int, weekday: int) -> bool:
    """Thin delegate kept for existing call sites/tests."""
    return w.active_at(minutes, weekday)
```

Then update the TWO positional `_Window(...)` constructor calls to keyword form (field order changed):
- `Scheduler.from_config` (~line 86): `out.append(_Window(start=start, end=end, days=days, brightness=int(w.brightness)))`
- `unreachable_window_indices` (~line 122): `indexed_windows.append((orig_idx, _Window(start=start, end=end, days=days, brightness=int(w.brightness))))`

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_schedule.py tests/test_schedule_ticker.py tests/test_config_schedule.py -v`
Expected: ALL PASS (new TestTimeWindow + every pre-existing schedule test)

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/schedule.py tests/test_schedule.py
git commit -m "refactor(schedule): extract TimeWindow shared primitive from _Window

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: `VisibilitySchedule`, strict parser, and the schedule timezone global

**Files:**
- Modify: `src/led_ticker/schedule.py` (append after `Scheduler`)
- Test: `tests/test_visibility_schedule.py` (new)

**Interfaces:**
- Consumes: `TimeWindow`, `to_minutes`, `_DAYS` from Task 1.
- Produces:
  - `VisibilitySchedule` — frozen attrs class, field `window: TimeWindow`, method `is_active(now: datetime | None = None) -> bool`.
  - `parse_visibility_schedule(raw: object, *, location: str) -> VisibilitySchedule` — raises `ValueError` (message prefixed with `location`) on any malformed input.
  - `set_schedule_timezone(name: str) -> None` — resolves an IANA name into the module-level clock used by `is_active(now=None)`; empty string = system local; invalid name = warn + system local (never raises).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_visibility_schedule.py`:

```python
"""VisibilitySchedule model + strict parser + timezone global."""

from datetime import datetime

import pytest

from led_ticker import schedule
from led_ticker.schedule import (
    VisibilitySchedule,
    parse_visibility_schedule,
    set_schedule_timezone,
)


@pytest.fixture(autouse=True)
def _reset_tz():
    yield
    set_schedule_timezone("")


class TestParse:
    def test_minimal_window(self):
        s = parse_visibility_schedule(
            {"start": "09:00", "end": "17:00"}, location="w"
        )
        assert s.window.start == 9 * 60
        assert s.window.end == 17 * 60
        assert s.window.days == frozenset()

    def test_days_parsed_to_weekday_ints(self):
        s = parse_visibility_schedule(
            {"start": "09:00", "end": "17:00", "days": ["mon", "fri"]},
            location="w",
        )
        assert s.window.days == frozenset({0, 4})

    def test_not_a_table(self):
        with pytest.raises(ValueError, match=r"w: schedule must be an inline table"):
            parse_visibility_schedule("09:00-17:00", location="w")

    def test_brightness_key_points_at_display_schedule(self):
        with pytest.raises(ValueError, match=r"\[display\.schedule\]"):
            parse_visibility_schedule(
                {"start": "09:00", "end": "17:00", "brightness": 0}, location="w"
            )

    def test_unknown_key(self):
        with pytest.raises(ValueError, match=r"unknown schedule key\(s\) \['stop'\]"):
            parse_visibility_schedule(
                {"start": "09:00", "stop": "17:00"}, location="w"
            )

    def test_bad_time(self):
        with pytest.raises(ValueError, match=r"start '9am' is not a valid"):
            parse_visibility_schedule({"start": "9am", "end": "17:00"}, location="w")

    def test_missing_end(self):
        with pytest.raises(ValueError, match=r"end None is not a valid"):
            parse_visibility_schedule({"start": "09:00"}, location="w")

    def test_start_equals_end(self):
        with pytest.raises(ValueError, match=r"start and end are equal"):
            parse_visibility_schedule(
                {"start": "09:00", "end": "09:00"}, location="w"
            )

    def test_bad_day_name(self):
        with pytest.raises(ValueError, match=r"invalid day name\(s\) \['monday'\]"):
            parse_visibility_schedule(
                {"start": "09:00", "end": "17:00", "days": ["monday"]}, location="w"
            )

    def test_days_not_a_list(self):
        with pytest.raises(ValueError, match=r"days must be a list"):
            parse_visibility_schedule(
                {"start": "09:00", "end": "17:00", "days": "mon"}, location="w"
            )


class TestIsActive:
    def _sched(self, start="09:00", end="17:00", days=None):
        raw = {"start": start, "end": end}
        if days is not None:
            raw["days"] = days
        return parse_visibility_schedule(raw, location="w")

    def test_active_with_injected_now(self):
        s = self._sched()
        # Wednesday 2026-07-15 12:00
        assert s.is_active(datetime(2026, 7, 15, 12, 0)) is True
        assert s.is_active(datetime(2026, 7, 15, 18, 0)) is False

    def test_overnight_wrap_active(self):
        s = self._sched(start="17:00", end="09:00")
        assert s.is_active(datetime(2026, 7, 15, 23, 0)) is True
        assert s.is_active(datetime(2026, 7, 15, 12, 0)) is False
        assert s.is_active(datetime(2026, 7, 16, 3, 0)) is True

    def test_day_filter(self):
        # 2026-07-15 is a Wednesday
        s = self._sched(days=["wed"])
        assert s.is_active(datetime(2026, 7, 15, 12, 0)) is True
        assert s.is_active(datetime(2026, 7, 16, 12, 0)) is False  # Thursday

    def test_now_default_uses_module_clock(self):
        # Full-day-minus-a-minute window: whatever "now" is, this is active
        # (except exactly 23:59, a 1-in-1440 flake we accept in a smoke test).
        s = self._sched(start="00:00", end="23:59")
        assert s.is_active() is True


class TestSetScheduleTimezone:
    def test_valid_zone_is_set(self):
        set_schedule_timezone("America/New_York")
        assert schedule._SCHEDULE_TZ is not None
        assert str(schedule._SCHEDULE_TZ) == "America/New_York"

    def test_empty_resets_to_system_local(self):
        set_schedule_timezone("America/New_York")
        set_schedule_timezone("")
        assert schedule._SCHEDULE_TZ is None

    def test_invalid_zone_warns_and_falls_back(self, caplog):
        set_schedule_timezone("America/New_York")
        with caplog.at_level("WARNING"):
            set_schedule_timezone("Not/AZone")
        assert schedule._SCHEDULE_TZ is None
        assert "invalid timezone" in caplog.text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_visibility_schedule.py -v`
Expected: FAIL with `ImportError: cannot import name 'VisibilitySchedule'`

- [ ] **Step 3: Implement**

Add to the top-of-module imports in `src/led_ticker/schedule.py`: `from zoneinfo import ZoneInfo` (`datetime` is already imported). Then append:

```python
# ---------------------------------------------------------------------------
# Visibility scheduling (widget/section `schedule = {...}`) — core-owned.
# Shares TimeWindow with the brightness scheduler above so wrap semantics
# can't drift between the two features.
# ---------------------------------------------------------------------------

# Module-level clock for visibility schedules. None = system local time.
# Set from `[display] timezone` at startup and on every hot-reload
# (app.run._respawn_schedule) — same pattern as app._configure_user_font_dir.
_SCHEDULE_TZ: ZoneInfo | None = None


def set_schedule_timezone(name: str) -> None:
    """Resolve `[display] timezone` into the clock visibility schedules use.

    Empty string = system local. An invalid name warns and falls back to
    system local — a bad timezone must never prevent boot (validate.py
    reports it as an error at preflight).
    """
    global _SCHEDULE_TZ
    if not name:
        _SCHEDULE_TZ = None
        return
    try:
        _SCHEDULE_TZ = ZoneInfo(name)
    except Exception:
        logging.warning(
            "schedule: invalid timezone %r; using system local time", name
        )
        _SCHEDULE_TZ = None


@attrs.define(frozen=True)
class VisibilitySchedule:
    """When a widget/section is shown. Evaluated against the module clock
    (`set_schedule_timezone`); pass `now` explicitly in tests."""

    window: TimeWindow

    def is_active(self, now: datetime | None = None) -> bool:
        if now is None:
            now = datetime.now(_SCHEDULE_TZ)
        return self.window.active_at(now.hour * 60 + now.minute, now.weekday())


_VISIBILITY_KEYS = frozenset({"start", "end", "days"})


def parse_visibility_schedule(raw: object, *, location: str) -> VisibilitySchedule:
    """STRICT parser for widget/section `schedule = {...}` tables.

    Raises ValueError (prefixed with `location`) on any malformed input —
    unlike brightness parsing (skip-and-warn), because silently mis-showing
    or mis-hiding content is worse than a dimming glitch, and this is new
    surface with no back-compat to protect.
    """
    if not isinstance(raw, dict):
        raise ValueError(
            f"{location}: schedule must be an inline table like "
            f'{{ start = "09:00", end = "17:00" }}; got {raw!r}'
        )
    if "brightness" in raw:
        raise ValueError(
            f"{location}: 'brightness' is not a visibility-schedule key — "
            "brightness windows live in [display.schedule]. A widget/section "
            "schedule only controls WHEN it is shown."
        )
    unknown = sorted(set(raw) - _VISIBILITY_KEYS)
    if unknown:
        raise ValueError(
            f"{location}: unknown schedule key(s) {unknown!r}; "
            "valid keys: start, end, days."
        )
    start = to_minutes(raw.get("start"))
    if start is None:
        raise ValueError(
            f"{location}: start {raw.get('start')!r} is not a valid 24h HH:MM "
            "time (zero-padded, e.g. '09:00')."
        )
    end = to_minutes(raw.get("end"))
    if end is None:
        raise ValueError(
            f"{location}: end {raw.get('end')!r} is not a valid 24h HH:MM "
            "time (zero-padded, e.g. '17:00')."
        )
    if start == end:
        raise ValueError(
            f"{location}: start and end are equal — ambiguous between an "
            "empty and a 24h window. Omit schedule entirely for always-on."
        )
    raw_days = raw.get("days", [])
    if not isinstance(raw_days, list):
        raise ValueError(
            f"{location}: days must be a list of day names, got {raw_days!r}. "
            'Use e.g. days = ["mon", "tue"].'
        )
    bad = [d for d in raw_days if d not in _DAYS]
    if bad:
        raise ValueError(
            f"{location}: invalid day name(s) {bad!r}; use lowercase "
            "3-letter days: mon, tue, wed, thu, fri, sat, sun."
        )
    days = frozenset(_DAYS.index(d) for d in raw_days)
    return VisibilitySchedule(window=TimeWindow(start=start, end=end, days=days))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_visibility_schedule.py tests/test_schedule.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/schedule.py tests/test_visibility_schedule.py
git commit -m "feat(schedule): VisibilitySchedule model, strict parser, timezone global

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Widget↔schedule binding registry

**Files:**
- Modify: `src/led_ticker/schedule.py` (append; add `import weakref` at top)
- Test: `tests/test_visibility_schedule.py` (append)

**Interfaces:**
- Consumes: `VisibilitySchedule` from Task 2.
- Produces: `bind_schedule(widget: Any, sched: VisibilitySchedule) -> None` and `schedule_for(widget: Any) -> VisibilitySchedule | None`. Task 4 (`ticker.py`) calls `schedule_for`; Task 5 (`factories.py`) calls `bind_schedule`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_visibility_schedule.py`:

```python
import gc

from led_ticker.schedule import bind_schedule, schedule_for


def _sched():
    return parse_visibility_schedule({"start": "09:00", "end": "17:00"}, location="t")


class TestBindingRegistry:
    def test_unbound_widget_has_no_schedule(self):
        class W:
            pass

        assert schedule_for(W()) is None

    def test_bind_then_lookup(self):
        class W:
            pass

        w = W()
        s = _sched()
        bind_schedule(w, s)
        assert schedule_for(w) is s

    def test_rebind_overwrites(self):
        class W:
            pass

        w = W()
        bind_schedule(w, _sched())
        s2 = parse_visibility_schedule(
            {"start": "10:00", "end": "11:00"}, location="t"
        )
        bind_schedule(w, s2)
        assert schedule_for(w) is s2

    def test_binding_evicted_on_gc(self):
        class W:
            pass

        w = W()
        bind_schedule(w, _sched())
        key = id(w)
        del w
        gc.collect()
        assert key not in schedule._BINDINGS

    def test_slotted_attrs_widget_is_bindable(self):
        # Real widgets are slotted @attrs.define classes; attrs' default
        # weakref_slot=True makes them weakref-able. TickerMessage is the
        # canonical case.
        from led_ticker.widgets.message import TickerMessage

        w = TickerMessage("hello")
        s = _sched()
        bind_schedule(w, s)
        assert schedule_for(w) is s
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_visibility_schedule.py::TestBindingRegistry -v`
Expected: FAIL with `ImportError: cannot import name 'bind_schedule'`

- [ ] **Step 3: Implement**

Append to `src/led_ticker/schedule.py` (add `import weakref` to the module imports):

```python
# Widget -> VisibilitySchedule bindings. Keyed by id() because widgets are
# slotted @attrs.define classes: no attribute injection possible, and
# eq=True makes them unhashable (no WeakKeyDictionary). Values hold a
# weakref so hot-reload-evicted widgets don't accumulate; the weakref
# callback removes the entry before the id can be reused.
_BINDINGS: dict[int, tuple[Any, "VisibilitySchedule"]] = {}


def bind_schedule(widget: Any, sched: VisibilitySchedule) -> None:
    """Associate a core `schedule = {...}` with a built widget.

    Called by app.factories._build_widget at construction time. Engine-side
    lookup is `schedule_for`.
    """
    key = id(widget)
    try:
        ref = weakref.ref(widget, lambda _r, _key=key: _BINDINGS.pop(_key, None))
    except TypeError:
        # Object without weakref support (rare; not an attrs widget). The
        # strong ref pins it for the process lifetime — acceptable for
        # config-built widgets, and it keeps the id stable.
        ref = lambda _w=widget: _w  # noqa: E731
    _BINDINGS[key] = (ref, sched)


def schedule_for(widget: Any) -> "VisibilitySchedule | None":
    """The widget's bound visibility schedule, or None (= always shown)."""
    entry = _BINDINGS.get(id(widget))
    if entry is None:
        return None
    ref, sched = entry
    if ref() is not widget:  # stale entry / id reuse — treat as unbound
        return None
    return sched
```

Also add `from typing import Any` to the imports if not already present.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_visibility_schedule.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/schedule.py tests/test_visibility_schedule.py
git commit -m "feat(schedule): weakref binding registry (bind_schedule / schedule_for)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Engine gate — `_schedule_active` in `_expand_sources`

**Files:**
- Modify: `src/led_ticker/ticker.py:1098-1142` (`_displayable` / `_expand_sources`)
- Test: `tests/test_ticker_expand_sources.py` (append)

**Interfaces:**
- Consumes: `schedule_for` from Task 3; `bind_schedule` + `parse_visibility_schedule` in tests.
- Produces: `_schedule_active(widget: Any) -> bool` in `ticker.py`; `_expand_sources` filters on it. Behavior later tasks rely on: unbound = shown; container gated before expansion; raising check keeps the widget.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_ticker_expand_sources.py`:

```python
from led_ticker.schedule import bind_schedule, parse_visibility_schedule


def _always():
    # 00:00–23:59 every day: active at any test runtime except exactly 23:59.
    return parse_visibility_schedule({"start": "00:00", "end": "23:59"}, location="t")


class _FakeSchedInactive:
    def is_active(self):
        return False


class _FakeSchedBoom:
    def is_active(self):
        raise RuntimeError("boom")


class _Container:
    """Satisfies the Container protocol structurally (has feed_stories)."""

    def __init__(self, stories):
        self.feed_stories = stories

    async def update(self):  # pragma: no cover - protocol completeness
        pass


class TestScheduleGate:
    def test_widget_without_binding_is_kept(self):
        w = _Plain()
        assert _expand_sources([w]) == [w]

    def test_active_schedule_is_kept(self):
        w = _Plain()
        bind_schedule(w, _always())
        assert _expand_sources([w]) == [w]

    def test_inactive_schedule_is_dropped(self):
        w = _Plain()
        bind_schedule(w, _FakeSchedInactive())
        assert _expand_sources([w]) == []

    def test_raising_schedule_keeps_widget(self):
        # Same contract as should_display: a check that raises must never
        # crash the render loop or silently hide content.
        w = _Plain()
        bind_schedule(w, _FakeSchedBoom())
        assert _expand_sources([w]) == [w]

    def test_schedule_ands_with_should_display(self):
        # Inactive schedule hides even when should_display() says show...
        w1 = _Shown()
        bind_schedule(w1, _FakeSchedInactive())
        assert _expand_sources([w1]) == []
        # ...and should_display() False hides even inside the window.
        w2 = _Hidden()
        bind_schedule(w2, _always())
        assert _expand_sources([w2]) == []

    def test_container_is_gated_before_expansion(self):
        story = _Plain()
        c = _Container([story])
        bind_schedule(c, _FakeSchedInactive())
        assert _expand_sources([c]) == []

    def test_container_with_active_schedule_expands(self):
        story = _Plain()
        c = _Container([story])
        bind_schedule(c, _always())
        assert _expand_sources([c]) == [story]
```

Note: `bind_schedule` accepts the fake schedule objects because `schedule_for` returns whatever was bound (duck-typed at the call site); the type hint is documentation, not a runtime gate.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_ticker_expand_sources.py::TestScheduleGate -v`
Expected: `test_inactive_schedule_is_dropped`, `test_container_is_gated_before_expansion`, `test_schedule_ands_with_should_display` FAIL (widgets not filtered)

- [ ] **Step 3: Implement**

In `src/led_ticker/ticker.py`, add after `_displayable` (line 1109):

```python
def _schedule_active(widget: Any) -> bool:
    """Core `schedule = {...}` visibility gate (bound at build time in
    app.factories). No binding = always shown. Same contract as
    `_displayable`: a check that raises KEEPS the widget — scheduling must
    never crash the render loop or silently hide content."""
    from led_ticker.schedule import schedule_for

    sched = schedule_for(widget)
    if sched is None:
        return True
    try:
        return bool(sched.is_active())
    except Exception:  # noqa: BLE001 - visibility must not crash the render loop
        return True
```

In `_expand_sources`, add the gate before the Container branch (a scheduled-out container must not expand):

```python
    for s in sources:
        if breaker is not None and breaker.is_disabled(s):
            continue
        if not _schedule_active(s):
            continue
        if isinstance(s, Container):
```

And extend the `_expand_sources` docstring's filtering paragraph:

```
    Widgets (and container stories) that define `should_display()` are also
    filtered: returning `False` removes the widget from this pass. A check
    that raises keeps the widget — visibility must never crash the render loop.
    Widgets with a bound core `schedule = {...}` (see led_ticker.schedule.
    bind_schedule) are additionally gated by `_schedule_active` — the two
    compose as AND. A scheduled container is gated BEFORE expansion (stories
    inherit); its background update() keeps running regardless.
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_ticker_expand_sources.py tests/test_container_refresh.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/ticker.py tests/test_ticker_expand_sources.py
git commit -m "feat(engine): gate widgets/containers on bound visibility schedules

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: Dispatch-level pop, hard reservation, bind at build, `--list-fields`

**Files:**
- Modify: `src/led_ticker/app/factories.py` (`validate_widget_cfg` ~line 743-750 area, `_build_widget` ~line 863-900, `_DISPATCH_APPLICABLE_TYPES` line 263, `FIELD_HINTS` line 65, `_list_widget_fields` plugin-suppression at ~line 1357)
- Modify: `tests/golden/list_fields/{message,two_row,gif,countdown}.txt` (regenerated)
- Test: `tests/test_widget_schedule_dispatch.py` (new)

**Interfaces:**
- Consumes: `parse_visibility_schedule`, `bind_schedule`, `schedule_for` (Tasks 2–3); `_widget_declares_field` (exists, factories.py:587).
- Produces: any TOML widget entry may carry `schedule = {...}`; the widget constructor never receives it; the built widget is bound. `validate_widget_cfg` raises on (a) malformed schedule, (b) a widget class declaring its own `schedule` field.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_widget_schedule_dispatch.py`:

```python
"""Core-owned `schedule` field: popped at dispatch, bound to the built widget,
reserved against widget classes that try to declare it."""

import asyncio

import attrs
import pytest

from led_ticker.app.factories import _build_widget, _cache_key, validate_widget_cfg
from led_ticker.schedule import schedule_for
from led_ticker.widgets import _WIDGET_REGISTRY

SCHED = {"start": "09:00", "end": "17:00", "days": ["mon"]}


def test_built_widget_is_bound_and_constructor_never_sees_schedule():
    widget = asyncio.run(
        _build_widget({"type": "message", "text": "hi", "schedule": dict(SCHED)}, None)
    )
    s = schedule_for(widget)
    assert s is not None
    assert s.window.start == 9 * 60
    assert s.window.days == frozenset({0})
    # attrs would have raised on an unknown kwarg; belt-and-suspenders:
    assert not hasattr(widget, "schedule")


def test_widget_without_schedule_is_unbound():
    widget = asyncio.run(_build_widget({"type": "message", "text": "hi"}, None))
    assert schedule_for(widget) is None


def test_malformed_schedule_raises_at_validate():
    with pytest.raises(ValueError, match="not a valid 24h HH:MM"):
        asyncio.run(
            validate_widget_cfg(
                {"type": "message", "text": "hi", "schedule": {"start": "9am", "end": "17:00"}},
                session=None,
            )
        )


def test_validate_pops_schedule():
    cfg = {"type": "message", "text": "hi", "schedule": dict(SCHED)}
    asyncio.run(validate_widget_cfg(cfg, session=None))
    assert "schedule" not in cfg


def test_widget_class_declaring_schedule_is_rejected(monkeypatch):
    @attrs.define
    class _SchedWidget:
        schedule: str = ""

    monkeypatch.setitem(_WIDGET_REGISTRY, "_sched_test", _SchedWidget)
    with pytest.raises(ValueError, match="reserved by the core engine"):
        asyncio.run(validate_widget_cfg({"type": "_sched_test"}, session=None))


def test_cache_key_includes_schedule():
    base = {"type": "message", "text": "hi"}
    a = {**base, "schedule": {"start": "09:00", "end": "17:00"}}
    b = {**base, "schedule": {"start": "10:00", "end": "17:00"}}
    assert _cache_key(a) != _cache_key(b)
    assert _cache_key(base) != _cache_key(a)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_widget_schedule_dispatch.py -v`
Expected: `test_built_widget_is_bound...` FAILS with attrs `TypeError` about unexpected keyword `schedule` (surfaced as ValueError by `_validate_cfg_fields`); reservation test FAILS (no such error raised). `test_cache_key_includes_schedule` PASSES already (`_cache_key` is `str(sorted(items))` over the raw dict) — it's the regression tripwire for the spec's hot-reload checkpoint.

- [ ] **Step 3: Implement**

In `src/led_ticker/app/factories.py`:

(a) Import at top with the other led_ticker imports:

```python
from led_ticker.schedule import bind_schedule, parse_visibility_schedule
```

(b) In `validate_widget_cfg`, right after `cls = get_widget_class(widget_type)` / `_run_validate_config(cls, widget_cfg, widget_type)` (line ~749), add:

```python
    # `schedule` is a HARD-RESERVED core field (visibility scheduling —
    # docs /concepts/scheduling/). Popped here so it never reaches a widget
    # constructor, and rejected on any widget class that declares its own
    # `schedule` field so the TOML key has exactly one meaning everywhere.
    if _widget_declares_field(cls, "schedule"):
        raise ValueError(
            f"widget type={widget_type!r} declares a 'schedule' field, but "
            "'schedule' is reserved by the core engine for visibility "
            "scheduling. Rename the widget's field (e.g. 'poll_schedule')."
        )
    schedule_value = widget_cfg.pop("schedule", None)
    if schedule_value is not None:
        parse_visibility_schedule(
            schedule_value, location=f"widget type={widget_type!r} schedule"
        )
```

(c) In `_build_widget` (line 888), peek before validation and bind after construction:

```python
    widget_type: str = widget_cfg["type"]  # peek before validate_widget_cfg pops it
    raw_schedule = widget_cfg.get("schedule")  # peek; validate pops + checks it
    await validate_widget_cfg(
        widget_cfg,
        session=session,
        config_dir=config_dir,
        default_bg_color=default_bg_color,
        panel_h_for_warning=panel_h_for_warning,
        coercion_collector=coercion_collector,
    )
    cls = get_widget_class(widget_type)
    if hasattr(cls, "start"):
        widget = await cls.start(session=session, **widget_cfg)
    else:
        widget = cls(**widget_cfg)
    if raw_schedule is not None:
        bind_schedule(
            widget,
            parse_visibility_schedule(
                raw_schedule, location=f"widget type={widget_type!r} schedule"
            ),
        )
    return widget
```

(d) `_DISPATCH_APPLICABLE_TYPES` (line 263): add `"schedule": None,` after `"border"`.

(e) `FIELD_HINTS` (line 65 dict): add:

```python
    "schedule": FieldHint(
        '{start = "HH:MM", end = "HH:MM", days = [...]}',
        "show this widget only during the time window (core-owned; start >"
        " end wraps overnight) — see /concepts/scheduling/",
        "none (always shown)",
    ),
```

(f) In `_list_widget_fields`, the plugin suppression (line ~1357) currently hides ALL `None`-typed dispatch fields for plugin widgets — but `schedule` applies to plugin widgets too (core pops it before construction). Add an allowlist above `_DISPATCH_APPLICABLE_TYPES`:

```python
# Dispatch fields that ARE valid on plugin widgets (core pops them before
# the constructor, so the plugin never has to accept them).
_PLUGIN_SAFE_DISPATCH = frozenset({"schedule"})
```

and change the suppression condition to:

```python
        if (
            is_plugin_widget
            and applicable_types is None
            and name not in _PLUGIN_SAFE_DISPATCH
        ):
            continue
```

- [ ] **Step 4: Regenerate the list-fields goldens (deliberate output change)**

```bash
uv run python - <<'EOF'
from pathlib import Path
from led_ticker.app.factories import _list_widget_fields
d = Path("tests/golden/list_fields")
for t in ["message", "two_row", "gif", "countdown"]:
    (d / f"{t}.txt").write_text(_list_widget_fields(t))
EOF
git diff --stat tests/golden/list_fields/
```

Expected: each golden gains one `schedule` row under "Shared fields".

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_widget_schedule_dispatch.py tests/test_list_fields_golden.py tests/test_dispatch_drift.py tests/test_app.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/app/factories.py tests/test_widget_schedule_dispatch.py tests/golden/list_fields/
git commit -m "feat(factories): reserved schedule field — pop at dispatch, bind at build

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: Config surface — `[display] timezone`, `SectionConfig.schedule`, tz plumbing

**Files:**
- Modify: `src/led_ticker/config.py` (DisplayConfig line 36, SectionConfig line 105, load_config section loop line ~751)
- Modify: `src/led_ticker/app/run.py` (`_respawn_schedule` line 149, `_supervised_schedule` tz arg line ~163)
- Modify: `tests/test_docs_config_options_drift.py` (DOCUMENTED_KEYS["section"] set, line ~74)
- Modify: `docs/site/src/content/docs/reference/config-options.mdx` (rows for `display.timezone` + section `schedule`)
- Test: `tests/test_config_visibility_schedule.py` (new)

**Interfaces:**
- Consumes: `VisibilitySchedule`, `parse_visibility_schedule`, `set_schedule_timezone` (Task 2).
- Produces: `DisplayConfig.timezone: str = ""`; `SectionConfig.schedule: "VisibilitySchedule | None" = None` (parsed strictly at load); `_schedule_tz_name(display) -> str` helper in run.py (brightness tz fallback); `set_schedule_timezone` called on boot AND on every hot-reload via `_respawn_schedule`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_config_visibility_schedule.py`:

```python
"""[display] timezone + section-level schedule parsing (strict)."""

import pytest

from led_ticker.config import load_config

BASE = """
[display]
rows = 16
cols = 32
{display_extra}

[[playlist.section]]
mode = "slideshow"
{section_extra}

[[playlist.section.widget]]
type = "message"
text = "hi"
"""


def _write(tmp_path, display_extra="", section_extra=""):
    p = tmp_path / "config.toml"
    p.write_text(BASE.format(display_extra=display_extra, section_extra=section_extra))
    return p


def test_display_timezone_default_empty(tmp_path):
    cfg = load_config(_write(tmp_path))
    assert cfg.display.timezone == ""


def test_display_timezone_parsed(tmp_path):
    cfg = load_config(_write(tmp_path, display_extra='timezone = "America/New_York"'))
    assert cfg.display.timezone == "America/New_York"


def test_section_schedule_default_none(tmp_path):
    cfg = load_config(_write(tmp_path))
    assert cfg.sections[0].schedule is None


def test_section_schedule_parsed(tmp_path):
    cfg = load_config(
        _write(
            tmp_path,
            section_extra='schedule = { start = "09:00", end = "21:00", days = ["sat", "sun"] }',
        )
    )
    s = cfg.sections[0].schedule
    assert s is not None
    assert (s.window.start, s.window.end) == (9 * 60, 21 * 60)
    assert s.window.days == frozenset({5, 6})


def test_malformed_section_schedule_raises_with_location(tmp_path):
    with pytest.raises(ValueError, match=r"section\[0\]\.schedule"):
        load_config(
            _write(tmp_path, section_extra='schedule = { start = "9am", end = "17:00" }')
        )


def test_brightness_tz_falls_back_to_display_timezone():
    from led_ticker.app.run import _schedule_tz_name
    from led_ticker.config import DisplayConfig, ScheduleConfig

    d = DisplayConfig(timezone="America/Chicago")
    assert _schedule_tz_name(d) == "America/Chicago"
    d2 = DisplayConfig(
        timezone="America/Chicago",
        schedule=ScheduleConfig(timezone="Europe/London"),
    )
    assert _schedule_tz_name(d2) == "Europe/London"
    assert _schedule_tz_name(DisplayConfig()) == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_config_visibility_schedule.py -v`
Expected: FAIL — `DisplayConfig` has no `timezone`, `SectionConfig` has no `schedule`, `_schedule_tz_name` missing.

- [ ] **Step 3: Implement**

(a) `src/led_ticker/config.py` — `DisplayConfig` (after `backend`, before `schedule`):

```python
    # One clock for ALL schedules (widget/section visibility + brightness).
    # IANA name (zoneinfo), e.g. "America/New_York"; empty = system local.
    # display.schedule.timezone (brightness) remains a back-compat override.
    timezone: str = ""
```

(No `_coerce_display` change needed — string fields pass through the `set(defaults) - _DISPLAY_INT_FIELDS - {"schedule"}` loop at line 495.)

(b) `SectionConfig` — after `bg_color` (line 151):

```python
    # Section-level visibility schedule (core `schedule = {...}` — start/end
    # HH:MM + optional days). None = always shown. Parsed STRICTLY at load
    # (parse_visibility_schedule); evaluated once per playlist cycle in
    # app/run.py's section loop.
    schedule: Any | None = None
```

(Use `Any` in the dataclass annotation; import `VisibilitySchedule` only inside `load_config` to keep config.py's import graph flat — matches the local-import style used for MigrationError.)

(c) In `load_config`'s section loop, before `section = SectionConfig(` (line ~751):

```python
        section_schedule = None
        if "schedule" in section_raw:
            from led_ticker.schedule import parse_visibility_schedule

            section_schedule = parse_visibility_schedule(
                section_raw["schedule"], location=f"section[{i}].schedule"
            )
```

and add `schedule=section_schedule,` to the `SectionConfig(...)` call.

(d) `src/led_ticker/app/run.py` — add a pure helper above `_respawn_schedule` (line 149):

```python
def _schedule_tz_name(display: Any) -> str:
    """Brightness-scheduler timezone: its own field wins (back-compat),
    else the sign-wide [display] timezone, else "" (system local)."""
    return display.schedule.timezone or display.timezone
```

In `_respawn_schedule` (line 149), first line of the body — this runs at boot AND on every hot-reload apply, so it's the single site that keeps the visibility clock current:

```python
    from led_ticker.schedule import set_schedule_timezone

    set_schedule_timezone(config.display.timezone)
```

And where `_supervised_schedule` is constructed (line ~163), replace `config.display.schedule.timezone` with `_schedule_tz_name(config.display)`.

(e) `tests/test_docs_config_options_drift.py` — add `"schedule"` to the `DOCUMENTED_KEYS["section"]` set (line ~74). (`display` derives from `fields(DisplayConfig)` automatically.)

(f) `docs/site/src/content/docs/reference/config-options.mdx` — add rows matching the surrounding table format (run the drift test to see exactly which headings it scans):
- Under `## [display]`: `timezone` — "IANA timezone for ALL schedules (visibility + brightness), e.g. `\"America/New_York\"`; empty = system local. `display.schedule.timezone` still overrides for brightness windows." Default: `""`.
- Under `## [[playlist.section]]`: `schedule` — "show this section only during a time window: `{ start = \"09:00\", end = \"21:00\", days = [\"mon\"] }`; `start > end` wraps overnight. See /concepts/scheduling/." Default: none (always shown).

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_config_visibility_schedule.py tests/test_config.py tests/test_config_schedule.py tests/test_docs_config_options_drift.py tests/test_schedule_ticker.py -v`
Expected: ALL PASS

Also verify the section field listing picks up the new field automatically:

```bash
uv run led-ticker --list-fields section | grep schedule
```

Expected: a `schedule` row appears. If the section listing uses a hints dict like `FIELD_HINTS`, add an entry mirroring the widget-level `schedule` hint from Task 5.

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/config.py src/led_ticker/app/run.py tests/test_config_visibility_schedule.py tests/test_docs_config_options_drift.py docs/site/src/content/docs/reference/config-options.mdx
git commit -m "feat(config): [display] timezone + section-level schedule, tz plumbing

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 7: Section skip + all-dark idle in the run loop

**Files:**
- Modify: `src/led_ticker/app/run.py` (helpers near `_idle_on_empty_playlist` line 194; main loop lines ~848-930)
- Test: `tests/test_run_section_schedule.py` (new)

**Interfaces:**
- Consumes: `SectionConfig.schedule` (Task 6).
- Produces: `_section_schedule_active(section) -> bool`; `_idle_when_all_scheduled_out(led_frame, any_section_ran, was_dark) -> bool` (returns new dark state); main loop tracks `any_section_ran` per cycle.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_run_section_schedule.py`:

```python
"""Section-level schedule gate + all-dark idle in the run loop."""

import asyncio
import logging
from types import SimpleNamespace
from unittest.mock import Mock

from led_ticker.app.run import _idle_when_all_scheduled_out, _section_schedule_active


class _Active:
    def is_active(self):
        return True


class _Inactive:
    def is_active(self):
        return False


class _Boom:
    def is_active(self):
        raise RuntimeError("boom")


class TestSectionScheduleActive:
    def test_no_schedule_is_active(self):
        assert _section_schedule_active(SimpleNamespace(schedule=None)) is True

    def test_active(self):
        assert _section_schedule_active(SimpleNamespace(schedule=_Active())) is True

    def test_inactive(self):
        assert _section_schedule_active(SimpleNamespace(schedule=_Inactive())) is False

    def test_raising_keeps_section(self):
        assert _section_schedule_active(SimpleNamespace(schedule=_Boom())) is True


def _frame():
    frame = Mock()
    frame.get_clean_canvas.return_value = Mock(name="canvas")
    frame.swap.return_value = Mock(name="back_buffer")
    return frame


class TestIdleWhenAllScheduledOut:
    def test_sections_ran_resets_dark(self, caplog):
        frame = _frame()
        with caplog.at_level(logging.INFO):
            dark = asyncio.run(_idle_when_all_scheduled_out(frame, True, True))
        assert dark is False
        assert "waking" in caplog.text
        frame.get_clean_canvas.assert_not_called()

    def test_sections_ran_stays_quiet_when_not_dark(self, caplog):
        with caplog.at_level(logging.INFO):
            dark = asyncio.run(_idle_when_all_scheduled_out(_frame(), True, False))
        assert dark is False
        assert caplog.text == ""

    def test_transition_to_dark_blanks_once_and_logs(self, caplog):
        frame = _frame()
        with caplog.at_level(logging.INFO):
            dark = asyncio.run(_idle_when_all_scheduled_out(frame, False, False))
        assert dark is True
        frame.get_clean_canvas.assert_called_once()
        frame.swap.assert_called_once_with(frame.get_clean_canvas.return_value)
        assert "panel dark" in caplog.text

    def test_already_dark_does_not_reblank(self, caplog):
        frame = _frame()
        with caplog.at_level(logging.INFO):
            dark = asyncio.run(_idle_when_all_scheduled_out(frame, False, True))
        assert dark is True
        frame.get_clean_canvas.assert_not_called()
        assert caplog.text == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_run_section_schedule.py -v`
Expected: FAIL with `ImportError: cannot import name '_section_schedule_active'`

- [ ] **Step 3: Implement the helpers**

In `src/led_ticker/app/run.py`, after `_idle_on_empty_playlist` (line 215):

```python
def _section_schedule_active(section: Any) -> bool:
    """Section-level `schedule = {...}` gate. No schedule = always active.
    Same contract as the widget-level check (ticker._schedule_active): an
    evaluation error KEEPS the section — scheduling must never blank the
    panel by accident."""
    sched = getattr(section, "schedule", None)
    if sched is None:
        return True
    try:
        return bool(sched.is_active())
    except Exception:  # noqa: BLE001 - visibility must not crash the run loop
        logging.exception("section schedule check failed; showing section")
        return True


async def _idle_when_all_scheduled_out(
    led_frame: Any, any_section_ran: bool, was_dark: bool
) -> bool:
    """When EVERY section sat outside its schedule window this cycle, blank
    the panel (a closed storefront going dark is correct behavior, not a
    freeze) and idle 1s so the outer loop's reload/restart checks stay
    responsive. Blanks and logs only on the dark/wake TRANSITIONS — never
    per iteration. Returns the new dark state."""
    if any_section_ran:
        if was_dark:
            logging.info("schedule: a section is active again — panel waking")
        return False
    if not was_dark:
        logging.info(
            "schedule: every section is outside its schedule window — panel dark"
        )
        canvas = led_frame.get_clean_canvas()
        canvas = led_frame.swap(canvas)  # constraint #1: capture the swap return
        del canvas  # next cycle re-fetches a clean canvas; nothing draws meanwhile
    await asyncio.sleep(1.0)
    return True
```

- [ ] **Step 4: Wire into the main loop**

In the main `while True:` loop:

(a) Before the loop starts (next to `_empty_playlist_warned = False`, line 848), add:

```python
                _any_section_ran = True  # first pass: no idle before sections run
                _display_dark = False
```

(b) At the top of each `while` iteration, immediately after the `_idle_on_empty_playlist` block (`if _idled: continue`, line ~886), add:

```python
                    _display_dark = await _idle_when_all_scheduled_out(
                        led_frame, _any_section_ran, _display_dark
                    )
                    _any_section_ran = False
```

(c) Inside the `for section_index, section in enumerate(config.sections):` loop, right after the per-section restart check (`sys.exit(0)` block ending line ~922) and BEFORE `status_board.record_section`, add:

```python
                        if not _section_schedule_active(section):
                            logging.debug(
                                "section %d skipped: outside its schedule window",
                                section_index,
                            )
                            continue
                        _any_section_ran = True
```

(d) In the reload branch inside the for loop (the `break` at line ~910), add `_any_section_ran = True` on the line before `break` — a reload aborts the pass mid-cycle, so it must not read as "everything scheduled out".

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_run_section_schedule.py tests/test_app.py tests/test_app_run_load_order.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/app/run.py tests/test_run_section_schedule.py
git commit -m "feat(run): skip scheduled-out sections; blank + idle when all are out

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 8: Validation — display.timezone rule, clock note, week-sweep blank warning

**Files:**
- Modify: `src/led_ticker/validate.py` (new checks near `_check_schedule` line 2058; wire-up at line ~2848)
- Test: `tests/test_validate_visibility_schedule.py` (new)

**Interfaces:**
- Consumes: `TimeWindow.active_at`, `parse_visibility_schedule` (Tasks 1–2); `SectionConfig.schedule` (Task 6); existing `ValidationIssue`, `_VALID_DAYS`.
- Produces: `_check_display_timezone(config)`, `_check_blank_intervals(config)` (both `-> list[ValidationIssue]`, `rule=None` like `_check_schedule`'s issues), `_visibility_schedule_notes(config) -> list[str]`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_validate_visibility_schedule.py`:

```python
"""Preflight rules for visibility schedules: timezone, clock note, blank sweep."""

import asyncio

from led_ticker.validate import validate_config_text

BASE = """
[display]
rows = 16
cols = 32
backend = "headless"
{display_extra}

{sections}
"""

SECTION = """
[[playlist.section]]
mode = "slideshow"
{section_extra}
[[playlist.section.widget]]
type = "message"
text = "hi"
{widget_extra}
"""


def _run(display_extra="", sections=None):
    text = BASE.format(
        display_extra=display_extra,
        sections="\n".join(sections or [SECTION.format(section_extra="", widget_extra="")]),
    )
    return asyncio.run(validate_config_text(text))


def test_bad_display_timezone_is_an_error():
    res = _run(display_extra='timezone = "Not/AZone"')
    assert any("display.timezone" in i.location for i in res.errors)


def test_valid_display_timezone_passes():
    res = _run(display_extra='timezone = "America/New_York"')
    assert not any("display.timezone" in i.location for i in res.errors)


def test_clock_note_printed_when_schedules_present():
    res = _run(
        display_extra='timezone = "America/New_York"',
        sections=[
            SECTION.format(
                section_extra='schedule = { start = "09:00", end = "17:00" }',
                widget_extra="",
            )
        ],
    )
    assert any("visibility schedules evaluate at" in n for n in res.notes)
    assert any("America/New_York" in n for n in res.notes)


def test_no_clock_note_without_schedules():
    res = _run()
    assert not any("visibility schedules evaluate" in n for n in res.notes)


def test_blank_interval_warning_when_sign_has_gaps():
    # One section, scheduled 09:00-17:00: the sign is blank 17:00-09:00 daily.
    res = _run(
        sections=[
            SECTION.format(
                section_extra='schedule = { start = "09:00", end = "17:00" }',
                widget_extra="",
            )
        ]
    )
    warning_texts = [i.message for i in res.warnings]
    assert any("blank" in t for t in warning_texts)


def test_no_blank_warning_when_windows_cover_the_week():
    open_w = SECTION.format(
        section_extra='schedule = { start = "09:00", end = "17:00" }', widget_extra=""
    )
    closed_w = SECTION.format(
        section_extra='schedule = { start = "17:00", end = "09:00" }', widget_extra=""
    )
    res = _run(sections=[open_w, closed_w])
    assert not any("blank" in i.message for i in res.warnings)


def test_unscheduled_section_means_never_blank():
    scheduled = SECTION.format(
        section_extra='schedule = { start = "09:00", end = "17:00" }', widget_extra=""
    )
    always_on = SECTION.format(section_extra="", widget_extra="")
    res = _run(sections=[scheduled, always_on])
    assert not any("blank" in i.message for i in res.warnings)


def test_widget_level_schedules_participate_in_sweep():
    # Single section, its ONLY widget scheduled 09:00-17:00 -> blank warning.
    res = _run(
        sections=[
            SECTION.format(
                section_extra="",
                widget_extra='schedule = { start = "09:00", end = "17:00" }',
            )
        ]
    )
    assert any("blank" in i.message for i in res.warnings)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_validate_visibility_schedule.py -v`
Expected: timezone/note/blank tests FAIL (no such rule/note yet). If `validate_config_text` needs different kwargs, mirror an existing test that calls it (grep `validate_config_text` under tests/) and adjust the harness, not the assertions.

- [ ] **Step 3: Implement**

In `src/led_ticker/validate.py`, add after `_check_schedule`:

```python
def _check_display_timezone(config: AppConfig) -> list[ValidationIssue]:
    """[display] timezone (the sign-wide clock for visibility + brightness
    schedules) must be a resolvable IANA name. Runtime falls back to system
    local with a warning; preflight is where the typo should be caught."""
    tz = config.display.timezone
    if not tz:
        return []
    if not isinstance(tz, str):
        return [
            ValidationIssue(
                rule=None,
                location="display.timezone",
                message=f"timezone must be a string IANA name, got {type(tz).__name__}",
                fix=(
                    "Use an IANA name like 'America/New_York',"
                    " or leave it empty for system local time."
                ),
                severity="error",
            )
        ]
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

    try:
        ZoneInfo(tz)
    except ZoneInfoNotFoundError, ValueError, TypeError:
        return [
            ValidationIssue(
                rule=None,
                location="display.timezone",
                message=f"timezone {tz!r} is not a valid IANA timezone name",
                fix=(
                    "Use an IANA name like 'America/New_York',"
                    " or leave it empty for system local time."
                ),
                severity="error",
            )
        ]
    return []


def _iter_widget_schedules(config: AppConfig):
    """Yield (section_index, parsed VisibilitySchedule | None) per widget.
    None = widget has no schedule OR its schedule is malformed (the async
    build check reports malformed ones; this static sweep stays quiet)."""
    from led_ticker.schedule import parse_visibility_schedule

    for i, section in enumerate(config.sections):
        for w in section.widgets:
            raw = w.get("schedule")
            if raw is None:
                yield i, None
                continue
            try:
                yield i, parse_visibility_schedule(raw, location=f"section[{i}]")
            except ValueError:
                yield i, None


def _any_visibility_schedule(config: AppConfig) -> bool:
    return any(s.schedule is not None for s in config.sections) or any(
        sched is not None for _i, sched in _iter_widget_schedules(config)
    )


def _visibility_schedule_notes(config: AppConfig) -> list[str]:
    """One line telling the user what clock visibility schedules run on —
    catches the TZ-less Docker container (UTC) at preflight, not at 5 p.m."""
    if not _any_visibility_schedule(config):
        return []
    from datetime import datetime
    from zoneinfo import ZoneInfo

    tz_name = config.display.timezone
    try:
        tz = ZoneInfo(tz_name) if tz_name else None
    except Exception:
        return []  # _check_display_timezone already errored on the bad name
    now = datetime.now(tz)
    label = tz_name or "system local"
    return [f"visibility schedules evaluate at {now:%H:%M} ({label})"]


_WEEK_DAY_LABELS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def _fmt_week_minute(m: int) -> str:
    day, rem = divmod(m % 10080, 1440)
    return f"{_WEEK_DAY_LABELS[day]} {rem // 60:02d}:{rem % 60:02d}"


def _check_blank_intervals(config: AppConfig) -> list[ValidationIssue]:
    """Week sweep (10,080 minutes, same technique as
    unreachable_window_indices): warn listing the intervals where EVERY
    section is scheduled out — 'your sign is blank Tue 03:00-09:00' before
    deploy. Warning, not error: dark-when-closed is often intended."""
    if not _any_visibility_schedule(config):
        return []
    per_section_widget_scheds: dict[int, list] = {}
    per_section_all_scheduled: dict[int, bool] = {
        i: bool(s.widgets) for i, s in enumerate(config.sections)
    }
    for i, sched in _iter_widget_schedules(config):
        if sched is None:
            per_section_all_scheduled[i] = False
        else:
            per_section_widget_scheds.setdefault(i, []).append(sched)

    def _sign_active(minutes: int, weekday: int) -> bool:
        for i, section in enumerate(config.sections):
            if section.schedule is not None and not section.schedule.window.active_at(
                minutes, weekday
            ):
                continue
            wscheds = per_section_widget_scheds.get(i, [])
            if (
                per_section_all_scheduled[i]
                and wscheds
                and not any(s.window.active_at(minutes, weekday) for s in wscheds)
            ):
                continue
            return True
        return False

    blank = [
        m for m in range(10080) if not _sign_active(m % 1440, m // 1440)
    ]
    if not blank:
        return []
    # Group consecutive minutes into runs; merge the week-boundary wrap.
    runs: list[list[int]] = []
    for m in blank:
        if runs and m == runs[-1][1] + 1:
            runs[-1][1] = m
        else:
            runs.append([m, m])
    if len(runs) > 1 and runs[0][0] == 0 and runs[-1][1] == 10079:
        runs[0][0] = runs.pop()[0] - 10080  # wrap: Sun tail joins Mon head
    shown = [
        f"{_fmt_week_minute(a)}-{_fmt_week_minute(b + 1)}" for a, b in runs[:4]
    ]
    more = f" (and {len(runs) - 4} more)" if len(runs) > 4 else ""
    return [
        ValidationIssue(
            rule=None,
            location="playlist",
            message=(
                "the sign is blank (every section scheduled out) during: "
                + ", ".join(shown)
                + more
            ),
            fix=(
                "Intended for a closed-hours dark panel? Ignore this. "
                "Otherwise add an unscheduled fallback section or widen a window."
            ),
            severity="warning",
        )
    ]
```

Wire up at the `notes` block (line ~2847):

```python
    notes: list[str] = []
    _sched_issues = (
        _check_schedule(config)
        + _check_display_timezone(config)
        + _check_blank_intervals(config)
    )
    errors.extend(i for i in _sched_issues if i.severity == "error")
    warnings.extend(i for i in _sched_issues if i.severity == "warning")
    if config.display.schedule.enabled:
        from led_ticker.schedule import format_schedule_summary

        notes = format_schedule_summary(
            config.display.schedule, config.display.brightness
        )
    notes = notes + _visibility_schedule_notes(config)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_validate_visibility_schedule.py tests/test_validate*.py -v`
Expected: ALL PASS (adjust to the actual validate-test filenames if the glob misses; `ls tests/ | grep validate`)

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/validate.py tests/test_validate_visibility_schedule.py
git commit -m "feat(validate): display.timezone rule, schedule clock note, blank-interval sweep

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 9: Docs, example config, CLAUDE.md invariant

**Files:**
- Create: `docs/site/src/content/docs/concepts/scheduling.mdx`
- Modify: `config/config.example.toml` (commented open/closed example block)
- Modify: `CLAUDE.md` (one invariant bullet)
- Modify: wherever `[display.schedule]` (brightness) is documented on the docs site — add a cross-link (find with `grep -rn "display.schedule" docs/site/src/content/`)

**Interfaces:** none (prose only). Read `docs/DOCS-STYLE.md` FIRST — it is the style guide and per-page review rubric for all docs work. Docs tooling runs on pnpm via nvm: run `source ~/.nvm/nvm.sh && nvm use` (or verify `node`/`pnpm` are on PATH) before any `make docs-*` target.

- [ ] **Step 1: Read `docs/DOCS-STYLE.md` and one existing concepts page** (`docs/site/src/content/docs/concepts/busy-light.mdx` or similar) to copy frontmatter shape and heading conventions.

- [ ] **Step 2: Write `docs/site/src/content/docs/concepts/scheduling.mdx`**

Cover, in the site's established voice (this is the content contract; exact prose is the implementer's, style per DOCS-STYLE.md):

- One mental model: **schedules are time windows** (`start`/`end` HH:MM + optional `days`, `start > end` wraps overnight). Two applications: **visibility** (`schedule = {...}` on any widget or section — this page) and **brightness** (`[display.schedule]` — cross-link).
- The open/closed storefront example (copy the TOML from the spec's Config surface section — `[[playlist.section]]` / `[[playlist.section.widget]]` syntax).
- `schedule` works on every widget type, including plugin widgets; it's core-owned and composes (AND) with widgets that hide themselves (countdown out of range).
- Timezone: `[display] timezone`, the Docker-defaults-to-UTC gotcha, and that `led-ticker validate` prints the resolved clock.
- Behavior notes: section-level granularity is one playlist cycle (put both widgets in one section for tight flips); a fully scheduled-out sign goes dark on purpose; validate warns about accidental blank intervals; the one-transition-frame exit artifact.

- [ ] **Step 3: Add the example block to `config/config.example.toml`**

Append (commented, matching the file's existing comment style):

```toml
# --- Scheduling (see https://docs.ledticker.dev/concepts/scheduling/) ---
# Show a widget only during a time window. start > end wraps overnight.
# [[playlist.section.widget]]
# type = "image"
# path = "open.png"
# schedule = { start = "09:00", end = "17:00", days = ["mon", "tue", "wed", "thu", "fri"] }
#
# [[playlist.section.widget]]
# type = "image"
# path = "closed.png"
# schedule = { start = "17:00", end = "09:00" }
#
# Sections take the same field; set the sign-wide clock with:
# [display]
# timezone = "America/New_York"
```

- [ ] **Step 4: Add the CLAUDE.md invariant bullet**

In the "Load-bearing invariants by subsystem" section, after the **Widget visibility hook** bullet:

```markdown
**Visibility scheduling** (`schedule = {...}` on widgets/sections) — `schedule` is a HARD-RESERVED core field: popped at dispatch level in `app/factories.py` (never reaches a widget constructor; a widget class declaring its own `schedule` field is rejected at config-load), parsed STRICTLY by `schedule.parse_visibility_schedule`, and bound to the built widget via the weakref registry in `schedule.py` (`bind_schedule`/`schedule_for` — widgets are slotted+unhashable, hence id-keyed weakrefs). Engine gates: `ticker._schedule_active` in `_expand_sources` (ANDs with `should_display`; a raising check KEEPS the widget) and `run._section_schedule_active` in the section loop (all-out → `_idle_when_all_scheduled_out` blanks once + idles, capturing the swap). `TimeWindow` in `schedule.py` is the ONE wrap-semantics implementation shared with brightness windows — never fork it. Clock: `[display] timezone` via `set_schedule_timezone`, refreshed in `_respawn_schedule` (boot + hot-reload). Tripwires: `tests/test_visibility_schedule.py`, `TestScheduleGate` (`tests/test_ticker_expand_sources.py`), `tests/test_widget_schedule_dispatch.py`, `tests/test_run_section_schedule.py`. Docs: <https://docs.ledticker.dev/concepts/scheduling/>.
```

- [ ] **Step 5: Verify docs build + full test suite**

```bash
source ~/.nvm/nvm.sh 2>/dev/null; make docs-build 2>/dev/null || echo "check Makefile for the docs target name (make help)"
make test
make lint
```

Expected: docs build clean; full suite green; ruff clean.

- [ ] **Step 6: Commit**

```bash
git add docs/site/src/content/docs/concepts/scheduling.mdx config/config.example.toml CLAUDE.md docs/site
git commit -m "docs: scheduling concepts page, example config block, CLAUDE.md invariant

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 10: Final verification + PR

**Files:** none new.

- [ ] **Step 1: Full gate**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker-widget-scheduling
git branch --show-current   # MUST print widget-scheduling
make test
make lint
uv run pyright
```

Expected: all green. Fix anything that isn't before proceeding.

- [ ] **Step 2: Smoke the feature end-to-end (headless backend)**

```bash
cat > /tmp/sched-smoke.toml <<'EOF'
[display]
rows = 16
cols = 32
backend = "headless"
timezone = "America/New_York"

[[playlist.section]]
mode = "slideshow"

[[playlist.section.widget]]
type = "message"
text = "OPEN"
schedule = { start = "09:00", end = "17:00", days = ["mon", "tue", "wed", "thu", "fri"] }

[[playlist.section.widget]]
type = "message"
text = "always on"
EOF
uv run led-ticker validate /tmp/sched-smoke.toml
```

Expected: valid, zero errors; notes include "visibility schedules evaluate at HH:MM (America/New_York)"; NO blank-interval warning (the unscheduled widget keeps the section alive). Then delete the `always on` widget block and re-validate: a blank-interval warning covering 17:00–09:00 weekdays + weekends appears.

- [ ] **Step 3: Push and open a draft PR**

Use the `open-pr` skill (James's PR conventions: succinct body, always draft, watch CI). Do NOT merge — merging requires James's explicit per-PR consent.
