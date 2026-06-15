"""Guard 1 — Real-ICS corpus (class A: real-feed quirks).

Each fixture in tests/fixtures/calendar_corpus/ exercises one real-world
feed shape or quirk that was hardened against during the 8-round review.
These tests assert CURRENT correct behavior and are permanent regression guards.

``now`` is fixed per fixture so events are deterministically in-window.
"""

import asyncio
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from led_ticker.widgets.calendar import (
    Calendar,
    CalendarEvent,
    _TwoToneLine,
    parse_ics,
)

_CORPUS = Path(__file__).resolve().parents[1] / "fixtures" / "calendar_corpus"
_NY = ZoneInfo("America/New_York")
_UTC = ZoneInfo("UTC")

# ---------------------------------------------------------------------------
# Parametrized parse_ics corpus: (fixture_name, now, lookahead_days, tz, checks)
# ---------------------------------------------------------------------------

# Each "check" is a callable that receives the event list and raises AssertionError
# with a descriptive message if the expectation is violated.  Using callables
# rather than strings keeps each assertion close to its fixture definition and
# makes failures self-describing.


def _has_summary(events: list[CalendarEvent], summary: str) -> bool:
    return any(e.summary == summary for e in events)


def _no_summary(events: list[CalendarEvent], summary: str) -> bool:
    return not _has_summary(events, summary)


# ---- google_basic.ics -------------------------------------------------------
# A typical Google Calendar export with VTIMEZONE, timed events, and a
# FREQ=WEEKLY;BYDAY recurring event.  Fixed now is early-week so Monday/Wed/Fri
# standup occurrences fall within the 7-day lookahead.

_GOOGLE_NOW = datetime(2026, 6, 15, 8, 0, tzinfo=_NY)  # Monday 08:00 EDT


def _check_google_basic(events: list[CalendarEvent]) -> None:
    assert events, "google_basic.ics: expected at least one event in the 7-day window"
    assert all(e.start.tzinfo is not None for e in events), (
        "google_basic.ics: all parsed events must have tz-aware starts"
    )
    # The Quarterly Review on 2026-06-18 must be present.
    assert _has_summary(events, "Quarterly Review"), (
        "google_basic.ics: Quarterly Review event (June 18) must be in 7-day window"
    )
    # Events must be sorted chronologically.
    starts = [e.start for e in events]
    assert starts == sorted(starts), (
        "google_basic.ics: events must be sorted by start time"
    )


# ---- outlook_bom.ics --------------------------------------------------------
# Outlook/Exchange feeds begin with a UTF-8 BOM (U+FEFF). parse_ics must strip
# it before handing the text to icalendar.Calendar.from_ical.

_OUTLOOK_NOW = datetime(2026, 6, 15, 8, 0, tzinfo=_UTC)  # before both events


def _check_outlook_bom(events: list[CalendarEvent]) -> None:
    assert events, (
        "outlook_bom.ics: parse_ics must return events even when the file starts "
        "with a UTF-8 BOM"
    )
    summaries = {e.summary for e in events}
    assert "Budget Review" in summaries, (
        "outlook_bom.ics: Budget Review (June 17) must be parsed correctly"
    )
    assert "Team Offsite" in summaries, (
        "outlook_bom.ics: Team Offsite (June 19) must be parsed correctly"
    )


# ---- cancelled.ics ----------------------------------------------------------
# A STATUS:CANCELLED VEVENT must be silently dropped; the normal companion must
# still appear.

_CANCELLED_NOW = datetime(2026, 6, 15, 8, 0, tzinfo=_UTC)


def _check_cancelled(events: list[CalendarEvent]) -> None:
    assert _no_summary(events, "Cancelled Meeting"), (
        "cancelled.ics: STATUS:CANCELLED event must not appear in parsed results"
    )
    assert _has_summary(events, "Normal Meeting"), (
        "cancelled.ics: STATUS:CONFIRMED event must survive the cancelled-event filter"
    )
    assert len(events) == 1, (
        f"cancelled.ics: expected exactly 1 event (the normal one), got {len(events)}"
    )


# ---- multi_rrule.ics --------------------------------------------------------
# A VEVENT with TWO RRULE lines (RFC 5545 allows it; some Google exports emit
# this).  parse_ics must not raise, and must return at least one occurrence.

_MULTI_RRULE_NOW = datetime(2026, 6, 15, 9, 0, tzinfo=_UTC)


def _check_multi_rrule(events: list[CalendarEvent]) -> None:
    assert _has_summary(events, "Multi-Rule Event"), (
        "multi_rrule.ics: a VEVENT with two RRULE lines must parse without raising "
        "and return at least one occurrence"
    )


