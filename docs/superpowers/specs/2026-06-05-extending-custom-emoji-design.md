# Extending led-ticker — Custom Emoji How-To (+ reference fixes) — Design

**Date:** 2026-06-05
**Status:** Approved (brainstorm), pending implementation plan

## Context

This reworks/expands the plugin technical docs. It was triggered by a hobbyist-persona review of the new API reference page (currently in held PR #157): the reference reads as a **catalog/overview**, and a motivated hobbyist ("Sam") could not actually build a custom emoji or a custom transition from it — `PixelData` had no literal example, `HiResEmoji`'s fields were documented nowhere in prose (only in `examples/plugins/acme/__init__.py`), there was no PNG→pixels recipe, the hi/low-res model was unexplained jargon, and the `frame_at` return-is-ignored contract was missing/contradicted.

The fix is a new **"Extending led-ticker"** how-to section of focused, technical, worked-example pages — plus targeted correctness fixes to the API reference (which stays the catalog). This is part of the phased docs effort:

- Phase 0 (style guide, #155, merged), Phase 1 (home page, #156, merged), Phase 2b (API reference, **#157, held**).
- This design = **Extending section, piece 1: Custom emoji** + the reference fixes Sam's review surfaced. It supersedes/absorbs the earlier "Phase 2c authoring walkthroughs" sketch.

**Branch:** continues on `feat/docs-tech` (the held #157 branch), so the reference fixes and the new page land together; #157 becomes the umbrella PR (retitled at finish).

### The "Extending led-ticker" section (roadmap)

A new sidebar group under Plugins (after "Authoring a plugin"): focused how-to pages, each with a tested worked example. Agreed full set, built in pieces:

1. **Custom emoji** ← this design.
2. Writing a transition (next).
3. Custom color provider.
4. Service + smaller surfaces (overlay/`on_startup` "service plugin", animation, border, easing).

The existing `plugins/authoring/04-beyond-widgets.mdx` (which sketches these shallowly) becomes a short **hub** that links into the deep pages as they land.

**Tone:** technical how-to — worked-example-driven, terse, code-forward (the user explicitly wanted these "less narrative, more technical" than the widget tutorial).

## Decisions (from brainstorm)

- **#157 disposition:** held; reference revisions + this how-to land together on the same branch.
- **Structure:** new "Extending led-ticker" sidebar section; `04-beyond-widgets` slimmed to a hub.
- **First piece:** Custom emoji only (transition follows next).
- **Tested example:** a **new, dedicated** plugin `examples/plugins/example_emoji/` (the widget tutorial's `example/` plugin is shown as a complete listing, so it must not gain unrelated emoji code). Its own behavioral tripwire test.
- **PNG→PixelData recipe:** a documented, copy-paste Pillow snippet (not tripwire-tested).

## The accurate emoji API (the page must get this right)

From `src/led_ticker/pixel_emoji.py` and `_types.py`:

- `PixelData = list[tuple[int, int, int, int, int]]` — a list of `(x, y, r, g, b)` (x,y are 0–7 for an 8×8 low-res sprite; r,g,b 0–255). One tuple per **lit** pixel; omit a pixel to leave it transparent/off.
- `api.emoji(slug, data)` registers a **low-res** sprite into `EMOJI_REGISTRY` under `namespace.slug`. Inline `:namespace.slug:` in any message text resolves it; this is what a small (unscaled) sign uses.
- `HiResEmoji(pixels, physical_size, physical_width=None)` — `pixels` is a tuple of `(x, y, r, g, b)` in **physical** coordinates (e.g. 0–31 for a 32×32 sprite), `physical_size` is the sprite's physical square size (e.g. 16 or 32), `physical_width` optionally overrides the laid-out width (auto-trimmed from the pixels when unset). `api.hires_emoji(slug, HiResEmoji(...))` registers into `HIRES_REGISTRY`, used by `draw_emoji_at`/`measure_emoji_at` on a scaled canvas (big signs / `default_scale > 1`).
- **Two registries / the pairing rule:** inline `:slug:` tokens and unscaled canvases resolve **only** through the low-res registry. So a hi-res emoji should have a matching low-res counterpart; a hi-res registration with no low-res pair logs a warning at load. Practical guidance for the page: *small sign → low-res is all you need; big/scaled sign or direct `draw_emoji_at` → add a hi-res sprite (and keep the low-res one for inline use).*

## Deliverable

### 1. New page: `plugins/extending/custom-emoji.mdx`

Audience named (plugin authors / motivated hobbyists). Sections (technical how-to, code-forward):

1. **Intro + what you'll need** — a one-line "what you'll build" (a plugin that adds a custom inline emoji) and a brief prerequisites note (a working plugin scaffold — link to the authoring guide; Pillow only for the optional PNG recipe). Payoff visual: reuse the existing `assets-emoji.gif` (emojis inline in messages) or show the literal sprite.
2. **What a `PixelData` is** — the format (`list[(x, y, r, g, b)]`, one tuple per lit pixel) with a **literal** 8×8 example (a recognizable sprite, e.g. a heart) the reader can paste.
3. **Register and show it** — `api.emoji("heart", PIXELS)` inside `register(api)`; then reference it inline as `:yourplugin.heart:` in a message widget's `text`, and run it (the local-preview command). Closes the "how does it show up" loop.
4. **Low-res vs hi-res, plainly** — the two-registry model in plain terms + the "small sign → low-res; big/scaled → add hi-res" rule. No unexplained jargon.
5. **Adding a hi-res sprite** — `HiResEmoji(pixels=…, physical_size=…)` (physical coords), the pairing rule, when you need it.
6. **From a PNG** — a copy-paste Pillow snippet that opens an image, skips transparent pixels, and prints the `PixelData` list (the conversion Sam wanted). Clearly marked as a one-time helper you run yourself; not part of the plugin.
7. **Complete listing** — the full `examples/plugins/example_emoji/__init__.py`, matching the shipped tested file.
8. **If it doesn't work** — short, symptom-first troubleshooting (emoji not showing → check the `namespace.slug`; hi-res not appearing on a big sign → low-res pairing; warning at load). Next-step CTA (→ Writing a transition, when it lands; → API reference; → emoji concept page).

### 2. New tested example plugin: `examples/plugins/example_emoji/__init__.py`

- A minimal plugin (namespace `example_emoji`) whose `register(api)` registers one low-res emoji (`api.emoji("heart", …)`) and a matching hi-res variant (`api.hires_emoji("heart", HiResEmoji(pixels=…, physical_size=16))`). Imports only `led_ticker.plugin` + stdlib. Teaching comments encouraged.
- **Tripwire test** `tests/test_plugins/test_example_emoji_plugin.py` (behavioral, mirroring `test_example_plugin.py`): loads the plugin into an isolated dir, asserts `example_emoji.heart` is in `EMOJI_REGISTRY` with the expected pixel data, and that the hi-res variant is in `HIRES_REGISTRY` with the expected `physical_size`. This keeps the page's code honest against the real API.
- The page's "Complete listing" (and the literal `PixelData` snippet) must match this file. Consistency is enforced by the tech-writer review + the behavioral tripwire (the exact-pixel assertions catch a drifted sprite). A brittle byte-match test is **not** added (the project's example-plugin precedent is behavioral).

### 3. Targeted API reference fixes: `plugins/api-reference.mdx`

The correctness gaps Sam found (the reference stays the catalog; depth lives on the new page):

- **`HiResEmoji`** export row: replace "Hi-res emoji sprite data" with its real fields — `pixels` (physical-coord `(x,y,r,g,b)` tuples), `physical_size`, optional `physical_width`.
- **`PixelData`** export row: keep the `list[(x,y,r,g,b)]` shape; ensure it reads as "one tuple per lit pixel."
- **Assets section:** add a short "See [Custom emoji](/plugins/extending/custom-emoji/) for a worked example" link (and reference the acme example) so the rows point at depth.
- **`frame_at` correctness note:** in the registration-methods area (or a one-line note), state that a transition draws onto `canvas` and its **return value is ignored** — fixing the misleading `Canvas`/`DrawResult` implication Sam hit. (Full transition walkthrough is the next piece; this is just the one-line correctness fix.)
- These edits must not disturb the drift-test marker regions or the documented method/export name sets (the edits are to the "What it is" column text and surrounding prose, not the first-column names). Re-run `tests/test_docs_plugin_api_drift.py` after.

### 4. Slim `plugins/authoring/04-beyond-widgets.mdx`

Its emoji portion becomes a short pointer to `plugins/extending/custom-emoji/` (the hub role); the rest of the page is unchanged until its other surfaces get their own pages.

### 5. Sidebar: `docs/site/astro.config.mjs`

Add an "Extending led-ticker" group under Plugins (after "Authoring a plugin") with one item now: "Custom emoji" → `/plugins/extending/custom-emoji/`.

## Applying the DOCS-STYLE rubric

It's a how-to (task) page, so more rubric items apply than for the reference: reader named; a brief "what you'll need"; payoff visual near top; **complete copy-pasteable example** (the literal `PixelData` + the full listing); concrete commands (how to preview); gloss jargon (`PixelData`, low/hi-res registry, physical coords); **code bound to a tested source** (the `example_emoji` plugin + tripwire); local "if it doesn't work" troubleshooting; cross-link don't re-explain; next-step CTA. Given the "more technical, less narrative" steer, the time/effort stamp (#12) and heavy beginner-reassurance (#15) are applied lightly or N/A.

## The review loop

After build, a **technical-writer reviewer subagent** runs the DOCS-STYLE §3 checklist against the new page + the reference edits and returns prioritized must-fix/nice-to-have; the implementer fixes and re-reviews until it passes. A second **hobbyist-persona check** (Sam: "can I now ship my emoji?") validates the page actually closes the gaps that triggered this work.

## Verification

- `make docs-build` + `make docs-lint` clean; the new page renders; the "Extending led-ticker" sidebar group shows "Custom emoji"; all internal links resolve.
- `tests/test_plugins/test_example_emoji_plugin.py` passes (loads the plugin; asserts the low-res + hi-res registrations and their pixel data).
- `tests/test_docs_plugin_api_drift.py` still passes after the reference edits.
- The page's literal `PixelData` and complete listing match `examples/plugins/example_emoji/__init__.py`.
- The PNG→PixelData snippet is correct, standard Pillow (reviewed by eye; explicitly not in the test suite).

## Out of scope (this piece)

- The transition, color-provider, and service/smaller-surface pages (later pieces in the same section).
- Any change to runtime emoji code (`pixel_emoji.py`) — docs + a new example plugin + a test only.
- A byte-match tripwire for the listing (behavioral test instead, per precedent).
- Merging or restructuring #157 beyond the targeted reference fixes.
