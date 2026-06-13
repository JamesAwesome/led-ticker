# Live Display Preview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mirror the LED panel into the web status page via a shadow-buffer tee, with zero render-path cost while nobody is watching.

**Architecture:** A `PreviewTee` canvas (owned by `LedFrame`, installed once when `[web]` is present) forwards every draw to hardware and, only while watched, mirrors into a `bytearray` shadow. `frame.swap()` writes the shadow as a raw-RGB frame file to the tmpfs volume at ≤5 fps. The sidecar serves the bytes verbatim and touches a marker file that is the "someone is watching" signal; the display's existing heartbeat toggles the mirror off when the marker goes stale. The browser renders raw RGB onto a pixelated `<canvas>`.

**Tech Stack:** stdlib only on the display side (`struct`, `bytearray`, `os.replace`); aiohttp (existing) on the sidecar; vanilla JS `ImageData` in the browser. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-06-12-live-preview-design.md`

**Worktree notes (read first):**
- Work in `/Users/james/projects/github/jamesawesome/led-ticker-worktrees/live-preview`, branch `feat/live-preview`. Run `git branch --show-current` and ABORT if it prints `main`.
- Tests: `PYTHONPATH=tests/stubs uv run pytest <files> -v` · Lint: `uv run --extra dev ruff check src/ tests/` · Format: `uv run --extra dev ruff format <files>` when check complains.
- Hooks WORK now — commit normally with `PATH="$PWD/.venv/bin:$PATH" git commit ...` (no `--no-verify`).
- House style: no gun metaphors; say pitfall/gotcha/sharp edge.
- EXTREME CAUTION: `frame.py`, `ticker.py`, `text_render.py` are the render path. CLAUDE.md constraints #1–#13 apply. The spine invariant of this feature: **hardware forward happens first and unconditionally; a shadow bug may break the preview, never the panel.**

**Pre-verified code facts (do not re-derive):**
- `frame.swap()` (`src/led_ticker/frame.py:99`) is the ONLY `matrix.SwapOnVSync` call site in the package — engine, transitions, and play()-widgets all route through it.
- `ticker._swap` (`ticker.py:131`) passes `canvas.real` (the innermost layer) to `frame.swap` for `ScaledCanvas`, else the canvas itself.
- `_maybe_wrap` (`ticker.py:144`) wraps whatever `frame.get_clean_canvas()` returned — so returning the tee there makes `ScaledCanvas(tee)` chains automatic.
- `unwrap_to_real` (`scaled_canvas.py`) peels ONLY `ScaledCanvas` (walks `.real`) — a tee whose hardware handle is named `_hw` is terminal to it by construction.
- `BDFGlyph` fields: `advance_width`, `bbx_width`, `bbx_height`, `bbx_xoff`, `bbx_yoff`, `lit_pixels: list[(col, row)]`. Baseline math (from `ScaledCanvas.draw_bdf_text`): `top_y = y - glyph.bbx_height - glyph.bbx_yoff`, `base_x = cx + glyph.bbx_xoff`; missing glyph advances `bdf.bbx_width`. `get_bdf_for(font)` (`fonts/__init__.py:36`) maps a graphics font to its `BDFFont`.
- Colors arrive as `graphics.Color` (`.red/.green/.blue`) or 3-tuples.
- The heartbeat task `_status_heartbeat(board)` (`app/run.py`) loops every `board.min_interval` (2.0 s) — marker checks ride it (wake latency ≤ ~2 s + one capture interval; fine against the spec's "~a second" intent, state it honestly in docs).
- Stub `RGBMatrix.SwapOnVSync` returns a DIFFERENT canvas each call; stub canvases store `_pixels[(x, y)] = (r, g, b)` and implement `Clear`/`Fill`/`SetPixel`.
- tmpfs dir = `status_path` parent (`/run/led-ticker` by default; the `ticker-status` volume in Docker), already 0o777 via `prepare_dir` — both processes can write there.

**File structure:**

| File | Responsibility |
|---|---|
| `src/led_ticker/preview.py` (create) | `PreviewTee`: shadow mirror, watched lifecycle, capture write, BDF text mirror. Stdlib-only, rgbmatrix-free. |
| `src/led_ticker/frame.py` (modify) | Tee install + rebind in `get_clean_canvas`/`swap`; capture call beside the liveness counter |
| `src/led_ticker/text_render.py` (modify) | Tee branch in `draw_text` (C draw to `_hw`, mirror via tee) |
| `src/led_ticker/app/run.py` (modify) | Install tee when `[web]` present; heartbeat toggles mirror from marker mtime |
| `src/led_ticker/webui/__init__.py` (modify) | `GET /api/preview` + marker touch |
| `src/led_ticker/webui/static/index.html` (modify) | Hero `<canvas>`, visibility-gated 5 fps poller |
| `tests/test_preview_tee.py`, `tests/test_preview_endpoint.py` (create); `tests/test_frame.py`, `tests/test_text_render.py` or new, `tests/test_status_instrumentation.py`, `tests/test_webui_app.py`, `tests/test_webui_purity.py` (extend) | |
| `docs/site/src/content/docs/concepts/web-status-ui.mdx` (modify) | Preview section + scale-1 fidelity caveat |

---

### Task 1: `PreviewTee` core — forward + mirror + spine invariant

**Files:**
- Create: `src/led_ticker/preview.py`
- Test: `tests/test_preview_tee.py` (create)

- [ ] **Step 1: Write the failing tests** — create `tests/test_preview_tee.py`:

```python
"""PreviewTee: hardware forwarding, shadow mirroring, the spine invariant."""

import pytest
from rgbmatrix import RGBMatrix, RGBMatrixOptions

from led_ticker.preview import PreviewTee


def _hw_canvas(width=32, height=16):
    options = RGBMatrixOptions()
    options.rows = height
    options.cols = width
    options.chain_length = 1
    matrix = RGBMatrix(options=options)
    canvas = matrix.CreateFrameCanvas()
    canvas.Clear()
    return canvas


def _tee(tmp_path, width=32, height=16):
    return PreviewTee(
        hw=_hw_canvas(width, height),
        width=width,
        height=height,
        frame_path=tmp_path / "preview.bin",
    )


def test_forwards_setpixel_to_hardware(tmp_path):
    tee = _tee(tmp_path)
    tee.SetPixel(3, 4, 10, 20, 30)
    assert tee._hw._pixels[(3, 4)] == (10, 20, 30)


def test_mirror_off_means_zero_shadow_writes(tmp_path):
    tee = _tee(tmp_path)
    tee.SetPixel(3, 4, 10, 20, 30)
    assert bytes(tee._shadow) == bytes(32 * 16 * 3)  # untouched


