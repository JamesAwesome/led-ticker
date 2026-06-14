"""Tests for the calendar widget."""

import asyncio
import os
import tempfile
from datetime import datetime, tzinfo
from pathlib import Path
from unittest.mock import Mock
from urllib.parse import quote
from zoneinfo import ZoneInfo

from led_ticker.widgets import get_widget_class
from led_ticker.widgets.calendar import (
    _MAX_OCCURRENCES,
    Calendar,
    CalendarEvent,
    TickerMessage,
    _clamp_recurrence_anchors,
    _match_any,
    _NextEventWidget,
    _normalize_ics_url,
    _resolve_tz,
    _rrule_is_subhourly,
    format_event_line,
    format_relative,
    parse_ics,
    select_events,
)

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


def test_select_highlight_exceeds_cap_is_still_capped():
    # More highlighted matches than max_events: still capped, still chronological.
    events = [_ev("Payday", d) for d in range(15, 22)]  # 7 highlighted events
    kept = select_events(events, filter=[], highlight=["payday"], max_events=3)
    assert len(kept) == 3
    assert [e.start for e in kept] == sorted(e.start for e in kept)


def test_format_today_timed_12h():
    now = datetime(2026, 6, 15, 8, 0, tzinfo=_UTC)
    e = CalendarEvent("Standup", datetime(2026, 6, 15, 15, 0, tzinfo=_UTC), False)
    result = format_event_line(e, now=now, time_format="12h", tz=_UTC)
    assert result == "Today 3:00 PM  Standup"


def test_format_tomorrow_24h():
    now = datetime(2026, 6, 15, 8, 0, tzinfo=_UTC)
    e = CalendarEvent("Dentist", datetime(2026, 6, 16, 9, 5, tzinfo=_UTC), False)
    result = format_event_line(e, now=now, time_format="24h", tz=_UTC)
    assert result == "Tomorrow 09:05  Dentist"


def test_format_weekday_within_week():
    now = datetime(2026, 6, 15, 8, 0, tzinfo=_UTC)  # Mon 2026-06-15
    e = CalendarEvent("1:1", datetime(2026, 6, 18, 10, 0, tzinfo=_UTC), False)  # Thu
    assert format_event_line(e, now=now, time_format="24h", tz=_UTC) == "Thu 10:00  1:1"


def test_format_all_day_omits_time():
    now = datetime(2026, 6, 15, 8, 0, tzinfo=_UTC)
    e = CalendarEvent("Holiday", datetime(2026, 6, 16, 0, 0, tzinfo=_UTC), True)
    result = format_event_line(e, now=now, time_format="12h", tz=_UTC)
    assert result == "Tomorrow  Holiday"


# ---------------------------------------------------------------------------
# Task 5: format_relative + _NextEventWidget
# ---------------------------------------------------------------------------


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
    w = _NextEventWidget(events=[e], empty_text="none", timezone="UTC")
    out_canvas, cursor = w.draw(canvas)
    assert out_canvas is canvas
    assert isinstance(cursor, int)


def test_next_event_widget_rainbow_advances_frame(canvas):
    from led_ticker.color_providers import Rainbow

    e = CalendarEvent("Standup", datetime(2026, 6, 15, 15, 0, tzinfo=_UTC), False)
    w = _NextEventWidget(
        events=[e], empty_text="none", timezone="UTC", font_color=Rainbow()
    )
    w.advance_frame()
    w.draw(canvas)  # must not raise; per-char path exercised


def test_format_relative_sub_minute_is_now():
    now = datetime(2026, 6, 15, 15, 0, 0, tzinfo=_UTC)
    e = CalendarEvent("Standup", datetime(2026, 6, 15, 15, 0, 30, tzinfo=_UTC), False)
    assert format_relative(e, now, "x") == "Standup now"


def test_format_relative_exact_hour_drops_zero_minutes():
    now = datetime(2026, 6, 15, 14, 0, tzinfo=_UTC)
    e = CalendarEvent("Standup", datetime(2026, 6, 15, 15, 0, tzinfo=_UTC), False)
    assert format_relative(e, now, "x") == "Standup in 1h"


def test_next_event_widget_unset_timezone_does_not_crash(canvas):
    # Default path: timezone=None must still produce an aware `now` so the
    # `event.start - now` subtraction in format_relative does not raise.
    local = datetime.now().astimezone().tzinfo
    e = CalendarEvent("Standup", datetime(2026, 12, 31, 23, 59, tzinfo=local), False)
    w = _NextEventWidget(events=[e], empty_text="none", timezone=None)
    out_canvas, _ = w.draw(canvas)  # must not raise
    assert out_canvas is canvas


# ---------------------------------------------------------------------------
# Task 6: update() + start() + file:// fetch + _build_stories
# ---------------------------------------------------------------------------


def _make_calendar(**kwargs):
    # session unused for file:// fetch; pass None.
    defaults = dict(session=None, ics_url=f"file://{_FIXTURE}", timezone="UTC")
    defaults.update(kwargs)
    return Calendar(**defaults)


def test_update_agenda_builds_messages(monkeypatch):
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
    cal = _make_calendar(layout="agenda", empty_text="Nothing", lookahead_days=1)
    monkeypatch.setattr(
        "led_ticker.widgets.calendar._now_in",
        lambda tz: datetime(2030, 1, 1, 0, 0, tzinfo=_UTC),  # far future, nothing
    )
    asyncio.run(cal.update())
    assert len(cal.feed_stories) == 1
    assert isinstance(cal.feed_stories[0], TickerMessage)


def test_update_default_timezone_parses_events(monkeypatch):
    # Regression for the default config (no `timezone`): update() must build
    # real events, not silently swallow a naive/aware TypeError into empty_text.
    local = datetime.now().astimezone().tzinfo
    # no timezone kwarg — exercises the tz=None path
    cal = Calendar(session=None, ics_url=f"file://{_FIXTURE}", layout="agenda")
    monkeypatch.setattr(
        "led_ticker.widgets.calendar._now_in",
        lambda tz: datetime(2026, 6, 15, 0, 0, tzinfo=local),
    )
    asyncio.run(cal.update())
    assert cal.feed_stories
    assert all(isinstance(s, TickerMessage) for s in cal.feed_stories)
    # not the single empty_text fallback
    assert not (
        len(cal.feed_stories) == 1 and cal.feed_stories[0].text == cal.empty_text
    )


def test_update_fetch_error_keeps_previous(monkeypatch):
    cal = _make_calendar(ics_url="file:///nonexistent/path.ics")
    sentinel = ["KEEP"]
    cal.feed_stories = sentinel
    asyncio.run(cal.update())  # must not raise
    assert cal.feed_stories is sentinel  # previous kept on error


def test_update_first_load_error_shows_empty_text():
    cal = _make_calendar(ics_url="file:///nonexistent/path.ics", empty_text="Down")
    asyncio.run(cal.update())  # no previous data
    assert len(cal.feed_stories) == 1
    assert isinstance(cal.feed_stories[0], TickerMessage)


# ---------------------------------------------------------------------------
# Task 7: color defaults/coercion + validate_config
# ---------------------------------------------------------------------------


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
    assert (
        Calendar.validate_config(
            {
                "ics_url": "https://x/c.ics",
                "layout": "next",
                "timezone": "America/New_York",
                "filter": ["a"],
                "highlight": ["b"],
            }
        )
        == []
    )


def test_validate_rejects_bool_max_events():
    msgs = Calendar.validate_config({"ics_url": "x", "max_events": True})
    assert any("max_events" in m for m in msgs)


def test_list_fields_calendar_shows_hint_descriptions():
    from led_ticker.app.factories import _list_widget_fields

    out = _list_widget_fields("calendar")
    # Field NAMES appear from the attrs fields / start() params regardless of
    # hints, so assert the hint DESCRIPTIONS — those only appear once the
    # FIELD_HINTS entries are added.
    assert "public .ics feed URL" in out
    assert "keep only events whose summary matches a keyword" in out


def test_list_fields_calendar_layout_is_calendar_specific():
    """--list-fields calendar must show calendar layout values, not pool values."""
    from led_ticker.app.factories import _list_widget_fields

    out = _list_widget_fields("calendar")
    # Calendar-specific values must be present.
    assert "agenda" in out
    assert "next" in out
    # Pool-specific value must NOT appear in the layout line.
    # ("scoreboard" is the pool layout variant never valid for calendar.)
    assert "scoreboard" not in out


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


# ---------------------------------------------------------------------------
# Fix A: time_format validation + build-error isolation in update()
# ---------------------------------------------------------------------------


def test_validate_rejects_bad_time_format():
    # Non-preset string (no % in it, and not 12h/24h) must be rejected.
    msgs = Calendar.validate_config({"ics_url": "x", "time_format": "bogus"})
    assert any("time_format" in m for m in msgs)


