# Reset incoming widget's frame counter at transition entry

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans for this focused fix.

**Goal:** Eliminate the brief "full text visible before typewriter starts" flash on §4 (and equivalent visit-initial-state flashes on any frame-aware widget on loop iteration 2+).

**Background:** `run_transition` and `_scroll_between` both call `pause_frame(incoming)` so the incoming widget's `_frame_count` doesn't drift while the transition compositor re-renders it. But neither calls `reset_frame(incoming)`. On the first loop iteration this is fine — the widget's frame_count starts at 0 (constructor default). On iteration 2+, the incoming widget's frame_count is whatever it was at the END of its previous visit — for a typewriter that's "all chars typed", for a rainbow that's "mid hue rotation", for a color_cycle that's "off-default hue". The transition compositor renders that *previous-visit-end* state for its full duration, then `_show_one` calls `reset_frame()` after the transition completes, snapping the widget back to its visit-initial state.

Visible on §4 of the showroom: wipe-in shows the full typewriter text → cuts to empty → typewriter plays. Same shape would affect §7 (BUILT TO BE SEEN, color_cycle) and §10 (countdown rainbow) but more subtly.

**Branch:** Continue on `main`. Personal repo, direct-to-main authorized.

---

## Task 1: Reset incoming frame counter inside `run_transition`

**Files:**
- Modify: `src/led_ticker/transitions/__init__.py` — after `_pause_presenter(incoming)` (line 125), call `reset_frame()` on the incoming widget if it has one.
- Test: `tests/test_transitions.py` — extend the existing pause/resume tests with one that asserts the incoming widget's `_frame_count` is reset to 0 by the time the transition's first compositor draw fires.

**Steps:**

- [ ] **Step 1: Write the failing tripwire**

```python
async def test_run_transition_resets_incoming_frame_counter():
    """Tripwire: incoming widget's _frame_count must be reset to 0
    before the transition's first compositor frame fires. Without
    this, a frame-aware widget (typewriter, color_cycle, rainbow)
    renders its previous-visit-end state during the transition,
    then snaps to its visit-initial state when the section begins.
    Visible on hardware as 'full typewriter text flashes during
    wipe-in, then resets and types out'."""
    from led_ticker.transitions import run_transition
    from led_ticker.transitions.effects import Cut

    incoming = mock.Mock()
    incoming._frame_count = 99  # simulate end-of-previous-visit state
    captured_frame_at_first_draw: list[int] = []

    def _draw(c, cursor_pos=0, **kw):
        captured_frame_at_first_draw.append(incoming._frame_count)
        return (c, cursor_pos + 30)

    incoming.draw.side_effect = _draw

    def _reset():
        incoming._frame_count = 0
    incoming.reset_frame.side_effect = _reset

    outgoing = mock.Mock()
    outgoing.draw.side_effect = lambda c, cursor_pos=0, **kw: (c, cursor_pos + 30)

    canvas = mock.Mock()
    canvas.width = 160
    frame = mock.Mock()
    frame.matrix.SwapOnVSync.return_value = canvas

    await run_transition(canvas, frame, outgoing, incoming, transition=Cut(), duration=0.05)

    assert captured_frame_at_first_draw, "incoming.draw never called"
    assert all(f == 0 for f in captured_frame_at_first_draw), (
        f"incoming._frame_count must be 0 throughout the transition; "
        f"got {captured_frame_at_first_draw}. Without reset, the "
        f"compositor renders the widget's previous-visit-end state."
    )
```

(Adjust selectors per the actual `Cut` transition shape — it may not call `incoming.draw` at all if `t<1`. Pick a transition that DOES call `incoming.draw` per frame, like `WipeLeft` or just a custom test transition. Or simulate via `frame_count = max(1, int(duration/scroll_speed))` so we know it'll iterate.)

Run: should FAIL — without the fix, `_frame_count` stays at 99 throughout.

- [ ] **Step 2: Apply the fix**

In `transitions/__init__.py:125`, after the pause:

```python
_pause_presenter(outgoing)
_pause_presenter(incoming)
# Reset the incoming widget's frame counter so frame-aware effects
# (typewriter, color_cycle, rainbow) render their visit-initial
# state during the transition. Without this, on loop iteration 2+
# the incoming widget's _frame_count holds the value from the END
# of its previous visit — typewriter shows the full text during
# the wipe-in, then snaps to "R" when the section begins. _show_one
# also calls reset_frame after the transition, so the post-transition
# reset is now redundant-but-harmless (idempotent).
_reset_presenter(incoming)
try:
    ...
```

Add helper near `_pause_presenter` / `_resume_presenter`:

```python
def _reset_presenter(obj: Any) -> None:
    reset = getattr(obj, "reset_frame", None)
    if callable(reset):
        reset()
```

- [ ] **Step 3: Verify tripwire passes**

- [ ] **Step 4: Apply the same fix to `_scroll_between`**

`_scroll_between` is the other transition compositor (commit 7a47d8c). It calls `pause_frame` on outgoing AND incoming explicitly. Add `reset_frame()` on incoming right after the pause:

```python
if hasattr(outgoing, "pause_frame"):
    outgoing.pause_frame()
if hasattr(incoming, "pause_frame"):
    incoming.pause_frame()
if hasattr(incoming, "reset_frame"):
    incoming.reset_frame()
try:
    ...
```

Add a parallel tripwire test in `tests/test_ticker_display.py::TestScrollBetween` mirroring the run_transition test.

- [ ] **Step 5: Verify the AST meta-tripwire still passes**

`tests/test_engine_redraw_contract.py::test_allow_list_entries_actually_pause_and_resume_frame` checks that allow-listed compositors (just `_scroll_between`) call pause + resume. Adding reset doesn't affect pause/resume counts. Should still pass.

- [ ] **Step 6: Full suite + lint**

- [ ] **Step 7: Commit**

```bash
git commit -m "transitions: reset incoming widget frame counter at compositor entry"
```

---

## What's NOT changing

- `_show_one` keeps its `reset_frame()` call. It's redundant for transition-routed widgets (now reset twice — once in run_transition, again in _show_one), but covers cases that bypass transitions (very first widget shown in any mode, no-transition swap chains). reset_frame is idempotent (just `_frame_count = 0`), so the double-call is harmless.

- `pause_frame` semantics are unchanged. The reset comes AFTER pause but reset_frame doesn't touch the pause flag (per `_FrameAware.reset_frame` docstring).

- Outgoing widget is NOT reset — the outgoing widget is being torn off-screen, its frame state during the transition is "the state it was in at the moment the user transitioned away" which is what the visual continuity story wants. Resetting outgoing would make the outgoing widget visually rewind during the wipe-out.

---

## Hardware repro post-fix

Pull on bigsign and watch §4 → §5 transition wraparound on iteration 2 (so wait through one full ~2-3 min loop, observe iteration 2's transition into §4). The full "READY. SET. GLOW." should NOT be visible during the wipe; only the typewriter's frame=0 state ("R" or empty) should appear, then type out cleanly.
