# Fix `_scroll_side_by_side` end-of-scroll hold — animate during the hold

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the rainbow on §17 (RSS feed in `forever_scroll` mode) keep sweeping during the 2-second `hold_at_end` after scroll completes. Today the rainbow animates while the text is moving, then freezes the moment the text comes to rest.

**Architecture:** Same bug class the AST meta-tripwire is designed to catch — but at a sleep boundary instead of a redraw loop. Line 514 in `_scroll_side_by_side` does `await asyncio.sleep(hold_at_end)` (single sleep, ~2s) after the final draw + swap. The widget's `_frame_count` stops advancing for the whole hold; rainbow / color_cycle freeze on whatever hue they last rendered. The meta-tripwire (`tests/test_engine_redraw_contract.py`) only checks loops, so this site slipped through.

**Branch:** Continue on `presentation-emoji-per-db52cper-char`. Personal repo, direct-to-main authorized.

---

## Audit results — all single-sleep "hold" sites in `ticker.py`

Audit: every `await asyncio.sleep(...)` call where the argument is a `hold_*` parameter (not `scroll_speed` / `tick_seconds`).

| Line | Function | Argument | Status |
|---|---|---|---|
| 514 | `_scroll_side_by_side` end-of-scroll | `hold_at_end` (~2s) | ❌ **BUG** — single sleep, no advance |
| 870 | `_swap_and_scroll` pre-scroll hold | `tick_seconds` (loop) | ✅ tick loop |
| 896 | `_swap_and_scroll` post-scroll hold | `tick_seconds` (loop) | ✅ tick loop |
| 905 | `_swap_and_scroll` held-text branch | `tick_seconds` (loop) | ✅ tick loop |
| 344 | `_scroll_and_delay` post-scroll hold | `tick_seconds` (loop) | ✅ tick loop |

The static-text fast paths in `_BaseImageWidget._play_with_text` / `_play_with_two_row_text` also do `await asyncio.sleep(n_ticks * tick_seconds)` (single sleep) — but those are gated on `frame_invariant=True`, so animated providers are forced through the per-tick loop. Correct by design.

So this is the last single-sleep hold in the engine. One site to fix.

---

## Task 1: Convert `_scroll_side_by_side` end-of-scroll hold into a tick loop

**Files:**
- Modify: `src/led_ticker/ticker.py:511-515` (the `if len(buffered_objects) == 1 ...` block)
- Test: `tests/test_ticker_display.py` (new test in `TestScrollSideBySide`)

**Steps:**

- [ ] **Step 1: Write the failing tripwire**

```python
async def test_end_of_scroll_hold_advances_frame_per_tick(
    self, canvas, mock_frame, no_sleep
):
    """Tripwire: when _scroll_side_by_side reaches its end-of-scroll
    hold (queue exhausted, single widget visible), the widget's
    frame counter must continue ticking during the hold so animated
    providers (rainbow, color_cycle) keep sweeping. Without this,
    the rainbow freezes the moment the text stops moving — visible
    on hardware as smoke §17 RSS feed.
    """
    from led_ticker.ticker import _scroll_side_by_side

    widget = mock.Mock()
    widget.draw.side_effect = lambda c, cursor_pos=0: (c, cursor_pos + 30)
    widget._advance_frame_count = 0
    widget.bg_color = None

    def _advance():
        widget._advance_frame_count += 1
    widget.advance_frame.side_effect = _advance

    queue = asyncio.Queue()
    await queue.put(widget)

    # hold_at_end=0.5s @ ENGINE_TICK_MS=50ms → 10 hold ticks expected,
    # plus N scroll-in ticks before the hold.
    await _scroll_side_by_side(
        canvas, mock_frame, queue, scroll_speed=0, hold_at_end=0.5
    )

    # The hold itself must produce ≥10 advance calls. Track scroll-in
    # advances separately by snapshotting before the hold? Easier:
    # assert advance count is at least scroll_in + 10. Since the
    # scroll loop runs while cursor_pos > stop, and widget.draw width
    # is 30, scroll-in count is small. Pragmatic threshold: ≥10.
    assert widget._advance_frame_count >= 10, (
        f"Expected ≥10 advance_frame calls covering the 0.5s "
        f"end-of-scroll hold; got {widget._advance_frame_count}. "
        f"The hold is a single sleep — animated providers freeze "
        f"during the held end-state."
    )
```

Run: `pytest tests/test_ticker_display.py::TestScrollSideBySide::test_end_of_scroll_hold_advances_frame_per_tick -v`
Expected: FAIL — single sleep produces 0 advances during the hold.

