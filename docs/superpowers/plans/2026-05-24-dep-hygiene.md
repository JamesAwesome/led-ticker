# Batch 2 (DR2): Dependency Hygiene + Dead Code

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Branch safety:** Before doing ANY work, run `git branch --show-current`. If it prints `main`, stop immediately and ask for a worktree.

**Goal:** Remove unused/wrong runtime dependencies, delete dead code, and add missing Makefile targets. The `imageio → Pillow` swap is the most impactful change (removes a runtime dep from Pi installs).

**Architecture:** Eleven independent changes. Group 1 (Tasks 1–3) cleans up `pyproject.toml` and `config.py`. Group 2 (Task 4) deletes a dead function. Group 3 (Tasks 5–6) is two-line production fixes. Group 4 (Tasks 7–11) is Makefile and tooling hygiene.

**Tech Stack:** Python, TOML, attrs, Pillow, Makefile

**Run tests with:** `PYTHONPATH=tests/stubs uv run pytest -x -q`

**Baseline:** Run `make test` before starting; note the count. It should not change.

---

### Task 1: M19 — Remove dead `tomli` conditional dep + simplify `config.py` import

`pyproject.toml:20` has `"tomli>=2.0; python_version<'3.11'"` which can never be true under `requires-python = ">=3.11"`. The `try/except tomllib` import guard in `config.py:5–8` is similarly dead.

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/led_ticker/config.py:5-8`

- [ ] **Step 1: Write a test confirming direct import works**

In `tests/test_app_run_module.py` (or any convenient existing test file for imports), verify the module imports cleanly. This step is primarily to confirm nothing breaks — run the existing suite first:

```bash
PYTHONPATH=tests/stubs uv run pytest -x -q
```

Expected: all pass (baseline).

- [ ] **Step 2: Remove the dead dep from `pyproject.toml`**

In `pyproject.toml`, remove the `tomli` line from `[project.dependencies]`:

```toml
# Before:
dependencies = [
    "Pillow>=10.0",
    "aiohttp>=3.9",
    "attrs>=23.0",
    "feedparser>=6.0",
    "imageio>=2.31",
    "tomli-w>=1.0",
    "tomli>=2.0; python_version<'3.11'",
]

# After:
dependencies = [
    "Pillow>=10.0",
    "aiohttp>=3.9",
    "attrs>=23.0",
    "feedparser>=6.0",
    "imageio>=2.31",
    "tomli-w>=1.0",
]
```

- [ ] **Step 3: Simplify `config.py` import**

In `src/led_ticker/config.py`, replace the try/except guard with a direct import. Find the block (around line 5–8):

```python
# Before:
try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore[no-redef]

# After:
import tomllib
```

- [ ] **Step 4: Run the test suite**

```bash
PYTHONPATH=tests/stubs uv run pytest -x -q
```

Expected: same count as baseline; all pass.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml src/led_ticker/config.py
git commit -m "fix: remove dead tomli conditional dep and simplify config.py import (M19)"
```

---

### Task 2: S24 — Replace `imageio.mimsave` with Pillow `Image.save`

`tools/render_demo/render.py:194` calls `imageio.v2.mimsave` exactly once to encode a list of `PIL.Image` frames. Pillow (already a hard runtime dep) supports this natively. After this change, `imageio` can be removed.

**Files:**
- Modify: `tools/render_demo/render.py`

- [ ] **Step 1: Run existing render_demo tests first**

```bash
PYTHONPATH=tests/stubs uv run pytest tools/render_demo/ -v
```

Expected: all pass (baseline).

- [ ] **Step 2: Find the imageio call**

```bash
grep -n "imageio" tools/render_demo/render.py
```

The call site should look approximately like:

```python
import imageio.v2 as imageio
...
imageio.mimsave(out_path, frames, duration=durations, loop=0)
```

Note: `frames` is a list of `PIL.Image` objects and `durations` is a list of per-frame durations in milliseconds.

- [ ] **Step 3: Replace with Pillow equivalent**

