# Hi-res Fonts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add opt-in TTF/OTF font rendering at native physical resolution, with bundled Inter (OFL) and a path for user-supplied Beloved Sans (Adobe Fonts).

**Architecture:** Extend `text_render.draw_text` to dispatch on font type. Hi-res fonts are pre-rasterized via `PIL.ImageFont` into per-glyph bitmaps (50%-threshold binarized for crisp LED rendering), cached via `@functools.cache` per (name, size). Render path paints to the unwrapped real canvas, bypassing the wrapper's 4×4 block expansion. Font name resolution scans `config/fonts/` first (user-supplied), then `src/led_ticker/fonts/hires/` (bundled), then falls back to BDF. Per-widget TOML knobs `font` + `font_size` resolve at config load via `app._build_widget`.

**Tech Stack:** Python 3.13, Pillow `ImageFont` (already a dep), pytest, attrs, hatchling.

---

## File Structure

**New files:**
- `src/led_ticker/fonts/hires/Inter-Regular.otf` — bundled OFL font (downloaded from rsms.me/inter v4.0).
- `src/led_ticker/fonts/hires/Inter-Bold.otf` — bundled OFL font.
- `src/led_ticker/fonts/hires_loader.py` — `HiresGlyph`, `HiresFont` dataclasses; `_find_font_path`, `_rasterize_glyph`, `_rasterize`, `load_hires_font` (cached), `list_available_hires_fonts`, `EXTENDED_LATIN` constant, `THRESHOLD` constant.

**Modified files:**
- `src/led_ticker/fonts/__init__.py` — add `resolve_font`, `list_available_fonts`, `UnknownFontError`, `font_line_height`, `DEFAULT_HIRES_SIZE` constant.
- `src/led_ticker/text_render.py` — add `_draw_hires_text`, dispatch on `isinstance(font, HiresFont)` in `draw_text`.
- `src/led_ticker/drawing.py` — `get_text_width` dispatches on font type.
- `src/led_ticker/pixel_emoji.py` — `measure_width` and `draw_with_emoji` use `font_line_height(font)` for default `emoji_y`.
- `src/led_ticker/app.py` — `_build_widget` pops `font` + `font_size`, calls `resolve_font`.
- `src/led_ticker/_types.py` — comment update on `Font` (denoting it now polymorphic).
- `.gitignore` — add `config/fonts/`.
- `CLAUDE.md` — document the hi-res font system + resolution chain.

**New tests:**
- `tests/test_hires_font_loader.py` — registry, rasterization, cache, threshold, BDF fallback, errors.
- Extensions to `tests/test_text_render.py`, `tests/test_drawing.py`, `tests/test_pixel_emoji.py`, `tests/test_app.py`.

---

## Conventions for this plan

- Hi-res font files are checked into the repo at `src/led_ticker/fonts/hires/`. Hatchling's default include behavior bundles them in the wheel (verified in Task 1).
- Tests use bundled `Inter-Regular.otf` as the canonical hi-res asset. Synthetic-font fixtures aren't worth the complexity.
- The `_StubCanvas` from `tests/stubs/rgbmatrix/__init__.py` supports `SetPixel` / `Clear` / `Fill` / `get_pixel` — adequate for pixel-level assertions.
- `Color` for tests is `from rgbmatrix.graphics import Color`.
- `unwrap_to_real(canvas)` lives at `led_ticker.scaled_canvas:106`.
- The conftest `canvas` fixture is a `Mock` — most existing tests rely on that. New pixel-level tests construct a real `_StubCanvas` via `RGBMatrix(options=opts).CreateFrameCanvas()`.

---

### Task 1: Bundle Inter assets + gitignore config/fonts + wheel verification

**Files:**
- Create: `src/led_ticker/fonts/hires/Inter-Regular.otf`
- Create: `src/led_ticker/fonts/hires/Inter-Bold.otf`
- Modify: `.gitignore`
- Test: none — pure asset task with verification

- [ ] **Step 1: Download Inter v4.0 release zip and extract Regular + Bold .otf**

```bash
mkdir -p src/led_ticker/fonts/hires
curl -L -o /tmp/inter.zip https://github.com/rsms/inter/releases/download/v4.0/Inter-4.0.zip
unzip -l /tmp/inter.zip | grep -E 'Inter-(Regular|Bold)\.otf' | head
```

The zip layout has a top-level `Inter Desktop/` dir containing all .otf weights. Extract the two we need:

```bash
unzip -j /tmp/inter.zip 'Inter Desktop/Inter-Regular.otf' 'Inter Desktop/Inter-Bold.otf' -d src/led_ticker/fonts/hires/
ls -la src/led_ticker/fonts/hires/
```

If the zip's internal layout differs, adjust the `unzip -j` paths. Both files should land directly in `src/led_ticker/fonts/hires/` with no nested directories.

- [ ] **Step 2: Verify the .otf files are valid and Pillow can load them**

```bash
PYTHONPATH=tests/stubs uv run python -c "
from PIL import ImageFont
for name in ('Inter-Regular.otf', 'Inter-Bold.otf'):
    p = f'src/led_ticker/fonts/hires/{name}'
    f = ImageFont.truetype(p, 32)
    print(f'{name}: ascent={f.getmetrics()[0]} descent={f.getmetrics()[1]} M-width={int(f.getlength(\"M\"))}')
"
```

Expected: both files load. Inter Regular at size=32 should report ascent ≈ 30, descent ≈ 8 (give or take a few px depending on font version).

- [ ] **Step 3: Add `config/fonts/` to .gitignore**

In `.gitignore`, find the section about `config/config.toml` (around line 145-148) and add `config/fonts/` immediately after:

```
config/config.toml
config/fonts/
.vscode/
.superpowers/
```

- [ ] **Step 4: Verify hatchling will include sprites in the wheel**

```bash
uv build --wheel 2>&1 | tail -3
unzip -l dist/led_ticker-2.0.0-py3-none-any.whl | grep -E 'fonts/hires/' || echo "MISSING — fonts not in wheel"
```

Expected: lines like `led_ticker/fonts/hires/Inter-Regular.otf` and `Inter-Bold.otf`. If "MISSING", add force-include to `pyproject.toml`:

```toml
[tool.hatch.build.targets.wheel.force-include]
"src/led_ticker/fonts/hires" = "led_ticker/fonts/hires"
```

Re-run `uv build --wheel` and re-verify.

- [ ] **Step 5: Clean up the test build**

```bash
rm -rf dist/
```

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/fonts/hires/ .gitignore
# Also pyproject.toml IF Step 4 required force-include
git commit -m "Bundle Inter (Regular + Bold) hi-res fonts; gitignore config/fonts/"
```

---

### Task 2: HiresGlyph + HiresFont dataclasses

**Files:**
- Create: `src/led_ticker/fonts/hires_loader.py` (just dataclasses + constants for now)
- Test: `tests/test_hires_font_loader.py` (new file)

Pure data structures. No PIL involvement yet.

- [ ] **Step 1: Create the test file with failing tests**

```python
# tests/test_hires_font_loader.py
"""Tests for the hi-res font loader."""

from __future__ import annotations


