"""Tests for the calendar widget."""

import asyncio
from datetime import datetime, tzinfo
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo

from led_ticker.widgets import get_widget_class
from led_ticker.widgets.calendar import (
    Calendar,
    CalendarEvent,
    TickerMessage,
    _match_any,
    _NextEventWidget,
    _resolve_tz,
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
    w = _NextEventWidget(event=e, empty_text="none", timezone="UTC")
    out_canvas, cursor = w.draw(canvas)
    assert out_canvas is canvas
    assert isinstance(cursor, int)


def test_next_event_widget_rainbow_advances_frame(canvas):
    from led_ticker.color_providers import Rainbow

    e = CalendarEvent("Standup", datetime(2026, 6, 15, 15, 0, tzinfo=_UTC), False)
    w = _NextEventWidget(
        event=e, empty_text="none", timezone="UTC", font_color=Rainbow()
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
    w = _NextEventWidget(event=e, empty_text="none", timezone=None)
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
