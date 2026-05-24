# Large #3: ScaledCanvas Encapsulation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce `ScaledCanvas` leakage by renaming the cross-module-read `_y_offset` field to `y_offset_real`, adding a `paint_hires()` helper that collapses the unwrap+scale+offset pattern used by every hi-res paint site, collapsing four `use_hires = isinstance(canvas, ScaledCanvas)` sites to `safe_scale(canvas) > 1`, and moving the nested-wrapper rebind loop in `Ticker._play_widget` onto `ScaledCanvas.rebind_innermost()`.

**Architecture:** Each task is an independently committable slice: Task 1 is a mechanical rename, Task 2 adds a new helper and collapses two paint sites, Task 3 substitutes a safer predicate at four scale-detection sites, Task 4 adds `rebind_innermost()` and cleans up `_play_widget`. No task breaks the others — failing tests after Task 1 point only at missed rename sites.

**Tech Stack:** Python, attrs, pytest. No new dependencies.

---

## File map

| File | Role |
|------|------|
| `src/led_ticker/scaled_canvas.py` | Rename `_y_offset` → `y_offset_real`; add `paint_hires()`; add `ScaledCanvas.rebind_innermost()` |
| `src/led_ticker/ticker.py` | Update `_draw_hires_circle` (line 75); update `Ticker._play_widget` (lines 418–429); update `_run_gif` (line 948) |
| `src/led_ticker/text_render.py` | Update two `getattr(canvas, "_y_offset", 0)` sites (lines 51, 141) |
| `src/led_ticker/pixel_emoji.py` | Update `_draw_hires_emoji` line 3047 (rename); collapse four `isinstance` sites (lines 2742, 2867, 2977, 3024) to `safe_scale(canvas) > 1` |
| `tests/test_scaled_canvas.py` | New tests for each task |

---

### Task 1: Rename `_y_offset` → `y_offset_real`

The field is already read cross-module in `ticker.py` (line 75) and `pixel_emoji.py` (line 3047) via direct attribute access. Keeping the single-underscore name implies "implementation detail" but external read access is already established. Renaming to `y_offset_real` declares the leakage honestly and removes the inconsistency. There is no on_setattr frozen guard on this field — it is already set by `__attrs_post_init__` normally via attrs.

**Files:**
- Modify: `src/led_ticker/scaled_canvas.py:36` (field), `:27` (docstring), `:64` (`__attrs_post_init__`), `:94` (`SetPixel`)
- Modify: `src/led_ticker/ticker.py:75` (`_draw_hires_circle`)
- Modify: `src/led_ticker/text_render.py:51`, `:141` (two `getattr` sites)
- Modify: `src/led_ticker/pixel_emoji.py:3047` (`_draw_hires_emoji`)
- Test: `tests/test_scaled_canvas.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_scaled_canvas.py`:

```python
def test_y_offset_real_attribute_name_at_scale_2():
    real = _make_real_canvas(real_w=256, real_h=64)
    sc = ScaledCanvas(real, scale=2)
    # y_offset_real = (64 - 16*2) // 2 = 16
    assert sc.y_offset_real == 16


def test_y_offset_real_attribute_name_at_scale_4_no_letterbox():
    real = _make_real_canvas(real_w=256, real_h=64)
    sc = ScaledCanvas(real, scale=4)
    # y_offset_real = (64 - 16*4) // 2 = 0
    assert sc.y_offset_real == 0


def test_no_private_y_offset():
    real = _make_real_canvas(real_w=256, real_h=64)
    sc = ScaledCanvas(real, scale=4)
    assert not hasattr(sc, "_y_offset"), "_y_offset must be gone after rename"
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /path/to/repo
PYTHONPATH=tests/stubs pytest tests/test_scaled_canvas.py::test_y_offset_real_attribute_name_at_scale_2 tests/test_scaled_canvas.py::test_y_offset_real_attribute_name_at_scale_4_no_letterbox tests/test_scaled_canvas.py::test_no_private_y_offset -v
```

Expected: FAIL — `AttributeError: 'ScaledCanvas' object has no attribute 'y_offset_real'` and `test_no_private_y_offset` passes (wrong direction).

- [ ] **Step 3: Rename in `scaled_canvas.py`**

Change line 27 docstring from `we cache `_y_offset` once at` → `we cache `y_offset_real` once at`.

Change line 36:
```python
# Before
_y_offset: int = attrs.field(init=False, default=0)

# After
y_offset_real: int = attrs.field(init=False, default=0)
```

