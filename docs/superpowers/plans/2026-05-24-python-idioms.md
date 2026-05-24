# Batch 6 (DR2): Python Idioms

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Branch safety:** Before doing ANY work, run `git branch --show-current`. If it prints `main`, stop immediately and ask for a worktree.

**Goal:** Type system tightening and Python 3.11+ idiom modernisation — concrete return types for coercion functions, parameterized generics, `match`/`case` for dispatch chains, `StrEnum` for validated string sets, a logged `except` block, and `attrs.field(converter=)` for color coercion.

**Architecture:** Six independent changes. Tasks 1–4 are type/annotation work with no behavior change. Task 5 adds a log line to a silent except block. Task 6 moves coercion timing in attrs — same result, earlier evaluation.

**Tech Stack:** Python 3.11+, attrs, StrEnum

**Run tests with:** `PYTHONPATH=tests/stubs uv run pytest -x -q`

**Type check with:** `uv run --extra dev pyright src/`

**Baseline:** Run both commands before starting. After all tasks, test count should be unchanged and typecheck should be no-worse than baseline (ideally fewer errors).

---

### Task 1: M3 — Tighten `-> Any` return types in coercion functions

`src/led_ticker/app/coercion.py` has `_coerce_color_provider() -> Any`, `_coerce_border() -> Any`, `_coerce_animation() -> Any`. `src/led_ticker/app/factories.py` has `_build_trans_obj(...) -> Any`. The base types for all of these exist in the package.

**Files:**
- Modify: `src/led_ticker/app/coercion.py`
- Modify: `src/led_ticker/app/factories.py`

- [ ] **Step 1: Check existing return type annotations**

```bash
grep -n "def _coerce_color_provider\|def _coerce_border\|def _coerce_animation\|def _build_trans_obj" src/led_ticker/app/coercion.py src/led_ticker/app/factories.py
```

Note current signatures.

- [ ] **Step 2: Update `_coerce_color_provider`**

```python
# Before:
def _coerce_color_provider(value: Any, context: str = "font_color") -> Any:

# After:
from led_ticker.color_providers import ColorProvider

def _coerce_color_provider(value: Any, context: str = "font_color") -> ColorProvider | None:
```

The function returns `None` when `value is None`. All other paths return a `ColorProvider` instance.

- [ ] **Step 3: Update `_coerce_border`**

```python
# Before:
def _coerce_border(value: Any) -> Any:

# After:
from led_ticker.borders import BorderEffect

def _coerce_border(value: Any) -> BorderEffect | None:
```

- [ ] **Step 4: Update `_coerce_animation`**

```python
# Before:
def _coerce_animation(value: Any) -> Any:

# After:
from led_ticker.animations import Animation

def _coerce_animation(value: Any) -> Animation | None:
```

- [ ] **Step 5: Update `_build_trans_obj` in `factories.py`**

```python
# Before:
def _build_trans_obj(trans_cfg: TransitionConfig) -> Any:

# After:
# Import the Transition protocol/base class — check what it's called:
# grep -n "class.*Transition\|Protocol" src/led_ticker/transitions/__init__.py | head -5

def _build_trans_obj(trans_cfg: TransitionConfig) -> Any:  # keep as Any if no base type exists
```

If there is no `Transition` base class or Protocol (check `transitions/__init__.py`), leave this one as `-> Any` and note it in a comment.

- [ ] **Step 6: Run typecheck and tests**

```bash
uv run --extra dev pyright src/
PYTHONPATH=tests/stubs uv run pytest -x -q
```

Expected: typecheck errors same or fewer; tests all pass.

- [ ] **Step 7: Commit**

```bash
git add src/led_ticker/app/coercion.py src/led_ticker/app/factories.py
git commit -m "fix: tighten -> Any return types to concrete types in coercion functions (M3)"
```

---

### Task 2: M4 — Parameterize bare `dict`/`list` annotations

`src/led_ticker/config.py:52–53` has `title: dict | None = None` and similar unparameterized generics. `src/led_ticker/color_lut.py:21,38` has `list | None` and bare `list`.

**Files:**
- Modify: `src/led_ticker/config.py`
- Modify: `src/led_ticker/color_lut.py`

- [ ] **Step 1: Find all bare dict/list annotations**