# ---- all_day_span.ics -------------------------------------------------------
# A multi-day all-day event (DTSTART;VALUE=DATE / DTEND;VALUE=DATE spanning
# multiple days).  The event must be present and flagged all_day=True.
# Fixed now = 2026-06-16 12:00 UTC (inside the Summer Vacation span 06-15..06-20).

_ALL_DAY_NOW = datetime(2026, 6, 16, 12, 0, tzinfo=_UTC)


def _check_all_day_span(events: list[CalendarEvent]) -> None:
    vacation = [e for e in events if e.summary == "Summer Vacation"]
    assert vacation, (
        "all_day_span.ics: Summer Vacation (06-15..06-20) must be present when "
        "now=06-16 is inside the span"
    )
    assert vacation[0].all_day is True, (
        "all_day_span.ics: Summer Vacation must have all_day=True"
    )
    # Tech Conference (single-day 06-18) must also be present (inside 7-day window).
    assert _has_summary(events, "Tech Conference"), (
        "all_day_span.ics: Tech Conference (06-18) must be present in 7-day window"
    )


# ---- summary_newline.ics ----------------------------------------------------
# A SUMMARY with an icalendar-escaped \n must be collapsed to a single space by
# parse_ics (via " ".join(summary.split())).

_NEWLINE_NOW = datetime(2026, 6, 15, 8, 0, tzinfo=_UTC)


def _check_summary_newline(events: list[CalendarEvent]) -> None:
    assert events, "summary_newline.ics: expected at least one event"
    for e in events:
        assert "\n" not in e.summary, (
            f"summary_newline.ics: event {e.summary!r} must have no raw newlines "
            "(icalendar \\n escape must be collapsed to space)"
        )
    assert _has_summary(events, "Team Standup"), (
        "summary_newline.ics: 'Team\\nStandup' must be collapsed to 'Team Standup'"
    )
    assert _has_summary(events, "Project Kickoff Meeting"), (
        "summary_newline.ics: 'Project\\nKickoff\\nMeeting' must collapse to "
        "'Project Kickoff Meeting'"
    )


# ---- non_ascii.ics ----------------------------------------------------------
# A SUMMARY with accented/Unicode characters (UTF-8 encoded). parse_ics must
# preserve the characters exactly.

_NON_ASCII_NOW = datetime(2026, 6, 15, 8, 0, tzinfo=_UTC)


def _check_non_ascii(events: list[CalendarEvent]) -> None:
    assert events, "non_ascii.ics: expected at least one event"
    assert _has_summary(events, "Café réunion ☕"), (
        "non_ascii.ics: accented/Unicode summary 'Café réunion ☕' must be preserved"
    )
    assert _has_summary(events, "Déjeuner d'équipe"), (
        "non_ascii.ics: accented summary 'Déjeuner d'équipe' must be preserved"
    )


# ---- floating_time.ics ------------------------------------------------------
# A VEVENT with a naive (floating, no TZID, no Z) DTSTART.
# _to_display_start must treat it as being in the display tz.

_FLOATING_NOW = datetime(2026, 6, 15, 8, 0, tzinfo=_NY)


def _check_floating_time(events: list[CalendarEvent]) -> None:
    assert events, (
        "floating_time.ics: floating-time (naive DTSTART) events must not be "
        "skipped; they should be treated as in the display timezone"
    )
    assert all(e.start.tzinfo is not None for e in events), (
        "floating_time.ics: all parsed events must have tz-aware starts "
        "(floating DTSTART resolved to display tz)"
    )
    assert _has_summary(events, "Floating Time Meeting"), (
        "floating_time.ics: 'Floating Time Meeting' must appear in results"
    )


# ---- recurring_daily.ics ----------------------------------------------------
# A FREQ=DAILY event with DTSTART ~6 months in the past (no COUNT/UNTIL).
# parse_ics must complete quickly and return only in-window occurrences.

_DAILY_NOW = datetime(2026, 6, 15, 0, 0, tzinfo=_UTC)


def _check_recurring_daily(events: list[CalendarEvent]) -> None:
    assert events, (
        "recurring_daily.ics: a FREQ=DAILY event with a past DTSTART must produce "
        "in-window occurrences"
    )
    assert all(e.summary == "Daily Standup" for e in events), (
        "recurring_daily.ics: all returned events must have summary 'Daily Standup'"
    )
    # 7-day window -> expect ~7 occurrences; allow a small margin for boundary.
    assert 6 <= len(events) <= 8, (
        f"recurring_daily.ics: expected ~7 in-window daily occurrences, "
        f"got {len(events)}"
    )
    # All events must be tz-aware and future (>= now).
    assert all(e.start >= _DAILY_NOW for e in events), (
        "recurring_daily.ics: no past timed events should appear"
    )


