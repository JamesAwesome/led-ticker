# Calendar widget — design

**Date:** 2026-06-13
**Status:** approved design, pre-implementation
**Context:** Steal #3, part 2 from the LEDMatrix comparison (clock + calendar). The
clock shipped in PR #204; this is the calendar. **Data source is a subscribed
iCal (`.ics`) URL — Google OAuth was explicitly rejected.** The widget is a
sibling to the clock and reuses the async-data pattern of `weather` / `rss_feed`.

## Summary

A new `type = "calendar"` widget that fetches a public `.ics` feed over HTTP,
parses it (recurrence-expanded), and shows upcoming events. It is **always a
Container** (like `rss_feed`): a shared data core fetches + parses, then
populates `feed_stories` according to a `layout` knob:

- **`layout = "agenda"`** (default) — each upcoming event becomes its own
  `TickerMessage` in `feed_stories`; the playlist rotates through them. This is
  the `rss_feed` pattern verbatim and reuses all message rendering.
- **`layout = "next"`** — `feed_stories` holds a single live countdown widget
  that recomputes "in 25m" every draw (the clock's `_hold_ticks` redraw
  mechanism). An empty window yields one `empty_text` message.

A keyword **`filter`** (keep-only) and **`highlight`** (recolor + guaranteed
inclusion) mirror the baseball-promotions widget. New core dependencies:
`icalendar` + `recurring-ical-events` (pure-Python, MIT).

## Why "always a Container" (the both-modes mechanism)

The engine detects a Container **structurally**: `Container` is a
`@runtime_checkable Protocol` in `widget.py` whose sole member is
`feed_stories: list[Widget]`, and `_expand_sources` (in `ticker.py`) re-reads it
on every pass. Because detection keys on the *presence* of `feed_stories` (a
class-level attrs field), a single class cannot cleanly be **both** a Container
and a `draw()` widget switched by a runtime flag — the structural check would
always treat it as a Container and never call its `draw()`.

The clean resolution: the calendar is **always** a Container. `layout` changes
only what `update()` puts into `feed_stories`:

- `agenda` → a list of `TickerMessage` (one per event).
- `next` → a list of exactly one live-countdown widget (`_NextEventWidget`,
  below), or one `empty_text` message when nothing is upcoming.

Both are proven patterns: `agenda` *is* `rss_feed`; the live countdown *is* the
clock mechanism (a held, non-overflowing `draw()` widget that recomputes its
text each tick via the engine's `_hold_ticks` loop). No new engine code.

## Components

### `widgets/calendar.py`

- **`CalendarEvent`** (`@attrs.define`, frozen-ish value object): the parsed,
  display-ready event — `summary: str`, `start: datetime` (tz-aware, resolved to
  the display timezone), `all_day: bool`. Pure data; no rendering.
- **`Calendar`** (`@register("calendar") @attrs.define`): the Container. Fields:
  `session: aiohttp.ClientSession`, `ics_url: str`, config knobs (below),
  `feed_stories: list[Widget] = attrs.field(init=False, factory=list)`,
  `feed_title: TickerMessage | None = attrs.field(init=False, default=None)`
  (optional section title, like `rss_feed`). It satisfies `Container`
  structurally and `Updatable` via `update()`.
- **`start(cls, session, ics_url, update_interval=900, **kwargs)`** classmethod
  (mirrors `rss_feed` / `weather`): construct, `await update()` once, then
  `spawn_tracked(run_monitor_loop(widget, update_interval))`.
- **`update(self)`** async: fetch → parse → expand recurrence → filter → window
  → sort → cap → build `feed_stories` per `layout`. Emits one INFO log per call
  (`"Calendar <name> updated: N events"`) — the silent-stream-means-dead-task
  diagnostic the longboi container note calls for. Errors keep the last good
  `feed_stories` (see Error handling).
- **`_NextEventWidget`** (`@attrs.define`, `FrameAwareBase`): the `layout="next"`
  feed story. Holds one `CalendarEvent` (or `None`) + formatting knobs. Its
  `draw()` recomputes `now` each call and renders `"<summary> in <rel>"` /
  `"<summary> now"` / `empty_text`. Lives in the same file. Mirrors the clock's
  draw structure (constant-vs-per-char color dispatch, optional border, baseline
  cache) — recomputing each draw keeps the countdown live with zero engine work.

### Parsing core (in `widgets/calendar.py`, pure functions for testability)

- **`parse_ics(text: str, *, now, lookahead_days, tz) -> list[CalendarEvent]`**:
  `icalendar.Calendar.from_ical(text)`, then
  `recurring_ical_events.of(cal).between(now, now + timedelta(days=lookahead_days))`
  to expand RRULE occurrences within the window. Map each component to a
  `CalendarEvent`: `summary` from `SUMMARY`; `start` from `DTSTART` (a
  `datetime` → resolve to `tz`; a `date` → `all_day=True`, start at local
  midnight of that date in `tz`); drop events whose start is in the past
  relative to `now` (an all-day event is "upcoming" through the end of its day).
  Return sorted by `start`. Pure: `now`/`tz` injected → no wall-clock flakiness.
- **`_match_any(summary: str, keywords: list[str]) -> bool`**: case-insensitive
  substring match against any keyword — identical semantics to the baseball
  `promotions._match_any`. (Local copy; it is not on the public plugin surface.)

## Config knobs

Under `[[playlist.section.widget]]` with `type = "calendar"`:

- **`ics_url`** (str, **required**): a public `.ics` URL — the "secret address in
  iCal format" Google/iCloud/Outlook expose. No auth in v1 (the secret URL *is*
  the credential).
