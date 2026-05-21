# Batch 2 Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Five small code-quality fixes to the led-ticker codebase: duplicate-name guard on registries, `Transition.min_frames` Protocol default, removal of the dead `cursor_override` field and stale docstring entries, deletion of the redundant `AsyncWidget` Protocol, and `from __future__ import annotations` consistency across three `__init__.py` files.

**Architecture:** All changes are purely internal (no user-facing behaviour change). Five independent tasks; commit each separately. No new modules.

**Tech Stack:** Python 3.13, attrs, pytest-asyncio. Working in worktree `fix+batch-2-polish`.

---

## File Map

| Task | Modify | Create |
|------|--------|--------|
| S7   | `src/led_ticker/widgets/__init__.py:14-16`, `src/led_ticker/transitions/__init__.py:72-77` | `tests/test_registry_collision.py` |
| M1   | `src/led_ticker/transitions/__init__.py:39` | add tests to `tests/test_transitions.py` |
| S9   | `src/led_ticker/animations.py`, `src/led_ticker/widget.py`, `src/led_ticker/widgets/_image_base.py:657-659`, `tests/test_animations.py:15` | — |
| M16  | `src/led_ticker/widget.py:55-61`, `tests/test_widget_protocol.py:8-13,65-68` | — |
| M10  | `src/led_ticker/__init__.py`, `src/led_ticker/widgets/__init__.py`, `src/led_ticker/widgets/crypto/__init__.py` | — |

---

### Task 1: S7 — Registries reject duplicate names

Registering two widgets or two transitions under the same name silently overwrites the first. The second module import wins and the first widget type becomes unreachable. Guard both `register()` and `register_transition()` with a collision check.

**Files:**
- Create: `tests/test_registry_collision.py`
- Modify: `src/led_ticker/widgets/__init__.py:14-16`
- Modify: `src/led_ticker/transitions/__init__.py:72-77`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_registry_collision.py
"""Registry duplicate-name collision guard (S7)."""

import pytest

from led_ticker.widgets import _WIDGET_REGISTRY, register
from led_ticker.transitions import _TRANSITION_REGISTRY, register_transition


def test_widget_registry_rejects_duplicate():
    """Second @register with same name must raise ValueError, not silently
    overwrite the first registration."""

    @register("_test_dup_widget")
    class First:
        pass

    with pytest.raises(ValueError, match="already registered"):

        @register("_test_dup_widget")
        class Second:
            pass

    _WIDGET_REGISTRY.pop("_test_dup_widget")


def test_transition_registry_rejects_duplicate():
    """Second @register_transition with same name must raise ValueError."""

    @register_transition("_test_dup_trans")
    class First:
        min_frames = 0

        def frame_at(self, t, canvas, outgoing, incoming, **kwargs):
            return canvas

    with pytest.raises(ValueError, match="already registered"):

        @register_transition("_test_dup_trans")
        class Second:
            min_frames = 0

            def frame_at(self, t, canvas, outgoing, incoming, **kwargs):
                return canvas

    _TRANSITION_REGISTRY.pop("_test_dup_trans")
```

- [ ] **Step 2: Run tests to verify they fail**

```
PYTHONPATH=tests/stubs uv run pytest tests/test_registry_collision.py -v
```

Expected: 2 FAILED (no ValueError is raised yet).

- [ ] **Step 3: Add collision guard to widget registry**

In `src/led_ticker/widgets/__init__.py`, replace the `decorator` body (currently line 14-15):

```python
def register(name: str) -> Callable[[_T], _T]:
    """Decorator to register a widget class by config name."""

    def decorator(cls: _T) -> _T:
        if name in _WIDGET_REGISTRY:
            raise ValueError(
                f"Widget name {name!r} is already registered to"
                f" {_WIDGET_REGISTRY[name].__name__!r}."  # type: ignore[union-attr]
            )
        _WIDGET_REGISTRY[name] = cls  # type: ignore[arg-type]
        return cls

    return decorator
```

- [ ] **Step 4: Add collision guard to transition registry**

In `src/led_ticker/transitions/__init__.py`, replace the `register_transition` decorator body (currently lines 72-77):

```python
def register_transition(name: str) -> Callable[[type], type]:
    def decorator(cls: type) -> type:
        if name in _TRANSITION_REGISTRY:
            raise ValueError(
                f"Transition name {name!r} is already registered to"
                f" {_TRANSITION_REGISTRY[name].__name__!r}."
            )
        _TRANSITION_REGISTRY[name] = cls
        return cls

    return decorator
