# Extending led-ticker — Custom Emoji How-To (piece 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a new "Extending led-ticker" docs section with its first page — a technical **Custom emoji** how-to — backed by a dedicated tested example plugin, plus targeted correctness fixes to the API reference and a hub pointer from `04-beyond-widgets`.

**Architecture:** A new tested example plugin (`examples/plugins/example_emoji/`) + a behavioral tripwire test; a new MDX how-to page whose code matches that plugin; a new sidebar group; small edits to the API reference (fixing the `HiResEmoji`/`PixelData`/`frame_at` gaps a hobbyist review surfaced) and to `04-beyond-widgets`. No runtime code changes.

**Tech Stack:** Astro Starlight, MDX, pytest. Docs: `make docs-build`/`make docs-lint`. Tests: `PYTHONPATH=tests/stubs uv run python -m pytest`.

**Source spec:** `docs/superpowers/specs/2026-06-05-extending-custom-emoji-design.md`

**Worktree:** `.claude/worktrees/docs-tech`, branch `feat/docs-tech` (the held #157 branch — these changes land with it). **Commit convention:** `git -c core.hooksPath=/dev/null commit`.

**Accurate API (verified from `src/led_ticker/pixel_emoji.py`, `_types.py`):** `PixelData = list[(x,y,r,g,b)]` (8×8, one tuple per lit pixel). `api.emoji(slug, data)` → low-res `EMOJI_REGISTRY`. `HiResEmoji(pixels, physical_size, physical_width=None)` (physical coords); `api.hires_emoji(slug, HiResEmoji(...))` → `HIRES_REGISTRY`. Inline `:ns.slug:` and unscaled canvases resolve only via low-res.

---

### Task 1: Dedicated emoji example plugin + tripwire test

**Files:**
- Create: `examples/plugins/example_emoji/__init__.py`
- Create: `tests/test_plugins/test_example_emoji_plugin.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_plugins/test_example_emoji_plugin.py`:

```python
"""Tripwire for the Custom-emoji how-to's worked example (examples/plugins/example_emoji).

The 'Custom emoji' page's code blocks are this plugin; this test keeps the
shipped example (and therefore the docs) honest against the real emoji API.
"""

import shutil
from pathlib import Path

import pytest

import led_ticker.pixel_emoji as pe
from led_ticker import _plugin_loader as L

EXAMPLE_DIR = (
    Path(__file__).resolve().parents[2] / "examples" / "plugins" / "example_emoji"
)


@pytest.fixture
def loaded(tmp_path):
    """Load examples/plugins/example_emoji into an isolated dir."""
    L.reset_plugins()
    pdir = tmp_path / "plugins"
    pdir.mkdir()
    shutil.copytree(EXAMPLE_DIR, pdir / "example_emoji")
    try:
        result = L.load_plugins(pdir, entry_points_enabled=False)
        assert "example_emoji" in {i.namespace for i in result.loaded}, result.failed
        yield
    finally:
        L.reset_plugins()


def test_low_res_heart_registered(loaded):
    data = pe.EMOJI_REGISTRY.get("example_emoji.heart")
    assert data is not None, "low-res emoji example_emoji.heart was not registered"
    assert len(data) == 40, f"expected a 40-pixel heart, got {len(data)}"
    # the bottom point of the heart (row 6, x in {3,4})
    assert (3, 6, 220, 40, 60) in data


def test_hires_heart_registered(loaded):
    assert "example_emoji.heart" in pe.HIRES_REGISTRY
```

- [ ] **Step 2: Run it — expect FAIL (plugin doesn't exist yet)**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/docs-tech
PYTHONPATH=tests/stubs uv run python -m pytest tests/test_plugins/test_example_emoji_plugin.py -q; echo "EXIT=$?"
```
Expected: FAIL (the `example_emoji` dir doesn't exist, so the fixture's load assertion fails). If `uv run` isn't set up, run `uv sync --extra dev` first.

- [ ] **Step 3: Write the plugin**

Create `examples/plugins/example_emoji/__init__.py`:

```python
"""Example led-ticker plugin: a custom inline emoji (the 'Custom emoji' how-to).

Drop `example_emoji/` into your `config/plugins/` (local use), or package it with
an `[project.entry-points."led_ticker.plugins"]  example_emoji = "example_emoji:register"`
entry, then use it inline in any message as `:example_emoji.heart:`.

Imports only `led_ticker.plugin` (the public surface) plus stdlib.
"""

from led_ticker.plugin import HiResEmoji

# An 8x8 heart. "X" = a lit pixel, "." = transparent.
_HEART_ART = [
    ".XX..XX.",
    "XXXXXXXX",
    "XXXXXXXX",
    "XXXXXXXX",
    ".XXXXXX.",
    "..XXXX..",
    "...XX...",
    "........",
]
_RED = (220, 40, 60)

# Low-res sprite: a PixelData = list of (x, y, r, g, b), one tuple per lit pixel.
HEART = [
    (x, y, *_RED)
    for y, row in enumerate(_HEART_ART)
    for x, cell in enumerate(row)
    if cell == "X"
]

# Hi-res sprite: scale the 8x8 up 2x into a 16x16, in physical coordinates.
HEART_HIRES = tuple(
    (x * 2 + dx, y * 2 + dy, r, g, b)
    for (x, y, r, g, b) in HEART
    for dx in (0, 1)
    for dy in (0, 1)
)


def register(api):
    # Low-res: used by inline `:example_emoji.heart:` and small / unscaled signs.
    api.emoji("heart", HEART)
    # Hi-res: used on scaled (big) signs; keep the low-res one for inline use.
    api.hires_emoji("heart", HiResEmoji(pixels=HEART_HIRES, physical_size=16))
```

- [ ] **Step 4: Run the test — expect PASS**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/docs-tech
PYTHONPATH=tests/stubs uv run python -m pytest tests/test_plugins/test_example_emoji_plugin.py -q; echo "EXIT=$?"
```
Expected: 2 passed, EXIT=0.

- [ ] **Step 5: Commit**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/docs-tech
git add examples/plugins/example_emoji/__init__.py tests/test_plugins/test_example_emoji_plugin.py
git -c core.hooksPath=/dev/null commit -m "test: dedicated example_emoji plugin + tripwire for the Custom emoji how-to

A focused plugin (namespace example_emoji) registering a low-res + hi-res heart,
with a behavioral tripwire asserting both registrations — the worked example the
Custom emoji page is bound to."
```

---

### Task 2: The Custom emoji how-to page + sidebar

**Files:**
- Create: `docs/site/src/content/docs/plugins/extending/custom-emoji.mdx`
- Modify: `docs/site/astro.config.mjs`

- [ ] **Step 1: Write the page**

Create `docs/site/src/content/docs/plugins/extending/custom-emoji.mdx` with EXACTLY this content. The "Complete listing" code block MUST be byte-identical to `examples/plugins/example_emoji/__init__.py` from Task 1.

````mdx
---
title: Custom emoji
description: Add your own inline emoji to led-ticker from a plugin — the PixelData format, registering low-res and hi-res sprites, and a PNG-to-pixels recipe.
---

import { Aside, Steps } from "@astrojs/starlight/components";
import DemoGif from "../../../../components/DemoGif.astro";
import RelatedPages from "../../../../components/RelatedPages.astro";

This is a how-to for **plugin authors**: add your own emoji so it renders inline in any message as `:yourplugin.slug:`. You'll register an 8×8 sprite, see it on the sign, then add a hi-res version for scaled (big) signs.

<Aside type="note">
  New to plugins? Start with the [authoring guide](/plugins/authoring/01-scaffold/) to scaffold one, then come back. You only need `led_ticker.plugin` — and, for the optional PNG recipe at the end, [Pillow](https://python-pillow.org/).
</Aside>

<DemoGif
  src="/demos/assets-emoji.gif"
  caption="Emoji render inline in message text — the built-ins, and any you add."
/>

## What a sprite looks like: `PixelData`

A low-res emoji is a **`PixelData`** — a `list` of `(x, y, r, g, b)` tuples, **one per lit pixel** on an 8×8 grid (`x`, `y` are 0–7; `r`, `g`, `b` are 0–255). Pixels you leave out stay transparent.

The easy way to build one is to "draw" it as text, then expand it:

```python
# An 8×8 heart. "X" = a lit pixel, "." = transparent.
_HEART_ART = [
    ".XX..XX.",
    "XXXXXXXX",
    "XXXXXXXX",
    "XXXXXXXX",
    ".XXXXXX.",
    "..XXXX..",
    "...XX...",
    "........",
]
_RED = (220, 40, 60)
HEART = [
    (x, y, *_RED)
    for y, row in enumerate(_HEART_ART)
    for x, cell in enumerate(row)
    if cell == "X"
]
# HEART == [(1, 0, 220, 40, 60), (2, 0, 220, 40, 60), ...] — 40 tuples.
```

## Register it and show it

<Steps>

1. Register the sprite inside your plugin's `register(api)` under a slug:

   ```python
   def register(api):
       api.emoji("heart", HEART)
   ```

   The slug is namespaced automatically — in the `example_emoji` plugin it becomes `example_emoji.heart`.

2. Use it inline in any message by wrapping the namespaced slug in colons:

   ```toml
   [[playlist.section.widget]]
   type = "message"
   text = "we :example_emoji.heart: led-ticker"
   ```

3. Preview it — no hardware needed:

   ```bash
   make render-demo CONFIG=config/config.toml OUT=preview.gif
   open preview.gif   # macOS; xdg-open on Linux
   ```

</Steps>

## Low-res vs hi-res

led-ticker keeps two emoji registries:

- **Low-res** — the 8×8 `PixelData` above. Used by inline `:slug:` text and by **small / unscaled signs**. This is all most plugins need.
- **Hi-res** — a larger sprite in **physical** pixel coordinates. Used on **scaled (big) signs** (`default_scale > 1`) and by direct draws (`draw_emoji_at`).

Rule of thumb: **small sign → register only the low-res sprite. Big / scaled sign → also register a hi-res version** (keep the low-res one — inline `:slug:` always resolves through it; a hi-res sprite with no low-res counterpart logs a warning at load).

## Adding a hi-res sprite

`HiResEmoji(pixels=…, physical_size=…)` takes pixels in physical coordinates (`0 … physical_size − 1`). The quickest way is to scale your 8×8 sprite up — here, 2× into a 16×16:

```python
from led_ticker.plugin import HiResEmoji

HEART_HIRES = tuple(
    (x * 2 + dx, y * 2 + dy, r, g, b)
    for (x, y, r, g, b) in HEART
    for dx in (0, 1)
    for dy in (0, 1)
)


def register(api):
    api.emoji("heart", HEART)
    api.hires_emoji("heart", HiResEmoji(pixels=HEART_HIRES, physical_size=16))
```

## From a PNG

Have an image instead? This one-time helper converts an 8×8 PNG into a `PixelData` list you can paste in. It's a script you run yourself — not part of the plugin.

```python
# pip install pillow
from PIL import Image

img = Image.open("heart.png").convert("RGBA")  # an 8×8 image
pixels = []
for y in range(img.height):
    for x in range(img.width):
        r, g, b, a = img.getpixel((x, y))
        if a > 0:  # skip fully transparent pixels
            pixels.append((x, y, r, g, b))

print(pixels)  # paste this as your PixelData
```

<Aside type="tip">
  Keep it 8×8 for a low-res sprite. For a hi-res sprite, use a 16×16 (or 32×32) image and pass `physical_size=16` (or `32`).
</Aside>

## Complete listing

The full plugin — `examples/plugins/example_emoji/__init__.py`:

```python
"""Example led-ticker plugin: a custom inline emoji (the 'Custom emoji' how-to).

Drop `example_emoji/` into your `config/plugins/` (local use), or package it with
an `[project.entry-points."led_ticker.plugins"]  example_emoji = "example_emoji:register"`
entry, then use it inline in any message as `:example_emoji.heart:`.

Imports only `led_ticker.plugin` (the public surface) plus stdlib.
"""

from led_ticker.plugin import HiResEmoji

# An 8x8 heart. "X" = a lit pixel, "." = transparent.
_HEART_ART = [
    ".XX..XX.",
    "XXXXXXXX",
    "XXXXXXXX",
    "XXXXXXXX",
    ".XXXXXX.",
    "..XXXX..",
    "...XX...",
    "........",
]
_RED = (220, 40, 60)

# Low-res sprite: a PixelData = list of (x, y, r, g, b), one tuple per lit pixel.
HEART = [
    (x, y, *_RED)
    for y, row in enumerate(_HEART_ART)
    for x, cell in enumerate(row)
    if cell == "X"
]

# Hi-res sprite: scale the 8x8 up 2x into a 16x16, in physical coordinates.
HEART_HIRES = tuple(
    (x * 2 + dx, y * 2 + dy, r, g, b)
    for (x, y, r, g, b) in HEART
    for dx in (0, 1)
    for dy in (0, 1)
)


def register(api):
    # Low-res: used by inline `:example_emoji.heart:` and small / unscaled signs.
    api.emoji("heart", HEART)
    # Hi-res: used on scaled (big) signs; keep the low-res one for inline use.
    api.hires_emoji("heart", HiResEmoji(pixels=HEART_HIRES, physical_size=16))
```

## If it doesn't work

- **The emoji doesn't appear / shows as literal text** — check the slug is namespaced (`:example_emoji.heart:`, not `:heart:`) and that the plugin is installed/loaded (see [Installing a plugin](/plugins/#installing-a-plugin)).
- **It shows on a small sign but not a big one** — register a hi-res sprite (above); inline use still needs the low-res one.
- **A "hi-res emoji has no low-res counterpart" warning at load** — register a matching `api.emoji(slug, …)` alongside `api.hires_emoji(slug, …)`.

<RelatedPages
  slugs={["plugins/api-reference", "assets/emoji", "plugins/authoring/01-scaffold"]}
/>
````

- [ ] **Step 2: Add the sidebar group**

In `docs/site/astro.config.mjs`, inside the `Plugins` group's `items` array, after the `Authoring a plugin` nested object, add an `Extending led-ticker` group. Change:

```js
            {
              label: "Authoring a plugin",
              items: [
                { label: "1. Scaffold & register", link: "/plugins/authoring/01-scaffold/" },
                { label: "2. Build the widget", link: "/plugins/authoring/02-widget/" },
                { label: "3. Package & install", link: "/plugins/authoring/03-package/" },
                { label: "4. Beyond widgets", link: "/plugins/authoring/04-beyond-widgets/" },
              ],
            },
          ],
        },
