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

- **`RgbMatrixBackend`** — owns the `RGBMatrixOptions` building currently in `LedFrame.__attrs_post_init__` (all `led_*` knobs: `gpio_slowdown`, `pwm_bits`, `rp1_pio`, `limit_refresh_rate_hz`, etc.) and constructs `RGBMatrix` in `setup()`. The move is verbatim, but note it is **not a pure copy**: it carries version-tolerant `hasattr(options, ...)` guards for `rp1_pio` / `limit_refresh_rate_hz` / `pwm_dither_bits` (`frame.py:66,84,87`) whose effect depends on the *installed rgbmatrix build*, plus the `_framerate_fraction` derivation (now in `setup()`). Production behavior byte-identical.
- **`HeadlessBackend`** — promoted from `tests/stubs/rgbmatrix/`. Ships in the package, runtime-selectable. Provides `create_canvas()` returning a software canvas implementing the full Canvas contract, and a double-buffered `swap()` that returns a *different* canvas object (preserving the capture-the-return semantics the stub already encodes).

### The Canvas contract

Every backend's canvas must satisfy `{SetPixel, Clear, Fill, SubFill, SetImage}` (plus the `DrawText` resolution below). `_types.CanvasLike` is widened from its current three methods (`SetPixel`/`Clear`/`Fill`) to include `SubFill` and `SetImage`, so the structural type matches reality and `isinstance` checks are accurate. The conformance kit is the executable source of truth for this contract.

**Wrapper invariant (unstated today, made explicit here):** the backend's *raw* canvas needs only the 5-method contract **precisely because `ScaledCanvas` and `PreviewTee` sit on top of it** and supply the rest (`draw_bdf_text`, `rebind_innermost`, `.scale`, `.y_offset_real`, scale-dividing `width`/`height` properties). In production the canvas widgets receive is wrapped, never raw. A backend canvas could therefore pass the flat 5-method conformance and still break under the wrappers. The conformance kit must assert wrappability: wrap a `HeadlessBackend` canvas in `ScaledCanvas` at scale=4 **and** in `PreviewTee`, then verify draws land correctly. `_StubCanvas` satisfies this today; the kit makes it a checked invariant for any future backend.

## Lifecycle and the privilege-drop boundary (constraint #13)

Today the privilege drop (root → `daemon`) happens implicitly **inside** `build_frame_from_config` → `LedFrame()` → `RGBMatrix()` construction. Ordering is enforced only by textual position: plugin reconcile, `status_board.prepare_dir()`, and startup validation all happen to run before `build_frame_from_config` in `app/run.py`.

This spec makes the boundary an explicit, single-point lifecycle. **`build_frame_from_config` returns an un-setup frame** (this is decided here, not deferred to the plan — see the partial-construction hazard below), and `run()` calls `setup()` at one explicit line that becomes the asserted privilege boundary:

1. App performs all pre-drop privileged work (plugin reconcile, `status_board.prepare_dir()`, startup validation). **Unchanged.**
2. App calls `build_frame_from_config(config.display)` → constructs `LedFrame(backend=RgbMatrixBackend(options))`. **Cheap — no matrix built, no privilege drop.** Matrix construction is moved out of `LedFrame.__init__`/`__attrs_post_init__`.
3. App calls `led_frame.setup()` → `backend.setup()` → constructs `RGBMatrix(options)`. **The privilege drop happens here, at one declared point.**
4. **Post-setup initialization sequence** (all require a live backend): `_setup_preview` (`run.py:603`, calls `led_frame.create_canvas()`), the brightness scheduler's first `apply()` (writes `led_frame.brightness`), the busy-light hook. These run *after* step 3 — the spec makes this ordering explicit because today they work only by virtue of the matrix being built inside `build_frame_from_config`.
5. From here the process runs as `daemon`; all canvas/swap operations work.

`setup()` is a named lifecycle method so a conformance test can assert "`setup()` is the privilege boundary; no privileged operation precedes it." The existing tripwire `test_setup_runs_before_frame_build` is reframed to "`prepare_dir`/privileged work precedes `backend.setup()`, and `setup()` precedes preview/scheduler init."

`HeadlessBackend.setup()` builds its software matrix and never drops privileges.

### Partial-construction hazard

