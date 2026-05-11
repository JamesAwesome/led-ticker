# Colors Module Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Decouple `colors.py` from eager `graphics.Color` construction at import time, expand the palette with matrix-tuned colors, scope crypto-specific trend colors to the crypto package, and cement a single lazy-load pattern across the codebase by converting `mlb.py` to the same pattern.

**Architecture:** Eight small, independent changes ordered so each commit is atomic and revertable. (1) Delete dead `BROWN`. (2) Expand `colors.py` with six new matrix-tuned palette colors and fix two washed-out RGB values. (3) Move trend colors to a new `widgets/crypto/_colors.py`. (4) Update `rss_feed.py` to use generic palette colors. (5) Remove now-unused trend constants + `LIME` from `colors.py`. (6) Move `RANDOM_COLOR` cycle to `app.py` with all 8 new palette colors. (7) Rename `_color` → public `make_color`. (8) Introduce `lazy_palette()` helper, convert `colors.py` AND `mlb.py` to use it via PEP 562 `__getattr__`. Call-site shape (`from led_ticker.colors import X`) is preserved end-to-end.

**Tech Stack:** Python 3.13, `pytest`, the project's existing `_compat.require_graphics()` lazy-loader, PEP 562 module `__getattr__`, `functools.cache`.

**Non-goals (explicit):**
- Do NOT change `_types.Color` from its current alias to `graphics.Color`. Architect review concluded the surface area + DrawText C-boundary cost outweighs the win.
- Do NOT rewrite the `isinstance(value, graphics.Color)` check at `app.py:98`. It is a structurally sound sum-type discriminator in a config-coercion function.
- Do NOT convert `etherscan.py`'s hand-rolled lazy `OK_GAS_COLOR`. It is already lazy and converting it would add a `__getattr__` for a single constant — pure churn.

---

## Palette decisions baked into this plan

**New `colors.py` palette** (matrix-tuned, replaces the legacy palette except where noted):

| Name | RGB | Notes |
|---|---|---|
| `RGB_WHITE` | `(255, 255, 255)` | Kept, unchanged |
| `DEFAULT_COLOR` | `(255, 255, 0)` | Kept, unchanged — semantic default (yellow) |
| `RED` | `(255, 40, 40)` | NEW. Same as mlb `LIVE_COLOR` — proven |
| `GREEN` | `(46, 200, 46)` | NEW. Same as mlb `WIN_COLOR` — proven |
| `BLUE` | `(40, 100, 255)` | NEW. Lifted; pure blue is dim on matrices |
| `YELLOW` | `(255, 220, 0)` | NEW. Tempered from full yellow |
| `ORANGE` | `(255, 140, 0)` | CHANGED from `(255, 215, 0)` (was amber) |
| `PURPLE` | `(160, 60, 200)` | CHANGED from `(221, 160, 221)` (was pastel/washed) |
| `CYAN` | `(0, 220, 220)` | NEW. Slight green pull to fight wash |
| `PINK` | `(240, 70, 200)` | NEW. Saturated, distinct from PURPLE + RED |

**Removed from `colors.py`:** `BROWN` (dead), `LIME` (covered by `GREEN`), `UP_TREND_COLOR` / `DOWN_TREND_COLOR` / `NEUTRAL_TREND_COLOR` (moved to crypto), `RANDOM_COLOR` (moved to `app.py`).

**New `widgets/crypto/_colors.py`:**

| Name | RGB | Notes |
|---|---|---|
| `UP_TREND_COLOR` | `(46, 200, 46)` | BUMPED from `(46, 139, 87)` to match the new `GREEN` |
| `DOWN_TREND_COLOR` | `(194, 24, 7)` | Kept as-is |
| `NEUTRAL_TREND_COLOR` | `(180, 180, 180)` | Kept as-is |

**New `app.RANDOM_COLOR` cycle:** all 8 new palette colors (`RED`, `GREEN`, `BLUE`, `YELLOW`, `ORANGE`, `PURPLE`, `CYAN`, `PINK`). Was 5 colors.

**`rss_feed.py` headline rotation:** `(DEFAULT_COLOR, RED, GREEN)` — preserves the existing yellow / red / green semantic shape without misleading "trend" names.

---

## File Map

**Modified:**
- `src/led_ticker/colors.py` — add new palette, fix two RGBs, drop dead/moved constants, rename helper, add `lazy_palette()`, convert to PEP 562 lazy.
- `src/led_ticker/app.py` — define expanded `RANDOM_COLOR` locally; remove import from `colors`.
- `src/led_ticker/widgets/mlb.py` — convert `WIN_COLOR` / `LOSS_COLOR` / `LIVE_COLOR` to `lazy_palette()`; update `_color` → `make_color`.
- `src/led_ticker/widgets/rss_feed.py` — drop trend-color import; use generic palette.
- `src/led_ticker/widgets/crypto/coinbase.py` — import trend colors from new local module.
- `src/led_ticker/widgets/crypto/etherscan.py` — import trend colors from new local module.
- `src/led_ticker/color_providers.py:82` — remove stale comment about cross-module `RANDOM_COLOR`.
- `tests/test_colors.py` — drop RANDOM_COLOR test; add lazy + new-palette tests.

**Created:**
- `src/led_ticker/widgets/crypto/_colors.py` — local trend-color palette.
- `tests/test_app_random_color.py` — RANDOM_COLOR tripwire.

