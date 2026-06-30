# Task 5 Report — Phase 2 Modes Rename: Long-tail sweep + demo renames + tripwire

**Commit:** `90fb3b06`
**Branch:** `feat/modes-rename-p2`
**Status:** COMPLETE — all verifications pass, hooks clean, full suite green.

---

## Counts swept by area

| Area | Files | Replacements |
|------|-------|-------------|
| `docs/site/demos-long/` TOMLs | 23 | ~55 mode values + comment text |
| `docs/site/demos-pinned/` TOMLs | 81 | ~82 mode values |
| `docs/site/demos/` TOMLs | 6 | ~6 mode values |
| `docs/site/src/content/docs/` MDX | 10 | ~30 prose + code-block occurrences |
| `docs/content-source/` markdown | 4 | 4 table-cell + prose occurrences |
| `README.md` | 1 | 1 hero GIF URL |
| **Total** | **125 files** | **~178 replacements** |

---

## Renames completed

| Old path | New path |
|----------|----------|
| `docs/site/demos-long/sections-forever_scroll.toml` | `sections-ticker.toml` |
| `docs/site/demos-long/sections-infini_scroll.toml` | `sections-one_at_a_time.toml` |
| `docs/site/public/demos-long/sections-forever_scroll.gif` | `sections-ticker.gif` |
| `docs/site/public/demos-long/sections-infini_scroll.gif` | `sections-one_at_a_time.gif` |

All 4 renames were done via `git mv` so git tracks them as renames (not add+delete).

### All references updated

- `docs/site/src/content/docs/concepts/sections-and-modes.mdx` — 2 `src=` GIF URLs updated.
- `README.md` — hero GIF URL updated to `sections-ticker.gif`.
- No render manifest, Makefile targets, or test files enumerated these config names by literal string (demo-drift test uses `glob("*.toml")`, not a hard-coded list).

---

## Tripwire: `tests/test_no_legacy_mode_names.py`

**Approach:** Pure-Python `rglob` + regex scan (no subprocess/grep), so it works on any platform and within the standard pytest run.

**Patterns checked:**
- `mode\s*=\s*"swap"` — catches the mode VALUE in TOML/prose
- `\bforever_scroll\b` — bare identifier in any file
- `\binfini_scroll\b` — bare identifier in any file

**Allowlist (file-level, 5 entries):**
| File | Reason |
|------|--------|
| `src/led_ticker/config.py` | `_MODE_RENAMES` migration map (the keys are the old names) |
| `src/led_ticker/validate.py` | User-facing migration error message mentions old names by string |
| `tests/test_config.py` | `TestModeMigration` parametrize inputs contain old names |
| `tests/test_validate.py` | Docstring + comment mention old names for context |
| `tests/test_no_legacy_mode_names.py` | The file itself contains the patterns as regex strings |

**Excluded dirs (prefix-based):**
- `docs/superpowers/` — archived implementation plans; legitimately reference old names for historical context
- `docs/site/dist/` — build output; regenerated from sources already checked
- `.git/` — git objects

The exclusion uses a relative-path-prefix check (`startswith(prefix + "/")`) so subdirectories like `docs/superpowers/plans/` are correctly excluded.

---

## Verify results

```
# Grep checks — all returned 0 results:
grep -rnE "forever_scroll|infini_scroll" docs/site/ docs/content-source/  → 0
grep -rnE 'mode = "swap"' docs/site/ docs/content-source/                 → 0
find docs/site -name "*forever_scroll*" -o -name "*infini_scroll*"        → 0

# Tripwire test:
PYTHONPATH=tests/stubs uv run --extra dev pytest tests/test_no_legacy_mode_names.py -v
→ 1 passed in 0.62s

# Full suite:
PYTHONPATH=tests/stubs uv run --extra dev pytest -q
→ 3080 passed, 2 skipped in 66.16s

# Ruff:
uv run --extra dev ruff check src/ tests/
→ All checks passed!

# Docs build:
make docs-build → 66 page(s) built — Complete!

# Docs lint:
make docs-lint → 0 errors, 0 warnings, 0 hints

# Docs llms check:
make docs-check-llms → check-llms OK: llms.txt + llms-full.txt present
```

---

## Concerns / notes

- `validate.mdx` line 172 retains `"swap fields to the correct scope"` — this is the English verb "swap" referring to TOML field placement (the `scroll_speed_ms` / `scroll_step_ms` scope mismatch), not a mode name. Left as-is.
- The word "swap" appears as a Python API name throughout `CLAUDE.md` and internal docs (`frame.swap()`, `SwapOnVSync`, `_swap_and_scroll`). These are method/function names, not mode values, and are correctly untouched.
- No stale old-name references were found in `src/` beyond the intentional migration map in `config.py` and the user error message in `validate.py`.
- `gif` mode: UNCHANGED throughout, as specified.

---

## Fix note — review finding: prose backtick references missed by Phase 2

**Commit:** TBD (follow-up to `90fb3b06`)

### Prose references fixed (7 total)