def test_mirror_on_shadows_setpixel(tmp_path):
    tee = _tee(tmp_path)
    tee.set_watched(True)
    tee.SetPixel(3, 4, 10, 20, 30)
    i = (4 * 32 + 3) * 3
    assert tuple(tee._shadow[i : i + 3]) == (10, 20, 30)
    assert tee._hw._pixels[(3, 4)] == (10, 20, 30)  # forward still happened


def test_out_of_bounds_setpixel_clips_in_shadow(tmp_path):
    tee = _tee(tmp_path)
    tee.set_watched(True)
    tee.SetPixel(-1, 0, 1, 2, 3)
    tee.SetPixel(32, 0, 1, 2, 3)
    tee.SetPixel(0, 16, 1, 2, 3)
    assert bytes(tee._shadow) == bytes(32 * 16 * 3)  # no corruption, no raise


def test_fill_and_clear_mirror_in_bulk(tmp_path):
    tee = _tee(tmp_path)
    tee.set_watched(True)
    tee.Fill(7, 8, 9)
    assert bytes(tee._shadow) == bytes((7, 8, 9)) * (32 * 16)
    tee.Clear()
    assert bytes(tee._shadow) == bytes(32 * 16 * 3)


def test_width_height_exposed(tmp_path):
    tee = _tee(tmp_path)
    assert (tee.width, tee.height) == (32, 16)


def test_spine_invariant_shadow_failure_never_blocks_hardware(tmp_path):
    """A broken shadow disables mirroring; the panel keeps receiving pixels."""
    tee = _tee(tmp_path)
    tee.set_watched(True)
    tee._shadow = None  # sabotage: every shadow write now raises
    tee.SetPixel(1, 1, 5, 5, 5)  # must NOT raise
    assert tee._hw._pixels[(1, 1)] == (5, 5, 5)  # hardware got it anyway
    assert tee.mirror is False  # mirroring self-disabled
    tee.Fill(1, 2, 3)  # subsequent calls: plain forwards, no raise
    assert tee._hw._pixels[(0, 0)] == (1, 2, 3)


def test_set_watched_false_unlinks_frame_file(tmp_path):
    tee = _tee(tmp_path)
    (tmp_path / "preview.bin").write_bytes(b"old")
    tee.set_watched(True)
    tee.set_watched(False)
    assert not (tmp_path / "preview.bin").exists()
    tee.set_watched(False)  # idempotent, no raise on missing file
```

- [ ] **Step 2: Run to verify failure**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_preview_tee.py -q`
Expected: `ModuleNotFoundError: No module named 'led_ticker.preview'`

- [ ] **Step 3: Implement `src/led_ticker/preview.py`** (capture/`maybe_capture` and text mirroring arrive in Tasks 2 and 4 — this step is the tee core only):

```python
"""Shadow-buffer tee for the live web preview.

PreviewTee sits innermost in the canvas chain (under ScaledCanvas on scaled
signs, handed to widgets directly on smallsign). Every draw is forwarded to
the hardware canvas FIRST and unconditionally; only while watched does it
also mirror into a flat RGB bytearray. The spine invariant: a shadow bug can
break the preview, never the panel — every mirror write is wrapped, and any
failure flips mirroring off for the session.

The hardware handle is deliberately named `_hw`, NOT `real`:
`scaled_canvas.unwrap_to_real` walks `.real`, so the tee is terminal to the
unwrap machinery and every physical-resolution paint site (hires fonts,
emoji, dissolve scatter, borders) lands here with zero call-site changes.

Stdlib-only; must never import rgbmatrix (webui purity rules apply to the
shapes this module shares with the sidecar).
"""

import logging
import os
import struct
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

PREVIEW_MAGIC = b"LTPV"
PREVIEW_VERSION = 1
# magic, version, width, height, reserved, seq -> 16 bytes
HEADER = struct.Struct("<4sHHHHI")
CAPTURE_INTERVAL = 0.2  # seconds -> 5 fps
MARKER_TTL = 10.0  # seconds of marker freshness that keep the mirror on


class PreviewTee:
    """Forward-and-mirror canvas. See module docstring for the contract."""

    def __init__(self, hw: Any, width: int, height: int, frame_path: Path) -> None:
        self._hw = hw
        self.width = width
        self.height = height
        self._frame_path = Path(frame_path)
        self._shadow: Any = bytearray(width * height * 3)
        self.mirror = False
        self._complete = False  # full Clear/Fill seen since mirror enable
        self._seq = 0
        self._last_capture = 0.0
        self._disabled = False  # session kill-switch after a shadow failure

    # -- lifecycle -----------------------------------------------------

    def set_watched(self, watched: bool) -> None:
        """Toggle mirroring from the watched-marker state. Off also removes
        the frame file so the sidecar reports idle, not a frozen frame."""
        if watched and not self._disabled:
            if not self.mirror:
                self._shadow[:] = bytes(len(self._shadow))
                self._complete = False
                self.mirror = True
        else:
            self.mirror = False
            try:
                self._frame_path.unlink(missing_ok=True)
            except OSError:
                pass

    def _disable(self, why: str) -> None:
        self.mirror = False
        self._disabled = True
        logger.warning(
            "preview mirroring disabled for this session (%s); panel unaffected",
            why,
        )

    # -- canvas surface (forward first, mirror second) -----------------

    def SetPixel(self, x: int, y: int, r: int, g: int, b: int) -> None:
        self._hw.SetPixel(x, y, r, g, b)
        if self.mirror:
            try:
                if 0 <= x < self.width and 0 <= y < self.height:
                    i = (y * self.width + x) * 3
                    s = self._shadow
                    s[i] = r
                    s[i + 1] = g
                    s[i + 2] = b
            except Exception:
                self._disable("shadow write failed")

    def Fill(self, r: int, g: int, b: int) -> None:
        self._hw.Fill(r, g, b)
        if self.mirror:
            try:
                self._shadow[:] = bytes((r, g, b)) * (self.width * self.height)
                self._complete = True
            except Exception:
                self._disable("shadow fill failed")

    def Clear(self) -> None:
        self._hw.Clear()
        if self.mirror:
            try:
                self._shadow[:] = bytes(len(self._shadow))
                self._complete = True
            except Exception:
                self._disable("shadow clear failed")
```

Implementation notes for this step:
- `try` blocks in CPython 3.11+ are zero-cost until an exception actually raises — the per-pixel wrap is the spine invariant's price and it is ~free.
- The bounds check both prevents shadow corruption AND replicates the hardware's silent clipping.
- `bytes(len(...))` is the zero-fill idiom (bytes of NULs); slice-assign into the bytearray is a C-speed bulk copy.

