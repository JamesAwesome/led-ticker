# Extending led-ticker — Service Plugins How-To (piece 4) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the final Extending how-to — "Service plugins" — a worked background-poller + status-overlay example (plus a compact animation/border/easing recap), backed by a dedicated tested example plugin.

**Architecture:** A new tested example plugin (`examples/plugins/example_service/`) + a behavioral tripwire (overlay + startup registered; paint draws the default dot); a new MDX how-to page whose "Complete listing" matches that plugin; a sidebar entry; a hub pointer from `04-beyond-widgets`. No runtime code changes.

**Tech Stack:** Astro Starlight, MDX, pytest. Docs: `make docs-build`/`make docs-lint`. Tests: `PYTHONPATH=tests/stubs uv run python -m pytest`. Lint: `uv run --extra dev ruff check src/ tests/` (run before committing Python).

**Source spec:** `docs/superpowers/specs/2026-06-05-extending-service-plugins-design.md`

**Worktree:** `.claude/worktrees/docs-service`, branch `feat/docs-service`. **Commit convention:** `git -c core.hooksPath=/dev/null commit`.

**Accurate API (verified):** `api.overlay(paint)` → `paint(canvas)` runs every frame pre-swap, exception-guarded; `api.on_startup(fn)` → `fn(StartupContext)` (`.session`/`.config`/`.frame`), sync/async, once; `spawn_tracked(coro)` spawns tracked background work; `LoadedPlugins` result has `.overlays`/`.startup_hooks` lists of `(namespace, callable)`. Animation: `frame_for(frame, full_text, canvas_width, text_width) -> AnimationFrame(visible_text=...)`. Border: `BorderEffectBase` + `paint(canvas, frame_count)`. Easing: `api.easing(name, fn)`.

---

### Task 1: Dedicated service example plugin + tripwire test

**Files:**
- Create: `examples/plugins/example_service/__init__.py`
- Create: `tests/test_plugins/test_example_service_plugin.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_plugins/test_example_service_plugin.py`:

```python
"""Tripwire for the Service plugins how-to's example plugin.

Keeps examples/plugins/example_service (the page's code) honest: the overlay and
the on_startup hook register, and the overlay paints a status dot.
"""

import shutil
from pathlib import Path

import pytest

from led_ticker import _plugin_loader as L

EXAMPLE_DIR = (
    Path(__file__).resolve().parents[2] / "examples" / "plugins" / "example_service"
)


def _canvas():
    from rgbmatrix import RGBMatrix, RGBMatrixOptions

    opts = RGBMatrixOptions()
    opts.cols = 64
    opts.rows = 32
    opts.chain_length = 1
    opts.parallel = 1
    return RGBMatrix(options=opts).CreateFrameCanvas()


@pytest.fixture
def result(tmp_path):
    L.reset_plugins()
    pdir = tmp_path / "plugins"
    pdir.mkdir()
    shutil.copytree(EXAMPLE_DIR, pdir / "example_service")
    try:
        res = L.load_plugins(pdir, entry_points_enabled=False)
        loaded = {i.namespace for i in res.loaded}
        assert "example_service" in loaded, res.failed
        yield res
    finally:
        L.reset_plugins()


def test_overlay_and_startup_registered(result):
    overlay_ns = [ns for ns, _ in result.overlays]
    startup_ns = [ns for ns, _ in result.startup_hooks]
    assert "example_service" in overlay_ns
    assert "example_service" in startup_ns


def test_overlay_paints_default_status_dot(result):
    paint = next(fn for ns, fn in result.overlays if ns == "example_service")
    canvas = _canvas()
    paint(canvas)
    # Default state is offline -> a red dot at (0, 0).
    assert canvas.get_pixel(0, 0) == (200, 0, 0)
```