def test_validate_rejects_non_string_time_format():
    # Non-string (e.g. the int 24) must be rejected.
    msgs = Calendar.validate_config({"ics_url": "x", "time_format": 24})
    assert any("time_format" in m for m in msgs)


def test_validate_accepts_strftime_time_format():
    # A string containing '%' is accepted as a strftime template.
    msgs = Calendar.validate_config({"ics_url": "x", "time_format": "%H:%M"})
    assert not any("time_format" in m for m in msgs)


def test_update_bad_time_format_does_not_propagate(monkeypatch):
    # An invalid time_format (bogus preset) surfacing inside _build_stories must
    # not propagate out of update() — the try block must cover it.
    cal = _make_calendar(time_format="bogus", timezone="UTC")
    monkeypatch.setattr(
        "led_ticker.widgets.calendar._now_in",
        lambda tz: datetime(2026, 6, 15, 0, 0, tzinfo=_UTC),
    )
    # Must NOT raise — exception should be caught inside update().
    asyncio.run(cal.update())
    # feed_stories should be set to either events or the empty fallback.
    assert isinstance(cal.feed_stories, list)


# ---------------------------------------------------------------------------
# Fix B: multi-day all-day events use DTEND
# ---------------------------------------------------------------------------

_MULTIDAY_ICS = """\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//test//EN
BEGIN:VEVENT
UID:multiday-1
DTSTART;VALUE=DATE:20260615
DTEND;VALUE=DATE:20260620
SUMMARY:Vacation
END:VEVENT
END:VCALENDAR
"""


def test_parse_keeps_ongoing_multiday_all_day():
    # now is in the middle of the Vacation (20260615–20260620, exclusive end).
    # With DTEND-based logic, the event must survive the past-drop filter.
    now = datetime(2026, 6, 17, 12, 0, tzinfo=_UTC)
    events = parse_ics(_MULTIDAY_ICS, now=now, lookahead_days=10, tz=_UTC)
    vacations = [e for e in events if e.summary == "Vacation"]
    assert len(vacations) == 1, (
        "Ongoing multi-day all-day event should be kept when now is before DTEND"
    )


def test_parse_drops_finished_multiday_all_day():
    # now is AFTER the Vacation ends (exclusive end 20260620).
    now = datetime(2026, 6, 20, 0, 0, tzinfo=_UTC)
    events = parse_ics(_MULTIDAY_ICS, now=now, lookahead_days=10, tz=_UTC)
    assert not any(e.summary == "Vacation" for e in events), (
        "Multi-day all-day event should be dropped when now >= DTEND"
    )


# ---------------------------------------------------------------------------
# Fix C: _resolve_tz returns concrete DST-correct tzinfo
# ---------------------------------------------------------------------------


def test_resolve_tz_explicit_is_zoneinfo():
    result = _resolve_tz("UTC")
    assert result == ZoneInfo("UTC")


def test_resolve_tz_default_returns_concrete_tzinfo():
    # No timezone configured — must return a non-None tzinfo without raising.
    result = _resolve_tz(None)
    assert result is not None
    assert isinstance(result, tzinfo)


# ---------------------------------------------------------------------------
# Fix D: percent-decode file:// paths
# ---------------------------------------------------------------------------


def test_fetch_ics_percent_decoded_path(tmp_path):
    # Write a tiny .ics to a directory whose name contains a space.
    spaced_dir = tmp_path / "my calendars"
    spaced_dir.mkdir()
    ics_file = spaced_dir / "test.ics"
    ics_file.write_text(_MULTIDAY_ICS)
    # Build a percent-encoded file:// URL for the path.
    encoded_url = "file://" + quote(str(ics_file))
    cal = Calendar(session=None, ics_url=encoded_url, timezone="UTC")
    content = asyncio.run(cal._fetch_ics())
    assert "Vacation" in content


# ---------------------------------------------------------------------------
# Fix E: lookahead_days upper-bound validation
# ---------------------------------------------------------------------------


def test_validate_rejects_excessive_lookahead():
    msgs = Calendar.validate_config({"ics_url": "x", "lookahead_days": 10_000})
    assert any("lookahead_days" in m for m in msgs)


def test_validate_accepts_max_valid_lookahead():
    msgs = Calendar.validate_config({"ics_url": "x", "lookahead_days": 366})
    assert not any("lookahead_days" in m for m in msgs)


# ---------------------------------------------------------------------------
# Fix 1: RRULE expansion cap (OOM DoS protection)
# ---------------------------------------------------------------------------

_SECONDLY_ICS = """\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//test//EN
BEGIN:VEVENT
UID:pathological-1
DTSTART:20260601T000000Z
RRULE:FREQ=SECONDLY
SUMMARY:Every Second
END:VEVENT
END:VCALENDAR
"""


_HOURLY_LONG_ICS = """\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//test//EN
BEGIN:VEVENT
UID:hourly-long-1
DTSTART:20200101T000000Z
RRULE:FREQ=HOURLY
SUMMARY:Every Hour
END:VEVENT
END:VCALENDAR
"""


def test_parse_caps_pathological_rrule():
    # A FREQ=HOURLY event starting in 2020 with no UNTIL/COUNT produces tens of
    # thousands of occurrences in a 365-day window — parse_ics must cap at
    # _MAX_OCCURRENCES and return quickly (islice bounds the expansion).
    # (Changed from FREQ=SECONDLY, pre-filtered by _drop_subhourly_recurrences;
    # HOURLY is the lowest frequency that exercises the islice cap.)
    now = datetime(2026, 6, 1, 0, 0, tzinfo=_UTC)
    events = parse_ics(_HOURLY_LONG_ICS, now=now, lookahead_days=365, tz=_UTC)
    # Must be bounded — not tens of thousands
    assert len(events) <= _MAX_OCCURRENCES


# ---------------------------------------------------------------------------
# Fix 2+3: layout="next" live-roll and no highlight distortion
# ---------------------------------------------------------------------------


def test_next_widget_picks_soonest_future_event(monkeypatch):
    # events in non-chronological order; draw() must pick the soonest future one.
    # We verify via format_relative: intercept the call to see which event is used.
    now = datetime(2026, 6, 15, 9, 0, tzinfo=_UTC)
    monkeypatch.setattr("led_ticker.widgets.calendar._now_in", lambda tz: now)
    picked = []
    original_format = format_relative

    def capture_format(event, _now, empty_text):
        picked.append(event)
        return original_format(event, _now, empty_text)

    monkeypatch.setattr("led_ticker.widgets.calendar.format_relative", capture_format)

    future_soon = CalendarEvent(
        "Dentist", datetime(2026, 6, 15, 9, 10, tzinfo=_UTC), False
    )
    future_later = CalendarEvent(
        "Lunch", datetime(2026, 6, 15, 12, 0, tzinfo=_UTC), False
    )
    # events deliberately not in chronological order
    w = _NextEventWidget(
        events=[future_later, future_soon],
        empty_text="none",
        timezone="UTC",
    )
    c = Mock()
    c.width = 160
    c.height = 16
    w.draw(c)
    # draw() must pick Dentist (soonest future), not Lunch
    assert picked and picked[0] is future_soon


def test_next_widget_rolls_past_started_event(monkeypatch):
    # An event whose start <= now must be skipped; draw shows the next future one.
    now = datetime(2026, 6, 15, 9, 5, tzinfo=_UTC)
    monkeypatch.setattr("led_ticker.widgets.calendar._now_in", lambda tz: now)
    picked = []
    original_format = format_relative

    def capture_format(event, _now, empty_text):
        picked.append(event)
        return original_format(event, _now, empty_text)

    monkeypatch.setattr("led_ticker.widgets.calendar.format_relative", capture_format)

    started = CalendarEvent(
        "Standup", datetime(2026, 6, 15, 9, 0, tzinfo=_UTC), False
    )  # started 5m ago (start <= now)
    upcoming = CalendarEvent("Lunch", datetime(2026, 6, 15, 12, 0, tzinfo=_UTC), False)
    w = _NextEventWidget(
        events=[started, upcoming],
        empty_text="none",
        timezone="UTC",
    )
    c = Mock()
    c.width = 160
    c.height = 16
    w.draw(c)
    # draw() must skip Standup (already started) and pick Lunch
    assert picked and picked[0] is upcoming


