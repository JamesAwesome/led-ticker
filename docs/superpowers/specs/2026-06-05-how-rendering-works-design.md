# "How Rendering Works" Page — Design (Phase 2a)

**Date:** 2026-06-05
**Status:** Approved (brainstorm), pending implementation plan

## Context

**Phase 2a** of the docs-site effort. Phase status: Phase 0 (style guide), Phase 1 (home page), Phase 2b (API reference), and the whole **Extending led-ticker** how-to section are all shipped. This is the **"how it works" / render-architecture** page — the one remaining technical-docs gap before the Phase 3 audit.

Unlike the Extending pages, this is an **explanatory / concept page** (a mental model), not a how-to bound to a tested plugin. New branch `feat/docs-howitworks` off main.

## Goal

Give a reader a clear mental model of **what happens between their TOML config and the panel lighting up** — the render pipeline. Today this narrative exists nowhere user-facing: the pieces are documented separately (`concepts/display` = canvas scaling; `reference/frame-counters` = per-effect counters; `transitions/` = transitions; `concepts/busy-light` = overlays), but nothing ties them into one flow. This page is the **hub** that does, linking out for depth rather than re-explaining.

## Decisions (from brainstorm)

- **Framing: mental model for everyone** — curious hobbyists first, developers get the map. Narrative + one ASCII pipeline diagram; light on internals.
- **Placement:** `concepts/how-rendering-works.mdx`, at the **top of the Concepts** sidebar group (the orientation page that frames the other concept pages).
- **Scope against `concepts/display.mdx`:** that page owns the logical-vs-physical canvas / `ScaledCanvas` / scaling-ceiling story. This page **cross-links** it for the canvas step, doesn't re-explain it.
- **Hardware constraints:** surface only 2–3 illuminating "why" facts in prose; do **not** restate the 12 CLAUDE.md constraints (drift + too deep). Point contributors to `docs/plugin-system.md` + the CLAUDE.md "Hardware Rendering Constraints" for the full list.
- **Diagrams:** ASCII (the site has no mermaid). The approved pipeline diagram.
- **No tested code, no drift tripwire** — it's narrative that *points at* the constraints, not a code catalog. The one soft constant ("~20 fps / a 50 ms tick") is phrased loosely and already matches `reference/frame-counters`.

## Verified facts (the page must be accurate)

From `src/led_ticker/ticker.py` + `frame.py`:

- The engine runs an asyncio loop at a steady **~20 frames per second** — a **50 ms** tick (`ENGINE_TICK_MS`); `reference/frame-counters` already states "ticks once per 50 ms engine iteration."
- Each tick: advance the per-effect frame counter(s), redraw the current widget onto the canvas, swap, sleep (drift-compensated). Scrolling modes use their own `scroll_speed` (default 0.05 s = 1 logical px/tick).
- **Modes** (swap / forever_scroll / infini_scroll / gif) decide how widgets are shown and for how long; **transitions** play between widgets/sections. (Cross-link `concepts/sections-and-modes` + `transitions/`.)
- Widgets draw to a **logical 16-tall canvas**; when `scale > 1`, a `ScaledCanvas` expands every pixel to a `scale×scale` block on the real panel and centers vertically. (Cross-link `concepts/display`.)
- `LedFrame.swap(canvas)` runs the registered **`overlay_hooks`** (composited over every frame), then `matrix.SwapOnVSync(canvas, …)` — a **double-buffered** swap (it returns the next back-buffer; the engine captures it). (Cross-link `concepts/busy-light` for overlays.)
- The panel framebuffer is **write-only** (no `GetPixel`) — widgets never read pixels back; this is why effects recompute each frame rather than reading the canvas.

The approved ASCII pipeline:

```
Config (TOML)
   ↓ parsed at startup
Playlist → sections → widgets
   ↓ engine tick (~20 fps)
widget.draw() → logical canvas
   ↓ ScaledCanvas expands it (when scale > 1)
overlay hooks paint (e.g. busy light)
   ↓
LedFrame.swap() → double-buffered → panel
```