| File | Line | Change |
|------|------|--------|
| `docs/site/src/content/docs/tutorial/05-polish.mdx` | 286 | `` `swap` mode `` → `` `slideshow` mode `` |
| `docs/site/src/content/docs/concepts/animations.mdx` | 56 | `` `swap` mode `` → `` `slideshow` mode `` |
| `docs/site/src/content/docs/transitions/index.mdx` | 8 | `` `swap` mode `` → `` `slideshow` mode `` |
| `docs/site/src/content/docs/widgets/two_row.mdx` | 13 | `` `swap` mode `` → `` `slideshow` mode `` |
| `docs/site/src/content/docs/concepts/how-rendering-works.mdx` | 42 | `` `swap` `` (mode ref) → `` `slideshow` `` |
| `docs/site/src/content/docs/concepts/how-rendering-works.mdx` | 52 | "unrelated to the `swap` section mode" → "unrelated to the `slideshow` section mode" |
| `docs/site/src/content/docs/widgets/clock.mdx` | 152 | "its own `swap` section" → "its own `slideshow` section" |

Additionally fixed non-mode `` `swap` `` references that would have tripped the new prose pattern:

| File | Line | Change |
|------|------|--------|
| `docs/plugin-system.md` | 280 | `` `swap` `` (referring to Backend protocol method) → `` `swap()` `` — disambiguated to method form |
| `docs/site/src/content/docs/plugins/api-reference.mdx` | 211 | `setup`, `create_canvas`, `swap`, `brightness` → all as `()` forms for consistency |
| `src/led_ticker/widgets/two_row.py` | 7 | Module docstring `` `swap` mode `` → `` `slideshow` mode `` |

### Tripwire hardening

Added `_DOCS_PATTERNS` list to `tests/test_no_legacy_mode_names.py`:

```python
_DOCS_PATTERNS = [
    re.compile(r'[`"](swap|forever_scroll|infini_scroll)[`"]'),
]
```

This is scoped to `.md`/`.mdx` files only (via `_DOCS_SUFFIXES`) to avoid false-positives from Python string literals that legitimately contain `"swap"` as a method or attribute name (e.g., `n.func.attr == "swap"` in `test_engine_redraw_contract.py`, `order.append("swap")` in `test_frame.py`).

Also extended `_EXCLUDED_DIR_PREFIXES` with two entries:
- `.superpowers/` — agent task reports; historical records that legitimately reference old names
- `docs/site/node_modules/` — third-party npm packages bundled with the docs site

### Legit `` `swap` `` uses disambiguated

No allowlist entries needed. All genuine method/API references were rewritten to unambiguous forms (`swap()`, `swap()`), so the docs-only pattern matches only mode-name prose without exceptions.

### Verify
- `grep -rnE '[` + "`" + `"](swap|forever_scroll|infini_scroll)[` + "`" + `"]' docs/site docs/content-source` → 0 results
- `PYTHONPATH=tests/stubs uv run --extra dev pytest tests/test_no_legacy_mode_names.py -v` → 1 passed
- `PYTHONPATH=tests/stubs uv run --extra dev pytest -q` → 3080 passed, 2 skipped
- `make docs-build` → 66 page(s) built, Complete!
- `make docs-lint` → 0 errors, 0 warnings, 0 hints

---

## Fix note — adversarial-review findings (4 items)

**Commit:** `8deb11f7`

### 1. Tripwire single-quote gap (FIXED)

The original `mode\s*=\s*"swap"` pattern only caught double-quoted TOML values.
`mode = 'swap'` (single quotes — valid TOML) slipped through undetected.

Changed to:
```python
re.compile(r"""mode\s*=\s*['"]swap['"]""")
```

Verified the new regex catches `mode = 'swap'`, `mode = "swap"`, `mode='swap'`, and `mode="swap"`, and does not false-positive on `mode = "slideshow"` or unquoted `# mode = swap`.

### 2. Demo file rename (FIXED)

`git mv` renamed:
- `docs/site/demos-long/sections-swap.toml` → `sections-slideshow.toml`
- `docs/site/public/demos-long/sections-swap.gif` → `sections-slideshow.gif`

Updated `src=` reference in `docs/site/src/content/docs/concepts/sections-and-modes.mdx` line 101.
No Makefile, Python, or other file referenced `sections-swap` by literal string — grep confirmed clean.

### 3. Stale comments in validate.py (FIXED)

Lines ~2066 and ~2070: `requires mode=swap` → `requires mode=slideshow` in both comments.

### 4. Stale private helper names in validate.py (FIXED)

Renamed:
- `_check_wraps_forever_swap_only` → `_check_wraps_slideshow_only`
- `_check_scroll_through_swap_only` → `_check_scroll_through_slideshow_only`

Updated both call sites (same block, lines ~2067 and ~2071). Behavior unchanged — pure rename.

### Verify (all passed)

```
grep -n "_forever_swap_only|_swap_only|mode=swap" src/led_ticker/validate.py → 0 results
grep -rn "sections-swap" docs/site/src docs/site/public Makefile            → 0 results
PYTHONPATH=tests/stubs uv run --extra dev pytest tests/test_no_legacy_mode_names.py tests/test_validate.py -q
→ 159 passed
PYTHONPATH=tests/stubs uv run --extra dev pytest -q → 3080 passed, 2 skipped
uv run --extra dev ruff check src/ tests/ → All checks passed!
uv run --extra dev ruff format src/ tests/ → 234 files left unchanged
uv run --extra dev pyright src/ → 0 errors, 0 warnings, 0 informations
make docs-build → 66 page(s) built, Complete!
make docs-lint → 0 errors, 0 warnings, 0 hints
```
