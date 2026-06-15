"""Guard 3 — next-mode selection truth table (class D).

Parametrized truth table covering _NextEventWidget.draw() selection priority:

  1. soonest future timed   (start > now, not all_day)   → "<summary> in …"
  2. else ongoing all-day   (all_day, start.date() <= today) → "<summary> today"
  3. else soonest future all-day                          → "<summary> in Nd"/"tomorrow"
  4. else most-recently-started in-progress timed         → "<summary> now"
  5. else empty_text

Each row in the parametrize table declares which event kinds are present and
asserts BOTH the picked event's summary AND the rendered format_relative string.
"""

from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

from led_ticker.widgets.calendar import (
    CalendarEvent,
    _NextEventWidget,
    split_relative,
)

_UTC = ZoneInfo("UTC")

# Fixed "now" used throughout: 2026-06-15 10:00 UTC (Monday).
_NOW = datetime(2026, 6, 15, 10, 0, tzinfo=_UTC)

# ---------------------------------------------------------------------------
# Event helpers — all starts are pinned relative to _NOW so tests are stable.
# ---------------------------------------------------------------------------

# Tier 1: future timed (soonest of two future-timed defined for priority tests)
_FUTURE_TIMED_SOON = CalendarEvent(
    "DentistSoon", datetime(2026, 6, 15, 14, 0, tzinfo=_UTC), all_day=False
)
_FUTURE_TIMED_LATE = CalendarEvent(
    "DentistLate", datetime(2026, 6, 15, 18, 0, tzinfo=_UTC), all_day=False
)

# Tier 2: ongoing all-day (started yesterday midnight, ends tomorrow — genuinely
# ongoing)
_ONGOING_ALLDAY = CalendarEvent(
    "Vacation",
    datetime(2026, 6, 14, 0, 0, tzinfo=_UTC),
    all_day=True,
    end=datetime(2026, 6, 16, 0, 0, tzinfo=_UTC),  # ends tomorrow (exclusive end)
)
# Another ongoing-today (start is today midnight, ends tomorrow — still ongoing now)
_TODAY_ALLDAY = CalendarEvent(
    "HolidayToday",
    datetime(2026, 6, 15, 0, 0, tzinfo=_UTC),
    all_day=True,
    end=datetime(2026, 6, 16, 0, 0, tzinfo=_UTC),  # ends tomorrow (exclusive end)
)

# Tier 3: future all-day (tomorrow)
_FUTURE_ALLDAY_TOMORROW = CalendarEvent(
    "Conference", datetime(2026, 6, 16, 0, 0, tzinfo=_UTC), all_day=True
)
# Future all-day 3 days out
_FUTURE_ALLDAY_3D = CalendarEvent(
    "Offsite", datetime(2026, 6, 18, 0, 0, tzinfo=_UTC), all_day=True
)

# Tier 4: in-progress timed (started 30m ago, ends in 30m — genuinely in-progress)
_INPROGRESS = CalendarEvent(
    "Standup",
    datetime(2026, 6, 15, 9, 30, tzinfo=_UTC),
    all_day=False,
    end=datetime(2026, 6, 15, 10, 30, tzinfo=_UTC),  # ends at 10:30, after _NOW=10:00
)
# A later-started in-progress event (started 5m ago) — draw() should pick THIS
# one (most-recently-started = last in sorted order, i.e. the latest start <= now)
_INPROGRESS_LATER = CalendarEvent(
    "Meeting",
    datetime(2026, 6, 15, 9, 55, tzinfo=_UTC),
    all_day=False,
    end=datetime(2026, 6, 15, 10, 55, tzinfo=_UTC),  # ends at 10:55, after _NOW=10:00
)


def _draw_with_fixed_now(events: list[CalendarEvent]) -> str:
    """Create a _NextEventWidget, monkeypatch _now_in, call draw(), and return
    the rendered text by intercepting format_relative."""
    rendered: list[str] = []
    original_split = split_relative

    def capture_split(event, now, empty_text):
        title, time_part = original_split(event, now, empty_text)
        rendered.append(title + time_part)
        return title, time_part

    w = _NextEventWidget(
        events=list(events), empty_text="No upcoming events", timezone="UTC"
    )
    from unittest.mock import Mock

    c = Mock()
    c.width = 160
    c.height = 16

    _rel_patch = "led_ticker.widgets.calendar.split_relative"
    with (
        patch("led_ticker.widgets.calendar._now_in", return_value=_NOW),
        patch(_rel_patch, side_effect=capture_split),
    ):
        w.draw(c)

    return rendered[0] if rendered else "No upcoming events"


