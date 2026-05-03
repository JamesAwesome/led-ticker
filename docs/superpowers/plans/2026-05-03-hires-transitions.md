# Hi-res Transitions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add high-resolution `nyancat` / `nyancat_reverse` / `pokeball` / `pokeball_reverse` transitions on the bigsign that auto-activate when the canvas is a `ScaledCanvas`, painting bundled animated sprites at native physical resolution.

**Architecture:** No new transition class registrations. Existing `NyanCat`/`NyanCatReverse`/`Pokeball`/`PokeballReverse` classes get a single dispatch line that picks `_frame_at_hires` (new) or `_frame_at_lowres` (today's body, renamed). The hi-res path imports a shared `render_hires_frame` helper that decodes the sprite once via Pillow, caches frames + non-black pixels via `@functools.cache`, and paints to the unwrapped real canvas. Reverse variants reuse the base sprite file with horizontal flip at decode.

**Tech Stack:** Python 3.13, Pillow (already a dep for the GIF widget), pytest, attrs, hatchling (build backend).

---

## File Structure

**New files:**
- `src/led_ticker/transitions/sprites/nyancat.webp` — copied from `~/Desktop/nyancat-transparent.webp` (250×175, 6 frames).
- `src/led_ticker/transitions/sprites/pokeball.gif` — copied from `~/Desktop/pikachu-run-transparent.gif` (220×160, 4 frames). Named `pokeball.gif` in the bundle to match the transition family even though the asset is a running Pikachu.
- `src/led_ticker/transitions/_hires_registry.py` — `HiresSpec` dataclass + `HIRES_REGISTRY` dict (4 entries).
- `src/led_ticker/transitions/_hires_loader.py` — `HiresFrames` dataclass + `_frame_for_elapsed` + `load_hires` (Pillow decode + cache) + `render_hires_frame` (the per-frame sprite painter).

**Modified files:**
- `src/led_ticker/transitions/__init__.py` — `run_transition` passes `duration_ms` kwarg to `frame_at`.
- `src/led_ticker/transitions/nyancat.py` — `NyanCat` and `NyanCatReverse` get `_registry_name`, `_frame_at_lowres` (today's body), `_frame_at_hires`, and dispatch in `frame_at`.
- `src/led_ticker/transitions/pokeball.py` — same edits to `Pokeball` and `PokeballReverse`.

**New tests:**
- `tests/test_hires_loader.py` — covers registry, decoder, frame picker, render helper, and a parametrized smoke test that loads each production sprite.
- Extensions to `tests/test_nyancat.py`, `tests/test_pokeball.py` — dispatch coverage.
- Extension to `tests/test_transitions.py` — `duration_ms` wiring through `run_transition`.

**No changes needed to `pyproject.toml`:** hatchling's default behavior includes everything in `src/led_ticker/` not matched by `.gitignore`. The sprite files will be in the wheel by virtue of being checked into git. Task 1 includes a verification step that confirms this.

---

## Conventions for this plan

- Tests use `make test ARGS="..."` so `PYTHONPATH=tests/stubs` is set.
- Production sprite files are NOT inputs to unit tests — generate small fixtures via Pillow at test setup. Only the production smoke test reads real sprites.
- `Image.Resampling.LANCZOS` is the canonical resize filter (matches existing `widgets/_image_fit.py` usage).
- `unwrap_to_real(canvas)` lives at `led_ticker.scaled_canvas:106` — peels any `ScaledCanvas` wrapper.
- `scan_non_black(pixels, w, h)` lives at `led_ticker.widgets._image_fit:29` — produces `[(x, y, r, g, b), ...]`.
- The conftest `canvas` fixture is a `mock.Mock`, NOT a `ScaledCanvas`. Existing `test_nyancat.py` / `test_pokeball.py` tests pass through unchanged because dispatch picks the lowres branch.
- Use `_StubCanvas` (test stub) wrapped in a real `ScaledCanvas` for hires-dispatch and rendering tests.

---

### Task 1: Bundle sprite assets and verify wheel inclusion

**Files:**
- Create: `src/led_ticker/transitions/sprites/nyancat.webp`
- Create: `src/led_ticker/transitions/sprites/pokeball.gif`

Sprites must be on disk before the registry module can reference them. No tests in this task — it's pure file copy + verification.

- [ ] **Step 1: Create the sprites directory and copy assets**

```bash
mkdir -p src/led_ticker/transitions/sprites
cp ~/Desktop/nyancat-transparent.webp src/led_ticker/transitions/sprites/nyancat.webp
cp ~/Desktop/pikachu-run-transparent.gif src/led_ticker/transitions/sprites/pokeball.gif
```

- [ ] **Step 2: Verify dimensions and frame counts via Pillow**

```bash
PYTHONPATH=tests/stubs uv run python -c "
from PIL import Image
import os
for name in ('nyancat.webp', 'pokeball.gif'):
    p = f'src/led_ticker/transitions/sprites/{name}'
    with Image.open(p) as im:
        print(f'{name}: size={im.size} frames={getattr(im, \"n_frames\", 1)} mode={im.mode}')
"
```

Expected output (approximately):
```
nyancat.webp: size=(250, 175) frames=6 mode=RGBA
pokeball.gif: size=(220, 160) frames=4 mode=P
```

If `n_frames < 2`, the asset is wrong — re-export from source.

- [ ] **Step 3: Verify hatchling will include sprites in the wheel**

```bash
uv build --wheel 2>&1 | tail -20
unzip -l dist/led_ticker-2.0.0-py3-none-any.whl | grep -E 'sprites/' || echo "MISSING — sprites not in wheel"
```

Expected: lines like `led_ticker/transitions/sprites/nyancat.webp` and `led_ticker/transitions/sprites/pokeball.gif`. If "MISSING", add explicit force-include to `pyproject.toml`:

```toml
[tool.hatch.build.targets.wheel.force-include]
"src/led_ticker/transitions/sprites" = "led_ticker/transitions/sprites"
```

Re-run `uv build --wheel` and re-verify.

- [ ] **Step 4: Clean up the test build**

```bash
rm -rf dist/
```

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/transitions/sprites/
# Also pyproject.toml IF Step 3 required force-include changes
git commit -m "Bundle nyancat + pokeball hi-res sprites in transitions/sprites"
```

---

### Task 2: HiresSpec + HIRES_REGISTRY

**Files:**
- Create: `src/led_ticker/transitions/_hires_registry.py`
- Test: `tests/test_hires_loader.py` (new — created here, extended in Task 3)

Pure data module. No Pillow involvement — just the dataclass and four entries.

- [ ] **Step 1: Create the test file with failing tests**

```python
# tests/test_hires_loader.py
"""Tests for the hi-res transition registry, loader, and renderer."""

from __future__ import annotations

from pathlib import Path

import pytest


class TestHiresRegistry:
    def test_registry_has_exactly_four_entries(self):
        from led_ticker.transitions._hires_registry import HIRES_REGISTRY

        assert set(HIRES_REGISTRY.keys()) == {
            "nyancat",
            "nyancat_reverse",
            "pokeball",
            "pokeball_reverse",
        }

    def test_nyancat_uses_webp_no_flip(self):
        from led_ticker.transitions._hires_registry import HIRES_REGISTRY

        spec = HIRES_REGISTRY["nyancat"]
        assert spec.sprite_path.name == "nyancat.webp"
        assert spec.flip_horizontal is False

    def test_nyancat_reverse_uses_same_file_with_flip(self):
        from led_ticker.transitions._hires_registry import HIRES_REGISTRY

        base = HIRES_REGISTRY["nyancat"]
        rev = HIRES_REGISTRY["nyancat_reverse"]
        assert rev.sprite_path == base.sprite_path
        assert rev.flip_horizontal is True

    def test_pokeball_uses_gif_no_flip(self):
        from led_ticker.transitions._hires_registry import HIRES_REGISTRY

        spec = HIRES_REGISTRY["pokeball"]
        assert spec.sprite_path.name == "pokeball.gif"
        assert spec.flip_horizontal is False

    def test_pokeball_reverse_uses_same_file_with_flip(self):
        from led_ticker.transitions._hires_registry import HIRES_REGISTRY

        base = HIRES_REGISTRY["pokeball"]
        rev = HIRES_REGISTRY["pokeball_reverse"]
        assert rev.sprite_path == base.sprite_path
        assert rev.flip_horizontal is True

    def test_sprite_paths_are_absolute_and_exist(self):
        from led_ticker.transitions._hires_registry import HIRES_REGISTRY

        for name, spec in HIRES_REGISTRY.items():
            assert spec.sprite_path.is_absolute(), f"{name} path not absolute"
            assert spec.sprite_path.exists(), f"{name} sprite file missing"
```

- [ ] **Step 2: Run, verify failure**

Run: `make test ARGS="tests/test_hires_loader.py::TestHiresRegistry -v"`
Expected: FAIL — `ModuleNotFoundError: No module named 'led_ticker.transitions._hires_registry'`.

- [ ] **Step 3: Create `_hires_registry.py`**

```python
# src/led_ticker/transitions/_hires_registry.py
"""Registry of hi-res sprite assets for sprite-based transitions.

When a transition's name appears here AND the canvas is a ScaledCanvas,
the dispatch in `nyancat.py` / `pokeball.py` picks the hi-res render
path. Reverse variants reuse the base sprite file and flip horizontally
at decode time so we ship one asset per family, not two.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

SPRITES_DIR = Path(__file__).parent / "sprites"


@dataclass(frozen=True)
class HiresSpec:
    """Describes one hi-res sprite asset.

    `sprite_path` points at the bundled gif/webp inside the package.
    `flip_horizontal=True` mirrors each frame at decode (used for
    `*_reverse` variants so the cat/pikachu faces its travel direction).
    """

    sprite_path: Path
    flip_horizontal: bool


HIRES_REGISTRY: dict[str, HiresSpec] = {
    "nyancat": HiresSpec(
        sprite_path=SPRITES_DIR / "nyancat.webp",
        flip_horizontal=False,
    ),
    "nyancat_reverse": HiresSpec(
        sprite_path=SPRITES_DIR / "nyancat.webp",
        flip_horizontal=True,
    ),
    "pokeball": HiresSpec(
        sprite_path=SPRITES_DIR / "pokeball.gif",
        flip_horizontal=False,
    ),
    "pokeball_reverse": HiresSpec(
        sprite_path=SPRITES_DIR / "pokeball.gif",
        flip_horizontal=True,
    ),
}
```

- [ ] **Step 4: Run tests, verify pass**

Run: `make test ARGS="tests/test_hires_loader.py::TestHiresRegistry -v"`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/transitions/_hires_registry.py tests/test_hires_loader.py
git commit -m "Add hi-res transition registry (nyancat + pokeball ± reverse)"
```

---

### Task 3: HiresFrames + load_hires + render_hires_frame

**Files:**
- Create: `src/led_ticker/transitions/_hires_loader.py`
- Modify: `tests/test_hires_loader.py` (extend)

Decoder, frame cache, frame-time picker, and the shared per-frame painter that both nyancat and pokeball will call.

- [ ] **Step 1: Add failing tests for the loader**

Append to `tests/test_hires_loader.py`:

```python
class _StubColor:
    def __init__(self, r, g, b):
        self.red = r
        self.green = g
        self.blue = b


def _make_tiny_sprite(tmp_path, *, n_frames=2, size=(8, 8), durations=(50, 100)):
    """Generate a tiny transparent GIF: a magenta filled square + alpha."""
    from PIL import Image

    frames = []
    for i in range(n_frames):
        img = Image.new("RGBA", size, (0, 0, 0, 0))
        # paint a 4x4 colored block in the upper-left so non-black-pixel
        # counting is predictable
        for y in range(4):
            for x in range(4):
                img.putpixel((x, y), (255, 0, 128, 255) if i == 0 else (0, 255, 200, 255))
        frames.append(img)
    path = tmp_path / "tiny.gif"
    frames[0].save(
        path,
        save_all=True,
        append_images=frames[1:],
        duration=list(durations[:n_frames]),
        loop=0,
        disposal=2,
    )
    return path


@pytest.fixture
def tiny_sprite(tmp_path):
    return _make_tiny_sprite(tmp_path)


@pytest.fixture(autouse=True)
def _clear_loader_cache():
    """Ensure load_hires's @functools.cache is cleared between tests so
    monkeypatched registry entries don't leak."""
    from led_ticker.transitions._hires_loader import load_hires
    load_hires.cache_clear()
    yield
    load_hires.cache_clear()


class TestFrameForElapsed:
    def test_picks_first_frame_at_zero(self):
        from led_ticker.transitions._hires_loader import _frame_for_elapsed

        assert _frame_for_elapsed(0, durations=[100, 100, 100]) == 0

    def test_picks_second_frame_after_first_duration(self):
        from led_ticker.transitions._hires_loader import _frame_for_elapsed

        # 0 .. <100 = frame 0; 100 .. <200 = frame 1
        assert _frame_for_elapsed(99, durations=[100, 100, 100]) == 0
        assert _frame_for_elapsed(100, durations=[100, 100, 100]) == 1
        assert _frame_for_elapsed(199, durations=[100, 100, 100]) == 1
        assert _frame_for_elapsed(200, durations=[100, 100, 100]) == 2

    def test_wraps_at_total_loop_ms(self):
        from led_ticker.transitions._hires_loader import _frame_for_elapsed

        # total = 300; elapsed=350 → pos=50 → frame 0
        assert _frame_for_elapsed(350, durations=[100, 100, 100]) == 0


class TestLoadHires:
    def test_returns_none_for_unregistered_name(self):
        from led_ticker.transitions._hires_loader import load_hires

        assert load_hires("not_a_real_transition") is None

    def test_decodes_tiny_sprite(self, tmp_path, monkeypatch):
        from led_ticker.transitions import _hires_registry
        from led_ticker.transitions._hires_registry import HiresSpec
        from led_ticker.transitions._hires_loader import load_hires

        path = _make_tiny_sprite(tmp_path)
        monkeypatch.setitem(
            _hires_registry.HIRES_REGISTRY,
            "test_sprite",
            HiresSpec(sprite_path=path, flip_horizontal=False),
        )
        frames = load_hires("test_sprite")
        assert frames is not None
        # Source is 8x8; scaled to fit panel_h=64 → 64x64 (no width change since w==h).
        assert frames.height == 64
        assert frames.width == 64
        assert len(frames.durations_ms) == 2
        assert frames.total_loop_ms == sum(frames.durations_ms)
        assert len(frames.non_black) == 2
        # The 4x4 block at (0,0) becomes 32x32 at scale 8x; expect ~1024 lit pixels.
        assert len(frames.non_black[0]) == 32 * 32

    def test_caches_decoded_frames(self, tmp_path, monkeypatch):
        from led_ticker.transitions import _hires_registry
        from led_ticker.transitions._hires_registry import HiresSpec
        from led_ticker.transitions._hires_loader import load_hires

        path = _make_tiny_sprite(tmp_path)
        monkeypatch.setitem(
            _hires_registry.HIRES_REGISTRY,
            "test_sprite",
            HiresSpec(sprite_path=path, flip_horizontal=False),
        )
        first = load_hires("test_sprite")
        second = load_hires("test_sprite")
        assert first is second  # @functools.cache returns the same object

    def test_flip_horizontal_mirrors_pixel_x(self, tmp_path, monkeypatch):
        from led_ticker.transitions import _hires_registry
        from led_ticker.transitions._hires_registry import HiresSpec
        from led_ticker.transitions._hires_loader import load_hires

        path = _make_tiny_sprite(tmp_path)
        monkeypatch.setitem(
            _hires_registry.HIRES_REGISTRY,
            "base", HiresSpec(sprite_path=path, flip_horizontal=False),
        )
        monkeypatch.setitem(
            _hires_registry.HIRES_REGISTRY,
            "flipped", HiresSpec(sprite_path=path, flip_horizontal=True),
        )
        base = load_hires("base")
        flipped = load_hires("flipped")
        assert base is not None and flipped is not None

        # In base, lit pixels are at x in [0, 32); in flipped at x in [width-32, width).
        base_xs = {x for (x, y, r, g, b) in base.non_black[0]}
        flipped_xs = {x for (x, y, r, g, b) in flipped.non_black[0]}
        assert max(base_xs) < base.width // 2
        assert min(flipped_xs) >= flipped.width // 2
```

- [ ] **Step 2: Run, verify failure**

Run: `make test ARGS="tests/test_hires_loader.py -v"`
Expected: FAIL — `ModuleNotFoundError: No module named 'led_ticker.transitions._hires_loader'`.

- [ ] **Step 3: Create `_hires_loader.py`**

```python
# src/led_ticker/transitions/_hires_loader.py
"""Decoder, cache, and per-frame painter for hi-res transitions.

The loader uses Pillow directly (not `widgets/_image_fit.apply_fit` /
`flatten_onto_black`) because those produce panel-sized output suitable
for the GIF widget. Hi-res transitions need sprite-sized output so the
sprite can be positioned horizontally during traversal.

`render_hires_frame` is shared by `NyanCat`, `NyanCatReverse`, `Pokeball`,
and `PokeballReverse` — they all paint a single sprite that traverses
horizontally and snap to incoming near t=1.0.
"""

from __future__ import annotations

import functools
from dataclasses import dataclass, field
from typing import Any

from PIL import Image

from led_ticker.scaled_canvas import unwrap_to_real
from led_ticker.transitions._hires_registry import HIRES_REGISTRY, HiresSpec
from led_ticker.widgets._image_fit import scan_non_black

# Snap to incoming this fraction of the way through; the sprite has
# traveled most of the way across by then. Keeps the panel from showing
# a frame of "outgoing only" right before t=1.0.
SNAP_THRESHOLD: float = 0.95


@dataclass
class HiresFrames:
    """Decoded sprite, ready to paint at native resolution."""

    width: int
    height: int
    durations_ms: list[int]
    non_black: list[list[tuple[int, int, int, int, int]]]
    total_loop_ms: int = field(init=False)

    def __post_init__(self) -> None:
        self.total_loop_ms = sum(self.durations_ms)


def _frame_for_elapsed(elapsed_ms: int, durations: list[int]) -> int:
    """Pick the frame index for a given elapsed time, wrapping at total loop."""
    total = sum(durations)
    if total <= 0:
        return 0
    pos = elapsed_ms % total
    cum = 0
    for i, d in enumerate(durations):
        cum += d
        if pos < cum:
            return i
    return len(durations) - 1


def _decode(spec: HiresSpec, panel_h: int = 64) -> HiresFrames:
    """Decode all frames of `spec.sprite_path` to sprite-sized non-black lists.

    Scales each frame by height to `panel_h`; flips horizontally if
    `spec.flip_horizontal`; flattens alpha onto black; runs `scan_non_black`.
    """
    durations: list[int] = []
    non_black: list[list[tuple[int, int, int, int, int]]] = []
    out_width = 0
    out_height = 0

    with Image.open(spec.sprite_path) as src:
        n_frames = getattr(src, "n_frames", 1)
        for i in range(n_frames):
            src.seek(i)
            rgba = src.convert("RGBA")
            if spec.flip_horizontal:
                rgba = rgba.transpose(Image.FLIP_LEFT_RIGHT)

            scale = panel_h / rgba.height
            new_w = max(1, round(rgba.width * scale))
            new_h = panel_h
            scaled = rgba.resize((new_w, new_h), Image.Resampling.LANCZOS)

            black = Image.new("RGB", (new_w, new_h), (0, 0, 0))
            black.paste(scaled, (0, 0), mask=scaled.split()[3])
            pixels = black.tobytes()

            durations.append(int(src.info.get("duration", 50)))
            non_black.append(scan_non_black(pixels, new_w, new_h))
            out_width = new_w
            out_height = new_h

    return HiresFrames(
        width=out_width,
        height=out_height,
        durations_ms=durations,
        non_black=non_black,
    )


@functools.cache
def load_hires(transition_name: str) -> HiresFrames | None:
    """Decode + cache a registered sprite. Returns None for unregistered names."""
    spec = HIRES_REGISTRY.get(transition_name)
    if spec is None:
        return None
    return _decode(spec)


def render_hires_frame(
    t: float,
    canvas: Any,
    outgoing: Any,
    incoming: Any,
    registry_name: str,
    **kwargs: Any,
) -> Any:
    """Paint one frame of a hi-res sprite traversing horizontally.

    Used by `NyanCat`/`NyanCatReverse`/`Pokeball`/`PokeballReverse` when
    the canvas is a `ScaledCanvas` and the registry has an entry.
    """
    sprite = load_hires(registry_name)
    if sprite is None:
        return canvas
    real = unwrap_to_real(canvas)
    panel_w = real.width
    panel_h = real.height

    # 1. Outgoing paints through the wrapper at logical coords.
    outgoing.draw(canvas, cursor_pos=kwargs.get("outgoing_scroll_pos", 0))

    # 2. Pick sprite frame from elapsed wall-clock time (intrinsic timing).
    duration_ms = int(kwargs.get("duration_ms", 500))
    elapsed_ms = int(t * duration_ms)
    frame_idx = _frame_for_elapsed(elapsed_ms, sprite.durations_ms)

    # 3. x-position. flip_horizontal drives both art mirroring AND
    #    traversal direction — sprite faces its travel direction.
    travel = panel_w + sprite.width
    spec = HIRES_REGISTRY[registry_name]
    if spec.flip_horizontal:
        sprite_x = panel_w - int(t * travel)
    else:
        sprite_x = -sprite.width + int(t * travel)
    sprite_y = (panel_h - sprite.height) // 2

    # 4. Paint sprite pixels to native physical canvas (skip-black).
    set_px = real.SetPixel
    for x, y, r, g, b in sprite.non_black[frame_idx]:
        rx = sprite_x + x
        if 0 <= rx < panel_w:
            set_px(rx, sprite_y + y, r, g, b)

    # 5. At t≥0.95, snap to incoming so the panel doesn't end on
    #    "outgoing-with-sprite-just-exited".
    if t >= SNAP_THRESHOLD:
        canvas.Clear()
        incoming.draw(canvas)

    return canvas
```

- [ ] **Step 4: Run loader tests, verify pass**

Run: `make test ARGS="tests/test_hires_loader.py -v"`
Expected: PASS (registry tests from Task 2 + new TestFrameForElapsed + TestLoadHires).

- [ ] **Step 5: Add render_hires_frame tests + production smoke test**

Append to `tests/test_hires_loader.py`:

```python
import unittest.mock as _mock_mod


class TestRenderHiresFrame:
    def _setup(self, tmp_path, monkeypatch):
        """Register a fixture sprite and return (real_canvas, scaled_canvas, name)."""
        from led_ticker.scaled_canvas import ScaledCanvas
        from led_ticker.transitions import _hires_registry
        from led_ticker.transitions._hires_registry import HiresSpec
        from rgbmatrix import RGBMatrix, RGBMatrixOptions

        path = _make_tiny_sprite(tmp_path)
        monkeypatch.setitem(
            _hires_registry.HIRES_REGISTRY,
            "test_sprite",
            HiresSpec(sprite_path=path, flip_horizontal=False),
        )
        opts = RGBMatrixOptions()
        opts.cols = 256
        opts.rows = 64
        opts.chain_length = 1
        opts.parallel = 1
        real = RGBMatrix(options=opts).CreateFrameCanvas()
        wrapped = ScaledCanvas(real, scale=4, content_height=16)
        return real, wrapped, "test_sprite"

    def test_paints_to_unwrapped_real_canvas(self, tmp_path, monkeypatch):
        from led_ticker.transitions._hires_loader import render_hires_frame

        real, wrapped, name = self._setup(tmp_path, monkeypatch)
        outgoing = _mock_mod.MagicMock()
        incoming = _mock_mod.MagicMock()
        render_hires_frame(0.5, wrapped, outgoing, incoming, name, duration_ms=500)

        # The fixture sprite's lit pixels should appear on the REAL canvas
        # (256-wide), not at logical wrapper coordinates (64-wide).
        lit = sum(
            1
            for x in range(real.width)
            for y in range(real.height)
            if real.get_pixel(x, y) != (0, 0, 0)
        )
        assert lit > 0
        # outgoing.draw was called through the wrapper (logical coords).
        outgoing.draw.assert_called_once()
        assert outgoing.draw.call_args.args[0] is wrapped

    def test_snaps_to_incoming_above_threshold(self, tmp_path, monkeypatch):
        from led_ticker.transitions._hires_loader import render_hires_frame

        real, wrapped, name = self._setup(tmp_path, monkeypatch)
        outgoing = _mock_mod.MagicMock()
        incoming = _mock_mod.MagicMock()
        render_hires_frame(0.96, wrapped, outgoing, incoming, name, duration_ms=500)
        incoming.draw.assert_called_once()

    def test_does_not_snap_below_threshold(self, tmp_path, monkeypatch):
        from led_ticker.transitions._hires_loader import render_hires_frame

        real, wrapped, name = self._setup(tmp_path, monkeypatch)
        outgoing = _mock_mod.MagicMock()
        incoming = _mock_mod.MagicMock()
        render_hires_frame(0.5, wrapped, outgoing, incoming, name, duration_ms=500)
        incoming.draw.assert_not_called()

    def test_clips_pixels_outside_panel_width(self, tmp_path, monkeypatch):
        from led_ticker.transitions._hires_loader import render_hires_frame

        real, wrapped, name = self._setup(tmp_path, monkeypatch)
        outgoing = _mock_mod.MagicMock()
        incoming = _mock_mod.MagicMock()
        # At t=0, sprite_x = -sprite.width — sprite is fully off-left.
        # Only the rightmost pixels (close to sprite_x + sprite.width) are
        # in [0, panel_w). After painting, no real pixel is lit at x=panel_w-1
        # with the sprite's color (sprite hasn't reached the right edge yet).
        render_hires_frame(0.0, wrapped, outgoing, incoming, name, duration_ms=500)
        # We don't assert exact lit-pixel counts here (depends on sprite
        # geometry); we only assert no crash and SetPixel never received
        # an out-of-bounds x. _StubCanvas.SetPixel itself bounds-checks
        # so a smoke run is enough.

    def test_unknown_registry_name_returns_canvas_unchanged(self, tmp_path, monkeypatch):
        from led_ticker.transitions._hires_loader import render_hires_frame

        real, wrapped, _ = self._setup(tmp_path, monkeypatch)
        outgoing = _mock_mod.MagicMock()
        incoming = _mock_mod.MagicMock()
        result = render_hires_frame(
            0.5, wrapped, outgoing, incoming, "not_in_registry", duration_ms=500
        )
        assert result is wrapped
        outgoing.draw.assert_not_called()


@pytest.mark.parametrize(
    "name", ["nyancat", "nyancat_reverse", "pokeball", "pokeball_reverse"]
)
def test_production_sprite_loads_and_fits(name):
    """Smoke test: each registered production sprite decodes successfully,
    fits within the bigsign panel, and has at least one non-black pixel."""
    from led_ticker.transitions._hires_loader import load_hires

    frames = load_hires(name)
    assert frames is not None, f"{name} not in registry"
    assert frames.height <= 64, f"{name} height {frames.height} exceeds panel_h"
    assert frames.width <= 256, f"{name} width {frames.width} exceeds panel_w"
    assert len(frames.durations_ms) >= 1
    assert any(len(f) > 0 for f in frames.non_black), (
        f"{name} has no non-black pixels in any frame"
    )
```

- [ ] **Step 6: Run all loader tests, verify pass**

Run: `make test ARGS="tests/test_hires_loader.py -v"`
Expected: PASS — every test in the file passes, including the 4 parametrized production smoke tests.

- [ ] **Step 7: Commit**

```bash
git add src/led_ticker/transitions/_hires_loader.py tests/test_hires_loader.py
git commit -m "Add hi-res transition loader: decode, cache, render helper"
```

---

### Task 4: `run_transition` passes `duration_ms` to `frame_at`

**Files:**
- Modify: `src/led_ticker/transitions/__init__.py:150-156`
- Test: `tests/test_transitions.py`

One-line wiring change so the hi-res branch can compute elapsed wall-clock time from `t`.

- [ ] **Step 1: Add a failing test**

Append to `tests/test_transitions.py`:

```python
class TestRunTransitionDurationMs:
    @pytest.mark.asyncio
    async def test_duration_ms_kwarg_passed_to_frame_at(self, mock_frame):
        """run_transition passes duration*1000 as duration_ms kwarg."""
        from led_ticker.transitions import run_transition

        captured: list[dict] = []

        class _CaptureTransition:
            min_frames = 1
            def frame_at(self, t, canvas, outgoing, incoming, **kwargs):
                captured.append(dict(kwargs))
                return canvas

        canvas = mock_frame.get_clean_canvas.return_value
        outgoing = mock.Mock()
        incoming = mock.Mock()
        await run_transition(
            canvas, mock_frame, outgoing, incoming,
            transition=_CaptureTransition(), duration=0.5,
        )
        assert captured  # at least one frame ran
        assert all(c.get("duration_ms") == 500 for c in captured)

    @pytest.mark.asyncio
    async def test_duration_ms_reflects_actual_duration(self, mock_frame):
        from led_ticker.transitions import run_transition

        captured: list[int] = []

        class _CaptureTransition:
            min_frames = 1
            def frame_at(self, t, canvas, outgoing, incoming, **kwargs):
                captured.append(kwargs.get("duration_ms"))
                return canvas

        canvas = mock_frame.get_clean_canvas.return_value
        outgoing = mock.Mock()
        incoming = mock.Mock()
        await run_transition(
            canvas, mock_frame, outgoing, incoming,
            transition=_CaptureTransition(), duration=1.25,
        )
        assert all(d == 1250 for d in captured)
```

(Verify `import unittest.mock as mock` is at the top of `test_transitions.py`; add if missing.)

- [ ] **Step 2: Run, verify failure**

Run: `make test ARGS="tests/test_transitions.py::TestRunTransitionDurationMs -v"`
Expected: FAIL — `c.get("duration_ms")` returns None (kwarg not yet passed).

- [ ] **Step 3: Add `duration_ms` to the `frame_at` call**

In `src/led_ticker/transitions/__init__.py` around line 150, modify the `transition.frame_at(...)` call:

```python
            transition.frame_at(
                t,
                active,
                outgoing,
                incoming,
                outgoing_scroll_pos=outgoing_scroll_pos,
                duration_ms=int(duration * 1000),
            )
```

- [ ] **Step 4: Run tests, verify pass**

Run: `make test ARGS="tests/test_transitions.py::TestRunTransitionDurationMs -v"`
Expected: PASS.

Also run the full transitions suite to confirm no regression:

Run: `make test ARGS="tests/test_transitions.py -v"`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/transitions/__init__.py tests/test_transitions.py
git commit -m "run_transition passes duration_ms kwarg to frame_at"
```

---

### Task 5: NyanCat + NyanCatReverse hires dispatch

**Files:**
- Modify: `src/led_ticker/transitions/nyancat.py:248-295`
- Test: `tests/test_nyancat.py`

Both classes get the same shape of edit: `_registry_name` class attr, `_frame_at_lowres` (today's body), `_frame_at_hires` (one-line delegation to `render_hires_frame`), and dispatch in `frame_at`.

- [ ] **Step 1: Add failing dispatch tests**

Append to `tests/test_nyancat.py`:

```python
class TestNyanCatDispatch:
    def test_mock_canvas_takes_lowres_path(self):
        """Mock isn't a ScaledCanvas → lowres path. Existing behavior preserved."""
        import unittest.mock as mock_mod
        from led_ticker.transitions.nyancat import NyanCat

        canvas = mock_mod.MagicMock()
        canvas.width = 160
        canvas.height = 16
        outgoing = mock_mod.MagicMock()
        incoming = mock_mod.MagicMock()

        nc = NyanCat()
        # Spy on both branches.
        with mock_mod.patch.object(
            nc, "_frame_at_lowres", wraps=nc._frame_at_lowres
        ) as lowres, mock_mod.patch.object(
            nc, "_frame_at_hires", wraps=nc._frame_at_hires
        ) as hires:
            nc.frame_at(0.5, canvas, outgoing, incoming)
            lowres.assert_called_once()
            hires.assert_not_called()

    def test_scaled_canvas_with_registered_name_takes_hires_path(self):
        import unittest.mock as mock_mod
        from led_ticker.scaled_canvas import ScaledCanvas
        from led_ticker.transitions.nyancat import NyanCat
        from rgbmatrix import RGBMatrix, RGBMatrixOptions

        opts = RGBMatrixOptions()
        opts.cols = 256
        opts.rows = 64
        opts.chain_length = 1
        opts.parallel = 1
        real = RGBMatrix(options=opts).CreateFrameCanvas()
        wrapped = ScaledCanvas(real, scale=4, content_height=16)

        outgoing = mock_mod.MagicMock()
        incoming = mock_mod.MagicMock()
        nc = NyanCat()

        with mock_mod.patch.object(
            nc, "_frame_at_lowres", wraps=nc._frame_at_lowres
        ) as lowres, mock_mod.patch.object(
            nc, "_frame_at_hires", wraps=nc._frame_at_hires
        ) as hires:
            nc.frame_at(0.5, wrapped, outgoing, incoming, duration_ms=500)
            hires.assert_called_once()
            lowres.assert_not_called()

    def test_nyancat_registry_name(self):
        from led_ticker.transitions.nyancat import NyanCat
        assert NyanCat._registry_name == "nyancat"

    def test_nyancat_reverse_registry_name(self):
        from led_ticker.transitions.nyancat import NyanCatReverse
        assert NyanCatReverse._registry_name == "nyancat_reverse"

    def test_t_above_one_snaps_to_incoming_in_either_path(self):
        """The early-return at t>=1.0 runs before dispatch, so both paths
        end on incoming.draw at t=1.0."""
        import unittest.mock as mock_mod
        from led_ticker.transitions.nyancat import NyanCat

        canvas = mock_mod.MagicMock()
        outgoing = mock_mod.MagicMock()
        incoming = mock_mod.MagicMock()
        NyanCat().frame_at(1.0, canvas, outgoing, incoming)
        incoming.draw.assert_called_once()
```

- [ ] **Step 2: Run, verify failure**

Run: `make test ARGS="tests/test_nyancat.py::TestNyanCatDispatch -v"`
Expected: FAIL — `_registry_name` doesn't exist; `_frame_at_lowres`/`_frame_at_hires` don't exist.

- [ ] **Step 3: Edit `nyancat.py` — add dispatch and split methods**

Replace the existing `NyanCat` class (around line 248) with:

```python
@register_transition("nyancat")
class NyanCat:
    """Nyan Cat flies left-to-right, rainbow fills screen before cut.

    On a `ScaledCanvas` (bigsign), dispatches to the hi-res path which
    paints a real animated sprite at native physical resolution. Lowres
    path (small sign / tests) is preserved unchanged.
    """

    _registry_name: str = "nyancat"

    def __init__(self, **kwargs: Any) -> None:
        pass

    def frame_at(
        self, t: float, canvas: Canvas, outgoing: Any, incoming: Any, **kwargs: Any
    ) -> Canvas:
        if t >= 1.0:
            incoming.draw(canvas, cursor_pos=0)
            return canvas

        from led_ticker.scaled_canvas import ScaledCanvas
        from led_ticker.transitions._hires_registry import HIRES_REGISTRY

        if isinstance(canvas, ScaledCanvas) and self._registry_name in HIRES_REGISTRY:
            return self._frame_at_hires(t, canvas, outgoing, incoming, **kwargs)
        return self._frame_at_lowres(t, canvas, outgoing, incoming, **kwargs)

    def _frame_at_lowres(
        self, t: float, canvas: Canvas, outgoing: Any, incoming: Any, **kwargs: Any
    ) -> Canvas:
        outgoing_scroll_pos: int = kwargs.get("outgoing_scroll_pos", 0)
        outgoing.draw(canvas, cursor_pos=outgoing_scroll_pos)
        draw_nyan_frame(
            canvas,
            t,
            width=canvas.width,
            height=getattr(canvas, "height", 16),
        )
        return canvas

    def _frame_at_hires(
        self, t: float, canvas: Canvas, outgoing: Any, incoming: Any, **kwargs: Any
    ) -> Canvas:
        from led_ticker.transitions._hires_loader import render_hires_frame
        return render_hires_frame(
            t, canvas, outgoing, incoming, self._registry_name, **kwargs
        )
```

And replace `NyanCatReverse` (around line 273) with the same shape:

```python
@register_transition("nyancat_reverse")
class NyanCatReverse:
    """Nyan Cat flies right-to-left, rainbow fills screen before cut."""

    _registry_name: str = "nyancat_reverse"

    def __init__(self, **kwargs: Any) -> None:
        pass

    def frame_at(
        self, t: float, canvas: Canvas, outgoing: Any, incoming: Any, **kwargs: Any
    ) -> Canvas:
        if t >= 1.0:
            incoming.draw(canvas, cursor_pos=0)
            return canvas

        from led_ticker.scaled_canvas import ScaledCanvas
        from led_ticker.transitions._hires_registry import HIRES_REGISTRY

        if isinstance(canvas, ScaledCanvas) and self._registry_name in HIRES_REGISTRY:
            return self._frame_at_hires(t, canvas, outgoing, incoming, **kwargs)
        return self._frame_at_lowres(t, canvas, outgoing, incoming, **kwargs)

    def _frame_at_lowres(
        self, t: float, canvas: Canvas, outgoing: Any, incoming: Any, **kwargs: Any
    ) -> Canvas:
        outgoing_scroll_pos: int = kwargs.get("outgoing_scroll_pos", 0)
        outgoing.draw(canvas, cursor_pos=outgoing_scroll_pos)
        draw_nyan_frame_rtl(
            canvas,
            t,
            width=canvas.width,
            height=getattr(canvas, "height", 16),
        )
        return canvas

    def _frame_at_hires(
        self, t: float, canvas: Canvas, outgoing: Any, incoming: Any, **kwargs: Any
    ) -> Canvas:
        from led_ticker.transitions._hires_loader import render_hires_frame
        return render_hires_frame(
            t, canvas, outgoing, incoming, self._registry_name, **kwargs
        )
```

(`NyanCatAlternating` at line 298 is unchanged — it delegates to the two classes above, dispatch happens inside each delegated call.)

- [ ] **Step 4: Run nyancat tests, verify pass**

Run: `make test ARGS="tests/test_nyancat.py -v"`
Expected: PASS — all existing tests (TestNyanCatSprite etc.) plus the new `TestNyanCatDispatch` (5 tests).

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/transitions/nyancat.py tests/test_nyancat.py
git commit -m "NyanCat + NyanCatReverse dispatch hi-res path on ScaledCanvas"
```

---

### Task 6: Pokeball + PokeballReverse hires dispatch

**Files:**
- Modify: `src/led_ticker/transitions/pokeball.py:816-869`
- Test: `tests/test_pokeball.py`

Same pattern as Task 5. The existing classes have `min_frames = 40` and a `show_pikachu` constructor kwarg — preserve both.

- [ ] **Step 1: Add failing dispatch tests**

Append to `tests/test_pokeball.py`:

```python
class TestPokeballDispatch:
    def test_mock_canvas_takes_lowres_path(self):
        import unittest.mock as mock_mod
        from led_ticker.transitions.pokeball import Pokeball

        canvas = mock_mod.MagicMock()
        canvas.width = 160
        canvas.height = 16
        outgoing = mock_mod.MagicMock()
        incoming = mock_mod.MagicMock()
        pb = Pokeball()
        with mock_mod.patch.object(
            pb, "_frame_at_lowres", wraps=pb._frame_at_lowres
        ) as lowres, mock_mod.patch.object(
            pb, "_frame_at_hires", wraps=pb._frame_at_hires
        ) as hires:
            pb.frame_at(0.5, canvas, outgoing, incoming)
            lowres.assert_called_once()
            hires.assert_not_called()

    def test_scaled_canvas_takes_hires_path(self):
        import unittest.mock as mock_mod
        from led_ticker.scaled_canvas import ScaledCanvas
        from led_ticker.transitions.pokeball import Pokeball
        from rgbmatrix import RGBMatrix, RGBMatrixOptions

        opts = RGBMatrixOptions()
        opts.cols = 256
        opts.rows = 64
        opts.chain_length = 1
        opts.parallel = 1
        real = RGBMatrix(options=opts).CreateFrameCanvas()
        wrapped = ScaledCanvas(real, scale=4, content_height=16)
        outgoing = mock_mod.MagicMock()
        incoming = mock_mod.MagicMock()
        pb = Pokeball()
        with mock_mod.patch.object(
            pb, "_frame_at_lowres", wraps=pb._frame_at_lowres
        ) as lowres, mock_mod.patch.object(
            pb, "_frame_at_hires", wraps=pb._frame_at_hires
        ) as hires:
            pb.frame_at(0.5, wrapped, outgoing, incoming, duration_ms=500)
            hires.assert_called_once()
            lowres.assert_not_called()

    def test_pokeball_registry_name(self):
        from led_ticker.transitions.pokeball import Pokeball
        assert Pokeball._registry_name == "pokeball"

    def test_pokeball_reverse_registry_name(self):
        from led_ticker.transitions.pokeball import PokeballReverse
        assert PokeballReverse._registry_name == "pokeball_reverse"

    def test_show_pikachu_kwarg_preserved(self):
        """The existing show_pikachu constructor kwarg still works."""
        from led_ticker.transitions.pokeball import Pokeball
        p1 = Pokeball(show_pikachu=False)
        assert p1._show_pikachu is False
        p2 = Pokeball(show_pikachu=True)
        assert p2._show_pikachu is True

    def test_min_frames_preserved(self):
        from led_ticker.transitions.pokeball import Pokeball
        assert Pokeball.min_frames == 40
```

- [ ] **Step 2: Run, verify failure**

Run: `make test ARGS="tests/test_pokeball.py::TestPokeballDispatch -v"`
Expected: FAIL — `_registry_name` / `_frame_at_lowres` / `_frame_at_hires` don't exist.

- [ ] **Step 3: Edit `pokeball.py` — add dispatch and split methods**

Replace `Pokeball` (around line 816) with:

```python
@register_transition("pokeball")
class Pokeball:
    """Pokeball rolls left-to-right, erasing outgoing content.

    On a `ScaledCanvas` (bigsign), dispatches to the hi-res path which
    paints a real animated Pikachu sprite at native physical resolution.
    """

    min_frames: int = 40
    _registry_name: str = "pokeball"

    def __init__(self, show_pikachu: bool = True, **kwargs: Any) -> None:
        self._show_pikachu = show_pikachu

    def frame_at(
        self, t: float, canvas: Canvas, outgoing: Any, incoming: Any, **kwargs: Any
    ) -> Canvas:
        if t >= 1.0:
            incoming.draw(canvas, cursor_pos=0)
            return canvas

        from led_ticker.scaled_canvas import ScaledCanvas
        from led_ticker.transitions._hires_registry import HIRES_REGISTRY

        if isinstance(canvas, ScaledCanvas) and self._registry_name in HIRES_REGISTRY:
            return self._frame_at_hires(t, canvas, outgoing, incoming, **kwargs)
        return self._frame_at_lowres(t, canvas, outgoing, incoming, **kwargs)

    def _frame_at_lowres(
        self, t: float, canvas: Canvas, outgoing: Any, incoming: Any, **kwargs: Any
    ) -> Canvas:
        outgoing_scroll_pos: int = kwargs.get("outgoing_scroll_pos", 0)
        outgoing.draw(canvas, cursor_pos=outgoing_scroll_pos)
        draw_pokeball_frame(
            canvas,
            t,
            width=canvas.width,
            height=getattr(canvas, "height", 16),
            show_pikachu=self._show_pikachu,
        )
        return canvas

    def _frame_at_hires(
        self, t: float, canvas: Canvas, outgoing: Any, incoming: Any, **kwargs: Any
    ) -> Canvas:
        from led_ticker.transitions._hires_loader import render_hires_frame
        return render_hires_frame(
            t, canvas, outgoing, incoming, self._registry_name, **kwargs
        )
```

And replace `PokeballReverse` (around line 844) with the same shape, swapping `_registry_name = "pokeball_reverse"` and calling `draw_pokeball_frame_rtl` in lowres:

```python
@register_transition("pokeball_reverse")
class PokeballReverse:
    """Pokeball rolls right-to-left, erasing outgoing content."""

    min_frames: int = 40
    _registry_name: str = "pokeball_reverse"

    def __init__(self, show_pikachu: bool = True, **kwargs: Any) -> None:
        self._show_pikachu = show_pikachu

    def frame_at(
        self, t: float, canvas: Canvas, outgoing: Any, incoming: Any, **kwargs: Any
    ) -> Canvas:
        if t >= 1.0:
            incoming.draw(canvas, cursor_pos=0)
            return canvas

        from led_ticker.scaled_canvas import ScaledCanvas
        from led_ticker.transitions._hires_registry import HIRES_REGISTRY

        if isinstance(canvas, ScaledCanvas) and self._registry_name in HIRES_REGISTRY:
            return self._frame_at_hires(t, canvas, outgoing, incoming, **kwargs)
        return self._frame_at_lowres(t, canvas, outgoing, incoming, **kwargs)

    def _frame_at_lowres(
        self, t: float, canvas: Canvas, outgoing: Any, incoming: Any, **kwargs: Any
    ) -> Canvas:
        outgoing_scroll_pos: int = kwargs.get("outgoing_scroll_pos", 0)
        outgoing.draw(canvas, cursor_pos=outgoing_scroll_pos)
        draw_pokeball_frame_rtl(
            canvas,
            t,
            width=canvas.width,
            height=getattr(canvas, "height", 16),
            show_pikachu=self._show_pikachu,
        )
        return canvas

    def _frame_at_hires(
        self, t: float, canvas: Canvas, outgoing: Any, incoming: Any, **kwargs: Any
    ) -> Canvas:
        from led_ticker.transitions._hires_loader import render_hires_frame
        return render_hires_frame(
            t, canvas, outgoing, incoming, self._registry_name, **kwargs
        )
```

(`PokeballAlternating` at line 872 is unchanged.)

- [ ] **Step 4: Run pokeball tests, verify pass**

Run: `make test ARGS="tests/test_pokeball.py -v"`
Expected: PASS — all existing tests + 6 new dispatch tests.

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/transitions/pokeball.py tests/test_pokeball.py
git commit -m "Pokeball + PokeballReverse dispatch hi-res path on ScaledCanvas"
```

---

### Task 7: End-to-end alternating + full-suite check

**Files:**
- Modify: `tests/test_nyancat.py` (add one test)
- Modify: `tests/test_pokeball.py` (add one test)

Verify alternating variants pick hi-res automatically through delegation. No source changes.

- [ ] **Step 1: Add alternating-delegates-to-hires tests**

Append to `tests/test_nyancat.py`:

```python
class TestNyanCatAlternatingDelegatesToHires:
    def test_alternating_picks_hires_when_scaled_canvas(self):
        """nyancat_alternating dispatches each call to base/reverse,
        which then independently pick hires on a ScaledCanvas."""
        import unittest.mock as mock_mod
        from led_ticker.scaled_canvas import ScaledCanvas
        from led_ticker.transitions.nyancat import NyanCatAlternating
        from rgbmatrix import RGBMatrix, RGBMatrixOptions

        opts = RGBMatrixOptions()
        opts.cols = 256
        opts.rows = 64
        opts.chain_length = 1
        opts.parallel = 1
        real = RGBMatrix(options=opts).CreateFrameCanvas()
        wrapped = ScaledCanvas(real, scale=4, content_height=16)
        outgoing = mock_mod.MagicMock()
        incoming = mock_mod.MagicMock()

        alt = NyanCatAlternating()
        # First swap: forward variant.
        with mock_mod.patch.object(
            alt._transitions[0], "_frame_at_hires",
            wraps=alt._transitions[0]._frame_at_hires,
        ) as fwd_hires:
            alt.frame_at(0.5, wrapped, outgoing, incoming, duration_ms=500)
            fwd_hires.assert_called_once()
```

Append to `tests/test_pokeball.py`:

```python
class TestPokeballAlternatingDelegatesToHires:
    def test_alternating_picks_hires_when_scaled_canvas(self):
        import unittest.mock as mock_mod
        from led_ticker.scaled_canvas import ScaledCanvas
        from led_ticker.transitions.pokeball import PokeballAlternating
        from rgbmatrix import RGBMatrix, RGBMatrixOptions

        opts = RGBMatrixOptions()
        opts.cols = 256
        opts.rows = 64
        opts.chain_length = 1
        opts.parallel = 1
        real = RGBMatrix(options=opts).CreateFrameCanvas()
        wrapped = ScaledCanvas(real, scale=4, content_height=16)
        outgoing = mock_mod.MagicMock()
        incoming = mock_mod.MagicMock()

        alt = PokeballAlternating()
        with mock_mod.patch.object(
            alt._transitions[0], "_frame_at_hires",
            wraps=alt._transitions[0]._frame_at_hires,
        ) as fwd_hires:
            alt.frame_at(0.5, wrapped, outgoing, incoming, duration_ms=500)
            fwd_hires.assert_called_once()
```

- [ ] **Step 2: Run alternating tests, verify pass**

Run: `make test ARGS="tests/test_nyancat.py::TestNyanCatAlternatingDelegatesToHires tests/test_pokeball.py::TestPokeballAlternatingDelegatesToHires -v"`
Expected: PASS.

- [ ] **Step 3: Run the full suite to confirm no regressions**

Run: `make test`
Expected: PASS — all ~830+ existing tests + ~25-30 new tests for hi-res transitions.

If `test_nyancat_alternating_alternates` or any existing test fails, the lowres dispatch path was disturbed — re-read the diff against `_frame_at_lowres`. The lowres body must be byte-identical to today's `frame_at` body.

- [ ] **Step 4: Run lint**

Run: `make lint`
Expected: 0 ruff warnings.

- [ ] **Step 5: Commit**

```bash
git add tests/test_nyancat.py tests/test_pokeball.py
git commit -m "Verify nyancat_alternating + pokeball_alternating hit hi-res path"
```

---

## Done — final checks

After all 7 tasks land:

- [ ] `make test` — full suite green (~860 tests).
- [ ] `make lint` — clean.
- [ ] On the bigsign Pi, write a small TOML config that uses `transition = "nyancat"` and `transition = "pokeball"` (and the alternating variants), then visually confirm the hi-res sprites animate correctly during section transitions. Same config on the small sign should still show the lowres versions (regression-free).

Optional follow-up (NOT in this plan): add a `:moon_bunny:` / `:pikachu:` / `:nyancat:` family of hi-res EMOJI to complement the hi-res transitions — separate spec, separate plan.
