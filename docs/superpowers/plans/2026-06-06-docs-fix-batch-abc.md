# Docs Fix Batch A+B+C (Phase 3b) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Fix the audit's correctness (A), etherscan key (B — code+docs), and consistency (C) findings in one PR.

**Architecture:** One code change (etherscan reads `ETHERSCAN_API_KEY` from `.env`) + a new test; ~8 mechanical doc corrections; ~3 consistency edits. Driven by the findings report.

**Source spec:** `docs/superpowers/specs/2026-06-06-docs-fix-batch-abc-design.md`
**Findings report (the edit list):** `docs/superpowers/specs/2026-06-06-docs-audit-findings.md`

**Worktree:** `.claude/worktrees/docs-audit`, branch `feat/docs-audit`. **Commit:** `git -c core.hooksPath=/dev/null commit`. **Lint:** `uv run --extra dev ruff check src/ tests/` before committing Python.

---

### Task 1: Etherscan — wire `ETHERSCAN_API_KEY` from `.env` (code + test, TDD)

**Files:** `src/led_ticker/widgets/crypto/etherscan.py`; `tests/test_widgets/test_etherscan.py` (new).

- [ ] **Step 1: Write the failing test** `tests/test_widgets/test_etherscan.py`. Mirror `tests/test_widgets/test_weather.py`'s session-mocking + `monkeypatch.setenv`. Cover: (a) `ETHERSCAN_API_KEY` set + no TOML `api_key` → `update()` issues the request with the env key (assert the mocked `session.get` was called with `params["apikey"]` == env value); (b) explicit TOML `api_key` wins over the env var; (c) neither set → `update()` raises `ValueError` mentioning `ETHERSCAN_API_KEY`. Read `test_weather.py` first to match the mock style (a fake `session` whose `.get(...)` async-context-manager returns a `.json()` with a valid `{"result": {"SafeGasPrice":..,"ProposeGasPrice":..,"FastGasPrice":..}}`). Keep lines ≤ 88 cols.

- [ ] **Step 2: Run it — expect FAIL** (`api_key` is still required / no env fallback):
```bash
cd /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/docs-audit
PYTHONPATH=tests/stubs uv run python -m pytest tests/test_widgets/test_etherscan.py -q; echo "EXIT=$?"
```

- [ ] **Step 3: Implement** in `src/led_ticker/widgets/crypto/etherscan.py`:
  - Add `import os` (top, with the other stdlib imports).
  - Change the attrs field `api_key: str` → `api_key: str = ""`.
  - In `start(...)`, change the `api_key: str` param → `api_key: str = ""`.
  - In `update()`, before building `params`, resolve and validate:
    ```python
    api_key = self.api_key or os.getenv("ETHERSCAN_API_KEY", "")
    if not api_key:
        raise ValueError(
            "ETHERSCAN_API_KEY not set. Add it to your .env file "
            "(or set api_key in the widget config)."
        )
    ```
    and use `api_key` (the local) in `params["apikey"]` instead of `self.api_key`.
  - Note: `api_key` is no longer a mandatory field; `start`'s `**kwargs` filter is unaffected. (attrs field ordering: `api_key` already follows `session`; giving it a default is fine since `padding`/`hold_time` after it also have defaults.)

- [ ] **Step 4: Run test + ruff — expect PASS:**
```bash
cd /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/docs-audit
PYTHONPATH=tests/stubs uv run python -m pytest tests/test_widgets/test_etherscan.py -q; echo "TEST=$?"
uv run --extra dev ruff check src/ tests/; echo "RUFF=$?"
```
Expected: all pass, exits 0.

- [ ] **Step 5: Commit**
```bash
git add src/led_ticker/widgets/crypto/etherscan.py tests/test_widgets/test_etherscan.py
git -c core.hooksPath=/dev/null commit -m "fix: etherscan reads ETHERSCAN_API_KEY from .env (like weather)

api_key is now optional; update() falls back to os.getenv('ETHERSCAN_API_KEY')
and raises a clear ValueError if neither the env var nor the config field is
set. Makes the documented .env path actually work; existing api_key configs
still work. + test."
```

---

### Task 2: Etherscan docs — make them match the working `.env` path

**Files:** `docs/site/src/content/docs/widgets/etherscan.mdx`; `docs/site/demos-long/widget-etherscan.toml`; the etherscan fact-pack under `docs/content-source/` (find it: `grep -rl etherscan docs/content-source/`).

- [ ] **Step 1:** In `widgets/etherscan.mdx`, present the `.env` path as primary and correct: the key goes in `.env` as `ETHERSCAN_API_KEY`; no `api_key` is needed in the TOML; mention the TOML `api_key` field still works as an alternative. Remove the current contradiction (it shows a placeholder TOML `api_key` string while telling the reader to use `.env`). Mirror the phrasing of `widgets/weather.mdx`'s key section for consistency.
- [ ] **Step 2:** Ensure `docs/site/demos-long/widget-etherscan.toml` has no bogus `api_key` line and keeps its `# requires-env: ETHERSCAN_API_KEY` marker (this now works).
- [ ] **Step 3:** Update the etherscan fact-pack's `api_key` entry so it describes the `.env`-first story (drop "reference it in config" if it implies env-substitution-in-TOML, which doesn't exist).
- [ ] **Step 4:** `make docs-format && make docs-build && make docs-lint` (all exit 0). Commit:
```bash
git add docs/site/src/content/docs/widgets/etherscan.mdx docs/site/demos-long/widget-etherscan.toml docs/content-source/
git -c core.hooksPath=/dev/null commit -m "docs: etherscan key lives in .env (now that the code reads it)"
```

