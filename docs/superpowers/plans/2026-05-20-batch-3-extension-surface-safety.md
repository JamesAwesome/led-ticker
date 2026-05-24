# Batch 3 — Extension Surface Safety

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden the extension surface so contributor mistakes (duplicate registration, forgotten `frame_invariant`, forgotten auto-import, undocumented kwargs) surface immediately as errors instead of silent misbehavior.

**Architecture:** Six independent, additive changes to `widgets/__init__.py`, `transitions/__init__.py`, `color_providers.py`, `borders.py`, and `animations.py`. No engine or render-path code touched. All changes are isolated to the extension/plugin layer.

**Tech Stack:** Python 3.13, attrs, pytest, pkgutil/importlib for auto-discovery.

**Branch from:** `main`. Batch 2 is in flight on its own worktree; see conflict notes in Task 6 re: `animations.py`.

---

## File Map

| File | Change |
|---|---|
| `src/led_ticker/widgets/__init__.py` | `register()` raises on duplicate name |
| `src/led_ticker/transitions/__init__.py` | `register_transition()` raises on duplicate; `frame_at` docstring; replace manual imports with pkgutil |
| `src/led_ticker/color_providers.py` | Add `ColorProviderBase` with `__init_subclass__` guard |
| `src/led_ticker/borders.py` | Add `BorderEffectBase` with `__init_subclass__` guard |
| `src/led_ticker/animations.py` | Add `Animation` Protocol |
| `tests/test_widgets/test_registry.py` | Duplicate widget test |
| `tests/test_transitions.py` | Duplicate transition test |
| `tests/test_color_providers.py` | `ColorProviderBase` enforcement test |
| `tests/test_borders.py` | `BorderEffectBase` enforcement test |
| `tests/test_animations.py` | `Animation` Protocol structural test |

---

## Task 1: S7 — Duplicate registry detection (widgets + transitions)

**Files:**
- Modify: `src/led_ticker/widgets/__init__.py:14-15`
- Modify: `src/led_ticker/transitions/__init__.py:72-76`
- Modify: `tests/test_widgets/test_registry.py`
- Modify: `tests/test_transitions.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_widgets/test_registry.py`:

```python
def test_register_duplicate_name_raises():
    from led_ticker.widgets import register

    @register("message")  # "message" is already registered to TickerMessage
    class ShouldFail:
        pass

    # unreachable — the decorator must raise
```

Wait — pytest expects `raises()` context manager for this. Update the test:

```python
def test_register_duplicate_name_raises():
    from led_ticker.widgets import register

    with pytest.raises(ValueError, match="duplicate.*message"):

        @register("message")
        class ShouldFail:
            pass
```

Add to `tests/test_transitions.py` (inside `TestTransitionRegistry`):

```python
def test_register_duplicate_transition_raises():
    from led_ticker.transitions import register_transition

    with pytest.raises(ValueError, match="duplicate.*cut"):

        @register_transition("cut")
        class ShouldFail:
            pass
```

- [ ] **Step 2: Run to verify failures**

```bash
cd /path/to/worktree
python -m pytest tests/test_widgets/test_registry.py::test_register_duplicate_name_raises tests/test_transitions.py::TestTransitionRegistry::test_register_duplicate_transition_raises -v
```

Expected: both FAIL (no duplicate check yet, decorator silently overwrites).

- [ ] **Step 3: Implement collision check in widget registry**

In `src/led_ticker/widgets/__init__.py`, replace the `decorator` body:

```python
def register(name: str) -> Callable[[_T], _T]:
    """Decorator to register a widget class by config name."""

    def decorator(cls: _T) -> _T:
        if name in _WIDGET_REGISTRY:
            raise ValueError(
                f"duplicate widget registration {name!r}: already bound to "
                f"{_WIDGET_REGISTRY[name].__name__}"  # type: ignore[union-attr]
            )
        _WIDGET_REGISTRY[name] = cls  # type: ignore[arg-type]
        return cls

    return decorator
```

- [ ] **Step 4: Implement collision check in transition registry**

In `src/led_ticker/transitions/__init__.py`, replace the `register_transition` decorator body:

```python
def register_transition(name: str) -> Callable[[type], type]:
    def decorator(cls: type) -> type:
        if name in _TRANSITION_REGISTRY:
            raise ValueError(
                f"duplicate transition registration {name!r}: already bound to "
                f"{_TRANSITION_REGISTRY[name].__name__}"
            )
        _TRANSITION_REGISTRY[name] = cls
        return cls

    return decorator
```

- [ ] **Step 5: Run tests to verify passing**

