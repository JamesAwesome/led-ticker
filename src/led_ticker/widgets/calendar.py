"""Calendar widget: upcoming events from a subscribed iCal (.ics) feed.

Always a Container (like rss_feed): a shared data core fetches + parses the
feed, then update() populates feed_stories per the `layout` knob — `agenda`
builds one two-tone line per event (time phrase in `time_color`, title in
`font_color`); `next` builds one live countdown widget.
"""

import asyncio
import logging
from datetime import UTC, date, datetime, time, timedelta, tzinfo
from pathlib import Path
from typing import Any, ClassVar, Self
from urllib.parse import unquote
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import aiohttp
import attrs
import icalendar
import recurring_ical_events

from led_ticker._types import Canvas, DrawResult, Font
from led_ticker.color_providers import ColorProvider, _ConstantColor
from led_ticker.colors import DEFAULT_COLOR, make_color
from led_ticker.drawing import compute_baseline, compute_cursor
from led_ticker.fonts import FONT_DEFAULT
from led_ticker.pixel_emoji import count_text_chars, draw_with_emoji, measure_width
from led_ticker.widget import Widget, run_monitor_loop, spawn_tracked
from led_ticker.widgets import register
from led_ticker.widgets._frame_aware import FrameAwareBase
from led_ticker.widgets.clock import format_clock
from led_ticker.widgets.message import TickerMessage

logger = logging.getLogger(__name__)

# Visible delimiter between the time/relative phrase and the event title.
# A space + U+00B7 MIDDLE DOT + space reads far more clearly on the panel than
# the old two-space gap (matches the convention the baseball promotions widget
# uses). Verified to render (non-tofu) in BOTH the bundled BDF fonts
# (5x8/6x10/6x12/7x13 all carry ENCODING 183) and the hires Inter-Regular.otf.
_SEP = " · "

# Belt-and-suspenders bound against a non-sub-hourly high-cardinality feed (e.g.
# a dense RDATE list). `.between(now, window_end)` already caps the expansion at
# the lookahead window; this is a final cap on the materialized in-window set so
# a pathological feed can't balloon memory.
_MAX_OCCURRENCES = 2000

_SUBHOURLY_FREQS = frozenset({"SECONDLY", "MINUTELY"})


def _rrule_is_subhourly(rrule: Any) -> bool:
    """Return True if a single vRecur object has a sub-hourly FREQ.

    icalendar stores FREQ as a list of vFrequency objects (e.g. ['SECONDLY']),
    so we pull index 0 when the value is a list.  Both vFrequency and
    plain-string values are handled via str()-cast.
    """
    freq = rrule.get("FREQ")
    freq_val = freq[0] if isinstance(freq, list) else freq
    return str(freq_val).upper() in _SUBHOURLY_FREQS


def _drop_subhourly_recurrences(cal: Any) -> int:
    """Remove VEVENTs with a SECONDLY/MINUTELY RRULE in place; return the count.

    recurring_ical_events walks every occurrence from DTSTART up to `now`
    before yielding the first in-window result, and that pre-now scan is NOT
    bounded by the islice occurrence cap. A sub-hourly RRULE with a past
    DTSTART makes that scan pin a CPU core for tens of seconds. Sub-hourly
    forever-recurrence is never legitimate calendar display content, so we
    drop such events (with a warning) before handing the calendar to the
    expander. Bounded sub-hourly rules (with COUNT/UNTIL) are dropped too —
    an accepted trade-off, as a per-second/minute event is not meaningful on
    an LED sign and the bounded case is vanishingly rare.

    Multi-RRULE VEVENTs (RFC 5545 allows more than one RRULE on an event;
    some exporters emit this) are handled: comp.get("RRULE") returns a list
    of vRecur objects in that case.  An event is sub-hourly if ANY of its
    RRULEs is sub-hourly.
    """
    kept = []
    dropped = 0
    for comp in cal.subcomponents:
        rrule = comp.get("RRULE") if comp.name == "VEVENT" else None
        if rrule is not None:
            rrules = rrule if isinstance(rrule, list) else [rrule]
            if any(_rrule_is_subhourly(rr) for rr in rrules):
                dropped += 1
                continue
        kept.append(comp)
    cal.subcomponents = kept
    return dropped


