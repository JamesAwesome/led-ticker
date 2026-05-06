# Frame-Advance Audit + Convention Lock-In

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop playing whack-a-mole on the "rainbow renders as static gradient" bug. Audit every redraw loop in the engine, fix every site that doesn't advance the frame counter, lock the convention with a meta-tripwire test, and document the rule in CLAUDE.md.

**Architecture:** The contract is *every per-tick redraw loop in the engine must call `_advance_frame_if_supported(widget)` before drawing*. Frame-aware widgets (`_FrameAware` mixin) increment `_frame_count`, which `ColorProvider.color_for(frame, ...)` reads to animate rainbow / color_cycle / typewriter. We've patched five sites incrementally; this plan finds them all and adds a regression-prevention tripwire.

**Branch:** Continue on `presentation-emoji-per-char`. Personal repo, direct-to-main authorized.

---

## Audit results — every redraw site in `ticker.py`

Sites confirmed to redraw the same widget across multiple ticks at frame cadence:

| Site | Function | Line | Status |
|---|---|---|---|
| 1 | `_swap_and_scroll` pre-scroll hold | 832 | ✅ advances |
| 2 | `_swap_and_scroll` scroll loop | 848 | ✅ advances |
| 3 | `_swap_and_scroll` post-scroll hold | 858 | ✅ advances |
| 4 | `_swap_and_scroll` held-text branch | 867 | ✅ advances |
| 5 | `_scroll_and_delay` scroll-in | 325 | ✅ advances (commit 79c95fc) |
| 6 | `_scroll_and_delay` post-scroll hold | 340 | ✅ advances (commit a1f10c1) |
| 7 | `_scroll_one_by_one` while loop | 381 | ❌ **MISSING** |
| 8 | `_scroll_side_by_side` outer while loop | 443 | ❌ **MISSING** (multi-widget) |
| 9 | `_scroll_between` transition loop | 579 | ⚠️  intentional? — see Task 4 |
| 10 | `_BaseImageWidget._play_with_text` per-tick | n/a | ✅ advances (commit 1651df8) |
| 11 | `_BaseImageWidget._play_with_two_row_text` per-tick | n/a | ✅ advances (commit 1651df8) |

**Excluded (single-shot draws, not loops):** lines 310 (`_scroll_and_delay` pre-loop draw), 820 (`_swap_and_scroll` pre-branch draw) — followed immediately by a tick loop that advances. Static-text fast paths in image widgets — gated on `frame_invariant=True`, so by definition no animation is wanted.

**Excluded (fast paths in image widgets):** static + frame_invariant provider takes paint-once-and-sleep — correct because output is invariant.

**Hardware bug surfaced now:** §17 (RSS feed in `forever_scroll` mode with `font_color = "rainbow"`) routes through `_scroll_one_by_one` (queue length 1) — site #7. Per-char dispatch works (gradient visible), but `_frame_count` never advances → static gradient.

---

## Task 1: Fix `_scroll_one_by_one` — advance per scroll tick

**Files:**
- Modify: `src/led_ticker/ticker.py:381` (the `while True` loop in `_scroll_one_by_one`)
- Test: `tests/test_ticker_display.py` (new test in `TestScrollOneByOne` or similar)

**Steps:**

- [ ] **Step 1: Write the failing tripwire**

```python
async def test_scroll_one_by_one_advances_frame_per_tick(
    self, canvas, mock_frame, no_sleep
):
    """Tripwire: forever_scroll mode redraws each story per tick.
    Animated providers (rainbow / color_cycle) need advance_frame
    per tick or they freeze on the visit-initial hue.

    Hardware bug: §17 (RSS rainbow) rendered as a static gradient
    because _scroll_one_by_one's while loop never advanced the
    widget's frame counter.
    """
    from led_ticker.ticker import _scroll_one_by_one

    widget = mock.Mock()
    widget.draw.side_effect = lambda c, cursor_pos=0: (c, cursor_pos + 5)
    widget._advance_frame_count = 0

    def _advance():
        widget._advance_frame_count += 1
    widget.advance_frame.side_effect = _advance

    queue = asyncio.Queue()
    await queue.put(widget)

    await _scroll_one_by_one(canvas, mock_frame, queue, scroll_speed=0)

    # Widget scrolled from cursor_pos=0 down through ~5 ticks before
    # final_pos < 0 broke the loop. advance_frame should have been
    # called once per tick.
    assert widget._advance_frame_count >= 1, (
        f"Expected ≥1 advance_frame calls; got "
        f"{widget._advance_frame_count}. _scroll_one_by_one redraws "
        f"the widget per tick but isn't calling _advance_frame_if_supported."
    )
```