- [ ] **Step 2: Run it — expect FAIL**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/docs-service
PYTHONPATH=tests/stubs uv run python -m pytest tests/test_plugins/test_example_service_plugin.py -q; echo "EXIT=$?"
```
Expected: FAIL (the `example_service` dir doesn't exist → fixture load assertion fails). If `uv run` isn't set up, run `uv sync --extra dev` first.

- [ ] **Step 3: Write the plugin**

Create `examples/plugins/example_service/__init__.py`:

```python
"""Example led-ticker plugin: a 'service' plugin — a background poller + a status overlay.

Drop `example_service/` into your `config/plugins/` (local use), or package it with an
`[project.entry-points."led_ticker.plugins"]  example_service = "example_service:register"`
entry. No TOML needed — the overlay paints a corner status dot on every screen.

Imports only `led_ticker.plugin` (the public surface) plus stdlib.
"""

import asyncio

from led_ticker.plugin import spawn_tracked


def register(api):
    # Shared state: the background poller writes it, the overlay reads it.
    state = {"online": False}

    def paint(canvas):
        # Runs every frame on the real canvas, BEFORE the hardware swap. Keep it
        # paint-only and fast, and never raise — a raising overlay is disabled and
        # logged, and must never be able to freeze the panel.
        r, g, b = (0, 200, 0) if state["online"] else (200, 0, 0)
        canvas.SetPixel(0, 0, r, g, b)  # a status dot in the top-left corner

    api.overlay(paint)

    async def start(ctx):
        # Runs once, after the frame + HTTP session exist. `ctx.session` is the
        # shared aiohttp ClientSession; `ctx.config` is the parsed app config.
        async def poll():
            while True:
                try:
                    async with ctx.session.get("https://example.com/health") as resp:
                        state["online"] = resp.status == 200
                except Exception:
                    state["online"] = False
                await asyncio.sleep(30)

        # Launch the long-lived poller as a tracked background task.
        spawn_tracked(poll())

    api.on_startup(start)
```

- [ ] **Step 4: Run the test — expect PASS; then ruff**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/docs-service
PYTHONPATH=tests/stubs uv run python -m pytest tests/test_plugins/test_example_service_plugin.py -q; echo "TEST=$?"
uv run --extra dev ruff check src/ tests/; echo "RUFF=$?"
```
Expected: 2 passed, `TEST=0`; `RUFF=0` (test lines ≤88; `examples/` isn't in ruff's CI scope). If ruff flags the test file, wrap the offending line.

- [ ] **Step 5: Commit**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/docs-service
git add examples/plugins/example_service/__init__.py tests/test_plugins/test_example_service_plugin.py
git -c core.hooksPath=/dev/null commit -m "test: dedicated example_service plugin + tripwire for the Service plugins how-to

