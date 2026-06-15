"""Guard 5 — tz/DST invariant (class C).

Asserts:
1. Every CalendarEvent.start from parse_ics is tz-AWARE (.tzinfo is not None)
   across: UTC DTSTART, a named TZID, a floating/naive DTSTART, an all-day DATE.

2. _resolve_tz(None) returns a concrete tzinfo (not None).
   _resolve_tz("America/New_York") returns ZoneInfo("America/New_York").

3. DST-boundary countdown is UTC-correct:
   - Spring-forward: now=2026-03-07 23:00 EST, event=2026-03-08 10:00 EDT
     → UTC gap is 10h, wall-clock gap is 11h. Must render "in 10h".
   - Fall-back: now=2026-11-01 00:30 EDT, event=2026-11-01 03:00 EST
     → Clock falls back at 02:00 (EDT→EST). UTC gap = 3h30m.
     Must render "in 3h 30m", not "in 2h 30m" (naive wall-clock).

4. _now_in(None) returns an aware datetime.
"""

from datetime import datetime, tzinfo
from pathlib import Path
from zoneinfo import ZoneInfo

from led_ticker.widgets.calendar import (
    CalendarEvent,
    _now_in,
    _resolve_tz,
    _to_display_start,
    format_relative,
    parse_ics,
)

_UTC = ZoneInfo("UTC")
_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "calendar_sample.ics"


# ---------------------------------------------------------------------------
# Section 1: CalendarEvent.start is always tz-aware after parse_ics
# ---------------------------------------------------------------------------

# ICS with four DTSTART variants:
#   a) UTC (Z suffix)
#   b) Named TZID (America/Los_Angeles)
#   c) Floating / naive datetime (no tz, no Z)
#   d) All-day DATE value
_MIXED_DTSTART_ICS = """\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//test//EN
BEGIN:VEVENT
UID:utc-1
DTSTART:20260615T150000Z
DTEND:20260615T160000Z
SUMMARY:UTC Event
END:VEVENT
BEGIN:VEVENT
UID:tzid-1
DTSTART;TZID=America/Los_Angeles:20260615T080000
DTEND;TZID=America/Los_Angeles:20260615T090000
SUMMARY:LA Event
END:VEVENT
BEGIN:VEVENT
UID:floating-1
DTSTART:20260615T120000
DTEND:20260615T130000
SUMMARY:Floating Event
END:VEVENT
BEGIN:VEVENT
UID:allday-1
DTSTART;VALUE=DATE:20260616
DTEND;VALUE=DATE:20260617
SUMMARY:All Day Event
END:VEVENT
END:VCALENDAR
"""


def test_parse_ics_all_dtstart_variants_are_tz_aware():
    """Every CalendarEvent.start is tz-aware regardless of DTSTART encoding."""
    now = datetime(2026, 6, 15, 0, 0, tzinfo=_UTC)
    events = parse_ics(_MIXED_DTSTART_ICS, now=now, lookahead_days=7, tz=_UTC)
    assert events, "Expected at least one event from the mixed-DTSTART fixture"
    for event in events:
        assert event.start.tzinfo is not None, (
            f"CalendarEvent.start for '{event.summary}' must be tz-aware, "
            f"got tzinfo=None (start={event.start!r})"
        )


def test_parse_ics_utc_event_is_tz_aware():
    """A DTSTART with Z suffix produces a tz-aware start."""
    now = datetime(2026, 6, 15, 0, 0, tzinfo=_UTC)
    events = parse_ics(_MIXED_DTSTART_ICS, now=now, lookahead_days=7, tz=_UTC)
    utc_events = [e for e in events if e.summary == "UTC Event"]
    assert utc_events, "UTC Event must be parsed"
    assert utc_events[0].start.tzinfo is not None


def test_parse_ics_tzid_event_is_tz_aware():
    """A DTSTART with TZID= produces a tz-aware start resolved to display tz."""
    now = datetime(2026, 6, 15, 0, 0, tzinfo=_UTC)
    events = parse_ics(_MIXED_DTSTART_ICS, now=now, lookahead_days=7, tz=_UTC)
    la_events = [e for e in events if e.summary == "LA Event"]
    assert la_events, "LA Event (TZID=America/Los_Angeles) must be parsed"
    assert la_events[0].start.tzinfo is not None


def test_parse_ics_floating_event_is_tz_aware():
    """A floating (naive) DTSTART is assumed to be in display tz and made aware."""
    now = datetime(2026, 6, 15, 0, 0, tzinfo=_UTC)
    events = parse_ics(_MIXED_DTSTART_ICS, now=now, lookahead_days=7, tz=_UTC)
    floating = [e for e in events if e.summary == "Floating Event"]
    assert floating, "Floating Event must be parsed"
    assert floating[0].start.tzinfo is not None, (
        "Floating/naive DTSTART must be localised to display tz and become aware"
    )


