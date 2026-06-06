# Config-skill migration 3/5 — asset-handling — Implementation Plan

> **For agentic workers:** mechanical verbatim move; single implementer, no TDD (no code, no automated test for skill content).

**Goal:** Move `docs/content-source/asset-handling-legacy.md` into the skill's `references/asset-handling.md`, repoint SKILL.md, delete the legacy file.

**Spec:** `docs/superpowers/specs/2026-06-06-skill-migrate-asset-handling-design.md`
**Worktree:** `.claude/worktrees/skill-asset`, branch `feat/skill-migrate-asset` (off origin/main).
**Commit:** `git -c core.hooksPath=/dev/null commit`.

---

### Task 1: Move content + repoint + delete

- [ ] Copy legacy content over the stub:
  `cp docs/content-source/asset-handling-legacy.md .claude/skills/creating-a-config/references/asset-handling.md`
- [ ] Repoint SKILL.md (all 6 refs):
  `perl -pi -e 's{docs/content-source/asset-handling-legacy\.md}{references/asset-handling.md}g' .claude/skills/creating-a-config/SKILL.md`
- [ ] Delete the legacy file:
  `git rm docs/content-source/asset-handling-legacy.md`
- [ ] Verify:
```bash
cd /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/skill-asset
grep -rn "asset-handling-legacy" . --include='*.md' --include='*.mdx' | grep -v "docs/superpowers/" || echo "OK: no dangling legacy refs"
grep -c "references/asset-handling.md" .claude/skills/creating-a-config/SKILL.md   # expect 6
grep -E "^#" .claude/skills/creating-a-config/references/asset-handling.md          # expect Brand colors / Custom fonts / Images / URLs
test -f docs/content-source/asset-handling-legacy.md && echo "STILL PRESENT" || echo "OK: legacy deleted"
git status --short docs/site/ | grep . && echo "UNEXPECTED site change" || echo "OK: no site change"
```
- [ ] Commit:
```bash
git add .claude/skills/creating-a-config/SKILL.md .claude/skills/creating-a-config/references/asset-handling.md docs/superpowers/
git -c core.hooksPath=/dev/null commit -m "skill: migrate asset-handling into the config skill's references (migration 3/5)"
```
(The `git rm` is already staged.)

---

## Self-Review

**Spec coverage:** move → cp; repoint → perl; delete → git rm; no site change → verified. ✓
**Placeholder scan:** none. ✓
**Consistency:** mirrors #170/#171 exactly. ✓