class TestHiresGlyphDataclass:
    def test_constructs_with_required_fields(self):
        from led_ticker.fonts.hires_loader import HiresGlyph

        glyph = HiresGlyph(
            width=10,
            height=20,
            advance=12,
            bearing_x=0,
            bearing_y=18,
            lit=((0, 0), (1, 1)),
        )
        assert glyph.width == 10
        assert glyph.lit == ((0, 0), (1, 1))

    def test_is_frozen(self):
        from led_ticker.fonts.hires_loader import HiresGlyph

        glyph = HiresGlyph(
            width=10, height=20, advance=12, bearing_x=0, bearing_y=18, lit=()
        )
        try:
            glyph.width = 99
        except Exception as e:  # noqa: BLE001
            assert "FrozenInstanceError" in type(e).__name__
            return
        raise AssertionError("expected FrozenInstanceError on attribute set")


class TestHiresFontDataclass:
    def test_constructs(self):
        from led_ticker.fonts.hires_loader import HiresFont, HiresGlyph

        glyph = HiresGlyph(
            width=10, height=20, advance=12, bearing_x=0, bearing_y=18, lit=()
        )
        font = HiresFont(
            name="test",
            size=32,
            ascent=30,
            descent=8,
            line_height=38,
            glyphs={"A": glyph},
        )
        assert font.name == "test"
        assert font.size == 32
        assert font.glyphs["A"] is glyph

    def test_is_frozen(self):
        from led_ticker.fonts.hires_loader import HiresFont

        font = HiresFont(
            name="t", size=8, ascent=6, descent=2, line_height=8, glyphs={}
        )
        try:
            font.size = 99
        except Exception as e:  # noqa: BLE001
            assert "FrozenInstanceError" in type(e).__name__
            return
        raise AssertionError("expected FrozenInstanceError on attribute set")


class TestThresholdConstant:
    def test_threshold_is_at_50_percent(self):
        from led_ticker.fonts.hires_loader import THRESHOLD

        # 50% of 0-255 ≈ 128
        assert THRESHOLD == 128
