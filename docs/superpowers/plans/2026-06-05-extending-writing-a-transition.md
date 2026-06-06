# Extending led-ticker — Writing a Transition How-To (piece 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the "Writing a transition" how-to to the Extending section — a worked **wipe** transition — backed by a dedicated tested example plugin.

**Architecture:** A new tested example plugin (`examples/plugins/example_transition/`) + a behavioral tripwire (registration + `frame_at` behavior); a new MDX how-to page whose "Complete listing" matches that plugin; a sidebar entry; a hub pointer from `04-beyond-widgets`. No runtime code changes.

**Tech Stack:** Astro Starlight, MDX, pytest. Docs: `make docs-build`/`make docs-lint`. Tests: `PYTHONPATH=tests/stubs uv run python -m pytest`.

**Source spec:** `docs/superpowers/specs/2026-06-05-extending-writing-a-transition-design.md`

**Worktree:** `.claude/worktrees/docs-transition`, branch `feat/docs-transition`. **Commit convention:** `git -c core.hooksPath=/dev/null commit`.

**Accurate API (verified):** transition = class with `min_frames` + `frame_at(self, t, canvas, outgoing, incoming, **kwargs)`. `t` 0→1; `outgoing`/`incoming` have `.draw(canvas, cursor_pos=N)`; runner clears the canvas before each call; return ignored. Canvas: `.width`, `.height`, `.SubFill(x,y,w,h,r,g,b)`, `.SetPixel(x,y,r,g,b)`. Plugin registers via `@api.transition("wipe")`; constructor receives TOML fields (`color`). Registry accessor: `led_ticker.transitions.get_transition_class(name)`.

---

### Task 1: Dedicated transition example plugin + tripwire test

**Files:**
- Create: `examples/plugins/example_transition/__init__.py`
- Create: `tests/test_plugins/test_example_transition_plugin.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_plugins/test_example_transition_plugin.py`:

```python
"""Tripwire for the Writing-a-transition how-to's worked example
(examples/plugins/example_transition).

Keeps the shipped example (and the docs bound to it) honest: the wipe registers,
and its frame_at DRAWS onto the canvas (return value ignored), sweeps a colored
line midway, and snaps to the incoming frame at t >= 1.0.
"""

import shutil
from pathlib import Path

import pytest

from led_ticker import _plugin_loader as L
from led_ticker.transitions import get_transition_class

EXAMPLE_DIR = (
    Path(__file__).resolve().parents[2] / "examples" / "plugins" / "example_transition"
)


class _Frame:
    """Stub frame: records draws and paints a recognizable pixel at (0, 0)."""

    def __init__(self, color):
        self.color = color
        self.drawn = False

    def draw(self, canvas, cursor_pos=0):
        self.drawn = True
        canvas.SetPixel(0, 0, *self.color)
        return canvas, 0


def _canvas():
    from rgbmatrix import RGBMatrix, RGBMatrixOptions

    opts = RGBMatrixOptions()
    opts.cols = 64
    opts.rows = 32
    opts.chain_length = 1
    opts.parallel = 1
    return RGBMatrix(options=opts).CreateFrameCanvas()


@pytest.fixture
def wipe_cls(tmp_path):
    L.reset_plugins()
    pdir = tmp_path / "plugins"
    pdir.mkdir()
    shutil.copytree(EXAMPLE_DIR, pdir / "example_transition")
    try:
        result = L.load_plugins(pdir, entry_points_enabled=False)
        assert (
            "example_transition" in {i.namespace for i in result.loaded}
        ), result.failed
        yield get_transition_class("example_transition.wipe")
    finally:
        L.reset_plugins()


def test_wipe_registers(wipe_cls):
    assert wipe_cls.__name__ == "Wipe"
    assert getattr(wipe_cls, "min_frames", 0) == 16


def test_wipe_draws_sweep_line_midway(wipe_cls):
    canvas = _canvas()
    out_frame = _Frame((1, 2, 3))
    in_frame = _Frame((4, 5, 6))
    wipe_cls().frame_at(0.5, canvas, out_frame, in_frame)
    # outgoing drawn, incoming not yet; a cyan sweep line sits at x = 32 (t*64).
    assert out_frame.drawn and not in_frame.drawn
    assert canvas.get_pixel(32, 0) == (0, 255, 255)


def test_wipe_snaps_to_incoming_at_end(wipe_cls):
    canvas = _canvas()
    out_frame = _Frame((1, 2, 3))
    in_frame = _Frame((4, 5, 6))
    wipe_cls().frame_at(1.0, canvas, out_frame, in_frame)
    assert in_frame.drawn
    assert canvas.get_pixel(0, 0) == (4, 5, 6)


def test_wipe_accepts_color_config(wipe_cls):
    canvas = _canvas()
    out_frame = _Frame((1, 2, 3))
    in_frame = _Frame((4, 5, 6))
    wipe_cls(color=[255, 0, 0]).frame_at(0.5, canvas, out_frame, in_frame)
    assert canvas.get_pixel(32, 0) == (255, 0, 0)
```

