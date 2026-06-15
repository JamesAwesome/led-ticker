# Calendar widget — two-tone time/title colors

**Date:** 2026-06-15
**Goal:** Render each calendar line in two colors — the time/relative phrase in
one color, the event title in another — and make a baseball-style two-tone the
**default**. User request; mapping decided: **time phrase amber `(255,200,60)`,
title white**.

## Why

On hardware a single-color agenda line (`Tomorrow 3:00 PM · Team Meeting`) reads
as one undifferentiated run. Coloring the time phrase distinctly from the title
(the way the baseball attendance/promo lines use amber values + white body) makes
the "when" pop and the title legible at a glance.

## Knobs

- **`font_color`** — unchanged name; now means the **title** color. Default
  white (`DEFAULT_COLOR`). Accepts any `ColorProvider` (`"rainbow"`, gradient, …).
- **`time_color`** — NEW. The time/relative phrase color. Default amber
  `(255,200,60)`. Accepts any `ColorProvider`.
- **`highlight_color`** — unchanged. A line whose summary matches `highlight`
  renders **entirely** in `highlight_color` (amber) — a highlight is a
  whole-event attention state, so two-tone applies to non-highlighted lines only.

The calendar merged minutes ago; there are no existing configs whose meaning of
`font_color` (previously: the whole line) changes in a breaking way for users.

## Mapping (both layouts)

The `_SEP = " · "` stays attached to the time segment so the dot inherits the
time color.

- **agenda** — `[<day> <time> · ]`=`time_color`, `[<summary>]`=`font_color`.
  All-day: `[<day> · ]`=`time_color`, `[<summary>]`=`font_color`.
- **next** — `[<summary>]`=`font_color`, `[ · <relative>]`=`time_color`
  (e.g. `Team Meeting` white, ` · in 5m` amber).
- **empty** (no events) — single segment, `empty_text` in `font_color`. No time
  segment.
- **highlighted line** — every segment uses `highlight_color`.

## Architecture

`draw_with_emoji(canvas, font, x, y, color, text, frame=, total_chars=)` already
accepts a `Color` **or** a `ColorProvider` per call and handles per-char sweep +
inline `:slug:` emoji. So each segment is one `draw_with_emoji` call with its own
provider + per-effect frame counter. This preserves providers, borders, and emoji
that a `SegmentMessage` swap would drop (SegmentMessage has no border and only
plain `Color` per segment).

1. **`_draw_two_tone(...)`** — module helper. Takes the canvas, font, layout
   knobs (center/padding/border + border frame), and an ordered list of
   `(text, provider, frame)` segments plus an optional whole-line `override`
   (the transitions-supplied `font_color`). Measures total width, centers,
   paints border once, draws each segment via `draw_with_emoji`, returns the
   advanced `cursor_pos` (+ end padding) so the engine's hold-vs-scroll math is
   correct.
2. **`split_event_line` / `split_relative`** — return the `(time, title)` /
   `(title, time)` parts. The existing string-returning `format_event_line` /
   `format_relative` are reimplemented as `"".join(split_*)` so their tests and
   any string callers are unchanged.
3. **`_TwoToneLine(FrameAwareBase)`** — the agenda feed-story widget (replaces
   per-event `TickerMessage`). Fields: `time_text`, `title_text`, `time_color`,
   `font_color` (title), `font`, `bg_color`, `border`, `center`, `padding`. Its
   `draw(...)` builds the two segments (skipping empties), applies a transitions
   `font_color` override to both, and delegates to `_draw_two_tone`.
4. **`_NextEventWidget.draw`** — keep the live event-selection logic; replace the
   final single-`text` render block with `split_relative` → two segments →
   `_draw_two_tone`. Highlighted current event → both segments `highlight_color`.
5. **`Calendar` / `_NextEventWidget`** gain a `time_color` field (default amber,
   `converter=_coerce_provider`). `_build_stories` passes `time_color` through;
   the agenda branch builds `_TwoToneLine` (highlighted → time & title both
   `highlight_color`).
6. **Wiring:** add `"time_color"` to `FrameAwareBase._EFFECT_ATTRS` (so an
   animated `time_color="rainbow"` advances its counter — the `highlight_color`
   trap) and to `coercion._PROVIDER_COLOR_KEYS` (so a TOML `time_color =
   "rainbow"` / `[r,g,b]` coerces to a provider).

`validate_config` gains nothing: like `font_color`/`highlight_color`, `time_color`
is validated by coercion, not the static validator (matches existing behavior).

## Tests (class-closing, mirror the calendar harness style)

- `split_event_line` / `split_relative` return the documented parts; their join
  equals the legacy `format_*` output (DRY/back-compat lock).
- `_TwoToneLine` renders the time pixels in `time_color` and title pixels in
  `font_color` (distinct colors on a stub canvas); empty segment skipped.
- agenda default: amber time + white title; highlighted line: all amber.
- `next` default: white title + amber time; highlighted: all amber; empty:
  `empty_text` in `font_color`, no time segment.
- animated `time_color="rainbow"` advances per `frame_for("time_color")` (color
  differs across ticks) — proves `_EFFECT_ATTRS` wiring.
- border still paints on agenda lines; `:slug:` emoji in a summary still renders.
- TOML `time_color = "rainbow"` / `[r,g,b]` coerces to a provider (coercion).
- full suite + ruff + pyright green (process guard from the hardening retro).

## Docs

- `widgets/calendar.mdx`: document `time_color`, the new default two-tone, the
  highlight-whole-line rule; refresh any example that implied single-color lines.
- `config/config.calendar_smoketest.toml`: add a `time_color` line / note.

## Out of scope

- Per-character independent providers spanning BOTH segments as one sweep (each
  segment sweeps independently — matches `SegmentMessage`/baseball semantics).
- New layouts or fields beyond `time_color`.