```

- [ ] **Step 2: Run tests, verify failure**

Run: `make test ARGS="tests/test_hires_font_loader.py -v"`
Expected: FAIL — `ModuleNotFoundError: No module named 'led_ticker.fonts.hires_loader'`.

- [ ] **Step 3: Create `hires_loader.py` with dataclasses + constants only**

```python
# src/led_ticker/fonts/hires_loader.py
"""Hi-res TTF/OTF font loader, glyph rasterizer, and cache.

Bundled fonts live at `src/led_ticker/fonts/hires/`. User-supplied
fonts (e.g. licensed Adobe Fonts) live at `config/fonts/` (gitignored).

`load_hires_font(name, size)` resolves a name through both dirs,
rasterizes glyphs once via Pillow, thresholds them to a 1-bit mask
at 50% intensity, and returns a frozen `HiresFont` cached forever.

The renderer (`text_render._draw_hires_text`) then paints lit pixels
directly to the unwrapped real canvas at native physical resolution.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# 50% of 0-255 — pixels at or above this are "on" after rasterization.
# Higher = thicker strokes; lower = thinner. 128 matches the natural
# midpoint and produces clean glyphs at 24-32px on a 64-row LED panel.
THRESHOLD: int = 128

# Most common Latin-1 accented characters. Pre-rasterized along with
# string.printable so widgets handling European-language feeds (Spanish,
# French, German, etc) render correctly. Other characters fall back to
# the '?' glyph at render time.
EXTENDED_LATIN: str = (
    "àáâãäåæçèéêëìíîïñòóôõöøùúûüýÿ"
    "ÀÁÂÃÄÅÆÇÈÉÊËÌÍÎÏÑÒÓÔÕÖØÙÚÛÜÝŸ"
)


@dataclass(frozen=True)
class HiresGlyph:
    """Rasterized glyph at a specific size, post-threshold.

    Coordinates are RELATIVE to the glyph's bbox: `(0, 0)` is the
    top-left of the bbox, NOT the canvas. The renderer adds the
    glyph's `bearing_x` / `bearing_y` to position relative to the
    cursor + baseline.
    """

    width: int
    height: int
    advance: int
    bearing_x: int
    bearing_y: int
    lit: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class HiresFont:
    """A loaded TTF/OTF font at one specific pixel size.

    `glyphs` maps each rasterized character to its `HiresGlyph`.
    Characters not in `glyphs` fall back to `'?'` at render time.
    """

    name: str
    size: int
    ascent: int
    descent: int
    line_height: int
    glyphs: dict[str, HiresGlyph] = field(default_factory=dict)
```

- [ ] **Step 4: Run tests, verify pass**

Run: `make test ARGS="tests/test_hires_font_loader.py -v"`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/fonts/hires_loader.py tests/test_hires_font_loader.py
git commit -m "Add HiresGlyph + HiresFont dataclasses and constants"
```

---

### Task 3: Glyph rasterization + load_hires_font + path discovery

**Files:**
- Modify: `src/led_ticker/fonts/hires_loader.py` (extend)
- Test: `tests/test_hires_font_loader.py` (extend)

Add `_find_font_path`, `_rasterize_glyph`, `_rasterize`, and `load_hires_font`.

- [ ] **Step 1: Add failing tests for rasterization + cache + discovery**

Append to `tests/test_hires_font_loader.py`:

```python
import pytest


@pytest.fixture(autouse=True)
def _clear_loader_cache():
    """Clear @functools.cache between tests."""
    from led_ticker.fonts.hires_loader import load_hires_font
    load_hires_font.cache_clear()
    yield
    load_hires_font.cache_clear()


class TestFindFontPath:
    def test_finds_bundled_inter_regular(self):
        from led_ticker.fonts.hires_loader import _find_font_path

        path = _find_font_path("Inter-Regular")
        assert path is not None
        assert path.name == "Inter-Regular.otf"
        assert path.is_absolute()

    def test_returns_none_for_unknown(self):
        from led_ticker.fonts.hires_loader import _find_font_path

        assert _find_font_path("definitely-not-a-font") is None

    def test_user_dir_overrides_bundled(self, tmp_path, monkeypatch):
        """If a font with the same name exists in config/fonts/ AND the
        bundled hires/ dir, the user-supplied one wins."""
        import led_ticker.fonts.hires_loader as hl

        user_dir = tmp_path / "user-fonts"
        user_dir.mkdir()
        # Drop a fake .otf with the same name as a bundled font.
        fake = user_dir / "Inter-Regular.otf"
        fake.write_bytes(b"not really a font")
        monkeypatch.setattr(hl, "USER_FONT_DIR", user_dir)

        from led_ticker.fonts.hires_loader import _find_font_path
        found = _find_font_path("Inter-Regular")
        assert found == fake


class TestLoadHiresFont:
    def test_loads_bundled_inter_regular(self):
        from led_ticker.fonts.hires_loader import load_hires_font

        font = load_hires_font("Inter-Regular", 32)
        assert font is not None
        assert font.name == "Inter-Regular"
        assert font.size == 32
        assert font.ascent > 0
        assert font.descent > 0
        assert font.line_height == font.ascent + font.descent

    def test_glyphs_for_ascii_printable(self):
        from led_ticker.fonts.hires_loader import load_hires_font

        font = load_hires_font("Inter-Regular", 32)
        assert font is not None
        for ch in "ABCabc0123!?":
            assert ch in font.glyphs, f"missing glyph for {ch!r}"

    def test_glyph_has_lit_pixels(self):
        from led_ticker.fonts.hires_loader import load_hires_font

        font = load_hires_font("Inter-Regular", 32)
        assert font is not None
        # 'M' is dense — should have many lit pixels.
        m = font.glyphs["M"]
        assert len(m.lit) > 0
        # 'M' should have more lit pixels than 'i' at the same size.
        i_glyph = font.glyphs["i"]
        assert len(m.lit) > len(i_glyph.lit)

    def test_glyph_advance_is_positive(self):
        from led_ticker.fonts.hires_loader import load_hires_font

        font = load_hires_font("Inter-Regular", 32)
        assert font is not None
        assert font.glyphs["A"].advance > 0

    def test_returns_none_for_unknown_name(self):
        from led_ticker.fonts.hires_loader import load_hires_font

        assert load_hires_font("not-a-real-font", 32) is None

    def test_caches_result(self):
        from led_ticker.fonts.hires_loader import load_hires_font

        first = load_hires_font("Inter-Regular", 24)
        second = load_hires_font("Inter-Regular", 24)
        assert first is second  # @functools.cache returns same object

    def test_different_sizes_are_different_objects(self):
        from led_ticker.fonts.hires_loader import load_hires_font

        a = load_hires_font("Inter-Regular", 24)
        b = load_hires_font("Inter-Regular", 32)
        assert a is not None and b is not None
        assert a is not b
        assert a.size == 24
        assert b.size == 32


class TestListAvailableHiresFonts:
    def test_lists_bundled_fonts(self):
        from led_ticker.fonts.hires_loader import list_available_hires_fonts

        names = list_available_hires_fonts()
        assert "Inter-Regular" in names
        assert "Inter-Bold" in names

    def test_returns_sorted(self):
        from led_ticker.fonts.hires_loader import list_available_hires_fonts

        names = list_available_hires_fonts()
        assert names == sorted(names)
```

- [ ] **Step 2: Run, verify failure**

Run: `make test ARGS="tests/test_hires_font_loader.py -v"`
Expected: FAIL on the new tests — `_find_font_path`, `load_hires_font`, etc. don't exist yet.

- [ ] **Step 3: Implement rasterization + discovery + cache**

In `src/led_ticker/fonts/hires_loader.py`, add at the top with the existing imports:

```python
import functools
import string
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont
```

Add directory constants near `THRESHOLD`:

```python
BUNDLED_HIRES_DIR: Path = Path(__file__).parent / "hires"
USER_FONT_DIR: Path = Path(__file__).parent.parent.parent.parent / "config" / "fonts"
# USER_FONT_DIR resolves to <repo_root>/config/fonts in dev. In a wheel
# install, the user's working dir matters — Path("config/fonts").resolve()
# would be relative to invocation. We re-resolve at lookup time below.
```

Add the discovery function:

```python
def _find_font_path(name: str) -> Path | None:
    """Look up a font by name across user + bundled dirs.

    User dir wins on collisions so users can override bundled fonts.
    Tries `.otf` first, then `.ttf`. Returns None if not found.
    """
    for ext in (".otf", ".ttf"):
        for base in (USER_FONT_DIR, BUNDLED_HIRES_DIR):
            candidate = base / f"{name}{ext}"
            if candidate.exists():
                return candidate.resolve()
    return None


def list_available_hires_fonts() -> list[str]:
    """Return sorted list of all hi-res font names across both dirs."""
    names: set[str] = set()
    for base in (USER_FONT_DIR, BUNDLED_HIRES_DIR):
        if not base.exists():
            continue
        for path in base.iterdir():
            if path.suffix.lower() in (".otf", ".ttf"):
                names.add(path.stem)
    return sorted(names)
```

Add the rasterizer:

```python
def _rasterize_glyph(pil_font: Any, ch: str) -> HiresGlyph:
    """Render a single character to a binarized HiresGlyph.

    Uses Pillow's `ImageFont.getbbox` to size the glyph, draws into
    a grayscale image, then thresholds to 1-bit. Lit pixel coords
    are bbox-relative (0,0 is glyph top-left).
    """
    bbox = pil_font.getbbox(ch)  # (x0, y0, x1, y1) in pixel space
    if bbox is None:
        # Whitespace or zero-width char — emit empty glyph with advance.
        advance = int(pil_font.getlength(ch))
        return HiresGlyph(
            width=0, height=0, advance=advance,
            bearing_x=0, bearing_y=0, lit=(),
        )

    width = max(1, bbox[2] - bbox[0])
    height = max(1, bbox[3] - bbox[1])
    img = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(img)
    # Offset by -bbox[0], -bbox[1] so the glyph fills the image at (0,0).
    draw.text((-bbox[0], -bbox[1]), ch, font=pil_font, fill=255)

    pixels = img.load()
    lit: list[tuple[int, int]] = []
    for dy in range(height):
        for dx in range(width):
            if pixels[dx, dy] >= THRESHOLD:
                lit.append((dx, dy))

    advance = int(pil_font.getlength(ch))
    return HiresGlyph(
        width=width,
        height=height,
        advance=advance,
        bearing_x=bbox[0],
        bearing_y=-bbox[1],  # bbox[1] is negative (above baseline) in PIL
        lit=tuple(lit),
    )


def _rasterize(path: Path, size: int, name: str) -> HiresFont:
    """Load .otf/.ttf via Pillow at `size` and rasterize all glyphs."""
    pil_font = ImageFont.truetype(str(path), size)
    ascent, descent = pil_font.getmetrics()
    chars = string.printable + EXTENDED_LATIN
    glyphs: dict[str, HiresGlyph] = {}
    for ch in chars:
        glyphs[ch] = _rasterize_glyph(pil_font, ch)
    return HiresFont(
        name=name,
        size=size,
        ascent=ascent,
        descent=descent,
        line_height=ascent + descent,
        glyphs=glyphs,
    )


@functools.cache
def load_hires_font(name: str, size: int) -> HiresFont | None:
    """Load (or fetch from cache) a hi-res font by name and pixel size."""
    path = _find_font_path(name)
    if path is None:
        return None
    return _rasterize(path, size, name)
```

- [ ] **Step 4: Run tests, verify pass**

Run: `make test ARGS="tests/test_hires_font_loader.py -v"`
Expected: PASS — all rasterization + cache + discovery tests green. Slow first-load may take ~200ms (full ASCII + extended Latin); subsequent calls are cache hits.

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/fonts/hires_loader.py tests/test_hires_font_loader.py
git commit -m "Add hi-res font rasterizer, path discovery, @functools.cache load_hires_font"
```

---

### Task 4: resolve_font + UnknownFontError + font_line_height in fonts/__init__.py

**Files:**
- Modify: `src/led_ticker/fonts/__init__.py`
- Test: `tests/test_hires_font_loader.py` (extend)

The TOML-facing layer: a single `resolve_font(name, size)` that tries hi-res → BDF → raises.

- [ ] **Step 1: Add failing tests**

Append to `tests/test_hires_font_loader.py`:

```python
class TestResolveFont:
    def test_returns_hires_for_bundled_name(self):
        from led_ticker.fonts import resolve_font
        from led_ticker.fonts.hires_loader import HiresFont

        font = resolve_font("Inter-Regular", 32)
        assert isinstance(font, HiresFont)
        assert font.size == 32

    def test_returns_bdf_for_alias_6x12(self):
        from led_ticker.fonts import FONT_DEFAULT, resolve_font

        font = resolve_font("6x12")
        # Identity check: same C font object as FONT_DEFAULT.
        assert font is FONT_DEFAULT

    def test_returns_bdf_for_alias_5x8(self):
        from led_ticker.fonts import FONT_SMALL, resolve_font

        font = resolve_font("5x8")
        assert font is FONT_SMALL

    def test_raises_for_unknown_name(self):
        from led_ticker.fonts import UnknownFontError, resolve_font

        try:
            resolve_font("totally-not-a-real-font")
        except UnknownFontError as e:
            assert "totally-not-a-real-font" in str(e)
            # Error message should list available names.
            assert "Inter-Regular" in str(e)
            assert "6x12" in str(e)
            return
        raise AssertionError("expected UnknownFontError")

    def test_default_size_used_when_size_omitted(self):
        from led_ticker.fonts import DEFAULT_HIRES_SIZE, resolve_font
        from led_ticker.fonts.hires_loader import HiresFont

        font = resolve_font("Inter-Regular")
        assert isinstance(font, HiresFont)
        assert font.size == DEFAULT_HIRES_SIZE

    def test_raises_for_size_below_8(self):
        """font_size < 8 produces unreadable glyphs — reject at resolve time."""
        from led_ticker.fonts import resolve_font

        try:
            resolve_font("Inter-Regular", 4)
        except ValueError as e:
            assert "font_size" in str(e)
            assert ">=" in str(e) or "8" in str(e)
            return
        raise AssertionError("expected ValueError for size < 8")


class TestListAvailableFonts:
    def test_includes_hires_and_bdf(self):
        from led_ticker.fonts import list_available_fonts

        names = list_available_fonts()
        assert "Inter-Regular" in names
        assert "Inter-Bold" in names
        assert "6x12" in names
        assert "5x8" in names


class TestFontLineHeight:
    def test_line_height_for_hires_font(self):
        from led_ticker.fonts import font_line_height, resolve_font

        font = resolve_font("Inter-Regular", 32)
        h = font_line_height(font)
        # Inter at 32px should have line_height around 38-40.
        assert 30 < h < 50

    def test_line_height_for_bdf_font(self):
        from led_ticker.fonts import FONT_DEFAULT, font_line_height

        # FONT_DEFAULT is 6x12 — height is 12.
        h = font_line_height(FONT_DEFAULT)
        assert h == 12

    def test_line_height_for_bdf_small_font(self):
        from led_ticker.fonts import FONT_SMALL, font_line_height

        # FONT_SMALL is 5x8 — height is 8.
        h = font_line_height(FONT_SMALL)
        assert h == 8
```

- [ ] **Step 2: Run, verify failure**

Run: `make test ARGS="tests/test_hires_font_loader.py::TestResolveFont tests/test_hires_font_loader.py::TestFontLineHeight tests/test_hires_font_loader.py::TestListAvailableFonts -v"`
Expected: FAIL — `resolve_font`, `UnknownFontError`, `DEFAULT_HIRES_SIZE`, `list_available_fonts`, `font_line_height` don't exist yet.

- [ ] **Step 3: Extend `fonts/__init__.py`**

In `src/led_ticker/fonts/__init__.py`, append after the existing FONT_* exports:

```python
from led_ticker.fonts.hires_loader import (
    HiresFont,
    list_available_hires_fonts,
    load_hires_font,
)

# Default size when TOML specifies `font = "..."` without `font_size`.
# 24 pixels is a reasonable "body text" size on a 64-row bigsign panel.
DEFAULT_HIRES_SIZE: int = 24

# Map from BDF "alias name" (used in TOML) to the loaded C font object.
# These names match the .bdf filename stems for consistency.
_BDF_ALIASES: dict[str, Font] = {
    "6x12": FONT_DEFAULT,
    "5x8": FONT_SMALL,
    "7x13": FONT_LABEL,
    "6x10": FONT_DELTA,
}


class UnknownFontError(ValueError):
    """Raised when a TOML font name resolves to nothing.

    The message lists all known fonts so the user can fix typos.
    """


def resolve_font(name: str, size: int = DEFAULT_HIRES_SIZE) -> Font | HiresFont:
    """Resolve a TOML font name to a loaded font object.

    Resolution order:
      1. Hi-res fonts (config/fonts/ overrides bundled fonts/hires/).
      2. BDF aliases (`6x12`, `5x8`, etc.).
      3. Raise `UnknownFontError`.

    `size` is only meaningful for hi-res fonts; BDF aliases ignore it.
    Raises `ValueError` if `size < 8` (glyphs unreadable below that).
    """
    if size < 8:
        raise ValueError(
            f"font_size must be >= 8 for legible rendering; got {size}"
        )
    hires = load_hires_font(name, size)
    if hires is not None:
        return hires
    if name in _BDF_ALIASES:
        return _BDF_ALIASES[name]
    available = list_available_fonts()
    raise UnknownFontError(
        f"unknown font {name!r}; available: {available}"
    )


def list_available_fonts() -> list[str]:
    """Sorted list of all font names: hi-res + BDF aliases."""
    names = set(list_available_hires_fonts())
    names.update(_BDF_ALIASES.keys())
    return sorted(names)


def font_line_height(font: Font | HiresFont) -> int:
    """Return the font's line height in logical pixels.

    For BDF fonts: the .bdf file's PIXEL_SIZE / FONTBOUNDINGBOX height.
    For HiresFont: `ascent + descent` from the loaded TTF metrics.

    Used by `pixel_emoji` to position emoji icons relative to the font's
    natural cell, instead of hardcoded 12-row BDF assumptions.
    """
    if isinstance(font, HiresFont):
        return font.line_height
    # BDF path: font.height() is the C bitmap height attribute.
    return font.height()
```

NOTE: the `font.height()` attribute on the C BDF font — verify it exists. The rgbmatrix `Font` C extension exposes `font.height()` (a method, not a property). If your Pillow stub or rgbmatrix version uses a different name, adapt. Looking at `src/led_ticker/widgets/_image_base.py:208` and similar sites in the codebase confirms the pattern.

- [ ] **Step 4: Run tests, verify pass**

Run: `make test ARGS="tests/test_hires_font_loader.py -v"`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/fonts/__init__.py tests/test_hires_font_loader.py
git commit -m "Add resolve_font + font_line_height + UnknownFontError"
```

---

### Task 5: _draw_hires_text + dispatch in text_render

**Files:**
- Modify: `src/led_ticker/text_render.py`
- Test: `tests/test_text_render.py` (extend)

The render path. Hi-res text bypasses the wrapper to paint at native pixels.

- [ ] **Step 1: Add failing tests**

If `tests/test_text_render.py` doesn't exist yet, create it. Otherwise append:

```python
"""Tests for the unified text rendering helper."""

from __future__ import annotations

import unittest.mock as mock_mod

import pytest


class TestDrawTextDispatch:
    def test_bdf_font_with_mock_canvas_uses_graphics_DrawText(self):
        """Real C canvas (Mock proxy) goes through graphics.DrawText."""
        from led_ticker.fonts import FONT_DEFAULT
        from led_ticker.text_render import draw_text

        canvas = mock_mod.MagicMock()
        with mock_mod.patch("led_ticker.text_render._graphics") as gfx:
            gfx.DrawText.return_value = 42
            result = draw_text(canvas, FONT_DEFAULT, 0, 12, "color", "hi")
            gfx.DrawText.assert_called_once()
            assert result == 42

    def test_hires_font_dispatches_to_hires_path(self):
        """HiresFont triggers _draw_hires_text, NOT graphics.DrawText."""
        from led_ticker.fonts import resolve_font
        from led_ticker.text_render import draw_text
        from rgbmatrix import RGBMatrix, RGBMatrixOptions
        from rgbmatrix.graphics import Color
        from led_ticker.scaled_canvas import ScaledCanvas

        font = resolve_font("Inter-Regular", 24)

        opts = RGBMatrixOptions()
        opts.cols = 256
        opts.rows = 64
        opts.chain_length = 1
        opts.parallel = 1
        real = RGBMatrix(options=opts).CreateFrameCanvas()
        wrapped = ScaledCanvas(real, scale=4, content_height=16)

        with mock_mod.patch("led_ticker.text_render._graphics") as gfx:
            draw_text(wrapped, font, 0, 12, Color(255, 255, 255), "Hi")
            gfx.DrawText.assert_not_called()

        # The hires path paints to the REAL canvas at native pixels.
        # Lit pixel count should be > 0 (we drew "Hi" at 24px).
        lit = sum(
            1
            for y in range(real.height)
            for x in range(real.width)
            if real.get_pixel(x, y) != (0, 0, 0)
        )
        assert lit > 0


class TestDrawHiresText:
    def _setup_canvas(self, scale=4, content_height=16):
        from led_ticker.scaled_canvas import ScaledCanvas
        from rgbmatrix import RGBMatrix, RGBMatrixOptions

        opts = RGBMatrixOptions()
        opts.cols = 256
        opts.rows = 64
        opts.chain_length = 1
        opts.parallel = 1
        real = RGBMatrix(options=opts).CreateFrameCanvas()
        wrapped = ScaledCanvas(real, scale=scale, content_height=content_height)
        return real, wrapped

    def test_paints_to_unwrapped_real_canvas(self):
        """Hires text bypasses the wrapper's 4×4 block expansion."""
        from led_ticker.fonts import resolve_font
        from led_ticker.text_render import draw_text
        from rgbmatrix.graphics import Color

        real, wrapped = self._setup_canvas()
        font = resolve_font("Inter-Regular", 24)
        draw_text(wrapped, font, 0, 12, Color(255, 0, 0), "M")

        # Find lit red pixels and confirm they're NOT block-expanded
        # (i.e., not arranged in 4×4 grids of identical color).
        lit = [
            (x, y)
            for y in range(real.height)
            for x in range(real.width)
            if real.get_pixel(x, y) == (255, 0, 0)
        ]
        assert len(lit) > 10  # 'M' at 24px has many pixels

        # Native rendering has lit pixels at non-multiple-of-4 coords.
        # Block-expanded rendering would have lit only at x % 4 == 0
        # boundaries with each lit pixel filling a 4x4 region.
        non_block_aligned = sum(1 for x, _ in lit if x % 4 != 0)
        assert non_block_aligned > 0, "looks block-expanded — hires path didn't bypass wrapper"

    def test_returns_advance_width(self):
        from led_ticker.fonts import resolve_font
        from led_ticker.text_render import draw_text
        from rgbmatrix.graphics import Color

        _, wrapped = self._setup_canvas()
        font = resolve_font("Inter-Regular", 24)
        advance = draw_text(wrapped, font, 0, 12, Color(0, 255, 0), "ABC")
        # Three glyphs at 24px should advance ~30-50 real pixels total.
        assert advance > 0
        assert advance < 200  # not absurdly wide

    def test_clips_x_out_of_panel(self):
        """Glyph painted off the right edge clips silently (no crash)."""
        from led_ticker.fonts import resolve_font
        from led_ticker.text_render import draw_text
        from rgbmatrix.graphics import Color

        real, wrapped = self._setup_canvas()
        font = resolve_font("Inter-Regular", 24)
        # logical x=1000 → real x=4000 (past 256 panel_w).
        draw_text(wrapped, font, 1000, 12, Color(0, 0, 255), "ABC")
        # No pixels lit anywhere on the panel.
        for y in range(real.height):
            for x in range(real.width):
                assert real.get_pixel(x, y) == (0, 0, 0)

    def test_unknown_char_falls_back_to_question_mark(self):
        """Characters not in the rasterized set use the '?' glyph."""
        from led_ticker.fonts import resolve_font
        from led_ticker.text_render import draw_text
        from rgbmatrix.graphics import Color

        real, wrapped = self._setup_canvas()
        font = resolve_font("Inter-Regular", 24)
        # 'Ω' isn't in EXTENDED_LATIN — should render as '?'.
        draw_text(wrapped, font, 10, 12, Color(255, 255, 255), "Ω")
        lit = sum(
            1
            for y in range(real.height)
            for x in range(real.width)
            if real.get_pixel(x, y) == (255, 255, 255)
        )
        # '?' has fewer pixels than Inter's 'Ω' glyph would have, but
        # both are non-empty. Just assert SOMETHING was painted.
        assert lit > 0
