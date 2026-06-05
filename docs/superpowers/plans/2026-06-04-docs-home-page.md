# Home / Landing Page Expansion (Phase 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite the docs-site home page (`docs/site/src/content/docs/index.mdx`) into a full landing page that positions led-ticker as an extensible library, stays inviting to hobbyists, and signposts both audiences.

**Architecture:** A single MDX file using the Starlight `splash` template, the built-in `hero`, the standard `Card`/`CardGrid` components, and the existing `DemoGif`. No new components, no newly rendered GIFs — every demo asset referenced already exists under `docs/site/public/demos*/`. After implementation, a technical-writer reviewer subagent runs the `docs/DOCS-STYLE.md` rubric against the page.

**Tech Stack:** Astro Starlight, MDX. Verification via `make docs-build` and `make docs-lint` (both run `pnpm install --frozen-lockfile` first, so they are self-contained in a fresh worktree).

**Source spec:** `docs/superpowers/specs/2026-06-04-docs-home-page-design.md`

**Worktree:** `.claude/worktrees/docs-home`, branch `feat/docs-home`. Single PR (led-ticker).

**Commit convention:** Use `git -c core.hooksPath=/dev/null commit` for every commit.

---

### Task 1: Rewrite `index.mdx` into the landing page

This is a content task — the complete final file is given in Step 2. There is no failing-test cycle; the verification steps (3–5) confirm assets exist, links resolve, and the site builds and lints clean.

**Files:**
- Modify (full rewrite): `docs/site/src/content/docs/index.mdx`

- [ ] **Step 1: Confirm every referenced asset and link target exists**

Run from the worktree root:
```bash
cd /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/docs-home/docs/site
# Demo GIFs referenced by the new page (all must print "OK")
for f in public/demos/message-rainbow.gif public/demos-long/widget-weather.gif \
         public/demos-long/widget-mlb.gif public/demos-long/widget-coinbase.gif \
         public/demos/widget-gif.gif public/demos/widget-countdown.gif \
         public/demos-long/widget-pool.gif; do
  test -f "$f" && echo "OK  $f" || echo "MISSING  $f"
done
# Internal link target pages (all must print "OK")
cd src/content/docs
for p in getting-started.mdx tutorial/01-setup.mdx widgets/index.mdx widgets/weather.mdx \
         widgets/mlb.mdx widgets/coinbase.mdx widgets/gif.mdx widgets/countdown.mdx \
         plugins/index.mdx plugins/available.mdx plugins/authoring/01-scaffold.mdx \
         transitions/push.mdx hardware/building-your-own.mdx; do
  test -f "$p" && echo "OK  $p" || echo "MISSING  $p"
done
```
Expected: every line prints `OK`. If any prints `MISSING`, STOP and report — the new page must not reference it.

- [ ] **Step 2: Replace the file contents**

Overwrite `docs/site/src/content/docs/index.mdx` with EXACTLY this content:

````mdx
---
title: led-ticker
description: An asyncio Python toolkit for displaying configurable feeds on RGB LED matrix panels — extensible with plugins.
template: splash
hero:
  tagline: An asyncio Python toolkit for RGB LED matrix signs — configurable feeds, extensible with plugins.
  actions:
    - text: Get started
      link: /getting-started/
      icon: right-arrow
    - text: GitHub
      link: https://github.com/JamesAwesome/led-ticker
      icon: external
      variant: minimal
---

import DemoGif from "../../components/DemoGif.astro";
import { Card, CardGrid } from "@astrojs/starlight/components";

<DemoGif
  src="/demos/message-rainbow.gif"
  caption="A `message` widget with rainbow per-character coloring — one of many built-in building blocks."
/>

## Two ways in

