# Extending led-ticker — Writing a Transition How-To — Design

**Date:** 2026-06-05
**Status:** Approved (brainstorm), pending implementation plan

## Context

Piece 2 of the **"Extending led-ticker"** how-to section (the section was designed in the Custom-emoji brainstorm; this is the next page). Triggered by the same hobbyist-persona review: "Sam" knew a transition's method was `frame_at` but not what `t`/`outgoing`/`incoming` meant, what to draw, or that the return value is ignored — and there was no worked example anywhere. The 2b API reference (merged in #157) added a one-line `frame_at` correctness note; this page is the full walkthrough that note points to.

Phase status: Phase 0/1 merged; 2b API reference + Extending piece 1 (Custom emoji) merged in #157. This = **Extending piece 2: Writing a transition**. New branch `feat/docs-transition` off the merged main.

**Tone:** technical how-to, worked-example-driven (the section's agreed style).

## Decisions (from brainstorm)

- **Worked example: a wipe** (Sam's ask), implemented the way the built-in wipes are — achievable with the **public surface only**.
- **Honesty framing (DOCS-STYLE #9):** it's a "sweep the old away behind a colored line, then reveal the new at the end" wipe. A *progressive* left-band-new / right-band-old reveal of arbitrary text is **not** cleanly doable because `DrawText` can't be clipped — which is exactly why the draw-then-blackout technique exists. The page states this rather than pretending.
- **Tested example:** a new dedicated plugin `examples/plugins/example_transition/` (namespace `example_transition`) registering `example_transition.wipe`, with a behavioral tripwire. (Mirrors the `example_emoji` decision; the widget tutorial's `example/` plugin stays untouched.)
- Same install-before-preview honesty as the emoji page (`make render-demo` only loads installed plugins).

## The accurate transition API (the page must get this right)

From `src/led_ticker/transitions/__init__.py`, `push.py`, `wipe.py`, `effects.py`:

- A transition is a class with `min_frames: int = 0` and `frame_at(self, t, canvas, outgoing, incoming, **kwargs) -> Canvas`.
- `t` runs **0.0 → 1.0**. "At `t=0`: render only `outgoing`. At `t=1.0`: render only `incoming`." (from the protocol docstring).
- `outgoing` / `incoming` are the two frames; each exposes **`.draw(canvas, cursor_pos=N)`** — paint that frame onto `canvas` starting at horizontal offset `N` (px). `cursor_pos=0` draws it in place.
- **The runner clears the canvas (`Clear()`/`Fill()`) before each `frame_at` call** — transitions must NOT clear it themselves.
- **The return value is ignored** (the engine renders to `canvas`); returning `canvas` is a harmless convention.
- Drawing tools available on the canvas a transition receives (used by the built-ins, so public-safe): `canvas.width`, `canvas.height` (use `getattr(canvas, "height", 16)` as the built-ins do), `canvas.SubFill(x, y, w, h, r, g, b)` to fill/black-out a sub-rectangle (the way to "clip", since `DrawText` can't be clipped), and `canvas.SetPixel(x, y, r, g, b)`.
- Registration in a plugin: `@api.transition("wipe")` on the class → `namespace.wipe` (TOML `transition = {type = "example_transition.wipe"}`). A config-driven field works via the constructor: `transition = {type="ns.wipe", color=[r,g,b]}` passes `color` to `__init__` (per the acme `Swoosh` precedent).
- Recognized `**kwargs` (safe to ignore): `outgoing_scroll_pos`, `duration_ms`, `incoming_bg_color`. The page mentions they exist but the worked example ignores them for simplicity.

**The worked wipe** (left → right; mirrors `WipeUp`/`WipeLeft`):
draw `outgoing` full; `SubFill` black the swept region `[0, edge)`; draw a 2px colored sweep line at `edge`; at `t≥1.0` draw `incoming`. `min_frames` set (e.g. 16) so the sweep is smooth regardless of duration. Default `color` cyan, overridable from TOML.

## Deliverable

### 1. New page: `plugins/extending/writing-a-transition.mdx`

Audience named (plugin authors). Technical how-to sections:

1. **Intro + what you'll build** — a custom `wipe` transition; payoff GIF (reuse `/demos/transitions-wipe.gif`). Brief prerequisites note (a plugin scaffold — link the authoring guide).
2. **The `frame_at` contract** — the signature; `t` 0→1; `outgoing`/`incoming` + their `.draw(canvas, cursor_pos=N)`; the return is ignored; the runner clears the canvas first. (Fills Sam's exact gaps.)
3. **The drawing tools** — `canvas.width`/`height`, `SubFill` (and *why* — `DrawText` can't be clipped), `SetPixel`.
4. **Build the wipe** — step the reader through the `frame_at` body (draw outgoing → blackout swept region → sweep line → snap to incoming at `t≥1.0`), `min_frames`, and the config-driven `color` field. Include the honesty note about the wipe style.
5. **Register & use it** — `@api.transition("wipe")`; the TOML (`transition = {type = "example_transition.wipe"}`, and with `color`); install-before-preview (`pip install -e .`, render-demo only loads installed plugins); preview command.
6. **Complete listing** — the full `examples/plugins/example_transition/__init__.py`, byte-matched to the shipped file.
7. **If it doesn't work** — symptom-first (transition name not found → namespacing/install; nothing happens → `min_frames`/duration; canvas looks wrong → don't clear it yourself) + next-step CTA (→ API reference, → other Extending pages).

### 2. New tested example plugin: `examples/plugins/example_transition/__init__.py`

- Minimal plugin (namespace `example_transition`) whose `register(api)` registers the `Wipe` class via `@api.transition("wipe")`. Imports only `led_ticker.plugin` + stdlib. Teaching comments.
- **Tripwire test** `tests/test_plugins/test_example_transition_plugin.py` (behavioral): loads the plugin into an isolated dir; asserts `example_transition.wipe` is in the transition registry; constructs the transition and calls `frame_at` against lightweight stub `outgoing`/`incoming` (objects recording `.draw(canvas, cursor_pos=...)` calls) and a stub canvas (with `width`/`height`/`SubFill`/`SetPixel`) at `t=0.5` and `t=1.0`, asserting it runs without error and that `incoming.draw` is called at `t≥1.0`. The exact registry accessor + stub shapes are pinned in the plan from the existing transition-plugin test pattern.

### 3. Sidebar + hub

- `docs/site/astro.config.mjs`: add "Writing a transition" to the "Extending led-ticker" group (after "Custom emoji").
- `plugins/authoring/04-beyond-widgets.mdx`: the transition line (under "Render surfaces") gets a pointer to the new page.

## Applying the DOCS-STYLE rubric

How-to (task) page: reader named; brief what-you'll-need; payoff GIF near top; complete copy-pasteable example + complete listing; concrete commands (install-before-preview); gloss jargon (`frame_at`, `t`, `cursor_pos`, `SubFill`, `min_frames`); **code bound to a tested source** (the `example_transition` plugin + tripwire); local "if it doesn't work"; honesty about the wipe's limits (#9); cross-link; next-step CTA. Time stamp (#12) and heavy reassurance (#15) lightly applied per the "more technical" steer.

## The review loop

Tech-writer reviewer (DOCS-STYLE §3) + a repeat **hobbyist-persona ("Sam") acceptance check** ("can I now build my wipe?") against the page. Fix must-fix; re-review until both pass.

## Verification

- `make docs-build` + `make docs-lint` clean; the new page renders; "Writing a transition" shows in the Extending sidebar group; links resolve.
- `tests/test_plugins/test_example_transition_plugin.py` passes (registration + `frame_at` behavior).
- The page's "Complete listing" matches `examples/plugins/example_transition/__init__.py`.
- The worked `frame_at` uses only public-surface calls (`.draw`, `SubFill`, `SetPixel`, `width`/`height`).

## Out of scope (this piece)

- The color-provider and service/smaller-surface pages (later pieces).
- Any change to runtime transition code (`transitions/*`) — docs + a new example plugin + a test only.
- A byte-match tripwire (behavioral test, per precedent).
- Progressive arbitrary-content reveal effects (documented as not cleanly doable, not implemented).