- [ ] **Step 4: Run tests**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_preview_tee.py -q`
Expected: all PASS

- [ ] **Step 5: Lint, format, commit**

```bash
uv run --extra dev ruff check src/led_ticker/preview.py tests/test_preview_tee.py
git add src/led_ticker/preview.py tests/test_preview_tee.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "feat(preview): PreviewTee shadow mirror with spine invariant"
```

---

### Task 2: capture write — `maybe_capture` + frame file format

**Files:**
- Modify: `src/led_ticker/preview.py`
- Test: `tests/test_preview_tee.py` (extend)

- [ ] **Step 1: Write the failing tests** (append):

```python
def _read_frame(path):
    from led_ticker.preview import HEADER, PREVIEW_MAGIC

    data = path.read_bytes()
    magic, ver, w, h, _res, seq = HEADER.unpack(data[: HEADER.size])
    assert magic == PREVIEW_MAGIC
    return ver, w, h, seq, data[HEADER.size :]


def test_capture_writes_header_and_payload(tmp_path):
    tee = _tee(tmp_path)
    tee.set_watched(True)
    tee.Clear()  # establishes completeness
    tee.SetPixel(0, 0, 255, 0, 0)
    tee.maybe_capture(now=100.0)
    ver, w, h, seq, payload = _read_frame(tmp_path / "preview.bin")
    assert (ver, w, h, seq) == (1, 32, 16, 1)
    assert payload[:3] == bytes((255, 0, 0))
    assert len(payload) == 32 * 16 * 3


def test_capture_requires_completeness(tmp_path):
    # Enabled mid-tick: no Clear/Fill seen yet -> first capture is deferred.
    tee = _tee(tmp_path)
    tee.set_watched(True)
    tee.SetPixel(0, 0, 9, 9, 9)
    tee.maybe_capture(now=100.0)
    assert not (tmp_path / "preview.bin").exists()
    tee.Clear()
    tee.maybe_capture(now=101.0)
    assert (tmp_path / "preview.bin").exists()


def test_capture_throttles_to_interval(tmp_path):
    tee = _tee(tmp_path)
    tee.set_watched(True)
    tee.Clear()
    tee.maybe_capture(now=100.0)
    tee.maybe_capture(now=100.05)  # inside 0.2 s window -> dropped
    tee.maybe_capture(now=100.1)
    _, _, _, seq, _ = _read_frame(tmp_path / "preview.bin")
    assert seq == 1
    tee.maybe_capture(now=100.3)
    _, _, _, seq, _ = _read_frame(tmp_path / "preview.bin")
    assert seq == 2


def test_capture_noop_when_mirror_off(tmp_path):
    tee = _tee(tmp_path)
    tee.maybe_capture(now=100.0)
    assert not (tmp_path / "preview.bin").exists()


def test_capture_failure_self_disables(tmp_path):
    tee = _tee(tmp_path)
    tee.set_watched(True)
    tee.Clear()
    tee._frame_path = tmp_path  # a directory: os.replace onto it fails
    tee.maybe_capture(now=100.0)  # must not raise
    assert tee.mirror is False


def test_capture_leaves_no_tmp_behind(tmp_path):
    tee = _tee(tmp_path)
    tee.set_watched(True)
    tee.Clear()
    tee.maybe_capture(now=100.0)
    assert [p.name for p in tmp_path.iterdir()] == ["preview.bin"]
```

- [ ] **Step 2: Run to verify failure** — `AttributeError: ... no attribute 'maybe_capture'`.

- [ ] **Step 3: Implement** — add to `PreviewTee`:

```python
    # -- capture --------------------------------------------------------

    def maybe_capture(self, now: float | None = None) -> None:
        """Write the shadow as a frame file, at most once per
        CAPTURE_INTERVAL, and only once a full Clear/Fill has run since
        mirroring was enabled (a mid-tick enable leaves the shadow
        incomplete for the remainder of that tick). Failures self-disable
        — same rule as every other write on the web path."""
        if not self.mirror or not self._complete:
            return
        if now is None:
            now = time.monotonic()
        if now - self._last_capture < CAPTURE_INTERVAL:
            return
        try:
            self._seq += 1
            header = HEADER.pack(
                PREVIEW_MAGIC, PREVIEW_VERSION, self.width, self.height, 0, self._seq
            )
            tmp = self._frame_path.with_name(self._frame_path.name + ".tmp")
            tmp.write_bytes(header + bytes(self._shadow))
            os.replace(tmp, self._frame_path)
            self._last_capture = now
        except Exception:
            self._disable("capture write failed")
```

- [ ] **Step 4: Run tests** — all PASS (`PYTHONPATH=tests/stubs uv run pytest tests/test_preview_tee.py -q`).

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/preview.py tests/test_preview_tee.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "feat(preview): throttled atomic frame capture"
```

---

### Task 3: `LedFrame` integration — install, rebind, capture-at-swap

**Files:**
- Modify: `src/led_ticker/frame.py`
- Test: `tests/test_frame.py` (extend)

- [ ] **Step 1: Write the failing tests** (append to `tests/test_frame.py`):