def _normalize_mismatched_all_day(cal: Any) -> int:
    """Fix RFC-violating all-day events (DTSTART;VALUE=DATE + datetime DTEND).

    recurring_ical_events promotes DTSTART to a midnight-UTC datetime on
    expansion when DTEND is a datetime, stripping the VALUE=DATE param so the
    event loses its all_day=True shape.  In negative-UTC zones (Americas) the
    promoted midnight-UTC DTSTART lands before the local midnight, causing the
    event to resolve BEFORE now and be silently dropped by parse_ics.

    Coerce DTEND to a DATE exclusive-end so the all-day shape survives expansion.
    For RFC 5545 all-day events DTEND is an exclusive boundary: an event on
    Jun 20 has DTEND;VALUE=DATE:20260621.  A datetime DTEND (e.g. 20:00 UTC on
    Jun 20) represents the actual end time — converting to an exclusive DATE
    requires taking the DATE of the datetime and adding one day so the event
    spans through the DTEND calendar date.

    Mutation method verified: comp.pop('DTEND') + comp.add('DTEND', date_value)
    correctly replaces the datetime with a plain date in the icalendar object.
    """
    fixed = 0
    for comp in cal.subcomponents:
        if comp.name != "VEVENT":
            continue
        dtstart = comp.get("DTSTART")
        dtend = comp.get("DTEND")
        if dtstart is None or dtend is None:
            continue
        ds_is_date = str(dtstart.params.get("VALUE", "")).upper() == "DATE"
        if ds_is_date and isinstance(dtend.dt, datetime):
            # Convert datetime DTEND to exclusive-date DTEND.
            # e.g. DTEND:20260620T200000Z -> date(2026-06-20) + 1 = date(2026-06-21)
            # so the event spans through June 20, consistent with what
            # DTEND;VALUE=DATE:20260621 would express.
            exclusive_end = dtend.dt.date() + timedelta(days=1)
            comp.pop("DTEND")
            comp.add("DTEND", exclusive_end)
            fixed += 1
    return fixed


@attrs.define(frozen=True)
class CalendarEvent:
    """A parsed, display-ready calendar event in the display timezone."""

    summary: str
    start: datetime  # tz-aware, resolved to the display tz
    all_day: bool
    end: datetime | None = None  # tz-aware exclusive end; None means unknown/not ended


def _now_in(tz: tzinfo | None) -> datetime:
    """Current time as an ALWAYS-aware datetime.

    When `tz` is None (no timezone configured) we resolve the system-local
    zone via `.astimezone()` rather than returning a naive `datetime.now()`.
    A naive `now` cannot be compared/subtracted against the tz-aware event
    starts that .ics feeds carry — doing so raises `TypeError`. Module-level
    so tests can monkeypatch `led_ticker.widgets.calendar._now_in`.
    """
    return datetime.now(tz) if tz is not None else datetime.now().astimezone()


