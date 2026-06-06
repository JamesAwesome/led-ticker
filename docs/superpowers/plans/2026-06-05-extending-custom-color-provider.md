# Extending led-ticker — Custom Color Provider How-To (piece 3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the "Custom color provider" how-to to the Extending section — a worked animated **pulse** provider — backed by a dedicated tested example plugin.

**Architecture:** A new tested example plugin (`examples/plugins/example_colorprovider/`) + a behavioral tripwire (registration + flags + animates-across-frames + config field); a new MDX how-to page whose "Complete listing" matches that plugin; a sidebar entry; a hub pointer from `04-beyond-widgets`. No runtime code changes.

**Tech Stack:** Astro Starlight, MDX, pytest. Docs: `make docs-build`/`make docs-lint`. Tests: `PYTHONPATH=tests/stubs uv run python -m pytest`. Lint: `uv run --extra dev ruff check src/ tests/` (CI scope — run it before committing Python).

**Source spec:** `docs/superpowers/specs/2026-06-05-extending-custom-color-provider-design.md`

**Worktree:** `.claude/worktrees/docs-colorprovider`, branch `feat/docs-colorprovider`. **Commit convention:** `git -c core.hooksPath=/dev/null commit`.

**Accurate API (verified):** provider = class with `per_char: bool`, `frame_invariant: bool`, `color_for(self, frame, char_index, total_chars) -> Color`. `ColorProviderBase` requires declaring `frame_invariant` (TypeError otherwise). `frame_invariant=False` ⇒ animates (re-render per tick); lying `True` freezes silently. Plugin registers via `@api.color_provider("pulse")`; used as `font_color = {style="ns.pulse", ...}`; `app/coercion._provider_from_style` does `cls(**kwargs)` (config fields pass through, raw values). `make_color` + `ColorProviderBase` are public. Registry: `led_ticker.color_providers._PROVIDER_REGISTRY`.

---

### Task 1: Dedicated color-provider example plugin + tripwire test

**Files:**
- Create: `examples/plugins/example_colorprovider/__init__.py`
- Create: `tests/test_plugins/test_example_colorprovider_plugin.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_plugins/test_example_colorprovider_plugin.py`:

```python
"""Tripwire for the Custom color provider how-to's example plugin.

Keeps examples/plugins/example_colorprovider (the page's code) honest against
the real ColorProvider surface.
"""

import shutil
from pathlib import Path

import pytest

from led_ticker import _plugin_loader as L
from led_ticker.color_providers import _PROVIDER_REGISTRY

EXAMPLE_DIR = (
    Path(__file__).resolve().parents[2]
    / "examples"
    / "plugins"
    / "example_colorprovider"
)


@pytest.fixture
def pulse_cls(tmp_path):
    L.reset_plugins()
    pdir = tmp_path / "plugins"
    pdir.mkdir()
    shutil.copytree(EXAMPLE_DIR, pdir / "example_colorprovider")
    try:
        result = L.load_plugins(pdir, entry_points_enabled=False)
        loaded = {i.namespace for i in result.loaded}
        assert "example_colorprovider" in loaded, result.failed
        yield _PROVIDER_REGISTRY["example_colorprovider.pulse"]
    finally:
        L.reset_plugins()


def test_pulse_registers_with_flags(pulse_cls):
    assert pulse_cls.__name__ == "Pulse"
    assert pulse_cls.per_char is False
    assert pulse_cls.frame_invariant is False


def test_pulse_animates_across_frames(pulse_cls):
    p = pulse_cls()
    c0 = p.color_for(0, 0, 1)
    c5 = p.color_for(5, 0, 1)
    assert (c0.red, c0.green, c0.blue) != (c5.red, c5.green, c5.blue)


def test_pulse_accepts_color_config(pulse_cls):
    g = pulse_cls(color=[0, 100, 0], speed=6).color_for(0, 0, 1).green
    assert 0 < g <= 100
```

- [ ] **Step 2: Run it — expect FAIL**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/docs-colorprovider
PYTHONPATH=tests/stubs uv run python -m pytest tests/test_plugins/test_example_colorprovider_plugin.py -q; echo "EXIT=$?"
```
Expected: FAIL (the `example_colorprovider` dir doesn't exist → fixture load assertion fails). If `uv run` isn't set up, run `uv sync --extra dev` first.

- [ ] **Step 3: Write the plugin**

Create `examples/plugins/example_colorprovider/__init__.py`:

```python
"""Example led-ticker plugin: a custom 'pulse' color provider (the 'Custom color provider' how-to).

Drop `example_colorprovider/` into your `config/plugins/` (local use), or package it
with an `[project.entry-points."led_ticker.plugins"]  example_colorprovider = "example_colorprovider:register"`
entry, then use it as `font_color = {style = "example_colorprovider.pulse"}`.

Imports only `led_ticker.plugin` (the public surface) plus stdlib.
"""

