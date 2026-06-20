"""Time-of-day brightness scheduling (pure logic).

A Scheduler resolves the panel brightness for a given local datetime from a list
of brightness windows. No hardware or asyncio dependency — the run loop calls
brightness_for() and assigns the result to matrix.brightness.
"""

import logging
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


def _window_active(w: _Window, minutes: int, weekday: int) -> bool:
    """True if window `w` is active at `minutes` (since midnight) on `weekday`.
    Same-day: start<=t<end. Wrap (start>end): pre-midnight part (t>=start) owned
    by today; post-midnight tail (t<end) owned by yesterday (weekday-1)%7."""
    if w.start < w.end:
        return w.start <= minutes < w.end and _day_ok(w.days, weekday)
    if minutes >= w.start:
        return _day_ok(w.days, weekday)
    if minutes < w.end:
        return _day_ok(w.days, (weekday - 1) % 7)
    return False


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
            out.append(_Window(start, end, int(w.brightness), days))
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
        indexed_windows.append((orig_idx, _Window(start, end, int(w.brightness), days)))

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