```

- [ ] **Step 5: Run tests to verify they pass**

```
PYTHONPATH=tests/stubs uv run pytest tests/test_registry_collision.py -v
```

Expected: 2 PASSED.

- [ ] **Step 6: Run full suite to verify no regressions**

```
PYTHONPATH=tests/stubs uv run pytest -x -q
```

Expected: 1775+ passed, 2 skipped.

- [ ] **Step 7: Commit**

```bash
git add tests/test_registry_collision.py \
        src/led_ticker/widgets/__init__.py \
        src/led_ticker/transitions/__init__.py
git commit -m "fix: raise ValueError on duplicate widget/transition registry name (S7)"
```

---

### Task 2: M1 — Transition.min_frames Protocol default

`Transition` Protocol declares `min_frames: int` as a required attribute, but `run_transition` already guards with `if hasattr(transition, "min_frames")` (line 162). The Protocol annotation is stricter than the runtime behaviour — it implies every conforming class must define the attribute. Change the annotation to `min_frames: int = 0` so the Protocol itself documents that 0 is the effective default for transitions that omit the attribute.

**Files:**
- Modify: `src/led_ticker/transitions/__init__.py:39`
- Modify: `tests/test_transitions.py` (append two tests to the end)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_transitions.py`:

```python
class TestMinFramesProtocol:
    def test_protocol_class_has_zero_default(self):
        """Transition.min_frames class attribute must be 0 so callers that
        access it via the Protocol class get the documented default."""
        from led_ticker.transitions import Transition

        assert Transition.min_frames == 0

    def test_transition_without_min_frames_satisfies_protocol(self):
        """A minimal transition that omits min_frames must still pass the
        runtime isinstance check — runtime_checkable only checks methods."""
        from led_ticker.transitions import Transition

        class MinimalTransition:
            def frame_at(self, t, canvas, outgoing, incoming, **kwargs):
                return canvas

        assert isinstance(MinimalTransition(), Transition)
```

- [ ] **Step 2: Run tests to verify they fail**

```
PYTHONPATH=tests/stubs uv run pytest tests/test_transitions.py::TestMinFramesProtocol -v
```

Expected: `test_protocol_class_has_zero_default` FAILED (AttributeError or AssertionError — Protocol class has no value yet).

- [ ] **Step 3: Apply the one-line Protocol change**

In `src/led_ticker/transitions/__init__.py` line 39, change:

```python
    min_frames: int
```

to:

```python
    min_frames: int = 0
```

- [ ] **Step 4: Run tests to verify they pass**

```
PYTHONPATH=tests/stubs uv run pytest tests/test_transitions.py::TestMinFramesProtocol -v
```

Expected: 2 PASSED.

- [ ] **Step 5: Run full suite**

```
PYTHONPATH=tests/stubs uv run pytest -x -q
```

Expected: 1775+ passed, 2 skipped.

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/transitions/__init__.py tests/test_transitions.py
git commit -m "fix: add default 0 to Transition.min_frames Protocol attribute (M1)"
```

---

### Task 3: S9-partial — Drop dead cursor_override field and stale docstring entries

`AnimationFrame.cursor_override` is always `None`; `_image_base.py` explicitly documents that it is ignored (line 657). `Widget.draw`'s docstring mentions a `region` kwarg that is plumbed but unused — removing the bullet prevents contributors from implementing it incorrectly against an outdated spec.

**Files:**
- Modify: `src/led_ticker/animations.py` (dataclass + Typewriter return)
- Modify: `src/led_ticker/widget.py` (docstring)
- Modify: `src/led_ticker/widgets/_image_base.py:657-659` (dead comment)
- Modify: `tests/test_animations.py:15` (remove assertion for deleted field)

- [ ] **Step 1: Update the test first (TDD on removal — removing assertion unblocks implementation)**

In `tests/test_animations.py`, in `test_frame_zero_returns_first_char`, remove the line:

```python
        assert f.cursor_override is None
```

The test after the change:

```python
    def test_frame_zero_returns_first_char(self):
        anim = Typewriter()
        f = anim.frame_for(0, "WATCH ME", canvas_width=256, text_width=48)
        assert f.visible_text == "W"
```

- [ ] **Step 2: Run test to verify it passes (still using the old AnimationFrame)**

```
PYTHONPATH=tests/stubs uv run pytest tests/test_animations.py -v
```

Expected: all PASSED (removing the assertion doesn't break anything yet).

- [ ] **Step 3: Remove cursor_override from AnimationFrame**

Replace the entire `AnimationFrame` class in `src/led_ticker/animations.py` (lines 18-31):

**Before:**

```python
@dataclass
class AnimationFrame:
    """What the widget should render at the current frame.

    visible_text:    The slice (or full text) to draw. Typewriter
                     returns growing prefixes.
    cursor_override: If set, place the text at this x. If None, the
                     orchestrator's cursor_pos is used (i.e. the
                     animation doesn't reposition).
    """

    visible_text: str
    cursor_override: int | None