A focused plugin (namespace example_service) registering a status overlay + an
on_startup poller, with a behavioral tripwire asserting both hooks register and
the overlay paints the default status dot."
```

---

### Task 2: The Service plugins how-to page + sidebar + hub pointer

**Files:**
- Create: `docs/site/src/content/docs/plugins/extending/service-plugins.mdx`
- Modify: `docs/site/astro.config.mjs`
- Modify: `docs/site/src/content/docs/plugins/authoring/04-beyond-widgets.mdx`

- [ ] **Step 1: Write the page**

Create `docs/site/src/content/docs/plugins/extending/service-plugins.mdx` with EXACTLY this content. The "Complete listing" python block MUST be byte-identical to `examples/plugins/example_service/__init__.py` from Task 1.

````mdx
---
title: Service plugins
description: Build a service plugin for led-ticker — a background poller via on_startup and spawn_tracked, plus a status overlay painted every frame. Plus animation, border, and easing.
---

import { Aside, Steps } from "@astrojs/starlight/components";
import RelatedPages from "../../../../components/RelatedPages.astro";

This is a how-to for **plugin authors**: build a **service plugin** — one that runs background work and paints a live indicator on the sign, instead of (or alongside) a widget. You'll build a status dot that turns green or red based on a background health check. The shipped [busy-light](/concepts/busy-light/) is a real-world version of this exact pattern.

**What you'll need:**

- A scaffolded plugin — see the [authoring guide](/plugins/authoring/01-scaffold/); you only import `led_ticker.plugin`.
- No hardware needed to develop, but an overlay shows on the sign when you run `led-ticker`.
- Your plugin **installed** (`pip install -e .` from its directory).

## The lifecycle hooks

A service plugin uses hooks instead of (or alongside) a widget:

- **`api.overlay(paint)`** — registers `paint(canvas)`, run **every frame on the real canvas, just before the hardware swap**. Use it to draw an indicator over whatever else is on screen. It's **exception-guarded**: if it raises, led-ticker disables it and logs — it can never freeze the panel. Keep it paint-only and fast.
- **`api.on_startup(fn)`** — `fn` runs once, after the panel and a shared HTTP session exist. It receives a **`StartupContext`** with `.session` (a shared `aiohttp.ClientSession`), `.config` (your parsed config), and `.frame`. Sync or async.
- **`spawn_tracked(coro)`** — start long-lived background work (a poll loop) as a tracked task from your startup hook: `spawn_tracked(poll())`.
- **`api.on_shutdown(fn)`** — optional cleanup when the loop exits.

<Aside type="caution">
  Do the slow work (network, sleeps) in the **poller**, never in `paint`. `paint` runs every frame — blocking or raising there stutters or disables your overlay. The painter should only read shared state and draw.
</Aside>

## Build the service

Hold shared state, paint it in the overlay, and update it from a background poller:

```python
def register(api):
    state = {"online": False}

    def paint(canvas):
        r, g, b = (0, 200, 0) if state["online"] else (200, 0, 0)
        canvas.SetPixel(0, 0, r, g, b)  # a status dot in the corner

    api.overlay(paint)

    async def start(ctx):
        async def poll():
            while True:
                try:
                    async with ctx.session.get("https://example.com/health") as resp:
                        state["online"] = resp.status == 200
                except Exception:
                    state["online"] = False
                await asyncio.sleep(30)

        spawn_tracked(poll())

    api.on_startup(start)
```

`ctx.session` is shared across all plugins, so you don't manage your own HTTP client. The poller loops forever on its own schedule; the overlay just reflects the latest `state`.

## Other surfaces at a glance

The remaining plugin surfaces are one-method classes (or a plain function), registered the same way. Each is shown complete in the tested [acme reference plugin](https://github.com/JamesAwesome/led-ticker/blob/main/examples/plugins/acme/__init__.py):

**Animation** — transforms the text shown each frame (e.g. a typewriter):

```python
@api.animation("scramble")
class Scramble:
    def frame_for(self, frame, full_text, canvas_width, text_width):
        return AnimationFrame(visible_text=full_text)
```

**Border** — paints a 1–2px ring around the content each frame. Subclass `BorderEffectBase` and declare `frame_invariant` (same rule as a [color provider](/plugins/extending/custom-color-provider/)):

```python
@api.border("neon")
class Neon(BorderEffectBase):
    frame_invariant = False

    def paint(self, canvas, frame_count):
        ...  # draw the ring with canvas.SetPixel
```

**Easing** — a plain `(float) -> float` curve, registered directly (no class):

```python
api.easing("snap", lambda p: p * p)
```

## Register and use it

<Steps>

1. Register the overlay + startup hook in `register(api)` (the complete listing is below). No TOML is needed — the overlay paints on every screen automatically.

2. Install your plugin so led-ticker loads it:

   ```bash
   pip install -e .   # run from your plugin's directory
   ```

3. Run it on the sign — the status dot appears in the corner:

   ```bash
   led-ticker --config config/config.toml
   ```

</Steps>

<Aside type="note">
  Overlays and startup hooks run on the live engine, so `make render-demo` (which renders widgets to a GIF) won't show them — run `led-ticker` on the Pi to see a service plugin in action.
</Aside>

## Complete listing

The full plugin — `examples/plugins/example_service/__init__.py`:

```python
"""Example led-ticker plugin: a 'service' plugin — a background poller + a status overlay.

Drop `example_service/` into your `config/plugins/` (local use), or package it with an
`[project.entry-points."led_ticker.plugins"]  example_service = "example_service:register"`
entry. No TOML needed — the overlay paints a corner status dot on every screen.

Imports only `led_ticker.plugin` (the public surface) plus stdlib.
"""

