# Calendar Widget Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `type = "calendar"` widget that shows upcoming events from a subscribed iCal (`.ics`) feed, in a rotating agenda or a live next-event countdown, with keyword filter/highlight.

**Architecture:** Always a Container (like `rss_feed`): a shared data core fetches + parses the `.ics` (recurrence-expanded via `recurring-ical-events`), then `update()` populates `feed_stories` per the `layout` knob — `agenda` builds one `TickerMessage` per event; `next` builds one live `_NextEventWidget` countdown (the clock's per-tick-redraw mechanism). `filter`/`highlight` mirror the baseball promotions widget.

**Tech Stack:** Python 3.14, attrs, aiohttp, `icalendar` + `recurring-ical-events` (new deps), pytest. Reuses `run_monitor_loop`/`spawn_tracked` (`widget.py`), `TickerMessage` (`widgets/message.py`), `format_clock` (`widgets/clock.py`), `FrameAwareBase` (`widgets/_frame_aware.py`).

**Spec:** `docs/superpowers/specs/2026-06-13-calendar-widget-design.md`

**Conventions for every task:**
- Worktree: `/Users/james/projects/github/jamesawesome/led-ticker-worktrees/calendar-widget`, branch `feat/calendar-widget`. Confirm with `git branch --show-current` (must NOT be `main`) before editing.
- Run tests with the worktree venv: `cd <worktree> && PYTHONPATH=tests/stubs .venv/bin/python -m pytest <files> -q`.
- Commit with the venv on PATH so hooks run: `PATH="$PWD/.venv/bin:$PATH" git commit ...`.
- Commit messages end with: `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

**File structure (locked):**
- `src/led_ticker/widgets/calendar.py` — everything: `CalendarEvent` (value object), `parse_ics` + helpers (pure), `_match_any`, `format_event_line`, `_NextEventWidget` (draw widget), `Calendar` (`@register("calendar")` Container). One file, mirroring how `clock.py` keeps its pure formatter + widget together.
- `tests/test_widgets/test_calendar.py` — all tests.
- `tests/fixtures/calendar_sample.ics` — fixture feed (one-off + all-day + RRULE).
- Append-only edits: `pyproject.toml`, `src/led_ticker/widgets/__init__.py`, `src/led_ticker/app/factories.py`, docs trees, `tests/test_widgets/test_registry.py`, `tests/test_border_surface_drift.py`, `docs/site/astro.config.mjs`.

---

### Task 1: Add dependencies + register an empty Calendar widget

**Files:**
- Modify: `pyproject.toml` (dependencies array)
- Create: `src/led_ticker/widgets/calendar.py`
- Modify: `src/led_ticker/widgets/__init__.py` (auto-import tuple)
- Test: `tests/test_widgets/test_calendar.py`

- [ ] **Step 1: Add the deps**

In `pyproject.toml`, add to the `dependencies` array (keep alphabetical-ish with the others):

```toml
    "icalendar>=6.0",
    "recurring-ical-events>=3.0",
```

Then run `cd <worktree> && make dev` (re-syncs the venv with the new deps). Expected: `uv sync` installs `icalendar` and `recurring-ical-events`.

- [ ] **Step 2: Write the failing registration test**

Create `tests/test_widgets/test_calendar.py`:

```python
"""Tests for the calendar widget."""

from led_ticker.widgets import get_widget_class


def test_calendar_registered():
    cls = get_widget_class("calendar")
    assert cls.__name__ == "Calendar"
```

- [ ] **Step 3: Run it — expect failure**

Run: `PYTHONPATH=tests/stubs .venv/bin/python -m pytest tests/test_widgets/test_calendar.py::test_calendar_registered -q`
Expected: FAIL — `KeyError`/`ValueError` for unknown widget `calendar`.

- [ ] **Step 4: Create the minimal widget**

Create `src/led_ticker/widgets/calendar.py`:

```python
"""Calendar widget: upcoming events from a subscribed iCal (.ics) feed.

Always a Container (like rss_feed): a shared data core fetches + parses the
feed, then update() populates feed_stories per the `layout` knob — `agenda`
builds one TickerMessage per event; `next` builds one live countdown widget.
"""

from typing import Any

import aiohttp
import attrs

from led_ticker.colors import DEFAULT_COLOR
from led_ticker.fonts import FONT_DEFAULT
from led_ticker.widget import Widget
from led_ticker.widgets import register
from led_ticker.widgets.message import TickerMessage


@register("calendar")
@attrs.define
class Calendar:
    """Container that shows upcoming .ics events as an agenda or next-event line."""

    session: aiohttp.ClientSession
    ics_url: str
    layout: str = "agenda"
    max_events: int = 5
    lookahead_days: int = 7
    time_format: str = "12h"
    timezone: str | None = None
    empty_text: str = "No upcoming events"
    update_interval: int = 900
    filter: list[str] = attrs.field(factory=list)
    highlight: list[str] = attrs.field(factory=list)
    padding: int = 6
    font: Any = attrs.Factory(lambda: FONT_DEFAULT)
    font_color: Any = attrs.field(default=None, kw_only=True)
    highlight_color: Any = attrs.field(default=None, kw_only=True)
    bg_color: Any = attrs.field(default=None, kw_only=True)
    border: Any | None = attrs.field(default=None, kw_only=True)
    feed_stories: list[Widget] = attrs.field(init=False, factory=list)
    feed_title: TickerMessage | None = attrs.field(init=False, default=None)
```

`DEFAULT_COLOR` import is used in later tasks (the fallback story color); keep it.

- [ ] **Step 5: Add to the auto-import tuple**

In `src/led_ticker/widgets/__init__.py`, add `calendar,` to the import tuple in alphabetical position (it appears as `clock,` / `rss_feed,` / `weather,` already — add `calendar,` before `clock,`).

- [ ] **Step 6: Run the test — expect pass**

Run: `PYTHONPATH=tests/stubs .venv/bin/python -m pytest tests/test_widgets/test_calendar.py -q`
Expected: PASS (1 passed).

- [ ] **Step 7: Commit**

```bash
PATH="$PWD/.venv/bin:$PATH" git add pyproject.toml uv.lock src/led_ticker/widgets/calendar.py src/led_ticker/widgets/__init__.py tests/test_widgets/test_calendar.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "feat(calendar): register skeleton widget + add icalendar deps

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: `CalendarEvent` + `parse_ics` (pure recurrence-expanded parsing)

**Files:**
- Modify: `src/led_ticker/widgets/calendar.py`
- Create: `tests/fixtures/calendar_sample.ics`
- Test: `tests/test_widgets/test_calendar.py`

- [ ] **Step 1: Create the fixture feed**

Create `tests/fixtures/calendar_sample.ics` (a one-off timed event, an all-day event, and a weekday-recurring event):

```text
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//led-ticker//calendar-test//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
UID:oneoff-1
DTSTART:20260615T150000Z
DTEND:20260615T153000Z
SUMMARY:Team Standup
END:VEVENT
BEGIN:VEVENT
UID:allday-1
DTSTART;VALUE=DATE:20260616
DTEND;VALUE=DATE:20260617
SUMMARY:Dentist
END:VEVENT
BEGIN:VEVENT
UID:rrule-1
DTSTART:20260615T100000Z
DTEND:20260615T103000Z
RRULE:FREQ=DAILY;COUNT=10
SUMMARY:Daily 1:1
END:VEVENT
END:VCALENDAR
```

- [ ] **Step 2: Write the failing parse tests**

Add to `tests/test_widgets/test_calendar.py`:

```python
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from led_ticker.widgets.calendar import CalendarEvent, parse_ics

_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "calendar_sample.ics"
_UTC = ZoneInfo("UTC")


def _parse(now, days=7, tz=_UTC):
    return parse_ics(_FIXTURE.read_text(), now=now, lookahead_days=days, tz=tz)


def test_parse_oneoff_event_tz_resolved():
    now = datetime(2026, 6, 15, 0, 0, tzinfo=_UTC)
    events = _parse(now)
    standup = [e for e in events if e.summary == "Team Standup"]
    assert len(standup) == 1
    assert standup[0].start == datetime(2026, 6, 15, 15, 0, tzinfo=_UTC)
    assert standup[0].all_day is False


def test_parse_all_day_event():
    now = datetime(2026, 6, 15, 0, 0, tzinfo=_UTC)
    events = _parse(now)
    dentist = [e for e in events if e.summary == "Dentist"]
    assert len(dentist) == 1
    assert dentist[0].all_day is True


def test_parse_rrule_expands_within_window():
    now = datetime(2026, 6, 15, 0, 0, tzinfo=_UTC)
    events = _parse(now, days=3)
    ones = [e for e in events if e.summary == "Daily 1:1"]
    # DAILY for 3-day window starting 06-15 -> 06-15, 06-16, 06-17
    assert len(ones) == 3
    assert ones[0].start < ones[1].start < ones[2].start


def test_parse_drops_past_and_sorts():
    now = datetime(2026, 6, 16, 12, 0, tzinfo=_UTC)  # after 06-15 events
    events = _parse(now, days=7)
    # no event should start before `now` (all_day Dentist on 06-16 still counts)
    starts = [e.start for e in events]
    assert starts == sorted(starts)
    assert all(not (e.start < now and not e.all_day) for e in events)


def test_calendar_event_is_value_object():
    e = CalendarEvent(summary="x", start=datetime(2026, 1, 1, tzinfo=_UTC), all_day=False)
    assert e.summary == "x"
```

- [ ] **Step 3: Run — expect failure**

Run: `PYTHONPATH=tests/stubs .venv/bin/python -m pytest tests/test_widgets/test_calendar.py -k parse -q`
Expected: FAIL — `ImportError` for `CalendarEvent` / `parse_ics`.

- [ ] **Step 4: Implement `CalendarEvent` + `parse_ics`**

Add to `src/led_ticker/widgets/calendar.py` (imports at top, definitions below the module docstring, above the `Calendar` class):

```python
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import icalendar
import recurring_ical_events


@attrs.define(frozen=True)
class CalendarEvent:
    """A parsed, display-ready calendar event in the display timezone."""

    summary: str
    start: datetime  # tz-aware, resolved to the display tz
    all_day: bool


def _to_display_start(dt_value: date | datetime, tz: ZoneInfo) -> tuple[datetime, bool]:
    """Resolve a DTSTART value to a tz-aware datetime + all_day flag.

    A bare `date` is an all-day event -> midnight of that date in `tz`.
    A naive `datetime` (floating time) is assumed to be in `tz`.
    """
    if isinstance(dt_value, datetime):
        if dt_value.tzinfo is None:
            return dt_value.replace(tzinfo=tz), False
        return dt_value.astimezone(tz), False
    # `date` (not datetime): all-day
    return datetime.combine(dt_value, time.min, tzinfo=tz), True


def parse_ics(
    text: str, *, now: datetime, lookahead_days: int, tz: ZoneInfo
) -> list[CalendarEvent]:
    """Parse an .ics document, expand recurrence in [now, now+lookahead_days],
    drop past events, and return CalendarEvents sorted by start (display tz)."""
    cal = icalendar.Calendar.from_ical(text)
    window_end = now + timedelta(days=lookahead_days)
    occurrences = recurring_ical_events.of(cal).between(now, window_end)

    events: list[CalendarEvent] = []
    for comp in occurrences:
        summary = str(comp.get("SUMMARY", "")).strip()
        if not summary:
            continue
        dtstart = comp.get("DTSTART")
        if dtstart is None:
            continue
        start, all_day = _to_display_start(dtstart.dt, tz)
        # An all-day event is upcoming through the end of its day; a timed
        # event must not have started yet.
        if all_day:
            if start + timedelta(days=1) <= now:
                continue
        elif start < now:
            continue
        events.append(CalendarEvent(summary=summary, start=start, all_day=all_day))

    events.sort(key=lambda e: e.start)
    return events
```

- [ ] **Step 5: Run — expect pass**

Run: `PYTHONPATH=tests/stubs .venv/bin/python -m pytest tests/test_widgets/test_calendar.py -k parse -q`
Expected: PASS (4 parse tests + the value-object test).

- [ ] **Step 6: Commit**

```bash
PATH="$PWD/.venv/bin:$PATH" git add src/led_ticker/widgets/calendar.py tests/test_widgets/test_calendar.py tests/fixtures/calendar_sample.ics
PATH="$PWD/.venv/bin:$PATH" git commit -m "feat(calendar): parse_ics with recurrence expansion + CalendarEvent

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: `_match_any` + filter/highlight selection (cap with guaranteed inclusion)

**Files:**
- Modify: `src/led_ticker/widgets/calendar.py`
- Test: `tests/test_widgets/test_calendar.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_widgets/test_calendar.py`:

```python
from led_ticker.widgets.calendar import _match_any, select_events


def _ev(summary, day):
    return CalendarEvent(
        summary=summary, start=datetime(2026, 6, day, 9, 0, tzinfo=_UTC), all_day=False
    )


def test_match_any_case_insensitive_substring():
    assert _match_any("Daily 1:1 w/ Sam", ["1:1"]) is True
    assert _match_any("STANDUP", ["stand"]) is True
    assert _match_any("Lunch", ["1:1", "review"]) is False
    assert _match_any("anything", []) is False


def test_select_filter_keeps_only_matches():
    events = [_ev("Standup", 15), _ev("Dentist", 16), _ev("1:1 Sam", 17)]
    kept = select_events(events, filter=["1:1", "dentist"], highlight=[], max_events=5)
    assert [e.summary for e in kept] == ["Dentist", "1:1 Sam"]


def test_select_highlight_guaranteed_inclusion_chronological():
    # 6 events; cap 3; the highlighted one (day 20) would be dropped by a plain
    # soonest-3 cap, but must survive — and order stays chronological.
    events = [_ev(f"E{d}", d) for d in (15, 16, 17, 18, 19)] + [_ev("Payday", 20)]
    kept = select_events(events, filter=[], highlight=["payday"], max_events=3)
    assert "Payday" in [e.summary for e in kept]
    assert len(kept) == 3
    assert [e.start for e in kept] == sorted(e.start for e in kept)


def test_select_no_filter_no_highlight_is_soonest_capped():
    events = [_ev(f"E{d}", d) for d in (15, 16, 17, 18)]
    kept = select_events(events, filter=[], highlight=[], max_events=2)
    assert [e.summary for e in kept] == ["E15", "E16"]
```

- [ ] **Step 2: Run — expect failure**

Run: `PYTHONPATH=tests/stubs .venv/bin/python -m pytest tests/test_widgets/test_calendar.py -k "match or select" -q`
Expected: FAIL — `ImportError` for `_match_any` / `select_events`.

- [ ] **Step 3: Implement**

Add to `src/led_ticker/widgets/calendar.py` (below `parse_ics`):

```python
def _match_any(summary: str, keywords: list[str]) -> bool:
    """Case-insensitive substring match against any keyword (empty -> False).

    Same semantics as the baseball promotions widget's _match_any.
    """
    s = summary.casefold()
    return any(k.casefold() in s for k in keywords)


def select_events(
    events: list[CalendarEvent],
    *,
    filter: list[str],
    highlight: list[str],
    max_events: int,
) -> list[CalendarEvent]:
    """Apply the keyword filter, then cap to max_events while guaranteeing every
    highlighted event survives. `events` is assumed sorted by start; the result
    is re-sorted by start so the agenda reads chronologically."""
    if filter:
        events = [e for e in events if _match_any(e.summary, filter)]
    if max_events <= 0 or len(events) <= max_events:
        return events
    highlighted = [e for e in events if _match_any(e.summary, highlight)]
    rest = [e for e in events if e not in highlighted]
    kept = highlighted[:max_events]
    kept += rest[: max_events - len(kept)]
    kept.sort(key=lambda e: e.start)
    return kept
```

- [ ] **Step 4: Run — expect pass**

Run: `PYTHONPATH=tests/stubs .venv/bin/python -m pytest tests/test_widgets/test_calendar.py -k "match or select" -q`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
PATH="$PWD/.venv/bin:$PATH" git add src/led_ticker/widgets/calendar.py tests/test_widgets/test_calendar.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "feat(calendar): keyword filter + highlight selection with guaranteed inclusion

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: `format_event_line` (agenda line formatting)

**Files:**
- Modify: `src/led_ticker/widgets/calendar.py`
- Test: `tests/test_widgets/test_calendar.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_widgets/test_calendar.py`:

```python
from led_ticker.widgets.calendar import format_event_line


def test_format_today_timed_12h():
    now = datetime(2026, 6, 15, 8, 0, tzinfo=_UTC)
    e = CalendarEvent("Standup", datetime(2026, 6, 15, 15, 0, tzinfo=_UTC), False)
    assert format_event_line(e, now=now, time_format="12h", tz=_UTC) == "Today 3:00 PM  Standup"


def test_format_tomorrow_24h():
    now = datetime(2026, 6, 15, 8, 0, tzinfo=_UTC)
    e = CalendarEvent("Dentist", datetime(2026, 6, 16, 9, 5, tzinfo=_UTC), False)
    assert format_event_line(e, now=now, time_format="24h", tz=_UTC) == "Tomorrow 09:05  Dentist"


def test_format_weekday_within_week():
    now = datetime(2026, 6, 15, 8, 0, tzinfo=_UTC)  # Mon 2026-06-15
    e = CalendarEvent("1:1", datetime(2026, 6, 18, 10, 0, tzinfo=_UTC), False)  # Thu
    assert format_event_line(e, now=now, time_format="24h", tz=_UTC) == "Thu 10:00  1:1"


def test_format_all_day_omits_time():
    now = datetime(2026, 6, 15, 8, 0, tzinfo=_UTC)
    e = CalendarEvent("Holiday", datetime(2026, 6, 16, 0, 0, tzinfo=_UTC), True)
    assert format_event_line(e, now=now, time_format="12h", tz=_UTC) == "Tomorrow  Holiday"
```

- [ ] **Step 2: Run — expect failure**

Run: `PYTHONPATH=tests/stubs .venv/bin/python -m pytest tests/test_widgets/test_calendar.py -k format_ -q`
Expected: FAIL — `ImportError` for `format_event_line`.

- [ ] **Step 3: Implement**

Add the import near the top of `src/led_ticker/widgets/calendar.py`:

```python
from led_ticker.widgets.clock import format_clock
```

Add below `select_events`:

```python
_WEEKDAY_ABBR = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_MONTH_ABBR = (
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
)


def _day_label(start: datetime, now: datetime) -> str:
    """Smart day label relative to `now` (same date math both in display tz).

    Today / Tomorrow / weekday abbrev (within 7 days) / "Mon D" further out.
    Built from datetime fields (not %- strftime codes) for cross-platform
    determinism — same rule as the clock presets.
    """
    delta_days = (start.date() - now.date()).days
    if delta_days == 0:
        return "Today"
    if delta_days == 1:
        return "Tomorrow"
    if 2 <= delta_days < 7:
        return _WEEKDAY_ABBR[start.weekday()]
    return f"{_MONTH_ABBR[start.month - 1]} {start.day}"


def format_event_line(
    event: CalendarEvent, *, now: datetime, time_format: str, tz: ZoneInfo
) -> str:
    """Agenda line: '<day> <time>  <summary>'; all-day omits the time."""
    day = _day_label(event.start, now)
    if event.all_day:
        return f"{day}  {event.summary}"
    return f"{day} {format_clock(event.start, time_format)}  {event.summary}"
```

Note: `format_clock("12h")` yields `"3:00 PM"` (no leading zero) and `"24h"` yields `"09:05"` — matches the test expectations.

- [ ] **Step 4: Run — expect pass**

Run: `PYTHONPATH=tests/stubs .venv/bin/python -m pytest tests/test_widgets/test_calendar.py -k format_ -q`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
PATH="$PWD/.venv/bin:$PATH" git add src/led_ticker/widgets/calendar.py tests/test_widgets/test_calendar.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "feat(calendar): agenda line formatting with smart day labels

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: `_NextEventWidget` (live next-event countdown)

**Files:**
- Modify: `src/led_ticker/widgets/calendar.py`
- Test: `tests/test_widgets/test_calendar.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_widgets/test_calendar.py`:

```python
from led_ticker.widgets.calendar import _NextEventWidget, format_relative


def test_format_relative_minutes():
    now = datetime(2026, 6, 15, 14, 35, tzinfo=_UTC)
    e = CalendarEvent("Standup", datetime(2026, 6, 15, 15, 0, tzinfo=_UTC), False)
    assert format_relative(e, now, "No upcoming events") == "Standup in 25m"


def test_format_relative_hours_minutes():
    now = datetime(2026, 6, 15, 12, 50, tzinfo=_UTC)
    e = CalendarEvent("Dentist", datetime(2026, 6, 15, 15, 0, tzinfo=_UTC), False)
    assert format_relative(e, now, "x") == "Dentist in 2h 10m"


def test_format_relative_days():
    now = datetime(2026, 6, 15, 12, 0, tzinfo=_UTC)
    e = CalendarEvent("Trip", datetime(2026, 6, 18, 12, 0, tzinfo=_UTC), False)
    assert format_relative(e, now, "x") == "Trip in 3d"


def test_format_relative_in_progress_is_now():
    now = datetime(2026, 6, 15, 15, 5, tzinfo=_UTC)
    e = CalendarEvent("Standup", datetime(2026, 6, 15, 15, 0, tzinfo=_UTC), False)
    assert format_relative(e, now, "x") == "Standup now"


def test_format_relative_none_is_empty_text():
    now = datetime(2026, 6, 15, 15, 5, tzinfo=_UTC)
    assert format_relative(None, now, "No upcoming events") == "No upcoming events"


def test_next_event_widget_draws(canvas):
    e = CalendarEvent("Standup", datetime(2026, 6, 15, 15, 0, tzinfo=_UTC), False)
    w = _NextEventWidget(event=e, empty_text="none", timezone="UTC")
    out_canvas, cursor = w.draw(canvas)
    assert out_canvas is canvas
    assert isinstance(cursor, int)


def test_next_event_widget_rainbow_advances_frame(canvas):
    from led_ticker.color_providers import Rainbow

    e = CalendarEvent("Standup", datetime(2026, 6, 15, 15, 0, tzinfo=_UTC), False)
    w = _NextEventWidget(event=e, empty_text="none", timezone="UTC", font_color=Rainbow())
    w.advance_frame()
    w.draw(canvas)  # must not raise; per-char path exercised
```

- [ ] **Step 2: Run — expect failure**

Run: `PYTHONPATH=tests/stubs .venv/bin/python -m pytest tests/test_widgets/test_calendar.py -k "relative or next_event" -q`
Expected: FAIL — `ImportError` for `_NextEventWidget` / `format_relative`.

- [ ] **Step 3: Implement**

Add imports near the top of `src/led_ticker/widgets/calendar.py`:

```python
from datetime import datetime as _dt  # for datetime.now(tz) in draw
from typing import Any

from led_ticker._types import Canvas, DrawResult
from led_ticker.color_providers import ColorProvider, _ConstantColor
from led_ticker.drawing import compute_baseline, compute_cursor, get_text_width
from led_ticker.text_render import draw_text, draw_text_per_char
from led_ticker.widgets._frame_aware import FrameAwareBase
```

(Some of these may already be imported from earlier tasks; do not duplicate — keep one import each.)

Add the relative formatter and widget (below `format_event_line`):

```python
def format_relative(
    event: CalendarEvent | None, now: datetime, empty_text: str
) -> str:
    """Next-mode line: '<summary> in <rel>' / '<summary> now' / empty_text."""
    if event is None:
        return empty_text
    delta = event.start - now
    secs = delta.total_seconds()
    if secs <= 0:
        return f"{event.summary} now"
    days = int(secs // 86400)
    if days >= 1:
        return f"{event.summary} in {days}d"
    hours = int(secs // 3600)
    minutes = int((secs % 3600) // 60)
    if hours >= 1:
        return f"{event.summary} in {hours}h {minutes}m"
    return f"{event.summary} in {minutes}m"


def _coerce_provider(value: Any) -> ColorProvider:
    if value is None:
        return _ConstantColor(DEFAULT_COLOR)
    if not hasattr(value, "color_for"):
        return _ConstantColor(value)
    return value


@attrs.define
class _NextEventWidget(FrameAwareBase):
    """The layout='next' feed story: one live countdown line, recomputed each
    draw (engine _hold_ticks redraws held widgets, so the countdown ticks)."""

    event: CalendarEvent | None = None
    empty_text: str = "No upcoming events"
    timezone: str | None = None
    font: Any = attrs.Factory(lambda: FONT_DEFAULT)
    font_color: ColorProvider = attrs.field(
        default=None, converter=_coerce_provider, kw_only=True
    )
    bg_color: Any = attrs.field(default=None, kw_only=True)
    border: Any | None = attrs.field(default=None, kw_only=True)
    center: bool = True
    padding: int = 6
    _baseline_y: int = attrs.field(init=False, default=-1)

    def draw(
        self,
        canvas: Canvas,
        cursor_pos: int = 0,
        *,
        y_offset: int = 0,
        font_color: Any = None,
    ) -> DrawResult:
        if font_color is not None and not hasattr(font_color, "color_for"):
            font_color = _ConstantColor(font_color)
        provider: ColorProvider = font_color or self.font_color

        tz = ZoneInfo(self.timezone) if self.timezone else None
        now = _dt.now(tz)
        text = format_relative(self.event, now, self.empty_text)

        content_width = get_text_width(self.font, text, padding=0, canvas=canvas)
        cursor_pos, end_padding = compute_cursor(
            canvas.width, content_width, cursor_pos, self.padding, center=self.center
        )
        if self._baseline_y < 0:
            self._baseline_y = compute_baseline(self.font, canvas, valign="center")
        baseline_y = self._baseline_y

        if self.border is not None:
            self.border.paint(canvas, self.frame_for("border"))

        if provider.per_char:
            cursor_pos += draw_text_per_char(
                canvas, self.font, cursor_pos, baseline_y + y_offset, text,
                lambda idx, total: provider.color_for(
                    self.frame_for("font_color"), idx, total
                ),
            )
        else:
            color = provider.color_for(self.frame_for("font_color"), 0, len(text))
            cursor_pos += draw_text(
                canvas, self.font, cursor_pos, baseline_y + y_offset, color, text
            )
        cursor_pos += end_padding
        return canvas, cursor_pos
```

This mirrors `clock.py`'s `draw()` structure exactly (constant-vs-per-char dispatch, border-before-text, baseline cache).

- [ ] **Step 4: Run — expect pass**

Run: `PYTHONPATH=tests/stubs .venv/bin/python -m pytest tests/test_widgets/test_calendar.py -k "relative or next_event" -q`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
PATH="$PWD/.venv/bin:$PATH" git add src/led_ticker/widgets/calendar.py tests/test_widgets/test_calendar.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "feat(calendar): live next-event countdown widget

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: `update()` + `start()` + `file://` fetch — build feed_stories per layout

**Files:**
- Modify: `src/led_ticker/widgets/calendar.py`
- Test: `tests/test_widgets/test_calendar.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_widgets/test_calendar.py`:

```python
import asyncio

from led_ticker.widgets.calendar import Calendar


def _make_calendar(**kwargs):
    # session unused for file:// fetch; pass None.
    defaults = dict(session=None, ics_url=f"file://{_FIXTURE}", timezone="UTC")
    defaults.update(kwargs)
    return Calendar(**defaults)


def test_update_agenda_builds_messages(monkeypatch):
    from led_ticker.widgets.calendar import TickerMessage
    cal = _make_calendar(layout="agenda", max_events=5)
    # Pin "now" so the fixture's events are in-window.
    monkeypatch.setattr(
        "led_ticker.widgets.calendar._now_in",
        lambda tz: datetime(2026, 6, 15, 0, 0, tzinfo=_UTC),
    )
    asyncio.run(cal.update())
    assert cal.feed_stories
    assert all(isinstance(s, TickerMessage) for s in cal.feed_stories)


def test_update_next_builds_single_countdown(monkeypatch):
    cal = _make_calendar(layout="next")
    monkeypatch.setattr(
        "led_ticker.widgets.calendar._now_in",
        lambda tz: datetime(2026, 6, 15, 0, 0, tzinfo=_UTC),
    )
    asyncio.run(cal.update())
    assert len(cal.feed_stories) == 1
    assert type(cal.feed_stories[0]).__name__ == "_NextEventWidget"


def test_update_empty_window_shows_empty_text(monkeypatch):
    from led_ticker.widgets.calendar import TickerMessage
    cal = _make_calendar(layout="agenda", empty_text="Nothing", lookahead_days=1)
    monkeypatch.setattr(
        "led_ticker.widgets.calendar._now_in",
        lambda tz: datetime(2030, 1, 1, 0, 0, tzinfo=_UTC),  # far future, nothing
    )
    asyncio.run(cal.update())
    assert len(cal.feed_stories) == 1
    assert isinstance(cal.feed_stories[0], TickerMessage)


def test_update_fetch_error_keeps_previous(monkeypatch):
    cal = _make_calendar(ics_url="file:///nonexistent/path.ics")
    sentinel = ["KEEP"]
    cal.feed_stories = sentinel
    asyncio.run(cal.update())  # must not raise
    assert cal.feed_stories is sentinel  # previous kept on error


def test_update_first_load_error_shows_empty_text():
    from led_ticker.widgets.calendar import TickerMessage
    cal = _make_calendar(ics_url="file:///nonexistent/path.ics", empty_text="Down")
    asyncio.run(cal.update())  # no previous data
    assert len(cal.feed_stories) == 1
    assert isinstance(cal.feed_stories[0], TickerMessage)
```

- [ ] **Step 2: Run — expect failure**

Run: `PYTHONPATH=tests/stubs .venv/bin/python -m pytest tests/test_widgets/test_calendar.py -k update -q`
Expected: FAIL — `AttributeError` (`Calendar` has no `update`) / `_now_in` missing.

- [ ] **Step 3: Implement fetch + update + start**

Add imports near the top of `src/led_ticker/widgets/calendar.py`:

```python
import asyncio
import logging
from pathlib import Path

from led_ticker.widget import run_monitor_loop, spawn_tracked

logger = logging.getLogger(__name__)
```

Add a tz-aware "now" helper (so tests can monkeypatch it) below the imports:

```python
def _now_in(tz: ZoneInfo | None) -> datetime:
    return _dt.now(tz)
```

Add these methods to the `Calendar` class body:

```python
    @classmethod
    async def start(
        cls,
        session: aiohttp.ClientSession,
        ics_url: str,
        update_interval: int = 900,
        **kwargs: Any,
    ) -> "Calendar":
        widget = cls(session=session, ics_url=ics_url, **kwargs)
        await widget.update()
        spawn_tracked(run_monitor_loop(widget, update_interval))
        return widget

    async def _fetch_ics(self) -> str:
        url = self.ics_url
        if url.startswith(("http://", "https://")):
            async with self.session.get(url) as resp:
                resp.raise_for_status()
                return await resp.text()
        # file:// or a bare local path — read from disk (offline calendars,
        # demos, tests). aiohttp does not handle file:// URLs.
        path = url[len("file://"):] if url.startswith("file://") else url
        return await asyncio.to_thread(Path(path).expanduser().read_text)

    def _empty_story(self) -> TickerMessage:
        return TickerMessage(
            self.empty_text, font=self.font,
            font_color=self.font_color, bg_color=self.bg_color,
        )

    async def update(self) -> None:
        logger.info("Updating calendar from: %s", self.ics_url)
        tz = ZoneInfo(self.timezone) if self.timezone else None
        try:
            text = await self._fetch_ics()
            now = _now_in(tz)
            parse_tz = tz if tz is not None else now.tzinfo  # local tz from now
            events = parse_ics(
                text, now=now, lookahead_days=self.lookahead_days, tz=parse_tz
            )
        except Exception:
            logger.exception("Calendar fetch/parse failed for %s", self.ics_url)
            if not self.feed_stories:
                self.feed_stories = [self._empty_story()]
            return

        kept = select_events(
            events, filter=self.filter, highlight=self.highlight,
            max_events=self.max_events,
        )
        self.feed_stories = self._build_stories(kept, now=now, tz=parse_tz)
        logger.info("Calendar %s updated: %d events", self.ics_url, len(kept))

    def _build_stories(
        self, events: list[CalendarEvent], *, now: datetime, tz: ZoneInfo
    ) -> list[Widget]:
        if self.layout == "next":
            event = events[0] if events else None
            color = (
                self.highlight_color
                if event is not None and _match_any(event.summary, self.highlight)
                else self.font_color
            )
            return [
                _NextEventWidget(
                    event=event, empty_text=self.empty_text, timezone=self.timezone,
                    font=self.font, font_color=color, bg_color=self.bg_color,
                    border=self.border, padding=self.padding,
                )
            ]
        # agenda
        if not events:
            return [self._empty_story()]
        stories: list[Widget] = []
        for e in events:
            color = (
                self.highlight_color
                if _match_any(e.summary, self.highlight)
                else self.font_color
            )
            stories.append(
                TickerMessage(
                    format_event_line(
                        e, now=now, time_format=self.time_format, tz=tz
                    ),
                    font=self.font, font_color=color, bg_color=self.bg_color,
                    border=self.border, padding=self.padding,
                )
            )
        return stories
```

Note on color defaults: `font_color`/`highlight_color` are passed straight to `TickerMessage` / `_NextEventWidget`, both of which coerce raw `[r,g,b]` or `None` to a provider. When `highlight_color` is `None` (unset) it falls back to the amber default in Task 7's coercion, so set the default there. To keep this task self-contained, also handle the `None` case here: if `self.highlight_color is None`, the highlighted color equals `self.font_color` is wrong — instead, in Task 7 we give `highlight_color` a real default of `[255, 200, 60]`. Until then, this task's tests do not exercise highlight color, so leave the pass-through as written.

- [ ] **Step 4: Run — expect pass**

Run: `PYTHONPATH=tests/stubs .venv/bin/python -m pytest tests/test_widgets/test_calendar.py -k update -q`
Expected: PASS (5 tests).

- [ ] **Step 5: Run the whole calendar test file**

Run: `PYTHONPATH=tests/stubs .venv/bin/python -m pytest tests/test_widgets/test_calendar.py -q`
Expected: PASS (all tests so far).

- [ ] **Step 6: Commit**

```bash
PATH="$PWD/.venv/bin:$PATH" git add src/led_ticker/widgets/calendar.py tests/test_widgets/test_calendar.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "feat(calendar): update()/start() build feed_stories; file:// + http fetch

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 7: Color defaults/coercion + `validate_config`

**Files:**
- Modify: `src/led_ticker/widgets/calendar.py`
- Test: `tests/test_widgets/test_calendar.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_widgets/test_calendar.py`:

```python
def test_highlight_color_defaults_to_amber():
    cal = _make_calendar(highlight=["pay"])
    # default amber [255, 200, 60] coerced to a provider
    c = cal.highlight_color.color_for(0, 0, 1)
    assert (c.red, c.green, c.blue) == (255, 200, 60)


def test_validate_requires_ics_url():
    msgs = Calendar.validate_config({"type": "calendar"})
    assert any("ics_url" in m for m in msgs)


def test_validate_rejects_bad_layout():
    msgs = Calendar.validate_config({"ics_url": "x", "layout": "grid"})
    assert any("layout" in m for m in msgs)


def test_validate_rejects_bad_timezone():
    msgs = Calendar.validate_config({"ics_url": "x", "timezone": "Mars/Phobos"})
    assert any("timezone" in m.lower() for m in msgs)


def test_validate_rejects_non_string_timezone():
    msgs = Calendar.validate_config({"ics_url": "x", "timezone": 123})
    assert any("timezone" in m.lower() for m in msgs)


def test_validate_rejects_non_list_filter():
    msgs = Calendar.validate_config({"ics_url": "x", "filter": "1:1"})
    assert any("filter" in m for m in msgs)


def test_validate_rejects_negative_max_events():
    msgs = Calendar.validate_config({"ics_url": "x", "max_events": -1})
    assert any("max_events" in m for m in msgs)


def test_validate_accepts_good_config():
    assert Calendar.validate_config(
        {"ics_url": "https://x/c.ics", "layout": "next",
         "timezone": "America/New_York", "filter": ["a"], "highlight": ["b"]}
    ) == []
```

- [ ] **Step 2: Run — expect failure**

Run: `PYTHONPATH=tests/stubs .venv/bin/python -m pytest tests/test_widgets/test_calendar.py -k "validate or amber" -q`
Expected: FAIL — `highlight_color` is `None` (no default); `validate_config` missing.

- [ ] **Step 3: Give the color fields converters + defaults**

In `src/led_ticker/widgets/calendar.py`, change the `Calendar` color fields to use `_coerce_provider` (defined in Task 5) with real defaults:

```python
    font_color: ColorProvider = attrs.field(
        default=None, converter=_coerce_provider, kw_only=True
    )
    highlight_color: ColorProvider = attrs.field(
        default=[255, 200, 60], converter=_coerce_provider, kw_only=True
    )
```

(`_coerce_provider(None)` → `_ConstantColor(DEFAULT_COLOR)`; `_coerce_provider([255,200,60])` → `_ConstantColor` of that amber.) Remove the now-stale `from led_ticker.colors import DEFAULT_COLOR` only if unused — it IS used by `_coerce_provider`, so keep it.

- [ ] **Step 4: Add `validate_config`**

Add the classmethod to the `Calendar` class (mirrors `clock.py`'s tz guards + the baseball list-of-str checks):

```python
    @classmethod
    def validate_config(cls, cfg: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        if not cfg.get("ics_url") or not isinstance(cfg.get("ics_url"), str):
            errors.append("ics_url is required and must be a non-empty string")
        layout = cfg.get("layout", "agenda")
        if layout not in ("agenda", "next"):
            errors.append(f"layout {layout!r} must be 'agenda' or 'next'")
        tz = cfg.get("timezone")
        if tz is not None:
            if not isinstance(tz, str):
                errors.append(
                    f"timezone must be a string IANA name, got {type(tz).__name__}"
                )
            else:
                try:
                    ZoneInfo(tz)
                except ZoneInfoNotFoundError, ValueError:
                    errors.append(
                        f"timezone {tz!r} is not a valid IANA timezone name"
                    )
        for key in ("filter", "highlight"):
            val = cfg.get(key)
            if val is not None and (
                not isinstance(val, list) or not all(isinstance(x, str) for x in val)
            ):
                errors.append(f"{key} must be a list of strings")
        for key in ("max_events", "lookahead_days"):
            val = cfg.get(key)
            if val is not None and (not isinstance(val, int) or val < 0):
                errors.append(f"{key} must be a non-negative integer")
        return errors
```

Add the import at the top if not already present:

```python
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
```

(Replace the earlier `from zoneinfo import ZoneInfo` with this combined import.)

- [ ] **Step 5: Run — expect pass**

Run: `PYTHONPATH=tests/stubs .venv/bin/python -m pytest tests/test_widgets/test_calendar.py -k "validate or amber" -q`
Expected: PASS (8 tests).

- [ ] **Step 6: Lint + full calendar file**

Run: `.venv/bin/ruff check src/led_ticker/widgets/calendar.py tests/test_widgets/test_calendar.py && .venv/bin/ruff format src/led_ticker/widgets/calendar.py && PYTHONPATH=tests/stubs .venv/bin/python -m pytest tests/test_widgets/test_calendar.py -q`
Expected: ruff clean; all calendar tests PASS.

- [ ] **Step 7: Commit**

```bash
PATH="$PWD/.venv/bin:$PATH" git add src/led_ticker/widgets/calendar.py tests/test_widgets/test_calendar.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "feat(calendar): highlight_color default + validate_config

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 8: Factory FIELD_HINTS (`--list-fields calendar`)

**Files:**
- Modify: `src/led_ticker/app/factories.py`
- Test: `tests/test_widgets/test_calendar.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_widgets/test_calendar.py`:

```python
def test_list_fields_calendar_shows_key_fields():
    from led_ticker.app.factories import _list_widget_fields

    out = _list_widget_fields("calendar")
    for field in ("ics_url", "layout", "filter", "highlight", "time_format"):
        assert field in out
```

- [ ] **Step 2: Run — expect failure**

Run: `PYTHONPATH=tests/stubs .venv/bin/python -m pytest tests/test_widgets/test_calendar.py -k list_fields -q`
Expected: FAIL — calendar-specific hints missing.

- [ ] **Step 3: Add the hints**

In `src/led_ticker/app/factories.py`, find the global `FIELD_HINTS` dict (where the clock's `format`/`timezone` hints live — search for `# --- Clock ---`). Add a calendar block with any keys not already present (the GLOBAL dict is name-keyed; `timezone`/`font_color`/`border`/`padding`/`bg_color`/`font` already exist — only add the new keys):

```python
    # --- Calendar ---
    "ics_url": FieldHint("str", "Public .ics feed URL (or file:// path)."),
    "layout": FieldHint("str", "'agenda' (rotating events) or 'next' (countdown)."),
    "max_events": FieldHint("int", "Max agenda events to show (default 5)."),
    "lookahead_days": FieldHint("int", "Days ahead to scan for events (default 7)."),
    "time_format": FieldHint("str", "'12h' or '24h' for the event time."),
    "empty_text": FieldHint("str", "Shown when no upcoming events."),
    "filter": FieldHint("list[str]", "Keep only events whose summary matches a keyword."),
    "highlight": FieldHint("list[str]", "Recolor + always-include matching events."),
    "highlight_color": FieldHint("[r,g,b]|provider", "Color for highlighted events."),
```

Match the exact `FieldHint(...)` constructor signature already used in that dict (check whether it is `FieldHint(type, description)` positional or keyword and follow it). If `update_interval` is not already a global hint and you want it listed, add `"update_interval": FieldHint("int", "Seconds between feed refreshes (default 900).")`.

- [ ] **Step 4: Run — expect pass**

Run: `PYTHONPATH=tests/stubs .venv/bin/python -m pytest tests/test_widgets/test_calendar.py -k list_fields -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
PATH="$PWD/.venv/bin:$PATH" git add src/led_ticker/app/factories.py tests/test_widgets/test_calendar.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "feat(calendar): --list-fields hints

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 9: End-to-end build through the factory + registry/border drift tests

**Files:**
- Test: `tests/test_widgets/test_calendar.py`, `tests/test_widgets/test_registry.py`, `tests/test_border_surface_drift.py`

- [ ] **Step 1: Write the failing end-to-end build test**

Add to `tests/test_widgets/test_calendar.py` (proves the widget builds through the real factory path, like a config would, via `start()` with a `file://` URL — no network):

```python
def test_calendar_builds_through_factory(monkeypatch):
    from led_ticker.app.factories import validate_widget_cfg
    monkeypatch.setattr(
        "led_ticker.widgets.calendar._now_in",
        lambda tz: datetime(2026, 6, 15, 0, 0, tzinfo=_UTC),
    )
    cfg = {
        "type": "calendar",
        "ics_url": f"file://{_FIXTURE}",
        "layout": "agenda",
        "timezone": "UTC",
        "highlight": ["1:1"],
    }
    # validate_widget_cfg must not raise for a good config
    asyncio.run(validate_widget_cfg(dict(cfg), session=None))
```

- [ ] **Step 2: Run — expect pass or failure**

Run: `PYTHONPATH=tests/stubs .venv/bin/python -m pytest tests/test_widgets/test_calendar.py -k builds_through_factory -q`
Expected: PASS (validation path already wired via `validate_config`). If it FAILS, fix the cause before continuing (e.g. an unexpected required-field interaction).

- [ ] **Step 3: Update the registry count test**

In `tests/test_widgets/test_registry.py`, find the assertion on the number of registered core widgets (it was bumped to 8 when the clock landed). Increment it to 9 and add `"calendar"` to any expected-names set/list in that test.

- [ ] **Step 4: Add calendar to border-surface drift (only if the fact-pack advertises border — it does)**

In `tests/test_border_surface_drift.py`, add `"calendar"` to the `FACT_PACK_FILES` tuple (so the test expects `docs/content-source/widgets/calendar.md` to carry a `border` row). The fact-pack is created in Task 10 with that row.

- [ ] **Step 5: Run the three test files**

Run: `PYTHONPATH=tests/stubs .venv/bin/python -m pytest tests/test_widgets/test_calendar.py tests/test_widgets/test_registry.py -q`
Expected: calendar + registry PASS. (Border-drift will fail until Task 10 creates the fact-pack — that's expected; run it in Task 10.)

- [ ] **Step 6: Commit**

```bash
PATH="$PWD/.venv/bin:$PATH" git add tests/test_widgets/test_calendar.py tests/test_widgets/test_registry.py tests/test_border_surface_drift.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "test(calendar): factory build + registry count + border-drift entry

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 10: Docs — user page, fact-pack, index, nav + demo gif

**Files:**
- Create: `docs/site/src/content/docs/widgets/calendar.mdx`
- Create: `docs/content-source/widgets/calendar.md`
- Create: `docs/site/demos/widget-calendar.toml`, `tests/fixtures/calendar_sample.ics` (already exists), `docs/site/public/demos/widget-calendar.gif`
- Modify: `docs/site/src/content/docs/widgets/index.mdx`, `docs/site/astro.config.mjs`

- [ ] **Step 1: Create the demo TOML (uses a committed sample .ics via file://; chain_length, NOT chain)**

Create `docs/site/demos/widget-calendar.toml`. Copy `tests/fixtures/calendar_sample.ics` to `docs/site/demos/calendar_sample.ics` first (the renderer runs from the repo root; use a repo-relative `file://` path). Then:

```toml
# Demo: calendar widget (agenda layout) reading a committed sample .ics offline.
# render-duration: 6
[display]
rows = 16
cols = 32
chain_length = 5
default_scale = 1
brightness = 60

[transitions]
default = "cut"

[[playlist.section]]
mode = "swap"
loop_count = 1
hold_time = 3.0

[[playlist.section.widget]]
type = "calendar"
ics_url = "file://docs/site/demos/calendar_sample.ics"
layout = "agenda"
timezone = "UTC"
highlight = ["1:1"]
font_color = "rainbow"
```

NOTE: the fixture's events are dated June 2026; if the render date is past them the agenda is empty. To keep the demo evergreen, the plan's implementer should regenerate `docs/site/demos/calendar_sample.ics` with DTSTART dates a few days in the future relative to render time, OR add an `RRULE:FREQ=DAILY` to each event so an occurrence always lands in-window. Use the RRULE approach (deterministic, no date maintenance): give each VEVENT a `RRULE:FREQ=DAILY` so there is always an upcoming occurrence.

- [ ] **Step 2: Render the gif and verify width + content**

Run: `.venv/bin/python tools/render_demo/render.py docs/site/demos/widget-calendar.toml -o docs/site/public/demos/widget-calendar.gif --duration 6`
Then verify: `.venv/bin/python -c "from PIL import Image; im=Image.open('docs/site/public/demos/widget-calendar.gif'); print(im.size)"`
Expected: `(640, 64)` (160 logical × 4 upscale — i.e. `chain_length` applied). View the gif (Read tool) and confirm an event line renders (e.g. "Today 3:00 PM Standup").

- [ ] **Step 3: Create the user docs page**

Create `docs/site/src/content/docs/widgets/calendar.mdx` modeled on `clock.mdx` and `rss_feed.mdx`: frontmatter `title`/`description`; imports for `DemoGif`, `TomlExample`, `OptionsTable`, `RelatedPages`, `Aside`; an intro paragraph; the `<DemoGif src="/demos/widget-calendar.gif" .../>`; a minimal `<TomlExample>` (`type = "calendar"` + `ics_url`); `## Options` `<OptionsTable source="widgets/calendar" />`; `## Layouts` (agenda vs next); `## Filter & highlight` (with a `<TomlExample>` for `filter`/`highlight`/`highlight_color`); `## Timezone & format`; `## Getting your .ics URL` (Google Calendar → Settings → "Secret address in iCal format"; iCloud public calendar link; an `<Aside type="caution">` that the secret URL is a credential — don't commit it); `## file:// / local feeds` (sync an .ics to the Pi and point at `file:///home/pi/cal.ics`); `<RelatedPages slugs={["widgets/clock","widgets/rss_feed","concepts/color-providers","concepts/borders"]} />`. Run prettier after (Step 7).

- [ ] **Step 4: Create the fact-pack**

Create `docs/content-source/widgets/calendar.md` modeled on an existing fact-pack (e.g. `docs/content-source/widgets/clock.md`). Include a fields table with every config knob and a `border` row (required by the border-drift test). Keep it terse and accurate.

- [ ] **Step 5: Update the widgets index + nav**

In `docs/site/src/content/docs/widgets/index.mdx`: bump the widget count (it reads "8" after the clock) to "9" and add a `calendar` row to the table. In `docs/site/astro.config.mjs`: add the `widgets/calendar` entry to the sidebar nav in the same place the clock entry sits (alphabetical with the other widgets).

- [ ] **Step 6: Run the border-drift + docs drift tests**

Run: `PYTHONPATH=tests/stubs .venv/bin/python -m pytest tests/test_border_surface_drift.py tests/test_demo_config_keys.py -q`
Expected: PASS (fact-pack now has the border row; demo TOML uses `chain_length`). If a `test_docs_config_options_drift.py` exists and audits per-widget fields, run it too and reconcile any field-list expectations.

- [ ] **Step 7: docs-lint**

Run: `PATH="$PWD/.venv/bin:$PATH" make docs-lint`
If prettier flags `calendar.mdx`, run `cd docs/site && pnpm exec prettier --write src/content/docs/widgets/calendar.mdx` and re-run. Expected: 0 errors.

- [ ] **Step 8: Commit**

```bash
PATH="$PWD/.venv/bin:$PATH" git add docs/ tests/test_border_surface_drift.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "docs(calendar): widget page, fact-pack, index, nav, demo gif

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 11: Full suite, lint, and final verification

**Files:** none (verification only)

- [ ] **Step 1: Run the full test suite**

Run: `PATH="$PWD/.venv/bin:$PATH" PYTHONPATH=tests/stubs .venv/bin/python -m pytest -q`
Expected: all pass (prior baseline was ~2613 + the new calendar tests). The 3 plugin-CLI subprocess tests pass only with the CLI on PATH (already set above).

- [ ] **Step 2: Ruff (the CI lint)**

Run: `.venv/bin/ruff check src/ tests/`
Expected: All checks passed.

- [ ] **Step 3: Pyright**

Run: `PATH="$PWD/.venv/bin:$PATH" make typecheck` (or the project's pyright invocation).
Expected: 0 errors. Fix any types (e.g. the `session: aiohttp.ClientSession` field is typed but tests pass `None` — that is test-only and fine at runtime; if pyright complains in the widget, it will be about real usage, not the tests).

- [ ] **Step 4: Validate an example config end-to-end**

Create a scratch `/tmp/cal.toml` with a `type = "calendar"` section pointing at `file://$PWD/tests/fixtures/calendar_sample.ics`, then run `.venv/bin/led-ticker validate /tmp/cal.toml`. Expected: `No issues found.` Delete the scratch file.

- [ ] **Step 5: Push and open the PR**

```bash
PATH="$PWD/.venv/bin:$PATH" git push -u origin feat/calendar-widget
gh pr create --title "feat: calendar widget (steal #3, part 2)" --body "<summary of the spec + deps note: icalendar + recurring-ical-events become core pinned deps; file:// support; filter/highlight mirror baseball promotions>

🤖 Generated with [Claude Code](https://claude.com/claude-code)"
```

---

## Self-Review

**Spec coverage:** always-Container + layout (Tasks 1,6); parse_ics recurrence/all-day/tz (Task 2); _match_any + filter/highlight cap (Task 3); agenda formatting (Task 4); next-event countdown (Task 5); update/start/fetch incl. file:// + error isolation + empty/first-load (Task 6); color defaults + validate_config (Task 7); FIELD_HINTS (Task 8); factory build + registry/border drift (Task 9); docs + demo gif (Task 10); deps in pyproject (Task 1); full verification (Task 11). All spec sections map to a task.

**Deferred-to-implementer specifics (acceptable, each with a concrete recommendation):** the exact `FieldHint(...)` constructor signature (Task 8 — match the existing dict); the evergreen-fixture approach for the demo (Task 10 — use `RRULE:FREQ=DAILY` so an occurrence is always in-window); the `_list_widget_fields` / `validate_widget_cfg` exact names (verified present in `factories.py`).

**Type consistency:** `parse_ics(text, *, now, lookahead_days, tz)`, `select_events(events, *, filter, highlight, max_events)`, `format_event_line(event, *, now, time_format, tz)`, `format_relative(event, now, empty_text)`, `_match_any(summary, keywords)`, `_now_in(tz)`, `CalendarEvent(summary, start, all_day)`, `_NextEventWidget(event, empty_text, timezone, font, font_color, bg_color, border, center, padding)`, `Calendar.start(session, ics_url, update_interval, **kwargs)` — names used identically across tasks and tests.

**PEP 758 note:** the `except ZoneInfoNotFoundError, ValueError:` form in Task 7 is intentional (valid on Python 3.14, catches both) — it matches the clock's committed style; ruff accepts it.