```bash
python -m pytest tests/test_widgets/test_registry.py tests/test_transitions.py -v
```

Expected: all green including the two new tests.

- [ ] **Step 6: Full suite smoke check**

```bash
make test
```

Expected: all green (no existing test registers a duplicate name).

- [ ] **Step 7: Commit**

```bash
git add src/led_ticker/widgets/__init__.py \
        src/led_ticker/transitions/__init__.py \
        tests/test_widgets/test_registry.py \
        tests/test_transitions.py
git commit -m "feat: raise on duplicate widget/transition registry names (S7)"
```

---

## Task 2: M2 — Document recognized frame_at kwargs

**Files:**
- Modify: `src/led_ticker/transitions/__init__.py:41-49` (the `Transition` Protocol `frame_at` method)

This is a docstring-only change; no new tests needed.

- [ ] **Step 1: Add docstring to `Transition.frame_at`**

In `src/led_ticker/transitions/__init__.py`, replace the `frame_at` stub inside the `Transition` Protocol:

```python
    def frame_at(
        self,
        t: float,
        canvas: Canvas,
        outgoing: Any,
        incoming: Any,
        **kwargs: Any,
    ) -> Canvas:
        """Render one frame at progress t (0.0–1.0).

        Recognized kwargs (passed by run_transition; safe to ignore if
        the transition doesn't need them):

        - ``outgoing_scroll_pos: int`` — pixel offset where the outgoing
          widget stopped scrolling. Push transitions use this to continue
          the scroll in the same direction without a visible jump.
        - ``duration_ms: int`` — total transition duration in milliseconds.
          Sprite-trail transitions use this to compute crossing speed so
          the entity reaches the far edge exactly when t=1.0.
        - ``incoming_bg_color: tuple[int,int,int] | None`` — the new
          section's background color. Hires snap transitions (pokeball,
          nyancat, baseball) use this at t≥0.95 to Fill() before drawing
          incoming so a bg-colored section doesn't flash black for one
          tick.

        At t=0: render only outgoing. At t=1.0: render only incoming.
        Call ``canvas.Clear()`` or ``canvas.Fill()`` is handled by the
        runner BEFORE each ``frame_at`` call — transitions must NOT clear
        the canvas themselves.
        """
        ...
```

- [ ] **Step 2: Run suite to confirm no breakage**

```bash
make test
```

Expected: all green (docstring-only change).

- [ ] **Step 3: Commit**

```bash
git add src/led_ticker/transitions/__init__.py
git commit -m "docs: document recognized frame_at kwargs on Transition Protocol (M2)"
```

---

## Task 3: S8 — Transition auto-discovery via pkgutil

Replace the hand-maintained auto-import list with `pkgutil.iter_modules` so adding a new `transitions/my_effect.py` with `@register_transition` never requires editing `__init__.py`.

The **re-export block** (`from led_ticker.transitions.push import PushLeft, ...`) is kept unchanged — it provides convenience imports for tests and direct callers. Only the auto-import block changes.

**Files:**
- Modify: `src/led_ticker/transitions/__init__.py` (auto-import block, lines ~267–277)

- [ ] **Step 1: Note the existing auto-import block before replacing it**

Read the current block (lines 266–277 in the source as of batch-3 branch):

```python
# --- Auto-import submodules so decorators execute ---
# ruff: noqa: E402
from led_ticker.transitions import (  # noqa: F401
    baseball,
    effects,
    nyancat,
    pacman,
    pokeball,
    push,
    sailor_moon,
    wipe,
)
```

- [ ] **Step 2: Replace with pkgutil auto-discovery**

Replace the block above (everything from `# --- Auto-import submodules` through the closing `)`) with:

```python
# --- Auto-import submodules so decorators execute ---
# pkgutil discovers every non-private .py file under transitions/ at
# import time so @register_transition decorators run automatically.
# Adding a new transitions/my_effect.py only requires the decorator —
# no manual entry here. Private modules (leading _) are excluded.
import importlib
import pkgutil

import led_ticker.transitions as _transitions_pkg

for _mod_info in pkgutil.iter_modules(
    _transitions_pkg.__path__,
    _transitions_pkg.__name__ + ".",
):
    if not _mod_info.name.rsplit(".", 1)[-1].startswith("_"):
        importlib.import_module(_mod_info.name)

del importlib, pkgutil, _transitions_pkg, _mod_info
```

The `del` at the end avoids leaking the loop variable and imports into the `transitions` namespace.

- [ ] **Step 3: Run the registry test**

