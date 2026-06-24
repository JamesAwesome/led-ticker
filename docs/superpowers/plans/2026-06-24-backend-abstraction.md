# Backend Abstraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Decouple the rendering engine from `rpi-rgb-led-matrix` behind a `Backend` protocol, ship a runtime-selectable `headless` backend, and provide an importable conformance kit — without changing production hardware behavior.

**Architecture:** A narrow `Backend` protocol owns the matrix lifecycle (`setup`/`create_canvas`/`swap`/`brightness`). `LedFrame` holds a backend and keeps all backend-agnostic mechanism (overlay hooks, status-board swap recording, preview tee, framerate). Two built-in backends — `RgbMatrixBackend` (the existing path) and `HeadlessBackend` (the promoted test stub) — register in a name→class registry selected via `[display] backend`.

**Tech Stack:** Python 3.14, `attrs`, `pytest`, `typing.Protocol`/`runtime_checkable`. No `from __future__ import annotations` anywhere (PEP 649 / project rule). stdlib `tomllib` for config.

**Spec:** `docs/superpowers/specs/2026-06-24-backend-abstraction-design.md`

## Global Constraints

- **No `from __future__ import annotations`** in any file (project + plugin rule; PEP 649).
- **Production rgbmatrix behavior must stay byte-identical** — the options-building moves verbatim (including the `hasattr` version-tolerance guards and the `_framerate_fraction` derivation).
- **Hardware rendering constraints (CLAUDE.md) are the contract** — especially: `swap()` MUST return a *different* canvas object (#1/#8); no `GetPixel` (#3); `SetPixel` works everywhere (#4); the privilege drop happens at one declared point (#13).
- **`build_frame_from_config` returns an UN-SETUP frame.** `run()` calls `led_frame.setup()` at one explicit line, after all pre-drop privileged work and before any consumer that needs a live backend.
- **Run `make test` (sets `PYTHONPATH=tests/stubs`) after every task** until Task 9 retires that path; from Task 9 on, `make test` runs without it.
- **Lint/format:** `make lint` and `make format` (ruff) clean before each commit.
- **`attrs` style:** new stateful classes use `@attrs.define` to match the codebase (`LedFrame` is `@attrs.define`).

---

## File Structure

- `src/led_ticker/backends/__init__.py` — **Create.** `Backend` Protocol, `BackendNotReadyError`, name→class registry, `get_backend_class(name)`, `known_backends()`.
- `src/led_ticker/backends/headless.py` — **Create.** `HeadlessBackend` + `HeadlessCanvas` (promoted from `tests/stubs/rgbmatrix/`).
- `src/led_ticker/backends/rgbmatrix.py` — **Create.** `RgbMatrixBackend` (owns `RGBMatrixOptions` building + `RGBMatrix` construction).
- `src/led_ticker/backends/conformance.py` — **Create.** `run_backend_conformance(backend_factory)` + individual checks.
- `src/led_ticker/frame.py` — **Modify.** `LedFrame` holds a `backend`; `setup()`; `create_canvas()`; `brightness` property; pre-setup guards; `_framerate_fraction` from backend.
- `src/led_ticker/app/factories.py:957` — **Modify.** `build_frame_from_config` selects a backend from `display.backend` and returns an un-setup `LedFrame`.
- `src/led_ticker/app/run.py` — **Modify.** Call `led_frame.setup()` after `build_frame_from_config`; repoint `matrix.brightness` writes and `matrix.CreateFrameCanvas()`; failure-mode logging.
- `src/led_ticker/transitions/__init__.py:263,308` — **Modify.** Repoint `frame.matrix.CreateFrameCanvas()` → `frame.create_canvas()`.
- `src/led_ticker/config.py:28` — **Modify.** Add `backend: str = "rgbmatrix"` to `DisplayConfig` + loader wiring.
- `src/led_ticker/_types.py` — **Modify.** Widen `CanvasLike` with `SubFill` + `SetImage`.
- `src/led_ticker/text_render.py` — **Modify (Task 10).** Route scale=1 through the rasterizer behind a flag; collapse the PreviewTee branch.
- `tests/stubs/rgbmatrix/` — **Delete (Task 9).** Collapsed into `HeadlessBackend`.
- `Makefile:17`, `pyproject.toml:84` — **Modify (Task 9).** Remove `PYTHONPATH=tests/stubs` / `extraPaths` / `pythonpath`.
- `tests/test_backends/` — **Create.** New test package for backend + conformance tests.

---

### Task 1: `Backend` protocol + registry

**Files:**
- Create: `src/led_ticker/backends/__init__.py`
- Test: `tests/test_backends/test_registry.py`, `tests/test_backends/__init__.py`

**Interfaces:**
- Produces:
  - `class Backend(Protocol)` — `runtime_checkable`; members `brightness: int`, `framerate_fraction: int`, `setup() -> None`, `create_canvas() -> Canvas`, `swap(canvas, framerate_fraction: int = 1) -> Canvas`.
  - `class BackendNotReadyError(RuntimeError)` — raised on pre-`setup()` access.
  - `register_backend(name: str)` — class decorator.
  - `get_backend_class(name: str) -> type` — raises `ValueError` listing `known_backends()` on miss.
  - `known_backends() -> list[str]` — sorted registered names.

- [ ] **Step 1: Create the test package**

Create `tests/test_backends/__init__.py` (empty file).

- [ ] **Step 2: Write the failing test**

Create `tests/test_backends/test_registry.py`:

```python
import pytest

from led_ticker.backends import (
    Backend,
    BackendNotReadyError,
    get_backend_class,
    known_backends,
    register_backend,
)


def test_register_and_get():
    @register_backend("dummy_test_backend")
    class _Dummy:
        pass

    assert get_backend_class("dummy_test_backend") is _Dummy
    assert "dummy_test_backend" in known_backends()


def test_unknown_backend_lists_known():
    with pytest.raises(ValueError) as exc:
        get_backend_class("does_not_exist")
    assert "does_not_exist" in str(exc.value)
    # Message enumerates valid names so the user can self-correct.
    assert "rgbmatrix" in str(exc.value) or known_backends() == []


def test_backend_protocol_is_runtime_checkable():
    class _Conforming:
        brightness = 100
        framerate_fraction = 1

        def setup(self): ...
        def create_canvas(self): ...
        def swap(self, canvas, framerate_fraction=1): ...

    assert isinstance(_Conforming(), Backend)


def test_backend_not_ready_error_is_runtimeerror():
    assert issubclass(BackendNotReadyError, RuntimeError)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `make test 2>/dev/null; PYTHONPATH=tests/stubs uv run pytest tests/test_backends/test_registry.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'led_ticker.backends'`.

- [ ] **Step 4: Write the implementation**

Create `src/led_ticker/backends/__init__.py`:

```python
"""Rendering-backend abstraction.

A `Backend` owns the matrix lifecycle the engine assumes: build the matrix
(privileged work) in `setup()`, hand out fresh back-buffer canvases via
`create_canvas()`, and present a canvas via `swap()` (returning the NEW
back-buffer — constraints #1/#8). `LedFrame` holds a backend and keeps all
backend-agnostic mechanism (overlay hooks, status-board, preview tee).

The 13 hardware-rendering constraints in CLAUDE.md are this protocol's
contract; `backends.conformance` encodes them as an importable test suite.
"""

from typing import Protocol, runtime_checkable

from led_ticker._types import Canvas


class BackendNotReadyError(RuntimeError):
    """Raised when a canvas/swap/brightness operation is attempted before
    `Backend.setup()` (and therefore before the matrix exists)."""


@runtime_checkable
class Backend(Protocol):
    """The rendering-backend contract. See module docstring + CLAUDE.md."""

    brightness: int  # settable; live brightness scheduling. The only mutable attr.
    framerate_fraction: int  # presentation hint; rgbmatrix-specific, 1 elsewhere.

    def setup(self) -> None:
        """Build the underlying matrix and perform all privileged work.
        The declared privilege-drop boundary. Called exactly once by the app
        after all pre-drop work."""
        ...

    def create_canvas(self) -> Canvas:
        """Return a fresh back-buffer canvas."""
        ...

    def swap(self, canvas: Canvas, framerate_fraction: int = 1) -> Canvas:
        """Present `canvas`; return the NEW back-buffer to draw into next.
        MUST return a different object than it was handed (constraints #1/#8)."""
        ...


_REGISTRY: dict[str, type] = {}


def register_backend(name: str):
    """Class decorator: register a backend implementation under `name`."""

    def _decorate(cls: type) -> type:
        _REGISTRY[name] = cls
        return cls

    return _decorate


def known_backends() -> list[str]:
    """Sorted list of registered backend names."""
    return sorted(_REGISTRY)


def get_backend_class(name: str) -> type:
    """Resolve a backend class by name. Raises ValueError (listing the known
    names) on an unknown name so the user can self-correct."""
    try:
        return _REGISTRY[name]
    except KeyError:
        raise ValueError(
            f"unknown backend {name!r}; known backends: {known_backends()}"
        ) from None
```

- [ ] **Step 5: Run test to verify it passes**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_backends/test_registry.py -v`
Expected: PASS (4 tests). The `known_backends() == []` fallback in `test_unknown_backend_lists_known` holds now since no backend is registered yet.

- [ ] **Step 6: Lint, format, commit**

```bash
make format && make lint
git add src/led_ticker/backends/__init__.py tests/test_backends/
git commit -m "feat(backends): Backend protocol + name->class registry"
```

---

### Task 2: `HeadlessBackend` (promote the stub)

**Files:**
- Create: `src/led_ticker/backends/headless.py`
- Test: `tests/test_backends/test_headless.py`

**Interfaces:**
- Consumes: `register_backend` (Task 1).
- Produces:
  - `class HeadlessCanvas` — `width`, `height`; methods `Clear`, `Fill(r,g,b)`, `SetPixel(x,y,r,g,b)`, `SubFill(x,y,w,h,r,g,b)`, `SetImage(image, offset_x=0, offset_y=0)`; test helpers `get_pixel(x,y) -> tuple[int,int,int]`, `count_nonzero() -> int`.
  - `class HeadlessBackend` — `__init__(self, width: int, height: int, *, pixel_mapper_config: str = "")`; attrs `brightness: int = 100`, `framerate_fraction: int = 1`; `setup()`, `create_canvas() -> HeadlessCanvas`, `swap(canvas, framerate_fraction=1) -> HeadlessCanvas`. Registered as `"headless"`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_backends/test_headless.py`:

```python
from led_ticker.backends import Backend, get_backend_class
from led_ticker.backends.headless import HeadlessBackend, HeadlessCanvas


def test_registered_as_headless():
    assert get_backend_class("headless") is HeadlessBackend


def test_satisfies_backend_protocol():
    assert isinstance(HeadlessBackend(160, 16), Backend)


def test_canvas_full_method_surface():
    c = HeadlessCanvas(width=8, height=8)
    c.SetPixel(1, 1, 10, 20, 30)
    assert c.get_pixel(1, 1) == (10, 20, 30)
    c.SubFill(0, 0, 2, 2, 5, 5, 5)
    assert c.get_pixel(0, 0) == (5, 5, 5)
    c.Fill(9, 9, 9)
    assert c.count_nonzero() == 64
    c.Clear()
    assert c.count_nonzero() == 0


def test_swap_returns_a_different_canvas_object():
    # Constraints #1/#8: the returned back-buffer is NOT the one handed in.
    b = HeadlessBackend(160, 16)
    b.setup()
    front = b.create_canvas()
    back = b.swap(front)
    assert back is not front


def test_u_mapper_reshapes_canvas():
    b = HeadlessBackend(64 * 8, 32, pixel_mapper_config="U-mapper")
    b.setup()
    c = b.create_canvas()
    # U-mapper folds the chain in half: doubles height, halves width.
    assert (c.width, c.height) == (64 * 8 // 2, 32 * 2)


def test_setpixel_clips_out_of_bounds():
    c = HeadlessCanvas(width=4, height=4)
    c.SetPixel(99, 99, 1, 2, 3)  # silently ignored
    assert c.count_nonzero() == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_backends/test_headless.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'led_ticker.backends.headless'`.

- [ ] **Step 3: Write the implementation**

Create `src/led_ticker/backends/headless.py`. Port `_StubCanvas` + `RGBMatrix` double-buffering from `tests/stubs/rgbmatrix/__init__.py` verbatim in behavior (including U-mapper reshape, SetImage alpha-on-black flatten, and the different-object swap):

```python
"""Headless software backend — runs the full engine with no hardware.

Promoted from the former `tests/stubs/rgbmatrix/` test stub. Shipped and
runtime-selectable via `[display] backend = "headless"`. Provides a software
canvas implementing the full Canvas contract and a double-buffered `swap()`
that returns a DIFFERENT canvas object each call (constraints #1/#8), so
dropped-capture bugs surface here exactly as on hardware.
"""

from typing import Any

from led_ticker.backends import register_backend


class HeadlessCanvas:
    """Software canvas with pixel storage. Satisfies the Canvas contract:
    SetPixel / Clear / Fill / SubFill / SetImage, plus test-only get_pixel /
    count_nonzero helpers."""

    def __init__(self, width: int = 160, height: int = 16) -> None:
        self.width = width
        self.height = height
        self._pixels: dict[tuple[int, int], tuple[int, int, int]] = {}

    def Clear(self) -> None:
        self._pixels.clear()

    def Fill(self, r: int, g: int, b: int) -> None:
        for y in range(self.height):
            for x in range(self.width):
                self._pixels[(x, y)] = (r, g, b)

    def SetPixel(self, x: int, y: int, r: int, g: int, b: int) -> None:
        if 0 <= x < self.width and 0 <= y < self.height:
            self._pixels[(x, y)] = (r, g, b)

    def SubFill(
        self, x: int, y: int, width: int, height: int, red: int, green: int, blue: int
    ) -> None:
        for dy in range(height):
            for dx in range(width):
                self.SetPixel(x + dx, y + dy, red, green, blue)

    def SetImage(self, image: Any, offset_x: int = 0, offset_y: int = 0) -> None:
        """Walk a PIL image and SetPixel each pixel. The real C lib pushes RGB
        bytes in one call; fidelity (not speed) is the job here. Alpha==0
        flattens onto black, matching the production SetImage path."""
        pixels = image.load()
        w, h = image.size
        for y in range(h):
            for x in range(w):
                px = pixels[x, y]
                if len(px) == 4 and px[3] == 0:
                    r, g, b = 0, 0, 0
                else:
                    r, g, b = px[0], px[1], px[2]
                self.SetPixel(offset_x + x, offset_y + y, r, g, b)

    # Test-only helpers (not part of the Canvas contract).
    def get_pixel(self, x: int, y: int) -> tuple[int, int, int]:
        return self._pixels.get((x, y), (0, 0, 0))

    def count_nonzero(self) -> int:
        return sum(1 for v in self._pixels.values() if v != (0, 0, 0))


@register_backend("headless")
class HeadlessBackend:
    """Software backend. No privilege drop; no hardware output."""

    def __init__(
        self, width: int, height: int, *, pixel_mapper_config: str = ""
    ) -> None:
        if pixel_mapper_config == "U-mapper":
            # U-mapper folds the chain in half: doubles height, halves width.
            assert width % 2 == 0, "U-mapper requires an even effective width"
            width, height = width // 2, height * 2
        self._width = width
        self._height = height
        self.brightness = 100
        self.framerate_fraction = 1
        self._back_buffer: HeadlessCanvas | None = None

    def setup(self) -> None:
        # No matrix to build, no privileges to drop.
        return None

    def create_canvas(self) -> HeadlessCanvas:
        return HeadlessCanvas(width=self._width, height=self._height)

    def swap(
        self, canvas: HeadlessCanvas, framerate_fraction: int = 1
    ) -> HeadlessCanvas:
        if self._back_buffer is None:
            self._back_buffer = HeadlessCanvas(
                width=self._width, height=self._height
            )
        old_back = self._back_buffer
        self._back_buffer = canvas
        return old_back
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_backends/test_headless.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Lint, format, commit**

```bash
make format && make lint
git add src/led_ticker/backends/headless.py tests/test_backends/test_headless.py
git commit -m "feat(backends): HeadlessBackend promoted from the test stub"
```

---

### Task 3: `RgbMatrixBackend` (extract options-building)

**Files:**
- Create: `src/led_ticker/backends/rgbmatrix.py`
- Test: `tests/test_backends/test_rgbmatrix_backend.py`

**Interfaces:**
- Consumes: `register_backend` (Task 1); `RGBMatrix`, `RGBMatrixOptions` from `led_ticker._compat`.
- Produces:
  - `class RgbMatrixBackend` — `__init__` takes the **same `led_*` fields `LedFrame` holds today** (verbatim list below) as keyword args with the same defaults. Attrs: settable `brightness`, `framerate_fraction` (computed in `setup()`). `setup()` builds `RGBMatrixOptions`, constructs `RGBMatrix`, derives `framerate_fraction`. `create_canvas()` → `matrix.CreateFrameCanvas()`. `swap(canvas, framerate_fraction=1)` → `matrix.SwapOnVSync(...)`. Registered as `"rgbmatrix"`.
  - `build_options(backend) -> RGBMatrixOptions` — a module function so the parity test can assert option fields without constructing a matrix.

- [ ] **Step 1: Write the failing test**

Create `tests/test_backends/test_rgbmatrix_backend.py` (runs against the stub `RGBMatrixOptions`, which has every attr — a structural parity guard, per spec):

```python
from led_ticker.backends import Backend, get_backend_class
from led_ticker.backends.rgbmatrix import RgbMatrixBackend, build_options


def test_registered_as_rgbmatrix():
    assert get_backend_class("rgbmatrix") is RgbMatrixBackend


def test_satisfies_backend_protocol():
    assert isinstance(RgbMatrixBackend(), Backend)


def test_build_options_maps_fields():
    b = RgbMatrixBackend(
        led_rows=16,
        led_cols=32,
        led_chain_length=5,
        led_gpio_slowdown=2,
        led_pwm_bits=8,
        led_hardware_mapping="adafruit-hat",
    )
    opts = build_options(b)
    assert opts.rows == 16
    assert opts.cols == 32
    assert opts.chain_length == 5
    assert opts.gpio_slowdown == 2
    assert opts.pwm_bits == 8
    assert opts.hardware_mapping == "adafruit-hat"


def test_framerate_fraction_default_until_setup():
    b = RgbMatrixBackend(led_limit_refresh_rate_hz=0)
    b.setup()
    assert b.framerate_fraction == 1


def test_framerate_fraction_from_refresh_cap():
    # _ENGINE_FPS = 20; 60Hz cap => round(60/20) = 3.
    b = RgbMatrixBackend(led_limit_refresh_rate_hz=60)
    b.setup()
    assert b.framerate_fraction == 3


def test_swap_returns_different_object_through_stub():
    b = RgbMatrixBackend(led_rows=16, led_cols=32, led_chain_length=5)
    b.setup()
    front = b.create_canvas()
    back = b.swap(front, b.framerate_fraction)
    assert back is not front
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_backends/test_rgbmatrix_backend.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'led_ticker.backends.rgbmatrix'`.

- [ ] **Step 3: Write the implementation**

Create `src/led_ticker/backends/rgbmatrix.py`. Move the option-building from `frame.py:51-95` **verbatim** (keep every `hasattr` guard) and the `_framerate_fraction` derivation. `_ENGINE_FPS = 20` (kept in sync with `ENGINE_TICK_MS = 50`):

```python
"""Production rgbmatrix backend.

Owns the RGBMatrixOptions building (moved verbatim from LedFrame, including
the version-tolerant hasattr guards) and constructs RGBMatrix in setup() —
the privilege-drop point (root -> daemon). Behavior is byte-identical to the
pre-refactor LedFrame path.
"""

import attrs

from led_ticker._compat import RGBMatrix, RGBMatrixOptions, require_matrix
from led_ticker._types import Canvas
from led_ticker.backends import register_backend

_ENGINE_FPS: int = 20  # must stay in sync with ENGINE_TICK_MS = 50 in ticker.py


def build_options(backend: "RgbMatrixBackend") -> RGBMatrixOptions:
    """Build RGBMatrixOptions from a backend's led_* fields. Verbatim move of
    LedFrame.__attrs_post_init__'s option mapping; keep the hasattr guards —
    they tolerate older installed rgbmatrix builds."""
    options = RGBMatrixOptions()

    if backend.led_hardware_mapping is not None:
        options.hardware_mapping = backend.led_hardware_mapping

    options.rows = backend.led_rows
    options.cols = backend.led_cols
    options.chain_length = backend.led_chain_length
    options.parallel = backend.led_parallel
    options.row_address_type = backend.led_row_address_type
    options.multiplexing = backend.led_multiplexing
    options.pwm_bits = backend.led_pwm_bits
    options.brightness = backend.brightness
    options.pwm_lsb_nanoseconds = backend.led_pwm_lsb_nanoseconds
    if backend.led_pwm_dither_bits and hasattr(options, "pwm_dither_bits"):
        options.pwm_dither_bits = backend.led_pwm_dither_bits  # type: ignore[attr-defined]
    options.led_rgb_sequence = backend.led_rgb_sequence
    options.pixel_mapper_config = backend.led_pixel_mapper_config
    options.panel_type = backend.led_panel_type

    if backend.led_show_refresh_rate:
        options.show_refresh_rate = 1
    if backend.led_gpio_slowdown is not None:
        options.gpio_slowdown = backend.led_gpio_slowdown
    if backend.led_disable_hardware_pulsing:
        options.disable_hardware_pulsing = True
    # rp1_pio exposed by rgbmatrix builds from June 2026 onward.
    if backend.led_rp1_pio and hasattr(options, "rp1_pio"):
        options.rp1_pio = backend.led_rp1_pio
    if backend.led_limit_refresh_rate_hz and hasattr(options, "limit_refresh_rate_hz"):
        options.limit_refresh_rate_hz = backend.led_limit_refresh_rate_hz

    return options


@attrs.define
class RgbMatrixBackend:
    """rgbmatrix hardware backend. Matrix built (and privileges dropped) in
    setup()."""

    led_rows: int = 16
    led_cols: int = 32
    led_chain_length: int = 1
    led_parallel: int = 1
    led_pwm_bits: int = 11
    led_pwm_dither_bits: int = 0
    brightness: int = 100
    led_hardware_mapping: str = "adafruit-hat"
    led_scan_mode: int = 0
    led_pwm_lsb_nanoseconds: int = 130
    led_show_refresh_rate: bool = False
    led_gpio_slowdown: int = 1
    led_disable_hardware_pulsing: bool = False
    led_rgb_sequence: str = "RGB"
    led_pixel_mapper_config: str = ""
    led_row_address_type: int = 0
    led_multiplexing: int = 0
    led_panel_type: str = ""
    led_rp1_pio: int = 0
    led_limit_refresh_rate_hz: int = 0
    framerate_fraction: int = attrs.field(init=False, default=1)
    _matrix: object = attrs.field(init=False, default=None)

    def setup(self) -> None:
        options = build_options(self)
        matrix_cls = require_matrix() if RGBMatrix is None else RGBMatrix
        # Constructing RGBMatrix drops root -> daemon (constraint #13).
        self._matrix = matrix_cls(options=options)
        self.framerate_fraction = (
            max(1, round(self.led_limit_refresh_rate_hz / _ENGINE_FPS))
            if self.led_limit_refresh_rate_hz
            else 1
        )

    def create_canvas(self) -> Canvas:
        return self._matrix.CreateFrameCanvas()

    def swap(self, canvas: Canvas, framerate_fraction: int = 1) -> Canvas:
        return self._matrix.SwapOnVSync(canvas, framerate_fraction)
```

Note: `brightness` is mutated post-`setup()` by the schedule ticker via `LedFrame.brightness` → `self._matrix.brightness`. The backend exposes `brightness` as a plain attr for *construction*; the live mutation goes through the matrix (Task 4 wires `LedFrame.brightness` to forward to `self.backend` which forwards to `self._matrix`). Add a `brightness` property forwarding to the matrix once built:

```python
    # Replace the plain `brightness` attr usage at runtime: after setup(),
    # writes must reach the live matrix. Implemented in Task 4 via LedFrame's
    # property delegating to backend; backend stores pre-setup brightness and
    # forwards to self._matrix.brightness once built.
```

For this task, keep `brightness` as the attrs field (construction-time value used in `build_options`). Task 4 adds the live-forwarding.

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_backends/test_rgbmatrix_backend.py -v`
Expected: PASS (6 tests). `require_matrix()` is not hit because the stub provides `RGBMatrix`.

- [ ] **Step 5: Lint, format, commit**

```bash
make format && make lint
git add src/led_ticker/backends/rgbmatrix.py tests/test_backends/test_rgbmatrix_backend.py
git commit -m "feat(backends): RgbMatrixBackend owns options-building + matrix lifecycle"
```

---

### Task 4: Refactor `LedFrame` to hold a backend

This is the breaking change. `LedFrame` stops building `RGBMatrix` itself, holds a `backend`, and gains `setup()`, `create_canvas()`, and a live `brightness` property with pre-setup guards. `build_frame_from_config` and `run()` are updated in the same task to keep the suite green.

**Files:**
- Modify: `src/led_ticker/frame.py` (rewrite `LedFrame`)
- Modify: `src/led_ticker/app/factories.py:957-1010+` (`build_frame_from_config`)
- Modify: `src/led_ticker/app/run.py:599` (call `setup()`)
- Test: `tests/test_backends/test_led_frame_backend.py`; existing `tests/test_frame*.py` (if present) updated

**Interfaces:**
- Consumes: `Backend`, `BackendNotReadyError` (Task 1); `RgbMatrixBackend` (Task 3); `HeadlessBackend` (Task 2).
- Produces:
  - `LedFrame.__init__(backend: Backend, *, overlay_hooks=[])` — holds a backend; no `led_*` fields.
  - `LedFrame.setup() -> None` — calls `backend.setup()`; flips a `_ready` flag.
  - `LedFrame.create_canvas() -> Canvas` — raw canvas via `backend.create_canvas()`; raises `BackendNotReadyError` before `setup()`.
  - `LedFrame.brightness` property — get/set forwarding to `backend`; raises `BackendNotReadyError` before `setup()`.
  - `LedFrame.get_clean_canvas()` / `swap()` — unchanged signatures; now route through the backend; raise `BackendNotReadyError` before `setup()`.
  - `build_frame_from_config(display) -> LedFrame` — returns an **un-setup** frame.

- [ ] **Step 1: Write the failing test**

Create `tests/test_backends/test_led_frame_backend.py`:

```python
import pytest

from led_ticker.backends import BackendNotReadyError
from led_ticker.backends.headless import HeadlessBackend
from led_ticker.frame import LedFrame


def _frame():
    return LedFrame(backend=HeadlessBackend(160, 16))


def test_create_canvas_before_setup_raises():
    f = _frame()
    with pytest.raises(BackendNotReadyError):
        f.create_canvas()


def test_swap_before_setup_raises():
    f = _frame()
    with pytest.raises(BackendNotReadyError):
        f.swap(object())


def test_brightness_before_setup_raises():
    f = _frame()
    with pytest.raises(BackendNotReadyError):
        _ = f.brightness
    with pytest.raises(BackendNotReadyError):
        f.brightness = 50


def test_create_canvas_after_setup():
    f = _frame()
    f.setup()
    c = f.create_canvas()
    assert (c.width, c.height) == (160, 16)


def test_swap_returns_different_object_and_records(monkeypatch):
    import led_ticker.status_board as sb

    calls = []
    monkeypatch.setattr(sb, "record_swap", lambda: calls.append(1))
    f = _frame()
    f.setup()
    front = f.get_clean_canvas()
    back = f.swap(front)
    assert back is not front
    assert calls  # record_swap fired inside swap


def test_overlay_hooks_run_in_swap():
    f = _frame()
    f.setup()
    painted = []
    f.overlay_hooks.append(lambda canvas: painted.append(canvas))
    c = f.get_clean_canvas()
    f.swap(c)
    assert painted == [c]


def test_brightness_forwards_after_setup():
    f = _frame()
    f.setup()
    f.brightness = 42
    assert f.brightness == 42
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_backends/test_led_frame_backend.py -v`
Expected: FAIL — `LedFrame.__init__` does not accept `backend` (current signature uses `led_*`).

- [ ] **Step 3: Rewrite `LedFrame`**

Replace the body of `src/led_ticker/frame.py` with:

```python
"""LED matrix frame wrapper — backend-agnostic render mechanism."""

from collections.abc import Callable
from typing import Any

import attrs

from led_ticker import status_board
from led_ticker.backends import Backend, BackendNotReadyError
from led_ticker._types import Canvas


@attrs.define
class LedFrame:
    """Backend-agnostic frame: overlay hooks, status-board swap recording, the
    preview tee, and framerate live here. The backend owns the matrix
    lifecycle. Nothing outside LedFrame touches the backend directly."""

    backend: Backend
    overlay_hooks: list[Callable[[Canvas], None]] = attrs.field(factory=list)
    _preview_tee: Any = attrs.field(init=False, default=None)
    _ready: bool = attrs.field(init=False, default=False)

    def setup(self) -> None:
        """Build the backend's matrix (privilege-drop boundary, constraint
        #13) and mark the frame ready. Call exactly once, after all pre-drop
        privileged work (prepare_dir, validation) and before any consumer that
        needs a live backend (preview tee, brightness scheduler)."""
        self.backend.setup()
        self._ready = True

    def _require_ready(self) -> None:
        if not self._ready:
            raise BackendNotReadyError(
                "backend not set up — call LedFrame.setup() before drawing"
            )

    @property
    def brightness(self) -> int:
        self._require_ready()
        return self.backend.brightness

    @brightness.setter
    def brightness(self, value: int) -> None:
        self._require_ready()
        self.backend.brightness = value

    def install_preview(self, tee: Any) -> None:
        """Install the (single, process-lifetime) preview tee."""
        self._preview_tee = tee

    def create_canvas(self) -> Canvas:
        """Raw back-buffer canvas (no Clear, no tee). Used by the preview-tee
        setup and cross-scale transitions."""
        self._require_ready()
        return self.backend.create_canvas()

    def get_clean_canvas(self) -> Canvas:
        """A cleared canvas ready for rendering (tee-aware)."""
        self._require_ready()
        canvas = self.backend.create_canvas()
        canvas.Clear()
        tee = self._preview_tee
        if tee is not None:
            tee._hw = canvas
            if tee.mirror:
                tee.Clear()
            return tee
        return canvas

    def swap(self, canvas: Canvas) -> Canvas:
        """Single centralized swap point. Overlay hooks paint on the real
        canvas before the backend swap; status_board records liveness. Hooks
        must be paint-only and not raise (see CLAUDE.md overlay invariant)."""
        self._require_ready()
        for hook in self.overlay_hooks:
            hook(canvas)
        status_board.record_swap()
        ff = self.backend.framerate_fraction
        tee = self._preview_tee
        if tee is not None and canvas is tee:
            new_hw = self.backend.swap(tee._hw, ff)
            tee.maybe_capture()
            tee._hw = new_hw
            return tee
        return self.backend.swap(canvas, ff)
```

- [ ] **Step 4: Wire `RgbMatrixBackend.brightness` to forward to the live matrix**

In `src/led_ticker/backends/rgbmatrix.py`, change `brightness` from a plain attrs field to a property backed by a private field so post-`setup()` writes reach the matrix. Replace the `brightness: int = 100` field and add:

```python
    _brightness: int = attrs.field(alias="brightness", default=100)

    @property
    def brightness(self) -> int:
        if self._matrix is not None:
            return self._matrix.brightness
        return self._brightness

    @brightness.setter
    def brightness(self, value: int) -> None:
        self._brightness = value
        if self._matrix is not None:
            self._matrix.brightness = value
```

Update `build_options` to read `backend._brightness` (construction value) instead of `backend.brightness`:

```python
    options.brightness = backend._brightness
```

Re-run Task 3's test to confirm still green: `PYTHONPATH=tests/stubs uv run pytest tests/test_backends/test_rgbmatrix_backend.py -v` (the `brightness` alias keeps `RgbMatrixBackend(... )` construction working; `build_options` still maps it).

- [ ] **Step 5: Update `build_frame_from_config`**

In `src/led_ticker/app/factories.py`, change the `return LedFrame(led_*=...)` (line 1024+) to select a backend and return an un-setup frame. Keep the logging block above unchanged. Replace the `return LedFrame(...)` block:

```python
    from led_ticker.backends import get_backend_class  # noqa: PLC0415
    from led_ticker.backends.rgbmatrix import RgbMatrixBackend  # noqa: PLC0415

    backend_name = getattr(display, "backend", "rgbmatrix")
    backend_cls = get_backend_class(backend_name)
    if backend_cls is RgbMatrixBackend:
        backend = RgbMatrixBackend(
            led_rows=display.rows,
            led_cols=display.cols,
            led_chain_length=display.chain_length,
            led_parallel=display.parallel,
            led_pixel_mapper_config=display.pixel_mapper_config,
            led_gpio_slowdown=display.gpio_slowdown,
            brightness=display.brightness,
            led_hardware_mapping=display.hardware_mapping,
            led_pwm_bits=display.pwm_bits,
            led_pwm_lsb_nanoseconds=display.pwm_lsb_nanoseconds,
            led_pwm_dither_bits=display.pwm_dither_bits,
            led_rgb_sequence=display.led_rgb_sequence,
            led_show_refresh_rate=display.show_refresh_rate,
            led_disable_hardware_pulsing=display.disable_hardware_pulsing,
            led_rp1_pio=display.rp1_pio,
            led_limit_refresh_rate_hz=display.limit_refresh_rate_hz,
            led_multiplexing=display.multiplexing,
            led_row_address_type=display.row_address_type,
            led_panel_type=display.panel_type,
        )
    else:
        # Headless (and future software backends): size from rows*chain x
        # parallel*cols-equivalent; reuse the rgbmatrix geometry convention.
        from led_ticker.backends.headless import HeadlessBackend  # noqa: PLC0415

        width = display.cols * display.chain_length
        height = display.rows * display.parallel
        backend = HeadlessBackend(
            width, height, pixel_mapper_config=display.pixel_mapper_config
        )
    return LedFrame(backend=backend)
```

Confirm the remaining `return LedFrame(led_rows=...)` original block is fully removed.

- [ ] **Step 6: Call `setup()` in `run()`**

In `src/led_ticker/app/run.py`, immediately after line 599 (`led_frame = build_frame_from_config(config.display)`), add the explicit privilege-boundary call BEFORE `_setup_preview` (line 603):

```python
        led_frame = build_frame_from_config(config.display)
        # Privilege-drop boundary (constraint #13): the rgbmatrix backend
        # constructs RGBMatrix here, dropping root -> daemon. All pre-drop work
        # (plugin reconcile, prepare_dir, validation) has already run above;
        # everything below needs a live backend.
        led_frame.setup()
```

- [ ] **Step 7: Run the full suite**

Run: `make test`
Expected: PASS. If any test constructed `LedFrame(led_*=...)` directly, update it to `LedFrame(backend=HeadlessBackend(w, h))` + `f.setup()`. Search first: `grep -rn "LedFrame(" tests/ src/` and fix each non-`backend=` call site.

- [ ] **Step 8: Lint, format, commit**

```bash
make format && make lint
git add src/led_ticker/frame.py src/led_ticker/backends/rgbmatrix.py src/led_ticker/app/factories.py src/led_ticker/app/run.py tests/
git commit -m "refactor(frame): LedFrame holds a Backend; explicit setup() lifecycle"
```

---

### Task 5: Repoint external `.matrix` sites + no-reach-through tripwire

**Files:**
- Modify: `src/led_ticker/app/run.py:98,142,165,448`
- Modify: `src/led_ticker/transitions/__init__.py:263,308`
- Test: `tests/test_backends/test_no_matrix_reachthrough.py`

**Interfaces:**
- Consumes: `LedFrame.create_canvas()` and `LedFrame.brightness` (Task 4).

- [ ] **Step 1: Write the failing tripwire test**

Create `tests/test_backends/test_no_matrix_reachthrough.py`:

```python
import pathlib
import re

SRC = pathlib.Path(__file__).resolve().parents[2] / "src" / "led_ticker"

# Files allowed to mention `.matrix` (none, after the refactor). frame.py no
# longer references a matrix attribute; the backend owns it.
ALLOWED: set[str] = set()


def test_no_matrix_reachthrough_outside_backends():
    offenders = []
    for path in SRC.rglob("*.py"):
        if "backends" in path.parts:
            continue  # backends own the matrix internally
        rel = str(path.relative_to(SRC))
        if rel in ALLOWED:
            continue
        text = path.read_text()
        for i, line in enumerate(text.splitlines(), 1):
            # Match `.matrix.` or `.matrix =` (attribute reach-through),
            # not the word in comments/strings like "RGBMatrix".
            if re.search(r"\b\w+\.matrix\b", line) and "self.matrix" not in line:
                offenders.append(f"{rel}:{i}: {line.strip()}")
    assert not offenders, "reach-through to `.matrix` found:\n" + "\n".join(offenders)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_backends/test_no_matrix_reachthrough.py -v`
Expected: FAIL — offenders at `run.py:98,142,165,448` and `transitions/__init__.py:263,308`.

- [ ] **Step 3: Repoint the brightness writes in `run.py`**

Replace `led_frame.matrix.brightness = level` (line 98), `led_frame.matrix.brightness = base` (line 142), and `led_frame.matrix.brightness = config.display.brightness` (line 165) with `led_frame.brightness = <same value>`. E.g. line 98 becomes:

```python
            led_frame.brightness = level
```

- [ ] **Step 4: Repoint the canvas creation in `run.py:448`**

Replace:

```python
    hw = led_frame.matrix.CreateFrameCanvas()
```

with:

```python
    hw = led_frame.create_canvas()
```

(`_setup_preview` runs after `led_frame.setup()`, so the backend is live — confirmed by Task 4 Step 6 ordering.)

- [ ] **Step 5: Repoint the cross-scale canvas creation in `transitions/__init__.py:263,308`**

Both sites call `frame.matrix.CreateFrameCanvas()`. Replace each with `frame.create_canvas()`:

```python
            incoming_canvas = _maybe_wrap(
                frame.create_canvas(),
                incoming_scale,
                incoming_content_height,
            )
```

(`frame` here is the `LedFrame`; it is set up by the time any transition runs.)

- [ ] **Step 6: Run the tripwire + full suite**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_backends/test_no_matrix_reachthrough.py -v && make test`
Expected: PASS.

- [ ] **Step 7: Lint, format, commit**

```bash
make format && make lint
git add src/led_ticker/app/run.py src/led_ticker/transitions/__init__.py tests/test_backends/test_no_matrix_reachthrough.py
git commit -m "refactor: route canvas/brightness through LedFrame; no .matrix reach-through"
```

---

### Task 6: Config `[display] backend` + selection + validation

**Files:**
- Modify: `src/led_ticker/config.py:28` (`DisplayConfig`) + loader
- Modify: `src/led_ticker/validate.py` (reject unknown backend)
- Test: `tests/test_backends/test_backend_selection.py`

**Interfaces:**
- Consumes: `get_backend_class`, `known_backends` (Task 1).
- Produces: `DisplayConfig.backend: str = "rgbmatrix"`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_backends/test_backend_selection.py`:

```python
from led_ticker.backends.headless import HeadlessBackend
from led_ticker.backends.rgbmatrix import RgbMatrixBackend
from led_ticker.config import DisplayConfig
from led_ticker.app.factories import build_frame_from_config


def test_default_backend_is_rgbmatrix():
    assert DisplayConfig().backend == "rgbmatrix"


def test_build_selects_headless():
    d = DisplayConfig(backend="headless", cols=32, chain_length=5, rows=16)
    frame = build_frame_from_config(d)
    assert isinstance(frame.backend, HeadlessBackend)


def test_build_selects_rgbmatrix_by_default():
    frame = build_frame_from_config(DisplayConfig())
    assert isinstance(frame.backend, RgbMatrixBackend)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_backends/test_backend_selection.py -v`
Expected: FAIL — `DisplayConfig` has no `backend` field.

- [ ] **Step 3: Add the field + loader wiring**

In `src/led_ticker/config.py`, add to `DisplayConfig` (after `hardware_mapping`, line 38):

```python
    backend: str = "rgbmatrix"  # rendering backend: "rgbmatrix" (hardware) or "headless"
```

Find where `DisplayConfig` is populated from the parsed `[display]` table (search `config.py` for `DisplayConfig(` and the `_maybe("default_scale", ...)`-style block near line 311/403). Add a string passthrough for `backend` alongside the other `[display]` fields, e.g.:

```python
        "backend": _maybe("backend", str, "rgbmatrix"),
```

(Match the exact `_maybe`/coercion helper signature used by neighboring string fields like `hardware_mapping`.)

- [ ] **Step 4: Reject unknown backend in validation**

In `src/led_ticker/validate.py`, find the `[display]` validation section and add a check. The validator collects messages; mirror the existing style:

```python
    from led_ticker.backends import known_backends  # noqa: PLC0415

    backend = getattr(display, "backend", "rgbmatrix")
    if backend not in known_backends():
        errors.append(
            f"[display] backend = {backend!r} is unknown; "
            f"valid backends: {known_backends()}"
        )
```

(Use the actual local variable name the surrounding validator uses for the error/warning list — read the function first.)

- [ ] **Step 5: Add a validation test**

Append to `tests/test_backends/test_backend_selection.py`:

```python
def test_validate_rejects_unknown_backend(tmp_path):
    from led_ticker.validate import validate_config_file

    cfg = tmp_path / "config.toml"
    cfg.write_text(
        '[display]\nbackend = "nope"\n\n'
        '[[sections]]\n[[sections.widgets]]\ntype = "message"\ntext = "hi"\n'
    )
    report = validate_config_file(str(cfg))
    assert any("nope" in m for m in report.errors)
```

(Adjust `validate_config_file` / `report.errors` to the real validate entry point + report shape — read `validate.py` for the exact names; the assertion is "an error mentions the bad backend name.")

- [ ] **Step 6: Run tests + full suite**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_backends/test_backend_selection.py -v && make test`
Expected: PASS.

- [ ] **Step 7: Lint, format, commit**

```bash
make format && make lint
git add src/led_ticker/config.py src/led_ticker/validate.py tests/test_backends/test_backend_selection.py
git commit -m "feat(config): [display] backend selection + validation"
```

---

### Task 7: Failure-mode logging

**Files:**
- Modify: `src/led_ticker/app/factories.py` (`build_frame_from_config`) — log loudly on headless
- Modify: `src/led_ticker/backends/rgbmatrix.py` (`setup()`) — actionable error off-hardware
- Test: `tests/test_backends/test_failure_modes.py`

**Interfaces:** none new.

- [ ] **Step 1: Write the failing test**

Create `tests/test_backends/test_failure_modes.py`:

```python
import logging

from led_ticker.config import DisplayConfig
from led_ticker.app.factories import build_frame_from_config


def test_headless_selection_logs_loudly(caplog):
    with caplog.at_level(logging.WARNING):
        build_frame_from_config(DisplayConfig(backend="headless"))
    assert any("headless" in r.message.lower() for r in caplog.records)
    assert any("no hardware" in r.message.lower() for r in caplog.records)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_backends/test_failure_modes.py -v`
Expected: FAIL — no warning emitted.

- [ ] **Step 3: Add the headless warning**

In `build_frame_from_config` (factories.py), in the `else` (non-rgbmatrix) branch added in Task 4 Step 5, before constructing the backend:

```python
        logging.warning(
            "headless backend selected — no hardware output (dev/CI/preview "
            "mode). Set [display] backend = \"rgbmatrix\" to drive a panel."
        )
```

- [ ] **Step 4: Make the off-hardware rgbmatrix error actionable**

In `RgbMatrixBackend.setup()`, the `require_matrix()` path raises today's `_compat` message. Wrap it to point at headless:

```python
    def setup(self) -> None:
        options = build_options(self)
        if RGBMatrix is None:
            raise RuntimeError(
                "rgbmatrix hardware library not installed. Run on a Raspberry "
                "Pi, or set [display] backend = \"headless\" for dev/CI/preview."
            )
        self._matrix = RGBMatrix(options=options)
        ...
```

(Keep the `framerate_fraction` derivation after matrix construction, unchanged.)

- [ ] **Step 5: Run tests + full suite**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_backends/test_failure_modes.py -v && make test`
Expected: PASS.

- [ ] **Step 6: Lint, format, commit**

```bash
make format && make lint
git add src/led_ticker/app/factories.py src/led_ticker/backends/rgbmatrix.py tests/test_backends/test_failure_modes.py
git commit -m "feat(backends): loud headless warning + actionable off-hardware error"
```

---

### Task 8: Conformance kit (importable)

**Files:**
- Create: `src/led_ticker/backends/conformance.py`
- Modify: `src/led_ticker/_types.py` (widen `CanvasLike`)
- Test: `tests/test_backends/test_conformance.py`

**Interfaces:**
- Consumes: `Backend`, `BackendNotReadyError` (Task 1); `ScaledCanvas` (`scaled_canvas.py`); `PreviewTee` (`preview.py`).
- Produces:
  - `run_backend_conformance(backend_factory: Callable[[], Backend]) -> None` — runs all checks; raises `AssertionError` on any failure. `backend_factory` returns a *fresh, un-setup* backend each call.

- [ ] **Step 1: Widen `CanvasLike`**

In `src/led_ticker/_types.py`, add `SubFill` and `SetImage` to the `CanvasLike` Protocol:

```python
    def SubFill(self, x: int, y: int, width: int, height: int, r: int, g: int, b: int) -> None: ...
    def SetImage(self, image: object, offset_x: int = 0, offset_y: int = 0) -> None: ...
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_backends/test_conformance.py`:

```python
from led_ticker.backends.conformance import run_backend_conformance
from led_ticker.backends.headless import HeadlessBackend


def test_headless_passes_conformance():
    run_backend_conformance(lambda: HeadlessBackend(64, 32))


def test_rgbmatrix_stub_passes_conformance():
    # Off-hardware the stub backs RGBMatrix, so the rgbmatrix backend is
    # constructible and must also pass.
    from led_ticker.backends.rgbmatrix import RgbMatrixBackend

    run_backend_conformance(
        lambda: RgbMatrixBackend(led_rows=32, led_cols=64, led_chain_length=1)
    )
```

- [ ] **Step 3: Run test to verify it fails**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_backends/test_conformance.py -v`
Expected: FAIL — `ModuleNotFoundError: ...conformance`.

- [ ] **Step 4: Write the conformance kit**

Create `src/led_ticker/backends/conformance.py`:

```python
"""Importable backend conformance suite.

Encodes the load-bearing hardware-rendering constraints (CLAUDE.md) as checks
every backend must pass. External backend authors run:

    from led_ticker.backends.conformance import run_backend_conformance
    run_backend_conformance(lambda: MyBackend(...))

`backend_factory` must return a FRESH, un-setup backend each call.
"""

from collections.abc import Callable

from led_ticker.backends import Backend, BackendNotReadyError
from led_ticker.preview import PreviewTee
from led_ticker.scaled_canvas import ScaledCanvas


def _check_protocol(factory: Callable[[], Backend]) -> None:
    assert isinstance(factory(), Backend), "does not satisfy the Backend protocol"


def _check_swap_returns_new_buffer(factory: Callable[[], Backend]) -> None:
    b = factory()
    b.setup()
    front = b.create_canvas()
    back = b.swap(front, getattr(b, "framerate_fraction", 1))
    assert back is not front, "swap() must return a DIFFERENT canvas (constraints #1/#8)"


def _check_canvas_contract(factory: Callable[[], Backend]) -> None:
    b = factory()
    b.setup()
    c = b.create_canvas()
    for meth in ("SetPixel", "Clear", "Fill", "SubFill", "SetImage"):
        assert hasattr(c, meth), f"canvas missing {meth} (Canvas contract)"
    c.SetPixel(0, 0, 1, 2, 3)  # must not raise
    c.Clear()


def _check_no_getpixel_required(factory: Callable[[], Backend]) -> None:
    # Constraint #3: the engine never reads pixels back. A backend may offer
    # test helpers, but production code must not need GetPixel. We assert the
    # engine-facing contract does not include it.
    b = factory()
    b.setup()
    c = b.create_canvas()
    assert not hasattr(c, "GetPixel"), "canvas must not expose GetPixel (constraint #3)"


def _check_wrappability(factory: Callable[[], Backend]) -> None:
    # The raw canvas is wrapped by ScaledCanvas (bigsign) and PreviewTee in
    # production. A backend that passes the flat contract must also survive the
    # wrappers.
    b = factory()
    b.setup()
    raw = b.create_canvas()
    scaled = ScaledCanvas(raw, scale=4, content_height=16)
    scaled.SetPixel(0, 0, 4, 5, 6)  # must paint through to the real canvas
    tee = PreviewTee(hw=b.create_canvas(), width=raw.width, height=raw.height,
                     frame_path=None, mirror=False)
    tee.SetPixel(0, 0, 7, 8, 9)  # must not raise


def _check_not_ready_guard(factory: Callable[[], Backend]) -> None:
    # Backends that build state in setup() should not silently work before it.
    # LedFrame enforces this; backends that raise BackendNotReadyError or
    # AttributeError before setup() are both acceptable. We only assert that a
    # backend which DID set up works — the LedFrame-level guard is tested
    # separately (test_led_frame_backend.py).
    b = factory()
    b.setup()
    assert b.create_canvas() is not None


_CHECKS = [
    _check_protocol,
    _check_swap_returns_new_buffer,
    _check_canvas_contract,
    _check_no_getpixel_required,
    _check_wrappability,
    _check_not_ready_guard,
]


def run_backend_conformance(backend_factory: Callable[[], Backend]) -> None:
    """Run every conformance check against backends from `backend_factory`.
    Raises AssertionError naming the first failing constraint."""
    for check in _CHECKS:
        check(backend_factory)
```

Note: verify `ScaledCanvas` and `PreviewTee` constructor signatures against `scaled_canvas.py` / `preview.py` and adjust the kwargs in `_check_wrappability` to match (e.g. `PreviewTee(hw=..., width=..., height=..., frame_path=...)` per `run.py:449-454`; `frame_path=None` + `mirror=False` must be accepted — if `PreviewTee` requires a real path, pass `tmp`-style path via a module constant or relax to constructing with a dummy path the tee tolerates when `mirror=False`).

- [ ] **Step 5: Run tests + full suite**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_backends/test_conformance.py -v && make test`
Expected: PASS. If `_check_wrappability` fails on `PreviewTee` construction, fix the kwargs to the real signature (do NOT weaken the assertion that draws land).

- [ ] **Step 6: Lint, format, commit**

```bash
make format && make lint
git add src/led_ticker/backends/conformance.py src/led_ticker/_types.py tests/test_backends/test_conformance.py
git commit -m "feat(backends): importable conformance kit + widen CanvasLike"
```

---

### Task 9: Dedup the rgbmatrix stub against `HeadlessCanvas`; retire the Makefile `PYTHONPATH` hack

**REVISED during execution (2026-06-24).** The original plan ("delete the stub, migrate ~30 files to HeadlessBackend, retire PYTHONPATH") was wrong: `RgbMatrixBackend.build_options()` constructs `RGBMatrixOptions()`, which is `None` off-hardware once the stub is gone — so deleting the stub would break the Task 3 byte-identical guard tests and the rgbmatrix conformance test off-hardware. The stub is genuinely needed to test the rgbmatrix backend without a Pi.

The spec's actual goals are met differently:
- **External/plugin consumers get a package import** — already achieved by shipping `HeadlessBackend` (Task 2). Plugins import `led_ticker.backends.headless`, not a sibling `tests/stubs` path.
- **Kill the `PYTHONPATH=tests/stubs` Makefile hack** — move the stub onto pytest's pythonpath via `pyproject.toml` so `make test` needs no env var.
- **Dedup** — `HeadlessCanvas` is currently a copy of the stub's `_StubCanvas`; make the stub REUSE `HeadlessCanvas` so there's one canvas implementation.

The ~30 test files are NOT migrated — they legitimately need a fake rgbmatrix (`RGBMatrixOptions`/`graphics`/canvas) and keep importing `from rgbmatrix import ...`, now resolved via the pytest pythonpath.

**Files:**
- Modify: `tests/stubs/rgbmatrix/__init__.py` — reuse `HeadlessCanvas`; keep `RGBMatrix`/`RGBMatrixOptions` shims.
- Modify: `pyproject.toml` — add `pythonpath = ["tests/stubs"]` to `[tool.pytest.ini_options]`.
- Modify: `Makefile:17` — drop `PYTHONPATH=tests/stubs`.

**Interfaces:**
- Consumes: `HeadlessCanvas` (Task 2).

- [ ] **Step 1: Dedup the stub canvas**

In `tests/stubs/rgbmatrix/__init__.py`, replace the duplicated `_StubCanvas` class body with a reuse of `HeadlessCanvas`. At minimum alias it so existing `from rgbmatrix import _StubCanvas` / internal uses keep working:

```python
from led_ticker.backends.headless import HeadlessCanvas as _StubCanvas  # noqa: F401
```

Then ensure `RGBMatrix.CreateFrameCanvas()` returns a `_StubCanvas(width=..., height=...)` (now `HeadlessCanvas`). `HeadlessCanvas` is API-identical to the old `_StubCanvas` (it was ported from it in Task 2: `SetPixel`/`Clear`/`Fill`/`SubFill`/`SetImage` + `get_pixel`/`count_nonzero`), so this is behavior-preserving. Keep the `RGBMatrix` + `RGBMatrixOptions` stub classes (including U-mapper reshape and the same-object `SwapOnVSync` default) — they are the rgbmatrix-shaped shim that lets the rgbmatrix backend be tested off-hardware. Keep `tests/stubs/rgbmatrix/graphics.py` as-is.

- [ ] **Step 2: Move the stub onto pytest's pythonpath**

In `pyproject.toml` `[tool.pytest.ini_options]` (currently has `testpaths = [...]`, NO `pythonpath`), add:

```toml
pythonpath = ["tests/stubs"]
```

Leave the pyright `extraPaths = ["tests/stubs"]` (line ~84) unchanged — it's for the type checker and is still correct.

- [ ] **Step 3: Drop the Makefile `PYTHONPATH` hack**

In `Makefile` (the `test` target, ~line 17), change:
```make
	PYTHONPATH=tests/stubs uv run pytest -s --cov=src/ --cov-report=term-missing
```
to:
```make
	uv run pytest -s --cov=src/ --cov-report=term-missing
```

- [ ] **Step 4: Verify the suite passes WITHOUT the env hack**

Run: `make test`
Expected: PASS — pytest now discovers `tests/stubs` via `pyproject.toml` `pythonpath`, so `from rgbmatrix import ...` resolves and the rgbmatrix-backend tests (build_options, conformance) still run off-hardware. Also run a focused check that the dedup didn't change behavior: `uv run pytest tests/test_backends/ tests/test_scaled_canvas.py tests/test_pixel_emoji.py -v`.

- [ ] **Step 5: Lint, format, commit**

```bash
make format && make lint
git add -A
git commit -m "test: dedup rgbmatrix stub canvas against HeadlessCanvas; move stub to pytest pythonpath (retire Makefile PYTHONPATH hack)"
```

---

### Task 10: DrawText rasterizer unification (independent)

Routes scale=1 text through the pure-Python rasterizer, collapsing the three-branch dispatch and removing the PreviewTee `DrawText` special-case. The C path stays behind a flag until a one-time hardware C-vs-rasterizer validation signs off. **This task is independent — it can run first or last.**

**Files:**
- Modify: `src/led_ticker/text_render.py:21-36`
- Modify: `src/led_ticker/preview.py` (remove `mirror_bdf_text` once the branch is gone — gated)
- Test: `tests/test_text_render.py` (add scale=1 rasterizer path tests)

**Interfaces:** none new.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_text_render.py` (use `HeadlessCanvas` — no `rgbmatrix`):

```python
def test_scale1_text_renders_via_rasterizer():
    from led_ticker.backends.headless import HeadlessCanvas
    from led_ticker.fonts import load_font
    from led_ticker import text_render

    text_render.USE_RASTERIZER_AT_SCALE1 = True  # flag default during migration
    canvas = HeadlessCanvas(width=64, height=16)
    font = load_font("5x7")  # use a real bundled BDF name from fonts/
    from led_ticker._compat import require_graphics

    color = require_graphics().Color(255, 255, 255)
    advance = text_render.draw_text(canvas, font, 0, 12, color, "Hi")
    assert advance > 0
    assert canvas.count_nonzero() > 0  # pixels actually painted at scale=1
```

(Replace `load_font("5x7")` and the font API with the real loader call used elsewhere in `test_text_render.py` — read the file for the exact font-loading helper.)

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_text_render.py::test_scale1_text_renders_via_rasterizer -v`
Expected: FAIL — `AttributeError: module 'led_ticker.text_render' has no attribute 'USE_RASTERIZER_AT_SCALE1'`, or no pixels painted (C `DrawText` path on a HeadlessCanvas is the stub rasterizer already — adjust: the assertion that distinguishes is that the *PreviewTee branch is gone*; see Step 3).

- [ ] **Step 3: Add the flag + rasterizer path**

In `src/led_ticker/text_render.py`, add a module flag and route scale=1 through the BDF rasterizer when enabled. Replace the dispatch (lines 21-36):

```python
USE_RASTERIZER_AT_SCALE1 = True  # flip to False to restore the C DrawText path
                                 # (kept until the hardware C-vs-rasterizer
                                 # validation signs off; then this flag + the
                                 # C branch are removed).


def draw_text(canvas, font, x, y, color, text):
    """Draw `text` at (x, y) baseline. Returns total advance width."""
    if isinstance(font, HiresFont):
        return _draw_hires_text(canvas, font, x, y, color, text)
    if is_scaled(canvas):
        bdf = get_bdf_for(font)
        return canvas.draw_bdf_text(bdf, x, y, color, text)
    if USE_RASTERIZER_AT_SCALE1:
        # One text path for every backend: rasterize via the shipped BDF
        # renderer (SetPixel-based). Paints through a PreviewTee directly (the
        # tee mirrors SetPixel), so the old C+mirror_bdf_text branch is gone.
        bdf = get_bdf_for(font)
        return _draw_bdf_text_scale1(canvas, bdf, x, y, color, text)
    # Legacy C path (retained until hardware sign-off):
    if isinstance(canvas, PreviewTee):
        advance = _graphics.DrawText(canvas._hw, font, x, y, color, text)
        if canvas.mirror:
            canvas.mirror_bdf_text(get_bdf_for(font), x, y, color, text)
        return advance
    return _graphics.DrawText(canvas, font, x, y, color, text)


def _draw_bdf_text_scale1(canvas, bdf, x, y, color, text):
    """Rasterize BDF glyphs at scale=1 via SetPixel. Same glyph math as
    ScaledCanvas.draw_bdf_text and _rgbmatrix_stub.DrawText: x left edge, y
    baseline, glyphs above baseline. Returns total advance width."""
    r, g, b = color.red, color.green, color.blue
    cx = int(x)
    base_y = int(y)
    for ch in text:
        glyph = bdf.glyphs.get(ch)
        if glyph is None:
            cx += bdf.bbx_width
            continue
        top_y = base_y - glyph.bbx_height - glyph.bbx_yoff
        base_x = cx + glyph.bbx_xoff
        for col, row in glyph.lit_pixels:
            canvas.SetPixel(base_x + col, top_y + row, r, g, b)
        cx += glyph.advance_width
    return sum(bdf.glyphs[c].advance_width if c in bdf.glyphs else bdf.bbx_width
               for c in text)
```

(Confirm `bdf.glyphs` is keyed by character — `_rgbmatrix_stub.DrawText` uses `glyphs.get(ch)` where `ch` is the character; match that. Verify against `fonts/bdf_parser.py`.)

- [ ] **Step 4: Run tests to verify pass**

Run: `uv run pytest tests/test_text_render.py -v`
Expected: PASS. Existing scale>1 and hires tests untouched.

- [ ] **Step 5: Full suite**

Run: `make test`
Expected: PASS. The PreviewTee text path now goes through the rasterizer; if any preview test asserted the old C+mirror behavior, update it to assert painted pixels on the shadow instead.

- [ ] **Step 6: Commit (rasterizer path, flag ON, C path retained)**

```bash
make format && make lint
git add src/led_ticker/text_render.py tests/test_text_render.py
git commit -m "feat(text): scale=1 text via BDF rasterizer (flag-gated; C path retained)"
```

- [ ] **Step 7: Document the hardware-validation follow-up**

The C-path removal + `mirror_bdf_text` deletion are gated on a **one-time hardware validation**: on the real smallsign (scale=1), render representative text both ways (C `DrawText` vs the rasterizer) and pixel-diff on the bundled BDF fonts. This is independent of the backend work and not unit-testable. Add a tracking note to the epic issue (#236) referencing this task; do NOT remove the C branch or `mirror_bdf_text` until the diff confirms byte-identical output. (Out of scope for this plan to execute the hardware step.)

---

## Self-Review

**Spec coverage:**
- Backend protocol → Task 1 ✅
- LedFrame keeps mechanism; create_canvas/brightness delegators; pre-setup guards → Task 4 ✅
- RgbMatrixBackend (verbatim options + hasattr guards + framerate) → Task 3 ✅
- HeadlessBackend promoted → Task 2 ✅
- Canvas contract + CanvasLike widening + wrappability → Tasks 8 ✅
- Privilege-drop lifecycle (un-setup build, explicit setup(), post-setup ordering) → Task 4 ✅
- 3 external `.matrix` sites repointed + tripwire → Task 5 ✅
- Config selection + validation → Task 6 ✅
- Failure-mode UX → Task 7 ✅
- Conformance kit (importable) → Task 8 ✅
- Test migration + PYTHONPATH retire + stub collapse + `_compat` decision → Task 9 ✅
- DrawText unification (flag-gated, hardware-validation follow-up) → Task 10 ✅
- Web-backend stress test → design-only (no task; validated in spec) ✅
- Plugins-monorepo migration → out of scope (separate repo) ✅

**Placeholder scan:** No "TBD"/"implement later"/vague-handling steps. The places that say "read the file for the exact name" (validate.py report shape, font loader API, ScaledCanvas/PreviewTee kwargs, bdf glyph keying) are real codebase-verification steps with the expected shape given — not deferred design.

**Type consistency:** `Backend` members, `BackendNotReadyError`, `get_backend_class`/`known_backends`, `HeadlessBackend(width, height, *, pixel_mapper_config)`, `HeadlessCanvas`, `RgbMatrixBackend(led_*)`, `build_options`, `LedFrame(backend=...)`/`setup()`/`create_canvas()`/`brightness`, `USE_RASTERIZER_AT_SCALE1` — all defined where first used and referenced consistently downstream.

**Known verification points for the implementer (flagged inline, not placeholders):**
- `validate.py` error-list variable name + entry-point/report shape (Task 6).
- `ScaledCanvas` + `PreviewTee` exact constructor kwargs (Task 8) — `PreviewTee` must accept `mirror=False` without a writable `frame_path`.
- Real BDF font-loading helper + `bdf.glyphs` keying (Task 10).
- Full `LedFrame(` call-site sweep in `tests/` + `src/` (Task 4 Step 7).
