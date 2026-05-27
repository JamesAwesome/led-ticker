# Design: Validator hardening (rules 32-35)

**Date:** 2026-05-14
**Status:** Approved

## Overview

Four additive validator rules catching real silent failures and high-frequency typos identified by the three-persona config-surface review panel. Pure additive — no field renames, no behavior changes. Each rule converts a current source of confusion into an explicit error or warning at `make validate` time.

| Rule | Severity | What it catches |
|---|---|---|
| **32** | error | `content_height × scale > panel_h_real` — silent top/bottom clipping on bigsign when section sizing exceeds the panel ceiling |
| **33** | warning | `mode = "gif"` — legacy mode, undocumented as such; 21 production configs still use it |
| **34** | error | `scroll_speed_ms` set at section level, OR `scroll_step_ms` set on a widget — did-you-mean bridge (same shape as rule 29) |
| **35** | warning | `default = "..."` written inside a `[[playlist.section]]` block — silently ignored field (looks like the global `[transitions] default` syntax) |

## Field surface

None. This is validator-only. No new TOML fields, no behavior changes for existing configs.

## Architecture

### Raw TOML access

Rules 34 and 35 need to inspect raw section dicts (not the `SectionConfig` dataclass) because `SectionConfig` silently drops unknown keys. Add a private field on `SectionConfig`:

```python
_raw: dict[str, Any] = field(default_factory=dict, repr=False)
```

The loader in `config.py` populates it: `_raw=section_raw`. Validator rules can then iterate keys to detect unknown / cross-scope fields. Other consumers of `SectionConfig` are unaffected (field has a default factory).

This is the minimum-surface change. The existing `_check_static` flow already iterates `config.sections`; each section now exposes its raw map.

### Rule 32: `content_height × scale` ceiling

Section-level error. Located in `_check_static`.

```python
# panel_h_real is computed from display.pixel_mapper_config or rows × parallel
ph_real = _panel_h_real(config.display)
product = section.content_height * section.scale
if product > ph_real:
    # error at section[i]
```

Helper `_panel_h_real` already exists at `validate.py:_panel_h_real`. Fire only when the computed product strictly exceeds the panel — equality is fine.

This complements rule 1 (the existing soft warning for `content_height × scale > panel_h`). Rule 32 is stricter — same condition, error severity, runs in `_check_static`. Rule 1 stays for completeness but rule 32 will fire first.

Actually: **rule 1 and rule 32 are the same check at different severities.** The cleanest answer is to promote rule 1 to error, not add rule 32. See "Implementation notes" below.

### Rule 33: `mode = "gif"` legacy warning

Section-level warning in `_check_soft`. Condition: `section.mode == "gif"`. Single warning per gif-mode section.

Message: legacy mode preserved for backward compat; `mode = "swap"` with a `gif` widget is the current recommendation. Fix lists the minimal migration.

### Rule 34: scroll cross-scope did-you-mean

Two conditions (same rule number, like rule 25's compound):

1. `scroll_speed_ms` set in section's `_raw` (section level, where it's not a valid field) — error pointing at `scroll_step_ms`.
2. Any widget's raw config has `scroll_step_ms` AND `widget.type in ("gif", "image")` — error pointing at `scroll_speed_ms`. Other widget types reject it but don't get a did-you-mean (no symmetric concept).

Two errors per offending key.

### Rule 35: `default = ` inside section

Section-level warning. Condition: `"default" in section._raw`. The user wrote `default = "wipe_left"` inside `[[playlist.section]]` (silently ignored — it's a `[transitions]` key, not a section key). Suggest using `transition = "wipe_left"` instead.

### Validator wiring

- Rule 32 (or rule 1 promotion): `_check_static` already handles section-level checks. Add the new block alongside rule 25.
- Rule 33: `_check_soft` for the warning.
- Rule 34: split between `_check_static` (widget loop, scroll_step_ms on gif/image) and a section-level check for `scroll_speed_ms`.
- Rule 35: `_check_soft` (warning).

## Validation behavior summary

After this PR, the section-level static checks in `_check_static` run in this order for each section:

1. Rule 32 (content_height × scale ceiling) — error
2. Rule 25 (start_hold mode-mismatch) — existing
3. Rule 26 (separator_* mode-mismatch) — existing
4. (widget loop):
   - Rule 28 (bottom_text_loops on two_row)
   - Rule 29 (text_loops typo)
   - Rule 34b (scroll_step_ms on gif/image widget)
5. Rule 34a (scroll_speed_ms on section, via section._raw)
6. Rule 35 (default on section, via section._raw)

`_check_soft` adds rule 33 (mode = gif).

## Test plan

Per rule, with both happy-path and edge cases:

**Rule 32** (3 tests):
- `content_height × scale > panel_h_real` → error
- `content_height × scale == panel_h_real` → no error (boundary)
- `content_height × scale < panel_h_real` → no error

**Rule 33** (2 tests):
- `mode = "gif"` → warning
- `mode = "swap"` → no warning

**Rule 34** (4 tests):
- `scroll_speed_ms` at section level → error pointing at scroll_step_ms
- `scroll_step_ms` on gif widget → error pointing at scroll_speed_ms
- `scroll_step_ms` on image widget → error pointing at scroll_speed_ms
- `scroll_step_ms` on message widget → no error (no symmetric concept)

**Rule 35** (2 tests):
- `default = "..."` inside section → warning
- `default = "..."` inside `[transitions]` block → no warning (legit usage)

**Regression sweep**:
- Validate every TOML in `config/` and `docs/site/demos-*/` — note any new errors. `mode = "gif"` warnings expected on ~21 configs; flag if anything else trips unexpectedly.

## Docs

- `pitfalls.mdx`: rule 32, 33, 34, 35 entries.
- `tools/validate.mdx`: 4 new rows in reference table.
- Optional: a sentence in `config-options.mdx` noting that `_raw` validation catches typos.

## Implementation notes

### Re: rule 1 vs rule 32

The existing rule 1 is a warning for the same condition. Two options:

**Option A:** Promote rule 1 to error severity. Renumber? No — keep the rule number, just change severity. The docs and tests for rule 1 need to flip from warnings to errors. Existing test `test_rule1_content_height_overflow` expects a warning; needs update.

**Option B:** Keep rule 1 as warning AND add rule 32 as error. Both fire when condition triggers. Confusing — users see both.

Going with **Option A**. Simpler, no rule-number bloat, the existing rule was always too lenient given the PM review's "silent clipping is a churn event" framing.

(So this spec adds rules 33, 34, 35 plus promotes rule 1. Updating the rule list above.)

### Raw access pattern

The `_raw` field uses `field(default_factory=dict, repr=False)` so test paths that construct `SectionConfig` directly don't break. The validator's check on `_raw` keys becomes the standard "unknown field" detection point — extensible for future similar rules.

### What this PR is NOT

- Not a rename of any field
- Not a behavior change in the engine
- Not a deprecation of any working idiom (rule 33 is a warning, not error)
- Not the general unknown-kwarg validator (still deferred; rules 34/35 are targeted bridges, not generic)
