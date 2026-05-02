# Still-image widget — pre-merge review plan

**Goal:** Review the still-image branch the same way we reviewed gif-widget
(parallel reviewers, focused slices) before merging into main.

**Branch state (still-image @ 7564a2f, 4 commits ahead of main):**

- ~565 lines new production code (`still.py` 409, `_image_fit.py` 100,
  `_still_decode.py` 56)
- `_gif_decode.py` slimmed (109 → 56-ish, imports shared bits from
  `_image_fit.py`)
- `gif.py` modified: `text_y_offset` + `text_x_offset` fields,
  `content_height = panel_h // text_scale` fix in `_play_with_text`
- `app.py`: path resolution extended to `type = "image"`
- ~700 lines new tests (`test_still.py` 578, `test_still_decode.py` 111;
  plus `test_gif.py` additions for the content_height fix + offsets)
- 5 test asset images (4 PNG + 1 JPG, ~440KB total)
- New `config.image_test.example.toml` (~210 lines, 10 sections)

**Headline features:**

1. New `type = "image"` widget — full feature parity with `GifPlayer`
   (fit modes, gif_align, text overlay variants, text_scale, text_loops,
   transparent PNG support).
2. `hold_seconds` (default 5.0) replaces `gif_loops` for per-visit
   duration; with `text_loops > 0` becomes a duration FLOOR.
3. Shared decode primitives (`apply_fit`, `flatten_onto_black`,
   `validate_choice`) extracted into `_image_fit.py` so both widgets
   import from one place.
4. `text_y_offset` / `text_x_offset` knobs added to BOTH widgets for
   precise pixel positioning past the valign defaults.
5. `text_valign = "top"` actually means panel top now: text wrapper
   uses `content_height = panel_h // text_scale` (was 16 default →
   letterboxed sub-region).

## Review areas

Six parallel reviewers, same approach as the gif-widget review.

### Area 1 — Hot-path performance

**Files:** `still.py` (`_ensure_paint_caches`, `_paint_full`,
`_paint_skip_black`, `_play_with_text`), `_still_decode.py`,
`_image_fit.py` (`apply_fit`, `flatten_onto_black`).

**Key questions:**