Change line 64:
```python
# Before
self._y_offset = (self.real.height - self.content_height * self.scale) // 2

# After
self.y_offset_real = (self.real.height - self.content_height * self.scale) // 2
```

Change line 94:
```python
# Before
ry = y * s + self._y_offset

# After
ry = y * s + self.y_offset_real
```

- [ ] **Step 4: Rename in the three caller files**

`ticker.py` line 75:
```python
# Before
cy_physical = canvas._y_offset + (canvas.height * scale) // 2

# After
cy_physical = canvas.y_offset_real + (canvas.height * scale) // 2
```

`text_render.py` line 51:
```python
# Before
y_offset = getattr(canvas, "_y_offset", 0)

# After
y_offset = getattr(canvas, "y_offset_real", 0)
```

`text_render.py` line 141:
```python
# Before
y_offset = getattr(canvas, "_y_offset", 0)

# After
y_offset = getattr(canvas, "y_offset_real", 0)
```

`pixel_emoji.py` line 3047:
```python
# Before
real_y_offset = canvas._y_offset

# After
real_y_offset = canvas.y_offset_real
```

- [ ] **Step 5: Run full test suite**

```bash
PYTHONPATH=tests/stubs pytest tests/test_scaled_canvas.py tests/test_text_render.py tests/test_pixel_emoji.py -v
```

Expected: all pass (including the three new tests).

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/scaled_canvas.py src/led_ticker/ticker.py src/led_ticker/text_render.py src/led_ticker/pixel_emoji.py tests/test_scaled_canvas.py
git commit -m "refactor: rename ScaledCanvas._y_offset → y_offset_real

The field was already read cross-module in ticker.py and pixel_emoji.py
via direct attribute access. Renaming declares that access pattern
honestly and removes the false 'implementation detail' signal from a
public-facing attribute name."
```

---

### Task 2: Add `paint_hires()` free function and update callers

`_draw_hires_circle` (ticker.py) and `_draw_hires_emoji` (pixel_emoji.py) both open with the same three-line idiom: unwrap the real canvas, read `canvas.scale`, read `canvas.y_offset_real`. `paint_hires(canvas, callback)` encodes that pattern once. After this task, adding a new hi-res paint site requires only the callback, not the unwrap pattern.

`paint_hires` lives in `scaled_canvas.py` alongside `unwrap_to_real` — both are canvas-navigation helpers.

**Files:**
- Modify: `src/led_ticker/scaled_canvas.py` — add `Callable` import, add `paint_hires()`
- Modify: `src/led_ticker/ticker.py` — import `paint_hires`; rewrite `_draw_hires_circle` body
- Modify: `src/led_ticker/pixel_emoji.py` — import `paint_hires`; rewrite `_draw_hires_emoji` body
- Test: `tests/test_scaled_canvas.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_scaled_canvas.py`:

```python
from led_ticker.scaled_canvas import ScaledCanvas, paint_hires


def test_paint_hires_scaled_canvas_no_letterbox():
    real = _make_real_canvas(real_w=256, real_h=64)
    sc = ScaledCanvas(real, scale=4)
    calls: list[tuple] = []
    paint_hires(sc, lambda r, s, y: calls.append((r, s, y)))
    assert calls == [(real, 4, 0)]


def test_paint_hires_scaled_canvas_with_letterbox():
    real = _make_real_canvas(real_w=256, real_h=64)
    sc = ScaledCanvas(real, scale=2)  # y_offset_real = (64 - 32) // 2 = 16
    calls: list[tuple] = []
    paint_hires(sc, lambda r, s, y: calls.append((r, s, y)))
    assert calls == [(real, 2, 16)]


def test_paint_hires_plain_canvas():
    real = _make_real_canvas(real_w=256, real_h=64)
    calls: list[tuple] = []
    paint_hires(real, lambda r, s, y: calls.append((r, s, y)))
    assert calls == [(real, 1, 0)]
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
PYTHONPATH=tests/stubs pytest tests/test_scaled_canvas.py::test_paint_hires_scaled_canvas_no_letterbox tests/test_scaled_canvas.py::test_paint_hires_scaled_canvas_with_letterbox tests/test_scaled_canvas.py::test_paint_hires_plain_canvas -v
```

Expected: FAIL — `ImportError: cannot import name 'paint_hires' from 'led_ticker.scaled_canvas'`.

- [ ] **Step 3: Add `paint_hires()` to `scaled_canvas.py`**

Add `Callable` to the typing import at the top of `scaled_canvas.py`:
```python
# Before
from typing import Any