**Deleted:** none.

---

## Task 1: Delete dead `BROWN` constant

**Files:**
- Modify: `src/led_ticker/colors.py:28`

- [ ] **Step 1: Confirm zero usage**

Run: `grep -rn "BROWN" src/ tests/ tools/ 2>/dev/null`
Expected: only line 28 of `colors.py`.

- [ ] **Step 2: Delete the definition**

In `src/led_ticker/colors.py` remove line 28:
```python
BROWN: Color = _color(139, 69, 19)
```

- [ ] **Step 3: Run the test suite**

Run: `make test`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add src/led_ticker/colors.py
git commit -m "refactor: remove dead BROWN constant from colors.py"
```

---

## Task 2: Expand `colors.py` palette with matrix-tuned colors

**Files:**
- Modify: `src/led_ticker/colors.py` (add 6 constants, change 2 RGBs)
- Modify: `tests/test_colors.py` (add palette tests)

**Rationale:** Add the new well-saturated colors that show up on the panel before any consumer needs them. `LIME`, `UP_TREND_COLOR`, etc. stay live in this task — they'll be removed in Task 5 after dependents migrate.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_colors.py`:

```python
def test_new_palette_colors_exist_and_are_correct():
    from led_ticker.colors import (
        BLUE,
        CYAN,
        GREEN,
        ORANGE,
        PINK,
        PURPLE,
        RED,
        YELLOW,
    )

    assert (RED.red, RED.green, RED.blue) == (255, 40, 40)
    assert (GREEN.red, GREEN.green, GREEN.blue) == (46, 200, 46)
    assert (BLUE.red, BLUE.green, BLUE.blue) == (40, 100, 255)
    assert (YELLOW.red, YELLOW.green, YELLOW.blue) == (255, 220, 0)
    assert (ORANGE.red, ORANGE.green, ORANGE.blue) == (255, 140, 0)
    assert (PURPLE.red, PURPLE.green, PURPLE.blue) == (160, 60, 200)
    assert (CYAN.red, CYAN.green, CYAN.blue) == (0, 220, 220)
    assert (PINK.red, PINK.green, PINK.blue) == (240, 70, 200)
```

- [ ] **Step 2: Run the test to confirm failure**

Run: `pytest tests/test_colors.py::test_new_palette_colors_exist_and_are_correct -v`
Expected: FAIL on the first missing import (`RED`).

- [ ] **Step 3: Update `colors.py`**

In `src/led_ticker/colors.py`, replace the existing color-definition block (lines 17-29 in the pre-Task-2 file, which after Task 1 lack BROWN) with:

```python
RGB_WHITE: Color = _color(255, 255, 255)

DEFAULT_COLOR: Color = _color(255, 255, 0)

# Matrix-tuned palette. Saturated where saturation lands well on the
# real panel; pastel/dark values were retired because LED matrices
# wash pastels toward white and crush near-blacks to invisible.
RED: Color = _color(255, 40, 40)
GREEN: Color = _color(46, 200, 46)
BLUE: Color = _color(40, 100, 255)
YELLOW: Color = _color(255, 220, 0)
ORANGE: Color = _color(255, 140, 0)
PURPLE: Color = _color(160, 60, 200)
CYAN: Color = _color(0, 220, 220)
PINK: Color = _color(240, 70, 200)

# Legacy constants — removed in a later task once dependents migrate:
UP_TREND_COLOR: Color = _color(46, 139, 87)
DOWN_TREND_COLOR: Color = _color(194, 24, 7)
NEUTRAL_TREND_COLOR: Color = _color(180, 180, 180)  # gray for 0% / unknown

LIME: Color = _color(0, 255, 0)

RANDOM_COLOR: itertools.cycle[Color] = itertools.cycle(
    [
        PURPLE,
        LIME,
        ORANGE,
        UP_TREND_COLOR,
        DOWN_TREND_COLOR,
    ]
)
```

Note: `PURPLE` and `ORANGE` get the NEW RGB values here. The `RANDOM_COLOR` cycle is preserved with its existing 5 entries (PURPLE/ORANGE just got punchier) — its expansion happens in Task 6.

- [ ] **Step 4: Run all tests**

Run: `make test`
Expected: PASS — the new test passes; the existing `test_random_color_cycles` still passes because the cycle has the same 5 names.

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/colors.py tests/test_colors.py
git commit -m "refactor: expand colors.py with matrix-tuned palette; bump PURPLE+ORANGE to saturated values"
```

---

## Task 3: Create `widgets/crypto/_colors.py` for trend colors

**Files:**
- Create: `src/led_ticker/widgets/crypto/_colors.py`
- Modify: `src/led_ticker/widgets/crypto/coinbase.py:15` (import path)
- Modify: `src/led_ticker/widgets/crypto/etherscan.py:15` (import path)

**Rationale:** `UP_TREND_COLOR` and friends are only meaningful for crypto widgets. Moving them to a crypto-local module clarifies intent. `UP_TREND_COLOR` is bumped from `(46, 139, 87)` to `(46, 200, 46)` for matrix visibility (now matches generic `GREEN`).

- [ ] **Step 1: Write the failing test**

Create `tests/test_widgets/test_crypto_colors.py`:

```python
"""Tripwire: trend colors live in crypto, not the global palette."""