def _picked_event(events: list[CalendarEvent]) -> CalendarEvent | None:
    """Like _draw_with_fixed_now but returns the PICKED event object."""
    picked: list[CalendarEvent | None] = []
    original_split = split_relative

    def capture_split(event, now, empty_text):
        picked.append(event)
        return original_split(event, now, empty_text)

    w = _NextEventWidget(
        events=list(events), empty_text="No upcoming events", timezone="UTC"
    )
    from unittest.mock import Mock

    c = Mock()
    c.width = 160
    c.height = 16

    _rel_patch = "led_ticker.widgets.calendar.split_relative"
    with (
        patch("led_ticker.widgets.calendar._now_in", return_value=_NOW),
        patch(_rel_patch, side_effect=capture_split),
    ):
        w.draw(c)

    return picked[0] if picked else None


# ---------------------------------------------------------------------------
# Tier 1: soonest future timed wins
# ---------------------------------------------------------------------------


def test_tier1_single_future_timed():
    """Only a future timed event → rendered as 'in …'."""
    text = _draw_with_fixed_now([_FUTURE_TIMED_SOON])
    assert text == "DentistSoon · in 4h"


def test_tier1_picks_soonest_of_two_future_timed():
    """Two future timed events → picks the sooner one."""
    picked = _picked_event([_FUTURE_TIMED_LATE, _FUTURE_TIMED_SOON])
    assert picked is _FUTURE_TIMED_SOON


def test_tier1_beats_ongoing_allday():
    """future-timed + ongoing all-day → future-timed wins (tier 1 before tier 2)."""
    picked = _picked_event([_ONGOING_ALLDAY, _FUTURE_TIMED_SOON])
    assert picked is _FUTURE_TIMED_SOON, (
        "future-timed event must be preferred over an ongoing all-day event"
    )


def test_tier1_beats_future_allday():
    """future-timed + future all-day → future-timed wins."""
    picked = _picked_event([_FUTURE_ALLDAY_TOMORROW, _FUTURE_TIMED_SOON])
    assert picked is _FUTURE_TIMED_SOON


def test_tier1_beats_inprogress_timed():
    """future-timed + in-progress-timed → future-timed wins (tier 1 before tier 4)."""
    picked = _picked_event([_INPROGRESS, _FUTURE_TIMED_SOON])
    assert picked is _FUTURE_TIMED_SOON, (
        "soonest future timed event must be preferred over an in-progress timed event"
    )


def test_tier1_all_four_present():
    """All four tiers present → tier 1 (future timed) wins."""
    picked = _picked_event(
        [_ONGOING_ALLDAY, _FUTURE_ALLDAY_TOMORROW, _INPROGRESS, _FUTURE_TIMED_SOON]
    )
    assert picked is _FUTURE_TIMED_SOON


# ---------------------------------------------------------------------------
# Tier 2: ongoing all-day when no future timed event
# ---------------------------------------------------------------------------


def test_tier2_ongoing_allday_no_timed():
    """ongoing all-day + nothing timed → 'today' (not hidden, not empty)."""
    text = _draw_with_fixed_now([_ONGOING_ALLDAY])
    assert text == "Vacation · today", (
        "Ongoing all-day (started before today) must render 'today'"
    )


def test_tier2_today_allday_start_is_midnight():
    """all-day with start = today midnight (start.date() == today) → 'today'."""
    text = _draw_with_fixed_now([_TODAY_ALLDAY])
    assert text == "HolidayToday · today"


def test_tier2_ongoing_allday_beats_future_allday():
    """ongoing all-day + future all-day → ongoing (tier 2) wins over future (tier 3)."""
    picked = _picked_event([_ONGOING_ALLDAY, _FUTURE_ALLDAY_TOMORROW])
    assert picked is _ONGOING_ALLDAY, (
        "Ongoing all-day (start.date() <= today) must beat a future all-day"
    )