Run: `pytest tests/test_ticker_display.py::TestScrollOneByOne::test_scroll_one_by_one_advances_frame_per_tick -v`
Expected: FAIL — `_advance_frame_count == 0`.

- [ ] **Step 2: Apply the fix** (already in working tree — verify still present)

```python
while True:
    # Advance the per-tick frame on the widget currently on-screen
    # so animated providers (rainbow, color_cycle) animate during
    # the scroll. Without this, RSS stories with `font_color =
    # "rainbow"` render as a static gradient that scrolls but
    # doesn't sweep over time.
    _advance_frame_if_supported(ticker_object)
    reset_canvas(canvas, getattr(ticker_object, "bg_color", None))
    canvas, final_pos = ticker_object.draw(canvas, cursor_pos=pos)
    ...
```

- [ ] **Step 3: Verify test passes + full suite green**

Run: `PYTHONPATH=tests/stubs uv run pytest -q`
Expected: 1163+ passing, 1 skipped.

- [ ] **Step 4: Commit**

```bash
git add src/led_ticker/ticker.py tests/test_ticker_display.py
git commit -m "_scroll_one_by_one: advance frame per tick"
```

---

## Task 2: Fix `_scroll_side_by_side` — advance every buffered widget per tick

This loop is more complex than #7 because it draws multiple `buffered_objects[i]` per iteration. Need to advance each unique widget once per outer tick, before the inner draw loop runs.

**Files:**
- Modify: `src/led_ticker/ticker.py:443` (the outer `while True` in `_scroll_side_by_side`)
- Test: `tests/test_ticker_display.py` (analogous tripwire)

**Steps:**

- [ ] **Step 1: Write the failing tripwire**

```python
async def test_scroll_side_by_side_advances_frame_per_tick(
    self, canvas, mock_frame, no_sleep
):
    """Tripwire: side-by-side scroll redraws every buffered widget
    per tick. Each unique widget must get advance_frame once per
    outer tick — not zero (frozen) and not multiple times per outer
    tick (over-advance when one widget appears multiple times in
    buffered_objects)."""
    from led_ticker.ticker import _scroll_side_by_side

    w1 = _make_tracking_widget(width=20)
    w2 = _make_tracking_widget(width=20)
    queue = asyncio.Queue()
    await queue.put(w1)
    await queue.put(w2)

    # Run a few ticks, then check both widgets advanced.
    # ... (cap iterations via mock to make this tractable)
    # Assert: w1._advance_frame_count >= 1 AND w2._advance_frame_count >= 1
    # AND w1._advance_frame_count is NOT wildly larger than the tick
    # count (no over-advance from buffered duplicates).
```

Run + verify FAIL.

- [ ] **Step 2: Apply the fix**

Add before the inner draw loop, deduping by `id()` since `buffered_objects` may contain a widget multiple times during scroll:

```python
while True:
    # Advance per-tick frame on every UNIQUE widget being drawn this
    # tick. Dedup by id() because buffered_objects can contain the
    # same widget instance multiple times during scroll — calling
    # advance_frame multiple times per tick would over-advance.
    seen: set[int] = set()
    for w in buffered_objects:
        if id(w) not in seen:
            _advance_frame_if_supported(w)
            seen.add(id(w))

    first_widget = buffered_objects[0] if buffered_objects else None
    bg = getattr(first_widget, "bg_color", None) if first_widget else None
    reset_canvas(canvas, bg)
    ...
