# Home / Landing Page Expansion — Design (Phase 1)

**Date:** 2026-06-04
**Status:** Approved (brainstorm), pending implementation plan

## Context: the larger docs effort

This is **Phase 1** of a phased deep-dive expansion + review of the led-ticker docs site. Phase order:

- **Phase 0 (shipped, PR #155):** the docs style guide + review rubric (`docs/DOCS-STYLE.md`).
- **Phase 1 (this spec):** expand the home/landing page — position led-ticker as an *extensible library*, keep it inviting to hobbyists, signpost both audiences.
- **Phase 2:** expand technical/API docs (render-architecture page, `led_ticker.plugin` API reference, transition/color-provider authoring walkthroughs).
- **Phase 3:** deep-dive audit + fixes of the existing ~58 pages.

Each phase is its own spec → plan → implementation cycle, with a **technical-writer reviewer subagent** applying the Phase 0 rubric to each completed task. This spec covers **Phase 1 only**.

## Goal

Replace the current thin home page (a hero with one tagline, a single "hello world" GIF, and a short "what you can do" paragraph linking only to widgets/transitions) with a full landing page that:

1. Positions led-ticker as an **extensible library** — not just a feed scroller — surfacing the public plugin API alongside the configure-it story.
2. Stays **genuinely inviting to hobbyists** — outcome-first, visual, no jargon wall.
3. **Signposts both audiences** up front: hobbyist sign-owners who *configure* (TOML), and developers who *extend* (plugins / public API).

It applies the just-merged `docs/DOCS-STYLE.md` rubric throughout.

## Decisions (from brainstorm)

- **Scope of redesign:** full landing page (hero + audience-signposted card grid + "what you can build" gallery + extensibility section + footer CTAs).
- **Tagline (hero):** "An asyncio Python toolkit for RGB LED matrix signs — configurable feeds, extensible with plugins." (Library-forward, concrete, no marketing language.)
- **Template:** `template: splash` — full-width, no right-hand "On this page" TOC, classic landing-page layout.
- **Assets:** reuse existing demo GIFs under `docs/site/public/demos*/`. **No new GIFs are rendered in this phase.**
- **Components:** Starlight built-in `hero`, `Card`/`CardGrid` (already used in `plugins/authoring/`), and the existing `DemoGif`. **No new Astro components.**
- **Single file:** only `docs/site/src/content/docs/index.mdx` changes.

## Deliverable

A rewritten `docs/site/src/content/docs/index.mdx` with the following structure.

### Frontmatter / hero

```yaml
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
```

Imports: `DemoGif` (existing), plus `Card` and `CardGrid` from `@astrojs/starlight/components` (the import path already used by `plugins/authoring/*`).

### 1. Lead visual

A `DemoGif` of `message-rainbow.gif` immediately under the hero — the payoff/visual near the top (rubric: lead with the payoff).

### 2. "Two ways in" (audience signpost)

A `CardGrid` with **two cards that name the reader** (rubric: reader named up front):

- **Run a sign** (icon e.g. `open-book` or a rocket/sign icon from Starlight's set) — for hobbyist sign-owners. Copy conveys: you have, or want, an LED sign; describe it in a TOML config — RSS, weather, scores, countdowns, images — no Python required. Links: Get started (`/getting-started/`), Tutorial (`/tutorial/01-setup/`), Browse widgets (`/widgets/`).
- **Build on it** (icon e.g. `puzzle`/`setting`) — for developers. Copy conveys: extend led-ticker by adding widgets, transitions, color providers, fonts, or lifecycle hooks through the public `led_ticker.plugin` API — without forking core. Links: Plugins overview (`/plugins/`), Write a plugin (`/plugins/authoring/01-scaffold/`).

(Use whatever icon names are valid in Starlight's built-in icon set; the plan will pin exact names. Cards may use the `icon` and link props or inline links in the body — match the existing `plugins/authoring/` card usage.)

### 3. "What you can put on it" (gallery)

A compact gallery showing a representative spread of capability, built from **existing** GIFs, each linking to its widget/concept page. Selected assets (all confirmed present):

- Weather — `demos-long/widget-weather.gif` → `/widgets/weather/`
- MLB scores — `demos-long/widget-mlb.gif` → `/widgets/mlb/`
- Crypto — `demos-long/widget-coinbase.gif` → `/widgets/coinbase/`
- Animated GIF — `demos/widget-gif.gif` → `/widgets/gif/`
- Countdown — `demos/widget-countdown.gif` → `/widgets/countdown/`
- Pool (plugin) — `demos-long/widget-pool.gif` → `/plugins/available/` (doubles as live proof of extensibility)

Closes with a "Browse all widgets →" link (`/widgets/`, the widgets index page). Layout: a `CardGrid` of `DemoGif`s, or a simple sequence of `DemoGif`s — the plan pins the exact markup. Keep captions short (one line each).

### 4. "Extensible by design"

One matter-of-fact paragraph (no marketing tone): led-ticker is a library with a curated public API (`led_ticker.plugin`); a plugin can contribute widgets, transitions, color providers, animations, borders, easings, emojis, fonts, and lifecycle hooks without forking core; the pool water-temperature widget is a real, shipped plugin in its own repo. This **cross-links** to the plugin pages rather than re-explaining them (rubric: cross-link, don't re-explain; honesty about what's built-in vs extension). CTAs: Plugins (`/plugins/`), Authoring guide (`/plugins/authoring/01-scaffold/`).

### 5. Footer CTA

An explicit next-step block pulling the reader forward (rubric: next-step CTA on every page) — links to Getting started, Tutorial, Widgets, Plugins. Implemented as a short Markdown list or `CardGrid`; `RelatedPages` is **not** used here because the splash template/landing context wants explicit forward CTAs rather than the standard related-pages footer. The plan pins the markup.

## Applying the DOCS-STYLE rubric

The page is the first Phase 1 artifact the technical-writer reviewer checks. Relevant rubric items and how this design meets them:

- **Reader named up front** → the two "ways in" cards (§2).
- **Payoff/visual near the top** → lead `DemoGif` (§1) + gallery (§3).
- **Gloss jargon / no jargon wall** → "plugin," "public API," "lifecycle hooks" appear with plain-language framing and link out; the hobbyist card explicitly says "no Python required."
- **Concrete, not marketing** → tagline and all copy stay literal; no "dazzling"/"blazing" language.
- **Cross-link, don't re-explain** → gallery and extensibility section link to widget/plugin pages instead of restating them.
- **Next-step CTA** → footer block (§5).
- **Builds + lints clean** → `make docs-build` and `make docs-lint` pass (verification below).

Items that **do not apply** to a landing page (and why): a "what you'll need" prerequisites box and a time/effort stamp are tutorial-page patterns, not landing-page patterns; local "if it doesn't work" troubleshooting belongs on task pages. The reviewer should treat these as N/A for the home page.

## The review loop (this phase)

After the page is implemented and self-checked, a **technical-writer reviewer subagent** reads `index.mdx`, runs the `docs/DOCS-STYLE.md` §3 checklist (treating the tutorial-only items as N/A per above), and returns prioritized **must-fix** vs **nice-to-have** notes. The implementer fixes the must-fix items and the reviewer re-reviews until the checklist passes. This runs alongside the standard spec-compliance review.

## Verification

- `make docs-build` passes (exit 0); the home page renders without errors.
- `make docs-lint` passes (run `make docs-format` first if Prettier complains, then re-lint, per the DOCS-STYLE gotcha — never pipe `docs-lint` to `tail`).
- Every `DemoGif` `src` resolves to a file that exists under `docs/site/public/`; every internal link target is a real page (no 404s in the build).
- The page names both audiences, surfaces the plugin/extensibility story, and ends with a forward CTA.

## Out of scope (Phase 1)

- Any page other than `index.mdx` (getting-started, widgets, plugins, etc. stay as-is).
- Rendering new demo GIFs (reuse existing assets only).
- New Astro components or changes to `DemoGif`.
- Sidebar / navigation / theme changes.
- The technical/API content expansion and the existing-docs audit — those are Phases 2 and 3.
