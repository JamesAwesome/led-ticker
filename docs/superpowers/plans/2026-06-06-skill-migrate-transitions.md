# Config-skill migration 5/5 — transitions — Implementation Plan

> **For agentic workers:** content restructure (not a verbatim move). No code, no automated test for skill content. Final piece — removes the last `*-legacy.md`.

**Goal:** Replace the skill's dependency on `transitions-legacy.md` with a new `references/transition-selection.md` (selection tone table + config-authoring semantics) plus the existing family fact-packs; delete the legacy file + orphan stub. Side effect: the migrated config examples fix the `transition_duration` ms→seconds drift.

**Spec:** `docs/superpowers/specs/2026-06-06-skill-migrate-transitions-design.md`
**Worktree:** `.claude/worktrees/skill-transitions`, branch `feat/skill-migrate-transitions` (off origin/main).
**Commit/push/PR:** prefix git with `-c core.hooksPath=/dev/null` (pre-commit framework absent in worktree).

---

### Task 1: Author `references/transition-selection.md`

**File:** Create `.claude/skills/creating-a-config/references/transition-selection.md`.

- [ ] Header: guide is for *choosing* a transition + *wiring* it into config; for each family's catalog/tuning (durations, easing, colors) read `docs/content-source/transitions/{push,wipe,sprite,special}.md`.
- [ ] **Selecting a transition** — the tone table verbatim from `transitions-legacy.md` lines 7–12 (Minimal / Playful / Info-dense / Branded-pro → suggested transitions).
- [ ] **Configuring transitions** — port legacy lines 141–176: global fallback / `between_sections`, per-section `transition` + section-precedence rule, and the `entry_transition` / `widget_transition` fine-grained-control subsection with its precedence rules and TOML examples. **In every example, write `transition_duration` in seconds — replace `= 800` with `= 0.8`.**
- [ ] Verify no ms drift carried: `grep -nE "transition_duration *= *[0-9]{2,}" .claude/skills/creating-a-config/references/transition-selection.md && echo "MS DRIFT — FIX" || echo "OK: durations in seconds"` (expect OK).

### Task 2: Repoint SKILL.md + delete legacy & orphan stub

**File:** Modify `.claude/skills/creating-a-config/SKILL.md`; delete `docs/content-source/transitions-legacy.md` and `.claude/skills/creating-a-config/references/transitions.md`.

- [ ] Phase 3 load (line ~121): replace `docs/content-source/transitions-legacy.md` with `references/transition-selection.md`; append "for family catalog/tuning read `docs/content-source/transitions/<family>.md`."
- [ ] "Selecting a transition" cite (line ~125): point the table reference at `references/transition-selection.md`.
- [ ] `refine` load (line ~165): replace `docs/content-source/transitions-legacy.md` with `references/transition-selection.md`.
- [ ] `git rm docs/content-source/transitions-legacy.md`
- [ ] `git rm .claude/skills/creating-a-config/references/transitions.md`
- [ ] Verify:
```bash
cd /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/skill-transitions
grep -rn "transitions-legacy" . --include='*.md' --include='*.mdx' | grep -v "docs/superpowers/" || echo "OK: no dangling transitions-legacy refs"
grep -c "references/transition-selection.md" .claude/skills/creating-a-config/SKILL.md   # expect 3
grep -c "transitions-legacy" .claude/skills/creating-a-config/SKILL.md                   # expect 0
grep -c -- "-legacy" .claude/skills/creating-a-config/SKILL.md                           # expect 0 — MIGRATION COMPLETE
grep -E "Minimal|Playful|Info-dense|Branded-pro" .claude/skills/creating-a-config/references/transition-selection.md | head
test -f docs/content-source/transitions-legacy.md && echo "STILL PRESENT" || echo "OK: legacy deleted"
test -f .claude/skills/creating-a-config/references/transitions.md && echo "STUB PRESENT" || echo "OK: orphan stub deleted"
ls docs/content-source/*-legacy.md 2>/dev/null && echo "LEGACY REMAINS" || echo "OK: zero *-legacy.md files remain"
git status --short docs/site/ | grep . && echo "UNEXPECTED site change" || echo "OK: no site change"
```

### Task 3: Build/lint + commit

- [ ] `make docs-lint` (expect clean).
- [ ] Commit:
```bash
git add .claude/skills/creating-a-config/SKILL.md .claude/skills/creating-a-config/references/transition-selection.md docs/superpowers/
git -c core.hooksPath=/dev/null commit -m "skill: migrate transitions onto fact-packs + selection guide (migration 5/5)"
```
(Both `git rm`s are already staged.)

---

## Self-Review

**Spec coverage:** new selection/config guide → Task 1; repoint + delete legacy & stub → Task 2; verify/commit → Task 3. ✓
**Placeholder scan:** none. ✓
**Drift-bug guard:** Task 1 grep asserts no `transition_duration = <int>` (ms) in the new file. ✓
**Completion guard:** Task 2 asserts `grep -c -- "-legacy"` on SKILL.md is 0 and zero `*-legacy.md` files remain — the migration is fully done. ✓
