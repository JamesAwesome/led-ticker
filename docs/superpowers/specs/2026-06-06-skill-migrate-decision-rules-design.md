# Config-Skill Migration — Sub-piece 1: decision-rules → skill references — Design

**Date:** 2026-06-06
**Status:** Approved (brainstorm), pending implementation plan

## Context

First sub-piece of the **config-skill fact-pack migration** (memory `project_config_skill_factpack_migration`) — retiring the five monolithic `docs/content-source/*-legacy.md` guides the `creating-a-config` skill reads, onto a clean split:

- **Shared reference data** (widget/transition/hardware options, emoji) → `docs/content-source/` fact-packs (the docs site also uses these).
- **Skill-procedural knowledge** (decision-rules, asset-handling playbook, must-customize lists, snippets) → the skill's own `.claude/skills/creating-a-config/references/`.

This sub-piece migrates the **decision-rules** (purely skill-procedural), chosen first as the cleanest pattern-setter: no content-source fact-pack, no docs-site coupling — a self-contained "move into the skill, repoint, delete" that validates the split + delete loop. The four remaining sub-pieces (hardware, asset-handling, widgets, transitions) follow, each its own spec→plan→impl.

New branch `feat/skill-migrate`.

## Current state (verified)

- `docs/content-source/decision-rules-legacy.md` — **267 lines**, the 21 numbered validation rules (each `SOURCE` / `DETECT` / `SYMPTOM` / `FIX`), with a header noting it's derived from CLAUDE.md sections (last-synced 2026-05-07). It is the skill's lint checklist — **not** a docs-site fact-pack (the site doesn't render it).
- `.claude/skills/creating-a-config/SKILL.md` references `docs/content-source/decision-rules-legacy.md` **9 times** (lines 101, 113, 121, 136, 150, 165, 167, 190, 198) across new / add / refine modes and the "validation: flag-and-ask philosophy" section.
- `.claude/skills/creating-a-config/references/decision-rules.md` — a **1-line stub**: "See docs/content-source/decision-rules-legacy.md and docs/content-source/rules/ for migrated content."
- Nothing else references the file (no docs-site page, no `OptionsTable`, no code, no test). (Mentions in `docs/superpowers/` plans/specs are historical and out of scope.)

## Decisions (from brainstorm)

- **Architecture: split** — procedural content goes to the skill's `references/`. Decision-rules are purely procedural → `references/decision-rules.md`.
- **Move, not rewrite** — carry the 21 rules verbatim. Do NOT reconcile them against `validate.py` / `pitfalls.mdx` (that was the rejected "reference validate.py" option) and do NOT touch the other four legacy files.

## Deliverable

1. **Replace** `.claude/skills/creating-a-config/references/decision-rules.md` (the stub) with the **full content** of `docs/content-source/decision-rules-legacy.md` (the 21 rules + header). Verbatim move; the only allowed edit is dropping the now-stale "and docs/content-source/rules/" phrasing if it appears (it's only in the stub being replaced).
2. **Repoint** all 9 `SKILL.md` references from `docs/content-source/decision-rules-legacy.md` to `references/decision-rules.md` (skill-relative, consistent with how `SKILL.md` already cites `references/snippets.md`). This includes the inline citations like "per `docs/content-source/decision-rules-legacy.md` rule N" → "per `references/decision-rules.md` rule N".
3. **Delete** `docs/content-source/decision-rules-legacy.md`.

## Verification

- `grep -rn "decision-rules-legacy" .` (excluding `.venv`/`node_modules`/`dist`/`docs/superpowers/`) returns **nothing** — no dangling reference.
- `.claude/skills/creating-a-config/references/decision-rules.md` contains all 21 rules (e.g. `grep -c "^## Rule " references/decision-rules.md` == 21) and the file is no longer a stub.
- Every `SKILL.md` mention of decision-rules now points at `references/decision-rules.md`; that path exists.
- `docs/content-source/decision-rules-legacy.md` no longer exists.
- No docs-site or code change → `make docs-build`/`make docs-lint` and the test suite are unaffected (sanity: `git status` shows only the skill + the deleted legacy file; nothing under `docs/site/` or `src/`).

## Notes / risks

- **No automated test for the skill.** The `creating-a-config` skill is markdown-driven; "does it still work" is validated by the references resolving + the content being intact, not by a test run. A read-through confirms the moved file is complete.
- The legacy file's header (`Derived from CLAUDE.md … Last synced: 2026-05-07`) is carried along; it documents the rules' provenance and stays accurate after the move. (Optional: bump the date — left as-is to keep the move clean.)

## Out of scope

- The other four sub-pieces (hardware, asset-handling, widgets, transitions).
- Reconciling the 21 rules with `validate.py` or the docs `pitfalls.mdx` rule catalog (different surface; rejected option).
- Hardening the validator to emit rule IDs.
- Touching `references/snippets.md` or the other `references/*.md` pointer stubs (those belong to their own sub-pieces).
