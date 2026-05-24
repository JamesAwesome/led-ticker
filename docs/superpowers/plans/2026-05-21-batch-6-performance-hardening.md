# Batch 6: Performance Hardening

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Branch safety:** Before doing ANY work, run `git branch --show-current`. If it prints `main`, stop immediately and ask for a worktree.

**Goal:** Eliminate four categories of unnecessary repeated computation: the `Scroll` transition's private cross-module import (M4), per-draw `compute_baseline` calls that are frame-invariant (M18), per-frame perimeter list reconstruction (S16 partial), and per-character `colorsys.hsv_to_rgb + graphics.Color()` allocations in every rainbow/cycle color tick (Medium #2).

**Architecture:** Four independent tasks, each isolated to one or two files. Task 1 is a structural refactor (no behavior change): inline `_draw_scroll_frame` logic into `Scroll.frame_at` so the transition doesn't import a private engine symbol. Tasks 2–3 add lazy-caching of frame-invariant values via existing attrs patterns and `@functools.cache`. Task 4 creates a new `color_lut.py` module with a lazily-built 360-entry `graphics.Color` table, then rewires `Rainbow`, `ColorCycle`, `RainbowChaseBorder`, `ColorCycleBorder`, and `Random` to use it — eliminating `colorsys.hsv_to_rgb` from every hot render loop.

**Tech Stack:** Python standard library (`functools`, `colorsys`, `inspect`), `attrs`, `pytest-asyncio` (`asyncio_mode = "auto"`)

**Run tests with:** `PYTHONPATH=tests/stubs uv run pytest -x -q`

**Baseline:** 1833 tests passing, 1 skipped.

---

## File Map

| File | Change |
|---|---|
| `src/led_ticker/color_lut.py` | **Create** — lazily-built 360-entry hue→Color LUT, `hue_color(hue_degrees)` public function |
| `src/led_ticker/transitions/effects.py` | Inline `_draw_scroll_frame` logic into `Scroll.frame_at`; remove deferred `ticker` private import |
| `src/led_ticker/widgets/message.py` | Add `_baseline_y` lazy cache to `TickerMessage` and `TickerCountdown` |
| `src/led_ticker/borders.py` | Add `@functools.cache` to `_perimeter_pixels`; import and use `hue_color` in `RainbowChaseBorder.paint` and `ColorCycleBorder.paint`; remove `import colorsys` |
| `src/led_ticker/color_providers.py` | Import and use `hue_color` in `Rainbow.color_for`, `ColorCycle.color_for`, `Random.__init__`; remove `import colorsys` |
| `tests/test_transitions.py` | Add `TestScrollInlinedDrawing` class |
| `tests/test_widgets/test_message.py` | Add `TestBaselineCache` class |
| `tests/test_borders.py` | Add `test_perimeter_pixels_cached` to `TestPerimeterGeometry`; add `TestColorLUTBorders` class |
| `tests/test_color_providers.py` | Add `TestColorLUT` class |

---

## Task 1: M4 — Inline `_draw_scroll_frame` into `Scroll.frame_at`

The `Scroll` transition (`effects.py`) imports `_draw_scroll_frame` from `ticker.py` inside `frame_at` — a private engine symbol that extension authors should never need. Fix: inline the draw logic directly. The public constants (`SCROLL_GAP`, `scroll_separator_width`) remain in `ticker.py` and may still be imported.

**Files:**
- Modify: `src/led_ticker/transitions/effects.py` (lines 173–203)
- Test: `tests/test_transitions.py` (add class at end of file)

- [ ] **Step 1: Write the failing test**

Add after the existing `TestScroll` class in `tests/test_transitions.py`:

```python
class TestScrollInlinedDrawing:
    def test_frame_at_does_not_import_draw_scroll_frame(self):
        """Scroll.frame_at must not import the private _draw_scroll_frame
        from ticker. Extension authors must not depend on engine privates.
        Inline the logic into frame_at instead."""
        import inspect

        source = inspect.getsource(Scroll.frame_at)
        assert "_draw_scroll_frame" not in source, (
            "Scroll.frame_at still imports _draw_scroll_frame from ticker — "
            "inline the draw logic into frame_at directly"
        )

    def test_blackout_region_cleared_at_mid_scroll(self, canvas, make_widget):
        """At mid-scroll the region between outgoing tail and the right
        edge of the canvas is blacked out so outgoing text doesn't bleed
        through the gap region."""
        scroll = Scroll()
        outgoing = make_widget(40)
        incoming = make_widget(40)
        # At t=0.5, sep_w=14: scroll_offset = int(0.5 * 174) = 87
        # clear_start = max(0, 160 - 87) = 73 → should black out x in [73, 159]
        scroll.frame_at(0.5, canvas, outgoing, incoming)
        black_calls = [
            c for c in canvas.SetPixel.call_args_list if c.args[2:] == (0, 0, 0)
        ]
        assert len(black_calls) > 0, "No blackout pixels were set during mid-scroll"
        # All blacked-out x coords must be in [73, 159]
        x_values = {c.args[0] for c in black_calls}
        assert min(x_values) == 73
        assert max(x_values) == 159

    def test_bullet_painted_at_mid_scroll(self, canvas, make_widget):
        """Bullet (2×2 white dot) is painted during scroll."""
        scroll = Scroll()
        outgoing = make_widget(40)
        incoming = make_widget(40)
        scroll.frame_at(0.5, canvas, outgoing, incoming)
        white_calls = [
            c for c in canvas.SetPixel.call_args_list if c.args[2:] == (255, 255, 255)
        ]
        assert len(white_calls) >= 1, "No bullet pixels were painted"
```

- [ ] **Step 2: Run the first test to verify it fails**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_transitions.py::TestScrollInlinedDrawing::test_frame_at_does_not_import_draw_scroll_frame -v`

Expected: FAIL — `AssertionError: Scroll.frame_at still imports _draw_scroll_frame from ticker`

(The other two tests already pass since the behavior is unchanged — they're coverage additions.)

- [ ] **Step 3: Inline the draw logic into `Scroll.frame_at`**

In `src/led_ticker/transitions/effects.py`, replace the `Scroll.frame_at` method (lines 173–203) with:

```python
    def frame_at(
        self, t: float, canvas: Canvas, outgoing: Any, incoming: Any, **kwargs: Any
    ) -> Canvas:
        w = canvas.width
        h = getattr(canvas, "height", 16)
        outgoing_scroll_pos: int = kwargs.get("outgoing_scroll_pos", 0)

        if t >= 1.0:
            incoming.draw(canvas, cursor_pos=0)
            return canvas

        total_travel = w + self._sep_w
        scroll_offset = int(t * total_travel)

        outgoing_pos = outgoing_scroll_pos - scroll_offset
        clear_start = max(0, w - scroll_offset)
        bullet_x = w + self._gap - scroll_offset
        incoming_pos = w + self._sep_w - scroll_offset

        outgoing.draw(canvas, cursor_pos=outgoing_pos)

        # Black out the tail region so outgoing text doesn't bleed
        # into the gap between outgoing and the bullet.
        if 0 <= clear_start < w:
            for y in range(h):
                for x in range(clear_start, w):
                    canvas.SetPixel(x, y, 0, 0, 0)

        # Bullet: 2×2 white dot centered vertically.
        y_center = h // 2
        for dy in range(-1, 1):
            for dx in range(2):
                px = bullet_x + dx
                py = y_center + dy
                if 0 <= px < w and 0 <= py < h:
                    canvas.SetPixel(px, py, 255, 255, 255)

        if incoming_pos < w:
            incoming.draw(canvas, cursor_pos=incoming_pos)

        return canvas