```bash
grep -n ": dict\b\|: list\b\|: dict |\|: list |" src/led_ticker/config.py src/led_ticker/color_lut.py
```

- [ ] **Step 2: Update `config.py`**

For each bare `dict` annotation, add the key/value type parameters based on what the field holds. Common cases:

```python
# Before:
title: dict | None = None

# After — widget config dicts are str-keyed with Any values:
title: dict[str, Any] | None = None
```

- [ ] **Step 3: Update `color_lut.py`**

```python
# Before (approximate):
_HUE_TABLE: list | None = None
table: list = []

# After:
_HUE_TABLE: list[tuple[int, int, int]] | None = None
table: list[tuple[int, int, int]] = attrs.Factory(list)
```

Read the actual field types from the file to confirm the tuple shape before applying.

- [ ] **Step 4: Run typecheck and tests**

```bash
uv run --extra dev pyright src/
PYTHONPATH=tests/stubs uv run pytest -x -q
```

Expected: typecheck same or fewer errors; tests all pass.

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/config.py src/led_ticker/color_lut.py
git commit -m "fix: parameterize bare dict/list annotations in config.py and color_lut.py (M4)"
```

---

### Task 3: M5 — Convert `if style ==` dispatch chains to `match`/`case`

`src/led_ticker/app/coercion.py:249–436` has long `if style == "rainbow": ... elif style == "constant": ...` chains in `_coerce_border` and `_coerce_animation`. `src/led_ticker/widgets/_image_fit.py` has a sequential `if` (not `elif`) in `apply_fit`.

**Files:**
- Modify: `src/led_ticker/app/coercion.py`
- Modify: `src/led_ticker/widgets/_image_fit.py`

- [ ] **Step 1: Convert `_coerce_border` dispatch chain**

Find the `if style == "..."` chain in `_coerce_border`. Replace with `match style:`:

```python
# Before (approximate):
if style == "rainbow":
    return RainbowChaseBorder(...)
elif style == "constant":
    return ConstantBorder(...)
else:
    raise ValueError(f"unknown border style: {style!r}")

# After:
match style:
    case "rainbow":
        return RainbowChaseBorder(...)
    case "constant":
        return ConstantBorder(...)
    case _:
        raise ValueError(f"unknown border style: {style!r}")
```

- [ ] **Step 2: Convert `_coerce_animation` dispatch chain**

Apply the same pattern to `_coerce_animation`:

```python
match style:
    case "typewriter":
        return Typewriter(...)
    case _:
        raise ValueError(f"unknown animation style: {style!r}")
```

- [ ] **Step 3: Fix `apply_fit` sequential `if` to `elif`**

In `src/led_ticker/widgets/_image_fit.py`, find `apply_fit`. It uses sequential `if` (not `elif`), meaning all branches are evaluated even after a match:

```python
# Before (approximate — sequential ifs):
def apply_fit(image, fit, canvas_w, canvas_h):
    if fit == "stretch":
        return _stretch(image, canvas_w, canvas_h)
    if fit == "crop":
        return _crop(image, canvas_w, canvas_h)
    if fit == "pillarbox":
        return _pillarbox(image, canvas_w, canvas_h)
    if fit == "letterbox":
        return _letterbox(image, canvas_w, canvas_h)

# After — use match/case OR at minimum change to elif:
def apply_fit(image, fit, canvas_w, canvas_h):
    match fit:
        case "stretch":
            return _stretch(image, canvas_w, canvas_h)
        case "crop":
            return _crop(image, canvas_w, canvas_h)
        case "pillarbox":
            return _pillarbox(image, canvas_w, canvas_h)
        case "letterbox":
            return _letterbox(image, canvas_w, canvas_h)
        case _:
            raise ValueError(f"unknown fit: {fit!r}")
```

Read the actual `apply_fit` before applying — the branches may not be simple returns. Preserve all logic exactly, only change the dispatch structure.

- [ ] **Step 4: Run tests**

```bash
PYTHONPATH=tests/stubs uv run pytest -x -q -k "border or animation or fit or coerce"
PYTHONPATH=tests/stubs uv run pytest -x -q
```

Expected: all pass. Behavior is unchanged.

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/app/coercion.py src/led_ticker/widgets/_image_fit.py
git commit -m "fix: convert if-elif dispatch chains to match/case in coercion.py and _image_fit.py (M5)"
```

