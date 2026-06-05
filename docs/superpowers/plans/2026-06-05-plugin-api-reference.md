# Plugin API Reference Page (Phase 2b) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a canonical docs-site plugin API reference (`plugins/api-reference.mdx`) cataloging the public `led_ticker.plugin` surface, guard it with a drift tripwire test, and slim the in-repo `docs/plugin-system.md` to point at it.

**Architecture:** One new MDX page (Starlight default template, `Aside` + `RelatedPages`), a sidebar entry, a pytest tripwire that introspects `PluginAPI` + `plugin.__all__` and compares against marker-fenced regions in the page, and edits to `plugin-system.md` / `plugins/index.mdx` / `CLAUDE.md` so there's one source of truth. No runtime code changes.

**Tech Stack:** Astro Starlight, MDX, pytest. Docs verification via `make docs-build` / `make docs-lint`; test via `make test` (or `pytest`).

**Source spec:** `docs/superpowers/specs/2026-06-05-plugin-api-reference-design.md`

**Worktree:** `.claude/worktrees/docs-tech`, branch `feat/docs-tech`. Single PR.

**Commit convention:** `git -c core.hooksPath=/dev/null commit` for every commit.

**Authoritative surface (from `src/led_ticker/plugin.py`):**
- 12 public `PluginAPI` methods: `widget`, `transition`, `color_provider`, `animation`, `border`, `easing`, `emoji`, `hires_emoji`, `font`, `overlay`, `on_startup`, `on_shutdown`.
- 32 `__all__` names: `API_VERSION`, `PluginAPI`, `Animation`, `AnimationFrame`, `BorderEffect`, `BorderEffectBase`, `Canvas`, `Color`, `Container`, `DrawResult`, `ColorProvider`, `ColorProviderBase`, `Font`, `HiResEmoji`, `HiresFont`, `PixelData`, `SegmentMessage`, `StartupContext`, `Transition`, `TwoRowMessage`, `Updatable`, `Widget`, `colors`, `compute_baseline`, `draw_emoji_at`, `draw_text`, `get_text_width`, `make_color`, `measure_emoji_at`, `resolve_font`, `run_monitor_loop`, `spawn_tracked`.

---

### Task 1: Create the API reference page + sidebar entry

**Files:**
- Create: `docs/site/src/content/docs/plugins/api-reference.mdx`
- Modify: `docs/site/astro.config.mjs` (Plugins sidebar group)

- [ ] **Step 1: Write the page**

Create `docs/site/src/content/docs/plugins/api-reference.mdx` with EXACTLY this content. The two `<!-- api-methods -->` / `<!-- api-exports -->` marker regions are load-bearing — the Task 2 test parses them; do not remove or rename them.

````mdx
---
title: Plugin API reference
description: The complete public led_ticker.plugin surface — the register(api) contract, every registration method, the exported names, and the authoring conventions.
---

import { Aside } from "@astrojs/starlight/components";
import RelatedPages from "../../../components/RelatedPages.astro";

This page is for **developers writing a plugin**. It catalogs the entire public `led_ticker.plugin` surface: the `register(api)` entry point, every registration method, the names you can import, and the conventions a plugin follows. For a guided, build-it-up introduction, start with the [plugin authoring guide](/plugins/authoring/01-scaffold/); come here when you need the exact shape of something.

<Aside type="note">
A plugin imports **only** from `led_ticker.plugin`. Everything else under `led_ticker` is internal and can change without notice. If a name isn't on this page, treat it as private.
</Aside>

## The `register(api)` contract

