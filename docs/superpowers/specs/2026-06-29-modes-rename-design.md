# Rename the section display modes — Design

**Date:** 2026-06-29
**Status:** Approved (brainstorm)
**Board item:** `project_modes_rename`

## Goal

Rename led-ticker's three confusing section `mode` values to clear, intentional names. `mode` is the user-facing per-section key in `config.toml` (`[[playlist.section]] mode = "..."`).

| current | → new | what the mode does |
|---|---|---|
| `swap` | **`slideshow`** | one widget at a time: hold (scroll only if too wide) → transition → next |
| `forever_scroll` | **`ticker`** | ALL widgets in one continuous side-by-side stream, looping endlessly |
| `infini_scroll` | **`one_at_a_time`** | widgets scroll one at a time, each fully off before the next |

(The `gif` mode is unaffected and out of scope.)

## Locked decisions (from the brainstorm)

- **Names:** as above — not re-litigated.
- **Back-compat: hard `MigrationError`.** The old names raise at config-load with a per-name hint; no alias/canonicalization. Rationale: no confirmed third-party production signs (James updates his own gitignored configs before pulling). Cleanest end state, zero alias code.
- **Phasing: 2 phases.** P1 = the rename + the docs a user *follows to write a config* (so following the docs can never produce a now-invalid name) = **one releasable PR**. P2 = the long-tail passing-mention docs sweep.

## P1 — the rename (one releasable PR)

### Code (`src/led_ticker/`)
- **`app/factories.py` `RUN_MODES`** (line ~981): keys become the new names → renamed methods:
  ```python
  RUN_MODES = {"ticker": "run_ticker", "one_at_a_time": "run_one_at_a_time", "slideshow": "run_slideshow", "gif": "run_gif"}
  ```
- **Internal `Ticker` method rename (in scope, P1):** `run_swap`→`run_slideshow`, `run_forever_scroll`→`run_ticker`, `run_infini_scroll`→`run_one_at_a_time` in `ticker.py` (+ their log strings "Running Swap"→"Running Slideshow" etc.). Not user-facing; renamed for code coherence with the config.
- **`config.py`:**
  - The section-mode **default** (line ~665, `section_raw.get("mode", "forever_scroll")`) → `"ticker"`.
  - The `mode` field comment (line ~84) + the inline comments referencing old mode names (lines ~120, 135, 145, 153) → new names.
  - **Migration:** when a section's raw `mode` is one of the three OLD names, raise `MigrationError` with the hint:
    - `swap` → `'mode = "swap" was renamed — use mode = "slideshow".'`
    - `forever_scroll` → `'mode = "forever_scroll" was renamed — use mode = "ticker".'`
    - `infini_scroll` → `'mode = "infini_scroll" was renamed — use mode = "one_at_a_time".'`
    (Raise at the earliest config-load point that sees the raw value — section parse in `config.py` is preferred; `MigrationError` is currently used in `factories.py`, so import/raise it consistently. Impl chooses the exact site; behavior = error-at-load with the hint.)
- **`validate.py`:** the ~11 inline mode string comparisons + human-readable hints → new names; introduce a `VALID_MODES` constant (`{"slideshow","ticker","one_at_a_time","gif"}`) so the set lives in one place. Rule 26 (the `forever_scroll`-only knob check) updates to `ticker`.
- **Mode-naming error strings** in the few widget files that name modes (grep `forever_scroll`/`infini_scroll`/`swap` in `src/`) → new names.
- **Status board / webui JSON:** carries `section.mode` verbatim; once parse only ever emits new names, this auto-follows. No webui code change beyond any literal mode strings in `webui/` (grep).

### Tests
- A migration-error test per old name (asserts `MigrationError` raised at load with the new-name hint).
- Update existing test fixtures (`SectionConfig(mode="forever_scroll")` etc., ~76 occurrences across ~9 test files) to the new names.
- Full suite green; `ruff` + `pyright`.

### Examples + skills
- Update the 9 `config/*.toml` examples that use old mode values.
- **Rename the 2 mode-named files:** `config.forever_scroll.toml`→`config.ticker.toml`, `config.infini_scroll.toml`→`config.one_at_a_time.toml` + fix their own `# Usage: cp config/config.<old>.toml ...` comments. (No live-doc/Makefile references — verified; only archived `docs/superpowers/plans/` mention them, which we leave.)
- `.claude/skills/creating-a-config/` fact-packs (`references/*.md`, `snippets.md`) + `CLAUDE.md` mode mentions → new names.

### Teaching docs (bundled with the code so the docs a user follows are correct)
Update these in P1 (the "follow-to-write-a-config" set, by mention count):
- **`concepts/sections-and-modes.mdx`** (18 mentions) — the canonical concept page: a genuine **prose rewrite** of what each mode does (not just find-replace), with the new names.
- **`tutorial/02-first-config.mdx`** (5), **`tutorial/03-multi-widget.mdx`** (9), **`tutorial/04-custom-branding.mdx`** (2).
- **`reference/config-options.mdx`** (5) — the `[[playlist.section]] mode` field.
- **`getting-started.mdx`** (1) + **`pitfalls.mdx`** (3) — prominent user-facing pages.

### P1 done = 
new names work; the 3 old names error at load with a helpful hint; all code/tests/examples/skills/CLAUDE + every teaching doc use the new names; suite + `make docs-build`/`docs-lint` green. **Releasable.**

## P2 — long-tail docs sweep (separate PR)
Mechanical find-replace of the remaining passing-mention pages: `widgets/{two_row,image,gif,clock}.mdx`, `hardware/{smallsign,bigsign}.mdx`, `tools/{validate,gif-plan}.mdx`, and any others a grep surfaces. Subagent-friendly.

**P2 done =** `grep -rE "forever_scroll|infini_scroll" docs/site/ config/ src/ tests/ .claude/` returns nothing (a tripwire test asserts this); `make docs-build`/`docs-lint`/`docs-check-llms` clean.

## Release
P1 is a **breaking config change** (old `mode` values now error). The release after P1 gets a prominent "BREAKING (config): section `mode` names renamed — `swap`→`slideshow`, `forever_scroll`→`ticker`, `infini_scroll`→`one_at_a_time`" note. Bump decision (clearly-marked minor vs major) made at release time by the maintainer.

## Non-goals
- The `gif` mode (unchanged). The alias/deprecation machinery (explicitly NOT built — `MigrationError` instead). Any behavior change to the modes themselves. The archived `docs/superpowers/` plans (left as historical).

## Effort
P1 ≈ 1 day (code+tests+examples+skills+migration ≈ half-day; teaching docs ≈ half-day, the concept-page rewrite being the careful part). P2 ≈ half-day. ~1.5 days total.

## Process
brainstorm (this) → writing-plans (phase the tasks) → subagent-driven execution. P1 and P2 are separate PRs; pause for merge per PR. The concept-page rewrite + the migration tests are the parts that need care; the long-tail sweep is mechanical.