---

### Task 4: M6 — Define `StrEnum` for validated string constant sets

`src/led_ticker/widgets/_image_fit.py` has `VALID_FITS`, `VALID_IMAGE_ALIGNS` as `frozenset[str]`. `src/led_ticker/widgets/_image_base.py` has `VALID_TEXT_ALIGNS`, `VALID_TEXT_VALIGNS`, `VALID_SCROLL_DIRECTIONS`. Replacing with `StrEnum` gives IDE autocompletion and exhaustiveness checking in `match` statements while remaining backward-compatible with string literals in TOML.

**Files:**
- Modify: `src/led_ticker/widgets/_image_fit.py`
- Modify: `src/led_ticker/widgets/_image_base.py`
- Modify: `src/led_ticker/app/coercion.py` (validation call sites)

- [ ] **Step 1: Read the current frozenset definitions and all usage sites**

```bash
grep -n "VALID_FITS\|VALID_IMAGE_ALIGNS" src/led_ticker/widgets/_image_fit.py
grep -n "VALID_TEXT_ALIGNS\|VALID_TEXT_VALIGNS\|VALID_SCROLL_DIRECTIONS" src/led_ticker/widgets/_image_base.py
grep -rn "VALID_FITS\|VALID_IMAGE_ALIGNS\|VALID_TEXT_ALIGNS\|VALID_TEXT_VALIGNS\|VALID_SCROLL" src/led_ticker/ --include="*.py" | grep -v "^src/led_ticker/widgets/_image"
```

Note all import sites in `coercion.py` and elsewhere.

- [ ] **Step 2: Define the StrEnum classes in `_image_fit.py`**

```python
from enum import StrEnum

class Fit(StrEnum):
    STRETCH = "stretch"
    CROP = "crop"
    PILLARBOX = "pillarbox"
    LETTERBOX = "letterbox"

class ImageAlign(StrEnum):
    LEFT = "left"
    CENTER = "center"
    RIGHT = "right"

# Keep frozenset aliases for any code that uses the old names — they
# can import the StrEnum now. Do NOT remove VALID_FITS etc. until all
# callers are updated (do that in a follow-up).
VALID_FITS: frozenset[str] = frozenset(Fit)
VALID_IMAGE_ALIGNS: frozenset[str] = frozenset(ImageAlign)
```

- [ ] **Step 3: Define the remaining StrEnum classes in `_image_base.py`**

```python
from enum import StrEnum

class TextAlign(StrEnum):
    SCROLL = "scroll"
    SCROLL_OVER = "scroll_over"
    LEFT = "left"
    CENTER = "center"
    RIGHT = "right"
    AUTO = "auto"

class TextValign(StrEnum):
    TOP = "top"
    CENTER = "center"
    BOTTOM = "bottom"

class ScrollDirection(StrEnum):
    LEFT = "left"
    RIGHT = "right"

# Keep frozenset aliases for backward compat
VALID_TEXT_ALIGNS: frozenset[str] = frozenset(TextAlign)
VALID_TEXT_VALIGNS: frozenset[str] = frozenset(TextValign)
VALID_SCROLL_DIRECTIONS: frozenset[str] = frozenset(ScrollDirection)
```

Read the actual current values from the frozensets before writing the enums — do not guess the valid string values.

- [ ] **Step 4: Update `validate_choice` call sites to use StrEnum (optional)**

The `frozenset` aliases make this backward-compatible without changing any `validate_choice` call sites. Skip this step unless the typecheck output identifies specific improvements to make.

- [ ] **Step 5: Run typecheck and tests**

```bash
uv run --extra dev pyright src/
PYTHONPATH=tests/stubs uv run pytest -x -q
```

Expected: tests all pass; typecheck same or fewer errors.

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/widgets/_image_fit.py src/led_ticker/widgets/_image_base.py
git commit -m "fix: add Fit/ImageAlign/TextAlign/TextValign/ScrollDirection StrEnum classes (M6)"
```

---

### Task 5: M7 — Add `logger.debug` to silent `except` block in `factories.py`

`src/led_ticker/app/factories.py:373–374` has a bare `except (ValueError, TypeError): pass` with no logging. In a widget factory, a misconfigured widget silently becomes `None` or is skipped with no diagnostic for the user.

**Files:**
- Modify: `src/led_ticker/app/factories.py:373-374`

- [ ] **Step 1: Find the silent except**

```bash
sed -n '368,380p' src/led_ticker/app/factories.py
```

It should look approximately like:

```python
try:
    widget = SomeWidgetClass(**resolved_cfg)