```

- [ ] **Step 2: Run, verify failure**

Run: `make test ARGS="tests/test_text_render.py -v"`
Expected: FAIL — hi-res dispatch doesn't exist; `_draw_hires_text` undefined.

- [ ] **Step 3: Extend `text_render.py`**

Replace the contents of `src/led_ticker/text_render.py`:

```python
"""Unified text-drawing helper that picks the right rendering path.

For a real `RGBMatrix` canvas (existing sign), forwards to `graphics.DrawText`
unchanged. For a `ScaledCanvas` (bigsign at scale > 1), uses the pure-Python
BDF rasterizer. For a `HiresFont`, uses the per-glyph hi-res renderer
that paints to the unwrapped real canvas at native physical resolution.
"""

from __future__ import annotations

from typing import Any

from led_ticker._compat import require_graphics
from led_ticker.fonts import get_bdf_for
from led_ticker.fonts.hires_loader import HiresFont
from led_ticker.scaled_canvas import ScaledCanvas, unwrap_to_real

_graphics = require_graphics()


def draw_text(canvas: Any, font: Any, x: int, y: int, color: Any, text: str) -> int:
    """Draw `text` at (x, y) baseline. Returns total advance width."""
    if isinstance(font, HiresFont):
        return _draw_hires_text(canvas, font, x, y, color, text)
    if isinstance(canvas, ScaledCanvas):
        bdf = get_bdf_for(font)
        return canvas.draw_bdf_text(bdf, x, y, color, text)
    return _graphics.DrawText(canvas, font, x, y, color, text)


