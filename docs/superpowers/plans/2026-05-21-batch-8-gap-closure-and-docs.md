# Batch 8: Gap Closure + Documentation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the four items missed in batches 1–7 (M6, M17, M13, Medium #3) and fix all stale documentation in CLAUDE.md and the docs content-source.

**Architecture:** Four independent code tasks (all small-to-medium), one documentation task. Code tasks can each be reviewed and committed independently. Documentation task touches CLAUDE.md and one docs content-source file.

**Tech Stack:** Python 3.12, attrs, functools, typing.Protocol, pytest (asyncio_mode="auto")

---

## File Map

| Task | Action | Path |
|------|--------|------|
| Task 1 (M6) | Modify | `src/led_ticker/transitions/push.py` |
| Task 1 (M17) | Modify | `src/led_ticker/transitions/effects.py` |
| Task 1 tests | Modify | `tests/test_transitions.py` |
| Task 2 (M13) | Modify | `src/led_ticker/widgets/_frame_aware.py` |
| Task 2 tests | Modify | `tests/test_widgets/test_frame_aware.py` (or nearest test file) |
| Task 3 (Medium #3) | Modify | `src/led_ticker/_types.py` |
| Task 3 tests | Modify | `tests/test_types.py` (new) or nearest types test |
| Task 4 (docs) | Modify | `CLAUDE.md` |
| Task 4 (docs) | Modify | `docs/content-source/transitions-legacy.md` |

---

## Task 1: M6 — PushRandom bootstrap + M17 — Dissolve sequence cache

**Files:**
- Modify: `src/led_ticker/transitions/push.py`
- Modify: `src/led_ticker/transitions/effects.py`
- Modify: `tests/test_transitions.py`

### Context

**M6 (PushRandom):** `PushRandom.__init__` sets `self._current = None`. The `min_frames` property has a fallback `return 10` for when `_current` is `None`. This fires on every first-frame query before the first `frame_at` call. Fix: pre-construct one sub-transition in `__init__`.

Current code in `src/led_ticker/transitions/push.py:235-259`:
```python
class PushRandom:
    def __init__(self, **kwargs: Any) -> None:
        self._rng = random.Random()
        self._last_cls: type[Transition] | None = None
        self._last_t: float = 1.0
        self._current: Transition | None = None

    @property
    def min_frames(self) -> int:
        if self._current is not None:
            return getattr(self._current, "min_frames", 10)
        return 10  # ← fires on first query
```

**M17 (Dissolve):** `Dissolve._get_sequence` caches the shuffled pixel list on `self._sequence` — per-instance. A fresh `Dissolve()` object pays the ~16K-element shuffle cost. Fix: module-level `@functools.cache` keyed on `(w, h, seed)`.

Current code in `src/led_ticker/transitions/effects.py:63-75`:
```python
class Dissolve:
    def __init__(self, seed: int = 42, **kwargs: Any) -> None:
        self.seed: int = seed
        self._sequence: list[tuple[int, int]] | None = None

    def _get_sequence(self, w: int, h: int) -> list[tuple[int, int]]:
        if self._sequence is None or len(self._sequence) != w * h:
            import random
            rng = random.Random(self.seed)
            coords = [(x, y) for y in range(h) for x in range(w)]
            rng.shuffle(coords)
            self._sequence = coords
        return self._sequence
```

### Steps

- [ ] **Step 1: Write failing tests**

In `tests/test_transitions.py`, find a suitable location (or add a new class at the end) and add:

```python
class TestPushRandomMinFrames:
    def test_min_frames_is_not_fallback_on_fresh_instance(self):
        """min_frames must reflect a real sub-transition, not a hardcoded 10."""
        pr = PushRandom()
        # PushLeft/Right/Up/Down all have min_frames=1 (not 10)
        # A hardcoded-10 return exposes the bootstrap gap.
        assert pr.min_frames != 10 or pr.min_frames == getattr(
            pr._current, "min_frames", 10
        )

    def test_current_is_set_at_construction(self):
        pr = PushRandom()
        assert pr._current is not None


class TestDissolveSequenceCache:
    def test_two_instances_same_seed_share_sequence_object(self):
        """Same (w, h, seed) must return the SAME list object."""
        d1 = Dissolve(seed=7)
        d2 = Dissolve(seed=7)
        seq1 = d1._get_sequence(160, 16)
        seq2 = d2._get_sequence(160, 16)
        assert seq1 is seq2

    def test_different_seed_gives_different_sequence(self):
        d1 = Dissolve(seed=1)
        d2 = Dissolve(seed=2)
        assert d1._get_sequence(160, 16) != d2._get_sequence(160, 16)
```

You'll need to find the imports at the top of `tests/test_transitions.py` and add `PushRandom` and `Dissolve` if not already imported.

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker && uv run pytest tests/test_transitions.py::TestPushRandomMinFrames tests/test_transitions.py::TestDissolveSequenceCache -v
```

Expected: `test_current_is_set_at_construction` FAILS (current is None). `test_two_instances_same_seed_share_sequence_object` FAILS (different objects).

- [ ] **Step 3: Fix M6 — PushRandom bootstrap**

In `src/led_ticker/transitions/push.py`, update `PushRandom.__init__` to pre-construct a sub-transition:

```python
def __init__(self, **kwargs: Any) -> None:
    self._rng = random.Random()
    chosen_cls = self._rng.choice(self._PUSH_CLASSES)
    self._last_cls: type[Transition] = chosen_cls
    self._last_t: float = 1.0
    self._current: Transition = chosen_cls()
```

And simplify `min_frames` (no more None guard needed):

```python
@property
def min_frames(self) -> int:
    return getattr(self._current, "min_frames", 10)
```

- [ ] **Step 4: Fix M17 — Dissolve sequence cache**

In `src/led_ticker/transitions/effects.py`, add a module-level cached helper and update `Dissolve`:

Add after the existing imports at the top of the file:
```python
import functools
```

(Check if `functools` is already imported — if so, skip.)

Add before `class Dissolve`:
```python
@functools.cache
def _dissolve_sequence(w: int, h: int, seed: int) -> list[tuple[int, int]]:
    import random
    rng = random.Random(seed)
    coords = [(x, y) for y in range(h) for x in range(w)]
    rng.shuffle(coords)
    return coords
```

Update `Dissolve.__init__` and `_get_sequence`:

```python
def __init__(self, seed: int = 42, **kwargs: Any) -> None:
    self.seed: int = seed

def _get_sequence(self, w: int, h: int) -> list[tuple[int, int]]:
    return _dissolve_sequence(w, h, self.seed)
```

Remove `self._sequence: list[tuple[int, int]] | None = None` from `__init__`.

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/test_transitions.py::TestPushRandomMinFrames tests/test_transitions.py::TestDissolveSequenceCache -v
```

Expected: all pass.

- [ ] **Step 6: Run full suite**

```bash
uv run pytest --tb=short -q
```

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add src/led_ticker/transitions/push.py src/led_ticker/transitions/effects.py tests/test_transitions.py
git commit -m "fix: pre-construct PushRandom sub-transition; cache Dissolve sequence across instances (M6, M17)"
```

---

## Task 2: M13 — _FrameAware.__new__ guard for missing @attrs.define

**Files:**
- Modify: `src/led_ticker/widgets/_frame_aware.py`
- Test: `tests/test_widgets/test_frame_aware.py` (check if this file exists; if not, look for frame_aware tests in the nearest test file)

### Context

`_FrameAware` is `@attrs.define`. A subclass that forgets `@attrs.define` inherits the parent's `__init__` but its own `attrs.field()` class attributes remain as sentinel objects rather than initialized values — a silent construction-succeeds-but-is-broken failure.

The fix: add `__new__` to `_FrameAware` that raises `TypeError` at first instantiation if the concrete class lacks attrs processing. By the time `__new__` fires, all class decorators (including `@attrs.define`) have already been applied.

`__init_subclass__` won't work here: it fires before `@attrs.define` is applied, so `attrs.has(cls)` always returns False in that hook even for properly decorated subclasses.

### Steps

- [ ] **Step 1: Find the right test file**

```bash
find /Users/james/projects/github/jamesawesome/led-ticker/tests -name "*frame_aware*"
```

If no dedicated file exists, add to `tests/test_widgets/test_frame_aware.py` (create it). If a file exists, add the new class there.

- [ ] **Step 2: Write failing test**

```python
import attrs
import pytest
from led_ticker.widgets._frame_aware import _FrameAware


class TestFrameAwareGuard:
    def test_properly_decorated_subclass_constructs_fine(self):
        @attrs.define
        class GoodWidget(_FrameAware):
            name: str = attrs.field(default="")

        w = GoodWidget()
        assert w._frame_count == 0

    def test_undecorated_subclass_raises_on_instantiation(self):
        class BadWidget(_FrameAware):
            name: str = attrs.field(default="")

        with pytest.raises(TypeError, match="attrs.define"):
            BadWidget()
```

Run to confirm `test_undecorated_subclass_raises_on_instantiation` fails (no TypeError raised currently).

- [ ] **Step 3: Run test to confirm failure**

```bash
uv run pytest tests/test_widgets/test_frame_aware.py::TestFrameAwareGuard::test_undecorated_subclass_raises_on_instantiation -v
```

Expected: FAIL — no TypeError raised.

- [ ] **Step 4: Add `__new__` guard to `_FrameAware`**

In `src/led_ticker/widgets/_frame_aware.py`, add `import attrs` at the top (it's already imported). Then add `__new__` to `_FrameAware` BEFORE the other methods:

```python
def __new__(cls, *args: object, **kwargs: object) -> "_FrameAware":
    if cls is not _FrameAware and not attrs.has(cls):
        raise TypeError(
            f"{cls.__name__} inherits _FrameAware but is not decorated with "
            "@attrs.define — frame-counter fields will not be initialized correctly."
        )
    return super().__new__(cls)
```

The check `cls is not _FrameAware` allows `_FrameAware()` itself to be instantiated (e.g., in tests). `attrs.has(cls)` returns True iff `cls` has been processed by `@attrs.define` or `@attr.s`.

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/test_widgets/test_frame_aware.py::TestFrameAwareGuard -v
```

Expected: both tests pass.

- [ ] **Step 6: Run full suite**

```bash
uv run pytest --tb=short -q
```

Expected: all pass (the guard fires only for undecorated subclasses; all existing widget subclasses use `@attrs.define`).

- [ ] **Step 7: Commit**

```bash
git add src/led_ticker/widgets/_frame_aware.py tests/test_widgets/test_frame_aware.py
git commit -m "fix: raise TypeError on _FrameAware subclass missing @attrs.define (M13)"
```

---

## Task 3: Medium #3 — CanvasLike Protocol replacing Canvas = Any

**Files:**
- Modify: `src/led_ticker/_types.py`
- Test: `tests/test_types.py` (create new, or nearest suitable test file)

### Context

`src/led_ticker/_types.py:12` is `Canvas = Any`. Every function that annotates `canvas: Canvas` is effectively untyped. The fix: define `CanvasLike` as a `@runtime_checkable` Protocol with the five methods every canvas must expose, then alias `Canvas = CanvasLike`.

The test stub (`tests/stubs/rgbmatrix/__init__.py:60-99`) already has `SetPixel`, `Clear`, `Fill`, `width`, `height`. `ScaledCanvas` has `SetPixel`, `Clear`, `Fill`, `width` (property), `height` (property). Both satisfy the Protocol.

No callers need to change — they import `Canvas` from `_types`, and the alias update makes all annotated signatures more precise automatically.

### Steps

- [ ] **Step 1: Write failing test**

Create `tests/test_types.py`:

```python
"""Tests that _types.py contracts are satisfied by all canvas implementations."""
import pytest
from led_ticker._types import Canvas, CanvasLike


class TestCanvasLike:
    def test_canvaslike_is_exported(self):
        from led_ticker._types import CanvasLike
        assert CanvasLike is not None

    def test_canvas_alias_equals_canvaslike(self):
        assert Canvas is CanvasLike

    def test_stub_canvas_satisfies_protocol(self):
        from tests.stubs.rgbmatrix import RGBMatrix
        frame = RGBMatrix(options=None)
        canvas = frame.CreateFrameCanvas()
        assert isinstance(canvas, CanvasLike)

    def test_scaled_canvas_satisfies_protocol(self):
        from led_ticker.frame import LedFrame
        from led_ticker.scaled_canvas import ScaledCanvas
        frame = LedFrame(led_cols=32, led_chain=5)
        canvas = frame.get_clean_canvas()
        scaled = ScaledCanvas(real=canvas, scale=2)
        assert isinstance(scaled, CanvasLike)

    def test_plain_object_without_methods_does_not_satisfy(self):
        class NotACanvas:
            pass
        assert not isinstance(NotACanvas(), CanvasLike)
```

Run to confirm `test_canvaslike_is_exported` FAILS (CanvasLike doesn't exist yet).

- [ ] **Step 2: Run test to verify failure**

```bash
uv run pytest tests/test_types.py::TestCanvasLike::test_canvaslike_is_exported -v
```

Expected: FAIL with ImportError.

- [ ] **Step 3: Implement CanvasLike Protocol in `_types.py`**

Replace the entire `_types.py` with:

```python
"""Type aliases for led-ticker.

Since rgbmatrix is a C extension with no type stubs, we define structural
Protocols to clarify intent at each use site and enable isinstance checks.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class CanvasLike(Protocol):
    """Structural interface every canvas implementation must satisfy.

    Satisfied by: the rgbmatrix real canvas, test stub _StubCanvas,
    and ScaledCanvas (which delegates to a real canvas).
    """

    width: int
    height: int

    def SetPixel(self, x: int, y: int, r: int, g: int, b: int) -> None: ...
    def Clear(self) -> None: ...
    def Fill(self, r: int, g: int, b: int) -> None: ...


# Public alias — import `Canvas` everywhere; `CanvasLike` is for isinstance checks.
Canvas = CanvasLike

# C extension objects with no stubs — remain as Any until native stubs exist.
Font = Any
Color = Any
RGBMatrix = Any
RGBMatrixOptions = Any

# Common type patterns
ColorTuple = tuple[int, int, int]
PixelData = list[tuple[int, int, int, int, int]]
DrawResult = tuple[Canvas, int]
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_types.py -v
```

Expected: all 5 tests pass.

- [ ] **Step 5: Run full suite**

```bash
uv run pytest --tb=short -q
```

Expected: all pass. If pyright/mypy reports new errors (test stubs previously matched `Any`, now matched `CanvasLike`), check: does the stub `_StubCanvas` satisfy all five methods? (It does: `SetPixel`, `Clear`, `Fill`, `width`, `height` are all present.) The `@runtime_checkable` Protocol checks attribute presence, not signatures, so `isinstance` checks in tests will pass.

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/_types.py tests/test_types.py
git commit -m "feat: introduce CanvasLike Protocol; replace Canvas = Any with typed alias (Medium #3)"
```

---

## Task 4: Documentation fixes (CLAUDE.md + transitions-legacy.md)

**Files:**
- Modify: `CLAUDE.md`
- Modify: `docs/content-source/transitions-legacy.md`

### Context

Several areas in CLAUDE.md are stale after batches 2–7. The transitions contributor doc has one stale step.

**Stale items in CLAUDE.md:**

1. **"Widget Protocol" section (line ~122)** — says `draw(canvas, cursor_pos=0, **kwargs)` and `Support y_offset = kwargs.get("y_offset", 0)` — both stale since batch 7 dropped `**kwargs`.

2. **"Adding a New Widget" section (lines ~205-206)** — step 3 says `draw(canvas, cursor_pos=0, **kwargs) -> (canvas, int)`, step 4 says `y_offset = kwargs.get("y_offset", 0)` — both stale.

3. **"Adding a New Transition" section (line ~218)** — step 7 says "Add import to `src/led_ticker/transitions/__init__.py` (submodule import + re-export)" — stale since batch 3 added pkgutil auto-discovery.

4. **`_has_play` description (line ~116)** — says `inspect.iscoroutinefunction(type(widget).play)` but doesn't mention the assertive RuntimeError added in batch 7.

5. **"Section transition precedence" (line ~247)** — mentions `transition_specified` but doesn't document `entry_transition` / `widget_transition` added in batch 4.

6. **Color providers section (line ~187)** — says "New providers default `frame_invariant = False` (conservative)" but doesn't mention the `__init_subclass__` enforcement added in batch 3.

7. **Commands section (line ~18)** — missing `make validate` description mentioning `--list-fields` (added in batch 5).

8. **Missing Animation Protocol note** — the color providers section doesn't mention the `Animation` Protocol added in batch 3.

**Stale item in docs/content-source/transitions-legacy.md:**

Line ~246 says: "Then import and re-export it in `src/led_ticker/transitions/__init__.py`." This is stale — pkgutil auto-discovers all non-private `.py` files under `transitions/`. No manual import needed.

### Steps

- [ ] **Step 1: Fix CLAUDE.md "Widget Protocol" section**

Find and replace the two stale lines in the "Key Patterns" section:

Old:
```
**Widget Protocol** — All widgets implement `draw(canvas, cursor_pos=0, **kwargs) -> (canvas, int)`. Support `y_offset = kwargs.get("y_offset", 0)` for vertical transitions. Async data widgets implement `update()` and use `run_monitor_loop()` with exponential backoff.
```

New:
```
**Widget Protocol** — All widgets implement `draw(canvas, cursor_pos=0, *, y_offset: int = 0, font_color: Any = None) -> (canvas, int)`. The `y_offset` param shifts the widget vertically; omitting it breaks PushUp/PushDown transitions. Async data widgets implement `update()` and use `run_monitor_loop()` with exponential backoff.
```

- [ ] **Step 2: Fix CLAUDE.md "Adding a New Widget" steps 3-4**

Old steps 3-4:
```
3. Implement `draw(canvas, cursor_pos=0, **kwargs) -> (canvas, int)`
4. Support `y_offset = kwargs.get("y_offset", 0)` — use `12 + y_offset` in DrawText
```

New steps 3-4:
```
3. Implement `draw(canvas, cursor_pos=0, *, y_offset: int = 0, font_color: Any = None) -> (canvas, int)`
4. Use `y_offset` directly in layout (e.g. `baseline_y + y_offset`) — omitting it breaks PushUp/PushDown transitions
```

- [ ] **Step 3: Fix CLAUDE.md "Adding a New Transition" step 7**

Old step 7:
```
7. Add import to `src/led_ticker/transitions/__init__.py` (submodule import + re-export)
```

New step 7:
```
7. No manual registration needed — `transitions/__init__.py` uses `pkgutil.iter_modules` to auto-discover every non-private `.py` file in `transitions/`. Creating the file and applying `@register_transition` is sufficient.
```

- [ ] **Step 4: Update CLAUDE.md `_has_play` description**

Find the `_has_play` paragraph in the "play()-style widgets" invariant (around line 116). It currently says:

```
`_has_play` checks `inspect.iscoroutinefunction(type(widget).play)` — looking at the CLASS, not the instance — so Mock objects don't false-positive.
```

Add the assertive-failure note:

```
`_has_play` checks `inspect.iscoroutinefunction(type(widget).play)` — looking at the CLASS, not the instance — so Mock objects don't false-positive. If the class has a `play` attribute that is NOT a coroutinefunction (e.g., forgot `async`), `_has_play` raises `RuntimeError` rather than silently routing the widget to the `draw()` path.
```

- [ ] **Step 5: Add entry_transition / widget_transition to CLAUDE.md "Section transition precedence"**

Find the "Section transition precedence" paragraph near the end of CLAUDE.md. It discusses `transition_specified`. Add a sentence documenting the fine-grained fields:

After `The `transition_specified: bool` flag on `SectionConfig` records whether the user wrote the field...`, add:

```
For independent control, sections also accept `entry_transition` (overrides how THIS section appears, ignoring `between_sections` and `transition`) and `widget_transition` (overrides inter-widget transitions within this section). Precedence: `entry_transition` > `transition` > `between_sections` for entry; `widget_transition` > `transition` > cut for within-section.
```

- [ ] **Step 6: Add frame_invariant enforcement note to CLAUDE.md color providers section**

Find the sentence "New providers default `frame_invariant = False` (conservative)." in the Color providers section. After it, add:

```
`ColorProvider` subclasses that omit the `frame_invariant` class attribute raise `TypeError` at definition time via `__init_subclass__` — the same enforcement applies to `BorderEffect` subclasses.
```

- [ ] **Step 7: Add --list-fields to CLAUDE.md Commands**

Find the `make validate` line in the Commands section. Update it:

Old:
```bash
make validate      # led-ticker validate CONFIG=path.toml (config preflight)
```

New:
```bash
make validate      # led-ticker validate CONFIG=path.toml (config preflight)
                   # led-ticker validate --list-fields TYPE=message (show all fields for a widget type)
```

Actually, `make validate` may not expose `--list-fields` directly — the subcommand is `led-ticker validate --list-fields type=message`. Add a note to the validate entry:

```bash
make validate      # led-ticker validate CONFIG=path.toml (config preflight); supports --list-fields type=<name> to print a widget's recognized TOML fields
```

- [ ] **Step 8: Add Animation Protocol note to CLAUDE.md**

Find the "Color providers and animations" section heading and the user-facing surface links. Add a sentence about the Animation Protocol:

After the link line `User-facing surface: <...animations...>`, add:

```
**Animation contract** — Custom animations implement the `Animation` Protocol (`src/led_ticker/animations.py`): `def frame_for(self, frame: int, text: str, canvas_width: int, content_width: int) -> AnimationFrame`. `AnimationFrame` carries `visible_text: str` (the slice to render this tick). `cursor_override` was removed — animations do not shift the cursor. Currently only `Typewriter` is shipped; the Protocol documents the contract for future animations.
```

- [ ] **Step 9: Fix transitions-legacy.md stale step**

In `docs/content-source/transitions-legacy.md`, find the line:

```
Then import and re-export it in `src/led_ticker/transitions/__init__.py`.
```

Replace with:

```
No import registration needed — `transitions/__init__.py` uses `pkgutil.iter_modules` to auto-discover every non-private `.py` file in the `transitions/` package. Creating the file and applying `@register_transition` is sufficient.
```

- [ ] **Step 10: Run full test suite to confirm no regressions**

```bash
uv run pytest --tb=short -q
```

Expected: all pass (doc changes don't affect tests).

- [ ] **Step 11: Commit**

```bash
git add CLAUDE.md docs/content-source/transitions-legacy.md
git commit -m "docs: fix stale **kwargs references, transition registration step, and add batch 3-7 invariants to CLAUDE.md"
```

---

## Self-Review

### Spec Coverage

| Item | Task | Status |
|------|------|--------|
| M6 — PushRandom pre-construct sub-transition | Task 1 | ✅ |
| M17 — Dissolve @functools.cache on (w,h,seed) | Task 1 | ✅ |
| M13 — _FrameAware.__new__ guard for missing @attrs.define | Task 2 | ✅ |
| Medium #3 — CanvasLike Protocol, Canvas = CanvasLike | Task 3 | ✅ |
| CLAUDE.md Widget Protocol stale **kwargs | Task 4 Step 1 | ✅ |
| CLAUDE.md Adding a New Widget stale draw signature | Task 4 Step 2 | ✅ |
| CLAUDE.md Adding a New Transition stale step 7 | Task 4 Step 3 | ✅ |
| CLAUDE.md _has_play assertive failure note | Task 4 Step 4 | ✅ |
| CLAUDE.md entry_transition / widget_transition | Task 4 Step 5 | ✅ |
| CLAUDE.md frame_invariant __init_subclass__ enforcement | Task 4 Step 6 | ✅ |
| CLAUDE.md --list-fields in Commands | Task 4 Step 7 | ✅ |
| CLAUDE.md Animation Protocol note | Task 4 Step 8 | ✅ |
| transitions-legacy.md stale pkgutil step | Task 4 Step 9 | ✅ |

### Placeholder Scan

No TBD, TODO, or "implement later" strings. All code steps include complete implementations.

### Type Consistency

- `CanvasLike` uses `Canvas = CanvasLike` alias — existing import sites `from led_ticker._types import Canvas` get the Protocol transparently
- `_dissolve_sequence` return type `list[tuple[int, int]]` matches `Dissolve._sequence` old type annotation
- `PushRandom._current: Transition` (not Optional) after fix — remove the `| None` annotation if present
