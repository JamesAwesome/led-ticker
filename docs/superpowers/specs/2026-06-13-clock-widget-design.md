# Clock widget — design

**Date:** 2026-06-13
**Status:** approved design, pre-implementation
**Context:** Steal #3 from the LEDMatrix comparison (clock + calendar). This spec covers
the **clock only**; the calendar is a separate, later brainstorm (its auth/data-source
decisions deserve their own treatment). Developed in parallel with the open overlay-state
PR #203 — see "Merge isolation".

## Summary

A new `type = "clock"` widget: a centered display of the current time, with an optional
inline date, 12h/24h presets or a custom strftime format, and an optional timezone
override. It's a thin formatter built on `FrameAwareBase` and `@attrs.define`, whose
`draw()` mirrors `TickerCountdown.draw` (the closest prior art — also non-static,
no-emoji text recomputed each draw). It reuses the text-render HELPER functions
(`text_render.draw_text` / `draw_text_per_char`, `drawing.compute_baseline` /
`compute_cursor`), so `font_color` (incl. rainbow/color_cycle), `font`, `font_size`,
`bg_color`, and `font_threshold` come via the same name-keyed coercion every text
widget gets. `border` is NOT free — it requires an explicit attrs field + a paint call
(see Widget shape). No external dependencies (stdlib `zoneinfo`).

## Merge isolation (developed alongside PR #203)

PR #203 (overlay-state) touches `app/run.py`, `status_board.py`, `busy_light.py`,
`webui/static/index.html`, and their tests/docs. This feature is **net-new files plus
append-only edits to files #203 does not open**: `widgets/clock.py` (new),
`widgets/__init__.py` (append `clock` to the auto-import tuple), `app/factories.py`
(append a clock `FieldHint`), `validate.py` (append clock field checks), a new docs
page, new test files. Zero file overlap; merges clean in either order.

## Widget shape

`src/led_ticker/widgets/clock.py` — `@register("clock") @attrs.define class Clock(FrameAwareBase)`
(the `@attrs.define` is required — `FrameAwareBase.__new__` raises `TypeError` without
it). Its `draw()` mirrors **`TickerCountdown.draw`** (`message.py`), the cleanest
template: like the clock, countdown has non-static, no-emoji text recomputed every
`draw()`, and it already does the constant-vs-per-char color dispatch + border paint a
clock needs. The clock's `draw()` must: (1) compute the time string for the current
instant (timezone-resolved here, see Time formatting); (2) paint the border if set
(`self.border.paint(canvas, self.frame_for("border"))`); (3) dispatch the time string
through the per-char-vs-constant color path against `font_color`, centered. There is no
shared `draw()` entry point that does this for you — the clock reuses the low-level
helpers and replicates countdown's structure (~30 lines), it does not inherit
`TickerMessage.draw` (which bakes in `self.text`, emoji parsing, and a scroll cursor a
clock doesn't want).

**Why this is live without any special engine mechanism:** a held, non-overflowing
`draw()` widget goes through the engine's `_hold_ticks` loop (`ticker.py`), which does
`advance_frame → reset_canvas → draw → swap → sleep` every `ENGINE_TICK_MS` (50ms)
**unconditionally, regardless of `font_color`**. Recomputing `now` inside `draw()`
therefore keeps the display current to ~50ms with zero special handling — exactly how
`TickerCountdown` stays live. The draw-once-then-sleep fast path that *could* freeze a
widget exists ONLY in the image widgets' `play()` loop (`_image_base.py`, gated on
`_is_static()`), which a `draw()`-based clock never enters. (Earlier drafts flagged this
as an open subtlety; it is resolved — there is nothing to special-case.)

**Visit-scope caveat:** the clock is live only while its section is the active visit
(~`hold_time` seconds), then the playlist advances. It is a widget, not a persistent
overlay — within a visit it's accurate to ~50ms; between visits it's stale until the
section comes around again. Expected and fine; documented so nobody expects a
wall-clock-accurate always-on display.

### Config knobs (per-widget TOML under `[[playlist.section.widget]]`)

- **`format`** (str, default `"12h"`): either a preset keyword `"12h"` / `"24h"`, OR a
  raw strftime template. Disambiguation: if the value contains `%`, it is a strftime
  template; otherwise it must be a known preset keyword (validator errors on unknown).
  Presets render **time only** by default; a date is shown in v1 by using a custom
  format with date tokens, e.g. `"%a %b %-d  %-I:%M %p"` → `Mon Jun 13  3:09 PM`.
- **`timezone`** (str, optional): an IANA name like `"America/New_York"`. Default =
  the Pi's system local time. Resolved via stdlib `zoneinfo.ZoneInfo`. An invalid name
  is rejected at config-load (validator), not at draw time.
