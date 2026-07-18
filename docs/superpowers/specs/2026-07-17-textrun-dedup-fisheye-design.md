# draw_text_run consolidation + message fisheye token colorization — Design

**Date:** 2026-07-17
**Repo:** led-ticker core (`src/led_ticker`)
**Status:** approved

## Why

Colored value tokens (Phase 1+2, core 4.14.0 / 4.19.0) introduced a shared
three-branch text-draw dispatch, `widgets/_text_run.draw_text_run`. But it
ended up used by ONLY `message.draw` — three near-identical inline copies of
the same emoji/per-char/whole-string dispatch remain, because the helper could
not forward `hires_downscale` (which the image overlay and message's fisheye
lens pass to `draw_with_emoji`). Adding that one param unblocks routing all
three through the helper. Routing the message lens copy additionally CLOSES the
one asymmetry documented after Phase 2: a colored token on a `message` widget
under `flair.fisheye` renders in the host color, while the same on an image
widget colorizes (image's lens shares `_draw_text`; message's uses a separate
`_paint_strip`). Detail note: [[project_colored_value_tokens]].

## Principle

One implementation of the three-branch dispatch. `draw_text_run` is the single
source of truth; the widgets thread their per-field overrides and geometry
into it, they do not re-implement the branch logic.

## Changes

### 1. `draw_text_run` gains `hires_downscale` (`widgets/_text_run.py`)

Add `hires_downscale: float = 1.0` (keyword-only) to `draw_text_run`.
Forward it to `draw_with_emoji` in the EMOJI branch only — the plain-text
branches (`draw_text_per_char` / `draw_text`) do not accept it and do not need
it (it only affects hi-res sprite sizing). Default `1.0` is a no-op, so
message and two_row (which never pass it) are unaffected. Extend the helper's
unit tests to assert the pass-through (emoji branch with `hires_downscale=0.5`
reaches `draw_with_emoji` with that value; plain branches ignore it).

### 2. Route the three inline copies through the helper

Each currently hand-duplicates the emoji/per-char/whole-string branches. After
this change each builds its override + geometry and calls `draw_text_run`,
deleting its branch block.

- **`_image_base._draw_text` (single-row):** already builds its override
  (`self._text_segments`, RAW `self._has_emoji()` basis) and passes
  `hires_downscale`. Replace its ~3-branch body with one `draw_text_run(...)`
  call forwarding `override`, `has_emoji=self._has_emoji()`,
  `total_chars=count_text_chars(full_display)`, `hires_downscale=...`. PURE
  DE-DUP — byte-identical (the existing image single-row suite is the guard).
- **`_image_base._draw_row_text` (two-row):** builds its per-row override
  (COMPOUND `self._has_emoji() and has_renderable_emoji(text)` basis) and
  passes `emoji_y`/`max_emoji_height` (NOT `hires_downscale` — two-row rows
  don't downscale). Replace its branch body with `draw_text_run(...)`
  forwarding `override`, the compound `has_emoji`, `emoji_y`,
  `max_emoji_height`, and `total_chars=per_char_total`. PURE DE-DUP —
  byte-identical.
- **`message._paint_strip` (fisheye lens):** currently NO override (its 3
  branches use the host provider only — the #2 gap). Route through
  `draw_text_run` AND build a token override from `self._resolved_segments`
  (the message widget already snapshots these; `_paint_strip` has `self`).
  Its `has_emoji` basis is the RAW `self._has_emoji` (same as `message.draw`).
  Pass `hires_downscale`. This DELETES the copy AND colorizes message-fisheye
  tokens. The override's `visible_text` is the `visible_text` the lens strip
  draws; `total_chars` anchors to `full_text` (as it does today).

### 3. `two_row` stays as-is (intentional exception)

`two_row`'s default rows (`:667`/`:702`) thread `color_override` directly into
`draw_with_emoji` via the shared `_row_override` builder; the wrap helper
`_draw_row_text_at` mirrors it inline. This was reviewed-correct in Phase 2:
routing the `:667`/`:702` sites through `draw_text_run` would send plain
(no-emoji, no-override) rows through its `draw_text` fast path instead of
`draw_with_emoji`, breaking ~20 existing tests that patch
`two_row.draw_with_emoji` — churn for no real DRY gain, since `_row_override`
already centralizes the override construction within the class. Document this
as the one intentional exception in CLAUDE.md rather than forcing uniformity.

## Behavior

- Image single-row + two-row: BYTE-IDENTICAL (equivalence-guarded by the
  existing image suites).
- Message NORMAL draw: unchanged (already routes through the helper).
- Message FISHEYE lens: colored tokens now render in the source color (was
  host color). The ONLY intended behavior change. A rainbow/gradient/constant
  `font_color` under fisheye is unchanged (override is `None` there).
- two_row: unchanged.

## Testing

- **De-dup equivalence:** the existing `test_message`, `test_image_base`, and
  `test_two_row` suites must all stay green after the routing (they are the
  byte-identical guard for the image de-dup and message-normal path).
- **`draw_text_run` pass-through:** new unit test — emoji branch forwards
  `hires_downscale` to `draw_with_emoji`; plain branches ignore it.
- **#2 closure (new, mutation-grade):** a colored token on a `message` widget
  drawn under `flair.fisheye` renders the token's chars in the source color and
  literals in the host color — PER-POSITION assertion (token x-span == source
  color, literal x-span == host), the standard set in Phase 2 (a coarse
  membership test does not catch a basis/alignment regression). Mutation-check
  it: flipping the lens override off (or its `has_emoji` basis) makes it fail.
- **GIF gate:** a `message` widget with a colored `:id:` token under
  `flair.fisheye` on bigsign — confirm the token colorizes through the lens.

## Rollout

One core PR: `_text_run.py` param + three widget routings + CLAUDE.md
invariant update (remove the two "deferred follow-up" bullets; add the two_row
intentional-exception note) → core release vNext (patch/minor — a de-dup plus
one narrow behavior fix, no config surface).

## Out of scope

- Routing `two_row` through `draw_text_run` (intentional exception, §3).
- Any change to the override-builder or has_emoji-basis semantics (unchanged
  from Phase 2).
