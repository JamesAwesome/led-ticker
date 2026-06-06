# Migration Sub-piece 1: decision-rules → skill references — Plan

> Controller-executed (mechanical move). Checkbox steps.

**Goal:** Move the 21 decision-rules into the skill's `references/decision-rules.md`, repoint `SKILL.md`'s 9 references, delete `decision-rules-legacy.md`.

**Source spec:** `docs/superpowers/specs/2026-06-06-skill-migrate-decision-rules-design.md`
**Worktree:** `.claude/worktrees/skill-migrate`, branch `feat/skill-migrate`. **Commit:** `git -c core.hooksPath=/dev/null commit`.

---

### Task 1: Move content + repoint + delete

- [ ] **Step 1: Move the rule content into the skill reference** (overwrite the 1-line stub with the full legacy content):
```bash
cd /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/skill-migrate
cp docs/content-source/decision-rules-legacy.md .claude/skills/creating-a-config/references/decision-rules.md
```

- [ ] **Step 2: Repoint all SKILL.md references** (skill-relative path, 9 occurrences):
```bash
cd /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/skill-migrate
perl -pi -e 's{docs/content-source/decision-rules-legacy\.md}{references/decision-rules.md}g' .claude/skills/creating-a-config/SKILL.md
```

- [ ] **Step 3: Delete the legacy file:**
```bash
cd /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/skill-migrate
git rm docs/content-source/decision-rules-legacy.md
```

- [ ] **Step 4: Verify:**
```bash
cd /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/skill-migrate
echo "--- no dangling refs (expect empty) ---"
grep -rn "decision-rules-legacy" . 2>/dev/null | grep -v "/.venv/\|/node_modules/\|/dist/\|docs/superpowers/" || echo "no dangling decision-rules-legacy refs"
echo "--- reference file has all 21 rules (expect 21) ---"
grep -c "^## Rule " .claude/skills/creating-a-config/references/decision-rules.md
echo "--- SKILL.md now points at references/decision-rules.md (expect 9) ---"
grep -c "references/decision-rules.md" .claude/skills/creating-a-config/SKILL.md
echo "--- legacy file gone (expect: not found) ---"
test -e docs/content-source/decision-rules-legacy.md && echo "STILL EXISTS" || echo "legacy file deleted"
echo "--- only skill + deleted legacy changed; nothing under docs/site or src ---"
git status --short | grep -E "docs/site/|src/" && echo "UNEXPECTED site/src change" || echo "no site/src change"
```
Expected: no dangling refs; rule count `21`; SKILL.md ref count `9`; "legacy file deleted"; no site/src change.

- [ ] **Step 5: Commit:**
```bash
cd /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/skill-migrate
git add .claude/skills/creating-a-config/references/decision-rules.md .claude/skills/creating-a-config/SKILL.md docs/content-source/decision-rules-legacy.md
git -c core.hooksPath=/dev/null commit -m "skill: move decision-rules into the config skill's references; drop the legacy guide

The 21 validation rules are skill-procedural (the config wizard's lint
checklist), not a docs-site fact-pack. Move them from
docs/content-source/decision-rules-legacy.md into the skill's own
references/decision-rules.md, repoint SKILL.md's 9 references, and delete the
legacy file. First sub-piece of the config-skill fact-pack migration."
```

---

## Self-Review

**1. Spec coverage:** Move content → Step 1. Repoint 9 refs → Step 2. Delete legacy → Step 3. Verify (no dangling, 21 rules, 9 refs, deleted, no site/src) → Step 4. ✓

**2. Placeholder scan:** No TBD/TODO; all commands concrete. ✓

**3. Consistency:** The `perl` replaces the exact path the 9 references use (`docs/content-source/decision-rules-legacy.md`), including the inline-citation occurrences (190, 198). `cp` overwrites the stub with the full content (so the rule list is complete, not appended). `git rm` + `git add` stage the deletion + the two edits. The verification rule-count (21) and ref-count (9) match the spec's verified numbers. ✓
