# Calendar Extraction — Phase 3: Core Removal — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the now-extracted `calendar` widget from led-ticker core — delete the widget, its calendar-only deps, the three calendar `validate.py` rule branches, and its FieldHints — and leave a migration breadcrumb so `type = "calendar"` raises a clear "install led-ticker-calendar, use calendar.events" error.

**Architecture:** Surgical deletions plus one rename (`_CRYPTO_MIGRATION` → `_EXTRACTED_TYPES`) with a new `calendar` entry, a `plugins_catalog.json` entry, and CLAUDE.md/example-config updates. The generic plugin-validation warnings channel (Phase 1, rule 55) stays and now serves the plugin's `calendar.events` advisory warnings — so removing the calendar-specific validate branches loses no behavior for plugin users. **Breaking change:** deployed signs must add `led-ticker-calendar` to `requirements-plugins.txt` and migrate `type = "calendar"` → `type = "calendar.events"`. Docs-site changes are Phase 4.

**Tech Stack:** Python 3.14, uv, pytest (`PYTHONPATH=tests/stubs`).

---

## Prerequisites
- Phases 1 (core warnings channel) and 2 (led-ticker-calendar plugin) are **merged**. The plugin provides `calendar.events`; core can safely drop the bare `calendar` widget.
- Work on branch `worktree-calendar-phase3-core-removal` in the led-ticker worktree. NEVER `main`.
- After all tasks: open a core PR, CI green, and **STOP — do not merge** (deploy coordination first).

## Verified facts (from the live tree)
- Core non-test files referencing `calendar`: `widgets/calendar.py` (delete), `widgets/__init__.py` (auto-import line ~41), `validate.py` (3 rule branches), `busy_light.py` (a COMMENT only — leave it).
- Calendar-only deps in `pyproject.toml` (lines ~18–19): `icalendar>=6.1`, `recurring-ical-events>=3.0` — no other core importer.
- `factories.py`: Calendar `FieldHint`s (lines ~236–252, `ics_url`→`highlight_color`); extracted-types migration table `_CRYPTO_MIGRATION` (line ~327); no `calendar` in the dispatch/applicable-types maps.
- `validate.py`: `_check_calendar_ics_paths` (def line ~758; called line ~1988); `wtype == "calendar"` branch inside `_check_band_layout` (def ~1128); `wtype == "calendar"` branch inside `_check_held_top_text_overflow` (def ~1393, called ~1986).
- Core test files referencing calendar (besides the moved ones): `tests/test_border_surface_drift.py` (line 48 — a widget-type tuple), `tests/test_plugin_extraction_readiness.py` (the `widgets/calendar.py` allowlist entry). `tests/test_validate.py` has ZERO calendar refs. `tests/test_plugin_validation_warnings.py` mentions calendar only in a docstring (no change).
- The moved test files (`tests/test_widgets/test_calendar*.py`, 6 files) and fixtures (`tests/fixtures/calendar_sample.ics`, `tests/fixtures/calendar_corpus/`) still exist in core and must be DELETED (they live in the plugin now).
- `config/config.calendar_smoketest.toml` exists (delete — moved to plugin); `config/config.example.toml` has only a busy-light COMMENT mentioning calendar (line ~192), no calendar widget block.

---

### Task 1: Delete the widget + deregister + drop deps

**Files:**
- Delete: `src/led_ticker/widgets/calendar.py`
- Modify: `src/led_ticker/widgets/__init__.py`, `pyproject.toml`, `uv.lock`

- [ ] **Step 1: Delete the widget module.**

```bash
git rm src/led_ticker/widgets/calendar.py
```

