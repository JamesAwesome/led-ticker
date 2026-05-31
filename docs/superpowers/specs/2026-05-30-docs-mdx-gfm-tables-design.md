# Docs: restore GFM tables under Astro 6.4 markdown pipeline — Design Spec

**Date:** 2026-05-30
**Status:** Implemented — legacy `markdown.remarkPlugins` path (the new
`markdown.processor` API proved unviable with current Starlight; see
"Outcome" and "Deferred work" below).
**Author:** James + Claude (debugging session)

## Summary

Markdown pipe-tables stopped rendering on the deployed docs site. Every GFM
table authored in markdown (e.g. the "six providers" table on
`concepts/color-providers/`) degrades to literal `| col | col |` text inside a
`<p>`. Tables emitted by Astro components (`<OptionsTable>`) are unaffected.

Root cause: Dependabot bumped **Astro `6.3.7 → 6.4.2`** (merged to `main`,
deployed 2026-05-31, commit `2d334677`). Astro 6.4 [reworked the Markdown
pipeline](https://astro.build/blog/astro-640/) — a pluggable `markdown.processor`
and the deprecation of top-level `markdown.gfm` / `remarkPlugins` / etc. in
favor of passing them to `unified({...})`. Under the new wiring, GFM is no
longer applied to the project's `.mdx` pages, so tables (a GFM extension) stop
parsing. The underlying GFM packages (`remark-gfm@4.0.1`,
`mdast-util-gfm-table@2.0.0`, `micromark-extension-gfm-table@2.1.1`) are
byte-identical across 6.3.7 and 6.4.2 — the break is purely in Astro's pipeline
wiring, not the table parser.

The fix is to opt into the new pipeline API and explicitly enable GFM via the
`markdown.processor` option, rather than re-enabling the deprecated
`markdown.gfm` flag.

## Evidence (already established)

Reproduced in a worktree off `origin/main` (Astro 6.4.2), `astro build`:

| Page | 6.3.7 (local, pre-bump) | 6.4.2 (deployed + repro) | Live site |
| --- | --- | --- | --- |
| `concepts/color-providers` | 2 `<table>` | **0** (raw text) | **0** |
| `reference/config-options` | 4 `<table>` | **0** | **0** |
| `widgets/two_row` | 7 `<table>` | 4 | 4 |

The 4 surviving `two_row` tables are all `<OptionsTable>` component output
(`Option | Type | Default | Description` headers). Every markdown-authored
pipe-table (`Field | Type | Default | Meaning`, the six-providers table, etc.)
breaks. So the regression is blanket across markdown tables; component tables
are a red herring.

Empirically, `markdown: { gfm: true }` restores all tables (color-providers
2, config-options 5) — confirming GFM-off is the mechanism — but emits a build
deprecation warning and is slated for removal in a future Astro major.

## Goals

- Markdown GFM tables render as `<table>` on every docs page again.
- Introduce **no new** deprecation warning. (Goal originally read "use the
  non-deprecated processor API" — revised once testing proved that API can't
  reach MDX on the current Starlight; see Approach. The achievable goal is "add
  no warning Starlight doesn't already emit," which the chosen fix meets.)
- No regression to other markdown features Starlight injects: heading anchor
  links, smartypants typographic quotes, autolinks, other GFM (strikethrough,
  task lists), syntax-highlit code blocks, `<OptionsTable>` output.
- Stay on Astro 6.4.2 (fix-forward; no downgrade pin).

## Non-goals

- No downgrade of Astro back to 6.3.x.
- No Starlight version bump in this PR (0.39.2 is already the latest release;
  there is nothing newer to bump to — see Approach).
- No content edits to the `.mdx` tables themselves (the markdown is valid GFM;
  the parser config is the defect).
- No switch to the optional Rust-based `@astrojs/markdown-satteri` processor.

## Approach considered: new `markdown.processor` API (REJECTED — doesn't work here)

The intended fix-forward was the new pipeline API:

```js
import { unified } from "@astrojs/markdown-remark";
markdown: { processor: unified({ remarkPlugins: [remarkGfm] }) }
```

This was implemented and tested, and **it does not render the tables** (0 on
every page). Two facts, both verified against the repro, explain why:

1. **`unified({ gfm: true })` is a no-op for tables** in
   `@astrojs/markdown-remark@7.2.0` — the internal `gfm` flag did not add the
   table extension. Passing the real `remark-gfm` plugin via the processor still
   produced 0 tables.
2. **MDX ignores `markdown.processor` entirely.** The decisive A/B (same plugin,
   only the wiring differs):
   - `markdown.processor: unified({ remarkPlugins: [remarkGfm] })` → **0 tables**
   - `markdown.remarkPlugins: [remarkGfm]` (legacy) → **2 tables**
   The pages are `.mdx`, processed by `@astrojs/mdx@5.x` (pinned by Starlight
   0.39.2), which predates the 6.4 rework and reads only the *legacy* markdown
   options. The new `processor` never reaches the MDX render path.

Crucially, **`@astrojs/starlight@latest` is 0.39.2 — already the installed
version.** There is no newer Starlight that adopts Astro 6.4's pipeline;
`@astrojs/mdx@6.0.1` (peer `astro ^6.4.0`) exists but Starlight does not depend
on it. So the new-API path is simply unavailable on the current Starlight.

## Outcome: legacy `markdown.remarkPlugins` (chosen)

```js
import remarkGfm from "remark-gfm";
markdown: { remarkPlugins: [remarkGfm] }
```

- `remark-gfm@^4.0.1` added as a direct dep (was transitive, not hoisted).
- `@astrojs/markdown-remark` is **not** needed and is not added.
- This rides the **same** deprecation surface Starlight 0.39.2 already triggers:
  the `markdown.remarkPlugins … deprecated` warning fires on the plain baseline
  too (Starlight injects its own plugins this way), so our change introduces
  **no new** deprecation warning. The `markdown.gfm` flag (a *separate*,
  additional warning) is deliberately avoided.
- Removal of legacy `markdown.remarkPlugins` isn't until **Astro 8.0** — far
  off, and Starlight will have shipped 6.4-pipeline support well before then.

Verified build signals (`concepts/color-providers`, plus page counts):

| Signal | Result |
| --- | --- |
| `color-providers` `<table>` | 2 ✅ |
| `config-options` `<table>` | 5 ✅ |
| `two_row` `<table>` | 7 ✅ |
| `sl-anchor-link` (heading anchors) | 13 (unchanged) ✅ |
| smartypants `“` | 13 (unchanged) ✅ |
| six-providers is a real `<table>` (`<thead>`/`<tbody>`) | yes ✅ |
| new deprecation warnings introduced | none ✅ |

So legacy `remarkPlugins` merges *with* Starlight's injected plugins (anchors
survive) rather than replacing them — the risk the processor approach carried
does not apply to this path.

## Deferred work

Tracked here because it has a future trigger, not a present action:

1. **Migrate to the new pipeline when Starlight supports it.** Watch for a
   Starlight release whose `@astrojs/mdx` dependency is `>=6` (the 6.4-pipeline
   integration). When it lands: bump Starlight, then either
   - drop the `markdown` block entirely if GFM defaults are restored, or
   - move to `markdown.processor: unified({ remarkPlugins: [remarkGfm] })`
     (and re-add `@astrojs/markdown-remark` only if `unified` is needed),
   and delete the legacy `remarkPlugins` block. Re-run the verification table
   above. The `DEFERRED:` comment in `astro.config.mjs` points back here.
2. **Astro 8.0 hard deadline.** `markdown.remarkPlugins` is removed in Astro
   8.0. The Starlight migration (item 1) must land before any bump to Astro 8.x;
   until then this fix is stable across 6.x/7.x.
3. **Dependabot resilience.** This break reached production because Dependabot
   bumped Astro across a pipeline rework Starlight wasn't ready for, with no
   rendered-HTML test to catch it. Consider (a) a Dependabot `ignore` /
   grouped-update rule pairing `astro` with `@astrojs/starlight` so they move
   together, and (b) the build-time table tripwire below.
4. **Rendered-HTML tripwire (no current guard).** `test_docs_config_options_drift.py`
   audits field-set drift, not built HTML. A CI/grep assertion — "a known
   markdown table renders to `<table>` in `dist/`" — would have caught this at
   build time. Worth a separate issue.

## Verification (done)

- `pnpm exec astro build` introduces **no new** deprecation warning (only the
  pre-existing Starlight `markdown.remarkPlugins` notice, which fires on a plain
  baseline too).
- Table counts restored: `color-providers` 2, `config-options` 5, `two_row` 7.
- Correctness signals all hold (anchors 13, smartypants 13).
- Six-providers renders as a real `<table>` with `<thead>`/`<tbody>`, not a
  `<p>` of pipes.
- Post-merge: re-fetch the live page via
  `cloudflared access curl https://docs.ledticker.dev/concepts/color-providers/`
  and confirm `<table>` present.