```

- [ ] **Step 3: Verify test passes + full suite green**

- [ ] **Step 4: Commit**

```bash
git commit -m "_scroll_side_by_side: advance every buffered widget per tick"
```

---

## Task 3: Add the meta-tripwire — prevents future regressions

A regression-prevention test that scans `ticker.py` for redraw patterns and asserts each is paired with `advance_frame`. Catches the next time someone adds a redraw loop without advancing.

**Files:**
- Create: `tests/test_engine_redraw_contract.py`

**Steps:**

- [ ] **Step 1: Write the meta-test**

Approach: parse `ticker.py` AST. Find every async function in the engine. For each, find every `widget.draw(...)` or `ticker_obj.draw(...)` call inside a loop (`while` or `for`). Assert every such loop body also contains a call to `_advance_frame_if_supported` OR is in an explicit allow-list (e.g. transition compositors where pause_frame is in effect).

```python
"""Meta-tripwire: every per-tick redraw loop in the engine must call
_advance_frame_if_supported. Scans ticker.py AST to enforce the rule
without listing each loop by name (which is exactly the manual audit
that produced the recurring 'rainbow as static gradient' bug)."""

import ast
from pathlib import Path

ENGINE_PATH = Path(__file__).parent.parent / "src" / "led_ticker" / "ticker.py"

# Functions whose redraw loops are intentionally NOT frame-advancing,
# because the frame is paused at the call site (transitions). Keep
# this list short and well-justified.
ALLOW_LIST: set[str] = {
    "_scroll_between",  # transition compositor; pause_frame in effect
    "_draw_scroll_frame",  # called by _scroll_between, not a loop itself
}