def _draw_hires_text(
    canvas: Any, font: HiresFont, x: int, y: int, color: Any, text: str
) -> int:
    """Paint hi-res glyphs at native physical resolution.

    `(x, y)` are LOGICAL coords (consistent with BDF callers). The
    renderer multiplies by canvas scale (and adds the wrapper's
    y-offset) to get real pixel coords, then paints glyph pixels
    directly to the unwrapped real canvas — bypasses the wrapper's
    4×4 block expansion. Out-of-bounds pixels clip silently.
    """
    real = unwrap_to_real(canvas)
    scale = getattr(canvas, "scale", 1)
    y_offset = getattr(canvas, "_y_offset", 0)
    real_baseline_y = y * scale + y_offset
    real_x = x * scale

    set_px = real.SetPixel
    panel_w = real.width
    panel_h = real.height
    r, g, b = color.red, color.green, color.blue

    cursor_x = real_x
    fallback = font.glyphs.get("?")
    for ch in text:
        glyph = font.glyphs.get(ch, fallback)
        if glyph is None:
            continue
        gx0 = cursor_x + glyph.bearing_x
        gy0 = real_baseline_y - glyph.bearing_y
        for dx, dy in glyph.lit:
            px = gx0 + dx
            py = gy0 + dy
            if 0 <= px < panel_w and 0 <= py < panel_h:
                set_px(px, py, r, g, b)
        cursor_x += glyph.advance
    return cursor_x - real_x
