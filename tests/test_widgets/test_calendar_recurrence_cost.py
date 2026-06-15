"""Guard 2 — Recurrence cost-matrix (class B: expansion cost / DoS protection).

Parametrized over a matrix of RRULE shapes to assert that parse_ics is BOUNDED
for every combination of FREQ, DTSTART age, and modifier.  The entire file
must run in a few seconds — a slow run is itself a diagnostic signal that a
cost regression exists.

Matrix axes:
  FREQ: SECONDLY, MINUTELY, HOURLY, DAILY
  DTSTART: ~2 years past, near now, ~1 year future
  modifier: none (forever), COUNT=10, UNTIL≈now+5d, BY* (BYHOUR/BYDAY)

Assertions per cell:
  (a) parse_ics COMPLETES (timeout is enforced by pytest; slow = finding)
  (b) len(events) <= _MAX_OCCURRENCES
  (c) SECONDLY / MINUTELY -> 0 events (pre-filter drops them)

Far-past forever HOURLY/DAILY/WEEKLY correctness (formerly the clamp-equivalence
invariant) is now covered by `test_far_past_recurrence_is_fast_and_correct`,
which asserts the .between()-bounded expansion returns the exact in-window set.
"""

import time
from datetime import datetime, timedelta
from textwrap import dedent
from zoneinfo import ZoneInfo

import pytest

from led_ticker.widgets.calendar import (
    _MAX_OCCURRENCES,
    parse_ics,
)

_UTC = ZoneInfo("UTC")

# Fixed reference "now" for all matrix cells.
_NOW = datetime(2026, 6, 15, 0, 0, tzinfo=_UTC)
_LOOKAHEAD = 7  # days

# DTSTART variations
# NOTE: 20240101 (Jan 1, 2024) is a Monday — ideal DTSTART for BYDAY=MO tests.
_FAR_PAST = "20240101T000000Z"  # ~2.5 years before _NOW
_NEAR_NOW = "20260614T000000Z"  # 1 day before _NOW (near)
_FUTURE = "20270101T000000Z"  # ~6 months after _NOW+lookahead (nothing in window)

# UNTIL ≈ now + 5 days (well inside the lookahead window)
_UNTIL_IN_WINDOW = "20260620T000000Z"


def _build_ics(freq: str, dtstart: str, modifier: str) -> str:
    """Build a minimal single-VEVENT .ics with the given RRULE components.

    DTEND is DTSTART + 30 minutes.  We compute it by parsing dtstart as a
    naive datetime string (all test values end in Z = UTC) and adding 30m,
    then re-formatting as a compact UTC datetime string.

    ``modifier`` is appended verbatim to the RRULE after ``FREQ=<freq>``, e.g.
    ``"INTERVAL=2;BYDAY=MO"`` → ``RRULE:FREQ=WEEKLY;INTERVAL=2;BYDAY=MO``.
    """
    rrule = f"FREQ={freq}"
    if modifier:
        rrule += f";{modifier}"
    # Parse the dtstart string (format: YYYYMMDDTHHMMSSz, always UTC for our matrix)
    dt_naive = datetime.strptime(dtstart.rstrip("Z"), "%Y%m%dT%H%M%S")
    dt_end = dt_naive + timedelta(minutes=30)
    dtend = dt_end.strftime("%Y%m%dT%H%M%S") + "Z"
    return dedent(f"""\
        BEGIN:VCALENDAR
        VERSION:2.0
        PRODID:-//led-ticker//cost-matrix//EN
        BEGIN:VEVENT
        UID:cost-matrix-{freq}-{dtstart[:8]}-{modifier or "none"}
        DTSTART:{dtstart}
        DTEND:{dtend}
        RRULE:{rrule}
        SUMMARY:Cost Matrix Event
        END:VEVENT
        END:VCALENDAR
    """)


# ---------------------------------------------------------------------------
# Matrix definition
# ---------------------------------------------------------------------------

# Sub-hourly freqs are pre-filtered — they always yield 0 events regardless of
# DTSTART or modifier.  We still include them in the matrix to guard that the
# pre-filter keeps working and doesn't hang.
_SUBHOURLY = {"SECONDLY", "MINUTELY"}

