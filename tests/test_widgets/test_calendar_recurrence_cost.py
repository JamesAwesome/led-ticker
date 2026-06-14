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
  (d) for far-past uniform HOURLY/DAILY without COUNT/BY* modifiers:
      in-window result equals an unclamped reference expansion
      (clamp-equivalence invariant)
"""

import time
from datetime import datetime, timedelta
from textwrap import dedent
from zoneinfo import ZoneInfo

import pytest

from led_ticker.widgets import calendar as _cal_mod
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
        # After Fix A (window break) + Fix 3 (clamp), it must complete fast.
        assert elapsed < 10.0, (
            f"{freq}/{dtstart_label}/{modifier_label}: "
            f"parse_ics took {elapsed:.2f}s for a far-past forever {freq} rule — "
            "window-break or clamp optimization may have regressed"
        )


# ---------------------------------------------------------------------------
# Clamp-equivalence invariant
# ---------------------------------------------------------------------------
# For far-past uniform HOURLY/DAILY without COUNT/BY*, the events returned
# by the clamped parse must exactly match those from an unclamped parse.
# This is the correctness proof for _clamp_recurrence_anchors.

_CLAMP_EQUIV_CASES = [
    # -----------------------------------------------------------------------
    # INTERVAL=1 (original cases — baseline correctness)
    # -----------------------------------------------------------------------
    pytest.param("HOURLY", _FAR_PAST, "", id="hourly_far_past_forever"),
    pytest.param("DAILY", _FAR_PAST, "", id="daily_far_past_forever"),
    pytest.param(
        "HOURLY",
        _FAR_PAST,
        f"UNTIL={_UNTIL_IN_WINDOW}",
        id="hourly_far_past_until",
    ),
    pytest.param(
        "DAILY",
        _FAR_PAST,
        f"UNTIL={_UNTIL_IN_WINDOW}",
        id="daily_far_past_until",
    ),
    # Round-11 Fix 2: BY* safe-subset shapes — these are NOW clamped.
    # The equivalence invariant must hold: clamped == unclamped in-window events.
    # If any of these fail, that shape must be REMOVED from the safe subset.
    pytest.param("HOURLY", _FAR_PAST, "BYMINUTE=0", id="hourly_far_past_byminute"),
    pytest.param("DAILY", _FAR_PAST, "BYHOUR=9", id="daily_far_past_byhour"),
    pytest.param("WEEKLY", _FAR_PAST, "BYDAY=MO", id="weekly_far_past_byday"),
    # -----------------------------------------------------------------------
    # INTERVAL > 1 — no-BY* (uniform) branch: regression guard
    # -----------------------------------------------------------------------
    # WEEKLY;INTERVAL=2 (biweekly), DAILY;INTERVAL=3, HOURLY;INTERVAL=5
    pytest.param("WEEKLY", _FAR_PAST, "INTERVAL=2", id="weekly_far_past_interval2"),
    pytest.param("DAILY", _FAR_PAST, "INTERVAL=3", id="daily_far_past_interval3"),
    pytest.param("HOURLY", _FAR_PAST, "INTERVAL=5", id="hourly_far_past_interval5"),
    pytest.param("DAILY", _FAR_PAST, "INTERVAL=2", id="daily_far_past_interval2"),
    # -----------------------------------------------------------------------
    # INTERVAL > 1 — BY*-safe branch (the bug was here)
    # -----------------------------------------------------------------------
    # WEEKLY BY* shapes
    pytest.param(
        "WEEKLY",
        _FAR_PAST,
        "INTERVAL=2;BYDAY=MO",
        id="weekly_far_past_interval2_byday_mo",
    ),
    pytest.param(
        "WEEKLY",
        _FAR_PAST,
        "INTERVAL=3;BYDAY=MO,WE,FR",
        id="weekly_far_past_interval3_byday_mo_we_fr",
    ),
    # DAILY BY* shapes
    pytest.param(
        "DAILY",
        _FAR_PAST,
        "INTERVAL=3;BYHOUR=9",
        id="daily_far_past_interval3_byhour9",
    ),
    pytest.param(
        "DAILY",
        _FAR_PAST,
        "INTERVAL=2;BYHOUR=9;BYMINUTE=30",
        id="daily_far_past_interval2_byhour9_byminute30",
    ),
    # HOURLY BY* shapes
    pytest.param(
        "HOURLY",
        _FAR_PAST,
        "INTERVAL=5;BYMINUTE=0",
        id="hourly_far_past_interval5_byminute0",
    ),
    pytest.param(
        "HOURLY",
        _FAR_PAST,
        "INTERVAL=3;BYMINUTE=0",
        id="hourly_far_past_interval3_byminute0",
    ),
]


def _unclamped_reference(
    ics: str, now: datetime, lookahead: int, tz: ZoneInfo
) -> set[tuple]:
    """Return {(summary, start)} from parse_ics with clamping bypassed."""
    original_clamp = _cal_mod._clamp_recurrence_anchors
    _cal_mod._clamp_recurrence_anchors = lambda cal, now: 0
    try:
        events = parse_ics(ics, now=now, lookahead_days=lookahead, tz=tz)
    finally:
        _cal_mod._clamp_recurrence_anchors = original_clamp
    return {(e.summary, e.start) for e in events}


@pytest.mark.parametrize("freq,dtstart_val,modifier_val", _CLAMP_EQUIV_CASES)
def test_clamp_equivalence(freq: str, dtstart_val: str, modifier_val: str) -> None:
    """Assert that clamped parse == unclamped parse for in-window events.

    Bypass _clamp_recurrence_anchors via monkeypatching to obtain the
    reference set, then compare {(summary, start)} pairs.

    Also asserts the clamp actually FIRED (so the test exercises the clamped
    path, not a no-op) — for far-past rules that should always clamp.

    If this fails, the clamp is changing the in-window result — that is a
    correctness bug that must NOT be papered over by weakening the test.
    """
    ics = _build_ics(freq, dtstart_val, modifier_val)

    # Path A: normal parse (clamping active); also capture whether any clamp fired.
    clamp_count = 0
    original_clamp = _cal_mod._clamp_recurrence_anchors

    def _counting_clamp(cal: object, now: datetime) -> int:
        nonlocal clamp_count
        n = original_clamp(cal, now)
        clamp_count += n
        return n

    _cal_mod._clamp_recurrence_anchors = _counting_clamp  # type: ignore[assignment]
    try:
        events_clamped = parse_ics(ics, now=_NOW, lookahead_days=_LOOKAHEAD, tz=_UTC)
    finally:
        _cal_mod._clamp_recurrence_anchors = original_clamp

    # Path B: bypass clamping (reference)
    unclamped_set = _unclamped_reference(ics, _NOW, _LOOKAHEAD, _UTC)

    clamped_set = {(e.summary, e.start) for e in events_clamped}

    # Clamp-equivalence: in-window events must be identical.
    assert clamped_set == unclamped_set, (
        f"{freq}/{dtstart_val[:8]}/{modifier_val or 'forever'}: "
        f"clamped and unclamped parse produced different in-window events.\n"
        f"Only in clamped:   {clamped_set - unclamped_set}\n"
        f"Only in unclamped: {unclamped_set - clamped_set}"
    )

    # Clamp-fired: the clamp must have run for far-past rules (COUNT absent,
    # no unsafe BY* keys) — if clamp_count==0 on a far-past rule, the test is
    # not exercising the optimised path and its equivalence check is a no-op.
    # (Rules with COUNT are excluded from clamping; near/future DTSTART may not
    # meet the gap threshold — skip the fired-assertion for those.)
    modifier_upper = modifier_val.upper()
    has_count = "COUNT=" in modifier_upper
    if not has_count and dtstart_val == _FAR_PAST:
        assert clamp_count > 0, (
            f"{freq}/{dtstart_val[:8]}/{modifier_val or 'forever'}: "
            f"expected the clamp to fire for a far-past rule, but clamp_count=0. "
            f"The equivalence check is a no-op — the clamped path was never exercised."
        )


# ---------------------------------------------------------------------------
# Direct regression: biweekly Monday correctness (the reported bug)
# ---------------------------------------------------------------------------


def test_clamp_interval_biweekly_correct_dates() -> None:
    """Regression: WEEKLY;INTERVAL=2;BYDAY=MO far-past anchor returns the
    CORRECT biweekly Mondays, not dates shifted by one week.

    Reported bug: _clamp_recurrence_anchors advanced the anchor by one-week
    steps (ignoring INTERVAL=2), landing on a wrong phase.  With now=2026-06-15
    and a 28-day lookahead, the correct biweekly Mondays (anchored Jan 1 2024,
    which is a Monday; parity: even ISO-week offsets from anchor) are:
      2026-06-29 and 2026-07-13
    The buggy result was one week early:
      2026-06-22 and 2026-07-06

    Both the clamped parse AND the unclamped reference must agree on the correct
    dates.
    """
    now = datetime(2026, 6, 15, 0, 0, tzinfo=_UTC)
    lookahead = 28  # days

    # DTSTART=20240101T000000Z (Monday Jan 1 2024) + INTERVAL=2 → biweekly Mondays
    ics = _build_ics("WEEKLY", _FAR_PAST, "INTERVAL=2;BYDAY=MO")

    # Unclamped reference (bypass clamp)
    unclamped_set = _unclamped_reference(ics, now, lookahead, _UTC)

    # Clamped parse
    events_clamped = parse_ics(ics, now=now, lookahead_days=lookahead, tz=_UTC)
    clamped_set = {(e.summary, e.start) for e in events_clamped}

    # The two must agree.
    assert clamped_set == unclamped_set, (
        f"Biweekly Monday: clamped={clamped_set} != unclamped={unclamped_set}\n"
        f"The INTERVAL=2 clamp bug may have been reintroduced."
    )

    # The correct dates must be present — not the off-by-one-week buggy dates.
    starts = {e.start for e in events_clamped}
    # Correct biweekly Mondays in window [2026-06-15, 2026-07-13]
    expected_correct = {
        datetime(2026, 6, 29, 0, 0, tzinfo=_UTC),
        datetime(2026, 7, 13, 0, 0, tzinfo=_UTC),
    }
    # Buggy (off by one week) dates that must NOT appear
    buggy_dates = {
        datetime(2026, 6, 22, 0, 0, tzinfo=_UTC),
        datetime(2026, 7, 6, 0, 0, tzinfo=_UTC),
    }
    assert expected_correct <= starts, (
        f"Expected biweekly Mondays {expected_correct} not found in {starts}.\n"
        f"INTERVAL clamp bug may be active."
    )
    assert not (buggy_dates & starts), (
        f"Off-by-one-week buggy dates {buggy_dates & starts} appeared in {starts}.\n"
        f"INTERVAL clamp bug may be active."
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
        "be fast after the subhourly pre-filter + window-break + clamp fixes)"
    )
