"""Calendar widget: upcoming events from a subscribed iCal (.ics) feed.

Always a Container (like rss_feed): a shared data core fetches + parses the
feed, then update() populates feed_stories per the `layout` knob — `agenda`
builds one TickerMessage per event; `next` builds one live countdown widget.
"""

import asyncio
import itertools
import logging
from datetime import date, datetime, time, timedelta, tzinfo
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
from led_ticker.drawing import compute_baseline, compute_cursor, get_text_width
from led_ticker.fonts import FONT_DEFAULT
from led_ticker.text_render import draw_text, draw_text_per_char
from led_ticker.widget import Widget, run_monitor_loop, spawn_tracked
from led_ticker.widgets import register
from led_ticker.widgets._frame_aware import FrameAwareBase
from led_ticker.widgets.clock import format_clock
from led_ticker.widgets.message import TickerMessage

logger = logging.getLogger(__name__)

# Bound memory against pathological/hostile high-frequency RRULEs (e.g. FREQ=SECONDLY).
# islice ensures we never materialize more than this many occurrences.
_MAX_OCCURRENCES = 2000


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

    Uses a lazy generator + islice to cap at _MAX_OCCURRENCES to prevent OOM on
    hostile/pathological high-frequency RRULEs (e.g. FREQ=SECONDLY). islice
    bounds the scan; events past window_end are skipped via `continue` (not an
    early `break`) because all-day events resolve to display-tz midnight and can
    reorder relative to timed events across a negative UTC offset. Also strips a
    leading UTF-8 BOM (U+FEFF) so Outlook/Exchange feeds parse correctly.
    """
    # Fix 4: strip leading BOM before parsing (Outlook/Exchange/.ics feeds)
    text = text.lstrip("﻿")
    cal = icalendar.Calendar.from_ical(text)
    window_end = now + timedelta(days=lookahead_days)

    # Fix 1: use lazy .after(now) + islice to bound memory against pathological RRULEs.
    # .after(now) filters occurrences whose END is after now, ascending by start.
    events: list[CalendarEvent] = []
    count = 0
    for comp in itertools.islice(
        recurring_ical_events.of(cal).after(now), _MAX_OCCURRENCES
    ):
        count += 1
        # Fix 1: skip STATUS:CANCELLED events (declined/cancelled meetings,
        # cancelled occurrence overrides from Google/Outlook/iCloud feeds).
        if str(comp.get("STATUS", "")).upper() == "CANCELLED":
            continue
        # Fix 5: collapse whitespace (embedded newlines/tabs from icalendar
        # unescaping \n) so SUMMARY renders cleanly on a single-line panel.
        summary = " ".join(str(comp.get("SUMMARY", "")).split())
        if not summary:
            continue
        dtstart = comp.get("DTSTART")
        if dtstart is None:
            continue
        start, all_day = _to_display_start(dtstart.dt, tz)
        # Fix 4: use continue (not break) here — all-day events resolved to
        # display-tz midnight can reorder relative to timed events across a
        # negative UTC offset (the Americas), so a break here can fire early
        # and drop valid in-window timed events. islice already bounds the loop.
        if start > window_end:
            continue
        # belt-and-suspenders: .after() already excludes ended occurrences;
        # this guards malformed/edge feeds.
        if all_day:
            dtend = comp.get("DTEND")
            if dtend is not None:
                end, _ = _to_display_start(dtend.dt, tz)  # exclusive end
            else:
                end = start + timedelta(days=1)
            if end <= now:  # ended before now -> past
                continue
        elif start < now:
            continue
        events.append(CalendarEvent(summary=summary, start=start, all_day=all_day))
    else:
        # Loop completed (didn't break) — check if we hit the islice cap
        if count >= _MAX_OCCURRENCES:
            logger.warning(
                "Calendar feed produced >= %d occurrences in the window; "
                "truncated (check the feed's RRULE)",
                _MAX_OCCURRENCES,
            )

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
    if delta_days == 0:
        return "Today"
    if delta_days == 1:
        return "Tomorrow"
    if 2 <= delta_days < 7:
        return _WEEKDAY_ABBR[start.weekday()]
    return f"{_MONTH_ABBR[start.month - 1]} {start.day}"


def format_event_line(
    event: CalendarEvent, *, now: datetime, time_format: str, tz: tzinfo
) -> str:
    """Agenda line: '<day> <time>  <summary>'; all-day omits the time."""
    day = _day_label(event.start, now)
    if event.all_day:
        return f"{day}  {event.summary}"
    return f"{day} {format_clock(event.start, time_format)}  {event.summary}"


def format_relative(event: CalendarEvent | None, now: datetime, empty_text: str) -> str:
    """Next-mode line: '<summary> in <rel>' / '<summary> now' / empty_text.

    All-day events are rendered by day (today/tomorrow/in Nd) rather than by
    seconds, since their start is always midnight and a seconds-based delta
    would produce misleading "now" or "in 14h" labels.
    """
    if event is None:
        return empty_text
    if event.all_day:
        days = (event.start.date() - now.date()).days
        if days <= 0:
            return f"{event.summary} today"
        if days == 1:
            return f"{event.summary} tomorrow"
        return f"{event.summary} in {days}d"
    delta = event.start - now
    secs = delta.total_seconds()
    if secs <= 0:
        return f"{event.summary} now"
    days = int(secs // 86400)
    if days >= 1:
        return f"{event.summary} in {days}d"
    hours = int(secs // 3600)
    minutes = int((secs % 3600) // 60)
    if hours >= 1:
        if minutes == 0:
            return f"{event.summary} in {hours}h"
        return f"{event.summary} in {hours}h {minutes}m"
    if minutes == 0:
        # sub-minute and imminent -> treat as happening now
        return f"{event.summary} now"
    return f"{event.summary} in {minutes}m"


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
        default=None, converter=_coerce_provider, kw_only=True
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

    def draw(
        self,
        canvas: Canvas,
        cursor_pos: int = 0,
        *,
        y_offset: int = 0,
        font_color: Any = None,
    ) -> DrawResult:
        tz = _resolve_tz(self.timezone)
        now = _now_in(tz)  # ALWAYS aware (local when tz is None) — event.start
        # is aware, and format_relative subtracts them; a naive now -> TypeError.

        # Pick the soonest event live on each draw call so the widget rolls
        # automatically (no stale 900s window).  Prefer a timed event (countdown
        # is actionable); fall back to all-day only when no timed event is pending.
        # Fix #3: an all-day today sorts at midnight and would MASK every timed
        # event the same day with the old single-pass pick.
        # Fix #2: a multi-day all-day that started BEFORE today (start.date() <
        # today) was invisible with the old start.date()==today predicate.
        events_sorted = sorted(self.events, key=lambda e: e.start)
        now_date = now.date()
        # 1) soonest not-yet-started timed event (the actionable countdown)
        event = next(
            (e for e in events_sorted if not e.all_day and e.start > now), None
        )
        if event is None:
            # 2) no timed event pending -> show a current/ongoing all-day
            #    (parse_ics already dropped ENDED all-days, so start.date() <=
            #    now_date means genuinely ongoing today)
            event = next(
                (e for e in events_sorted if e.all_day and e.start.date() <= now_date),
                None,
            )
            if event is None:
                # 3) ...or the soonest future all-day
                event = next(
                    (e for e in events_sorted if e.all_day and e.start > now), None
                )

        # Color: highlight wins for the currently-shown event; engine-supplied
        # font_color (passed by transitions) takes precedence over both.
        if font_color is not None and not hasattr(font_color, "color_for"):
            font_color = _ConstantColor(font_color)
        use_highlight = (
            font_color is None
            and event is not None
            and _match_any(event.summary, self.highlight)
        )
        provider: ColorProvider = font_color or (
            self.highlight_color if use_highlight else self.font_color
        )
        frame_key = "highlight_color" if use_highlight else "font_color"

        text = format_relative(event, now, self.empty_text)

        content_width = get_text_width(self.font, text, padding=0, canvas=canvas)
        cursor_pos, end_padding = compute_cursor(
            canvas.width, content_width, cursor_pos, self.padding, center=self.center
        )
        if self._baseline_y < 0:
            self._baseline_y = compute_baseline(self.font, canvas, valign="center")
        baseline_y = self._baseline_y

        if self.border is not None:
            self.border.paint(canvas, self.frame_for("border"))

        if provider.per_char:
            cursor_pos += draw_text_per_char(
                canvas,
                self.font,
                cursor_pos,
                baseline_y + y_offset,
                text,
                lambda idx, total: provider.color_for(
                    self.frame_for(frame_key), idx, total
                ),
            )
        else:
            color = provider.color_for(self.frame_for(frame_key), 0, len(text))
            cursor_pos += draw_text(
                canvas, self.font, cursor_pos, baseline_y + y_offset, color, text
            )
        cursor_pos += end_padding
        return canvas, cursor_pos


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
    filter: list[str] = attrs.field(factory=list)
    highlight: list[str] = attrs.field(factory=list)
    padding: int = 6
    font: Font = attrs.Factory(lambda: FONT_DEFAULT)
    font_color: ColorProvider = attrs.field(
        default=None, converter=_coerce_provider, kw_only=True
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
        layout = cfg.get("layout", "agenda")
        if layout not in ("agenda", "next"):
            errors.append(f"layout {layout!r} must be 'agenda' or 'next'")
        tz = cfg.get("timezone")
        if tz is not None:
            if not isinstance(tz, str):
                errors.append(
                    f"timezone must be a string IANA name, got {type(tz).__name__}"
                )
            else:
                try:
                    ZoneInfo(tz)
                except ZoneInfoNotFoundError, ValueError:
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
                return await resp.text()
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
        return await asyncio.to_thread(Path(path).expanduser().read_text)

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
        except Exception:
            logger.exception("Calendar fetch/parse failed for %s", self.ics_url)
            if not self.feed_stories:
                self.feed_stories = [self._empty_story()]

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
            color = (
                self.highlight_color
                if _match_any(e.summary, self.highlight)
                else self.font_color
            )
            stories.append(
                TickerMessage(
                    format_event_line(e, now=now, time_format=self.time_format, tz=tz),
                    font=self.font,
                    font_color=color,
                    bg_color=self.bg_color,
                    border=self.border,
                    padding=self.padding,
                )
            )
        return stories