- [ ] **Step 2: Run it — expect FAIL**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/docs-transition
PYTHONPATH=tests/stubs uv run python -m pytest tests/test_plugins/test_example_transition_plugin.py -q; echo "EXIT=$?"
```
Expected: FAIL (the `example_transition` dir doesn't exist → fixture load assertion fails). If `uv run` isn't set up, run `uv sync --extra dev` first.

- [ ] **Step 3: Write the plugin**

Create `examples/plugins/example_transition/__init__.py`:

```python
"""Example led-ticker plugin: a custom 'wipe' transition (the 'Writing a transition' how-to).

Drop `example_transition/` into your `config/plugins/` (local use), or package it
with an `[project.entry-points."led_ticker.plugins"]  example_transition = "example_transition:register"`
entry, then use it in TOML as `transition = {type = "example_transition.wipe"}`.

Imports only `led_ticker.plugin` (the public surface) plus stdlib.
"""


def register(api):
    @api.transition("wipe")
    class Wipe:
        # Enough frames for a smooth sweep regardless of the configured duration.
        min_frames = 16

        # A config-driven field: `transition = {type = "example_transition.wipe",
        # color = [255, 0, 0]}` passes `color` here. Default: cyan.
        def __init__(self, color=(0, 255, 255)):
            self.color = color

        def frame_at(self, t, canvas, outgoing, incoming, **kwargs):
            # The engine clears the canvas before each call — don't clear it here.
            # Draw onto `canvas`; the return value is ignored (returning canvas
            # is just a convention).
            w = canvas.width
            h = getattr(canvas, "height", 16)

            if t >= 1.0:
                incoming.draw(canvas, cursor_pos=0)
                return canvas

            edge = int(t * w)  # the sweep edge moves left -> right, 0 .. w

            outgoing.draw(canvas, cursor_pos=0)  # 1. the old frame fills the canvas
            if edge > 0:  # 2. black out everything the sweep has passed
                canvas.SubFill(0, 0, edge, h, 0, 0, 0)
            for dx in range(2):  # 3. a 2px colored sweep line at the edge
                x = edge + dx
                if 0 <= x < w:
                    for y in range(h):
                        canvas.SetPixel(x, y, self.color[0], self.color[1], self.color[2])
            return canvas
```

- [ ] **Step 4: Run the test — expect PASS**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/docs-transition
PYTHONPATH=tests/stubs uv run python -m pytest tests/test_plugins/test_example_transition_plugin.py -q; echo "EXIT=$?"
```
Expected: 4 passed, EXIT=0.

- [ ] **Step 5: Commit**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/docs-transition
git add examples/plugins/example_transition/__init__.py tests/test_plugins/test_example_transition_plugin.py
git -c core.hooksPath=/dev/null commit -m "test: dedicated example_transition plugin + tripwire for the Writing a transition how-to

