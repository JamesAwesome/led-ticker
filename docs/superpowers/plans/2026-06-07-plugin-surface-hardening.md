# Plugin public-surface hardening (A1–A4) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden the public `led_ticker.plugin` surface — `FrameAwareBase` as a real class, public `snap_reset`/`normalize_bg`, an `is_scaled()` predicate, and canonical text drawing on `draw_text`+`measure_width` (drop `draw_with_emoji`) — as a clean break, migrating the one consumer (led-ticker-baseball).

**Architecture:** Three PRs across two repos, ordered so no CI run is ever red (A4's removal is the only breaking change): **(Phase 1)** core additive+rename, **(Phase 2)** baseball adopts the new forms, **(Phase 3)** core removes `draw_with_emoji`. pool uses none of these and is untouched.

**Tech Stack:** Python 3.14, uv, pytest, ruff; the docs-site api-reference drift test (prettier/astro).

**Companion spec:** `docs/superpowers/specs/2026-06-07-plugin-surface-hardening-design.md`

**Repos:** core = `/Users/james/projects/github/jamesawesome/led-ticker`; baseball = `/Users/james/projects/github/jamesawesome/led-ticker-baseball`.

**Worktree discipline:** each core PR gets its own worktree off `led-ticker` main; the baseball PR is a branch in the baseball repo. Verify `git branch --show-current` ≠ `main` before any commit. Commit with `git commit --no-verify` (global hooksPath breaks the hook); run the explicit gates instead. Run `make dev` in any new core worktree.

**Sequencing gate:** Phase 2 requires Phase 1 **merged** (baseball resolves led-ticker from `../led-ticker` on main). Phase 3 requires Phase 2 **merged** (no consumer of `draw_with_emoji` may remain).

---

## PHASE 1 — Core PR #1: rename + additive surface (branch `feat/plugin-surface-harden`)

**Worktree:** `git worktree add -b feat/plugin-surface-harden ../lt-harden main` (off `led-ticker`), then `cd ../lt-harden && make dev`.

### Task 1.1: Rename `_FrameAware` → `FrameAwareBase` (real public class)

**Files:**
- Modify: `src/led_ticker/widgets/_frame_aware.py` (class def), the 8 inheritors, `src/led_ticker/plugin.py:64`
- Test: `tests/test_plugin_surface.py`

- [ ] **Step 1: Update the surface test first** (it currently asserts `FrameAwareBase is _FrameAware`). In `tests/test_plugin_surface.py`, change `test_frame_aware_base_is_the_internal_class` to assert the class is now named publicly:

```python
def test_frame_aware_base_is_a_real_public_class():
    from led_ticker.widgets._frame_aware import FrameAwareBase as RealBase
    assert led_ticker_plugin_module().FrameAwareBase is RealBase
    # the old private name no longer exists
    import led_ticker.widgets._frame_aware as fa
    assert not hasattr(fa, "_FrameAware"), "_FrameAware should be renamed to FrameAwareBase"
```
(Use the same `import led_ticker.plugin as P` accessor the file already uses; the helper name above is illustrative — match the file's existing style, i.e. `assert P.FrameAwareBase is RealBase`.)

- [ ] **Step 2: Run it, expect FAIL** (`_FrameAware` still exists): `cd ../lt-harden && PYTHONPATH=tests/stubs uv run pytest tests/test_plugin_surface.py -v` → FAIL.

- [ ] **Step 3: Rename the class.** In `src/led_ticker/widgets/_frame_aware.py:35`, `class _FrameAware:` → `class FrameAwareBase:`. Update any internal self-references / `__init_subclass__` if they name `_FrameAware`.

- [ ] **Step 4: Update the 8 inheritors** — in each, change the import of `_FrameAware` and the base-class reference to `FrameAwareBase`:
  - `src/led_ticker/widgets/message.py` (lines ~34, ~308 — `class TickerMessage(_FrameAware)`, `class TickerCountdown(_FrameAware)`)
  - `src/led_ticker/widgets/two_row.py:75`
  - `src/led_ticker/widgets/weather.py:25`
  - `src/led_ticker/widgets/crypto/coinbase.py:48`
  - `src/led_ticker/widgets/crypto/coingecko.py:24`
  - `src/led_ticker/widgets/crypto/etherscan.py:50`
  - `src/led_ticker/widgets/_image_base.py:104`
  Find every import: `grep -rn "_FrameAware" src/ tests/` — update ALL (imports, base classes, and any test referencing `_FrameAware`).

- [ ] **Step 5: Update the surface export.** `src/led_ticker/plugin.py:64`: `from led_ticker.widgets._frame_aware import _FrameAware as FrameAwareBase` → `from led_ticker.widgets._frame_aware import FrameAwareBase`. (The `__all__` entry `"FrameAwareBase"` stays.)

- [ ] **Step 6: Confirm no `_FrameAware` remains:** `grep -rn "_FrameAware" src/ tests/` → empty.

- [ ] **Step 7: Gates:** `PYTHONPATH=tests/stubs uv run pytest tests/test_plugin_surface.py -v` → PASS; `make test` → all green; `uv run --extra dev ruff check src/ tests/` → clean.

- [ ] **Step 8: Commit** — `git add -A && git commit --no-verify -m "refactor(plugin): promote _FrameAware to public FrameAwareBase"` (+ Co-Authored-By trailer).

### Task 1.2: Promote `_snap_reset`/`_normalize_bg` to public `snap_reset`/`normalize_bg`

**Files:**
- Modify: `src/led_ticker/transitions/__init__.py` (`_normalize_bg`), `src/led_ticker/transitions/_hires_loader.py` (`_snap_reset` + its internal callers), `src/led_ticker/plugin.py`, plus tests referencing the old names.

- [ ] **Step 1: Add the surface assertions** to `tests/test_plugin_surface.py` (extend the `NEW_SYMBOLS`-style list or add a test):

```python
def test_snap_and_normalize_exported():
    assert "snap_reset" in P.__all__ and hasattr(P, "snap_reset")
    assert "normalize_bg" in P.__all__ and hasattr(P, "normalize_bg")
    # behavior: normalize_bg coerces a graphics.Color and a tuple and None
    assert P.normalize_bg(None) is None
    assert P.normalize_bg((1, 2, 3)) == (1, 2, 3)
```

- [ ] **Step 2: Run, expect FAIL** (`snap_reset`/`normalize_bg` not exported).

- [ ] **Step 3: Rename `_normalize_bg` → `normalize_bg`** in `src/led_ticker/transitions/__init__.py` (the def). Update ALL internal callers: `grep -rn "_normalize_bg" src/ tests/` and rename each (the lazy import inside `_snap_reset`, any `run_transition` use, test references). Keep the function body identical.

- [ ] **Step 4: Rename `_snap_reset` → `snap_reset`** in `src/led_ticker/transitions/_hires_loader.py` (the def, and its internal callers in `render_hires_frame` / `render_hires_baseball_frame` if still present in core, and test references). `grep -rn "_snap_reset" src/ tests/` → rename each. Body identical (it now calls the renamed `normalize_bg`).

- [ ] **Step 5: Export from the surface.** In `src/led_ticker/plugin.py`, add imports and `__all__` entries:

```python
from led_ticker.transitions import normalize_bg
from led_ticker.transitions._hires_loader import snap_reset
```
Add `"normalize_bg"` and `"snap_reset"` to `__all__` (keep it sorted).

- [ ] **Step 6: Confirm no `_snap_reset`/`_normalize_bg` remain:** `grep -rnE "_snap_reset|_normalize_bg" src/ tests/` → empty.

- [ ] **Step 7: Gates:** `make test` → green (esp. `TestHiresSnapRespectsIncomingBg` + the `snap`/`normalize` unit tests, now under the new names); ruff clean; surface test PASS.

- [ ] **Step 8: Commit** — `refactor(plugin): expose snap_reset/normalize_bg on the public surface`.

### Task 1.3: Add `is_scaled(canvas)` predicate

**Files:**
- Modify: `src/led_ticker/scaled_canvas.py`, `src/led_ticker/plugin.py`
- Test: `tests/test_plugin_surface.py` (+ a behavior test, e.g. in `tests/test_scaled_canvas.py` if it exists)

- [ ] **Step 1: Write the failing test** in `tests/test_plugin_surface.py`:

```python
def test_is_scaled_predicate():
    assert "is_scaled" in P.__all__ and hasattr(P, "is_scaled")
    from led_ticker.scaled_canvas import ScaledCanvas
    from rgbmatrix import RGBMatrix, RGBMatrixOptions
    real = RGBMatrix(options=RGBMatrixOptions()).CreateFrameCanvas()
    assert P.is_scaled(real) is False
    assert P.is_scaled(ScaledCanvas(real, scale=4)) is True
```
(Match how `tests/test_scaled_canvas.py` constructs a `ScaledCanvas` if the constructor differs — read that file first; adjust the construction to the real signature.)

- [ ] **Step 2: Run, expect FAIL.**

- [ ] **Step 3: Implement** in `src/led_ticker/scaled_canvas.py` (after the `ScaledCanvas` class):

```python
def is_scaled(canvas: Any) -> bool:
    """True if ``canvas`` is a scaled wrapper (bigsign hi-res path).

    The documented gate for plugins that need the hi-res branch — call
    this instead of ``isinstance(canvas, ScaledCanvas)`` so the wrapper
    type can evolve without breaking plugins.
    """
    return isinstance(canvas, ScaledCanvas)
```

- [ ] **Step 4: Export** in `src/led_ticker/plugin.py`: add `is_scaled` to the `from led_ticker.scaled_canvas import (...)` line (currently `ScaledCanvas, paint_hires, unwrap_to_real`) and add `"is_scaled"` to `__all__`.

- [ ] **Step 5: Gates:** surface test PASS; `make test` green; ruff clean.

- [ ] **Step 6: Commit** — `feat(plugin): add is_scaled(canvas) predicate`.

### Task 1.4: Document the new surface (api-reference + drift test)

**Files:**
- Modify: `docs/site/src/content/docs/plugins/api-reference.mdx`

- [ ] **Step 1: Add rows** inside the `<!-- api-exports -->` region: `FrameAwareBase` already exists (now points at a real class — update its description if it said "internal `_FrameAware`"); add `snap_reset`, `normalize_bg` (Helpers table) and `is_scaled` (Helpers). Match the existing table column style.
- [ ] **Step 2: Run the drift test:** `PYTHONPATH=tests/stubs uv run pytest tests/test_docs_plugin_api_drift.py -v` → PASS (it asserts `__all__` ⊆ documented).
- [ ] **Step 3: Prettier:** `cd docs/site && pnpm install --silent && npx prettier --write src/content/docs/plugins/api-reference.mdx && npx prettier --check .` → clean.
- [ ] **Step 4: Commit** — `docs(api-reference): document FrameAwareBase/snap_reset/normalize_bg/is_scaled`.

### Task 1.5: Push + open Core PR #1

- [ ] `git push --no-verify -u origin feat/plugin-surface-harden`
- [ ] `gh pr create --repo JamesAwesome/led-ticker --title "feat(plugin): harden public surface (FrameAwareBase, snap_reset/normalize_bg, is_scaled)" --body "Phase 1 of plugin-surface hardening (spec: docs/superpowers/specs/2026-06-07-plugin-surface-hardening-design.md). Additive + rename, no breaking change: promotes _FrameAware→FrameAwareBase (real public class), exposes snap_reset/normalize_bg, adds is_scaled(). draw_with_emoji removal is a later PR after baseball migrates. No consumer breaks.

🤖 Generated with [Claude Code](https://claude.com/claude-code)"`
- [ ] Confirm CI green. **CHECKPOINT: merge before Phase 2.**

---

## PHASE 2 — Baseball PR: adopt the hardened forms (branch `feat/adopt-hardened-surface` in the baseball repo)

**Prereq:** Phase 1 merged to led-ticker main; update the local core checkout: `git -C /Users/james/projects/github/jamesawesome/led-ticker checkout main && git -C /Users/james/projects/github/jamesawesome/led-ticker pull --no-verify origin main`. Then branch in the plugin repo: `cd /Users/james/projects/github/jamesawesome/led-ticker-baseball && git checkout main && git pull --no-verify origin main && git checkout -b feat/adopt-hardened-surface`. Confirm the new symbols resolve: `uv run python -c "from led_ticker.plugin import snap_reset, normalize_bg, is_scaled; print('ok')"`.

### Task 2.1: Drop local `_snap_reset`/`_normalize_bg` copies; import the public ones

**Files:** Modify `src/led_ticker_baseball/transition.py`

- [ ] **Step 1:** Delete the local `_normalize_bg` (def ~line 336) and `_snap_reset` (def ~line 351) functions. Add `snap_reset` and `normalize_bg` to the `from led_ticker.plugin import (...)` block at the top (currently `Canvas, PixelData, ScaledCanvas, Transition, unwrap_to_real`).
- [ ] **Step 2:** Replace the internal call `_snap_reset(canvas, kwargs.get("incoming_bg_color"))` (~line 516) with `snap_reset(canvas, kwargs.get("incoming_bg_color"))`. If `render_hires_baseball_frame`'s local logic called `_normalize_bg` anywhere else, point it at `normalize_bg`.
- [ ] **Step 3: Gates:** `uv run pytest tests/test_transition.py -q` → all pass (behavior is byte-identical — the public functions are the same code the copies were verbatim from); `grep -nE "_snap_reset|_normalize_bg|def normalize_bg|def _snap" src/led_ticker_baseball/transition.py` → only the `from led_ticker.plugin import` reference remains (no local defs).
- [ ] **Step 4: Commit** — `refactor: use public snap_reset/normalize_bg instead of local copies`.

### Task 2.2: Replace `isinstance(ScaledCanvas)` with `is_scaled`

**Files:** Modify `src/led_ticker_baseball/transition.py`

- [ ] **Step 1:** Add `is_scaled` to the `from led_ticker.plugin import (...)` block. Replace the two `isinstance(canvas, ScaledCanvas)` checks (~lines 546, 587) with `is_scaled(canvas)`. Keep `ScaledCanvas` in the import only if still used elsewhere (e.g. a type annotation) — `grep -n "ScaledCanvas" src/led_ticker_baseball/transition.py`; if no other use, drop it from the import.
- [ ] **Step 2: Gates:** `uv run pytest tests/test_transition.py -q` → pass; `uv run ruff check src tests` → clean (catches an unused `ScaledCanvas` import if you left it).
- [ ] **Step 3: Commit** — `refactor: gate hi-res path on is_scaled() instead of isinstance(ScaledCanvas)`.

### Task 2.3: Migrate `draw_with_emoji` → `draw_text`

**Files:** Modify `src/led_ticker_baseball/scores.py`

The migration maps `draw_with_emoji(canvas, font, X, Y, COLOR, TEXT)` → `draw_text(canvas, font, TEXT, X, Y, COLOR)` (note the arg reshuffle: text moves to 3rd). Handle kwargs (`y=`, `color=`, `text=`) by keeping them as kwargs and passing `text` positionally-or-as-kwarg in draw_text's `text` slot.

- [ ] **Step 1:** In the two `from led_ticker.plugin import (...)` blocks in `scores.py` (top-level ~line 23 region and the inline import ~line 492 / ~1097), replace `draw_with_emoji` with `draw_text`. (`measure_width` is already imported.)
- [ ] **Step 2:** Migrate each call site (`grep -n "draw_with_emoji" src/led_ticker_baseball/scores.py` to find them — there are ~8 draw sites):
  - **Return-ignored sites** (most — e.g. `scores.py:534`, the `_draw_small`/`_draw_center` helpers ~581/602/611, ~665/668/671): rewrite args. Example:
    `draw_with_emoji(canvas, self.font, x, y + y_offset, color, text)` → `draw_text(canvas, self.font, text, x, y + y_offset, color)`.
    Kwarg form `draw_with_emoji(canvas, self.small_font, x, y=y + y_offset, color=color, text=text)` → `draw_text(canvas, self.small_font, text, x, y=y + y_offset, color=color)`.
  - **The advance-using site** (`scores.py:~1153`, `x += draw_with_emoji(...)`): `draw_text` returns the absolute next-x, so change `x += draw_with_emoji(canvas, font, x, y, color, seg_text)` → `x = draw_text(canvas, font, seg_text, x, y, color)` (assign, don't `+=` — next-x is absolute). Read the surrounding loop to confirm `x` is the running cursor; the assignment is equivalent to the old `x += advance`.
- [ ] **Step 3:** Confirm none remain: `grep -n "draw_with_emoji" src/led_ticker_baseball/scores.py` → empty.
- [ ] **Step 4: Gates (the safety net):** `uv run pytest -q` → all 232 pass (the scoreboard pixel-level tests catch any wrong arg mapping); `uv run ruff check src tests` → clean; `uv run pytest tests/test_import_purity.py -q` → pass (still imports only `led_ticker.plugin`).
- [ ] **Step 5: Commit** — `refactor: migrate draw_with_emoji call sites to draw_text`.

### Task 2.4: Push + open Baseball PR

- [ ] `git push --no-verify -u origin feat/adopt-hardened-surface`
- [ ] `gh pr create --repo JamesAwesome/led-ticker-baseball --title "refactor: adopt the hardened led_ticker.plugin surface" --body "Drops the local snap_reset/normalize_bg copies (now public), gates the hi-res path on is_scaled() instead of isinstance(ScaledCanvas), and migrates draw_with_emoji call sites to draw_text. Behavior-preserving (232 tests green, transition stays pixel-identical, import-purity holds).

🤖 Generated with [Claude Code](https://claude.com/claude-code)"`
- [ ] Confirm CI green. **CHECKPOINT: merge before Phase 3.**

---

## PHASE 3 — Core PR #2: remove `draw_with_emoji` from the surface (branch `feat/plugin-drop-draw-with-emoji`)

**Prereq:** Phase 2 merged (baseball no longer references `draw_with_emoji`). **Worktree:** `git worktree add -b feat/plugin-drop-draw-with-emoji ../lt-drop main` (off updated led-ticker main), `cd ../lt-drop && make dev`.

### Task 3.1: Remove `draw_with_emoji` from the public surface

**Files:** Modify `src/led_ticker/plugin.py`, `tests/test_plugin_surface.py`, `docs/site/src/content/docs/plugins/api-reference.mdx`

- [ ] **Step 1: Update the surface test** in `tests/test_plugin_surface.py` to assert it's gone:

```python
def test_draw_with_emoji_not_public():
    assert "draw_with_emoji" not in P.__all__
    assert not hasattr(P, "draw_with_emoji")
```

- [ ] **Step 2: Run, expect FAIL** (still exported).

- [ ] **Step 3: Remove from the surface.** In `src/led_ticker/plugin.py`: remove `draw_with_emoji` from the `from led_ticker.pixel_emoji import (...)` block (line ~50) and from `__all__` (line ~102). KEEP the private alias line `from led_ticker.pixel_emoji import draw_with_emoji as _draw_with_emoji` (line ~54) — `draw_text` still wraps `_draw_with_emoji` (line ~350). So `draw_text` keeps working; only the public re-export is gone.

- [ ] **Step 4: Confirm `draw_text` still works** (it wraps `_draw_with_emoji`): the `make test` text/draw tests + the existing `draw_text` coverage stay green.

- [ ] **Step 5: Update docs.** Remove the `draw_with_emoji` row from `api-reference.mdx`'s exports table. Run the drift test (`tests/test_docs_plugin_api_drift.py`) → PASS (now `draw_with_emoji` is neither in `__all__` nor documented). Prettier the mdx → clean.

- [ ] **Step 6: Gates:** surface test PASS (incl. the new "not public" test); `make test` green; ruff clean.

- [ ] **Step 7: Commit + push + PR.**
```bash
git add -A
git commit --no-verify -m "refactor(plugin): remove draw_with_emoji from the public surface

Canonicalized on draw_text (+ measure_width). draw_with_emoji stays
internal (draw_text wraps it). No consumer remains after the baseball
migration."
git push --no-verify -u origin feat/plugin-drop-draw-with-emoji
gh pr create --repo JamesAwesome/led-ticker --title "refactor(plugin): remove draw_with_emoji from the public surface" --body "Phase 3 (final) of plugin-surface hardening. Canonicalizes text drawing on draw_text + measure_width. Safe now that baseball migrated off draw_with_emoji.

🤖 Generated with [Claude Code](https://claude.com/claude-code)"
```
- [ ] Confirm CI green.

---

## Self-review notes (coverage map)

| Spec item | Tasks |
|---|---|
| A1 FrameAwareBase real class | 1.1 (rename + inheritors + export) |
| A2 public snap_reset/normalize_bg | 1.2 (rename + export), 2.1 (baseball drops copies) |
| A3 is_scaled predicate | 1.3 (add), 2.2 (baseball adopts) |
| A4 canonicalize text draw / drop draw_with_emoji | 2.3 (baseball migrates), 3.1 (core removes) |
| Docs (api-reference + drift) | 1.4 (add), 3.1 (remove) |
| 3-PR no-red-CI sequencing | Phase order + the two CHECKPOINTs |
| Tests (surface, drift, import-purity, pixel-identical) | 1.1–1.4, 2.1–2.3, 3.1 |
| Out of scope (B–G, scores.py split, pool) | honored — no split task; pool untouched |
