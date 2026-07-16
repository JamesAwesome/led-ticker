# Widget & Section Scheduling — Design

**Date:** 2026-07-15
**Status:** Approved (brainstorming complete)

## Problem

Users want the sign's content to change by time of day — e.g. an "OPEN" image
during business hours and a "CLOSED" image otherwise. Today the only
time-driven behavior is `[display.schedule]` (brightness windows, which can
dark the panel but cannot swap content) and per-widget hacks like
`TickerCountdown.should_display()`.

This must be a **core engine feature**: plugins and widgets must not have to
implement (or even be able to observe) scheduling, and the TOML surface must
not overlap or collide with widget-owned fields.

## Decisions (settled during brainstorming)

1. **Granularity:** both widget-level and section-level `schedule`.
2. **Syntax:** single time window + optional day-of-week filter, aligned with
   the existing `[display.schedule]` window vocabulary (`start`/`end` HH:MM,
   `days`, overnight wrap). No `between = "HH:MM-HH:MM"` string form, no cron.
3. **Ownership:** `schedule` is a hard-reserved core field name. Popped at
   dispatch level before widget construction; any widget class (core or
   plugin) that declares its own `schedule` field is rejected loudly at
   config-load. Core scheduling ANDs with a widget's own `should_display()`.
4. **Clock:** system local time by default; new optional `[display] timezone`
   (IANA / zoneinfo) overrides, shared by visibility and brightness schedules.
5. **Mechanism:** engine-side schedule registry + a check in
   `_expand_sources` beside the existing `should_display()` filter (Approach A
   — no widget wrapping, no `WidgetEntry` refactor).

## Config surface

```toml
[display]
timezone = "America/New_York"   # NEW, optional; IANA name; "" = system local.
                                # One clock for all schedules (visibility + brightness).

[[playlist.section]]
mode = "slideshow"
schedule = { start = "09:00", end = "21:00" }   # NEW: section-level

[[playlist.section.widget]]
type = "image"
path = "open.png"
schedule = { start = "09:00", end = "17:00", days = ["mon","tue","wed","thu","fri"] }

[[playlist.section.widget]]
type = "image"
path = "closed.png"
schedule = { start = "17:00", end = "09:00" }   # overnight wrap = inverse window
```

### Semantics

- `start` / `end`: zero-padded `"HH:MM"` 24h wall-clock. `start > end` wraps
  past midnight; the post-midnight tail is owned by the **previous** day's
  `days` filter (identical to brightness-window semantics in
  `schedule._window_active`).
- `days`: list of `mon`..`sun`; empty/omitted = every day.
- `start == end` is a **validation error** (ambiguous between zero-length and
  24 h). Users wanting "always" simply omit `schedule`.
- A `brightness` key inside a widget/section `schedule` is an error whose
  message points at `[display.schedule]`.
- `schedule` is valid on **every** widget type, including plugin widgets —
  core owns it entirely and the widget never sees it.

### Timezone resolution

- Visibility schedules: `display.timezone` → system local.
- Brightness scheduler: `display.schedule.timezone` (kept as back-compat
  override) → `display.timezone` → system local.
- Invalid zone name: validation error at preflight; at runtime, warn + fall
  back to system local (matches the brightness scheduler's graceful fallback —
  a bad timezone must not prevent boot).

## Core model (`src/led_ticker/schedule.py`)

The existing module gains a shared primitive rather than a parallel
implementation:

- Extract the pure matching logic of `_Window` / `_window_active` into a
  frozen **`TimeWindow`** (`start`, `end`, `days`,
  `active_at(minutes, weekday) -> bool`). Brightness windows compose it with a
  brightness level; existing `Scheduler` behavior and tests are unchanged.
- New frozen **`VisibilitySchedule`**: a `TimeWindow` + resolved
  `tzinfo | None`, exposing `is_active(now: datetime | None = None) -> bool`
  (`now` injectable for tests; default `datetime.now(tz)`).
- New `parse_visibility_schedule(raw: dict, *, location: str)
  -> VisibilitySchedule` — **strict**: raises `ValueError` on malformed input.
  (Brightness parsing stays skip-and-warn: dimming degradation is cosmetic;
  silently mis-showing/hiding content is not, and new surface has no
  back-compat to protect.)

## Widget↔schedule association (registry)

Widgets are slotted `@attrs.define` classes: core cannot set attributes on
instances, and `eq=True` makes them unhashable (no `WeakKeyDictionary`).

`schedule.py` keeps a module-level registry:

- `bind_schedule(widget, sched)` / `schedule_for(widget)
  -> VisibilitySchedule | None`.
- Backing store: `dict[int, tuple[weakref.ref, VisibilitySchedule]]` keyed by
  `id(widget)`, with a weakref finalizer that removes the entry on collection.
  attrs' default `weakref_slot=True` makes widgets weakref-able; the rare
  non-weakref-able object falls back to a strong ref (accepted small leak,
  commented).
- Weakrefs matter because hot-reload rebuilds widgets — a strong-ref registry
  would grow every reload.

**Implementation checkpoint:** the hot-reload `widget_cache` key must include
the raw `schedule` table so editing only a widget's schedule busts its cache
entry and rebinds. Add a test.

## Engine flow

