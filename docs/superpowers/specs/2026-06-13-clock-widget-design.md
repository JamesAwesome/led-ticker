# Clock widget — design

**Date:** 2026-06-13
**Status:** approved design, pre-implementation
**Context:** Steal #3 from the LEDMatrix comparison (clock + calendar). This spec covers
the **clock only**; the calendar is a separate, later brainstorm (its auth/data-source
decisions deserve their own treatment). Developed in parallel with the open overlay-state
PR #203 — see "Merge isolation".

## Summary

A new `type = "clock"` widget: a held/centered display of the current time, with an
optional inline date, 12h/24h presets or a custom strftime format, and an optional
timezone override. It's a thin formatter built on `FrameAwareBase` (like
`TickerMessage`) that delegates rendering to the shared text surface, so `font_color`
(incl. rainbow/color_cycle), `border`, `font`, `font_size`, and `bg_color` all work
with no new code. No external dependencies (stdlib `zoneinfo`).

## Merge isolation (developed alongside PR #203)

PR #203 (overlay-state) touches `app/run.py`, `status_board.py`, `busy_light.py`,
`webui/static/index.html`, and their tests/docs. This feature is **net-new files plus
append-only edits to files #203 does not open**: `widgets/clock.py` (new),
`widgets/__init__.py` (append `clock` to the auto-import tuple), `app/factories.py`
(append a clock `FieldHint`), `validate.py` (append clock field checks), a new docs
page, new test files. Zero file overlap; merges clean in either order.

## Widget shape

`src/led_ticker/widgets/clock.py` — `@register("clock") @attrs.define class Clock(FrameAwareBase)`,
mirroring `TickerMessage`'s structure. Each `draw()` computes the time string for the
current instant and renders it via the same text-drawing path `TickerMessage` uses
(so per-char color providers, borders, hires fonts, and emoji-free text all behave
identically). Held/centered; no scrolling.

### Config knobs (per-widget TOML under `[[playlist.section.widget]]`)

- **`format`** (str, default `"12h"`): either a preset keyword `"12h"` / `"24h"`, OR a
  raw strftime template. Disambiguation: if the value contains `%`, it is a strftime
  template; otherwise it must be a known preset keyword (validator errors on unknown).
  Presets render **time only** by default; a date is shown in v1 by using a custom
  format with date tokens, e.g. `"%a %b %-d  %-I:%M %p"` → `Mon Jun 13  3:09 PM`.
- **`timezone`** (str, optional): an IANA name like `"America/New_York"`. Default =
  the Pi's system local time. Resolved via stdlib `zoneinfo.ZoneInfo`. An invalid name
  is rejected at config-load (validator), not at draw time.
- Inherited from the shared text surface (same semantics as `message`): `font_color`,
  `border`, `font`, `font_size`, `bg_color`, `font_threshold`. The widget does NOT
  reimplement these — it passes them through to the shared render path.

### Deliberately out of v1
- First-class `show_seconds` toggle and colon-blink — not built. `%S` works via a
  custom `format` for anyone who wants seconds; it's just not a special-cased knob.
- Stacked two-line date-over-time (date held above time) — deferred to a v2 that uses
  the existing two_row band layout; v1's date is inline via the format string.

## Time formatting

A pure function `format_clock(now: datetime, fmt: str) -> str` (the widget's `draw()`
calls it with the real `now`; tests call it directly with an injected `now`).

- **Presets are built in Python from `datetime` fields, NOT via `%-` codes.** The
  no-leading-zero strftime codes (`%-I`, `%-d`) are a glibc extension: they work on the
  Pi (Linux) but not reliably on macOS, where dev/test runs. Building the preset output
  from `datetime` fields directly (e.g. composing the 12-hour value and stripping the
  leading zero in code) makes preset output **byte-identical on mac and Pi** and
  deterministic to unit-test.
  - `"12h"` → `H:MM AM/PM` with no leading zero on the hour (e.g. `3:09 PM`, `12:00 AM`).
  - `"24h"` → `HH:MM` (e.g. `15:09`, `03:09`).
- **A custom `format` string is passed to `strftime` verbatim.** That's the user's
  responsibility and they target their own Pi, so `%-I`/`%-d` are fine there. The docs
  note this Linux-ism for custom formats.
- **Timezone:** `datetime.now(ZoneInfo(timezone))` when set, else `datetime.now()`.

## Engine interaction (the one subtlety)

The clock must be **redrawn during a hold** so the displayed time stays current. The
engine's held branch re-renders frame-aware widgets every `ENGINE_TICK_MS` (50ms) tick
(CLAUDE.md render constraint #12), but a held widget rendered with a *static* color can
hit a draw-once-then-sleep fast path — which would freeze the clock on a stale minute
for the whole hold. The widget must guarantee per-tick redraw regardless of whether its
`font_color` is animated. The implementation plan will determine the exact mechanism
(e.g. ensuring the clock is treated as frame-variant so the engine takes the tick-loop
path); this spec records it as a hard requirement with a tripwire (see Testing).

## Files

- **Create:** `src/led_ticker/widgets/clock.py`; `tests/test_widgets/test_clock.py`.
- **Append-only:** `src/led_ticker/widgets/__init__.py` (add `clock` to the auto-import
  tuple); `src/led_ticker/app/factories.py` (a `FieldHint` block for clock fields so
  `--list-fields clock` works); `src/led_ticker/validate.py` (clock field validation:
  unknown-preset and bad-tz-name checks).
- **Docs:** a new `docs/site/.../widgets/clock.mdx`; the widget-index / config-options
  entry if the drift test requires the field list.

## Error handling

- Unknown `format` preset (no `%`, not `12h`/`24h`) → config-load error naming the
  valid presets.
- Invalid `timezone` name → config-load error (caught when constructing `ZoneInfo`),
  not a draw-time crash.
- A custom strftime that produces odd output is the user's responsibility (passed
  verbatim); the widget never crashes on it.
- The widget holds no external resources and makes no network calls — no async, no
  failure modes beyond config validation.

## Testing

- **`format_clock` (pure):** `"12h"` of 15:09 → `3:09 PM`; 00:09 → `12:09 AM`; 12:00 →
  `12:00 PM`; `"24h"` of 15:09 → `15:09`, of 03:09 → `03:09`; a custom date format
  renders date+time on one line; a `timezone` override converts correctly. All with an
  injected `now` — zero wall-clock flakiness; identical on mac and Pi.
- **Widget:** registers under `"clock"`; `draw()` renders to the stub canvas
  held/centered with the right return; inherits `font_color`/`border` (a rainbow clock
  advances its frame counter like `message` does).
- **Redraw-during-hold tripwire:** the clock re-renders each engine tick rather than
  freezing on a stale minute — in the spirit of the existing per-tick redraw contract
  tests (`TestSwapAndScrollEngineTick` / the frame-advance contract).
- **Validation:** unknown preset and bad tz name both rejected at config-load with a
  clear message.
- **`--list-fields clock`** golden/coverage test if the repo's list-fields test pattern
  requires it.

## Out of scope

- Calendar widget (separate brainstorm).
- Stacked two-line date-over-time (deferred v2).
- First-class seconds toggle / colon blink.
- Any new dependency — `zoneinfo` is stdlib.
