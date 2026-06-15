# Calendar widget — `two_row` layout

**Date:** 2026-06-15
**Goal:** Add a third calendar layout, `layout = "two_row"`, that renders each
upcoming event as a two-row card: the held top row shows the "when" (day +
time), the bottom row shows the title and scrolls only if it overflows. Cards
rotate one-per-screen like `agenda`.

## Decisions (from brainstorming)

- **Content model:** per-event card. One card per selected event; rotates with
  `hold_time` + section transitions exactly like `agenda`.
- **Top row (held):** absolute day + clock time — `Tomorrow 3:00 PM`,
  `Fri 9:00 AM`; all-day → just the day (`Tomorrow`). Static (no live
  countdown — that stays the `next` layout's job). Honors `time_format`.
- **Bottom row:** the event title; scroll-on-overflow (the `TwoRowMessage`
  marquee mechanic).
- **Colors:** reuse `time_color` (top) and `font_color` (bottom) — the SAME
  knobs as `agenda`/`next`, one vocabulary across all layouts. A `highlight`-
  matched event renders BOTH rows in `highlight_color` (whole-card attention
  state).

## Architecture — reuse `TwoRowMessage`, no new widget

A per-event card IS a `TwoRowMessage` (the existing, hardened held-top/
scroll-bottom widget). `Calendar._build_stories` gains a `two_row` branch that
constructs one `TwoRowMessage` per selected event:

```
TwoRowMessage(
    top_text=<when>,            # day + time, no separator
    bottom_text=<event.summary>,
    top_font=self.font,
    bottom_font=self.font,
    top_color=<time or highlight provider>,
    bottom_color=<font or highlight provider>,
    top_row_height=self.top_row_height,   # new calendar field (passthrough)
    top_text_y_offset=self.top_text_y_offset,
    bottom_text_y_offset=self.bottom_text_y_offset,
    bg_color=self.bg_color,
    border=self.border,
    padding=self.padding,
)
```

Highlight selection mirrors the `agenda` branch: if `_match_any(summary,
highlight)`, both colors are `highlight_color`; else top=`time_color`,
bottom=`font_color`.

`TwoRowMessage` already owns: held top + scroll-on-overflow bottom, per-row
`Color | ColorProvider`, `top_row_height`, border at physical resolution,
bg fill, inline `:slug:` emoji on the title, and the constraint-#10 (rebind
after swap) / #12 (advance_frame per tick) rules. The shared `_row_layout`
helpers come along unchanged. No new render code, no new constraints.

### The "when" string

A new module helper `format_when(event, *, now, time_format, tz) -> str`
returns the top-row text:
- timed event → `f"{day} {format_clock(event.start, time_format)}"`
- all-day event → `day`

This is `split_event_line`'s time part **without** the trailing `_SEP` (the two
rows separate the when and the title visually, so the ` · ` is dropped).
`split_event_line` may be refactored to build on `format_when` so the day/time
formatting lives in one place.

## Knob surface

- **Opt in:** `layout = "two_row"` joins `"agenda" | "next"` (validate_config
  updated; layout-set is the single source).
- **Colors:** `time_color` / `font_color` / `highlight_color` (unchanged,
  reused).
- **Per-row structural knobs (new on `Calendar`, passthrough to
  `TwoRowMessage`):** `top_row_height: int | None = None` (split point;
  `None` = 50/50), `top_text_y_offset: int = 0`, `bottom_text_y_offset:
  int = 0`. These are genuinely per-row and have no cross-layout meaning, so
  they take the `top_`/`bottom_` prefix per the two-row convention.
- **Font:** `font` / `font_size` / `font_threshold` apply to both rows (the
  calendar has a single resolved `self.font`; a per-row font split is YAGNI for
  now). These knobs are ignored by `agenda`/`next` only in the sense that those
  layouts are single-row; nothing changes there.
- **Empty / error:** unchanged — `empty_text` (empty feed) and `error_text`
  (first-load failure) render as the existing single centered line
  (`_empty_story` / `_error_story`), not a card.

