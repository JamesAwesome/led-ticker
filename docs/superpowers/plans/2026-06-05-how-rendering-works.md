# "How Rendering Works" Page (Phase 2a) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `concepts/how-rendering-works.mdx` page — a reader-friendly mental model of the render pipeline (config → engine loop → canvas → overlays → swap → panel) — at the top of the Concepts sidebar group.

**Architecture:** One new MDX concept page (Starlight default template, `DemoGif` lead visual + an ASCII pipeline diagram + `RelatedPages`). Placement is via frontmatter `sidebar.order` (the Concepts group is `autogenerate`d). No new components, no tested code, no runtime change — it's an explanatory hub page that cross-links the existing concept/reference pages rather than re-explaining them.

**Tech Stack:** Astro Starlight, MDX. Verification via `make docs-build` / `make docs-lint`.

**Source spec:** `docs/superpowers/specs/2026-06-05-how-rendering-works-design.md`

**Worktree:** `.claude/worktrees/docs-howitworks`, branch `feat/docs-howitworks`. **Commit convention:** `git -c core.hooksPath=/dev/null commit`.

**Verified facts (baked into the page):** ~20 fps / 50 ms engine tick (`ENGINE_TICK_MS`; matches `reference/frame-counters`); each tick advances per-effect frame counters, redraws, swaps, sleeps; `LedFrame.swap()` runs overlay hooks then a double-buffered `SwapOnVSync`; widgets draw to a logical 16-tall canvas, `ScaledCanvas` expands to physical when `scale > 1`; the panel is write-only. All link targets verified to exist (`concepts/display`, `concepts/sections-and-modes`, `concepts/busy-light`, `reference/frame-counters`, `transitions/`, `plugins/api-reference`).

---

### Task 1: Create the "How rendering works" page

**Files:**
- Create: `docs/site/src/content/docs/concepts/how-rendering-works.mdx`

- [ ] **Step 1: Write the page**

Create `docs/site/src/content/docs/concepts/how-rendering-works.mdx` with EXACTLY this content:

````mdx
---
title: How rendering works
description: The render pipeline — what happens between your TOML config and the panel lighting up. The engine loop, the canvas, overlays, and the swap.
sidebar:
  order: 1
---

import DemoGif from "../../../components/DemoGif.astro";
import RelatedPages from "../../../components/RelatedPages.astro";

This page is a mental model of **what happens between your `config.toml` and the panel lighting up** — useful whether you're tuning a config or building a plugin. The other concept pages go deep on each piece; this one shows how they fit together.

<DemoGif
  src="/demos/message-rainbow.gif"
  caption="A rainbow message on the panel — here's the pipeline that produces it."
/>

## The pipeline

```
Config (TOML)
   ↓ parsed at startup
Playlist → sections → widgets
   ↓ engine tick (~20 fps)
widget.draw() → logical canvas
   ↓ ScaledCanvas expands it (when scale > 1)
overlay hooks paint (e.g. the busy light)
   ↓
LedFrame.swap() → double-buffered → panel
```

Each section below is one step of that flow.

## The engine loop

At startup, led-ticker parses your config into a **playlist** of [sections](/concepts/sections-and-modes/), each holding one or more **widgets**. Then an asyncio engine runs a steady loop — about **20 frames per second** (a 50 ms _tick_).

On each tick the engine:

1. **advances the frame counter(s)** — every animated effect (rainbow text, a color cycle, a typewriter) has [its own counter](/reference/frame-counters/) that moves one step;
2. **redraws** the current widget onto the canvas at its new frame;
3. **swaps** the finished frame to the panel (below), then sleeps until the next tick.

A section's **mode** decides how its widgets are shown — held in place (`swap`) or scrolling — and for how long; **[transitions](/transitions/)** play the animation between one widget or section and the next. (An effect whose output doesn't change with the frame skips the per-tick redraw — see [frame counters](/reference/frame-counters/).)

## The canvas

Widgets don't draw to physical LEDs directly. They draw to a **logical canvas** — a fixed 16-pixel-tall grid — using simple `(x, y)` coordinates, so a widget never needs to know how big your sign is. When your `[display]` runs at `scale > 1` (a big sign), a **`ScaledCanvas`** wraps the real panel and expands every logical pixel into a `scale × scale` block, centering the content vertically.

That's the short version — [Display](/concepts/display/) covers scaling, the `content_height × scale` ceiling, and per-section overrides in full.

## Reaching the panel

When a frame is ready, the engine calls **`LedFrame.swap()`**, which does two things in order:

1. runs every registered **overlay hook** — paint functions that draw _over_ whatever's on screen, every frame, like the [busy light](/concepts/busy-light/)'s status dot;
2. performs a **double-buffered swap**: the new frame is sent to the panel while the next one is drawn off-screen, so the display never tears or flickers mid-update.

Then the loop sleeps and the next tick begins.

## Why it's built this way

A few deliberate choices explain the rest:

- **A fixed tick.** Driving everything from one steady ~20 fps clock keeps animations smooth and in sync, and makes timing predictable across very different signs.
- **A write-only panel.** The hardware framebuffer can be written but not read back, so widgets and effects **recompute each frame** from their frame counter rather than reading the current pixels — that's why effects are functions of the frame number.
- **Logical, then physical.** Keeping drawing in logical 16-tall coordinates and expanding to the real panel at swap time means one widget runs unchanged on a tiny sign or a giant one.

