# Batch D2 — Cheap High-Value Docs Polish — Design

**Date:** 2026-06-06
**Status:** Approved (brainstorm), pending implementation plan

## Context

Phase 3b **Batch D2** — the **final piece of the whole docs-site effort**. Scope was set in the Batch-D brainstorm: do the *cheap high-value* nice-to-haves from the Phase 3a audit (`docs/superpowers/specs/2026-06-06-docs-audit-findings.md`); **defer** the bigger ones (symptom-first troubleshooting boxes, OptionsTable migration). New branch `feat/docs-d2` off main. Per-page edits parallelized by area, like the audit.

This is the design (the audit findings + the approved cheap-scope filter); no new brainstorm needed.

## Decisions (from brainstorm)

- **IN (cheap high-value):** tutorial time-stamps + "what you'll need" boxes; glosses (`ScaledCanvas`, `TickerMessage`); a light name-the-reader line where a page genuinely mixes audiences or reads ambiguously; small per-page fixes the audit named.
- **DEFERRED (not D2):** symptom-first "if it doesn't work" boxes on widget pages; migrating hand-rolled gif/image/two_row tables to `OptionsTable`.
- Single PR.

## Deliverable

### 1. Tutorial chapters — time/effort stamp + "what you'll need" (rubric #11/#12)

For each of `tutorial/01-setup`, `02-first-config`, `03-multi-widget`, `04-custom-branding`, `05-polish`:
- Add a short **time/effort stamp** near the top (e.g. `**~10 min · no hardware needed**`) — estimate per chapter from its content.
- Add a brief scannable **"What you'll need"** block (the prereqs already in prose, surfaced as a list) where the chapter has prerequisites (e.g. 01: a laptop + `make dev`; 04: the brand font/logo files). Keep it to a few bullets; don't invent prereqs.
- Use the same plain-markdown-list form (not inside an `Aside`) used on the Extending pages, to avoid the prettier list-merge issue.

### 2. Glosses (rubric #3)

- **`ScaledCanvas`** — on `concepts/borders.mdx`, `concepts/display.mdx`, `transitions/sprite.mdx`: gloss on first use (one clause: "the wrapper that expands logical pixels onto a big sign") or link to `concepts/how-rendering-works` / `concepts/display`. For the config-author reader, prefer "big / scaled sign (`default_scale > 1`)" phrasing over the internal class name where the class name isn't needed.
- **`TickerMessage`** — on `widgets/rss_feed.mdx`: gloss ("a single scrolling line") instead of the bare internal type name.

### 3. Name-the-reader (rubric #1) — light touch

Add a one-line reader signpost ONLY where a page genuinely reads ambiguously or mixes audiences — not mechanically on every page. Priority targets (from the audit): concept pages that drop developer terms into config-author content (`borders`, `display`) — a half-line clarifying which paragraphs are for developers. Skip pages where context already makes the reader obvious (most widget pages). YAGNI: a handful, not ~20.

### 4. Small per-page fixes (the audit's concrete nice-to-haves)

- `widgets/index.mdx` — fill the empty "Use when" cell on the `image` row (e.g. "logos / single still graphics"); add a "(plugin)" tag to the `pool` row so the "12 built-in" count reads right.
- `transitions/index.mdx` — reword the `between_sections` "Default `cut`" cell to "Falls back to `default` (itself `cut` by default)" (the audit found it's a half-truth).
- `concepts/color-providers.mdx` — signpost the shimmer GIF from the top GIF's "(shimmer not shown)" caption (a one-line pointer to the dedicated shimmer GIF lower down).
- `widgets/coingecko.mdx` — align the rate-limit guidance phrasing with the fact-pack (the audit found page vs fact-pack disagree).
- `tools/panel-test.mdx` — "a single `~50`-line script" → the file is ~96 lines; change to "~95-line" or "a small script."
- `reference/frame-counters.mdx` — the table labels the constant provider `Constant` but the class is `_ConstantColor`; add a parenthetical or rename the label so a grep finds it.

(These are the concrete, verifiable small fixes; the implementer applies each exactly. Anything fuzzier from the audit is out of D2.)

## Applying the DOCS-STYLE rubric

These are additions/corrections to existing pages; the tech-writer reviewer confirms each edited page still passes the §3 checklist (now including principle #17, no release-history framing) and that the new stamps/boxes/glosses read cleanly and don't duplicate content the page already cross-links.

## The review loop

A tech-writer review over the edited pages (per area). Apply must-fix; re-build/lint. No hobbyist pass needed (these are polish additions).

## Verification

- `make docs-build` + `make docs-lint` clean; all edited pages render and links resolve.
- Each tutorial chapter has a time stamp + (where applicable) a "what you'll need" block.
- `ScaledCanvas`/`TickerMessage` glossed or replaced with reader-friendly phrasing on the named pages.
- The named small per-page fixes are applied (spot-check: `widgets/index` `image` row non-empty; `panel-test` no "~50-line").
- No release-history framing reintroduced (`grep` clean) — D1's principle holds.

## Out of scope (D2)

- Symptom-first troubleshooting boxes on widget pages; OptionsTable migration of hand-rolled tables (deferred per the Batch-D scope decision).
- The deferred config-skill fact-pack migration (separate effort).
- Reader-naming on every page (light touch only).
- Any code change (docs-only).