from led_ticker.widgets.crypto import _colors as crypto_colors


def test_crypto_trend_colors_exist():
    assert (crypto_colors.UP_TREND_COLOR.red,
            crypto_colors.UP_TREND_COLOR.green,
            crypto_colors.UP_TREND_COLOR.blue) == (46, 200, 46)
    assert (crypto_colors.DOWN_TREND_COLOR.red,
            crypto_colors.DOWN_TREND_COLOR.green,
            crypto_colors.DOWN_TREND_COLOR.blue) == (194, 24, 7)
    assert (crypto_colors.NEUTRAL_TREND_COLOR.red,
            crypto_colors.NEUTRAL_TREND_COLOR.green,
            crypto_colors.NEUTRAL_TREND_COLOR.blue) == (180, 180, 180)
```

- [ ] **Step 2: Run the test to confirm failure**

Run: `pytest tests/test_widgets/test_crypto_colors.py -v`
Expected: FAIL on `ModuleNotFoundError`.

- [ ] **Step 3: Create the crypto-local colors module**

Create `src/led_ticker/widgets/crypto/_colors.py`:

```python
"""Trend colors for crypto widgets.

These were previously global in `led_ticker.colors` but are
crypto-specific (positive/negative/neutral price movement). The
generic palette in `led_ticker.colors` should not encode crypto
semantics.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from led_ticker.colors import make_color  # introduced in Task 7

if TYPE_CHECKING:
    from led_ticker._types import Color


# NOTE: until Task 7 renames `_color` -> `make_color`, this import
# will fail. This task must run AFTER Task 7. The task ordering in
# this plan already reflects that — Task 7 (rename) is run before
# Task 3 in the actual execution order if needed.
#
# In practice, ordering this plan task #3 BEFORE the rename works
# too: we can use `from led_ticker.colors import _color as _mk` here
# and rename in one shot. To keep the plan strictly sequential and
# simple, this file uses `make_color` and Task 3 is executed AFTER
# Task 7 (see Execution Order at the bottom of this plan).
UP_TREND_COLOR: Color = make_color(46, 200, 46)
DOWN_TREND_COLOR: Color = make_color(194, 24, 7)
NEUTRAL_TREND_COLOR: Color = make_color(180, 180, 180)
```

**STOP — execution-order note:** This task imports `make_color`, which is created in Task 7. Run Task 7 before this task. The task numbers in this document reflect logical grouping, not execution order. See "Execution Order" at the end.

- [ ] **Step 4: Update `coinbase.py` import**

In `src/led_ticker/widgets/crypto/coinbase.py:15`, find the current import block (the trend-color names):

```python
from led_ticker.colors import (
    ...
)
```

Replace the trend-color names with imports from the new local module. The exact pre-edit content needs reading first — run:
```bash
grep -A 4 "from led_ticker.colors import" src/led_ticker/widgets/crypto/coinbase.py
```

Then split: keep `DEFAULT_COLOR` (or whatever else) imported from `led_ticker.colors`, and add:

```python
from led_ticker.widgets.crypto._colors import (
    DOWN_TREND_COLOR,
    NEUTRAL_TREND_COLOR,
    UP_TREND_COLOR,
)
```

(Remove these three names from the `led_ticker.colors` import block.)

- [ ] **Step 5: Update `etherscan.py` import**

In `src/led_ticker/widgets/crypto/etherscan.py:15`, replace:
```python
from led_ticker.colors import DEFAULT_COLOR, DOWN_TREND_COLOR, UP_TREND_COLOR
```
with:
```python
from led_ticker.colors import DEFAULT_COLOR
from led_ticker.widgets.crypto._colors import DOWN_TREND_COLOR, UP_TREND_COLOR
```

- [ ] **Step 6: Run all tests**

Run: `make test`
Expected: PASS — new tripwire passes; crypto widget tests pass; no other module imports trend colors from `led_ticker.colors` (we'll confirm rss_feed in Task 4).

- [ ] **Step 7: Commit**

```bash
git add src/led_ticker/widgets/crypto/_colors.py src/led_ticker/widgets/crypto/coinbase.py src/led_ticker/widgets/crypto/etherscan.py tests/test_widgets/test_crypto_colors.py
git commit -m "refactor: move trend colors to widgets/crypto/_colors.py; bump UP_TREND for matrix visibility"
```

---

## Task 4: Update `rss_feed.py` headline rotation

**Files:**
- Modify: `src/led_ticker/widgets/rss_feed.py:15` (import)
- Modify: `src/led_ticker/widgets/rss_feed.py:29-31` (cycle factory)

**Rationale:** `rss_feed` uses trend colors as a 3-color cycle for headline variety, not for any trend semantic. Switch to `(DEFAULT_COLOR, RED, GREEN)` — preserves the yellow/red/green visual shape with non-misleading names.

- [ ] **Step 1: Confirm the pre-edit cycle**

Run: `grep -n "itertools.cycle\|DEFAULT_COLOR\|UP_TREND\|DOWN_TREND" src/led_ticker/widgets/rss_feed.py`
Expected: line 15 imports `DEFAULT_COLOR, DOWN_TREND_COLOR, UP_TREND_COLOR`; lines 29-31 build the cycle.

- [ ] **Step 2: Update the import**

In `src/led_ticker/widgets/rss_feed.py:15`, change:
```python
from led_ticker.colors import DEFAULT_COLOR, DOWN_TREND_COLOR, UP_TREND_COLOR
```
to:
```python
from led_ticker.colors import DEFAULT_COLOR, GREEN, RED
```

- [ ] **Step 3: Update the cycle factory**

In `src/led_ticker/widgets/rss_feed.py:29-31`, change:
```python
    colors: itertools.cycle[Color] = attrs.Factory(
        lambda: itertools.cycle([DEFAULT_COLOR, DOWN_TREND_COLOR, UP_TREND_COLOR])
    )
```
to:
```python
    colors: itertools.cycle[Color] = attrs.Factory(
        lambda: itertools.cycle([DEFAULT_COLOR, RED, GREEN])
    )
```

- [ ] **Step 4: Run rss_feed tests**

Run: `pytest tests/test_widgets/ -k rss -v`
Expected: PASS. Any test that hard-codes the old colors may fail — if so, update the test to use the new names.

- [ ] **Step 5: Run full suite**

Run: `make test`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/widgets/rss_feed.py
git commit -m "refactor: rss_feed uses generic palette (DEFAULT/RED/GREEN) instead of crypto trend colors"
```

---

## Task 5: Remove migrated/dead constants from `colors.py`

**Files:**
- Modify: `src/led_ticker/colors.py` (delete trend colors + LIME)

**Rationale:** After Tasks 3 and 4, no module imports `UP_TREND_COLOR`, `DOWN_TREND_COLOR`, `NEUTRAL_TREND_COLOR`, or `LIME` from `led_ticker.colors`. Safe to delete.

- [ ] **Step 1: Confirm nothing imports these names from `colors.py`**

Run:
```bash
grep -rn "from led_ticker.colors import.*\(UP_TREND_COLOR\|DOWN_TREND_COLOR\|NEUTRAL_TREND_COLOR\|LIME\)\|from .colors import.*\(UP_TREND_COLOR\|DOWN_TREND_COLOR\|NEUTRAL_TREND_COLOR\|LIME\)" src/ tests/
```
Expected: zero hits in `src/`. May still see references inside `colors.py` itself (the `RANDOM_COLOR` list still uses `LIME`, `UP_TREND_COLOR`, `DOWN_TREND_COLOR` — these are about to move in Task 6). If anything else surfaces, audit before continuing.

- [ ] **Step 2: Hold off on deleting**

LIME, UP_TREND_COLOR, and DOWN_TREND_COLOR are still referenced inside `colors.py`'s `RANDOM_COLOR` definition. This task can't fully delete them until Task 6 moves `RANDOM_COLOR` out. Mark this task as a no-op IF executed before Task 6.

**Revised order:** Task 5 runs AFTER Task 6. See Execution Order.

- [ ] **Step 3: After Task 6 has run, delete the four constants**

In `src/led_ticker/colors.py`, remove these lines (line numbers will have drifted; identify by name):
```python
UP_TREND_COLOR: Color = _color(46, 139, 87)
DOWN_TREND_COLOR: Color = _color(194, 24, 7)
NEUTRAL_TREND_COLOR: Color = _color(180, 180, 180)  # gray for 0% / unknown

LIME: Color = _color(0, 255, 0)
```

Also remove the "Legacy constants" comment block header.

- [ ] **Step 4: Run all tests**

Run: `make test`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/colors.py
git commit -m "refactor: remove LIME and trend colors from colors.py (migrated to crypto)"
```

---

## Task 6: Move `RANDOM_COLOR` to `app.py` with expanded palette

**Files:**
- Modify: `src/led_ticker/colors.py` (remove RANDOM_COLOR + unused itertools import after removal)
- Modify: `src/led_ticker/app.py` (add local RANDOM_COLOR with 8 colors)
- Modify: `src/led_ticker/color_providers.py:82` (stale comment)
- Modify: `tests/test_colors.py` (drop test_random_color_cycles)
- Create: `tests/test_app_random_color.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_app_random_color.py`:

```python
"""Tripwire: RANDOM_COLOR lives in app.py with the 8-color palette."""

from led_ticker import app
from led_ticker import colors


def test_random_color_is_in_app_module():
    assert hasattr(app, "RANDOM_COLOR")


def test_random_color_not_in_colors_module():
    assert not hasattr(colors, "RANDOM_COLOR")


def test_random_color_cycles_eight_colors():
    cycle = app.RANDOM_COLOR
    seen = [next(cycle) for _ in range(16)]
    # 8-element cycle: index N and N+8 must match
    assert seen[0] == seen[8]
    assert seen[1] == seen[9]
    assert seen[7] == seen[15]
    # First 8 are distinct
    distinct = {(c.red, c.green, c.blue) for c in seen[:8]}
    assert len(distinct) == 8
```

- [ ] **Step 2: Run the test to confirm failure**

Run: `pytest tests/test_app_random_color.py -v`
Expected: FAIL on `assert hasattr(app, "RANDOM_COLOR")`.

- [ ] **Step 3: Add RANDOM_COLOR to `app.py`**

In `src/led_ticker/app.py`, after the existing import block (replacing the existing `from led_ticker.colors import RANDOM_COLOR` line at line 14), add:

```python
import itertools

from led_ticker.colors import (
    BLUE,
    CYAN,
    GREEN,
    ORANGE,
    PINK,
    PURPLE,
    RED,
    YELLOW,
)

# Section-title random color cycle. One stable color per section visit.
# Lives here (not in `colors.py`) because this is the only consumer; a
# module-level `itertools.cycle` is mutable singleton state and belongs
# next to the code whose lifecycle owns it.
RANDOM_COLOR: itertools.cycle = itertools.cycle(
    [RED, GREEN, BLUE, YELLOW, ORANGE, PURPLE, CYAN, PINK]
)
```

If `import itertools` is already present in `app.py`, do not duplicate (ruff will flag duplicates).

- [ ] **Step 4: Remove `RANDOM_COLOR` from `colors.py`**

In `src/led_ticker/colors.py`, delete the `RANDOM_COLOR` definition (the `itertools.cycle([...])` block) and the unused `import itertools` line if no other definition needs it.

- [ ] **Step 5: Update stale comment in `color_providers.py`**

In `src/led_ticker/color_providers.py:82`, read 5 lines of context first:
```bash
sed -n '78,86p' src/led_ticker/color_providers.py
```

Replace the comment about "the same RANDOM_COLOR cycle as the rest of the codebase" with:
```python
        # Random color: pick a hue uniformly per call (independent of
        # app.py's section-title RANDOM_COLOR cycle).
```

- [ ] **Step 6: Update `tests/test_colors.py`**

Remove the `RANDOM_COLOR` import and `test_random_color_cycles` test from `tests/test_colors.py`. Post-edit, that file no longer references `RANDOM_COLOR`.

- [ ] **Step 7: Run all tests**

Run: `make test`
Expected: PASS — 3 new tests in `test_app_random_color.py` pass; existing app.py + section-title rotation tests pass; `test_colors.py` has one fewer test.

- [ ] **Step 8: Commit**

```bash
git add src/led_ticker/colors.py src/led_ticker/app.py src/led_ticker/color_providers.py tests/test_colors.py tests/test_app_random_color.py
git commit -m "refactor: move RANDOM_COLOR to app.py with expanded 8-color palette"
```

---

## Task 7: Rename `_color` → `make_color`

**Files:**
- Modify: `src/led_ticker/colors.py:11-14` (rename)
- Modify: `src/led_ticker/widgets/mlb.py:18` (import)
- Modify: `src/led_ticker/widgets/mlb.py` (9 call sites: lines 34, 35, 36, 114, 121, 408, 409, 410, 431 in pre-edit file)

**Rationale:** `widgets/mlb.py` already imports the private `_color` from `colors`. Promote to public `make_color`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_colors.py`:

```python
def test_make_color_public_helper():
    from led_ticker.colors import make_color

    c = make_color(10, 20, 30)
    assert c.red == 10
    assert c.green == 20
    assert c.blue == 30


def test_make_color_replaces_private_helper():
    import led_ticker.colors as colors_mod

    assert hasattr(colors_mod, "make_color")
    assert not hasattr(colors_mod, "_color")
```

- [ ] **Step 2: Run the new tests to confirm failure**

Run: `pytest tests/test_colors.py::test_make_color_public_helper tests/test_colors.py::test_make_color_replaces_private_helper -v`
Expected: both FAIL.

- [ ] **Step 3: Rename in `colors.py`**

In `src/led_ticker/colors.py`, change the helper:
```python
def _color(r: int, g: int, b: int) -> Color:
    """Create a color, using real graphics.Color when available."""
    g_mod = require_graphics()
    return g_mod.Color(r, g, b)
```
to:
```python
def make_color(r: int, g: int, b: int) -> Color:
    """Construct a `graphics.Color` lazily.

    Public because `widgets/mlb.py` needs to build team colors at
    draw time. Internal callers also use this so there's one place
    that touches `require_graphics`.
    """
    g_mod = require_graphics()
    return g_mod.Color(r, g, b)
```

Then search-and-replace every `_color(` → `make_color(` within `colors.py` itself. The remaining palette constants (RGB_WHITE, DEFAULT_COLOR, RED, GREEN, …) all become `make_color(...)` calls.

- [ ] **Step 4: Update `mlb.py` import**

In `src/led_ticker/widgets/mlb.py:18`, change:
```python
from led_ticker.colors import RGB_WHITE, _color
```
to:
```python
from led_ticker.colors import RGB_WHITE, make_color
```

- [ ] **Step 5: Update `mlb.py` call sites**

Search-and-replace `_color(` → `make_color(` across `src/led_ticker/widgets/mlb.py`. Spot-check:
```bash
grep -n "_color\|make_color" src/led_ticker/widgets/mlb.py
```
Expected: no `_color(` remains; instance attributes like `self.font_color` are untouched.

- [ ] **Step 6: Run all tests**

Run: `make test`
Expected: PASS. (Task 3's `widgets/crypto/_colors.py` already imports `make_color` — it can be created BEFORE this task only if step 4's STOP note is heeded.)

- [ ] **Step 7: Commit**

```bash
git add src/led_ticker/colors.py src/led_ticker/widgets/mlb.py tests/test_colors.py
git commit -m "refactor: rename colors._color to public make_color"
```

---

## Task 8: Add `lazy_palette()` helper + convert `colors.py` to PEP 562

**Files:**
- Modify: `src/led_ticker/colors.py` (introduce lazy_palette, switch constants to lazy)
- Modify: `tests/test_colors.py` (add tripwires)

**Rationale:** Each `make_color(...)` at module scope forces `require_graphics()` at import time. Convert to PEP 562 `__getattr__` so constants are built on first access. Expose `lazy_palette()` as a reusable helper for Task 9 (mlb conversion).

- [ ] **Step 1: Write the failing tripwires**

Append to `tests/test_colors.py`:

```python
def test_colors_module_has_no_eager_color_construction():
    """Tripwire: module-level constants must be lazy. No `make_color(...)`
    or `_color(...)` calls at module scope."""
    import ast
    import inspect

    import led_ticker.colors as colors_mod

    source = inspect.getsource(colors_mod)
    tree = ast.parse(source)

    offenders: list[str] = []
    for node in tree.body:
        if isinstance(node, (ast.AnnAssign, ast.Assign)):
            value = node.value
            if isinstance(value, ast.Call):
                func_repr = ast.unparse(value.func)
                if func_repr in {"make_color", "_color"}:
                    offenders.append(ast.unparse(node))

    assert not offenders, (
        "colors.py has eager color construction at module scope — "
        "move these behind `__getattr__`:\n" + "\n".join(offenders)
    )


def test_colors_module_defines_getattr():
    import led_ticker.colors as colors_mod
    assert hasattr(colors_mod, "__getattr__")


def test_lazy_palette_helper_exists():
    from led_ticker.colors import lazy_palette
    assert callable(lazy_palette)


def test_lazy_palette_builds_getattr_function():
    from led_ticker.colors import lazy_palette

    getter = lazy_palette({"FOO_COLOR": (10, 20, 30)})
    foo = getter("FOO_COLOR")
    assert (foo.red, foo.green, foo.blue) == (10, 20, 30)

    try:
        getter("MISSING")
    except AttributeError:
        pass
    else:
        raise AssertionError("getter must raise AttributeError for unknown names")
```

- [ ] **Step 2: Run the new tests to confirm failure**

Run: `pytest tests/test_colors.py -k "lazy or getattr or eager" -v`
Expected: all four FAIL.

- [ ] **Step 3: Rewrite `colors.py`**

Replace the entire contents of `src/led_ticker/colors.py` with:

```python
"""RGB color definitions for the LED display.