- **`layout`** (str, `"agenda"` | `"next"`, default `"agenda"`).
- **`max_events`** (int, default `5`): cap on agenda stories (post-filter,
  post-highlight-inclusion).
- **`lookahead_days`** (int, default `7`): recurrence-expansion + filter window.
- **`time_format`** (str, `"12h"` | `"24h"`, default `"12h"`): reuses the clock's
  `format_clock` for the time portion of a line.
- **`timezone`** (str, optional IANA; default system local): resolved via stdlib
  `zoneinfo`. Events are converted to this zone for display. Mirrors the clock.
- **`empty_text`** (str, default `"No upcoming events"`): shown when the window
  has no (post-filter) events, and on first-load fetch failure.
- **`filter`** (list[str], default `[]`): keep only events whose summary matches
  any keyword (case-insensitive substring); empty = all.
- **`highlight`** (list[str], default `[]`): events whose summary matches render
  in `highlight_color` and are **guaranteed to survive the `max_events` cap**.
- **`highlight_color`** (color/provider, default `[255, 200, 60]` — the amber the
  baseball widget uses): accepts the same shapes as `font_color`.
- **`update_interval`** (int seconds, default `900`): passed to
  `run_monitor_loop`. (The `next`-mode countdown stays smooth *between* updates
  via per-tick redraw; `update_interval` only governs how often the "which event
  is next / what's in the window" set is recomputed.)
- **Standard text knobs** via name-keyed coercion (same as `rss_feed` /
  `message`): `font`, `font_color`, `bg_color`, `border`, `font_threshold`,
  `padding`. `font_color` is the default per-event color (a provider like
  `"rainbow"` applies per event, as in `rss_feed`).

## Selection, ordering, and highlight

In `update()`, after parsing to the sorted-by-time `events` list:

1. **Filter**: if `filter` is non-empty, keep only `_match_any(e.summary, filter)`.
2. **Cap with guaranteed highlight inclusion** (agenda): partition into
   `highlighted = [e for e in events if _match_any(e.summary, highlight)]` and
   the rest. Take all highlighted first (capped at `max_events`), then fill the
   remaining slots with the soonest non-highlighted events, then **re-sort the
   kept set by `start`** for display. Result: highlighted events are never the
   ones dropped, but the agenda still reads in chronological order.
   *(Deliberate divergence from baseball, which sorts highlighted-first;
   approved — a calendar reads best in time order.)*
3. **Build feed_stories**:
   - `agenda` → one `TickerMessage` per kept event; text =
     `format_event_line(event, time_format, tz)`; color = `highlight_color` if
     the event is highlighted else `font_color`; standard `font` / `bg_color` /
     `border` / `padding` passed through.
   - `next` → take the soonest kept event (post-filter); build one
     `_NextEventWidget(event, ...)` whose color is `highlight_color` when that
     event is highlighted, else `font_color`. No events → one `TickerMessage`
     with `empty_text`.

## Formatting

- **`format_event_line(event, time_format, tz) -> str`** (agenda): `"<day>
  <time>  <summary>"`. `day` is a smart label relative to today in `tz`:
  `"Today"` / `"Tomorrow"` / weekday abbrev (`"Mon"`) for within the week /
  `"%b %-d"`-style date further out (built from `datetime` fields, not `%-`
  codes, for cross-platform determinism — same rule as the clock). `time` via
  the clock's `format_clock(event.start, time_format)`. All-day events omit the
  time: `"<day>  <summary>"`.
- **Next-mode relative** (`_NextEventWidget.draw`): delta = `event.start - now`.
  `>= 1 day` → `"<summary> in 3d"`; `>= 1 hour` → `"<summary> in 2h 10m"`;
  `< 1 hour` → `"<summary> in 25m"`; event started but not over → `"<summary>
  now"`; `event is None` → `empty_text`.

## Error handling

- **Fetch / parse failure**: caught in `update()`; log and **keep the previous
  `feed_stories`** (so a transient network blip doesn't blank the panel).
  `run_monitor_loop` already retries with exponential backoff. A parse error
  must never propagate out of `update()` — Container error isolation; a broken
  feed must not crash or freeze the display.
- **First-load failure** (no previous good data): `feed_stories = [TickerMessage
  with empty_text]` so the section is never blank.
- **Empty window** (fetch ok, no upcoming/post-filter events): same single
  `empty_text` message.
- **Config-load validation** via `validate_config(cls, cfg) -> list[str]`
  (the idiomatic classmethod hook, as on the clock): require `ics_url`
  (non-empty str); `layout` in `{"agenda","next"}`; `timezone` a valid IANA name
  (catch `ZoneInfoNotFoundError` / `ValueError`, and reject non-str — the clock's
  exact guards); `filter` / `highlight` each a list of strings (the baseball
  `validate_config` shape); `max_events` / `lookahead_days` non-negative ints.
- **All-day vs timed** ambiguity is resolved at parse time (a `date` DTSTART →
  `all_day`), so rendering never has to guess.

## Files

- **Create:** `src/led_ticker/widgets/calendar.py`;
  `tests/test_widgets/test_calendar.py`; a fixture `.ics`
  (`tests/fixtures/calendar_sample.ics`) with a one-off, an all-day, and an
  RRULE event.
- **Append-only:**
  - `src/led_ticker/widgets/__init__.py` — add `calendar` to the auto-import
    tuple.
  - `pyproject.toml` — add `icalendar` and `recurring-ical-events` to
    `dependencies`. **Plugin note:** these become core *pinned* deps under the
    constraints mechanism; document in the PR.
  - `src/led_ticker/app/factories.py` — add new GLOBAL `FIELD_HINTS` entries for
    the calendar-specific keys (`ics_url`, `layout`, `lookahead_days`,
    `time_format`, `filter`, `highlight`, `highlight_color`, `empty_text`,
    `max_events`) for `--list-fields calendar`.
  - The `Calendar` Container declares the standard text knobs (`font`,
    `font_color`, `bg_color`, `border`, `font_threshold`, `padding`) as fields so
    config values land on it; `update()` passes them through to the agenda
    `TickerMessage`s and the `_NextEventWidget`. Declaring `border` on `Calendar`
    (and on `_NextEventWidget`) satisfies the factory border gate via
    `_widget_declares_field` — no edit to the border-type allowlist needed (same
    path the clock took).
- **Docs — two trees** (same as the clock): `docs/site/src/content/docs/widgets/
  calendar.mdx` (user docs, with a `<DemoGif>`) AND `docs/content-source/widgets/
  calendar.md` (fact-pack). Add `calendar` to the widgets index page (bump the
  count + add a row) and the sidebar nav in `astro.config.mjs`. If the fact-pack
  advertises `border`, add `calendar` to `FACT_PACK_FILES` in
  `tests/test_border_surface_drift.py`. Update the registry-count test.
- **Demo gif(s):** a source TOML in `docs/site/demos/` (`widget-calendar.toml`,
  agenda layout) rendered to `docs/site/public/demos/widget-calendar.gif`; the
  demo TOML must use `chain_length` (not the stale `chain`) per the new
  `tests/test_demo_config_keys.py` tripwire. The calendar fetches a live URL, so
  the demo uses a small committed sample `.ics` served via a `file://` URL or a
  local fixture path the renderer can read (decide in the plan; a `file://` path
  to a committed `.ics` keeps the render deterministic and offline).

## Testing

- **`parse_ics` (pure):** feed the fixture `.ics` with injected `now` + `tz`;
  assert (a) the one-off event parses with correct tz-resolved `start`; (b) the
  all-day event is `all_day=True` and upcoming through its day; (c) the RRULE
  event expands to the expected occurrences inside the window and none outside;
  (d) past events are dropped; (e) result sorted by `start`. Zero wall-clock
  flakiness (now injected).
- **`update()` (mocked aiohttp):** patch the session to return the fixture; assert
  `feed_stories` is built per `layout` — N `TickerMessage`s in agenda, one
  `_NextEventWidget` in next; INFO log emitted.
- **Filter / highlight:** `filter` narrows the set; `highlight` recolors matched
  events (`highlight_color`) and guarantees their inclusion under a small
  `max_events` while the displayed order stays chronological.
- **Next-mode countdown:** `_NextEventWidget.draw` with injected `now` — `"in
  25m"`, `"in 2h 10m"`, `"in 3d"`, `"now"` (in-progress), and `empty_text`
  (None). Frame-advance like the clock so a rainbow `font_color` animates.
- **Container behavior:** widget exposes `feed_stories`; engine re-reads it
  (mutate-and-pull); empty / first-load-failure → single `empty_text` message;
  a fetch exception keeps the previous `feed_stories` and never propagates.
- **`validate_config`:** missing `ics_url`, bad `layout`, bad/non-str
  `timezone`, non-list `filter`/`highlight`, negative `max_events`.
- **`--list-fields calendar`** coverage; border-surface drift updated if the
  fact-pack advertises `border`; registry-count test bumped.

## Out of scope (v1)

- Private feeds needing real auth (basic auth / tokens beyond the secret URL).
- Writing to the calendar; RSVP; any mutation.
- Multi-calendar merge in one widget (use multiple `calendar` widgets / sections).
- Two-row layout (held date over scrolling title) — a possible v2 reusing the
  two_row band layout.
- Per-event color rules beyond the single `highlight` keyword set.
- New dependency beyond `icalendar` + `recurring-ical-events`.
