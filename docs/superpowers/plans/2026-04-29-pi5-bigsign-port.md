# Pi 5 / 2×4 Bigsign Port Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port led-ticker to a Raspberry Pi 5 driving 8× P3 32×64 panels in a 2×4 serpentine layout (logical 64×256 canvas), while keeping the existing 16×160 sign working from the same `main` branch.

**Architecture:** Single codebase, config-driven. New `[display].pixel_mapper`, `[display].parallel`, `[display].default_scale` keys plus per-section `scale` override. A `ScaledCanvas` wrapper transparently scales `SetPixel` calls into `scale × scale` blocks and vertically centers the logical 16-tall canvas inside the real canvas. Pure-Python BDF rasterization replaces C-level `graphics.DrawText` when `scale > 1`. A `Region` type is plumbed for future zoned layouts but always equals the full canvas in this port.

**Tech stack:** Python 3.13, attrs/dataclasses, asyncio, hzeller `rpi-rgb-led-matrix` (Pi 4 fork or new Pi 5 fork via Docker build-arg), pytest.

**Spec:** `docs/superpowers/specs/2026-04-29-pi5-bigsign-port-design.md`

---

## File Structure

**Create:**
- `src/led_ticker/scaled_canvas.py` — `ScaledCanvas` wrapper class
- `src/led_ticker/fonts/bdf_parser.py` — `BDFFont` class with pure-Python BDF parser
- `src/led_ticker/text_render.py` — `draw_text()` helper that dispatches between `graphics.DrawText` and the BDF rasterizer
- `tests/test_scaled_canvas.py`
- `tests/test_bdf_parser.py`
- `tests/test_text_render.py`
- `config/config.bigsign.example.toml`

**Modify:**
- `src/led_ticker/drawing.py` — add `Region` dataclass
- `src/led_ticker/config.py` — add `parallel`, `pixel_mapper`, `default_scale` to `DisplayConfig`; add `scale` to `SectionConfig`
- `src/led_ticker/frame.py` — wire `parallel` from config (already has `led_pixel_mapper`)
- `src/led_ticker/app.py` — pass new config fields through to `LedFrame`
- `src/led_ticker/ticker.py` — wrap real canvas in `ScaledCanvas` when section `scale > 1`
- `src/led_ticker/widget.py` — add `region` to widget protocol docstring
- `src/led_ticker/transitions/__init__.py` — accept and forward `region` kwarg in `run_transition`
- `src/led_ticker/fonts/__init__.py` — load BDF data alongside C fonts
- `src/led_ticker/widgets/message.py`, `widgets/weather.py`, `widgets/mlb.py`, `widgets/crypto/coinbase.py`, `widgets/crypto/etherscan.py`, `presentation.py` — replace `graphics.DrawText` with `draw_text()`
- `Dockerfile` — add `RGBMATRIX_REF` build-arg
- `tests/stubs/rgbmatrix/__init__.py` — honor `parallel` and `pixel_mapper_config = "U-mapper"` for canvas size

---

## Task 1: Add `Region` dataclass to `drawing.py`

**Files:**
- Modify: `src/led_ticker/drawing.py`
- Test: `tests/test_drawing.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_drawing.py`:

```python
from led_ticker.drawing import Region


def test_region_full_canvas_defaults():
    r = Region(0, 0, 160, 16)
    assert r.x == 0
    assert r.y == 0
    assert r.width == 160
    assert r.height == 16


def test_region_subregion():
    r = Region(10, 4, 80, 8)
    assert r.x == 10
    assert r.y == 4
    assert r.width == 80
    assert r.height == 8
```

- [ ] **Step 2: Run test to verify it fails**

Run: `make test ARGS="tests/test_drawing.py -k region"` (or `pytest tests/test_drawing.py -k region -v`)
Expected: FAIL — `cannot import name 'Region'`

- [ ] **Step 3: Add `Region` to `drawing.py`**

Append to `src/led_ticker/drawing.py`:

```python
import attrs


@attrs.define(frozen=True, slots=True)
class Region:
    """A rectangular sub-area of a canvas.

    Plumbed through draw() and run_transition() for forward compatibility
    with zoned layouts. Currently always equals the full canvas.
    """
    x: int
    y: int
    width: int
    height: int
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `make test ARGS="tests/test_drawing.py -k region"`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/drawing.py tests/test_drawing.py
git commit -m "Add Region dataclass for forward-compat with zoned layouts"
```

---

## Task 2: Add `parallel`, `pixel_mapper`, `default_scale` to `DisplayConfig`; add `scale` to `SectionConfig`

**Files:**
- Modify: `src/led_ticker/config.py:14-21,35-46,89-102,113+`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_config.py`:

```python
import tomllib
from pathlib import Path

import pytest

from led_ticker.config import load_config


def test_display_config_defaults_match_existing_sign(tmp_path: Path):
    config_path = tmp_path / "config.toml"
    config_path.write_text("""
[display]
rows = 16
cols = 32
chain = 5

[[playlist.section]]
mode = "swap"
""")
    cfg = load_config(config_path)
    assert cfg.display.parallel == 1
    assert cfg.display.pixel_mapper == ""
    assert cfg.display.default_scale == 1
    assert cfg.sections[0].scale == 1


def test_display_config_bigsign_keys(tmp_path: Path):
    config_path = tmp_path / "config.toml"
    config_path.write_text("""
[display]
rows = 32
cols = 64
chain = 8
parallel = 1
pixel_mapper = "U-mapper"
default_scale = 4

[[playlist.section]]
mode = "swap"
scale = 2
""")
    cfg = load_config(config_path)
    assert cfg.display.parallel == 1
    assert cfg.display.pixel_mapper == "U-mapper"
    assert cfg.display.default_scale == 4
    assert cfg.sections[0].scale == 2


def test_section_scale_falls_back_to_default(tmp_path: Path):
    config_path = tmp_path / "config.toml"
    config_path.write_text("""
[display]
rows = 32
cols = 64
chain = 8
default_scale = 4

[[playlist.section]]
mode = "swap"
""")
    cfg = load_config(config_path)
    assert cfg.sections[0].scale == 4
```

- [ ] **Step 2: Run test to verify it fails**

Run: `make test ARGS="tests/test_config.py::test_display_config_bigsign_keys"`
Expected: FAIL — `AttributeError: 'DisplayConfig' object has no attribute 'parallel'`

- [ ] **Step 3: Add fields to dataclasses**

Edit `src/led_ticker/config.py`:

In `DisplayConfig` (after `chain`):

```python
@dataclass
class DisplayConfig:
    rows: int = 16
    cols: int = 32
    chain: int = 1
    parallel: int = 1
    pixel_mapper: str = ""
    default_scale: int = 1
    brightness: int = 100
    slowdown_gpio: int = 1
    gpio_mapping: str = "adafruit-hat"