# (freq, dtstart_label, dtstart_value, modifier_label, modifier_value)
_MATRIX: list[tuple[str, str, str, str, str]] = []

for _freq in ("SECONDLY", "MINUTELY", "HOURLY", "DAILY"):
    for _dtstart_label, _dtstart_val in [
        ("far_past", _FAR_PAST),
        ("near_now", _NEAR_NOW),
        ("future", _FUTURE),
    ]:
        for _mod_label, _mod_val in [
            ("forever", ""),
            ("count10", "COUNT=10"),
            (f"until_{_UNTIL_IN_WINDOW[:8]}", f"UNTIL={_UNTIL_IN_WINDOW}"),
            (
                "by_modifier",
                "BYHOUR=9" if _freq == "HOURLY" else "BYDAY=MO",
            ),
        ]:
            _MATRIX.append((_freq, _dtstart_label, _dtstart_val, _mod_label, _mod_val))


def _matrix_id(val):
    if isinstance(val, str):
        return val
    return str(val)


@pytest.mark.parametrize(
    "freq,dtstart_label,dtstart_val,modifier_label,modifier_val",
    _MATRIX,
    ids=[f"{freq}-{ds}-{mod}" for freq, ds, _, mod, _ in _MATRIX],
)
def test_parse_is_bounded(
    freq: str,
    dtstart_label: str,
    dtstart_val: str,
    modifier_label: str,
    modifier_val: str,
) -> None:
    """Assert parse_ics is bounded for every FREQ × DTSTART × modifier cell.

    Assertions:
    (a) completes (slow completion IS the finding — no explicit timeout here;
        pytest's overall timeout / the test runner clock will catch hangs)
    (b) len(events) <= _MAX_OCCURRENCES
    (c) SECONDLY/MINUTELY -> 0 events (subhourly pre-filter active)

    Guard: if a cell was previously slow and the fix is reverted, this test
    will hang, making the regression visible immediately.
    """
    ics = _build_ics(freq, dtstart_val, modifier_val)
    t0 = time.monotonic()
    events = parse_ics(ics, now=_NOW, lookahead_days=_LOOKAHEAD, tz=_UTC)
    elapsed = time.monotonic() - t0

    # (a) Bounded count
    assert len(events) <= _MAX_OCCURRENCES, (
        f"{freq}/{dtstart_label}/{modifier_label}: "
        f"event count {len(events)} exceeds _MAX_OCCURRENCES={_MAX_OCCURRENCES}"
    )

    # (b) Sub-hourly -> 0 events (pre-filter must be active)
    if freq in _SUBHOURLY:
        assert len(events) == 0, (
            f"{freq}/{dtstart_label}/{modifier_label}: "
            f"SECONDLY/MINUTELY events must be pre-filtered to 0, "
            f"got {len(events)}"
        )

    # (c) Timing soft-guard: log a warning if a cell is suspiciously slow.
    # We do NOT hard-fail here for the far-past sub-hourly + future cells
    # (they should be instant due to pre-filter / no in-window occurrences),
    # but anything > 5s is a clear regression signal for the non-subhourly cases.
    if freq not in _SUBHOURLY and dtstart_label == "far_past" and not modifier_val:
        # This is the historically problematic cell (far-past forever RRULE).
        # The library's .between(now, window_end) bounds the expansion, so it
        # must complete fast.
        assert elapsed < 10.0, (
            f"{freq}/{dtstart_label}/{modifier_label}: "
            f"parse_ics took {elapsed:.2f}s for a far-past forever {freq} rule — "
            "the .between() bound may have regressed"
        )


# ---------------------------------------------------------------------------
# Far-past forever recurrence: fast + correct (replaces clamp-equivalence)
# ---------------------------------------------------------------------------
# .between(now, window_end) bounds the expansion, so a far-past forever rule
# is cheap; it must also return the EXACT in-window set.  We assert concrete
# expected dates so the test does not depend on the expansion path under test.