## Deliverable

### New page: `concepts/how-rendering-works.mdx`

Reader named (anyone curious; developers get the map). Sections:

1. **Intro + payoff** — "what happens between your config and the panel lighting up." Lead visual: reuse an existing demo GIF (`/demos/message-rainbow.gif`) as "here's the result — here's how it gets there."
2. **The pipeline** — the ASCII diagram above, with a one-line caption per stage.
3. **The engine loop** — the asyncio engine, the steady ~20 fps tick; each tick advances the frame counter(s) and redraws; modes decide what's shown and for how long, transitions play between them. Cross-link `concepts/sections-and-modes`, `transitions/`, `reference/frame-counters`.
4. **The canvas** — widgets draw to a logical 16-tall canvas; `ScaledCanvas` expands it to physical pixels when `scale > 1`. Keep it to ~2 sentences and **cross-link `concepts/display`** for the full scaling story.
5. **Reaching the panel** — `LedFrame.swap()`: overlay hooks composite over every frame (→ `concepts/busy-light`), then a double-buffered swap sends it to the panel flicker-free.
6. **Why it's built this way** — 2–3 "why" facts: the fixed tick keeps animation smooth and predictable; the panel is write-only, so widgets recompute each frame instead of reading pixels back; the logical-vs-physical split lets one widget run at any scale. For the full engineering invariants, point to `docs/plugin-system.md` + the CLAUDE.md "Hardware Rendering Constraints" (linked, not restated).
7. **Where to next** — `concepts/display`, `concepts/sections-and-modes`, `transitions/`, `plugins/api-reference`, `concepts/busy-light`.

### Sidebar

`docs/site/astro.config.mjs`: add "How rendering works" → `/concepts/how-rendering-works/` at the **top** of the Concepts group (before the existing autogenerated/listed concept entries). The plan pins the exact edit to match the current Concepts sidebar config (it may be an `autogenerate` block or an explicit list — if autogenerated, add an explicit ordered entry or a frontmatter `sidebar.order` so this page sorts first).

## Applying the DOCS-STYLE rubric

Concept page (not a task page): reader named; payoff visual near the top (the lead GIF + the diagram); gloss jargon (engine tick, logical/physical canvas, swap, double-buffering, overlay, frame counter) on first use; **cross-link, don't re-explain** (this page's whole job — it links display/frame-counters/transitions/busy-light instead of duplicating them); honesty about the model being a simplification (point to the deep refs); next-step CTA. **N/A** (concept page, not a task): the "what you'll need" box (#11), time/effort stamp (#12), and local "if it doesn't work" troubleshooting (#13) — the reviewer treats these as N/A. No new component; no tested code.

## The review loop

Tech-writer reviewer (DOCS-STYLE §3, with the N/A items above) + a hobbyist-persona ("Sam") check — "after reading this, do I understand how my config becomes pixels, without it being over my head?" Fix must-fix; re-review until both pass.

## Verification

- `make docs-build` + `make docs-lint` clean; the page renders; "How rendering works" appears at the top of the Concepts sidebar group; all cross-links resolve.
- Every internal link target exists (`concepts/display`, `concepts/sections-and-modes`, `concepts/busy-light`, `reference/frame-counters`, `transitions/`, `plugins/api-reference`).
- The lead GIF `src` resolves under `docs/site/public/`.
- The stated facts (≈20 fps / 50 ms tick; overlay-then-swap; logical-vs-physical; write-only panel) match the code (verified above) and are consistent with `reference/frame-counters`.

## Out of scope (Phase 2a)

- A deep "render architecture for contributors" treatment (the 12 constraints, module-by-module, double-buffering internals) — that stays in `docs/plugin-system.md` + CLAUDE.md; this page links to them.
- Any change to `concepts/display.mdx` or other existing pages beyond the sidebar entry (and, if needed, a `sidebar.order` so the new page sorts first).
- A drift tripwire (narrative prose, not a code catalog).
- The Phase 3 docs audit (separate).
