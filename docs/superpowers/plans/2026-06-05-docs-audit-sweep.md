# Docs Audit Sweep (Phase 3a) Implementation Plan

> **For agentic workers:** This plan is executed by the **controller directly** (dispatching review agents + aggregating), NOT via subagent-driven-development — the audit agents ARE the work. Steps use checkbox (`- [ ]`) tracking.

**Goal:** Produce one prioritized findings report auditing the 47 pre-rubric docs-site pages against `docs/DOCS-STYLE.md`. **No page is edited.**

**Architecture:** 8 area batches → one technical-writer reviewer agent per batch (run concurrently) → each returns structured per-page findings → controller aggregates into `docs/superpowers/specs/2026-06-06-docs-audit-findings.md` and commits.

**Source spec:** `docs/superpowers/specs/2026-06-05-docs-audit-sweep-design.md`

**Worktree:** `.claude/worktrees/docs-audit`, branch `feat/docs-audit`. **Commit convention:** `git -c core.hooksPath=/dev/null commit`.

**Page base path (absolute):** `/Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/docs-audit/docs/site/src/content/docs/`
**Rubric (absolute):** `/Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/docs-audit/docs/DOCS-STYLE.md`

### The 8 batches (47 pages, all dated ≤ 2026-06-03)

1. **Widgets A** — `widgets/message.mdx`, `widgets/countdown.mdx`, `widgets/two_row.mdx`, `widgets/weather.mdx`, `widgets/gif.mdx`, `widgets/image.mdx`, `widgets/index.mdx`
2. **Widgets B** — `widgets/mlb.mdx`, `widgets/mlb_standings.mdx`, `widgets/coinbase.mdx`, `widgets/coingecko.mdx`, `widgets/etherscan.mdx`, `widgets/rss_feed.mdx`, `widgets/pool.mdx`
3. **Transitions** — `transitions/index.mdx`, `transitions/push.mdx`, `transitions/wipe.mdx`, `transitions/sprite.mdx`, `transitions/special.mdx`
4. **Concepts** — `concepts/animations.mdx`, `concepts/borders.mdx`, `concepts/color-providers.mdx`, `concepts/display.mdx`, `concepts/fonts.mdx`, `concepts/sections-and-modes.mdx`, `concepts/busy-light.mdx`
5. **Tools** — `tools/creating-a-config.mdx`, `tools/validate.mdx`, `tools/gif-plan.mdx`, `tools/panel-test.mdx`, `tools/render-demo.mdx`
6. **Reference** — `reference/config-options.mdx`, `reference/cli.mdx`, `reference/frame-counters.mdx`
7. **Hardware** — `hardware/smallsign.mdx`, `hardware/bigsign.mdx`, `hardware/longboi.mdx`, `hardware/building-your-own.mdx`
8. **Tutorial + top-level** — `tutorial/01-setup.mdx`, `tutorial/02-first-config.mdx`, `tutorial/03-multi-widget.mdx`, `tutorial/04-custom-branding.mdx`, `tutorial/05-polish.mdx`, `getting-started.mdx`, `pitfalls.mdx`, `showcase.mdx`, `assets/emoji.mdx`

---

### Task 1: Run the 8 reviewer agents (parallel)

- [ ] **Step 1: Dispatch all 8 agents in one message** (general-purpose subagents), each with the prompt template below, filling `{BATCH_NAME}` and `{PAGE_LIST}` (absolute paths) per batch.

**Reviewer agent prompt template:**

```
You are a technical-writer auditor for the led-ticker docs site. Audit a batch of EXISTING pages against the project's style rubric and return structured findings. Do NOT edit any files — this is a read-only audit.

## Read first
The rubric (authoritative): `/Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/docs-audit/docs/DOCS-STYLE.md` — read all of it, especially §1 (audience/voice), §2 (16 principles), §3 (the 10-item checklist).

## Pages to audit (batch: {BATCH_NAME})
{PAGE_LIST}

## How to audit each page
For EACH page, read it fully (and follow/spot-check its internal links and commands where you can — you have read/grep/bash tools and may check source under src/ or config/ if a claim looks wrong). Apply the §3 checklist. Use this N/A logic (consistent with how the site was built):
- Items #11 "what you'll need" box, #12 time/effort stamp, #13 local "if it doesn't work" troubleshooting are TUTORIAL/TASK-page patterns — treat them N/A for **reference** pages (reference/*) and **concept** pages (concepts/*), and for index/landing pages.
- Visual-payoff (#7) is N/A only when there is genuinely nothing visual to show.

Severity:
- **must-fix** = misleads or blocks a reader: a broken or wrong command, a broken internal link, an unexplained jargon wall, missing prerequisites on a task page, a factual error / stale default, internal inconsistency, or missing visual payoff on a visibly-visual feature.
- **nice-to-have** = real but non-blocking polish.

## Output format — return EXACTLY this markdown (one block per page, nothing else)
For each page:

### <page path relative to docs/, e.g. widgets/message.mdx>
**Grade:** Good | Minor gaps | Needs work
**Scorecard:** reader-named=PASS/ISSUE/N/A · payoff/visual=… · jargon-glossed=… · complete-examples/concrete-commands=… · internal-consistency=… · code-bound-to-source=… · local-troubleshooting/blameless=… · cross-links/next-step-CTA=… · builds/lint=ASSUME-PASS · tone=…
**Must-fix:**
- <issue>: "<quoted offending text>" → <concrete suggested fix>   (or "none")
**Nice-to-have:**
- <issue> → <suggested fix>   (or "none")
**Accuracy / links / drift:**
- <any command that looks wrong, stale default, broken link, or code-drift you spotted, with specifics>   (or "none spotted")

Be specific and quote exact text. Be rigorous but fair — these pages predate the rubric, so some gaps are expected; focus on what genuinely hurts a reader. Do NOT invent issues to seem thorough. Your entire final message is the structured findings for your batch (it is consumed by the controller).
```

