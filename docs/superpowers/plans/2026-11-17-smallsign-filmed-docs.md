# Smallsign filmed docs (PR 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans (inline). Steps use checkbox (`- [ ]`) syntax.

**Goal:** Put the session-0 footage (dark-room takes, James's pick) on the docs site: hero video on the homepage, showcase and smallsign pages; filmed clips on every effect-family, transition and widget page that has one; a lit-vs-dark comparison on the smallsign hardware page.

**Architecture:** `DemoGif.astro` gains `video` (mp4-primary `<video autoplay muted loop playsinline>`) and `filmed` (no `image-rendering: pixelated`). A new `FilmedGrid.astro` lays several filmed `DemoGif`s out in a two-column grid so a page shows its whole family in one "On real hardware" block. A pytest tripwire keeps `docs/site/public/filmed/` and the pages in lockstep (every reference exists, every file is referenced, budgets hold).

**Spec:** `docs/superpowers/specs/2026-11-17-smallsign-filming-design.md` §C (docs wiring). Executed inline; James chose dark takes for the docs, lit takes as comparisons, YouTube in both (2026-11-17).

## Global Constraints

- `docs/DOCS-STYLE.md`: captions describe content (they are the alt text), Firebird Yoga identity, lead with the payoff, no boilerplate.
- Committed media: GIFs ≤ 2.6 MB except `animation-fisheye.gif` (3.4 MB, accepted), `hero.mp4` ≤ 4 MB. No raw recordings, no YouTube mp4s (they live on James's Desktop).
- Every file under `docs/site/public/filmed/` must be referenced by a page; every `/filmed/...` reference must exist.
- `make docs-lint` (prettier + astro check) clean; `make test` green.

## Review Focus

- A browser without autoplay (low-power mode) shows a frozen first frame — acceptable, `controls` are off by design; `poster` not used because the first frame is the slate-adjacent black panel.
- Reduced-motion users: the rendered GIF catalog already animates, so no new regression; noted, not handled.
- `FilmedGrid` on a phone: single column (media query), captions wrap.
- `lit/` comparison clips must be the same segment as their dark twin so the comparison is honest.
- Homepage hero replaces the rainbow message GIF; the alt text must still say what the sign is showing.

---

### Task 1: Components, cache rule, tripwire

**Files:** Modify `docs/site/src/components/DemoGif.astro`; Create `docs/site/src/components/FilmedGrid.astro`; Modify `docs/site/public/_headers`; Create `tests/test_docs_filmed_media.py`.

- [ ] Step 1: write `tests/test_docs_filmed_media.py` — reference ↔ file lockstep, size budgets, `_headers` has `/filmed/*`, `DemoGif.astro` declares `video` and `filmed` props. Run: `uv run pytest tests/test_docs_filmed_media.py -q` → FAIL (props missing, unreferenced files).
- [ ] Step 2: `DemoGif.astro`: props `src?: string`, `video?: string`, `filmed?: boolean`; `<video>` when `video` given (`<source type="video/mp4">`, `<img>` fallback when `src` also given); class `filmed` drops pixelated rendering and the black background. `FilmedGrid.astro`: `items: {src: string; caption: string}[]` → `<div class="filmed-grid">` of `<DemoGif filmed …/>`, 2 columns ≥ 640 px, 1 below.
- [ ] Step 3: `_headers`: `/filmed/*  Cache-Control: public, max-age=86400`.
- [ ] Step 4: commit `feat(docs): DemoGif video + filmed props, FilmedGrid, /filmed cache rule`.

### Task 2: Pages

**Files:** `index.mdx`, `showcase.mdx`, `hardware/smallsign.mdx`, `concepts/{color-providers,borders,backgrounds,animations}.mdx`, `transitions/{push,wipe,special,sprite}.mdx`, `assets/emoji.mdx`, `widgets/{clock,countdown,two_row}.mdx`; prune `public/filmed/lit/` to the clips the smallsign page uses.

- [ ] Step 1: homepage hero → `<DemoGif video="/filmed/hero.mp4" filmed caption=…/>`.
- [ ] Step 2: showcase: a smallsign Firebird Yoga entry with the hero video and the same table shape as the bigsign entry.
- [ ] Step 3: smallsign page: "## What it looks like" with the hero video, then "Lights on vs off" `FilmedGrid` pairing `lit/<x>.gif` with `<x>.gif` for emoji-sampler, color-rainbow, border-lightbulbs-chase; delete the three unused lit files.
- [ ] Step 4: each family/transition/widget page: an "On real hardware" `FilmedGrid` (or single `DemoGif filmed`) placed after the page's first rendered demo, captions in the existing voice.
- [ ] Step 5: `make docs-format`, `make docs-lint`, `uv run pytest tests/test_docs_filmed_media.py tests/test_docs_cli_make_targets_drift.py -q`, then `make test`. Commit `docs: filmed smallsign footage across the site`.

### Task 3: Finish

- [ ] `make docs-build` succeeds; open the draft PR (gh needs James); watch CI.
