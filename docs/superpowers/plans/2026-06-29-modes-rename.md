# Section Modes Rename — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename the three section display modes — `swap`→`slideshow`, `forever_scroll`→`ticker`, `infini_scroll`→`one_at_a_time` — across the engine, config, examples, skills, and docs, with a hard `MigrationError` for the old names.

**Architecture:** P1 is one atomic, releasable PR (engine + migration + examples + skills + the docs a user *follows*); P2 is the long-tail docs sweep. The engine rename must land atomically (a partial rename breaks dispatch). Old names raise `MigrationError` at config-load — no aliases.

**Tech Stack:** Python 3.14, pytest (stubs on `PYTHONPATH=tests/stubs`), ruff, pyright, Astro/Starlight docs.

**Spec:** `docs/superpowers/specs/2026-06-29-modes-rename-design.md`

## Global Constraints
- **Names LOCKED:** `swap`→`slideshow`, `forever_scroll`→`ticker`, `infini_scroll`→`one_at_a_time`.
- The **`gif` mode is UNCHANGED** / out of scope.
- **Back-compat = hard `MigrationError` ONLY** — no alias/canonicalization machinery.
- `MigrationError` (defined `validate.py:42`) is imported LOCALLY inside functions to avoid a circular import (config.py ⇄ validate.py). Call shape: `MigrationError(message, suggested_fix=…)` (the `fix_key`/`fix_replacement_key` kwargs are for KEY renames and do NOT apply to a value rename — omit them).
- **DOCS-STYLE.md** for all docs (no release-history framing, no "footgun"/"gun" metaphors).
- **PEP 649** — no `from __future__ import annotations`.
- **P1 is a BREAKING config change** — the release after P1 gets a prominent breaking note.
- Core gates: `PYTHONPATH=tests/stubs uv run --extra dev pytest`; `uv run --extra dev ruff check src/ tests/` + `ruff format`; `uv run --extra dev pyright src/`.
- Commit trailer on every commit:
  ```
  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01P7r9q2YjKvWBsTSfdPotAh
  ```
- **NON-GOALS:** the `gif` mode; alias machinery; any mode *behavior* change; editing archived `docs/superpowers/` plans.

---

# PHASE 1 — the rename + teaching docs (one releasable PR)

## Task 1: Engine rename + migration (atomic, TDD)

**Files:**
- Modify: `src/led_ticker/app/factories.py` (`RUN_MODES` ~981), `src/led_ticker/ticker.py` (the 3 `run_*` methods + log strings), `src/led_ticker/config.py` (mode default ~665 + migration + comments ~84/120/135/145/153), `src/led_ticker/validate.py` (`VALID_MODES` + ~11 comparisons/hints), any widget files with mode-naming error strings, `src/led_ticker/webui/` literals if any.
- Test: `tests/test_config.py` (migration), plus updates across ~9 test files using `mode=`.

**Interfaces produced:** config values `"slideshow"`, `"ticker"`, `"one_at_a_time"` (+ unchanged `"gif"`); `Ticker.run_slideshow` / `run_ticker` / `run_one_at_a_time`; `validate.VALID_MODES = {"slideshow","ticker","one_at_a_time","gif"}`.

