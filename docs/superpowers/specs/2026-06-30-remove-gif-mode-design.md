# Remove the `gif` section mode — Design

**Status:** Approved (brainstorm 2026-06-30)

## Problem

`mode = "gif"` is a section display mode — a legacy full-panel gif-takeover that runs its own `run_gif` / `_run_gif` path in `ticker.py`, parallel to the v3.0.0-renamed `slideshow` / `ticker` / `one_at_a_time`. It is **strictly redundant** with `mode = "slideshow"` + a gif widget, and in fact does *less*:

| | `mode = "gif"` | `slideshow` + gif widget |
|---|---|---|
| Section titles | never (suppressed) | yes |
| `hold_time` / duration-driven playback | no (silent fallback — Rule 36 bug) | yes |
| Status-board visit tracking | no | yes |
| Frame reset at visit entry | no | yes |
| Loop control | `section.loop_count` → `widget.play(loop_count=…)` (inverted semantic) | per-widget `play_count` field |

It is already half-walked-back: the validator **warns** on it (Rule 33), Rule 36 documents a silent bug in it, and several surfaces (`--list-fields` mode list, the "Which mode to use" docs table, `getting-started.mdx`, `CLAUDE.md`'s run-path list) already omit it. It is drifting into inconsistent dead code.

## Decision

Remove `mode = "gif"` entirely as a **breaking change**, replacing it with a directed `MigrationError`. Scope and the key sub-decisions were chosen in the brainstorm:

- **Scope:** full removal (code + validator + tests + example configs + docs).
- **Migration message:** directed fix including the loop-semantics note (not a bare rename).
- **Versioning:** breaking; the actual version number is **decided at end-of-work, before release** (not pinned here).

## Components

### 1. Config-load migration (user-facing contract)

`mode = "gif"` raises a `MigrationError` at config load. Because the message is custom (it carries the `loop_count → play_count` note), it gets its **own branch in `config.py`** — **not** the generic `_MODE_RENAMES` map, whose "X was renamed to Y" template would misrepresent the non-pure migration.

Message (exact intent; final wording finalized in the plan):

> `mode = "gif"` was removed. Use `mode = "slideshow"` with a gif widget instead. If you relied on repeat counts, set `play_count` on the gif widget. See https://docs.ledticker.dev/widgets/gif/

The `suggested_fix` field: `Change mode = "gif" to mode = "slideshow"; move any repeat count to play_count on the gif widget.`

The docs link targets **`widgets/gif`** (not `sections-and-modes`) — that page shows the concrete slideshow + gif + `play_count` setup, which is exactly the fix the reader needs.

The branch must run in the same place the v3.0.0 `_MODE_RENAMES` check runs (`config.py` section parsing, ~line 665), and fire **before** `SectionConfig(mode=…)` is constructed, so no downstream code ever sees `mode == "gif"`.

### 2. Engine code removal

- `src/led_ticker/ticker.py`: delete `run_gif` (~lines 270–317) and `_run_gif` (~lines 1083–1132).
- `src/led_ticker/app/factories.py`: remove `"gif": "run_gif"` from `RUN_MODES`.
- `src/led_ticker/app/run.py`: update the `start_pos`-guard comment (~line 1005–1007) that names `run_gif` so it no longer references a deleted method.
- `CLAUDE.md`: scrub any `run_gif` / `mode = "gif"` mention (the mode list already omits gif; this is a grep-and-clean pass, e.g. the GIF-widget invariant section if it references the legacy path).

### 3. Validator cleanup (`src/led_ticker/validate.py`)

- Remove `"gif"` from `VALID_MODES` (so it is no longer an accepted value — though config-load now errors first, this keeps the validator's own list honest).
- Delete **Rule 33** (gif-mode "prefer slideshow" warning) and **Rule 36** (gif `play_count = 0` silent-loop warning) — both exist *only* because gif is a live mode.
- Trim `"gif"` from **Rule 25** (`start_hold` mode list + fix-text that names "gif mode") and **Rule 26** (`separator_*` mode check). After removal, gif can never reach these rules (it errors at load), so the references are dead.
- Rule 54 (unknown-mode error): its valid-modes list drops "gif" automatically once `VALID_MODES` is updated.

### 4. Example-config migration (3 files)

Migrate every `mode = "gif"` section to `mode = "slideshow"`:

- `config/config.gif_test.example.toml` (~13 sections)
- `config/config.gif_text.example.toml` (5 sections)
- `config/config.presentation_test.example.toml` (3 sections)

Per section: change the mode, and where the section relied on repeat counts, set `play_count` on the gif widget to preserve intent. Drop any field that was a gif-mode-only no-op. Re-run `led-ticker validate` on each migrated file — all must pass clean (no warnings).

Constraint: `config.presentation_test.example.toml` carries a `# requires-plugins:` header from the merged plugin-flags work. The mode change does not affect `required_plugins` derivation (mode is not a plugin reference), so the header stays correct and its tripwire keeps passing — verify, don't edit the header.

### 5. Docs scrub (4 pages, DOCS-STYLE-compliant)

Per **DOCS-STYLE rule 17** (no legacy/deprecation/release-history framing), the pages simply present *three* modes — they do **not** narrate "gif was removed." All migration guidance lives in the `MigrationError`.

- `docs/site/src/content/docs/concepts/sections-and-modes.mdx`: delete the `## The mode = "gif" shorthand` section; fix the frontmatter `description` and the intro ("Four modes…" → "Three modes…"); remove gif from the incidental scroll-mode co-mentions.
- `docs/site/src/content/docs/reference/config-options.mdx`: drop gif from the `mode` row's value list; trim the `start_hold` note's "slideshow / gif" to "slideshow".
- `docs/site/src/content/docs/pitfalls.mdx`: delete the Rule 33 and Rule 36 entries; trim gif from the Rule 25 and Rule 26 co-mentions.
- `docs/site/src/content/docs/tools/validate.mdx`: delete the Rule 33 and Rule 36 table rows and the closing prose tip that references a "mode = gif section"; trim gif from the `start_hold` error row.

(`getting-started.mdx`, the "Which mode to use" summary table, `CLAUDE.md`'s mode list, and `DOCS-STYLE.md` already omit gif — no change.)

### 6. Testing

**Remove (6 tests):**
- `tests/test_run_gif.py` — entire file (3 tests: `test_run_gif_invokes_widget_play`, `test_run_gif_unwraps_scaled_canvas`, `test_run_gif_enqueues_monitors_when_queue_empty`).
- `tests/test_render_breaker_engine.py` — `test_run_gif_survives_faulty_play`, `test_run_gif_pre_tripped_play_not_called`.
- `tests/test_ticker.py` — `test_run_gif_is_instance_method`.

**Edit (validator tests):**
- `tests/test_validate.py` — delete the Rule 33 test (`test_rule33_mode_gif_warns`) and the Rule 36 tests (`test_rule36_gif_loops_zero_in_mode_gif_warns`, `test_rule36_gif_loops_positive_in_mode_gif_does_not_warn`); remove `"gif"` from the parametrized `test_all_valid_modes_pass` and from the rule-54 valid-modes-list assertion; remove or repoint the Rule 25/26 gif-section tests (`test_rule25_start_hold_on_gif_section_errors`, `test_rule26_separator_on_gif_errors`) to a still-valid mode, since `mode = "gif"` now errors at load before validation.

**Add (tripwire):**
- A test asserting `mode = "gif"` raises `MigrationError`, and that the message names `slideshow`, `play_count`, and the docs link — placed alongside the existing v3.0.0 rename tripwires (the `#320` legacy-mode tripwire location) so the "old mode names error out" guarantee covers gif too.

**Gate:** full `make test` green; `uv run --extra dev ruff check src/ tests/` clean; `led-ticker validate` clean on all 3 migrated example configs.

## Out of scope

- Renaming or consolidating the example config files (e.g. `config.gif_test` is now a slideshow-gif demo, not a "gif-mode" exerciser — keeping the filename is fine; a rename is unrelated churn).
- Any change to `slideshow` / gif-widget behavior. This is a pure removal of the redundant path.
- The version number / release cut (deferred to end-of-work).

## Testing & verification summary

1. `mode = "gif"` → `MigrationError` (new tripwire).
2. No `run_gif` / `_run_gif` / `RUN_MODES["gif"]` / `VALID_MODES` gif references remain (grep-clean).
3. 3 migrated example configs validate clean; `presentation_test` plugin-flags header unchanged and passing.
4. Full suite + ruff + docs build clean.