```

- [ ] **Step 4: Run tests, verify pass**

Run: `make test ARGS="tests/test_text_render.py -v"`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/text_render.py tests/test_text_render.py
git commit -m "Add _draw_hires_text + HiresFont dispatch in draw_text"
```

---

### Task 6: get_text_width polymorphism

**Files:**
- Modify: `src/led_ticker/drawing.py`
- Test: `tests/test_drawing.py`

`get_text_width` currently calls `font.CharacterWidth(ord(c))` which only works for BDF C fonts. Extend to handle HiresFont.

- [ ] **Step 1: Add failing tests**

Append to `tests/test_drawing.py`:

```python
class TestGetTextWidthHiresFont:
    def test_hires_font_sums_advances(self):
        from led_ticker.drawing import get_text_width
        from led_ticker.fonts import resolve_font

        font = resolve_font("Inter-Regular", 24)
        width = get_text_width(font, "ABC", padding=0)
        # Sum of glyph advances for A, B, C — should be positive.
        assert width > 0
        # And consistent: same call returns same result.
        assert get_text_width(font, "ABC", padding=0) == width

    def test_hires_font_padding_added(self):
        from led_ticker.drawing import get_text_width
        from led_ticker.fonts import resolve_font

        font = resolve_font("Inter-Regular", 24)
        no_pad = get_text_width(font, "X", padding=0)
        with_pad = get_text_width(font, "X", padding=6)
        assert with_pad == no_pad + 6

    def test_hires_font_empty_string(self):
        from led_ticker.drawing import get_text_width
        from led_ticker.fonts import resolve_font

        font = resolve_font("Inter-Regular", 24)
        assert get_text_width(font, "", padding=0) == 0

    def test_hires_font_unknown_char_uses_fallback(self):
        from led_ticker.drawing import get_text_width
        from led_ticker.fonts import resolve_font

        font = resolve_font("Inter-Regular", 24)
        # 'Ω' not in rasterized set — uses '?' advance.
        omega_width = get_text_width(font, "Ω", padding=0)
        question_width = get_text_width(font, "?", padding=0)
        assert omega_width == question_width

    def test_bdf_font_path_unchanged(self):
        """Existing BDF behavior preserved."""
        from led_ticker.drawing import get_text_width
        from led_ticker.fonts import FONT_DEFAULT

        # FONT_DEFAULT is 6×12 — 'A' is 6 wide.
        width = get_text_width(FONT_DEFAULT, "A", padding=0)
        assert width == 6
```

- [ ] **Step 2: Run, verify failure**

Run: `make test ARGS="tests/test_drawing.py::TestGetTextWidthHiresFont -v"`
Expected: FAIL — hi-res font doesn't have `CharacterWidth` method, AttributeError or similar.

- [ ] **Step 3: Update `get_text_width`**

In `src/led_ticker/drawing.py`, replace the existing `get_text_width`:

```python
def get_text_width(font: Any, text: str, padding: int = 6) -> int:
    """Get the pixel width of rendered text plus padding.

    Dispatches on font type: HiresFont sums glyph advances (with `?`
    fallback for unknown chars); BDF C font uses `CharacterWidth(ord(c))`
    as before.
    """
    from led_ticker.fonts.hires_loader import HiresFont

    if isinstance(font, HiresFont):
        fallback = font.glyphs.get("?")
        fallback_advance = fallback.advance if fallback else 0
        total = sum(
            (font.glyphs.get(c, fallback).advance if font.glyphs.get(c, fallback) else fallback_advance)
            for c in text
        )
        return total + padding
    return sum(font.CharacterWidth(ord(c)) for c in text) + padding
```

NOTE: the import is inside the function to avoid a circular `drawing.py` → `fonts.hires_loader` → ... at module load. Module-top imports should also work since hires_loader doesn't import drawing, but the inline import is defensive.

- [ ] **Step 4: Run tests, verify pass**

Run: `make test ARGS="tests/test_drawing.py -v"`
Expected: PASS — all existing BDF tests + 5 new hi-res tests green.

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/drawing.py tests/test_drawing.py
git commit -m "get_text_width polymorphism: HiresFont sums glyph advances"
```

---

### Task 7: pixel_emoji emoji_y derivation update

**Files:**
- Modify: `src/led_ticker/pixel_emoji.py:2565-2620` (around `draw_with_emoji`)
- Test: `tests/test_pixel_emoji.py`

The default `emoji_y` in `draw_with_emoji` is hardcoded `4 + y_offset`, which assumes 12-tall BDF glyph cells. For hi-res fonts, derive from `font_line_height(font)` so emoji align with the larger glyphs.

- [ ] **Step 1: Add failing tests**

Append to `tests/test_pixel_emoji.py`:

```python
class TestDrawWithEmojiHiresFont:
    def test_default_emoji_y_uses_font_line_height(self):
        """When emoji_y is not specified, the default position should be
        derived from the font's line_height (centering the 8x8 sprite
        on the glyph cell), not hardcoded for BDF."""
        from led_ticker.fonts import resolve_font
        from led_ticker.pixel_emoji import draw_with_emoji
        from rgbmatrix.graphics import Color
        from led_ticker.scaled_canvas import ScaledCanvas
        from rgbmatrix import RGBMatrix, RGBMatrixOptions

        opts = RGBMatrixOptions()
        opts.cols = 256
        opts.rows = 64
        opts.chain_length = 1
        opts.parallel = 1
        real = RGBMatrix(options=opts).CreateFrameCanvas()
        wrapped = ScaledCanvas(real, scale=4, content_height=16)

        font = resolve_font("Inter-Regular", 24)
        # Should not crash; should return positive total.
        total = draw_with_emoji(
            wrapped, font, cursor_pos=10, y=12,
            color=Color(255, 255, 255),
            text=":taco: hi",
        )
        assert total > 0

    def test_measure_width_with_hires_font(self):
        """measure_width should handle hi-res fonts for non-emoji text."""
        from led_ticker.fonts import resolve_font
        from led_ticker.pixel_emoji import measure_width

        font = resolve_font("Inter-Regular", 24)
        width = measure_width(font, "hi")
        assert width > 0
