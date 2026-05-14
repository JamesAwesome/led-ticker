# Unify hold_time on scroll_through — Implementation Plan

> Every subagent MUST run `git branch --show-current` first. Expected: `unify-hold-time-scroll-through`.

**Goal:** Bring TwoRow scroll_through's `hold_time` honoring up to parity with image widgets. Engine computes `n_passes = max(loops_or_1, ceil(hold_time_ticks / cycle_width))` and runs the scroll for that many passes.

**Spec:** `docs/superpowers/specs/2026-05-14-unify-hold-time-scroll-through-design.md`.

**Working directory:** `/Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/unify-hold-time/`.

---

### Task 1: TDD — write all 5 failing engine tests

**File:** `tests/test_widgets/test_two_row_scroll_through.py`

Add a new test class `TestScrollThroughHoldTimeUnification` with the five tests from the spec. Use real `TwoRowMessage` widgets driven through `_swap_and_scroll` (not mocks of the engine). Pattern after the existing `TestScrollThroughEngineIntegration` class.

Each test asserts on the final `pos` value (or on the number of times `draw()` was called, depending on what's easier to instrument). For "N passes":

```python
expected_min_pos = -(n_passes * cycle_width)
assert final_pos <= expected_min_pos
```

For "exactly N passes":

```python
expected_pos_range = (-(n_passes * cycle_width), -((n_passes - 1) * cycle_width))
assert expected_pos_range[0] <= final_pos < expected_pos_range[1]
```

Run: `uv run pytest tests/test_widgets/test_two_row_scroll_through.py -k "TestScrollThroughHoldTimeUnification" -v`. Expect all 5 to FAIL initially.

Commit: `tests: add failing tests for scroll_through hold_time unification`

### Task 2: Engine implementation in `_swap_and_scroll`

**File:** `src/led_ticker/ticker.py`

Find the `forces_offscreen_scroll = True` branch in `_swap_and_scroll`. Currently it just sets `continuous = True` and falls through to the standard scroll loop.

Replace with a dedicated loop that:

1. Does an initial draw to populate `widget._bottom_width`. Capture the swap return (constraint #1).
2. Computes `bottom_width = widget._bottom_width`.
3. Computes `cycle_width = canvas.width + bottom_width` (distance from "off-right" to "off-left").
4. Computes `hold_time_ticks = int(hold_time * 1000 / (scroll_speed * 1000))` (equivalent to `int(hold_time / scroll_speed)`).
5. Reads `bottom_text_loops` from widget (default 0). Computes `loops_floor = bottom_text_loops or 1`.
6. Computes `n_passes = max(loops_floor, math.ceil(hold_time_ticks / cycle_width))` if `cycle_width > 0` else `loops_floor`.
7. Loops `pos` from `0` to `-(n_passes * cycle_width)`, decrementing by 1 each tick.
8. Per tick: `_advance_frame_if_supported(widget)`, `reset_canvas`, `widget.draw(canvas, cursor_pos=pos)`, `canvas = _swap(canvas, frame)`, `await asyncio.sleep(scroll_speed)`.
9. Return `(canvas, final_cursor_pos, pos)` matching the function's existing return shape.

Reference: `_image_base._play_with_text`'s marquee path implements the same `max(min_loops × cycle_width, time_based_ticks)` math. Mirror that pattern.

Run: `uv run pytest tests/test_widgets/test_two_row_scroll_through.py -k "TestScrollThroughHoldTimeUnification" -v`. Expect all 5 to PASS.

Run: `uv run pytest tests/test_widgets/test_two_row_scroll_through.py -v` for regressions in the existing tests, especially `TestScrollThroughEngineIntegration`. All should stay green.

Commit: `ticker: scroll_through hold_time unification (max-of with bottom_text_loops)`

### Task 3: TwoRowMessage docstring update

**File:** `src/led_ticker/widgets/two_row.py`

Find `draw()`'s docstring (near the return statement). Add a one-liner noting that on the scroll_through engine path the returned `cursor_pos` is overridden by the engine's max-of computation. No behavior change.

Commit: `two_row: docstring note about engine cursor_pos override on scroll_through`

### Task 4: Docs cleanup

**Files:**
- `docs/site/src/content/docs/widgets/two_row.mdx`
- `docs/site/src/content/docs/widgets/gif.mdx`
- `docs/site/src/content/docs/widgets/image.mdx`

For `two_row.mdx`:
- DELETE the "Section `hold_time` is IGNORED" callout in scroll-through section.
- DELETE the "Important: same field on gif/image behaves DIFFERENTLY" callout.
- UPDATE `bottom_text_loops` (or scroll_through equivalent) prose to describe max-of-with-hold_time. Copy the shape from the wrap-mode docs in the same file (the existing rule-28 prose).

For `gif.mdx` and `image.mdx`:
- DELETE the parallel "Important" callouts about cross-widget asymmetry. The text warned of a difference that's about to vanish.

Verification: `make docs-lint` clean.

Commit: `docs: remove scroll_through cross-widget asymmetry callouts`

### Task 5: Demo re-render

**File:** `docs/site/demos-pinned/two_row-scroll_through.toml`

Update the demo to showcase the new max-of behavior. Suggested change:

```toml
# Before: bottom_text_loops = 3 (with hold_time ignored)
# After:
bottom_text_loops = 0
hold_time = 10.0
bottom_text = "<longer text to clearly show multiple passes>"
```

Run:
```bash
uv run python tools/render_demo/render.py docs/site/demos-pinned/two_row-scroll_through.toml -o docs/site/public/demos-pinned/two_row-scroll_through.gif --duration 20
```

Verify the gif visually shows multiple passes happening because `hold_time` is the floor.

Commit: `demos: re-render two_row-scroll_through to showcase hold_time-driven passes`

### Task 6: Final verification + PR

```bash
make test
make lint
uv run pyright src/
make docs-lint
```

All clean. Target test count: 1692 (was 1687 before this PR plus 5 new).

Push:
```bash
git push -u origin unify-hold-time-scroll-through
gh pr create --title "ticker: unify hold_time semantics on scroll_through (TwoRow ↔ image)" --body "..."
```

PR body should reference PR #63 (which introduced the asymmetry), explain the unification math (max-of pattern), summarize the 5 new tests, list the deleted docs callouts, and note the demo re-render.

---

## Self-review

- TDD discipline maintained (Task 1 writes failing tests first).
- Engine change is localized to one branch in `_swap_and_scroll`.
- Constraints #1 (SwapOnVSync capture) and #12 (advance_frame per tick) explicitly called out in the implementation steps.
- No widget behavior change — the widget's `draw()` is unchanged; only the engine path is rewritten.
- No image/gif widget changes — they already implement the target pattern.
- Docs cleanup is pure deletions + one prose update to match the wrap-mode pattern.
- Demo re-render proves the new behavior is visible in the docs.

## Tradeoffs

- Engine uses `widget._bottom_width` (private attribute). This is the same pattern image widgets use to read each other's measured dimensions; not new coupling.
- The first-draw-then-measure pattern adds one extra tick before the timed loop begins. Acceptable cost — it's needed to know `bottom_width` for the cycle math.