<CardGrid>
  <Card title="Run a sign">
    You have, or want, an RGB LED matrix sign. Describe what it shows in a TOML
    config — RSS, weather, scores, countdowns, images — **no Python required.**

    - [Get started](/getting-started/) — install and light up a sign in minutes
    - [Tutorial](/tutorial/01-setup/) — build a complete config step by step
    - [Browse widgets](/widgets/) — every built-in building block
  </Card>
  <Card title="Build on it">
    You want to extend led-ticker. Add widgets, transitions, color providers,
    fonts, or lifecycle hooks through the public `led_ticker.plugin` API —
    without forking core.

    - [Plugins](/plugins/) — how extensions install and load
    - [Write a plugin](/plugins/authoring/01-scaffold/) — a guided walkthrough
  </Card>
</CardGrid>

## What you can put on it

<CardGrid>
  <Card title="Weather">
    <DemoGif src="/demos-long/widget-weather.gif" caption="Current conditions for any location." />

    [Weather widget →](/widgets/weather/)
  </Card>
  <Card title="MLB scores">
    <DemoGif src="/demos-long/widget-mlb.gif" caption="Live game scores and counts." />

    [MLB widget →](/widgets/mlb/)
  </Card>
  <Card title="Crypto prices">
    <DemoGif src="/demos-long/widget-coinbase.gif" caption="Spot prices from Coinbase." />

    [Coinbase widget →](/widgets/coinbase/)
  </Card>
  <Card title="Animated GIFs">
    <DemoGif src="/demos/widget-gif.gif" caption="Play a looping GIF, with optional overlay text." />

    [GIF widget →](/widgets/gif/)
  </Card>
  <Card title="Countdowns">
    <DemoGif src="/demos/widget-countdown.gif" caption="Count down to any date or time." />

    [Countdown widget →](/widgets/countdown/)
  </Card>
  <Card title="…and your own">
    <DemoGif src="/demos-long/widget-pool.gif" caption="The pool widget is a real, shipped plugin." />

    [Pool plugin →](/plugins/available/)
  </Card>
</CardGrid>

[Browse all widgets →](/widgets/)

## Extensible by design

