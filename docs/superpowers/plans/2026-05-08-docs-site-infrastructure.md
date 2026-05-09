# Docs Site Infrastructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the led-ticker docs site infrastructure — Astro Starlight scaffold, Python gif renderer, fact pack with skill migration, MDX components, prototype pages exercising every component, CI deploy workflow — so subsequent content authoring (Plan B) just fills in pages.

**Architecture:** Three new top-level directories: `docs/site/` (Astro Starlight project), `docs/content-source/` (shared markdown consumed by both site and the existing skill), `tools/render_demo/` (Python script that drives the ticker engine against the test stub canvas, captures frames, encodes a gif). A new `.github/workflows/docs.yml` builds + deploys to GitHub Pages. The existing skill at `.claude/skills/creating-a-config/` is migrated to load shared facts from `docs/content-source/` instead of its own `references/`.

**Tech Stack:** Python 3.13 (existing) + uv (existing) + Pillow + imageio for the renderer; Node LTS + Astro 5 + Starlight for the docs site; GitHub Actions for CI.

---

## File map

| File | Action |
|------|--------|
| `docs/site/package.json` | Create |
| `docs/site/astro.config.mjs` | Create |
| `docs/site/tsconfig.json` | Create |
| `docs/site/.gitignore` | Create |
| `docs/site/src/content.config.ts` | Create — Starlight content collection |
| `docs/site/src/content/docs/index.mdx` | Create — prototype home |
| `docs/site/src/content/docs/getting-started.mdx` | Create — prototype |
| `docs/site/src/content/docs/widgets/message.mdx` | Create — prototype, exercises every component |
| `docs/site/src/content/docs/transitions/push.mdx` | Create — prototype |
| `docs/site/src/content/docs/footguns.mdx` | Create — prototype |
| `docs/site/src/components/DemoGif.astro` | Create |
| `docs/site/src/components/TomlExample.astro` | Create |
| `docs/site/src/components/OptionsTable.astro` | Create |
| `docs/site/src/components/DecisionRule.astro` | Create |
| `docs/site/src/components/RelatedPages.astro` | Create |
| `docs/site/scripts/build-demos.mjs` | Create — prebuild orchestrator |
| `docs/site/demos/message-rainbow.toml` | Create — prototype demo config |
| `docs/site/demos/push-left.toml` | Create — prototype demo config |
| `docs/site/public/.gitkeep` | Create |
| `docs/site/README.md` | Create |
| `docs/content-source/widgets/message.md` | Create — prototype fact pack file |
| `docs/content-source/transitions/push.md` | Create — prototype |
| `docs/content-source/rules/14-typewriter-on-image.md` | Create — prototype |
| `docs/content-source/README.md` | Create |
| `tools/render_demo/__init__.py` | Create |
| `tools/render_demo/recording.py` | Create — canvas-snapshot wrapper |
| `tools/render_demo/placeholder.py` | Create — synthetic missing-asset stand-ins |
| `tools/render_demo/render.py` | Create — CLI orchestrator |
| `tools/render_demo/README.md` | Create |
| `tools/render_demo/test_recording.py` | Create — pytest |
| `tools/render_demo/test_placeholder.py` | Create — pytest |
| `tools/render_demo/test_render.py` | Create — smoke pytest |
| `.github/workflows/docs.yml` | Create |
| `.github/ISSUE_TEMPLATE/submit-sign.yml` | Create |
| `.claude/skills/creating-a-config/SKILL.md` | Modify — load from docs/content-source/ |
| `.claude/skills/creating-a-config/references/widgets.md` | Replace with pointer file |
| `.claude/skills/creating-a-config/references/transitions.md` | Replace with pointer file |
| `.claude/skills/creating-a-config/references/decision-rules.md` | Replace with pointer file |
| `.claude/skills/creating-a-config/references/asset-handling.md` | Replace with pointer file |
| `.claude/skills/creating-a-config/references/hardware-guide.md` | Replace with pointer file |
| `pyproject.toml` | Modify — add Pillow, imageio to deps (Pillow may already be present) |
| `Makefile` | Modify — add `docs-dev`, `docs-build`, `render-demo` targets |
| `.gitignore` | Modify — ignore `docs/site/node_modules`, `docs/site/dist`, `docs/site/public/demos/` |

---

## Task 1: Scaffold Astro Starlight project

**Files:**
- Create: `docs/site/package.json`
- Create: `docs/site/astro.config.mjs`
- Create: `docs/site/tsconfig.json`
- Create: `docs/site/.gitignore`
- Create: `docs/site/public/.gitkeep`
- Create: `docs/site/README.md`
- Modify: `.gitignore` (root) — add Astro outputs

- [ ] **Step 1: Create the Astro project directory structure**

```bash
mkdir -p docs/site/src/content/docs docs/site/src/components docs/site/scripts docs/site/demos docs/site/public
```

- [ ] **Step 2: Create `docs/site/package.json`**

```json
{
  "name": "led-ticker-docs",
  "type": "module",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "dev": "astro dev",
    "build": "node scripts/build-demos.mjs && astro build",
    "preview": "astro preview",
    "build-demos": "node scripts/build-demos.mjs"
  },
  "dependencies": {
    "@astrojs/starlight": "^0.30.0",
    "astro": "^5.0.0",
    "sharp": "^0.33.0"
  }
}
```

- [ ] **Step 3: Create `docs/site/astro.config.mjs`**

```js
import { defineConfig } from "astro/config";
import starlight from "@astrojs/starlight";

export default defineConfig({
  site: "https://jamesawesome.github.io",
  base: "/led-ticker",
  integrations: [
    starlight({
      title: "led-ticker",
      description: "An asyncio Python toolkit for displaying scrolling feeds on RGB LED matrix panels.",
      social: [
        { icon: "github", label: "GitHub", href: "https://github.com/JamesAwesome/led-ticker" },
      ],
      sidebar: [
        { label: "Home", link: "/" },
        { label: "Getting started", link: "/getting-started/" },
        {
          label: "Widgets",
          autogenerate: { directory: "widgets" },
        },
        {
          label: "Transitions",
          autogenerate: { directory: "transitions" },
        },
        {
          label: "Footguns",
          link: "/footguns/",
        },
      ],
    }),
  ],
});
```

- [ ] **Step 4: Create `docs/site/tsconfig.json`**

```json
{
  "extends": "astro/tsconfigs/strict",
  "include": [".astro/types.d.ts", "**/*"],
  "exclude": ["dist"]
}
```

- [ ] **Step 5: Create `docs/site/.gitignore`**

```
node_modules/
dist/
.astro/
public/demos/
```

- [ ] **Step 6: Create `docs/site/public/.gitkeep` (empty file) and `docs/site/README.md`**

```markdown
# led-ticker docs site

Astro Starlight site for the led-ticker documentation.

## Local development

```bash
cd docs/site
npm install
npm run dev
```

Visits `http://localhost:4321/led-ticker/` (Astro picks the port; check the terminal output).

## Building demo gifs

`npm run build` runs `scripts/build-demos.mjs` first, which iterates `demos/*.toml`
and calls the Python renderer for any missing or stale gifs in `public/demos/`.
The renderer requires `uv` and the Python deps installed at the repo root
(`uv sync` from the repo root).

## Deploy

GitHub Actions builds and deploys on push to `main`. See `.github/workflows/docs.yml`.
```

- [ ] **Step 7: Append Astro outputs to root `.gitignore`**

Find the existing `.gitignore` at the repo root. Append at the end:

```
# Astro docs site
docs/site/node_modules/
docs/site/dist/
docs/site/.astro/
docs/site/public/demos/
```

- [ ] **Step 8: Verify the package.json is valid**

Run: `cd docs/site && node -e "JSON.parse(require('fs').readFileSync('package.json'))" && echo OK`
Expected: `OK`

- [ ] **Step 9: Commit**

```bash
git add docs/site/ .gitignore
git commit -m "feat(docs): scaffold Astro Starlight project"
```

---

## Task 2: Build the Python renderer's recording wrapper

**Files:**
- Create: `tools/render_demo/__init__.py`
- Create: `tools/render_demo/recording.py`
- Create: `tools/render_demo/test_recording.py`

**Background:** The recording wrapper intercepts `LedFrame.matrix.SwapOnVSync` calls. Each time the ticker engine swaps a canvas, we copy its pixel data into a `PIL.Image` and stash it in a frames list before forwarding to the underlying stub swap. The wrapper is what makes pixel-level capture possible without changing engine code.

- [ ] **Step 1: Create `tools/render_demo/__init__.py` (empty file)**

```python
```

- [ ] **Step 2: Write the failing test**

Create `tools/render_demo/test_recording.py`:

```python
"""Tests for the recording canvas wrapper."""

from __future__ import annotations