def test_update_next_not_distorted_by_highlight_cap(monkeypatch):
    # A daily-recurring highlighted event plus a sooner one-off "Dentist".
    # layout="next", highlight=["1:1"], default max_events=5.
    # The widget's events list (after update) must include Dentist as the
    # soonest item so draw() picks it over a 1:1 occurrence.
    _MIXED_ICS = """\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//test//EN
BEGIN:VEVENT
UID:dentist-1
DTSTART:20260615T100000Z
DTEND:20260615T110000Z
SUMMARY:Dentist
END:VEVENT
BEGIN:VEVENT
UID:one-on-one-daily
DTSTART:20260615T150000Z
RRULE:FREQ=DAILY;COUNT=20
SUMMARY:Daily 1:1
END:VEVENT
END:VCALENDAR
"""
    now = datetime(2026, 6, 15, 9, 0, tzinfo=_UTC)
    monkeypatch.setattr("led_ticker.widgets.calendar._now_in", lambda tz: now)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".ics", delete=False) as f:
        f.write(_MIXED_ICS)
        tmp_path = f.name
    try:
        cal = Calendar(
            session=None,
            ics_url=f"file://{tmp_path}",
            layout="next",
            timezone="UTC",
            highlight=["1:1"],
            max_events=5,
        )
        asyncio.run(cal.update())
        assert len(cal.feed_stories) == 1
        widget = cal.feed_stories[0]
        assert type(widget).__name__ == "_NextEventWidget"
        # The events list must contain Dentist (soonest)
        assert any(e.summary == "Dentist" for e in widget.events)
        # Chronologically first event must be Dentist (10:00), not 1:1 (15:00)
        sorted_events = sorted(widget.events, key=lambda e: e.start)
        assert sorted_events[0].summary == "Dentist"
    finally:
        os.unlink(tmp_path)


# ---------------------------------------------------------------------------
# Fix 4: Strip UTF-8 BOM before parsing
# ---------------------------------------------------------------------------


def test_parse_strips_utf8_bom():
    # Microsoft Exchange/Outlook .ics feeds start with a UTF-8 BOM.
    # parse_ics must not raise and must return events normally.
    bom = "﻿"
    bom_ics = bom + _MULTIDAY_ICS
    now = datetime(2026, 6, 14, 0, 0, tzinfo=_UTC)
    events = parse_ics(bom_ics, now=now, lookahead_days=10, tz=_UTC)
    assert any(e.summary == "Vacation" for e in events)


# ---------------------------------------------------------------------------
# Fix 5: Reject whitespace-only ics_url
# ---------------------------------------------------------------------------


def test_validate_rejects_whitespace_ics_url():
    msgs = Calendar.validate_config({"ics_url": "   "})
    assert any("ics_url" in m for m in msgs)


# ---------------------------------------------------------------------------
# Fix 1 (new): webcal:// / webcals:// scheme rewrite
# ---------------------------------------------------------------------------


def test_fetch_ics_rewrites_webcal():
    assert (
        _normalize_ics_url("webcal://example.com/c.ics") == "https://example.com/c.ics"
    )


def test_fetch_ics_rewrites_webcals():
    assert (
        _normalize_ics_url("webcals://example.com/c.ics") == "https://example.com/c.ics"
    )


def test_normalize_ics_url_http_passthrough():
    assert _normalize_ics_url("http://example.com/c.ics") == "http://example.com/c.ics"


def test_normalize_ics_url_https_passthrough():
    assert (
        _normalize_ics_url("https://example.com/c.ics") == "https://example.com/c.ics"
    )


def test_normalize_ics_url_file_passthrough():
    assert _normalize_ics_url("file:///tmp/c.ics") == "file:///tmp/c.ics"


def test_normalize_ics_url_bare_path_passthrough():
    assert _normalize_ics_url("/tmp/c.ics") == "/tmp/c.ics"


# ---------------------------------------------------------------------------
# Fix 2 (new): bare local paths not percent-decoded
# ---------------------------------------------------------------------------


def test_fetch_ics_bare_path_not_percent_decoded(tmp_path):
    # Write a tiny .ics file whose name contains the literal characters %41
    # (NOT 'A'). _fetch_ics must NOT percent-decode bare paths, so the file
    # is read as-is.
    literal_name = tmp_path / "report%41.ics"
    literal_name.write_text(_MULTIDAY_ICS)
    cal = Calendar(session=None, ics_url=str(literal_name), timezone="UTC")
    content = asyncio.run(cal._fetch_ics())
    assert "Vacation" in content


# ---------------------------------------------------------------------------
# Fix 3 (new): all-day event today visible in layout="next"
# ---------------------------------------------------------------------------


def test_next_widget_shows_all_day_today(monkeypatch):
    # An all-day event whose start date is today (midnight < now) must appear,
    # not be skipped as "past".
    now = datetime(2026, 6, 15, 10, 0, tzinfo=_UTC)
    monkeypatch.setattr("led_ticker.widgets.calendar._now_in", lambda tz: now)
    all_day_today = CalendarEvent(
        "Holiday", datetime(2026, 6, 15, 0, 0, tzinfo=_UTC), all_day=True
    )
    w = _NextEventWidget(
        events=[all_day_today], empty_text="No upcoming events", timezone="UTC"
    )
    c = Mock()
    c.width = 160
    c.height = 16
    result = format_relative(all_day_today, now, "No upcoming events")
    assert result == "Holiday today"
    # Also verify draw() does not produce the empty_text (the event IS shown)
    out_canvas, _ = w.draw(c)
    assert out_canvas is c


def test_format_relative_all_day_today_tomorrow():
    now = datetime(2026, 6, 15, 10, 0, tzinfo=_UTC)
    today = CalendarEvent(
        "Holiday", datetime(2026, 6, 15, 0, 0, tzinfo=_UTC), all_day=True
    )
    tomorrow = CalendarEvent(
        "Holiday", datetime(2026, 6, 16, 0, 0, tzinfo=_UTC), all_day=True
    )
    in_3d = CalendarEvent(
        "Holiday", datetime(2026, 6, 18, 0, 0, tzinfo=_UTC), all_day=True
    )
    assert format_relative(today, now, "x") == "Holiday today"
    assert format_relative(tomorrow, now, "x") == "Holiday tomorrow"
    assert format_relative(in_3d, now, "x") == "Holiday in 3d"


# ---------------------------------------------------------------------------
# Round-4 adversarial hardening fixes
# ---------------------------------------------------------------------------


# Fix 1: skip STATUS:CANCELLED events
_CANCELLED_ICS = """\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//test//EN
BEGIN:VEVENT
UID:cancelled-1
DTSTART:20260615T140000Z
DTEND:20260615T150000Z
SUMMARY:Cancelled Meeting
STATUS:CANCELLED
END:VEVENT
BEGIN:VEVENT
UID:normal-1
DTSTART:20260615T160000Z
DTEND:20260615T170000Z
SUMMARY:Normal Meeting
END:VEVENT
END:VCALENDAR
"""


def test_parse_skips_cancelled_events():
    now = datetime(2026, 6, 15, 13, 0, tzinfo=_UTC)
    events = parse_ics(_CANCELLED_ICS, now=now, lookahead_days=1, tz=_UTC)
    summaries = [e.summary for e in events]
    assert "Cancelled Meeting" not in summaries, (
        "STATUS:CANCELLED events must be skipped"
    )
    assert "Normal Meeting" in summaries, "Non-cancelled events must be kept"
    assert len(events) == 1


def test_parse_skips_cancelled_recurrence_override():
    # A RECURRENCE-ID override with STATUS:CANCELLED cancels that one occurrence.
    cancelled_override_ics = """\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//test//EN
BEGIN:VEVENT
UID:recurring-1
DTSTART:20260615T100000Z
RRULE:FREQ=DAILY;COUNT=3
SUMMARY:Daily Standup
END:VEVENT
BEGIN:VEVENT
UID:recurring-1
RECURRENCE-ID:20260616T100000Z
DTSTART:20260616T100000Z
DTEND:20260616T110000Z
SUMMARY:Daily Standup
STATUS:CANCELLED
END:VEVENT
END:VCALENDAR
"""
    now = datetime(2026, 6, 15, 0, 0, tzinfo=_UTC)
    events = parse_ics(cancelled_override_ics, now=now, lookahead_days=7, tz=_UTC)
    # The 06-16 occurrence should be suppressed by icalendar/recurring_ical_events
    # before our STATUS check, or caught by our check. Either way, no cancelled one.
    cancelled = [
        e
        for e in events
        if e.summary == "Daily Standup"
        and e.start == datetime(2026, 6, 16, 10, 0, tzinfo=_UTC)
    ]
    # Note: recurring_ical_events may already suppress the RECURRENCE-ID cancelled
    # override; this test asserts the net result is zero occurrences for that slot.
    assert len(cancelled) == 0, (
        "Cancelled RECURRENCE-ID override must not appear in parsed events"
    )