- [ ] **Step 2: Remove the auto-import.** In `src/led_ticker/widgets/__init__.py`, delete the `calendar,` entry from the auto-import list (~line 41). Confirm the surrounding import statement stays syntactically valid (it's a multi-name import block — remove only the `calendar,` line).

- [ ] **Step 3: Drop the deps.** In `pyproject.toml`, delete the `"icalendar>=6.1",` and `"recurring-ical-events>=3.0",` lines from `[project] dependencies`.

- [ ] **Step 4: Refresh the lock + reinstall.**

Run: `uv lock && uv sync --extra dev`
Expected: resolves; icalendar / recurring-ical-events drop from the lock (they may remain as transitive of nothing — confirm they're gone or only present if another dep needs them; they should disappear).

- [ ] **Step 5: Verify core still imports + `calendar` is no longer registered.**

Run: `PYTHONPATH=tests/stubs uv run python -c "import led_ticker.widgets; from led_ticker.widgets import get_widget_class; print('calendar' in __import__('led_ticker.widgets', fromlist=['_WIDGET_REGISTRY'])._WIDGET_REGISTRY)"`
Expected: prints `False` (calendar gone from the registry). No ImportError.

Run: `PYTHONPATH=tests/stubs uv run python -c "import led_ticker.app.run"` — expected: no ImportError (nothing else imports the calendar module).

- [ ] **Step 6: Commit.**

```bash
git add -A && git commit --no-verify -m "feat: remove calendar widget from core (extracted to led-ticker-calendar)"
```

---

### Task 2: Remove the three calendar `validate.py` rule branches

**Files:** Modify `src/led_ticker/validate.py`

- [ ] **Step 1: Delete `_check_calendar_ics_paths` and its call.** Remove the entire `def _check_calendar_ics_paths(config, config_dir)` function (rule 54, starts ~line 758) AND the call `warnings.extend(_check_calendar_ics_paths(config, path.parent))` in the Phase-2 block (~line 1988). Leave the other Phase-2 calls (`_check_soft`, `_check_held_top_text_overflow`, `_check_transition_fps`, and the new `_check_plugin_validation_warnings`) intact.

- [ ] **Step 2: Remove the calendar branch in `_check_band_layout`.** In `_check_band_layout` (~line 1128), delete the `elif wtype == "calendar" and widget_cfg.get("layout") == "two_row":` branch (the whole elif block that sets `default_font = FONT_SMALL` for calendar — keep the `two_row` and `gif`/`image` branches and the final `else: continue`). Verify the remaining if/elif/else chain is valid.

- [ ] **Step 3: Remove the calendar branch in `_check_held_top_text_overflow`.** In `_check_held_top_text_overflow` (~line 1393), delete the `elif wtype == "calendar" and widget_cfg.get("layout") == "two_row":` branch (the one measuring `"Tomorrow ..."` representative phrases and setting `is_calendar_two_row = True`). Remove any now-unused `is_calendar_two_row` logic that becomes dead once the calendar branch is gone (check downstream uses of `is_calendar_two_row` in that function and simplify — if it was only ever set True in the calendar branch, the variable and its conditional uses can be removed; if the two_row/image branches also rely on it, keep what they need). Keep the `two_row` and `gif`/`image` branches.

- [ ] **Step 4: Clean up now-unused imports.** After removing the branches, run ruff to surface any imports in `validate.py` that became unused (e.g. a calendar-only helper). Remove only genuinely-unused ones.

Run: `uv run --extra dev ruff check src/led_ticker/validate.py`
Expected: clean (fix unused imports it flags).

- [ ] **Step 5: Run the validator test suite.**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_validate.py -q`
Expected: PASS (test_validate.py has no calendar refs, so it's unaffected — this confirms the surgical removal didn't break the shared rules for two_row/gif/image).

- [ ] **Step 6: Commit.**

```bash
git add -A && git commit --no-verify -m "feat: drop calendar-specific validate rules (re-homed to the plugin)"
```

---

### Task 3: Remove FieldHints + migration breadcrumb (TDD)

**Files:**
- Modify: `src/led_ticker/app/factories.py`
- Test: `tests/test_factories_migration.py` (or wherever extracted-type migration is tested — see Step 1)

- [ ] **Step 1: Write the failing migration test.** First find where `_CRYPTO_MIGRATION` / `build_widget_cfg_error_for_type` is tested (grep `tests/` for `coingecko` or `build_widget_cfg_error_for_type` or `MigrationError` + `crypto`). Add a test in that same file (matching its style) asserting the calendar breadcrumb:

```python
def test_bare_calendar_type_raises_migration_to_plugin():
    from led_ticker.app.factories import build_widget_cfg_error_for_type

    result = build_widget_cfg_error_for_type("calendar")
    assert result is not None
    message, fix = result
    assert "led-ticker-calendar" in message
    assert "calendar.events" in fix
```

> If no such test file exists, create `tests/test_extracted_type_migration.py` with the test above plus a sibling assertion that `build_widget_cfg_error_for_type("coingecko")` still returns its crypto migration (guards the rename).

- [ ] **Step 2: Run it — expect FAIL** (`build_widget_cfg_error_for_type("calendar")` currently returns None).

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_extracted_type_migration.py -q` (or the file you added to)
Expected: FAIL.

- [ ] **Step 3: Remove the Calendar FieldHints block.** In `factories.py`, delete the `# --- Calendar ---` block (lines ~236–252: `ics_url`, `max_events`, `lookahead_days`, `time_format`, `empty_text`, `filter`, `highlight`, `highlight_color`). Leave the shared `label_color` hint above it and the `TWO_ROW_OVERLAY_FIELDS` set below it intact.

- [ ] **Step 4: Rename `_CRYPTO_MIGRATION` → `_EXTRACTED_TYPES` and add the calendar entry.** Rename the dict (line ~327) and every reference (the `build_widget_cfg_error_for_type` body returns `_CRYPTO_MIGRATION.get(...)` — update it). Add a `calendar` entry alongside the crypto ones:

```python
    "calendar": (
        "Widget type 'calendar' was extracted from led-ticker core; it now ships "
        "in the led-ticker-calendar plugin as 'calendar.events'.",
        'Install led-ticker-calendar (add it to config/requirements-plugins.txt) '
        'and use type = "calendar.events".',
    ),
```

Update the dict's docstring/comment if it says "crypto" specifically (it's now the general extracted-types table).

- [ ] **Step 5: Run the test — expect PASS.**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_extracted_type_migration.py -q`
Expected: PASS (calendar breadcrumb + crypto still works).

- [ ] **Step 6: Commit.**

```bash
git add -A && git commit --no-verify -m "feat: calendar migration breadcrumb + drop calendar FieldHints (rename _CRYPTO_MIGRATION -> _EXTRACTED_TYPES)"
```

---

### Task 4: Plugin catalog + CLAUDE.md

**Files:** Modify `src/led_ticker/plugins_catalog.json`, `CLAUDE.md`

- [ ] **Step 1: Add the catalog entry.** In `src/led_ticker/plugins_catalog.json`, add a `calendar` object to the `plugins` array (mirror the baseball/pool/crypto entries):

```json
{
  "name": "calendar",
  "namespace": "calendar",
  "summary": "Calendar (.ics) agenda/next/two_row widget.",
  "homepage": "https://github.com/JamesAwesome/led-ticker-calendar",
  "provides": ["calendar.events"],
  "sources": [
    { "type": "git", "url": "https://github.com/JamesAwesome/led-ticker-calendar", "ref": "main" }
  ]
}
```

> If a test guards `plugins_catalog.json` (grep `tests/` for `plugins_catalog`), run it and fix any schema/count assertion.

- [ ] **Step 2: Update CLAUDE.md.** In the "Plugin ecosystem" list, add a bullet:

```
- [`led-ticker-calendar`](https://github.com/JamesAwesome/led-ticker-calendar) — `calendar.events`: calendar (.ics) agenda/next/two_row widget.
```

Also update the top-level Plugin invariants paragraph that enumerates the external plugins (`led-ticker-pool` / `led-ticker-baseball` / `led-ticker-crypto`) to include `led-ticker-calendar`. If the "extracted widgets retain core hooks" note or any prose still implies calendar is a core widget, adjust it. (Do NOT touch docs-site pages — that's Phase 4.)

- [ ] **Step 3: Run any catalog/docs drift tests.**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/ -k "catalog or plugin_catalog or claude" -q`
Expected: PASS (or no tests collected). If a CLAUDE.md/catalog drift test exists and fails, align to it.

- [ ] **Step 4: Commit.**

```bash
git add -A && git commit --no-verify -m "docs: add led-ticker-calendar to plugin catalog + CLAUDE.md ecosystem"
```

---

### Task 5: Delete moved tests/fixtures + update remaining core tests + example configs

**Files:**
- Delete: `tests/test_widgets/test_calendar*.py` (6 files), `tests/fixtures/calendar_sample.ics`, `tests/fixtures/calendar_corpus/`, `config/config.calendar_smoketest.toml`
- Modify: `tests/test_border_surface_drift.py`, `tests/test_plugin_extraction_readiness.py`, `config/config.example.toml` (verify only)

- [ ] **Step 1: Delete the moved test files + fixtures + smoketest config.**

```bash
git rm tests/test_widgets/test_calendar.py tests/test_widgets/test_calendar_corpus.py tests/test_widgets/test_calendar_next_selection.py tests/test_widgets/test_calendar_recurrence_cost.py tests/test_widgets/test_calendar_tz_invariant.py tests/test_widgets/test_calendar_validate_contract.py
git rm tests/fixtures/calendar_sample.ics
git rm -r tests/fixtures/calendar_corpus
git rm config/config.calendar_smoketest.toml
```

> Confirm the exact set of `tests/test_widgets/test_calendar*.py` first with `ls tests/test_widgets/test_calendar*.py` and rm precisely those.

- [ ] **Step 2: Update `test_border_surface_drift.py`.** Line ~48 iterates a widget-type tuple `("message", "countdown", "two_row", "gif", "image", "clock", "calendar")`. Remove `"calendar"` from that tuple (it's no longer a core widget — `get_widget_class("calendar")` will raise). Read the test to confirm that's the only calendar reference and that dropping it leaves the test meaningful.

- [ ] **Step 3: Update `test_plugin_extraction_readiness.py`.** Remove the `"widgets/calendar.py": { "register": ... }` entry from the `_ALLOWED` dict (the file no longer exists, so the AST scan would otherwise error or the entry is stale). Confirm the test still passes for the remaining candidates (weather/rss/transitions).

- [ ] **Step 4: Verify `config/config.example.toml`.** Confirm it has NO `type = "calendar"` widget block (only the busy-light comment ~line 192 mentioning calendar as a future source). Run `grep -n 'type = "calendar"' config/config.example.toml` — expect no output. If a calendar widget block IS present, convert it to a commented note pointing at the plugin. (The busy-light comment about future calendar sources stays.)

- [ ] **Step 5: Full suite + lint.**

Run: `PYTHONPATH=tests/stubs uv run pytest -q`
Expected: PASS, 0 failures. (Calendar tests are gone; the warnings-channel tests from Phase 1 remain green; shared validate rules unaffected.)
Run: `uv run --extra dev ruff check src/ tests/`
Expected: clean.

- [ ] **Step 6: Commit.**

```bash
git add -A && git commit --no-verify -m "test: drop moved calendar tests/fixtures; update border-drift + readiness; remove smoketest config"
```

---

### Task 6: Final verification + PR (no merge)

- [ ] **Step 1: Confirm no stray core calendar references remain.**

Run: `grep -rnE "\\bcalendar\\b" src/led_ticker/ | grep -viE "busy_light|# |plugins_catalog|_EXTRACTED_TYPES|calendar.events|led-ticker-calendar"`
Expected: no real code references (only the allowed busy-light comment, the migration breadcrumb, and the catalog entry). Investigate anything else.

Run: `grep -rn "icalendar\|recurring_ical_events\|recurring-ical-events" src/ pyproject.toml uv.lock | grep -v "led-ticker-calendar"`
Expected: no `src/` imports; deps gone from pyproject (uv.lock may list them only if transitively required — confirm not).

- [ ] **Step 2: Full green.**

Run: `PYTHONPATH=tests/stubs uv run pytest -q` → 0 failures.
Run: `uv run --extra dev ruff check src/ tests/` → clean.
Run: `PYTHONPATH=tests/stubs uv run python -m led_ticker.validate --help` is not needed; instead validate the breadcrumb end-to-end:
`PYTHONPATH=tests/stubs uv run python -c "from led_ticker.app.factories import build_widget_cfg_error_for_type as b; print(b('calendar'))"` → prints the (message, fix) tuple mentioning led-ticker-calendar / calendar.events.

- [ ] **Step 3: Push + open PR.**

```bash
git push --no-verify -u origin worktree-calendar-phase3-core-removal
gh pr create --base main --title "feat: remove calendar widget from core (Phase 3 of extraction)" --body "<summary + BREAKING-CHANGE deploy note + test plan>"
```

The PR body MUST include a **BREAKING CHANGE** note: deployed signs must add `led-ticker-calendar` to `config/requirements-plugins.txt` and migrate `type = "calendar"` → `type = "calendar.events"`; bare `type = "calendar"` now raises a MigrationError with that guidance.

- [ ] **Step 4: Watch CI to green, then STOP.** Do NOT merge. Report the PR URL + CI status to the controller for deploy coordination.

---

## Self-Review

**Spec coverage (Phase-3 portion of the design):**
- Delete widget + `widgets/__init__.py` import → Task 1. ✓
- Remove icalendar + recurring-ical-events (calendar-only) → Task 1. ✓
- Delete the 3 validate.py calendar branches → Task 2. ✓
- Remove `# --- Calendar ---` FieldHints → Task 3. ✓
- Rename `_CRYPTO_MIGRATION` → `_EXTRACTED_TYPES` + `calendar → calendar.events` breadcrumb → Task 3 (TDD). ✓
- `plugins_catalog.json` entry → Task 4. ✓
- CLAUDE.md ecosystem bullet + invariants prose → Task 4. ✓
- Core test updates (readiness allowlist, border-drift) + delete moved tests/fixtures + example configs → Task 5. ✓
- Docs-site is Phase 4 (explicitly out of scope here). ✓

**Placeholder scan:** Step-level `>` notes are verification/triage instructions with concrete grep fallbacks (find the migration test file; confirm the FieldHint block bounds; verify example.toml has no calendar block), not unfinished work. The PR body summary in Task 6 Step 3 is a `<...>` template because the exact wording is written at PR time — but its required content (BREAKING CHANGE deploy note) is specified.

**Consistency:** The migration table is renamed `_CRYPTO_MIGRATION` → `_EXTRACTED_TYPES` in Task 3 and referenced by that new name in `build_widget_cfg_error_for_type`; the breadcrumb message/fix mention `led-ticker-calendar` and `calendar.events`, matching the catalog entry (Task 4) and the plugin's actual type (Phase 2). The three validate rules removed in Task 2 are exactly those re-homed into the plugin's `validate_config_warnings` in Phase 2 — no behavior lost for plugin users (the Phase-1 rule-55 channel surfaces them).
