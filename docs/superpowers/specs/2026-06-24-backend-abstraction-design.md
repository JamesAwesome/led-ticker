# Backend abstraction — decouple the engine from rpi-rgb-led-matrix

**Date:** 2026-06-24
**Issue:** [#236 (epic)](https://github.com/JamesAwesome/led-ticker/issues/236), first deliverable [#233](https://github.com/JamesAwesome/led-ticker/issues/233)
**Status:** Design approved; ready for implementation planning

## Scope

This spec covers the **first deliverable** of the backend-abstraction epic:

- The `Backend` protocol (formalizing the matrix lifecycle the engine assumes implicitly today).
- Two built-in backends: `rgbmatrix` (the existing production path, behind the new protocol) and `headless` (the full test stub, promoted to a shipped, runtime-selectable backend).
- An importable **conformance kit** that any backend must pass.
- Resolution of the `graphics.DrawText` scale=1 leak.
- Config-based backend selection (`[display] backend = "..."`).

The protocol is **stress-tested against a hypothetical web/streamed backend** so the contract does not bake in rgbmatrix-specific shape — but no web backend is built here. The plugin entry-point surface for third-party backends (`api.backend("...")`) is **designed-for but not built**.

### Out of scope

- Web/streamed/other backends (enabled by this work, not delivered by it).
- The plugin entry-point registration surface for backends.
- The plugins monorepo migration (separate repo; noted as a downstream follow-up).
- Any change to production rgbmatrix rendering behavior — it must remain byte-identical.

## Background: the existing seams

The rgbmatrix coupling funnels through two narrow seams:

- **`_compat.require_graphics()` / `require_matrix()`** — splits the always-available graphics primitives (`Color`/`Font`/`DrawText`, real lib or bundled `_rgbmatrix_stub.py`) from the hardware-only `RGBMatrix`/`RGBMatrixOptions`.
- **`frame.py`** — the place that builds `RGBMatrix`/`RGBMatrixOptions`, calls `CreateFrameCanvas`, and `SwapOnVSync`.

Three implementations of the matrix surface already exist: the real C library; the shipped graphics-only `_rgbmatrix_stub.py`; and the **full** `tests/stubs/rgbmatrix/` (`RGBMatrix` + `_StubCanvas` + double-buffered `SwapOnVSync` + `SetPixel`/`SubFill`/`SetImage`/`Fill`/`Clear`). The full stub is effectively a complete software backend already.

The 13 hardware-rendering constraints in `CLAUDE.md` **are** the backend contract. They become the conformance suite.

### Validation findings (the seam is wider than "just frame.py")

A sweep of `.matrix` accesses across `src/` found the contract reaches beyond `frame.py`:

1. **`brightness` is runtime-mutable.** `app/run.py` sets `led_frame.matrix.brightness = level` in three places (the brightness scheduler dims/restores the panel live). It is the **only** mutable matrix attribute anywhere — a sweep for any other `matrix.<attr>` found only docstrings.
2. **`create_canvas` is called from three external sites**, not only `frame.py`:
   - `app/run.py:448` — preview-tee setup grabs a raw `hw = led_frame.matrix.CreateFrameCanvas()` (deliberately raw: no `Clear`, no tee).
   - `transitions/__init__.py:263,308` — cross-scale transitions allocate a fresh back-buffer mid-transition via `frame.matrix.CreateFrameCanvas()`.
3. **`width`/`height` are never read off the matrix** — the only reads are on the *canvas* (`hw.width`/`hw.height`). They are construction params the backend needs internally, not load-bearing protocol surface.
4. **The Canvas method surface is wider than `_types.CanvasLike` documents.** Used across the codebase: `SetPixel`, `Clear`, `Fill` (declared) plus `SubFill` (11 sites) and `SetImage` (gif/still/preview) — **used but undeclared** — plus `DrawText` (the scale=1 leak).

## Architecture

### The `Backend` protocol

```python
@runtime_checkable
class Backend(Protocol):
    brightness: int  # settable; live brightness scheduling. The only mutable attribute.

    def setup(self) -> None:
        """Build the underlying matrix and perform all privileged work.
        This is the declared privilege-drop boundary (see Lifecycle).
        Idempotent-safe; called exactly once by the app after all pre-drop work."""

    def create_canvas(self) -> Canvas:
        """Return a fresh back-buffer canvas. (Was matrix.CreateFrameCanvas().)"""

    def swap(self, canvas: Canvas, framerate_fraction: int = 1) -> Canvas:
        """Present `canvas` and return the NEW back-buffer to draw into next.
        Returning a *different* object is mandatory (constraint #1/#8). The
        framerate_fraction arg is rgbmatrix-specific; other backends accept and
        ignore it."""
```

`width`/`height` may be exposed informationally but are not required by the protocol; in practice size is read off the canvas.

### `LedFrame` keeps the shared mechanism

`LedFrame` holds a `backend` instead of a `matrix`, and keeps everything backend-agnostic — overlay hooks, `status_board.record_swap()`, the preview tee, and `framerate_fraction` handling. These are product features that must behave identically across all backends, so they live in one place.

`LedFrame` gains two delegating members so nothing outside it touches the backend:

- `LedFrame.create_canvas() -> Canvas` — raw canvas (delegates to `backend.create_canvas()`); used by the three external sites above (preview-tee setup, cross-scale transitions). Distinct from the existing `get_clean_canvas()`, which adds `Clear()` + tee handling.
- `LedFrame.brightness` property — get/set delegating to `backend.brightness`; the schedule ticker writes `led_frame.brightness = level`.

After the refactor, `frame.matrix` / `led_frame.matrix` reach-throughs are removed from `run.py` and `transitions/__init__.py`. The backend is fully encapsulated behind `LedFrame`.

### Built-in backends

- **`RgbMatrixBackend`** — owns the `RGBMatrixOptions` building currently in `LedFrame.__attrs_post_init__` (all `led_*` knobs: `gpio_slowdown`, `pwm_bits`, `rp1_pio`, `limit_refresh_rate_hz`, etc.) and constructs `RGBMatrix` in `setup()`. Production behavior byte-identical.
- **`HeadlessBackend`** — promoted from `tests/stubs/rgbmatrix/`. Ships in the package, runtime-selectable. Provides `create_canvas()` returning a software canvas implementing the full Canvas contract, and a double-buffered `swap()` that returns a *different* canvas object (preserving the capture-the-return semantics the stub already encodes).

### The Canvas contract

Every backend's canvas must satisfy `{SetPixel, Clear, Fill, SubFill, SetImage}` (plus the `DrawText` resolution below). `_types.CanvasLike` is widened from its current three methods (`SetPixel`/`Clear`/`Fill`) to include `SubFill` and `SetImage`, so the structural type matches reality and `isinstance` checks are accurate. The conformance kit is the executable source of truth for this contract.

## Lifecycle and the privilege-drop boundary (constraint #13)

Today the privilege drop (root → `daemon`) happens implicitly **inside** `build_frame_from_config` → `LedFrame()` → `RGBMatrix()` construction. Ordering is enforced only by textual position: plugin reconcile, `status_board.prepare_dir()`, and startup validation all happen to run before `build_frame_from_config` in `app/run.py`.

This spec makes the boundary an explicit, single-point lifecycle:

1. App performs all pre-drop privileged work (plugin reconcile, `status_board.prepare_dir()`, startup validation). **Unchanged.**
2. App constructs `LedFrame(backend=RgbMatrixBackend(options))`. **Cheap — no matrix built, no privilege drop.** Matrix construction is moved out of `LedFrame.__init__`/`__attrs_post_init__`.
3. App calls `led_frame.setup()`, which delegates to `backend.setup()`, which constructs `RGBMatrix(options)`. **The privilege drop happens here, at one declared point.**
4. From here the process runs as `daemon`; all canvas/swap operations work.

`build_frame_from_config` either calls `setup()` internally at its end or returns an un-setup frame for the app to set up explicitly; the implementation plan picks one, but `setup()` is a named lifecycle method either way so a conformance test can assert "`setup()` is the privilege boundary; no privileged operation precedes it." The existing tripwire `test_setup_runs_before_frame_build` is reframed to "before `backend.setup()`."

`HeadlessBackend.setup()` builds its software matrix and never drops privileges.

## The `graphics.DrawText` leak

`text_render.py` uses the C `graphics.DrawText` at scale=1 and the pure-Python BDF rasterizer (SetPixel-based) at scale>1. A non-rgbmatrix backend at scale=1 has no C `DrawText`.

**Resolution:** standardize on the pure-Python rasterizer at *all* scales. `DrawText` leaves the Canvas contract entirely — one text path for every backend.

**Risk and gate:** the smallsign runs at scale=1 in production, so this changes the real smallsign text path, and the epic requires production output to stay byte-identical. The rasterizer cannot be pixel-diffed against real C `DrawText` off-hardware (the C `DrawText` type-checks for a real `Canvas`, which requires `RGBMatrix`, which requires a Pi). Therefore:

- C `graphics.DrawText` stays reachable behind a flag/branch for the scale=1 path.
- A **hardware pixel-diff on the real smallsign** renders representative text both ways (rasterizer vs C `DrawText`) and confirms byte-identical output.
- Only after that sign-off does the rasterizer become the default scale=1 path and the C `DrawText` branch get removed.

This keeps the clean single-path end-state while making the byte-identical guarantee evidence-based rather than assumed. The hardware pixel-diff is an explicit task in the implementation plan, blocking the removal of the C path (not the rest of the work).

## Backend selection

- New config field: `[display] backend = "rgbmatrix" | "headless"`, default `"rgbmatrix"`.
- An internal name→class registry in `led_ticker.backends` maps the string to a backend class; `build_frame_from_config` selects via this registry.
- The registry is structured so a second population source (plugin entry points, `api.backend("web")`) is a purely additive change. That hook is **not built** here — the epic marks it TBD and there is no consumer yet.

Config validation (`led-ticker validate`) rejects an unknown backend name with the list of known backends.

## Packaging

```
src/led_ticker/backends/
  __init__.py     # Backend protocol + name->class registry + select()/build helper
  rgbmatrix.py    # RgbMatrixBackend (owns RGBMatrixOptions building + RGBMatrix construction)
  headless.py     # HeadlessBackend + its software canvas (promoted from tests/stubs/rgbmatrix/)
  conformance.py  # the conformance suite, as importable functions
```

- `headless.py` is **shipped** — it is a runtime-selectable backend, not a test artifact.
- `conformance.py` is **shipped and importable**: `from led_ticker.backends.conformance import run_backend_conformance`. External backend authors (and the plugins monorepo) run it against their backend instead of putting `../led-ticker/tests/stubs` on `PYTHONPATH` or vendoring a copy.
- `tests/stubs/rgbmatrix/` collapses. Core tests stop relying on `PYTHONPATH=tests/stubs` (Makefile + `pyproject.toml` `extraPaths`/`pythonpath`) and run against the shipped `HeadlessBackend`. The `swapping_frame` and `mock_frame` fixtures (`tests/conftest.py`) rebind onto `HeadlessBackend`.
- The graphics-only `_rgbmatrix_stub.py` remains (it backs `require_graphics()` for non-drawing operations on any machine).

### Plugins monorepo (downstream, separate repo)

The plugins monorepo currently reaches the full stub via a vendored copy / sibling `PYTHONPATH` (its README and CLAUDE.md have already drifted on which). Once the conformance kit and `HeadlessBackend` ship, the monorepo migrates to importing them as package symbols. Tracked separately under the plugins-monorepo work (#235); not part of this deliverable.

## Conformance kit

The kit encodes the 13 hardware constraints from `CLAUDE.md` as importable test functions parameterized over a backend instance. The subtle ones the full stub already encodes deliberately:

- **#1 / #8** — `swap()` returns a *different* canvas object than it was given (dropped-capture detection).
- **#2** — `DrawText` type-checking (becomes moot once `DrawText` leaves the contract; the kit asserts the canvas does *not* require it).
- **#3** — no `GetPixel` / no pixel readback expected.
- **#4** — `SetPixel` works on every canvas.
- **Canvas contract** — `SetPixel`, `Clear`, `Fill`, `SubFill`, `SetImage` all present and behave (paint/clear observable via the headless canvas's test-only `get_pixel`/`count_nonzero` helpers).
- **#13** — `setup()` is the declared privilege boundary; the app calls no privileged operation before it.

`run_backend_conformance(backend_factory)` runs the full suite against any backend; core runs it against both `RgbMatrixBackend` (where constructible) and `HeadlessBackend`.

## Web-backend stress test (forward-looking validation)

A hypothetical socket-pushing backend satisfies the contract without contortion:

- `brightness` — a serialized field on the outgoing frame state.
- `setup()` — binds its (possibly privileged) port; never drops OS privileges.
- `create_canvas()` — returns a fresh in-memory buffer.
- `swap()` — serializes the canvas to the socket and returns the next buffer.
- `framerate_fraction` — accepted and ignored.

The contract does not assume `SwapOnVSync` naming, vsync semantics, or the rgbmatrix options shape. It survives.

## Testing strategy

- Conformance suite (above) run against `HeadlessBackend` and `RgbMatrixBackend`.
- `LedFrame` unit tests: overlay hooks, `record_swap`, preview tee, and `framerate_fraction` all exercised against `HeadlessBackend` (no `PYTHONPATH` stub).
- Tripwire: no `.matrix` reach-through outside `LedFrame` (AST or grep-based test, mirroring the existing `app/run.py` container tripwire style).
- Tripwire: `test_setup_runs_before_frame_build` reframed to assert `prepare_dir`/privileged work precedes `backend.setup()`.
- Selection: `[display] backend` round-trips through config load; unknown name rejected by `validate`.
- DrawText: existing text-render tests run against the rasterizer; the hardware pixel-diff is a manual/hardware task gating C-path removal.
- Production parity: the rgbmatrix options-building moves verbatim; a test asserts the `RGBMatrixOptions` produced from a given `DisplayConfig` is unchanged from today.

## Risks

- **Byte-identical scale=1 text** — mitigated by the hardware pixel-diff gate; C path retained until sign-off.
- **Privilege-drop regression** — mitigated by reframed tripwire and the explicit single-point `setup()`; this class of bug is not unit-testable (the stub does not setuid), so the change is small and the ordering is asserted structurally.
- **Hidden `.matrix` coupling** — the validation sweep found all current sites; the no-reach-through tripwire prevents regression.

## Implementation phasing (for the plan)

1. Introduce `backends/` with the `Backend` protocol, `RgbMatrixBackend` (options-building moved verbatim), and `HeadlessBackend` (promoted stub). `LedFrame` holds a backend; add `create_canvas()` + `brightness` delegators.
2. Repoint the three external `.matrix` sites; add the no-reach-through tripwire.
3. Explicit `setup()` lifecycle; reframe the privilege tripwire.
4. Config `[display] backend` + registry + validation.
5. Conformance kit; repoint core tests + fixtures off `PYTHONPATH=tests/stubs`; collapse `tests/stubs/rgbmatrix/`.
6. DrawText: route scale=1 through the rasterizer behind a flag; (hardware) pixel-diff; remove C path on sign-off.