Remove the `import imageio.v2 as imageio` line (or the `imageio` import if it's separate). Replace the `imageio.mimsave(...)` call with:

```python
frames[0].save(
    out_path,
    save_all=True,
    append_images=frames[1:],
    duration=durations,
    loop=0,
)
```

The Pillow `Image.save` signature for GIF:
- `save_all=True` — encode multiple frames
- `append_images=frames[1:]` — subsequent frames after the first
- `duration=durations` — per-frame durations (ms), same as imageio
- `loop=0` — loop forever, same as imageio default

- [ ] **Step 4: Run the render_demo tests**

```bash
PYTHONPATH=tests/stubs uv run pytest tools/render_demo/ -v
```

Expected: all pass. The GIF output should be identical in structure.

- [ ] **Step 5: Run the full test suite**

```bash
PYTHONPATH=tests/stubs uv run pytest -x -q
```

Expected: same count as baseline; all pass.

- [ ] **Step 6: Commit**

```bash
git add tools/render_demo/render.py
git commit -m "fix: replace imageio.mimsave with Pillow Image.save in render_demo (S24)"
```

---

### Task 3: S23 — Move `imageio` and `tomli-w` to an optional dep group

After Task 2, `imageio` is no longer used anywhere. `tomli-w` is only used in `tools/render_demo/render.py` (if at all — check with grep first). Both should be moved out of `[project.dependencies]` (installed on every Pi) into `[project.optional-dependencies]`.

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Confirm imageio is no longer used**

```bash
grep -rn "imageio" src/ tools/ tests/ --include="*.py"
```

Expected: zero results after Task 2 removed the last usage.

- [ ] **Step 2: Confirm where `tomli-w` is used**

```bash
grep -rn "tomli.w\|import tomli_w\|tomliw" src/ tools/ --include="*.py"
```

If `tomli-w` is only in `tools/render_demo/` (not in `src/`), move it to the optional group. If it's not used at all, remove it entirely.

- [ ] **Step 3: Update `pyproject.toml`**

```toml
# Before:
dependencies = [
    "Pillow>=10.0",
    "aiohttp>=3.9",
    "attrs>=23.0",
    "feedparser>=6.0",
    "imageio>=2.31",
    "tomli-w>=1.0",
]

# After:
dependencies = [
    "Pillow>=10.0",
    "aiohttp>=3.9",
    "attrs>=23.0",
    "feedparser>=6.0",
]

# Add a new optional group:
[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "pytest-cov>=5.0",
    "pytest-mock>=3.12",
    "pre-commit>=4.0",
    "ruff>=0.4",
    "pyright>=1.1",
]
render = [
    "imageio>=2.31",
    "tomli-w>=1.0",
]
```

Note: if `tomli-w` has zero usages, omit it from the `render` group entirely.

- [ ] **Step 4: Update `uv.lock` and run tests**

```bash
uv sync
PYTHONPATH=tests/stubs uv run pytest -x -q
```

Expected: all pass. The `render` group is not needed for the test suite.

- [ ] **Step 5: Update `render_demo` README or header comment**

In `tools/render_demo/render.py`, add or update the module docstring to note:

```python
# Requires optional render deps: pip install "led-ticker[render]"
```

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock tools/render_demo/render.py
git commit -m "fix: move imageio and tomli-w to optional render dep group, remove from Pi installs (S23)"
```

---

### Task 4: M1 — Delete dead `_enqueue_from_rss_feed`

`src/led_ticker/ticker.py:1008–1020` defines `_enqueue_from_rss_feed` which is not called anywhere in `src/`. It is a leftover from the Large #2+4 ticker-methods refactor.

**Files:**
- Modify: `src/led_ticker/ticker.py`

- [ ] **Step 1: Confirm no callers exist**

```bash
grep -rn "_enqueue_from_rss_feed" src/ tests/ --include="*.py"
```

Expected: only the definition in `ticker.py`. If tests reference it, read those tests before deleting.

- [ ] **Step 2: Delete the function**

In `src/led_ticker/ticker.py`, find and delete the `_enqueue_from_rss_feed` function (lines ~1008–1020). It should look like a standalone helper that processes RSS items into the queue but is never called.

- [ ] **Step 3: Run the test suite**

```bash
PYTHONPATH=tests/stubs uv run pytest -x -q
```

Expected: same count as baseline (no tests should reference this function).

- [ ] **Step 4: Commit**

```bash
git add src/led_ticker/ticker.py
git commit -m "fix: delete dead _enqueue_from_rss_feed — leftover from Large #2+4 (M1)"
```

---

### Task 5: M8 — Replace `@dataclass` with `@attrs.frozen` on `CoercionWarning`

`src/led_ticker/_coerce.py` uses `@dataclass(frozen=True)` — the only production data class not using `attrs`. Inconsistency with the rest of the package.

**Files:**
- Modify: `src/led_ticker/_coerce.py`

- [ ] **Step 1: Run tests**

```bash
PYTHONPATH=tests/stubs uv run pytest -x -q -k "coerce"
```

Note the count.

- [ ] **Step 2: Apply the fix**

In `src/led_ticker/_coerce.py`, find `CoercionWarning`. The current definition looks like:

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class CoercionWarning:
    message: str
    field: str
```

Change to:

```python
import attrs

@attrs.frozen
class CoercionWarning:
    message: str
    field: str
```

Remove the `from dataclasses import dataclass` line if it's only used for `CoercionWarning`.

- [ ] **Step 3: Run tests**

```bash
PYTHONPATH=tests/stubs uv run pytest -x -q
```

Expected: same count; all pass. `attrs.frozen` produces the same interface as `@dataclass(frozen=True)`.

- [ ] **Step 4: Commit**

```bash
git add src/led_ticker/_coerce.py
git commit -m "fix: replace @dataclass with @attrs.frozen on CoercionWarning for consistency (M8)"
```

---

### Task 6: M9 — Extract magic number constants in `ColorFlash`

`src/led_ticker/transitions/effects.py:48–49` uses unnamed literals `0.33` and `0.66` for flash onset and fadeout phase thresholds.

**Files:**
- Modify: `src/led_ticker/transitions/effects.py`

- [ ] **Step 1: Apply the fix**

Find the `ColorFlash` class in `src/led_ticker/transitions/effects.py`. Near the top of the file (or at module level), add two constants:

```python
_FLASH_ONSET: float = 1 / 3
_FLASH_FADEOUT: float = 2 / 3
```

Then in `ColorFlash.frame_at` (around lines 48–49), replace the literals:

```python
# Before:
if t < 0.33:
    ...
elif t > 0.66:
    ...

# After:
if t < _FLASH_ONSET:
    ...
elif t > _FLASH_FADEOUT:
    ...
```

- [ ] **Step 2: Run tests**

```bash
PYTHONPATH=tests/stubs uv run pytest -x -q -k "flash or transition"
```

Expected: all pass. The behavior is unchanged.

- [ ] **Step 3: Commit**

```bash
git add src/led_ticker/transitions/effects.py
git commit -m "fix: extract _FLASH_ONSET, _FLASH_FADEOUT constants in ColorFlash (M9)"
```

---

### Task 7: M20 — Remove unused `--fps` parameter from `render_demo`

`tools/render_demo/render.py` accepts `--fps` in the CLI and in the `render()` function signature, but never uses it. `README.md` (line 9 of the render_demo README, if it exists) shows `--fps 20` in a usage example.

**Files:**
- Modify: `tools/render_demo/render.py`
- Modify: `tools/render_demo/README.md` (if it exists)

- [ ] **Step 1: Confirm `fps` is unused**

```bash
grep -n "fps" tools/render_demo/render.py
```

Verify that `fps` appears in the function signature and CLI argument definition, but is never referenced in the function body after those points.

- [ ] **Step 2: Remove `fps` from the function signature and CLI**

In `tools/render_demo/render.py`:
- Remove the `fps` parameter from the `render()` function signature
- Remove the `parser.add_argument("--fps", ...)` line
- Remove any `fps=args.fps` in the CLI dispatch call

- [ ] **Step 3: Update the render_demo README if it shows `--fps`**

```bash
ls tools/render_demo/README.md 2>/dev/null && grep "fps" tools/render_demo/README.md
```

Remove or update any `--fps` example.

- [ ] **Step 4: Run render_demo tests**

```bash
PYTHONPATH=tests/stubs uv run pytest tools/render_demo/ -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add tools/render_demo/
git commit -m "fix: remove unused --fps parameter from render_demo render() (M20)"
```

---

### Task 8: M21 — Add `make render-emoji-previews` target

`tools/render_emoji_previews.py` generates per-slug emoji preview PNGs committed to `docs/site/public/emoji/`. It has no Makefile target, is not in CI, and goes stale when new emoji slugs are added with no signal to the maintainer.

**Files:**
- Modify: `Makefile`

- [ ] **Step 1: Confirm the script exists and runs**

```bash
ls tools/render_emoji_previews.py
uv run python tools/render_emoji_previews.py --help 2>/dev/null || echo "no --help"
```

- [ ] **Step 2: Add the Makefile target**

In `Makefile`, add after the existing tool targets:

```makefile
render-emoji-previews: ## Re-generate per-slug emoji preview PNGs in docs/site/public/emoji/
	uv run python tools/render_emoji_previews.py
```

Also add `render-emoji-previews` to the `.PHONY` declaration at line 1.

- [ ] **Step 3: Add a note in `CLAUDE.md`**

In the "Tooling" or "Commands" section of `CLAUDE.md`, add:

```
make render-emoji-previews  # re-generate emoji preview PNGs after adding new slugs
```

- [ ] **Step 4: Commit**

```bash
git add Makefile CLAUDE.md
git commit -m "fix: add make render-emoji-previews target and CLAUDE.md note (M21)"
```

---

### Task 9: M22 — Add `tools/` to `make lint` and `make format`

`Makefile:22,28` runs `ruff check src/ tests/` and `ruff format src/ tests/`, excluding `tools/`. `tools/` is in `testpaths` so its tests run in the standard suite, but linting is skipped.

**Files:**
- Modify: `Makefile`

- [ ] **Step 1: Update both targets**

In `Makefile`, find the `lint` and `format` targets and add `tools/`:

```makefile
# Before:
lint:
	uv run ruff check src/ tests/

format:
	uv run ruff format src/ tests/

# After:
lint:
	uv run ruff check src/ tests/ tools/

format:
	uv run ruff format src/ tests/ tools/
```

- [ ] **Step 2: Run lint to see if tools/ has any issues**

```bash
make lint
```

Fix any ruff issues found in `tools/` before committing.

- [ ] **Step 3: Commit**

```bash
git add Makefile
git commit -m "fix: add tools/ to make lint and make format targets (M22)"
```

---

### Task 10: M23 — Add `setup-demo-fonts` to `.PHONY`

`Makefile` lists all targets in `.PHONY` except `setup-demo-fonts`. If a file named `setup-demo-fonts` ever appears in the repo root, Make silently skips the target.

**Files:**
- Modify: `Makefile:1`

- [ ] **Step 1: Apply the fix**

In `Makefile`, find the `.PHONY` declaration (line 1) and add `setup-demo-fonts`:

```makefile
# Before (example — add setup-demo-fonts to whatever list is already there):
.PHONY: dev test lint format clean build-docker validate ...

# After:
.PHONY: dev test lint format clean build-docker validate setup-demo-fonts ...
```

- [ ] **Step 2: Verify Make still works**

```bash
make --dry-run setup-demo-fonts
```

Expected: prints the command(s) in the target without error.

- [ ] **Step 3: Commit**

```bash
git add Makefile
git commit -m "fix: add setup-demo-fonts to .PHONY in Makefile (M23)"
```

---

### Task 11: M24 — Delete or date `scripts/crypto-ticker.py`

`scripts/crypto-ticker.py` is a three-line deprecation warning stub. Untested, undocumented, and indefinitely lingering.

**Files:**
- Delete (or modify): `scripts/crypto-ticker.py`

- [ ] **Step 1: Read the file**

```bash
cat scripts/crypto-ticker.py
```

If it's a pure deprecation stub (prints a warning, does nothing else), delete it. If it actually does something, add a removal deadline comment.

- [ ] **Step 2a: If it's a pure stub — delete it**

```bash
git rm scripts/crypto-ticker.py
```

- [ ] **Step 2b: If it has non-trivial logic — add a deadline comment**

Add at the top of the file:

```python
# TODO: remove after 2026-Q3 — migration period has ended
```

- [ ] **Step 3: Check for references**

```bash
grep -rn "crypto-ticker.py" README.md docs/ CLAUDE.md 2>/dev/null
```

Update or remove any references found.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "fix: delete deprecated crypto-ticker.py stub (M24)"
```

---

## Self-Review

**Spec coverage:**

| Finding | Task | Status |
|---------|------|--------|
| M19 — dead tomli dep | Task 1 | ✅ |
| S24 — imageio → Pillow | Task 2 | ✅ |
| S23 — imageio/tomli-w as runtime dep | Task 3 | ✅ |
| M1 — dead _enqueue_from_rss_feed | Task 4 | ✅ |
| M8 — @dataclass → @attrs.frozen | Task 5 | ✅ |
| M9 — magic numbers in ColorFlash | Task 6 | ✅ |
| M20 — unused --fps parameter | Task 7 | ✅ |
| M21 — no render-emoji-previews target | Task 8 | ✅ |
| M22 — tools/ excluded from lint/format | Task 9 | ✅ |
| M23 — setup-demo-fonts not in .PHONY | Task 10 | ✅ |
| M24 — crypto-ticker.py undated stub | Task 11 | ✅ |

**Placeholder scan:** No TBD/TODO in steps. All code blocks are complete.

**Dependency:** Task 3 depends on Task 2 (imageio must be removed from production code before it can be moved to optional). Tasks 1–11 are otherwise independent.