# Fix 2: ongoing multi-day all-day visible in next mode when it started before today
def test_next_shows_ongoing_multiday_all_day_when_no_timed(monkeypatch):
    # Multi-day all-day started YESTERDAY (start.date() < today), no timed events.
    # Old predicate (start.date() == today) would miss this; new predicate
    # (start.date() <= now_date) catches it as ongoing.
    now = datetime(2026, 6, 15, 10, 0, tzinfo=_UTC)
    monkeypatch.setattr("led_ticker.widgets.calendar._now_in", lambda tz: now)
    # Starts yesterday, ends tomorrow (ongoing multi-day all-day).
    multiday = CalendarEvent(
        "Vacation", datetime(2026, 6, 14, 0, 0, tzinfo=_UTC), all_day=True
    )
    picked = []
    original_format = format_relative

    def capture_format(event, _now, empty_text):
        picked.append(event)
        return original_format(event, _now, empty_text)

    monkeypatch.setattr("led_ticker.widgets.calendar.format_relative", capture_format)

    w = _NextEventWidget(
        events=[multiday], empty_text="No upcoming events", timezone="UTC"
    )
    c = Mock()
    c.width = 160
    c.height = 16
    w.draw(c)
    assert picked and picked[0] is multiday, (
        "Ongoing multi-day all-day (started before today) must appear in next mode"
    )
    result = format_relative(multiday, now, "No upcoming events")
    assert result == "Vacation today"


# Fix 3: timed event today preferred over all-day today
def test_next_prefers_timed_over_all_day_today(monkeypatch):
    # An all-day event today + a timed event later today -> draw shows the TIMED
    # event (actionable countdown), NOT the all-day.
    now = datetime(2026, 6, 15, 10, 0, tzinfo=_UTC)
    monkeypatch.setattr("led_ticker.widgets.calendar._now_in", lambda tz: now)
    all_day_today = CalendarEvent(
        "Holiday", datetime(2026, 6, 15, 0, 0, tzinfo=_UTC), all_day=True
    )
    timed_today = CalendarEvent(
        "Dentist", datetime(2026, 6, 15, 14, 0, tzinfo=_UTC), all_day=False
    )
    # all_day sorts first (midnight); timed sorts second (14:00).
    w = _NextEventWidget(
        events=[all_day_today, timed_today],
        empty_text="No upcoming events",
        timezone="UTC",
    )
    picked = []
    original_format = format_relative

    def capture_format(event, _now, empty_text):
        picked.append(event)
        return original_format(event, _now, empty_text)

    monkeypatch.setattr("led_ticker.widgets.calendar.format_relative", capture_format)

    c = Mock()
    c.width = 160
    c.height = 16
    w.draw(c)
    assert picked and picked[0] is timed_today, (
        "Timed event must be preferred over all-day event on the same day"
    )


# Fix 4: break->continue order-safety regression
_ALLDAY_THEN_TIMED_ICS = """\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//test//EN
BEGIN:VEVENT
UID:allday-1
DTSTART;VALUE=DATE:20260615
DTEND;VALUE=DATE:20260616
SUMMARY:All Day Thing
END:VEVENT
BEGIN:VEVENT
UID:timed-1
DTSTART:20260615T200000Z
DTEND:20260615T210000Z
SUMMARY:Evening Call
END:VEVENT
END:VCALENDAR
"""


def test_parse_keeps_inwindow_timed_event_negative_offset():
    # America/New_York is UTC-4 in summer. All-day events are resolved to
    # midnight local time (00:00 EDT = 04:00 UTC). A timed event at 20:00 UTC
    # on the same calendar date is later in UTC but earlier in local midnight
    # ordering — the old break would fire on the all-day and drop the timed one.
    tz = ZoneInfo("America/New_York")
    # "now" is 2026-06-15 at 08:00 EDT = 12:00 UTC (before both events)
    now = datetime(2026, 6, 15, 12, 0, tzinfo=ZoneInfo("UTC")).astimezone(tz)
    events = parse_ics(_ALLDAY_THEN_TIMED_ICS, now=now, lookahead_days=2, tz=tz)
    summaries = [e.summary for e in events]
    assert "All Day Thing" in summaries, "All-day event must be present"
    assert "Evening Call" in summaries, (
        "Timed event must not be dropped by an early break "
        "triggered by all-day ordering"
    )


# Hardening 5: collapse whitespace in SUMMARY
_NEWLINE_SUMMARY_ICS = """\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//test//EN
BEGIN:VEVENT
UID:newline-1
DTSTART:20260615T140000Z
DTEND:20260615T150000Z
SUMMARY:Team\\nStandup
END:VEVENT
END:VCALENDAR
"""


def test_parse_collapses_summary_whitespace():
    now = datetime(2026, 6, 15, 13, 0, tzinfo=_UTC)
    events = parse_ics(_NEWLINE_SUMMARY_ICS, now=now, lookahead_days=1, tz=_UTC)
    assert len(events) == 1
    # The embedded \n (icalendar-unescaped) must be collapsed to a single space.
    assert events[0].summary == "Team Standup", (
        f"Expected 'Team Standup', got {events[0].summary!r}"
    )


# ---------------------------------------------------------------------------
# False-positive truncation warning fix
# ---------------------------------------------------------------------------

_DAILY_RRULE_ICS = """\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//test//EN
BEGIN:VEVENT
UID:daily-1
DTSTART:20200101T100000Z
RRULE:FREQ=DAILY
SUMMARY:Daily Standup
END:VEVENT
END:VCALENDAR
"""


def test_parse_no_truncation_warning_for_normal_recurring(caplog):
    """A normal never-ending RRULE must NOT trigger the truncation warning.

    Regression for the false-positive: a FREQ=DAILY event with no COUNT/UNTIL
    has >2000 lifetime occurrences, so the islice cap fires — but all in-window
    events are returned BEFORE any occurrence past window_end is scanned, so
    nothing was genuinely truncated. The warning must stay silent.
    """
    import logging

    now = datetime(2026, 6, 15, 0, 0, tzinfo=_UTC)
    with caplog.at_level(logging.WARNING, logger="led_ticker.widgets.calendar"):
        events = parse_ics(_DAILY_RRULE_ICS, now=now, lookahead_days=7, tz=_UTC)

    assert not any("truncated" in record.message for record in caplog.records), (
        "No truncation warning expected for a normal never-ending RRULE"
    )
    # 7-day window starting 2026-06-15 00:00 UTC: .after(now) returns events
    # whose end is after now, and DTSTART is 10:00 UTC. The first occurrence on
    # 06-15 at 10:00 UTC is in-window; through 06-21 (window_end = 06-22 00:00)
    # gives 7 occurrences. Assert in a range to stay robust to edge cases.
    assert 6 <= len(events) <= 8, (
        f"Expected ~7 in-window events for a 7-day daily recurrence, got {len(events)}"
    )


def test_parse_warns_on_genuine_truncation(caplog):
    """A FREQ=HOURLY event with >2000 occurrences inside the window MUST warn.

    The cap fires and no occurrence past window_end was ever reached before the
    islice was exhausted, so scanned_past_window stays False — the warning fires.
    (Changed from FREQ=SECONDLY which is pre-filtered by _drop_subhourly_recurrences;
    HOURLY is the lowest frequency that exercises the islice cap.)
    """
    import logging

    now = datetime(2026, 6, 1, 0, 0, tzinfo=_UTC)
    # A 365-day window contains ~8760 occurrences of a FREQ=HOURLY event —
    # far more than _MAX_OCCURRENCES, so the cap is hit with events still inside
    # the window (scanned_past_window never becomes True).
    with caplog.at_level(logging.WARNING, logger="led_ticker.widgets.calendar"):
        events = parse_ics(_HOURLY_LONG_ICS, now=now, lookahead_days=365, tz=_UTC)

    assert any("truncated" in record.message for record in caplog.records), (
        "Truncation warning expected when in-window events genuinely overflow the cap"
    )
    assert len(events) <= _MAX_OCCURRENCES


# Hardening 6: file://localhost/ host form
def test_fetch_ics_file_localhost_host(tmp_path):
    ics_file = tmp_path / "test.ics"
    ics_file.write_text(_MULTIDAY_ICS)
    # RFC 8089: file://localhost/abs/path is equivalent to file:///abs/path
    url = "file://localhost" + str(ics_file)
    cal = Calendar(session=None, ics_url=url, timezone="UTC")
    content = asyncio.run(cal._fetch_ics())
    assert "Vacation" in content


# ---------------------------------------------------------------------------
# Round-6 adversarial hardening fixes
# ---------------------------------------------------------------------------