# After
from collections.abc import Callable
from typing import Any
```

Add the function after `unwrap_to_real()` (after line 142):
```python
def paint_hires(
    canvas: Any, callback: Callable[[Any, int, int], None]
) -> None:
    """Call `callback(real_canvas, scale, y_offset_real)` with unwrapped coords.

    For a ScaledCanvas, unwraps to the innermost real canvas and forwards
    `canvas.scale` and `canvas.y_offset_real`. For any other canvas, passes
    through with scale=1 and y_offset=0. Use this instead of the three-line
    unwrap idiom whenever a paint site needs to write at physical resolution.
    """
    if isinstance(canvas, ScaledCanvas):
        callback(unwrap_to_real(canvas), canvas.scale, canvas.y_offset_real)
    else:
        callback(canvas, 1, 0)
```

- [ ] **Step 4: Run the three new tests**

```bash
PYTHONPATH=tests/stubs pytest tests/test_scaled_canvas.py::test_paint_hires_scaled_canvas_no_letterbox tests/test_scaled_canvas.py::test_paint_hires_scaled_canvas_with_letterbox tests/test_scaled_canvas.py::test_paint_hires_plain_canvas -v
```

Expected: PASS.

- [ ] **Step 5: Update `_draw_hires_circle` in `ticker.py`**

Add `paint_hires` to the import:
```python
# Before
from led_ticker.scaled_canvas import ScaledCanvas, unwrap_to_real

# After
from led_ticker.scaled_canvas import ScaledCanvas, paint_hires, unwrap_to_real
```

Replace the body of `_draw_hires_circle` (lines 53–86). Keep the signature and docstring unchanged:
```python
def _draw_hires_circle(
    canvas: ScaledCanvas, cursor_pos: int, color: ColorTuple
) -> tuple[ScaledCanvas, int]:
    """Paint a filled disk at physical resolution centered in the
    canvas's content band. Will be called by draw methods on ScaledCanvas
    (added in upcoming tasks); plain Canvas paths go through TickerMessage's
    BDF rendering.

    Logical footprint is 10 px wide (1 left pad + 8 disk + 1 right pad)
    matching today's " • " BDF advance so _scroll_side_by_side layout
    stays stable.
    """
    if isinstance(color, tuple):
        r, g, b = color
    else:
        r, g, b = color.red, color.green, color.blue

    def _paint(real: Any, scale: int, y_offset_real: int) -> None:
        radius_physical = _CIRCLE_LOGICAL_RADIUS * scale
        offsets = _build_circle_offsets(radius_physical)
        cx_physical = (cursor_pos + _CIRCLE_LOGICAL_PAD) * scale + radius_physical
        cy_physical = y_offset_real + (canvas.height * scale) // 2
        set_px = real.SetPixel
        for dx, dy in offsets:
            set_px(cx_physical + dx, cy_physical + dy, r, g, b)

    paint_hires(canvas, _paint)
    return canvas, cursor_pos + _CIRCLE_LOGICAL_ADVANCE
```

- [ ] **Step 6: Update `_draw_hires_emoji` in `pixel_emoji.py`**

Add `paint_hires` to the import:
```python
# Before
from led_ticker.scaled_canvas import ScaledCanvas

# After
from led_ticker.scaled_canvas import ScaledCanvas, paint_hires
```

Replace the body of `_draw_hires_emoji` (keep signature and docstring):
```python
def _draw_hires_emoji(
    canvas: ScaledCanvas,
    hires: HiResEmoji,
    ix_logical: int,
    iy_logical: int,
) -> None:
    """Paint a hi-res sprite directly to the ScaledCanvas's real canvas.

    The wrapper's `SetPixel` would expand each pixel to a `scale × scale`
    block, defeating the purpose of the hi-res sprite. Calling
    `real.SetPixel` writes individual physical LEDs.
    """
    def _paint(real: Any, scale: int, y_offset_real: int) -> None:
        real_x_anchor = ix_logical * scale
        real_y_anchor = iy_logical * scale + y_offset_real
        real_w = real.width
        real_h = real.height
        for px, py, r, g, b in hires.pixels:
            rx = real_x_anchor + px
            ry = real_y_anchor + py
            if 0 <= rx < real_w and 0 <= ry < real_h:
                real.SetPixel(rx, ry, r, g, b)

    paint_hires(canvas, _paint)