A focused plugin (namespace example_transition) registering a 'wipe' transition,
with a behavioral tripwire asserting registration + that frame_at draws the sweep
and snaps to incoming at t>=1.0 — the worked example the page is bound to."
```

---

### Task 2: The Writing a transition how-to page + sidebar + hub pointer

**Files:**
- Create: `docs/site/src/content/docs/plugins/extending/writing-a-transition.mdx`
- Modify: `docs/site/astro.config.mjs`
- Modify: `docs/site/src/content/docs/plugins/authoring/04-beyond-widgets.mdx`

- [ ] **Step 1: Write the page**

Create `docs/site/src/content/docs/plugins/extending/writing-a-transition.mdx` with EXACTLY this content. The "Complete listing" python block MUST be byte-identical to `examples/plugins/example_transition/__init__.py` from Task 1.

````mdx
---
title: Writing a transition
description: Build a custom transition for led-ticker from a plugin — the frame_at contract, the canvas drawing tools, and a worked wipe effect.
---

import { Aside, Steps } from "@astrojs/starlight/components";
import DemoGif from "../../../../components/DemoGif.astro";
import RelatedPages from "../../../../components/RelatedPages.astro";

This is a how-to for **plugin authors**: write a custom transition — the short animation played between two widgets. You'll build a **wipe** that sweeps the old frame away behind a colored line, then reveals the new one.

<Aside type="note">
  New to plugins? Start with the [authoring guide](/plugins/authoring/01-scaffold/) to scaffold one, then come back. You only need `led_ticker.plugin`.
</Aside>

<DemoGif
  src="/demos/transitions-wipe.gif"
  caption="A wipe — a sweep line crosses the panel and the new content follows."
/>

## The `frame_at` contract

A transition is a class with one method, `frame_at`, called once per frame while the transition plays:

```python
def frame_at(self, t, canvas, outgoing, incoming, **kwargs): ...
```

- **`t`** runs from **0.0 to 1.0** — the transition's progress. At `t=0` you'd show only `outgoing`; at `t=1.0`, only `incoming`.
- **`canvas`** is what you draw on (the pixel grid for this frame). The engine **clears it for you before each call** — don't clear it yourself.
- **`outgoing`** and **`incoming`** are the two frames. You don't read their pixels — you ask each to paint itself with **`frame.draw(canvas, cursor_pos=N)`**, where `cursor_pos` is a horizontal pixel offset (`0` = in place).
- The **return value is ignored** — the engine renders whatever you drew onto `canvas`. Returning `canvas` is a harmless convention.

<Aside type="tip">
  `frame_at` also receives a few `**kwargs` (e.g. `outgoing_scroll_pos`, `duration_ms`) that fancier transitions use. You can ignore them — this wipe does.
</Aside>

## The drawing tools

You composite each frame with three canvas calls:

- **`canvas.width`** / **`canvas.height`** — the panel size in pixels (use `getattr(canvas, "height", 16)` to be safe).
- **`canvas.SubFill(x, y, w, h, r, g, b)`** — fill a rectangle with a color. This is how you "clip": a frame drawn with `draw()` can't be cropped, so you draw it in full and then **black out** the part you don't want with `SubFill(…, 0, 0, 0)`.
- **`canvas.SetPixel(x, y, r, g, b)`** — set a single pixel (here, the sweep line).

## Build the wipe

Draw the **outgoing** frame, black out everything the sweep has already crossed, draw the colored **sweep line** at the moving edge, and at the very end snap to the **incoming** frame:

```python
def frame_at(self, t, canvas, outgoing, incoming, **kwargs):
    w = canvas.width
    h = getattr(canvas, "height", 16)

    if t >= 1.0:
        incoming.draw(canvas, cursor_pos=0)
        return canvas

    edge = int(t * w)  # the sweep edge moves left -> right, 0 .. w

    outgoing.draw(canvas, cursor_pos=0)  # 1. the old frame fills the canvas
    if edge > 0:  # 2. black out everything the sweep has passed
        canvas.SubFill(0, 0, edge, h, 0, 0, 0)
    for dx in range(2):  # 3. a 2px colored sweep line at the edge
        x = edge + dx
        if 0 <= x < w:
            for y in range(h):
                canvas.SetPixel(x, y, self.color[0], self.color[1], self.color[2])
    return canvas
