# Docs Site Panel-Review Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land the ship-blocking fixes + voice/IA polish from the four-persona docs site review (PR #29's `/review-docs` panel run on 2026-05-09).

**Architecture:** Two PRs. **PR 1 (Tasks 1-4)** is the orientation + structural-defect bundle: Getting Started no-hardware path + Pitfalls page populate + double-`<h1>` accessibility bug fix. These are the showstoppers (PM + User + UX convergent) plus a verifiable a11y/SEO defect. **PR 2 (Tasks 5-11)** is the voice + IA polish bundle: sidebar reorder + frame-counters relocation + concepts pages voice cleanup + heading renames + concepts/display dedup + Tools group label + hardware-page newcomer polish (HUB75 def, cost estimates, `pixel_mapper_config` example) + Rule 14 label fix. The two PRs touch disjoint file sets — they can run sequentially or in parallel worktrees, but sequential is cleaner for review.

**Tech stack:** Astro Starlight v0.39.x docs site at `docs/site/`. MDX content under `docs/site/src/content/docs/`. Reusable components at `docs/site/src/components/`. Markdown fact-packs under `docs/content-source/`. Build via `make docs-build` or `pnpm --dir docs/site run build`. Lint via `make docs-lint`.

**Worktree convention:** Per project memory, both PRs land via worktrees + PRs (no direct push to `main`). Use `EnterWorktree name="docs-panel-review-pr1"` for PR 1; after PR 1 merges, `EnterWorktree name="docs-panel-review-pr2"` for PR 2.

---

## File map

### PR 1 — orientation + structural defects

| File | Action | Why |
|---|---|---|
| `docs/site/src/content/docs/getting-started.mdx` | Modify | Add no-hardware callout, link to `/hardware/building-your-own/`, split Run section by environment, add Next-steps block |
| `docs/site/src/content/docs/pitfalls.mdx` | Modify | Render every fact-pack rule via `<DecisionRule id="N" />` instead of just rule 14 |
| `docs/site/src/components/OptionsTable.astro` | Modify | Strip leading `# Heading` line from fact-pack markdown before `marked.parse` |
| `docs/site/src/components/DecisionRule.astro` | Modify | Same strip — the markdown's `# Rule N: ...` collides with the rule-badge div |

### PR 2 — voice + IA polish

| File | Action | Why |
|---|---|---|
| `docs/site/astro.config.mjs` | Modify | Reorder sidebar: Home → Getting Started → Widgets → Transitions → Concepts → Tools → Hardware → Reference. Pin `message` first in Widgets. Drop `concepts/frame-counters` from Concepts (it moves to Reference). |
| `docs/site/src/content/docs/concepts/frame-counters.mdx` → `docs/site/src/content/docs/reference/frame-counters.mdx` | `git mv` | Move out of beginner-facing Concepts to Reference per UX finding F2 |
| `docs/site/src/content/docs/concepts/borders.mdx` | Modify | Update internal cross-link from `/concepts/frame-counters/` → `/reference/frame-counters/` |
| `docs/site/src/content/docs/concepts/animations.mdx` | Modify | Same cross-link update |
| (any other page linking to `concepts/frame-counters`) | Modify | Same — discovered via grep |
| `docs/site/src/content/docs/concepts/color-providers.mdx` | Modify | 2 paragraph rewrites (opening + "Picking the right provider") + heading rename |
| `docs/site/src/content/docs/concepts/display.mdx` | Modify | Opening paragraph rewrite + drop the duplicate full `[display]` table (link to `/reference/config-options/` instead) |
| `docs/site/src/content/docs/reference/frame-counters.mdx` (post-move) | Modify | Opening paragraph rewrite |
| `docs/site/src/content/docs/concepts/sections-and-modes.mdx` | Modify | Heading rename: `## Picking a mode` → `## Which mode to use` |
| `docs/site/src/content/docs/transitions/index.mdx` | Modify | Heading rename: `## Picking a transition` → `## Which to use` |
| `docs/site/src/content/docs/tools/creating-a-config.mdx` | Modify | Heading rename: `## Validation philosophy` → `## How violations are surfaced`. Rewrite the section's first paragraph to drop "flag-and-ask discipline" jargon |
| `docs/site/src/content/docs/widgets/message.mdx` | Modify | Replace bare `<DecisionRule id="14" />` with descriptive `### Typewriter is single-row only` heading + the rule callout below it |
| `docs/site/src/content/docs/hardware/smallsign.mdx` | Modify | Define HUB75 once in the BOM section. Add cost ballpark to BOM. |
| `docs/site/src/content/docs/hardware/bigsign.mdx` | Modify | Add cost ballpark. Add a worked `pixel_mapper_config` example for a simple 2×2 layout in the Pitfalls section. |

---

## Per-task contract

Every task ends with:

1. `cd docs/site && pnpm run lint 2>&1 | tail -3` — must pass clean (0 errors / 0 warnings / 0 hints). If prettier reformats, re-stage and continue.
2. `cd docs/site && pnpm run build 2>&1 | tail -3` — must build expected page count (start: 39 pages; PR 2 keeps 39 since `frame-counters` just moves URLs).
3. `git add <files> && git commit -m "..."` with the commit message specified in the task.

Tests live in `tests/` and are unaffected by docs-only changes — no need to run `make test` per task. PR 1 final integration runs the full Python suite as a sanity check; PR 2 final integration runs lint + build only.

---

# PR 1 — Orientation + structural defects

Worktree: `docs-panel-review-pr1`

## Task 1: Getting Started orientation overhaul

**Files:**
- Modify: `docs/site/src/content/docs/getting-started.mdx` (entire file is ~50 lines; rewrite in place)

This task addresses the **showstopper** flagged by PM + User + UX: the page reads as if a Pi is mandatory, doesn't link to the existing software-first path, and its sequential "next" link drops users into `concepts/animations` (theory) instead of `widgets` or `sections-and-modes` (practice).

- [ ] **Step 1: Read the current state**

```bash
cat docs/site/src/content/docs/getting-started.mdx
```

Confirm structure: frontmatter + intro paragraph + Install + Configure + Validate + Run sections, no Next steps block.

- [ ] **Step 2: Replace the file with the new content**

Write the full replacement file:

````mdx
---
title: Getting started
description: Install led-ticker, point it at a config, watch a sign light up — with or without hardware on hand.
---

import RelatedPages from "../../components/RelatedPages.astro";

led-ticker drives RGB LED matrix panels from a Raspberry Pi via a TOML
config — RSS, weather, custom messages, animated transitions, and more.
You don't need any hardware to start: the same engine runs against a
test stub and renders configs to GIFs you can preview on a laptop.