```

The `__init__` stays the same — it only imports public symbols (`SCROLL_GAP`, `scroll_separator_width`) from ticker:

```python
    def __init__(self, **kwargs: Any) -> None:
        from led_ticker.ticker import SCROLL_GAP, scroll_separator_width

        self._sep_w: int = scroll_separator_width()
        self._gap: int = SCROLL_GAP
```

- [ ] **Step 4: Run all Scroll tests**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_transitions.py::TestScroll tests/test_transitions.py::TestScrollInlinedDrawing -v`

Expected: all PASS (7 existing + 3 new = 10 total)

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/transitions/effects.py tests/test_transitions.py
git commit -m "refactor: inline _draw_scroll_frame into Scroll.frame_at (M4)"
```

---

## Task 2: M18 — Cache `compute_baseline` on `TickerMessage` and `TickerCountdown`

`TickerMessage.draw()` and `TickerCountdown.draw()` each call `compute_baseline(self.font, canvas, valign="center")` on every draw call. The result depends only on `font` metrics and `canvas.height + canvas.scale` — both invariant for the widget's lifetime within a section. Add a `_baseline_y: int` lazy-init field (same pattern as the existing `_content_width` cache) and compute once on first draw.

**Files:**
- Modify: `src/led_ticker/widgets/message.py`
- Test: `tests/test_widgets/test_message.py` (add class at end of file)

- [ ] **Step 1: Write the failing tests**

Add at the end of `tests/test_widgets/test_message.py`:

```python
class TestBaselineCache:
    """compute_baseline is frame-invariant — result depends only on the
    font metrics and canvas dimensions, both fixed within a section.
    Cache it after the first draw to avoid recomputing per tick."""

    def test_ticker_message_baseline_computed_once(self, canvas, monkeypatch):
        from led_ticker import drawing
        from led_ticker.widgets.message import TickerMessage

        calls: list = []
        original = drawing.compute_baseline

        def _track(*args, **kwargs):
            calls.append(args)
            return original(*args, **kwargs)

        monkeypatch.setattr(drawing, "compute_baseline", _track)

        widget = TickerMessage(message="Hello")
        widget.draw(canvas)
        widget.draw(canvas)
        widget.draw(canvas)

        assert len(calls) == 1, (
            f"compute_baseline called {len(calls)} times — should be cached after first draw"
        )

    def test_ticker_countdown_baseline_computed_once(self, canvas, monkeypatch):
        from datetime import date

        from led_ticker import drawing
        from led_ticker.widgets.message import TickerCountdown

        calls: list = []
        original = drawing.compute_baseline

        def _track(*args, **kwargs):
            calls.append(args)
            return original(*args, **kwargs)

        monkeypatch.setattr(drawing, "compute_baseline", _track)

        widget = TickerCountdown(message="Days", countdown_date=date(2027, 1, 1))
        widget.draw(canvas)
        widget.draw(canvas)
        widget.draw(canvas)

        assert len(calls) == 1, (
            f"compute_baseline called {len(calls)} times — should be cached after first draw"
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_widgets/test_message.py::TestBaselineCache -v`

Expected: FAIL — `AssertionError: compute_baseline called 3 times — should be cached after first draw`

- [ ] **Step 3: Add `_baseline_y` cache to `TickerMessage`**

In `src/led_ticker/widgets/message.py`, add `_baseline_y` to `TickerMessage`'s attrs fields (after `_has_emoji`):

```python
    _content_width: int = attrs.field(init=False, default=-1)
    _has_emoji: bool = attrs.field(init=False, default=False)
    _baseline_y: int = attrs.field(init=False, default=-1)
```

Then in `TickerMessage.draw()`, replace the single line `baseline_y = compute_baseline(self.font, canvas, valign="center")` (line 113) with:

```python
        if self._baseline_y < 0:
            self._baseline_y = compute_baseline(self.font, canvas, valign="center")
        baseline_y = self._baseline_y
```

- [ ] **Step 4: Add `_baseline_y` cache to `TickerCountdown`**

In `TickerCountdown`, add `_baseline_y` field (after `border`):

```python
    border: Any | None = attrs.field(default=None, kw_only=True)
    _baseline_y: int = attrs.field(init=False, default=-1)
```

Replace `baseline_y = compute_baseline(self.font, canvas, valign="center")` (line 244) with:

```python
        if self._baseline_y < 0:
            self._baseline_y = compute_baseline(self.font, canvas, valign="center")
        baseline_y = self._baseline_y
```

- [ ] **Step 5: Run all message tests**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_widgets/test_message.py -v`

Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/widgets/message.py tests/test_widgets/test_message.py
git commit -m "perf: cache compute_baseline on TickerMessage and TickerCountdown (M18)"
```

---

## Task 3: `@functools.cache` on `_perimeter_pixels`

`RainbowChaseBorder.paint()` and `ColorCycleBorder.paint()` call `_perimeter_pixels(real.width, real.height, self.thickness)` on every frame. On bigsign (256×64, thickness=1) this builds a 640-element list of `(x, y)` tuples 20 times per second. The function is pure: same `(width, height, thickness)` always returns the same sequence. Add `@functools.cache` to memoize it.

**Callers only iterate — never mutate — the returned list, so returning the same object is safe.**

**Files:**
- Modify: `src/led_ticker/borders.py`
- Test: `tests/test_borders.py` (add test to `TestPerimeterGeometry`)

- [ ] **Step 1: Write the failing test**

Add inside `class TestPerimeterGeometry` in `tests/test_borders.py`, after the last existing test:

```python
    def test_same_args_return_cached_object(self):
        """_perimeter_pixels is pure — repeated calls with the same
        args must return the same list object, not a freshly-built one.
        Without caching, each call allocates a new list every frame."""
        a = _perimeter_pixels(160, 16, thickness=1)
        b = _perimeter_pixels(160, 16, thickness=1)
        assert a is b, (
            "_perimeter_pixels should be @functools.cache'd — same args must "
            "return the same list object"
        )
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_borders.py::TestPerimeterGeometry::test_same_args_return_cached_object -v`

Expected: FAIL — `AssertionError: _perimeter_pixels should be @functools.cache'd`

- [ ] **Step 3: Add `@functools.cache` to `_perimeter_pixels`**

In `src/led_ticker/borders.py`, add `import functools` to the imports at the top (alphabetically after the existing imports):

```python
from __future__ import annotations

import colorsys
import functools
from typing import Any, Protocol
```

Then add the decorator directly above `def _perimeter_pixels`:

```python
@functools.cache
def _perimeter_pixels(
    width: int,
    height: int,
    thickness: int = 1,
) -> list[tuple[int, int]]:
```

The function body is unchanged.

- [ ] **Step 4: Run all border tests**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_borders.py -v`

Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/borders.py tests/test_borders.py
git commit -m "perf: cache _perimeter_pixels with @functools.cache (S16 partial)"
```

---

## Task 4: Medium #2 — Precomputed 360-entry hue→Color LUT

`Rainbow.color_for`, `ColorCycle.color_for`, `RainbowChaseBorder.paint` (per perimeter pixel), and `ColorCycleBorder.paint` all call `colorsys.hsv_to_rgb(hue, 1.0, 1.0)` then allocate a new `graphics.Color(...)` object on every call. On bigsign at 20 fps, `RainbowChaseBorder` alone does 640 × 20 = 12,800 `colorsys` calls per second. Replace all of them with a lazily-built 360-entry table in a new `color_lut.py` module.

**Precision**: the table has integer-degree (1°) resolution. All callers use integer `speed` and `char_offset`, so the hue index `(frame * speed + idx * char_offset) % 360` is always an integer already. For arc-restricted paths (`from_hue` / `to_hue`), `int(hue_float) % 360` introduces at most 1° truncation — imperceptible for animated sweeps.

**Files:**
- Create: `src/led_ticker/color_lut.py`
- Modify: `src/led_ticker/color_providers.py`
- Modify: `src/led_ticker/borders.py`
- Test: `tests/test_color_providers.py` (add `TestColorLUT` class)
- Test: `tests/test_borders.py` (add `TestColorLUTBorders` class)

### Sub-task 4a: Create `color_lut.py` and test `hue_color`

- [ ] **Step 1: Write the failing tests for `hue_color`**

Add at the end of `tests/test_color_providers.py`:

```python
class TestColorLUT:
    """Precomputed 360-entry hue → Color table.

    hue_color(deg) must return a pre-built Color object — the same object
    for repeated calls with the same integer degree, no colorsys call
    needed after the first build."""

    def test_hue_color_returns_red_at_zero(self):
        from led_ticker.color_lut import hue_color

        c = hue_color(0)
        assert c.red == 255
        assert c.green == 0
        assert c.blue == 0

    def test_hue_color_same_degree_returns_same_object(self):
        """Core LUT contract: same degree → same pre-built object (not a
        new allocation). Identity check — colorsys is only called once."""
        from led_ticker.color_lut import hue_color

        c1 = hue_color(120)
        c2 = hue_color(120)
        assert c1 is c2, (
            "hue_color should return the same object for the same degree — "
            "LUT is not working"
        )

    def test_hue_color_wraps_at_360(self):
        from led_ticker.color_lut import hue_color

        assert hue_color(0) is hue_color(360)
        assert hue_color(0) is hue_color(720)

    def test_hue_color_float_truncates(self):
        """Float degrees truncate to int — 119.9 and 119.0 both hit LUT[119]."""
        from led_ticker.color_lut import hue_color

        assert hue_color(119.9) is hue_color(119.0)

    def test_rainbow_same_args_returns_same_object(self):
        """Rainbow.color_for with the same (frame, char_index) must return
        the cached Color object, not a freshly-allocated one."""
        from led_ticker.color_providers import Rainbow

        r = Rainbow()
        c1 = r.color_for(frame=5, char_index=2, total_chars=10)
        c2 = r.color_for(frame=5, char_index=2, total_chars=10)
        assert c1 is c2, "Rainbow.color_for should use the LUT — same args → same object"

    def test_color_cycle_same_frame_returns_same_object(self):
        from led_ticker.color_providers import ColorCycle

        cc = ColorCycle(speed=5)
        c1 = cc.color_for(frame=10, char_index=0, total_chars=1)
        c2 = cc.color_for(frame=10, char_index=4, total_chars=1)
        # ColorCycle ignores char_index — same frame → same LUT entry
        assert c1 is c2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_color_providers.py::TestColorLUT -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'led_ticker.color_lut'`

### Sub-task 4b: Create `src/led_ticker/color_lut.py`

- [ ] **Step 3: Create the LUT module**

Create `src/led_ticker/color_lut.py`:

```python
"""Precomputed 360-entry full-saturation hue → Color table.

Shared by Rainbow, ColorCycle (color_providers) and RainbowChaseBorder,
ColorCycleBorder (borders) to replace per-call colorsys.hsv_to_rgb +
graphics.Color() allocations in every hot render loop.

The table is built lazily on first use (avoids import-time graphics
initialization). 360 entries at 1° resolution covers all integer-degree
hue arithmetic used by the built-in providers and border effects.
"""

from __future__ import annotations

import colorsys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from led_ticker._types import Color

_HUE_TABLE: list | None = None


def hue_color(hue_degrees: float) -> "Color":
    """Return the precomputed Color for the given hue (0–360).

    Uses integer-degree (1°) precision — `int(hue_degrees) % 360` is the
    table index. Floating-point hues are truncated, not rounded: 119.9°
    and 119.0° both map to LUT[119]. For all built-in callers (Rainbow,
    ColorCycle, RainbowChaseBorder) the index is already an integer, so
    no precision is lost.
    """
    global _HUE_TABLE
    if _HUE_TABLE is None:
        from led_ticker._compat import require_graphics

        graphics = require_graphics()
        table: list = []
        for h in range(360):
            r, g, b = colorsys.hsv_to_rgb(h / 360.0, 1.0, 1.0)
            table.append(graphics.Color(int(r * 255), int(g * 255), int(b * 255)))
        _HUE_TABLE = table  # atomic assignment — no partial-state reads
    return _HUE_TABLE[int(hue_degrees) % 360]
```

- [ ] **Step 4: Run the LUT tests**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_color_providers.py::TestColorLUT -v`

Expected: `test_hue_color_*` tests PASS; `test_rainbow_same_args_returns_same_object` and `test_color_cycle_same_frame_returns_same_object` still FAIL (providers not yet updated).

### Sub-task 4c: Update `color_providers.py`

- [ ] **Step 5: Wire `Rainbow.color_for` to use `hue_color`**

In `src/led_ticker/color_providers.py`, add the `hue_color` import after the existing imports:

```python
from __future__ import annotations

import random
from typing import Protocol

from led_ticker._compat import require_graphics
from led_ticker._types import Color
from led_ticker.color_lut import hue_color
```

(Remove `import colorsys` — it's no longer used after this task.)

Replace `Rainbow.color_for`:

```python
    def color_for(self, frame: int, char_index: int, total_chars: int) -> Color:
        hue_int = (frame * self.speed + char_index * self.char_offset) % 360
        return hue_color(hue_int)
```

Replace `ColorCycle.color_for`:

```python
    def color_for(self, frame: int, char_index: int, total_chars: int) -> Color:
        span = self._span if self._span != 0 else 360.0
        progress = (frame * self.speed) % abs(span)
        if span < 0:
            hue = (self._from_hue - progress) % 360
        else:
            hue = (self._from_hue + progress) % 360
        return hue_color(hue)
```

Replace `Random.__init__`:

```python
    def __init__(self) -> None:
        self._color = hue_color(random.random() * 360)
```

(Also remove `require_graphics` from `Random.__init__` — it's no longer needed there. The module-level `from led_ticker._compat import require_graphics` import can be removed too if `require_graphics` is only used in `Random.__init__`. Check: `require_graphics` is NOT used anywhere else in this file after these changes — remove the import.)

Full updated imports for `color_providers.py`:

```python
from __future__ import annotations

import random
from typing import Protocol

from led_ticker._types import Color
from led_ticker.color_lut import hue_color
```

- [ ] **Step 6: Run color provider tests**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_color_providers.py -v`

Expected: all PASS (existing tests preserved, new LUT tests pass)

### Sub-task 4d: Update `borders.py`

- [ ] **Step 7: Write the border LUT tests**

Add at the end of `tests/test_borders.py`:

```python
class TestColorLUTBorders:
    """RainbowChaseBorder and ColorCycleBorder use the shared LUT instead
    of per-call colorsys.hsv_to_rgb."""

    def test_rainbow_chase_same_position_same_frame_returns_same_pixel(self):
        """Same perimeter position at same frame must produce the same RGB.
        Verifies the LUT is consistent across calls (not a per-call allocation
        that might differ due to float drift)."""
        c1 = _StubCanvas(20, 8)
        c2 = _StubCanvas(20, 8)
        b = RainbowChaseBorder(speed=4, char_offset=6)
        b.paint(c1, frame_count=5)
        b.paint(c2, frame_count=5)
        assert c1.pixels == c2.pixels, "Same frame must produce identical pixels"

    def test_color_cycle_border_same_frame_uniform_color_from_lut(self):
        """ColorCycleBorder paints every perimeter pixel the same hue each
        frame. The LUT entry at that hue must match the expected RGB."""
        import colorsys

        c = _StubCanvas(10, 4)
        # speed=0 is rejected — use speed=1. At frame=0, hue=0 → red.
        ColorCycleBorder(speed=1).paint(c, frame_count=0)
        # hue = (0 * 1) % 360 = 0 → red (255, 0, 0)
        assert all(rgb == (255, 0, 0) for rgb in c.pixels.values()), (
            f"Expected all red at frame=0, got: {set(c.pixels.values())}"
        )
```

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_borders.py::TestColorLUTBorders -v`

Expected: PASS (both tests should pass with current code too, since the RGB formula is identical — these are behavior-preservation tests).

- [ ] **Step 8: Wire `RainbowChaseBorder.paint` to use `hue_color`**

In `src/led_ticker/borders.py`, add `hue_color` import and remove `import colorsys`:

```python
from __future__ import annotations

import functools
from typing import Any, Protocol

from led_ticker._types import Canvas
from led_ticker.color_lut import hue_color
from led_ticker.scaled_canvas import unwrap_to_real
```

Replace `RainbowChaseBorder.paint`:

```python
    def paint(self, canvas: Canvas, frame_count: int) -> None:
        real = unwrap_to_real(canvas)
        arc = self._arc if self._arc != 0 else 360.0
        abs_arc = abs(arc)
        for idx, (x, y) in enumerate(
            _perimeter_pixels(real.width, real.height, self.thickness)
        ):
            phase = (idx * self.char_offset + frame_count * self.speed) % abs_arc
            if arc < 0:
                hue = (self._from_hue - phase) % 360
            else:
                hue = (self._from_hue + phase) % 360
            color = hue_color(hue)
            real.SetPixel(x, y, color.red, color.green, color.blue)
```

Replace `ColorCycleBorder.paint`:

```python
    def paint(self, canvas: Canvas, frame_count: int) -> None:
        span = self._span if self._span != 0 else 360.0
        progress = (frame_count * self.speed) % abs(span)
        if span < 0:
            hue = (self._from_hue - progress) % 360
        else:
            hue = (self._from_hue + progress) % 360
        color = hue_color(hue)
        real = unwrap_to_real(canvas)
        for x, y in _perimeter_pixels(real.width, real.height, self.thickness):
            real.SetPixel(x, y, color.red, color.green, color.blue)
```

- [ ] **Step 9: Run all border tests**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_borders.py -v`

Expected: all PASS

- [ ] **Step 10: Run the full test suite**

Run: `PYTHONPATH=tests/stubs uv run pytest -x -q`

Expected: 1833+ passed, 1 skipped

- [ ] **Step 11: Commit**

```bash
git add src/led_ticker/color_lut.py src/led_ticker/color_providers.py src/led_ticker/borders.py tests/test_color_providers.py tests/test_borders.py
git commit -m "perf: precomputed hue→Color LUT for Rainbow, ColorCycle, RainbowChaseBorder, ColorCycleBorder (Medium #2)"
```

---

## Self-review

**1. Spec coverage:**
- M4 (inline `_draw_scroll_frame`): Task 1 ✓
- M18 (cache `compute_baseline`): Task 2 covers both TickerMessage and TickerCountdown ✓
- S16 perimeter cache: Task 3 ✓
- Medium #2 (Color LUT): Task 4 covers Rainbow, ColorCycle, RainbowChaseBorder, ColorCycleBorder, and Random ✓

**2. Placeholder scan:** None found — all code blocks are complete.

**3. Type consistency:**
- `hue_color(hue_degrees: float) -> Color` — used consistently as `hue_color(hue_int)` (int satisfies float) and `hue_color(hue)` (float). ✓
- `_baseline_y: int = attrs.field(init=False, default=-1)` — read as `int` throughout. ✓
- `_HUE_TABLE: list | None = None` in `color_lut.py` — assigned atomically as `list`. ✓

**4. Existing tests preserved:** The existing `TestRainbow`, `TestColorCycle`, `TestColorCycleRange`, `TestRainbowChaseBorder`, `TestRainbowChaseBorderHueRange`, `TestColorCycleBorder` tests all verify behavior via `(r, g, b)` tuples — these are unaffected by returning from the LUT vs computing inline (same RGB values). The 1° truncation in arc-restricted paths is below the precision of any existing assertion.