- **Free via name-keyed coercion** (same as `message`): `font_color`, `font`,
  `font_size`, `bg_color`, `font_threshold` — the engine's `reset_canvas(canvas,
  bg_color)` and the coercion layer handle these by field name, no per-widget code.
- **`border` — explicit, NOT free.** `factories.py`'s border-acceptance check gates
  `border` behind a hardcoded widget-type allowlist OR `_widget_declares_field(cls,
  "border")`. The clock takes the second path: it declares a `border` attrs field
  (like `TickerMessage`/`TickerCountdown` do) — that satisfies the gate WITHOUT editing
  the allowlist — and its `draw()` calls `self.border.paint(...)` before the text.
- **Scroll-mode behavior:** "centered" is only meaningful in `swap` mode (a held,
  fitting widget centers via `compute_cursor`). In `forever_scroll` / `infini_scroll`
  the clock is a normal `draw()` widget drawn at a moving cursor, so it WILL scroll
  (and update mid-scroll, harmlessly). It does not crash — it degrades to a scrolling
  clock. The clock is intended for `swap`-mode sections; this is documented, not
  enforced.

### Deliberately out of v1
- First-class `show_seconds` toggle and colon-blink — not built. `%S` works via a
  custom `format` for anyone who wants seconds; it's just not a special-cased knob.
- Stacked two-line date-over-time (date held above time) — deferred to a v2 that uses
  the existing two_row band layout; v1's date is inline via the format string.

## Time formatting

A pure function `format_clock(now: datetime, fmt: str) -> str`, **timezone-agnostic**:
it formats an already-localized `now`. The widget's `draw()` resolves the timezone and
passes the localized `now`; tests call `format_clock` directly with an injected `now`.
This keeps the pure function trivial to test and free of tz/clock state.

- **Presets are built in Python from `datetime` fields, NOT via `%-` strftime codes.**
  Rationale (corrected from an earlier draft): the no-leading-zero codes `%-I`/`%-d` are
  a platform/libc passthrough that **Python does not guarantee** — they are not in the
  strftime spec and their behavior is undocumented/implementation-defined. (They happen
  to work on both Linux and macOS today, and CI runs on Linux self-hosted runners — so
  this is about determinism and not depending on unspecified behavior, NOT about a
  macOS breakage, which does not exist.) Composing presets from `datetime` fields makes
  their output deterministic and spec-defined regardless of libc.
  - `"12h"` → `H:MM AM/PM`, no leading zero on the hour: `3:09 PM`, `12:09 AM` (midnight),
    `12:00 PM` (noon) — standard 12-hour convention.
  - `"24h"` → `HH:MM`: `15:09`, `03:09`.
- **A custom `format` string is passed to `strftime` verbatim.** The user's
  responsibility; `%-I`/`%-d` are fine on their Pi. Docs note `%-` is a Linux-ism for
  custom formats.
- **Timezone (resolved in `draw()`, not in `format_clock`):**
  `datetime.now(ZoneInfo(timezone))` when `timezone` is set, else `datetime.now()`
  (system local). DST-correct by construction.

## Files

- **Create:** `src/led_ticker/widgets/clock.py`; `tests/test_widgets/test_clock.py`.
- **Append-only:**
  - `src/led_ticker/widgets/__init__.py` — add `clock` to the auto-import tuple.
  - `src/led_ticker/app/factories.py` — add two new GLOBAL `FIELD_HINTS` keys
    (`format`, `timezone`); the dict is name-keyed and shared across widgets, so this is
    two entries, not a per-widget block. (`font_color`/`font`/etc. hints already exist.)
  - The clock's `border` field is satisfied by declaring it on the class (no edit to
    `factories.py`'s border-type allowlist needed).
- **Validation lives on the widget, not in `validate.py`.** The clock defines the
  optional `validate_config(cls, cfg) -> list[str]` classmethod (the idiomatic hook run
  inside `validate_widget_cfg`): value-level checks for an unknown `format` preset and a
  bad `timezone` name. (Unknown *fields* are already caught generically by the attrs
  field check — only value-level checks need writing.)
- **Docs — TWO trees:** `docs/site/src/content/docs/widgets/clock.mdx` (user docs) AND
  `docs/content-source/widgets/clock.md` (fact-pack). Because the clock advertises
  `border`, add `clock` to the `FACT_PACK_FILES` tuple in
  `tests/test_border_surface_drift.py` and give the fact-pack a `border` row (the repo's
  border-surface drift convention). The config-options drift test may require the field
  list too.

## Error handling

- Unknown `format` preset (no `%`, not `12h`/`24h`) → `validate_config` error naming the
  valid presets.
- Invalid `timezone` name → `validate_config` catches `zoneinfo.ZoneInfoNotFoundError`
  (and `ValueError` for malformed input) and reports a clear config-load error, not a
  draw-time crash. (Edge: a dev machine lacking the `tzdata` package could false-reject
  a valid name; the Pi ships system tzdata, so this is a low-risk dev-only note.)
- A custom strftime that produces odd output is the user's responsibility (passed
  verbatim); the widget never crashes on it. `strftime("%")` returns `"%"` — harmless.
- The widget holds no external resources and makes no network calls — no async, no
  failure modes beyond config validation.

## Testing

- **`format_clock` (pure):** `"12h"` of 15:09 → `3:09 PM`; 00:09 → `12:09 AM`; 12:00 →
  `12:00 PM`; `"24h"` of 15:09 → `15:09`, of 03:09 → `03:09`; a custom date format
  renders date+time on one line; a `timezone` override converts correctly. All with an
  injected `now` — zero wall-clock flakiness; identical on mac and Pi.
- **Widget:** registers under `"clock"`; `draw()` renders to the stub canvas centered
  with the right return; `border` paints (the field is declared so the type gate
  accepts it); a rainbow `font_color` advances the frame counter like `message`/
  `countdown` do.
- **Liveness:** because the clock recomputes `now` in `draw()` and the engine's
  `_hold_ticks` redraws every tick, a held clock shows the current value across the
  hold — assert via the same per-tick redraw contract the engine tests use
  (`TestSwapAndScrollEngineTick` / the frame-advance contract). (This is the
  countdown mechanism, already proven; the test guards against a regression, not a
  speculative fix.)
- **Validation:** `validate_config` rejects an unknown preset and a bad tz name with a
  clear message.
- **`--list-fields clock`** golden/coverage test if the repo's list-fields test pattern
  requires it; border-surface drift test updated for the new fact-pack.

## Out of scope

- Calendar widget (separate brainstorm).
- Stacked two-line date-over-time (deferred v2).
- First-class seconds toggle / colon blink.
- Any new dependency — `zoneinfo` is stdlib.
