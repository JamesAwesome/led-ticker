# Config-skill migration 4/5 — widgets — Implementation Plan

> **For agentic workers:** content restructure (not a verbatim move). No code, no automated test for skill content.

**Goal:** Replace the skill's dependency on the stale `widgets-legacy.md` with (a) a new `references/widget-selection.md` for selection knowledge and (b) the existing per-page fact-packs for option details; delete the legacy file. Side effect: the skill stops emitting the drift-bug fields `gif_loops`/`hold_seconds`.

**Spec:** `docs/superpowers/specs/2026-06-06-skill-migrate-widgets-design.md`
**Worktree:** `.claude/worktrees/skill-widgets`, branch `feat/skill-migrate-widgets` (off origin/main).
**Commit:** `git -c core.hooksPath=/dev/null commit`; push/PR also need `-c core.hooksPath=/dev/null` (pre-commit framework absent in worktree).

---

### Task 1: Author `references/widget-selection.md`

**File:** Create `.claude/skills/creating-a-config/references/widget-selection.md`.

- [ ] Write a "Widget Selection Guide" with a header that says: this guide is for *choosing* widgets; for each widget's option/parameter details, read `docs/content-source/widgets/<type>.md`.
- [ ] One entry per core widget (12): `message`, `countdown`, `two_row`, `weather`, `rss_feed`, `mlb`, `mlb_standings`, `gif`, `image`, `crypto.coinbase`, `crypto.coingecko`, `crypto.etherscan`. Each entry = **Purpose** (one line) + **When to use** (the legacy bullets) + **Selection notes** (only selection-bearing gotchas — drop param-mechanics gotchas). Source the wording from `widgets-legacy.md` but DO NOT copy its param lists, and DO NOT carry `gif_loops` or `hold_seconds`.
- [ ] Add a final one-line `pool` (plugin) pointer → its fact-pack `docs/content-source/widgets/pool.md`.
- [ ] Verify the new file: `grep -E "gif_loops|hold_seconds" .claude/skills/creating-a-config/references/widget-selection.md && echo "BUG CARRIED — FIX" || echo "OK: no drift bugs"` (expect OK).

### Task 2: Repoint SKILL.md + delete legacy

**File:** Modify `.claude/skills/creating-a-config/SKILL.md`; delete `docs/content-source/widgets-legacy.md`.

- [ ] Phase 2 load line (~101): replace `docs/content-source/widgets-legacy.md` with `references/widget-selection.md`, and append to that step an instruction: "for each chosen widget's options, read its fact-pack `docs/content-source/widgets/<type>.md`."
- [ ] `add` load line (~150): same replacement + same fact-pack instruction.
- [ ] `add` multi-select line (~153): "multi-select from `references/widget-selection.md`".
- [ ] `refine` load line (~165): replace `widgets-legacy.md` with `references/widget-selection.md`.
- [ ] `git rm docs/content-source/widgets-legacy.md`.
- [ ] Verify:
```bash
cd /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/skill-widgets
grep -rn "widgets-legacy" . --include='*.md' --include='*.mdx' | grep -v "docs/superpowers/" || echo "OK: no dangling legacy refs"
grep -c "references/widget-selection.md" .claude/skills/creating-a-config/SKILL.md   # expect >=4
grep -c "docs/content-source/widgets/" .claude/skills/creating-a-config/SKILL.md     # expect >=2 (fact-pack dir refs)
grep -c "widgets-legacy" .claude/skills/creating-a-config/SKILL.md                   # expect 0
test -f docs/content-source/widgets-legacy.md && echo "STILL PRESENT" || echo "OK: legacy deleted"
git status --short docs/site/ | grep . && echo "UNEXPECTED site change" || echo "OK: no site change"
```

### Task 3: Build/lint + commit

- [ ] `make docs-lint` (legacy deletion + spec/plan under docs/ trigger docs CI; expect clean).
- [ ] Commit:
```bash
git add .claude/skills/creating-a-config/SKILL.md .claude/skills/creating-a-config/references/widget-selection.md docs/superpowers/
git -c core.hooksPath=/dev/null commit -m "skill: migrate widgets onto fact-packs + selection guide (migration 4/5)"
```
(The `git rm` is already staged.)

---

## Self-Review

**Spec coverage:** new selection guide → Task 1; repoint + delete → Task 2; verify/commit → Task 3. ✓
**Placeholder scan:** none. ✓
**Drift-bug guard:** Task 1 grep asserts no `gif_loops`/`hold_seconds` in the new file. ✓
**Consistency:** SKILL.md points at `references/widget-selection.md` (selection) + `docs/content-source/widgets/<type>.md` (options), legacy gone. ✓
