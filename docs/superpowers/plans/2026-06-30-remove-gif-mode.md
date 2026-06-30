# Remove the `gif` section mode — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the redundant `mode = "gif"` section display mode (breaking), replacing it with a directed `MigrationError`, and purge its code, validator rules, example-config usage, and docs.

**Architecture:** `mode = "gif"` is a legacy full-panel gif-takeover mode with its own `run_gif`/`_run_gif` path in `ticker.py`, strictly redundant with `mode = "slideshow"` + a gif widget. We make it a hard `MigrationError` at config load (so no downstream code ever sees it), then delete the now-unreachable engine path, validator rules, and docs, and migrate the 3 example configs to slideshow.

**Tech Stack:** Python 3.14, pytest, `tomllib`, the Astro docs site (mdx).

**Spec:** `docs/superpowers/specs/2026-06-30-remove-gif-mode-design.md` (peer-reviewed).

**Pre-flight (anchors re-verified against `main` @ f3a28c50, 2026-06-30):** This plan was rebased after 6 PRs landed (incl. #326 ruff-format and #321 inline value tokens). The code *text* the steps quote is unchanged, but line numbers shifted. Corrected anchors: `config.py` mode comment **line 91**, `_MODE_RENAMES` **~682**; `validate.py` `VALID_MODES` **66**, Rule 25 guard `if section.mode in ("slideshow", "gif"):` **~413**, Rule 26 comment **~441**, Rule 33 **~1135–1158**, Rule 36 **~1160–1196**; `ticker.py` `run_gif` **270**, `_run_gif` **~1152**; `factories.py` `RUN_MODES` gif entry **~992**; `run.py` comment **~1031**. Steps below find by quoted text — trust the text over any line number. **`sections-and-modes.mdx` now has a line ~138 about `gif` *widgets* in `slideshow` mode (`play_count = 0`) — that is correct and MUST be kept; only `mode = "gif"` references are removed (see Task 4).**

## Global Constraints

- Python 3.14. **No `from __future__ import annotations`** in any source.
- Branch `feat/remove-gif-mode` (worktree). Never commit to `main`. Commit with `git commit --no-verify` (repo's pre-commit hook errors "pre-commit not found" — `--no-verify` is expected/correct here).
- The `MigrationError` **message** (`str(e)`) must be self-contained — `led-ticker validate` surfaces only `message`, not `suggested_fix`. The slideshow guidance, the `play_count` note, and the docs link all live in `message`.
- Docs follow **DOCS-STYLE rule 17**: no legacy/deprecation/release-history framing. Pages present *three* modes; they do NOT narrate "gif was removed." Migration guidance lives only in the `MigrationError`.
- Before any push: `uv run --extra dev ruff check src/ tests/` AND `uv run --extra dev ruff format --check src/ tests/` both clean (the pre-push hook runs `ruff format`, which enforces PEP 758 unparenthesized `except` + double quotes — run it locally so the push doesn't bounce). Run `make dev` once in the worktree before pushing.
- Gate at the end: `make test` green; `led-ticker validate` clean (no warnings) on all 3 migrated example configs; docs build (`docs-lint`) clean.
- This is a breaking change. The version number / release cut is a SEPARATE decision made at end-of-work — NOT part of these tasks.

---

### Task 1: Make `mode = "gif"` a config-load `MigrationError` and purge the validator's gif handling

These are one task because the moment `mode = "gif"` errors at load, the validator's gif tests (which call `validate_config` → `load_config`) break — they must be fixed in the same change to keep the suite green.

**Files:**
- Modify: `src/led_ticker/config.py` (the `_MODE_RENAMES` block ~line 666–680; the `SectionConfig.mode` comment ~line 84)
- Modify: `src/led_ticker/validate.py` (`VALID_MODES` line 65; Rule 25 ~244–266; Rule 26 comment ~278–279; Rule 33 ~972–995; Rule 36 ~997–1032)
- Test: `tests/test_config.py` (`TestModeMigration` ~line 1126); `tests/test_validate.py` (gif tests at ~932, ~1062, ~1687, ~1719, ~1770, ~3505, ~3525)

**Interfaces:**
- `MigrationError(message: str, suggested_fix: str, *, fix_key=None, fix_replacement_key=None)` — defined in `src/led_ticker/validate.py:42`; imported locally inside `config.py` (avoids a config↔validate import cycle).
- Produces: after this task, `load_config(path)` raises `MigrationError` for any section with `mode = "gif"`, before `SectionConfig` is built.

- [ ] **Step 1: Write the failing tripwire test**

Add to `tests/test_config.py` inside `class TestModeMigration` (after `test_old_mode_name_raises_migration_error`, ~line 1148):

```python
    def test_gif_mode_raises_migration_error(self, tmp_path):
        from led_ticker.validate import MigrationError

        cfg = tmp_path / "config.toml"
        cfg.write_text(
            "[display]\nrows=16\ncols=32\nchain_length=5\n"
            '[[playlist.section]]\nmode = "gif"\n'
            '[[playlist.section.widget]]\ntype = "gif"\npath = "x.gif"\n'
        )
        with pytest.raises(MigrationError) as ei:
            load_config(str(cfg))
        msg = str(ei.value)
        assert "slideshow" in msg
        assert "play_count" in msg
        assert "docs.ledticker.dev/widgets/gif" in msg
```

- [ ] **Step 2: Run it — verify it fails**

Run: `uv run pytest tests/test_config.py::TestModeMigration::test_gif_mode_raises_migration_error -v`
Expected: FAIL — `mode = "gif"` is currently accepted, so no `MigrationError` is raised (`pytest.raises` fails: "DID NOT RAISE").

- [ ] **Step 3: Add the gif `MigrationError` branch + trim the mode comment in `config.py`**

In `src/led_ticker/config.py`, immediately after the `_MODE_RENAMES` block (after the `raise MigrationError(...)` for renames, ~line 680, before `section = SectionConfig(`), add:

```python
        if raw_mode == "gif":
            # Local import: avoid config<->validate circular dependency
            from led_ticker.validate import MigrationError

            raise MigrationError(
                'mode = "gif" was removed. Use mode = "slideshow" with a gif '
                "widget instead. If you relied on repeat counts, set play_count "
                "on the gif widget. See https://docs.ledticker.dev/widgets/gif/",
                suggested_fix=(
                    'Change mode = "gif" to mode = "slideshow"; move any repeat '
                    "count to play_count on the gif widget."
                ),
            )
```

And change the `SectionConfig.mode` field comment at line 84 from:

```python
    mode: str  # "slideshow", "ticker", "one_at_a_time", "gif"
```
to:
```python
    mode: str  # "slideshow", "ticker", "one_at_a_time"
```

- [ ] **Step 4: Run the tripwire — verify it passes**

Run: `uv run pytest tests/test_config.py::TestModeMigration -v`
Expected: PASS (all rename cases + the new gif case). The validator's gif tests are now broken — that's expected; the next steps fix them.

- [ ] **Step 5: Delete Rules 33 & 36 and trim Rules 25/26 in `validate.py`**

In `src/led_ticker/validate.py`:

(a) Remove `"gif"` from `VALID_MODES` (line 65):
```python
VALID_MODES: frozenset[str] = frozenset({"slideshow", "ticker", "one_at_a_time"})
```

(b) **Delete Rule 33 entirely** — the whole block at ~972–995 (the comment `# Rule 33: ...` through the closing `)` of the `warnings.append(...)`).

(c) **Delete Rule 36 entirely** — the whole block at ~997–1032 (the comment `# Rule 36: ...` through the closing `)` of its `warnings.append(...)`).

(d) Trim Rule 25 (~244–266). Change the gif-inclusive guard and comment. Replace:
```python
        # Rule 25: start_hold is only meaningful on scroll modes
        # (ticker / one_at_a_time), which are the only modes
        # that call _scroll_and_delay. Setting it on slideshow / gif has
        # no runtime effect — surface as an error so users don't think
        # they're tuning something they're not.
        if section.start_hold is not None:
            if section.mode in ("slideshow", "gif"):
```
with:
```python
        # Rule 25: start_hold is only meaningful on scroll modes
        # (ticker / one_at_a_time), which are the only modes
        # that call _scroll_and_delay. Setting it on slideshow has
        # no runtime effect — surface as an error so users don't think
        # they're tuning something they're not.
        if section.start_hold is not None:
            if section.mode == "slideshow":
```
and change that branch's `fix=` text from:
```python
                        fix=(
                            "Remove start_hold. For slideshow mode, use hold_time"
                            " (per-widget hold). For gif mode, the gif's own"
                            " duration controls timing."
                        ),
```
to:
```python
                        fix=(
                            "Remove start_hold. For slideshow mode, use hold_time"
                            " (per-widget hold)."
                        ),
```

(e) Trim the Rule 26 comment (~278–280) only — the logic (`section.mode != "ticker"`) is correct and unchanged. Change:
```python
        # On slideshow / gif / one_at_a_time, the engine doesn't intersperse a
```
to:
```python
        # On slideshow / one_at_a_time, the engine doesn't intersperse a
```

- [ ] **Step 6: Update the validator's gif tests in `tests/test_validate.py`**

- `test_rule25_start_hold_on_gif_section_errors` (~932): change the config's `mode = "gif"` to `mode = "slideshow"` (Rule 25 still fires on slideshow). Rename the function to `test_rule25_start_hold_on_slideshow_section_errors`.
- `test_rule26_separator_on_gif_errors` (~1062): change its `mode = "gif"` to `mode = "slideshow"` (Rule 26 fires on any non-ticker mode). Rename to `test_rule26_separator_on_slideshow_errors`.
- `test_rule33_mode_gif_warns` (~1687): **delete** the whole function (Rule 33 is gone).
- `test_rule36_gif_loops_zero_in_mode_gif_warns` (~1719): **delete** the whole function.
- `test_rule36_gif_loops_positive_in_mode_gif_does_not_warn` (~1770): **delete** the whole function.
- The rule-54 unknown-mode test (~3500–3505): **delete** the line `assert "gif" in msg, f"error should list valid modes; got: {msg!r}"` (gif is no longer a valid mode the message lists). Leave the slideshow/ticker/one_at_a_time asserts.
- `test_all_valid_modes_pass` (~3508): remove `"gif"` from the loop tuple (line ~3525) → `for mode in ("slideshow", "ticker", "one_at_a_time"):`, and update the docstring (~3509) to drop ", gif".

- [ ] **Step 7: Run the config + validate suites and lint**

Run: `uv run pytest tests/test_config.py tests/test_validate.py -q`
Expected: PASS (no gif warnings/errors; repointed rule 25/26 tests green; tripwire green).
Run: `uv run --extra dev ruff check src/led_ticker/config.py src/led_ticker/validate.py tests/test_config.py tests/test_validate.py` → clean.
Run: `uv run --extra dev ruff format --check src/led_ticker/config.py src/led_ticker/validate.py tests/test_config.py tests/test_validate.py` → clean.

- [ ] **Step 8: Commit**

```bash
git add src/led_ticker/config.py src/led_ticker/validate.py tests/test_config.py tests/test_validate.py
git commit --no-verify -m "feat!: mode = \"gif\" is now a config-load MigrationError; purge validator gif rules"
```

---

### Task 2: Remove the gif run path (engine code + its tests)

After Task 1, no config can reach `mode = "gif"` (it errors at load), so `run_gif`/`_run_gif`/`RUN_MODES["gif"]` are dead. Delete them. (`tests/test_run_gif.py` calls `run_gif` directly on a Ticker, so it survived Task 1 — delete it here alongside the code.)

**Files:**
- Modify: `src/led_ticker/ticker.py` (delete `run_gif` ~270–317 and `_run_gif` ~1083–1132)
- Modify: `src/led_ticker/app/factories.py` (`RUN_MODES` ~981–986)
- Modify: `src/led_ticker/app/run.py` (comment ~1005–1007)
- Modify: `src/led_ticker/widgets/gif.py` (module docstring ~24–28)
- Delete: `tests/test_run_gif.py` (whole file)
- Modify: `tests/test_render_breaker_engine.py` (delete 2 tests ~381, ~391); `tests/test_ticker.py` (delete 1 test ~463)

**Interfaces:**
- Consumes: nothing from Task 1 at the code level (independent). Relies on Task 1 having made `mode = "gif"` unreachable so this deletion is safe.
- Produces: no `run_gif` / `_run_gif` / `RUN_MODES["gif"]` anywhere in `src/`.

- [ ] **Step 1: Delete the engine tests first**

- Delete the file `tests/test_run_gif.py` entirely (`git rm tests/test_run_gif.py`).
- In `tests/test_render_breaker_engine.py`, delete the two functions `test_run_gif_survives_faulty_play` (~381) and `test_run_gif_pre_tripped_play_not_called` (~391).
- In `tests/test_ticker.py`, delete the function `test_run_gif_is_instance_method` (~463).

- [ ] **Step 2: Delete the engine code**

- In `src/led_ticker/ticker.py`: delete the entire `async def run_gif(self, loop_count: int = 0) -> None:` method (~270–317) and the entire `async def _run_gif(self, ...)` method (~1083–1132). Delete only those two methods; leave the methods immediately before/after intact.
- In `src/led_ticker/app/factories.py`, remove the gif entry from `RUN_MODES`:
```python
RUN_MODES: dict[str, str] = {
    "slideshow": "run_slideshow",
    "ticker": "run_ticker",
    "one_at_a_time": "run_one_at_a_time",
}
```
- In `src/led_ticker/app/run.py`, update the comment (~1005–1007) from:
```python
                        # `start_pos` is only meaningful for scrolling modes —
                        # `run_slideshow` and `run_gif` don't have a scroll position
                        # to skip past.
```
to:
```python
                        # `start_pos` is only meaningful for scrolling modes —
                        # `run_slideshow` doesn't have a scroll position to skip past.
```
- In `src/led_ticker/widgets/gif.py`, replace the docstring block (~23–28):
```
The widget lazily decodes all frames on first use, paints frames
directly to the underlying real canvas (bypassing ScaledCanvas so each
pixel is a native LED, not a scale×scale block), and exposes an async
``play()`` method that drives the per-frame playback loop.

Two run modes:
    - ``mode = "gif"``  legacy panel-takeover orchestrator (no titles)
    - ``mode = "slideshow"`` unified path; gif rides ``_show_one``'s
                       ``_has_play`` dispatch and works alongside an
                       optional title
```
with:
```
The widget lazily decodes all frames on first use, paints frames
directly to the underlying real canvas (bypassing ScaledCanvas so each
pixel is a native LED, not a scale×scale block), and exposes an async
``play()`` method that drives the per-frame playback loop. It runs under
``mode = "slideshow"`` via ``_show_one``'s ``_has_play`` dispatch, alongside
an optional section title.
```

- [ ] **Step 3: Verify no orphan references + full suite + lint**

Run: `grep -rn 'run_gif\|_run_gif\|"gif": "run_gif"' src/ tests/ CLAUDE.md`
Expected: NO matches (CLAUDE.md confirmed already clean — this guards against drift).
Run: `uv run pytest -q`
Expected: PASS (full suite; the deleted tests are gone, nothing references the removed methods).
Run: `uv run --extra dev ruff check src/ tests/` and `uv run --extra dev ruff format --check src/ tests/` → both clean.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit --no-verify -m "feat!: remove the gif run path (run_gif/_run_gif, RUN_MODES gif entry)"
```

---

### Task 3: Migrate the 3 example configs to `mode = "slideshow"`

**Files:**
- Modify: `config/config.gif_test.example.toml`, `config/config.gif_text.example.toml`, `config/config.presentation_test.example.toml`

**Interfaces:**
- Consumes: Task 1's `MigrationError` (these configs would now fail to load until migrated).
- Produces: all 3 configs load + validate clean with no `mode = "gif"`.

The transform per gif section: change `mode = "gif"` → `mode = "slideshow"`; if the section sets `loop_count = N` (gif-loop count), **remove it from the section** and add `play_count = N` to the gif widget in that section (preserves "play this gif N times"). Leave transitions, `transition_duration`, `path`, `fit`, etc. unchanged.

Representative example — in `config.gif_test.example.toml`, a section like:
```toml
[[playlist.section]]
mode = "gif"
loop_count = 17  # ~10s of playback (17 × 600ms per loop)
transition = "dissolve"
transition_duration = 0.6

[[playlist.section.widget]]
type = "gif"
path = "assets/phoenix.gif"
fit = "stretch"
```
becomes:
```toml
[[playlist.section]]
mode = "slideshow"
transition = "dissolve"
transition_duration = 0.6

[[playlist.section.widget]]
type = "gif"
path = "assets/phoenix.gif"
fit = "stretch"
play_count = 17  # ~10s of playback (17 × 600ms per loop)
```

- [ ] **Step 1: Migrate `config.gif_test.example.toml`**

Change every uncommented `mode = "gif"` (12 sections) to `mode = "slideshow"`, moving each section's `loop_count` to `play_count` on its gif widget per the pattern above. Also update the two **commented-out** `# mode = "gif"` lines (~445, ~464) to `# mode = "slideshow"` so an uncommenting user doesn't reintroduce a removed mode.

- [ ] **Step 2: Migrate `config.gif_text.example.toml` and `config.presentation_test.example.toml`**

Apply the same transform to all `mode = "gif"` sections (gif_text: 5; presentation_test: 3). For `presentation_test`, do NOT touch the `# requires-plugins:` header — the mode change doesn't affect it.

- [ ] **Step 3: Validate all three configs**

Run each:
```bash
uv run led-ticker validate CONFIG=config/config.gif_test.example.toml
uv run led-ticker validate CONFIG=config/config.gif_text.example.toml
uv run led-ticker validate CONFIG=config/config.presentation_test.example.toml
```
Expected: each exits 0 with **no errors and no warnings**. (A `MigrationError` here means a `mode = "gif"` was missed; a Rule-25/26 error means a stray `start_hold`/`separator_*` — fix per the message.)

- [ ] **Step 4: Confirm the plugin-flags tripwire still passes + commit**

Run: `uv run pytest tests/test_example_config_plugin_flags.py -q`
Expected: PASS (presentation_test's plugin header unchanged and still matches its derived deps).

```bash
git add config/config.gif_test.example.toml config/config.gif_text.example.toml config/config.presentation_test.example.toml
git commit --no-verify -m "chore: migrate example configs from mode = \"gif\" to slideshow"
```

---

### Task 4: Scrub `mode = "gif"` from the docs (4 pages)

DOCS-STYLE rule 17: present *three* modes; do not narrate the removal.

**Files:**
- Modify: `docs/site/src/content/docs/concepts/sections-and-modes.mdx`
- Modify: `docs/site/src/content/docs/reference/config-options.mdx`
- Modify: `docs/site/src/content/docs/pitfalls.mdx`
- Modify: `docs/site/src/content/docs/tools/validate.mdx`

- [ ] **Step 1: `sections-and-modes.mdx`**

- Frontmatter `description` (~line 3): change `"... slideshow, ticker, one_at_a_time, or gif."` → `"... slideshow, ticker, or one_at_a_time."`
- Intro (~line 10): change `"Four modes are available: slideshow, ticker, one_at_a_time, and gif."` → `"Three modes are available: slideshow, ticker, and one_at_a_time."`
- **Delete the entire `## The mode = "gif" shorthand` section** (the heading ~line 186 and its body paragraph ~188).
- Remove only `mode = "gif"` references. **Preserve every `gif` *widget* / `type = "gif"` reference** — e.g. line ~138 ("For `gif` widgets in `slideshow` mode, `play_count = 0` plays the gif through the section's `hold_time`…") and line ~161 (the `scroll_speed_ms` on `gif` and `image` widgets note) are about the gif *widget* under slideshow and are CORRECT — leave them. After editing, `grep -n 'mode = "gif"' docs/site/src/content/docs/concepts/sections-and-modes.mdx` must return nothing, while the `gif`-widget mentions remain.

- [ ] **Step 2: `config-options.mdx`**

- `mode` table row (~line 124): change `One of ticker, one_at_a_time, slideshow, gif.` → `One of ticker, one_at_a_time, slideshow.`
- `start_hold` row (~line 143): change `Setting it on slideshow / gif is a validation error.` → `Setting it on slideshow is a validation error.`

- [ ] **Step 3: `pitfalls.mdx`**

- **Delete the entire Rule 33 entry** (`### Rule 33 — prefer mode = "slideshow" ... over mode = "gif"` heading + body, ~125–127).
- **Delete the entire Rule 36 entry** (`### Rule 36 — play_count = 0 in mode = "gif" ...` heading + body, ~133–135).
- Rule 25 entry (~48): trim the gif clause so it reads only about slideshow (e.g. drop "For gif mode, the gif's own duration controls timing.").
- Rule 26 entry (~52): change `"slideshow and gif modes don't intersperse anything"` → `"slideshow and one_at_a_time modes don't intersperse anything"`.

- [ ] **Step 4: `validate.mdx`**

- Errors table `start_hold` row (~166): change `start_hold on slideshow / gif section ...` → `start_hold on slideshow section ...`.
- **Delete the Rule 33 warnings-table row** (~181).
- **Delete the Rule 36 warnings-table row** (~183).
- Delete the closing prose tip (~210) that references "a mode = "gif" section that would benefit from the full slideshow-mode feature set."

- [ ] **Step 5: Build docs + final full gate**

Run: `grep -rn 'mode = "gif"\|mode="gif"\|"gif"' docs/site/src/content/docs/`
Expected: NO `mode = "gif"` matches (a bare "gif" in the gif-widget page about `type = "gif"` is fine; confirm none are about the *mode*).
Run the docs lint the same way CI does (prettier + astro check) — e.g. `cd docs/site && npx astro check` (or `make` docs target if present). Expected: clean.
Run: `make test` → full suite green.

- [ ] **Step 6: Commit**

```bash
git add docs/site/src/content/docs/
git commit --no-verify -m "docs: present three section modes (remove mode = \"gif\")"
```

---

## Notes (not plan tasks)

- **Versioning/release** is deferred to end-of-work per the spec — handled by the normal release flow, not these tasks.
- No new AST/"don't reintroduce" guard is added beyond the Task 1 `MigrationError` tripwire — the error blocks the code path, so a re-added `run_gif` would be unreachable (YAGNI, per spec).

## Self-Review

- **Spec coverage:** Component 1 (config-load migration) → Task 1 Steps 1–4. Component 2 (engine removal) → Task 2. Component 3 (validator cleanup) → Task 1 Steps 5–6. Component 4 (example configs) → Task 3. Component 5 (docs) → Task 4. Component 6 (testing: 6 removed, validator tests edited, 1 tripwire) → Task 1 Step 1 + 6, Task 2 Step 1. The three peer-review must-fixes (gif.py docstring, config.py:84 comment, tripwire home = `tests/test_config.py::TestModeMigration`) are in Task 2 Step 2, Task 1 Step 3, Task 1 Step 1 respectively. Covered.
- **Placeholder scan:** none — every code/edit step shows exact before/after; line numbers are `~` approximate but anchored to quoted current text.
- **Type/name consistency:** `MigrationError(message, suggested_fix, ...)` signature consistent with `validate.py:42`; `VALID_MODES`, `RUN_MODES`, `run_gif`/`_run_gif`, `play_count`, `loop_count` used consistently with the verified code.
