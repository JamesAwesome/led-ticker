# Plugin Authoring Guide — Design

**Date:** 2026-06-04
**Status:** Approved (brainstorm), pending implementation plan
**Context:** The deferred "next phase" after the pool extraction (Phases 1–6, complete). Today, plugin authoring is covered only by the terse engineering reference `docs/plugin-system.md` and two code examples (`examples/plugins/acme/`, the external `led-ticker-pool` repo); the docs-site Plugins overview only teases it.

## Goal

A pedagogical, build-it-yourself **plugin authoring guide** on the led-ticker docs site that takes a developer from nothing to a working, installed widget plugin — then surveys the other extension points. It complements (does not replace) the engineering reference.

## Decisions (from brainstorm)

- **Shape:** widget-first tutorial + a "beyond widgets" survey (not an every-surface reference, not a single annotated example).
- **Worked example:** build a NEW minimal widget from scratch in the guide, AND ship it as a tested example in the repo so the tutorial code can't drift.
- **Structure:** a multi-page numbered sub-section (`plugins/authoring/`) with prev/next nav, mirroring the 5-page beginner tutorial.
- **Relationship to `plugin-system.md`:** unchanged; the guide links to it (and to `acme`) for depth, never duplicates it.

## The worked example

A new minimal widget — a **"days-since" counter**:
- **Namespace/type:** `example` → `type = "example.counter"`.
- **Config fields** (`@attrs.define`): `since` (a `YYYY-MM-DD` date string, required), `label` (string, default `"DAY"`), `color` (`[r,g,b]`, optional accent).
- **`validate_config`:** `since` must parse as a date and not be in the future.
- **`draw()`:** computes whole days since `since`, renders `"<label> <N>"` (e.g. `DAY 42`) using `draw_text` + the `font_color` convention, accent color from `color`.
- **No external data** — deterministic, so it teaches config + `validate_config` + the `draw()` contract + color without networking or async.
- **Shipped at** `examples/plugins/example/__init__.py` (single-file, local-dir style, like `acme`), imports only `led_ticker.plugin` + stdlib + `attrs`.
- **Tested** by a new `tests/test_plugins/test_example_plugin.py`: loads the plugin, asserts `example.counter` registers, builds the widget, and `draw()` returns a canvas (drift tripwire). The tutorial's code blocks are excerpts of this real file.

## Pages (`plugins/authoring/`)

Each page is an `.mdx` with `<TutorialNav>` prev/next, using `<Steps>`, `<Aside>`, `<Tabs>`, and `<Code>`/`<TomlExample>`.

1. **`01-scaffold.mdx` — Scaffold & register.** What a plugin is (a package exposing `register(api)`); the file layout; the two discovery channels via `<Tabs>` — local `config/plugins/<name>/` directory vs a packaged `led_ticker.plugins` entry point; namespaces (`<plugin>.<name>`); `requires_api`/`API_VERSION`. Verify a do-nothing `register(api)` loads with `led-ticker plugins`. **End state:** an empty plugin that loads.
2. **`02-widget.mdx` — Build the widget.** `@api.widget("counter")`; config fields with `@attrs.define`; the `draw(canvas, cursor_pos=0, *, y_offset=0, font_color=None)` contract and what it must return; the `font_color` convention (honor the injected color); helpers `make_color`, `resolve_font`, `draw_text`, `get_text_width`; and `validate_config(cls, cfg) -> list[str]`. **End state:** a working `example.counter` widget. Show its config TOML + the rendered idea (a `<DemoGif>` only if cheap to render; otherwise a captioned still/description — see Open question).
3. **`03-package.mdx` — Package, install & test.** Turning the local plugin into a distributable package: `pyproject.toml` with the `[project.entry-points."led_ticker.plugins"]` block; adding it to `config/requirements-plugins.txt` (link to the [Plugins overview](/plugins/) for the constraint-based build install — do not duplicate that mechanism); testing locally against the bundled rgbmatrix stub (`tests/stubs`, the `pythonpath` trick). Point to `led-ticker-pool` as the full packaged real-world example.
4. **`04-beyond-widgets.mdx` — Beyond widgets.** A survey: one short snippet each for the remaining surfaces — `api.transition`, `api.color_provider`, `api.animation`, `api.border`, `api.easing`, `api.emoji` + `api.hires_emoji`, `api.font` — and the three lifecycle hooks `api.overlay` / `api.on_startup` / `api.on_shutdown` (the "service plugin" pattern, `spawn_tracked`, `StartupContext`). Each links to the matching part of `acme` + `plugin-system.md`. Not a page-per-surface — a scannable map with pointers.

## Navigation & cross-links

- **Sidebar (`astro.config.mjs`):** under the existing **Plugins** group, add the four authoring pages (e.g. nested or sequential, matching the tutorial's numbered style): `Authoring: 1. Scaffold`, `2. Build the widget`, `3. Package & install`, `4. Beyond widgets`. Keep `Plugins overview` and `Available plugins` as the first two entries.
- **Plugins overview:** replace the "Writing a plugin … a step-by-step authoring guide is planned / the pool repo is the worked example" passage with a link to the new guide (`/plugins/authoring/01-scaffold/`), keeping the `plugin-system.md` + `led-ticker-pool` references as "for depth / a real packaged example."
- The guide's pages link back to the overview (install flow) and to `plugin-system.md` (full contract).

## Components & house style

Reuse the tutorial's components: `<TutorialNav>`, `<Steps>`, `<Aside>` (info/tip/caution), `<Tabs>`, `<Code>`/`<TomlExample>`, and `<DemoGif>` only where a rendered demo already exists or is cheap to produce. Match the docs-site voice (pragmatic, second-person, no marketing). Gotchas to call out via `<Aside caution>`: no `from __future__ import annotations` in plugin source (PEP 649 / ruff UP037); hi-res emoji must be paired with a low-res fallback; single-file vs package layout; per-row font knobs are widget-specific.

## Testing / verification

- `make docs-build` (site builds; new pages produced; no broken internal links) and `make docs-lint` (prettier + astro check) clean.
- The new `examples/plugins/example/` plugin loads and `example.counter` registers + draws — asserted by `tests/test_plugins/test_example_plugin.py`, green in `make test`.
- The tutorial code blocks match the shipped example file (a reviewer diff-checks snippets against `examples/plugins/example/__init__.py`).

## Open question (resolve during planning, not blocking)

- **Rendered demo for page 2:** whether to render a `<DemoGif>` of `example.counter` (via the repo's demo-rendering tooling, `make render-demo`) or describe/screenshot it. Default: describe it + a TOML example; add a GIF only if the existing tooling renders it cheaply. The plan will decide based on `make render-demo` ergonomics.

## Out of scope

- Moving `plugin-system.md` onto the docs site (it stays the repo engineering reference).
- A cookiecutter / `led-ticker new-plugin` scaffolding generator.
- A page-per-surface deep dive (page 4 stays a survey).
- Changes to the plugin API itself (docs only).