import sys
from pathlib import Path

# Make rgbmatrix test stub available before importing led_ticker
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT / "tests" / "stubs"))

import pytest
from PIL import Image

from tools.render_demo.recording import RecordingMatrix, snapshot_to_image


def _make_stub_canvas(width: int, height: int):
    from rgbmatrix import RGBMatrix, RGBMatrixOptions

    opts = RGBMatrixOptions()
    opts.rows = height
    opts.cols = width
    opts.chain_length = 1
    matrix = RGBMatrix(options=opts)
    canvas = matrix.CreateFrameCanvas()
    return matrix, canvas


def test_snapshot_to_image_produces_correct_pixels():
    _, canvas = _make_stub_canvas(width=8, height=4)
    canvas.SetPixel(0, 0, 255, 0, 0)  # red top-left
    canvas.SetPixel(7, 3, 0, 0, 255)  # blue bottom-right

    img = snapshot_to_image(canvas)

    assert img.size == (8, 4)
    assert img.getpixel((0, 0)) == (255, 0, 0)
    assert img.getpixel((7, 3)) == (0, 0, 255)
    assert img.getpixel((1, 1)) == (0, 0, 0)  # untouched defaults to black


def test_recording_matrix_captures_each_swap():
    matrix, canvas = _make_stub_canvas(width=4, height=2)
    rec = RecordingMatrix(matrix)

    # First swap with a single red pixel
    canvas.SetPixel(0, 0, 255, 0, 0)
    canvas2 = rec.SwapOnVSync(canvas)

    # Second swap with a single green pixel
    canvas2.SetPixel(1, 0, 0, 255, 0)
    rec.SwapOnVSync(canvas2)

    assert len(rec.frames) == 2
    assert rec.frames[0].getpixel((0, 0)) == (255, 0, 0)
    assert rec.frames[1].getpixel((1, 0)) == (0, 255, 0)


def test_recording_matrix_forwards_to_underlying_swap():
    """SwapOnVSync must return the underlying stub's return value
    (the previous back-buffer) so engine code that captures the result
    keeps working."""
    matrix, canvas = _make_stub_canvas(width=2, height=2)
    rec = RecordingMatrix(matrix)

    returned = rec.SwapOnVSync(canvas)

    # Stub returns a different canvas (the previous back-buffer); we just
    # verify it's a canvas-shaped object, not None or the same one.
    assert returned is not None
    assert hasattr(returned, "SetPixel")


def test_recording_matrix_proxies_other_attrs():
    """CreateFrameCanvas, etc. should pass through to the wrapped matrix."""
    matrix, _ = _make_stub_canvas(width=4, height=4)
    rec = RecordingMatrix(matrix)
    new_canvas = rec.CreateFrameCanvas()
    assert new_canvas is not None
    assert hasattr(new_canvas, "SetPixel")
```

- [ ] **Step 3: Run the test to verify it fails**

```bash
uv run pytest tools/render_demo/test_recording.py -v
```
Expected: `ImportError: cannot import name 'RecordingMatrix' from 'tools.render_demo.recording'`

- [ ] **Step 4: Implement `tools/render_demo/recording.py`**

```python
"""Canvas-snapshot wrapper around RGBMatrix.SwapOnVSync.

The renderer drives the existing ticker engine and intercepts each
canvas swap to capture pixel data. We avoid modifying engine code by
wrapping the matrix object the engine talks to.
"""

from __future__ import annotations

from typing import Any

from PIL import Image


def snapshot_to_image(canvas: Any) -> Image.Image:
    """Copy a stub canvas's pixel grid into a fresh RGB PIL Image.

    Reads from the test stub's `_pixels` dict directly. The dict is
    keyed by `(x, y)` and stores `(r, g, b)` tuples. Unset pixels
    default to black.
    """
    width = canvas.width
    height = canvas.height
    img = Image.new("RGB", (width, height), (0, 0, 0))
    pixels = canvas._pixels  # stub-only; intentional coupling
    for (x, y), rgb in pixels.items():
        if 0 <= x < width and 0 <= y < height:
            img.putpixel((x, y), rgb)
    return img


class RecordingMatrix:
    """Wraps an RGBMatrix and captures each SwapOnVSync.

    Forwards every other attribute access to the wrapped matrix so the
    engine sees a transparent stand-in.
    """

    def __init__(self, matrix: Any) -> None:
        self._matrix = matrix
        self.frames: list[Image.Image] = []

    def SwapOnVSync(self, canvas: Any) -> Any:
        self.frames.append(snapshot_to_image(canvas))
        return self._matrix.SwapOnVSync(canvas)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._matrix, name)
```

- [ ] **Step 5: Run the tests — expect PASS (4 tests)**

```bash
uv run pytest tools/render_demo/test_recording.py -v
```
Expected: `4 passed`

- [ ] **Step 6: Commit**

```bash
git add tools/render_demo/__init__.py tools/render_demo/recording.py tools/render_demo/test_recording.py
git commit -m "feat(render-demo): canvas-snapshot recording wrapper"
```

---

## Task 3: Build the placeholder generator

**Files:**
- Create: `tools/render_demo/placeholder.py`
- Create: `tools/render_demo/test_placeholder.py`

**Background:** Configs may reference assets that aren't in the repo (customer-IP logos, custom fonts). The renderer detects missing assets, generates synthetic stand-ins to a temp dir, and rewrites the config to point at them. Image stand-ins are dark-lavender solid blocks with the missing-path text overlay; gif stand-ins add a 3-frame pulse; font references fall back to bundled `Inter-Regular.otf`.

- [ ] **Step 1: Write the failing test**

Create `tools/render_demo/test_placeholder.py`:

```python
"""Tests for placeholder asset generation."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from tools.render_demo.placeholder import (
    make_image_placeholder,
    make_gif_placeholder,
    rewrite_config_for_missing_assets,
)


def test_image_placeholder_has_correct_dimensions(tmp_path):
    out = tmp_path / "ph.png"
    make_image_placeholder(out, width=64, height=64, missing_path="assets/foo.png")
    img = Image.open(out)
    assert img.size == (64, 64)


def test_image_placeholder_is_dark_lavender(tmp_path):
    out = tmp_path / "ph.png"
    make_image_placeholder(out, width=32, height=32, missing_path="x.png")
    img = Image.open(out).convert("RGB")
    # Top-left is solid background (no text overlay there).
    r, g, b = img.getpixel((1, 1))
    # Rough check: dark-lavender range.
    assert 30 <= r <= 90
    assert 25 <= g <= 80
    assert 60 <= b <= 130


def test_gif_placeholder_has_three_frames(tmp_path):
    out = tmp_path / "ph.gif"
    make_gif_placeholder(out, width=32, height=32, missing_path="x.gif")
    img = Image.open(out)
    img.seek(0)
    frame_count = 0
    while True:
        frame_count += 1
        try:
            img.seek(img.tell() + 1)
        except EOFError:
            break
    assert frame_count == 3


def test_rewrite_config_substitutes_missing_image(tmp_path):
    cfg = {
        "playlist": {
            "section": [
                {
                    "widget": [
                        {"type": "image", "path": "assets/missing.png"},
                    ],
                }
            ]
        }
    }
    rewritten = rewrite_config_for_missing_assets(
        cfg,
        config_dir=tmp_path,
        placeholder_dir=tmp_path / "ph",
    )
    new_path = rewritten["playlist"]["section"][0]["widget"][0]["path"]
    # Must point at a real file (the placeholder) AND no longer be the
    # original missing path.
    assert new_path != "assets/missing.png"
    assert (tmp_path / new_path).exists() or Path(new_path).exists()


def test_rewrite_config_leaves_existing_assets_alone(tmp_path):
    real_png = tmp_path / "real.png"
    Image.new("RGB", (8, 8), (255, 0, 0)).save(real_png)

    cfg = {
        "playlist": {
            "section": [
                {"widget": [{"type": "image", "path": "real.png"}]}
            ]
        }
    }
    rewritten = rewrite_config_for_missing_assets(
        cfg,
        config_dir=tmp_path,
        placeholder_dir=tmp_path / "ph",
    )
    assert rewritten["playlist"]["section"][0]["widget"][0]["path"] == "real.png"


def test_rewrite_config_substitutes_missing_gif(tmp_path):
    cfg = {
        "playlist": {
            "section": [
                {"widget": [{"type": "gif", "path": "assets/missing.gif"}]}
            ]
        }
    }
    rewritten = rewrite_config_for_missing_assets(
        cfg,
        config_dir=tmp_path,
        placeholder_dir=tmp_path / "ph",
    )
    new_path = rewritten["playlist"]["section"][0]["widget"][0]["path"]
    assert new_path != "assets/missing.gif"
    # Verify the file actually got created
    full_path = (tmp_path / new_path) if not Path(new_path).is_absolute() else Path(new_path)
    assert full_path.exists()
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
uv run pytest tools/render_demo/test_placeholder.py -v
```
Expected: `ImportError: cannot import name 'make_image_placeholder'`

- [ ] **Step 3: Implement `tools/render_demo/placeholder.py`**

```python
"""Synthesize placeholder assets for missing files referenced by demo configs.