import math

from led_ticker.plugin import ColorProviderBase, make_color


def register(api):
    @api.color_provider("pulse")
    class Pulse(ColorProviderBase):
        # One color for the whole string (not per-character).
        per_char = False
        # `color_for` depends on `frame`, so the widget must re-render each tick.
        # Declaring this True would freeze the pulse — ColorProviderBase forces
        # you to set it explicitly.
        frame_invariant = False

        # Config fields come from TOML, e.g.
        #   font_color = {style = "example_colorprovider.pulse", color = [0, 200, 255], speed = 6}
        def __init__(self, color=(0, 200, 255), speed=6):
            self.color = color
            self.speed = speed

        def color_for(self, frame, char_index, total_chars):
            # Brightness breathes between ~0.30 and ~1.00 as the frame advances.
            level = 0.65 + 0.35 * math.sin(frame * self.speed * 0.05)
            r, g, b = self.color
            return make_color(int(r * level), int(g * level), int(b * level))
```

- [ ] **Step 4: Run the test — expect PASS; then ruff**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/docs-colorprovider
PYTHONPATH=tests/stubs uv run python -m pytest tests/test_plugins/test_example_colorprovider_plugin.py -q; echo "TEST=$?"
uv run --extra dev ruff check src/ tests/; echo "RUFF=$?"
```
Expected: 3 passed, `TEST=0`; `RUFF=0` (the test file lines are ≤88; `examples/` isn't in ruff's CI scope). If ruff flags the test file, wrap the offending line — do not let it exceed 88.

- [ ] **Step 5: Commit**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/docs-colorprovider
git add examples/plugins/example_colorprovider/__init__.py tests/test_plugins/test_example_colorprovider_plugin.py
git -c core.hooksPath=/dev/null commit -m "test: dedicated example_colorprovider plugin + tripwire for the Custom color provider how-to

A focused plugin (namespace example_colorprovider) registering an animated 'pulse'
provider, with a behavioral tripwire asserting registration, the per_char/
frame_invariant flags, that it animates across frames, and config pass-through."
```

---

### Task 2: The Custom color provider how-to page + sidebar + hub pointer

**Files:**
- Create: `docs/site/src/content/docs/plugins/extending/custom-color-provider.mdx`
- Modify: `docs/site/astro.config.mjs`
- Modify: `docs/site/src/content/docs/plugins/authoring/04-beyond-widgets.mdx`

- [ ] **Step 1: Write the page**

Create `docs/site/src/content/docs/plugins/extending/custom-color-provider.mdx` with EXACTLY this content. The "Complete listing" python block MUST be byte-identical to `examples/plugins/example_colorprovider/__init__.py` from Task 1.

````mdx
---
title: Custom color provider
description: Build a custom color provider for led-ticker from a plugin — the color_for contract, the per_char and frame_invariant flags, and a worked animated pulse effect.
---

import { Aside, Steps } from "@astrojs/starlight/components";
import DemoGif from "../../../../components/DemoGif.astro";
import RelatedPages from "../../../../components/RelatedPages.astro";

This is a how-to for **plugin authors**: write a custom **color provider** — the object that decides what color text is, frame by frame. You'll build a **pulse** that makes a message breathe brighter and dimmer.

**What you'll need:**

- A scaffolded plugin — see the [authoring guide](/plugins/authoring/01-scaffold/); you only import `led_ticker.plugin`.
- No hardware needed: you'll preview with `make render-demo` (run from the repo after `make dev`).
- Your plugin **installed** (`pip install -e .` from its directory) — `make render-demo` only picks up installed plugins.

<DemoGif
  src="/demos/concepts-color-providers.gif"
  caption="Color providers drive animated text color — rainbow, cycle, and your own."
/>

## The `color_for` contract

A color provider is a class with two flags and one method:

```python
class Pulse(ColorProviderBase):
    per_char = False
    frame_invariant = False

    def color_for(self, frame, char_index, total_chars): ...