except (ValueError, TypeError):
    pass
```

- [ ] **Step 2: Add logging**

```python
# Before:
    except (ValueError, TypeError):
        pass

# After:
    except (ValueError, TypeError) as exc:
        logging.debug("skipping widget construction: %s", exc)
```

`logging.debug` keeps the behavior silent in production (not shown at default log level) but visible when debug logging is enabled — exactly the right level for a "this config field was wrong" diagnostic.

- [ ] **Step 3: Run tests**

```bash
PYTHONPATH=tests/stubs uv run pytest -x -q
```

Expected: all pass. No behavior change at default log level.

- [ ] **Step 4: Commit**

```bash
git add src/led_ticker/app/factories.py
git commit -m "fix: add logger.debug to silent except in _build_widget so errors are traceable (M7)"
```

---

### Task 6: M10 — Move `font_color` coercion from `__attrs_post_init__` to `attrs.field(converter=)`

`src/led_ticker/widgets/message.py` coerces `font_color` from raw TOML in `__attrs_post_init__`, meaning the attribute is briefly in an invalid intermediate state between `__init__` and post-init. Attrs `converter=` runs at construction time and makes the field always valid after `__init__`.

**Files:**
- Modify: `src/led_ticker/widgets/message.py`

- [ ] **Step 1: Read the current `font_color` field and `__attrs_post_init__`**

```bash
grep -n "font_color\|__attrs_post_init__" src/led_ticker/widgets/message.py | head -20
```

Find the `font_color` field definition and the coercion line in `__attrs_post_init__`.

- [ ] **Step 2: Apply the fix**

```python
# Before (approximate):
@attrs.define
class TickerMessage:
    text: str
    font_color: Any = None
    # ...

    def __attrs_post_init__(self) -> None:
        self.font_color = _coerce_color_provider(self.font_color)
        # ... other post-init work ...

# After:
from led_ticker.app.coercion import _coerce_color_provider

@attrs.define
class TickerMessage:
    text: str
    font_color: ColorProvider | None = attrs.field(
        default=None,
        converter=_coerce_color_provider,
    )
    # ...

    def __attrs_post_init__(self) -> None:
        # Remove the font_color coercion line; keep any other post-init work
        # ...
```

Note: `converter=` receives the raw value and returns the coerced value. If `_coerce_color_provider` takes a second `context=` argument, use `converter=lambda v: _coerce_color_provider(v, "font_color")`.

Read the full `__attrs_post_init__` before removing anything — only remove the `font_color` coercion line; leave everything else intact.

- [ ] **Step 3: Run tests**

```bash
PYTHONPATH=tests/stubs uv run pytest -x -q -k "message or ticker_message"
PYTHONPATH=tests/stubs uv run pytest -x -q
```

Expected: all pass. The behavior is identical — coercion now happens earlier (at construction) rather than in post-init.

- [ ] **Step 4: Commit**

```bash
git add src/led_ticker/widgets/message.py
git commit -m "fix: move font_color coercion from __attrs_post_init__ to attrs.field(converter=) (M10)"
```

---

## Self-Review

**Spec coverage:**

| Finding | Task | Status |
|---------|------|--------|
| M3 — `-> Any` return types | Task 1 | ✅ |
| M4 — bare dict/list annotations | Task 2 | ✅ |
| M5 — if-elif dispatch chains | Task 3 | ✅ |
| M6 — StrEnum for validated string sets | Task 4 | ✅ |
| M7 — silent except in _build_widget | Task 5 | ✅ |
| M10 — font_color coercion in post_init | Task 6 | ✅ |

**Placeholder scan:** Task 1 notes "if no Transition base class exists, leave as -> Any" — this is intentional and documented. Task 4 notes "read actual frozenset values" — required at execution time. Task 6 notes "read full __attrs_post_init__ before removing" — standard caution, not a gap.

**Order note:** All 6 tasks are independent. Task 4 (StrEnum) is the largest because it touches multiple files; do it last if time is limited so the type-annotation tasks (1–3) land first.