def test_tier2_ongoing_allday_beats_inprogress_timed():
    """ongoing all-day + in-progress timed → all-day wins (tier 2 before tier 4)."""
    picked = _picked_event([_ONGOING_ALLDAY, _INPROGRESS])
    assert picked is _ONGOING_ALLDAY, (
        "Ongoing all-day must be preferred over an in-progress timed event"
    )


# ---------------------------------------------------------------------------
# Tier 3: soonest future all-day when no timed or ongoing all-day
# ---------------------------------------------------------------------------


def test_tier3_future_allday_tomorrow():
    """Only a future all-day (tomorrow) → renders 'tomorrow'."""
    text = _draw_with_fixed_now([_FUTURE_ALLDAY_TOMORROW])
    assert text == "Conference · tomorrow"


def test_tier3_future_allday_3d():
    """Only a future all-day 3 days out → renders 'in 3d'."""
    text = _draw_with_fixed_now([_FUTURE_ALLDAY_3D])
    assert text == "Offsite · in 3d"


def test_tier3_picks_soonest_future_allday():
    """Two future all-days (no timed) → picks the sooner one."""
    picked = _picked_event([_FUTURE_ALLDAY_3D, _FUTURE_ALLDAY_TOMORROW])
    assert picked is _FUTURE_ALLDAY_TOMORROW


def test_tier3_future_allday_beats_inprogress():
    """future all-day + in-progress timed → future all-day (tier 3) wins."""
    picked = _picked_event([_FUTURE_ALLDAY_TOMORROW, _INPROGRESS])
    assert picked is _FUTURE_ALLDAY_TOMORROW, (
        "Future all-day (tier 3) must be preferred over in-progress timed (tier 4)"
    )


# ---------------------------------------------------------------------------
# Tier 4: most-recently-started in-progress timed
# ---------------------------------------------------------------------------


def test_tier4_inprogress_shows_now():
    """Only an in-progress timed event → '<summary> now' (not empty_text)."""
    text = _draw_with_fixed_now([_INPROGRESS])
    assert text == "Standup · now", (
        "In-progress timed event must render 'now', not empty_text"
    )


def test_tier4_picks_most_recently_started():
    """Two in-progress timed events → picks the most-recently-started one."""
    picked = _picked_event([_INPROGRESS, _INPROGRESS_LATER])
    assert picked is _INPROGRESS_LATER, (
        "Most-recently-started in-progress event must be selected (latest start <= now)"
    )


# ---------------------------------------------------------------------------
# Tier 5: empty list → empty_text
# ---------------------------------------------------------------------------


def test_tier5_empty_list():
    """No events at all → empty_text."""
    text = _draw_with_fixed_now([])
    assert text == "No upcoming events"


# ---------------------------------------------------------------------------
# Rendered-string end-to-end spot checks via format_relative
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "events, expected_text",
    [
        # tier 1 only
        ([_FUTURE_TIMED_SOON], "DentistSoon · in 4h"),
        # tier 2 only (ongoing from yesterday)
        ([_ONGOING_ALLDAY], "Vacation · today"),
        # tier 3 only (tomorrow)
        ([_FUTURE_ALLDAY_TOMORROW], "Conference · tomorrow"),
        # tier 3 only (3 days)
        ([_FUTURE_ALLDAY_3D], "Offsite · in 3d"),
        # tier 4 only
        ([_INPROGRESS], "Standup · now"),
        # tier 5
        ([], "No upcoming events"),
        # tier 1 beats tier 2
        ([_FUTURE_TIMED_SOON, _ONGOING_ALLDAY], "DentistSoon · in 4h"),
        # tier 1 beats tier 4
        ([_INPROGRESS, _FUTURE_TIMED_SOON], "DentistSoon · in 4h"),
        # tier 2 beats tier 3
        ([_ONGOING_ALLDAY, _FUTURE_ALLDAY_TOMORROW], "Vacation · today"),
        # tier 2 beats tier 4
        ([_ONGOING_ALLDAY, _INPROGRESS], "Vacation · today"),
        # tier 3 beats tier 4
        ([_FUTURE_ALLDAY_TOMORROW, _INPROGRESS], "Conference · tomorrow"),
        # ended all-day (end <= now) → skipped, falls to empty (tier 5)
        (
            [
                CalendarEvent(
                    "EndedVacation",
                    datetime(2026, 6, 14, 0, 0, tzinfo=_UTC),
                    all_day=True,
                    # ended at midnight = _NOW boundary
                    end=datetime(2026, 6, 15, 0, 0, tzinfo=_UTC),
                )
            ],
            "No upcoming events",
        ),
        # ended timed (end <= now) → skipped, falls to empty (tier 5)
        (
            [
                CalendarEvent(
                    "EndedMeeting",
                    datetime(2026, 6, 15, 9, 0, tzinfo=_UTC),
                    all_day=False,
                    # ended 30m before _NOW=10:00
                    end=datetime(2026, 6, 15, 9, 30, tzinfo=_UTC),
                )
            ],
            "No upcoming events",
        ),
    ],
)
def test_selection_truth_table(events, expected_text):
    """Parametrized truth table: given event kinds, assert rendered string."""
    text = _draw_with_fixed_now(events)
    summaries = [e.summary for e in events]
    assert text == expected_text, (
        f"Expected {expected_text!r}, got {text!r} for events={summaries}"
    )