```

to:

```js
            {
              label: "Authoring a plugin",
              items: [
                { label: "1. Scaffold & register", link: "/plugins/authoring/01-scaffold/" },
                { label: "2. Build the widget", link: "/plugins/authoring/02-widget/" },
                { label: "3. Package & install", link: "/plugins/authoring/03-package/" },
                { label: "4. Beyond widgets", link: "/plugins/authoring/04-beyond-widgets/" },
              ],
            },
            {
              label: "Extending led-ticker",
              items: [
                { label: "Custom emoji", link: "/plugins/extending/custom-emoji/" },
              ],
            },
          ],
        },
```

- [ ] **Step 3: Format, build, lint**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/docs-tech
make docs-format
make docs-build; echo "BUILD=$?"
make docs-lint; echo "LINT=$?"
```
Expected: both exit 0; build reports one more page than before (57). `astro check` validates links — `/plugins/authoring/01-scaffold/`, `/plugins/#installing-a-plugin`, `/plugins/api-reference`, `/assets/emoji` all resolve.

- [ ] **Step 4: Verify the listing matches the plugin file**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/docs-tech
# Extract the page's "Complete listing" python block and diff against the plugin.
python3 - <<'PY'
import re, pathlib
page = pathlib.Path("docs/site/src/content/docs/plugins/extending/custom-emoji.mdx").read_text()
plugin = pathlib.Path("examples/plugins/example_emoji/__init__.py").read_text().rstrip("\n")
# the listing is the python block that starts with the module docstring
blocks = re.findall(r"```python\n(.*?)```", page, re.DOTALL)
listing = next(b for b in blocks if b.lstrip().startswith('"""Example led-ticker plugin')).rstrip("\n")
print("MATCH" if listing == plugin else "MISMATCH")
if listing != plugin:
    import difflib
    print("\n".join(difflib.unified_diff(plugin.splitlines(), listing.splitlines(), "plugin", "page-listing", lineterm="")))