```

In `SectionConfig` (after `continuous_scroll`):

```python
@dataclass
class SectionConfig:
    mode: str
    loop_count: int = 1
    title: dict | None = None
    widgets: list[dict] = field(default_factory=list)
    transition: TransitionConfig = field(default_factory=TransitionConfig)
    hold_time: float = 3.0
    continuous_scroll: bool = False
    scale: int = 1  # overridden in load_config when not set in TOML
```

In `load_config()`, in the `display = DisplayConfig(...)` block, add:

```python
display = DisplayConfig(
    rows=display_raw.get("rows", 16),
    cols=display_raw.get("cols", 32),
    chain=display_raw.get("chain", 1),
    parallel=display_raw.get("parallel", 1),
    pixel_mapper=display_raw.get("pixel_mapper", ""),
    default_scale=display_raw.get("default_scale", 1),
    brightness=display_raw.get("brightness", 100),
    slowdown_gpio=display_raw.get("slowdown_gpio", 1),
    gpio_mapping=display_raw.get("gpio_mapping", "adafruit-hat"),
)
```

In the per-section loop (after parsing other section fields but before appending), set scale with fallback:

```python
section = SectionConfig(
    mode=section_raw["mode"],
    # ... other fields ...
    scale=section_raw.get("scale", display.default_scale),
)
```

(Apply that pattern to wherever the `SectionConfig(...)` constructor lives.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `make test ARGS="tests/test_config.py"`
Expected: PASS (all existing config tests + new ones)

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/config.py tests/test_config.py
git commit -m "Config: add parallel/pixel_mapper/default_scale + per-section scale"
```

---

## Task 3: Wire `parallel` and `pixel_mapper` from `DisplayConfig` through `LedFrame` in `app.py`

**Files:**
- Modify: `src/led_ticker/app.py` (wherever it constructs `LedFrame`)
- Test: `tests/test_app.py` or `tests/test_frame.py`

`LedFrame` already has `led_pixel_mapper` and `led_parallel` attributes — `app.py` likely doesn't pass them through yet.

- [ ] **Step 1: Find the `LedFrame(...)` construction in `app.py`**

Run: `grep -n "LedFrame" src/led_ticker/app.py`

- [ ] **Step 2: Write the failing test**

Add to `tests/test_app.py`:

```python
from led_ticker.app import build_frame_from_config  # or however app constructs it
from led_ticker.config import DisplayConfig


def test_build_frame_passes_pixel_mapper_and_parallel():
    display = DisplayConfig(
        rows=32, cols=64, chain=8, parallel=1,
        pixel_mapper="U-mapper", default_scale=4,
    )
    frame = build_frame_from_config(display)
    assert frame.led_pixel_mapper == "U-mapper"
    assert frame.led_parallel == 1
    assert frame.led_chain == 8
```

If `app.py` doesn't expose a `build_frame_from_config` helper, refactor the inline `LedFrame(...)` call into one, and route `app.py` through it. Keep that refactor in this task.

- [ ] **Step 3: Run test to verify it fails**

Run: `make test ARGS="tests/test_app.py::test_build_frame_passes_pixel_mapper_and_parallel"`
Expected: FAIL

- [ ] **Step 4: Add `pixel_mapper`, `parallel` to the `LedFrame` construction in `app.py`**

In `app.py`, the `LedFrame(...)` call should pass through:

```python
frame = LedFrame(
    led_rows=display.rows,
    led_cols=display.cols,
    led_chain=display.chain,
    led_parallel=display.parallel,
    led_pixel_mapper=display.pixel_mapper,
    led_brightness=display.brightness,
    led_slowdown_gpio=display.slowdown_gpio,
    led_gpio_mapping=display.gpio_mapping,
)
```

- [ ] **Step 5: Run tests**

Run: `make test ARGS="tests/test_app.py tests/test_frame.py"`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/app.py tests/test_app.py
git commit -m "App: wire parallel and pixel_mapper from config to LedFrame"
```

---

## Task 4: Update test stub `RGBMatrix` to honor `parallel` and `pixel_mapper_config = "U-mapper"`

**Files:**
- Modify: `tests/stubs/rgbmatrix/__init__.py:58-72`
- Test: `tests/test_frame.py` (or new fixture test)

- [ ] **Step 1: Write the failing test**

Add to `tests/test_frame.py`:

```python
from led_ticker.frame import LedFrame


def test_stub_canvas_size_honors_u_mapper_fold():
    frame = LedFrame(
        led_rows=32,
        led_cols=64,
        led_chain=8,
        led_parallel=1,
        led_pixel_mapper="U-mapper",
    )
    canvas = frame.matrix.CreateFrameCanvas()
    # 1×8 chain folded U-mapper => 2 rows × 4 cols of panels
    # height = rows × 2, width = (cols × chain) // 2
    assert canvas.height == 64
    assert canvas.width == 256


def test_stub_canvas_size_default_no_mapper():
    frame = LedFrame(
        led_rows=16, led_cols=32, led_chain=5,
    )
    canvas = frame.matrix.CreateFrameCanvas()
    assert canvas.height == 16
    assert canvas.width == 160


def test_stub_canvas_size_parallel():
    frame = LedFrame(
        led_rows=32, led_cols=64, led_chain=4, led_parallel=2,
    )
    canvas = frame.matrix.CreateFrameCanvas()
    assert canvas.height == 64  # 32 × 2
    assert canvas.width == 256  # 64 × 4
```

- [ ] **Step 2: Run test to verify it fails**

Run: `make test ARGS="tests/test_frame.py::test_stub_canvas_size_honors_u_mapper_fold"`
Expected: FAIL — current stub gives `width=512, height=32` for U-mapper case.

- [ ] **Step 3: Update stub to compute folded size**

Edit `tests/stubs/rgbmatrix/__init__.py`, replace the `RGBMatrix.__init__` body:

```python
class RGBMatrix:
    """Stub for rgbmatrix.RGBMatrix."""

    def __init__(self, options=None):
        self._options = options
        cols = getattr(options, "cols", 64) if options else 64
        chain = getattr(options, "chain_length", 1) if options else 1
        rows = getattr(options, "rows", 32) if options else 32
        parallel = getattr(options, "parallel", 1) if options else 1
        mapper = getattr(options, "pixel_mapper_config", "") if options else ""

        width = cols * chain
        height = rows * parallel

        if mapper == "U-mapper":
            # U-mapper folds the chain in half: doubles height, halves width.
            assert chain % 2 == 0, "U-mapper requires an even chain length"
            width = (cols * chain) // 2
            height = rows * 2 * parallel

        self._width = width
        self._height = height
        self._back_buffer = None