```

Two finishing touches: set **`min_frames`** so the sweep has enough frames to look smooth no matter the configured duration, and accept a **`color`** field so the sweep line is configurable from TOML.

<Aside type="note">
  This is a "sweep the old away to a colored line, then reveal the new" wipe — the same style as led-ticker's built-in wipes. A _progressive_ reveal (new content on the left, old on the right, with no black band) isn't cleanly possible because `draw()` can't be clipped — which is exactly why the black-out step exists.
</Aside>

## Register and use it

<Steps>

1. Register the class in your plugin's `register(api)`:

   ```python
   @api.transition("wipe")
   class Wipe: ...
   ```

   It's namespaced — in the `example_transition` plugin it becomes `example_transition.wipe`.

2. Use it on a section in your `config/config.toml` (optionally with a `color`):

   ```toml
   [[playlist.section]]
   transition = { type = "example_transition.wipe", color = [255, 0, 0] }
   ```

3. Install your plugin so led-ticker can find it. `make render-demo` loads only **installed** plugins (see [Package & install](/plugins/authoring/03-package/)), then preview — no hardware needed:

   ```bash
   pip install -e .   # run from your plugin's directory
   make render-demo CONFIG=config/config.toml OUT=preview.gif
   open preview.gif   # macOS; xdg-open on Linux
   ```

</Steps>

## Complete listing

The full plugin — `examples/plugins/example_transition/__init__.py`:

```python
"""Example led-ticker plugin: a custom 'wipe' transition (the 'Writing a transition' how-to).

Drop `example_transition/` into your `config/plugins/` (local use), or package it
with an `[project.entry-points."led_ticker.plugins"]  example_transition = "example_transition:register"`
entry, then use it in TOML as `transition = {type = "example_transition.wipe"}`.

Imports only `led_ticker.plugin` (the public surface) plus stdlib.
"""


def register(api):
    @api.transition("wipe")
    class Wipe:
        # Enough frames for a smooth sweep regardless of the configured duration.
        min_frames = 16

        # A config-driven field: `transition = {type = "example_transition.wipe",
        # color = [255, 0, 0]}` passes `color` here. Default: cyan.
        def __init__(self, color=(0, 255, 255)):
            self.color = color

        def frame_at(self, t, canvas, outgoing, incoming, **kwargs):
            # The engine clears the canvas before each call — don't clear it here.
            # Draw onto `canvas`; the return value is ignored (returning canvas
            # is just a convention).
            w = canvas.width
            h = getattr(canvas, "height", 16)

            if t >= 1.0:
                incoming.draw(canvas, cursor_pos=0)
                return canvas

            edge = int(t * w)  # the sweep edge moves left -> right, 0 .. w

            outgoing.draw(canvas, cursor_pos=0)  # 1. the old frame fills the canvas
            if edge > 0:  # 2. black out everything the sweep has passed
                canvas.SubFill(0, 0, edge, h, 0, 0, 0)
            for dx in range(2):  # 3. a 2px colored sweep line at the edge
                x = edge + dx
                if 0 <= x < w:
                    for y in range(h):
                        canvas.SetPixel(x, y, self.color[0], self.color[1], self.color[2])
            return canvas
```

## If it doesn't work

- **"Unknown transition" / the name isn't found** — check the namespaced `type` (`example_transition.wipe`, not `wipe`) and that the plugin is installed/loaded (see [Installing a plugin](/plugins/#installing-a-plugin)).
- **The transition flickers or is too quick to see** — raise `min_frames`, or the section's transition duration.
- **The canvas looks smeared / wrong** — don't call `canvas.Clear()` or `canvas.Fill()` yourself; the engine clears before each `frame_at`.

<RelatedPages
  slugs={["plugins/api-reference", "plugins/extending/custom-emoji", "plugins/authoring/01-scaffold"]}
/>
````

- [ ] **Step 2: Add the sidebar entry**

In `docs/site/astro.config.mjs`, inside the "Extending led-ticker" group's `items`, add "Writing a transition" after "Custom emoji". Change:

```js
            {
              label: "Extending led-ticker",
              items: [{ label: "Custom emoji", link: "/plugins/extending/custom-emoji/" }],
            },
```

to:

```js
            {
              label: "Extending led-ticker",
              items: [
                { label: "Custom emoji", link: "/plugins/extending/custom-emoji/" },
                { label: "Writing a transition", link: "/plugins/extending/writing-a-transition/" },
              ],
            },
```

(If prettier previously collapsed the single-item array onto one line, match the current formatting; the key is the two items end up in the Extending group.)

- [ ] **Step 3: Add the hub pointer in `04-beyond-widgets.mdx`**

In `plugins/authoring/04-beyond-widgets.mdx`, under "## Render surfaces (decorate a class)" (where `api.transition` is listed), just after that section's code block, add:

```markdown
Writing a transition? See the [Writing a transition](/plugins/extending/writing-a-transition/) how-to — the `frame_at` contract and a worked wipe.
```

- [ ] **Step 4: Format, build, lint**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/docs-transition
make docs-format
make docs-build; echo "BUILD=$?"
make docs-lint; echo "LINT=$?"
```
Expected: both exit 0; build reports one more page (58). `astro check` validates links — `/plugins/authoring/01-scaffold/`, `/plugins/authoring/03-package/`, `/plugins/#installing-a-plugin`, `/plugins/api-reference`, `/plugins/extending/custom-emoji` all resolve.