```bash
python -m pytest tests/test_transitions.py::TestTransitionRegistry -v
```

Expected: `test_all_transitions_registered` PASSES (all 32 transitions still discovered). `test_register_duplicate_transition_raises` PASSES (from Task 1).

- [ ] **Step 4: Full suite**

```bash
make test
```

Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/transitions/__init__.py
git commit -m "feat: auto-discover transition submodules via pkgutil (S8)"
```

---

## Task 4: S6 — ColorProvider frame_invariant enforcement

**Problem:** A new provider author who copies `_ConstantColor` as a template and sets `frame_invariant = True` (when the new provider varies per-frame) ships a widget that freezes on the `_play_with_text` fast path with no error. The fix surfaces the mistake at class-definition time via `__init_subclass__`.

**Files:**
- Modify: `src/led_ticker/color_providers.py`
- Modify: `tests/test_color_providers.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_color_providers.py`:

```python
class TestColorProviderBase:
    def test_subclass_without_frame_invariant_raises(self):
        from led_ticker.color_providers import ColorProviderBase

        with pytest.raises(TypeError, match="frame_invariant"):

            class BadProvider(ColorProviderBase):
                per_char = False

                def color_for(self, frame, char_index, total_chars):
                    return None  # pragma: no cover

    def test_subclass_with_class_attribute_ok(self):
        from led_ticker.color_providers import ColorProviderBase

        class GoodProvider(ColorProviderBase):
            per_char = False
            frame_invariant = True

            def color_for(self, frame, char_index, total_chars):
                return None  # pragma: no cover

        # No error raised

    def test_subclass_with_property_ok(self):
        from led_ticker.color_providers import ColorProviderBase

        class DynamicProvider(ColorProviderBase):
            per_char = False

            @property
            def frame_invariant(self) -> bool:
                return False

            def color_for(self, frame, char_index, total_chars):
                return None  # pragma: no cover

        # No error raised

    def test_existing_providers_satisfy_base(self):
        from led_ticker.color_providers import (
            ColorProviderBase,
            ColorCycle,
            Gradient,
            Rainbow,
            Random,
            _ConstantColor,
        )
        from rgbmatrix.graphics import Color as GColor

        for cls in (_ConstantColor, Random, Rainbow, ColorCycle, Gradient):
            assert issubclass(cls, ColorProviderBase), f"{cls.__name__} not a subclass"
```

- [ ] **Step 2: Run to verify failures**

```bash
python -m pytest tests/test_color_providers.py::TestColorProviderBase -v
```

Expected: all four FAIL (`ColorProviderBase` doesn't exist yet).

- [ ] **Step 3: Add ColorProviderBase to color_providers.py**

In `src/led_ticker/color_providers.py`, insert after the module docstring's imports block (before `class ColorProvider(Protocol):`):

```python
class ColorProviderBase:
    """Optional base for ColorProvider implementations.

    Enforces that every subclass declares ``frame_invariant`` explicitly
    (as a class attribute or ``@property``) so the fast-path gate in
    ``_play_with_text`` / ``_play_with_two_row_text`` never silently
    freezes an animated widget. Class attributes (``frame_invariant = True``)
    and properties both satisfy the check.

    Lying *True-when-False* makes the widget freeze with no error; lying
    *False-when-True* wastes one per-tick redraw but renders correctly.
    Neither lie is detectable at runtime — the only protection is forcing
    authors to answer the question at class definition time.
    """

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        if "frame_invariant" not in cls.__dict__:
            raise TypeError(
                f"{cls.__name__} must define 'frame_invariant' as a class "
                "attribute or property. Set True if color_for() output is "
                "independent of the frame argument (constant, gradient); "
                "False if it varies per frame (rainbow, color_cycle)."
            )
```

- [ ] **Step 4: Make existing providers inherit from ColorProviderBase**

Change each class declaration in `src/led_ticker/color_providers.py`:

```python
# Before:
class _ConstantColor:
# After:
class _ConstantColor(ColorProviderBase):

# Before:
class Random:
# After:
class Random(ColorProviderBase):

# Before:
class Rainbow:
# After:
class Rainbow(ColorProviderBase):

# Before:
class ColorCycle:
# After:
class ColorCycle(ColorProviderBase):