```

- [ ] **Step 4: Run tests**

Run: `make test ARGS="tests/test_frame.py"`
Expected: PASS (existing + 3 new). All other tests should still pass too — run `make test` in full to confirm.

- [ ] **Step 5: Commit**

```bash
git add tests/stubs/rgbmatrix/__init__.py tests/test_frame.py
git commit -m "Test stub: honor parallel and U-mapper for canvas size"
```

---

## Task 5: BDF parser — minimal `BDFFont` with `glyphs` dict

**Files:**
- Create: `src/led_ticker/fonts/bdf_parser.py`
- Test: `tests/test_bdf_parser.py`

- [ ] **Step 1: Write the failing test using a synthetic 3×3 BDF**

Create `tests/test_bdf_parser.py`:

```python
import textwrap

from led_ticker.fonts.bdf_parser import BDFFont, parse_bdf


SYNTHETIC_BDF = textwrap.dedent('''\
STARTFONT 2.1
FONT -synthetic-3x3
SIZE 3 75 75
FONTBOUNDINGBOX 3 3 0 0
STARTPROPERTIES 1
FONT_ASCENT 3
ENDPROPERTIES
CHARS 1
STARTCHAR A
ENCODING 65
SWIDTH 600 0
DWIDTH 3 0
BBX 3 3 0 0
BITMAP
A0
40
A0
ENDCHAR
ENDFONT
''')


def test_parse_synthetic_bdf_glyph_count():
    font = parse_bdf(SYNTHETIC_BDF)
    assert isinstance(font, BDFFont)
    assert "A" in font.glyphs
    assert font.bbx_height == 3


def test_parse_synthetic_bdf_glyph_bitmap():
    font = parse_bdf(SYNTHETIC_BDF)
    glyph_a = font.glyphs["A"]
    # 0xA0 = 1010 0000, top 3 bits = 1, 0, 1
    # 0x40 = 0100 0000, top 3 bits = 0, 1, 0
    # 0xA0 = 1010 0000, top 3 bits = 1, 0, 1
    assert glyph_a.bitmap == [
        [True, False, True],
        [False, True, False],
        [True, False, True],
    ]
    assert glyph_a.advance_width == 3


def test_parse_synthetic_bdf_advance_width():
    font = parse_bdf(SYNTHETIC_BDF)
    assert font.glyphs["A"].advance_width == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `make test ARGS="tests/test_bdf_parser.py"`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement minimal BDF parser**

Create `src/led_ticker/fonts/bdf_parser.py`:

```python
"""Pure-Python BDF font parser for scaled rendering on the bigsign.

BDF (Bitmap Distribution Format) is a plain-text font format. We parse only
the fields we need: per-glyph bitmap, advance width, and bounding box. The
existing C font path (`graphics.DrawText`) handles `scale = 1`; this parser
backs the `scale > 1` path via `ScaledCanvas`.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class BDFGlyph:
    char: str
    bitmap: list[list[bool]]
    advance_width: int
    bbx_width: int
    bbx_height: int
    bbx_xoff: int
    bbx_yoff: int


@dataclass
class BDFFont:
    bbx_width: int
    bbx_height: int
    ascent: int
    glyphs: dict[str, BDFGlyph] = field(default_factory=dict)


def parse_bdf(text: str) -> BDFFont:
    lines = iter(text.splitlines())
    bbx_w = bbx_h = ascent = 0
    glyphs: dict[str, BDFGlyph] = {}

    for line in lines:
        parts = line.split()
        if not parts:
            continue
        key = parts[0]
        if key == "FONTBOUNDINGBOX":
            bbx_w = int(parts[1])
            bbx_h = int(parts[2])
        elif key == "FONT_ASCENT":
            ascent = int(parts[1])
        elif key == "STARTCHAR":
            glyph = _parse_glyph(lines)
            if glyph is not None:
                glyphs[glyph.char] = glyph

    return BDFFont(
        bbx_width=bbx_w, bbx_height=bbx_h, ascent=ascent, glyphs=glyphs,
    )


def _parse_glyph(lines) -> BDFGlyph | None:
    encoding: int | None = None
    advance = 0
    bbx_w = bbx_h = bbx_xoff = bbx_yoff = 0
    bitmap_rows: list[list[bool]] = []
    in_bitmap = False

    for line in lines:
        parts = line.split()
        if not parts:
            continue
        key = parts[0]
        if key == "ENCODING":
            encoding = int(parts[1])
        elif key == "DWIDTH":
            advance = int(parts[1])
        elif key == "BBX":
            bbx_w = int(parts[1])
            bbx_h = int(parts[2])
            bbx_xoff = int(parts[3])
            bbx_yoff = int(parts[4])
        elif key == "BITMAP":
            in_bitmap = True
        elif key == "ENDCHAR":
            break
        elif in_bitmap:
            row = _hex_row_to_bools(parts[0], bbx_w)
            bitmap_rows.append(row)

    if encoding is None or encoding < 0:
        return None

    char = chr(encoding)
    return BDFGlyph(
        char=char,
        bitmap=bitmap_rows,
        advance_width=advance,
        bbx_width=bbx_w,
        bbx_height=bbx_h,
        bbx_xoff=bbx_xoff,
        bbx_yoff=bbx_yoff,
    )


def _hex_row_to_bools(hex_str: str, bit_count: int) -> list[bool]:
    """Convert a hex row like 'A0' into a list of bool, MSB first, width-clipped."""
    n_hex = len(hex_str)
    value = int(hex_str, 16)
    total_bits = n_hex * 4
    bools = [(value >> (total_bits - 1 - i)) & 1 == 1 for i in range(total_bits)]
    return bools[:bit_count]
```

- [ ] **Step 4: Run tests**

Run: `make test ARGS="tests/test_bdf_parser.py"`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/fonts/bdf_parser.py tests/test_bdf_parser.py
git commit -m "Add pure-Python BDF parser for scaled-text rendering path"
```

---

## Task 6: BDF parser — load and verify a bundled font

**Files:**
- Modify: `tests/test_bdf_parser.py`

- [ ] **Step 1: Write a test against a real bundled BDF**

Add to `tests/test_bdf_parser.py`:

```python
from pathlib import Path

from led_ticker.fonts.bdf_parser import parse_bdf


FONTS_DIR = Path(__file__).resolve().parents[1] / "src" / "led_ticker" / "fonts"


def test_parse_bundled_5x8_font():
    text = (FONTS_DIR / "5x8.bdf").read_text()
    font = parse_bdf(text)
    assert "A" in font.glyphs
    assert "0" in font.glyphs
    assert " " in font.glyphs
    assert font.glyphs["A"].advance_width == 5
    assert font.glyphs["A"].bbx_height <= 8