```

- [ ] **Step 7: Run full test suite**

```bash
PYTHONPATH=tests/stubs pytest tests/test_scaled_canvas.py tests/test_pixel_emoji.py tests/test_ticker.py -v
```

Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add src/led_ticker/scaled_canvas.py src/led_ticker/ticker.py src/led_ticker/pixel_emoji.py tests/test_scaled_canvas.py
git commit -m "refactor: add paint_hires() helper; collapse unwrap idiom in two callers

Encodes the three-line 'unwrap real canvas, read scale, read y_offset_real'
pattern used by _draw_hires_circle and _draw_hires_emoji into a single
paint_hires(canvas, callback) call. New hi-res paint sites only need the
callback; the navigation logic lives once in scaled_canvas.py."
```

---

### Task 3: Replace `use_hires = isinstance(canvas, ScaledCanvas)` with `safe_scale(canvas) > 1`

Four sites in `pixel_emoji.py` gate hi-res rendering on `isinstance(canvas, ScaledCanvas)`. `safe_scale()` already exists in `drawing.py` as the canonical "read canvas.scale defensively" helper — it returns the int `scale` attribute when valid, falls back to 1 otherwise. Replacing `isinstance` with `safe_scale(canvas) > 1` makes the condition more truthful (it fires on any canvas whose scale attribute says ≥ 2, not just those that happen to be `ScaledCanvas` instances), eliminates a cross-module type import at each site, and matches the pattern used elsewhere in the codebase (`two_row.py:428`, `_image_base.py:1237`).

The same substitution applies to `ticker.py:948` where `wrapper_scale = canvas.scale if isinstance(canvas, ScaledCanvas) else 1` becomes `wrapper_scale = safe_scale(canvas)`.

**Files:**
- Modify: `src/led_ticker/pixel_emoji.py` — add `safe_scale` import; replace 4 `isinstance` sites (lines 2742, 2867, 2977, 3024)
- Modify: `src/led_ticker/ticker.py` — replace the `isinstance` ternary at line 948
- Test: `tests/test_scaled_canvas.py`

- [ ] **Step 1: Write a contract test**

Add to `tests/test_scaled_canvas.py`:

```python
def test_safe_scale_matches_isinstance_for_scaled_canvas():
    from led_ticker.drawing import safe_scale
    real = _make_real_canvas(real_w=256, real_h=64)
    sc = ScaledCanvas(real, scale=4)
    assert safe_scale(sc) > 1
    assert safe_scale(real) == 1
```

- [ ] **Step 2: Run test to confirm it passes (it exercises `safe_scale`)**

```bash
PYTHONPATH=tests/stubs pytest tests/test_scaled_canvas.py::test_safe_scale_matches_isinstance_for_scaled_canvas -v
```

Expected: PASS — this validates that `safe_scale` returns useful values before we depend on it at the substituted sites.

- [ ] **Step 3: Update `pixel_emoji.py`**

Add `safe_scale` import:
```python
# Before
from led_ticker.scaled_canvas import ScaledCanvas, paint_hires

# After
from led_ticker.drawing import safe_scale
from led_ticker.scaled_canvas import ScaledCanvas, paint_hires
```

Replace the four `isinstance` sites:

Line 2742 (inside `measure_width`):
```python
# Before
use_hires = isinstance(canvas, ScaledCanvas)

# After
use_hires = safe_scale(canvas) > 1
```

Line 2867 (inside the draw-with-emoji loop):
```python
# Before
use_hires = isinstance(canvas, ScaledCanvas)

# After
use_hires = safe_scale(canvas) > 1
```

Line 2977 (inside `draw_emoji_single`):
```python
# Before
use_hires = isinstance(canvas, ScaledCanvas)

# After
use_hires = safe_scale(canvas) > 1
```

Line 3024 (inside `measure_emoji_single`):
```python
# Before
use_hires = isinstance(canvas, ScaledCanvas)

# After
use_hires = safe_scale(canvas) > 1
```

- [ ] **Step 4: Update `ticker.py`**

Line 948 (inside `_run_gif`):
```python
# Before
wrapper_scale = canvas.scale if isinstance(canvas, ScaledCanvas) else 1

# After
wrapper_scale = safe_scale(canvas)
```

Also add `safe_scale` to the `drawing` import in `ticker.py`:
```python
# Before
from led_ticker.drawing import get_widget_padding

# After
from led_ticker.drawing import get_widget_padding, safe_scale
```