def _resolve_tz(timezone: str | None) -> tzinfo:
    """Resolve a config timezone to a concrete, DST-correct tzinfo.

    An explicit IANA name -> ZoneInfo. Unset -> the SYSTEM-LOCAL IANA zone
    (resolved from the /etc/localtime symlink) so events across a DST boundary
    in the lookahead window get the right offset. Falls back to the current
    fixed UTC offset only if the system zone can't be determined.
    """
    if timezone:
        return ZoneInfo(timezone)
    try:
        parts = Path("/etc/localtime").resolve().parts
        if "zoneinfo" in parts:
            name = "/".join(parts[parts.index("zoneinfo") + 1 :])
            return ZoneInfo(name)
    except Exception:
        pass
    fallback = datetime.now().astimezone().tzinfo
    if fallback is None:
        return ZoneInfo("UTC")  # should never happen, but satisfies the type checker
    return fallback  # best-effort fixed-offset fallback


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
    drop past events, and return CalendarEvents sorted by start (display tz).

    Recurrence is expanded via `recurring_ical_events.of(cal).between(now,
    window_end)`, which is hard-bounded by `window_end` (it delegates to
    `dateutil.rrule.between`, which stops at the upper bound). This makes even a
    far-past forever HOURLY/DAILY rule cheap — no unbounded forward walk. Two
    pre-expansion passes still run because `.between()` does NOT help with them:
    `_drop_subhourly_recurrences` (a far-past SECONDLY/MINUTELY rule is still
    catastrophic — the pre-now walk dominates) and `_normalize_mismatched_all_day`
    (the DATE-promotion still happens on expansion).

    `.between()` is END-INCLUSIVE, so an explicit `start > window_end` filter is
    kept inside the loop to match the original exclusive window edge. As a final
    belt-and-suspenders bound against a non-sub-hourly high-cardinality feed
    (e.g. a dense RDATE list), the materialized in-window set is capped at
    `_MAX_OCCURRENCES` with a visible warning. Also strips a leading UTF-8 BOM
    (U+FEFF) so Outlook/Exchange feeds parse correctly.
    """
    # Fix 4: strip leading BOM before parsing (Outlook/Exchange/.ics feeds)
    text = text.lstrip("﻿")
    cal = icalendar.Calendar.from_ical(text)
    dropped = _drop_subhourly_recurrences(cal)
    if dropped:
        logger.warning(
            "Calendar: dropped %d event(s) with a sub-hourly (SECONDLY/MINUTELY) "
            "RRULE to avoid an unbounded recurrence scan",
            dropped,
        )
    # Fix 1 (round-11): normalize RFC-violating all-day events that have
    # DTSTART;VALUE=DATE but a datetime DTEND — coerce DTEND to a DATE so the
    # event survives expansion with its all_day shape intact.
    fixed_allday = _normalize_mismatched_all_day(cal)
    if fixed_allday:
        logger.debug(
            "Calendar: fixed %d RFC-violating all-day event(s) "
            "(DTSTART;VALUE=DATE + datetime DTEND)",
            fixed_allday,
        )
    window_end = now + timedelta(days=lookahead_days)

    # Expand recurrence with the library's hard-bounded .between(now, window_end).
    # It delegates to dateutil.rrule.between, which stops at the upper bound — no
    # unbounded forward walk, so a far-past forever HOURLY/DAILY rule is cheap.
    occurrences = recurring_ical_events.of(cal).between(now, window_end)

    events: list[CalendarEvent] = []
    for comp in occurrences:
        # skip STATUS:CANCELLED events (declined/cancelled meetings, cancelled
        # occurrence overrides from Google/Outlook/iCloud feeds).
        if str(comp.get("STATUS", "")).upper() == "CANCELLED":
            continue
        # collapse whitespace (embedded newlines/tabs from icalendar unescaping
        # \n) so SUMMARY renders cleanly on a single-line panel.
        summary = " ".join(str(comp.get("SUMMARY", "")).split())
        if not summary:
            continue
        dtstart = comp.get("DTSTART")
        if dtstart is None:
            continue
        start, all_day = _to_display_start(dtstart.dt, tz)
        # .between() is END-INCLUSIVE; the original window edge was exclusive.
        # Filter the boundary occurrences so the in-window set matches exactly.
        if start > window_end:
            continue
        # belt-and-suspenders: .between() already excludes ended occurrences;
        # this guards malformed/edge feeds.
        dtend_prop = comp.get("DTEND")
        if all_day:
            if dtend_prop is not None:
                end, _ = _to_display_start(dtend_prop.dt, tz)  # exclusive end
            else:
                end = start + timedelta(days=1)
            if end <= now:  # ended before now -> past
                continue
        else:  # timed event
            # For timed events: use DTEND if present, else treat as instantaneous.
            if dtend_prop is not None:
                end, _ = _to_display_start(dtend_prop.dt, tz)
            else:
                end = start  # zero-duration: expires the instant it starts
            if end <= now:  # already ended -> past
                continue
        events.append(
            CalendarEvent(summary=summary, start=start, all_day=all_day, end=end)
        )

    events.sort(key=lambda e: e.start)
    # Final belt-and-suspenders cap against a non-sub-hourly high-cardinality
    # feed (e.g. a dense RDATE list).  .between() already bounds the window, so
    # this only fires on a pathological in-window count — never silently drop.
    if len(events) > _MAX_OCCURRENCES:
        logger.warning(
            "Calendar feed produced %d in-window occurrences; truncated to %d "
            "(check the feed's RRULE/RDATE)",
            len(events),
            _MAX_OCCURRENCES,
        )
        events = events[:_MAX_OCCURRENCES]
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


_WEEKDAY_ABBR = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_MONTH_ABBR = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)


def _day_label(start: datetime, now: datetime) -> str:
    """Smart day label relative to `now` (both in display tz).

    Today / Tomorrow / weekday abbrev (2..6 days out) / "Mon D" further out.
    Built from datetime fields (not %- strftime codes) for cross-platform
    determinism — same rule as the clock presets.
    """
    delta_days = (start.date() - now.date()).days
    if delta_days <= 0:
        # Covers today (delta_days == 0) and ongoing all-day events whose
        # DTSTART is in the past (delta_days < 0). Timed events with a past
        # start are dropped by parse_ics, so only ongoing all-day events can
        # reach here with a negative delta — "Today" is correct for them.
        return "Today"
    if delta_days == 1:
        return "Tomorrow"
    if 2 <= delta_days < 7:
        return _WEEKDAY_ABBR[start.weekday()]
    return f"{_MONTH_ABBR[start.month - 1]} {start.day}"


def split_event_line(
    event: CalendarEvent, *, now: datetime, time_format: str, tz: tzinfo
) -> tuple[str, str]:
    """Agenda line split into ``(time_phrase_with_sep, title)``.

    The trailing ``_SEP`` stays attached to the time phrase so the separator
    inherits the time color in two-tone rendering. All-day events omit the
    clock time. ``tz`` is accepted for signature symmetry with the other
    formatters; ``event.start`` is already in the display zone.
    """
    day = _day_label(event.start, now)
    if event.all_day:
        return f"{day}{_SEP}", event.summary
    return f"{day} {format_clock(event.start, time_format)}{_SEP}", event.summary


def format_event_line(
    event: CalendarEvent, *, now: datetime, time_format: str, tz: tzinfo
) -> str:
    """Agenda line: '<day> <time> · <summary>'; all-day omits the time.

    The joined form of :func:`split_event_line`.
    """
    time_part, title = split_event_line(event, now=now, time_format=time_format, tz=tz)
    return time_part + title


def split_relative(
    event: CalendarEvent | None, now: datetime, empty_text: str
) -> tuple[str, str]:
    """Next-mode line split into ``(title, relative_phrase_with_sep)``.

    The leading ``_SEP`` stays attached to the relative phrase so the separator
    inherits the time color in two-tone rendering. When there is no event,
    returns ``(empty_text, "")`` — the empty line has no time segment.

    All-day events are rendered by day (today/tomorrow/in Nd) rather than by
    seconds, since their start is always midnight and a seconds-based delta
    would produce misleading "now" or "in 14h" labels.
    """
    if event is None:
        return empty_text, ""
    if event.all_day:
        days = (event.start.date() - now.date()).days
        if days <= 0:
            return event.summary, f"{_SEP}today"
        if days == 1:
            return event.summary, f"{_SEP}tomorrow"
        return event.summary, f"{_SEP}in {days}d"
    # Convert both to UTC before subtracting so DST transitions don't skew the
    # delta (two aware datetimes with the same ZoneInfo subtract naively in
    # wall-clock time, which is wrong by the DST offset across a transition).
    delta = event.start.astimezone(UTC) - now.astimezone(UTC)
    secs = delta.total_seconds()
    if secs <= 0:
        return event.summary, f"{_SEP}now"
    days = int(secs // 86400)
    if days >= 1:
        return event.summary, f"{_SEP}in {days}d"
    hours = int(secs // 3600)
    minutes = int((secs % 3600) // 60)
    if hours >= 1:
        if minutes == 0:
            return event.summary, f"{_SEP}in {hours}h"
        return event.summary, f"{_SEP}in {hours}h {minutes}m"
    if minutes == 0:
        # sub-minute and imminent -> treat as happening now
        return event.summary, f"{_SEP}now"
    return event.summary, f"{_SEP}in {minutes}m"


def format_relative(event: CalendarEvent | None, now: datetime, empty_text: str) -> str:
    """Next-mode line: '<summary> · in <rel>' / '<summary> · now' / empty_text.

    The joined form of :func:`split_relative`.
    """
    title, time_part = split_relative(event, now, empty_text)
    return title + time_part


def _not_ended(e: CalendarEvent, now: datetime) -> bool:
    """Return True when the event has not yet ended (or its end is unknown).

    `end is None` is treated as "unknown / not ended" for back-compat with any
    CalendarEvent constructed without an explicit `end` field (e.g. older tests
    that use the 3-arg form).
    """
    return e.end is None or e.end > now


def _normalize_ics_url(url: str) -> str:
    """Rewrite non-standard URL schemes to their canonical equivalents.

    ``webcal://`` and ``webcals://`` are Apple/Google/Outlook "Subscribe" links
    that are identical to ``https://`` in content — rewrite them so the http
    fetch path handles them. All other schemes (``http://``, ``https://``,
    ``file://``, bare paths) are returned unchanged.
    """
    if url.startswith("webcal://"):
        return "https://" + url[len("webcal://") :]
    if url.startswith("webcals://"):
        return "https://" + url[len("webcals://") :]
    return url


_CALENDAR_DOCS_URL = "https://docs.ledticker.dev/widgets/calendar/"


def _describe_fetch_error(exc: BaseException, url: str) -> str:
    """One concise, actionable line for why an .ics fetch/parse failed.

    Classifies by exception type so the user gets a fix hint instead of a
    traceback. Pure (exc + url -> str) so it is independently testable. Note the
    ordering: ``FileNotFoundError`` / ``IsADirectoryError`` are ``OSError``
    subclasses and must be matched before the generic ``OSError`` branch, and
    ``ClientResponseError`` before its ``ClientError`` base.
    """
    if isinstance(exc, (FileNotFoundError, IsADirectoryError)):
        detail = (
            f"Calendar feed file not found: {url!r}. "
            "Set ics_url to a real .ics URL or an existing file."
        )
    elif isinstance(exc, aiohttp.ClientResponseError):
        detail = (
            f"Calendar feed returned HTTP {exc.status} for {url}. "
            "Check the URL is public and correct."
        )
    elif isinstance(exc, (aiohttp.ClientError, OSError)):
        detail = (
            f"Calendar feed unreachable: {url} ({type(exc).__name__}). "
            "Check the URL and your network."
        )
    else:
        detail = f"Calendar feed downloaded but is not valid iCal: {url}."
    return f"{detail} See {_CALENDAR_DOCS_URL}"


def _coerce_provider(value: Any) -> ColorProvider:
    """Coerce a color field to a ColorProvider.

    None -> default color; an existing provider -> as-is; a raw [r,g,b]
    list/tuple -> _ConstantColor(graphics.Color(...)) (NOT a bare list — a
    list has no .red/.green/.blue and the real C DrawText/SetPixel require a
    graphics.Color); an existing graphics.Color -> _ConstantColor. Config
    strings/tables (e.g. "rainbow") are coerced by the factory before
    construction (highlight_color is added to _PROVIDER_COLOR_KEYS in Task 7),
    so they arrive here already as providers.
    """
    if value is None:
        return _ConstantColor(DEFAULT_COLOR)
    if hasattr(value, "color_for"):
        return value
    if isinstance(value, (list, tuple)):
        return _ConstantColor(make_color(*value))
    return _ConstantColor(value)  # already a graphics.Color


def _draw_two_tone(
    canvas: Canvas,
    *,
    font: Font,
    cursor_pos: int,
    center: bool,
    padding: int,
    border: Any | None,
    border_frame: int,
    segments: list[tuple[str, ColorProvider, int]],
    override: ColorProvider | None,
    y_offset: int,
    baseline_y: int,
    content_width: int,
) -> DrawResult:
    """Draw an ordered list of ``(text, provider, frame)`` segments on one line.

    Each segment is one ``draw_with_emoji`` call so it keeps its own color
    provider (constant amber / rainbow / gradient / …), its per-char sweep, and
    inline ``:slug:`` emoji — none of which a ``SegmentMessage`` swap could
    preserve. ``override`` (the transitions-supplied ``font_color``) replaces
    every segment's provider when set, so a section transition recolors the
    whole line uniformly. ``border`` paints once, before the text, at physical
    resolution. Empty-text segments are skipped (e.g. the no-time empty line).

    Returns the advanced cursor (+ end padding) so the engine's hold-vs-scroll
    check in ``_swap_and_scroll`` sees the full content width.
    """
    cursor_pos, end_padding = compute_cursor(
        canvas.width, content_width, cursor_pos, padding, center=center
    )
    if border is not None:
        border.paint(canvas, border_frame)
    for text, provider, frame in segments:
        if not text:
            continue
        color = override if override is not None else provider
        cursor_pos += draw_with_emoji(
            canvas,
            font,
            int(cursor_pos),
            baseline_y + y_offset,
            color,
            text,
            frame=frame,
            total_chars=count_text_chars(text),
        )
    cursor_pos += end_padding
    return canvas, cursor_pos


@attrs.define
class _TwoToneLine(FrameAwareBase):
    """One agenda feed-story line drawn in two colors.

    The time phrase renders in ``time_color`` and the event title in
    ``font_color``. ``_build_stories`` constructs one per upcoming event; a
    highlighted event is built with ``highlight_color`` for BOTH so the whole
    line reads in the highlight color (a highlight is a whole-event attention
    state). Mirrors the baseball attendance/promo two-tone lines.
    """

    time_text: str = ""
    title_text: str = ""
    font: Any = attrs.Factory(lambda: FONT_DEFAULT)
    time_color: ColorProvider = attrs.field(
        default=attrs.Factory(lambda: make_color(255, 200, 60)),
        converter=_coerce_provider,
        kw_only=True,
    )
    font_color: ColorProvider = attrs.field(
        default=attrs.Factory(lambda: make_color(255, 255, 255)),
        converter=_coerce_provider,
        kw_only=True,
    )
    bg_color: Any = attrs.field(default=None, kw_only=True)
    border: Any | None = attrs.field(default=None, kw_only=True)
    center: bool = True
    padding: int = 6
    _content_width: int = attrs.field(init=False, default=-1)
    _baseline_y: int = attrs.field(init=False, default=-1)

    def draw(
        self,
        canvas: Canvas,
        cursor_pos: int = 0,
        *,
        y_offset: int = 0,
        font_color: Any = None,
    ) -> DrawResult:
        if font_color is not None and not hasattr(font_color, "color_for"):
            font_color = _ConstantColor(font_color)
        if self._content_width < 0:
            self._content_width = sum(
                measure_width(self.font, t, canvas)
                for t in (self.time_text, self.title_text)
                if t
            )
        if self._baseline_y < 0:
            self._baseline_y = compute_baseline(self.font, canvas, valign="center")
        segments = [
            (self.time_text, self.time_color, self.frame_for("time_color")),
            (self.title_text, self.font_color, self.frame_for("font_color")),
        ]
        return _draw_two_tone(
            canvas,
            font=self.font,
            cursor_pos=cursor_pos,
            center=self.center,
            padding=self.padding,
            border=self.border,
            border_frame=self.frame_for("border"),
            segments=segments,
            override=font_color,
            y_offset=y_offset,
            baseline_y=self._baseline_y,
            content_width=self._content_width,
        )


@attrs.define
class _NextEventWidget(FrameAwareBase):
    """The layout='next' feed story: one live countdown line, recomputed each
    draw (engine _hold_ticks redraws held widgets, so the countdown ticks).

    Holds the full upcoming events list and picks the current soonest-future
    event live in draw(), so the widget rolls to the next event the moment the
    current one starts — no 900s stale-display stickiness.
    """

    events: list[CalendarEvent] = attrs.field(factory=list)
    empty_text: str = "No upcoming events"
    timezone: str | None = None
    font: Any = attrs.Factory(lambda: FONT_DEFAULT)
    font_color: ColorProvider = attrs.field(
        default=attrs.Factory(lambda: make_color(255, 255, 255)),
        converter=_coerce_provider,
        kw_only=True,
    )
    time_color: ColorProvider = attrs.field(
        default=attrs.Factory(lambda: make_color(255, 200, 60)),
        converter=_coerce_provider,
        kw_only=True,
    )
    highlight: list[str] = attrs.field(factory=list, kw_only=True)
    highlight_color: ColorProvider = attrs.field(
        default=attrs.Factory(lambda: make_color(255, 200, 60)),
        converter=_coerce_provider,
        kw_only=True,
    )
    bg_color: Any = attrs.field(default=None, kw_only=True)
    border: Any | None = attrs.field(default=None, kw_only=True)
    center: bool = True
    padding: int = 6
    _baseline_y: int = attrs.field(init=False, default=-1)
    _resolved_tz: tzinfo | None = attrs.field(init=False, default=None)
    _events_sorted: list[CalendarEvent] | None = attrs.field(init=False, default=None)

    def draw(
        self,
        canvas: Canvas,
        cursor_pos: int = 0,
        *,
        y_offset: int = 0,
        font_color: Any = None,
    ) -> DrawResult:
        if self._resolved_tz is None:
            self._resolved_tz = _resolve_tz(self.timezone)
        tz = self._resolved_tz
        now = _now_in(tz)  # ALWAYS aware (local when tz is None) — event.start
        # is aware, and format_relative subtracts them; a naive now -> TypeError.

        # Pick the soonest event live on each draw call so the widget rolls
        # automatically (no stale 900s window).  Prefer a timed event (countdown
        # is actionable); fall back to all-day only when no timed event is pending.
        # Fix #3: an all-day today sorts at midnight and would MASK every timed
        # event the same day with the old single-pass pick.
        # Fix #2: a multi-day all-day that started BEFORE today (start.date() <
        # today) was invisible with the old start.date()==today predicate.
        # `self.events` is fixed for the life of this widget (the Container
        # rebuilds a NEW _NextEventWidget on every update()), so sort once and
        # cache rather than re-sorting on every 20 Hz draw tick. parse_ics +
        # select_events already hand us a start-sorted list, but we sort
        # defensively so a directly-constructed widget (e.g. tests) is correct
        # regardless of input order — paid once, not per tick.
        if self._events_sorted is None:
            self._events_sorted = sorted(self.events, key=lambda e: e.start)
        events_sorted = self._events_sorted
        now_date = now.date()
        # 1) soonest not-yet-started timed event (the actionable countdown)
        event = next(
            (e for e in events_sorted if not e.all_day and e.start > now), None
        )
        if event is None:
            # 2) no timed event pending -> show a current/ongoing all-day.
            # Guard with _not_ended so a stale ended all-day (end <= now) is never
            # shown as "today" — either because it ended between fetches, or because
            # the fetch failed and stale events were retained.
            event = next(
                (
                    e
                    for e in events_sorted
                    if e.all_day and e.start.date() <= now_date and _not_ended(e, now)
                ),
                None,
            )
            if event is None:
                # 3) ...or the soonest future all-day
                event = next(
                    (e for e in events_sorted if e.all_day and e.start > now), None
                )

        if event is None:
            # 4) Final fallback: the most-recently-started in-progress timed event.
            # Timed events whose start <= now were future at fetch time but became
            # in-progress before the next update().  format_relative renders them as
            # "<summary> now" via the secs<=0 branch.
            # Guard with _not_ended so a stale ended timed event is never shown
            # as "now" indefinitely between fetches.
            in_progress = [
                e
                for e in events_sorted
                if not e.all_day and e.start <= now and _not_ended(e, now)
            ]
            event = in_progress[-1] if in_progress else None  # latest-started = current

        # Color: highlight wins for the currently-shown event; engine-supplied
        # font_color (passed by transitions) overrides both segments uniformly.
        # Two-tone: the title renders in font_color, the relative phrase (with
        # its leading separator) in time_color. A highlighted current event uses
        # highlight_color for BOTH (whole-line attention state).
        if font_color is not None and not hasattr(font_color, "color_for"):
            font_color = _ConstantColor(font_color)
        use_highlight = (
            font_color is None
            and event is not None
            and _match_any(event.summary, self.highlight)
        )
        title_text, time_text = split_relative(event, now, self.empty_text)
        if use_highlight:
            title_provider = time_provider = self.highlight_color
            title_frame = time_frame = self.frame_for("highlight_color")
        else:
            title_provider = self.font_color
            time_provider = self.time_color
            title_frame = self.frame_for("font_color")
            time_frame = self.frame_for("time_color")

        # Content (the countdown) changes every draw tick, so measure each time
        # rather than caching — only the baseline cache survives across ticks.
        content_width = sum(
            measure_width(self.font, t, canvas) for t in (title_text, time_text) if t
        )
        if self._baseline_y < 0:
            self._baseline_y = compute_baseline(self.font, canvas, valign="center")

        segments = [
            (title_text, title_provider, title_frame),
            (time_text, time_provider, time_frame),
        ]
        return _draw_two_tone(
            canvas,
            font=self.font,
            cursor_pos=cursor_pos,
            center=self.center,
            padding=self.padding,
            border=self.border,
            border_frame=self.frame_for("border"),
            segments=segments,
            override=font_color,
            y_offset=y_offset,
            baseline_y=self._baseline_y,
            content_width=content_width,
        )


@register("calendar")
@attrs.define
class Calendar:
    """Container that shows upcoming .ics events as an agenda or next-event line."""

    # Per-widget hint overrides for ``--list-fields calendar``.
    # Defined as plain 3-tuples (display_type, description, default_display)
    # to avoid importing ``FieldHint`` from ``led_ticker.app.factories`` —
    # that import would be circular (factories imports widgets).
    # ``_list_widget_fields`` coerces plain tuples to ``FieldHint`` before use.
    _LIST_FIELD_HINTS: ClassVar[dict] = {
        "layout": (
            '"agenda" | "next"',
            "agenda = rotating events list; next = live countdown to the next event",
            '"agenda"',
        ),
    }

    session: aiohttp.ClientSession
    ics_url: str
    layout: str = "agenda"
    max_events: int = 5
    lookahead_days: int = 7
    time_format: str = "12h"
    timezone: str | None = None
    empty_text: str = "No upcoming events"
    # Shown on the panel when the FIRST load fails (no prior good data) — kept
    # distinct from empty_text so a broken feed doesn't masquerade as "no
    # events". A transient refresh failure keeps the last-good stories instead.
    error_text: str = "Calendar unavailable"
    filter: list[str] = attrs.field(factory=list)
    highlight: list[str] = attrs.field(factory=list)
    padding: int = 6
    font: Font = attrs.Factory(lambda: FONT_DEFAULT)
    font_color: ColorProvider = attrs.field(
        default=attrs.Factory(lambda: make_color(255, 255, 255)),
        converter=_coerce_provider,
        kw_only=True,
    )
    time_color: ColorProvider = attrs.field(
        default=attrs.Factory(lambda: make_color(255, 200, 60)),
        converter=_coerce_provider,
        kw_only=True,
    )
    highlight_color: ColorProvider = attrs.field(
        default=attrs.Factory(lambda: make_color(255, 200, 60)),
        converter=_coerce_provider,
        kw_only=True,
    )
    bg_color: Any = attrs.field(default=None, kw_only=True)
    border: Any | None = attrs.field(default=None, kw_only=True)
    feed_stories: list[Widget] = attrs.field(init=False, factory=list)
    feed_title: TickerMessage | None = attrs.field(init=False, default=None)

    @classmethod
    def validate_config(cls, cfg: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        ics_url = cfg.get("ics_url")
        if not isinstance(ics_url, str) or not ics_url.strip():
            errors.append("ics_url is required and must be a non-empty string")
        elif any(tok in ics_url.upper() for tok in ("PASTE", "YOUR_", "_HERE")):
            # An unfilled template value (e.g. "PASTE_YOUR_..._ICS_URL_HERE" from
            # the smoke config). Catch it at validate/startup with a clear
            # message rather than letting it fail at runtime as a FileNotFound.
            errors.append(
                f"ics_url looks like an unfilled placeholder ({ics_url!r}) — "
                "paste your real .ics URL (Google/iCloud/Outlook 'iCal' link)"
            )
        layout = cfg.get("layout", "agenda")
        if layout not in ("agenda", "next"):
            errors.append(f"layout {layout!r} must be 'agenda' or 'next'")
        tz = cfg.get("timezone")
        if tz:  # empty string / None => use system-local default (see _resolve_tz)
            if not isinstance(tz, str):
                errors.append(
                    f"timezone must be a string IANA name, got {type(tz).__name__}"
                )
            else:
                try:
                    ZoneInfo(tz)
                except ZoneInfoNotFoundError, ValueError, OSError:
                    errors.append(f"timezone {tz!r} is not a valid IANA timezone name")
        for key in ("filter", "highlight"):
            val = cfg.get(key)
            if val is not None and (
                not isinstance(val, list) or not all(isinstance(x, str) for x in val)
            ):
                errors.append(f"{key} must be a list of strings")
        for key in ("max_events", "lookahead_days"):
            val = cfg.get(key)
            if val is not None and (
                isinstance(val, bool) or not isinstance(val, int) or val < 0
            ):
                errors.append(f"{key} must be a non-negative integer")
        ld = cfg.get("lookahead_days")
        if isinstance(ld, int) and not isinstance(ld, bool) and ld > 366:
            errors.append("lookahead_days must be <= 366")
        fmt = cfg.get("time_format", "12h")
        if not isinstance(fmt, str):
            errors.append(
                f"time_format must be a string ('12h'/'24h' or a strftime "
                f"template), got {type(fmt).__name__}"
            )
        elif "%" not in fmt and fmt not in ("12h", "24h"):
            errors.append(
                f"time_format {fmt!r} is not '12h'/'24h' or a strftime template"
            )
        return errors

    @classmethod
    async def start(
        cls,
        session: aiohttp.ClientSession,
        ics_url: str,
        update_interval: int = 900,
        **kwargs: Any,
    ) -> Self:
        widget = cls(session=session, ics_url=ics_url, **kwargs)
        await widget.update()
        spawn_tracked(run_monitor_loop(widget, update_interval))
        return widget

    async def _fetch_ics(self) -> str:
        url = _normalize_ics_url(self.ics_url)
        if url.startswith(("http://", "https://")):
            async with self.session.get(url) as resp:
                resp.raise_for_status()
                # Fix 3 (round-11): read raw bytes and decode as UTF-8 (with
                # replacement) rather than letting aiohttp guess the charset.
                # .ics is UTF-8 per RFC 5545; a missing/wrong charset header
                # can cause UnicodeDecodeError with resp.text().  The BOM-lstrip
                # in parse_ics handles any leading U+FEFF.
                raw = await resp.read()
                return raw.decode("utf-8", errors="replace")
        # file:// or a bare local path -> read from disk (offline calendars,
        # demos, tests). aiohttp cannot fetch file://. NOTE: a relative path is
        # resolved against the process CWD, not the config dir — prefer an
        # absolute path (file:///abs or /abs) for deployed configs.
        # Percent-decode only the file:// form; bare paths are taken literally
        # so a path that contains literal %41 is not silently rewritten to A.
        # Fix 6: RFC 8089 allows file://localhost/abs/path as equivalent to
        # file:///abs/path — strip the 'localhost' host so the leading '/'
        # is preserved in the resolved path.
        if url.startswith("file://"):
            raw = url[len("file://") :]
            if raw.startswith("localhost/"):
                raw = raw[len("localhost") :]  # -> "/abs/path"
            path = unquote(raw)
        else:
            path = url
        return await asyncio.to_thread(
            lambda: Path(path).expanduser().read_text(encoding="utf-8")
        )

    def _error_story(self) -> TickerMessage:
        """First-load failure placeholder — error_text, distinct from empty."""
        return TickerMessage(
            self.error_text,
            font=self.font,
            font_color=self.font_color,
            bg_color=self.bg_color,
            border=self.border,
            padding=self.padding,
        )

    def _empty_story(self) -> TickerMessage:
        return TickerMessage(
            self.empty_text,
            font=self.font,
            font_color=self.font_color,
            bg_color=self.bg_color,
            border=self.border,
            padding=self.padding,
        )

    async def update(self) -> None:
        logger.info("Updating calendar from: %s", self.ics_url)
        tz = _resolve_tz(self.timezone)
        try:
            text = await self._fetch_ics()
            now = _now_in(tz)  # ALWAYS aware (local when tz is None)
            # concrete tzinfo (never None) — keeps all comparisons aware
            parse_tz = now.tzinfo
            assert parse_tz is not None  # _now_in guarantees an aware datetime
            events = await asyncio.to_thread(
                parse_ics,
                text,
                now=now,
                lookahead_days=self.lookahead_days,
                tz=parse_tz,
            )
            if self.layout == "next":
                # For next mode: filter only, no highlight reordering, no cap.
                # The widget picks the soonest event live in draw(), so we hand
                # it the full chronological list — highlight distortion via cap
                # cannot hide a sooner event this way.
                kept = select_events(
                    events,
                    filter=self.filter,
                    highlight=[],
                    max_events=0,
                )
            else:
                kept = select_events(
                    events,
                    filter=self.filter,
                    highlight=self.highlight,
                    max_events=self.max_events,
                )
            self.feed_stories = self._build_stories(kept, now=now, tz=parse_tz)
            logger.info("Calendar %s updated: %d events", self.ics_url, len(kept))
        except Exception as exc:
            # Concise, actionable WARNING — the full traceback (rarely useful to
            # an end user staring at a sign) is demoted to DEBUG. On a FIRST-load
            # failure show error_text; a transient refresh failure keeps the
            # last-good stories (don't blank a working sign on a blip).
            logger.warning(_describe_fetch_error(exc, self.ics_url))
            logger.debug("Calendar fetch/parse traceback", exc_info=True)
            if not self.feed_stories:
                self.feed_stories = [self._error_story()]

    def _build_stories(
        self, events: list[CalendarEvent], *, now: datetime, tz: tzinfo
    ) -> list[Widget]:
        if self.layout == "next":
            return [
                _NextEventWidget(
                    events=events,
                    empty_text=self.empty_text,
                    timezone=self.timezone,
                    font=self.font,
                    font_color=self.font_color,
                    time_color=self.time_color,
                    highlight=self.highlight,
                    highlight_color=self.highlight_color,
                    bg_color=self.bg_color,
                    border=self.border,
                    padding=self.padding,
                )
            ]
        # agenda
        if not events:
            return [self._empty_story()]
        stories: list[Widget] = []
        for e in events:
            # Two-tone: time phrase in time_color, title in font_color. A
            # highlighted event uses highlight_color for BOTH (whole-line
            # attention state), so two-tone applies to non-highlighted lines.
            if _match_any(e.summary, self.highlight):
                time_color = title_color = self.highlight_color
            else:
                time_color = self.time_color
                title_color = self.font_color
            time_text, title_text = split_event_line(
                e, now=now, time_format=self.time_format, tz=tz
            )
            stories.append(
                _TwoToneLine(
                    time_text=time_text,
                    title_text=title_text,
                    font=self.font,
                    time_color=time_color,
                    font_color=title_color,
                    bg_color=self.bg_color,
                    border=self.border,
                    padding=self.padding,
                )
            )
        return stories