```python
def test_install_preview_returns_tee_from_get_clean_canvas(tmp_path):
    from led_ticker.preview import PreviewTee

    frame = LedFrame(led_cols=32, led_chain_length=1)
    tee = PreviewTee(
        hw=frame.matrix.CreateFrameCanvas(),
        width=32,
        height=16,
        frame_path=tmp_path / "preview.bin",
    )
    frame.install_preview(tee)
    canvas = frame.get_clean_canvas()
    assert canvas is tee  # same object, every time
    assert frame.get_clean_canvas() is tee


def test_swap_unwraps_and_rebinds_tee(tmp_path):
    from led_ticker.preview import PreviewTee

    frame = LedFrame(led_cols=32, led_chain_length=1)
    tee = PreviewTee(
        hw=frame.matrix.CreateFrameCanvas(),
        width=32,
        height=16,
        frame_path=tmp_path / "preview.bin",
    )
    frame.install_preview(tee)
    canvas = frame.get_clean_canvas()
    hw_before = tee._hw
    returned = frame.swap(canvas)
    assert returned is tee  # callers keep the tee (constraint #1 unchanged)
    assert tee._hw is not hw_before  # stub returns a DIFFERENT canvas


def test_swap_captures_when_watched(tmp_path):
    from led_ticker.preview import PreviewTee

    frame = LedFrame(led_cols=32, led_chain_length=1)
    tee = PreviewTee(
        hw=frame.matrix.CreateFrameCanvas(),
        width=32,
        height=16,
        frame_path=tmp_path / "preview.bin",
    )
    frame.install_preview(tee)
    canvas = frame.get_clean_canvas()  # mirror off here
    tee.set_watched(True)
    canvas = frame.get_clean_canvas()  # fresh tick: Clear mirrored
    canvas.SetPixel(0, 0, 1, 2, 3)
    frame.swap(canvas)
    assert (tmp_path / "preview.bin").exists()


def test_overlay_hooks_paint_through_tee_into_shadow(tmp_path):
    """The busy-light dot must appear in the preview: hooks receive the tee."""
    from led_ticker.preview import PreviewTee

    frame = LedFrame(led_cols=32, led_chain_length=1)
    tee = PreviewTee(
        hw=frame.matrix.CreateFrameCanvas(),
        width=32,
        height=16,
        frame_path=tmp_path / "preview.bin",
    )
    frame.install_preview(tee)
    tee.set_watched(True)
    canvas = frame.get_clean_canvas()
    frame.overlay_hooks.append(lambda c: c.SetPixel(31, 0, 200, 0, 0))
    frame.swap(canvas)
    i = (0 * 32 + 31) * 3
    assert tuple(tee._shadow[i : i + 3]) == (200, 0, 0)


def test_swap_without_preview_unchanged():
    frame = LedFrame(led_cols=32, led_chain_length=1)
    canvas = frame.get_clean_canvas()
    swapped = frame.swap(canvas)
    assert swapped is not canvas  # plain path: stub returns a new canvas
```

- [ ] **Step 2: Run to verify failure** — `AttributeError: ... install_preview`.

- [ ] **Step 3: Implement in `src/led_ticker/frame.py`.** Add an attrs field beside `overlay_hooks`:

```python
    _preview_tee: Any = attrs.field(init=False, default=None)
```

Add the install method:

```python
    def install_preview(self, tee: Any) -> None:
        """Install the (single, process-lifetime) preview tee. From here on
        get_clean_canvas/swap hand out and rebind the tee instead of raw
        hardware canvases; widgets never see the difference."""
        self._preview_tee = tee
```

Replace `get_clean_canvas`:

```python
    def get_clean_canvas(self) -> Canvas:
        """Get a clean canvas ready for rendering."""
        canvas = self.matrix.CreateFrameCanvas()
        canvas.Clear()
        tee = self._preview_tee
        if tee is not None:
            tee._hw = canvas
            # Mirror the Clear we just did on the raw canvas so the shadow
            # matches (and counts as the completeness-establishing clear).
            if tee.mirror:
                tee.Clear()
            return tee
        return canvas
```

In `swap()`, replace the final return with the tee-aware path (keep hooks + `record_swap` exactly where they are — hooks must run on the canvas ARG so they hit the tee and get mirrored):

```python
        for hook in self.overlay_hooks:
            hook(canvas)
        # Liveness breadcrumb for the web status UI: an int increment
        # (no-op without an active board, no I/O, cannot raise) — the one
        # deliberate exception to LedFrame staying mechanism-only, because
        # this is the single point every render path crosses.
        status_board.record_swap()
        tee = self._preview_tee
        if tee is not None and canvas is tee:
            new_hw = self.matrix.SwapOnVSync(tee._hw, self._framerate_fraction)
            # Shadow == the frame just sent to the panel; capture before the
            # next tick starts drawing over it.
            tee.maybe_capture()
            tee._hw = new_hw
            return tee
        return self.matrix.SwapOnVSync(canvas, self._framerate_fraction)
```

NOTE: `ticker._swap` needs NO change — for `ScaledCanvas(tee)` chains it calls `frame.swap(canvas.real)` where `.real` IS the tee, and gets the tee back; for smallsign the canvas itself is the tee. Verify by reading `ticker.py:131-141`, do not modify it.

- [ ] **Step 4: Run the frame tests + the engine suites** (the tee must be invisible to them):

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_frame.py tests/test_ticker_display.py tests/test_engine_redraw_contract.py tests/test_transitions.py -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/frame.py tests/test_frame.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "feat(preview): LedFrame owns the tee — install, rebind, capture at swap"
```

---

### Task 4: scale=1 text mirror — the `draw_text` tee branch

**Files:**
- Modify: `src/led_ticker/preview.py` (add `mirror_bdf_text`)
- Modify: `src/led_ticker/text_render.py`
- Test: `tests/test_preview_tee.py` (extend)

- [ ] **Step 1: Write the failing tests** (append to `tests/test_preview_tee.py`):

```python
def test_draw_text_funnel_forwards_to_hw_and_mirrors(tmp_path):
    """scale=1 path: C DrawText hits the hardware canvas; the shadow gets the
    pure-Python rasterization of the same glyphs. Parity standard: the stub's
    DrawText writes pixels, so shadow == stub _pixels for the text region."""
    from led_ticker._compat import require_graphics
    from led_ticker.text_render import draw_text

    graphics = require_graphics()
    font = graphics.Font()
    font.LoadFont("src/led_ticker/fonts/5x8.bdf")
    color = graphics.Color(10, 200, 30)

    tee = _tee(tmp_path, width=64, height=16)
    tee.set_watched(True)
    tee.Clear()
    advance = draw_text(tee, font, 1, 8, color, "Hi!")
    assert advance > 0

    # Every pixel the stub DrawText lit on the hw canvas is lit identically
    # in the shadow, and vice versa (full-region equality).
    lit_hw = {
        (x, y): rgb
        for (x, y), rgb in tee._hw._pixels.items()
        if rgb != (0, 0, 0)
    }
    lit_shadow = {}
    for y in range(16):
        for x in range(64):
            i = (y * 64 + x) * 3
            rgb = tuple(tee._shadow[i : i + 3])
            if rgb != (0, 0, 0):
                lit_shadow[(x, y)] = rgb
    assert lit_shadow == lit_hw


def test_draw_text_funnel_mirror_off_is_pure_forward(tmp_path):
    from led_ticker._compat import require_graphics
    from led_ticker.text_render import draw_text

    graphics = require_graphics()
    font = graphics.Font()
    font.LoadFont("src/led_ticker/fonts/5x8.bdf")

    tee = _tee(tmp_path, width=64, height=16)
    draw_text(tee, font, 1, 8, graphics.Color(1, 1, 1), "x")
    assert bytes(tee._shadow) == bytes(64 * 16 * 3)