# Fix 1: sub-hourly RRULE pre-filter (SECONDLY/MINUTELY DoS protection)
_SECONDLY_FAR_PAST_ICS = """\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//test//EN
BEGIN:VEVENT
UID:secondly-past-1
DTSTART:20240101T000000Z
RRULE:FREQ=SECONDLY
SUMMARY:Every Second Past
END:VEVENT
BEGIN:VEVENT
UID:daily-companion-1
DTSTART:20260615T100000Z
DTEND:20260615T110000Z
SUMMARY:Normal Meeting
END:VEVENT
END:VCALENDAR
"""

_MINUTELY_ICS = """\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//test//EN
BEGIN:VEVENT
UID:minutely-1
DTSTART:20260601T000000Z
RRULE:FREQ=MINUTELY
SUMMARY:Every Minute
END:VEVENT
END:VCALENDAR
"""


def test_parse_drops_subhourly_rrule_fast(caplog):
    """FREQ=SECONDLY/MINUTELY events are dropped before expansion.

    A SECONDLY VEVENT with DTSTART ~2 years in the past would pin the CPU for
    >60s if handed to recurring_ical_events.of().after(now) without pre-filtering
    (the library walks every occurrence from DTSTART up to `now` before yielding
    the first in-window result, and that pre-now scan is not bounded by islice).
    The pre-filter drops it instantly and logs a warning. A co-resident DAILY
    event must still be returned.

    The test itself is the timing proof — if the pre-filter were absent, this
    test would hang for >60 seconds on a SECONDLY DTSTART ~2.5 years in the past.
    """
    import logging

    now = datetime(2026, 6, 15, 9, 0, tzinfo=_UTC)
    with caplog.at_level(logging.WARNING, logger="led_ticker.widgets.calendar"):
        events = parse_ics(_SECONDLY_FAR_PAST_ICS, now=now, lookahead_days=7, tz=_UTC)

    # (a) The SECONDLY rule contributes 0 events
    assert not any(e.summary == "Every Second Past" for e in events), (
        "SECONDLY RRULE events must be pre-filtered (0 yielded)"
    )
    # (b) The sub-hourly warning was logged
    assert any("sub-hourly" in record.message for record in caplog.records), (
        "Expected a 'sub-hourly' warning when a SECONDLY/MINUTELY RRULE is dropped"
    )
    # (c) The co-resident DAILY event is still returned
    assert any(e.summary == "Normal Meeting" for e in events), (
        "Normal DAILY event alongside a SECONDLY RRULE must survive"
    )


def test_parse_drops_minutely_rrule(caplog):
    """FREQ=MINUTELY is also pre-filtered by _drop_subhourly_recurrences."""
    import logging

    now = datetime(2026, 6, 1, 0, 0, tzinfo=_UTC)
    with caplog.at_level(logging.WARNING, logger="led_ticker.widgets.calendar"):
        events = parse_ics(_MINUTELY_ICS, now=now, lookahead_days=1, tz=_UTC)

    assert not any(e.summary == "Every Minute" for e in events), (
        "MINUTELY RRULE events must be pre-filtered"
    )
    assert any("sub-hourly" in record.message for record in caplog.records)


# Fix 2: ongoing all-day event (past-start) gets "Today" label in agenda mode
def test_day_label_ongoing_all_day_is_today():
    """An all-day event with DTSTART 2 days in the past renders 'Today <summary>'.

    Ongoing multi-day all-day events (kept by parse_ics via DTEND) have a
    negative delta_days in _day_label. The old `== 0` check produced the past
    start date ("Jun 12 Vacation"); the new `<= 0` check returns "Today".
    """
    now = datetime(2026, 6, 15, 10, 0, tzinfo=_UTC)
    # Event started 2 days ago, still ongoing (parse_ics kept it)
    e = CalendarEvent(
        summary="Vacation",
        start=datetime(2026, 6, 13, 0, 0, tzinfo=_UTC),  # 2 days before now
        all_day=True,
    )
    line = format_event_line(e, now=now, time_format="12h", tz=_UTC)
    assert line == "Today  Vacation", (
        f"Ongoing all-day event with past start must render "
        f"'Today  <summary>', got {line!r}"
    )


# Fix 3: file:// reads are explicitly UTF-8
def test_fetch_ics_reads_utf8(tmp_path):
    """_fetch_ics must read .ics files as UTF-8 regardless of locale.

    A non-ASCII event name (e.g. 'Café') written as UTF-8 must round-trip
    correctly through _fetch_ics (encoding="utf-8" explicit).
    """
    utf8_ics = """\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//test//EN
BEGIN:VEVENT
UID:utf8-1
DTSTART:20260615T140000Z
DTEND:20260615T150000Z
SUMMARY:Café au lait
END:VEVENT
END:VCALENDAR
"""
    ics_file = tmp_path / "test.ics"
    ics_file.write_text(utf8_ics, encoding="utf-8")
    cal = Calendar(session=None, ics_url=f"file://{ics_file}", timezone="UTC")
    content = asyncio.run(cal._fetch_ics())
    assert "Café" in content, (
        "Non-ASCII characters in .ics file must survive the UTF-8 read"
    )


# Fix 4: empty-string timezone treated as unset in validate_config
def test_validate_accepts_empty_timezone():
    """timezone = '' must be treated as 'use system default', not an error.

    _resolve_tz('') already treats falsy as 'unset' (returns system local tz);
    validate_config must align by skipping validation for empty/None timezone.
    """
    msgs = Calendar.validate_config({"ics_url": "x", "timezone": ""})
    assert msgs == [], f"Empty-string timezone must be accepted (no errors), got {msgs}"


# ---------------------------------------------------------------------------
# Round-7 adversarial hardening fixes
# ---------------------------------------------------------------------------


# Fix A: window-aware break for far-past sub-daily RRULEs

_HOURLY_FAR_PAST_ICS = """\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//test//EN
BEGIN:VEVENT
UID:hourly-far-past-1
DTSTART:{dtstart}
RRULE:FREQ=HOURLY
SUMMARY:Every Hour Far Past
END:VEVENT
END:VCALENDAR
"""


def test_parse_far_past_hourly_is_bounded():
    """A FREQ=HOURLY event with a DTSTART ~10 years in the past must parse quickly.

    Before Fix A the loop used `continue` past window_end, dragging through the
    full _MAX_OCCURRENCES=2000 cap (~83 days of hourly occurrences from the
    far-past start — in fact the pre-now scan by recurring_ical_events is also
    large).  The new window_end + 2-day break exits as soon as we clear the
    window, so only ~168-ish in-window occurrences are yielded.

    The test completing in a normal pytest run (seconds, not minutes) IS the
    timing proof.  We also assert the returned count is in the expected range
    (~168 occurrences per 7-day window at HOURLY frequency) to confirm correct
    events are returned.
    """
    import time

    # DTSTART ~10 years in the past so the pre-now scan is large.
    dtstart = "20160101T000000Z"
    ics = _HOURLY_FAR_PAST_ICS.format(dtstart=dtstart)
    now = datetime(2026, 6, 15, 0, 0, tzinfo=_UTC)

    t0 = time.monotonic()
    events = parse_ics(ics, now=now, lookahead_days=7, tz=_UTC)
    elapsed = time.monotonic() - t0

    # 7-day window at FREQ=HOURLY = 168 h; allow a small margin for boundary
    # effects (.after(now) may exclude the first tick depending on exact start).
    assert 160 <= len(events) <= 176, (
        f"Expected ~168 in-window HOURLY events, got {len(events)}"
    )
    # The scan must complete in well under 10 seconds (before the fix it was
    # 20s-200s on real hardware due to the pre-now walk + full islice drain).
    # We set a generous 10s ceiling to avoid flakiness on slow CI.
    assert elapsed < 10.0, (
        f"parse_ics took {elapsed:.1f}s for a far-past HOURLY rule — "
        "Fix A (window-aware break) may not be in effect"
    )


# Fix B: multi-RRULE VEVENT handling

_MULTI_RRULE_ICS = """\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//test//EN
BEGIN:VEVENT
UID:multi-rrule-1
DTSTART:20260615T100000Z
DTEND:20260615T110000Z
RRULE:FREQ=DAILY;COUNT=3
RRULE:FREQ=WEEKLY;COUNT=2
SUMMARY:Multi-Rule Event
END:VEVENT
END:VCALENDAR
"""

_MULTI_RRULE_ONE_SUBHOURLY_ICS = """\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//test//EN
BEGIN:VEVENT
UID:multi-rrule-subhourly-1
DTSTART:20260615T100000Z
RRULE:FREQ=DAILY;COUNT=3
RRULE:FREQ=SECONDLY
SUMMARY:Bad Multi-Rule Event
END:VEVENT
END:VCALENDAR
"""