The full engineering rules behind this — the hardware-rendering constraints that keep the panel from freezing — live in [`docs/plugin-system.md`](https://github.com/JamesAwesome/led-ticker/blob/main/docs/plugin-system.md) and the project's `CLAUDE.md`, for contributors and plugin authors who need them.

<RelatedPages
  slugs={["concepts/display", "concepts/sections-and-modes", "transitions"]}
/>
````

- [ ] **Step 2: Format, build, lint**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/docs-howitworks
make docs-format
make docs-build; echo "BUILD=$?"
make docs-lint; echo "LINT=$?"
```
Expected: both exit 0; build reports one more page (61). `astro check` validates internal links — `/concepts/sections-and-modes/`, `/reference/frame-counters/`, `/transitions/`, `/concepts/display/`, `/concepts/busy-light/`, and the `RelatedPages` slugs (`concepts/display`, `concepts/sections-and-modes`, `transitions`) all resolve.

- [ ] **Step 3: Verify it sorts to the top of Concepts**

The Concepts group is autogenerated; `sidebar.order: 1` should float this page above the (unordered) concept pages. Confirm from a built page's sidebar nav that `how-rendering-works` appears before `display`:

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/docs-howitworks/docs/site
python3 - <<'PY'
import re, pathlib
html = pathlib.Path("dist/concepts/display/index.html").read_text()
order = [m for m in re.findall(r'/concepts/([a-z-]+)/', html)]
# first occurrence index of each within the rendered sidebar
def first(slug):
    try: return order.index(slug)
    except ValueError: return 10**9
hrw, disp = first("how-rendering-works"), first("display")
print(f"how-rendering-works@{hrw}  display@{disp}")
print("ORDER_OK" if hrw < disp else "ORDER_WRONG")
PY
```
Expected: `ORDER_OK` (how-rendering-works appears before display in the Concepts sidebar). If `ORDER_WRONG`, the autogenerate ordering didn't honor the frontmatter as expected — fall back to converting the Concepts group in `docs/site/astro.config.mjs` to an explicit list with `{ label: "How rendering works", link: "/concepts/how-rendering-works/" }` first, followed by `{ autogenerate: { directory: "concepts" } }` for the rest, and re-run Step 2.

- [ ] **Step 4: Confirm the lead GIF resolves**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/docs-howitworks/docs/site
test -f public/demos/message-rainbow.gif && echo "GIF OK"
grep -o "/demos/message-rainbow.gif" dist/concepts/how-rendering-works/index.html | head -1
```
Expected: `GIF OK`; the built page references the GIF.

- [ ] **Step 5: Commit**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/docs-howitworks
git add docs/site/src/content/docs/concepts/how-rendering-works.mdx
git -c core.hooksPath=/dev/null commit -m "docs: add the How rendering works page (Phase 2a)

A mental-model hub for the render pipeline (config -> engine tick -> canvas ->
overlays -> double-buffered swap -> panel). Sorts to the top of Concepts; cross-
links display/frame-counters/transitions/busy-light rather than re-explaining,
and points contributors at plugin-system.md/CLAUDE.md for the constraints."
```

(If Step 3 needed the astro.config fallback, add `docs/site/astro.config.mjs` to the `git add`.)

---

### Task 2: Technical-writer + hobbyist-persona review

After the page builds clean, run two reviews and apply fixes:

- [ ] **Step 1: Tech-writer reviewer** — reads `concepts/how-rendering-works.mdx`, runs the `docs/DOCS-STYLE.md` §3 checklist treating the task-page items (#11 what-you'll-need, #12 time stamp, #13 local troubleshooting) as **N/A** for a concept page, returns prioritized must-fix vs nice-to-have. (Its whole job is cross-linking, not re-explaining — confirm it doesn't duplicate display.mdx.)
- [ ] **Step 2: Hobbyist-persona ("Sam") check** — goal "understand how my config becomes pixels." Reports whether the page gives a clear mental model without going over his head, and whether the jargon (tick, canvas, swap, double-buffering, overlay) is glossed — pass/fail.
- [ ] **Step 3:** Apply must-fix from both; re-run `make docs-format && make docs-build && make docs-lint` (exit 0); commit fixes (or record "no must-fix items").

---

## Self-Review

**1. Spec coverage:**
- New `concepts/how-rendering-works.mdx`, mental-model framing, lead GIF + ASCII pipeline → Task 1 Step 1. ✓
- Sections: pipeline, engine loop, canvas (cross-links display, ~2 sentences), reaching the panel (overlay-then-double-buffered-swap), why-it's-built-this-way (3 facts), where-to-next → Task 1 Step 1. ✓
- Top of Concepts via `sidebar.order` (autogenerate) + verification + astro.config fallback → Task 1 Steps 1, 3. ✓
- Cross-link, don't re-explain; point to plugin-system.md/CLAUDE.md for the 12 constraints (not restated) → page body. ✓
- Tech-writer + hobbyist review with concept-page N/A items → Task 2. ✓
- Verification: build/lint clean, links resolve, GIF resolves, order correct → Task 1 Steps 2–4. ✓
- Out of scope (no deep contributor treatment; no display.mdx change; no drift tripwire) → respected. ✓

**2. Placeholder scan:** No TBD/TODO. The fallback note in Step 3 is a contingency with the exact astro.config edit given, not a placeholder.

**3. Type/consistency:** Component import depth `../../../components/` matches the verified depth-2 (concepts/) convention (same as `concepts/display.mdx`). The stated tick (~20 fps / 50 ms) matches `reference/frame-counters` and `ENGINE_TICK_MS`. The overlay-then-swap order matches `frame.py:swap()`. All in-body links and `RelatedPages` slugs correspond to verified-existing pages. `sidebar.order: 1` floats the page above the unordered concept pages (Starlight treats unordered as last); Step 3 verifies and gives a fallback if not.
