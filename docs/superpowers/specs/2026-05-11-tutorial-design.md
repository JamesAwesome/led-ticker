# Tutorial: "Build moonbunny's storefront sign" — Design Spec

## Goal

Add a five-chapter, hand-holding tutorial to the docs site that walks a moderately-technical reader from `git clone` to a polished bigsign preview gif of a fictional moonbunny aerial circus storefront sign. The tutorial lives alongside the existing terse `getting-started.mdx` (which stays as the 5-minute orientation); the new tutorial is for the reader who wants to actually build something.

Outcome the reader leaves with:
- A working `config/config.toml` they wrote themselves
- A rendered preview gif of that config on a 256×64 bigsign canvas
- Practical familiarity with sections + modes, the `two_row` widget, hi-res emoji on a `two_row` top row, custom fonts via `config/fonts/`, custom images via `config/assets/`, and transitions
- A clear next step pointing at the Hardware sidebar group for the on-Pi deploy story

## Audience

Moderately-technical reader who is comfortable in a terminal, comfortable cloning a GitHub repo, and willing to copy/paste TOML and run `make` targets. Not a novice — they don't need git instructions — but they have not authored a led-ticker config before. They are NOT the existing-user / power-user audience (those readers go straight to Widgets / Concepts / Reference and skip the tutorial).

## Architecture

### Sidebar IA

New top-level **"Tutorial"** group between Getting Started and Widgets:

```
- Home
- Getting started
- Tutorial          ← NEW
  - 1. Setup
  - 2. Your first config
  - 3. Multi-widget sign
  - 4. Custom branding
  - 5. Polish & deploy
- Widgets
- Transitions
- Concepts
...
```

Implementation: add the group to `docs/site/astro.config.mjs`'s `sidebar` array, between the existing Getting Started entry and the Widgets group.

### URL pattern

Zero-padded chapter numbers in the URL so the order is part of the contract:
- `/tutorial/01-setup/`
- `/tutorial/02-first-config/`
- `/tutorial/03-multi-widget/`
- `/tutorial/04-custom-branding/`
- `/tutorial/05-polish/`

### Page structure

Each chapter is a single MDX file at `docs/site/src/content/docs/tutorial/0N-<slug>.mdx`. Frontmatter:

```yaml
---
title: "Tutorial 3: Multi-widget sign"
description: <one-sentence description for SEO + search>
---
```

Each chapter opens with a `<details>` "If you're starting here" block containing the exact `config/config.toml` snapshot for the chapter's starting state. This lets a reader jump to Chapter 4 without doing 1-3.

Each chapter ends with:
- A "Reference" callout listing the relevant deep-dive pages (Widgets / Concepts / Reference / Pitfalls)
- A `<TutorialNav prev="..." next="..." />` Astro component (new — see below) for Prev / Next navigation

### TutorialNav component

New Astro component at `docs/site/src/components/TutorialNav.astro` (~30 lines). Renders a two-column footer:
```
← Previous: <prev title>          Next: <next title> →
```

Both columns link to the relevant chapter; the Previous slot is empty on Chapter 1 and the Next slot is empty on Chapter 5. Used at the bottom of every chapter MDX file.

### Rendered preview gifs

Each chapter has at least one inline `<DemoGif>` showing the rendered config at that stage. Chapter 3 and Chapter 4 get 2-3 gifs each to make the visual progression land.

Source TOMLs live in `docs/site/demos-long/tutorial-NN-<topic>.toml`; outputs land at `docs/site/public/demos-long/tutorial-NN-<topic>.gif`. Rendered with `make render-long-demo NAME=tutorial-NN-<topic>`. Estimated total: 8-10 new demo TOMLs across the five chapters.

Each demo TOML carries a `# render-duration: <N>` comment so re-renders are deterministic. The `make render-long-demos` target picks these up automatically (per the existing convention in `docs/site/demos-long/`).

## Per-chapter scope

### Chapter 1: Setup

**Goal:** reader has the repo cloned, dev deps installed, and renders a bundled showcase config to a preview gif — sees what they're building toward.

**Length:** ~80-120 lines of MDX.

