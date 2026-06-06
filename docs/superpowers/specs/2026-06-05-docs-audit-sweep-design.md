# Docs Audit Sweep — Design (Phase 3a)

**Date:** 2026-06-05
**Status:** Approved (brainstorm), pending implementation plan

## Context

**Phase 3** (final phase) of the docs-site effort — the original "deep-dive review of the docs" thrust. Phases 0–2 are shipped (style guide, home page, the full technical/API docs incl. the Extending section + how-it-works). Phase 3 is **fundamentally different**: it AUDITS the existing pages and fixes what's weak, rather than writing new ones.

Phase 3 is decomposed (per the brainstorm):
- **3a (this spec): the audit sweep** — a read-only pass that produces ONE prioritized findings report. **No page is edited.**
- **Review gate:** the user reads the report and decides the fix scope.
- **3b+ (later, separate specs/plans): fix batches** — driven by the user's prioritization, each its own PR with the tech-writer review loop.

## Audit scope

The **~45 pre-rubric pages** — those last touched before `docs/DOCS-STYLE.md` existed (2026-06-04). The ~15 pages built to the rubric this effort (home/index, getting-started's recent state, the 4 Extending pages, api-reference, how-rendering-works, plugins overview/available, tutorial/01-setup if recent) are **skipped** — they already passed tech-writer + hobbyist review. (The plan confirms the exact include/skip list from git dates; a page touched after the DOCS-STYLE commit is skipped.)

## Decisions (from brainstorm)

- **Structure:** audit → review → fix-batches. This piece is the audit only.
- **Parallel by area:** ~8 batches, one technical-writer reviewer agent each, run concurrently.
- **Deliverable:** one committed, prioritized findings report; **not** edits.
- **Fix scope is decided AFTER the audit** (the report informs it) — out of scope here.

## Deliverable

### The audit batches (~8, by area)

1. **Widgets A** — `message`, `countdown`, `two_row`, `weather`, `gif`, `image`
2. **Widgets B** — `mlb`, `mlb_standings`, `coinbase`, `coingecko`, `etherscan`, `rss_feed`, `widgets/index`
3. **Transitions** — `index`, `push`, `wipe`, `sprite`, `special`
4. **Concepts (pre-rubric)** — `animations`, `borders`, `color-providers`, `display`, `fonts`, `sections-and-modes`, `busy-light`
5. **Tools** — `creating-a-config`, `validate`, `gif-plan`, `panel-test`, `render-demo`
6. **Reference** — `config-options`, `cli`, `frame-counters`
7. **Hardware** — `smallsign`, `bigsign`, `longboi`, `building-your-own`
8. **Tutorial + top-level** — `tutorial/02`–`05`, `getting-started`, `pitfalls`, `showcase`, `assets/emoji`

(The plan pins the final per-batch page list from the git-date check; ~45 pages total.)

### Each reviewer agent returns (structured, per page in its batch)

- **Rubric scorecard** — the `docs/DOCS-STYLE.md` §3 checklist (10 items) → **PASS / ISSUE / N/A**. The reviewer applies the same N/A logic used all effort: the tutorial/task-page items (#11 "what you'll need", #12 time stamp, #13 local troubleshooting) are **N/A for reference and concept pages**; visual-payoff (#7) is N/A where there's genuinely nothing visual.
- **Issues** — each tagged **must-fix** vs **nice-to-have**, quoting the offending text and giving a concrete suggested fix. Must-fix = misleads or blocks a reader (broken/wrong command, unexplained jargon wall, missing prerequisites, broken internal link, factual error, missing visual payoff on a visibly-visual feature, internal inconsistency).
- **Accuracy / drift / links** — the agent flags commands that look wrong, defaults that look stale, broken internal links, or code-drift it can spot. (Agents have read + search tools; for accuracy on a specific claim they may check the relevant source/config, but deep verification of every claim is out of scope — flag suspicions for the fix phase to confirm.)
- **Overall per-page grade** — a one-word health rating (e.g. Good / Minor gaps / Needs work) so the report can rank pages.

### The aggregated report

I (the controller) merge all batch outputs into ONE report committed at:
`docs/superpowers/specs/2026-06-06-docs-audit-findings.md`

Structure:
- **Executive summary** — cross-cutting themes (e.g. "N widgets lack a local troubleshooting box"; "M pages have stale commands"), the worst-offending pages, rough counts of must-fix vs nice-to-have.
- **Per-area findings** — each page's grade + its must-fix list then nice-to-haves, with the suggested fix for each.
- **Suggested fix batches** — a proposed grouping of the must-fix work into PR-sized batches (the user adjusts at the review gate).

## Applying the DOCS-STYLE rubric

The rubric IS the audit instrument — agents score each page against `docs/DOCS-STYLE.md` §3. This sub-part does not itself produce a docs page, so the rubric isn't applied to an output page; it's applied *by* the agents *to* the existing pages.

## The review loop / gate

There is no per-task tech-writer re-review in 3a (the agents ARE the tech-writers). After the report is committed, the **user reviews it** and decides the fix scope and ordering. The fix batches (3b+) each run the normal implementer + tech-writer review loop.

## Verification

- The findings report exists at `docs/superpowers/specs/2026-06-06-docs-audit-findings.md`, covers every in-scope page (each appears with a grade), and tags issues by severity.
- No docs-site page is modified in this piece (`git status` shows only the new report + the spec/plan docs).
- The report's internal-link/command findings are specific (page + quoted text + suggested fix), so the fix phase can act on them directly.

## Out of scope (Phase 3a)

- **Any edit to a docs-site page** — fixes are 3b+.
- Deep verification of every factual claim — agents flag suspicions; the fix phase confirms.
- Re-auditing the ~15 rubric-built pages (skipped).
- Deciding the fix scope — that's the user's call at the review gate.
