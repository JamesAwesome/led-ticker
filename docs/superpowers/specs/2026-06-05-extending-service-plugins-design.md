# Extending led-ticker — Service Plugins How-To (+ other surfaces) — Design

**Date:** 2026-06-05
**Status:** Approved (brainstorm), pending implementation plan

## Context

The **last** piece of the "Extending led-ticker" how-to section (after Custom emoji #157, Writing a transition #158, Custom color provider #159). Same shape: a technical, worked-example how-to bound to a dedicated tested example plugin, reviewed by the tech-writer + a repeat hobbyist-persona ("Sam"). New branch `feat/docs-service` off the merged main.

The high-value, unique content is the **service plugin** pattern — a background poller (`on_startup` + `spawn_tracked`) plus a status `overlay` painted from shared state. This is the generic version of the shipped busy-light feature (a real-world status light). Animation / border / easing are small and near-identical to patterns already taught, so they get a compact "other surfaces at a glance" recap that points at the already-tested **acme** reference plugin (DRY) rather than full walkthroughs.

## Decisions (from brainstorm)

- **One page**: a "Service plugins" how-to with the service worked example + a brief other-surfaces recap (animation/border/easing) — not separate pages for the small surfaces.
- **Worked example: a status-dot service** — `api.overlay(paint)` paints a corner dot; `api.on_startup(start)` spawns a poller via `spawn_tracked` that updates shared state from `ctx.session`. Demonstrates the lifecycle hooks + the "overlays are paint-only and must never raise" rule.
- Animation/border/easing shown as compact snippets, each pointing to acme's tested version.
- **Tested example:** a new dedicated plugin `examples/plugins/example_service/` (namespace `example_service`) registering the overlay + startup hook, with a behavioral tripwire.
- **No new demo GIF** (a corner status dot isn't well served by the existing assets); lead with a clear "what you'll build" and link the [busy-light concept](https://docs.ledticker.dev/concepts/busy-light/) as the shipped real-world example of this exact pattern.
- Same install-before-preview honesty; **run `ruff check src/ tests/`** before committing.

## The accurate lifecycle/surface API (the page must get this right)

From `src/led_ticker/plugin.py`, `_plugin_loader.py`, `animations.py`, `borders.py`:

- **`api.overlay(paint)`** — registers `paint(canvas)`, run every frame on the **real** canvas **before** the hardware swap. It is **exception-guarded**: a raise disables that overlay and is logged (so it can't freeze the panel). Must be paint-only and fast. Draw with `canvas.SetPixel(x, y, r, g, b)` (and `canvas.width`/`height` for bounds).
- **`api.on_startup(fn)`** — `fn` runs once, after the frame + HTTP session exist, before the main loop; receives a **`StartupContext`** with `.frame` (the `LedFrame`), `.session` (a shared `aiohttp.ClientSession`), `.config` (parsed app config). May be sync or async.
- **`api.on_shutdown(fn)`** — runs best-effort when the loop exits; no args; sync or async.
- **`spawn_tracked(coro)`** — spawn long-lived background work (e.g. a poll loop) as a tracked task from an `on_startup` hook: `spawn_tracked(poll())`.
- The loader's `load_plugins(...)` result (`LoadedPlugins`) exposes `.overlays: list[(namespace, paint)]`, `.startup_hooks: list[(namespace, fn)]`, `.shutdown_hooks: list[(namespace, fn)]` — used by the tripwire to assert registration.
- **Animation:** `@api.animation("name")` on a class with `frame_for(self, frame, full_text, canvas_width, text_width) -> AnimationFrame`; `AnimationFrame(visible_text=...)`.
- **Border:** `@api.border("name")` on a `BorderEffectBase` subclass (must declare `frame_invariant`) with `paint(self, canvas, frame_count) -> None` (mutates the canvas — a 1–2px perimeter ring via `SetPixel`).
- **Easing:** `api.easing("name", fn)` — `fn` is `(float) -> float` (a plain callable, not a class).
- All of `overlay`/`on_startup`/`on_shutdown`/`spawn_tracked`/`StartupContext`/`AnimationFrame`/`BorderEffectBase` are on the public `led_ticker.plugin` surface.

**The worked service plugin:** module imports `asyncio` + `spawn_tracked`; `register(api)` holds `state = {"online": False}`; `paint(canvas)` sets `(0,0)` to green when online else red; `api.overlay(paint)`; an async `start(ctx)` defines a `poll()` loop that GETs a health URL via `ctx.session`, sets `state["online"]`, sleeps 30s, and `spawn_tracked(poll())`; `api.on_startup(start)`.

## Deliverable

### 1. New page: `plugins/extending/service-plugins.mdx`

Audience named (plugin authors). Technical how-to sections:

1. **Intro + what you'll need** — what you'll build (a plugin that paints a live status dot driven by a background poll); the install requirement up front; link the busy-light concept as the shipped version of this pattern. (No new GIF.)
2. **The lifecycle hooks** — `overlay`, `on_startup` (+ `StartupContext`: `frame`/`session`/`config`), `on_shutdown`, and `spawn_tracked` for background work. The exception-guarded, paint-only overlay rule highlighted.
3. **Build the service** — the worked status-dot: shared state, the `overlay` painter, the `on_startup` poller spawned with `spawn_tracked`, using `ctx.session`. Call out: keep `paint` fast and non-raising; do real work in the poller, not the painter.
4. **Other surfaces at a glance** — compact snippets for **animation** (`frame_for → AnimationFrame`), **border** (`paint(canvas, frame_count)` on `BorderEffectBase`, declare `frame_invariant`), **easing** (`api.easing(name, fn)`), each linking to the tested [acme reference plugin](https://github.com/JamesAwesome/led-ticker/blob/main/examples/plugins/acme/__init__.py) for a complete example.
5. **Register & use it** — `register(api)` with the overlay + startup hook; no TOML needed (the overlay paints on every screen); install-before-preview note (and that an overlay shows on the sign when running `led-ticker`).
6. **Complete listing** — the full `examples/plugins/example_service/__init__.py`, byte-matched to the shipped file.
7. **If it doesn't work** — symptom-first: the dot never appears → the plugin isn't installed/loaded; the dot never changes → the poller errored or the URL is unreachable (it's caught; check logs); the panel froze → an overlay must never raise / must be paint-only (don't do blocking work in `paint`). Next-step CTA.

### 2. New tested example plugin: `examples/plugins/example_service/__init__.py`

- Minimal plugin (namespace `example_service`) registering the `overlay` painter + the `on_startup` poller. Imports only `led_ticker.plugin` + stdlib `asyncio`. Teaching comments.
- **Tripwire test** `tests/test_plugins/test_example_service_plugin.py` (behavioral): loads the plugin; asserts an `example_service` entry is in `result.overlays` **and** in `result.startup_hooks`; calls the registered `paint` against a stub canvas and asserts it draws the default "offline" red dot at `(0,0)` (no network, no event loop). Test lines ≤88 (CI ruff).

### 3. Sidebar + hub

- `docs/site/astro.config.mjs`: add "Service plugins" to the "Extending led-ticker" group (after "Custom color provider").
- `plugins/authoring/04-beyond-widgets.mdx`: the lifecycle-hooks section gets a pointer to the new page.

## Applying the DOCS-STYLE rubric

How-to (task) page: reader named; brief what-you'll-need (install up front); payoff stated in prose (+ busy-light link) since there's no apt GIF; complete copy-pasteable example + complete listing; concrete commands; gloss jargon (`overlay`, `on_startup`, `StartupContext`, `spawn_tracked`, `frame_for`, `frame_invariant`); **code bound to a tested source**; local "if it doesn't work" (panel-freeze + dot-not-updating); cross-link (busy-light, api-reference, acme); next-step CTA (this is the last Extending page — CTA points back to the API reference + the section). Time stamp (#12) / heavy reassurance (#15) lightly applied per the "more technical" steer; a missing GIF is an honest exception to #7 (no apt asset).

## The review loop

Tech-writer reviewer (DOCS-STYLE §3) + a repeat hobbyist-persona ("Sam") acceptance check ("could I build a background status light, and do I understand the overlay-must-not-freeze rule?"). Fix must-fix; re-review until both pass.

## Verification

- `make docs-build` + `make docs-lint` clean; the new page renders; "Service plugins" shows in the Extending sidebar group; links resolve.
- `tests/test_plugins/test_example_service_plugin.py` passes (overlay + startup registered; paint draws the default dot).
- `uv run --extra dev ruff check src/ tests/` clean.
- The page's "Complete listing" matches `examples/plugins/example_service/__init__.py`.
- The worked code uses only public-surface calls (`api.overlay`/`on_startup`, `spawn_tracked`, `StartupContext` via the hook arg, `canvas.SetPixel`).

## Out of scope (this piece)

- Full standalone walkthroughs for animation/border/easing (compact recap + acme links instead).
- Any change to runtime lifecycle/overlay code — docs + a new example plugin + a test only.
- A byte-match tripwire (behavioral test, per precedent).
- Rendering a new demo GIF for the status dot.
- This completes the Extending section; the remaining docs work (Phase 2a "how it works", Phase 3 audit) is separate.