- [ ] **Step 5: Verify the listing matches the plugin file**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/docs-transition
python3 - <<'PY'
import re, pathlib
page = pathlib.Path("docs/site/src/content/docs/plugins/extending/writing-a-transition.mdx").read_text()
plugin = pathlib.Path("examples/plugins/example_transition/__init__.py").read_text().rstrip("\n")
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
cd /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/docs-transition
git add docs/site/src/content/docs/plugins/extending/writing-a-transition.mdx docs/site/astro.config.mjs docs/site/src/content/docs/plugins/authoring/04-beyond-widgets.mdx
git -c core.hooksPath=/dev/null commit -m "docs: add the Writing a transition how-to (Extending piece 2)

A worked wipe: the frame_at contract (t, outgoing/incoming, return-ignored,
runner-clears-first), the SubFill/SetPixel tools and why, and the full effect —
bound to the example_transition plugin. Sidebar entry + beyond-widgets pointer."
```

---

### Task 3: Technical-writer + hobbyist-persona review

After the page builds clean, run two reviews and apply fixes:

- [ ] **Step 1: Tech-writer reviewer** — reads `plugins/extending/writing-a-transition.mdx`, runs the `docs/DOCS-STYLE.md` §3 checklist (how-to page; time stamp #12 and heavy reassurance #15 lightly-applied/N-A per the "more technical" steer), returns prioritized must-fix vs nice-to-have.
- [ ] **Step 2: Hobbyist-persona ("Sam") check** — the same persona, now with the goal "build my wipe transition." Reports whether the page closes his original transition blockers (what `t`/`outgoing`/`incoming` mean, what to draw, return-ignored, a real worked effect he can copy) — pass/fail on those.
- [ ] **Step 3:** Apply must-fix from both; re-run `make docs-format && make docs-build && make docs-lint` + the transition tripwire (`PYTHONPATH=tests/stubs uv run python -m pytest tests/test_plugins/test_example_transition_plugin.py -q`); confirm exit 0 and (if the listing changed) re-run the Task 2 Step 5 MATCH check; commit fixes (or record "no must-fix items").

---

## Self-Review

**1. Spec coverage:**
- New "Writing a transition" page: frame_at contract, drawing tools, worked wipe (build steps + min_frames + color), honesty note, register/use, complete listing, troubleshooting, CTA → Task 2 Step 1. ✓
- Dedicated tested example plugin + behavioral tripwire (registration + frame_at behavior incl. snap-to-incoming + color config) → Task 1. ✓
- Sidebar entry + 04-beyond-widgets hub pointer → Task 2 Steps 2–3. ✓
- Tech-writer + hobbyist review loop → Task 3. ✓
- Verification: build/lint clean, tripwire passes, listing matches file → Tasks 1/2 steps. ✓
- Out of scope (color-provider/service pages; no runtime transition code change; no byte-match test; no progressive-reveal effect) → respected. ✓

**2. Placeholder scan:** No TBD/TODO.

**3. Type/consistency:** The plugin file is identical in Task 1 Step 3 and the Task 2 "Complete listing" (Task 2 Step 5 enforces MATCH). The test's geometry is consistent with the plugin: stub canvas `width=64` (cols=64, chain=1) → at `t=0.5`, `edge = int(0.5*64) = 32`, so the sweep line lands at `x=32` (asserted), `SubFill(0,0,32,h,…)` blacks `[0,32)` (so the (0,0) outgoing pixel is gone — the test asserts the sweep pixel, not (0,0)); at `t=1.0` incoming draws `(0,0)` (asserted). `min_frames=16` asserted. `color` passed as a list works via `self.color[0..2]`. Component import depth `../../../../components/` matches the verified depth-3 convention. The worked `frame_at` uses only public calls (`.draw`, `SubFill`, `SetPixel`, `width`/`height`).
