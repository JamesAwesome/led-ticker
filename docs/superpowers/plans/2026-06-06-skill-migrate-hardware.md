# Migration Sub-piece 2: hardware-guide → skill references — Plan

> Controller-executed (mechanical move, mirrors sub-piece 1). Checkbox steps.

**Goal:** Move `hardware-guide-legacy.md` into the skill's `references/hardware-guide.md`, repoint `SKILL.md`'s 3 references, delete the legacy file. No content-source fact-pack.

**Source spec:** `docs/superpowers/specs/2026-06-06-skill-migrate-hardware-design.md`
**Worktree:** `.claude/worktrees/skill-migrate`, branch `feat/skill-migrate`. **Commit:** `git -c core.hooksPath=/dev/null commit`.

---

### Task 1: Move + repoint + delete

- [ ] **Step 1: Move content** (overwrite the stub with the full legacy content):
  `cp docs/content-source/hardware-guide-legacy.md .claude/skills/creating-a-config/references/hardware-guide.md`
- [ ] **Step 2: Repoint SKILL.md** (3 occurrences):
  `perl -pi -e 's{docs/content-source/hardware-guide-legacy\.md}{references/hardware-guide.md}g' .claude/skills/creating-a-config/SKILL.md`
- [ ] **Step 3: Delete legacy:** `git rm docs/content-source/hardware-guide-legacy.md`
- [ ] **Step 4: Verify** — no dangling `hardware-guide-legacy` refs (outside `docs/superpowers/`); `references/hardware-guide.md` contains "At-a-glance comparison" + "Refresh tuning"; `SKILL.md` has 3 `references/hardware-guide.md`; legacy gone; no `docs/site/`/`src/` change.
- [ ] **Step 5: Commit:**
  `git add .claude/skills/creating-a-config/references/hardware-guide.md .claude/skills/creating-a-config/SKILL.md` then commit (the `git rm` already staged the deletion) with message:
  `skill: move hardware-guide into the config skill's references; drop the legacy guide`

---

## Self-Review

Spec coverage: move → 1, repoint 3 → 2, delete → 3, verify → 4. ✓ No placeholders; commands concrete. ✓ The `perl` targets the exact path the 3 refs use; `cp` overwrites the stub with full content; `git rm`+`git add` stage deletion + the two edits. Consistent with sub-piece 1. ✓