- [ ] **Step 2: Collect all 8 agents' structured outputs.** If any agent returns malformed output or skips a page, re-dispatch that batch.

---

### Task 2: Aggregate + commit the findings report

- [ ] **Step 1: Write the aggregated report** to `docs/superpowers/specs/2026-06-06-docs-audit-findings.md` with this structure:

```markdown
# Docs Audit Findings (Phase 3a)

**Date:** 2026-06-06
**Scope:** 47 pre-rubric docs-site pages audited against docs/DOCS-STYLE.md. Read-only — no pages edited. (The ~13 pages built to the rubric this effort were skipped.)

## Executive summary
- <cross-cutting themes: e.g. "X pages have stale/unrunnable commands", "Y widget pages lack a local troubleshooting box", "Z broken internal links">
- **Worst-offending pages (Needs work):** <list>
- **Counts:** <N must-fix across M pages; P nice-to-have>

## Suggested fix batches (for the review gate)
A proposed grouping of the must-fix work into PR-sized batches the user can adjust:
1. <batch> — <pages/issues>
2. ...

## Findings by area
### Widgets
#### widgets/message.mdx — Grade: <...>
<scorecard, must-fix, nice-to-have, accuracy/links — carried from the agent output>
... (every in-scope page, grouped by area)
```

Carry each page's findings verbatim from its agent (lightly normalized). Sort the per-area sections so **Needs work** pages come first within each area. The executive summary + suggested fix batches are the controller's synthesis across all findings.

- [ ] **Step 2: Verify coverage** — every one of the 47 pages appears in the report with a grade:

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/docs-audit
for p in widgets/message widgets/countdown widgets/two_row widgets/weather widgets/gif widgets/image widgets/index \
         widgets/mlb widgets/mlb_standings widgets/coinbase widgets/coingecko widgets/etherscan widgets/rss_feed widgets/pool \
         transitions/index transitions/push transitions/wipe transitions/sprite transitions/special \
         concepts/animations concepts/borders concepts/color-providers concepts/display concepts/fonts concepts/sections-and-modes concepts/busy-light \
         tools/creating-a-config tools/validate tools/gif-plan tools/panel-test tools/render-demo \
         reference/config-options reference/cli reference/frame-counters \
         hardware/smallsign hardware/bigsign hardware/longboi hardware/building-your-own \
         tutorial/01-setup tutorial/02-first-config tutorial/03-multi-widget tutorial/04-custom-branding tutorial/05-polish \
         getting-started pitfalls showcase assets/emoji; do
  grep -q "$p.mdx" docs/superpowers/specs/2026-06-06-docs-audit-findings.md || echo "MISSING FROM REPORT: $p"
done; echo "coverage check done (no MISSING lines = all 47 covered)"
```
Expected: no `MISSING` lines.

- [ ] **Step 3: Confirm no docs page was edited** (read-only guarantee):

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/docs-audit
git status --short docs/site/   # expect EMPTY (no site pages touched)
```
Expected: empty output.

- [ ] **Step 4: Commit the report**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/docs-audit
git add docs/superpowers/specs/2026-06-06-docs-audit-findings.md docs/superpowers/plans/2026-06-05-docs-audit-sweep.md
git -c core.hooksPath=/dev/null commit -m "docs: audit findings for the 47 pre-rubric docs pages (Phase 3a)

Read-only audit against docs/DOCS-STYLE.md via 8 per-area tech-writer passes.
Prioritized findings (must-fix vs nice-to-have) + suggested fix batches for the
review gate. No docs-site page edited."
```

---

### Task 3: Present the report at the review gate

- [ ] Surface the executive summary + suggested fix batches to the user. The user decides the fix scope and ordering. The fix batches (Phase 3b+) each become their own spec→plan→PR with the normal implementer + tech-writer review loop. **Do not edit any page until the user picks the fix scope.**

---

## Self-Review

**1. Spec coverage:** Audit-only (no edits) → Tasks 1–2 + Step 3 guard. ✓  8 area batches, ~45–47 pages → batch list (47). ✓  Reviewer returns scorecard + severity-tagged issues + accuracy/links + grade → agent prompt output format. ✓  Aggregated report at the specified path → Task 2 Step 1. ✓  Review gate, fixes out of scope → Task 3. ✓  Skips the rubric-built pages → batch list excludes all 2026-06-04+ pages. ✓

**2. Placeholder scan:** The `{BATCH_NAME}`/`{PAGE_LIST}` and `<...>` markers are fill-in slots for the agent prompt / report template (the controller fills them at dispatch/aggregation), not plan placeholders. No TBD/TODO in the plan's own steps.

**3. Consistency:** The 47 pages in the coverage check (Task 2 Step 2) exactly match the 8 batch lists. Cutoff is consistent (≤ 2026-06-03 audited; 2026-06-04+ skipped). The report path is identical across spec, plan, and the commit. N/A logic in the agent prompt matches what the effort used for reference/concept pages.