Moving `RGBMatrix()` out of `__attrs_post_init__` leaves `self.matrix` **and** `self._framerate_fraction` unset until `setup()` runs. `_framerate_fraction` is derived from the options in post-init today (`frame.py:91-95`) and read in *every* `swap()` (`frame.py:140,146`). So between construction and `setup()`, any `swap()` / `create_canvas()` / `brightness` access would otherwise `AttributeError`.

Resolution, fixed in this design:
- `_framerate_fraction` is computed inside `setup()` (it depends only on options, which the backend owns).
- `LedFrame` guards pre-`setup()` canvas/swap/brightness access and raises a **clear, named error** ("backend not set up — call setup() first"), not a bare `AttributeError`.
- A unit test asserts touching canvas/swap/brightness before `setup()` raises that clear error.

## The `graphics.DrawText` dispatch

`text_render.draw_text` (`text_render.py:21-36`) has **three** branches that reach a `DrawText` (not one):

1. `is_scaled(canvas)` (bigsign, scale>1) → `canvas.draw_bdf_text(...)` — the pure-Python BDF rasterizer (SetPixel-based).
2. `isinstance(canvas, PreviewTee)` (scale=1 with preview installed) → `_graphics.DrawText(canvas._hw, ...)` **then** `canvas.mirror_bdf_text(...)`. This branch exists *because of constraint #2*: the C `DrawText` type-checks for a real `Canvas` and rejects the tee, so text is drawn on `_hw` and the shadow is painted by a **second** rasterizer (`preview.py`).
3. bare real canvas (scale=1, no preview) → `_graphics.DrawText(canvas, ...)`.

**Key correction to the original framing:** a pure-Python `DrawText` that rasterizes the *same BDF parser* the bigsign uses **already ships and already runs off-hardware** — `_rgbmatrix_stub.DrawText` (`_rgbmatrix_stub.py:93-132`), reached via `require_graphics()` whenever rgbmatrix isn't installed (`_compat.py:16-21`). Its glyph math is the same as `ScaledCanvas.draw_bdf_text`. So `HeadlessBackend` at scale=1 already has correct text today.

