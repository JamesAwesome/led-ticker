# Design: led-ticker docs site

**Date:** 2026-05-08
**Status:** Approved

## Overview

A GitHub Pages-hosted in-depth configuration guide for led-ticker. Covers widgets, transitions, customization, the emoji system, decision rules, hardware setup, and the validator tool. Visual-forward: every widget and transition gets a demo gif rendered from a tiny TOML snippet by a software renderer that runs the actual ticker engine against the test stub. Real hardware photos cover the showcase / "what this looks like in real life" angle.

The site shares a single source of truth for factual content (option tables, transition lists, decision rules) with the existing `creating-a-config` Claude Code skill. Tutorials, walkthroughs, and visuals are docs-only.

---

## Foundational decisions

These were locked during brainstorming and drive every section below.

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Audience phasing | Phased: showcase → tutorial → reference | Captures top-of-funnel + setup conversion + power-user lookup |
| Source-of-truth strategy | Mixed: shared fact pack + docs-only framing | Skill and docs site read the same factual content; tutorials/visuals are docs-only |
| Visual pipeline | Mix: software renderer + real hardware capture | Renderer for the bulk of widget/transition demos (clean, repeatable); hardware for showcase |
| Static site generator | Astro Starlight (MDX) | Enables embedded components for `<DemoGif>`, `<OptionsTable>`, `<DecisionRule>`; markdown-first |
| Per-page tier | Tiered minimum on every page | Every widget/transition has a real page in v1, deeper content accretes over time |

---

## Architecture overview

Three new top-level directories at repo root:

```
docs/site/                  Astro Starlight project (MDX, components, assets)
docs/content-source/        Shared fact-pack markdown (consumed by both site + skill)
tools/render-demo/          Python gif renderer
```

Plus:

```
.github/workflows/docs.yml             New CI workflow: build + deploy
.github/ISSUE_TEMPLATE/submit-sign.yml New: showcase submissions
```

The `src/led_ticker/` Python package is unchanged. The existing `tests/stubs/rgbmatrix/` is reused by the renderer (no test-stub-to-package promotion needed).

The site deploys to GitHub Pages at `https://jamesawesome.github.io/led-ticker/` by default. Custom domain via `docs/site/public/CNAME` is a one-step add later.

---

## Information architecture

```
docs/site/src/content/docs/
├── index.mdx                          Home (showcase teasers + nav)
├── getting-started.mdx                "First sign in 10 minutes"
│
├── concepts/
│   ├── display.mdx                    rows / cols / scale / content_height / pixel_mapper_config
│   ├── sections-and-modes.mdx         forever_scroll / infini_scroll / swap
│   ├── fonts.mdx                      BDF vs hires (TTF/OTF), font_size, font_threshold
│   ├── color-providers.mdx            constant / rainbow / gradient / color_cycle / random
│   ├── animations.mdx                 typewriter
│   ├── borders.mdx                    rainbow chase, constant
│   └── frame-counters.mdx             per-effect counters, visit reset, transition pause
│
├── widgets/
│   ├── index.mdx                      List + decision tree
│   ├── message.mdx, countdown.mdx, two_row.mdx
│   ├── weather.mdx, rss_feed.mdx
│   ├── mlb.mdx, mlb_standings.mdx
│   ├── coinbase.mdx, coingecko.mdx, etherscan.mdx
│   └── gif.mdx, image.mdx
│
├── transitions/
│   ├── index.mdx                      Grid + selection table
│   ├── push.mdx                       push_left/right/up/down + alternating + random
│   ├── wipe.mdx                       wipe_*
│   ├── sprite.mdx                     nyancat / pokeball / baseball / sailor_moon / pacman
│   └── special.mdx                    cut, color_flash, dissolve, split, scroll
│
├── assets/
│   ├── emoji.mdx                      17+ slugs, lowres + hires, how to add one
│   ├── fonts.mdx                      BDF bundled + custom hires (Adobe / TTF / OTF)
│   └── images.mdx                     GIFs, stills, fit modes, scroll layering
│
├── footguns.mdx                       21 decision rules
│
├── hardware/
│   ├── small-sign.mdx                 Pi 4, 5x32x16
│   ├── bigsign.mdx                    Pi 5 RP1, vertical-serpentine
│   └── deploy.mdx                     systemd / Docker / config bundles
│
├── tools/
│   ├── validate.mdx                   `led-ticker validate`
│   └── creating-a-config.mdx          The Claude Code skill (cross-link)
│
├── showcase.mdx                       Real-world signs (gallery)
│
└── reference/
    ├── config-options.mdx             Every TOML key
    └── cli.mdx                        `led-ticker` command reference
```

