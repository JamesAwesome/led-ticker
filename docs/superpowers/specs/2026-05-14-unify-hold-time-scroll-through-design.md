# Design: Unify `hold_time` semantics on `scroll_through`

**Date:** 2026-05-14
**Status:** Approved

## Overview

PR #63 shipped `bottom_text_scroll = "scroll_through"` on `TwoRowMessage` and image/gif widgets with the same field surface but asymmetric `hold_time` semantics. This PR removes the asymmetry: both widget families now honor `hold_time` as a floor alongside `bottom_text_loops`, with max-of semantics — the same shape that already exists for wrap mode (rule 28 docs spell this out).

## Current behavior (the asymmetry)

| Widget family | Behavior |
|---|---|
| `TwoRowMessage` scroll_through | Runs exactly `bottom_text_loops` passes (default 1). `hold_time` is **ignored**. Widget exits as soon as scrolls complete. |
| Image/gif scroll_through | Marquee auto-floor — at least one pass, `hold_seconds` extends to fill the time (text keeps cycling until hold elapses). |

A user who copies a scroll_through config from a `gif` widget to a `two_row` widget loses the `hold_time` honoring silently.

## Target behavior

```
passes = max(bottom_text_loops or 1, ceil(hold_time_ticks / cycle_width))
where cycle_width = canvas.width + bottom_width
      hold_time_ticks = int(hold_time * 1000 / scroll_step_ms)
```

- Both unset → baseline 1 pass (regression-safe; matches current single-pass default).
- Only loops set → exactly N passes (current TwoRow behavior; preserved).
- Only hold_time set → enough passes to cover the hold.
- Both set → max wins.

## Scope

**TwoRow side only.** Image widgets already implement this exact pattern in `_image_base._play_with_text` (the marquee auto-floor with `text_loops` × cycle_width vs hold_time-derived ticks, max-of). The fix is to bring the TwoRow engine path up to parity.

## File map

1. **`src/led_ticker/ticker.py`** — `_swap_and_scroll`, the `forces_offscreen_scroll = True` branch. Currently sets `continuous = True` and lets the standard scroll loop run. Replace with a dedicated loop that:
   - Performs a first draw to populate `widget._bottom_width` (it's measured lazily).
   - Computes `cycle_width = canvas.width + widget._bottom_width`.
   - Computes `hold_time_ticks = int(hold_time * 1000 / scroll_step_ms)` (using the scroll_speed already in scope as `scroll_step_ms / 1000`).
   - Computes `n_passes = max(bottom_text_loops or 1, ceil(hold_time_ticks / cycle_width))`.
   - Loops `pos` from `0` down to `-n_passes * cycle_width`, calling `advance_frame + draw + swap` per tick (per constraint #12 / #1).
   - ~15-20 lines.

2. **`src/led_ticker/widgets/two_row.py`** — no behavior change. The widget's `draw()` still returns a `cursor_pos`; on this engine path the engine overrides it with the max-of-derived bound. Add a one-line note in the docstring on `draw()` near the return statement.

3. **`docs/site/src/content/docs/widgets/two_row.mdx`**:
   - DELETE the "Section `hold_time` is IGNORED" callout in scroll-through section.
   - DELETE the "Important: same field on gif/image behaves DIFFERENTLY" callout (no longer differs).
   - UPDATE the `bottom_text_loops` section to describe the max-of-with-hold_time semantics. Copy the shape from the wrap-mode docs in the same file.

4. **`docs/site/src/content/docs/widgets/gif.mdx`** and **`image.mdx`** — DELETE the parallel "Important" callouts that pointed at the cross-widget asymmetry. The text was warning of a difference that's about to vanish.

5. **`docs/site/demos-pinned/two_row-scroll_through.toml`** — re-render the demo to showcase the new max-of behavior. Current demo uses `loops=3` with `hold_time` ignored; change to e.g., `bottom_text_loops = 0` + `hold_time = 10.0` + a longer `bottom_text` so the demo visually shows passes being driven by the hold-time floor.

## Tests

Five new tests in `tests/test_widgets/test_two_row_scroll_through.py` (real-widget engine integration; don't mock `_swap_and_scroll`):

1. `test_scroll_through_hold_time_alone_drives_passes` — `hold_time=2.0`, `bottom_text_loops=0` → ≥ 2 full passes.
2. `test_scroll_through_loops_wins_over_short_hold_time` — `hold_time=0.5`, `bottom_text_loops=3` → exactly 3 passes.
3. `test_scroll_through_hold_time_wins_over_one_loop` — `hold_time=5.0`, `bottom_text_loops=1` → multiple passes.
4. `test_scroll_through_both_zero_one_pass` — regression-safe: `hold_time=0.0`, `bottom_text_loops=0` → exactly 1 pass.
5. `test_scroll_through_loops_only_unchanged` — `bottom_text_loops=3`, `hold_time=0` → exactly 3 passes. Regression coverage; existing test should stay green.

## Constraints (CLAUDE.md hardware-rendering invariants)

- **#1** `SwapOnVSync` return value MUST be captured every iteration.
- **#12** Every per-tick `widget.draw()` MUST be preceded by `_advance_frame_if_supported()`.
- The existing `TestScrollThroughEngineIntegration` mock tests for "skip pre/post holds" must stay green. They exercise the basic skip behavior which is unchanged on this code path.

## Out of scope

- No changes to image/gif widget behavior (they already implement this).
- No validator rule changes — the unification doesn't introduce a new error class.
- No changes to wrap-mode behavior (the rule-28 `max()` semantics are the model we're matching, not changing).
- No demo gif re-render scripting; the user already has the render command in their muscle memory.

## Why this matters

This is a small but load-bearing fix for a documented confusion. The wrap-mode docs already say "engine uses max(hold_time_ticks, bottom_text_loops × cycle_width)" — users learn that mental model once. Then scroll_through silently violates it on TwoRow but not on gif/image. After this PR, the mental model holds across all three widget × mode combinations.