def test_mirror_text_failure_self_disables_but_returns_advance(tmp_path):
    from led_ticker._compat import require_graphics
    from led_ticker.text_render import draw_text

    graphics = require_graphics()
    font = graphics.Font()
    font.LoadFont("src/led_ticker/fonts/5x8.bdf")

    tee = _tee(tmp_path, width=64, height=16)
    tee.set_watched(True)
    tee._shadow = None  # sabotage
    advance = draw_text(tee, font, 1, 8, graphics.Color(1, 1, 1), "x")
    assert advance > 0  # the C/hw draw still returned its width
    assert tee.mirror is False
```

- [ ] **Step 2: Run to verify failure** — the funnel doesn't know the tee yet, so the shadow stays empty in test 1.

- [ ] **Step 3a: Add `mirror_bdf_text` to `PreviewTee`** (`src/led_ticker/preview.py`) — replicates `ScaledCanvas.draw_bdf_text`'s glyph walk, writing shadow bytes directly:

```python
    # -- text mirror (scale = 1 funnel) ---------------------------------

    def mirror_bdf_text(self, bdf: Any, x: int, y: int, color: Any, text: str) -> None:
        """Rasterize `text` into the shadow only (the C library has already
        drawn it on the hardware canvas). Same glyph math as
        ScaledCanvas.draw_bdf_text; failures self-disable, never raise."""
        if not self.mirror:
            return
        try:
            if isinstance(color, tuple):
                r, g, b = color
            else:
                r, g, b = color.red, color.green, color.blue
            shadow = self._shadow
            w, h = self.width, self.height
            cx = x
            for ch in text:
                glyph = bdf.glyphs.get(ch)
                if glyph is None:
                    cx += bdf.bbx_width
                    continue
                top_y = y - glyph.bbx_height - glyph.bbx_yoff
                base_x = cx + glyph.bbx_xoff
                for col, row in glyph.lit_pixels:
                    px = base_x + col
                    py = top_y + row
                    if 0 <= px < w and 0 <= py < h:
                        i = (py * w + px) * 3
                        shadow[i] = r
                        shadow[i + 1] = g
                        shadow[i + 2] = b
                cx += glyph.advance_width
        except Exception:
            self._disable("shadow text raster failed")
```

- [ ] **Step 3b: The funnel branch** in `src/led_ticker/text_render.py` — add the import and extend `draw_text`'s final branch:

```python
from led_ticker.preview import PreviewTee
```

```python
def draw_text(canvas: Any, font: Any, x: int, y: int, color: Any, text: str) -> int:
    """Draw `text` at (x, y) baseline. Returns total advance width."""
    if isinstance(font, HiresFont):
        return _draw_hires_text(canvas, font, x, y, color, text)
    if isinstance(canvas, ScaledCanvas):
        bdf = get_bdf_for(font)
        return canvas.draw_bdf_text(bdf, x, y, color, text)
    if isinstance(canvas, PreviewTee):
        # scale=1 with the preview tee installed: the C library draws on the
        # hardware canvas (it type-checks for a real Canvas — constraint #2),
        # and the tee mirrors the same glyphs into the shadow.
        advance = _graphics.DrawText(canvas._hw, font, x, y, color, text)
        canvas.mirror_bdf_text(get_bdf_for(font), x, y, color, text)
        return advance
    return _graphics.DrawText(canvas, font, x, y, color, text)
```

PITFALL — import cycle check: `preview.py` imports nothing from led_ticker; `text_render.py` already imports `scaled_canvas` and `fonts`. Adding `preview` is acyclic. Verify with the import-purity test run in Step 4.

PITFALL — `get_bdf_for(font)` is called even when mirror is off in the branch above; it is `@functools.cache`-backed (check `fonts/__init__.py` — if it is NOT cached, hoist the call inside `canvas.mirror`-gated code: `if canvas.mirror: canvas.mirror_bdf_text(get_bdf_for(font), ...)`). Implement whichever keeps the mirror-off path free of per-call font lookups; the mirror-off test only asserts shadow purity, so add a cheap guard regardless:

```python
        if canvas.mirror:
            canvas.mirror_bdf_text(get_bdf_for(font), x, y, color, text)
```

(Use this gated form — it is strictly better.)

- [ ] **Step 4: Run tests + parity + purity suites**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_preview_tee.py tests/test_bdf_parser.py tests/test_webui_purity.py -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/preview.py src/led_ticker/text_render.py tests/test_preview_tee.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "feat(preview): scale=1 text mirroring through the draw_text funnel"
```

---

### Task 5: ScaledCanvas chain end-to-end + run.py wiring

**Files:**
- Modify: `src/led_ticker/app/run.py`
- Test: `tests/test_preview_tee.py`, `tests/test_status_instrumentation.py` (extend)

- [ ] **Step 1: Write the failing tests.** Append to `tests/test_preview_tee.py`:

```python
def test_scaled_canvas_chain_mirrors_through_tee(tmp_path):
    """ScaledCanvas(tee): block expansion, unwrap_to_real, and draw_bdf_text
    all land on the tee — full mirroring with zero call-site changes."""
    from led_ticker.scaled_canvas import ScaledCanvas, unwrap_to_real

    tee = _tee(tmp_path, width=64, height=32)
    tee.set_watched(True)
    tee.Clear()
    wrapper = ScaledCanvas(tee, scale=2, content_height=16)

    assert unwrap_to_real(wrapper) is tee  # tee is terminal to unwrap

    wrapper.SetPixel(1, 1, 50, 60, 70)  # expands to a 2x2 block on the tee
    lit = [
        (x, y)
        for y in range(32)
        for x in range(64)
        if tuple(tee._shadow[(y * 64 + x) * 3 : (y * 64 + x) * 3 + 3]) != (0, 0, 0)
    ]
    assert len(lit) == 4  # the 2x2 block, mirrored
```

Append to `tests/test_status_instrumentation.py`:

```python
def test_setup_preview_installs_tee_when_web_present(tmp_path):
    from led_ticker.app.run import _setup_preview
    from led_ticker.frame import LedFrame

    config = _make_fake_config(str(tmp_path / "status.json"))
    frame = LedFrame(led_cols=32, led_chain_length=1)
    tee = _setup_preview(config, frame)
    assert tee is not None
    assert frame.get_clean_canvas() is tee


def test_setup_preview_none_when_web_absent(tmp_path):
    import types as _types

    from led_ticker.app.run import _setup_preview
    from led_ticker.frame import LedFrame

    config = _types.SimpleNamespace(web=None, display=None)
    frame = LedFrame(led_cols=32, led_chain_length=1)
    assert _setup_preview(config, frame) is None
    canvas = frame.get_clean_canvas()
    assert not hasattr(canvas, "mirror")  # raw canvas, no tee


async def test_heartbeat_toggles_mirror_from_marker(tmp_path):
    import asyncio as _asyncio

    from led_ticker.app.run import _status_heartbeat
    from led_ticker.preview import PreviewTee
    from led_ticker.frame import LedFrame

    board = StatusBoard(path=tmp_path / "status.json", min_interval=0.05)
    frame = LedFrame(led_cols=32, led_chain_length=1)
    tee = PreviewTee(
        hw=frame.matrix.CreateFrameCanvas(),
        width=32,
        height=16,
        frame_path=tmp_path / "preview.bin",
    )
    status_board.set_active_board(board)
    task = _asyncio.create_task(_status_heartbeat(board, tee=tee, marker_ttl=0.2))
    try:
        marker = tmp_path / "preview-requested"
        marker.touch()
        await _asyncio.sleep(0.15)
        assert tee.mirror is True  # fresh marker -> mirroring on
        await _asyncio.sleep(0.4)  # let the marker age past ttl
        assert tee.mirror is False  # stale -> off
    finally:
        status_board.clear_active_board()
        await _asyncio.wait_for(task, timeout=2)
```

NOTE: the marker path is derived inside the tee/heartbeat as `frame_path.parent / "preview-requested"` — the test writes it in `tmp_path`, which is `frame_path.parent`. If the implementation parameterizes the marker path differently, keep test and implementation consistent — the CONTRACT is: marker lives next to the frame file, named `preview-requested`.

- [ ] **Step 2: Run to verify failures.**

- [ ] **Step 3: Implement in `src/led_ticker/app/run.py`.**

Add a setup helper next to `_setup_status_board`:

```python
def _setup_preview(config: Any, led_frame: Any) -> Any:
    """Install the preview tee when [web] is configured. The tee is sized to
    the physical panel and writes frames next to status.json (the tmpfs
    volume both processes share). Returns the tee, or None."""
    if config.web is None:
        return None
    from led_ticker.preview import PreviewTee  # noqa: PLC0415

    frame_path = Path(config.web.status_path).expanduser().parent / "preview.bin"
    tee = PreviewTee(
        hw=led_frame.matrix.CreateFrameCanvas(),
        width=config.display.cols * config.display.chain_length,
        height=config.display.rows * config.display.parallel,
        frame_path=frame_path,
    )
    led_frame.install_preview(tee)
    return tee
```

In `run()`, after `led_frame = build_frame_from_config(config.display)` (inside the existing try):

```python
        preview_tee = _setup_preview(config, led_frame)
```

Extend `_status_heartbeat` to carry the marker check (signature change; update the existing `spawn_tracked(_status_heartbeat(_status_handle[0]))` call site to pass `tee=preview_tee`):

```python
async def _status_heartbeat(
    board: Any, tee: Any = None, marker_ttl: float = 10.0
) -> None:
    """Republish at the throttle cadence so the sidecar's staleness verdict
    measures process liveness, not event frequency. Also toggles the preview
    mirror from the watched-marker mtime (one tmpfs stat per beat, off the
    render path). Exits once the board self-disables or is deactivated."""
    from led_ticker import status_board as _sb  # noqa: PLC0415

    marker = None
    if tee is not None:
        marker = tee._frame_path.parent / "preview-requested"
    while not board.disabled and _sb.get_active_board() is board:
        board.publish()
        if tee is not None:
            try:
                fresh = (time.time() - marker.stat().st_mtime) < marker_ttl
            except OSError:
                fresh = False
            tee.set_watched(fresh)
        await asyncio.sleep(board.min_interval)
```

(`time` may need importing in `run.py` — check the imports; add if absent. `Path` is already imported.)