```

- [ ] **Step 2: Run, verify failure (or smoke pass)**

Run: `make test ARGS="tests/test_pixel_emoji.py::TestDrawWithEmojiHiresFont -v"`
Expected: depends on existing code — `measure_width` might already work via the polymorphic `get_text_width` from Task 6. `draw_with_emoji` may crash if `iy_default = 4 + y_offset` produces a value that conflicts with hi-res text height.

If both tests pass already (the integration is "free" because the existing code is well-decoupled), skip to Step 5 with a brief commit message about adding regression coverage. If failing, proceed to Step 3.

- [ ] **Step 3: Update `pixel_emoji.draw_with_emoji` to derive default emoji_y from font height**

In `src/led_ticker/pixel_emoji.py`, find the line `iy_default = 4 + y_offset` (around line 2593) and replace:

```python
    # Default emoji_y centers the 8x8 sprite on the font's glyph cell.
    # For BDF (line_height=12), this produces iy=4 (centering 8 in 12).
    # For hi-res fonts (line_height ~32-40), the icon stays vertically
    # aligned with the (larger) text rather than floating at the BDF
    # baseline. Callers can override per-row in two_row layouts.
    from led_ticker.fonts import font_line_height
    line_h = font_line_height(font)
    iy_default = max(0, (line_h - 8) // 2) + y_offset
```

NOTE: this function is on the hot path for every text frame. The `from led_ticker.fonts import font_line_height` import cost is amortized — Python caches module imports, so this is a dict lookup after first call. If profiling shows it's a hot spot later, hoist to module top (cycle-safe since `pixel_emoji` doesn't import from `fonts.__init__`).

- [ ] **Step 4: Run tests, verify pass**

Run: `make test ARGS="tests/test_pixel_emoji.py -v"`
Expected: PASS — all existing pixel_emoji tests + 2 new hi-res tests green.

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/pixel_emoji.py tests/test_pixel_emoji.py
git commit -m "pixel_emoji emoji_y default derives from font_line_height"
```

---

### Task 8: app.py _build_widget plumbing for font + font_size

**Files:**
- Modify: `src/led_ticker/app.py:79-124` (`_build_widget`)
- Test: `tests/test_app.py`

User-facing TOML wiring: pop `font` and `font_size` from widget config, call `resolve_font`.

- [ ] **Step 1: Add failing tests**

Append to `tests/test_app.py`:

```python
class TestBuildWidgetFontResolution:
    @pytest.mark.asyncio
    async def test_hires_font_name_resolves_to_HiresFont(self):
        from led_ticker.app import _build_widget
        from led_ticker.fonts.hires_loader import HiresFont
        import aiohttp

        async with aiohttp.ClientSession() as session:
            widget_cfg = {
                "type": "message",
                "text": "hi",
                "font": "Inter-Regular",
                "font_size": 28,
            }
            widget = await _build_widget(widget_cfg, session)
        assert isinstance(widget.font, HiresFont)
        assert widget.font.size == 28

    @pytest.mark.asyncio
    async def test_bdf_alias_resolves_to_C_font(self):
        from led_ticker.app import _build_widget
        from led_ticker.fonts import FONT_DEFAULT
        import aiohttp

        async with aiohttp.ClientSession() as session:
            widget_cfg = {"type": "message", "text": "hi", "font": "6x12"}
            widget = await _build_widget(widget_cfg, session)
        assert widget.font is FONT_DEFAULT

    @pytest.mark.asyncio
    async def test_no_font_field_keeps_class_default(self):
        from led_ticker.app import _build_widget
        from led_ticker.fonts import FONT_DEFAULT
        import aiohttp

        async with aiohttp.ClientSession() as session:
            widget_cfg = {"type": "message", "text": "hi"}
            widget = await _build_widget(widget_cfg, session)
        # TickerMessage's class default is FONT_DEFAULT.
        assert widget.font is FONT_DEFAULT

    @pytest.mark.asyncio
    async def test_unknown_font_name_raises(self):
        from led_ticker.app import _build_widget
        from led_ticker.fonts import UnknownFontError
        import aiohttp

        async with aiohttp.ClientSession() as session:
            widget_cfg = {
                "type": "message",
                "text": "hi",
                "font": "totally-not-a-font",
            }
            try:
                await _build_widget(widget_cfg, session)
            except UnknownFontError as e:
                assert "totally-not-a-font" in str(e)
                return
            raise AssertionError("expected UnknownFontError")

    @pytest.mark.asyncio
    async def test_default_size_when_font_size_omitted(self):
        from led_ticker.app import _build_widget
        from led_ticker.fonts import DEFAULT_HIRES_SIZE
        from led_ticker.fonts.hires_loader import HiresFont
        import aiohttp

        async with aiohttp.ClientSession() as session:
            widget_cfg = {
                "type": "message",
                "text": "hi",
                "font": "Inter-Regular",
                # no font_size
            }
            widget = await _build_widget(widget_cfg, session)
        assert isinstance(widget.font, HiresFont)
        assert widget.font.size == DEFAULT_HIRES_SIZE
```

- [ ] **Step 2: Run, verify failure**

Run: `make test ARGS="tests/test_app.py::TestBuildWidgetFontResolution -v"`
Expected: FAIL — `_build_widget` doesn't process `font` / `font_size` keys.

- [ ] **Step 3: Update `_build_widget`**

In `src/led_ticker/app.py`, find `_build_widget` (line 79). Add font resolution BEFORE `_coerce_widget_colors`:

```python
async def _build_widget(
    widget_cfg: dict[str, Any],
    session: aiohttp.ClientSession,
    config_dir: Path | None = None,
    default_bg_color: tuple[int, int, int] | None = None,
) -> Any:
    """Instantiate a widget from its config dict."""
    widget_type = widget_cfg.pop("type")
    cls = get_widget_class(widget_type)

    # Inject section default before color coercion runs. Skip when the
    # widget already specified bg_color (widget-level wins).
    if default_bg_color is not None and "bg_color" not in widget_cfg:
        widget_cfg["bg_color"] = list(default_bg_color)

    # Resolve `font` + `font_size` into a font object before passing to
    # the widget. Hi-res fonts come from config/fonts/ or the bundled
    # hires/ dir; BDF aliases (6x12, 5x8, etc.) fall back to the C
    # bitmap fonts. Raises UnknownFontError on bogus names.
    font_name = widget_cfg.pop("font", None)
    font_size = widget_cfg.pop("font_size", None)
    if font_name is not None:
        from led_ticker.fonts import DEFAULT_HIRES_SIZE, resolve_font
        size = font_size if font_size is not None else DEFAULT_HIRES_SIZE
        widget_cfg["font"] = resolve_font(font_name, size)

    # Config uses "text" but TickerMessage/TickerCountdown use "message".
    # ... (rest of existing function unchanged)
```

The rest of `_build_widget` stays as-is. Don't touch the color coercion, presentation handling, or instantiation logic.

NOTE: `font_size` is popped to prevent it from being passed as a kwarg to widgets that don't accept it. Widgets accept a `font` kwarg (the resolved object) but never `font_size`.

- [ ] **Step 4: Run tests, verify pass**

Run: `make test ARGS="tests/test_app.py -v"`
Expected: PASS — all existing app tests + 5 new font-resolution tests green.

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/app.py tests/test_app.py
git commit -m "_build_widget resolves font + font_size kwargs via resolve_font"
```

---

### Task 9: CLAUDE.md docs + smoke test config

**Files:**
- Modify: `CLAUDE.md`
- Create: `config/config.hires_fonts_test.example.toml`
- Test: none — pure docs + config asset

- [ ] **Step 1: Add hi-res font system documentation to CLAUDE.md**

In `CLAUDE.md`, find the "Hi-res emoji on the bigsign" section (around line 83 after the recent hires-transitions edits). After that paragraph and the "Hi-res transitions on the bigsign" paragraph, add a new paragraph:

> **Hi-res fonts on the bigsign**: Widgets can opt into TTF/OTF rendering at native physical resolution by setting `font = "<name>"` and `font_size = <pixels>` in their TOML config. The loader (`fonts/hires_loader.py`) scans `config/fonts/` first (user-supplied, gitignored — for licensed fonts like Adobe's Beloved Sans), then `src/led_ticker/fonts/hires/` (bundled — currently `Inter-Regular`, `Inter-Bold`), then falls back to BDF aliases (`6x12`, `5x8`, etc.). Glyphs are rasterized via Pillow once per (font, size) pair, thresholded at 50% intensity for a clean pixel-art look (no anti-aliasing fuzz on the LED panel), and cached via `@functools.cache load_hires_font`. The render path (`text_render._draw_hires_text`) paints lit pixels directly to `unwrap_to_real(canvas).SetPixel`, bypassing the wrapper's 4×4 block expansion. `(x, y)` widget coords are still LOGICAL — the renderer multiplies by `canvas.scale` internally. Existing `get_text_width` and `pixel_emoji.draw_with_emoji` are polymorphic on font type via `isinstance(font, HiresFont)`. `font_line_height(font)` is the shared helper for vertical alignment math (replaces the hardcoded BDF cell height of 12). Widgets without `font`/`font_size` in TOML keep their class default (BDF). Hi-res rendering on the small sign is allowed but text overflows vertically — user's responsibility to pick `font_size` ≤ panel height.

- [ ] **Step 2: Create the smoke test config**

Create `config/config.hires_fonts_test.example.toml`:

```toml
# led-ticker hi-res fonts smoke test config
#
# Exercises the hi-res font path:
#   - Bundled Inter Regular + Bold at multiple sizes
#   - User-supplied Beloved Sans (drops gracefully if not present)
#   - BDF alias on the same widget surface for back-compat sanity
#
# Bigsign-only — text size assumes 64-row panel.
# Run: led-ticker --config config/config.hires_fonts_test.example.toml

[display]
rows = 32
cols = 64
chain = 8
parallel = 1
pixel_mapper = "Remap:256,64|192,32n|192,0n|128,32n|128,0n|64,32n|64,0n|0,32n|0,0n"
brightness = 60
slowdown_gpio = 3
gpio_mapping = "adafruit-hat"
default_scale = 4
pwm_bits = 8
rp1_rio = 1

[title]
delay = 2

[transitions]
default = "cut"
duration = 0.6
between_sections = "cut"

# 1. Inter Regular at 24px (default size)
[[playlist.section]]
mode = "swap"
hold_time = 3.0
loop_count = 1

  [[playlist.section.widget]]
  type = "message"
  text = "Inter 24px"
  font = "Inter-Regular"
  font_size = 24
  font_color = [255, 220, 70]

# 2. Inter Bold at 36px
[[playlist.section]]
mode = "swap"
hold_time = 3.0
loop_count = 1

  [[playlist.section.widget]]
  type = "message"
  text = "Inter Bold 36"
  font = "Inter-Bold"
  font_size = 36
  font_color = [70, 200, 255]

# 3. Inter Regular at 40px (large display)
[[playlist.section]]
mode = "swap"
hold_time = 3.0
loop_count = 1

  [[playlist.section.widget]]
  type = "message"
  text = "Inter 40px BIG"
  font = "Inter-Regular"
  font_size = 40
  font_color = [255, 100, 200]

# 4. Beloved Sans at 32px (only renders if user dropped the .otf)
# Comment out this section if you haven't downloaded Beloved Sans.
# [[playlist.section]]
# mode = "swap"
# hold_time = 3.0
# loop_count = 1
#
#   [[playlist.section.widget]]
#   type = "message"
#   text = "@MoonBunny"
#   font = "beloved-sans"
#   font_size = 32
#   font_color = [255, 220, 70]

# 5. BDF baseline (current 6x12 path) for visual comparison
[[playlist.section]]
mode = "swap"
hold_time = 3.0
loop_count = 1

  [[playlist.section.widget]]
  type = "message"
  text = "BDF 6x12 (4x scaled)"
  font = "6x12"
  font_color = [200, 200, 200]
```

- [ ] **Step 3: Verify the config parses**

```bash
PYTHONPATH=tests/stubs uv run python -c "
from led_ticker.config import load_config
from pathlib import Path
cfg = load_config(Path('config/config.hires_fonts_test.example.toml'))
for i, s in enumerate(cfg.sections):
    for w in s.widgets:
        print(f'  [{i+1}] {w.get(\"font\", \"<class default>\"):20} {w.get(\"font_size\", \"-\"):>4} {w.get(\"text\", \"\")}')
"
```

Expected output: 4 sections (Inter Regular 24, Inter Bold 36, Inter Regular 40, BDF 6x12), with the Beloved Sans section commented out.

- [ ] **Step 4: Run the full suite to confirm no regressions**

```bash
make test
```

Expected: PASS (~900+ tests, including all the new hi-res font tests from Tasks 2-8).

- [ ] **Step 5: Run lint**

```bash
make lint
```

Expected: 0 ruff warnings.

- [ ] **Step 6: Commit**

```bash
git add CLAUDE.md config/config.hires_fonts_test.example.toml
git commit -m "Document hi-res font system in CLAUDE.md + smoke test config"
```

---

## Done — final checks

After all 9 tasks land:

- [ ] `make test` — full suite green (~900+ tests).
- [ ] `make lint` — clean.
- [ ] On the bigsign Pi, run `led-ticker --config config/config.hires_fonts_test.example.toml` and visually verify Inter Regular at 24/40px and Inter Bold at 36px render with crisp curves (not block-expanded).
- [ ] Drop a Beloved Sans .otf into `config/fonts/`, uncomment section 4 of the smoke config, re-run, verify it renders.
- [ ] Confirm `config/fonts/` is gitignored: `git status` should NOT show the dropped .otf as untracked.

Optional follow-ups (NOT in this plan):
- Section-level `font` defaults that propagate to widgets (mirrors bg_color pattern). Add when repetition becomes annoying.
- Anti-aliased rendering (full intensity modulation instead of binarize). Add if user wants smoother brand text.
- Auto-sizing based on widget content_height. Add if user complains about manually picking font_size for every widget.
