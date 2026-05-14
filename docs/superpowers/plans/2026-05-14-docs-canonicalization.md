# Docs canonicalization implementation plan

> **Every subagent prompt MUST tell the subagent to run `git branch --show-current` first and abort if it returns `main`.** Expected: `worktree-docs-canonicalization`.

**Goal:** Six `.mdx` edits + one drift-test allow-list bump. Surface undocumented section fields, declare canonical TOML idioms, clarify title-vs-widget grammar.

**Spec:** `docs/superpowers/specs/2026-05-14-docs-canonicalization-design.md`.

**Working directory:** `/Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/docs-canonicalization/`

This is a docs-only PR. No code changes, no test additions beyond the drift-test allow-list.

---

### Task 1: `config-options.mdx` — surface undocumented fields

**File:** `docs/site/src/content/docs/reference/config-options.mdx`

Find the `[[playlist.section]]` field table (around line 68). Add three rows after `scroll_step_ms` (before `transition_specified`, alphabetical-ish):

| Field | Type | Default | Notes |
| --- | --- | --- | --- |
| `transition_colors` | `[[r,g,b], ...]` | `null` | Multi-color list for transitions that cycle through colors (e.g., `wipe_random` with multiple sweep colors). Plural form of `transition_color`. |
| `show_pikachu` | bool | `true` | Pokeball-family transitions: toggle the Pikachu sprite that emerges after the ball opens. |
| `show_pokeball` | bool | `true` | Pokeball-family transitions: toggle the ball itself. (Setting both to `false` produces a beam-only transition.) |

Also add a short paragraph after the table noting the inline-table form for `transition`:

> When the transition needs more than just the type, prefer the inline-table form: `transition = { type = "wipe_left", duration = 0.8, easing = "ease_out", color = [255, 0, 0] }`. The flat sibling form (`transition = "wipe_left"` + `transition_duration = 0.8`) is equivalent and remains fully supported.

### Task 2: `config-options.mdx` — title block clarification

Same file. Find the `[playlist.section.title]` section. Replace the current "uses all the same knobs as a message widget" framing with:

> A title block accepts the same field surface as a `message` widget plus one title-specific alias: `color` is the title-specific spelling of `font_color`. Both work, and the `color` alias only applies inside title blocks — writing `color = "random"` on a regular `[[playlist.section.widget]]` is a configuration error (the alias doesn't apply outside titles).

### Task 3: Widget reference pages — `text` vs `message`

**Files:**
- `docs/site/src/content/docs/widgets/message.mdx`
- `docs/site/src/content/docs/widgets/countdown.mdx`
- `docs/site/src/content/docs/widgets/weather.mdx`

For message + countdown, add one line near the existing field surface note:

> The canonical TOML key for the content string is `text`. `message =` is also accepted (it's the internal Python attribute name) but new configs should prefer `text`.

For weather, slightly different framing because weather's Python attr is `message` and `text` is a `_build_widget`-time alias:

> Weather's content is set via either `text =` or `message =` — both spellings work. The internal Python attribute is `message`, but `text =` is supported for consistency with the message and countdown widgets.

### Task 4: `concepts/sections-and-modes.mdx`

Two additions:

**A.** Near the existing mode descriptions, add a `mode = "gif"` legacy note:

> **Legacy: `mode = "gif"`.** Preserved for backward compatibility, but the recommended setup for displaying gifs is `mode = "swap"` with a `gif` widget in the section's `widget` list. Direct use of `mode = "gif"` may be removed in a future release.

**B.** Near the `[transitions]` discussion or in a new "Common confusions" subsection, add:

> **`default` vs `transition`.** The `[transitions]` block uses `default = "wipe_left"` for the playlist-wide default. Inside a `[[playlist.section]]` the equivalent is `transition = "wipe_left"` — writing `default = ` inside a section block has no effect (the key is silently dropped). The validator's rule 35 (when shipped) catches this.

If rule 35 hasn't shipped yet, omit the last sentence; the rest stands.

### Task 5: Drift-test allow-list

**File:** `tests/test_docs_config_options_drift.py`

Add three entries to `DOCUMENTED_KEYS["section"]`:

```python
"transition_colors",
"show_pikachu",
"show_pokeball",
```

Place alphabetically. The drift test will fail (red) without this update because the new docs rows would mismatch the allow-list.

### Task 6: Verification

```bash
make docs-lint   # prettier + astro check
make docs-build  # 44 pages built
uv run pytest tests/test_docs_config_options_drift.py -v
```

All three must pass.

### Task 7: Commit + PR

Single commit since this is all docs:

```
docs: canonicalize TOML idioms (text, transition table, title alias)

Surface undocumented [[playlist.section]] fields (transition_colors,
show_pikachu, show_pokeball). Document the inline-table form for
`transition` as the preferred section-scope syntax when more than
just the type is needed. Clarify that `color` on title blocks is a
title-specific alias for `font_color` — it does NOT apply on regular
widgets. Note mode="gif" is legacy. Declare `text` as canonical
content key (`message` continues to work as an alias).

Pure docs PR. No code changes. Findings from the three-persona
config-surface review panel that didn't require renames or behavior
changes.
```

Push + open PR. PR body should reference the panel review and the
sibling validator-hardening PR.

---

## Self-review

- All edits are additive — no removal of existing prose.
- No field renames or deprecations.
- Drift-test allow-list update lands in the same commit as the new docs rows (per the established pattern; failing to update it makes the test red).
- Rule 33/35 cross-references in the concepts page are optional — if the validator-hardening PR isn't merged first, the docs-only PR mentions "may be" or omits the rule reference.