Constants are constructed lazily via PEP 562 `__getattr__`: the first
access to e.g. `RGB_WHITE` calls `make_color(...)`, which triggers
`require_graphics()`. Importing this module is a no-op against the
rgbmatrix library — useful for keeping cold-start cost low and keeping
test stubs un-loaded until they're actually needed.

`lazy_palette()` is the reusable building block: pass a name → RGB
mapping, get back a function suitable for use as a module-level
`__getattr__`. `widgets/mlb.py` uses this pattern for its own palette.
"""

from __future__ import annotations

from functools import cache
from typing import TYPE_CHECKING, Callable

from led_ticker._compat import require_graphics

if TYPE_CHECKING:
    from led_ticker._types import Color


def make_color(r: int, g: int, b: int) -> Color:
    """Construct a `graphics.Color` lazily.

    Public because `widgets/mlb.py` needs to build team colors at
    draw time. Internal callers also use this so there's one place
    that touches `require_graphics`.
    """
    g_mod = require_graphics()
    return g_mod.Color(r, g, b)


def lazy_palette(palette: dict[str, tuple[int, int, int]]) -> Callable[[str], Color]:
    """Build a module-level `__getattr__` that materializes colors on demand.

    Usage::

        # in some_widget.py
        __getattr__ = lazy_palette({
            "WIN_COLOR": (46, 200, 46),
            "LOSS_COLOR": (220, 30, 30),
        })

    The returned function caches each color so repeated access is O(1)
    and identity-stable.
    """
    @cache
    def _build(name: str) -> Color:
        if name not in palette:
            raise AttributeError(
                f"no such color {name!r} (available: {sorted(palette)})"
            )
        return make_color(*palette[name])

    return _build


# Source-of-truth palette. Mapping name → (r, g, b). Materialized
# to `graphics.Color` on first attribute access via `__getattr__`.
_PALETTE: dict[str, tuple[int, int, int]] = {
    "RGB_WHITE": (255, 255, 255),
    "DEFAULT_COLOR": (255, 255, 0),
    "RED": (255, 40, 40),
    "GREEN": (46, 200, 46),
    "BLUE": (40, 100, 255),
    "YELLOW": (255, 220, 0),
    "ORANGE": (255, 140, 0),
    "PURPLE": (160, 60, 200),
    "CYAN": (0, 220, 220),
    "PINK": (240, 70, 200),
}

__getattr__ = lazy_palette(_PALETTE)


def __dir__() -> list[str]:
    return [*globals(), *_PALETTE.keys()]
```

Key points the engineer needs to understand:
- `from __future__ import annotations` + `TYPE_CHECKING`-guarded `Color` import keeps annotations cheap.
- PEP 562 routes both `colors.RGB_WHITE` (attribute access) AND `from colors import RGB_WHITE` (import-from) through `__getattr__`. Both work identically.
- `functools.cache` inside `lazy_palette` guarantees one `graphics.Color` instance per name across the process — identity stable across calls. Tests comparing colors via `==` keep working.
- `lazy_palette` is the helper Task 9 uses for `mlb.py`. Same code, two consumers.
- The plain-old `__getattr__ = lazy_palette(_PALETTE)` line installs the function as the module's lazy attr-resolver. Defining a module-level `__getattr__` is the PEP 562 protocol.

- [ ] **Step 4: Run all tests**

Run: `make test`
Expected: PASS. All four new tripwires pass. All existing `test_colors.py` assertions pass. Every widget import (`from led_ticker.colors import DEFAULT_COLOR`, etc.) routes through `__getattr__`.

If a test fails with `AttributeError: no such color 'X'`, the name X is missing from `_PALETTE`. The complete set of names anything imports is verified in "Risks and rollback" at the bottom.

- [ ] **Step 5: Run lint**

Run: `make lint`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/colors.py tests/test_colors.py
git commit -m "refactor: lazy palette in colors.py via PEP 562 __getattr__; expose lazy_palette helper"
```

---

## Task 9: Convert `mlb.py` to use `lazy_palette()`

**Files:**
- Modify: `src/led_ticker/widgets/mlb.py:34-36` (replace eager constants with `__getattr__`)

**Rationale:** `mlb.py` has three module-level eager `make_color(...)` calls (post-Task-7 rename). Convert them to use the same `lazy_palette()` pattern. This cements the lazy approach as the codebase-wide standard for module palettes.

- [ ] **Step 1: Write the failing tripwire**

Create `tests/test_widgets/test_mlb_lazy_palette.py`:

```python
"""Tripwire: mlb.py uses lazy_palette() like colors.py does."""

import ast
import inspect

from led_ticker.widgets import mlb as mlb_mod


def test_mlb_has_no_eager_color_construction():
    source = inspect.getsource(mlb_mod)
    tree = ast.parse(source)

    offenders: list[str] = []
    for node in tree.body:
        if isinstance(node, (ast.AnnAssign, ast.Assign)):
            value = node.value
            if isinstance(value, ast.Call):
                func_repr = ast.unparse(value.func)
                if func_repr in {"make_color", "_color"}:
                    offenders.append(ast.unparse(node))

    assert not offenders, (
        "mlb.py has eager module-level color construction; "
        "convert to lazy_palette():\n" + "\n".join(offenders)
    )


def test_mlb_palette_still_resolves():
    """The colors must still be importable with their existing names."""
    from led_ticker.widgets.mlb import LIVE_COLOR, LOSS_COLOR, WIN_COLOR

    assert (WIN_COLOR.red, WIN_COLOR.green, WIN_COLOR.blue) == (46, 200, 46)
    assert (LOSS_COLOR.red, LOSS_COLOR.green, LOSS_COLOR.blue) == (220, 30, 30)
    assert (LIVE_COLOR.red, LIVE_COLOR.green, LIVE_COLOR.blue) == (255, 40, 40)
```

- [ ] **Step 2: Run the test to confirm failure**

Run: `pytest tests/test_widgets/test_mlb_lazy_palette.py -v`
Expected: `test_mlb_has_no_eager_color_construction` FAILS listing the three offenders. `test_mlb_palette_still_resolves` PASSES (eager constants still exist and resolve).

- [ ] **Step 3: Convert `mlb.py`**

In `src/led_ticker/widgets/mlb.py:18`, the import currently is:
```python
from led_ticker.colors import RGB_WHITE, make_color
```

Add `lazy_palette` to that import:
```python
from led_ticker.colors import RGB_WHITE, lazy_palette, make_color
```

(`make_color` stays — `_team_color()` and `_team_color_by_name()` call it dynamically at draw time, those calls are not module-level so they don't force eager loading.)

Then replace lines 34-36:
```python
WIN_COLOR: Color = _color(46, 200, 46)
LOSS_COLOR: Color = _color(220, 30, 30)
LIVE_COLOR: Color = _color(255, 40, 40)
```
(which after Task 7 read `make_color(...)` instead of `_color(...)`)

with:
```python
__getattr__ = lazy_palette({
    "WIN_COLOR": (46, 200, 46),
    "LOSS_COLOR": (220, 30, 30),
    "LIVE_COLOR": (255, 40, 40),
})
```

The `Color` import remains (used in annotations elsewhere in the file).

- [ ] **Step 4: Verify type annotations still work**

`mlb.py` has explicit `Color` annotations on the deleted constants (line 34 `WIN_COLOR: Color = ...`). After the conversion these annotations vanish — the names are no longer module-level. That's fine: `__getattr__` returns `Color`, and callers like `_team_color()` already annotate their return as `-> Color`.

Run: `make lint`
Expected: PASS.

- [ ] **Step 5: Run all tests**

Run: `make test`
Expected: PASS. The mlb tripwire passes (no eager construction); existing mlb tests pass (the constants still resolve via `__getattr__`).

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/widgets/mlb.py tests/test_widgets/test_mlb_lazy_palette.py
git commit -m "refactor: mlb.py uses lazy_palette() — cements one lazy-load pattern for module palettes"
```

---

## Task 10: Verification sweep

- [ ] **Step 1: Full test suite**

Run: `make test`
Expected: PASS. Test count is +9 from baseline: 1 palette test, 1 crypto-colors tripwire, 3 random-color tests, 2 make_color tests, 2 mlb lazy-palette tests (the existing `test_random_color_cycles` was removed, net +9 −1 = +8; minor rounding fine).

- [ ] **Step 2: Lint**

Run: `make lint`
Expected: PASS.

- [ ] **Step 3: Config validator smoke test**

Run: `make validate CONFIG=config/config.example.toml`
Expected: PASS. Also test bigsign:
```bash
uv run led-ticker validate --config config/config.bigsign.example.toml
```

- [ ] **Step 4: Confirm both palettes are truly lazy**

Run:
```bash
uv run python -c "
import ast, inspect
import led_ticker.colors as c, led_ticker.widgets.mlb as m

for mod in (c, m):
    src = inspect.getsource(mod)
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, (ast.AnnAssign, ast.Assign)):
            v = node.value
            if isinstance(v, ast.Call) and ast.unparse(v.func) in {'make_color', '_color'}:
                raise SystemExit(f'eager construction in {mod.__name__}: {ast.unparse(node)}')

# Access works
print('colors.RGB_WHITE:', tuple([c.RGB_WHITE.red, c.RGB_WHITE.green, c.RGB_WHITE.blue]))
print('mlb.WIN_COLOR:', tuple([m.WIN_COLOR.red, m.WIN_COLOR.green, m.WIN_COLOR.blue]))
"
```
Expected output:
```
colors.RGB_WHITE: (255, 255, 255)
mlb.WIN_COLOR: (46, 200, 46)
```

- [ ] **Step 5: Confirm git log is clean**

Run: `git log --oneline main..HEAD`
Expected: 9 commits (one per task; Task 10 makes no commits).

---

## Execution Order

The plan is laid out by logical grouping. Execute in this order to satisfy dependencies (`make_color` must exist before `widgets/crypto/_colors.py`; `RED`/`GREEN` must exist before `rss_feed.py` changes; `RANDOM_COLOR` must move out of `colors.py` before legacy constants can be deleted):

1. **Task 1** — Delete BROWN
2. **Task 2** — Expand palette in `colors.py` (adds RED/GREEN/etc.; legacy constants still present)
3. **Task 7** — Rename `_color` → `make_color` (needed before Task 3)
4. **Task 3** — Create `widgets/crypto/_colors.py`; migrate crypto imports
5. **Task 4** — Update `rss_feed.py` rotation
6. **Task 6** — Move `RANDOM_COLOR` to `app.py` with 8 colors
7. **Task 5** — Remove legacy constants (`LIME`, trend colors) from `colors.py`
8. **Task 8** — Lazy palette + `lazy_palette()` helper in `colors.py`
9. **Task 9** — Convert `mlb.py` to `lazy_palette()`
10. **Task 10** — Verification sweep

Resulting commit order (newest first):
```
refactor: mlb.py uses lazy_palette() — cements one lazy-load pattern for module palettes
refactor: lazy palette in colors.py via PEP 562 __getattr__; expose lazy_palette helper
refactor: remove LIME and trend colors from colors.py (migrated to crypto)
refactor: move RANDOM_COLOR to app.py with expanded 8-color palette
refactor: rss_feed uses generic palette (DEFAULT/RED/GREEN) instead of crypto trend colors
refactor: move trend colors to widgets/crypto/_colors.py; bump UP_TREND for matrix visibility
refactor: rename colors._color to public make_color
refactor: expand colors.py with matrix-tuned palette; bump PURPLE+ORANGE to saturated values
refactor: remove dead BROWN constant from colors.py
```

---

## Risks and rollback

**Highest-risk change:** Task 8 (PEP 562 in `colors.py`). If any consumer imports a name not listed in `_PALETTE`, it surfaces as `AttributeError` at first access — not import time.

**Complete `_PALETTE` consumer audit:**
- `RGB_WHITE` — `ticker.py:14`, `widgets/mlb.py:18`, `widgets/weather.py:15`, `widgets/mlb_standings.py:18`
- `DEFAULT_COLOR` — `widgets/message.py:12`, `widgets/weather.py:15`, `widgets/rss_feed.py:15` (after Task 4), `widgets/two_row.py:51`, `widgets/_image_base.py:36`, `widgets/crypto/coinbase.py:15`, `widgets/crypto/coingecko.py:14`, `widgets/crypto/etherscan.py:15`
- `RED`, `GREEN` — `widgets/rss_feed.py:15` (Task 4)
- `RED`, `GREEN`, `BLUE`, `YELLOW`, `ORANGE`, `PURPLE`, `CYAN`, `PINK` — `app.py` (Task 6)

All ten live in `_PALETTE` in the Task 8 rewrite.

**Second-highest risk:** Task 9 (`mlb.py` lazy conversion). Same failure mode at a smaller scale. Audit:
- `WIN_COLOR`, `LOSS_COLOR`, `LIVE_COLOR` — only used inside `mlb.py` itself (the file imports them implicitly via `__getattr__`, but only the file accesses these names). No external consumers.

**Rollback:** Each task is one commit. `git revert <sha>` reverses any single step. The two PEP 562 tasks (8, 9) are revertable independently — Task 9 doesn't depend on Task 8 except through the shared `lazy_palette()` helper; reverting only Task 9 leaves the helper exposed but unused (harmless).
