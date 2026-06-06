# Batch D1 — Omit Release-History Framing — Implementation Plan

> **For agentic workers:** Mix of precise edits (controller) + one rewording implementer + a tech-writer review.

**Goal:** Remove release-history framing from the docs site, fix `hold_seconds`→`hold_time` in the skill's content-source, and add the "no release-history framing" DOCS-STYLE principle.

**Source spec:** `docs/superpowers/specs/2026-06-06-docs-d1-omit-legacy-framing-design.md`
**Worktree:** `.claude/worktrees/docs-d1`, branch `feat/docs-d1`. **Commit:** `git -c core.hooksPath=/dev/null commit`.

---

### Task 1: Add the DOCS-STYLE principle (#17) + checklist clause

**File:** `docs/DOCS-STYLE.md`

- [ ] **Step 1:** After principle 16 (line 40) and before the `### Do NOT copy (from Adafruit)` heading (line 42), add:
```markdown
17. **No release-history framing.** led-ticker is unreleased — don't describe anything as "legacy", "deprecated", "backward-compatible", "no longer accepted", or "still works as before." There's no prior version to preserve, so document the current way only.
```
(Keep the blank line before `### Do NOT copy`.)

- [ ] **Step 2:** Amend the §3 checklist tone item (line 62) from:
```markdown
- [ ] Tone consistent + matter-of-fact (no upsell, no breathless marketing).
```
to:
```markdown
- [ ] Tone consistent + matter-of-fact (no upsell, no breathless marketing, no release-history framing).
```

- [ ] **Step 3: Commit** (DOCS-STYLE is outside the site build):
```bash
cd /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/docs-d1
git add docs/DOCS-STYLE.md
git -c core.hooksPath=/dev/null commit -m "docs: add the 'no release-history framing' principle to DOCS-STYLE (D1)"
```

---

### Task 2: Strip release-history framing from the docs site (rewording — implementer)

**Files (reword in place; keep facts correct, omit history):**
- `docs/site/src/content/docs/pitfalls.mdx` — Rule 33 + Rule 35 (`mode = "gif"`): keep the rules, drop "the original way / preserved for backward compatibility / undocumented and may be removed in a future release" and the "legacy" adjective. Neutral: prefer `mode = "swap"` with a `gif` widget (full section feature set); `mode = "gif"` is a narrower direct-play form; switch by changing `mode = "gif"` → `mode = "swap"`.
- `docs/site/src/content/docs/concepts/sections-and-modes.mdx` — retitle `## Legacy: mode = "gif"` (e.g. `## The `mode = "gif"` shorthand`); remove "Preserved for backward compatibility" + "Existing `mode = "gif"` configs continue to work"; present it as a simpler alternative.
- `docs/site/src/content/docs/tools/validate.mdx` — the two "legacy mode" mentions (~L181 table row + ~L210 prose): reword to neutral (`mode = "gif"` → prefer `mode = "swap"`).
- `docs/site/src/content/docs/widgets/weather.mdx` (~L33) — replace "`message =` … is no longer accepted" with "Set the content with `text =`."
- `docs/site/src/content/docs/widgets/message.mdx` + `countdown.mdx` (~L26/L30) — drop "existing configs with `message =` … continue to work"; document `text =` as the way (keep "`message =` is also accepted" only if you want to note the alias — no history).
- `docs/site/src/content/docs/widgets/gif.mdx` (~L261) — "play_count ≥ 1 still works exactly as before" → "`play_count ≥ 1` plays the exact count regardless of `hold_time`."

- [ ] **Implementer step:** read each page, reword per the above (document the current way, omit history; facts must stay correct — spot-check `mode = "gif"`/`play_count`/`text =` against `src/` if unsure). Then:
```bash
cd /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/docs-d1
make docs-format && make docs-build; echo "BUILD=$?"; make docs-lint; echo "LINT=$?"
grep -riE "\blegacy\b|backward[- ]?compat|deprecat|no longer (accepted|valid|supported)|preserved for|continue[s]? to work|still works.*as before|kept for compat" docs/site/src/content/docs/ && echo "STILL HAS history framing" || echo "history framing gone"
git add docs/site/src/content/docs
git -c core.hooksPath=/dev/null commit -m "docs: drop release-history (legacy/backward-compat) framing site-wide (D1)

The project is unreleased; document the current way only. Reword mode=\"gif\"
rules, sections-and-modes, validate, and the message=/play_count notes without
legacy/no-longer-accepted/still-works framing."
```
Expected: BUILD=0, LINT=0, "history framing gone".

---

### Task 3: Content-source `hold_seconds` → `hold_time`

**Files:** `docs/content-source/decision-rules-legacy.md`, `docs/content-source/widgets-legacy.md`, `docs/content-source/asset-handling-legacy.md`.

- [ ] **Step 1:** Replace every `hold_seconds` with `hold_time` across the three files (8 occurrences: decision-rules L93/97/101, widgets L225/235/239, asset-handling L91/93). These are the `creating-a-config` skill's knowledge base; `hold_seconds` is not a real field (it's `hold_time`), so left as-is the skill would emit configs that fail validation. (Pure field-name replacement; the surrounding prose stays.)
- [ ] **Step 2: Verify + commit:**
```bash
cd /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/docs-d1
grep -rn "hold_seconds" docs/content-source/ && echo "STILL hold_seconds" || echo "content-source clean"
git add docs/content-source/
git -c core.hooksPath=/dev/null commit -m "docs: fix hold_seconds -> hold_time in the config-skill content-source (D1)

hold_seconds is not a real field; the creating-a-config skill reads these files
and would otherwise generate configs that fail validation."
```
Expected: "content-source clean".

---

### Task 4: Tech-writer review + final verification

- [ ] **Step 1:** Tech-writer reviewer over the reworded site pages — confirm the rewordings read cleanly, no history framing remains, and the facts (mode/play_count/text) are still correct + the §3 checklist still passes. Apply must-fix; re-build/lint.
- [ ] **Step 2: Final verification:**
```bash
cd /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/docs-d1
make docs-build; echo "BUILD=$?"; make docs-lint; echo "LINT=$?"
grep -riE "\blegacy\b|backward[- ]?compat|deprecat|no longer (accepted|valid)|continue[s]? to work|still works.*as before" docs/site/src/content/docs/ || echo "site framing clean"
grep -rn "hold_seconds" docs/content-source/ docs/site/ || echo "hold_seconds clean everywhere"
```
Expected: BUILD=0, LINT=0; both grep guards clean.
- [ ] **Step 3:** Commit any review fixes.

---

## Self-Review

**1. Spec coverage:** Strip framing (site) → Task 2. content-source hold_seconds → Task 3. DOCS-STYLE principle + checklist → Task 1. Review + verify → Task 4. ✓ Out of scope (D2 polish, removing mode=gif, renaming *-legacy files) → respected. ✓

**2. Placeholder scan:** No TBD/TODO; the rewording task gives intent + exact targets (implementer phrases the prose, facts pinned). ✓

**3. Consistency:** DOCS-STYLE insertion points (after L40, amend L62) verified. The content-source occurrences (8) match Task 3. The site grep guard matches the targets in Task 2. The `mode = "gif"` rule + validator stay (only framing changes), consistent across spec + plan. ✓
