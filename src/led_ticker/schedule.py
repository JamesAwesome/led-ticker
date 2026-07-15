"""Time-of-day brightness scheduling (pure logic).

A Scheduler resolves the panel brightness for a given local datetime from a list
of brightness windows. No hardware or asyncio dependency — the run loop calls
brightness_for() and assigns the result to matrix.brightness.
"""

import logging
import re
import weakref
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import attrs

_DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")  # index == datetime.weekday()
_HHMM = re.compile(r"^([0-9]{2}):([0-9]{2})$")


def to_minutes(hhmm: object) -> int | None:
    """Minutes since midnight for a zero-padded 'HH:MM' (0–23/0–59), else None.

    Accepts any input (raw TOML values reach this); non-str returns None."""
    if not isinstance(hhmm, str):
        return None
    m = _HHMM.match(hhmm)
    if not m:
        return None
    hh, mm = int(m.group(1)), int(m.group(2))
    if hh > 23 or mm > 59:
        return None
    return hh * 60 + mm


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


@attrs.define(frozen=True)
class Scheduler:
    windows: tuple[_Window, ...]

    @classmethod
    def from_config(cls, cfg) -> Scheduler:
        out: list[_Window] = []
        for w in cfg.windows:
            start = to_minutes(w.start)
            end = to_minutes(w.end)
            if start is None or end is None:
                logging.warning(
                    "schedule: skipping window with unparseable time(s) "
                    "start=%r end=%r (run `led-ticker validate` to see details)",
                    w.start,
                    w.end,
                )
                continue  # malformed → skipped here; validate.py reports it
            raw_days = w.days or []
            days = frozenset(_DAYS.index(d) for d in raw_days if d in _DAYS)
            if raw_days and not days:
                logging.warning(
                    "schedule: skipping window with no valid day names "
                    "start=%r end=%r days=%r"
                    " (run `led-ticker validate` to see details)",
                    w.start,
                    w.end,
                    list(raw_days),
                )
                continue
            out.append(
                _Window(start=start, end=end, days=days, brightness=int(w.brightness))
            )
        return cls(windows=tuple(out))

    def _active_index(self, minutes: int, weekday: int) -> int | None:
        """Index of the last matching window (last-wins), or None."""
        winner: int | None = None
        for i, w in enumerate(self.windows):
            if _window_active(w, minutes, weekday):
                winner = i
        return winner

    def brightness_for(self, now: datetime, base: int) -> int:
        idx = self._active_index(now.hour * 60 + now.minute, now.weekday())
        return base if idx is None else self.windows[idx].brightness


def unreachable_window_indices(cfg) -> list[int]:
    """Indices of windows (in cfg.windows) that can never be the effective window
    (fully shadowed by later same-coverage windows). Uses ORIGINAL config indices
    so the reported index matches `display.schedule.windows[i]` in the TOML,
    even when earlier windows were skipped for malformed times.

    Computed by sampling every minute of a full week (10080 samples; trivial)
    and noting which windows never win."""
    # Build (original_index, _Window) pairs, skipping malformed times
    # without renumbering.
    indexed_windows: list[tuple[int, _Window]] = []
    for orig_idx, w in enumerate(cfg.windows):
        start = to_minutes(w.start)
        end = to_minutes(w.end)
        if start is None or end is None:
            continue  # malformed time — skip without renumbering
        raw_days = w.days or []
        days = frozenset(_DAYS.index(d) for d in raw_days if d in _DAYS)
        if raw_days and not days:
            continue  # all-invalid days — skip without renumbering
        indexed_windows.append(
            (
                orig_idx,
                _Window(start=start, end=end, days=days, brightness=int(w.brightness)),
            )
        )

    if not indexed_windows:
        return []

    has_active: set[int] = set()  # original indices that are active at some minute
    winners: set[int] = set()  # original indices that ever win (last-wins)

    for weekday in range(7):
        for minutes in range(1440):
            winner_orig: int | None = None
            for orig_idx, w in indexed_windows:
                if _window_active(w, minutes, weekday):
                    has_active.add(orig_idx)
                    winner_orig = orig_idx
            if winner_orig is not None:
                winners.add(winner_orig)

    return sorted(orig_idx for orig_idx in has_active if orig_idx not in winners)


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
        _s = to_minutes(w.start)
        _e = to_minutes(w.end)
        if _s is None or _e is None:
            # Invalid time — mark clearly instead of rendering as a normal row
            days_label = (
                _days_label(w.days) if isinstance(w.days, list) else str(w.days)
            )
            lines.append(f"  {days_label:<11} {w.start}–{w.end} (invalid — see errors)")
            continue
        wrap = " (overnight)" if _s > _e else ""
        dark = "  (dark)" if int(w.brightness) == 0 else ""
        lines.append(
            f"  {_days_label(w.days):<11} {w.start}–{w.end}{wrap} "
            f"→ {int(w.brightness)}%{dark}"
        )
    lines.append(f"  otherwise → {base}% (base)")
    return lines


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
        logging.warning("schedule: invalid timezone %r; using system local time", name)
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


# Widget -> VisibilitySchedule bindings. Keyed by id() because widgets are
# slotted @attrs.define classes: no attribute injection possible, and
# eq=True makes them unhashable (no WeakKeyDictionary). Values hold a
# weakref so hot-reload-evicted widgets don't accumulate; the weakref
# callback removes the entry before the id can be reused.
_BINDINGS: dict[int, tuple[Any, VisibilitySchedule]] = {}


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


def schedule_for(widget: Any) -> VisibilitySchedule | None:
    """The widget's bound visibility schedule, or None (= always shown)."""
    entry = _BINDINGS.get(id(widget))
    if entry is None:
        return None
    ref, sched = entry
    if ref() is not widget:  # stale entry / id reuse — treat as unbound
        return None
    return sched
