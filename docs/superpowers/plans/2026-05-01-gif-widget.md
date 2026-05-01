# GIF Widget Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `type = "gif"` widget + `mode = "gif"` section orchestrator that displays animated GIFs at the panel's native physical resolution, looping a configurable number of times then transitioning out.

**Architecture:** A pure `decode_gif` helper handles Pillow decoding + fit-mode resizing. `GifPlayer` widget owns the per-frame pixel data and exposes `draw()` (paints current frame for transition compositing) and `play()` (the async playback loop). New `Ticker.run_gif()` orchestrator drives playback. `app.py` resolves config-relative `path` values before widget construction.

**Tech Stack:** Python, Pillow ≥10 (already a dep), asyncio, attrs, pytest, rgbmatrix (real on Pi 5, stub locally).

---

## Task 0: Setup — copy test GIF + create assets dir

**Files:**
- Create: `config/assets/.gitkeep`
- Create: `config/assets/pika_wave.gif` (copied from user's Desktop)

- [ ] **Step 1: Verify on the gif-widget branch**

Run: `git status`
Expected: `On branch gif-widget`. If not, run `git checkout gif-widget`.

- [ ] **Step 2: Create assets directory and copy the test GIF**

Run:
```bash
mkdir -p config/assets
cp ~/Desktop/pika_wave.gif config/assets/pika_wave.gif
touch config/assets/.gitkeep
```

- [ ] **Step 3: Verify the file exists and is a valid GIF**

Run:
```bash
file config/assets/pika_wave.gif
PYTHONPATH=tests/stubs uv run python -c "from PIL import Image; img = Image.open('config/assets/pika_wave.gif'); print('frames:', img.n_frames, 'size:', img.size)"
```
Expected: file output reports `GIF image data`; Python output prints frame count and (W, H) size.

- [ ] **Step 4: Commit**

```bash
git add config/assets/
git commit -m "Add test GIF (pika_wave.gif) for the gif widget"
```

---

## Task 1: `decode_gif` pure helper

**Files:**
- Create: `src/led_ticker/widgets/_gif_decode.py`
- Create: `tests/test_widgets/test_gif_decode.py`

- [ ] **Step 1: Write failing tests for `decode_gif`**

Create `tests/test_widgets/test_gif_decode.py`:

```python
"""Tests for the pure decode_gif helper."""

from __future__ import annotations

import io

import pytest
from PIL import Image

from led_ticker.widgets._gif_decode import decode_gif


def _make_gif(
    frames: list[tuple[int, int, int]],
    size: tuple[int, int] = (32, 32),
    duration_ms: int = 100,
) -> io.BytesIO:
    """Build an in-memory GIF with `len(frames)` solid-color frames."""
    images = [Image.new("RGB", size, color=c) for c in frames]
    buf = io.BytesIO()
    images[0].save(
        buf,
        format="GIF",
        save_all=True,
        append_images=images[1:],
        duration=duration_ms,
        loop=0,
    )
    buf.seek(0)
    return buf


def test_decode_returns_one_entry_per_frame(tmp_path):
    path = tmp_path / "two.gif"
    path.write_bytes(_make_gif([(255, 0, 0), (0, 255, 0)]).getvalue())

    frames = decode_gif(path, panel_w=256, panel_h=64, fit="stretch")

    assert len(frames) == 2
    for pixels, duration in frames:
        assert isinstance(pixels, bytes)
        assert len(pixels) == 256 * 64 * 3  # rgb
        assert duration == 100


def test_stretch_fills_full_canvas_with_input_color(tmp_path):
    path = tmp_path / "red.gif"
    path.write_bytes(_make_gif([(200, 30, 40)]).getvalue())

    [(pixels, _)] = decode_gif(path, panel_w=256, panel_h=64, fit="stretch")

    # Every pixel should be the source red
    assert pixels[0:3] == bytes((200, 30, 40))
    assert pixels[-3:] == bytes((200, 30, 40))


def test_pillarbox_centers_square_with_black_bands(tmp_path):
    # Square 32×32 GIF in pillarbox mode: scale by height to 64, gives
    # 64×64 centered horizontally on the 256×64 canvas.
    path = tmp_path / "sq.gif"
    path.write_bytes(_make_gif([(255, 255, 255)], size=(32, 32)).getvalue())

    [(pixels, _)] = decode_gif(path, panel_w=256, panel_h=64, fit="pillarbox")

    def px(x: int, y: int) -> tuple[int, int, int]:
        i = (y * 256 + x) * 3
        return (pixels[i], pixels[i + 1], pixels[i + 2])

    # Left/right pillars are black
    assert px(0, 32) == (0, 0, 0)
    assert px(255, 32) == (0, 0, 0)
    # Center area is white
    assert px(128, 32) == (255, 255, 255)


def test_letterbox_centers_wide_with_black_bands(tmp_path):
    # 256×32 GIF in letterbox: scale by width to 256, gives 256×32
    # centered vertically (black bands top + bottom).
    path = tmp_path / "wide.gif"
    path.write_bytes(_make_gif([(120, 200, 255)], size=(256, 32)).getvalue())

    [(pixels, _)] = decode_gif(path, panel_w=256, panel_h=64, fit="letterbox")

    def px(x: int, y: int) -> tuple[int, int, int]:
        i = (y * 256 + x) * 3
        return (pixels[i], pixels[i + 1], pixels[i + 2])

    # Top + bottom rows are black
    assert px(128, 0) == (0, 0, 0)
    assert px(128, 63) == (0, 0, 0)
    # Middle row is the input color
    assert px(128, 32) == (120, 200, 255)


def test_crop_fills_canvas_with_no_black(tmp_path):
    # Square 64×64 source in crop mode covers 256×64 by scaling to
    # 256×256 then cropping vertically. Every output pixel is white.
    path = tmp_path / "sq.gif"
    path.write_bytes(_make_gif([(255, 255, 255)], size=(64, 64)).getvalue())

    [(pixels, _)] = decode_gif(path, panel_w=256, panel_h=64, fit="crop")

    # No pixel should be black
    for i in range(0, len(pixels), 3):
        assert (pixels[i], pixels[i + 1], pixels[i + 2]) == (255, 255, 255)


def test_zero_duration_is_clamped(tmp_path):
    path = tmp_path / "fast.gif"
    path.write_bytes(_make_gif([(0, 0, 0)], duration_ms=0).getvalue())

    frames = decode_gif(path, panel_w=256, panel_h=64, fit="stretch")
    assert frames[0][1] >= 50  # clamped to ≥50 ms


def test_unknown_fit_raises(tmp_path):
    path = tmp_path / "x.gif"
    path.write_bytes(_make_gif([(0, 0, 0)]).getvalue())

    with pytest.raises(ValueError, match="fit"):
        decode_gif(path, panel_w=256, panel_h=64, fit="weird")


def test_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        decode_gif(tmp_path / "nope.gif", panel_w=256, panel_h=64, fit="stretch")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_widgets/test_gif_decode.py -v`
Expected: All 7 tests FAIL with `ModuleNotFoundError: No module named 'led_ticker.widgets._gif_decode'`.

- [ ] **Step 3: Implement `decode_gif`**

Create `src/led_ticker/widgets/_gif_decode.py`:

```python
"""GIF decoding helper — pure function, no side effects.

Reads an animated GIF, applies a fit mode, and returns a list of
(rgb_bytes, duration_ms) tuples ready to be SetPixel-blitted to the
panel.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

_VALID_FITS: frozenset[str] = frozenset(
    {"pillarbox", "letterbox", "stretch", "crop"}
)
_MIN_FRAME_DURATION_MS = 50


def decode_gif(
    path: Path,
    panel_w: int,
    panel_h: int,
    fit: str,
) -> list[tuple[bytes, int]]:
    """Decode an animated GIF and return per-frame RGB bytes + durations.

    `fit` controls how each frame is scaled to fit the panel's
    `panel_w × panel_h`:

    - ``pillarbox``: scale by height (or width, whichever is the more
      restrictive constraint), center the result on a black canvas.
      Most common for square / portrait sources on a wide panel.
    - ``letterbox``: scale by width, center vertically with black bars.
    - ``stretch``: resize directly, distorting aspect ratio.
    - ``crop``: scale to cover both axes, center-crop the excess.

    Frame durations below 50 ms are clamped to 50 ms (some GIFs encode
    `duration=0` which would otherwise spin the playback loop).
    """
    if fit not in _VALID_FITS:
        raise ValueError(
            f"unknown fit={fit!r}; expected one of {sorted(_VALID_FITS)}"
        )

    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"GIF not found at {path}")

    frames: list[tuple[bytes, int]] = []
    with Image.open(path) as img:
        n = getattr(img, "n_frames", 1)
        for i in range(n):
            img.seek(i)
            rgb = img.convert("RGB")
            fitted = _apply_fit(rgb, panel_w, panel_h, fit)
            duration = max(_MIN_FRAME_DURATION_MS, int(img.info.get("duration", 100)))
            frames.append((fitted.tobytes(), duration))
    return frames


def _apply_fit(
    src: Image.Image, panel_w: int, panel_h: int, fit: str
) -> Image.Image:
    """Scale + place `src` onto a `panel_w × panel_h` black canvas."""
    sw, sh = src.size
    if fit == "stretch":
        return src.resize((panel_w, panel_h), Image.Resampling.LANCZOS)

    if fit == "crop":
        scale = max(panel_w / sw, panel_h / sh)
        new_w = max(panel_w, int(round(sw * scale)))
        new_h = max(panel_h, int(round(sh * scale)))
        scaled = src.resize((new_w, new_h), Image.Resampling.LANCZOS)
        x0 = (new_w - panel_w) // 2
        y0 = (new_h - panel_h) // 2
        return scaled.crop((x0, y0, x0 + panel_w, y0 + panel_h))

    # pillarbox / letterbox both fit-by-axis with black bands.
    # `pillarbox` prefers height; `letterbox` prefers width.
    if fit == "pillarbox":
        scale = panel_h / sh
        if int(round(sw * scale)) > panel_w:
            scale = panel_w / sw  # fall back to width-fit if width would overflow
    else:  # letterbox
        scale = panel_w / sw
        if int(round(sh * scale)) > panel_h:
            scale = panel_h / sh

    new_w = max(1, int(round(sw * scale)))
    new_h = max(1, int(round(sh * scale)))
    scaled = src.resize((new_w, new_h), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (panel_w, panel_h), color=(0, 0, 0))
    canvas.paste(scaled, ((panel_w - new_w) // 2, (panel_h - new_h) // 2))
    return canvas
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_widgets/test_gif_decode.py -v`
Expected: 7 PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/widgets/_gif_decode.py tests/test_widgets/test_gif_decode.py
git commit -m "Add decode_gif helper with pillarbox/letterbox/stretch/crop fits"
```

---

## Task 2: `GifPlayer` widget — `_load()` and `draw()`

**Files:**
- Create: `src/led_ticker/widgets/gif.py`
- Modify: `src/led_ticker/widgets/__init__.py` (add the import)
- Create: `tests/test_widgets/test_gif.py`

- [ ] **Step 1: Write failing tests for `_load()` + `draw()`**

Create `tests/test_widgets/test_gif.py`:

```python
"""Tests for the :gif: widget — _load() lazy decode + draw() compositing."""

from __future__ import annotations

import io

import pytest
from PIL import Image
from rgbmatrix import RGBMatrix, RGBMatrixOptions

from led_ticker.scaled_canvas import ScaledCanvas
from led_ticker.widgets.gif import GifPlayer


def _make_gif_path(tmp_path, frames, size=(32, 32), duration_ms=100):
    images = [Image.new("RGB", size, color=c) for c in frames]
    buf = io.BytesIO()
    images[0].save(
        buf,
        format="GIF",
        save_all=True,
        append_images=images[1:],
        duration=duration_ms,
        loop=0,
    )
    p = tmp_path / "test.gif"
    p.write_bytes(buf.getvalue())
    return p


def _bigsign_real_canvas():
    opts = RGBMatrixOptions()
    opts.cols = 64
    opts.rows = 32
    opts.chain_length = 8
    opts.parallel = 1
    opts.pixel_mapper_config = "U-mapper"
    return RGBMatrix(options=opts).CreateFrameCanvas()


def test_load_decodes_lazily(tmp_path):
    path = _make_gif_path(tmp_path, [(255, 0, 0), (0, 255, 0)])
    widget = GifPlayer(path=str(path), fit="stretch")
    assert widget._frames == []  # not loaded yet
    widget._load()
    assert len(widget._frames) == 2
    # Idempotent
    widget._load()
    assert len(widget._frames) == 2


def test_draw_paints_first_frame_to_real_canvas(tmp_path):
    path = _make_gif_path(tmp_path, [(200, 30, 40)])
    widget = GifPlayer(path=str(path), fit="stretch")
    real = _bigsign_real_canvas()

    canvas, advance = widget.draw(real, cursor_pos=0)

    # advance is the panel width — the widget claims the whole row
    assert advance == real.width
    # Lit pixels should match the source color
    assert real.get_pixel(0, 0) != (0, 0, 0)
    assert real.get_pixel(real.width - 1, real.height - 1) != (0, 0, 0)


def test_draw_unwraps_scaled_canvas(tmp_path):
    """ScaledCanvas wrapper must be bypassed so the GIF paints at native
    physical resolution, not as scale×scale blocks."""
    path = _make_gif_path(tmp_path, [(255, 255, 0)])
    widget = GifPlayer(path=str(path), fit="stretch")
    real = _bigsign_real_canvas()
    sc = ScaledCanvas(real, scale=4)

    canvas, advance = widget.draw(sc, cursor_pos=0)

    # advance is the SCALED canvas's width (logical), which is what
    # the layout system expects from any widget.
    assert advance == sc.width
    # The hi-res sprite painted directly to `real` — pixel at col 1
    # (NOT divisible by scale=4) should be lit, proving we bypassed
    # the wrapper.
    assert real.get_pixel(1, 1) != (0, 0, 0)


def test_draw_paints_current_frame_after_play(tmp_path):
    """After `play()` advances the frame index, draw() should paint the
    new current frame, not frame 0."""
    path = _make_gif_path(tmp_path, [(200, 0, 0), (0, 200, 0)])
    widget = GifPlayer(path=str(path), fit="stretch")
    widget._load()
    widget._current_frame_idx = 1  # simulate end-of-play state

    real = _bigsign_real_canvas()
    widget.draw(real, cursor_pos=0)

    # Pixel should reflect frame 1 (green), not frame 0 (red)
    r, g, b = real.get_pixel(real.width // 2, real.height // 2)
    assert g > r  # green-dominant


def test_missing_file_raises_at_load(tmp_path):
    widget = GifPlayer(path=str(tmp_path / "nope.gif"), fit="stretch")
    with pytest.raises(FileNotFoundError):
        widget._load()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_widgets/test_gif.py -v`
Expected: All 5 tests FAIL with `ModuleNotFoundError: No module named 'led_ticker.widgets.gif'`.

- [ ] **Step 3: Implement `GifPlayer` with `_load()` and `draw()`**

Create `src/led_ticker/widgets/gif.py`:

```python
"""GIF player widget — displays an animated GIF on the LED panel as
if it were a small monitor.

The widget lazily decodes all frames on first use, paints the current
frame directly to the underlying real canvas (bypassing ScaledCanvas
so each pixel is a native LED, not a scale×scale block), and exposes
an async `play()` method that drives the per-frame playback loop.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import attrs

from led_ticker._types import Canvas, DrawResult
from led_ticker.widgets import register
from led_ticker.widgets._gif_decode import decode_gif


@register("gif")
@attrs.define
class GifPlayer:
    """Animated-GIF widget. See `mode = "gif"` for orchestration."""

    path: str
    fit: str = "pillarbox"
    padding: int = 0  # required by widget protocol; unused here

    _frames: list[tuple[bytes, int]] = attrs.field(init=False, factory=list)
    _current_frame_idx: int = attrs.field(init=False, default=0)
    _panel_w: int = attrs.field(init=False, default=0)
    _panel_h: int = attrs.field(init=False, default=0)

    def _real_canvas(self, canvas: Canvas) -> Canvas:
        """Unwrap ScaledCanvas so we paint native physical pixels."""
        return getattr(canvas, "real", canvas)

    def _load(self, panel_w: int = 0, panel_h: int = 0) -> None:
        """Decode all frames. Idempotent — second call is a no-op."""
        if self._frames:
            return
        # Default to bigsign physical dims; tests/callers can override
        # before the first call by setting _panel_w/_panel_h.
        if panel_w <= 0:
            panel_w = self._panel_w or 256
        if panel_h <= 0:
            panel_h = self._panel_h or 64
        self._panel_w = panel_w
        self._panel_h = panel_h
        self._frames = decode_gif(
            Path(self.path), panel_w=panel_w, panel_h=panel_h, fit=self.fit
        )

    def draw(
        self, canvas: Canvas, cursor_pos: int = 0, **kwargs: Any
    ) -> DrawResult:
        """Paint the current frame to the real canvas at native res.

        Returns `(canvas, canvas.width)` so the widget claims the full
        row — the framework treats GIFs as full-screen takeovers.
        """
        del cursor_pos, kwargs  # unused

        real = self._real_canvas(canvas)
        # Lazy load using the real canvas's physical dimensions
        self._load(panel_w=real.width, panel_h=real.height)

        if not self._frames:
            return canvas, canvas.width

        pixels, _ = self._frames[self._current_frame_idx]
        w = real.width
        h = real.height
        set_px = real.SetPixel
        for y in range(h):
            row = y * w * 3
            for x in range(w):
                base = row + x * 3
                set_px(x, y, pixels[base], pixels[base + 1], pixels[base + 2])
        return canvas, canvas.width

    async def play(
        self,
        real_canvas: Canvas,
        frame: Any,
        loop_count: int = 1,
    ) -> Canvas:
        """Run the playback loop. Implemented in Task 3."""
        # NOTE: implementation lives in the next task — tests are
        # additive so this stub never has to pass any tests.
        raise NotImplementedError
```

- [ ] **Step 4: Wire the widget into the registry by importing it**

Find the line in `src/led_ticker/widgets/__init__.py` where other widgets are auto-imported (look for `from led_ticker.widgets.message import` or similar).

Add (alphabetical placement is fine):

```python
from led_ticker.widgets.gif import GifPlayer  # noqa: F401
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_widgets/test_gif.py -v`
Expected: 5 PASSED.

- [ ] **Step 6: Run the full suite to make sure no regressions**

Run: `PYTHONPATH=tests/stubs uv run pytest 2>&1 | tail -3`
Expected: ` … passed, 1 skipped …` with NO failures.

- [ ] **Step 7: Commit**

```bash
git add src/led_ticker/widgets/gif.py src/led_ticker/widgets/__init__.py tests/test_widgets/test_gif.py
git commit -m "Add GifPlayer widget — _load() + draw() (single frame)"
```

---

## Task 3: `GifPlayer.play()` async loop

**Files:**
- Modify: `src/led_ticker/widgets/gif.py:65-72` (replace the `play()` stub)
- Modify: `tests/test_widgets/test_gif.py` (add play() tests)

- [ ] **Step 1: Add tests for `play()` in `tests/test_widgets/test_gif.py`**

Append these tests to the bottom of the test file:

```python
async def test_play_loops_through_frames(tmp_path, mocker):
    path = _make_gif_path(tmp_path, [(255, 0, 0), (0, 255, 0)], duration_ms=10)
    widget = GifPlayer(path=str(path), fit="stretch")
    real = _bigsign_real_canvas()

    # Stub frame.matrix.SwapOnVSync to return a fresh canvas each call —
    # mirrors the real-stub tripwire from CLAUDE.md #1 / conftest.py.
    frame = mocker.MagicMock()
    swap_returns = []
    def fake_swap(c):
        new = type(real)(width=real.width, height=real.height)
        swap_returns.append(new)
        return new
    frame.matrix.SwapOnVSync.side_effect = fake_swap

    # Stub asyncio.sleep so the test runs instantly
    mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

    final = await widget.play(real, frame, loop_count=2)

    # 2 loops × 2 frames = 4 swaps
    assert frame.matrix.SwapOnVSync.call_count == 4
    # Final canvas is whatever the last swap returned (drop-capture
    # regression: we MUST capture the swap return value)
    assert final is swap_returns[-1]
    # _current_frame_idx left at the last frame
    assert widget._current_frame_idx == 1


async def test_play_clamps_zero_loop_count_to_one(tmp_path, mocker):
    path = _make_gif_path(tmp_path, [(50, 50, 50)], duration_ms=10)
    widget = GifPlayer(path=str(path), fit="stretch")
    real = _bigsign_real_canvas()
    frame = mocker.MagicMock()
    frame.matrix.SwapOnVSync.side_effect = lambda c: c
    mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

    await widget.play(real, frame, loop_count=0)

    # Treated as "play once"
    assert frame.matrix.SwapOnVSync.call_count == 1


async def test_play_uses_per_frame_durations(tmp_path, mocker):
    path = _make_gif_path(tmp_path, [(0, 0, 0), (0, 0, 0)], duration_ms=120)
    widget = GifPlayer(path=str(path), fit="stretch")
    real = _bigsign_real_canvas()
    frame = mocker.MagicMock()
    frame.matrix.SwapOnVSync.side_effect = lambda c: c

    sleep_mock = mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

    await widget.play(real, frame, loop_count=1)

    # Each frame's duration was 120ms → 0.12s passed to asyncio.sleep
    sleeps = [c.args[0] for c in sleep_mock.await_args_list]
    assert all(abs(s - 0.12) < 1e-6 for s in sleeps)
    assert len(sleeps) == 2
```

- [ ] **Step 2: Run new tests to confirm they fail**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_widgets/test_gif.py -v`
Expected: 3 NEW FAILUREs (`NotImplementedError`); the previous 5 still PASS.

- [ ] **Step 3: Implement `play()`**

Replace the `play()` stub in `src/led_ticker/widgets/gif.py` (the `raise NotImplementedError` at the bottom) with:

```python
    async def play(
        self,
        real_canvas: Canvas,
        frame: Any,
        loop_count: int = 1,
    ) -> Canvas:
        """Run the playback loop: paint each frame, swap, sleep,
        repeat for `loop_count` complete loops.

        Returns the back-buffer canvas left after the final swap so
        the caller (Ticker) can keep using it. Per CLAUDE.md #1, the
        SwapOnVSync return value MUST be captured every iteration.
        """
        self._load(panel_w=real_canvas.width, panel_h=real_canvas.height)
        if not self._frames:
            return real_canvas

        loops = max(1, loop_count)
        canvas = real_canvas
        w = canvas.width
        h = canvas.height

        for _ in range(loops):
            for pixels, duration_ms in self._frames:
                canvas.Clear()
                set_px = canvas.SetPixel
                for y in range(h):
                    row = y * w * 3
                    for x in range(w):
                        base = row + x * 3
                        set_px(
                            x,
                            y,
                            pixels[base],
                            pixels[base + 1],
                            pixels[base + 2],
                        )
                canvas = frame.matrix.SwapOnVSync(canvas)
                await asyncio.sleep(duration_ms / 1000)

        # Land on the last frame so subsequent draw() calls (for the
        # exit transition's compositing) paint it.
        self._current_frame_idx = len(self._frames) - 1
        return canvas
```

- [ ] **Step 4: Run all gif tests**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_widgets/test_gif.py -v`
Expected: 8 PASSED.

- [ ] **Step 5: Run the full suite for regressions**

Run: `PYTHONPATH=tests/stubs uv run pytest 2>&1 | tail -3`
Expected: passes with no new failures.

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/widgets/gif.py tests/test_widgets/test_gif.py
git commit -m "Implement GifPlayer.play() — async per-frame playback loop"
```

---

## Task 4: `Ticker.run_gif()` orchestrator + `RUN_MODES` entry

**Files:**
- Modify: `src/led_ticker/ticker.py` (add `run_gif()` method + `_run_gif()` helper)
- Modify: `src/led_ticker/app.py:122-126` (add to `RUN_MODES`)
- Modify: `tests/test_ticker_display.py` or new `tests/test_run_gif.py` (smoke test)

- [ ] **Step 1: Write a smoke test for the run_gif orchestrator**

Create `tests/test_run_gif.py`:

```python
"""Smoke test for Ticker.run_gif() — pulls a GifPlayer from the queue
and calls its play() method on the underlying real canvas."""

from __future__ import annotations

import asyncio
import io
from unittest import mock

import pytest
from PIL import Image
from rgbmatrix import RGBMatrix, RGBMatrixOptions

from led_ticker.scaled_canvas import ScaledCanvas
from led_ticker.ticker import Ticker
from led_ticker.widgets.gif import GifPlayer


def _make_gif(tmp_path, n_frames=2, size=(32, 32), duration_ms=10):
    imgs = [Image.new("RGB", size, color=(50 * (i + 1), 0, 0)) for i in range(n_frames)]
    buf = io.BytesIO()
    imgs[0].save(
        buf,
        format="GIF",
        save_all=True,
        append_images=imgs[1:],
        duration=duration_ms,
        loop=0,
    )
    p = tmp_path / "anim.gif"
    p.write_bytes(buf.getvalue())
    return p


def _bigsign_real_canvas():
    opts = RGBMatrixOptions()
    opts.cols = 64
    opts.rows = 32
    opts.chain_length = 8
    opts.parallel = 1
    opts.pixel_mapper_config = "U-mapper"
    return RGBMatrix(options=opts).CreateFrameCanvas()


async def test_run_gif_invokes_widget_play(tmp_path, mocker):
    real = _bigsign_real_canvas()
    frame = mock.Mock()
    frame.get_clean_canvas.return_value = real
    frame.matrix.SwapOnVSync.side_effect = lambda c: c

    mocker.patch("asyncio.sleep", new=mock.AsyncMock())

    queue: asyncio.Queue = asyncio.Queue()
    widget = GifPlayer(path=str(_make_gif(tmp_path)), fit="stretch")
    queue.put_nowait(widget)

    ticker = Ticker(
        monitors=[widget],
        frame=frame,
        notif_queue=queue,
        scale=1,
    )

    await ticker.run_gif(loop_count=2)

    # 2 loops × 2 frames = 4 swaps issued by play()
    assert frame.matrix.SwapOnVSync.call_count == 4
    # And widget ended on the last frame
    assert widget._current_frame_idx == 1


async def test_run_gif_unwraps_scaled_canvas(tmp_path, mocker):
    """When the section's scale > 1, the orchestrator must paint to the
    underlying real canvas, not the wrapper."""
    real = _bigsign_real_canvas()
    sc = ScaledCanvas(real, scale=4)
    frame = mock.Mock()
    frame.get_clean_canvas.return_value = sc
    frame.matrix.SwapOnVSync.side_effect = lambda c: c

    mocker.patch("asyncio.sleep", new=mock.AsyncMock())

    queue: asyncio.Queue = asyncio.Queue()
    widget = GifPlayer(path=str(_make_gif(tmp_path)), fit="stretch")
    queue.put_nowait(widget)

    ticker = Ticker(
        monitors=[widget],
        frame=frame,
        notif_queue=queue,
        scale=4,
    )

    await ticker.run_gif(loop_count=1)

    # Pixel at col 1 (mod 4 = 1, NOT block-aligned) lit on the real
    # canvas → proves we bypassed the wrapper.
    real_after = frame.matrix.SwapOnVSync.call_args.args[0]
    # Some non-zero pixel exists at a non-block-aligned col
    assert real_after.get_pixel(1, 1) != (0, 0, 0)
```

- [ ] **Step 2: Run the test to confirm it fails**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_run_gif.py -v`
Expected: FAIL — `Ticker` has no `run_gif` method.

- [ ] **Step 3: Implement `Ticker.run_gif()` and `_run_gif()`**

In `src/led_ticker/ticker.py`, find the `run_swap` method (around line 97) and add `run_gif` directly after it. Keep the `_maybe_wrap` + `_build_then_enqueue` patterns identical to `run_swap`:

```python
    async def run_gif(self, loop_count: int = 0) -> None:
        """GIF playback mode: each widget pulled from the queue is a
        GifPlayer; play() is called with the underlying real canvas
        so frames render at native physical resolution.

        loop_count is the number of complete passes through each GIF
        before the next widget (or section transition) takes over.
        Treats loop_count=0 as 1 (consistent with other run modes).
        """
        logging.info("Running GIF playback with loop count %s...", loop_count)
        canvas = _maybe_wrap(
            self.frame.get_clean_canvas(), self.scale, self.content_height
        )
        title = self.title if self.title else None
        assert self.notif_queue is not None

        asyncio.create_task(
            _build_then_enqueue(
                self.monitors,
                self.notif_queue,
                title=title,
                loop_count=loop_count,
            )
        )

        await _run_gif(
            canvas,
            self.frame,
            self.notif_queue,
            loop_count=loop_count,
        )
```

Then add the `_run_gif` async helper next to `_run_swap` (around line 525). Place it just below the existing `_run_swap` definition:

```python
async def _run_gif(
    canvas: Canvas,
    frame: Any,
    notif_queue: asyncio.Queue[Any],
    loop_count: int = 0,
) -> None:
    """Pull GifPlayer widgets from the queue and play() each in turn.

    The widget's `play()` method paints to the real canvas (unwrapping
    any ScaledCanvas) and returns the back-buffer canvas after its
    final swap; we feed that back into the next widget's play() so
    swap chaining stays correct.
    """
    real = getattr(canvas, "real", canvas)
    while True:
        try:
            widget = notif_queue.get_nowait()
        except asyncio.QueueEmpty:
            try:
                widget = await asyncio.wait_for(notif_queue.get(), timeout=0.1)
            except asyncio.TimeoutError:
                return
        real = await widget.play(real, frame, loop_count=loop_count)
```

- [ ] **Step 4: Add `"gif": "run_gif"` to `RUN_MODES`**

Modify `src/led_ticker/app.py` line 122-126:

```python
RUN_MODES: dict[str, str] = {
    "forever_scroll": "run_forever_scroll",
    "infini_scroll": "run_infini_scroll",
    "swap": "run_swap",
    "gif": "run_gif",
}
```

- [ ] **Step 5: Run the smoke tests**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_run_gif.py -v`
Expected: 2 PASSED.

- [ ] **Step 6: Run the full suite**

Run: `PYTHONPATH=tests/stubs uv run pytest 2>&1 | tail -3`
Expected: passes with no new failures.

- [ ] **Step 7: Commit**

```bash
git add src/led_ticker/ticker.py src/led_ticker/app.py tests/test_run_gif.py
git commit -m "Add Ticker.run_gif() orchestrator + RUN_MODES entry"
```

---

## Task 5: Config-relative path resolution in `app.py`

**Files:**
- Modify: `src/led_ticker/app.py` (thread `config_path.parent` into `_build_widget`)
- Modify: `tests/test_app.py` or create `tests/test_gif_path_resolution.py` (small test)

- [ ] **Step 1: Write a test that fails — config-relative path is resolved**

Create `tests/test_gif_path_resolution.py`:

```python
"""Test that gif widget paths are resolved relative to the config dir."""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image

from led_ticker.app import _build_widget


async def _build(cfg, config_dir):
    import aiohttp

    async with aiohttp.ClientSession() as s:
        return await _build_widget(cfg, s, config_dir=config_dir)


def _write_tiny_gif(path: Path) -> None:
    img = Image.new("RGB", (4, 4), color=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="GIF")
    path.write_bytes(buf.getvalue())


async def test_gif_relative_path_resolves_against_config_dir(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    assets = config_dir / "assets"
    assets.mkdir()
    gif_path = assets / "tiny.gif"
    _write_tiny_gif(gif_path)

    cfg = {"type": "gif", "path": "assets/tiny.gif", "fit": "stretch"}
    widget = await _build(cfg, config_dir=config_dir)

    assert Path(widget.path) == gif_path.resolve()


async def test_gif_absolute_path_left_alone(tmp_path):
    gif_path = tmp_path / "abs.gif"
    _write_tiny_gif(gif_path)

    cfg = {"type": "gif", "path": str(gif_path.resolve()), "fit": "stretch"}
    widget = await _build(cfg, config_dir=tmp_path / "elsewhere")

    assert Path(widget.path) == gif_path.resolve()
```

- [ ] **Step 2: Run the test to confirm it fails**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_gif_path_resolution.py -v`
Expected: FAIL — `_build_widget()` doesn't accept `config_dir`.

- [ ] **Step 3: Update `_build_widget` signature + implementation**

Modify `src/led_ticker/app.py:71` — replace the function definition with:

```python
async def _build_widget(
    widget_cfg: dict[str, Any],
    session: aiohttp.ClientSession,
    config_dir: Path | None = None,
) -> Any:
    """Instantiate a widget from its config dict.

    `config_dir` is the directory containing the config.toml; used to
    resolve relative `path` values for widgets that reference asset
    files (currently just `type = "gif"`).
    """
    widget_type = widget_cfg.pop("type")
    cls = get_widget_class(widget_type)

    # Config uses "text" but TickerMessage/TickerCountdown use "message"
    if "text" in widget_cfg:
        if "message" not in widget_cfg:
            widget_cfg["message"] = widget_cfg.pop("text")
        else:
            widget_cfg.pop("text")

    # GIF widgets get config-relative paths resolved here so the widget
    # itself doesn't need to know about config layout.
    if widget_type == "gif" and "path" in widget_cfg and config_dir is not None:
        candidate = Path(widget_cfg["path"])
        if not candidate.is_absolute():
            widget_cfg["path"] = str((config_dir / candidate).resolve())

    # Convert any [r, g, b] lists in known color keys to graphics.Color.
    _coerce_widget_colors(widget_cfg)

    # Extract presentation config before passing to widget
    presentation_name = widget_cfg.pop("presentation", None)
    widget_cfg.pop("presentation_speed", None)

    if hasattr(cls, "start"):
        widget = await cls.start(session=session, **widget_cfg)
    else:
        widget = cls(**widget_cfg)

    # Wrap with presentation mode if configured
    if presentation_name:
        pres_cls = get_presentation_class(presentation_name)
        widget = WidgetPresenter(widget, pres_cls())

    return widget
```

- [ ] **Step 4: Update the call site to pass `config_dir`**

Find the call to `_build_widget` in `src/led_ticker/app.py:205` (inside `run()`, while iterating `section.widgets`). Change it to pass `config_dir=config_path.parent`:

```python
                        widget = await _build_widget(
                            cfg, session, config_dir=config_path.parent
                        )
```

- [ ] **Step 5: Run the path-resolution tests**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_gif_path_resolution.py -v`
Expected: 2 PASSED.

- [ ] **Step 6: Run the full suite**

Run: `PYTHONPATH=tests/stubs uv run pytest 2>&1 | tail -3`
Expected: passes — and existing `_build_widget` tests still work because `config_dir` defaults to `None`.

- [ ] **Step 7: Commit**

```bash
git add src/led_ticker/app.py tests/test_gif_path_resolution.py
git commit -m "Resolve gif widget paths relative to config dir"
```

---

## Task 6: Wire it into the test config + manual hardware test

**Files:**
- Modify: `config/config.hires_emoji_test.example.toml` (add a GIF section)
- Modify: `config/config.bigsign.example.toml` (add a commented-out GIF example for documentation)

- [ ] **Step 1: Add a GIF section to the hi-res test config**

Append to `config/config.hires_emoji_test.example.toml`:

```toml
# ---------------------------------------------------------------------------
# Section 8 — GIF playback (Pikachu wave)
#
# Plays config/assets/pika_wave.gif twice in pillarbox mode (the source
# is square; the panel is 4:1, so the GIF appears 64×64 centered with
# black pillars on either side). The section transition before/after
# uses the default dissolve, sandwiching the GIF playback cleanly.
# ---------------------------------------------------------------------------

[[playlist.section]]
mode = "gif"
loop_count = 2
transition = "dissolve"
transition_duration = 0.6

[[playlist.section.widget]]
type = "gif"
path = "assets/pika_wave.gif"
fit = "pillarbox"
```

- [ ] **Step 2: Add a commented-out reference example to the bigsign config**

Append to `config/config.bigsign.example.toml`:

```toml
# ---------------------------------------------------------------------------
# GIF playback example
#
# `mode = "gif"` plays an animated GIF at the panel's native physical
# resolution (256×64), bypassing the ScaledCanvas wrapper. Frame timing
# comes from the GIF's own metadata; `loop_count` controls how many
# complete passes play before the next section runs.
#
# `fit` options (default "pillarbox"):
#   pillarbox — scale by height, center horizontally with black pillars
#   letterbox — scale by width, center vertically with black bars
#   stretch   — fill the whole panel, distorting aspect ratio
#   crop      — scale to cover both axes, center-crop the excess
#
# `path` is resolved relative to this config file's directory. Drop GIFs
# under `<config_dir>/assets/` and reference by relative path.
# ---------------------------------------------------------------------------

# [[playlist.section]]
# mode = "gif"
# loop_count = 2
#
# [[playlist.section.widget]]
# type = "gif"
# path = "assets/example.gif"
# fit = "pillarbox"
```

- [ ] **Step 3: Run the full suite as a final smoke check**

Run: `PYTHONPATH=tests/stubs uv run pytest 2>&1 | tail -3`
Expected: all green.

- [ ] **Step 4: Commit the config changes**

```bash
git add config/config.hires_emoji_test.example.toml config/config.bigsign.example.toml
git commit -m "Wire :gif: into test config; document on bigsign example"
```

- [ ] **Step 5: Manual hardware test on the bigsign**

On the bigsign Pi:

```bash
# Copy the test config + assets to the active config
cp config/config.hires_emoji_test.example.toml config/config.toml
# (assets/pika_wave.gif is already in the repo — it'll be on the Pi after a git pull)

# Restart the service to pick up new config + new gif widget code
sudo systemctl restart led-ticker
journalctl -u led-ticker -f
```

Watch for:
- Pikachu appears centered on the panel (64×64 with black pillars)
- Frames advance smoothly (no stutter / no double-paint)
- Plays through 2 complete loops
- Dissolve transition runs cleanly between gif and the next section (entry → frame 0; exit → last frame)
- No flicker, tearing, or memory growth across many loops

If anything looks off, capture symptoms and feed them back as a follow-up.

- [ ] **Step 6: Merge to main once the hardware test passes**

```bash
git checkout main
git merge --no-ff gif-widget -m "Merge branch 'gif-widget' — animated GIF widget"
git push origin main
```

---

## Self-review notes

- All four spec sections (architecture, components, data flow, error handling, testing) have implementing tasks above.
- No placeholders / TBDs / "implement later".
- All code shown in full where steps modify code.
- Type names consistent across tasks: `GifPlayer`, `decode_gif`, `_frames`, `_current_frame_idx`, `play()`, `run_gif()`, `_run_gif()`.
- Hardware-test step references `config/assets/pika_wave.gif` matching Task 0's setup.