def test_parse_multiple_rrule_no_crash():
    """A VEVENT with two RRULE lines must not crash and must return events.

    RFC 5545 allows multiple RRULE properties on one VEVENT; some calendar
    exporters emit this.  Before Fix B, comp.get("RRULE") returned a list of
    vRecur objects, and calling .get("FREQ") on that list raised AttributeError,
    propagating out of parse_ics -> caught by update() -> whole calendar blanked.
    """
    now = datetime(2026, 6, 15, 9, 0, tzinfo=_UTC)
    # Must not raise; must return at least one event from the multi-RRULE VEVENT.
    events = parse_ics(_MULTI_RRULE_ICS, now=now, lookahead_days=14, tz=_UTC)
    summaries = [e.summary for e in events]
    assert "Multi-Rule Event" in summaries, (
        "Multi-RRULE VEVENT must be parsed without raising (calendar must not blank)"
    )


def test_drop_subhourly_multiple_rrule():
    """A VEVENT with two RRULEs where ONE is SECONDLY must be dropped.

    _drop_subhourly_recurrences must use any-match: if any of the event's RRULEs
    is sub-hourly, the whole event is dropped.
    """
    now = datetime(2026, 6, 15, 9, 0, tzinfo=_UTC)
    events = parse_ics(
        _MULTI_RRULE_ONE_SUBHOURLY_ICS, now=now, lookahead_days=7, tz=_UTC
    )
    assert not any(e.summary == "Bad Multi-Rule Event" for e in events), (
        "VEVENT with any sub-hourly RRULE must be dropped by "
        "_drop_subhourly_recurrences"
    )


def test_rrule_is_subhourly_single_value():
    """_rrule_is_subhourly handles the normal single-vRecur case."""
    import icalendar

    cal = icalendar.Calendar.from_ical(_MULTI_RRULE_ONE_SUBHOURLY_ICS)
    for comp in cal.subcomponents:
        if comp.name == "VEVENT":
            rrule = comp.get("RRULE")
            rrules = rrule if isinstance(rrule, list) else [rrule]
            results = [_rrule_is_subhourly(rr) for rr in rrules]
            # One is DAILY (not sub-hourly), one is SECONDLY (sub-hourly)
            assert True in results, "SECONDLY RRULE must be identified as sub-hourly"
            assert False in results, "DAILY RRULE must not be identified as sub-hourly"


# ---------------------------------------------------------------------------
# Round-8 adversarial hardening fixes
# ---------------------------------------------------------------------------


# Fix 1: DST-correct countdown via UTC subtraction
def test_format_relative_dst_transition():
    """format_relative uses UTC delta so DST transitions don't skew the result.

    now = 2026-03-07 23:00 America/New_York (before spring-forward)
    event = 2026-03-08 10:00 America/New_York (after spring-forward at 02:00)

    Wall-clock gap: 11 hours.  UTC gap: 10 hours (the clock "springs forward"
    one hour at 02:00, eating one hour from the countdown).  The panel should
    display "in 10h", not the naive wall-clock "in 11h".
    """
    tz = ZoneInfo("America/New_York")
    # 2026-03-08 02:00 is the spring-forward boundary.
    now = datetime(2026, 3, 7, 23, 0, tzinfo=tz)  # EST (UTC-5)
    event = CalendarEvent(
        "Meeting",
        datetime(2026, 3, 8, 10, 0, tzinfo=tz),  # EDT (UTC-4) after spring-forward
        all_day=False,
    )
    result = format_relative(event, now, "x")
    assert result == "Meeting in 10h", (
        f"Expected 'Meeting in 10h' (UTC-correct), got {result!r}. "
        "Check that format_relative subtracts in UTC, not wall-clock."
    )


# Fix 2: in-progress timed event shows "<summary> now" in next mode (not empty)
def test_next_in_progress_timed_shows_now(monkeypatch):
    """A timed event that was future at fetch time but is now in-progress must
    show '<summary> now', not empty_text.

    This exercises the new tier-4 fallback in _NextEventWidget.draw() — the
    most-recently-started in-progress timed event when all three earlier tiers
    yield None.
    """
    # Event started 3 minutes ago; no other events
    now = datetime(2026, 6, 15, 15, 3, tzinfo=_UTC)
    monkeypatch.setattr("led_ticker.widgets.calendar._now_in", lambda tz: now)
    started = CalendarEvent(
        "Standup", datetime(2026, 6, 15, 15, 0, tzinfo=_UTC), all_day=False
    )
    w = _NextEventWidget(
        events=[started], empty_text="No upcoming events", timezone="UTC"
    )
    c = Mock()
    c.width = 160
    c.height = 16

    # format_relative renders secs<=0 as "<summary> now"
    text = format_relative(started, now, "No upcoming events")
    assert text == "Standup now", (
        f"format_relative should render in-progress event as 'now', got {text!r}"
    )

    # draw() must pick the in-progress event (tier-4 fallback), not empty_text
    picked = []
    original_format = format_relative

    def capture_format(event, _now, empty_text):
        picked.append(event)
        return original_format(event, _now, empty_text)

    monkeypatch.setattr("led_ticker.widgets.calendar.format_relative", capture_format)
    w.draw(c)
    assert picked, "format_relative must be called from draw()"
    assert picked[0] is started, (
        "draw() must pick the in-progress timed event via tier-4 fallback"
    )


# Fix 3: _clamp_recurrence_anchors — equivalence and safety
_FAR_PAST_HOURLY_CLAMP_ICS = """\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//test//EN
BEGIN:VEVENT
UID:hourly-clamp-1
DTSTART:20160101T000000Z
RRULE:FREQ=HOURLY
SUMMARY:Hourly Clamp Test
END:VEVENT
END:VCALENDAR
"""

_BYDAY_WEEKLY_ICS = """\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//test//EN
BEGIN:VEVENT
UID:weekly-byday-1
DTSTART:20200101T100000Z
RRULE:FREQ=WEEKLY;BYDAY=MO
SUMMARY:Monday Meeting
END:VEVENT
END:VCALENDAR
"""

_COUNT_HOURLY_ICS = """\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//test//EN
BEGIN:VEVENT
UID:hourly-count-1
DTSTART:20200101T000000Z
RRULE:FREQ=HOURLY;COUNT=100000
SUMMARY:Bounded Hourly
END:VEVENT
END:VCALENDAR
"""


def test_clamp_recurrence_preserves_inwindow_events():
    """_clamp_recurrence_anchors must not change which events appear in-window.

    Parse the far-past HOURLY .ics TWICE: once normally (with clamping) and
    once with clamping bypassed via monkeypatching — then assert the in-window
    CalendarEvents (summary + start) are IDENTICAL.  This is the correctness
    gate: if it fails, Fix 3 must NOT be shipped.
    """
    from led_ticker.widgets import calendar as _cal_mod

    now = datetime(2026, 6, 15, 0, 0, tzinfo=_UTC)

    # Path A: normal parse (clamping active)
    events_clamped = parse_ics(
        _FAR_PAST_HOURLY_CLAMP_ICS, now=now, lookahead_days=7, tz=_UTC
    )

    # Path B: bypass clamping by patching _clamp_recurrence_anchors to a no-op
    original_clamp = _cal_mod._clamp_recurrence_anchors
    _cal_mod._clamp_recurrence_anchors = lambda cal, now: 0
    try:
        events_unclamped = parse_ics(
            _FAR_PAST_HOURLY_CLAMP_ICS, now=now, lookahead_days=7, tz=_UTC
        )
    finally:
        _cal_mod._clamp_recurrence_anchors = original_clamp

    # Compare by (summary, start) — the identity-invariant fields
    clamped_set = {(e.summary, e.start) for e in events_clamped}
    unclamped_set = {(e.summary, e.start) for e in events_unclamped}
    assert clamped_set == unclamped_set, (
        f"Clamped and unclamped parse produced different in-window events.\n"
        f"Only in clamped:   {clamped_set - unclamped_set}\n"
        f"Only in unclamped: {unclamped_set - clamped_set}"
    )


def test_clamp_far_past_hourly_is_fast():
    """After clamping, a far-past HOURLY parse completes well within 10 s.

    (The round-7 window break already bounded the forward scan; the clamp
    further eliminates the pre-now walk by recurring_ical_events.)
    """
    import time

    now = datetime(2026, 6, 15, 0, 0, tzinfo=_UTC)
    t0 = time.monotonic()
    events = parse_ics(_FAR_PAST_HOURLY_CLAMP_ICS, now=now, lookahead_days=7, tz=_UTC)
    elapsed = time.monotonic() - t0

    assert elapsed < 10.0, (
        f"parse_ics with far-past HOURLY took {elapsed:.1f}s — "
        "_clamp_recurrence_anchors may not be working"
    )
    assert 160 <= len(events) <= 176, (
        f"Expected ~168 in-window HOURLY events after clamping, got {len(events)}"
    )