GOTCHA — heartbeat spawn order: `_setup_status_board` runs BEFORE frame construction (privilege-drop constraint #13), but the heartbeat is spawned inside the try right after; the tee exists only AFTER frame build. Move the heartbeat spawn to AFTER `preview_tee = _setup_preview(...)` (it stays inside the same try, after frame build) and verify `tests/test_status_instrumentation.py::test_run_teardown_is_adjacent_to_setup` and `test_setup_runs_before_frame_build` still pass — the setup/try adjacency is untouched; only the spawn line moves later. Also update `test_run_spawns_heartbeat` if its source assertion needs the new call shape (`spawn_tracked(_status_heartbeat(_status_handle[0], tee=preview_tee))`).

- [ ] **Step 4: Run the suites**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_preview_tee.py tests/test_status_instrumentation.py tests/test_app.py tests/test_frame.py -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/app/run.py tests/test_preview_tee.py tests/test_status_instrumentation.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "feat(preview): wire tee install + watched-marker toggle into run()"
```

---

### Task 6: sidecar endpoint — `GET /api/preview`

**Files:**
- Modify: `src/led_ticker/webui/__init__.py`
- Test: `tests/test_preview_endpoint.py` (create), `tests/test_webui_purity.py` (extend import list with `led_ticker.preview`)

- [ ] **Step 1: Write the failing tests** — create `tests/test_preview_endpoint.py`:

```python
"""GET /api/preview: binary frames, idle/unsupported envelopes, marker touch."""

import json

from aiohttp.test_utils import TestClient, TestServer

from led_ticker.preview import HEADER, PREVIEW_MAGIC, PREVIEW_VERSION
from led_ticker.webui import build_webui_app


async def _client(tmp_path, token=""):
    config_path = tmp_path / "config.toml"
    config_path.write_text("[display]\nrows = 16\ncols = 32\n")
    app = build_webui_app(
        config_path=config_path, status_path=tmp_path / "status.json", token=token
    )
    client = TestClient(TestServer(app))
    await client.start_server()
    return client


def _write_frame(tmp_path, width=32, height=16, seq=7):
    payload = bytes(range(256))[: width * height * 3 % 256]  # any bytes
    payload = (b"\x01\x02\x03" * (width * height))[: width * height * 3]
    header = HEADER.pack(PREVIEW_MAGIC, PREVIEW_VERSION, width, height, 0, seq)
    (tmp_path / "preview.bin").write_bytes(header + payload)
    return payload


async def test_preview_serves_frame_with_headers(tmp_path):
    payload = _write_frame(tmp_path)
    client = await _client(tmp_path)
    try:
        resp = await client.get("/api/preview")
        assert resp.status == 200
        assert resp.content_type == "application/octet-stream"
        assert resp.headers["X-Preview-Width"] == "32"
        assert resp.headers["X-Preview-Height"] == "16"
        assert resp.headers["X-Preview-Seq"] == "7"
        assert await resp.read() == payload
    finally:
        await client.close()


async def test_preview_touches_watch_marker(tmp_path):
    client = await _client(tmp_path)
    try:
        await client.get("/api/preview")  # even an idle fetch wakes the mirror
        assert (tmp_path / "preview-requested").exists()
    finally:
        await client.close()


async def test_preview_idle_when_no_frame(tmp_path):
    client = await _client(tmp_path)
    try:
        resp = await client.get("/api/preview")
        assert resp.status == 200
        assert (await resp.json())["state"] == "idle"
    finally:
        await client.close()


async def test_preview_unsupported_on_bad_magic_version_or_size(tmp_path):
    client = await _client(tmp_path)
    cases = [
        b"XXXX" + bytes(12),  # bad magic
        HEADER.pack(PREVIEW_MAGIC, 99, 32, 16, 0, 1) + bytes(32 * 16 * 3),  # version
        HEADER.pack(PREVIEW_MAGIC, PREVIEW_VERSION, 32, 16, 0, 1) + b"short",  # size
        b"tiny",  # shorter than the header
    ]
    try:
        for blob in cases:
            (tmp_path / "preview.bin").write_bytes(blob)
            resp = await client.get("/api/preview")
            assert resp.status == 200
            assert (await resp.json())["state"] == "unsupported"
    finally:
        await client.close()


async def test_preview_is_auth_gated(tmp_path):
    client = await _client(tmp_path, token="s3cret")
    try:
        assert (await client.get("/api/preview")).status == 401
        assert not (tmp_path / "preview-requested").exists()  # 401s do not wake
    finally:
        await client.close()
```

- [ ] **Step 2: Run to verify failure** — 404 on `/api/preview`.

- [ ] **Step 3: Implement** in `src/led_ticker/webui/__init__.py`. Import at module top (purity-safe — `preview.py` is stdlib-only):

```python
from led_ticker.preview import HEADER, PREVIEW_MAGIC, PREVIEW_VERSION
```

In `build_webui_app`, derive the shared paths next to where `status_path` is in scope, and register a new route (sibling of the inventory handler):

```python
    preview_frame_path = status_path.parent / "preview.bin"
    preview_marker_path = status_path.parent / "preview-requested"

    async def preview_handler(request: web.Request) -> web.Response:
        # The fetch IS the watch signal: touch the marker first, so even an
        # idle answer wakes the display's mirror for the next poll. This is
        # the sidecar's only write, ever — one empty file, mtime-only.
        try:
            preview_marker_path.touch()
        except OSError:
            logger.debug("could not touch preview marker", exc_info=True)
        try:
            data = preview_frame_path.read_bytes()
        except FileNotFoundError:
            return web.json_response({"state": "idle"})
        except OSError as e:
            return web.json_response({"state": "idle", "detail": str(e)})
        if len(data) < HEADER.size:
            return web.json_response({"state": "unsupported"})
        magic, ver, w, h, _res, seq = HEADER.unpack(data[: HEADER.size])
        if (
            magic != PREVIEW_MAGIC
            or ver != PREVIEW_VERSION
            or len(data) != HEADER.size + w * h * 3
        ):
            return web.json_response({"state": "unsupported"})
        return web.Response(
            body=data[HEADER.size :],
            content_type="application/octet-stream",
            headers={
                "X-Preview-Width": str(w),
                "X-Preview-Height": str(h),
                "X-Preview-Seq": str(seq),
            },
        )

    app.router.add_get("/api/preview", preview_handler)
```

Extend `tests/test_webui_purity.py`'s subprocess import line with `led_ticker.preview` (the tee module must stay rgbmatrix-free).

- [ ] **Step 4: Run** `PYTHONPATH=tests/stubs uv run pytest tests/test_preview_endpoint.py tests/test_webui_app.py tests/test_webui_purity.py -q` — all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/webui/__init__.py tests/test_preview_endpoint.py tests/test_webui_purity.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "feat(preview): /api/preview endpoint with watch-marker touch"
```

---

### Task 7: the page — hero canvas + visibility-gated poller

**Files:**
- Modify: `src/led_ticker/webui/static/index.html`
- Test: `tests/test_webui_app.py` (extend the page-marker test with `"/api/preview"` and `"preview-canvas"`)

- [ ] **Step 1: Extend the marker test, run, see it fail.**

- [ ] **Step 2: Implement.** Markup — insert ABOVE the now-playing hero card in the Status tab:

```html
    <div class="card" style="text-align:center;">
      <div id="preview-bezel" style="display:inline-block;background:#000;border:6px solid #222;border-radius:8px;padding:6px;max-width:100%;">
        <canvas id="preview-canvas" width="1" height="1" style="image-rendering:pixelated;width:100%;max-width:1024px;display:block;"></canvas>
      </div>
      <div id="preview-note" class="muted"></div>
    </div>
```

CSS: nothing new needed beyond the inline styles above (matches the page's existing inline-style usage for one-off elements).

JS — add near the other poll machinery:

```javascript
let previewTimer = null;
let previewSeq = -1;
let previewIdlePolls = 0;

async function pollPreview() {
  try {
    const r = await fetch("/api/preview", {headers: auth});
    if (r.status === 401) { $("preview-note").textContent = "auth failed"; return; }
    const ctype = r.headers.get("Content-Type") || "";
    if (!ctype.includes("octet-stream")) {
      const body = await r.json();
      previewIdlePolls++;
      $("preview-note").textContent =
        body.state === "unsupported"
          ? "preview format mismatch — display and webui versions differ"
          : previewIdlePolls > 25
            ? "no preview frames — the display process predates this feature"
            : "waking the preview…";
      return;
    }
    previewIdlePolls = 0;
    const seq = +(r.headers.get("X-Preview-Seq") || -1);
    const w = +(r.headers.get("X-Preview-Width") || 0);
    const h = +(r.headers.get("X-Preview-Height") || 0);
    if (seq === previewSeq || !w || !h) return;  // unchanged frame: skip repaint
    const rgb = new Uint8Array(await r.arrayBuffer());
    const cv = $("preview-canvas");
    if (cv.width !== w || cv.height !== h) { cv.width = w; cv.height = h; }
    const img = new ImageData(w, h);
    for (let p = 0, q = 0; p < rgb.length; p += 3, q += 4) {
      img.data[q] = rgb[p];
      img.data[q + 1] = rgb[p + 1];
      img.data[q + 2] = rgb[p + 2];
      img.data[q + 3] = 255;
    }
    cv.getContext("2d").putImageData(img, 0, 0);
    previewSeq = seq;
    const scaleNote = (lastStatus && lastStatus.geometry &&
      lastStatus.geometry.default_scale === 1)
      ? " · text may differ by a pixel from the panel (scale-1 mirror)" : "";
    $("preview-note").textContent = "live · frame " + seq + scaleNote;
  } catch (e) {
    $("preview-note").textContent = "preview unreachable";
  }
}

function setPreviewPolling(on) {
  if (on && !previewTimer) {
    pollPreview();
    previewTimer = setInterval(pollPreview, 200);
  } else if (!on && previewTimer) {
    clearInterval(previewTimer);
    previewTimer = null;
  }
}

function previewShouldPoll() {
  return document.visibilityState === "visible" &&
    document.querySelector('nav button[data-tab="status"]').classList.contains("active");
}

document.addEventListener("visibilitychange", () => setPreviewPolling(previewShouldPoll()));
```

Wiring into the existing tab-switch handler: after the existing per-tab activation lines (`loadConfig()` / `loadConfigList()` / `loadInventory()`), add:

```javascript
  setPreviewPolling(previewShouldPoll());
```

And start it at page load next to `poll();`:

```javascript
setPreviewPolling(previewShouldPoll());
```

NOTE the 200 ms interval matches `CAPTURE_INTERVAL`; the seq check makes over-polling free. The RGB→RGBA loop is ~33k iterations for 512×64 — sub-millisecond in any modern browser.

- [ ] **Step 3: Run** `PYTHONPATH=tests/stubs uv run pytest tests/test_webui_app.py -q` — PASS.

- [ ] **Step 4: Commit**

```bash
git add src/led_ticker/webui/static/index.html tests/test_webui_app.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "feat(preview): hero panel preview on the status tab"
```

---

### Task 8: composition test, docs, gates, smoke, PR

**Files:**
- Test: `tools/render_demo/test_recording.py` or `tests/test_preview_tee.py` (the composition test — implementer's choice of home, prefer `tests/`)
- Modify: `docs/site/src/content/docs/concepts/web-status-ui.mdx`

- [ ] **Step 1: Composition test** (append to `tests/test_preview_tee.py`):

```python
def test_tee_composes_with_recording_matrix(tmp_path):
    """render_demo wraps the MATRIX; the tee wraps the CANVAS — they must
    compose (door open for preview-in-CI)."""
    import sys

    sys.path.insert(0, "tools")
    from render_demo.recording import RecordingMatrix

    from led_ticker.frame import LedFrame
    from led_ticker.preview import PreviewTee

    frame = LedFrame(led_cols=32, led_chain_length=1)
    frame.matrix = RecordingMatrix(frame.matrix)
    tee = PreviewTee(
        hw=frame.matrix.CreateFrameCanvas(),
        width=32,
        height=16,
        frame_path=tmp_path / "preview.bin",
    )
    frame.install_preview(tee)
    canvas = frame.get_clean_canvas()
    canvas.SetPixel(0, 0, 9, 9, 9)
    frame.swap(canvas)
    assert len(frame.matrix.frames) == 1  # RecordingMatrix captured the swap
```

(Check how existing render_demo tests import `recording` — mirror their sys.path/import idiom exactly rather than the sketch above if it differs.)

- [ ] **Step 2: Docs.** Read `docs/DOCS-STYLE.md` first. In the concepts page: add a "Live preview" subsection under the dashboard section — what it shows (the actual panel, busy-dot included, ~5 fps), that it costs nothing while the page is closed (the mirror wakes when the page looks and sleeps ~10 s after it stops), the scale-1 one-pixel text caveat, and a troubleshooting line ("preview stuck on 'waking…'" → display process predates the feature / `[web]` missing). Prettier + `make docs-lint` clean.

- [ ] **Step 3: Full gates.**

```bash
PYTHONPATH=tests/stubs uv run pytest -q
uv run --extra dev ruff check src/ tests/
uv run --extra dev ruff format --check src/ tests/ | tail -1
PYTHONPATH=tests/stubs uv run pyright src/
make docs-lint
```
All green; report exact numbers.

- [ ] **Step 4: Smoke test** (throwaway script under /tmp, deleted after): build a real `LedFrame` (stub), install a tee pointed at a temp dir, run a few `get_clean_canvas → draw text+pixels → swap` cycles with the marker file fresh, start `serve_webui` against the same dir, fetch `/api/preview`, unpack header+payload, assert the drawn pixels are in the payload, assert the marker got re-touched by the fetch. Paste the output in the report.

- [ ] **Step 5: Push + PR (do NOT merge — the user confirms merges).** PR body covers: the watched-flag lifecycle, the spine invariant, the perf posture table from the spec, the scale-1 caveat, and the on-device validation steps for longboi:
  - pull + `COMPOSE_PROFILES=webui docker compose up -d --build`
  - open the page → preview appears within ~2 s; close the page → `ls /run/led-ticker/` inside the container shows `preview.bin` gone within ~12 s
  - watch the panel while previewing a text section and a gif section — no visible stutter (the gif case is the named worst case; report what you see)
  - micro-bench: time 1000 `SetPixel` calls through the tee with mirror off vs on vs raw canvas, in-container, paste numbers into the PR thread

```bash
git push -u origin feat/live-preview
gh pr create --title "feat: live display preview — watched-only shadow mirror" --body "..."
```

---

## Self-review notes (done at plan-writing time)

- **Spec coverage:** lifecycle/marker (T5, T6), shadow+capture+format (T1, T2), frame integration + overlay-hooks-in-preview + rebind (T3), scale-1 funnel + fidelity standard (T4), ScaledCanvas chain (T5), endpoint envelopes + auth + marker (T6), page incl. visibility gating + seq skip + upgrade messaging + scale-1 caption (T7), composition + docs + perf gates + hardware bench (T8). Spine invariant tested in T1 and re-exercised via T4's sabotage test. Out-of-scope items appear in no task.
- **Type consistency:** `PreviewTee(hw=, width=, height=, frame_path=)`, `set_watched(bool)`, `maybe_capture(now=None)`, `mirror_bdf_text(bdf, x, y, color, text)`, `install_preview(tee)`, `_setup_preview(config, led_frame)`, `_status_heartbeat(board, tee=None, marker_ttl=10.0)` — used identically across tasks. Header struct `<4sHHHHI` shared via `preview.py` imports on both sides.
- **Known uncertainties flagged inline:** `get_bdf_for` caching (T4 — gated form mandated), render_demo import idiom (T8), heartbeat-spawn-order tripwire interactions (T5), marker-path contract note (T5).
- **No status.json changes** → schema stays 2, no drift-test changes; **no new TOML fields** → config-options page untouched.
