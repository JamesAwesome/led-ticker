# Design: Docs canonicalization

**Date:** 2026-05-14
**Status:** Approved

## Overview

Pure docs-only PR addressing the docs-side findings from the three-persona config-surface review. Surfaces undocumented fields, declares canonical TOML idioms, and clarifies the per-block grammar without renaming a single Python field. No code changes, no behavior changes. The implementation is six `.mdx` edits.

## Goals

1. **Surface undocumented fields** that the loader accepts but the reference page omits: `transition_colors`, `show_pikachu`, `show_pokeball`.
2. **Declare `text` as canonical** content key for `message`, `countdown`, `weather` widgets. Keep `message` as a silent forever-alias. Currently the tutorials use `text` in places and `message` in others — confusing for new readers.
3. **Document inline-table form for `transition`** as the recommended form at section scope when more than just the type is needed. The flat sibling pattern (`transition = "X"` + `transition_duration = Y`) stays valid; the inline table is just made discoverable.
4. **Clarify `color` on `[playlist.section.title]` is a title-specific alias** for `font_color`. Currently the example configs use `color = "random"` in title blocks while widget blocks use `font_color = "random"` — users copy the title pattern to widgets and silently fail.
5. **Cross-reference `mode = "gif"` as legacy** (paired with the validator rule 33 warning shipping in the sibling PR — if that PR isn't merged first, the reference docs should still mention the legacy status).

## Non-goals

- **No field renames.** The advocate persona's vetoes apply: `font_color`, `top_color`, `bottom_color`, `transition_duration`, `color` on titles, `hold_time` / `hold_seconds` distinction — all stay.
- **No deprecations.** Both spellings of `text` / `message` continue to work; both flat-sibling and inline-table `transition` continue to work.
- **No new concepts.** Not adding a "Field naming conventions" page; the per-block table on `config-options.mdx` is where field-level rules live.

## File-by-file changes

### 1. `docs/site/src/content/docs/reference/config-options.mdx`

Surface area additions to the `[[playlist.section]]` table:

| Field | Type | Default | Notes |
| --- | --- | --- | --- |
| `transition_colors` | `[[r,g,b], ...]` | `null` | Multi-color list for transitions that cycle through colors (e.g., `wipe_random` with multiple sweep colors). Plural form of `transition_color`. |
| `show_pikachu` | bool | `true` | Pokeball-family transitions: toggle the Pikachu sprite that emerges after the ball opens. |
| `show_pokeball` | bool | `true` | Pokeball-family transitions: toggle the ball itself. (Setting both to `false` produces a beam-only transition.) |

Both `[[playlist.section]]` and `[transitions]` table rows for the inline-table form of `transition`:

> When the transition needs more than just the type, prefer the inline-table form: `transition = { type = "wipe_left", duration = 0.8, easing = "ease_out", color = [255, 0, 0] }`. The flat sibling form (`transition = "wipe_left"` + `transition_duration = 0.8`) is equivalent and remains supported.

### 2. `docs/site/src/content/docs/reference/config-options.mdx` — title section

The `[playlist.section.title]` heading currently says titles "use all the same knobs as a `message` widget." Replace with the more accurate framing:

> A title block accepts the same field surface as a `message` widget with one alias: `color` is the title-specific spelling of `font_color`. Both work, and only on title blocks — writing `color = "random"` on a regular `[[playlist.section.widget]]` is a configuration error (the alias doesn't apply outside titles).

### 3. `docs/site/src/content/docs/widgets/message.mdx`

Reference-page touch: under the field surface, note that `text` is the canonical TOML key while `message` is the Python attribute name. Configs that use either spelling work today.

### 4. `docs/site/src/content/docs/widgets/countdown.mdx`

Same `text` vs `message` clarification.

### 5. `docs/site/src/content/docs/widgets/weather.mdx`

Weather's Python attr is `message`. Add a single-line note that `text =` is accepted (per `_build_widget`'s remap) for parity with message/countdown configs.

### 6. `docs/site/src/content/docs/concepts/sections-and-modes.mdx`

Two short additions:
- Note `mode = "gif"` is legacy and `mode = "swap"` with a `gif` widget is the current recommendation (mirrors validator rule 33 if/when shipped).
- Document the `default = ` vs `transition = ` distinction: `default` is the `[transitions]`-block-level key for the playlist-wide default; sections use `transition` to override. Writing `default = ` inside a section block has no effect.

## Test plan

- `make docs-lint` clean
- `make docs-build` succeeds (44 pages built)
- `pnpm exec prettier --check` on the modified .mdx files
- Drift test (`test_docs_config_options_drift`) catches any new field references and flags allow-list updates needed. (For `transition_colors`, `show_pikachu`, `show_pokeball` — these need to be added to the allow-list at `tests/test_docs_config_options_drift.py` since they're now in the reference table.)

## Out of scope / parallel work

- **Validator rules for the same surface area** (rules 32-35) ship in the parallel PR. This PR is docs-only.
- **`gif_loops = 0` semantics** — different PR with a small engine change.
- **Tutorial rewrites** to use `text` everywhere instead of `message` — too much churn for the value; this PR just declares the canonical form on the reference pages and lets the tutorials evolve organically.

## Implementation notes

- Each .mdx edit is a few lines. The total PR diff should be < 100 lines of docs prose, perhaps 6-8 files.
- The drift-test allow-list update is the only test change. Treat it like the previous PRs: same commit as the relevant docs row.
- If the validator-hardening PR lands first, this PR can also add a one-line note in `pitfalls.mdx` for rule 33 pointing readers at the recommended migration path. If this PR lands first, the validator PR can do the back-reference.
