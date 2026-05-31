# Docs: restore GFM tables under Astro 6.4 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to
> implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.
>
> **Branch safety:** Before ANY work, run `git branch --show-current`. If it prints
> `main`, stop and ask for a worktree. Expected branch:
> `worktree-fix+docs-mdx-tables-astro64`.

**Status (2026-05-30): DONE.** The plan originally targeted the new
`markdown.processor` API, but execution proved that API **cannot reach MDX** on
the current Starlight (0.39.2, latest, still on `@astrojs/mdx@5.x`). Pivoted to
the legacy `markdown.remarkPlugins: [remarkGfm]` path — the only mechanism that
renders MDX tables here, and one that adds no deprecation warning Starlight
isn't already emitting. Full rationale + deferred migration:
`docs/superpowers/specs/2026-05-30-docs-mdx-gfm-tables-design.md`.

**Goal:** Markdown GFM tables render again on the docs site under Astro 6.4.2,
introducing no new deprecation warning, no downgrade.

**Root cause / context:** See the spec. Astro 6.4 reworked the markdown
pipeline; GFM stopped applying to `.mdx`, so pipe-tables degrade to literal
text. Component (`<OptionsTable>`) tables are unaffected.

**Tech stack:** Astro 6.4.2, Starlight 0.39.2, `@astrojs/markdown-remark` 7.2.0, pnpm.

**Work dir:** `docs/site`. **Build (fast, ~2s, no gifs):** `pnpm exec astro build`.

**Baseline (current `main`, 6.4.2, no fix):** color-providers 0 tables,
config-options 0 tables, two_row 4 tables (component only). Live site matches.

---

> **Pivot note:** Tasks 1–2 below are rewritten to the **as-built** legacy path.
> The original processor-based steps (add `@astrojs/markdown-remark`, set
> `markdown.processor`) were attempted and reverted — see the spec's "Approach
> considered (REJECTED)" for the A/B that ruled them out.

### Task 1: Add `remark-gfm` as a direct dependency — DONE

`remark-gfm` is the GFM remark plugin. It was transitive (`4.0.1`) but not
hoisted, so it must be a direct dep to import it in the config.

**Files:** `docs/site/package.json`, `docs/site/pnpm-lock.yaml` (via install)

- [x] **Step 1:** Add `"remark-gfm": "^4.0.1"` to `dependencies`.
- [x] **Step 2:** `pnpm install` (not `--frozen-lockfile`). Confirmed direct dep
  resolving to `4.0.1`. (`@astrojs/markdown-remark` is NOT added — only needed
  for the rejected processor path.)

### Task 2: Enable GFM via legacy `markdown.remarkPlugins` — DONE

**Files:** `docs/site/astro.config.mjs`

- [x] **Step 1:** `import remarkGfm from "remark-gfm";`
- [x] **Step 2:** Add to `defineConfig({...})`:
  ```js
  markdown: {
    remarkPlugins: [remarkGfm],
  },
  ```
- [x] **Step 3:** Comment explains WHY legacy (MDX/@astrojs/mdx 5.x ignores
  `markdown.processor`; Starlight 0.39.2 is latest) and carries a `DEFERRED:`
  pointer to the spec for the future migration.
- [x] **Step 4:** No `markdown.gfm` flag; no `markdown.processor`; debug
  experiments removed.

### Task 3: Build and verify — tables restored, no NEW deprecation warning — DONE

- [x] **Step 1:** `pnpm exec astro build` — no NEW deprecation. (The
  `markdown.remarkPlugins` notice is pre-existing: Starlight emits it on a plain
  baseline too. No `markdown.gfm` notice.)
- [x] **Step 2:** Table counts — color-providers **2**, config-options **5**,
  two_row **7**.
- [x] **Step 3:** Six-providers confirmed a real `<table>` with `<thead>`/`<tbody>`.

### Task 4: Verify NO collateral regression — DONE

Legacy `markdown.remarkPlugins` merges WITH Starlight's injected plugins (it
does not replace them), so the processor-era risk doesn't apply. Confirmed on
`dist/concepts/color-providers/index.html`:

- [x] **Step 1:** `sl-anchor-link` count == **13** (heading anchors intact).
- [x] **Step 2:** smartypants curly quote `“` count == **13** (typography intact).
- [x] **Step 3:** `dist/widgets/two_row/index.html` — 7 tables (4 `<OptionsTable>`
  component + 3 markdown) and 8 code blocks all render.
- [x] **Step 4 — DECISION GATE:** all signals hold → proceeded to Task 5.

### Task 5: Lint + finalize

- [x] **Step 1:** `prettier --check` passes on `astro.config.mjs` + `package.json`.
- [ ] **Step 2:** `git status` — confirm only `docs/site/astro.config.mjs`,
  `docs/site/package.json`, `docs/site/pnpm-lock.yaml` (+ the spec/plan docs) are
  changed. No stray edits in the main repo checkout.
- [ ] **Step 3:** Commit. Open a PR to `main` (do NOT merge without explicit
  go-ahead). PR body: root cause (Astro 6.4 pipeline rework + Starlight not yet
  6.4-pipeline-ready), why the legacy `remarkPlugins` path (not the processor),
  before/after table counts, verified no-regression signals, and the deferred
  migration.

### Task 6: Post-merge deploy verification (after merge is approved)

- [ ] **Step 1:** `docs-deploy.yml` runs on push to `main`. After it succeeds,
  re-fetch live:
  `cloudflared access curl https://docs.ledticker.dev/concepts/color-providers/ | grep -c '<table'`
  → expect 2. Confirm the six-providers table renders as a table in a browser.

---

## Notes

- Build is fast because demo gifs are a separate `build-demos` step, not part of
  `astro build`. The missing gifs in `dist/` during local verification are
  expected and irrelevant to table rendering.
- Future-proofing tripwire (rendered-HTML table assertion in CI) is out of scope
  — noted as a follow-up in the spec.