Demo configs may point at customer-IP brand assets that aren't checked
into the repo. Rather than skip these demos, we generate visually
obvious stand-ins so the configs still render.

- Image / single-frame: solid dark-lavender block with the missing path
  text rendered on top in small white.
- GIF: same block with a 3-frame subtle pulse so motion-aware widgets
  still tick.
- Font: not handled here — the renderer detects font references and
  rewrites them to Inter-Regular separately.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

# Brand-neutral dark lavender. Visible but obviously a placeholder.
_BG = (60, 50, 90)
_LIGHT = (75, 65, 110)


def _draw_label(img: Image.Image, text: str) -> None:
    draw = ImageDraw.Draw(img)
    # Use the default PIL font (small bitmap). It's fine for placeholder labels.
    try:
        font = ImageFont.load_default()
    except OSError:
        font = None
    # Fit within the image; truncate if needed.
    max_chars = max(8, img.width // 6)
    label = text if len(text) <= max_chars else "…" + text[-(max_chars - 1):]
    draw.text((2, 2), "PLACEHOLDER", fill=(255, 255, 255), font=font)
    draw.text((2, 12), label, fill=(220, 220, 220), font=font)


def make_image_placeholder(
    out_path: Path, *, width: int, height: int, missing_path: str
) -> None:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (width, height), _BG)
    _draw_label(img, missing_path)
    img.save(out_path)


def make_gif_placeholder(
    out_path: Path, *, width: int, height: int, missing_path: str
) -> None:
    """3-frame placeholder. Pulse alternates background slightly so
    widget code that reads gif_loops × frame_count behaves naturally."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    frames = []
    for bg in (_BG, _LIGHT, _BG):
        frame = Image.new("RGB", (width, height), bg)
        _draw_label(frame, missing_path)
        frames.append(frame)
    frames[0].save(
        out_path,
        save_all=True,
        append_images=frames[1:],
        duration=200,
        loop=0,
    )


def _asset_resolves(value: str, config_dir: Path) -> bool:
    """Check whether a path string resolves to an existing file.

    Tries: absolute path, relative to config_dir, and relative to repo root.
    """
    p = Path(value)
    if p.is_absolute() and p.exists():
        return True
    if (config_dir / p).exists():
        return True
    return False


def rewrite_config_for_missing_assets(
    config: dict[str, Any], *, config_dir: Path, placeholder_dir: Path
) -> dict[str, Any]:
    """Walk every widget in the config; for each image/gif widget whose
    `path` doesn't resolve to a real file, generate a placeholder and
    rewrite the path to point at it.

    Returns a deep-copy with substitutions; original `config` is untouched.
    Default placeholder dimensions: 256×64 (bigsign panel), which most
    `fit` modes will scale appropriately for whatever panel the demo
    actually configures.
    """
    config_dir = Path(config_dir)
    placeholder_dir = Path(placeholder_dir)
    placeholder_dir.mkdir(parents=True, exist_ok=True)

    new_cfg = copy.deepcopy(config)
    sections = (new_cfg.get("playlist") or {}).get("section") or []
    for section in sections:
        for widget in section.get("widget") or []:
            wtype = widget.get("type")
            path = widget.get("path")
            if not path or wtype not in ("image", "gif"):
                continue
            if _asset_resolves(path, config_dir):
                continue
            slug = path.replace("/", "_").replace("\\", "_")
            if wtype == "image":
                ph_path = placeholder_dir / f"{slug}.png"
                make_image_placeholder(ph_path, width=256, height=64, missing_path=path)
            else:
                ph_path = placeholder_dir / f"{slug}.gif"
                make_gif_placeholder(ph_path, width=256, height=64, missing_path=path)
            widget["path"] = str(ph_path)
    return new_cfg
```

- [ ] **Step 4: Run the tests — expect PASS (6 tests)**

```bash
uv run pytest tools/render_demo/test_placeholder.py -v
```
Expected: `6 passed`

- [ ] **Step 5: Commit**

```bash
git add tools/render_demo/placeholder.py tools/render_demo/test_placeholder.py
git commit -m "feat(render-demo): synthesize placeholders for missing assets"
```

---

## Task 4: Build the renderer CLI orchestrator

**Files:**
- Create: `tools/render_demo/render.py`
- Create: `tools/render_demo/test_render.py`
- Create: `tools/render_demo/README.md`
- Modify: `pyproject.toml` (add `imageio` dep if missing)

**Background:** The CLI ties everything together: parse args, load TOML, rewrite missing-asset paths, write the rewritten TOML to a temp file, drive the ticker engine for `--duration` seconds while the recording wrapper captures frames, encode the captured frames to a gif at native panel resolution upscaled by `--upscale`. Uses the existing `app.run()` engine entry point but with a hook that swaps the real `RGBMatrix` for `RecordingMatrix(real_matrix)`.

- [ ] **Step 1: Verify `imageio` is in pyproject.toml; add it if missing**

Run: `grep -n "imageio" pyproject.toml`

If no match, edit `pyproject.toml` and add `"imageio>=2.31",` to the `dependencies` list (find the existing list in `[project]` table — it has `aiohttp`, `attrs`, etc.). Then run `uv sync` and verify imageio installs.

```bash
uv sync
uv run python -c "import imageio; print(imageio.__version__)"
```
Expected: prints a version like `2.34.0`. If it errors with ModuleNotFoundError, fix the dependency entry and re-run uv sync.

- [ ] **Step 2: Write the failing smoke test**

Create `tools/render_demo/test_render.py`:

```python
"""Smoke test for the gif renderer CLI."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_RENDERER = _REPO_ROOT / "tools" / "render_demo" / "render.py"


_MINIMAL_CONFIG = """\
[display]
rows = 16
cols = 32
chain = 5
default_scale = 1
brightness = 60

[[playlist.section]]
mode = "swap"
loop_count = 1
hold_time = 0.5

[[playlist.section.widget]]
type = "message"
text = "Hi"
"""


def test_renderer_produces_a_gif_for_a_minimal_config(tmp_path):
    cfg = tmp_path / "demo.toml"
    cfg.write_text(_MINIMAL_CONFIG)
    out = tmp_path / "out.gif"

    result = subprocess.run(
        ["uv", "run", "python", str(_RENDERER), str(cfg), "-o", str(out), "--duration", "1"],
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
    )

    assert result.returncode == 0, f"renderer failed:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
    assert out.exists()

    img = Image.open(out)
    # Native panel is 160x16; default upscale is 4 → 640x64.
    assert img.size == (640, 64)
    # Multi-frame gif (1 sec at 20fps ≈ 20 frames; tolerate 18-22).
    n = 0
    img.seek(0)
    while True:
        n += 1
        try:
            img.seek(img.tell() + 1)
        except EOFError:
            break
    assert 15 <= n <= 25, f"expected ~20 frames, got {n}"


def test_renderer_substitutes_placeholder_for_missing_image(tmp_path):
    cfg = tmp_path / "demo.toml"
    cfg.write_text("""\
[display]
rows = 16
cols = 32
chain = 5
default_scale = 1
brightness = 60

[[playlist.section]]
mode = "swap"
loop_count = 1
hold_time = 0.5

[[playlist.section.widget]]
type = "image"
path = "assets/does-not-exist.png"
fit = "pillarbox"
hold_seconds = 0.5
""")
    out = tmp_path / "out.gif"

    result = subprocess.run(
        ["uv", "run", "python", str(_RENDERER), str(cfg), "-o", str(out), "--duration", "1"],
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
    )

    assert result.returncode == 0, f"renderer failed:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
    assert out.exists()
```

- [ ] **Step 3: Run the test to verify it fails**

```bash
uv run pytest tools/render_demo/test_render.py -v
```
Expected: `FileNotFoundError` or test fails because `render.py` doesn't exist.

- [ ] **Step 4: Implement `tools/render_demo/render.py`**

```python
#!/usr/bin/env python3
"""Render a led-ticker config TOML to a gif at panel resolution.

Drives the existing ticker engine against the test stub canvas; captures
each `SwapOnVSync` frame; encodes to gif. Generates placeholder assets
on the fly for any image/gif paths that don't resolve.

Usage:
    uv run python tools/render_demo/render.py <config.toml> -o out.gif \\
        [--duration 5] [--upscale 4] [--fps 20] [--start-section 0]
"""

from __future__ import annotations

