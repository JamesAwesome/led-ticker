# Extending led-ticker — Custom Color Provider How-To — Design

**Date:** 2026-06-05
**Status:** Approved (brainstorm), pending implementation plan

## Context

Piece 3 of the **"Extending led-ticker"** how-to section (after Custom emoji #157 and Writing a transition #158). Same trigger and tone as the others: a technical, worked-example how-to bound to a dedicated tested example plugin, reviewed by the tech-writer + a repeat hobbyist-persona ("Sam"). New branch `feat/docs-colorprovider` off the merged main.

## Decisions (from brainstorm)

- **Worked example: a `pulse` color provider** — one color for the whole string whose **brightness breathes** with the frame. Chosen over cloning the built-in rainbow because it most clearly demonstrates the concept that actually bites authors: `frame_invariant = False` (output depends on `frame`, so the widget must re-render each tick — declare it wrong and the animation silently freezes).
- Built with the **public surface only**: `make_color` + stdlib `math` (the internal `hue_color` is NOT public; a rainbow would need the author to write HSV, so it's mentioned as a variation, not the worked example).
- A short **"per-character variation"** note shows `per_char=True` + `char_index`/`total_chars` (how the built-in rainbow colors each letter), so the reader knows that surface exists without it bloating the worked example.
- **Tested example:** a new dedicated plugin `examples/plugins/example_colorprovider/` (namespace `example_colorprovider`) registering `example_colorprovider.pulse`, with a behavioral tripwire.
- Same install-before-preview honesty as the other pages.
- **Run `ruff check src/ tests/`** as part of verification (CI lints `src/ tests/`; the docs/test make targets don't — a ruff E501 in a new test file broke CI after #157).

## The accurate ColorProvider API (the page must get this right)

From `src/led_ticker/color_providers.py` and `app/coercion.py`:

- A color provider is a class implementing the `ColorProvider` protocol: class attrs `per_char: bool` and `frame_invariant: bool`, and `color_for(self, frame: int, char_index: int, total_chars: int) -> Color`.
- **`ColorProviderBase`** is the recommended base: it **requires** every subclass to declare `frame_invariant` as a class attr (raises `TypeError` at class-definition time otherwise). This is the guardrail against the silent-freeze bug.
- **`frame_invariant`**: `True` = `color_for` output is independent of `frame` (constant, gradient) — lets the engine paint-once-and-sleep; `False` = output varies per frame (pulse, rainbow, cycle) — forces the per-tick render loop so it actually animates. **Lying `True` when the output is animated freezes the widget with no error.**
- **`per_char`**: `False` = one color per call (whole string); `True` = called per character with a meaningful `char_index` (e.g. a per-letter hue).
- **`restart_on_visit`** (optional class attr, default behaves as reset-per-visit): set `False` to keep a continuous animation phase across a section's `loop_count`.
- **Registration in a plugin:** `@api.color_provider("pulse")` on the class → `namespace.pulse`. Used in TOML as `font_color = {style = "namespace.pulse"}` on a text widget.
- **Config fields:** `app/coercion._provider_from_style(style, kwargs)` looks the class up in `_PROVIDER_REGISTRY` and instantiates `cls(**kwargs)`, validating kwargs against the `__init__` signature. So `font_color = {style="ns.pulse", speed=6, color=[0,200,255]}` passes `speed`/`color` to the constructor. Plugin providers receive **raw** TOML values (a list for `color`, an int for `speed`) — there is no RGB→Color coercion for plugin provider fields (that special-casing applies only to the built-in `gradient`/`color_cycle`), so the example handles a raw `[r,g,b]` list itself.
- Public helpers available: `make_color(r,g,b)`, and `ColorProviderBase`, `ColorProvider`, `Color` are all in `led_ticker.plugin.__all__`.

**The worked `pulse`:** `per_char=False`, `frame_invariant=False`; `__init__(self, color=(0,200,255), speed=6)`; `color_for` computes `level = 0.65 + 0.35*sin(frame*speed*0.05)` and returns `make_color(int(r*level), int(g*level), int(b*level))`. (`import math` at module top.)

## Deliverable

### 1. New page: `plugins/extending/custom-color-provider.mdx`

Audience named (plugin authors). Technical how-to sections:

1. **Intro + what you'll need** — what you'll build (a color provider that pulses a message's brightness); payoff GIF (reuse `/demos/concepts-color-providers.gif`); brief prerequisites (a plugin scaffold — link the authoring guide; the install requirement stated up front, per the CI/preview lesson).
2. **The `ColorProvider` contract** — `color_for(frame, char_index, total_chars)`; `per_char` (whole-string vs per-letter); **`frame_invariant`** with the freeze warning prominent; subclass `ColorProviderBase` so the flag is enforced.
3. **Build the pulse** — the worked `color_for` (brightness via `math.sin`), the config fields (`color`, `speed`), and why `frame_invariant=False`. Note `restart_on_visit` for continuous phase across loops.
4. **Per-character variation** — a short note: set `per_char=True` and use `char_index`/`total_chars` to color each letter (the built-in rainbow's approach).
5. **Register & use it** — `@api.color_provider("pulse")`; `font_color = {style = "example_colorprovider.pulse", speed = 6}`; install-before-preview (`pip install -e .`, render-demo only loads installed plugins); preview command.
6. **Complete listing** — the full `examples/plugins/example_colorprovider/__init__.py`, byte-matched to the shipped file.
7. **If it doesn't work** — symptom-first, with the headline case: **"the color is frozen / doesn't animate" → you declared `frame_invariant=True` but `color_for` uses `frame`; set it `False`.** Plus name-not-found → namespacing/install; `TypeError: must define 'frame_invariant'` → declare the class attr. Next-step CTA.

### 2. New tested example plugin: `examples/plugins/example_colorprovider/__init__.py`

- Minimal plugin (namespace `example_colorprovider`) whose `register(api)` registers the `Pulse` class via `@api.color_provider("pulse")`. Imports only `led_ticker.plugin` + stdlib `math`. Teaching comments.
- **Tripwire test** `tests/test_plugins/test_example_colorprovider_plugin.py` (behavioral): loads the plugin; asserts `example_colorprovider.pulse` is in `_PROVIDER_REGISTRY`; asserts `per_char is False` and `frame_invariant is False`; asserts `color_for` returns **different** colors at two different frames (proving it animates); asserts the `color` config field flows through (a configured color comes out dimmed but nonzero). Test lines kept ≤88 cols (CI ruff).

### 3. Sidebar + hub

- `docs/site/astro.config.mjs`: add "Custom color provider" to the "Extending led-ticker" group (after "Writing a transition").
- `plugins/authoring/04-beyond-widgets.mdx`: the color-provider line (under "Render surfaces") gets a pointer to the new page.

## Applying the DOCS-STYLE rubric

How-to (task) page: reader named; brief what-you'll-need (with the install requirement up front); payoff GIF; complete copy-pasteable example + complete listing; concrete commands; gloss jargon (`color_for`, `per_char`, `frame_invariant`, `restart_on_visit`); **code bound to a tested source**; local "if it doesn't work" (freeze case headlined); cross-link; next-step CTA. Time stamp (#12) and heavy reassurance (#15) lightly applied per the "more technical" steer.

## The review loop

Tech-writer reviewer (DOCS-STYLE §3) + a repeat hobbyist-persona ("Sam") acceptance check ("could I build an animated color effect, and would I understand the `frame_invariant` flag?"). Fix must-fix; re-review until both pass.

## Verification

- `make docs-build` + `make docs-lint` clean; the new page renders; "Custom color provider" shows in the Extending sidebar group; links resolve.
- `tests/test_plugins/test_example_colorprovider_plugin.py` passes.
- `uv run --extra dev ruff check src/ tests/` clean (the CI lint scope).
- The page's "Complete listing" matches `examples/plugins/example_colorprovider/__init__.py`.
- The worked provider uses only public-surface calls (`ColorProviderBase`, `make_color`) + stdlib.

## Out of scope (this piece)

- The service/smaller-surface pages (later pieces).
- Any change to runtime color-provider code (`color_providers.py`, `coercion.py`) — docs + a new example plugin + a test only.
- A byte-match tripwire (behavioral test, per precedent).
- Documenting the full built-in provider catalog (that's the existing `concepts/color-providers` page — this page links to it, doesn't duplicate).