led-ticker is a library, not just an app. A curated public API
(`led_ticker.plugin`) lets anyone add **widgets, transitions, color providers,
animations, borders, easings, emojis, fonts, and lifecycle hooks** as an
installable plugin — no fork of core required. The pool water-temperature
widget shown above is exactly that: a real plugin that lives in
[its own repo](https://github.com/JamesAwesome/led-ticker-pool) and contributes
`type = "pool.monitor"`.

- [Plugins overview](/plugins/) — install, load, and the `[plugins]` config block
- [Write a plugin](/plugins/authoring/01-scaffold/) — scaffold, build, and package one

## Where to next

- **Run a sign:** [Get started](/getting-started/) · [Tutorial](/tutorial/01-setup/)
- **Pick content:** [Widgets](/widgets/) · [Transitions](/transitions/push/)
- **Extend it:** [Plugins](/plugins/) · [Write a plugin](/plugins/authoring/01-scaffold/)
- **Get the hardware:** [Building your own](/hardware/building-your-own/)
````

- [ ] **Step 3: Format, then build**

Run (do NOT pipe to `tail` before checking the exit code — per the DOCS-STYLE gotcha):
```bash
cd /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/docs-home
make docs-format
make docs-build
echo "BUILD_EXIT=$?"
```
Expected: `make docs-build` completes with `[build] Complete!` and `BUILD_EXIT=0`. The page count should be unchanged from before (the build prints "N page(s) built"; this task adds no pages). If the build errors on an unknown `icon` name in the hero, note that only `right-arrow` and `external` are used here (both already valid in the prior version) — investigate the actual error rather than guessing.

- [ ] **Step 4: Lint**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/docs-home
make docs-lint
echo "LINT_EXIT=$?"
```
Expected: `LINT_EXIT=0`. `make docs-lint` runs `prettier --check` + `astro check`; `astro check` validates internal links, so a broken link target fails here. If prettier reports formatting diffs, you already ran `make docs-format` in Step 3 — re-run it, then re-run `make docs-lint` and confirm `LINT_EXIT=0`.

- [ ] **Step 5: Sanity-check the rendered output references the right assets**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/docs-home/docs/site
# The built home page should reference the lead GIF and the gallery GIFs
grep -o "/demos[^\"')]*\.gif" dist/index.html | sort -u
```
Expected: lists `/demos/message-rainbow.gif` and the six gallery GIFs (`widget-weather`, `widget-mlb`, `widget-coinbase`, `widget-gif`, `widget-countdown`, `widget-pool`). If the gallery GIFs are absent, the `Card`-wrapped `DemoGif`s didn't render — investigate before committing.

- [ ] **Step 6: Commit**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/docs-home
git add docs/site/src/content/docs/index.mdx
git -c core.hooksPath=/dev/null commit -m "docs: expand the home page into an extensible-library landing page

Splash-template landing page: library-forward hero tagline, a two-audience
'ways in' card grid (configure vs. extend), a 'what you can put on it'
gallery (reusing existing demo GIFs, incl. the pool plugin as live proof of
extensibility), an 'extensible by design' section, and forward CTAs."
```

---

### Task 2: Technical-writer review pass

Per the spec's review loop, after the page builds clean the controller dispatches a **technical-writer reviewer subagent** that reads the rendered/source `index.mdx`, runs the `docs/DOCS-STYLE.md` §3 checklist (treating the tutorial-only items — "what you'll need" box, time/effort stamp, local troubleshooting — as **N/A** for a landing page), and returns prioritized **must-fix** vs **nice-to-have** notes. The implementer applies must-fix items; re-review until the checklist passes; then re-run Steps 3–4 of Task 1 and amend/extend the commit.

This task has no fixed code — its output is whatever fixes the review surfaces. If the reviewer returns zero must-fix items, record that and proceed.

- [ ] **Step 1:** Dispatch the tech-writer reviewer against `index.mdx` with the DOCS-STYLE rubric (N/A items noted above).
- [ ] **Step 2:** Apply must-fix items; re-run `make docs-format && make docs-build && make docs-lint`; confirm exit 0.
- [ ] **Step 3:** Commit any fixes (`git -c core.hooksPath=/dev/null commit`), or record "no must-fix items" if none.

---

## Self-Review

**1. Spec coverage:**
- Splash template + library-forward tagline + hero actions → frontmatter (Task 1 Step 2). ✓
- Lead visual (`message-rainbow.gif`) → first `DemoGif` (Step 2). ✓
- Two-audience signpost cards (Run a sign / Build on it, reader named) → "Two ways in" CardGrid (Step 2). ✓
- "What you can put on it" gallery from six confirmed-existing GIFs, each linking to its page; pool plugin as extensibility proof → "What you can put on it" CardGrid + "Browse all widgets" (Step 2). ✓
- "Extensible by design" section (public API, plugin contributions, pool as real plugin, cross-links) → that section (Step 2). ✓
- Footer next-step CTA → "Where to next" (Step 2). ✓
- Reuse existing assets / no new components → only `DemoGif` + standard `Card`/`CardGrid` imported; all GIF paths verified in Step 1. ✓
- Verification: build + lint clean, assets resolve, links resolve → Steps 1, 3, 4, 5. ✓
- Review loop with tech-writer reviewer → Task 2. ✓
- Out of scope (only `index.mdx` changes; no new GIFs; no new components) → only `index.mdx` modified. ✓

No gaps.

**2. Placeholder scan:** No TBD/TODO. The literal "…and your own" card title and the ellipsis in copy are intentional content, not placeholders. ✓

**3. Type/consistency:** Component imports (`DemoGif`, `Card`, `CardGrid`) match their usage; every internal link in the file content corresponds to a path verified in Task 1 Step 1; GIF `src` paths match the Step 1 asset checks exactly; icons used in the hero (`right-arrow`, `external`) are the two already present in the pre-existing page, so no new icon names are introduced. ✓