def _function_has_advance_in_loops(func_node: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[bool, list[str]]:
    """Return (compliant, reasons). Compliant means: every loop body that
    contains a *.draw(...) call also contains a _advance_frame_if_supported
    call (anywhere in the same loop body)."""
    issues: list[str] = []
    for node in ast.walk(func_node):
        if isinstance(node, (ast.While, ast.For, ast.AsyncFor)):
            # Look for *.draw(...) calls in this loop body
            draw_calls = [
                n for n in ast.walk(node)
                if isinstance(n, ast.Call)
                and isinstance(n.func, ast.Attribute)
                and n.func.attr == "draw"
            ]
            if not draw_calls:
                continue
            # And look for _advance_frame_if_supported(...)
            advance_calls = [
                n for n in ast.walk(node)
                if isinstance(n, ast.Call)
                and isinstance(n.func, ast.Name)
                and n.func.id == "_advance_frame_if_supported"
            ]
            if not advance_calls:
                issues.append(
                    f"loop at line {node.lineno} draws but doesn't advance"
                )
    return (not issues, issues)


def test_every_redraw_loop_advances_frame():
    tree = ast.parse(ENGINE_PATH.read_text())
    failures: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name in ALLOW_LIST:
                continue
            ok, issues = _function_has_advance_in_loops(node)
            if not ok:
                for issue in issues:
                    failures.append(f"{node.name}: {issue}")

    assert not failures, (
        "Engine redraw loops missing advance_frame calls:\n  - "
        + "\n  - ".join(failures)
        + "\n\nEither add `_advance_frame_if_supported(widget)` per "
        "tick, or add the function name to ALLOW_LIST with justification."
    )
```

- [ ] **Step 2: Run test — should pass after Task 1 + Task 2**

If it fails, the AST scan caught a site we missed. Investigate.

- [ ] **Step 3: Commit**

```bash
git commit -m "tests: AST meta-tripwire for engine redraw loop contract"
```

---

## Task 4: Decide on `_scroll_between` — transition or redraw loop?

`_scroll_between` (line 579) is the seamless 1px/frame scroll between widgets used by the `scroll` transition. Both `outgoing` and `incoming` are drawn every frame for `total_travel + 1` ticks (~166 ticks for 160-px canvas + separator). The current code does NOT advance frame on either widget.

Decision needed:
- **(A)** This is a transition; frame is paused per CLAUDE.md constraint #11. Confirm pause is actually in effect during `_scroll_between` (audit `_run_swap` for pause_frame calls around the call site). If yes, add to ALLOW_LIST with justification. Done.
- **(B)** Pause is NOT in effect — `_scroll_between` is dispatched directly from `_run_swap`, not through `run_transition` which is the function that pauses. So a rainbow widget mid-scroll-transition would freeze. Visually subtle (transition lasts ~8s on small sign), but inconsistent.

**Files:**
- Investigate: `src/led_ticker/ticker.py` — find `_scroll_between` call sites and check if `pause_frame` is set on the widgets first.

**Steps:**

- [ ] **Step 1: Audit call sites**

```bash
grep -n "_scroll_between\|pause_frame\|resume_frame" src/led_ticker/ticker.py
```

- [ ] **Step 2: Decide A or B based on findings**

If A (pause is in effect): add `"_scroll_between"` to `ALLOW_LIST` in the meta-test. Document why in a comment.

If B (pause is NOT in effect): add `_advance_frame_if_supported(outgoing)` and `_advance_frame_if_supported(incoming)` once per outer tick. Update the meta-test.

- [ ] **Step 3: Test + commit accordingly**

---

## Task 5: CLAUDE.md — formalize the contract

Constraint #12 currently mentions `play()`-style widgets. Generalize it to cover all redraw loops, naming the meta-tripwire as the enforcement mechanism.

**Files:**
- Modify: `CLAUDE.md` (constraint #12 in the `### CRITICAL: Hardware Rendering Constraints` section)

**Steps:**

- [ ] **Step 1: Edit constraint #12 wording**

Replace the existing text with:

> 12. **Every per-tick redraw loop must call `advance_frame()` per tick**: Frame-aware widgets (the `_FrameAware` mixin) track `_frame_count`, which `ColorProvider.color_for(frame, ...)` reads to animate rainbow / color_cycle. Any loop that calls `widget.draw(...)` at frame cadence must also call `_advance_frame_if_supported(widget)` before the draw — otherwise the provider sees a stuck `_frame_count` and the rainbow renders as a static gradient. The convention applies to:
>   - The shared engine (`_swap_and_scroll`, `_scroll_and_delay`, `_scroll_one_by_one`, `_scroll_side_by_side`).
>   - `play()`-style widgets that own their render loop (`GifPlayer.play()` / `StillImage.play()` via `_BaseImageWidget._play_with_text` / `_play_with_two_row_text`).
>   - Static-text fast paths bypass via the provider's `frame_invariant` flag — only `_ConstantColor`, `Random`, and `Gradient` skip the per-tick loop.
>   - Transition compositors are EXEMPT — `run_transition` calls `pause_frame()` so the widget's counter doesn't drift while being re-rendered for compositing.
>
>   Enforcement: `tests/test_engine_redraw_contract.py` AST-scans `ticker.py` and asserts every loop body containing a `widget.draw(...)` call also contains `_advance_frame_if_supported(...)`, with a minimal allow-list for transition compositors.

- [ ] **Step 2: Commit**

```bash
git commit -m "CLAUDE.md: formalize redraw-loop frame-advance contract"
```

---

## Order of operations

1. Task 1 (fix `_scroll_one_by_one` — directly fixes the §17 RSS bug)
2. Task 2 (fix `_scroll_side_by_side`)
3. Task 4 (decide on `_scroll_between`)
4. Task 3 (add meta-tripwire — passes once 1, 2, 4 are done)
5. Task 5 (CLAUDE.md update)

After all five: push, hardware-test §17 + smoke that uses `forever_scroll` (mlb in any existing config), then merge `presentation-emoji-per-char` into `main`.

---

## What's deferred

- Wall-clock-based frame counter (`int(time.monotonic() * fps)`) — would make this whole bug class disappear architecturally, but breaks `pause_frame` semantics during transitions. Worth considering as a future cleanup, not on this branch.
- Property-based test that constructs every public engine entry × every animated provider and verifies frame_count advances. Overkill for a personal repo; the AST tripwire catches the bug class for ~30 lines of test code.