# Before:
class Gradient:
# After:
class Gradient(ColorProviderBase):
```

All five classes already define `frame_invariant` as a class attribute, so `__init_subclass__` will pass for all of them.

- [ ] **Step 5: Run the new tests**

```bash
python -m pytest tests/test_color_providers.py::TestColorProviderBase -v
```

Expected: all four PASS.

- [ ] **Step 6: Full suite**

```bash
make test
```

Expected: all green.

- [ ] **Step 7: Commit**

```bash
git add src/led_ticker/color_providers.py tests/test_color_providers.py
git commit -m "feat: enforce frame_invariant on ColorProvider subclasses via __init_subclass__ (S6)"
```

---

## Task 5: S6 — BorderEffect frame_invariant enforcement

Same pattern as Task 4, applied to `BorderEffect` implementations.

**Files:**
- Modify: `src/led_ticker/borders.py`
- Modify: `tests/test_borders.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_borders.py`:

```python
class TestBorderEffectBase:
    def test_subclass_without_frame_invariant_raises(self):
        from led_ticker.borders import BorderEffectBase

        with pytest.raises(TypeError, match="frame_invariant"):

            class BadBorder(BorderEffectBase):
                def paint(self, canvas, frame_count):
                    pass  # pragma: no cover

    def test_subclass_with_class_attribute_ok(self):
        from led_ticker.borders import BorderEffectBase

        class GoodBorder(BorderEffectBase):
            frame_invariant = True

            def paint(self, canvas, frame_count):
                pass  # pragma: no cover

        # No error raised

    def test_subclass_with_property_ok(self):
        from led_ticker.borders import BorderEffectBase

        class DynamicBorder(BorderEffectBase):
            @property
            def frame_invariant(self) -> bool:
                return self._speed == 0

            def __init__(self, speed: int) -> None:
                self._speed = speed

            def paint(self, canvas, frame_count):
                pass  # pragma: no cover

        # No error raised

    def test_existing_borders_satisfy_base(self):
        from led_ticker.borders import (
            BorderEffectBase,
            ColorCycleBorder,
            ConstantBorder,
            RainbowChaseBorder,
        )

        for cls in (RainbowChaseBorder, ColorCycleBorder, ConstantBorder):
            assert issubclass(cls, BorderEffectBase), f"{cls.__name__} not a subclass"
```

- [ ] **Step 2: Run to verify failures**

```bash
python -m pytest tests/test_borders.py::TestBorderEffectBase -v
```

Expected: all four FAIL (`BorderEffectBase` doesn't exist yet).

- [ ] **Step 3: Add BorderEffectBase to borders.py**

In `src/led_ticker/borders.py`, insert after the module imports (before `class BorderEffect(Protocol):`):

```python
class BorderEffectBase:
    """Optional base for BorderEffect implementations.

    Enforces that every subclass declares ``frame_invariant`` explicitly
    (class attribute or ``@property``) so the fast-path predicate in
    image widgets cannot silently freeze an animated border. Analogous
    to ``ColorProviderBase`` — see its docstring for the full rationale.
    """

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        if "frame_invariant" not in cls.__dict__:
            raise TypeError(
                f"{cls.__name__} must define 'frame_invariant' as a class "
                "attribute or property. Set True if paint() output is "
                "frame-independent (ConstantBorder); False if it varies per "
                "frame (RainbowChaseBorder, ColorCycleBorder)."
            )
```

- [ ] **Step 4: Make existing border classes inherit from BorderEffectBase**

Change each class declaration in `src/led_ticker/borders.py`:

```python
# Before:
class RainbowChaseBorder:
# After:
class RainbowChaseBorder(BorderEffectBase):

# Before:
class ColorCycleBorder:
# After:
class ColorCycleBorder(BorderEffectBase):

# Before:
class ConstantBorder:
# After:
class ConstantBorder(BorderEffectBase):
```

All three define `frame_invariant` (two as class attributes, one as a `@property`), so `__init_subclass__` passes for all.

- [ ] **Step 5: Run the new tests**

```bash
python -m pytest tests/test_borders.py::TestBorderEffectBase -v
```

Expected: all four PASS.

- [ ] **Step 6: Full suite**

```bash
make test
```

Expected: all green.

- [ ] **Step 7: Commit**

```bash
git add src/led_ticker/borders.py tests/test_borders.py
git commit -m "feat: enforce frame_invariant on BorderEffect subclasses via __init_subclass__ (S6)"
```

---

## Task 6: S9 — Animation Protocol

Add a formal `Animation` Protocol to `animations.py` so contributors implementing new animations have a documented, structurally-checkable contract instead of reverse-engineering `Typewriter` from widget call sites.

**Batch 2 note:** Batch 2 (in its own worktree) removes `cursor_override` from `AnimationFrame` and also touches `animations.py`. This task does not touch `cursor_override` at all, so there will be a textual merge conflict on `animations.py` — but the semantic changes don't overlap. When rebasing or merging, keep both: batch 2's `cursor_override` removal AND batch 3's new `Animation` Protocol class.

**Files:**
- Modify: `src/led_ticker/animations.py`
- Modify: `tests/test_animations.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_animations.py`:

```python
class TestAnimationProtocol:
    def test_animation_protocol_exists(self):
        from led_ticker.animations import Animation
        assert Animation is not None

    def test_animation_is_runtime_checkable(self):
        from led_ticker.animations import Animation
        # @runtime_checkable lets isinstance work structurally
        from typing import runtime_checkable
        # If not runtime_checkable, isinstance raises TypeError
        from led_ticker.animations import Typewriter
        result = isinstance(Typewriter(), Animation)
        assert result is True

    def test_typewriter_satisfies_animation_protocol(self):
        from led_ticker.animations import Animation, Typewriter
        assert isinstance(Typewriter(), Animation)

    def test_plain_object_does_not_satisfy_animation(self):
        from led_ticker.animations import Animation

        class NotAnAnimation:
            pass

        assert not isinstance(NotAnAnimation(), Animation)