PY
```
Expected: `MATCH`. If `MISMATCH`, reconcile the page's Complete listing block to the plugin file (the plugin file is the source of truth; prettier does not touch fenced code, so a mismatch is a real copy error).

- [ ] **Step 5: Commit**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/docs-tech
git add docs/site/src/content/docs/plugins/extending/custom-emoji.mdx docs/site/astro.config.mjs
git -c core.hooksPath=/dev/null commit -m "docs: add the Custom emoji how-to + Extending led-ticker section

A worked, technical how-to (PixelData format, register-and-show, low/hi-res
model, HiResEmoji, a PNG->pixels recipe), bound to the example_emoji plugin.
New 'Extending led-ticker' sidebar group under Plugins."
```

---

### Task 3: API reference fixes + beyond-widgets hub pointer

**Files:**
- Modify: `docs/site/src/content/docs/plugins/api-reference.mdx`
- Modify: `docs/site/src/content/docs/plugins/authoring/04-beyond-widgets.mdx`

- [ ] **Step 1: Fix the `HiResEmoji` and `PixelData` rows**

In `plugins/api-reference.mdx`, in the "Data & types" table, replace the `HiResEmoji` row's description (keep the first column `` `HiResEmoji` `` unchanged — the drift test reads it). Change:
```
| `HiResEmoji`     | Hi-res emoji sprite data                           |
```
to:
```
| `HiResEmoji`     | A hi-res emoji sprite — `pixels` ((x,y,r,g,b) in physical coords), `physical_size`, optional `physical_width` |
```
And update the `PixelData` row description to make "one tuple per lit pixel" explicit. Change:
```
| `PixelData`      | `list[(x, y, r, g, b)]` describing a low-res emoji  |
```
to:
```
| `PixelData`      | `list[(x, y, r, g, b)]` — one tuple per lit pixel of a low-res emoji |
```
(Prettier will re-pad the table columns; that's fine. Do NOT touch the first-column backtick names.)

- [ ] **Step 2: Add the `frame_at` correctness note**

In `plugins/api-reference.mdx`, immediately AFTER the "Visual building blocks" python code block (the one ending with the `api.easing("snap", …)` line and its closing ```` ``` ````), and BEFORE the `### Assets` heading, insert this paragraph (it sits inside the `api-methods` marker region, but contains no `api.<name>` token, so the drift test is unaffected):

```markdown
In a transition's `frame_at`, `t` runs 0 → 1; `outgoing` and `incoming` each have a `.draw(canvas)`; you render the in-between frame onto `canvas`, and the **return value is ignored**. A full walkthrough (building a wipe) is coming in the Extending section.
```

- [ ] **Step 3: Link the Assets rows to the worked example**

In `plugins/api-reference.mdx`, immediately after the **Assets** table (and before the existing emoji-pairing `<Aside>`), add:

```markdown
→ Worked example: [Custom emoji](/plugins/extending/custom-emoji/) covers the `PixelData` format, hi-res sprites, and a PNG→pixels recipe.
```

- [ ] **Step 4: Slim the `04-beyond-widgets` emoji line to a hub pointer**

In `plugins/authoring/04-beyond-widgets.mdx`, under "## Value surfaces (pass data directly)", just after the code block containing the `api.emoji(...)` / `api.hires_emoji(...)` lines, add:

```markdown
Adding your own emoji? See the [Custom emoji](/plugins/extending/custom-emoji/) how-to for the `PixelData` format, low-res vs hi-res sprites, and a PNG→pixels recipe.
```

- [ ] **Step 5: Format, build, lint, re-run the drift test**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/docs-tech
make docs-format
make docs-build; echo "BUILD=$?"
make docs-lint; echo "LINT=$?"
PYTHONPATH=tests/stubs uv run python -m pytest tests/test_docs_plugin_api_drift.py -q; echo "DRIFT=$?"
```
Expected: all exit 0. The drift test must still pass (the edits changed only description columns + added a marker-free paragraph). The new `/plugins/extending/custom-emoji/` links resolve.

- [ ] **Step 6: Commit**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/docs-tech
git add docs/site/src/content/docs/plugins/api-reference.mdx docs/site/src/content/docs/plugins/authoring/04-beyond-widgets.mdx
git -c core.hooksPath=/dev/null commit -m "docs: fix API reference emoji/transition gaps; point beyond-widgets at the how-to

Define HiResEmoji's fields and PixelData's 'one tuple per lit pixel'; note that
frame_at draws onto canvas and its return is ignored; link the Assets rows and
04-beyond-widgets to the new Custom emoji how-to."
```

---

### Task 4: Technical-writer + hobbyist-persona review

After the page builds clean, run two reviews:

- [ ] **Step 1: Tech-writer reviewer** — reads `plugins/extending/custom-emoji.mdx` + the reference edits, runs the `docs/DOCS-STYLE.md` §3 checklist (it's a how-to, so all items apply except the lightly-applied/N-A time stamp #12 and heavy reassurance #15, per the "more technical" steer), returns prioritized must-fix vs nice-to-have.
- [ ] **Step 2: Hobbyist-persona check ("Sam")** — the same persona that triggered this work re-reads the page with the goal "ship a custom inline emoji." It reports whether the page now closes the gaps (literal `PixelData`, register-and-show loop, low/hi-res clarity, `HiResEmoji` fields, PNG recipe) — a pass/fail on Sam's original blockers.
- [ ] **Step 3:** Apply must-fix items from both; re-run `make docs-format && make docs-build && make docs-lint`, the emoji tripwire, and the drift test (all exit 0); commit fixes (or record "no must-fix items").

---

## Self-Review

**1. Spec coverage:**
- New "Extending led-ticker" section + sidebar → Task 2 Steps 1–2. ✓
- Custom emoji page: PixelData literal, register-and-show, low/hi-res plainly, HiResEmoji, PNG recipe, complete listing, troubleshooting, CTA → Task 2 Step 1. ✓
- Dedicated tested example plugin + behavioral tripwire → Task 1. ✓
- API reference fixes (HiResEmoji fields, PixelData wording, frame_at return-ignored, Assets link) → Task 3 Steps 1–3. ✓
- Slim 04-beyond-widgets to a hub pointer → Task 3 Step 4. ✓
- Tech-writer + hobbyist-persona review loop → Task 4. ✓
- Verification: build/lint clean, emoji tripwire passes, drift test still passes, listing matches file → Tasks 1/2/3 steps + Task 2 Step 4. ✓
- Out of scope (transition/color-provider/service pages; no runtime emoji code change; no byte-match test) → respected. ✓

**2. Placeholder scan:** No TBD/TODO. The "coming in the Extending section" note in the frame_at fix is intentional forward-reference copy, not a plan placeholder.

**3. Type/consistency:** The plugin file content is identical in Task 1 Step 3 and the Task 2 page "Complete listing" (Task 2 Step 4 enforces this). The heart is 40 low-res pixels (4+8+8+8+6+4+2), matching the test's `len == 40` and the `(3, 6, 220, 40, 60)` bottom-point assertion. `HEART` builds 5-tuples via `(x, y, *_RED)`; `HEART_HIRES` unpacks `(x, y, r, g, b)` — consistent. Component import depth `../../../../components/` matches the verified depth-3 convention. Drift-test safety: Task 3 edits touch only description columns + a marker-free paragraph (no `api.<name>` token, first-column names unchanged).
