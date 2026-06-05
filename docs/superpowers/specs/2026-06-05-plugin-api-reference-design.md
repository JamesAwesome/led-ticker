# Plugin API Reference Page — Design (Phase 2b)

**Date:** 2026-06-05
**Status:** Approved (brainstorm), pending implementation plan

## Context: the larger docs effort

This is **Phase 2b** of a phased deep-dive expansion + review of the led-ticker docs site. Phase status:

- **Phase 0 (shipped, #155):** the docs style guide + review rubric (`docs/DOCS-STYLE.md`).
- **Phase 1 (shipped, #156):** the home/landing page — positions led-ticker as an extensible library, signposts two audiences.
- **Phase 2 (this phase):** expand the technical/API docs. Decomposed into three sequenced sub-parts, each its own spec → plan → implementation cycle:
  - **2b (this spec):** a `led_ticker.plugin` **API reference** page (chosen first — it's the keystone the home page now advertises, and has the most ready source material).
  - **2c (next):** extension authoring walkthroughs (custom transition + custom color provider).
  - **2a (last):** a "how it works"/render-architecture page.
- **Phase 3:** deep-dive audit + fixes of the existing ~58 pages.

Each task in this sub-part is reviewed by a **technical-writer reviewer subagent** applying the `docs/DOCS-STYLE.md` rubric. This spec covers **Phase 2b only**.

## Goal

Give plugin authors a single, canonical, polished reference for the public `led_ticker.plugin` surface on the docs site. Today that surface is only documented in the in-repo `docs/plugin-system.md` (244 lines, engineer-grade, off-site) and the linked GitHub file — there is no docs-site API reference, even though the Phase 1 home page now sends developers to "Build on it → the public API."

## Decisions (from brainstorm)

- **Placement:** `docs/site/src/content/docs/plugins/api-reference.mdx`, with a sidebar entry **between "Available plugins" and "Authoring a plugin"** (keeps the plugin-author journey together).
- **Relationship to `docs/plugin-system.md`:** the docs-site page becomes the **canonical** public API reference; `plugin-system.md` is **slimmed** — its API-surface sections condense to a pointer at the new page, while it keeps loader internals, discovery/CLI/deploy, known surface-gaps/edges, and the reference-example pointer. One source of truth per topic.
- **Drift protection:** add a **tripwire test** `tests/test_docs_plugin_api_drift.py` that fails if the documented surface diverges from the real `led_ticker.plugin` (mirrors the existing `tests/test_docs_config_options_drift.py`).
- **Depth:** document the `register(api)` contract and all 12 registration methods thoroughly; present the ~50 exported types as a **categorized table** (name + one-line + cross-link), not exhaustive prose (YAGNI).
- **No runtime code changes:** `src/led_ticker/plugin.py` is not modified. This sub-part is docs + the new tripwire test + the `plugin-system.md` slim.

## The public surface being documented

From `src/led_ticker/plugin.py` (319 lines). `__all__` exports ~50 names. `PluginAPI` registration methods:

| Method | Form | Registers |
|--------|------|-----------|
| `api.widget(name)` | decorator | Widget class → `namespace.name` |
| `api.transition(name)` | decorator | Transition class |
| `api.color_provider(style)` | decorator | ColorProvider class |
| `api.animation(style)` | decorator | Animation class |
| `api.border(name)` | decorator | BorderEffect class |
| `api.easing(name, fn)` | call | Easing function `(float) -> float` |
| `api.emoji(slug, data)` | call | Lo-res 8×8 `PixelData` |
| `api.hires_emoji(slug, data)` | call | Hi-res emoji |
| `api.font(name, path)` | call | Font file (path rel. to plugin root) |
| `api.overlay(paint)` | call | Per-frame paint fn (exception-guarded) |
| `api.on_startup(fn)` | call | Startup hook `(StartupContext) -> Any` |
| `api.on_shutdown(fn)` | call | Shutdown hook `() -> Any` |

Contracts/conventions to document: auto-namespacing (can't shadow built-ins); atomic load (registrations buffer until `register()` returns cleanly; any error discards the whole plugin); `validate_config` (widget `@classmethod validate_config(cls, cfg) -> list[str]`, raw pre-coercion TOML); `font_color` field-injection convention; `restart_on_visit` and `frame_invariant` class-attr conventions; `API_VERSION`.

The plan will re-derive exact signatures and the full `__all__` from `plugin.py` at authoring time (the source of truth), not from this spec's summary.

## Deliverable

### 1. New page: `plugins/api-reference.mdx`

Audience named at the top (plugin authors / developers). Sections:

1. **Intro** — what `led_ticker.plugin` is: the single curated public import surface (a plugin imports *only* from it); the `register(api)` entry point; everything auto-namespaced; atomic load. Cross-links to [Plugins overview](/plugins/) and the authoring guide.
2. **The `register(api)` contract** — the `led_ticker.plugins` entry-point group; `register(api: PluginAPI) -> None`; buffer-then-commit semantics; the `<plugin>.<name>` namespacing rule.
3. **Registration methods** — a summary table, then brief detail for each of the 12, grouped into *visual building blocks* (`widget`, `transition`, `color_provider`, `animation`, `border`, `easing`), *assets* (`emoji`, `hires_emoji`, `font`), and *lifecycle* (`overlay`, `on_startup`, `on_shutdown`). Each entry: signature, one-line purpose, namespacing note, a minimal example. Examples are illustrative one-liners (e.g. `@api.widget("clock")`); the drift test (below) guards the method set, so snippets need not be byte-bound to a tested file.
4. **Exported types** — a categorized table: *drawing* (`Canvas`, `Color`, `draw_text`, `make_color`, `get_text_width`, `compute_baseline`, `resolve_font`, `draw_emoji_at`, `measure_emoji_at`, `colors`), *base classes & protocols* (`Widget`, `Transition`, `ColorProvider`/`ColorProviderBase`, `Animation`, `BorderEffect`/`BorderEffectBase`, `Container`, `Updatable`), *data/context* (`StartupContext`, `DrawResult`, `AnimationFrame`, `PixelData`, `HiResEmoji`, `Font`/`HiresFont`, `SegmentMessage`, `TwoRowMessage`), *helpers* (`run_monitor_loop`, `spawn_tracked`, `API_VERSION`). Each: name + one-line + cross-link to the page that explains it where one exists (e.g. color providers, animations, borders, fonts concept pages).
5. **Conventions** — `validate_config`, `font_color` field injection, `restart_on_visit`, `frame_invariant`, `API_VERSION`.
6. **Where to next** — the authoring walkthroughs (2c, forthcoming; link the existing widget authoring guide now) and `docs/plugin-system.md` for loader internals/edge cases. A next-step CTA (per DOCS-STYLE #16).

### 2. Tripwire test: `tests/test_docs_plugin_api_drift.py`

Asserts the API reference can't silently drift from the code. Approach (mirrors `tests/test_docs_config_options_drift.py`):

- Introspect the real surface: the public registration-method names on `led_ticker.plugin.PluginAPI` (callable, non-underscore), and `led_ticker.plugin.__all__`.
- Parse the documented surface from `plugins/api-reference.mdx` — read from explicit machine-readable markers in the page so parsing is robust (e.g. an HTML comment fence `<!-- api-methods:start -->` … `<!-- api-methods:end -->` around the registration-method list, and `<!-- api-exports:start/end -->` around the exported-types list, or a comparably stable convention the plan pins).
- Assert: every real registration method appears in the documented method set and vice-versa; every name in `__all__` appears in the documented exports table and vice-versa. On mismatch, the test message names the missing/extra symbols and points the author at the page section to update.
- The plan specifies the exact marker convention and the parser so the page and test are authored together and consistent.

### 3. Slim `docs/plugin-system.md`

- Condense the three API-surface sections (the `register(api)` contract, the public-surface catalog, the non-widget surface contracts) to a short paragraph that points at `plugins/api-reference.mdx` as the canonical reference.
- Keep: loader internals, discovery/CLI/deployment, known surface-gaps/edges, and the reference-example (`examples/plugins/acme/`) pointer.
- Update the link in `plugins/index.mdx` (the "Writing a plugin" paragraph) to send API-surface questions to the new page (keep the `plugin-system.md` link for loader internals).
- Update the CLAUDE.md "## Plugin invariants" pointer so the new page is named as the API surface and `plugin-system.md` remains the deep-internals link.

## Applying the DOCS-STYLE rubric

- **Reader named up front** → intro states it's for plugin authors.
- **Payoff near the top** → the intro's one-import rule + a minimal `register(api)` example show the shape immediately.
- **Gloss jargon** → "entry point," "namespacing," "atomic load," "color provider," "frame-invariant" each get a one-line gloss or link on first use.
- **Complete, concrete examples** → each method's snippet is runnable-shaped; the page links the full worked example (`examples/plugins/acme/` via the authoring guide).
- **Internal consistency / code bound to tested source** → the drift test binds the documented method + export sets to `plugin.py`.
- **Cross-link, don't re-explain** → the exported-types table links to the concept pages instead of restating them.
- **Next-step CTA** → §6.
- **N/A for this page** (reference, not a task page): the "what you'll need" box (#11), time/effort stamp (#12), and local "if it doesn't work" troubleshooting (#13). The reviewer treats these as N/A.

## The review loop (this sub-part)

After each task builds clean, a **technical-writer reviewer subagent** runs the `docs/DOCS-STYLE.md` §3 checklist (with the N/A items above) against the changed page(s) and returns prioritized must-fix vs nice-to-have notes; the implementer fixes must-fix items and re-reviews until the checklist passes. Runs alongside the standard spec-compliance review.

## Verification

- `make docs-build` passes (exit 0); the new page renders; the sidebar shows "API reference" in the right slot.
- `make docs-lint` passes (run `make docs-format` first if Prettier complains; never pipe `docs-lint` to `tail`). `astro check` validates internal links — every cross-link must resolve.
- `tests/test_docs_plugin_api_drift.py` passes against the authored page and the real `plugin.py`; deliberately removing a documented method (or adding a fake one) makes it fail (the plan includes this negative check).
- `plugin-system.md`, `plugins/index.mdx`, and CLAUDE.md no longer duplicate the API-surface catalog; each points at the canonical page.
- No change to `src/led_ticker/plugin.py` runtime behavior.

## Out of scope (Phase 2b)

- Sub-parts 2a ("how it works") and 2c (authoring walkthroughs) — separate specs.
- Any change to the plugin runtime/loader code (`plugin.py` and the loader) — docs + a test + a doc-slim only.
- New Astro components.
- Documenting widget authoring in depth (already covered by the plugin authoring guide) beyond linking to it.
- An exhaustive prose entry per exported type (the categorized table is deliberate; YAGNI).