```

**After:**

```python
@dataclass
class AnimationFrame:
    """What the widget should render at the current frame.

    visible_text: The slice (or full text) to draw. Typewriter returns
                  growing prefixes.
    """

    visible_text: str
```

- [ ] **Step 4: Update Typewriter.frame_for return (lines 52-55)**

**Before:**

```python
        return AnimationFrame(
            visible_text=full_text[:chars_visible],
            cursor_override=None,
        )
```

**After:**

```python
        return AnimationFrame(visible_text=full_text[:chars_visible])
```

- [ ] **Step 5: Remove stale cursor_override comment in _image_base.py**

In `src/led_ticker/widgets/_image_base.py` lines 657-659, replace:

```python
        `cursor_override` is intentionally ignored — image widgets fix
        cursor via `text_align`, not animation overrides (Bounce was
        removed in the PR #11 rework).
```

with (keep surrounding context, just drop those 3 lines):

```python
        cursor position via `text_align`.
```

The surrounding docstring section will read:

```
        Mirrors `TickerMessage.draw`'s animation branch: calls
        `Typewriter.frame_for(frame, full_text, canvas_width, text_width)`
        and reads `.visible_text` from the returned `AnimationFrame`.
        cursor position via `text_align`.
        """
```

- [ ] **Step 6: Remove region kwarg entry from Widget.draw docstring**

In `src/led_ticker/widget.py` lines 32-35, remove the `region` bullet from the recognized kwargs list:

**Before:**

```python
        Recognized kwargs:
        - ``y_offset`` (int): vertical offset from natural baseline
        - ``region`` (Region | None): sub-area of canvas to draw within
          (default: full canvas — plumbed for forward-compat with zoned
          layouts; widgets that don't care should ignore it)
        - ``font_color`` (Color): override the widget's own font color
```

**After:**

```python
        Recognized kwargs:
        - ``y_offset`` (int): vertical offset from natural baseline
        - ``font_color`` (Color): override the widget's own font color
```

- [ ] **Step 7: Run animation and widget protocol tests**

```
PYTHONPATH=tests/stubs uv run pytest tests/test_animations.py tests/test_widget_protocol.py -v
```

Expected: all PASSED.

- [ ] **Step 8: Run full suite**

```
PYTHONPATH=tests/stubs uv run pytest -x -q
```

Expected: 1775+ passed, 2 skipped.

- [ ] **Step 9: Commit**

```bash
git add src/led_ticker/animations.py \
        src/led_ticker/widget.py \
        src/led_ticker/widgets/_image_base.py \
        tests/test_animations.py
git commit -m "fix: drop dead cursor_override field from AnimationFrame; remove stale docstring entries (S9-partial)"
```

---

### Task 4: M16 — Delete unused AsyncWidget Protocol

`AsyncWidget(Widget, Protocol)` is a redundant intersection — `Widget` + `Updatable` covers the same contract. Nothing in `src/` uses it; it only appears in the tests file that tests the Protocol itself. Delete it and update the tests to assert conformance against `Widget` + `Updatable` instead.

**Files:**
- Modify: `src/led_ticker/widget.py:55-61`
- Modify: `tests/test_widget_protocol.py` (import + `test_async_widget_protocol_conformance`)

- [ ] **Step 1: Update the test to use Widget + Updatable**

In `tests/test_widget_protocol.py`, change the import block (lines 8-14):

**Before:**

```python
from led_ticker.widget import (
    _MAX_BACKOFF,
    _MIN_BACKOFF,
    AsyncWidget,
    Widget,
    run_monitor_loop,
)
```

**After:**

```python
from led_ticker.widget import (
    _MAX_BACKOFF,
    _MIN_BACKOFF,
    Updatable,
    Widget,
    run_monitor_loop,
)
```

Then replace `test_async_widget_protocol_conformance` (lines 65-68):

**Before:**

```python
def test_async_widget_protocol_conformance():
    w = SimpleAsyncWidget()
    assert isinstance(w, AsyncWidget)
    assert isinstance(w, Widget)
```

**After:**

```python
def test_async_widget_protocol_conformance():
    w = SimpleAsyncWidget()
    assert isinstance(w, Widget)
    assert isinstance(w, Updatable)
```

- [ ] **Step 2: Run the protocol tests to verify they fail**

```
PYTHONPATH=tests/stubs uv run pytest tests/test_widget_protocol.py -v
```

Expected: `ImportError: cannot import name 'Updatable'` — or if `Updatable` exists, `test_async_widget_protocol_conformance` PASSED but `AsyncWidget` import fails. Either way confirms we need the implementation step.

- [ ] **Step 3: Delete AsyncWidget from widget.py**

In `src/led_ticker/widget.py`, delete lines 55-61:

```python
@runtime_checkable
class AsyncWidget(Widget, Protocol):
    """A widget that fetches data asynchronously and updates itself."""

    async def update(self) -> None:
        """Fetch fresh data from an external source."""
        ...
```

Leave `Updatable` (lines 46-52) in place — it is the canonical async-widget protocol.

- [ ] **Step 4: Run the protocol tests**

```
PYTHONPATH=tests/stubs uv run pytest tests/test_widget_protocol.py -v
```

Expected: all PASSED (including `test_async_widget_protocol_conformance` via `Widget` + `Updatable`).

- [ ] **Step 5: Run full suite**

```
PYTHONPATH=tests/stubs uv run pytest -x -q
```

Expected: 1775+ passed, 2 skipped.

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/widget.py tests/test_widget_protocol.py
git commit -m "fix: delete redundant AsyncWidget Protocol; use Widget + Updatable (M16)"
```

---

### Task 5: M10 — Add from __future__ import annotations to three __init__.py files

Three public package init files are missing the `from __future__ import annotations` header present in every other module. Add it for consistency (enables PEP 563 deferred annotation evaluation everywhere the package is imported).

**Files:**
- Modify: `src/led_ticker/__init__.py`
- Modify: `src/led_ticker/widgets/__init__.py`
- Modify: `src/led_ticker/widgets/crypto/__init__.py`

- [ ] **Step 1: Verify the import is missing**

```
grep -l "from __future__ import annotations" \
  src/led_ticker/__init__.py \
  src/led_ticker/widgets/__init__.py \
  src/led_ticker/widgets/crypto/__init__.py
```

Expected: no output (none of the three have it yet).

- [ ] **Step 2: Add to src/led_ticker/__init__.py**

**Before (entire file):**

```python
"""led-ticker: Asyncio LED matrix display for news, weather, crypto, and more."""

__version__ = "2.0.0"
```

**After:**

```python
"""led-ticker: Asyncio LED matrix display for news, weather, crypto, and more."""

from __future__ import annotations

__version__ = "2.0.0"
```

- [ ] **Step 3: Add to src/led_ticker/widgets/__init__.py**

Insert `from __future__ import annotations` as the first non-docstring line. The file currently begins:

```python
"""Widget registry and auto-discovery."""

from collections.abc import Callable
...
```

Change to:

```python
"""Widget registry and auto-discovery."""

from __future__ import annotations

from collections.abc import Callable
...
```

- [ ] **Step 4: Add to src/led_ticker/widgets/crypto/__init__.py**

**Before (entire file):**

```python
"""Cryptocurrency widgets."""
```

**After:**

```python
"""Cryptocurrency widgets."""

from __future__ import annotations
```

- [ ] **Step 5: Verify grep finds all three**

```
grep -l "from __future__ import annotations" \
  src/led_ticker/__init__.py \
  src/led_ticker/widgets/__init__.py \
  src/led_ticker/widgets/crypto/__init__.py
```

Expected: all three paths printed.

- [ ] **Step 6: Run full suite**

```
PYTHONPATH=tests/stubs uv run pytest -x -q
```

Expected: 1775+ passed, 2 skipped.

- [ ] **Step 7: Commit**

```bash
git add src/led_ticker/__init__.py \
        src/led_ticker/widgets/__init__.py \
        src/led_ticker/widgets/crypto/__init__.py
git commit -m "chore: add from __future__ import annotations to three __init__ files (M10)"
```

---

## Self-Review

**Spec coverage:**
- S7: Tasks 1 — widget + transition registry collision guard ✓
- M1: Task 2 — Protocol default ✓
- S9-partial: Task 3 — cursor_override removal + docstring cleanup ✓
- M16: Task 4 — AsyncWidget deletion ✓
- M10: Task 5 — future annotations ✓

**Placeholder scan:** No TBD/TODO present. All code is complete.

**Type consistency:**
- `_WIDGET_REGISTRY[name].__name__` access — `.name` is a standard Python class attribute, present on all types ✓
- `AnimationFrame(visible_text=...)` — single-field dataclass, keyword-only call site ✓
- `Updatable` used in test matches the exported name in `widget.py` ✓
- `Transition.min_frames = 0` — Protocol class attribute; runtime code uses `hasattr` guard, so no behaviour change ✓
