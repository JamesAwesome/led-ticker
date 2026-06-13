"""Calendar widget: upcoming events from a subscribed iCal (.ics) feed.

Always a Container (like rss_feed): a shared data core fetches + parses the
feed, then update() populates feed_stories per the `layout` knob — `agenda`
builds one TickerMessage per event; `next` builds one live countdown widget.
"""

from datetime import date, datetime, time, timedelta, tzinfo
from typing import Any

import aiohttp
import attrs
import icalendar
import recurring_ical_events

from led_ticker._types import Font
from led_ticker.fonts import FONT_DEFAULT
from led_ticker.widget import Widget
from led_ticker.widgets import register
from led_ticker.widgets.message import TickerMessage


@attrs.define(frozen=True)
class CalendarEvent:
    """A parsed, display-ready calendar event in the display timezone."""

    summary: str
    start: datetime  # tz-aware, resolved to the display tz
    all_day: bool


def _now_in(tz: tzinfo | None) -> datetime:
    """Current time as an ALWAYS-aware datetime.

    When `tz` is None (no timezone configured) we resolve the system-local
    zone via `.astimezone()` rather than returning a naive `datetime.now()`.
    A naive `now` cannot be compared/subtracted against the tz-aware event
    starts that .ics feeds carry — doing so raises `TypeError`. Module-level
    so tests can monkeypatch `led_ticker.widgets.calendar._now_in`.
    """
    return datetime.now(tz) if tz is not None else datetime.now().astimezone()


def _to_display_start(dt_value: date | datetime, tz: tzinfo) -> tuple[datetime, bool]:
    """Resolve a DTSTART value to a tz-aware datetime + all_day flag.

    `tz` is always a concrete tzinfo (never None). A bare `date` is an all-day
    event -> midnight of that date in `tz`. A naive `datetime` (floating time)
    is assumed to be in `tz`.
    """
    if isinstance(dt_value, datetime):
        if dt_value.tzinfo is None:
            return dt_value.replace(tzinfo=tz), False
        return dt_value.astimezone(tz), False
    return datetime.combine(dt_value, time.min, tzinfo=tz), True


def parse_ics(
    text: str, *, now: datetime, lookahead_days: int, tz: tzinfo
) -> list[CalendarEvent]:
    """Parse an .ics document, expand recurrence in [now, now+lookahead_days],
    drop past events, and return CalendarEvents sorted by start (display tz)."""
    cal = icalendar.Calendar.from_ical(text)
    window_end = now + timedelta(days=lookahead_days)
    occurrences = recurring_ical_events.of(cal).between(now, window_end)

    events: list[CalendarEvent] = []
    for comp in occurrences:
        summary = str(comp.get("SUMMARY", "")).strip()
        if not summary:
            continue
        dtstart = comp.get("DTSTART")
        if dtstart is None:
            continue
        start, all_day = _to_display_start(dtstart.dt, tz)
        # belt-and-suspenders: recurring_ical_events.between() already excludes
        # past all-day events; this guards malformed/edge feeds.
        if all_day:
            if start + timedelta(days=1) <= now:
                continue
        elif start < now:
            continue
        events.append(CalendarEvent(summary=summary, start=start, all_day=all_day))

    events.sort(key=lambda e: e.start)
    return events


def _match_any(summary: str, keywords: list[str]) -> bool:
    """Case-insensitive substring match against any keyword (empty -> False).

    Same semantics as the baseball promotions widget's _match_any.
    """
    s = summary.casefold()
    return any(k.casefold() in s for k in keywords)


def select_events(
    events: list[CalendarEvent],
    *,
    filter: list[str],
    highlight: list[str],
    max_events: int,
) -> list[CalendarEvent]:
    """Apply the keyword filter, then cap to max_events while guaranteeing every
    highlighted event survives. `events` is assumed sorted by start; the result
    is re-sorted by start so the agenda reads chronologically.

    `max_events <= 0` means no cap: all post-filter events are returned.
    """
    if filter:
        events = [e for e in events if _match_any(e.summary, filter)]
    if max_events <= 0 or len(events) <= max_events:
        return events
    highlighted = [e for e in events if _match_any(e.summary, highlight)]
    highlighted_ids = {id(e) for e in highlighted}
    rest = [e for e in events if id(e) not in highlighted_ids]
    kept = highlighted[:max_events]
    kept += rest[: max_events - len(kept)]
    kept.sort(key=lambda e: e.start)
    return kept


@register("calendar")
@attrs.define
class Calendar:
    """Container that shows upcoming .ics events as an agenda or next-event line."""

    session: aiohttp.ClientSession
    ics_url: str
    layout: str = "agenda"
    max_events: int = 5
    lookahead_days: int = 7
    time_format: str = "12h"
    timezone: str | None = None
    empty_text: str = "No upcoming events"
    filter: list[str] = attrs.field(factory=list)
    highlight: list[str] = attrs.field(factory=list)
    padding: int = 6
    font: Font = attrs.Factory(lambda: FONT_DEFAULT)
    font_color: Any = attrs.field(default=None, kw_only=True)
    highlight_color: Any = attrs.field(default=None, kw_only=True)
    bg_color: Any = attrs.field(default=None, kw_only=True)
    border: Any | None = attrs.field(default=None, kw_only=True)
    feed_stories: list[Widget] = attrs.field(init=False, factory=list)
    feed_title: TickerMessage | None = attrs.field(init=False, default=None)