**Content arc:**
1. Prerequisites callout: git, Python 3.13+, `uv`, `make`. Single-paragraph.
2. Clone + `make dev` walkthrough. Same commands as `getting-started.mdx` but with more "here's what this is doing" context.
3. Render the bundled `config.bigsign.moonbunny.example.toml` (creates a new file in `config/` — see Asset story below) to a preview gif via `make render-demo CONFIG=config/config.bigsign.moonbunny.example.toml OUT=preview.gif`. Inline `<DemoGif>` shows the rendered result.
4. "What you're going to build" mini-section: this gif is your destination. Over five chapters you'll build a simpler version of this from scratch.
5. Closing: a sentence on what's NOT covered (hardware deploy → Hardware sidebar group).

**New TOML:** `config/config.bigsign.moonbunny.example.toml` (committed to the repo; referenced by Chapter 1's render command). Realistically-shaped moonbunny config — uses the existing pinned demo content as a base.

**New gif:** `tutorial-01-setup.gif` rendered from the moonbunny example.

**Links out to:** Hardware → Building your own (for users who pause here to plan their physical sign).

### Chapter 2: Your first config

**Goal:** reader writes a minimal config from scratch — a single scrolling message — validates it, renders it.

**Length:** ~150-200 lines of MDX.

**Content arc:**
1. Reset block: copy this `[display]` block into `config/config.toml`. Explain each knob briefly (rows, cols, chain, default_scale). Call out which knobs are "hardware-only, ignore for now" (brightness, gpio_slowdown, hardware_mapping if present in the snippet).
2. Add the smallest possible playlist: one `forever_scroll` section with one `message` widget that says "Welcome to Moonbunny". Walk through the TOML line by line.
3. Run `led-ticker validate config/config.toml`. Show expected output ("No issues found"). Mention what an error would look like.
4. Render with `make render-demo CONFIG=config/config.toml OUT=preview.gif`. Inline gif shows the scrolling welcome message.
5. Make a change (swap the text, change `font_color`) and re-render. The point: edit-validate-render is the loop.

**New TOML:** `docs/site/demos-long/tutorial-02-first-config.toml` (matches the chapter's final config state).

**New gif:** `tutorial-02-first-config.gif`.

**Links out to:** Concepts → Sections and modes, Widgets → message.

### Chapter 3: Multi-widget sign

**Goal:** reader expands the single-message config into a multi-section, multi-widget config that introduces sections, modes, the `two_row` widget, and (as a major sub-section) hi-res emoji on a `two_row` top row.

**Length:** ~300-400 lines of MDX. This is the longest chapter and it earns it — three distinct sub-sections build on each other.

**Content arc:**

1. **Reset block.**

2. **Sections and modes intro.** Explain what a section is (a group of widgets + a mode). Walk through the three modes (`forever_scroll`, `swap`, `infini_scroll`) with one sentence each describing when to use it. Demonstrate by adding a SECOND section to the config — `swap` mode with two `message` widgets ("Open daily" / "10am-8pm"). Render. One gif shows the panel cycling through the two sections.

3. **Adding more widget types.** Add a `countdown` widget for a "Summer Camps" countdown. Add a `weather` widget for "Brooklyn, NY" (with a callout: weather needs `WEATHERAPI_KEY`; if you don't have one yet, swap in another `message` widget for now — the layout reads the same). Render.

4. **The `two_row` widget — basic.** Introduce a `two_row` section: held top row (a handle), scrolling bottom row (promo copy). Use BDF `5x8` font for both rows. `scale = 1` at this stage. Render. Walk through how the band split works (top half / bottom half of the canvas).

5. **`two_row` with hi-res emoji — the hard configuration case.** This is the dedicated sub-section the brainstorming flagged as worth calling out.
   - Goal: add `:instagram: @moonbunny` to `top_text`, render the hi-res Instagram sprite (the colorful 32×32 one, not the 8×8 fallback).
   - Required changes: bump section to `scale = 2`, set `content_height = 24` and `top_row_height = 16`.
   - The math, walked through with concrete numbers:
     - Why `scale = 2`: the hi-res Instagram sprite is 32 real pixels tall; at scale=2 it's 16 logical pixels and fits a 16-row top band. (At scale=4 the logical canvas is only 64 wide — handles like `@moonbunny` clip.)
     - Why `content_height = 24`: the ceiling rule is `content_height × scale ≤ panel_h_real`. Bigsign panel_h = 64, so at scale=2 the ceiling is 32. We pick 24 to leave breathing room above and below.
     - Why `top_row_height = 16`: matches the 16-logical-row hi-res sprite. Bottom row gets the remainder = 8 rows, perfect for `5x8` BDF text.
   - Inline note on the row_layout fix (PR #43, just merged): as of the current main, the hi-res sprite anchors at the top of its band automatically. Older docs / configs may show `top_emoji_y_offset = -4`; that's no longer needed but doesn't hurt to keep if you see it in third-party configs.
   - Render. Show the inline gif. Compare with the lo-res fallback variant (`scale = 1`) side-by-side — make the "this is why bigsign + hi-res matters" punch land.

**New TOMLs:** `tutorial-03a-sections.toml`, `tutorial-03b-multi-widget.toml`, `tutorial-03c-two_row-basic.toml`, `tutorial-03d-two_row-hires.toml`. Four TOMLs because the chapter has four distinct rendering checkpoints.

**Links out to:** Concepts → Sections and modes (deep dive), Widgets → message / countdown / weather / two_row, Pitfalls → Rule 6 (`two_row` at scale=4).

### Chapter 4: Custom branding

**Goal:** reader upgrades their config with a brand font (Atkinson Hyperlegible) and a brand logo image. Revisits the Chapter 3 `two_row` with the new font to close the loop.

**Length:** ~250-350 lines of MDX.

**Content arc:**

1. **Reset block.**

2. **Adding a custom font.** Download Atkinson Hyperlegible from the Braille Institute (link out). Save the `.otf` files to `config/fonts/`. Brief callout on why we picked this font (designed for legibility at distance, OFL-licensed, free for any use — perfectly fits LED signs).

3. **Using the font in a widget.** Update the `two_row` section from Chapter 3 to use `top_font = "AtkinsonHyperlegible-Bold"` and `top_font_size = 22` (or comparable). Render. Walk through the `font_threshold` knob — explain when it matters (thin-stroked fonts need ~80 to avoid edge-clipping) and confirm Atkinson at default 128 looks fine.

4. **Adding a logo image.** Add an `image` widget to a new `swap` section. Use the existing `config/assets/moon-transparent.png` (already in the repo) since "a moon" reads as the moonbunny logo motif. Walk through `path`, `fit = "pillarbox"`, `image_align`, `hold_seconds`. Render.

5. **Combining text + image.** Use the `bottom_text` field on the image widget to overlay scrolling promo copy. Walk through the two-row text overlay mode on image widgets (callback to Chapter 3's `two_row` — same layout primitives, different widget). Render.

**New TOMLs:** `tutorial-04a-font.toml`, `tutorial-04b-image.toml`, `tutorial-04c-image-with-text.toml`.

**Links out to:** Concepts → Fonts, Widgets → image, Assets → Emoji (for inline emoji compatibility with custom fonts).

### Chapter 5: Polish & deploy

**Goal:** reader adds finishing touches (transitions, border effects) and gets a "next step" pointer for hardware deploy.

**Length:** ~150-200 lines of MDX.

**Content arc:**

1. **Reset block.**

2. **Transitions.** Add a `[transitions]` block with `default = "wipe_left"` and `between_sections = "dissolve"`. Render — the panel now transitions between widgets smoothly. Touch briefly on alternatives (`push_left`, `nyancat`, etc.); link out to the Transitions group for the full catalogue.

3. **Border effects.** Add `border = "rainbow"` to one of the `message` widgets. Render. Explain that border + transition + font effects can all compose on a single widget — pointer to Concepts → Borders for the full effect catalogue.

4. **Final preview gif** (the destination from Chapter 1).

5. **Deploying to a Pi.** This section is intentionally short. Three lines describing the deploy path (`docker compose up`, mount your `config/` directory at `/code/config`, see Hardware sidebar group) and a prominent `<RelatedPages>` cluster pointing at Hardware → Bigsign / Smallsign / Building your own.

**New TOMLs:** `tutorial-05a-transitions.toml`, `tutorial-05b-final.toml`.

**Links out to:** Transitions group, Concepts → Borders, Hardware group.

## Asset story

### Custom font (Atkinson Hyperlegible)

NOT committed to the repo (the `.otf` files are gitignored). Chapter 4 has the reader download it from the Braille Institute website (link to the official download page) and drop the `.otf` files into `config/fonts/`. The chapter walks through this in ~10 lines of prose with the exact download URL.

Why not ship it: pedagogy. The "here's how custom fonts work" lesson lands harder when the reader actually does the drop-in. Also avoids the maintenance burden of tracking a third-party font in the repo.

**For rendering the tutorial's preview gifs (maintainer-local workflow):**

The renderer's hi-res font loader anchors to `<config.toml dir>/fonts/` (per CLAUDE.md's font search order). For tutorial demos at `docs/site/demos-long/tutorial-04-*.toml`, that anchor is `docs/site/demos-long/fonts/`. The plan:

1. Create `docs/site/demos-long/fonts/` directory in the repo.
2. Add a `docs/site/demos-long/fonts/.gitignore` containing `*.otf` and `*.ttf` (or extend the top-level `.gitignore` — pick whichever matches existing convention).
3. The maintainer (us) downloads Atkinson Hyperlegible Regular and Bold to that directory locally — same drop-in workflow the reader does in their `config/fonts/`.
4. `make render-long-demo NAME=tutorial-04-font` (etc.) finds the font via the standard anchor and renders the gif.
5. The rendered gif IS committed to `docs/site/public/demos-long/` (this matches existing `render-long-demos` convention: source TOML committed, font assets NOT committed, output gif committed).

This is consistent with how long demos already work (`make render-long-demos` is documented as "local only, output committed"). Cloudflare's auto-build doesn't re-render demos, so the missing font in CI is never an issue.

Trade-off: a reader who skips Chapter 4 won't have the font file in their working tree if they jump to Chapter 5's reset block. The reset block for Chapter 5 can either (a) include the download instructions again, or (b) fall back to a bundled font so the chapter still runs without the font. **Decision:** option (b). Chapter 5's reset block uses `Inter-Bold` (already bundled) so it's self-contained; an inline callout points back to Chapter 4 for the Atkinson version.

### Custom image (moon-transparent.png)

Already in the repo at `config/assets/moon-transparent.png`. Re-used by Chapter 4 — no new asset committed.

### The `config.bigsign.moonbunny.example.toml` reference config

NEW file committed to the repo at `config/config.bigsign.moonbunny.example.toml`. This is the "polished destination" config that Chapter 1 renders so the reader sees what they're building toward. It should be a realistic moonbunny-themed bigsign config that exercises the same concepts the tutorial covers: multi-section, `two_row` with hi-res emoji, image widget, custom font (Atkinson — but with a fallback to Inter-Bold for users who haven't done the font drop-in yet), transitions, border effects.

**Critical:** this file's `font` references must resolve cleanly EITHER with Atkinson Hyperlegible OR without it. Options:
- (a) Use `Inter-Bold` (already bundled). Chapter 1 reads cleanly with no font drop-in needed. Chapter 4 then walks through SWAPPING Inter for Atkinson.
- (b) Use Atkinson and ship a fallback path.

**Decision:** option (a). Inter-Bold for the Chapter 1 example config. Pedagogically cleaner: Chapter 1 doesn't ask the reader to do font setup, and Chapter 4's payoff is "swap one font reference for another and re-render — that's all it takes to rebrand."

## Render generation plan

Total new TOMLs in `docs/site/demos-long/`:
- `tutorial-01-setup.toml` — renders the `config/config.bigsign.moonbunny.example.toml`
- `tutorial-02-first-config.toml`
- `tutorial-03a-sections.toml`
- `tutorial-03b-multi-widget.toml`
- `tutorial-03c-two_row-basic.toml`
- `tutorial-03d-two_row-hires.toml`
- `tutorial-04a-font.toml`
- `tutorial-04b-image.toml`
- `tutorial-04c-image-with-text.toml`
- `tutorial-05a-transitions.toml`
- `tutorial-05b-final.toml`

11 TOMLs. Each TOML carries a `# render-duration:` comment. Outputs land in `docs/site/public/demos-long/` (committed to the repo, served by Astro).

Rendering uses `make render-long-demo NAME=tutorial-NN-<topic>` (existing target, no new Make plumbing needed).

For the plan: render each demo, check the gif visually with the Read tool to confirm the rendered output matches the chapter's prose, iterate on render-duration if the cycle is cut off mid-content.

## Cross-linking strategy

Each chapter ends with a `<RelatedPages>` cluster listing 3-5 deep-dive pages most relevant to that chapter's content. The chapters are NOT trying to be reference material — they hand the reader off to the existing reference pages where the deep details live.

Pattern:
- Chapter 1 → Hardware / Building your own; Getting started (for the terse alt path)
- Chapter 2 → Concepts / Sections and modes; Widgets / message; Tools / validate
- Chapter 3 → Concepts / Sections and modes; Widgets / two_row; Pitfalls (esp. Rule 6 + the `content_height` ceiling discussion); Reference / Config options
- Chapter 4 → Concepts / Fonts; Widgets / image; Assets / Emoji
- Chapter 5 → Transitions group; Concepts / Borders; Hardware group

Inline links throughout the prose where a concept first comes up, also pointing at the relevant reference page.

## Validation strategy

After each chapter is drafted:
- Run `make docs-build` — confirms the MDX parses and the build is clean.
- Render every TOML the chapter references — confirms the demos actually produce the claimed gifs.
- Read the rendered gifs (PIL frame extraction → Read tool on PNG) to confirm visual content matches the chapter's prose.
- Run `make docs-lint` — prettier + astro check.

If a chapter's prose says "now the panel shows X" and the rendered gif doesn't show X, the chapter is wrong. The plan should include this as a per-chapter validation step.

After all five chapters are drafted:
- Spot-check the sidebar IA in the rendered HTML.
- Click through Prev / Next nav from Chapter 1 to Chapter 5 to confirm the chain holds.
- Spot-check the `<details>` reset blocks render correctly (they should be folded by default).

## Out of scope

These are explicitly NOT in this tutorial. Each has a clear home elsewhere in the docs:

- **Hardware deploy** — owned by the Hardware sidebar group (`/hardware/bigsign/`, `/hardware/smallsign/`, `/hardware/building-your-own/`). Chapter 5 links out.
- **Smallsign-specific content** — owned by `/hardware/smallsign/` + the existing widget docs that note smallsign caveats. Tutorial is bigsign-only.
- **Live-data widgets in depth (RSS / Coinbase / etc.)** — owned by `/widgets/*/`. Tutorial uses `weather` briefly in Chapter 3 but otherwise stays away from live-data widget setup details (API keys, polling cadence).
- **The `creating-a-config` skill** — separate authoring path (Claude-assisted). Tutorial is the unassisted-but-hand-held path. Could cross-link from Tutorial → `/tools/creating-a-config/` ("if you'd rather have Claude do this for you, see ...") but that's a small editorial decision, not a structural one.
- **Webconfig browser UI** — feature deferred (separate brainstorm session). Tutorial doesn't reference it.

## Risks and mitigations

1. **Chapter 3 gets too long.** Four sub-sections with four renders is ambitious. Mitigation: structure with clear `## H2` boundaries and 2-3 lines of "what just happened" between sub-sections so the reader has natural pause points. If review feedback flags it as too dense, split into 3a (sections + multi-widget) and 3b (two_row + hi-res emoji) as separate chapters — small refactor.

2. **Demo TOMLs drift from chapter prose.** Mitigation: the demos and the MDX should be edited together in each chapter's commit. The plan's per-chapter validation step (render + visually inspect) catches drift before it ships.

3. **Atkinson Hyperlegible download instructions go stale.** Mitigation: link to the Braille Institute's main project page (`https://brailleinstitute.org/freefont`) rather than a deep URL — that page survives URL restructuring. Verify the link before shipping.

4. **`config.bigsign.moonbunny.example.toml` becomes an unmaintained reference config.** Mitigation: it gets exercised by the Chapter 1 render every time we re-render demos. Treat it as a tested asset, not a docs example.

5. **Tutorial's bigsign-only stance leaves smallsign users feeling ignored.** Mitigation: a small "smallsign tutorial?" callout at the top of Chapter 1 acknowledging that the tutorial is bigsign-targeted because hi-res emoji and image widgets work best at bigsign resolution, and linking smallsign-specific pages for users on that hardware. Doesn't try to support both — just acknowledges the choice.

## What this design is NOT trying to do

- Replace `getting-started.mdx` — that page stays as-is.
- Be a reference. It's a narrative walk, not a lookup surface.
- Cover every widget — the reader meets ~5-6 widget types out of the ~12 available. Others are linked.
- Be exhaustive on transitions / concepts — those have their own dedicated sidebar groups.
- Document the hardware bring-up — owned by the Hardware sidebar group.
