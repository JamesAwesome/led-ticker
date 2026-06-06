# Config-skill migration 5/5 — transitions — Design

**Date:** 2026-06-06
**Status:** Approved (brainstorm)

## Context

Final sub-piece of the config-skill fact-pack migration (memory `project_config_skill_factpack_migration`). After this, all five `docs/content-source/*-legacy.md` guides are gone and the `creating-a-config` skill reads only its own `references/` + the per-page `content-source/` fact-packs. Prior pieces: decision-rules #170, hardware-guide #171, asset-handling #172 (clean moves); widgets #173 (first reconciliation — fact-packs were richer/more-correct; added a selection guide, fixed two drift bugs).

`transitions-legacy.md` is the last `*-legacy` reference in SKILL.md (3 refs: lines 121, 125, 165).

## Finding from exploration

The 4 family fact-packs (`docs/content-source/transitions/{push,wipe,sprite,special}.md`, 92 lines) are current and own the **per-family catalog + tuning** — transition names/directions/best-for, `transition_duration` ranges, `easing`, sweep colors (`transition_color`/`transition_colors`), cross-scale behavior, and family-specific tips (e.g. the `dissolve` physical-resolution note with its tripwire test name). In places they're *better* than the legacy guide.

What `transitions-legacy.md` (246 lines) has that the fact-packs do **not** is **skill-procedural wizard knowledge**:

1. **"Selecting a transition" tone table** (Minimal / Playful / Info-dense / Branded-pro → suggested transitions). Pure wizard logic; SKILL.md:125 consults it by name; it lives in no fact-pack and no docs page.
2. **"Configuring transitions" authoring semantics** — global `[transitions]` / `between_sections` fallback, per-section `transition` and its precedence, and the `entry_transition` / `widget_transition` fine-grained-control fields with their precedence rules. The wizard needs this to author Phase-3 transition TOML and to reason in `refine` mode.

**Drift bug:** the legacy "Configuring transitions" examples write `transition_duration = 800` (lines 192, 216) — a milliseconds value — while legacy's own prose (line 127) and the fact-packs say `transition_duration` is in **seconds**, and `validate.py:896` (Rule 21) warns when it "looks like milliseconds". Migrating those examples must fix `800` → seconds (`0.8`).

The remaining legacy sections are **pure dev internals already covered on the docs site**, not wizard-authoring knowledge:
- "How transitions work" (frame_at / draw-blackout-draw constraints) and "Per-widget font and colors" (frame-aware pausing) — internals.
- "Register your own transition" — covered by `docs/site/src/content/docs/plugins/extending/writing-a-transition.mdx`.
These are **dropped**, not migrated.

## The split for transitions

- **Per-family catalog + tuning (shared, docs-site-consumed):** already in `content-source/transitions/{push,wipe,sprite,special}.md`. The skill reads those for family details.
- **Skill-procedural wizard knowledge:** move into a **new `.claude/skills/creating-a-config/references/transition-selection.md`** — the "Selecting a transition" tone table + the "Configuring transitions" authoring semantics (precedence, entry/widget control), with the `transition_duration` examples corrected to seconds.
- **Delete `transitions-legacy.md`** and the orphan `references/transitions.md` stub (left from the earlier abandoned migration attempt; nothing references it).

## Deliverable

1. **Create `references/transition-selection.md`:**
   - Header: this guide is for *choosing* a transition + *wiring* it into the config; for each family's catalog and tuning (durations, easing, colors) read `docs/content-source/transitions/{push,wipe,sprite,special}.md`.
   - **Selecting a transition** — the tone table, verbatim from legacy (lines 7–12).
   - **Configuring transitions** — global fallback / `between_sections`, per-section `transition` + the precedence rule, and the `entry_transition` / `widget_transition` fine-grained-control section with its precedence rules and TOML examples — **with `transition_duration = 800` → `0.8` (seconds)** in the examples.
2. **Repoint SKILL.md (3 refs):**
   - Phase 3 load (line ~121): `docs/content-source/transitions-legacy.md` → `references/transition-selection.md`; add "for family catalog/tuning read `docs/content-source/transitions/<family>.md`".
   - "Selecting a transition" table cite (line ~125): → `references/transition-selection.md`.
   - `refine` load (line ~165): `docs/content-source/transitions-legacy.md` → `references/transition-selection.md`.
3. **`git rm docs/content-source/transitions-legacy.md`** and **`git rm .claude/skills/creating-a-config/references/transitions.md`** (orphan stub).
4. **No docs-site change.**

## Out of scope

- Rewriting the fact-packs (current; correctness-swept during the docs effort).
- Re-documenting the dropped dev-internals sections (already on the docs site).
- `snippets.md` (skill-only; stays).

## Verification

- New `references/transition-selection.md` contains the tone table (Minimal/Playful/Info-dense/Branded-pro) and the entry_transition/widget_transition precedence content.
- **No `transition_duration = 800` (or any `transition_duration = <int ≥ 50>`) in the new file** — the ms drift is fixed to seconds. Grep clean.
- No `transitions-legacy` references remain outside `docs/superpowers/`.
- SKILL.md references `references/transition-selection.md` (3×) and `docs/content-source/transitions/` (family dir); `transitions-legacy` 0×; **and no `*-legacy` references remain anywhere in SKILL.md** (migration complete).
- `transitions-legacy.md` + orphan `references/transitions.md` stub deleted; no change under `docs/site/src/`.
- `make docs-lint` clean.
- Skill content has no automated test and skips CI's Python jobs — verify by grep + read-through.