def test_parse_bundled_7x13_font_height():
    text = (FONTS_DIR / "7x13.bdf").read_text()
    font = parse_bdf(text)
    assert font.bbx_height == 13
    assert font.glyphs["A"].advance_width == 7
```

- [ ] **Step 2: Run tests**

Run: `make test ARGS="tests/test_bdf_parser.py"`
Expected: PASS. If a glyph is missing, inspect the BDF and adjust the parser (likely whitespace/CHARS-count handling).

- [ ] **Step 3: Commit**

```bash
git add tests/test_bdf_parser.py
git commit -m "Test BDF parser against bundled 5x8 and 7x13 fonts"
```

---

## Task 7: Load BDF data alongside C fonts in `fonts/__init__.py`

**Files:**
- Modify: `src/led_ticker/fonts/__init__.py`
- Test: `tests/test_fonts.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_fonts.py`:

```python
from led_ticker.fonts import (
    FONT_DEFAULT, FONT_SMALL, FONT_LABEL, FONT_DELTA,
    get_bdf_for,
)
from led_ticker.fonts.bdf_parser import BDFFont


def test_bdf_lookup_for_each_font():
    for font in (FONT_DEFAULT, FONT_SMALL, FONT_LABEL, FONT_DELTA):
        bdf = get_bdf_for(font)
        assert isinstance(bdf, BDFFont)
        assert "A" in bdf.glyphs


def test_bdf_lookup_unknown_font_raises():
    import pytest
    with pytest.raises(KeyError):
        get_bdf_for(object())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `make test ARGS="tests/test_fonts.py"`
Expected: FAIL — `cannot import 'get_bdf_for'`.

- [ ] **Step 3: Update `fonts/__init__.py`**

Replace contents of `src/led_ticker/fonts/__init__.py`:

```python
"""Font loading for LED display with generic naming."""

from __future__ import annotations

import os

from led_ticker._compat import require_graphics
from led_ticker._types import Font
from led_ticker.fonts.bdf_parser import BDFFont, parse_bdf

_graphics = require_graphics()
FONT_DIR: str = os.path.dirname(os.path.realpath(__file__))

_BDF_BY_ID: dict[int, BDFFont] = {}


def _load_font(filename: str) -> Font:
    path = os.path.join(FONT_DIR, filename)
    c_font = _graphics.Font()
    c_font.LoadFont(path)
    with open(path) as f:
        bdf = parse_bdf(f.read())
    _BDF_BY_ID[id(c_font)] = bdf
    return c_font


def get_bdf_for(font: Font) -> BDFFont:
    """Return the parsed BDF data for a previously-loaded font."""
    return _BDF_BY_ID[id(font)]


FONT_DEFAULT: Font = _load_font("6x12.bdf")
FONT_SMALL: Font = _load_font("5x8.bdf")
FONT_LABEL: Font = _load_font("7x13.bdf")
FONT_VALUE: Font = FONT_DEFAULT
FONT_VALUE_SMALL: Font = FONT_SMALL
FONT_DELTA: Font = _load_font("6x10.bdf")
```

- [ ] **Step 4: Run tests**

Run: `make test ARGS="tests/test_fonts.py"`
Expected: PASS.

- [ ] **Step 5: Run the full suite to ensure no regression**

Run: `make test`
Expected: All existing tests still pass.

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/fonts/__init__.py tests/test_fonts.py
git commit -m "Load BDF data alongside C fonts; expose get_bdf_for() lookup"
```

---

## Task 8: `ScaledCanvas` — `width`, `height`, `Clear`, `SetPixel` with centering

**Files:**
- Create: `src/led_ticker/scaled_canvas.py`
- Test: `tests/test_scaled_canvas.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_scaled_canvas.py`:

```python
from rgbmatrix import RGBMatrix, RGBMatrixOptions

from led_ticker.scaled_canvas import ScaledCanvas


def _make_real_canvas(real_w=256, real_h=64):
    options = RGBMatrixOptions()
    options.cols = real_w  # stub honors cols * chain when chain=1
    options.rows = real_h
    options.chain_length = 1
    matrix = RGBMatrix(options=options)
    return matrix.CreateFrameCanvas()


def test_logical_dimensions_at_scale_4():
    real = _make_real_canvas(real_w=256, real_h=64)
    sc = ScaledCanvas(real, scale=4)
    assert sc.width == 64       # 256 // 4
    assert sc.height == 16
    assert sc.scale == 4


def test_logical_dimensions_at_scale_2_letterbox():
    real = _make_real_canvas(real_w=256, real_h=64)
    sc = ScaledCanvas(real, scale=2)
    assert sc.width == 128
    assert sc.height == 16


def test_setpixel_paints_block_at_scale_4():
    real = _make_real_canvas(real_w=256, real_h=64)
    sc = ScaledCanvas(real, scale=4)
    sc.SetPixel(0, 0, 255, 0, 0)  # logical (0, 0)
    # At scale=4 on 64-tall canvas, y_offset = (64 - 16*4)/2 = 0
    # Should paint a 4x4 block at real (0, 0)..(3, 3)
    for y in range(4):
        for x in range(4):
            assert real.get_pixel(x, y) == (255, 0, 0)
    # Outside the block: still black
    assert real.get_pixel(4, 0) == (0, 0, 0)
    assert real.get_pixel(0, 4) == (0, 0, 0)


def test_setpixel_centers_at_scale_2():
    real = _make_real_canvas(real_w=256, real_h=64)
    sc = ScaledCanvas(real, scale=2)
    # y_offset = (64 - 16*2)/2 = 16
    sc.SetPixel(0, 0, 255, 0, 0)
    # 2x2 block at real (0, 16)..(1, 17)
    assert real.get_pixel(0, 16) == (255, 0, 0)
    assert real.get_pixel(1, 17) == (255, 0, 0)
    assert real.get_pixel(0, 15) == (0, 0, 0)  # above letterbox
    assert real.get_pixel(0, 18) == (0, 0, 0)


