# Config-skill migration 3/5 — asset-handling — Design

**Date:** 2026-06-06
**Status:** Approved (brainstorm)

## Context

Third of five sub-pieces in the config-skill fact-pack migration (see memory `project_config_skill_factpack_migration`). The `creating-a-config` skill reads five monolithic `docs/content-source/*-legacy.md` guides. The agreed architecture is a **split**: shared reference data → `content-source/` fact-packs (also consumed by the docs site); skill-procedural knowledge → the skill's own `references/`. Sub-pieces 1/5 (decision-rules, #170) and 2/5 (hardware-guide, #171) are done — both were clean moves of pure-procedural content into `references/`.

## Finding from exploration

`docs/content-source/asset-handling-legacy.md` (107 lines) is **entirely skill-procedural**:
- Brand colors hex→RGB mapping table
- Custom fonts + the `font_threshold` weight-contrast rule
- Images / GIFs fit-mode decision tree (stretch / pillarbox / letterbox / alpha)
- URLs and handles mapping

Nothing in the docs site consumes it as an `OptionsTable` fact-pack (confirmed by grep — no site reference to `asset-handling-legacy`). So, like the prior two, **all of it moves to the skill's `references/`; none stays as a `content-source/` fact-pack.**

The docs-site page `docs/site/src/content/docs/tools/creating-a-config.mdx:62` **already links to `references/asset-handling.md`** (the destination), which is currently a 1-line stub. This migration fills that stub with the real content, so the existing site link starts resolving to substance — no docs-site edit needed.

## Deliverable

- Replace the stub `.claude/skills/creating-a-config/references/asset-handling.md` with the full content of `docs/content-source/asset-handling-legacy.md` (verbatim move).
- Repoint SKILL.md's 6 references (`docs/content-source/asset-handling-legacy.md` → `references/asset-handling.md`).
- `git rm docs/content-source/asset-handling-legacy.md`.
- No docs-site change.

## Out of scope

- Sub-pieces 4/5 (widgets) and 5/5 (transitions) — these involve reconciling the leaner existing fact-packs against the richer legacy content; each is its own spec→plan→PR.
- Any content rewrite. This is a verbatim move (the content already passed the docs effort's correctness sweep, incl. the `hold_time` fix).

## Verification

- No `asset-handling-legacy` references remain outside `docs/superpowers/` (the spec/plan themselves may mention it).
- The new `references/asset-handling.md` contains the legacy headings (Brand colors, Custom fonts, Images / GIFs, URLs and handles).
- SKILL.md references `references/asset-handling.md` (6×) and `asset-handling-legacy` 0×.
- Legacy file deleted; no change under `docs/site/src/`.
- Skill changes have no automated test and skip CI's Python jobs — verify by grep + read-through.