import asyncio

from led_ticker.plugin import spawn_tracked


def register(api):
    # Shared state: the background poller writes it, the overlay reads it.
    state = {"online": False}

    def paint(canvas):
        # Runs every frame on the real canvas, BEFORE the hardware swap. Keep it
        # paint-only and fast, and never raise — a raising overlay is disabled and
        # logged, and must never be able to freeze the panel.
        r, g, b = (0, 200, 0) if state["online"] else (200, 0, 0)
        canvas.SetPixel(0, 0, r, g, b)  # a status dot in the top-left corner

    api.overlay(paint)

    async def start(ctx):
        # Runs once, after the frame + HTTP session exist. `ctx.session` is the
        # shared aiohttp ClientSession; `ctx.config` is the parsed app config.
        async def poll():
            while True:
                try:
                    async with ctx.session.get("https://example.com/health") as resp:
                        state["online"] = resp.status == 200
                except Exception:
                    state["online"] = False
                await asyncio.sleep(30)

        # Launch the long-lived poller as a tracked background task.
        spawn_tracked(poll())

    api.on_startup(start)
```

## If it doesn't work

- **The dot never appears** — the plugin isn't installed/loaded (see [Installing a plugin](/plugins/#installing-a-plugin)); overlays need an installed plugin.
- **The dot never changes** — the poller hit an error or the URL is unreachable (it's caught and falls back to "offline"); check the logs and your endpoint.
- **The panel stutters or froze** — you did slow or raising work in `paint`. Move it to the poller; `paint` must be fast and must not raise.

<RelatedPages
  slugs={["concepts/busy-light", "plugins/api-reference", "plugins/extending/custom-color-provider"]}
/>
````

- [ ] **Step 2: Add the sidebar entry**

In `docs/site/astro.config.mjs`, add "Service plugins" to the "Extending led-ticker" group's `items`, after "Custom color provider":

```js
{ label: "Service plugins", link: "/plugins/extending/service-plugins/" },
```

so the Extending group has four items: Custom emoji, Writing a transition, Custom color provider, Service plugins. Keep valid JS (match the current formatting).

- [ ] **Step 3: Add the hub pointer in `04-beyond-widgets.mdx`**

In `plugins/authoring/04-beyond-widgets.mdx`, under the lifecycle-hooks section (heading "## Lifecycle hooks (the \"service plugin\" pattern)"), just after that section's code block, add:

```markdown
Building a background service? See the [Service plugins](/plugins/extending/service-plugins/) how-to — an `on_startup` poller plus a status overlay.
```

- [ ] **Step 4: Format, build, lint**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/docs-service
make docs-format
make docs-build; echo "BUILD=$?"
make docs-lint; echo "LINT=$?"
```
Expected: both exit 0; build reports one more page (60). `astro check` validates links — `/concepts/busy-light/`, `/plugins/authoring/01-scaffold/`, `/plugins/#installing-a-plugin`, `/plugins/api-reference`, `/plugins/extending/custom-color-provider` all resolve.

- [ ] **Step 5: Verify the listing matches the plugin file**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/docs-service
python3 - <<'PY'
import re, pathlib
page = pathlib.Path("docs/site/src/content/docs/plugins/extending/service-plugins.mdx").read_text()
plugin = pathlib.Path("examples/plugins/example_service/__init__.py").read_text().rstrip("\n")
blocks = re.findall(r"```python\n(.*?)```", page, re.DOTALL)
listing = next(b for b in blocks if b.lstrip().startswith('"""Example led-ticker plugin')).rstrip("\n")
print("MATCH" if listing == plugin else "MISMATCH")
if listing != plugin:
    import difflib
    print("\n".join(difflib.unified_diff(plugin.splitlines(), listing.splitlines(), "plugin", "listing", lineterm="")))