~36 pages.

---

## Shared fact pack

Solves: skill and docs site need the same factual content (widget options, transition descriptions, decision rules). Diverging copies drift over time. Single source of truth in `docs/content-source/`.

### What lives in the fact pack (shared)

- **Per-widget**: option table + base description (`widgets/<name>.md`)
- **Per-transition family**: description + when-to-use (`transitions/<family>.md`)
- **Decision rules**: 21 rules, one file each (`rules/<NN>-<slug>.md`), `DETECT` / `SYMPTOM` / `FIX` format
- **Emoji slug list** (`emoji.md`): both lowres + hires
- **Color providers, animations, borders** vocabularies (`color-providers.md`, `animations.md`, `borders.md`)
- **Hardware specs** (`hardware/small-sign.md`, `hardware/bigsign.md`)

### What's docs-only

- Tutorials, walkthroughs (`getting-started.mdx`, etc.)
- Showcase gallery (`showcase.mdx`)
- Cross-cutting concept pages where multiple shared facts are woven together
- Visual demos
- Page-level framing prose

### What's skill-only

- `SKILL.md` — Q&A wizard flow
- `references/snippets.md` — recipe library indexed by `(use_case × widget × sign)`

### Wiring

The docs site MDX pages do `?raw` imports of the shared markdown files and either render them through component wrappers (`<OptionsTable source="widgets/message" />`) or include them inline.

The skill's existing references at `.claude/skills/creating-a-config/references/{widgets,transitions,decision-rules,asset-handling,hardware-guide}.md` are no longer loaded by the skill. `SKILL.md` is updated so its `Load references/...` directives point at the new `docs/content-source/...` files instead. The old reference files are replaced with one-line pointer markers (e.g., `See docs/content-source/widgets/`) so anyone browsing the old paths gets redirected; nothing in the skill loop reads them. The migration is behavior-preserving for the skill (same content, new location). `references/snippets.md` stays where it is — it's skill-only and not part of the fact pack.

### Phase 2+ (not v1)

Auto-generate widget option tables from `attrs.define` introspection so the source of truth is the Python class. v1 is hand-maintained — same as today, just relocated.

---

## Gif renderer

`tools/render-demo/render.py` — a Python script that takes a TOML config and produces a gif at panel resolution. Internal tool, not exposed as a `led-ticker` subcommand.

### How it works

A recording wrapper around `LedFrame.matrix.SwapOnVSync` snapshots each swap's canvas before forwarding to the real (stub) swap. The script drives the ticker engine for `--duration` seconds at the standard 50 ms engine tick (5 sec → 100 frames). Each captured snapshot becomes a `PIL.Image` at native panel resolution, upscaled 4× by default (each LED pixel → 4×4 block), encoded with `imageio.mimsave` to gif at 20 fps. Uses the existing `tests/stubs/rgbmatrix` infrastructure via `PYTHONPATH=tests/stubs` — no new stub code.

### CLI

```
uv run python tools/render-demo/render.py <config.toml> -o out.gif \
  [--duration 5] [--upscale 4] [--fps 20] [--start-section 0]
```

Defaults: 5 sec, 4× upscale, 20 fps, section 0. `--start-section` lets a long config jump to a specific section (so a per-widget demo TOML with one section just plays that).

### Demo configs

Live at `docs/site/src/content/demos/*.toml`. One per widget, transition family, color provider, animation, border. Each is a minimal complete config (display + one section + the widget). Hand-authored once.

### Missing-asset placeholders

Before running the engine, the renderer walks the config's widget paths (`assets/foo.png`, font references, etc.) and checks each. For any missing asset it generates a synthetic stand-in to a temp dir and rewrites the config to point at it:

- **Image / single-frame placeholder**: PIL-generated solid block (dark lavender brand neutral) sized to panel aspect, with the missing path text rendered on top in small white.
- **Gif placeholder**: same block with a 3-frame subtle pulse so motion-aware widgets behave correctly.
- **Font placeholder**: falls back to bundled `Inter-Regular.otf`.

This means customer-IP configs (e.g., `config.moonbunny.example.toml`) can be rendered as STRUCTURAL DEMOS even though brand assets aren't in the repo. Placeholders are visibly placeholders; no risk of confusion.

### Docs-build wiring

`docs/site/scripts/build-demos.mjs` (Node, called from `astro build` prebuild):

1. Walks `src/content/demos/*.toml`
2. For each demo, checks if `public/demos/<name>.gif` exists and is fresher than the .toml
3. If not, calls the Python renderer via `child_process`
4. Output gifs land in `public/demos/`, referenced from MDX as `/demos/<name>.gif`

