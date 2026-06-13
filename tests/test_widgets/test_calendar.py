"""Tests for the calendar widget."""

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from led_ticker.widgets import get_widget_class
from led_ticker.widgets.calendar import CalendarEvent, parse_ics

_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "calendar_sample.ics"
_UTC = ZoneInfo("UTC")


def _parse(now, days=7, tz=_UTC):
    return parse_ics(_FIXTURE.read_text(), now=now, lookahead_days=days, tz=tz)


def test_calendar_registered():
    cls = get_widget_class("calendar")
    assert cls.__name__ == "Calendar"


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
    assert len(ones) == 3
    assert ones[0].start < ones[1].start < ones[2].start


def test_parse_drops_past_and_sorts():
    now = datetime(2026, 6, 16, 12, 0, tzinfo=_UTC)
    events = _parse(now, days=7)
    starts = [e.start for e in events]
    assert starts == sorted(starts)
    assert all(not (e.start < now and not e.all_day) for e in events)


def test_parse_drops_ongoing_timed_event():
    # The "Daily 1:1" recurs at 10:00 UTC. At 11:00 the 10:00 occurrence has
    # started (it is "ongoing"/past-start) and must be dropped by the
    # start < now filter even though recurring_ical_events still returns it.
    now = datetime(2026, 6, 15, 11, 0, tzinfo=_UTC)
    events = _parse(now, days=1)
    # the 10:00 occurrence on 06-15 must NOT appear (it already started)
    assert not any(
        e.summary == "Daily 1:1"
        and e.start == datetime(2026, 6, 15, 10, 0, tzinfo=_UTC)
        for e in events
    )


def test_calendar_event_is_value_object():
    e = CalendarEvent(
        summary="x", start=datetime(2026, 1, 1, tzinfo=_UTC), all_day=False
    )
    assert e.summary == "x"
    # equality is load-bearing for later select_events membership checks
    assert e == CalendarEvent(
        summary="x", start=datetime(2026, 1, 1, tzinfo=_UTC), all_day=False
    )


def test_parse_with_local_tz_does_not_crash():
    # Regression for the default (no `timezone`) path: a concrete local tzinfo
    # must parse the tz-aware fixture without a naive/aware TypeError, and
    # timed + all-day events must sort together.
    local = datetime.now().astimezone().tzinfo
    now = datetime(2026, 6, 15, 0, 0, tzinfo=local)
    events = parse_ics(_FIXTURE.read_text(), now=now, lookahead_days=7, tz=local)
    assert events
    assert all(e.start.tzinfo is not None for e in events)
    starts = [e.start for e in events]
    assert starts == sorted(starts)