```

- **`color_for(frame, char_index, total_chars)`** returns a `Color` for the current `frame`. `char_index` / `total_chars` describe the character being drawn (for per-character effects).
- **`per_char`** — `False` returns one color for the whole string; `True` is called per character, so you can color each letter differently (using `char_index`).
- **`frame_invariant`** — does your color depend on `frame`? `True` means no (a constant or gradient — led-ticker paints it once and sleeps); `False` means yes (it animates — led-ticker re-renders every tick).

<Aside type="danger">
  Get `frame_invariant` right. If `color_for` uses `frame` but you declare `frame_invariant = True`, led-ticker takes the paint-once fast path and your animation **silently freezes** — with no error. Subclassing `ColorProviderBase` forces you to declare the flag so you can't forget it.
</Aside>

## Build the pulse

The pulse keeps one color but scales its brightness up and down with a sine wave driven by `frame`:

```python
def color_for(self, frame, char_index, total_chars):
    level = 0.65 + 0.35 * math.sin(frame * self.speed * 0.05)
    r, g, b = self.color
    return make_color(int(r * level), int(g * level), int(b * level))
```

`make_color(r, g, b)` builds a `Color` (channels 0–255). Because the output depends on `frame`, **`frame_invariant = False`**. Add a base `color` and a `speed` as constructor arguments and they'll come from TOML.

<Aside type="tip">
  Want a different color per letter (like the built-in rainbow)? Set `per_char = True` and use `char_index` / `total_chars` in `color_for` — e.g. offset the hue by `char_index`. And set `restart_on_visit = False` to keep the animation's phase continuous across a section's `loop_count`.
</Aside>

## Register and use it

<Steps>

1. Register the class in your plugin's `register(api)`:

   ```python
   @api.color_provider("pulse")
   class Pulse(ColorProviderBase): ...
   ```

   It's namespaced — in the `example_colorprovider` plugin it becomes `example_colorprovider.pulse`.

2. Point a text widget's `font_color` at it in your `config/config.toml` (optionally with fields):

   ```toml
   [[playlist.section.widget]]
   type = "message"
   text = "breathing"
   font_color = { style = "example_colorprovider.pulse", color = [0, 200, 255], speed = 6 }
   ```

3. Install your plugin so led-ticker can find it. `make render-demo` loads only **installed** plugins (see [Package & install](/plugins/authoring/03-package/)), then preview — no hardware needed:

   ```bash
   pip install -e .   # run from your plugin's directory
   make render-demo CONFIG=config/config.toml OUT=preview.gif
   open preview.gif   # macOS; xdg-open on Linux
   ```

</Steps>

## Complete listing

The full plugin — `examples/plugins/example_colorprovider/__init__.py`:

```python
"""Example led-ticker plugin: a custom 'pulse' color provider (the 'Custom color provider' how-to).

Drop `example_colorprovider/` into your `config/plugins/` (local use), or package it
with an `[project.entry-points."led_ticker.plugins"]  example_colorprovider = "example_colorprovider:register"`
entry, then use it as `font_color = {style = "example_colorprovider.pulse"}`.

Imports only `led_ticker.plugin` (the public surface) plus stdlib.
"""

import math

from led_ticker.plugin import ColorProviderBase, make_color


def register(api):
    @api.color_provider("pulse")
    class Pulse(ColorProviderBase):
        # One color for the whole string (not per-character).
        per_char = False
        # `color_for` depends on `frame`, so the widget must re-render each tick.
        # Declaring this True would freeze the pulse — ColorProviderBase forces
        # you to set it explicitly.
        frame_invariant = False

        # Config fields come from TOML, e.g.
        #   font_color = {style = "example_colorprovider.pulse", color = [0, 200, 255], speed = 6}
        def __init__(self, color=(0, 200, 255), speed=6):
            self.color = color
            self.speed = speed

        def color_for(self, frame, char_index, total_chars):
            # Brightness breathes between ~0.30 and ~1.00 as the frame advances.
            level = 0.65 + 0.35 * math.sin(frame * self.speed * 0.05)
            r, g, b = self.color
            return make_color(int(r * level), int(g * level), int(b * level))