# ---------------------------------------------------------------------------
# Ended-event correctness tests (the fix for stale "today"/"now" display)
# ---------------------------------------------------------------------------


def test_next_skips_ended_all_day():
    """An all-day event whose end <= now must NOT show as 'today' — shows empty_text.

    Before the fix: a stale ended all-day (e.g. kept in _NextEventWidget.events
    from the last fetch) with start.date() <= now.date() was picked by tier 2
    and rendered as '<summary> today' indefinitely — even after it ended.

    After the fix: _not_ended(e, now) gates tier 2; end <= now → skip → empty_text.
    """
    # All-day that started yesterday and ended at midnight today (exclusive end = now).
    ended_allday = CalendarEvent(
        "Ended Vacation",
        datetime(2026, 6, 14, 0, 0, tzinfo=_UTC),
        all_day=True,
        end=datetime(2026, 6, 15, 0, 0, tzinfo=_UTC),  # exclusive end == _NOW midnight
    )
    text = _draw_with_fixed_now([ended_allday])
    assert text == "No upcoming events", (
        f"Ended all-day event (end <= now) must not render 'today'; got {text!r}"
    )


def test_next_ended_all_day_does_not_mask_current():
    """A stale ended all-day must not mask a genuinely current all-day.

    Before the fix: the stale ended all-day (earlier start) was picked first
    by the ascending-sort, hiding the current all-day with a later start.

    After the fix: the stale one is excluded by _not_ended; the current one
    (start <= now, end > now) is shown as 'today'.
    """
    stale_ended = CalendarEvent(
        "StaleVacation",
        datetime(2026, 6, 13, 0, 0, tzinfo=_UTC),  # earlier start → sorts first
        all_day=True,
        # ended at midnight = _NOW boundary
        end=datetime(2026, 6, 15, 0, 0, tzinfo=_UTC),
    )
    current = CalendarEvent(
        "CurrentHoliday",
        datetime(2026, 6, 15, 0, 0, tzinfo=_UTC),
        all_day=True,
        # ends tomorrow — genuinely ongoing
        end=datetime(2026, 6, 16, 0, 0, tzinfo=_UTC),
    )
    picked = _picked_event([stale_ended, current])
    assert picked is current, (
        f"Stale ended all-day must not mask a genuinely current all-day; "
        f"picked {picked!r} instead of current event"
    )
    text = _draw_with_fixed_now([stale_ended, current])
    assert text == "CurrentHoliday · today", (
        f"Expected 'CurrentHoliday · today', got {text!r}"
    )


def test_next_skips_ended_in_progress_timed():
    """A timed event with start <= now and end <= now must NOT show as 'now'.

    Before the fix: a timed event that ended between fetches (start in the past,
    end also in the past) was picked by tier 4 and shown as '<summary> now'
    indefinitely until the next successful fetch.

    After the fix: _not_ended(e, now) gates tier 4; end <= now → skip → empty_text.
    """
    ended_timed = CalendarEvent(
        "Ended Standup",
        datetime(2026, 6, 15, 9, 0, tzinfo=_UTC),  # started 1h before _NOW
        all_day=False,
        # ended 30m before _NOW=10:00
        end=datetime(2026, 6, 15, 9, 30, tzinfo=_UTC),
    )
    text = _draw_with_fixed_now([ended_timed])
    assert text == "No upcoming events", (
        f"Ended in-progress timed event (end <= now) must not render 'now'; "
        f"got {text!r}"
    )