- [ ] **Step 2: Apply the fix**

Replace the `if ... else: hold` block at line 511 with a tick loop:

```python
# Hold the last widget at end-of-scroll instead of letting it scroll
# fully off the left. Tick the frame counter during the hold so
# animated providers (rainbow, color_cycle) keep sweeping while the
# text is at rest. Without the tick loop, the rainbow freezes the
# moment the text stops moving — visible as static gradient on §17.
if len(buffered_objects) == 1 and queue_empty and mon_0_end_pos <= canvas.width:
    held_pos = pos + 1  # input pos used for the just-drawn frame
    canvas = _swap(canvas, frame)
    n_ticks = max(1, int(hold_at_end * 1000) // ENGINE_TICK_MS)
    tick_seconds = ENGINE_TICK_MS / 1000
    for _ in range(n_ticks):
        _advance_frame_if_supported(buffered_objects[0])
        bg = getattr(buffered_objects[0], "bg_color", None)
        reset_canvas(canvas, bg)
        canvas, _ = buffered_objects[0].draw(canvas, cursor_pos=held_pos - 1)
        canvas = _swap(canvas, frame)
        await asyncio.sleep(tick_seconds)
    return held_pos
```

Note: `held_pos = pos + 1` is the input pos used for the just-drawn frame. To redraw the same visual position, pass `held_pos - 1` (= `pos`) as `cursor_pos`.

- [ ] **Step 3: Verify test passes + meta-tripwire still passes**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_ticker_display.py::TestScrollSideBySide tests/test_engine_redraw_contract.py -v
```

Expected: all pass. The meta-tripwire's loop-detection now sees the new redraw loop and verifies it advances.

- [ ] **Step 4: Full suite**

```bash
PYTHONPATH=tests/stubs uv run pytest -q
```

Expected: 1168+ passing.

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/ticker.py tests/test_ticker_display.py
git commit -m "_scroll_side_by_side: tick end-of-scroll hold for animated providers"
```

---

## Task 2 (optional): Extend the meta-tripwire to catch single-sleep holds

The AST meta-tripwire currently only checks loops with `widget.draw(...)` calls. The bug we're fixing here was a single sleep AFTER a draw — invisible to the loop scanner.

Consider extending the test to also flag: an `await asyncio.sleep(...)` whose argument name matches `hold*` and which is NOT inside a tick loop. The check would walk every async function and look for `Call(func=Attribute(attr='sleep'))` whose argument is an identifier matching `hold_time | hold_at_end | delay` and whose nearest enclosing loop doesn't redraw.

**Verdict:** **Skip on this branch.** The cost/benefit is poor:
- The bug class only has 5 known sites total in the engine; we've now fixed all of them.
- Writing the AST check correctly (matching argument names, walking loops, identifying "the redraw loop") is more code than the per-site tripwire we already have.
- A future contributor adding a new function with a `hold_*` parameter is unlikely to skip the tick-loop pattern given it's now consistent across `_swap_and_scroll`, `_scroll_and_delay`, and `_scroll_side_by_side`.

If a 6th instance of this bug surfaces, revisit. For now, document the gap in CLAUDE.md so the next reader knows.

**Files:**
- Modify: `CLAUDE.md` constraint #12 — add a note that the AST meta-tripwire only catches loop-shaped redraws, not single-sleep holds; manual tripwires required for those.

**Steps:**

- [ ] **Step 1: Add one sentence to constraint #12**

After the "Enforcement: ..." sentence, append:

> The meta-tripwire only catches loop-shaped redraws. Single-sleep holds (`await asyncio.sleep(hold_time)` after a draw) are NOT caught by AST; each such site needs its own per-function tripwire that asserts `advance_frame` is called per `ENGINE_TICK_MS` during the hold.

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "CLAUDE.md #12: note AST meta-tripwire's loop-only coverage"
```

---

## Order of operations

1. Task 1 (fix the bug + tripwire). This directly resolves the §17 hardware report.
2. Task 2 (CLAUDE.md note). Optional — closes the loop on the meta-tripwire's documented coverage.

After Task 1: push, hardware-test §17 — the rainbow should sweep continuously across both the scroll and the 2-second end-of-scroll hold.

---

## What's deferred

- **Wall-clock-based frame counter** — same as the parent plan. Architecturally eliminates this bug class but breaks `pause_frame` semantics during transitions. Out of scope for this branch.
- **AST tripwire extension to single-sleep holds** — see Task 2 verdict. Skipped intentionally.