---

### Task 3: Batch A — correctness doc corrections

Apply each exact fix from the findings report (`2026-06-06-docs-audit-findings.md`, the must-fix table). Read each page to get the current text, then edit.

**Files & fixes:**
- [ ] `widgets/gif.mdx` — replace BOTH `hold_seconds` → `hold_time` (the cycling caption + the floor note). Verify `grep -c hold_seconds` == 0 after.
- [ ] `tools/render-demo.mdx` — remove the `--fps N` table row (no such flag). Keep/representation of the 20fps/50ms cadence may move to prose. (Optional: add the required `config` positional row.)
- [ ] `reference/cli.mdx` — add a `led-ticker plugins` subcommand section (read the real CLI `src/led_ticker/app/cli.py` to describe it accurately: prints loaded/failed plugins, takes `--config`/`-c`); add `--fix` to the `validate` flag table AND the Tips enumeration (in-place key-rename migration; "comments not preserved").
- [ ] `tutorial/02-first-config.mdx` — fix the `--duration 20` advice (not forwarded by `make render-demo`): drop it OR show `uv run python tools/render_demo/render.py config/config.toml -o preview.gif --duration 20`.
- [ ] `tutorial/03-multi-widget.mdx` — reword "hi-res path activates when `default_scale > 1`" to "activates when the effective (per-section) scale is ≥ 2 and the band is tall enough" (matches the mechanism the chapter demonstrates).
- [ ] `tutorial/05-polish.mdx` — fix dead link `/reference/config-pitfalls/` → `/pitfalls/`, and its link text to "Validation rules" (the real page title).
- [ ] `concepts/borders.mdx` — change the Lightbulbs example block from `[[section]]`/`[[section.widget]]` to `[[playlist.section.widget]]`.
- [ ] `hardware/longboi.mdx` — change the `gpio_slowdown` "Why" from "Raise to 4–5 if flicker persists" to "Raise to 6+ if flicker persists" (value is already 5).

- [ ] **Verify + commit:**
```bash
cd /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/docs-audit
make docs-format && make docs-build; echo "BUILD=$?"; make docs-lint; echo "LINT=$?"
grep -rn "hold_seconds" docs/site && echo "STILL HAS hold_seconds" || echo "hold_seconds gone"
grep -rn "config-pitfalls" docs/site && echo "STILL HAS config-pitfalls" || echo "config-pitfalls gone"
grep -n -- "--fps" docs/site/src/content/docs/tools/render-demo.mdx && echo "STILL HAS --fps" || echo "--fps gone"
git add -A docs/site/src/content/docs
git -c core.hooksPath=/dev/null commit -m "docs: correctness fixes from the audit (batch A)

gif hold_time field name; remove phantom render-demo --fps flag; document the
cli plugins subcommand + validate --fix; fix tutorial-02 --duration advice,
tutorial-03 hi-res trigger, tutorial-05 dead pitfalls link; borders TOML path;
longboi gpio_slowdown note."
```

---

### Task 4: Batch C — consistency

- [ ] `pitfalls.mdx` — add a bottom `RelatedPages` CTA (import the component if not already imported; slugs `tools/validate`, `getting-started`, `transitions`).
- [ ] **Unify the validate command** on the bare `led-ticker validate config/config.toml` form: in `pitfalls.mdx`, change any `make validate CONFIG=…` to the bare form (the rest of the site already uses bare). (tutorial-05's link text already handled in Task 3.)
- [ ] **Verify + commit:**
```bash
cd /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/docs-audit
make docs-format && make docs-build; echo "BUILD=$?"; make docs-lint; echo "LINT=$?"
git add docs/site/src/content/docs/pitfalls.mdx
git -c core.hooksPath=/dev/null commit -m "docs: consistency — pitfalls CTA + unify the validate command form (batch C)"
```

---

### Task 5: Tech-writer review + final verification

- [ ] **Step 1: Tech-writer reviewer** over the edited pages (especially `widgets/etherscan.mdx`, `reference/cli.mdx`, `pitfalls.mdx`) + a quick hobbyist-persona pass on the etherscan page ("can I set up the key now?"). Apply must-fix; re-build/lint.
- [ ] **Step 2: Full verification:**
```bash
cd /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/docs-audit
make docs-build; echo "BUILD=$?"
make docs-lint; echo "LINT=$?"
uv run --extra dev ruff check src/ tests/; echo "RUFF=$?"
PYTHONPATH=tests/stubs uv run python -m pytest tests/test_widgets/test_etherscan.py tests/test_widgets/test_weather.py -q; echo "TEST=$?"
```
Expected: all exit 0.
- [ ] **Step 3:** Commit any review fixes.

---

## Self-Review

**1. Spec coverage:** A (8 corrections) → Task 3. B (etherscan code+test+docs) → Tasks 1–2. C (pitfalls CTA + validate-form + page-name) → Tasks 3–4. Review + verify (build/lint/ruff/test) → Task 5. ✓ Out of scope (batch D, the validate.py:70 code bug, route renames) → respected. ✓

**2. Placeholder scan:** No TBD/TODO; the per-page fixes name the exact change (the findings report carries the quoted current text). ✓

**3. Consistency:** The etherscan code design matches `weather.py`'s env pattern; `api_key` default-empty keeps the `start()` kwargs filter and attrs field-ordering valid (defaulted field followed by other defaulted fields). The C decisions (bare `led-ticker validate`; keep "Validation rules" title) are applied consistently. Verification greps (hold_seconds, config-pitfalls, --fps) match the edits. Ruff is run because Task 1 touches `src/` + `tests/`. ✓