**Resolution:** standardize on the pure-Python rasterizer at *all* scales. `DrawText` leaves the Canvas contract entirely — one text path for every backend. This **collapses the PreviewTee branch**: a SetPixel-based rasterizer paints *through* the tee directly (the tee already mirrors SetPixel), so `mirror_bdf_text` becomes dead code and is removed. That simplification is a benefit of this change and an explicit plan task (it is also a behavior change to the preview text path, called out here so it isn't a surprise).

**What the real risk actually is, and its gate:** the smallsign runs at scale=1 in production and the epic requires byte-identical production output. The open question is *not* "rasterizer vs an untestable C function" — it is **"does the C library's `DrawText` produce pixels identical to our BDF parser's `lit_pixels` on the bundled BDF fonts?"** That is a property of the C library's glyph rendering, independent of this refactor. It can only be answered on a Pi (the C `DrawText` needs a real `Canvas`). Therefore:

- A **one-time hardware validation on the real smallsign** renders representative text both ways (C `DrawText` vs our BDF rasterizer) and confirms byte-identical output on the bundled fonts.
- This validation is **independent of the backend work and could be run first**, decoupling C-path removal from the rest of the deliverable. C `graphics.DrawText` stays reachable for the scale=1 path only until that sign-off, then the branch is removed.
- Until sign-off, the engine keeps the C scale=1 branch; everything else in this deliverable ships regardless.

## Backend selection

- New config field: `[display] backend = "rgbmatrix" | "headless"`, default `"rgbmatrix"`.
- An internal name→class registry in `led_ticker.backends` maps the string to a backend class; `build_frame_from_config` selects via this registry.
- The registry is structured so a second population source (plugin entry points, `api.backend("web")`) is a purely additive change. That hook is **not built** here — the epic marks it TBD and there is no consumer yet.

Config validation (`led-ticker validate`) rejects an unknown backend name with the list of known backends.

### Failure-mode UX

The deliverable's dev/preview/CI value depends on these being good, not just possible:

- **`backend = "headless"` on real hardware** — runs blind (paints nothing to the panel). Must **log loudly at startup** ("headless backend selected — no hardware output") so it's never a silent mystery.
- **`backend = "rgbmatrix"` off hardware** — today `require_matrix()` raises a clear, actionable error at `frame.py:90`. Under the new lifecycle that error **moves to `backend.setup()`**; the message must survive the move and point the user at `backend = "headless"` as the dev/CI alternative.
- **Dev / CI story** — with `HeadlessBackend` shipped, running the full engine off-hardware is `backend = "headless"` with no `PYTHONPATH` tricks. This is the promotion of what `tools/render_demo` already does. The story is only "good" if the `PYTHONPATH=tests/stubs` removal lands in lockstep with the import repoint (see Packaging) so the suite stays green throughout.

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
- `tests/stubs/rgbmatrix/` collapses. **This is a broad import migration, not a fixture tweak.** ~30 test files import `from rgbmatrix import ...` / use `_StubCanvas` / construct `RGBMatrix(RGBMatrixOptions())` directly (e.g. `test_pixel_emoji.py`, `test_text_render.py`, `test_borders.py`, plus the `bigsign_canvas` fixture in `conftest.py`). The plan needs an explicit "repoint ~30 import sites to `led_ticker.backends.headless`" task with the real count.
  - **`mock_frame` / `swapping_frame` are NOT affected** — they are `mock.Mock()` objects mocking `LedFrame.get_clean_canvas`/`swap` (`conftest.py:53-88`), i.e. a level *above* the backend. They have nothing to rebind.
  - **Decision needed in the plan:** `_compat.py:16` itself does `from rgbmatrix import RGBMatrix, RGBMatrixOptions, graphics` under the stub fallback — so the `tests/stubs/rgbmatrix` import surface backs `_compat`'s *production* import too, not just tests. Either `_compat` keeps importing `from rgbmatrix` (real lib only, raising to `require_matrix()` semantics off-hardware) or it sources the matrix from `led_ticker.backends`. The plan picks one; this changes whether off-hardware core has *any* `rgbmatrix`-named import.
  - `make test` must stop setting `PYTHONPATH=tests/stubs` (`Makefile:17`) and drop `pyproject.toml:84` `extraPaths` / `pythonpath` **in lockstep** with the repoint, or imports break mid-migration.
- The graphics-only `_rgbmatrix_stub.py` remains (it backs `require_graphics()` for non-drawing operations on any machine, including the off-hardware `DrawText` rasterizer above).

### Plugins monorepo (downstream, separate repo)

The plugins monorepo currently reaches the full stub via a vendored copy / sibling `PYTHONPATH` (its README and CLAUDE.md have already drifted on which). Once the conformance kit and `HeadlessBackend` ship, the monorepo migrates to importing them as package symbols. Tracked separately under the plugins-monorepo work (#235); not part of this deliverable.

## Conformance kit

The kit encodes the 13 hardware constraints from `CLAUDE.md` as importable test functions parameterized over a backend instance. The subtle ones the full stub already encodes deliberately:

- **#1 / #8** — `swap()` returns a *different* canvas object than it was given (dropped-capture detection).
- **#2** — `DrawText` type-checking (becomes moot once `DrawText` leaves the contract; the kit asserts the canvas does *not* require it).
- **#3** — no `GetPixel` / no pixel readback expected.
- **#4** — `SetPixel` works on every canvas.
- **Canvas contract** — `SetPixel`, `Clear`, `Fill`, `SubFill`, `SetImage` all present and behave (paint/clear observable via the headless canvas's test-only `get_pixel`/`count_nonzero` helpers).
- **Wrappability** — a backend canvas wraps cleanly in `ScaledCanvas` at scale=4 and in `PreviewTee`; draws through the wrappers land correctly (guards against a backend that passes the flat contract but breaks under the production wrappers).
- **#13** — `setup()` is the declared privilege boundary; the app calls no privileged operation before it; canvas/swap/brightness access before `setup()` raises the clear named error.

`run_backend_conformance(backend_factory)` runs the full suite against any backend; core runs it against both `RgbMatrixBackend` (where constructible) and `HeadlessBackend`.

## Web-backend stress test (forward-looking validation)

A hypothetical socket-pushing backend satisfies the contract without contortion:

- `brightness` — a serialized field on the outgoing frame state.
- `setup()` — binds its (possibly privileged) port; never drops OS privileges.
- `create_canvas()` — returns a fresh in-memory buffer.
- `swap()` — serializes the back-buffer it was handed to the socket and returns the next buffer.
- `framerate_fraction` — accepted and ignored.

There is no `GetPixel`/readback (constraint #3), so `swap()` can only serialize state the canvas *accumulated* as it was drawn — i.e. the canvas must store its own pixels, exactly as `_StubCanvas._pixels` does. The practical consequence: **a streamed backend is `HeadlessBackend`'s canvas + a socket**, and should reuse the headless canvas rather than invent a parallel one. This strengthens the "headless is the reference software backend" framing. The contract does not assume `SwapOnVSync` naming, vsync semantics, or the rgbmatrix options shape. It survives.

`framerate_fraction` is the one place the protocol leaks hardware shape (a single consumer solving a real long-chain tearing problem). Acceptable now; if a second backend ever needs a *different* presentation hint, this becomes an options-bag conversation rather than a positional arg. Deferred deliberately.

## Testing strategy

- Conformance suite (above) run against `HeadlessBackend` and `RgbMatrixBackend`.
- `LedFrame` unit tests: overlay hooks, `record_swap`, preview tee, and `framerate_fraction` all exercised against `HeadlessBackend` (no `PYTHONPATH` stub).
- Tripwire: no `.matrix` reach-through outside `LedFrame` (AST or grep-based test, mirroring the existing `app/run.py` container tripwire style).
- Tripwire: `test_setup_runs_before_frame_build` reframed to assert `prepare_dir`/privileged work precedes `backend.setup()`.
- Selection: `[display] backend` round-trips through config load; unknown name rejected by `validate`.
- DrawText: existing text-render tests run against the rasterizer; the hardware pixel-diff is a manual/hardware task gating C-path removal.
- Production parity: a test asserts the `RGBMatrixOptions` produced from a given `DisplayConfig` is unchanged from today. **This runs against the *stub* `RGBMatrixOptions` off-hardware** (which has all attrs present), so it is a structural guard — it cannot catch a regression on an *older real build* where a `hasattr` guard matters. The `hasattr` guards and the `_framerate_fraction`/brightness derivation are explicitly in scope of the move and reviewed by reading, not just the parity test.

## Risks

- **Byte-identical scale=1 text** — the real question is C-`DrawText`-vs-BDF-parser agreement on bundled fonts (a property of the C library, independent of this refactor). Mitigated by the one-time hardware validation; C path retained until sign-off and decoupled from the rest of the work.
- **Partial-construction hazard** — addressed in design: `build_frame_from_config` returns un-setup, `_framerate_fraction` computed in `setup()`, pre-`setup()` access raises a clear named error (tested).
- **Privilege-drop regression** — mitigated by reframed tripwire and the explicit single-point `setup()`; this class of bug is not unit-testable (the stub does not setuid), so the change is small and the ordering is asserted structurally, including the post-`setup()` init sequence.
- **Test-migration breakage mid-flight** — ~30 import sites repoint in lockstep with the `Makefile`/`pyproject.toml` `PYTHONPATH` removal; sequenced so the suite stays green.
- **Hidden `.matrix` coupling** — the validation sweep found all current sites (`run.py:98,142,165,448`, `transitions:263,308`); the no-reach-through tripwire prevents regression.

## Implementation phasing (for the plan)

1. Introduce `backends/` with the `Backend` protocol, `RgbMatrixBackend` (options-building moved, incl. `hasattr` guards + `_framerate_fraction`), and `HeadlessBackend` (promoted stub). `LedFrame` holds a backend; add `create_canvas()` + `brightness` delegators with pre-`setup()` guards.
2. Repoint the three external `.matrix` sites (`run.py:448`, `transitions:263,308`) through `LedFrame.create_canvas()`, and the brightness writes through `LedFrame.brightness`; add the no-reach-through tripwire.
3. Explicit un-setup `build_frame_from_config` + `setup()` lifecycle in `run()` (with the post-setup init sequence ordered correctly); reframe the privilege tripwire; failure-mode logging.
4. Config `[display] backend` + registry + validation (unknown-name rejection; headless-on-hardware + rgbmatrix-off-hardware messages).
5. Conformance kit (incl. the ScaledCanvas/PreviewTee wrappability assertions); repoint the ~30 test import sites to `led_ticker.backends.headless`; decide `_compat`'s matrix import source; remove `PYTHONPATH=tests/stubs` from `Makefile`/`pyproject.toml`; collapse `tests/stubs/rgbmatrix/`.
6. DrawText: route scale=1 through the rasterizer (collapsing the PreviewTee branch + removing `mirror_bdf_text`) behind a flag; one-time hardware C-vs-rasterizer validation; remove C path on sign-off. **This phase is independent and can run first or last.**