def test_clear_clears_underlying():
    real = _make_real_canvas()
    sc = ScaledCanvas(real, scale=4)
    sc.SetPixel(0, 0, 255, 0, 0)
    sc.Clear()
    assert real.get_pixel(0, 0) == (0, 0, 0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `make test ARGS="tests/test_scaled_canvas.py"`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `ScaledCanvas`**

Create `src/led_ticker/scaled_canvas.py`:

```python
"""Scaled-canvas wrapper for the bigsign rendering path.

Wraps a real `RGBMatrix` canvas. Callers always work in a 16-tall logical
canvas; the wrapper paints `scale × scale` blocks and vertically centers
the logical canvas inside the real canvas.

Used only when `scale > 1`. At `scale = 1` the existing sign uses the real
canvas directly with no wrapper.
"""

from __future__ import annotations

import attrs

CONTENT_HEIGHT = 16


@attrs.define
class ScaledCanvas:
    real: object = attrs.field()  # rgbmatrix Canvas (or test stub)
    scale: int = attrs.field(default=1)
    content_height: int = attrs.field(default=CONTENT_HEIGHT)

    @property
    def width(self) -> int:
        return self.real.width // self.scale

    @property
    def height(self) -> int:
        return self.content_height

    @property
    def _y_offset(self) -> int:
        return (self.real.height - self.content_height * self.scale) // 2

    def Clear(self) -> None:
        self.real.Clear()

    def SetPixel(self, x: int, y: int, r: int, g: int, b: int) -> None:
        rx = x * self.scale
        ry = y * self.scale + self._y_offset
        for dy in range(self.scale):
            for dx in range(self.scale):
                self.real.SetPixel(rx + dx, ry + dy, r, g, b)
```

- [ ] **Step 4: Run tests**

Run: `make test ARGS="tests/test_scaled_canvas.py"`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/scaled_canvas.py tests/test_scaled_canvas.py
git commit -m "Add ScaledCanvas wrapper: scaled SetPixel + vertical centering"
```

---

## Task 9: `ScaledCanvas` — `draw_bdf_text` method

**Files:**
- Modify: `src/led_ticker/scaled_canvas.py`
- Modify: `tests/test_scaled_canvas.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_scaled_canvas.py`:

```python
from led_ticker.fonts import FONT_SMALL, get_bdf_for


def test_draw_bdf_text_paints_glyph_blocks():
    real = _make_real_canvas(real_w=256, real_h=64)
    sc = ScaledCanvas(real, scale=4)
    bdf = get_bdf_for(FONT_SMALL)  # 5x8
    advance = sc.draw_bdf_text(bdf, x=0, y=8, color=(255, 0, 0), text="A")
    assert advance == 5  # 5x8 advance width is 5 logical pixels
    # Some red pixel should exist within the first 5 logical columns
    found_red = False
    for ry in range(64):
        for rx in range(20):  # 5 logical * 4 scale
            if real.get_pixel(rx, ry) == (255, 0, 0):
                found_red = True
                break
        if found_red:
            break
    assert found_red


def test_draw_bdf_text_returns_total_advance():
    real = _make_real_canvas(real_w=256, real_h=64)
    sc = ScaledCanvas(real, scale=4)
    bdf = get_bdf_for(FONT_SMALL)
    advance = sc.draw_bdf_text(bdf, x=0, y=8, color=(0, 255, 0), text="ABC")
    assert advance == 15  # 3 chars × 5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `make test ARGS="tests/test_scaled_canvas.py::test_draw_bdf_text_paints_glyph_blocks"`
Expected: FAIL — method not defined.

- [ ] **Step 3: Add `draw_bdf_text` to `ScaledCanvas`**

Append to `src/led_ticker/scaled_canvas.py`:

```python
    def draw_bdf_text(self, bdf, x: int, y: int, color, text: str) -> int:
        """Draw `text` at logical (x, y) baseline. Returns total advance width.

        Mirrors the contract of `graphics.DrawText`: x is the left edge and
        y is the baseline (BDF glyphs draw above the baseline coordinate).
        """
        r, g, b = color if isinstance(color, tuple) else (color.red, color.green, color.blue)
        cx = x
        for ch in text:
            glyph = bdf.glyphs.get(ch)
            if glyph is None:
                cx += bdf.bbx_width  # fallback: use font default width
                continue
            top_y = y - glyph.bbx_height - glyph.bbx_yoff
            for row_idx, row in enumerate(glyph.bitmap):
                py = top_y + row_idx
                for col_idx, bit in enumerate(row):
                    if bit:
                        self.SetPixel(cx + glyph.bbx_xoff + col_idx, py, r, g, b)
            cx += glyph.advance_width
        return cx - x
```

- [ ] **Step 4: Run tests**

Run: `make test ARGS="tests/test_scaled_canvas.py"`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/scaled_canvas.py tests/test_scaled_canvas.py
git commit -m "ScaledCanvas: add draw_bdf_text method (BDF rasterization)"
```

---

## Task 10: `text_render.draw_text()` helper that dispatches between `graphics.DrawText` and `ScaledCanvas`

**Files:**
- Create: `src/led_ticker/text_render.py`
- Test: `tests/test_text_render.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_text_render.py`:

```python
from rgbmatrix import RGBMatrix, RGBMatrixOptions
from rgbmatrix import graphics

from led_ticker.fonts import FONT_SMALL
from led_ticker.scaled_canvas import ScaledCanvas
from led_ticker.text_render import draw_text


def _real_canvas(real_w=160, real_h=16):
    options = RGBMatrixOptions()
    options.cols = real_w
    options.rows = real_h
    options.chain_length = 1
    matrix = RGBMatrix(options=options)
    return matrix.CreateFrameCanvas()


def test_draw_text_on_real_canvas_uses_graphics_drawtext():
    real = _real_canvas()
    color = graphics.Color(255, 0, 0)
    advance = draw_text(real, FONT_SMALL, 0, 8, color, "A")
    # The C-function path returns the advance width
    assert advance > 0


def test_draw_text_on_scaled_canvas_uses_bdf_path():
    real = _real_canvas(real_w=256, real_h=64)
    sc = ScaledCanvas(real, scale=4)
    color = (0, 255, 0)
    advance = draw_text(sc, FONT_SMALL, 0, 8, color, "A")
    assert advance == 5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `make test ARGS="tests/test_text_render.py"`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `draw_text`**

Create `src/led_ticker/text_render.py`:

```python
"""Unified text-drawing helper that picks the right rendering path.

For a real `RGBMatrix` canvas (existing sign), forwards to `graphics.DrawText`
unchanged. For a `ScaledCanvas` (bigsign at scale > 1), uses the pure-Python
BDF rasterizer. Call sites swap from `graphics.DrawText(...)` to
`draw_text(...)` mechanically.
"""

from __future__ import annotations

from led_ticker._compat import require_graphics
from led_ticker.fonts import get_bdf_for
from led_ticker.scaled_canvas import ScaledCanvas

_graphics = require_graphics()


def draw_text(canvas, font, x: int, y: int, color, text: str) -> int:
    """Draw `text` at (x, y) baseline. Returns total advance width."""
    if isinstance(canvas, ScaledCanvas):
        bdf = get_bdf_for(font)
        return canvas.draw_bdf_text(bdf, x, y, color, text)
    return _graphics.DrawText(canvas, font, x, y, color, text)
```

- [ ] **Step 4: Run tests**

Run: `make test ARGS="tests/test_text_render.py"`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/text_render.py tests/test_text_render.py
git commit -m "Add draw_text() helper: dispatches DrawText vs BDF rasterizer"
```

---

## Task 11: Replace `graphics.DrawText` with `draw_text` across widgets and `presentation.py`

**Files (all 6 to modify):**
- `src/led_ticker/widgets/message.py:67,106`
- `src/led_ticker/widgets/weather.py:128,149,158`
- `src/led_ticker/widgets/mlb.py:227`
- `src/led_ticker/widgets/crypto/coinbase.py:138,142,146`
- `src/led_ticker/widgets/crypto/etherscan.py:89,96,106`
- `src/led_ticker/presentation.py:96,165`

These are mechanical replacements: at each call site, change `graphics.DrawText(canvas, font, x, y, color, text)` to `draw_text(canvas, font, x, y, color, text)`. The signature is identical and the return value is identical (advance width).

- [ ] **Step 1: Run the existing test suite to establish a green baseline**

Run: `make test`
Expected: All tests PASS. If anything is failing already, stop and fix before continuing.

- [ ] **Step 2: For each of the 6 files, swap `graphics.DrawText(...)` to `draw_text(...)` and update the import**

In each file:
- Add `from led_ticker.text_render import draw_text` at the top.
- Remove `graphics` import if it was only used for `DrawText`. If `graphics` is also used for `Color(...)`, leave the import.
- Replace each `graphics.DrawText(...)` call with `draw_text(...)`. Keep all arguments identical.

Repeat for: `message.py`, `weather.py`, `mlb.py`, `coinbase.py`, `etherscan.py`, `presentation.py`.

- [ ] **Step 3: Verify no `graphics.DrawText` references remain**

Run: `grep -rn "graphics.DrawText" src/`
Expected: no output (all call sites swapped).

- [ ] **Step 4: Run full test suite**

Run: `make test`
Expected: All tests PASS — `draw_text` on a real canvas is semantically identical to `graphics.DrawText`, so existing tests are unaffected.

- [ ] **Step 5: Lint**

Run: `make lint`
Expected: PASS (no unused imports left over).

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/widgets src/led_ticker/presentation.py
git commit -m "Replace graphics.DrawText with draw_text helper across widgets"
```

---

## Task 12: Add `region` kwarg to widget protocol and `run_transition` (no behavior change yet)

**Files:**
- Modify: `src/led_ticker/widget.py` — protocol docstring
- Modify: `src/led_ticker/transitions/__init__.py` — `run_transition` signature
- Test: `tests/test_widget_protocol.py`, `tests/test_transitions.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_widget_protocol.py`:

```python
from led_ticker.drawing import Region


def test_widget_protocol_accepts_region_kwarg():
    """Existing widgets must accept (and ignore) a `region` kwarg."""
    from led_ticker.widgets.message import TickerMessage

    msg = TickerMessage(text="hi")
    # Smoke: doesn't raise when given region
    canvas = _make_test_canvas()  # adapt from existing fixture
    canvas2, pos = msg.draw(canvas, cursor_pos=0, region=Region(0, 0, 160, 16))
    assert pos >= 0
```

(Adapt `_make_test_canvas()` from existing patterns in `tests/test_widget_protocol.py`. If `region` is consumed via `**kwargs` already, the test passes immediately.)

- [ ] **Step 2: Run test to verify it fails (or passes)**

Run: `make test ARGS="tests/test_widget_protocol.py"`
- If PASS: widgets already accept `**kwargs` and the protocol is forward-compatible. Skip to step 5.
- If FAIL: at least one widget's `draw()` doesn't accept `region`.

- [ ] **Step 3: If failing, audit each widget's `draw()` signature**

Run: `grep -n "def draw" src/led_ticker/widgets/*.py src/led_ticker/widgets/crypto/*.py`

For each widget that doesn't end with `**kwargs`, add it. The widget protocol is documented in `src/led_ticker/widget.py`.

- [ ] **Step 4: Update widget protocol docstring in `widget.py`**

In `src/led_ticker/widget.py`, find the `Widget` Protocol class and update the `draw` method docstring:

```python
class Widget(Protocol):
    def draw(
        self,
        canvas,
        cursor_pos: int = 0,
        **kwargs,
    ) -> tuple[object, int]:
        """Draw the widget into `canvas`.

        Recognized kwargs:
        - `y_offset` (int): vertical offset from natural baseline
        - `region` (Region | None): sub-area of canvas to draw within (default: full canvas)
        - `scale` is NOT a kwarg; if the canvas is a ScaledCanvas the
          scaling is transparent. Widgets that need to read scale can
          use `getattr(canvas, "scale", 1)`.
        """
```

- [ ] **Step 5: Add `region` to `run_transition`**

Edit `src/led_ticker/transitions/__init__.py`. Find `run_transition` and add `region=None` to the signature; forward it to `frame_at` only if the transition's `frame_at` accepts `region`. Cleanest path: add it to the `**kwargs` already passed through.

Add to `tests/test_transitions.py`:

```python
def test_run_transition_accepts_region_kwarg():
    # Smoke test: `region=...` is accepted and doesn't raise.
    from led_ticker.transitions import run_transition
    from led_ticker.drawing import Region
    # Use the simplest transition (cut) and existing fixtures
    # ... build canvas, outgoing, incoming ...
    # await run_transition("cut", ..., region=Region(0, 0, 160, 16))
```

(Adapt to the existing run_transition test scaffolding.)

- [ ] **Step 6: Run all tests**

Run: `make test`
Expected: All tests PASS.

- [ ] **Step 7: Commit**

```bash
git add src/led_ticker/widget.py src/led_ticker/transitions/__init__.py tests/
git commit -m "Plumb Region kwarg through widget protocol and run_transition"
```

---

## Task 13: Wire scale through `Ticker` — wrap canvas in `ScaledCanvas` when section `scale > 1`

**Files:**
- Modify: `src/led_ticker/ticker.py`
- Test: `tests/test_ticker.py` (or `test_ticker_display.py`)

The Ticker reads `section.scale` and, when `> 1`, wraps the real canvas in a `ScaledCanvas`. The wrapper is created once per section and reused across draws within that section. SwapOnVSync is always called on the real canvas.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_ticker.py`:

```python
from led_ticker.scaled_canvas import ScaledCanvas


def test_ticker_wraps_canvas_when_section_scale_is_4(monkeypatch):
    """When a section sets scale=4, widgets receive a ScaledCanvas."""
    received = []

    class CapturingWidget:
        def draw(self, canvas, cursor_pos=0, **kwargs):
            received.append(canvas)
            return canvas, 0

    # Build a Ticker with one CapturingWidget section at scale=4.
    # ... (use existing test scaffolding to construct Ticker) ...
    # Run a single section iteration.
    # Assert the canvas passed in is a ScaledCanvas.
    assert any(isinstance(c, ScaledCanvas) for c in received)


def test_ticker_passes_real_canvas_when_section_scale_is_1():
    """When scale=1 (existing sign), widgets receive the real canvas unchanged."""
    received = []

    class CapturingWidget:
        def draw(self, canvas, cursor_pos=0, **kwargs):
            received.append(canvas)
            return canvas, 0

    # ... build Ticker at scale=1 ...
    assert all(not isinstance(c, ScaledCanvas) for c in received)
```

(The exact scaffolding depends on the existing test patterns in `test_ticker.py` — adapt accordingly. The minimum viable scaffold builds a `Ticker` with a single section, runs one iteration of `run_swap()` (or similar), and inspects what `draw()` saw.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `make test ARGS="tests/test_ticker.py -k scale"`
Expected: FAIL.

- [ ] **Step 3: Implement scale wrapping in `Ticker`**

In `src/led_ticker/ticker.py`, identify each place where `canvas = self.frame.get_clean_canvas()` is followed by widget `draw()` calls. Add wrapping:

```python
def _maybe_wrap(self, canvas, scale: int):
    if scale > 1:
        return ScaledCanvas(canvas, scale=scale)
    return canvas
```

In each `run_*` method, after `canvas = self.frame.get_clean_canvas()`, wrap once per section:

```python
section_scale = getattr(self.current_section, "scale", 1)
draw_canvas = self._maybe_wrap(canvas, section_scale)
# ... pass `draw_canvas` to widgets and run_transition ...
# SwapOnVSync still called on the real canvas:
canvas = self.frame.matrix.SwapOnVSync(canvas)
```

This is a careful sweep — every widget `draw()` call site and every `run_transition()` call gets `draw_canvas` instead of `canvas`. SwapOnVSync stays on `canvas`. The wrapper is recreated when the back-buffer is swapped (since `canvas` changes after SwapOnVSync, but the new back-buffer also needs wrapping).

A clean pattern: a small `_DrawTarget` helper that holds `(real, wrapped)` and exposes both.

- [ ] **Step 4: Run all tests**

Run: `make test`
Expected: All tests PASS, including new ones.

- [ ] **Step 5: Lint**

Run: `make lint`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/ticker.py tests/test_ticker.py
git commit -m "Ticker: wrap canvas in ScaledCanvas when section scale > 1"
```

---

## Task 14: Add `RGBMATRIX_REF` build-arg to `Dockerfile`

**Files:**
- Modify: `Dockerfile`

- [ ] **Step 1: Find the rgbmatrix install step**

Run: `grep -n "rpi-rgb-led-matrix\|rgbmatrix" Dockerfile`

- [ ] **Step 2: Add a `RGBMATRIX_REF` build-arg**

Edit `Dockerfile`. Near the top of the rgbmatrix layer, add:

```dockerfile
ARG RGBMATRIX_REF=main
```

Update the `git clone` (or pip install from git) step to use the ref:

```dockerfile
RUN git clone --depth 1 --branch ${RGBMATRIX_REF} \
    https://github.com/jamesawesome/rpi-rgb-led-matrix.git \
    && cd rpi-rgb-led-matrix \
    && make build-python PYTHON=$(which python3) \
    && cd bindings/python \
    && pip install .
```

(Match the exact install pattern used in the current Dockerfile — only the `--branch ${RGBMATRIX_REF}` part is new.)

- [ ] **Step 3: Smoke-test the build with the existing default ref**

Run: `make build-docker`
Expected: builds cleanly with `RGBMATRIX_REF` defaulting to whatever the current pin is. (If `make build-docker` doesn't pass `--build-arg`, the default applies, which is what we want.)

- [ ] **Step 4: Document the new build-arg in the Makefile**

In `Makefile`, add a `build-docker-pi5` target (or document it in the existing target's comments):

```makefile
build-docker-pi5:
	docker build --build-arg RGBMATRIX_REF=<pi5-ref> -t led-ticker:pi5 .
```

(Leave `<pi5-ref>` as a literal placeholder for now — Task 16 fills this in after the fork research.)

- [ ] **Step 5: Commit**

```bash
git add Dockerfile Makefile
git commit -m "Dockerfile: add RGBMATRIX_REF build-arg for Pi 4 / Pi 5 fork pinning"
```

---

## Task 15: Create `config/config.bigsign.example.toml`

**Files:**
- Create: `config/config.bigsign.example.toml`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_config.py`:

```python
from pathlib import Path


def test_bigsign_example_config_loads():
    repo_root = Path(__file__).resolve().parents[1]
    cfg = load_config(repo_root / "config" / "config.bigsign.example.toml")
    assert cfg.display.rows == 32
    assert cfg.display.cols == 64
    assert cfg.display.chain == 8
    assert cfg.display.pixel_mapper == "U-mapper"
    assert cfg.display.default_scale == 4
    assert len(cfg.sections) >= 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `make test ARGS="tests/test_config.py::test_bigsign_example_config_loads"`
Expected: FAIL — file not found.

- [ ] **Step 3: Create the example config**

Create `config/config.bigsign.example.toml`. Start by copying `config/config.example.toml`, then change the `[display]` block:

```toml
[display]
rows = 32
cols = 64
chain = 8
parallel = 1
pixel_mapper = "U-mapper"
brightness = 60
slowdown_gpio = 2
gpio_mapping = "adafruit-hat"
default_scale = 4
```

Keep the rest (`[transitions]`, `[[playlist.section]]`) identical to `config.example.toml`. Optionally add one section with `scale = 2` to demonstrate per-section override.

- [ ] **Step 4: Run tests**

Run: `make test ARGS="tests/test_config.py"`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add config/config.bigsign.example.toml tests/test_config.py
git commit -m "Add bigsign example config (64x256, scale=4, U-mapper)"
```

---

## Task 16: Pi 5 fork research and dependency pin (research-only)

**Files:**
- Modify: `Dockerfile` (set the default `RGBMATRIX_REF` for Pi 5 build)
- Modify: `Makefile` (replace placeholder `<pi5-ref>`)
- Modify: `CLAUDE.md` (note the fork in deployment section)

This task has no automated tests — it's a research deliverable.

- [ ] **Step 1: Research current Pi 5 forks of `rpi-rgb-led-matrix`**

Use `WebSearch` and `WebFetch` to evaluate:
- The state of Pi 5 support in the upstream `hzeller/rpi-rgb-led-matrix` repo (issues, branches, PRs)
- Active community forks claiming Pi 5 support
- Recent activity / open issues on each candidate

Document findings (one paragraph each) for the top 2-3 candidates.

- [ ] **Step 2: Choose the most stable Pi-5-capable fork/branch**

Pick one based on: recent commits, working community reports, compatibility with the Adafruit HAT wiring, support for `--led-pixel-mapper=U-mapper`.

- [ ] **Step 3: Re-fork under `jamesawesome/rpi-rgb-led-matrix`**

Either:
- Add the chosen Pi-5 ref as a branch on the existing `jamesawesome/rpi-rgb-led-matrix` fork, OR
- Mirror the chosen fork as a separate fork.

Push and confirm the branch is accessible from the build host.

- [ ] **Step 4: Update Dockerfile default and Makefile placeholder**

In `Dockerfile`, leave the default `ARG RGBMATRIX_REF=main` (Pi 4 default) untouched.
In `Makefile`, set the actual ref in `build-docker-pi5`:

```makefile
build-docker-pi5:
	docker build --build-arg RGBMATRIX_REF=<actual-pi5-ref> -t led-ticker:pi5 .
```

- [ ] **Step 5: Document the fork choice**

In `CLAUDE.md`, in the "Docker / Deployment" section, add a line under the rgbmatrix fork note:

```
- Pi 5 build: `make build-docker-pi5` — uses Pi-5-capable fork at <ref>.
  See `docs/superpowers/specs/2026-04-29-pi5-bigsign-port-design.md` for context.
```

- [ ] **Step 6: Smoke-test the Pi 5 image build (on a host with Docker; can be a Pi 5 itself)**

Run: `make build-docker-pi5`
Expected: builds cleanly. If linker errors or missing headers appear, document them in the commit message and follow up in a hardware-verification task.

- [ ] **Step 7: Commit**

```bash
git add Dockerfile Makefile CLAUDE.md
git commit -m "Pin Pi 5–capable rgbmatrix fork for the bigsign build"
```

---

## Task 17: Hardware verification (manual, on the new sign)

This is a **manual** task with no automated tests. Execute on the physical Pi 5 + 2×4 panel installation.

- [ ] **Step 1: Deploy the `led-ticker:pi5` image and `config/config.bigsign.example.toml`**

Per the existing systemd deploy pattern (`deploy/led-ticker.service`), point a fresh service unit at the Pi 5 image and the bigsign config.

- [ ] **Step 2: Confirm panel arrangement matches expected serpentine layout**

Display a known pattern (e.g., a test message). Verify text appears unbroken across panel boundaries — if it appears mirrored or split, the cable serpentines opposite to assumed; add `Rotate:180` to `pixel_mapper`:

```toml
pixel_mapper = "U-mapper;Rotate:180"
```

(or just `Rotate:180` if U-mapper isn't needed.)

- [ ] **Step 3: Verify each widget renders cleanly at scale = 4**

Cycle through the playlist and confirm:
- Text is legible (no aliasing artifacts)
- Sprites (nyancat, pokeball, baseball, pacman, sailor_moon) animate cleanly
- Weather icons render at expected size
- Push/wipe transitions execute without tearing or visible flicker

- [ ] **Step 4: Tune timing constants if refresh is unstable**

If flicker or tearing appears, edit the bigsign config:
- Increase `slowdown_gpio` (try 3, 4, 5) until flicker stops
- If colors are wrong, try `pwm_lsb_nanoseconds = 200` (default 130)

- [ ] **Step 5: Verify 20 fps target is hit**

Add `[display].show_refresh = true` (if a `LedFrame.led_show_refresh` flag is exposed via config — if not, this step is informational only). Watch the matrix's reported refresh rate. Should comfortably exceed 100 Hz at the configured `pwm_bits=11`. The 20 fps animation rate is a separate concern — if widget loops feel sluggish, profile with `cProfile` and apply the frame-budget levers from the spec.

- [ ] **Step 6: Add a section with `scale = 2` and verify letterboxing**

Edit the running config to add a `scale = 2` section. Verify content appears 32 real-pixels tall, vertically centered, with 16 black pixels above and below.

- [ ] **Step 7: Commit the tuned bigsign config**

If any tuning was needed, commit the final `config/config.bigsign.example.toml`:

```bash
git add config/config.bigsign.example.toml
git commit -m "Tune bigsign config for hardware on first deploy"
```

---

## Self-Review Checklist (run before handing off)

- [ ] **Spec coverage:** every section of `docs/superpowers/specs/2026-04-29-pi5-bigsign-port-design.md` is covered by at least one task above. Confirmed:
  - Hardware constants → Task 4 (test stub), Task 17 (hardware)
  - Library / Pi 5 dependency → Tasks 14, 16
  - Configuration → Tasks 2, 3, 15
  - Canvas dimensions derived → Task 4
  - ScaledCanvas wrapper → Tasks 8, 9
  - BDF parser + glyph cache → Tasks 5, 6, 7
  - Y centering → Task 8
  - Widget protocol + Region → Tasks 1, 12
  - Plumbing (Ticker, run_transition) → Tasks 12, 13
  - Per-widget changes (DrawText → draw_text) → Task 11
  - Transitions at scale → handled transparently by ScaledCanvas (no per-transition tasks needed); per-transition timing tunes are part of Task 17
  - Frame budget levers → Task 17
  - Deployment → Tasks 14, 15, 16
  - Testing → tests inline in each task
- [ ] **Placeholder scan:** no "TBD"/"TODO" in implementation steps. The sole literal placeholders (`<pi5-ref>` in Task 14 and `<actual-pi5-ref>` in Task 16) are explicitly resolved within Task 16.
- [ ] **Type consistency:** `BDFFont`/`BDFGlyph` defined in Task 5, used in Task 7/8/9/10. `ScaledCanvas` defined in Task 8, used in Tasks 9/10/12/13. `Region` defined in Task 1, used in Task 12. `draw_text()` defined in Task 10, used in Task 11.
- [ ] **Order check:** every task's prerequisites land in earlier tasks. Task 11 (mechanical sweep) requires Task 10 (`draw_text`). Task 13 (Ticker wrapping) requires Task 8/9 (`ScaledCanvas`) and Task 12 (region plumbing).

---

## Out of Scope (deferred)

- Zoned multi-region layouts (the future "C" from the brainstorm). The `Region` type is the seed; a separate spec/plan covers zoned layouts when needed.
- New widget types (live game scores, calendar, clock).
- Hand-drawn larger sprites or new BDF fonts.
- Dynamic per-zone scale.
- A second-level `(text, font, color, scale)` glyph-string cache. Only added if Task 17 reveals a frame-budget shortfall.
