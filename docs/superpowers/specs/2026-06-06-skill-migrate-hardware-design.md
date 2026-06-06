# Config-Skill Migration — Sub-piece 2: hardware-guide → skill references — Design

**Date:** 2026-06-06
**Status:** Approved (brainstorm), pending implementation plan

## Context

Second sub-piece of the config-skill fact-pack migration (memory `project_config_skill_factpack_migration`; architecture = split, see sub-piece 1 spec). Sub-piece 1 (decision-rules → skill references, #170) is merged and set the pattern.

`docs/content-source/hardware-guide-legacy.md` (58 lines) is the skill's hardware cheat-sheet: an at-a-glance specs comparison, viewing-distance → font-size heuristics, bigsign refresh tuning, scale guidance, and a "what doesn't work where" list. `SKILL.md` reads it **3×** (lines 73, 81, 133) — for Phase-1 default font sizes (the distance table), Phase-3 refresh tuning, and general Phase-1 context.

## Decision (refined from exploring)

The genuinely *shared* part (the specs comparison) **already lives on the docs site** at `hardware/bigsign.mdx` + `smallsign.mdx` (hand-written `.mdx`, audited in Phase 3). The docs site does **not** consume hardware via `OptionsTable`, so there's no fact-pack to feed — creating a `content-source/hardware/*.md` fact-pack would **triplicate** the specs (legacy + docs mdx + new pack) and add drift.

Therefore: treat the whole hardware-guide as **skill-procedural** — move it into the skill's `references/`. Same clean pattern as decision-rules; **no content-source fact-pack created.**

## Deliverable

1. **Move** `docs/content-source/hardware-guide-legacy.md` → `.claude/skills/creating-a-config/references/hardware-guide.md` (replacing the current 1-line pointer stub there). Verbatim move (only drop the now-stale "and docs/content-source/hardware/" phrasing if present — that's only in the stub being replaced).
2. **Repoint** `SKILL.md`'s 3 references (lines 73, 81, 133) from `docs/content-source/hardware-guide-legacy.md` → `references/hardware-guide.md` (skill-relative).
3. **Delete** `docs/content-source/hardware-guide-legacy.md`.

## Verification

- `grep -rn "hardware-guide-legacy" .` (excluding `.venv`/`node_modules`/`dist`/`docs/superpowers/`) returns nothing.
- `.claude/skills/creating-a-config/references/hardware-guide.md` holds the full content (no longer a stub; e.g. contains the "At-a-glance comparison" + "Refresh tuning" headings).
- `SKILL.md`'s 3 hardware references now resolve to `references/hardware-guide.md`.
- `docs/content-source/hardware-guide-legacy.md` deleted.
- No `docs/site/` or `src/` change (skill + content-source only); docs build + test suite unaffected.

## Notes / out of scope

- **No content-source `hardware/` fact-pack** — the docs `hardware/*.mdx` pages own the user-facing specs.
- **Not** reconciling the skill's hardware cheat-sheet against the docs `hardware/*.mdx` pages (a separate drift concern).
- The remaining sub-pieces (asset-handling, widgets, transitions). No automated test for the skill (markdown-driven) — verify by grep + path-existence + read-through, as in sub-piece 1.