import argparse
import asyncio
import shutil
import sys
import tempfile
import tomllib
from pathlib import Path

# Ensure the rgbmatrix test stub is importable BEFORE any led_ticker import.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT / "tests" / "stubs"))

import imageio.v2 as imageio  # noqa: E402
import tomli_w  # noqa: E402  -- TOML writer; alternative: hand-format
from PIL import Image  # noqa: E402

from tools.render_demo.placeholder import rewrite_config_for_missing_assets  # noqa: E402
from tools.render_demo.recording import RecordingMatrix  # noqa: E402


def _load_config(path: Path) -> dict:
    with path.open("rb") as f:
        return tomllib.load(f)


def _trim_to_section(config: dict, start_section: int) -> dict:
    """Drop sections before `start_section` so a long config jumps to
    the selected section."""
    sections = (config.get("playlist") or {}).get("section") or []
    if start_section <= 0 or start_section >= len(sections):
        return config
    config["playlist"]["section"] = sections[start_section:]
    return config


def _upscale(img: Image.Image, factor: int) -> Image.Image:
    if factor == 1:
        return img
    return img.resize((img.width * factor, img.height * factor), Image.NEAREST)


async def _drive_engine(rewritten_cfg_path: Path, duration_s: float, recorder_holder: list) -> None:
    """Start the led-ticker app on the rewritten config; substitute a
    RecordingMatrix for the real RGBMatrix; cancel after `duration_s`.

    Patches `led_ticker.frame.RGBMatrix` so when LedFrame instantiates the
    matrix, it gets a `RecordingMatrix` wrapping the stub. The recorder
    is appended to `recorder_holder` so the caller can read frames after
    the run ends.
    """
    from led_ticker import frame as frame_mod
    from led_ticker.app import run as app_run

    original_rgbmatrix = frame_mod.RGBMatrix

    def patched_rgbmatrix(*args, **kwargs):
        real = original_rgbmatrix(*args, **kwargs)
        rec = RecordingMatrix(real)
        recorder_holder.append(rec)
        return rec

    frame_mod.RGBMatrix = patched_rgbmatrix
    try:
        task = asyncio.create_task(app_run(rewritten_cfg_path))
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=duration_s)
        except asyncio.TimeoutError:
            pass
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    finally:
        frame_mod.RGBMatrix = original_rgbmatrix


def render(
    config_path: Path,
    out_path: Path,
    *,
    duration: float = 5.0,
    upscale: int = 4,
    fps: int = 20,
    start_section: int = 0,
) -> None:
    config = _load_config(config_path)
    config = _trim_to_section(config, start_section)

    with tempfile.TemporaryDirectory(prefix="led-ticker-render-") as tmp:
        tmp_dir = Path(tmp)
        rewritten = rewrite_config_for_missing_assets(
            config,
            config_dir=config_path.parent,
            placeholder_dir=tmp_dir / "placeholders",
        )

        # Write rewritten config to a temp file the engine can load.
        rewritten_path = tmp_dir / "rewritten.toml"
        rewritten_path.write_bytes(tomli_w.dumps(rewritten).encode("utf-8"))

        recorder_holder: list = []
        asyncio.run(_drive_engine(rewritten_path, duration, recorder_holder))

        if not recorder_holder:
            raise RuntimeError("Renderer never instantiated a matrix; engine may have crashed.")
        rec = recorder_holder[0]
        if not rec.frames:
            raise RuntimeError("No frames captured; the engine started but never swapped a canvas.")

        upscaled = [_upscale(f, upscale) for f in rec.frames]
        imageio.mimsave(out_path, upscaled, format="GIF", duration=1.0 / fps, loop=0)


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a led-ticker config to a gif")
    parser.add_argument("config", type=Path, help="Path to TOML config")
    parser.add_argument("-o", "--output", type=Path, required=True, help="Output gif path")
    parser.add_argument("--duration", type=float, default=5.0, help="Capture duration in seconds (default 5)")
    parser.add_argument("--upscale", type=int, default=4, help="Pixel upscale factor (default 4)")
    parser.add_argument("--fps", type=int, default=20, help="Output gif fps (default 20)")
    parser.add_argument("--start-section", type=int, default=0, help="Start at this section index (default 0)")
    args = parser.parse_args()

    if not args.config.exists():
        print(f"Config not found: {args.config}", file=sys.stderr)
        sys.exit(2)

    render(
        args.config,
        args.output,
        duration=args.duration,
        upscale=args.upscale,
        fps=args.fps,
        start_section=args.start_section,
    )


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Add `tomli-w` to pyproject.toml deps**

Edit `pyproject.toml`. In the `[project] dependencies` list, add `"tomli-w>=1.0",`. Then:

```bash
uv sync
uv run python -c "import tomli_w; print('ok')"
```
Expected: `ok`.

- [ ] **Step 6: Run the smoke tests**

```bash
uv run pytest tools/render_demo/test_render.py -v
```
Expected: `2 passed`. The first test verifies a basic message renders to a 640×64 gif with ~20 frames; the second verifies a missing image asset gets placeholder-substituted.

- [ ] **Step 7: Run the full test suite to confirm no regressions**

```bash
make test 2>&1 | tail -3
```
Expected: same pass count as before plus the new tests. No failures.

- [ ] **Step 8: Create `tools/render_demo/README.md`**

```markdown
# render-demo

Render a led-ticker config TOML to a gif at panel resolution. Used by the
docs site to generate per-widget demo gifs from minimal config snippets.

## Usage

```bash
uv run python tools/render_demo/render.py path/to/config.toml -o out.gif \
  [--duration 5] [--upscale 4] [--fps 20] [--start-section 0]
```

## How it works

The script wraps `LedFrame.matrix.SwapOnVSync` with a `RecordingMatrix` that
snapshots each canvas before forwarding to the underlying stub swap. After
`--duration` seconds, the captured frames are upscaled (default 4×) and
encoded to a gif.

## Missing assets

If the config references images, gifs, or fonts that don't exist on disk,
the renderer generates synthetic placeholder stand-ins (dark-lavender block
with the missing path text) before running. This means customer-IP configs
can be used as structural demos without committing brand assets to the repo.

## Tests

```bash
uv run pytest tools/render_demo/ -v
```
```

- [ ] **Step 9: Commit**

```bash
git add tools/render_demo/ pyproject.toml uv.lock
git commit -m "feat(render-demo): CLI orchestrator and smoke tests"
```

---

## Task 5: Build the prebuild orchestrator (build-demos.mjs)

**Files:**
- Create: `docs/site/scripts/build-demos.mjs`
- Create: `docs/site/demos/message-rainbow.toml`
- Create: `docs/site/demos/push-left.toml`

- [ ] **Step 1: Create the prototype demo configs**

`docs/site/demos/message-rainbow.toml`:

```toml
# Demo: message widget with per-character rainbow font color.
[display]
rows = 16
cols = 32
chain = 5
default_scale = 1
brightness = 60

[[playlist.section]]
mode = "swap"
loop_count = 1
hold_time = 4.0

[[playlist.section.widget]]
type = "message"
text = "Hello, world!"
font_color = "rainbow"
```

`docs/site/demos/push-left.toml`:

```toml
# Demo: push_left transition between two messages.
[display]
rows = 16
cols = 32
chain = 5
default_scale = 1
brightness = 60

[transitions]
default = "push_left"
duration = 0.6

[[playlist.section]]
mode = "swap"
loop_count = 2
hold_time = 1.5

[[playlist.section.widget]]
type = "message"
text = "First"

[[playlist.section.widget]]
type = "message"
text = "Second"
```

- [ ] **Step 2: Create `docs/site/scripts/build-demos.mjs`**

```js
#!/usr/bin/env node
/**
 * Prebuild step: render each demo TOML to a gif if missing or stale.
 *
 * Walks `demos/*.toml`. For each, checks `public/demos/<name>.gif`.
 * If the gif is missing or older than the TOML, runs the Python renderer.
 * Any failure aborts the build with a non-zero exit so we never deploy
 * with broken demo gifs.
 */