```

- [ ] **Step 2: Run to verify failures**

```bash
python -m pytest tests/test_animations.py::TestAnimationProtocol -v
```

Expected: `test_animation_protocol_exists` FAILS (no `Animation` in the module). Other tests also fail.

- [ ] **Step 3: Add Animation Protocol to animations.py**

In `src/led_ticker/animations.py`, add these imports at the top of the imports block:

```python
from typing import Protocol, runtime_checkable
```

Then insert the `Animation` Protocol class AFTER `AnimationFrame` and BEFORE `Typewriter`:

```python
@runtime_checkable
class Animation(Protocol):
    """Protocol for frame-aware animations on TickerMessage and image widgets.

    An animation controls how much of ``full_text`` is revealed each tick.
    The ``frame`` counter comes from the widget's ``_FrameAware`` counter
    for the ``"animation"`` effect slot — it ticks at ENGINE_TICK_MS
    cadence, pauses during transitions, and resets per-visit (unless the
    class sets ``restart_on_visit = False``).

    Implementing a new animation:

    1. Implement ``frame_for`` returning an ``AnimationFrame``.
    2. To reveal text progressively, return growing prefixes of ``full_text``
       in ``visible_text`` (typewriter pattern).
    3. To animate position instead, return ``full_text`` unchanged and set
       a cursor position via ... (currently ``AnimationFrame`` only carries
       ``visible_text``; a future ``cursor_override`` field would belong here).
    4. Register the style name in ``app._coerce_animation`` and add a test.

    See ``Typewriter`` for the canonical implementation.
    """

    def frame_for(
        self,
        frame: int,
        full_text: str,
        canvas_width: int,
        text_width: int,
    ) -> "AnimationFrame": ...
```

Note: the `"AnimationFrame"` string annotation avoids a forward-reference issue since `AnimationFrame` is defined before `Animation` in the file; you can use a plain reference if the dataclass is already defined above this class.

- [ ] **Step 4: Run the new tests**

```bash
python -m pytest tests/test_animations.py -v
```

Expected: all PASS (including the four new Protocol tests and the five existing `TestTypewriter` tests).

- [ ] **Step 5: Full suite**

```bash
make test
```

Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/animations.py tests/test_animations.py
git commit -m "feat: add Animation Protocol to animations.py (S9)"
```

---

## Self-Review Checklist

**Spec coverage:**
- [x] S7 (duplicate registry) — Tasks 1 (widget) + 1 (transition)
- [x] S8 (pkgutil auto-discover) — Task 3
- [x] M2 (frame_at kwargs documented) — Task 2
- [x] S6 (frame_invariant enforcement) — Tasks 4 + 5
- [x] S9/Animation Protocol — Task 6

**Placeholder scan:** All steps contain actual code. No "TBD" or "add appropriate handling."

**Type consistency:**
- `ColorProviderBase` defined in Task 4, referenced in Task 4 tests only.
- `BorderEffectBase` defined in Task 5, referenced in Task 5 tests only.
- `Animation` Protocol defined in Task 6; return type is `AnimationFrame` (existing dataclass).
- `frame_at` docstring in Task 2 matches the actual kwargs passed by `run_transition` (verified by reading lines 220–234 of `transitions/__init__.py`).

**Merge conflict note:** Tasks 1, 2, 3 all modify `transitions/__init__.py`. Execute in order (1 → 2 → 3) within the same session to avoid self-conflicts. Each step commits its change before the next step begins, so git history is clean.