If any demo render fails, the build fails fast (so docs never ship with broken demos).

---

## Asset capture & contribution

Two flows: yours, and theirs.

### Owner capture (you)

Hardware photos/clips for the showcase, hero shots, the moonbunny case study. You record on phone, send the file, I trim/encode/place. Lives in `docs/site/public/showcase/<entry-slug>/photo-1.jpg` etc., referenced by `docs/site/src/content/showcase/<entry-slug>.mdx`. Software gif renderer covers the synthetic side; this covers "what does it actually look like in real life."

### External submission

A "Submit your sign" CTA on the Showcase page. v1 mechanism: links to a pre-filled GitHub issue at `.github/ISSUE_TEMPLATE/submit-sign.yml` asking for:

- 1+ photos or short clips of the sign running (drag-and-drop into the issue)
- One-line description of where/why it runs
- Hardware specs (Pi 4 small / Pi 5 bigsign / custom)
- Optional: their TOML config
- Permission line: explicit checkbox confirming the maintainer can use the assets in the docs

Maintainer reviews the issue, opens a PR adding the entry to the showcase, closes the issue with a thanks.

PR-based submission is also accepted (one-line note in the showcase index `.mdx`); the issue path is just the friendlier default for non-coders.

### What's NOT user-submittable in v1

Widgets, transitions, emoji slugs (these are code contributions, follow the existing repo PR flow). Submissions are showcase entries + photos.

---

## Per-page content templates

Every page hits a minimum bar (per the C-tier decision); some grow beyond it as content matures. Shared MDX components in `docs/site/src/components/` enforce the minimum without hand-curation.

### Components

- `<DemoGif src="..." caption="..." />` — gif at consistent panel-aspect framing with caption ("rendered at 4× upscale, 5 sec")
- `<TomlExample title="..." />` — code block with copy button + optional title
- `<OptionsTable source="widgets/message" />` — imports the shared fact-pack markdown for that widget's options and renders as a table
- `<DecisionRule id="14" />` — looks up rule 14 from the shared fact pack and renders a compact callout (DETECT / SYMPTOM / FIX)
- `<RelatedPages slugs={[...]} />` — small "see also" cluster at the bottom of each page

### Widget-page template

```mdx
---
title: message widget
description: Static text with optional border, inline emoji, and color/animation effects.
---

The `message` widget displays static text. It's the most-used widget — most LED signs are 80% messages.

<DemoGif src="/demos/message-rainbow.gif" caption="message + font_color = 'rainbow'" />

<TomlExample title="Minimal example">
```toml
[[playlist.section.widget]]
type = "message"
text = "Hello, world!"
```
</TomlExample>

## Options

<OptionsTable source="widgets/message" />

## Common patterns

[…short examples for typical use cases…]

## Footguns

<DecisionRule id="12" />
<DecisionRule id="20" />

<RelatedPages slugs={["widgets/countdown", "widgets/two_row", "concepts/color-providers"]} />
```

### Transition-page template

Opening sentence → per-direction grid of `<DemoGif>` cards → behavior notes → selection guidance.

### Showcase-entry template

Hero photo/clip → one-paragraph context → hardware spec → optional config (linked or embedded) → submitter credit.

### Decision-rule rendering

Each rule lives once in the shared fact pack (`docs/content-source/rules/14-typewriter-on-image.md`). The `<DecisionRule id="14" />` component wraps the import and styles it as a callout. The `footguns.mdx` page lists ALL rules in numeric order, each rendered with the same component.

---

## CI / build / deploy

`.github/workflows/docs.yml`. Existing `ci.yml` (test suite) is untouched.

### Triggers

- `push` to `main` with paths matching `docs/**`, `tools/render-demo/**`, or `.github/workflows/docs.yml`
- `workflow_dispatch` (manual rebuild from Actions tab)

### Concurrency

One docs deploy in flight at a time; new push cancels older runs.

### Permissions

`pages: write`, `id-token: write` (modern GH Pages deploy via `actions/deploy-pages@v4`).

### Steps

1. Checkout
2. `actions/setup-python` + `astral-sh/setup-uv` — Python 3.13 (matches `pyproject.toml`)
3. `actions/setup-node@v4` — Node LTS for Astro
4. `uv sync` — installs `led_ticker` so the renderer can import it
5. `npm ci` in `docs/site/`
6. **Pre-build demos**: `node docs/site/scripts/build-demos.mjs` iterates demo TOMLs, calls `uv run python tools/render-demo/render.py` for each missing or stale gif, writes to `docs/site/public/demos/`
7. **Smoke**: build-demos fails fast if any single render fails; CI fails before astro builds
8. `npm run build` (`astro build`)
9. `actions/upload-pages-artifact` → `actions/deploy-pages`