- [ ] **Step 1: Write the failing migration tests** in `tests/test_config.py`:
```python
import pytest
from led_ticker.validate import MigrationError
from led_ticker.config import load_config  # adjust to the actual loader used elsewhere in this test file

@pytest.mark.parametrize("old,new", [
    ("swap", "slideshow"),
    ("forever_scroll", "ticker"),
    ("infini_scroll", "one_at_a_time"),
])
def test_old_mode_name_raises_migration_error(tmp_path, old, new):
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        "[display]\nrows=16\ncols=32\nchain_length=5\n"
        f'[[playlist.section]]\nmode = "{old}"\n'
        '[[playlist.section.widget]]\ntype = "message"\ntext = "hi"\n'
    )
    with pytest.raises(MigrationError) as ei:
        load_config(str(cfg))
    assert new in str(ei.value)            # hint names the new mode
    assert old in str(ei.value)            # and the old one being replaced
```
(Match `load_config`'s real import + signature to how `tests/test_config.py` already loads configs.)

- [ ] **Step 2: Run → fail** — `PYTHONPATH=tests/stubs uv run --extra dev pytest tests/test_config.py -k old_mode_name -v` → FAIL (old names currently load fine).

- [ ] **Step 3: Implement the migration + default** in `src/led_ticker/config.py` at the section loop (~665). Before constructing `SectionConfig`:
```python
        raw_mode = section_raw.get("mode", "ticker")   # default flipped forever_scroll -> ticker
        _MODE_RENAMES = {
            "swap": "slideshow",
            "forever_scroll": "ticker",
            "infini_scroll": "one_at_a_time",
        }
        if raw_mode in _MODE_RENAMES:
            from led_ticker.validate import MigrationError  # local import: avoid config<->validate cycle
            new = _MODE_RENAMES[raw_mode]
            raise MigrationError(
                f'mode = "{raw_mode}" was renamed to "{new}". '
                f'Update your config: mode = "{new}".',
                suggested_fix=f'Rename mode "{raw_mode}" to "{new}".',
            )
        section = SectionConfig(
            mode=raw_mode,
            ...
```
Also update the `mode` field comment at ~84 (`# "slideshow", "ticker", "one_at_a_time", "gif"`) and the inline old-name comments at ~120/135/145/153.

- [ ] **Step 4: Run → pass** the migration tests.

- [ ] **Step 5: Rename `RUN_MODES`** in `src/led_ticker/app/factories.py` (~981):
```python
RUN_MODES: dict[str, str] = {
    "slideshow": "run_slideshow",
    "ticker": "run_ticker",
    "one_at_a_time": "run_one_at_a_time",
    "gif": "run_gif",
}
```

- [ ] **Step 6: Rename the `Ticker` methods** in `src/led_ticker/ticker.py`: `run_swap`→`run_slideshow`, `run_forever_scroll`→`run_ticker`, `run_infini_scroll`→`run_one_at_a_time`, and their log strings (`"Running Swap..."`→`"Running Slideshow..."`, `"Running Forever Scroll..."`→`"Running Ticker..."`, `"Running Infini Scroll..."`→`"Running One-at-a-time..."`). Grep `run_swap|run_forever_scroll|run_infini_scroll` across `src/` to catch any other internal callers and update them.

- [ ] **Step 7: Update `validate.py`** — add near the top: `VALID_MODES = {"slideshow", "ticker", "one_at_a_time", "gif"}`. Replace every user-facing mode string in the rule comparisons + hint text (lines ~219, 224, 232, 252, 263, 272, 276, 947, 959, 964, 996, 999, 1190, 1236, 1243): `"swap"`→`"slideshow"`, `"forever_scroll"`→`"ticker"`, `"infini_scroll"`→`"one_at_a_time"`. (E.g. Rule 26's `section.mode != "forever_scroll"` → `!= "ticker"`; "Prefer mode='swap'" → "mode='slideshow'".) Use `VALID_MODES` wherever the code enumerates the valid set.

- [ ] **Step 8: Sweep remaining src literals** — `grep -rnE "forever_scroll|infini_scroll|mode.*['\"]swap['\"]|['\"]swap['\"].*mode" src/` and update any mode-naming error/hint strings in widget files + `webui/` literals. (The status board carries `section.mode` verbatim — no code change once parse emits new names.)

- [ ] **Step 9: Update test fixtures** — `grep -rlnE "mode=\"(swap|forever_scroll|infini_scroll)\"|mode = \"(swap|forever_scroll|infini_scroll)\"" tests/` → replace with new names (~76 occurrences/~9 files). KEEP the new migration tests (they intentionally use old names). Any test asserting on old run-method names / log strings → update.

- [ ] **Step 10: Full gates** — `PYTHONPATH=tests/stubs uv run --extra dev pytest -q` green; `uv run --extra dev ruff check src/ tests/` + `ruff format`; `uv run --extra dev pyright src/`. Then `grep -rnE "forever_scroll|infini_scroll" src/ tests/` returns nothing (old `swap`-as-mode also gone — but the literal word "swap" may remain in unrelated contexts; verify mode usages specifically).

- [ ] **Step 11: Commit** (`feat(modes)!: rename section modes — swap→slideshow, forever_scroll→ticker, infini_scroll→one_at_a_time (engine + migration)`).

## Task 2: Config examples + file renames

**Files:** all `config/*.toml` using old mode values; `git mv config/config.forever_scroll.toml config/config.ticker.toml` + `git mv config/config.infini_scroll.toml config/config.one_at_a_time.toml`.

- [ ] **Step 1:** `grep -rlnE "mode = \"(swap|forever_scroll|infini_scroll)\"" config/` → update each to the new value.
- [ ] **Step 2:** `git mv` the two mode-named files to `config.ticker.toml` / `config.one_at_a_time.toml`; fix their own `# Usage: cp config/config.<old>.toml config/config.toml` comment lines to the new filenames. (No live-doc/Makefile references exist — verified; archived `docs/superpowers/plans/` mentions are left.)
- [ ] **Step 3: Verify** each renamed/edited example validates: `PYTHONPATH=tests/stubs uv run --extra dev python -m led_ticker.validate config/config.ticker.toml` (and the others). `grep -rnE "forever_scroll|infini_scroll" config/` → nothing.
- [ ] **Step 4: Commit** (`docs(config): update examples + rename mode-named example files to new mode names`).

## Task 3: Skills + CLAUDE.md

**Files:** `.claude/skills/creating-a-config/SKILL.md` (2), `.claude/skills/creating-a-config/references/snippets.md` (8), any other `references/*.md` with mode mentions; `CLAUDE.md`.

- [ ] **Step 1:** `grep -rnE "forever_scroll|infini_scroll|mode.*swap" .claude/skills/creating-a-config/ CLAUDE.md` → update each mode mention to the new name (incl. the `mode = "..."` snippet values + any prose). Watch for the snippet TOML values (must stay valid — new names).
- [ ] **Step 2: Verify** `grep -rnE "forever_scroll|infini_scroll" .claude/skills/ CLAUDE.md` → nothing.
- [ ] **Step 3: Commit** (`docs(skills): config-skill fact-packs + CLAUDE.md to new mode names`).

## Task 4: Teaching docs (bundled so following the docs can't mislead)

**Files:** `docs/site/src/content/docs/concepts/sections-and-modes.mdx` (prose rewrite), `tutorial/02-first-config.mdx`, `tutorial/03-multi-widget.mdx`, `tutorial/04-custom-branding.mdx`, `reference/config-options.mdx`, `getting-started.mdx`, `pitfalls.mdx`.

- [ ] **Step 1: Rewrite `concepts/sections-and-modes.mdx`** — this is the canonical concept page; don't just find-replace. Rewrite each mode's description with the new name + a clear one-line "what it looks like": `slideshow` (one widget at a time, holds then transitions), `ticker` (all widgets in one continuous side-by-side stream, looping), `one_at_a_time` (each widget scrolls fully across and off before the next). DOCS-STYLE compliant.
- [ ] **Step 2:** update the other teaching pages (tutorials 02/03/04, config-options reference's `[[playlist.section]] mode` field, getting-started, pitfalls) to the new names — find-replace + read-through for any prose that explains the old name.
- [ ] **Step 3: Verify** `make docs-build` + `make docs-lint` clean; `grep -rnE "forever_scroll|infini_scroll" <the 7 teaching files>` → nothing. (Long-tail docs may still mention old names until P2 — that's expected.)
- [ ] **Step 4: Commit** (`docs: rewrite sections-and-modes + teaching pages for the new mode names`).

**P1 done =** new names work; the 3 old names raise `MigrationError` with a hint; code/tests/examples/skills/CLAUDE + every teaching doc use the new names; suite + `make docs-build`/`docs-lint` green. **Open the P1 PR; pause for merge.** (Release after merge carries the BREAKING-config note; bump decided by the maintainer.)

---

# PHASE 2 — long-tail docs sweep (separate PR, after P1 merges)

## Task 5: Sweep the remaining docs + add a repo-wide tripwire

**Files:** `docs/site/src/content/docs/widgets/{two_row,image,gif,clock}.mdx`, `hardware/{smallsign,bigsign}.mdx`, `tools/{validate,gif-plan}.mdx`, + any a fresh grep surfaces; a new tripwire test.

- [ ] **Step 1:** `grep -rlnE "forever_scroll|infini_scroll" docs/site/` → update every remaining page to the new names (find-replace + a read-through so no sentence still explains the old behavior under the old name).
- [ ] **Step 2: Add a tripwire test** `tests/test_no_legacy_mode_names.py`:
```python
import subprocess, pathlib
REPO = pathlib.Path(__file__).resolve().parents[1]
def test_no_legacy_mode_names_anywhere():
    # Old mode names must not survive outside the archived planning docs.
    r = subprocess.run(
        ["grep", "-rnE", "forever_scroll|infini_scroll",
         "src", "tests", "config", ".claude",
         "docs/site/src/content/docs"],
        cwd=REPO, capture_output=True, text=True,
    )
    # grep exits 1 (no matches) on success; 0 means a leftover was found.
    assert r.returncode == 1, f"legacy mode names still present:\n{r.stdout}"
```
(Scope excludes `docs/superpowers/` — archived plans legitimately mention the old names.)
- [ ] **Step 3: Verify** the tripwire passes; `make docs-build` + `make docs-lint` + `make docs-check-llms` clean; full suite green.
- [ ] **Step 4: Commit** (`docs: sweep remaining mode-name mentions + add no-legacy-mode-names tripwire`). Open the P2 PR; pause for merge.

---

## Self-Review
**Spec coverage:** RUN_MODES + method rename + config default/migration + validate + error strings → Task 1; examples + file renames → Task 2; skills/CLAUDE → Task 3; teaching docs (concept rewrite + tutorials + config-options + getting-started + pitfalls) → Task 4; long-tail sweep + tripwire → Task 5. ✅
**Placeholders:** migration test + the config.py migration block + RUN_MODES + the tripwire test carry real code; validate.py edits are enumerated by line; the concept-page rewrite is a genuine-prose task with the per-mode content specified. The `load_config` import in Task 1 is flagged "match the test file's real loader" (one lookup, not a placeholder).
**Consistency:** new names + `VALID_MODES` + the `run_*` method names are identical across Tasks 1–5; the MigrationError call shape matches `validate.py:42` (message + suggested_fix, no fix_key for a value rename).
**Notes for the executor:** Task 1 is atomic (a partial rename breaks dispatch) — do all of it in one task; the migration tests are the TDD anchor. The tripwire (Task 5) would FAIL during P1 (long-tail docs still have old names), so it's only added in P2 after the sweep.