# ---------------------------------------------------------------------------
# Parametrize: (fixture_name, now, lookahead_days, tz, check_fn)
# ---------------------------------------------------------------------------

_CORPUS_CASES = [
    pytest.param(
        "google_basic.ics",
        _GOOGLE_NOW,
        7,
        _NY,
        _check_google_basic,
        id="google_basic",
    ),
    pytest.param(
        "outlook_bom.ics",
        _OUTLOOK_NOW,
        7,
        _UTC,
        _check_outlook_bom,
        id="outlook_bom",
    ),
    pytest.param(
        "cancelled.ics",
        _CANCELLED_NOW,
        7,
        _UTC,
        _check_cancelled,
        id="cancelled",
    ),
    pytest.param(
        "multi_rrule.ics",
        _MULTI_RRULE_NOW,
        7,
        _UTC,
        _check_multi_rrule,
        id="multi_rrule",
    ),
    pytest.param(
        "all_day_span.ics",
        _ALL_DAY_NOW,
        7,
        _UTC,
        _check_all_day_span,
        id="all_day_span",
    ),
    pytest.param(
        "summary_newline.ics",
        _NEWLINE_NOW,
        7,
        _UTC,
        _check_summary_newline,
        id="summary_newline",
    ),
    pytest.param(
        "non_ascii.ics",
        _NON_ASCII_NOW,
        7,
        _UTC,
        _check_non_ascii,
        id="non_ascii",
    ),
    pytest.param(
        "floating_time.ics",
        _FLOATING_NOW,
        7,
        _NY,
        _check_floating_time,
        id="floating_time",
    ),
    pytest.param(
        "recurring_daily.ics",
        _DAILY_NOW,
        7,
        _UTC,
        _check_recurring_daily,
        id="recurring_daily",
    ),
]


@pytest.mark.parametrize("fixture_name,now,lookahead_days,tz,check_fn", _CORPUS_CASES)
def test_corpus_parse_does_not_raise_and_meets_expectations(
    fixture_name: str,
    now: datetime,
    lookahead_days: int,
    tz,
    check_fn,
) -> None:
    """Corpus guard: each fixture must parse without raising and satisfy its
    per-shape expectation.

    If this test FAILS it means either:
    (a) a regression was introduced in parse_ics / a helper, or
    (b) the fixture was mutated in a way that broke the expected invariant.
    Do NOT weaken the assertion — treat a failure as a bug report.
    """
    text = (_CORPUS / fixture_name).read_text(encoding="utf-8")
    # (a) Must not raise — any exception propagates as a test failure.
    events = parse_ics(text, now=now, lookahead_days=lookahead_days, tz=tz)
    # (b) Per-fixture expectation.
    check_fn(events)


# ---------------------------------------------------------------------------
# Full update() path test — drives Calendar.update() against a file:// URL
# with a fixed now (via monkeypatch) and asserts feed_stories are non-empty.
# ---------------------------------------------------------------------------


def test_corpus_update_agenda_builds_feed_stories(monkeypatch) -> None:
    """Drive the full Calendar.update() path (layout='agenda') against the
    google_basic.ics corpus fixture via a file:// URL.

    Asserts that feed_stories are built (not just the empty_text fallback)
    when now is pinned so events are in-window.  This exercises the fetch +
    parse + build_stories pipeline end-to-end without a live HTTP server.
    """
    fixture_path = _CORPUS / "google_basic.ics"
    monkeypatch.setattr(
        "led_ticker.widgets.calendar._now_in",
        lambda tz: _GOOGLE_NOW,
    )
    cal = Calendar(
        session=None,
        ics_url=f"file://{fixture_path}",
        layout="agenda",
        timezone="America/New_York",
    )
    asyncio.run(cal.update())

    assert cal.feed_stories, (
        "Calendar.update() must build at least one feed story for google_basic.ics "
        "when now is within the event window"
    )
    assert all(isinstance(s, _TwoToneLine) for s in cal.feed_stories), (
        "agenda layout must build _TwoToneLine feed stories"
    )
    # Must NOT be the single empty_text placeholder (events are in-window).
    assert not (
        len(cal.feed_stories) == 1 and cal.feed_stories[0].text == cal.empty_text
    ), "feed_stories must contain real events, not just the empty_text placeholder"
