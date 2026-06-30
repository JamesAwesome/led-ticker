# Task 10 Report — docs(tokens): value-tokens concept page + example + reference

## Status: COMPLETE

## Commit
`6f5706f0` — `docs(tokens): value-tokens concept page + example + reference`

## Gates

| Check | Result |
|---|---|
| `make docs-build` | clean — 67 pages built, 0 errors |
| `make docs-lint` | clean — 0 errors, 0 warnings, 0 hints |
| `tests/test_docs_config_options_drift.py` | 8/8 passed |

## What was done

### New page
`docs/site/src/content/docs/concepts/value-tokens.mdx` — DOCS-STYLE compliant concept page covering:
- The `:id:` token syntax and how it relates to the existing `:slug:` emoji syntax
- All three built-in source types (`clock`, `date`, `static`) with `TomlExample` blocks and strftime format tables
- A full working example that declares two sources and uses them in a `message` widget
- Live-update / reflow behavior (1 Hz, version-gated, freeze during scroll/transition/typewriter)
- Resolution order: emoji wins, then source, then literal fallback
- v1 scope note (clock/date/static built-in; `api.source` available for plugin authors; polled/async sources are v2)
- Tips section: zero-pad for no-reflow, multiple `[[source]]` blocks, ticker/one_at_a_time support
- `RelatedPages` CTA pointing at emoji, sections-and-modes, and message widget
- Description is quoted to handle the `:id:` colon chars in YAML frontmatter

### Sidebar
`docs/site/astro.config.mjs` — added `{ label: "Value tokens", link: "/concepts/value-tokens/" }` in alphabetical position (after "Sections and modes") in the Concepts group.

### Reference page
`docs/site/src/content/docs/reference/config-options.mdx`:
- Added `[[source]]` to the opening "this page covers" list
- Added new `## \`[[source]]\`` section (before `[busy_light]`) with a 5-row field table: `id`, `type`, `format`, `timezone`, `value` — including Required column and notes on what applies to which type

### Example config
`config/config.example.toml` — added a commented `[[source]]` block between the `[transitions]` and playlist sections, matching the file's existing comment density and style. Shows all three source types (`clock.now`, `date.today`, `brand.tagline`) with inline comments.

### Cross-links (RelatedPages)
- `concepts/sections-and-modes.mdx` — added `concepts/value-tokens`
- `widgets/message.mdx` — added `concepts/value-tokens`
- `widgets/two_row.mdx` — added `concepts/value-tokens`
- `widgets/gif.mdx` — added `concepts/value-tokens`
- `widgets/image.mdx` — added `concepts/value-tokens`
- `plugins/api-reference.mdx` — Prettier fixed a trailing space in the `api.source` table row (no content change)

## Drift test note
`tests/test_docs_config_options_drift.py` does not cover `[[source]]` — `SourceConfig` is not one of the checked dataclasses (the test covers `DisplayConfig`, `BusyLightConfig`, `WebConfig`, title, transitions, and section). No update to the drift test was needed or appropriate; `[[source]]` config is hand-curated on the reference page (like `[title]` and `[transitions]`).

## Concerns
None. All gates clean.

---

## Task 10 — Doc-accuracy follow-up (commit `1ae1bc01`)

Three inaccuracies found in post-implementation review and corrected:

### Fix 1 — `format` is optional, not required (important)

**Files:** `config-options.mdx` (Required column + Notes), `value-tokens.mdx` (no change needed — page showed `format` in examples but did not claim it was required).

**Before (`config-options.mdx`):**
```
| `format`   | string | see note | strftime format string. Required for `clock` and `date`; ignored by `static`. |
```
**After:**
```
| `format`   | string | no       | strftime format string. Optional for `clock` and `date` (default `"%H:%M"`); ignored by `static`. |
```

**Evidence:** `factories.build_source` uses `cfg.raw.get("format", "%H:%M")` — the `%H:%M` default applies when `format` is absent. `validate._check_sources` mirrors this with `src.raw.get("format", "%H:%M")` before calling `_strftime_test`. Neither raises an error when `format` is omitted.

### Fix 2 — `id` pattern is a functional requirement, not validator-enforced (minor)

**Files:** `config-options.mdx` (id row Notes column), `value-tokens.mdx` (paragraph after the static source example).

**Before (`config-options.mdx`):** "Must match `[a-z_][a-z0-9_.]*`." (implied enforcement by validator)
**After:** "Must match `[a-z_][a-z0-9_.]*` to be usable as a `:token:` — an id that doesn't match the pattern is accepted by the validator but won't be recognized at display time (the `:...:` renders as literal text)."

**Before (`value-tokens.mdx`):** "It must match the `:slug:` pattern (`[a-z_][a-z0-9_.]*`) — lowercase letters, digits, underscores, and dots."
**After:** "It must match the pattern `[a-z_][a-z0-9_.]*` — lowercase letters, digits, underscores, and dots — to be usable as a `:token:`. An id that doesn't match the pattern is accepted, but the `:...:` placeholder won't be recognized at display time and renders as literal text instead."

**Evidence:** `validate._check_sources` checks only: duplicate id, emoji slug collision, unknown type, bad strftime format, bad timezone, missing static value. No regex check on `id` shape anywhere in the codebase.

### Fix 3 — DOCS-STYLE §17 banned phrase (minor)

**File:** `value-tokens.mdx` line 14 (opening code block comment).

**Before:** `# no token — works exactly as before`
**After:** `# no token — plain string`

### Gates (post-fix)

| Check | Result |
|---|---|
| `make docs-build` | clean — 67 pages built, 0 errors |
| `make docs-lint` | clean — 0 errors, 0 warnings, 0 hints |