:::tip[Don't have hardware yet?]
Skip the Pi for now. After `make dev`, run `make render-demo CONFIG=config/config.example.toml OUT=preview.gif`
to render any config to a GIF at native panel resolution.
See [Building your own](/hardware/building-your-own/) for the full
software-first workflow.
:::

## Install

```bash
git clone https://github.com/JamesAwesome/led-ticker.git
cd led-ticker
make dev
```

`make dev` installs the Python dependencies via `uv` and sets up the
test stub for laptop development. No `rgbmatrix` C library required at
this stage — it's only needed on the actual Pi.

## Configure

Pick the example config matching what you have (or want to build):

```bash
# Smallsign reference: Pi 4 + 5x32x16 panels = 160x16 logical canvas
cp config/config.example.toml config/config.toml

# Bigsign reference: Pi 5 + 8x P3 32x64 panels = 256x64 logical canvas
cp config/config.bigsign.example.toml config/config.toml
```

Not sure which fits your setup? See
[Choosing a sign size](/hardware/building-your-own/#choosing-a-sign-size)
— anything between the two reference builds works; you'll edit the
`[display]` block to match your panels.

A config is a list of **sections**, each containing **widgets** and a
**mode** (`forever_scroll`, `swap`, or `infini_scroll`). To understand
what to put in `config.toml` before editing, skim
[Sections and modes](/concepts/sections-and-modes/) and the
[message widget](/widgets/message/) page — the two most-used building
blocks.

## Validate

```bash
led-ticker validate config/config.toml
```

A clean config prints `No issues found.` and exits 0. Errors and
warnings print with their fix suggestions — see
[`led-ticker validate`](/tools/validate/) for details and the
[Pitfalls](/pitfalls/) page for the full rule list.

## Run

Pick the path that matches where you are:

```bash
# Local laptop preview (no hardware needed):
make render-demo CONFIG=config/config.toml OUT=preview.gif
open preview.gif   # macOS; xdg-open on Linux

# On the Pi (real panels):
led-ticker --config config/config.toml

# On the Pi via Docker (production deploy):
docker compose up -d --build
```

The `led-ticker` binary requires the `rgbmatrix` C library and real
hardware — running it on macOS or a non-Pi Linux machine will fail at
import. Use `make render-demo` for everything pre-deployment.

## Next steps

- **Build a config from scratch:** [Sections and modes](/concepts/sections-and-modes/) → [Widgets](/widgets/) → [Transitions](/transitions/)
- **Buy / build the hardware:** [Building your own](/hardware/building-your-own/) → [Smallsign](/hardware/smallsign/) or [Bigsign](/hardware/bigsign/)
- **Reference:** [`[display]` and section knobs](/reference/config-options/) · [CLI](/reference/cli/)

<RelatedPages slugs={["concepts/sections-and-modes", "widgets/message", "hardware/building-your-own"]} />
````

- [ ] **Step 3: Lint + build**

```bash
cd docs/site && pnpm run lint 2>&1 | tail -3
cd docs/site && pnpm run build 2>&1 | tail -3
```

Expected: 0 lint errors, 39 pages built.

- [ ] **Step 4: Verify rendered HTML resolves the new links**

```bash
test -f docs/site/dist/getting-started/index.html && echo OK
grep -c '/hardware/building-your-own/' docs/site/dist/getting-started/index.html  # ≥1
grep -c 'render-demo' docs/site/dist/getting-started/index.html                     # ≥2
```

- [ ] **Step 5: Commit**

```bash
git add docs/site/src/content/docs/getting-started.mdx
git commit -m "docs: getting-started — surface no-hardware path, fix orientation flow

Three convergent panel-review findings (PM showstopper, User bounce,
UX wrong-next-link) all rooted in this page:

  - The opening line implied a Pi was mandatory, sending laptop-only
    visitors away before they reached the software-first path that
    /hardware/building-your-own/ already documents.
  - The Configure step said \"copy an example matching your hardware\"
    with no link to help users pick.
  - The Run step listed Pi + Docker side-by-side with no laptop
    option, so a developer who tried led-ticker on macOS hit an
    import error with no signposting.
  - There was no explicit Next-steps block, so the sidebar's
    sequential next-link sent users into concepts/animations
    (frame-timing theory) before they'd written a config.

Rewrite the page end-to-end: add a tip callout for no-hardware path,
link Configure step to the hardware sizing guide and to
sections-and-modes / widgets/message for what-goes-in-config.toml,
split Run into laptop / Pi / Docker with the right command for each,
add a Next-steps block at the bottom that points at the right second
page for each persona (config-builder vs hardware-buyer vs reference)."
```

## Task 2: Populate the Pitfalls page

**Files:**
- Modify: `docs/site/src/content/docs/pitfalls.mdx`

UX called the page "a near-empty stub"; User said "almost empty"; PM noted the "Rule 14" label problem. The fact-pack files for rules 3, 6, 7, 8, 12, and 14 already exist at `docs/content-source/rules/`; the page only renders rule 14. Render all six.

- [ ] **Step 1: Confirm fact-pack files**

```bash
ls docs/content-source/rules/
```

Expected output:

```
03-scroll-plus-stretch.md
06-two-row-at-scale-4.md
07-text-x-offset-with-scroll.md
08-hold-seconds-too-short.md
12-animation-on-wrong-widget.md
14-typewriter-on-image.md
```

- [ ] **Step 2: Replace the file**

Write the full replacement:

```mdx
---
title: Pitfalls
description: The validator's decision rules — what fires when, what you'll see, how to fix it.
---

import DecisionRule from "../../components/DecisionRule.astro";

This page lists every decision rule the validator checks. Each rule
has a **DETECT** clause (when it fires), a **SYMPTOM** clause (what
you see on the panel), and a **FIX** clause. Run
[`led-ticker validate`](/tools/validate/) on your `config.toml` to
check it against all of them automatically.

## Hard rules (errors)

Errors block the ticker from starting. Fix all of these before
deploying.

<DecisionRule id="3" />

<DecisionRule id="7" />

<DecisionRule id="8" />

<DecisionRule id="12" />

<DecisionRule id="14" />

## Soft rules (warnings)

Warnings don't block the ticker but flag a likely rendering quirk.
Worth resolving before you deploy.

<DecisionRule id="6" />
```

- [ ] **Step 3: Lint + build**

```bash
cd docs/site && pnpm run lint 2>&1 | tail -3
cd docs/site && pnpm run build 2>&1 | tail -3
```

Expected: 0 lint errors, 39 pages built. The `<DecisionRule>` component throws if a rule id has no matching fact-pack file; build succeeding confirms all six render.

- [ ] **Step 4: Verify all six rule callouts render**

```bash
for n in 3 6 7 8 12 14; do
  grep -c "data-rule-id=\"$n\"" docs/site/dist/pitfalls/index.html | grep -q 1 \
    && echo "OK rule $n" || echo "MISSING rule $n"
done
```

Expected: 6 OK lines.

- [ ] **Step 5: Commit**

```bash
git add docs/site/src/content/docs/pitfalls.mdx
git commit -m "docs: pitfalls — render all six fact-pack rules, not just rule 14

UX + User panel reviews both flagged the page as a near-empty stub;
the docs/content-source/rules/ directory has six fact-packs but only
rule 14 was rendered. Add the other five (3, 6, 7, 8, 12) and group
them into Hard (errors) vs Soft (warnings) sections so a reader
arriving here after running \`led-ticker validate\` sees the full
ruleset rather than wondering if the page is broken."
```

## Task 3: Fix the double-`<h1>` accessibility bug

**Files:**
- Modify: `docs/site/src/components/OptionsTable.astro`
- Modify: `docs/site/src/components/DecisionRule.astro`

UX finding F3: every page using `<OptionsTable>` emits two `<h1>` tags (the page's frontmatter title + the markdown fact-pack's `# Heading`). Same for `<DecisionRule>` (page title + `# Rule N: ...`). Fix at the component level by stripping the leading `# heading` line from fact-pack markdown before `marked.parse`.

- [ ] **Step 1: Read the current OptionsTable**

```bash
cat docs/site/src/components/OptionsTable.astro
```

The relevant block is:

```ts
const raw = files[lookupKey];
if (!raw) {
  throw new Error(...);
}
const html = marked.parse(raw as string);
```

- [ ] **Step 2: Strip the leading h1 in OptionsTable**

Replace the parse line with a strip-then-parse:

```ts
const raw = files[lookupKey];
if (!raw) {
  throw new Error(
    `OptionsTable: source "${source}" not found at ${lookupKey}. ` +
      `Available: ${Object.keys(files).join(", ")}`,
  );
}

// Strip a leading `# Heading` from the fact-pack markdown — the
// surrounding MDX page already has an <h1> from frontmatter.title,
// and emitting a second h1 from the fact-pack breaks document
// structure for screen readers and SEO. The fact-pack heading was
// vestigial from when the .md files were viewed in isolation; the
// `## Options` heading on the MDX page above the <OptionsTable />
// already provides scannable context.
const stripped = (raw as string).replace(/^#\s+[^\n]*\n+/, "");
const html = marked.parse(stripped);
```

- [ ] **Step 3: Read the current DecisionRule**

```bash
cat docs/site/src/components/DecisionRule.astro
```

- [ ] **Step 4: Strip the leading h1 in DecisionRule**

Same pattern. Replace the parse line:

```ts
const raw = files[matchKey];

// Strip the fact-pack's leading `# Rule N: ...` heading — the
// component's own .rule-badge div above this content already shows
// the rule number, and the surrounding page's <h2> already frames
// the section. The markdown h1 was a third hierarchy level that
// broke screen-reader document structure.
const stripped = (raw as string).replace(/^#\s+[^\n]*\n+/, "");
const html = marked.parse(stripped);
```

- [ ] **Step 5: Lint + build**

```bash
cd docs/site && pnpm run lint 2>&1 | tail -3
cd docs/site && pnpm run build 2>&1 | tail -3
```

Expected: 0 lint errors, 39 pages built.

- [ ] **Step 6: Verify the fix removed extra h1s**

```bash
# Widget page should now have exactly 1 h1 (the page title)
grep -c '<h1' docs/site/dist/widgets/message/index.html
# Pitfalls page should now have exactly 1 h1 (the page title), not 7 (title + 6 rules)
grep -c '<h1' docs/site/dist/pitfalls/index.html
```

Expected: both output `1`.

- [ ] **Step 7: Commit**

```bash
git add docs/site/src/components/OptionsTable.astro docs/site/src/components/DecisionRule.astro
git commit -m "docs: fix double-h1 in OptionsTable + DecisionRule components

UX panel review F3: every page using <OptionsTable> emitted a second
<h1> from the fact-pack markdown (\"# Message Widget Options\"), and
<DecisionRule> added a third (\"# Rule 14: ...\"). Pages with three
h1 tags break screen-reader document structure and confuse SEO
crawlers about page hierarchy.

Fix at the component level: strip the leading \`# Heading\` line from
the fact-pack markdown before passing to \`marked.parse\`. The
fact-pack's h1 was vestigial from when the .md files were viewed in
isolation; the MDX page's own h2 (\"## Options\") and DecisionRule's
.rule-badge div already provide the framing those h1s were doing.

Verified on widgets/message (now 1 h1) and pitfalls (now 1 h1, not
7). No content moved or hidden — only the structural duplication is
removed."
```

## Task 4: PR 1 final integration

- [ ] **Step 1: Full lint pass**

```bash
cd docs/site && pnpm run lint 2>&1 | tail -3
```

Expected: 0 errors / 0 warnings / 0 hints.

- [ ] **Step 2: Full build**

```bash
cd docs/site && pnpm run build 2>&1 | tail -5
```

Expected: 39 pages built, "Complete!".

- [ ] **Step 3: Run the Python suite as a sanity check**

```bash
PYTHONPATH=tests/stubs uv run pytest -q 2>&1 | tail -3
```

Expected: 1439 passed, 2 skipped (or whatever the current baseline is — confirm no regressions, since docs-only changes shouldn't touch this).

- [ ] **Step 4: Verify expected dist files**

```bash
test -f docs/site/dist/getting-started/index.html && echo OK getting-started
test -f docs/site/dist/pitfalls/index.html && echo OK pitfalls
grep -q 'data-rule-id="3"' docs/site/dist/pitfalls/index.html && echo OK rule-3-rendered
grep -q 'render-demo' docs/site/dist/getting-started/index.html && echo OK no-hardware-callout
```

Expected: 4 OK lines.

- [ ] **Step 5: Push and open PR**

```bash
git push -u origin worktree-docs-panel-review-pr1
gh pr create --title "docs: panel-review fixes — orientation + structural defects" --body "$(cat <<'EOF'
## Summary

First of two PRs addressing the four-persona panel review (run via /review-docs on 2026-05-09). Bundles the showstopper findings (PM + User + UX convergent) and the verifiable a11y/SEO defect.

## Changes

- **Getting Started overhaul** — surfaces the no-hardware path that already exists at `/hardware/building-your-own/`, adds explicit Next-steps block, splits Run section by environment (laptop / Pi / Docker), links Configure step to sections-and-modes + widgets for "what goes in config.toml".
- **Pitfalls page populate** — renders all six fact-pack rules (3, 6, 7, 8, 12, 14) grouped Hard / Soft, instead of rule 14 in isolation.
- **Double-h1 component fix** — `OptionsTable.astro` and `DecisionRule.astro` strip the leading `# heading` line from fact-pack markdown before parsing, so widget and pitfalls pages emit one `<h1>` (the page title) instead of 2-7.

## Test plan

- [x] `pnpm run lint` clean (0/0/0)
- [x] `pnpm run build` builds 39 pages
- [x] All six rule callouts render on `/pitfalls/`
- [x] `/widgets/message/` and `/pitfalls/` each emit exactly one `<h1>`
- [x] Python test suite passes unchanged

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

# PR 2 — Voice + IA polish

Worktree: `docs-panel-review-pr2` (start AFTER PR 1 merges to main, or in a parallel worktree if you accept the rebase risk — the file sets are disjoint so conflicts are unlikely).

## Task 5: Sidebar reorder + pin `message` first in Widgets

**Files:**
- Modify: `docs/site/astro.config.mjs`

UX finding F1 + F7 + F2: current sidebar puts Concepts (chapter-2 reference) ahead of Widgets (chapter 1.5 actionable), the Widgets group autogenerates alphabetically so `message` (the most-used widget) is buried at position 7, and `concepts/frame-counters` is in beginner-facing Concepts despite explicitly saying "most users never need this." This task does the sidebar half (the file move happens in Task 6).

- [ ] **Step 1: Read current sidebar**

```bash
sed -n '20,55p' docs/site/astro.config.mjs
```

- [ ] **Step 2: Replace the sidebar array**

Find the `sidebar: [` block and replace its contents (the entries between `sidebar: [` and the matching `],`) with this exact ordering. The Widgets group becomes explicit so `message` pins to the top; the Concepts group stays autogenerate-from-directory but `frame-counters.mdx` will move out in Task 6.

```js
sidebar: [
  { label: "Home", link: "/" },
  { label: "Getting started", link: "/getting-started/" },
  {
    label: "Widgets",
    items: [
      // Pinned: message is the most-used widget; surface it first
      // rather than letting the autogenerate sort bury it
      // alphabetically at position 7.
      { label: "message", link: "/widgets/message/" },
      { label: "All widgets (overview)", link: "/widgets/" },
      { label: "countdown", link: "/widgets/countdown/" },
      { label: "two_row", link: "/widgets/two_row/" },
      { label: "weather", link: "/widgets/weather/" },
      { label: "rss_feed", link: "/widgets/rss_feed/" },
      { label: "gif", link: "/widgets/gif/" },
      { label: "image", link: "/widgets/image/" },
      { label: "mlb", link: "/widgets/mlb/" },
      { label: "mlb_standings", link: "/widgets/mlb_standings/" },
      { label: "coinbase", link: "/widgets/coinbase/" },
      { label: "coingecko", link: "/widgets/coingecko/" },
      { label: "etherscan", link: "/widgets/etherscan/" },
    ],
  },
  {
    label: "Transitions",
    items: [{ autogenerate: { directory: "transitions" } }],
  },
  {
    label: "Concepts",
    items: [{ autogenerate: { directory: "concepts" } }],
  },
  {
    label: "Tools",
    items: [{ autogenerate: { directory: "tools" } }],
  },
  {
    label: "Hardware",
    items: [{ autogenerate: { directory: "hardware" } }],
  },
  {
    label: "Reference",
    items: [{ autogenerate: { directory: "reference" } }],
  },
  {
    label: "Assets",
    items: [{ autogenerate: { directory: "assets" } }],
  },
  { label: "Showcase", link: "/showcase/" },
  { label: "Pitfalls", link: "/pitfalls/" },
],
```

- [ ] **Step 3: Lint + build**

```bash
cd docs/site && pnpm run lint 2>&1 | tail -3
cd docs/site && pnpm run build 2>&1 | tail -3
```

Expected: 0 lint errors, 39 pages built.

- [ ] **Step 4: Verify sidebar order in built HTML**

```bash
# Sidebar group labels appear in this order on every page
grep -oE '>(Home|Getting started|Widgets|Transitions|Concepts|Tools|Hardware|Reference|Assets|Showcase|Pitfalls)<' \
  docs/site/dist/index.html | head -11
```

Expected output (in this order):

```
>Home<
>Getting started<
>Widgets<
>Transitions<
>Concepts<
>Tools<
>Hardware<
>Reference<
>Assets<
>Showcase<
>Pitfalls<
```

- [ ] **Step 5: Commit**

```bash
git add docs/site/astro.config.mjs
git commit -m "docs: sidebar — reorder for orientation flow, pin message first in Widgets

UX panel review F1 + F7: Concepts (chapter-2 reference) sat ahead of
Widgets (chapter 1.5 actionable), and the autogenerated Widgets group
sorted alphabetically so \`message\` — the most-used widget — was
buried at position 7 between \`mlb_standings\` and \`rss_feed\`.

New top-level order: Home, Getting started, Widgets, Transitions,
Concepts, Tools, Hardware, Reference, Assets, Showcase, Pitfalls.
This matches the natural reading sequence for a new user (what
to put in a config → how the engine swaps between them → why →
local tooling → physical builds → exhaustive reference).

Widgets becomes an explicit-items list with message pinned first
(plus a link to the /widgets/ overview), then the rest sorted by
expected use frequency (text widgets, then live data, then crypto)
rather than alphabetically."
```

## Task 6: Move `frame-counters` from Concepts to Reference

**Files:**
- Move: `docs/site/src/content/docs/concepts/frame-counters.mdx` → `docs/site/src/content/docs/reference/frame-counters.mdx`
- Modify: any MDX page linking to `/concepts/frame-counters/` (find via grep)

UX finding F2: the page's first paragraph already says "most users never need to think about this model directly… for two narrower audiences: users debugging unexpected restart behavior, and developers implementing a new effect class." It belongs in Reference, not in beginner-facing Concepts.

- [ ] **Step 1: Move the file**

```bash
git mv docs/site/src/content/docs/concepts/frame-counters.mdx \
       docs/site/src/content/docs/reference/frame-counters.mdx
```

- [ ] **Step 2: Find all internal links to the old URL**

```bash
grep -rn '/concepts/frame-counters/' docs/site/src/content/docs/ \
  | grep -v 'frame-counters.mdx:'  # exclude the file itself if it self-references
```

Expected hits (verify before editing): `concepts/borders.mdx`, `concepts/animations.mdx` (the borders rainbow-chase section explicitly cross-refs frame-counters; the animations page may too).

- [ ] **Step 3: Update each link**

For every match in step 2, edit the file and replace `/concepts/frame-counters/` with `/reference/frame-counters/`. Use the Edit tool one file at a time. Example for `concepts/borders.mdx`:

```bash
# Find the line first to give context to Edit
grep -n '/concepts/frame-counters/' docs/site/src/content/docs/concepts/borders.mdx
```

Then Edit replacing the URL. If a `RelatedPages slugs={[...]}` array contains `"concepts/frame-counters"`, change it to `"reference/frame-counters"`.

- [ ] **Step 4: Lint + build**

```bash
cd docs/site && pnpm run lint 2>&1 | tail -3
cd docs/site && pnpm run build 2>&1 | tail -3
```

Expected: 0 lint errors, 39 pages built. The new URL `/reference/frame-counters/` should now exist; `/concepts/frame-counters/` should not.

- [ ] **Step 5: Verify the move**

```bash
test -f docs/site/dist/reference/frame-counters/index.html && echo OK new-location
test ! -f docs/site/dist/concepts/frame-counters/index.html && echo OK old-removed
# No remaining references to the old URL anywhere in the built site
grep -r '/concepts/frame-counters/' docs/site/dist/ | head -3 || echo OK no-stale-links
```

Expected: 3 OK lines.

- [ ] **Step 6: Commit**

```bash
git add docs/site/src/content/docs/
git commit -m "docs: move frame-counters from Concepts to Reference

UX panel review F2: frame-counters.mdx's own opening paragraph says
\"most users never need to think about this model directly… for two
narrower audiences: users debugging unexpected restart behavior, and
developers implementing a new effect class.\" Living next to Fonts
and Color providers in beginner-facing Concepts is a contract
violation with that framing — a new user following the docs linearly
hits engine-internal frame-counter mechanics before they learn what
a section is.

Move to Reference. Update internal cross-links from
/concepts/frame-counters/ to /reference/frame-counters/ (concepts/
borders.mdx and concepts/animations.mdx both pointed at it). Sidebar
auto-discovery picks up the new location with no further config
change."
```

## Task 7: Concepts pages voice cleanup + heading renames

**Files:**
- Modify: `docs/site/src/content/docs/concepts/color-providers.mdx`
- Modify: `docs/site/src/content/docs/concepts/display.mdx`
- Modify: `docs/site/src/content/docs/concepts/sections-and-modes.mdx`
- Modify: `docs/site/src/content/docs/transitions/index.mdx`
- Modify: `docs/site/src/content/docs/tools/creating-a-config.mdx`
- Modify: `docs/site/src/content/docs/reference/frame-counters.mdx` (post-move)

Apply the writer's heat-map rewrites (4 of 5 land here; the display dedup is Task 8) and rename the AI-archetypal "Picking the right X" / "Validation philosophy" headings.

- [ ] **Step 1: Rewrite `color-providers.mdx` opening paragraph**

Find the opening paragraph:

```mdx
Every text-bearing widget's `font_color` field — and `top_color` / `bottom_color` on `two_row` and image widgets — accepts five distinct flavors. A plain RGB list gives you a constant color. Three named string sentinels (`"rainbow"`, `"color_cycle"`, `"random"`) activate built-in effects. An inline TOML table unlocks a gradient. Some of these animate over time; others pick once per visit and stay fixed. The widget-side code is uniform regardless of which flavor you choose — all five resolve to the same `color_for(frame, char_index, total_chars)` interface internally.
```

Replace with:

```mdx
`font_color` accepts five forms: a `[r, g, b]` list (constant), the string shorthands `"rainbow"`, `"color_cycle"`, and `"random"`, or an inline table for a gradient. The first three cover most signs. The same field on `top_color` / `bottom_color` for `two_row` and image widgets behaves identically — pick once per widget, swap providers without changing anything else.
```

- [ ] **Step 2: Rewrite `color-providers.mdx` "Picking the right provider" section**

Find the section starting with `## Picking the right provider`. Rename the heading and replace the paragraph below it.

Old heading + body:

```mdx
## Picking the right provider

Use a **constant** when you are matching brand colors or want a predictable, distraction-free look. Use **color_cycle** when you want motion that stays tasteful — the whole message shifts as one, which reads as a subtle effect rather than a visual shout. Use **rainbow** when you want maximum visual impact: kid-friendly sections, attention-grabbing announcements, or any context where flair is the point. Use **gradient** when you want the feel of a color transition without the animation — useful when your brand palette has two distinct anchor colors and you want to bridge them politely. Use **random** when you have a long-running display and want each rotation to feel slightly different without any engineering effort.
```

New:

```mdx
## Which to use

- **Constant** — brand colors, anything that shouldn't animate.
- **Color_cycle** — the whole message shifts hue together; subtler than rainbow.
- **Rainbow** — per-character hue sweep; use it when flair is the point (kids' sections, grand openings, announcements).
- **Gradient** — frozen left-to-right interpolation; good when your brand has two anchor colors you want to bridge.
- **Random** — picks a different color each time the section plays; no animation.
```

- [ ] **Step 3: Rewrite `display.mdx` opening paragraph**

Find the page's opening paragraph (immediately after the imports):

```mdx
led-ticker drives a panel of LEDs. The `[display]` block in your TOML tells the engine the panel's physical geometry — how many pixels wide and tall each panel is, how many chain together, and what scaling to apply. Get this right and everything else "just works"; get it wrong and content prints to a three-pixel slice or runs off the edge entirely.
```

Replace with:

```mdx
The `[display]` block describes your panel's physical geometry: pixel dimensions per panel, chain length, and scaling. These values flow into every layout calculation, so a mismatch between config and hardware clips content or centers it on the wrong axis.
```

- [ ] **Step 4: Rewrite `frame-counters.mdx` opening paragraph**

The page is now at `docs/site/src/content/docs/reference/frame-counters.mdx` after Task 6. Find the opening paragraph after the imports (the existing text contains "advances based on a frame counter that ticks once per engine iteration" and ends with "None of them advance together, and none of them interfere.").

Replace with:

```mdx
Every animated effect — rainbow text, color cycle, typewriter, rainbow chase border — advances a frame counter that ticks once per 50 ms engine iteration. Each effect on a widget gets its own independent counter: a `message` with `font_color = "rainbow"`, `border = "rainbow"`, and `animation = "typewriter"` carries three counters, one per effect, that advance separately and never interfere.
```

- [ ] **Step 5: Rename `sections-and-modes.mdx` "Picking a mode" heading**

```bash
grep -n '## Picking a mode' docs/site/src/content/docs/concepts/sections-and-modes.mdx
```

Edit that line: `## Picking a mode` → `## Which mode to use`.

- [ ] **Step 6: Rename `transitions/index.mdx` "Picking a transition" heading**

```bash
grep -n '## Picking a transition' docs/site/src/content/docs/transitions/index.mdx
```

Edit that line: `## Picking a transition` → `## Which to use`.

- [ ] **Step 7: Rewrite `tools/creating-a-config.mdx` "Validation philosophy" section**

Find the section starting with `## Validation philosophy`. Rename heading + rewrite first paragraph.

Old:

```mdx
## Validation philosophy

The skill **never silently auto-fixes a violation.** Every problem the validator surfaces — and every pitfall the skill catches on its own pass through `references/decision-rules.md` — is presented to you with the rule cited and a one-line fix proposed. You decide whether to apply it. The same flag-and-ask discipline applies at all three checkpoints: per-section lint in `new` Phase 2 (and `add`), the assembled-config check in `new` Phase 3, and the symptom + catch-all pass in `refine`.
```

New:

```mdx
## How violations are surfaced

The skill never silently auto-fixes a violation. Every problem the validator surfaces — and every pitfall the skill's own pass through `references/decision-rules.md` catches — is shown to you with the rule id and a one-line fix. You approve or skip each one. This applies at every checkpoint: per-section in `new` Phase 2 / `add`, the full-config run in `new` Phase 3, and the symptom + catch-all pass in `refine`.
```

- [ ] **Step 8: Lint + build**

```bash
cd docs/site && pnpm run lint 2>&1 | tail -3
cd docs/site && pnpm run build 2>&1 | tail -3
```

Expected: 0 lint errors, 39 pages built.

- [ ] **Step 9: Commit**

```bash
git add docs/site/src/content/docs/
git commit -m "docs: concepts + tools voice cleanup, drop AI-archetypal headings

Writer panel review heat-map: four of five worst AI-prose offenders
were on concepts pages (color-providers x2, display, frame-counters)
plus one on tools/creating-a-config (\"Validation philosophy\"
heading + \"flag-and-ask discipline\" jargon). UX corroborated the
\"Picking the right X\" headings as filler and called out the same
Validation philosophy heading via the Tools-group label finding.

Apply Writer's specific rewrites verbatim:
  - color-providers opening: drop \"unlocks a gradient\" + the
    five-short-sentence cadence; tighten to one paragraph
  - color-providers \"Picking the right provider\": replace the five
    \"Use X when you want Y\" prose paragraphs with a five-bullet
    list; rename heading to \"Which to use\"
  - display opening: drop the scare-quoted \"just works\" cliche,
    rewrite to focus on layout-calculation flow
  - frame-counters opening: drop the redundant negative restatement
    (\"None of them advance together, and none of them interfere\"
    after \"three counters, one per effect\")

Plus heading renames flagged in the same review:
  - sections-and-modes: \"Picking a mode\" → \"Which mode to use\"
  - transitions/index: \"Picking a transition\" → \"Which to use\"
  - tools/creating-a-config: \"Validation philosophy\" → \"How
    violations are surfaced\""
```

## Task 8: Concepts/display dedup — link to reference instead of duplicating the table

**Files:**
- Modify: `docs/site/src/content/docs/concepts/display.mdx`

UX F5: `concepts/display` ends with a full `[display]` options table that duplicates `reference/config-options`'s coverage. The concepts page should focus on mental model; the table belongs in Reference.

- [ ] **Step 1: Find the duplicate table**

```bash
grep -n '## All `\[display\]` options' docs/site/src/content/docs/concepts/display.mdx
```

- [ ] **Step 2: Replace the table with a short pointer**

Find the section starting with `## All \`[display]\` options` and ending at the next `## ` heading or the `<RelatedPages` line. Replace the entire section (heading + table) with:

```mdx
## `[display]` reference

The full field reference — every knob, default value, and
Pi-version note — lives at
[Reference: Config options](/reference/config-options/#display).
The most-touched fields are above (`rows`, `cols`, `chain`,
`default_scale`, `pixel_mapper_config`, `gpio_slowdown`); see the
reference page when you need `pwm_bits`, `pwm_lsb_nanoseconds`,
`rp1_rio`, or the other Pi-tuning options.
```

- [ ] **Step 3: Lint + build**

```bash
cd docs/site && pnpm run lint 2>&1 | tail -3
cd docs/site && pnpm run build 2>&1 | tail -3
```

Expected: 0 lint errors, 39 pages built.

- [ ] **Step 4: Verify the link resolves**

```bash
# /reference/config-options/#display anchor exists
grep -q 'id="display"' docs/site/dist/reference/config-options/index.html && echo OK anchor
```

If the anchor is missing (the reference page uses `## \`[display]\`` which Starlight slugifies), check what the actual anchor id is and update the link in display.mdx accordingly. Common slugifications: `display`, `-display-`, `display-` — whichever Starlight emits.

- [ ] **Step 5: Commit**

```bash
git add docs/site/src/content/docs/concepts/display.mdx
git commit -m "docs: concepts/display — drop duplicate field table, link to reference

UX F5: concepts/display ended with a full \`[display]\` options table
that duplicated reference/config-options. Two pages owning the same
table is a drift risk (test_docs_config_options_drift only covers
the reference page) and bloats concepts/display past its job.

Replace the duplicate table with a short pointer to
/reference/config-options/#display. The mental-model content above
(logical canvas, ScaledCanvas, content_height ceiling, per-section
overrides) stays — that's what the concepts page is for."
```

## Task 9: Tools group — clarify creating-a-config is a skill, not a CLI tool

**Files:**
- Modify: `docs/site/src/content/docs/tools/creating-a-config.mdx`

UX F6: a visitor seeing "Tools → creating-a-config" expects a CLI or web form. The page title already says "Tool: creating-a-config skill" but the word "skill" is buried after a colon. Tighten the framing in the page intro.

- [ ] **Step 1: Read current intro**

```bash
head -30 docs/site/src/content/docs/tools/creating-a-config.mdx
```

- [ ] **Step 2: Rewrite the opening paragraph**

Find the opening paragraph (after the frontmatter + imports). It currently leads with "`creating-a-config` is a Claude skill that…" — keep the substance but lead more clearly with the distinction from the CLI tools.

Old (approximate, depending on prior PRs):

```mdx
`creating-a-config` is a Claude skill for building or modifying a led-ticker `config/config.toml`. Give it a natural-language request — "build me a config", "add weather to my sign", "fix the colors" — and it runs a structured Q&A to assemble or revise the TOML, then validates it before writing.
```

Replacement:

```mdx
Unlike the other entries in this section (`render-demo` and
`validate` are both CLI tools you run from a terminal),
`creating-a-config` is a **Claude Code skill** — an instruction set
the AI follows when you ask it to build or refine a `config.toml`.
Triggered by natural-language requests like "build me a config",
"add weather to my sign", or "fix the colors", it runs a structured
Q&A to assemble or revise the TOML, then validates the result
before writing.
```

- [ ] **Step 3: Lint + build + commit**

```bash
cd docs/site && pnpm run lint 2>&1 | tail -3
cd docs/site && pnpm run build 2>&1 | tail -3

git add docs/site/src/content/docs/tools/creating-a-config.mdx
git commit -m "docs: tools/creating-a-config — clarify it's a Claude skill, not a CLI

UX F6: a visitor seeing \"Tools → creating-a-config\" reasonably
expected a CLI or web form (since render-demo and validate are both
CLIs). The distinction was buried after a colon in the page title.
Lead the page intro with the skill-vs-CLI framing instead so a user
landing here from the sidebar knows immediately that this is the AI
assistant entry, not another command to type."
```

## Task 10: Hardware page polish — HUB75 def, cost estimates, `pixel_mapper_config` example

**Files:**
- Modify: `docs/site/src/content/docs/hardware/smallsign.mdx`
- Modify: `docs/site/src/content/docs/hardware/bigsign.mdx`

User panel review surfaced three concrete gaps: HUB75 used without explanation; no dollar cost anywhere; `pixel_mapper_config` Remap string format unexplained for non-bigsign layouts.

- [ ] **Step 1: Add HUB75 definition + cost estimate to smallsign**

Find the BOM table or the paragraph immediately preceding it in `hardware/smallsign.mdx`. Add a short paragraph (or extend the existing intro) introducing HUB75 the first time it's mentioned, and add a **Total cost** line under the BOM.

Insert this text immediately above the BOM table:

```mdx
:::note[What is HUB75?]
HUB75 is the standard data-cable interface for RGB LED matrix
panels — a 16-pin IDC connector carrying RGB + clock + addressing
signals. Any panel advertised as "HUB75-compatible" works with the
Adafruit bonnet / HAT and the rgbmatrix library this project uses.
:::
```

Then immediately after the BOM table, add:

```mdx
**Total cost (rough):** ~$150–200 USD depending on panel sourcing
and shipping. The Pi 4 is the largest single line item; the
Adafruit bonnet or HAT runs $20–25; matched 32×16 panels run
$15–25 each at retail (cheaper in lots from AliExpress).
Cross-check current pricing before ordering — these numbers were
verified in early 2026 and panel prices fluctuate.
```

- [ ] **Step 2: Add cost estimate + pixel_mapper_config example to bigsign**

In `hardware/bigsign.mdx`, immediately after the BOM table, add:

```mdx
**Total cost (rough):** ~$400–600 USD. The 8 P3 panels at $40–60
each are the dominant line item; the Pi 5 + HAT + a 30–60 A 5 V
supply with thick busbars round out the build. Frame and shroud
costs vary widely depending on whether you fabricate or buy.
Cross-check current pricing before ordering — these numbers were
verified in early 2026.
```

Then in the same file, find the existing **Pitfalls** section (already covers `pixel_mapper_config` chain-order sensitivity per a prior PR). Append a new pitfall paragraph for `pixel_mapper_config` examples on simpler layouts:

```mdx
**`pixel_mapper_config` for non-bigsign layouts.** The Remap string
follows the format `Remap:WIDTH,HEIGHT|x,yORIENT|...` with one
entry per panel in chain order. Orientations: `n` = normal,
`s` = 180°, `e` = 270°, `w` = 90°, `x` = discard. The bigsign's
2×4 vertical-serpentine chain is documented above. For simpler
layouts:

- **2×2 grid (chain runs along the bottom row first, then top
  row right-to-left)**, all panels upright:
  `Remap:128,64|0,32n|64,32n|64,0n|0,0n`
- **Single row of 4 panels**, all upright, chain enters left:
  `Remap:256,32|0,0n|64,0n|128,0n|192,0n`

If your physical layout doesn't match the chain order from the
data cable, every panel in the wrong position needs an entry in
the Remap string. See the upstream
[hzeller/rpi-rgb-led-matrix](https://github.com/hzeller/rpi-rgb-led-matrix)
README for the full Remap reference.
```

- [ ] **Step 3: Lint + build**

```bash
cd docs/site && pnpm run lint 2>&1 | tail -3
cd docs/site && pnpm run build 2>&1 | tail -3
```

Expected: 0 lint errors, 39 pages built.

- [ ] **Step 4: Commit**

```bash
git add docs/site/src/content/docs/hardware/smallsign.mdx docs/site/src/content/docs/hardware/bigsign.mdx
git commit -m "docs: hardware — define HUB75, add cost estimates, document pixel_mapper_config

User panel review (the prospective-user persona, who came from a
\"saw it on HN, deciding whether to build one\" framing) surfaced
three specific gaps that nearly bounced them:

  - \"HUB75 panels\" appears in the smallsign BOM but is never
    defined; a beginner who hasn't bought matrix panels before
    won't know if they're shopping for the right thing
  - No dollar cost anywhere — \"a Pi 4, five panels, a bonnet\"
    leaves the reader Googling every line item to ballpark the
    project as $50, $200, or $500
  - pixel_mapper_config Remap string format is referenced as
    \"see config.bigsign.example.toml\" but never explained, so
    a builder doing a 2×2 or 1×4 layout has no working example

Add a HUB75 definition note above the smallsign BOM. Add a Total
cost line (~\$150–200 smallsign, ~\$400–600 bigsign) with the
caveat that prices fluctuate. Add a Pitfalls entry on bigsign with
the Remap format reference + worked examples for 2×2 and 1×4
layouts."
```

## Task 11: Rule 14 label fix on widgets/message + PR 2 final integration

**Files:**
- Modify: `docs/site/src/content/docs/widgets/message.mdx`

PM finding: the bare `<DecisionRule id="14" />` callout under the Pitfalls section reads "Rule 14" without context, which is an internal artifact. Wrap it in a descriptive sub-heading.

- [ ] **Step 1: Read current Pitfalls section**

```bash
grep -n -B 2 -A 4 'DecisionRule id="14"' docs/site/src/content/docs/widgets/message.mdx
```

- [ ] **Step 2: Add a descriptive heading above the callout**

Edit `widgets/message.mdx`. Find the line `<DecisionRule id="14" />` and replace it with:

```mdx
### Typewriter is single-row only

<DecisionRule id="14" />
```

- [ ] **Step 3: Lint + build**

```bash
cd docs/site && pnpm run lint 2>&1 | tail -3
cd docs/site && pnpm run build 2>&1 | tail -3
```

Expected: 0 lint errors, 39 pages built.

- [ ] **Step 4: Commit the Rule 14 fix**

```bash
git add docs/site/src/content/docs/widgets/message.mdx
git commit -m "docs: widgets/message — descriptive heading above Rule 14 callout

PM panel review: the bare \"Rule 14\" badge in the Pitfalls section
was an internal tracking artifact from CLAUDE.md with no meaning to
an external reader. The pitfall content (typewriter is single-row
only on gif/image widgets) is good but the framing undermined
credibility — the reader either ignored the rule number or wondered
if they needed to read Rules 1-13 first.

Wrap the callout in an h3 that names the constraint plainly. The
Rule N badge stays on the callout itself for cross-referencing
\`led-ticker validate\` output, but it now sits under a heading that
tells you what the rule is about."
```

- [ ] **Step 5: PR 2 final lint pass**

```bash
cd docs/site && pnpm run lint 2>&1 | tail -3
```

Expected: 0/0/0.

- [ ] **Step 6: PR 2 final build + verify expected files**

```bash
cd docs/site && pnpm run build 2>&1 | tail -5
test -f docs/site/dist/reference/frame-counters/index.html && echo OK frame-counters-moved
test ! -f docs/site/dist/concepts/frame-counters/index.html && echo OK frame-counters-old-gone
test -f docs/site/dist/widgets/message/index.html && echo OK widgets-message
grep -q 'Typewriter is single-row only' docs/site/dist/widgets/message/index.html && echo OK rule-14-heading
grep -q 'Total cost' docs/site/dist/hardware/smallsign/index.html && echo OK smallsign-cost
grep -q 'HUB75' docs/site/dist/hardware/smallsign/index.html && echo OK hub75-def
grep -q 'Remap:128,64' docs/site/dist/hardware/bigsign/index.html && echo OK pixel-mapper-example
grep -q 'Which mode to use' docs/site/dist/concepts/sections-and-modes/index.html && echo OK sections-heading-renamed
grep -q 'How violations are surfaced' docs/site/dist/tools/creating-a-config/index.html && echo OK validation-heading-renamed
```

Expected: 9 OK lines.

- [ ] **Step 7: Push and open PR**

```bash
git push -u origin worktree-docs-panel-review-pr2
gh pr create --title "docs: panel-review fixes — voice + IA polish" --body "$(cat <<'EOF'
## Summary

Second of two PRs addressing the four-persona panel review (run via /review-docs on 2026-05-09). Bundles the voice cleanup, IA polish, and newcomer-facing gaps. Builds on PR #N (orientation + structural defects).

## Changes

- **Sidebar reorder** — Home → Getting started → Widgets → Transitions → Concepts → Tools → Hardware → Reference → Assets → Showcase → Pitfalls. Pin `message` first in Widgets (was buried at alphabetical position 7).
- **frame-counters: Concepts → Reference** — the page itself says "most users never need this"; living next to Fonts in beginner-facing Concepts was a contract violation. Cross-links updated.
- **Concepts voice cleanup** — Writer's heat-map rewrites applied verbatim to color-providers (×2), display, and frame-counters openings.
- **Heading renames** — drop AI-archetypal "Picking the right X" / "Validation philosophy" headings on color-providers, sections-and-modes, transitions/index, and tools/creating-a-config.
- **concepts/display dedup** — drop the duplicate `[display]` options table that lived alongside the canonical version in reference/config-options. Replaced with a short pointer.
- **Tools group label** — lead the creating-a-config page intro with the "Claude skill, not CLI" distinction so the sidebar grouping doesn't mislead.
- **Hardware page polish** — define HUB75 once on smallsign; add Total cost lines to both smallsign (~$150–200) and bigsign (~$400–600); add worked `pixel_mapper_config` Remap examples for 2×2 and 1×4 layouts.
- **Rule 14 label fix** — descriptive `### Typewriter is single-row only` heading above the bare callout on widgets/message.

## Test plan

- [x] `pnpm run lint` clean (0/0/0)
- [x] `pnpm run build` builds 39 pages (no count change — frame-counters just moved URLs)
- [x] All 9 verification grep checks pass (frame-counters move, sidebar order, headings, costs, HUB75, pixel_mapper_config, Rule 14)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-review checklist

**Spec coverage** — every panel finding maps to a task:

- ✅ Showstopper: Getting Started no-hardware path → Task 1
- ✅ Important: Wrong default reading order → Task 1 (Next steps block) + Task 5 (sidebar reorder)
- ✅ Important: Pitfalls page stub → Task 2
- ✅ Important: Concepts AI-prose drift → Task 7
- ✅ Important: Double-h1 a11y bug → Task 3
- ✅ Important: Homepage / showcase weak → deferred to memory (photos are content drops, not engineering)
- ✅ Nice-to-have: Tools group label → Task 9
- ✅ Nice-to-have: Widgets sidebar order → Task 5
- ✅ Nice-to-have: concepts/display dedup → Task 8
- ✅ Nice-to-have: Hardware cost estimates → Task 10
- ✅ Nice-to-have: HUB75 unexplained → Task 10
- ✅ Nice-to-have: pixel_mapper_config Remap examples → Task 10
- ✅ Nice-to-have: Rule 14 label → Task 11

**Placeholder scan** — no TBDs / TODOs / "fill in later" / "add appropriate X". Every step has the actual content the implementer needs (specific paragraphs, file paths, commands, expected outputs).

**Type consistency** — file paths used in Task 6's frame-counters move (`docs/site/src/content/docs/reference/frame-counters.mdx`) match Task 7's reference to it. Sidebar entries in Task 5 match the directory structure assumed in Task 6 (Concepts autogenerate will pick up that frame-counters has moved out). Verification greps in Task 11 reference the headings renamed in Task 7.

**Out of scope (intentional):**
- Real photos for hardware/showcase — pending memory; content drop, not engineering
- Custom Cloudflare domain + OG card — operations / branding; deferred per prior turn