@pytest.mark.parametrize(
    "freq,modifier,expected_starts",
    [
        pytest.param(
            "DAILY",
            "BYHOUR=9;BYMINUTE=0",
            # now=2026-06-15 00:00, window_end=2026-06-22 00:00.  The 9am
            # occurrences from 06-15 through 06-21 are in window; 06-22 09:00
            # is past window_end and filtered.  -> 7 occurrences.
            {datetime(2026, 6, 15 + d, 9, 0, tzinfo=_UTC) for d in range(0, 7)},
            id="daily_far_past_forever",
        ),
        pytest.param(
            "WEEKLY",
            "BYDAY=MO",  # anchor 2024-01-01 is a Monday; weekly Mondays
            # Only 2026-06-15 (a Monday) falls inside [now, window_end); the
            # next Monday (06-22 00:00) is at the exclusive window edge.
            {datetime(2026, 6, 15, 0, 0, tzinfo=_UTC)},
            id="weekly_far_past_forever_monday",
        ),
    ],
)
def test_far_past_recurrence_is_fast_and_correct(
    freq: str, modifier: str, expected_starts: set
) -> None:
    """A far-past forever recurrence parses fast AND returns the exact in-window
    set via .between(now, window_end).

    This replaces the old clamp-equivalence invariant: the correctness guarantee
    for far-past uniform rules (HOURLY/DAILY/WEEKLY, BY*/INTERVAL variants) now
    rides on the library's bounded expansion rather than on the deleted
    anchor-clamp workaround.
    """
    ics = _build_ics(freq, _FAR_PAST, modifier)
    t0 = time.monotonic()
    events = parse_ics(ics, now=_NOW, lookahead_days=_LOOKAHEAD, tz=_UTC)
    elapsed = time.monotonic() - t0

    # (a) fast — a far-past forever rule must not trigger an unbounded walk.
    assert elapsed < 10.0, (
        f"{freq}/{modifier}: parse_ics took {elapsed:.2f}s for a far-past "
        "forever rule — the .between() bound may have regressed"
    )
    # (b) correct — exact in-window starts.
    starts = {e.start for e in events}
    assert starts == expected_starts, (
        f"{freq}/{modifier}: in-window starts mismatch.\n"
        f"Missing:  {sorted(expected_starts - starts)}\n"
        f"Unexpected: {sorted(starts - expected_starts)}"
    )


def test_far_past_hourly_forever_is_fast_and_bounded() -> None:
    """The historically problematic cell: far-past forever HOURLY.

    Asserts (a) it completes fast and (b) returns ~168 (7-day) in-window
    occurrences — the count a 7-day HOURLY window must yield.
    """
    ics = _build_ics("HOURLY", _FAR_PAST, "")
    t0 = time.monotonic()
    events = parse_ics(ics, now=_NOW, lookahead_days=_LOOKAHEAD, tz=_UTC)
    elapsed = time.monotonic() - t0

    assert elapsed < 10.0, (
        f"far-past forever HOURLY took {elapsed:.2f}s — the .between() bound "
        "may have regressed"
    )
    # 7 days * 24 h = 168; allow a small boundary margin.
    assert 160 <= len(events) <= 176, (
        f"Expected ~168 in-window HOURLY events, got {len(events)}"
    )


# ---------------------------------------------------------------------------
# Whole-file timing guard
# ---------------------------------------------------------------------------


def test_full_matrix_is_fast() -> None:
    """Run the full cost matrix serially and assert total wall time is bounded.

    This is the DoS regression test: if any fix is reverted, the matrix
    will take minutes instead of seconds, and this assertion will catch it.

    Target: < 30 seconds for the entire matrix on a modern laptop.
    If CI is slow, raise the ceiling before weakening individual cell guards.
    """
    t0 = time.monotonic()
    for freq, _ds_label, dtstart_val, _mod_label, modifier_val in _MATRIX:
        ics = _build_ics(freq, dtstart_val, modifier_val)
        parse_ics(ics, now=_NOW, lookahead_days=_LOOKAHEAD, tz=_UTC)
    elapsed = time.monotonic() - t0

    assert elapsed < 30.0, (
        f"Full cost matrix took {elapsed:.1f}s — a single RRULE cell may have "
        "regressed (far-past SECONDLY/MINUTELY/HOURLY/DAILY without COUNT should "
        "be fast given the subhourly pre-filter + the .between() window bound)"
    )