PY
```
Expected: `MATCH`. If `MISMATCH`, reconcile the page's Complete listing to the plugin file (plugin is source of truth).

- [ ] **Step 6: Commit**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/docs-service
git add docs/site/src/content/docs/plugins/extending/service-plugins.mdx docs/site/astro.config.mjs docs/site/src/content/docs/plugins/authoring/04-beyond-widgets.mdx
git -c core.hooksPath=/dev/null commit -m "docs: add the Service plugins how-to (Extending piece 4)

A worked service plugin (status overlay + on_startup poller via spawn_tracked),
plus a compact animation/border/easing recap pointing at the acme example —
bound to the example_service plugin. Sidebar entry + beyond-widgets pointer."
```

---

### Task 3: Technical-writer + hobbyist-persona review

After the page builds clean, run two reviews and apply fixes:

- [ ] **Step 1: Tech-writer reviewer** — reads `plugins/extending/service-plugins.mdx`, runs the `docs/DOCS-STYLE.md` §3 checklist (how-to page; #12/#15 lightly-applied; note this page intentionally has no demo GIF — there's no apt asset for a live overlay, and the spec records this as an honest exception to #7 — don't flag it as missing), returns prioritized must-fix vs nice-to-have.
- [ ] **Step 2: Hobbyist-persona ("Sam") check** — goal "build a background status light." Reports whether the overlay/poller split and the "paint must not freeze the panel" rule are clear, and whether he could build/install/run it — pass/fail.
- [ ] **Step 3:** Apply must-fix from both; re-run `make docs-format && make docs-build && make docs-lint`, the tripwire, and `ruff check src/ tests/` (all exit 0); re-run the Step-5 MATCH check if the listing changed; commit fixes (or record "no must-fix items").

---

## Self-Review

**1. Spec coverage:**
- New page: lifecycle hooks (overlay/on_startup/StartupContext/spawn_tracked/on_shutdown), worked status-dot service, other-surfaces recap (animation/border/easing → acme), register/use, complete listing, troubleshooting (panel-freeze + dot-not-updating), CTA → Task 2 Step 1. ✓
- Dedicated tested example plugin + behavioral tripwire (overlay + startup registered; paint draws default dot) → Task 1. ✓
- Sidebar entry + 04-beyond-widgets pointer → Task 2 Steps 2–3. ✓
- Tech-writer + hobbyist review loop (no-GIF noted as intentional) → Task 3. ✓
- Verification incl. `ruff check src/ tests/` → Task 1 Step 4 + Task 3 Step 3. ✓
- Out of scope (no standalone animation/border/easing pages; no runtime change; no byte-match test; no new GIF) → respected. ✓

**2. Placeholder scan:** The `...` in the border snippet ("# draw the ring with canvas.SetPixel") is an intentional illustrative ellipsis in a non-runnable recap snippet (the full version is in acme), not a plan placeholder. No TBD/TODO.

**3. Type/consistency:** Plugin file identical in Task 1 Step 3 and Task 2 "Complete listing" (Step 5 enforces MATCH). The test matches the plugin: `result.overlays`/`result.startup_hooks` are populated by the loader as `(namespace, callable)`; default `state["online"]` is `False` → `paint` writes `(200,0,0)` at `(0,0)`, asserted via `canvas.get_pixel(0,0)`. The loader collects hooks but does NOT run them, so `state` stays default in the test (no event loop needed). `spawn_tracked` is a public import; `StartupContext` reaches the hook as its `ctx` arg (no import needed in the plugin). Component import depth `../../../../components/` matches the verified depth-3 convention. "What you'll need" is a plain markdown list (not inside an Aside). Test lines ≤88 for CI ruff. The "Build the service" excerpt's `frame_at`-style body is identical to the complete listing's `register` body (minus the teaching comments), so the page is internally consistent.