The new per-row fields are inert in `agenda`/`next` mode (constructed but
unused), matching how `agenda`-only and `next`-only knobs already coexist.

## Constraints & the band-fit guard (revised after review)

Two rows split the canvas, so each band is at most 8 logical rows
(`content_height` caps at 16 on both reference signs → a 50/50 split = 8). The
calendar's default `font` is `6x12` (logical line-height 12), which can NEVER fit
an 8-row band on either sign — so a default `layout = "two_row"` would raise at
draw and freeze the panel (constraint #1), and the run path does NOT validate at
startup. Two coordinated fixes:

1. **Runtime substitution.** `_build_two_row_stories` uses `FONT_SMALL` (5x8,
   lh 8) for the rows when `self.font is FONT_DEFAULT` (omitted or `"6x12"`).
   Lossless — 6x12 is unusable in a two_row band here anyway — so the default
   config renders.
2. **Validate-time net (parity with the `two_row` widget).**
   `validate._check_band_layout` is extended to cover `type = "calendar"` with
   `layout = "two_row"`, mirroring the substitution (default + the
   `FONT_DEFAULT → FONT_SMALL` swap). An *explicitly* too-tall font (a large
   hires `font_size`, or `7x13`) is caught at `led-ticker validate` (rule 22)
   with an actionable message, instead of crashing at draw.

For larger/hi-res text, choose a `font`/`font_size` whose line-height fits the
row; raise `content_height` or set `top_row_height` for an asymmetric split.
`content_height × scale ≤ panel_h_real` still applies.

`validate_config` also validates the new per-row knobs: `top_row_height` must be a
positive int (TwoRowMessage rejects ≤ 0, which would otherwise surface only as the
runtime error placeholder); the y-offsets must be ints.

## Files

- `src/led_ticker/widgets/calendar.py` — `format_when` helper; `two_row` in the
  accepted layout set + `validate_config`; new `top_row_height` /
  `top_text_y_offset` / `bottom_text_y_offset` fields; `two_row` branch in
  `_build_stories` building `TwoRowMessage` per event; import `TwoRowMessage`.
- `docs/content-source/widgets/calendar.md` — `two_row` in the `layout` row;
  new rows for `top_row_height` / `top_text_y_offset` / `bottom_text_y_offset`
  (noted as two_row-only).
- `docs/site/src/content/docs/widgets/calendar.mdx` — a `two_row` layout
  subsection under Layouts with a TOML example (and a DemoGif placeholder
  following the agenda/next pattern, generated separately).

## Tests

- `format_when`: timed → `"<day> <clock>"` honoring `time_format`; all-day →
  day only; no `_SEP`.
- `validate_config`: accepts `layout = "two_row"`; still rejects unknown layouts.
- `_build_stories` two_row branch: yields one `TwoRowMessage` per event;
  `top_text` == `format_when`, `bottom_text` == summary; `top_color` is
  `time_color` and `bottom_color` is `font_color` for a normal event.
- highlighted event → BOTH `top_color` and `bottom_color` are `highlight_color`.
- all-day event → `top_text` is the day label only (no clock).
- `max_events` honored (N events → N cards); `filter` applied.
- empty feed → single `_empty_story` (not a `TwoRowMessage`); first-load failure
  → single `_error_story`.
- passthrough: `top_row_height` / `top_text_y_offset` / `bottom_text_y_offset`
  reach the constructed `TwoRowMessage`.
- a `two_row` card draws without raising on the stub canvas (smoke).
- Full suite + ruff + pyright + docs-lint green.

## Out of scope

- Live/relative top row (that's the `next` layout).
- Per-row font split (`top_font`/`bottom_font` from distinct calendar fields) —
  YAGNI; both rows use `font`.
- Two-events-stacked or header+ticker models (rejected in brainstorming).
- A demo `.gif` asset (generated in a follow-up like the other layouts).
