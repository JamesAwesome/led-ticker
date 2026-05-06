# Fix `_scroll_side_by_side` end-of-scroll 1px visual snap

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans for this single-task fix.

**Goal:** Eliminate the 1-pixel left-snap visible at §17 (RSS feed) when scrolling stops at the held end-position. Introduced by commit `c357528` which added a tick loop for the hold but draws at the wrong cursor position.

**Architecture:** Off-by-one in the hold tick loop's `cursor_pos` argument. Trace: outer loop draws at `pos=N`, decrements `pos` to `N-1`, recovers `held_pos = pos + 1 = N`. The just-drawn frame is at cursor=N. The hold loop calls `draw(cursor_pos=held_pos - 1)` — at N-1, one pixel LEFT of the held frame. First hold tick visibly snaps the text 1px left.

The fix is a one-character edit: pass `held_pos` (not `held_pos - 1`).

**Branch:** Continue on `presentation-emoji-per-char`.

---

## Task 1: Pass `held_pos` directly in the hold tick loop

**Files:**
- Modify: `src/led_ticker/ticker.py:527`
- Test: `tests/test_ticker_display.py` — extend `TestScrollSideBySide.test_end_of_scroll_hold_advances_frame_per_tick` (or add a sibling test) that asserts `cursor_pos` passed to draw during the hold matches the cursor_pos used for the final scroll frame.

**Steps:**

- [ ] **Step 1: Write the failing tripwire**

```python
async def test_end_of_scroll_hold_redraws_at_same_position(
    self, canvas, mock_frame, no_sleep
):
    """Tripwire: the hold loop must redraw at the SAME cursor_pos as
    the final scroll frame — not one pixel left. Off-by-one would
    surface as a 1px visual snap when scrolling stops."""
    from led_ticker.ticker import _scroll_side_by_side

    # Capture every cursor_pos the widget was drawn at.
    draw_positions: list[int] = []
    widget = mock.Mock()

    def _draw(c, cursor_pos=0):
        draw_positions.append(cursor_pos)
        return (c, cursor_pos + 30)

    widget.draw.side_effect = _draw
    widget.bg_color = None

    queue = asyncio.Queue()
    await queue.put(widget)
    await _scroll_side_by_side(
        canvas, mock_frame, queue, scroll_speed=0, hold_at_end=0.2
    )

    # Find where the hold begins — the first cursor_pos that REPEATS
    # signals the hold (vs the monotonically-decreasing scroll-in
    # sequence). All hold positions must equal that first hold pos.
    last_scroll_pos = draw_positions[-5]  # arbitrary final scroll
    # ... actually simpler: assert the last N positions are constant.
    final_positions = draw_positions[-3:]
    assert all(p == final_positions[0] for p in final_positions), (
        f"Last 3 draw positions: {final_positions}. The hold loop "
        f"must redraw at the same cursor_pos every tick — variation "
        f"means a visual snap."
    )
```

Run: `pytest tests/test_ticker_display.py::TestScrollSideBySide::test_end_of_scroll_hold_redraws_at_same_position -v`
Expected: FAIL — first hold tick is at `held_pos - 1`, all subsequent at `held_pos - 1` (since `cursor_pos=held_pos - 1` is hardcoded), but the FINAL scroll frame was at `held_pos` — so the last scroll frame and the first hold tick differ by 1.

Hmm — actually the test as-written might pass since the hold loop is internally consistent. The snap is visible only at the boundary between scroll and hold. Let me make the assertion specifically about that boundary:

```python
# The final scroll-in draw and the first hold-loop draw should be
# at the same cursor_pos. Visually this means the text doesn't
# jump when scrolling stops.
# ... need to identify which index in draw_positions is the
# scroll/hold boundary. Easiest: the LAST scroll iteration's draw
# is at `pos`, and `pos` decrements each iter. The hold loop's
# draws are all at the same value. So the boundary is where the
# strictly-decreasing prefix ends.
diffs = [draw_positions[i+1] - draw_positions[i] for i in range(len(draw_positions)-1)]
# Find the first non-(-1) diff — that's where the snap lives.
boundary = next((i for i, d in enumerate(diffs) if d != -1), len(diffs))
# At the boundary, the diff should be 0 (no jump), not -1 (snap).
# Actually the scroll-in goes pos, pos-1, pos-2 ... so diffs are -1.
# Then at scroll→hold the diff becomes (hold_pos - last_scroll_pos).
# We want this to be 0 (no snap).
if boundary < len(diffs):
    assert diffs[boundary] == 0, (
        f"Visual snap at scroll→hold boundary: cursor jumped by "
        f"{diffs[boundary]}px. Expected 0 (hold redraws at the same "
        f"position as the final scroll frame)."
    )
```

Or simpler — since I know `held_pos = pos + 1` and the bug passes `held_pos - 1 == pos`: assert that the cursor_pos values are continuously decreasing through scroll AND the first hold value matches the last scroll value.

- [ ] **Step 2: Apply the fix**

In `ticker.py:527`, change:
```python
canvas, _ = buffered_objects[0].draw(canvas, cursor_pos=held_pos - 1)
```
to:
```python
canvas, _ = buffered_objects[0].draw(canvas, cursor_pos=held_pos)
```

And update the comment block above it — it currently says "we redraw at the same position by passing `held_pos - 1` (= the original pos)" which is the wrong arithmetic. The original input pos that produced the just-drawn frame IS `held_pos` (since `held_pos = pos + 1` and `pos` was decremented after the draw). So passing `held_pos` directly redraws at the same position.

- [ ] **Step 3: Verify test passes + meta-tripwire still passes + full suite green**

```bash
PYTHONPATH=tests/stubs uv run pytest -q
```

- [ ] **Step 4: Commit**

```bash
git add src/led_ticker/ticker.py tests/test_ticker_display.py
git commit -m "_scroll_side_by_side hold: redraw at held_pos not held_pos-1"
```

---

## Why this happened

The original code did `await asyncio.sleep(hold_at_end)` — no redraw, so no off-by-one to make. When I converted to a tick loop in `c357528`, I reasoned: `held_pos = pos + 1` is "the input pos used for the just-drawn frame" — but then I mis-reasoned and subtracted 1 again, conflating "the input pos" with "the next pos to use." Since the `for` loop in the original scroll code does `pos -= 1` AFTER the draw, the input pos that produced the draw IS `held_pos` itself.

A unit test that compared the last scroll cursor_pos to the first hold cursor_pos would have caught this. Adding it now closes the loop.

---

## Out of scope

- Whether `held_pos` is the right place to STOP scrolling at all is a separate question — that's the engine's choice (last char fully visible at the right edge). This plan only fixes the snap caused by the redraw using a different cursor than the held frame.
