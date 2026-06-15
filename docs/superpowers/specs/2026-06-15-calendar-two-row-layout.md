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

## Constraints (documented, inherited from two-row)

Two rows need vertical room. Comfortable on bigsign (`content_height = 16` →
32 real px/row at scale 4); tight on smallsign (16 px → 8 px/row). A hires font
whose line-height exceeds a band raises at draw time identifying the row
(inherited `TwoRowMessage` behavior). `content_height × scale ≤ panel_h_real`
still applies.

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