def test_parse_ics_allday_event_is_tz_aware():
    """An all-day DATE DTSTART is resolved to midnight in display tz and is aware."""
    now = datetime(2026, 6, 15, 0, 0, tzinfo=_UTC)
    events = parse_ics(_MIXED_DTSTART_ICS, now=now, lookahead_days=7, tz=_UTC)
    allday = [e for e in events if e.summary == "All Day Event"]
    assert allday, "All Day Event must be parsed"
    assert allday[0].start.tzinfo is not None, (
        "All-day DATE DTSTART must produce an aware start (midnight in display tz)"
    )
    assert allday[0].all_day is True


def test_fixture_all_starts_tz_aware():
    """Every event in the shared test fixture has an aware start."""
    now = datetime(2026, 6, 15, 0, 0, tzinfo=_UTC)
    events = parse_ics(_FIXTURE.read_text(), now=now, lookahead_days=30, tz=_UTC)
    assert events
    for e in events:
        assert e.start.tzinfo is not None, (
            f"Fixture event '{e.summary}' start={e.start!r} must be tz-aware"
        )


# ---------------------------------------------------------------------------
# Section 2: _resolve_tz / _now_in contracts
# ---------------------------------------------------------------------------


def test_resolve_tz_none_returns_concrete_tzinfo():
    """_resolve_tz(None) must return a concrete, non-None tzinfo."""
    result = _resolve_tz(None)
    assert result is not None
    assert isinstance(result, tzinfo), (
        f"_resolve_tz(None) must return a tzinfo, got {type(result)!r}"
    )


def test_resolve_tz_explicit_utc():
    """_resolve_tz('UTC') returns ZoneInfo('UTC')."""
    result = _resolve_tz("UTC")
    assert result == ZoneInfo("UTC")


def test_resolve_tz_new_york():
    """_resolve_tz('America/New_York') returns the correct ZoneInfo."""
    result = _resolve_tz("America/New_York")
    assert result == ZoneInfo("America/New_York")
    assert isinstance(result, ZoneInfo)


def test_resolve_tz_london():
    """_resolve_tz('Europe/London') returns the correct ZoneInfo."""
    result = _resolve_tz("Europe/London")
    assert result == ZoneInfo("Europe/London")


def test_now_in_none_is_aware():
    """_now_in(None) must return an aware datetime (tzinfo is not None)."""
    result = _now_in(None)
    assert result.tzinfo is not None, (
        "_now_in(None) must return an aware datetime (local zone), got naive"
    )


def test_now_in_explicit_tz_is_aware():
    """_now_in(ZoneInfo('UTC')) returns an aware datetime in that zone."""
    result = _now_in(ZoneInfo("UTC"))
    assert result.tzinfo is not None


def test_now_in_new_york_is_aware():
    """_now_in with America/New_York returns an aware, DST-correct datetime."""
    tz = ZoneInfo("America/New_York")
    result = _now_in(tz)
    assert result.tzinfo is not None


# ---------------------------------------------------------------------------
# Section 3: _to_display_start makes all DTSTART kinds tz-aware
# ---------------------------------------------------------------------------


def test_to_display_start_bare_date_is_aware_allday():
    """A bare date produces (midnight in tz, all_day=True) — start is aware."""
    from datetime import date

    d = date(2026, 6, 15)
    start, is_all_day = _to_display_start(d, _UTC)
    assert is_all_day is True
    assert start.tzinfo is not None
    assert start == datetime(2026, 6, 15, 0, 0, tzinfo=_UTC)


def test_to_display_start_naive_datetime_localises():
    """A naive datetime is assumed to be in display tz and made aware."""
    naive = datetime(2026, 6, 15, 10, 0)  # no tzinfo
    start, is_all_day = _to_display_start(naive, _UTC)
    assert is_all_day is False
    assert start.tzinfo is not None
    assert start == datetime(2026, 6, 15, 10, 0, tzinfo=_UTC)


def test_to_display_start_aware_datetime_converts_to_display_tz():
    """An aware datetime is converted to display tz and remains aware."""
    tz_ny = ZoneInfo("America/New_York")
    aware = datetime(2026, 6, 15, 10, 0, tzinfo=tz_ny)  # UTC-4 in summer
    start, is_all_day = _to_display_start(aware, _UTC)
    assert is_all_day is False
    assert start.tzinfo is not None
    # 10:00 EDT = 14:00 UTC
    assert start == datetime(2026, 6, 15, 14, 0, tzinfo=_UTC)