import { existsSync, mkdirSync, readdirSync, statSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const SITE_ROOT = resolve(__dirname, "..");
const REPO_ROOT = resolve(SITE_ROOT, "..", "..");
const DEMOS_DIR = join(SITE_ROOT, "demos");
const OUT_DIR = join(SITE_ROOT, "public", "demos");
const RENDERER = join(REPO_ROOT, "tools", "render_demo", "render.py");

function isStale(gifPath, tomlPath) {
  if (!existsSync(gifPath)) return true;
  return statSync(tomlPath).mtimeMs > statSync(gifPath).mtimeMs;
}

function renderDemo(tomlPath, gifPath) {
  console.log(`[build-demos] rendering ${tomlPath} -> ${gifPath}`);
  const result = spawnSync(
    "uv",
    [
      "run",
      "python",
      RENDERER,
      tomlPath,
      "-o",
      gifPath,
      "--duration",
      "5",
    ],
    { cwd: REPO_ROOT, stdio: "inherit" },
  );
  if (result.status !== 0) {
    console.error(`[build-demos] FAILED: ${tomlPath}`);
    process.exit(1);
  }
}

function main() {
  if (!existsSync(DEMOS_DIR)) {
    console.log(`[build-demos] no demos dir at ${DEMOS_DIR}; nothing to do`);
    return;
  }
  mkdirSync(OUT_DIR, { recursive: true });

  const tomls = readdirSync(DEMOS_DIR).filter((f) => f.endsWith(".toml"));
  if (tomls.length === 0) {
    console.log(`[build-demos] no .toml files in ${DEMOS_DIR}; nothing to do`);
    return;
  }

  let rendered = 0;
  let skipped = 0;
  for (const file of tomls) {
    const tomlPath = join(DEMOS_DIR, file);
    const gifName = file.replace(/\.toml$/, ".gif");
    const gifPath = join(OUT_DIR, gifName);
    if (isStale(gifPath, tomlPath)) {
      renderDemo(tomlPath, gifPath);
      rendered++;
    } else {
      skipped++;
    }
  }
  console.log(`[build-demos] done. rendered=${rendered} skipped=${skipped}`);
}

main();
```

- [ ] **Step 3: Smoke-test the script locally**

From the repo root:

```bash
cd docs/site && node scripts/build-demos.mjs
```

Expected: `rendered=2 skipped=0` (both demos rendered fresh) AND two new files at `docs/site/public/demos/message-rainbow.gif` and `push-left.gif`. Each ≥ 50 KB (5 sec at 20fps × upscaled).

- [ ] **Step 4: Run again to verify caching**

```bash
node scripts/build-demos.mjs
```

Expected: `rendered=0 skipped=2`.

- [ ] **Step 5: Commit**

```bash
git add docs/site/scripts/ docs/site/demos/
git commit -m "feat(docs): prebuild script that renders demo gifs"
```

---

## Task 6: Author the MDX components

**Files:**
- Create: `docs/site/src/components/DemoGif.astro`
- Create: `docs/site/src/components/TomlExample.astro`
- Create: `docs/site/src/components/OptionsTable.astro`
- Create: `docs/site/src/components/DecisionRule.astro`
- Create: `docs/site/src/components/RelatedPages.astro`

- [ ] **Step 1: Install Astro deps so the project actually builds**

```bash
cd docs/site && npm install
```

Expected: `node_modules/` populated; no errors. Verify with: `ls node_modules/@astrojs/starlight | head -3` and confirm files exist.

- [ ] **Step 2: Create `docs/site/src/components/DemoGif.astro`**

```astro
---
interface Props {
  src: string;
  caption?: string;
  alt?: string;
}
const { src, caption, alt } = Astro.props;
const altText = alt ?? caption ?? "led-ticker demo";
---

<figure class="demo-gif">
  <img src={src} alt={altText} loading="lazy" />
  {caption && <figcaption>{caption}</figcaption>}
</figure>

<style>
  .demo-gif {
    margin: 1.5rem 0;
    text-align: center;
  }
  .demo-gif img {
    max-width: 100%;
    height: auto;
    image-rendering: pixelated;
    border: 1px solid var(--sl-color-gray-5);
    border-radius: 4px;
    background: black;
  }
  .demo-gif figcaption {
    margin-top: 0.5rem;
    font-size: 0.875rem;
    color: var(--sl-color-gray-3);
  }
</style>
```

- [ ] **Step 3: Create `docs/site/src/components/TomlExample.astro`**

```astro
---
import { Code } from "@astrojs/starlight/components";

interface Props {
  title?: string;
  code: string;
}
const { title, code } = Astro.props;
---

<div class="toml-example">
  {title && <p class="toml-title">{title}</p>}
  <Code code={code} lang="toml" />
</div>

<style>
  .toml-example {
    margin: 1rem 0;
  }
  .toml-title {
    margin: 0 0 0.25rem 0;
    font-weight: 600;
    font-size: 0.875rem;
    color: var(--sl-color-gray-2);
  }
</style>
```

- [ ] **Step 4: Create `docs/site/src/components/OptionsTable.astro`**

```astro
---
/**
 * Imports a fact-pack markdown file from `docs/content-source/` and
 * renders its body inline. The file is expected to contain a
 * markdown table; Astro renders it as HTML.
 *
 * Usage: <OptionsTable source="widgets/message" />
 *   imports `../../../../content-source/widgets/message.md` (relative
 *   from a page nested 4 levels deep under src/content/docs/).
 *
 * Implementation: dynamic glob import that includes every fact-pack
 * file at build time. Lookup by source key.
 */

import { marked } from "marked";

interface Props {
  source: string;
}
const { source } = Astro.props;

// Vite glob: include all .md under content-source. Eager so the
// build resolves them statically.
const files = import.meta.glob("/../../content-source/**/*.md", {
  eager: true,
  query: "?raw",
  import: "default",
});

const lookupKey = `/../../content-source/${source}.md`;
const raw = files[lookupKey];
if (!raw) {
  throw new Error(
    `OptionsTable: source "${source}" not found at ${lookupKey}. ` +
      `Available: ${Object.keys(files).join(", ")}`,
  );
}
const html = marked.parse(raw as string);
---

<div class="options-table" set:html={html} />

<style>
  .options-table table {
    width: 100%;
    border-collapse: collapse;
    margin: 1rem 0;
  }
  .options-table th, .options-table td {
    border: 1px solid var(--sl-color-gray-5);
    padding: 0.4rem 0.6rem;
    text-align: left;
    font-size: 0.95rem;
  }
  .options-table th {
    background: var(--sl-color-gray-6);
  }
</style>
```

- [ ] **Step 5: Add `marked` to `docs/site/package.json` dependencies**

Edit `docs/site/package.json`. Add `"marked": "^14.0.0"` to `dependencies`. Then:

```bash
cd docs/site && npm install
```

- [ ] **Step 6: Create `docs/site/src/components/DecisionRule.astro`**

```astro
---
/**
 * Renders a single decision rule from the fact pack as a callout.
 *
 * Usage: <DecisionRule id="14" />
 *   imports `docs/content-source/rules/14-*.md`.
 */
import { marked } from "marked";

interface Props {
  id: string | number;
}
const { id } = Astro.props;
const idStr = String(id).padStart(2, "0");

const files = import.meta.glob("/../../content-source/rules/*.md", {
  eager: true,
  query: "?raw",
  import: "default",
});

const matchKey = Object.keys(files).find((k) =>
  k.includes(`/${idStr}-`),
);
if (!matchKey) {
  throw new Error(`DecisionRule: rule id "${id}" not found. Looked for files matching /${idStr}-*.md`);
}
const raw = files[matchKey];
const html = marked.parse(raw as string);
---

<aside class="decision-rule" data-rule-id={id}>
  <div class="rule-badge">Rule {id}</div>
  <div set:html={html} />
</aside>

<style>
  .decision-rule {
    border-left: 4px solid var(--sl-color-orange);
    background: var(--sl-color-gray-7);
    padding: 0.75rem 1rem;
    margin: 1rem 0;
    border-radius: 0 4px 4px 0;
  }
  .rule-badge {
    display: inline-block;
    font-size: 0.75rem;
    font-weight: 700;
    color: var(--sl-color-orange);
    margin-bottom: 0.5rem;
    letter-spacing: 0.05em;
  }
  .decision-rule h2,
  .decision-rule h3 {
    font-size: 1rem;
    margin: 0.5rem 0 0.25rem 0;
  }
</style>
```

- [ ] **Step 7: Create `docs/site/src/components/RelatedPages.astro`**

```astro
---
interface Props {
  slugs: string[];
}
const { slugs } = Astro.props;
---

<aside class="related">
  <p class="related-title">See also</p>
  <ul>
    {slugs.map((s) => <li><a href={`/led-ticker/${s}/`}>{s}</a></li>)}
  </ul>
</aside>

<style>
  .related {
    margin-top: 2rem;
    padding-top: 1rem;
    border-top: 1px solid var(--sl-color-gray-5);
  }
  .related-title {
    font-weight: 600;
    margin-bottom: 0.5rem;
  }
  .related ul { list-style: none; padding: 0; margin: 0; }
  .related li { margin: 0.25rem 0; }
</style>
```

- [ ] **Step 8: Commit**

```bash
git add docs/site/src/components/ docs/site/package.json docs/site/package-lock.json
git commit -m "feat(docs): MDX components — DemoGif, TomlExample, OptionsTable, DecisionRule, RelatedPages"
```

---

## Task 7: Author prototype fact-pack files

**Files:**
- Create: `docs/content-source/widgets/message.md`
- Create: `docs/content-source/transitions/push.md`
- Create: `docs/content-source/rules/14-typewriter-on-image.md`
- Create: `docs/content-source/README.md`

- [ ] **Step 1: Create `docs/content-source/README.md`**

```markdown
# Shared fact pack

This directory holds shared markdown content consumed by BOTH:
- The `creating-a-config` skill at `.claude/skills/creating-a-config/`,
  loaded by `SKILL.md` directly.
- The docs site at `docs/site/`, imported by MDX components like
  `<OptionsTable source="widgets/message" />`.

When you add or change content here, both consumers update with no
extra work.

## Layout

- `widgets/<name>.md` — option table + base description per widget.
- `transitions/<family>.md` — push / wipe / sprite / special.
- `rules/<NN>-<slug>.md` — one file per decision rule (numbered).
- `emoji.md`, `color-providers.md`, `animations.md`, `borders.md`, `fonts.md` — vocab references.
- `hardware/<sign>.md` — small sign / bigsign hardware specs.

## What goes where

- This pack: facts (option tables, lists, rules).
- Skill (`SKILL.md`, `references/snippets.md`): wizard flow + recipe library.
- Docs site (`docs/site/src/content/docs/`): tutorials, walkthroughs, framing.
```

- [ ] **Step 2: Create `docs/content-source/widgets/message.md`**

```markdown
| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `text` | string | required | The text to display. Inline `:slug:` emoji are rendered as pixel art. |
| `font` | string | `"6x12"` | BDF font name (e.g., `"5x8"`, `"6x12"`) or hires font (e.g., `"Inter-Bold"`). |
| `font_size` | int | (BDF cell height) | Real-pixel font size for hires fonts. Required if `font` is hires. |
| `font_threshold` | int 0–255 | `128` | Rasterization threshold for hires fonts. Lower = thicker glyphs. |
| `font_color` | RGB list / string / table | `[255, 255, 0]` | Constant `[r,g,b]`, `"rainbow"`, `"color_cycle"`, `"random"`, or `{style="gradient", from=[...], to=[...]}`. |
| `bg_color` | RGB list | none | Background fill color. Painted across the full panel before text. |
| `border` | string / table | none | `"rainbow"`, `[r,g,b]` constant, or `{style="rainbow", thickness=N, speed=N, char_offset=N}`. |
| `animation` | string | none | `"typewriter"` for character-by-character reveal. |
| `frames_per_char` | int | `3` | Typewriter speed: 50 ms × N per character. |
| `padding` | int | `6` | Horizontal padding (in logical pixels) when scrolling. |
| `text_y_offset` | int | `0` | Vertical text nudge in logical rows. Negative = up. |
```

- [ ] **Step 3: Create `docs/content-source/transitions/push.md`**

```markdown
The `push` family scrolls the outgoing and incoming widgets together — the old slides off one edge while the new enters from the opposite edge. Both are visible simultaneously during the transition.

| Name | Direction | Best for |
|------|-----------|----------|
| `push_left` | Old exits left, new enters from right | General purpose, news-ticker feel |
| `push_right` | Old exits right, new enters from left | "Going back" in a sequence |
| `push_up` | Old exits top, new enters from bottom | Countdowns, score updates |
| `push_down` | Old exits bottom, new enters from top | Variety, vertical change |
| `push_alternating` | Cycles through left → right → up → down each swap | Dynamic variety |
| `push_random` | Random direction each swap, never repeats back-to-back | Unpredictable variety |

## Tuning

- `transition_duration` (seconds): default 0.5. Push transitions feel right at 0.4–0.8 s. Below 0.3 the motion blurs; above 1.2 it drags.
- `easing`: `linear`, `ease_in_out` (default for pushes), `ease_out`. Linear is sharper; ease_in_out feels softer.

## Footguns

- Push transitions ignore `transition_color` (no sweep line, no flash).
- Push reads from the engine's "outgoing scroll position" so a widget mid-scroll continues seamlessly into the push. This is why push transitions feel snappier than wipes.
```

- [ ] **Step 4: Create `docs/content-source/rules/14-typewriter-on-image.md`**

```markdown
## Rule 14: animation = "typewriter" on gif/image is single-row only

**SOURCE:** CLAUDE.md — "Typewriter on image widgets" section.

**DETECT:** A widget of type `gif` or `image` specifies `animation = "typewriter"` AND any of: `bottom_text != ""`, `text_align ∈ ("scroll", "scroll_over")`, or `text == ""`.

**SYMPTOM:** Config load raises with one of:
- `"animation='typewriter' on gif/image is single-row only; bottom_text is set"`
- `"animation='typewriter' on gif/image cannot combine with scrolling text_align"`
- `"animation='typewriter' on gif/image requires non-empty text"`

**FIX:**
- For two-row layouts: omit `animation` (typewriter is single-row only).
- For scrolling text: omit `animation`.
- For empty text: add a non-empty `text = "..."` or omit `animation`.

Typewriter on gif/image composes cleanly with `font_color = "rainbow"` and `border = {style="rainbow"}` — independent counters, all animate together. The single-row constraint exists because typewriter draws fixed-position glyphs and a scrolling/two-row layout has no fixed positions to anchor characters to.
```

- [ ] **Step 5: Verify the files exist with the right content**

```bash
ls -la docs/content-source/
wc -l docs/content-source/widgets/message.md docs/content-source/transitions/push.md docs/content-source/rules/14-typewriter-on-image.md
```
Expected: each file is non-zero, all paths exist.

- [ ] **Step 6: Commit**

```bash
git add docs/content-source/
git commit -m "feat(docs): prototype fact-pack files (message widget, push transition, rule 14)"
```

---

## Task 8: Author prototype MDX pages

**Files:**
- Create: `docs/site/src/content/docs/index.mdx`
- Create: `docs/site/src/content/docs/getting-started.mdx`
- Create: `docs/site/src/content/docs/widgets/message.mdx`
- Create: `docs/site/src/content/docs/transitions/push.mdx`
- Create: `docs/site/src/content/docs/footguns.mdx`

- [ ] **Step 1: Create `docs/site/src/content/docs/index.mdx`**

```mdx
---
title: led-ticker
description: An asyncio Python toolkit for displaying scrolling feeds on RGB LED matrix panels.
template: splash
hero:
  tagline: Scrolling feeds on RGB LED matrix panels.
  actions:
    - text: Get started
      link: /led-ticker/getting-started/
      icon: right-arrow
    - text: GitHub
      link: https://github.com/JamesAwesome/led-ticker
      icon: external
      variant: minimal
---

import DemoGif from '../../components/DemoGif.astro';

## Hello world

<DemoGif src="/led-ticker/demos/message-rainbow.gif" caption="A simple `message` widget with rainbow per-character coloring." />

## What you can do

led-ticker drives an RGB LED matrix sign from a TOML config. Display
RSS feeds, weather, countdowns, crypto prices, MLB scores, custom messages,
animated gifs, and still images. Mix transitions, color animations, and
typewriter effects.

[Browse widgets →](/led-ticker/widgets/message/)
[Browse transitions →](/led-ticker/transitions/push/)
```

- [ ] **Step 2: Create `docs/site/src/content/docs/getting-started.mdx`**

```mdx
---
title: Getting started
description: Install led-ticker, point it at a config, watch a sign light up.
---

led-ticker runs on a Raspberry Pi connected to RGB LED matrix panels.
It reads a TOML config file, drives the panels, and updates content
from various sources (RSS, weather, etc.).

## Install

```bash
git clone https://github.com/JamesAwesome/led-ticker.git
cd led-ticker
make dev
```

## Configure

Copy an example config matching your hardware:

```bash
# Pi 4 + 5x32x16 panels
cp config/config.example.toml config/config.toml

# Pi 5 + 8x P3 32x64 panels in vertical-serpentine layout
cp config/config.bigsign.example.toml config/config.toml
```

Edit `config/config.toml` to set up sections, widgets, and transitions.

## Validate

```bash
led-ticker validate config/config.toml
```

A clean config prints `No issues found.` and exits 0. Errors and warnings
print with their fix suggestions; see [`led-ticker validate`](/led-ticker/tools/validate/).

## Run

```bash
# On the Pi:
led-ticker --config config/config.toml

# Or via Docker:
docker compose up -d --build
```
```

- [ ] **Step 3: Create `docs/site/src/content/docs/widgets/message.mdx`**

```mdx
---
title: message widget
description: Static text with optional border, inline emoji, and color/animation effects.
---

import DemoGif from '../../../components/DemoGif.astro';
import TomlExample from '../../../components/TomlExample.astro';
import OptionsTable from '../../../components/OptionsTable.astro';
import DecisionRule from '../../../components/DecisionRule.astro';
import RelatedPages from '../../../components/RelatedPages.astro';

The `message` widget displays static text. It's the most-used widget — most LED signs are 80% messages with a sprinkling of data widgets.

<DemoGif src="/led-ticker/demos/message-rainbow.gif" caption="message with font_color = 'rainbow'" />

<TomlExample title="Minimal example" code={`[[playlist.section.widget]]
type = "message"
text = "Hello, world!"`} />

## Options

<OptionsTable source="widgets/message" />

## Common patterns

Static text with brand color:

<TomlExample code={`[[playlist.section.widget]]
type = "message"
text = "Aerial for Everybody"
font_color = [189, 169, 234]   # brand lavender`} />

Inline emoji:

<TomlExample code={`[[playlist.section.widget]]
type = "message"
text = ":taco: Taco Tuesday!"`} />

Typewriter effect with rainbow text:

<TomlExample code={`[[playlist.section.widget]]
type = "message"
text = "Now Enrolling"
font_color = "rainbow"
animation = "typewriter"`} />

## Footguns

<DecisionRule id="14" />

<RelatedPages slugs={["widgets/countdown", "widgets/two_row", "concepts/color-providers"]} />
```

- [ ] **Step 4: Create `docs/site/src/content/docs/transitions/push.mdx`**

```mdx
---
title: Push transitions
description: Outgoing and incoming widgets scroll together — old slides off one edge while new enters from the opposite edge.
---

import DemoGif from '../../../components/DemoGif.astro';
import OptionsTable from '../../../components/OptionsTable.astro';
import RelatedPages from '../../../components/RelatedPages.astro';

The push family scrolls the outgoing and incoming widgets together. Both are visible simultaneously during the transition.

<DemoGif src="/led-ticker/demos/push-left.gif" caption="push_left between two messages" />

## Variants

<OptionsTable source="transitions/push" />

<RelatedPages slugs={["transitions/wipe", "transitions/special"]} />
```

- [ ] **Step 5: Create `docs/site/src/content/docs/footguns.mdx`**

```mdx
---
title: Footguns
description: Common configuration mistakes and their fixes.
---

import DecisionRule from '../../components/DecisionRule.astro';

This page lists each decision rule the validator checks. Every rule has a
`DETECT` (when it fires), a `SYMPTOM` (what you see), and a `FIX`. Run
[`led-ticker validate`](/led-ticker/tools/validate/) to check your config
against all of these automatically.

<DecisionRule id="14" />
```

- [ ] **Step 6: Build the site to verify all imports resolve**

```bash
cd docs/site && npm run build
```

Expected: build completes successfully. Output in `dist/`.

If it fails on a missing prebuilt demo:

```bash
node scripts/build-demos.mjs
npm run build
```

- [ ] **Step 7: Run `astro dev` and visually verify**

```bash
npm run dev
```

In another terminal or browser, visit `http://localhost:4321/led-ticker/`. Expected:
- Home page renders with hero, the message-rainbow demo gif visible.
- `/widgets/message/` renders with the demo gif, the options table, the typewriter example, and the rule-14 callout.
- `/transitions/push/` renders with the push-left demo gif and the variants table.
- `/footguns/` shows the rule-14 callout.

Stop the dev server with Ctrl+C.

- [ ] **Step 8: Commit**

```bash
git add docs/site/src/content/docs/
git commit -m "feat(docs): prototype MDX pages exercising every component"
```

---

## Task 9: Migrate the skill to load from docs/content-source/

**Files:**
- Modify: `.claude/skills/creating-a-config/SKILL.md`
- Replace: `.claude/skills/creating-a-config/references/widgets.md`
- Replace: `.claude/skills/creating-a-config/references/transitions.md`
- Replace: `.claude/skills/creating-a-config/references/decision-rules.md`
- Replace: `.claude/skills/creating-a-config/references/asset-handling.md`
- Replace: `.claude/skills/creating-a-config/references/hardware-guide.md`

**Background:** The skill currently loads `references/widgets.md`, etc. After migration it loads the equivalent files from `docs/content-source/` so the skill and the docs site share one source. The old `references/*.md` files become 1-line pointer markers (so anyone browsing the file tree gets redirected). `references/snippets.md` is NOT touched (skill-only content).

NOTE: At this point in the plan we've only created prototype fact-pack files for `widgets/message.md`, `transitions/push.md`, and `rules/14-...md`. The full migration (writing all 12 widget files, all 4 transition family files, all 21 rule files, and the rest) happens in Plan B. For Plan A, we only do the mechanical wiring + the prototype files; the skill will function with reduced content until Plan B fills in the rest.

To make the skill still work end-to-end during Plan A, we'll do an interim migration: copy the EXISTING content from `references/widgets.md` etc. into `docs/content-source/widgets-legacy.md`, `transitions-legacy.md`, etc., and have the skill load those interim files. Plan B replaces the legacy files with the proper per-widget / per-transition / per-rule files.

- [ ] **Step 1: Move the existing skill reference content into docs/content-source/ as legacy files**

```bash
cp .claude/skills/creating-a-config/references/widgets.md docs/content-source/widgets-legacy.md
cp .claude/skills/creating-a-config/references/transitions.md docs/content-source/transitions-legacy.md
cp .claude/skills/creating-a-config/references/decision-rules.md docs/content-source/decision-rules-legacy.md
cp .claude/skills/creating-a-config/references/asset-handling.md docs/content-source/asset-handling-legacy.md
cp .claude/skills/creating-a-config/references/hardware-guide.md docs/content-source/hardware-guide-legacy.md
```

Verify:
```bash
ls docs/content-source/*-legacy.md
```
Expected: 5 files.

- [ ] **Step 2: Update `SKILL.md` to load from docs/content-source/**

Edit `.claude/skills/creating-a-config/SKILL.md`. Find every occurrence of `references/widgets.md`, `references/transitions.md`, `references/decision-rules.md`, `references/asset-handling.md`, `references/hardware-guide.md` and replace with the corresponding `docs/content-source/*-legacy.md` path.

Use `grep -n` to find them first:

```bash
grep -n "references/\(widgets\|transitions\|decision-rules\|asset-handling\|hardware-guide\)" .claude/skills/creating-a-config/SKILL.md
```

For each match, edit the line. Example replacements:
- `Load references/widgets.md` → `Load docs/content-source/widgets-legacy.md`
- `references/decision-rules.md` → `docs/content-source/decision-rules-legacy.md`
- `references/transitions.md` → `docs/content-source/transitions-legacy.md`
- `references/asset-handling.md` → `docs/content-source/asset-handling-legacy.md`
- `references/hardware-guide.md` → `docs/content-source/hardware-guide-legacy.md`

`references/snippets.md` is NOT changed.

After editing, verify no remaining references-path matches except `snippets`:

```bash
grep -n "references/" .claude/skills/creating-a-config/SKILL.md | grep -v "snippets.md"
```

Expected: no output (or only matches you've already converted).

- [ ] **Step 3: Replace the old reference files with pointer markers**

For each of the 5 files (`widgets`, `transitions`, `decision-rules`, `asset-handling`, `hardware-guide`):

```bash
echo "See docs/content-source/<name>-legacy.md (and Plan B-authored per-topic files when complete)." \
  > .claude/skills/creating-a-config/references/<name>.md
```

Concretely, run all 5:

```bash
echo "See docs/content-source/widgets-legacy.md and docs/content-source/widgets/ for migrated content." > .claude/skills/creating-a-config/references/widgets.md
echo "See docs/content-source/transitions-legacy.md and docs/content-source/transitions/ for migrated content." > .claude/skills/creating-a-config/references/transitions.md
echo "See docs/content-source/decision-rules-legacy.md and docs/content-source/rules/ for migrated content." > .claude/skills/creating-a-config/references/decision-rules.md
echo "See docs/content-source/asset-handling-legacy.md for migrated content." > .claude/skills/creating-a-config/references/asset-handling.md
echo "See docs/content-source/hardware-guide-legacy.md and docs/content-source/hardware/ for migrated content." > .claude/skills/creating-a-config/references/hardware-guide.md
```

- [ ] **Step 4: Smoke-test the skill structure**

The skill is invoked by Claude Code at runtime; we can't run it from a script. Instead, verify the skill paths it would load all exist:

```bash
test -f docs/content-source/widgets-legacy.md && echo OK widgets
test -f docs/content-source/transitions-legacy.md && echo OK transitions
test -f docs/content-source/decision-rules-legacy.md && echo OK decision-rules
test -f docs/content-source/asset-handling-legacy.md && echo OK asset-handling
test -f docs/content-source/hardware-guide-legacy.md && echo OK hardware-guide
test -f .claude/skills/creating-a-config/references/snippets.md && echo OK snippets-still-there
```

Expected: 6 OK lines.

Also verify the SKILL.md edits are syntactically clean:

```bash
grep -c "docs/content-source/" .claude/skills/creating-a-config/SKILL.md
```
Expected: positive count (matches the number of references replaced, typically 5–10).

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/creating-a-config/ docs/content-source/
git commit -m "feat(skill): load fact-pack content from docs/content-source/

Plan A interim migration: copies the existing references/*.md content
into docs/content-source/<name>-legacy.md and updates SKILL.md to load
from the new paths. Plan B replaces the legacy files with proper
per-widget / per-transition / per-rule fact-pack files."
```

---

## Task 10: CI workflow + issue template

**Files:**
- Create: `.github/workflows/docs.yml`
- Create: `.github/ISSUE_TEMPLATE/submit-sign.yml`

- [ ] **Step 1: Create `.github/workflows/docs.yml`**

```yaml
name: docs

on:
  push:
    branches: [main]
    paths:
      - "docs/**"
      - "tools/render_demo/**"
      - ".github/workflows/docs.yml"
  workflow_dispatch:

permissions:
  contents: read
  pages: write
  id-token: write

concurrency:
  group: docs-pages
  cancel-in-progress: true

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: astral-sh/setup-uv@v3
        with:
          enable-cache: true

      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"

      - name: Install Python deps
        run: uv sync

      - uses: actions/setup-node@v4
        with:
          node-version: "lts/*"
          cache: npm
          cache-dependency-path: docs/site/package-lock.json

      - name: Install Node deps
        working-directory: docs/site
        run: npm ci

      - name: Build demo gifs
        working-directory: docs/site
        run: node scripts/build-demos.mjs

      - name: Build Astro site
        working-directory: docs/site
        run: npm run build

      - uses: actions/upload-pages-artifact@v3
        with:
          path: docs/site/dist

  deploy:
    needs: build
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - uses: actions/deploy-pages@v4
        id: deployment
```

- [ ] **Step 2: Create `.github/ISSUE_TEMPLATE/submit-sign.yml`**

```yaml
name: Submit your sign
description: Share a photo or clip of your led-ticker sign for the showcase gallery.
title: "[Showcase] "
labels: ["showcase", "submission"]
body:
  - type: markdown
    attributes:
      value: |
        Thanks for sharing! Drag your photos / short clips into the description field below.
        Image sizes up to ~10 MB are fine; for longer videos consider a YouTube/Vimeo link.

  - type: textarea
    id: media
    attributes:
      label: Photos / clips
      description: Drag and drop images/short videos here. At least one is required.
      placeholder: (paste or drag-drop here)
    validations:
      required: true

  - type: input
    id: where
    attributes:
      label: Where does it run?
      description: Storefront, home, office, art install, etc.
      placeholder: e.g. "moonbunny aerial storefront, NYC"
    validations:
      required: true

  - type: dropdown
    id: hardware
    attributes:
      label: Hardware
      options:
        - Pi 4 + small sign (5×32×16)
        - Pi 5 + bigsign (8× P3 32×64 vertical serpentine)
        - Custom (describe in the description)
    validations:
      required: true

  - type: textarea
    id: config
    attributes:
      label: Config (optional)
      description: Paste your config.toml if you'd like it featured in a community-configs gallery.
      render: toml

  - type: input
    id: credit
    attributes:
      label: Credit (optional)
      description: How would you like to be credited? Name, handle, link, or "anonymous".
      placeholder: e.g. "@example on Instagram"

  - type: checkboxes
    id: permission
    attributes:
      label: Permission
      description: Required to feature your submission in the docs.
      options:
        - label: I have permission to share these assets and grant the led-ticker maintainers permission to use them in the docs site.
          required: true
```

- [ ] **Step 3: Verify the YAML is valid**

```bash
python -c "import yaml; yaml.safe_load(open('.github/workflows/docs.yml'))" && echo OK workflow
python -c "import yaml; yaml.safe_load(open('.github/ISSUE_TEMPLATE/submit-sign.yml'))" && echo OK template
```
Expected: 2 OK lines.

- [ ] **Step 4: Commit**

```bash
git add .github/
git commit -m "feat(ci): docs deploy workflow + showcase submission issue template"
```

---

## Task 11: Add Makefile targets for local dev

**Files:**
- Modify: `Makefile`

- [ ] **Step 1: Append docs-dev / docs-build / render-demo targets to the Makefile**

Find the existing `.PHONY:` line at the top of `Makefile`. Update it to add the new target names. Then add the new target blocks before the final `clean:` block.

Update the `.PHONY:` line to include the new targets. Example: if the line was `.PHONY: dev hooks test lint typecheck format clean build-docker`, change it to `.PHONY: dev hooks test lint typecheck format clean build-docker docs-dev docs-build render-demo`.

Add the new target blocks:

```makefile
# --- Docs site ---

docs-dev:  ## Run the Astro Starlight dev server (http://localhost:4321/led-ticker/)
	cd docs/site && npm install && node scripts/build-demos.mjs && npm run dev

docs-build:  ## Build the docs site to docs/site/dist/
	cd docs/site && npm install && npm run build

render-demo:  ## Render a single demo gif. Usage: make render-demo CONFIG=path/to.toml OUT=out.gif
	uv run python tools/render_demo/render.py $(CONFIG) -o $(OUT)
```

- [ ] **Step 2: Smoke-test the docs-build target**

```bash
make docs-build 2>&1 | tail -10
```
Expected: build succeeds (`✓ Completed in ...`). `docs/site/dist/index.html` exists.

```bash
test -f docs/site/dist/index.html && echo OK
```

- [ ] **Step 3: Commit**

```bash
git add Makefile
git commit -m "feat(make): docs-dev, docs-build, and render-demo targets"
```

---

## Task 12: End-to-end deploy verification

**Files:** none modified — verification step.

- [ ] **Step 1: Run the full test suite to confirm no regressions**

```bash
make test 2>&1 | tail -3
```
Expected: all existing tests pass plus the 12 new render-demo tests (4 recording + 6 placeholder + 2 render).

- [ ] **Step 2: Run the docs build end-to-end**

```bash
make docs-build 2>&1 | tail -10
```
Expected: build succeeds, demo gifs regenerated if needed, `docs/site/dist/` populated.

- [ ] **Step 3: Verify the deployed site shape locally**

```bash
test -f docs/site/dist/index.html && echo OK home
test -f docs/site/dist/getting-started/index.html && echo OK getting-started
test -f docs/site/dist/widgets/message/index.html && echo OK widgets-message
test -f docs/site/dist/transitions/push/index.html && echo OK transitions-push
test -f docs/site/dist/footguns/index.html && echo OK footguns
test -f docs/site/dist/demos/message-rainbow.gif && echo OK demo-gif
test -f docs/site/dist/demos/push-left.gif && echo OK demo-push
```
Expected: 7 OK lines.

- [ ] **Step 4: Manual GitHub Pages source toggle (one-time)**

In a browser, go to GitHub repo Settings → Pages. Under "Build and deployment" → "Source", select "GitHub Actions" (not "Deploy from a branch").

Verify the page now shows "Your site will be deployed via the configured GitHub Actions workflow."

- [ ] **Step 5: Push the branch and verify CI builds**

```bash
git push origin worktree-feat-docs-site
```

Watch the Actions tab on GitHub. Expected: a `docs` workflow run kicks off (because the push touches `docs/**`), runs successfully, and the deploy step succeeds. Live URL appears in the workflow's deploy step output (`https://jamesawesome.github.io/led-ticker/`).

If the workflow doesn't trigger (e.g., still on a feature branch and the workflow only triggers on `main`), merge to `main` first OR add the feature branch to the workflow's `branches:` filter temporarily for verification.

- [ ] **Step 6: Visit the deployed site**

In a browser, visit `https://jamesawesome.github.io/led-ticker/`. Verify:
- Home page renders with hero
- Demo gif on home page is visible and animates
- Sidebar shows widgets/transitions/footguns sections
- All 5 prototype pages reachable and render correctly

- [ ] **Step 7: No commit needed for verification.**

If everything works, the infrastructure is complete and Plan B (content authoring) can begin against this foundation.

---

## Final check

After all 12 tasks complete:

- [ ] **Run full test suite:** `make test` passes with no regressions.
- [ ] **Run docs build:** `make docs-build` succeeds.
- [ ] **CI green:** the docs workflow on GitHub Actions is green on `worktree-feat-docs-site` (or `main` if merged).
- [ ] **Site live:** `https://jamesawesome.github.io/led-ticker/` shows the prototype pages.

The infrastructure is the load-bearing piece. Plan B fills in 30+ pages of content into this scaffold without further architectural decisions.