A plugin is a Python package that exposes a top-level `register(api)` function under the `led_ticker.plugins` [entry-point group](https://packaging.python.org/en/latest/specifications/entry-points/) — an _entry point_ is how an installed package advertises a hook other code can discover. The loader finds it, builds a `PluginAPI` bound to your plugin's **namespace** (the prefix every registered name gets), and calls it:

```python
# my_plugin/__init__.py
from led_ticker.plugin import PluginAPI


def register(api: PluginAPI) -> None:
    @api.widget("clock")
    class Clock:
        def draw(self, canvas, frame): ...
```

```toml
# pyproject.toml
[project.entry-points."led_ticker.plugins"]
my_plugin = "my_plugin:register"
```

Two rules govern every registration:

- **Auto-namespacing.** Every name you register is prefixed with your plugin's namespace — `api.widget("clock")` in the `acme` plugin registers `acme.clock` (written in config as `type = "acme.clock"`). You cannot register a bare name or shadow a built-in.
- **Atomic load.** Calls buffer until `register()` returns cleanly. If `register()` raises, the whole plugin is discarded — there is no half-registered state.

`API_VERSION` (currently `(1, 0)`) is exported so a plugin can check the surface version it was built against.

## Registration methods

`PluginAPI` exposes twelve registration methods. The **decorator** forms register a class; the **call** forms register a value directly.

<!-- api-methods:start -->

### Visual building blocks

| Method | Form | Registers |
| --- | --- | --- |
| `api.widget(name)` | decorator | A [widget](/widgets/) class under `namespace.name` |
| `api.transition(name)` | decorator | A [transition](/transitions/) class |
| `api.color_provider(style)` | decorator | A [color provider](/concepts/color-providers/) class |
| `api.animation(style)` | decorator | An [animation](/concepts/animations/) class |
| `api.border(name)` | decorator | A [border effect](/concepts/borders/) class |
| `api.easing(name, fn)` | call | An easing function `(float) -> float` |

```python
@api.widget("clock")
class Clock:
    def draw(self, canvas, frame): ...


@api.transition("swirl")
class Swirl:
    def frame_at(self, t, canvas, outgoing, incoming, **kw): ...


api.easing("snap", lambda t: 0.0 if t < 0.5 else 1.0)
```

### Assets

| Method | Form | Registers |
| --- | --- | --- |
| `api.emoji(slug, data)` | call | A low-res 8×8 emoji (`PixelData`) under `namespace.slug` |
| `api.hires_emoji(slug, data)` | call | A hi-res emoji (`HiResEmoji`) for scaled-canvas draws |
| `api.font(name, path)` | call | A font file; `path` is relative to the plugin root |

### Lifecycle hooks

| Method | Form | Registers |
| --- | --- | --- |
| `api.overlay(paint)` | call | A `paint(canvas)` run every frame before the hardware swap |
| `api.on_startup(fn)` | call | A hook run once after the frame + session exist; receives a `StartupContext` |
| `api.on_shutdown(fn)` | call | A hook run best-effort when the run loop exits |

<!-- api-methods:end -->

<Aside type="caution">
Register overlays via `api.overlay` — only these are exception-guarded (a raise disables the hook and is logged, instead of freezing the panel). Appending directly to `StartupContext.frame.overlay_hooks` is **not** guarded. Likewise, a hi-res emoji with no matching `api.emoji(slug, …)` low-res counterpart logs a warning at load, because inline `:namespace.slug:` text and unscaled canvases resolve only through the low-res registry.
</Aside>

## Exported names

Everything importable from `led_ticker.plugin`. Subclass or annotate against these; don't reach into `led_ticker` internals.

<!-- api-exports:start -->

### Core

| Name | What it is |
| --- | --- |
| `PluginAPI` | The namespace-bound registrar passed to `register(api)` |
| `StartupContext` | Frozen dataclass passed to an `on_startup` hook (`frame`, `session`, `config`) |
| `API_VERSION` | `(major, minor)` tuple of the plugin surface version |

### Base classes & protocols

| Name | What it is |
| --- | --- |
| `Widget` | The widget protocol (a `draw()` or play-style widget) |
| `Container` | Monitor/container widget base (cycles a live `feed_stories` list) |
| `Updatable` | Protocol for widgets with `async def update(self)` |
| `Transition` | The [transition](/transitions/) protocol (`frame_at`) |
| `ColorProvider` | The [color-provider](/concepts/color-providers/) protocol (`color_for`) |
| `ColorProviderBase` | Base that enforces the `frame_invariant` class attr |
| `Animation` | The [animation](/concepts/animations/) protocol (`frame_for`) |
| `BorderEffect` | The [border](/concepts/borders/) protocol (`paint`) |
| `BorderEffectBase` | Base that enforces the `frame_invariant` class attr |
| `SegmentMessage` | Re-exported single-line message widget (compose stories from it) |
| `TwoRowMessage` | Re-exported two-row widget |

### Data & types

| Name | What it is |
| --- | --- |
| `Canvas` | The draw target (`SetPixel`, `width`, `height`) |
| `Color` | An rgbmatrix color value |
| `DrawResult` | The return shape of a widget `draw()` |
| `AnimationFrame` | The return shape of `Animation.frame_for` |
| `PixelData` | `list[(x, y, r, g, b)]` describing a low-res emoji |
| `HiResEmoji` | Hi-res emoji sprite data |
| `Font` | A resolved font handle |
| `HiresFont` | A resolved hi-res font |

### Helpers

| Name | What it is |
| --- | --- |
| `make_color(r, g, b)` | Build a `Color` from RGB components (0–255) |
| `draw_text(canvas, font, text, x, y, color)` | Draw text (inline `:emoji:` included); returns the next x |
| `get_text_width(font, text)` | Pixel width of `text` in `font` |
| `compute_baseline(font, ...)` | The baseline y for a font |
| `resolve_font(name, ...)` | Resolve a font by name (bundled, plugin, or BDF) |
| `draw_emoji_at(canvas, slug, x, y)` | Draw a registered emoji at a position |
| `measure_emoji_at(canvas, slug)` | Measure a registered emoji |
| `colors` | The built-in named-color module |
| `run_monitor_loop(widget, interval)` | The periodic-refresh loop for a monitor widget |
| `spawn_tracked(coro)` | Spawn a tracked background task from a `start()` / hook |

<!-- api-exports:end -->

## Conventions

A few behaviors are **conventions** the type carries, not `api.*` calls:

- **`validate_config`** — a widget may define `@classmethod validate_config(cls, cfg) -> list[str]`. It's called during config validation with the raw (pre-coercion) TOML for that widget; any returned strings become pre-flight errors. The rule travels with the widget type.
- **`font_color` injection** — to accept the standard `font_color` color-provider knob, declare a `font_color: object = None` field on the widget; the loader coerces the TOML value to a `ColorProvider` and injects it. Without the field, `font_color` is rejected as unknown.
- **`frame_invariant`** — `ColorProviderBase` / `BorderEffectBase` require subclasses to set a `frame_invariant: bool` class attr. `True` means output never varies by frame (enables a static fast path); `False` forces a per-tick redraw.
- **`restart_on_visit`** — a color provider or border may set `restart_on_visit = False` to keep a continuous animation phase across a section's `loop_count`, instead of resetting on each visit.

## Where to next

- **Build one step by step:** the [plugin authoring guide](/plugins/authoring/01-scaffold/) walks from scaffold to a packaged widget.
- **Loader internals & edge cases:** [`docs/plugin-system.md`](https://github.com/JamesAwesome/led-ticker/blob/main/docs/plugin-system.md) covers discovery, the `[plugins]` config block, deployment, and known surface gaps.
- **The surfaces you'll extend:** [widgets](/widgets/), [transitions](/transitions/), [color providers](/concepts/color-providers/), [animations](/concepts/animations/), [borders](/concepts/borders/).

<RelatedPages
  slugs={["plugins/authoring/01-scaffold", "plugins", "concepts/color-providers"]}
/>
````

- [ ] **Step 2: Add the sidebar entry**

In `docs/site/astro.config.mjs`, inside the `Plugins` group, insert the API reference between "Available plugins" and "Authoring a plugin". Change:

```js
            { label: "Available plugins", link: "/plugins/available/" },
            {
              label: "Authoring a plugin",
```

to:

```js
            { label: "Available plugins", link: "/plugins/available/" },
            { label: "API reference", link: "/plugins/api-reference/" },
            {
              label: "Authoring a plugin",
```

- [ ] **Step 3: Format, build, lint**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/docs-tech
make docs-format
make docs-build; echo "BUILD_EXIT=$?"
make docs-lint; echo "LINT_EXIT=$?"
```
Expected: both exit 0; build adds one page (`56 page(s) built`, up from 55). `astro check` validates the internal links — all the `/widgets/`, `/transitions/`, `/concepts/*`, `/plugins/*` targets resolve. If a link 404s, fix the target (all referenced pages exist: `widgets/index`, `transitions/index`, `concepts/color-providers|animations|borders`, `plugins/authoring/01-scaffold`).

- [ ] **Step 4: Confirm the markers survived formatting**

Prettier reflows MDX; confirm the HTML-comment markers are still present and intact (the Task 2 test depends on them):
```bash
cd /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/docs-tech/docs/site/src/content/docs
grep -c "api-methods:start\|api-methods:end\|api-exports:start\|api-exports:end" plugins/api-reference.mdx
```
Expected: `4`. If not 4, the markers were altered — restore them.

- [ ] **Step 5: Commit**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/docs-tech
git add docs/site/src/content/docs/plugins/api-reference.mdx docs/site/astro.config.mjs
git -c core.hooksPath=/dev/null commit -m "docs: add the plugin API reference page (Phase 2b)

Canonical docs-site reference for the public led_ticker.plugin surface: the
register(api) contract, all 12 registration methods, the 32 exported names,
and the authoring conventions. Sidebar entry under Plugins."
```

---

### Task 2: Drift tripwire test

**Files:**
- Create: `tests/test_docs_plugin_api_drift.py`

- [ ] **Step 1: Write the test**

Create `tests/test_docs_plugin_api_drift.py` with EXACTLY this content:

```python
"""Tripwire test for docs/site/.../plugins/api-reference.mdx drift.

The plugin API reference page hand-curates the public ``led_ticker.plugin``
surface: the registration methods on ``PluginAPI`` and the names in
``__all__``. Hand curation buys readable, cross-linked tables that pure
autogeneration would lose — but it can drift when ``plugin.py`` changes.

This test is that pressure. It asserts:
- the registration methods documented in the page's ``api-methods`` region
  exactly match ``PluginAPI``'s public methods, and
- the names documented in the page's ``api-exports`` region exactly match
  ``led_ticker.plugin.__all__``.

Marked regions in the .mdx make parsing robust:

    <!-- api-methods:start --> ... <!-- api-methods:end -->
    <!-- api-exports:start --> ... <!-- api-exports:end -->

When ``plugin.py``'s public surface changes, update the page inside those
markers — the test fails loudly (naming the missing/extra symbols) until the
page and the code agree.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

from led_ticker import plugin
from led_ticker.plugin import PluginAPI

REPO_ROOT = Path(__file__).resolve().parent.parent
PAGE_PATH = (
    REPO_ROOT
    / "docs"
    / "site"
    / "src"
    / "content"
    / "docs"
    / "plugins"
    / "api-reference.mdx"
)

_FIRST_COL_RE = re.compile(r"^\|\s*`([^`]+)`\s*\|", re.MULTILINE)


def _region(page_text: str, name: str) -> str:
    """Return the text between ``<!-- name:start -->`` and ``<!-- name:end -->``."""
    match = re.search(
        rf"<!--\s*{re.escape(name)}:start\s*-->(.*?)<!--\s*{re.escape(name)}:end\s*-->",
        page_text,
        re.DOTALL,
    )
    assert match, f"Marker region {name!r} not found in {PAGE_PATH}"
    return match.group(1)


def _documented_methods(page_text: str) -> set[str]:
    """Method names from ``api.<name>(`` occurrences in the api-methods region."""
    return set(re.findall(r"api\.(\w+)", _region(page_text, "api-methods")))


def _documented_exports(page_text: str) -> set[str]:
    """First-column backtick names in the api-exports region, call sigs stripped."""
    names: set[str] = set()
    for cell in _FIRST_COL_RE.findall(_region(page_text, "api-exports")):
        names.add(cell.split("(", 1)[0].strip())
    return names


def _real_methods() -> set[str]:
    """Public (non-underscore) methods on PluginAPI — the registration surface."""
    return {
        name
        for name, _ in inspect.getmembers(PluginAPI, predicate=inspect.isfunction)
        if not name.startswith("_")
    }


def test_docs_page_exists() -> None:
    assert PAGE_PATH.exists(), f"Plugin API reference page not found at {PAGE_PATH}"


def test_registration_methods_match() -> None:
    page_text = PAGE_PATH.read_text()
    documented = _documented_methods(page_text)
    real = _real_methods()
    missing = real - documented
    extra = documented - real
    assert not missing, (
        f"PluginAPI methods missing from the API reference methods tables: "
        f"{sorted(missing)}.\n"
        "Add a row inside the <!-- api-methods --> region of "
        "docs/site/src/content/docs/plugins/api-reference.mdx."
    )
    assert not extra, (
        f"API reference methods tables list names that aren't public PluginAPI "
        f"methods: {sorted(extra)}.\n"
        "They were renamed/removed in src/led_ticker/plugin.py, or the table "
        "has a typo."
    )


def test_exported_names_match() -> None:
    page_text = PAGE_PATH.read_text()
    documented = _documented_exports(page_text)
    real = set(plugin.__all__)
    missing = real - documented
    extra = documented - real
    assert not missing, (
        f"Names in led_ticker.plugin.__all__ missing from the API reference "
        f"exports tables: {sorted(missing)}.\n"
        "Add a row inside the <!-- api-exports --> region of "
        "docs/site/src/content/docs/plugins/api-reference.mdx."
    )
    assert not extra, (
        f"API reference exports tables list names not in "
        f"led_ticker.plugin.__all__: {sorted(extra)}.\n"
        "They were removed from __all__, or the table has a typo."
    )
```

- [ ] **Step 2: Run the test — expect PASS**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/docs-tech
make test PYTEST_ARGS="tests/test_docs_plugin_api_drift.py -v" 2>/dev/null || PYTHONPATH=tests/stubs python -m pytest tests/test_docs_plugin_api_drift.py -v
```
Expected: 3 tests pass (`test_docs_page_exists`, `test_registration_methods_match`, `test_exported_names_match`). If `test_registration_methods_match` fails, the page's `api-methods` region is missing a method row (or has a stray `api.x`); if `test_exported_names_match` fails, the `api-exports` tables don't list exactly the 32 `__all__` names — fix the page, not the test.

- [ ] **Step 3: Negative check — prove the tripwire bites**

Temporarily delete one exports row to confirm the test fails, then restore it:
```bash
cd /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/docs-tech
cp docs/site/src/content/docs/plugins/api-reference.mdx /tmp/api-ref.bak
# remove the `colors` row
perl -0pi -e 's/^\| `colors` \| The built-in named-color module \|\n//m' docs/site/src/content/docs/plugins/api-reference.mdx
PYTHONPATH=tests/stubs python -m pytest tests/test_docs_plugin_api_drift.py::test_exported_names_match -q; echo "RESULT=$? (expect non-zero)"
cp /tmp/api-ref.bak docs/site/src/content/docs/plugins/api-reference.mdx
PYTHONPATH=tests/stubs python -m pytest tests/test_docs_plugin_api_drift.py -q; echo "RESTORED=$? (expect 0)"
```
Expected: the middle run fails (`RESULT` non-zero, message naming `colors`), the restore run passes (`RESTORED=0`). Confirm `git status` shows no change to the page after restore.

- [ ] **Step 4: Commit**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/docs-tech
git add tests/test_docs_plugin_api_drift.py
git -c core.hooksPath=/dev/null commit -m "test: tripwire guarding the plugin API reference against drift

Introspects PluginAPI's public methods + led_ticker.plugin.__all__ and asserts
they match the marker-fenced tables in plugins/api-reference.mdx."
```

---

### Task 3: Slim `plugin-system.md` + redirect pointers

Make the docs-site page canonical: condense the duplicated API-surface sections of `plugin-system.md` to a pointer, and update the two links that currently send API-surface readers to `plugin-system.md`.

**Files:**
- Modify: `docs/plugin-system.md` (sections 2, 3, 5)
- Modify: `docs/site/src/content/docs/plugins/index.mdx` ("Writing a plugin" paragraph)
- Modify: `CLAUDE.md` (the "Plugin invariants" pointer line)

- [ ] **Step 1: Slim `plugin-system.md`**

Read `docs/plugin-system.md`. Make these surgical edits, preserving every other section:

1. Under **`## 2. The `register(api)` contract`** — keep the heading and the short code example, but replace any prose that re-catalogs the surface with a lead pointer line. Immediately after the `## 2.` heading, insert:
   > The canonical, reader-facing version of this contract and the full public surface now lives on the docs site: **[Plugin API reference](https://docs.ledticker.dev/plugins/api-reference/)**. This file keeps the loader-internal and deployment detail below.

2. Replace the **entire body** of **`## 3. The public surface (`led_ticker.plugin`)`** (everything from the `## 3.` heading line up to — but not including — `## 4.`) with:
   ```markdown
   ## 3. The public surface (`led_ticker.plugin`)

   The complete catalog — every registration method, the `__all__` exports, and
   the authoring conventions — is the canonical
   [Plugin API reference](https://docs.ledticker.dev/plugins/api-reference/) on
   the docs site (guarded against drift by
   `tests/test_docs_plugin_api_drift.py`). Sections 4–11 below cover what that
   page intentionally omits: deeper authoring patterns, loader internals,
   deployment, and known edges.
   ```

3. Replace the **entire body** of **`## 5. Non-widget surface contracts (minimal shapes)`** (from the `## 5.` heading up to — but not including — `## 6.`) with:
   ```markdown
   ## 5. Non-widget surface contracts (minimal shapes)

   The minimal class shapes for transitions, color providers, animations,
   borders, easings, emojis, and fonts are listed on the
   [Plugin API reference](https://docs.ledticker.dev/plugins/api-reference/)
   (each with the method it must implement). Worked, build-it-up examples of a
   custom transition and color provider are the subject of the forthcoming
   extension authoring walkthroughs.
   ```

Leave sections 1, 4, 6, 7, 8, 9, 10, 11 unchanged.

- [ ] **Step 2: Redirect the `plugins/index.mdx` pointer**

In `docs/site/src/content/docs/plugins/index.mdx`, the "Writing a plugin" section ends with a sentence pointing the surface to `plugin-system.md`. Replace:

```markdown
The engineering reference — the `register(api)` contract, the public surface, authoring patterns, and lifecycle hooks — is in [`docs/plugin-system.md`](https://github.com/JamesAwesome/led-ticker/blob/main/docs/plugin-system.md).
```

with:

```markdown
The full surface — the `register(api)` contract, every registration method, the exported names, and the conventions — is the [Plugin API reference](/plugins/api-reference/). For loader internals, deployment, and known edges, see [`docs/plugin-system.md`](https://github.com/JamesAwesome/led-ticker/blob/main/docs/plugin-system.md).
```

(If the exact source sentence differs slightly, match on the `docs/plugin-system.md` link and replace that sentence with the two-sentence version above.)

- [ ] **Step 3: Update the CLAUDE.md pointer**

In `CLAUDE.md`, replace the line:
```markdown
- Deep reference: `docs/plugin-system.md`. User-facing overview: the docs-site [Plugins page](https://docs.ledticker.dev/plugins/).
```
with:
```markdown
- API surface (canonical): the docs-site [Plugin API reference](https://docs.ledticker.dev/plugins/api-reference/) (drift-guarded by `tests/test_docs_plugin_api_drift.py`). Deep reference (loader internals, deployment, edges): `docs/plugin-system.md`. User-facing overview: the docs-site [Plugins page](https://docs.ledticker.dev/plugins/).
```

- [ ] **Step 4: Rebuild, lint, re-run the drift test**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/docs-tech
make docs-format
make docs-build; echo "BUILD_EXIT=$?"
make docs-lint; echo "LINT_EXIT=$?"
PYTHONPATH=tests/stubs python -m pytest tests/test_docs_plugin_api_drift.py -q; echo "DRIFT_EXIT=$?"
```
Expected: all exit 0. The `plugins/index.mdx` internal link `/plugins/api-reference/` must resolve (it exists from Task 1). `plugin-system.md` is not part of the Astro build, so its edits don't affect the build.

- [ ] **Step 5: Confirm the duplication is gone**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/docs-tech
# §3 and §5 should now be short pointers, not full catalogs.
awk '/^## 3\./,/^## 4\./' docs/plugin-system.md | wc -l
awk '/^## 5\./,/^## 6\./' docs/plugin-system.md | wc -l
```
Expected: each range is small (well under ~10 lines) — confirming the catalogs were condensed to pointers.

- [ ] **Step 6: Commit**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/docs-tech
git add docs/plugin-system.md docs/site/src/content/docs/plugins/index.mdx CLAUDE.md
git -c core.hooksPath=/dev/null commit -m "docs: make the API reference canonical; slim plugin-system.md to internals

Condense plugin-system.md's surface catalog (§2/§3/§5) to pointers at the new
docs-site API reference; redirect the Plugins-overview and CLAUDE.md pointers
to it. plugin-system.md keeps loader internals, deployment, and edges."
```

---

### Task 4: Technical-writer review pass

Per the spec's review loop, the controller dispatches a **technical-writer reviewer subagent** that reads `plugins/api-reference.mdx` (and the slimmed `plugin-system.md` / updated `plugins/index.mdx`), runs the `docs/DOCS-STYLE.md` §3 checklist treating the tutorial-only items (#11 what-you'll-need box, #12 time stamp, #13 local troubleshooting) as **N/A** for a reference page, and returns prioritized **must-fix** vs **nice-to-have** notes. The implementer applies must-fix items, re-runs `make docs-format && make docs-build && make docs-lint` + the drift test (all exit 0), and commits any fixes. If the page changed in a way that touches a marker region, re-run the drift test specifically.

- [ ] **Step 1:** Dispatch the tech-writer reviewer (rubric + N/A items as above).
- [ ] **Step 2:** Apply must-fix items; re-build/lint + re-run the drift test; confirm exit 0.
- [ ] **Step 3:** Commit fixes (`git -c core.hooksPath=/dev/null commit`), or record "no must-fix items".

---

## Self-Review

**1. Spec coverage:**
- New page under Plugins, audience named, 6 sections (intro, register contract, registration methods, exported names, conventions, where-to-next) → Task 1 Step 1. ✓
- Sidebar entry between "Available plugins" and "Authoring a plugin" → Task 1 Step 2. ✓
- Drift tripwire introspecting `PluginAPI` + `__all__` vs marker-fenced regions, with negative check → Task 2. ✓
- Slim `plugin-system.md` (condense §2/§3/§5 to pointers, keep internals) + redirect `plugins/index.mdx` + CLAUDE.md → Task 3. ✓
- DOCS-STYLE rubric application + tech-writer review loop with N/A items → Task 4. ✓
- Verification: build + lint clean, drift test passes + negatively-checked, duplication gone, no `plugin.py` change → Tasks 1/2/3 steps. ✓
- Out of scope (2a, 2c, no runtime code change, no new components) → respected (only `Aside`/`RelatedPages`, both existing). ✓

**2. Placeholder scan:** No TBD/TODO. Task 3 Step 2's "if the exact sentence differs" is a match-resilience note with the exact target text given, not a placeholder.

**3. Type/consistency:** The 12 methods and 32 `__all__` names in the page tables match the authoritative list in the header (cross-checked: methods region documents exactly the 12; exports tables document 3 + 11 + 8 + 10 = 32 names = `__all__`). The test's `_real_methods()` (public non-underscore `PluginAPI` functions) yields exactly those 12 (`namespace`/`root` are instance attributes, not class functions; `_qualify`/`_widgets`/`_transitions` are underscore-prefixed). The marker strings (`api-methods`, `api-exports`) match between the page (Task 1) and the test parser (Task 2). The component import path `../../../components/RelatedPages.astro` matches the verified depth-2 convention. Link targets (`/plugins/api-reference/`, `/widgets/`, `/transitions/`, `/concepts/*`) all correspond to existing pages.