- `_ensure_paint_caches` builds the non_black list with a Python
  triple-nested loop over 16,384 pixels. One-time per widget but
  blocking when first encountered. Is this acceptable, or should it
  use struct.iter_unpack / numpy / batch? (Same question we asked of
  gif's version, which moved to `canvas.SetImage`.)
- The text-canvas content_height fix: `canvas.height // self.text_scale`.
  Does this correctly handle non-divisible cases (e.g. scale=3 on
  64-tall panel → 21)?
- `_play_with_text` for stills with no scrolling: still runs a tick
  loop. For `text_align="left"`/`"right"` (static), the image and
  text don't change between ticks — could we paint once and `await
  asyncio.sleep(hold_seconds)` like the no-text fast path?

### Area 2 — DRY / refactoring opportunities

**Files:** `still.py` and `gif.py` side-by-side, `_image_fit.py`,
`_gif_decode.py`, `_still_decode.py`.

**Key questions:**

- `still.py` and `gif.py` now share ~250 lines of nearly identical
  code: text helpers (`_baseline_y`, `_has_emoji`, `_measure_text`,
  `_draw_text`, `_render_tick`), validation (post-init, _VALID_*
  sets, _AUTO_TEXT_ALIGN_FOR_GIF), constants
  (`_TEXT_EDGE_PADDING_PX`, `_MIN_SCROLL_SPEED_MS`, `_EMOJI_PATTERN`).
  Is a shared `_BaseImageWidget` mixin / base class worth pulling
  out, or does duplication remain acceptable?
- The `_play_with_text` orchestration body itself is near-identical
  in both files (only difference: `_paint_full(canvas, frame_idx)`
  vs `_paint_full(canvas)`). Could this be unified via a shared
  mixin method that takes the frame-pick callable as a parameter?
- `_image_fit.py`: are `apply_fit`, `flatten_onto_black`,
  `validate_choice` named consistently with the rest of the codebase?
  (mixed underscore-prefix convention — `apply_fit` is public,
  `_VALID_FITS` is private but exported.)
- `_still_decode.py` is tiny — should it just live inline in
  `still.py`?

### Area 3 — API surface / naming

**Files:** `still.py`, `_still_decode.py`, both example configs.

**Key questions:**

- `gif_align` on `StillImage` is misleading — it's not "gif" alignment,
  it's the image's horizontal alignment. Should be renamed to
  `image_align` / `h_align`. But that creates a divergence with
  `GifPlayer` unless we rename there too. Cost/benefit of cross-widget
  rename now (still pre-merge for still, post-merge for gif)?
- `hold_seconds` vs `gif_loops` — different fields for "how long does
  this thing display" across the two widgets. Confusing? Could one
  generic name cover both?
- `text_x_offset` / `text_y_offset` defaults are 0 — are they ever
  validated? Negative values are explicitly meaningful. Any range
  to enforce?
- Validation gaps: `text_valign = "top"` requires no min for
  `text_y_offset`, but at extreme negatives the text goes off-canvas.
  Should we clamp or warn? Same question for `text_x_offset` with
  long text + extreme offsets.
- Discoverability: a TOML author looking at `still.py` would see the
  schema-at-a-glance docstring at the top, but the `text_x_offset`
  + `text_y_offset` interaction with `text_valign` / `text_align`
  isn't visually clear. Worth a "common patterns" section in the
  docstring with examples?

### Area 4 — Test effectiveness

**Files:** `test_still.py`, `test_still_decode.py`, additions to
`test_gif.py`.

**Key questions:**

- Adversarial: pick 3 plausible regressions in `StillImage` that
  would NOT be caught by the current tests.
- Are tests over-specified? `test_top_valign_paints_at_panel_top_with_text_scale_2`
  asserts `seen_canvases[0].height == 32` — would this fail on a
  benign refactor that picks a different (still-correct) content
  height?
- Coverage gaps: each fit × gif_align combo for stills?
  hold_seconds=0 edge case? text_loops + scroll_direction="right"
  combo (scroll right + traversal floor)?
- Real-asset smoke tests in `test_still.py` skip if the asset is
  missing. CI may or may not have the assets — is that the
  intended behavior, or should they fail loudly?
- `test_text_canvas_follows_back_buffer` is a regression for the
  pulsing-flicker bug we hit in gif. Same bug pattern in still —
  test exists. Does it actually trip without the fix?

### Area 5 — Documentation

**Files:** `still.py` module/class docstrings, `_image_fit.py` /
`_still_decode.py` docstrings, `CLAUDE.md`,
`config/config.image_test.example.toml`, this branch's commit
messages.

**Key questions:**

- `CLAUDE.md` got a one-paragraph section about StillImage. Is that
  enough? Should it be a parallel structure with the gif paragraph?
- Schema docstring at top of `still.py` — does it describe
  `text_x_offset` and the new `text_y_offset` content_height
  semantics correctly?
- Cross-references: should `gif.py` mention `still.py` in its
  module docstring (and vice versa) so readers can find the sibling?
- Example config — section comments accurate? Section 10's
  `text_y_offset = -2` comment explains the BDF padding situation
  but is it the right thing to lead with for the
  text_y_offset / text_x_offset demonstration?
- `_image_fit.py` is the one TRULY shared module. Does its
  docstring acknowledge it's the canonical place for the fit
  primitives, and does it list both consumers?

### Area 6 — Holistic review (against the "feature parity" claim)

**Tool:** `superpowers:code-reviewer` agent.

**Inputs:**

- The branch's commit messages (especially the first big one for
  context on intent).
- `gif.py` and `still.py` side-by-side.
- `CLAUDE.md` GIF + StillImage paragraphs.
- This branch had NO formal spec — the design was "identical feature
  sets to the gif". The reviewer's job is to verify that.

**Key questions:**

- "Identical feature set" check — walk through every public field on
  `GifPlayer` and confirm `StillImage` has the equivalent (with
  documented exceptions like `gif_loops` ↔ `hold_seconds`).
- Behavioral parity — do shared features (text alignments, valign,
  scroll, transparency, gif_align) actually behave identically
  given the same inputs?
- Hardware constraint compliance for the new `still.py` code (per
  CLAUDE.md's CRITICAL section #1-#11). Particularly: SwapOnVSync
  return capture (#1), text-canvas rebind after swap (#10).
- Architectural integration — does `StillImage` inherit / delegate
  / share the right amount of code with `GifPlayer`? Any couplings
  that should be loosened or tightened?
- Untested surface areas in the new code.

## Process

1. Dispatch all 6 reviewers in parallel.
2. Aggregate findings into
   `docs/superpowers/plans/2026-05-02-still-image-review-findings.md`
   ordered by severity, deduplicated.
3. Discuss with user; user picks pre-merge vs post-merge fixes.

## Success criteria

Same as before: every reviewer returns non-empty findings, low
overlap (<30%), aggregated punch list short enough to read in one
sitting.