And remove `ScaledCanvas` from the `scaled_canvas` import in `ticker.py` if it's no longer needed at that site (check all remaining `isinstance(canvas, ScaledCanvas)` uses — there are still some at lines 113, 142, 148–162, and in `_play_widget` at 418–420 which Task 4 will clean up, so keep the import).

- [ ] **Step 5: Run full test suite**

```bash
PYTHONPATH=tests/stubs pytest tests/test_pixel_emoji.py tests/test_ticker.py tests/test_ticker_display.py -v
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/pixel_emoji.py src/led_ticker/ticker.py tests/test_scaled_canvas.py
git commit -m "refactor: replace isinstance(canvas, ScaledCanvas) with safe_scale() > 1

Four use_hires guards in pixel_emoji.py and one wrapper_scale ternary in
ticker._run_gif all pattern-matched on ScaledCanvas type. safe_scale()
already exists as the canonical scale-reading helper and produces the
same boolean without cross-module type imports at each site."
```

---

### Task 4: Add `ScaledCanvas.rebind_innermost()` and update `Ticker._play_widget`

`Ticker._play_widget` (lines 418–429) walks nested `ScaledCanvas` wrappers via a `while isinstance` loop to rebind the innermost `.real` after `widget.play()` returns a new back-buffer canvas. This loop is the same shape as `unwrap_to_real()` — it belongs on the class, not scattered in a caller. Moving it onto `ScaledCanvas.rebind_innermost(new_real)` makes `_play_widget` readable at a glance and gives the pattern a test surface of its own.

**Files:**
- Modify: `src/led_ticker/scaled_canvas.py` — add `ScaledCanvas.rebind_innermost()`
- Modify: `src/led_ticker/ticker.py` — simplify `Ticker._play_widget` body (lines 418–429)
- Test: `tests/test_scaled_canvas.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_scaled_canvas.py`:

```python
def test_rebind_innermost_single_wrapper():
    real_a = _make_real_canvas(real_w=256, real_h=64)
    real_b = _make_real_canvas(real_w=256, real_h=64)
    sc = ScaledCanvas(real_a, scale=4)
    sc.rebind_innermost(real_b)
    assert sc.real is real_b


def test_rebind_innermost_nested_wrappers():
    real_a = _make_real_canvas(real_w=256, real_h=64)
    real_b = _make_real_canvas(real_w=256, real_h=64)
    inner = ScaledCanvas(real_a, scale=4)
    # Outer wraps inner — __attrs_post_init__ peels to real_a (64px) for validation.
    outer = ScaledCanvas(inner, scale=4, content_height=16)
    outer.rebind_innermost(real_b)
    assert inner.real is real_b  # deepest wrapper updated
    assert outer.real is inner   # outer unchanged


def test_rebind_innermost_does_not_change_outer_real_on_nesting():
    real_a = _make_real_canvas(real_w=256, real_h=64)
    real_b = _make_real_canvas(real_w=256, real_h=64)
    inner = ScaledCanvas(real_a, scale=4)
    outer = ScaledCanvas(inner, scale=4, content_height=16)
    outer.rebind_innermost(real_b)
    assert outer.real is inner  # outer still points at inner
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
PYTHONPATH=tests/stubs pytest tests/test_scaled_canvas.py::test_rebind_innermost_single_wrapper tests/test_scaled_canvas.py::test_rebind_innermost_nested_wrappers tests/test_scaled_canvas.py::test_rebind_innermost_does_not_change_outer_real_on_nesting -v
```

Expected: FAIL — `AttributeError: 'ScaledCanvas' object has no attribute 'rebind_innermost'`.

- [ ] **Step 3: Add `rebind_innermost()` to `ScaledCanvas`**

Add as a method on `ScaledCanvas` after `draw_bdf_text()`:
```python
def rebind_innermost(self, new_real: Any) -> None:
    """Rewire the innermost `.real` to `new_real`, leaving outer wrappers intact.

    Called after `widget.play()` returns a new back-buffer canvas so
    subsequent draws through this wrapper use the fresh canvas. Walks
    nested ScaledCanvas wrappers — cross-scale dissolve transitions wrap
    a wrapper at transition time; we must reach the bottom of the chain.
    """
    innermost = self
    while isinstance(innermost.real, ScaledCanvas):
        innermost = innermost.real
    innermost.real = new_real
```