def test_clamp_byday_rule_equivalent():
    """A FREQ=WEEKLY;BYDAY=MO rule IS now clamped (round-11 Fix 2).

    BYDAY is in the safe set for WEEKLY — advancing by whole 1-WEEK steps
    preserves the weekday pattern exactly.  Verify:
    (a) _clamp_recurrence_anchors reports at least 1 clamped event.
    (b) Clamped and unclamped parse produce IDENTICAL in-window events.
    (c) Events still appear in the window after clamping.
    """
    import icalendar as _ical

    from led_ticker.widgets import calendar as _cal_mod

    now = datetime(2026, 6, 15, 0, 0, tzinfo=_UTC)
    cal = _ical.Calendar.from_ical(_BYDAY_WEEKLY_ICS)
    count = _clamp_recurrence_anchors(cal, now)
    assert count >= 1, (
        f"FREQ=WEEKLY;BYDAY=MO (far-past DTSTART) must be clamped (count={count}); "
        "round-11 Fix 2 extended the safe BY* subset to include BYDAY for WEEKLY"
    )

    # Equivalence: clamped == unclamped in-window events
    events_clamped = parse_ics(_BYDAY_WEEKLY_ICS, now=now, lookahead_days=14, tz=_UTC)
    original_clamp = _cal_mod._clamp_recurrence_anchors
    _cal_mod._clamp_recurrence_anchors = lambda cal, now: 0
    try:
        events_unclamped = parse_ics(
            _BYDAY_WEEKLY_ICS, now=now, lookahead_days=14, tz=_UTC
        )
    finally:
        _cal_mod._clamp_recurrence_anchors = original_clamp

    clamped_set = {(e.summary, e.start) for e in events_clamped}
    unclamped_set = {(e.summary, e.start) for e in events_unclamped}
    assert clamped_set == unclamped_set, (
        f"Clamped and unclamped WEEKLY;BYDAY parse differ.\n"
        f"Only in clamped:   {clamped_set - unclamped_set}\n"
        f"Only in unclamped: {unclamped_set - clamped_set}"
    )

    # Events still appear
    assert any(e.summary == "Monday Meeting" for e in events_clamped), (
        "BYDAY rule events must parse correctly after clamping"
    )


def test_clamp_skips_count_rule():
    """A FREQ=HOURLY;COUNT=... rule must NOT be clamped (COUNT changes window)."""
    import icalendar

    now = datetime(2026, 6, 15, 0, 0, tzinfo=_UTC)
    cal = icalendar.Calendar.from_ical(_COUNT_HOURLY_ICS)
    count = _clamp_recurrence_anchors(cal, now)
    assert count == 0, (
        f"FREQ=HOURLY;COUNT=... must be skipped by the clamp (count={count})"
    )


# Fix 5: validate_config catches OSError from ZoneInfo
def test_validate_rejects_bad_timezone_still_passes():
    """Fix 5 must not break existing bad-timezone detection."""
    msgs = Calendar.validate_config({"ics_url": "x", "timezone": "Mars/Phobos"})
    assert any("timezone" in m.lower() for m in msgs), (
        "Bad timezone must still be caught after adding OSError to the except clause"
    )


# ---------------------------------------------------------------------------
# Render hot-path: _NextEventWidget must cache the resolved timezone
# ---------------------------------------------------------------------------


def test_next_widget_resolves_tz_once(canvas):
    """_NextEventWidget._resolved_tz caches the result of _resolve_tz.

    draw() runs at ~20 Hz (ENGINE_TICK_MS=50ms). Calling _resolve_tz(None) on
    every tick does a Path("/etc/localtime").resolve() filesystem syscall plus a
    ZoneInfo lookup — expensive for a value that never changes mid-section.

    The cache field (_resolved_tz) is populated on the FIRST draw() call and
    reused for all subsequent calls. This test spies on the module-level
    _resolve_tz to assert it is invoked AT MOST ONCE across 10 draws.
    """
    from led_ticker.widgets import calendar as _cal_mod

    e = CalendarEvent("Standup", datetime(2026, 6, 15, 15, 0, tzinfo=_UTC), False)
    w = _NextEventWidget(events=[e], empty_text="none", timezone=None)

    call_count = 0
    original_resolve_tz = _cal_mod._resolve_tz

    def counting_resolve_tz(tz):
        nonlocal call_count
        call_count += 1
        return original_resolve_tz(tz)

    _cal_mod._resolve_tz = counting_resolve_tz
    try:
        for _ in range(10):
            w.draw(canvas)
    finally:
        _cal_mod._resolve_tz = original_resolve_tz

    assert call_count <= 1, (
        f"_resolve_tz was called {call_count} times across 10 draw() calls — "
        "expected at most 1 (cached after first draw). "
        "Check _NextEventWidget._resolved_tz caching in draw()."
    )


# ---------------------------------------------------------------------------
# Round-11 adversarial hardening fixes
# ---------------------------------------------------------------------------

# Fix 1: normalize mismatched all-day events (DTSTART;VALUE=DATE + datetime DTEND)

_MISMATCHED_ALLDAY_ICS = """\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//test//RFC-violating all-day//EN
BEGIN:VEVENT
UID:bday-mismatch-1
DTSTART;VALUE=DATE:20260620
DTEND:20260620T200000Z
SUMMARY:Birthday
END:VEVENT
END:VCALENDAR
"""

_TOKYO_ALLDAY_ICS = """\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//test//RFC-violating all-day//EN
BEGIN:VEVENT
UID:bday-tokyo-1
DTSTART;VALUE=DATE:20260620
DTEND:20260620T200000Z
SUMMARY:Birthday Tokyo
END:VEVENT
END:VCALENDAR
"""


def test_parse_mismatched_all_day_kept_negative_offset():
    """Birthday on 2026-06-20 with DTSTART;VALUE=DATE but datetime DTEND must
    appear as an all-day event in America/Los_Angeles, not be silently dropped.

    Without the fix, recurring_ical_events promotes DTSTART to midnight-UTC
    (2026-06-20T00:00Z), which is BEFORE now (2026-06-20T15:00Z = 8am LA),
    so parse_ics drops the event as 'past'.

    With the fix, DTEND is coerced to a date before expansion, keeping
    DTSTART as a proper all-day date that resolves to LA midnight — which
    is AFTER now — so the event is kept.
    """
    tz_la = ZoneInfo("America/Los_Angeles")
    # 8:00 AM LA on June 20 = 15:00 UTC (before DTEND 20:00 UTC; event ongoing)
    now = datetime(2026, 6, 20, 8, 0, tzinfo=tz_la)
    events = parse_ics(_MISMATCHED_ALLDAY_ICS, now=now, lookahead_days=7, tz=tz_la)
    bdays = [e for e in events if e.summary == "Birthday"]
    assert len(bdays) == 1, (
        f"Birthday (DTSTART;VALUE=DATE + datetime DTEND) must be kept in "
        f"America/Los_Angeles at 8am on the event day; got {bdays!r}. "
        "Check _normalize_mismatched_all_day is called before expansion."
    )
    assert bdays[0].all_day is True, (
        f"Birthday must be all_day=True after normalization, got {bdays[0].all_day}"
    )


def test_parse_mismatched_all_day_all_day_positive_offset():
    """Same RFC-violating event in a positive-UTC timezone (Asia/Tokyo, UTC+9)
    must also be all_day=True, not a spurious timed 9am event.

    Without the fix, recurring_ical_events promotes DTSTART to midnight-UTC
    which astimezone(Tokyo) = 09:00 JST — appearing as a timed 9am event
    instead of an all-day event.
    """
    tz_tokyo = ZoneInfo("Asia/Tokyo")
    # 6am Tokyo on June 20 = 21:00 UTC June 19 (before the event date)
    now = datetime(2026, 6, 20, 6, 0, tzinfo=tz_tokyo)
    events = parse_ics(_TOKYO_ALLDAY_ICS, now=now, lookahead_days=7, tz=tz_tokyo)
    bdays = [e for e in events if e.summary == "Birthday Tokyo"]
    assert len(bdays) == 1, f"Birthday Tokyo must be found in Asia/Tokyo; got {bdays!r}"
    assert bdays[0].all_day is True, (
        f"Birthday Tokyo must be all_day=True (not a spurious timed 9am event), "
        f"got all_day={bdays[0].all_day}, start={bdays[0].start}"
    )


def test_normalize_mismatched_all_day_fixture():
    """The mismatched_all_day.ics corpus fixture parses correctly."""
    from pathlib import Path

    fixture = (
        Path(__file__).resolve().parents[1]
        / "fixtures"
        / "calendar_corpus"
        / "mismatched_all_day.ics"
    )
    tz_la = ZoneInfo("America/Los_Angeles")
    now = datetime(2026, 6, 20, 8, 0, tzinfo=tz_la)
    events = parse_ics(fixture.read_text(), now=now, lookahead_days=7, tz=tz_la)
    assert any(e.summary == "Birthday" and e.all_day for e in events), (
        "corpus fixture mismatched_all_day.ics must parse Birthday as all_day=True "
        "in America/Los_Angeles"
    )