### Widget-level (`ticker.py:_expand_sources`)

A schedule check beside the existing `_displayable()` filter: a widget is
shown iff `schedule_active(widget) AND should_display()`.

- `schedule_active` consults the registry; no binding = always active.
- Same once-per-section-pass cadence as `should_display` (bounded staleness:
  a widget mid-hold finishes its hold).
- Same never-crash contract: a check that raises **keeps** the widget.
- Composition example: a scheduled countdown still hides when its count is out
  of range, and hides outside its window — AND, both directions.

### Containers

A `schedule` on a container entry (e.g. `rss.feed`) gates expansion of the
whole container — checked on the container object **before** `feed_stories`
expansion; stories inherit implicitly. The container's background `update()`
task keeps polling regardless (display-only gating), so content is fresh the
moment the window opens.

### Section-level (`app/run.py` section loop)

`SectionConfig` gains `schedule: VisibilitySchedule | None = None`. The
section loop skips inactive sections each playlist cycle (`continue`
immediately after the existing per-section reload/restart checks). Granularity
is one playlist cycle — consistent with the established section-seam
precedent. For tight flips (open→closed at exactly 17:00), users put both
widgets in one section, where the check runs per pass. Document this.

### Everything scheduled out

A sibling of `_idle_on_empty_playlist` (e.g. `_idle_when_all_scheduled_out`):

- Blank the panel once: `Clear()` + swap, **capturing the swap return**
  (hardware constraint #1).
- Idle ~1 s per outer-loop iteration so reload/restart checks stay live.
- INFO log once on going dark and once on waking — not per iteration.
- A dark panel when the store is closed is correct behavior, not a freeze.

A section whose widgets are all scheduled out degrades via the existing
empty-section `None`-sentinel path that `should_display` established.

### Accepted edge

Same as countdown today: a widget whose window just closed can still appear as
a transition's **outgoing** frame for one sub-second transition. Documented,
not fixed.

## Dispatch-level popping & hard reservation (`app/factories.py`)

- `validate_widget_cfg` / `_build_widget` pop `schedule` before construction
  (the `animation` / `border` pattern), parse via
  `parse_visibility_schedule`, and `bind_schedule` the built widget.
- Reservation check: if `_widget_declares_field(cls, "schedule")`, raise a
  loud config-load error telling the author the field is core-owned. Applies
  to core and plugin widget classes alike.

## Validation (`led-ticker validate`)

New rules (numbers assigned at implementation):

1. Schedule table shape — unknown keys; bad `HH:MM` (reuse `to_minutes`);
   invalid day names (**error** here, unlike brightness's warn — strict per
   the parsing decision); `start == end`; `brightness` key present.
2. `display.timezone` must resolve via `zoneinfo`.
3. Summary output prints the resolved zone **and the current time in it**
   ("schedules evaluate at 14:32 America/New_York") — catches the
   UTC-Docker-container gotcha at preflight instead of at 5 p.m.
4. Week-sampling soft **warning** (same 10,080-minute sweep as
   `unreachable_window_indices`): list intervals where every section/widget is
   scheduled out — "your sign is blank Tue 03:00–09:00". Warning, not error:
   dark-when-closed is often intended.
5. `--list-fields <type>` lists `schedule` for every widget type as a core
   dispatch field.

Runtime config-load raises on malformed schedules (strict), consistent with
other coercion errors; the webui editor's validate-before-write path catches
them for hot edits.

## Testing

- **Pure model:** `TimeWindow` extraction keeps existing `Scheduler` tests
  green; `VisibilitySchedule.is_active` — same-day window, overnight wrap,
  day filter on the wrapped tail, tz override vs system local, injected `now`.
- **Parsing:** strict errors for every malformed shape listed under
  Validation rule 1.
- **Engine:** `_expand_sources` drops an inactive widget / keeps active /
  raise-keeps; container gating (stories inherit, `update()` unaffected);
  AND-composition with `should_display`; section skip in the run loop;
  all-dark idle blanks with captured swap and recovers when a window opens.
- **Reservation:** a widget class declaring `schedule` is rejected at
  config-load.
- **Hot-reload:** editing only a widget's schedule takes effect (cache key
  includes it); registry doesn't leak across reloads (weakref eviction).
- **Drift:** `test_docs_config_options_drift` forces the config-options.mdx
  update for the new `SectionConfig` / `DisplayConfig` fields.

## Documentation

- New docs-site concepts page covering **scheduling as one mental model**
  (time windows) with two applications: visibility (this feature) and
  brightness (`[display.schedule]`), cross-linked both ways.
- `reference/config-options` additions (forced by the drift test).
- Example configs gain an open/closed image pair.
- Deploy docs: TZ env note for Docker.
- CLAUDE.md load-bearing-invariants bullet: reserved `schedule` field, the
  registry, strict parsing, the two engine check sites, and the
  never-crash/AND contract with `should_display`.

## Out of scope (v1)

- Multiple windows per widget/section (shape chosen so a list can be accepted
  later without breaking the single-table form).
- Date-based scheduling (holidays, specific dates), cron expressions.
- Status-board/webui surfacing of "skipped (scheduled out)" — DEBUG log only.
- Per-schedule timezone overrides.