```

## If it doesn't work

- **The color is frozen / doesn't animate** — you declared `frame_invariant = True` but `color_for` uses `frame`. Set `frame_invariant = False`.
- **`TypeError: Pulse must define 'frame_invariant'`** — declare it as a class attribute (that's `ColorProviderBase` doing its job).
- **"unknown font_color style" / not found** — check the namespaced `style` (`example_colorprovider.pulse`, not `pulse`) and that the plugin is installed/loaded (see [Installing a plugin](/plugins/#installing-a-plugin)).

<RelatedPages
  slugs={["concepts/color-providers", "plugins/api-reference", "plugins/extending/writing-a-transition"]}
/>
````

- [ ] **Step 2: Add the sidebar entry**

In `docs/site/astro.config.mjs`, add "Custom color provider" to the "Extending led-ticker" group's `items`, after "Writing a transition". Read the current group (prettier may format it one-item-per-line or compact) and add:

```js
{ label: "Custom color provider", link: "/plugins/extending/custom-color-provider/" },
```

so the Extending group ends up with three items: Custom emoji, Writing a transition, Custom color provider. Keep valid JS.

- [ ] **Step 3: Add the hub pointer in `04-beyond-widgets.mdx`**

In `plugins/authoring/04-beyond-widgets.mdx`, under "## Render surfaces (decorate a class)" (where `api.color_provider` is listed), just after that section's code block (alongside the existing transition pointer), add:

```markdown
Writing a color provider? See the [Custom color provider](/plugins/extending/custom-color-provider/) how-to — the `color_for` contract and a worked animated pulse.
```

- [ ] **Step 4: Format, build, lint**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/docs-colorprovider
make docs-format
make docs-build; echo "BUILD=$?"
make docs-lint; echo "LINT=$?"
```
Expected: both exit 0; build reports one more page (59). `astro check` validates links — `/plugins/authoring/01-scaffold/`, `/plugins/authoring/03-package/`, `/plugins/#installing-a-plugin`, `/concepts/color-providers`, `/plugins/api-reference`, `/plugins/extending/writing-a-transition` all resolve.

- [ ] **Step 5: Verify the listing matches the plugin file**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/docs-colorprovider
python3 - <<'PY'
import re, pathlib
page = pathlib.Path("docs/site/src/content/docs/plugins/extending/custom-color-provider.mdx").read_text()
plugin = pathlib.Path("examples/plugins/example_colorprovider/__init__.py").read_text().rstrip("\n")
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
cd /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/docs-colorprovider
git add docs/site/src/content/docs/plugins/extending/custom-color-provider.mdx docs/site/astro.config.mjs docs/site/src/content/docs/plugins/authoring/04-beyond-widgets.mdx
git -c core.hooksPath=/dev/null commit -m "docs: add the Custom color provider how-to (Extending piece 3)

A worked animated 'pulse': the color_for contract, the per_char + frame_invariant
flags (with the silent-freeze warning), and the full effect — bound to the
example_colorprovider plugin. Sidebar entry + beyond-widgets pointer."
```

---

### Task 3: Technical-writer + hobbyist-persona review

After the page builds clean, run two reviews and apply fixes:

- [ ] **Step 1: Tech-writer reviewer** — reads `plugins/extending/custom-color-provider.mdx`, runs the `docs/DOCS-STYLE.md` §3 checklist (how-to page; #12/#15 lightly-applied per the "more technical" steer), returns prioritized must-fix vs nice-to-have.
- [ ] **Step 2: Hobbyist-persona ("Sam") check** — goal "make my message's color animate." Reports whether the page makes the `frame_invariant` flag understandable (so he won't ship a frozen pulse) and whether he could build/register/use it end-to-end — pass/fail.
- [ ] **Step 3:** Apply must-fix from both; re-run `make docs-format && make docs-build && make docs-lint`, the tripwire, and `ruff check src/ tests/` (all exit 0); re-run the Step-5 MATCH check if the listing changed; commit fixes (or record "no must-fix items").

---

## Self-Review

**1. Spec coverage:**
- New page: color_for contract, per_char/frame_invariant (freeze warning headlined), worked pulse, per-char variation note, register/use, complete listing, troubleshooting (freeze case first), CTA → Task 2 Step 1. ✓
- Dedicated tested example plugin + behavioral tripwire (registration + flags + animates-across-frames + config field) → Task 1. ✓
- Sidebar entry + 04-beyond-widgets pointer → Task 2 Steps 2–3. ✓
- Tech-writer + hobbyist review loop → Task 3. ✓
- Verification incl. `ruff check src/ tests/` (CI lesson) → Task 1 Step 4 + Task 3 Step 3. ✓
- Out of scope (service/smaller pages; no runtime code change; no byte-match test; no full provider catalog) → respected. ✓

**2. Placeholder scan:** No TBD/TODO.

**3. Type/consistency:** Plugin file identical in Task 1 Step 3 and Task 2 "Complete listing" (Step 5 enforces MATCH). The test's expectations match the plugin: `per_char=False`/`frame_invariant=False` asserted; `color_for(0,…)` (level 0.65) vs `color_for(5,…)` (level ≈ 1.0) differ → animates; `color=[0,100,0]` → green `int(100*0.65)=65`, in `(0,100]`. `Pulse(ColorProviderBase)` declares `frame_invariant` so no `__init_subclass__` TypeError. `make_color`/`ColorProviderBase` are public imports. Component import depth `../../../../components/` matches the verified depth-3 convention. "What you'll need" is a plain markdown list (not inside an Aside) to avoid the prettier list-merge issue seen on the transition page. Test lines kept ≤88 for CI ruff.
