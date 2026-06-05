# Plugin Authoring Guide Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a 4-page "Authoring a plugin" docs-site sub-section built around a new, minimal, tested `example.counter` widget plugin, so a developer can go from nothing to an installed widget plugin and then survey the other extension points.

**Architecture:** Build the worked-example plugin first (`examples/plugins/example/`) with a drift-tripwire test, then write four `plugins/authoring/*.mdx` pages whose code blocks are excerpts of that real, tested file. Wire the pages into the sidebar and repoint the Plugins-overview teaser. Docs + one tiny example plugin; no production `src/` changes.

**Tech Stack:** Python (`attrs`, the `led_ticker.plugin` public surface), pytest, Astro Starlight (`docs/site/`, pnpm), Makefile docs targets.

**Spec:** `docs/superpowers/specs/2026-06-04-plugin-authoring-guide-design.md`

**Decisions baked in:** No rendered GIF for the widget (describe + TOML example — keeps it off the `make render-demo` path, per the spec's open question). `plugin-system.md` stays as-is; the guide links to it.

**Worktree/branch:** `.claude/worktrees/plugin-authoring` on `feat/plugin-authoring-guide`. Verify branch first (`git -C <wt> branch --show-current` → `feat/plugin-authoring-guide`). Commit with `git -C <wt> -c core.hooksPath=/dev/null commit`. `<wt>` = `/Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/plugin-authoring`. Use ABSOLUTE paths.

---

## File Structure

- **Create** `examples/plugins/example/__init__.py` — the minimal `example.counter` widget (the worked example).
- **Create** `tests/test_plugins/test_example_plugin.py` — drift tripwire (loads, registers, validate_config, draws).
- **Create** `docs/site/src/content/docs/plugins/authoring/01-scaffold.mdx`
- **Create** `docs/site/src/content/docs/plugins/authoring/02-widget.mdx`
- **Create** `docs/site/src/content/docs/plugins/authoring/03-package.mdx`
- **Create** `docs/site/src/content/docs/plugins/authoring/04-beyond-widgets.mdx`
- **Modify** `docs/site/astro.config.mjs` — add the four authoring pages to the Plugins sidebar group.
- **Modify** `docs/site/src/content/docs/plugins/index.mdx` — repoint the "Writing a plugin" teaser at the new guide.

---

### Task 1: The `example.counter` widget + drift-tripwire test

**Files:**
- Create: `examples/plugins/example/__init__.py`
- Create: `tests/test_plugins/test_example_plugin.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_plugins/test_example_plugin.py`:

```python
"""Tripwire for the authoring-guide worked example (examples/plugins/example).

The plugin authoring guide's code blocks are excerpts of this plugin; this test
keeps the shipped example (and therefore the docs) honest against the API.
"""

import shutil
from pathlib import Path

import pytest

from led_ticker import _plugin_loader as L
from led_ticker.widgets import _WIDGET_REGISTRY, get_widget_class

EXAMPLE_DIR = Path(__file__).resolve().parents[2] / "examples" / "plugins" / "example"


@pytest.fixture
def counter_cls(tmp_path):
    """Load examples/plugins/example into an isolated plugins dir; yield the widget class."""
    L.reset_plugins()
    pdir = tmp_path / "plugins"
    pdir.mkdir()
    shutil.copytree(EXAMPLE_DIR, pdir / "example")
    try:
        result = L.load_plugins(pdir, entry_points_enabled=False)
        assert "example" in {i.namespace for i in result.loaded}, result.failed
        yield get_widget_class("example.counter")
    finally:
        L.reset_plugins()


def test_example_counter_registers(counter_cls):
    assert "example.counter" in _WIDGET_REGISTRY
    assert counter_cls.__name__ == "Counter"


def test_validate_config_accepts_a_past_date(counter_cls):
    assert counter_cls.validate_config({"since": "2020-01-01"}) == []


def test_validate_config_rejects_bad_and_future_dates(counter_cls):
    assert counter_cls.validate_config({"since": "not-a-date"})  # non-empty error list
    assert counter_cls.validate_config({"since": "2999-01-01"})  # future → error
    assert counter_cls.validate_config({})  # missing → error


def test_draw_returns_canvas_and_end_x(counter_cls, canvas):
    w = counter_cls(since="2020-01-01", label="DAY")
    out, end_x = w.draw(canvas)
    assert out is canvas
    assert isinstance(end_x, int)
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd <wt> && uv run pytest tests/test_plugins/test_example_plugin.py -q`
Expected: FAIL — `examples/plugins/example` doesn't exist (copytree / load yields no `example` namespace).

- [ ] **Step 3: Create the example plugin**

Create `examples/plugins/example/__init__.py`:

```python
"""Minimal example led-ticker plugin — the worked example for the authoring guide.

Drop `example/` into your `config/plugins/` (local use), or package it with an
`[project.entry-points."led_ticker.plugins"]  example = "example:register"`
entry (packaged use), then reference it in TOML as `type = "example.counter"`.

Imports only `led_ticker.plugin` (the public surface) plus `attrs` and stdlib —
never a private `led_ticker.*` module.
"""

import datetime as _dt

import attrs

from led_ticker.plugin import Color, draw_text, make_color, resolve_font


def register(api):
    @api.widget("counter")
    @attrs.define
    class Counter:
        """Shows whole days since a configured date, e.g. ``DAY 42``."""

        # Config fields. The loader builds the widget from your TOML, passing
        # declared keys as constructor kwargs; `@attrs.define` lets it inspect them.
        since: str = "2020-01-01"
        label: str = "DAY"
        # `color` is a known color key: the loader coerces an [r, g, b] list in
        # TOML into a Color before your widget sees it (None = default white).
        color: Color | None = None

        @classmethod
        def validate_config(cls, cfg):
            """Pre-coercion config check; return a list of human-readable errors."""
            errors = []
            since = cfg.get("since")
            if since is None:
                errors.append("since is required (a YYYY-MM-DD date)")
            else:
                try:
                    start = _dt.date.fromisoformat(str(since))
                except ValueError:
                    errors.append(f"since must be a YYYY-MM-DD date; got {since!r}")
                else:
                    if start > _dt.date.today():
                        errors.append(f"since must not be in the future; got {since!r}")
            return errors

        def _days(self):
            return (_dt.date.today() - _dt.date.fromisoformat(self.since)).days

        def draw(self, canvas, cursor_pos=0, *, y_offset=0, font_color=None):
            """Render `<label> <N>` onto the canvas; return (canvas, end_x)."""
            font = resolve_font("6x12")
            color = self.color if self.color is not None else make_color(255, 255, 255)
            text = f"{self.label} {self._days()}"
            end_x = draw_text(canvas, font, text, cursor_pos, 10 + y_offset, color)
            return canvas, end_x
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd <wt> && uv run pytest tests/test_plugins/test_example_plugin.py -q`
Expected: PASS (4 tests). Then `cd <wt> && uv run ruff check examples/plugins/example tests/test_plugins/test_example_plugin.py` → clean (no `from __future__ import annotations`; `Color` annotation is unquoted + imported).

- [ ] **Step 5: Commit**

```bash
git -C <wt> add examples/plugins/example/__init__.py tests/test_plugins/test_example_plugin.py
git -C <wt> -c core.hooksPath=/dev/null commit -m "feat(examples): add minimal example.counter plugin + tripwire test for the authoring guide"
```

---

### Task 2: Page 1 — Scaffold & register

**Files:**
- Create: `docs/site/src/content/docs/plugins/authoring/01-scaffold.mdx`

- [ ] **Step 1: Create the page** with EXACTLY:

````mdx
---
title: "Authoring 1: Scaffold & register"
description: Create a led-ticker plugin that loads — the register(api) entry point, the two discovery channels, and how to verify it.
prev: false
next: false
---

import TutorialNav from "../../../../components/TutorialNav.astro";
import { Steps, Aside, Tabs, TabItem } from "@astrojs/starlight/components";

A **plugin** is a small Python package that adds widgets (and more) to led-ticker without changing core. Over these four pages you'll build one — `example.counter`, a widget that shows the number of days since a date — then survey everything else you can contribute.

A plugin is just a module that exposes a `register(api)` function. led-ticker calls it once at startup and hands you an `api` object; you call methods on it to register your contributions.

## The smallest plugin that loads

<Steps>

1. Create a file for your plugin. A plugin can be a single `.py` file or a package directory:

   ```
   example/
     __init__.py
   ```

2. Add a `register(api)` that does nothing yet:

   ```python
   # example/__init__.py
   def register(api):
       pass
   ```

3. Make led-ticker discover it — two ways:

   <Tabs>
   <TabItem label="Local (drop-in)">
   Put the file under your config's plugins directory (default `config/plugins/`):

   ```
   config/plugins/example/__init__.py
   ```

   The plugin's **namespace** is its file/dir name — here, `example`.
   </TabItem>
   <TabItem label="Packaged (entry point)">
   Ship it as an installable package declaring a `led_ticker.plugins` entry point (covered in [Package & install](/plugins/authoring/03-package/)):

   ```toml
   [project.entry-points."led_ticker.plugins"]
   example = "example:register"
   ```

   The entry-point **name** (`example`) is the namespace.
   </TabItem>
   </Tabs>

4. Verify it loads:

   ```bash
   led-ticker plugins
   ```

   Your `example` namespace should appear in the list (with no contributions yet).

</Steps>

## Namespaces

Everything a plugin registers is namespaced by `<plugin>.<name>`, so plugins never collide with core or each other. The widget you build next, registered as `counter`, becomes `example.counter` in config — `type = "example.counter"`.

<Aside type="note" title="API version">
The plugin API is versioned (`API_VERSION`, currently `1.0`). A plugin can declare the major version it needs with a module-level `requires_api = 1`; led-ticker skips (and logs) a plugin that needs a newer API than it provides.
</Aside>

<Aside type="caution" title="Import only the public surface">
Import only from `led_ticker.plugin` (plus `attrs` and the standard library). Anything else under `led_ticker.*` is private and may change without notice. Also: no `from __future__ import annotations` in plugin source — led-ticker runs on Python 3.14 (PEP 649) and the linter rejects it.
</Aside>

<TutorialNav
  next={{ href: "/plugins/authoring/02-widget/", title: "Authoring 2: Build the widget" }}
/>
````

- [ ] **Step 2: Commit** (build/lint deferred to Task 7's `make docs-build`)

```bash
git -C <wt> add docs/site/src/content/docs/plugins/authoring/01-scaffold.mdx
git -C <wt> -c core.hooksPath=/dev/null commit -m "docs(site): authoring guide page 1 — scaffold & register"
```

---

### Task 3: Page 2 — Build the widget

**Files:**
- Create: `docs/site/src/content/docs/plugins/authoring/02-widget.mdx`

**Context:** The code blocks below are excerpts of the shipped `examples/plugins/example/__init__.py` (Task 1). Keep them byte-identical to that file so the tripwire test guards them.

- [ ] **Step 1: Create the page** with EXACTLY:

````mdx
---
title: "Authoring 2: Build the widget"
description: Register a widget, declare its config fields, implement draw(), and validate config — the full Counter widget.
prev: false
next: false
---

import TutorialNav from "../../../../components/TutorialNav.astro";
import { Steps, Aside } from "@astrojs/starlight/components";

Now make `example.counter` real. A widget is a class registered with `api.widget`, carrying its config as fields and rendering with a `draw()` method.

## Register a widget class

`api.widget(name)` is a decorator. Pair it with `@attrs.define` so led-ticker can inspect your config fields:

```python
import attrs
from led_ticker.plugin import Color, draw_text, make_color, resolve_font


def register(api):
    @api.widget("counter")
    @attrs.define
    class Counter:
        since: str = "2020-01-01"
        label: str = "DAY"
        color: Color | None = None
```

Each field is a config key. In TOML:

```toml
[[playlist.section.widget]]
type = "example.counter"
since = "2024-01-01"
label = "DAY"
color = [130, 220, 255]
```

<Aside type="tip" title="Color fields are coerced for you">
`color` is a known color key, so led-ticker converts an `[r, g, b]` list into a `Color` object before constructing your widget — `self.color` is already a `Color` (or `None`). The same applies to `bg_color`, `font_color`, and friends.
</Aside>

## Implement `draw()`

`draw()` paints one frame and returns `(canvas, end_x)` — the canvas and the x-coordinate where your content ends (so the engine can chain widgets):

```python
        def draw(self, canvas, cursor_pos=0, *, y_offset=0, font_color=None):
            font = resolve_font("6x12")
            color = self.color if self.color is not None else make_color(255, 255, 255)
            text = f"{self.label} {self._days()}"
            end_x = draw_text(canvas, font, text, cursor_pos, 10 + y_offset, color)
            return canvas, end_x
```

The helpers all come from `led_ticker.plugin`:

- `resolve_font("6x12")` — a bundled BDF font (or a hi-res name + size).
- `make_color(r, g, b)` — a `Color` without importing the matrix library.
- `draw_text(canvas, font, text, x, y, color)` — draws text (with inline emoji support) and returns the end-x.

<Aside type="note" title="cursor_pos and font_color">
`cursor_pos` is the horizontal scroll offset the engine passes in — draw relative to it. `font_color` is an optional per-frame color the engine may inject (e.g. a color provider); honor it when your widget should follow a theme. This widget uses its own `color` field instead.
</Aside>

The `_days()` helper is plain Python:

```python
import datetime as _dt
# ...
        def _days(self):
            return (_dt.date.today() - _dt.date.fromisoformat(self.since)).days
```

## Validate config

Add a `validate_config` classmethod to reject bad config *before* the sign runs (it shows up in `led-ticker validate`). It receives the raw, pre-coercion config and returns a list of error strings:

```python
        @classmethod
        def validate_config(cls, cfg):
            errors = []
            since = cfg.get("since")
            if since is None:
                errors.append("since is required (a YYYY-MM-DD date)")
            else:
                try:
                    start = _dt.date.fromisoformat(str(since))
                except ValueError:
                    errors.append(f"since must be a YYYY-MM-DD date; got {since!r}")
                else:
                    if start > _dt.date.today():
                        errors.append(f"since must not be in the future; got {since!r}")
            return errors
```

The complete widget is [`examples/plugins/example/`](https://github.com/JamesAwesome/led-ticker/tree/main/examples/plugins/example) in the repo.

<TutorialNav
  prev={{ href: "/plugins/authoring/01-scaffold/", title: "Authoring 1: Scaffold & register" }}
  next={{ href: "/plugins/authoring/03-package/", title: "Authoring 3: Package & install" }}
/>
````

- [ ] **Step 2: Verify snippets match the shipped file.** Confirm the `draw`, `validate_config`, and field declarations in this page are character-identical to `examples/plugins/example/__init__.py`:

```bash
cd <wt> && grep -q 'end_x = draw_text(canvas, font, text, cursor_pos, 10 + y_offset, color)' docs/site/src/content/docs/plugins/authoring/02-widget.mdx examples/plugins/example/__init__.py && echo "draw snippet matches"
```
Expected: `draw snippet matches`.

- [ ] **Step 3: Commit**

```bash
git -C <wt> add docs/site/src/content/docs/plugins/authoring/02-widget.mdx
git -C <wt> -c core.hooksPath=/dev/null commit -m "docs(site): authoring guide page 2 — build the widget"
```

---

### Task 4: Page 3 — Package, install & test

**Files:**
- Create: `docs/site/src/content/docs/plugins/authoring/03-package.mdx`

- [ ] **Step 1: Create the page** with EXACTLY:

````mdx
---
title: "Authoring 3: Package & install"
description: Turn a local plugin into an installable package, add it to a sign, and test it on your laptop.
prev: false
next: false
---

import TutorialNav from "../../../../components/TutorialNav.astro";
import { Steps, Aside } from "@astrojs/starlight/components";

A local `config/plugins/` file is great while you iterate. To share a plugin or deploy it to a sign, package it.

## Declare an entry point

Add a `pyproject.toml` next to your package and expose `register` under the `led_ticker.plugins` group:

```toml
[project]
name = "led-ticker-example"
version = "0.1.0"
dependencies = ["led-ticker"]

[project.entry-points."led_ticker.plugins"]
example = "example:register"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

Once the package is installed, led-ticker discovers it automatically — no config change needed.

## Install it on a sign

Add the package to your led-ticker checkout's `config/requirements-plugins.txt` and rebuild. The install flow (the constraint-based build, the gitignored live file) is covered on the [Plugins overview](/plugins/) — in short:

```bash
cp config/requirements-plugins.example.txt config/requirements-plugins.txt
# add a line for your package (a PyPI name, or a git URL), then:
docker compose up -d --build
```

<Aside type="note" title="led-ticker isn't on PyPI (yet)">
Plugins are installed `--no-deps`-free but **constrained to core's versions** — a plugin can bring its own deps but can't move led-ticker's. Because led-ticker is already in the image, your `dependencies = ["led-ticker"]` resolves without a PyPI fetch. See the [Plugins overview](/plugins/) for the details.
</Aside>

## Test it on your laptop

You don't need hardware. led-ticker ships a headless graphics stub, and its `tests/stubs/` has a full matrix stub you can put on the path. A minimal test that loads your plugin and draws once:

```python
import shutil
from pathlib import Path
from led_ticker import _plugin_loader as L
from led_ticker.widgets import get_widget_class

def test_counter_draws(tmp_path, canvas):  # `canvas` fixture = a stub canvas
    L.reset_plugins()
    pdir = tmp_path / "plugins"; pdir.mkdir()
    shutil.copytree(Path("examples/plugins/example"), pdir / "example")
    L.load_plugins(pdir, entry_points_enabled=False)
    widget = get_widget_class("example.counter")(since="2020-01-01")
    out, end_x = widget.draw(canvas)
    assert out is canvas
    L.reset_plugins()
```

This is exactly how the bundled example is tested (`tests/test_plugins/test_example_plugin.py`).

## A real packaged plugin

[`led-ticker-pool`](https://github.com/JamesAwesome/led-ticker-pool) is a complete, published example: a data-fetching widget with its own repo, `pyproject.toml`, CI, and tests. Read it when you're ready to ship something real.

<TutorialNav
  prev={{ href: "/plugins/authoring/02-widget/", title: "Authoring 2: Build the widget" }}
  next={{ href: "/plugins/authoring/04-beyond-widgets/", title: "Authoring 4: Beyond widgets" }}
/>
````

- [ ] **Step 2: Commit**

```bash
git -C <wt> add docs/site/src/content/docs/plugins/authoring/03-package.mdx
git -C <wt> -c core.hooksPath=/dev/null commit -m "docs(site): authoring guide page 3 — package & install"
```

---

### Task 5: Page 4 — Beyond widgets

**Files:**
- Create: `docs/site/src/content/docs/plugins/authoring/04-beyond-widgets.mdx`

- [ ] **Step 1: Create the page** with EXACTLY:

````mdx
---
title: "Authoring 4: Beyond widgets"
description: A map of the other plugin surfaces — transitions, color providers, animations, borders, easings, emoji, fonts, and lifecycle hooks.
prev: false
next: false
---

import TutorialNav from "../../../../components/TutorialNav.astro";
import { Aside } from "@astrojs/starlight/components";

Widgets are the most common contribution, but `api` registers a lot more. Each call below namespaces under your plugin (`example.<name>`). The reference plugin [`examples/plugins/acme/`](https://github.com/JamesAwesome/led-ticker/blob/main/examples/plugins/acme/__init__.py) exercises every one of these in ~100 lines; the full contracts are in [`plugin-system.md`](https://github.com/JamesAwesome/led-ticker/blob/main/docs/plugin-system.md).

## Render surfaces (decorate a class)

```python
@api.transition("swoosh")          # a Transition: frame_at(t, canvas, outgoing, incoming)
@api.color_provider("fire")        # a ColorProvider: color_for(frame, char_index, total)
@api.animation("scramble")         # an Animation: frame_for(frame, text, width, text_width)
@api.border("neon")                # a BorderEffect: paint(canvas, frame_count)
```

Subclass the matching base (`ColorProviderBase`, `BorderEffectBase`) or implement the protocol; reference them in TOML as `transition = {type = "example.swoosh"}`, `font_color = {style = "example.fire"}`, etc.

## Value surfaces (pass data directly)

```python
api.easing("snap", lambda p: p * p)                 # an easing curve (0..1 -> 0..1)
api.emoji("spark", [(x, y, r, g, b), ...])          # an 8x8 inline emoji, used as :example.spark:
api.hires_emoji("spark", HiResEmoji(...))           # hi-res variant (pair it with a low-res one)
api.font("Brand", "fonts/Brand.ttf")                # a bundled font file, usable as font = "example.Brand"
```

## Lifecycle hooks (the "service plugin" pattern)

Hooks let a plugin run code around the display loop — for example, poll an API in the background and paint a status dot over every frame:

```python
api.overlay(paint)            # paint(canvas) runs every frame (exception-guarded)
api.on_startup(on_startup)    # on_startup(ctx: StartupContext) runs once before the loop (sync or async)
api.on_shutdown(cleanup)      # runs once at exit
```

Start background work with `spawn_tracked(coro)` from inside `on_startup`, and have your overlay paint whatever shared state it updates.

<Aside type="tip" title="Copy the example">
The fastest way to add any of these is to copy the relevant block out of [`acme/__init__.py`](https://github.com/JamesAwesome/led-ticker/blob/main/examples/plugins/acme/__init__.py) and renamespace it. For the precise contracts, return types, and edge cases, see [`plugin-system.md`](https://github.com/JamesAwesome/led-ticker/blob/main/docs/plugin-system.md).
</Aside>

That's the whole surface. Build something and [add it to the directory](/plugins/available/).

<TutorialNav
  prev={{ href: "/plugins/authoring/03-package/", title: "Authoring 3: Package & install" }}
/>
````

- [ ] **Step 2: Commit**

```bash
git -C <wt> add docs/site/src/content/docs/plugins/authoring/04-beyond-widgets.mdx
git -C <wt> -c core.hooksPath=/dev/null commit -m "docs(site): authoring guide page 4 — beyond widgets"
```

---

### Task 6: Sidebar nav + repoint the overview teaser

**Files:**
- Modify: `docs/site/astro.config.mjs`
- Modify: `docs/site/src/content/docs/plugins/index.mdx`

- [ ] **Step 1: Add the authoring pages to the Plugins nav group.** In `docs/site/astro.config.mjs`, replace this exact block:

```javascript
          label: "Plugins",
          items: [
            { label: "Plugins overview", link: "/plugins/" },
            { label: "Available plugins", link: "/plugins/available/" },
          ],
        },
```
with:

```javascript
          label: "Plugins",
          items: [
            { label: "Plugins overview", link: "/plugins/" },
            { label: "Available plugins", link: "/plugins/available/" },
            { label: "Authoring: 1. Scaffold", link: "/plugins/authoring/01-scaffold/" },
            { label: "Authoring: 2. Build the widget", link: "/plugins/authoring/02-widget/" },
            { label: "Authoring: 3. Package & install", link: "/plugins/authoring/03-package/" },
            { label: "Authoring: 4. Beyond widgets", link: "/plugins/authoring/04-beyond-widgets/" },
          ],
        },
```

- [ ] **Step 2: Repoint the overview teaser.** In `docs/site/src/content/docs/plugins/index.mdx`, replace this exact block:

```markdown
The best starting point today is a complete worked example: the [`led-ticker-pool`](https://github.com/JamesAwesome/led-ticker-pool) repo shows the `register(api)` function, the `pyproject.toml` entry point, tests, and packaging end-to-end. (A step-by-step authoring guide is a future addition.)
```
with:

```markdown
New to it? The [**authoring guide**](/plugins/authoring/01-scaffold/) walks you from an empty `register(api)` to an installed widget plugin, step by step. For a complete real-world example, the [`led-ticker-pool`](https://github.com/JamesAwesome/led-ticker-pool) repo shows the entry point, tests, and packaging end-to-end.
```

- [ ] **Step 3: Verify the nav parses**

```bash
cd <wt>/docs/site && node --check astro.config.mjs && echo "nav ok"
```
Expected: `nav ok`.

- [ ] **Step 4: Commit**

```bash
git -C <wt> add docs/site/astro.config.mjs docs/site/src/content/docs/plugins/index.mdx
git -C <wt> -c core.hooksPath=/dev/null commit -m "docs(site): wire authoring guide into nav + repoint overview teaser"
```

---

### Task 7: Build, lint, test, PR

**Files:** none (verification + PR)

- [ ] **Step 1: Build the docs site** (catches broken MDX, frontmatter, component imports, internal links)

```bash
cd <wt> && make docs-build 2>&1 | tail -15
```
Expected: build succeeds; the four `/plugins/authoring/*` pages are produced. If a `<TutorialNav>`/Starlight import path is wrong (the authoring pages are one directory deeper than the tutorial pages — note the `../../../../components/` depth), fix the relative import and rebuild.

- [ ] **Step 2: Docs lint**

```bash
cd <wt> && make docs-lint 2>&1 | tail -8
```
Expected: clean. If prettier reformats, run `make docs-format`, re-run `make docs-lint`, and commit ("docs(site): prettier format").

- [ ] **Step 3: Full Python suite** (the example plugin + its test)

```bash
cd <wt> && make test 2>&1 | tail -6 && make lint 2>&1 | tail -2
```
Expected: green (includes `tests/test_plugins/test_example_plugin.py`), ruff clean.

- [ ] **Step 4: Push + open the PR**

```bash
git -C <wt> -c core.hooksPath=/dev/null push -u origin feat/plugin-authoring-guide
gh pr create --repo JamesAwesome/led-ticker --base main --head feat/plugin-authoring-guide \
  --title "docs: plugin authoring guide (+ example.counter worked example)" \
  --body "Adds the deferred plugin authoring guide: a 4-page plugins/authoring/ sub-section (scaffold & register → build the widget → package & install → beyond widgets), built around a new minimal example.counter widget shipped + tested at examples/plugins/example/ so the tutorial snippets can't drift. Wires the pages into the Plugins nav and repoints the overview teaser. plugin-system.md stays the engineering reference (linked, not duplicated).

Test plan: make docs-build + docs-lint clean; make test green incl. tests/test_plugins/test_example_plugin.py (loads, registers, validate_config, draws)."
```

- [ ] **Step 5: Watch CI**

```bash
cd <wt> && gh pr checks $(gh pr view feat/plugin-authoring-guide --json number --jq .number) --watch --interval 15 2>&1 | grep -vE "skipping" | tail -10
```
Expected: green (docs-lint, test, build-and-deploy). Do NOT merge — the controller confirms merges with the user.

---

## Notes for the implementer

- **Build Task 1 first** — the doc snippets (pages 2–3) must match the shipped `examples/plugins/example/__init__.py` byte-for-byte; the tripwire test guards behavior.
- The authoring `.mdx` pages live one directory deeper than `tutorial/` pages, so component imports are `../../../../components/...` (four `../`), not three. The build (Task 7) will catch a wrong depth.
- No rendered GIF for the widget (spec decision) — describe + TOML only.
- Do NOT modify `plugin-system.md`, the plugin API, or `examples/plugins/acme/` — the guide references them as-is.
- `prev: false` / `next: false` in frontmatter disables Starlight's auto prev/next so the explicit `<TutorialNav>` is the only pager (matches the tutorial pages).