- [ ] **Step 4: Run the three new tests**

```bash
PYTHONPATH=tests/stubs pytest tests/test_scaled_canvas.py::test_rebind_innermost_single_wrapper tests/test_scaled_canvas.py::test_rebind_innermost_nested_wrappers tests/test_scaled_canvas.py::test_rebind_innermost_does_not_change_outer_real_on_nesting -v
```

Expected: PASS.

- [ ] **Step 5: Update `Ticker._play_widget`**

Replace lines 418–429 in `ticker.py`. The `isinstance` check at line 418 stays — it's a dispatch, not a scale probe. The inner `while isinstance` loop at lines 419–421 and the `innermost.real = new_real` at line 429 collapse to one call:

```python
async def _play_widget(
    self, canvas: Any, widget: Any, *, section_hold_time: float = 3.0
) -> Any:
    """Hand the canvas off to a widget's `play()` method.

    Used by widgets that drive their own animation loop (e.g. GifPlayer).
    Unwraps any ScaledCanvas wrappers so the widget paints at native
    physical resolution; the wrapper is re-anchored to the new
    back-buffer canvas afterward so subsequent draws stay scaled.

    ``section_hold_time`` is forwarded to ``widget.play()`` as ``hold_time``
    so gif widgets with ``gif_loops = 0`` can compute how many loops fit in
    the section's duration.
    """
    gif_loops = getattr(widget, "gif_loops", None)
    loops = (
        gif_loops if gif_loops is not None else (getattr(widget, "loops", 1) or 1)
    )
    if isinstance(canvas, ScaledCanvas):
        Ticker._set_logical_scale(widget, canvas.scale)
        new_real = await widget.play(
            unwrap_to_real(canvas),
            self.frame,
            loop_count=loops,
            hold_time=section_hold_time,
        )
        canvas.rebind_innermost(new_real)
        return canvas
    Ticker._set_logical_scale(widget, 1)
    return await widget.play(
        canvas, self.frame, loop_count=loops, hold_time=section_hold_time
    )
```

- [ ] **Step 6: Run full test suite**

```bash
PYTHONPATH=tests/stubs pytest tests/ -v
```

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add src/led_ticker/scaled_canvas.py src/led_ticker/ticker.py tests/test_scaled_canvas.py
git commit -m "refactor: add ScaledCanvas.rebind_innermost(); simplify Ticker._play_widget

The nested while-isinstance loop in _play_widget walked ScaledCanvas
wrappers to rebind the innermost .real after widget.play() returns.
Moved onto the class as rebind_innermost(new_real) so the pattern is
tested in isolation and the call site reads as one line."
```

---

## Self-Review

**Spec coverage check:**

- S4 rename `_y_offset` → `y_offset_real` ✅ Task 1
- S4 `paint_hires()` helper ✅ Task 2
- S4 collapse `isinstance` scale-detection sites ✅ Task 3 (4 in `pixel_emoji.py`, 1 in `ticker.py`)
- S4 rebind loop onto `ScaledCanvas` ✅ Task 4
- Docstring at line 27 mentions old name ✅ Task 1 Step 3

**Remaining `isinstance(canvas, ScaledCanvas)` sites not touched:**

The following sites are **not** changed by this plan — they are dispatch or construction sites, not scale-detection sites:
- `ticker.py:113` — `_CircleBufferMsg.draw` dispatches to `_draw_hires_circle` vs BDF; dispatch is correct
- `ticker.py:142` — `_swap()` reads `canvas.real`; this requires type identity, not scale
- `ticker.py:148–162` — `_maybe_wrap()` constructs a `ScaledCanvas`; construction site
- `ticker.py:418` — `_play_widget` dispatch; kept as explicit type check, now cleaner after rebind removal
- `text_render.py:26` — `draw_text` dispatches to `canvas.draw_bdf_text` which requires the method to exist; type identity is correct here
- `scaled_canvas.py:51, 140` — internal to `ScaledCanvas.__attrs_post_init__` and `unwrap_to_real`; correct
- `scaled_canvas.py` in `rebind_innermost` (Task 4) — internal; correct

**Placeholder scan:** None found.

**Type consistency:** `paint_hires` callback is `Callable[[Any, int, int], None]` — the three `Any, int, int` params are `real_canvas, scale, y_offset_real` used consistently in both `_draw_hires_circle` (Task 2 Step 5) and `_draw_hires_emoji` (Task 2 Step 6).