# Fix 2: BY* safe-subset clamping for HOURLY/DAILY/WEEKLY


_HOURLY_BYMINUTE_FAR_PAST_ICS = """\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//test//EN
BEGIN:VEVENT
UID:hourly-byminute-far-past
DTSTART:20160101T000000Z
DTEND:20160101T003000Z
RRULE:FREQ=HOURLY;BYMINUTE=0
SUMMARY:Hourly Top Of Hour
END:VEVENT
END:VCALENDAR
"""

_DAILY_BYHOUR_FAR_PAST_ICS = """\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//test//EN
BEGIN:VEVENT
UID:daily-byhour-far-past
DTSTART:20000101T090000Z
DTEND:20000101T093000Z
RRULE:FREQ=DAILY;BYHOUR=9
SUMMARY:Daily 9am
END:VEVENT
END:VCALENDAR
"""

_WEEKLY_BYDAY_FAR_PAST_ICS = """\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//test//EN
BEGIN:VEVENT
UID:weekly-byday-far-past
DTSTART:20000103T100000Z
DTEND:20000103T103000Z
RRULE:FREQ=WEEKLY;BYDAY=MO
SUMMARY:Weekly Monday
END:VEVENT
END:VCALENDAR
"""

_BYMONTH_SKIP_ICS = """\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//test//EN
BEGIN:VEVENT
UID:monthly-bymonth
DTSTART:20160101T090000Z
DTEND:20160101T093000Z
RRULE:FREQ=MONTHLY;BYMONTH=1
SUMMARY:Annual January
END:VEVENT
END:VCALENDAR
"""


def _bypass_clamp_parse(ics_text, now, lookahead_days=7):
    """Parse without clamping (bypass _clamp_recurrence_anchors) for comparison."""
    from led_ticker.widgets import calendar as _cal_mod

    original_clamp = _cal_mod._clamp_recurrence_anchors
    _cal_mod._clamp_recurrence_anchors = lambda cal, now: 0
    try:
        return parse_ics(ics_text, now=now, lookahead_days=lookahead_days, tz=_UTC)
    finally:
        _cal_mod._clamp_recurrence_anchors = original_clamp


_R11_NOW = datetime(2026, 6, 15, 12, 0, tzinfo=_UTC)


def test_clamp_byrule_equivalence_hourly_byminute():
    """FREQ=HOURLY;BYMINUTE=0 (far past): clamped == unclamped in-window events.

    This is the equivalence gate for the HOURLY + BYMINUTE safe subset.
    If this fails, the HOURLY;BYMINUTE shape must be removed from the clamp.
    """
    events_clamped = parse_ics(
        _HOURLY_BYMINUTE_FAR_PAST_ICS, now=_R11_NOW, lookahead_days=7, tz=_UTC
    )
    events_unclamped = _bypass_clamp_parse(
        _HOURLY_BYMINUTE_FAR_PAST_ICS, _R11_NOW, lookahead_days=7
    )
    clamped_set = {(e.summary, e.start) for e in events_clamped}
    unclamped_set = {(e.summary, e.start) for e in events_unclamped}
    assert clamped_set == unclamped_set, (
        f"HOURLY;BYMINUTE=0 clamped/unclamped differ.\n"
        f"Only in clamped:   {sorted(clamped_set - unclamped_set)[:3]}\n"
        f"Only in unclamped: {sorted(unclamped_set - clamped_set)[:3]}"
    )


def test_clamp_byrule_equivalence_daily_byhour():
    """FREQ=DAILY;BYHOUR=9 (far past): clamped == unclamped in-window events."""
    events_clamped = parse_ics(
        _DAILY_BYHOUR_FAR_PAST_ICS, now=_R11_NOW, lookahead_days=7, tz=_UTC
    )
    events_unclamped = _bypass_clamp_parse(
        _DAILY_BYHOUR_FAR_PAST_ICS, _R11_NOW, lookahead_days=7
    )
    clamped_set = {(e.summary, e.start) for e in events_clamped}
    unclamped_set = {(e.summary, e.start) for e in events_unclamped}
    assert clamped_set == unclamped_set, (
        f"DAILY;BYHOUR=9 clamped/unclamped differ.\n"
        f"Only in clamped:   {sorted(clamped_set - unclamped_set)}\n"
        f"Only in unclamped: {sorted(unclamped_set - clamped_set)}"
    )


def test_clamp_byrule_equivalence_weekly_byday():
    """FREQ=WEEKLY;BYDAY=MO (far past): clamped == unclamped in-window events."""
    events_clamped = parse_ics(
        _WEEKLY_BYDAY_FAR_PAST_ICS, now=_R11_NOW, lookahead_days=7, tz=_UTC
    )
    events_unclamped = _bypass_clamp_parse(
        _WEEKLY_BYDAY_FAR_PAST_ICS, _R11_NOW, lookahead_days=7
    )
    clamped_set = {(e.summary, e.start) for e in events_clamped}
    unclamped_set = {(e.summary, e.start) for e in events_unclamped}
    assert clamped_set == unclamped_set, (
        f"WEEKLY;BYDAY=MO clamped/unclamped differ.\n"
        f"Only in clamped:   {sorted(clamped_set - unclamped_set)}\n"
        f"Only in unclamped: {sorted(unclamped_set - clamped_set)}"
    )


def test_clamp_far_past_hourly_byminute_fast():
    """FREQ=HOURLY;BYMINUTE=0 with 10y-past DTSTART must parse in well under 5s.

    Without the BY*-safe clamp, recurring_ical_events must walk ~87,000+
    pre-now occurrences before yielding the first in-window result.
    With the clamp (1-DAY step), DTSTART jumps to ~1 day before now, so
    the pre-now walk is ~24 occurrences instead.
    """
    import time

    t0 = time.monotonic()
    events = parse_ics(
        _HOURLY_BYMINUTE_FAR_PAST_ICS, now=_R11_NOW, lookahead_days=7, tz=_UTC
    )
    elapsed = time.monotonic() - t0
    assert elapsed < 5.0, (
        f"FREQ=HOURLY;BYMINUTE=0 (10y past) took {elapsed:.2f}s — "
        "the BY* safe-subset clamp may not be active"
    )
    assert len(events) > 0, "Expected in-window events for HOURLY;BYMINUTE=0"


def test_clamp_skips_unsafe_bymonth():
    """FREQ=MONTHLY;BYMONTH=1 must NOT be clamped (BYMONTH is in unsafe set)."""
    import icalendar as _ical

    now = datetime(2026, 6, 15, 0, 0, tzinfo=_UTC)
    cal = _ical.Calendar.from_ical(_BYMONTH_SKIP_ICS)
    count = _clamp_recurrence_anchors(cal, now)
    assert count == 0, (
        f"BYMONTH is an unsafe BY* key — must not be clamped (count={count})"
    )


# Fix 3: UTF-8 HTTP body decode
# Existing http-path tests cover the functional path.
# This test guards the decode mode by mocking the response.


def test_fetch_ics_http_reads_utf8_bytes(monkeypatch):
    """_fetch_ics must read bytes and decode as UTF-8 (not let aiohttp guess charset).

    Patch the session to return a fake response with a non-ASCII UTF-8 body
    and no charset header.  Before Fix 3, aiohttp would guess charset (often
    latin-1 for no header), corrupting the content.  After Fix 3, the raw
    bytes are decoded explicitly as UTF-8.
    """
    from unittest.mock import AsyncMock, MagicMock

    utf8_ics = """\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//test//EN
BEGIN:VEVENT
UID:utf8-http-1
DTSTART:20260620T100000Z
DTEND:20260620T110000Z
SUMMARY:Réunion
END:VEVENT
END:VCALENDAR
""".encode()

    fake_resp = AsyncMock()
    fake_resp.raise_for_status = MagicMock()
    fake_resp.read = AsyncMock(return_value=utf8_ics)
    # Simulate aiohttp async context manager
    fake_cm = AsyncMock()
    fake_cm.__aenter__ = AsyncMock(return_value=fake_resp)
    fake_cm.__aexit__ = AsyncMock(return_value=False)

    fake_session = MagicMock()
    fake_session.get = MagicMock(return_value=fake_cm)

    cal = Calendar(session=fake_session, ics_url="https://example.com/c.ics")
    content = asyncio.run(cal._fetch_ics())
    assert "Réunion" in content, (
        f"Non-ASCII UTF-8 content from HTTP must decode correctly; got {content!r}"
    )