### Demo-gif strategy

Regenerate on every deploy in v1. Demo TOMLs are committed to git; gifs are not. ~25 v1 demos × 5 sec render × 2× margin ≈ ~5 min worst-case CI. Acceptable. If it ever becomes painful, switch to caching by `(TOML content hash + renderer git SHA)` via `actions/cache`.

### Repo Settings change (manual, one-time)

GitHub repo Settings → Pages → Source = "GitHub Actions" (the modern flow, not "Deploy from a branch").

---

## Phase 1 deliverables checklist

### Infrastructure (one-time)

- [ ] `docs/site/` Astro Starlight project scaffolded with theme tweaks (sidebar, color, logo)
- [ ] `docs/site/scripts/build-demos.mjs` pre-build script
- [ ] `docs/content-source/` directory created
- [ ] `tools/render-demo/render.py` gif renderer with placeholder support
- [ ] `tools/render-demo/README.md` how to run locally
- [ ] `.github/workflows/docs.yml` build + deploy pipeline
- [ ] `.github/ISSUE_TEMPLATE/submit-sign.yml` showcase submission template
- [ ] Repo Settings → Pages → Source = "GitHub Actions" (manual one-time toggle)

### Shared fact pack (`docs/content-source/`)

- [ ] `widgets/<name>.md` × 12 — option table + base description per widget
- [ ] `transitions/<family>.md` × 4 — push / wipe / sprite / special
- [ ] `rules/<NN>-<slug>.md` × 21 — one file per decision rule
- [ ] `emoji.md` — full slug list, lowres + hires
- [ ] `color-providers.md`, `animations.md`, `borders.md`
- [ ] `fonts.md` — BDF + hires + threshold tuning
- [ ] `hardware/small-sign.md`, `hardware/bigsign.md`

### Skill integration (mechanical migration)

- [ ] Replace `.claude/skills/.../references/{widgets,transitions,decision-rules,asset-handling,hardware-guide}.md` with thin pointer files referencing `docs/content-source/`
- [ ] Update `SKILL.md` to load from new paths
- [ ] Verify skill still runs end-to-end

### Demo configs (`docs/site/src/content/demos/*.toml`)

- [ ] One per widget × 12
- [ ] One per transition family × 4-5 (family demo covers each direction in the family)
- [ ] One per color provider × ~5
- [ ] One per animation × 1 (typewriter)
- [ ] One per border style × ~2
- [ ] Initial set: ~25 demos. Grows as content thickens.

### Astro pages (~36 MDX files), each at the C-tier minimum

C-tier minimum = intro paragraph + option table (where applicable) + ≥1 TOML example + 1 demo gif (where applicable).

- [ ] `index.mdx`, `getting-started.mdx`
- [ ] `concepts/*` × 7
- [ ] `widgets/*` × 13 (index + 12)
- [ ] `transitions/*` × 5 (index + 4 families)
- [ ] `assets/*` × 3
- [ ] `footguns.mdx`
- [ ] `hardware/*` × 3
- [ ] `tools/validate.mdx`, `tools/creating-a-config.mdx`
- [ ] `showcase.mdx` + 1 initial entry (moonbunny case study, with placeholders for brand assets)
- [ ] `reference/config-options.mdx`, `reference/cli.mdx`

### Owner-captured assets (you record, I trim/place)

- [ ] 1 hero clip — small sign in action
- [ ] 1 hero clip — bigsign in action
- [ ] Optional: 1 moonbunny showcase clip (storefront window context)
- [ ] These can land post-launch — placeholder hero images at first, swap when you have time

---

## Phase 2+ (NOT in v1, listed for readiness)

- **Live config preview** — TOML editor + drag-drop assets + render → gif. Implementation: Python service on Fly.io / Railway (recommended) OR Pyodide WASM client-side. Decided when phase 2 starts. Hosting is independent of the static site — phase 2 doesn't require migrating the GitHub Pages frontend; the live preview is a separate origin behind a CORS-enabled API.
- **Auto-generated option tables** from `attrs.define` introspection (replaces hand-maintained tables in the fact pack).
- **Community configs gallery** — user-submitted full TOMLs displayed alongside owner-curated showcase entries.
- **Internationalization, search filter UI on showcase, versioned docs by released `led-ticker` tag.**

---

## Open questions

None at brainstorm close. Implementation decisions that surface during planning (exact MDX import syntax, theme details, demo selection priority) get handled in the implementation plan, not here.