# ---------------------------------------------------------------------------
# Section 4: DST boundary countdown is UTC-correct
# ---------------------------------------------------------------------------


def test_format_relative_spring_forward_is_utc_correct():
    """Spring-forward: format_relative uses UTC delta, not wall-clock.

    now  = 2026-03-07 23:00 EST (UTC-5) — just before DST change day
    event = 2026-03-08 10:00 EDT (UTC-4) — after spring-forward at 02:00

    Wall-clock gap: 11h (23:00 → 10:00 next day = 11h by naive subtraction)
    UTC gap:        10h (04:00 UTC → 14:00 UTC = 10h)

    Panel must display "in 10h" (UTC-correct), NOT "in 11h" (naive wall-clock).
    """
    tz = ZoneInfo("America/New_York")
    now = datetime(2026, 3, 7, 23, 0, tzinfo=tz)  # EST (UTC-5)
    event = CalendarEvent(
        "MeetingSpring",
        datetime(2026, 3, 8, 10, 0, tzinfo=tz),  # EDT (UTC-4) post-spring-forward
        all_day=False,
    )
    result = format_relative(event, now, "x")
    assert result == "MeetingSpring · in 10h", (
        f"Spring-forward countdown must be UTC-correct ('in 10h'), got {result!r}. "
        "Check that format_relative subtracts event.start.astimezone(UTC) - "
        "now.astimezone(UTC), not naively."
    )


def test_format_relative_fall_back_is_utc_correct():
    """Fall-back: format_relative must be UTC-correct across the fall-back boundary.

    2026-11-01 02:00 EDT falls back to 02:00 EST (clocks go back one hour).

    now  = 2026-11-01 00:30 EDT (UTC-4) = 04:30 UTC
    event = 2026-11-01 03:00 EST (UTC-5) = 08:00 UTC

    UTC gap: 3h 30m (04:30 → 08:00 UTC).
    Naive wall-clock: 00:30 → 03:00 = 2h 30m (incorrect — ignores fall-back hour).

    Panel must display "in 3h 30m", NOT "in 2h 30m".
    """
    tz = ZoneInfo("America/New_York")
    # 00:30 on the fall-back day, still in EDT (UTC-4)
    now = datetime(2026, 11, 1, 0, 30, tzinfo=tz)
    # 03:00 on the same day — but by then EDT has fallen back to EST (UTC-5)
    # ZoneInfo will fold=0 by default; use fold=1 to get the first 03:00 (EST)

    # Construct 03:00 EST explicitly by going through UTC
    event_utc = datetime(2026, 11, 1, 8, 0, tzinfo=_UTC)  # 08:00 UTC = 03:00 EST
    event = CalendarEvent(
        "MeetingFall",
        event_utc.astimezone(tz),
        all_day=False,
    )
    result = format_relative(event, now, "x")
    assert result == "MeetingFall · in 3h 30m", (
        f"Fall-back countdown must be UTC-correct ('in 3h 30m'), got {result!r}. "
        "Check that format_relative subtracts in UTC, not wall-clock."
    )


def test_format_relative_no_dst_one_hour_is_exact():
    """Sanity: without a DST transition, 1-hour-ahead event renders 'in 1h'."""
    now = datetime(2026, 6, 15, 14, 0, tzinfo=_UTC)
    event = CalendarEvent(
        "Sanity", datetime(2026, 6, 15, 15, 0, tzinfo=_UTC), all_day=False
    )
    result = format_relative(event, now, "x")
    assert result == "Sanity · in 1h"


def test_format_relative_mixed_tz_providers_same_instant():
    """Two datetimes representing the same instant but in different zones produce
    the same countdown. Verifies that subtracting in UTC eliminates zone-offset skew."""
    tz_la = ZoneInfo("America/Los_Angeles")
    tz_ny = ZoneInfo("America/New_York")
    # 15:00 UTC on a standard-time day (no DST in January)
    base_utc = datetime(2026, 1, 15, 15, 0, tzinfo=_UTC)
    # now in LA (UTC-8): 07:00 PST
    now_la = base_utc.astimezone(tz_la)
    # event in NY (UTC-5): 10:00 EST; 1h ahead of now in UTC
    event_ny = datetime(2026, 1, 15, 16, 0, tzinfo=_UTC).astimezone(tz_ny)
    event = CalendarEvent("CrossZone", event_ny, all_day=False)
    result = format_relative(event, now_la, "x")
    assert result == "CrossZone · in 1h", (
        f"Cross-timezone 1h delta must render 'in 1h', got {result!r}"
    )
