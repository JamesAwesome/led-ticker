# Physical-Resolution Rotation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** flair.propeller rotates at physical resolution on scaled displays — hires fonts spin, hires emoji spin (settle pop gone), rotation `scale×` finer — via a construct-once `RotationSurface` seam that a future rotation transition can reuse. Smallsign byte-identical.

**Architecture:** `PixelBuffer` gains `SubFill`/`clear` (the ScaledCanvas write path needs them); `rotate.py` gains `make_rotation_surface(canvas)` returning a cached-per-consumer surface (`.target` to draw into at logical coords, `.clear()` per frame, `.blit(angle, cx_logical)` with scale-aware pivot math); `TickerMessage` swaps its inline v1 policy for the surface and keeps the hires guard only at scale 1; rule 63 gates on `section.scale`.

**Tech Stack:** Python 3.14, attrs, pytest, ruff, pyright.

**Spec:** `docs/superpowers/specs/2026-07-02-physical-resolution-rotation-design.md` (antagonist-optimization-reviewed; the spec governs). Core repo only — no plugin changes (a one-line flair README follow-up happens later in the monorepo).

## Global Constraints

- Feature branch only (`git branch --show-current` first; abort on `main`).
- No `from __future__ import annotations`; "sanity"/"sane" banned (full-suite grep); no gun metaphors; lazy imports need `# noqa: PLC0415`; PEP-758 un-parenthesized `except A, B:` is project style; duck-typed canvas params are `Any`.
- **Smallsign byte-identity:** the existing rotation tests (`tests/test_rotate.py`, `tests/test_widgets/test_message_rotation.py`) must pass UNCHANGED except where a test asserts v1's construction pattern (per-draw `PixelBuffer(...)` patching) — those may be updated to the surface seam, but pixel-output assertions must not change.
- **Construct-once contract:** no per-frame `PixelBuffer`/`ScaledCanvas` construction anywhere in the new code — surfaces are cached on the consumer and `clear()`ed.
- **Antagonistic optimization review** is an added lens on every task review AND runs standalone on this plan before execution (stopping point #2).
- Per task: ruff check + ruff format before commit; pyright on touched src files. Final gate: full `make test`.

---

### Task 1: `PixelBuffer.SubFill` + `clear()`

**Files:**
- Modify: `src/led_ticker/rotate.py` (the `PixelBuffer` class)
- Test: `tests/test_rotate.py` (extend)

**Interfaces:**
- Produces: `PixelBuffer.SubFill(x, y, w, h, r, g, b)` (fills the clamped block; out-of-bounds portions silently ignored, matching SetPixel semantics) and `PixelBuffer.clear()` (every slot back to `None`). Task 2's wrapped surface depends on both; `ScaledCanvas.SetPixel`/`SubFill` call `self.real.SubFill(...)` (`scaled_canvas.py:88,94`).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_rotate.py`:

```python
class TestPixelBufferSubFill:
    def test_subfill_fills_exact_block(self) -> None:
        buf = PixelBuffer(8, 8)
        buf.SubFill(2, 3, 2, 2, 9, 8, 7)
        filled = {(x, y) for x in range(8) for y in range(8) if buf.get(x, y)}
        assert filled == {(2, 3), (3, 3), (2, 4), (3, 4)}
        assert buf.get(2, 3) == (9, 8, 7)

    def test_subfill_clamps_out_of_bounds(self) -> None:
        buf = PixelBuffer(4, 4)
        buf.SubFill(3, 3, 4, 4, 1, 1, 1)  # spills past both edges
        filled = {(x, y) for x in range(4) for y in range(4) if buf.get(x, y)}
        assert filled == {(3, 3)}
        buf2 = PixelBuffer(4, 4)
        buf2.SubFill(-2, -2, 3, 3, 1, 1, 1)  # negative origin clamps
        filled2 = {(x, y) for x in range(4) for y in range(4) if buf2.get(x, y)}
        assert filled2 == {(0, 0)}

    def test_clear_resets_all_slots(self) -> None:
        buf = PixelBuffer(4, 4)
        buf.SubFill(0, 0, 4, 4, 5, 5, 5)
        buf.clear()
        assert all(buf.get(x, y) is None for x in range(4) for y in range(4))


class TestWrappedBufferDraw:
    def test_scaled_canvas_over_buffer_draws_bdf_text(self) -> None:
        """Regression pin for spec §1b: ScaledCanvas writes route through
        real.SubFill — a bare PixelBuffer AttributeError'd here before
        this task. BDF text through the wrapper must land as scale-sized
        blocks in the buffer."""
        from led_ticker.fonts import FONT_DEFAULT
        from led_ticker.scaled_canvas import ScaledCanvas

        buf = PixelBuffer(64 * 4, 16 * 4)  # panel-shaped, scale 4
        wrapper = ScaledCanvas(buf, scale=4, content_height=16)
        wrapper.draw_bdf_text(FONT_DEFAULT, 0, 12, (255, 255, 255), "HI")
        lit = [
            (x, y)
            for x in range(buf.width)
            for y in range(buf.height)
            if buf.get(x, y)
        ]
        assert lit, "wrapped BDF draw painted nothing"
```

NOTE for the implementer: verify `ScaledCanvas.draw_bdf_text`'s exact signature and color-argument type in `scaled_canvas.py` before running (it may take a `graphics.Color` — construct via the test stubs the way `tests/test_scaled_canvas.py` does; copy that file's call pattern). The assertion (non-empty lit set) must not weaken.

- [ ] **Step 2: Run to verify failures**

Run: `uv run --extra dev pytest tests/test_rotate.py -k "SubFill or clear or WrappedBuffer" -v`
Expected: FAIL — `AttributeError: 'PixelBuffer' object has no attribute 'SubFill'` (and the wrapped-draw test fails the same way).

- [ ] **Step 3: Implement**

Add to `PixelBuffer` in `src/led_ticker/rotate.py`:

```python
    def SubFill(  # noqa: N802 - canvas API
        self, x: int, y: int, w: int, h: int, r: int, g: int, b: int
    ) -> None:
        """Fill the (clamped) w×h block at (x, y). Out-of-bounds portions
        are silently ignored — same semantics as SetPixel. Required by
        ScaledCanvas, whose SetPixel/SubFill write through real.SubFill."""
        x0 = max(0, x)
        y0 = max(0, y)
        x1 = min(self.width, x + w)
        y1 = min(self.height, y + h)
        pixel = (r, g, b)
        for yy in range(y0, y1):
            row = yy * self.width
            for xx in range(x0, x1):
                self._pixels[row + xx] = pixel

    def clear(self) -> None:
        """Reset every slot to None (transparent). The per-frame reset for
        construct-once rotation surfaces.

        Rebind-not-loop, adjudicated by the antagonist plan review: one
        C-level list construction per frame beats 16K interpreted stores;
        nothing else holds the list (the wrapper holds the BUFFER object;
        rotate_blit reads via get()). The Task-5 benchmark times clear()
        as part of the frame unit and re-adjudicates if it ever matters."""
        self._pixels = [None] * (self.width * self.height)
```

- [ ] **Step 4: Run to verify pass + module regression**

Run: `uv run --extra dev pytest tests/test_rotate.py -q`
Expected: all PASS (the 9 existing + new).

- [ ] **Step 5: Lint, pyright, commit**

```bash
uv run --extra dev ruff check src/ tests/ && uv run --extra dev ruff format src/ tests/
uv run --extra dev pyright src/led_ticker/rotate.py
git add src/led_ticker/rotate.py tests/test_rotate.py
git commit -m "feat(rotate): PixelBuffer.SubFill + clear — the ScaledCanvas write path

ScaledCanvas.SetPixel/SubFill write through real.SubFill; a bare
PixelBuffer AttributeError'd when wrapped. SubFill fills the clamped
block with SetPixel semantics; clear() is the per-frame reset for
construct-once surfaces. Physical-resolution rotation spec §1b."
```

---

### Task 2: `RotationSurface` + `make_rotation_surface`

**Files:**
- Modify: `src/led_ticker/rotate.py`
- Test: `tests/test_rotate.py` (extend)

**Interfaces:**
- Consumes: `PixelBuffer` (+ Task 1's additions), `rotate_blit`; `ScaledCanvas`, `is_scaled`, `unwrap_to_real` from `led_ticker.scaled_canvas`.
- Produces (Task 3 consumes):

```python
def make_rotation_surface(canvas: Any) -> RotationSurface

class RotationSurface:
    target: Any               # draw here, LOGICAL coordinates
    logical_width: int        # convenience for callers' pivot math
    logical_height: int
    def matches(self, canvas: Any) -> bool   # cache-validity: same dims/scale?
    def clear(self) -> None                  # per-frame reset
    def blit(self, canvas: Any, angle_deg: float, cx_logical: float) -> None
```

  `blit` takes the CURRENT canvas per call (wrapper identity is stable but
  `.real` is rebound per swap — hardware constraint #9 — so the surface
  must not capture a canvas reference at construction; it captures only
  dims/scale POLICY).
- Scale policy (spec §1): `not is_scaled(canvas)` → `target` = bare
  `PixelBuffer(canvas.width, canvas.height)`; blit → `rotate_blit(canvas,
  buffer, angle, cx_logical, canvas.height / 2)`. Scaled → buffer at
  `(w_real, h_real)` read from `unwrap_to_real(canvas)`, `target` =
  `ScaledCanvas(buffer, scale=canvas.scale, content_height=canvas.content_height)`;
  blit → `rotate_blit(unwrap_to_real(canvas), buffer, angle,
  cx_logical * scale, h_real / 2)` (continuous-coordinate pivot: pure
  scaling, NO half-block offset — spec §1).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_rotate.py`:

```python
class TestRotationSurface:
    def test_scale1_target_is_bare_buffer(self) -> None:
        from led_ticker.rotate import make_rotation_surface

        dst = _RecordingDst(160, 16)
        surface = make_rotation_surface(dst)
        assert isinstance(surface.target, PixelBuffer)
        assert (surface.target.width, surface.target.height) == (160, 16)

    def test_scaled_target_is_panel_shaped_wrapper(self) -> None:
        from led_ticker.rotate import make_rotation_surface
        from led_ticker.scaled_canvas import ScaledCanvas

        real = _RecordingDst(256, 64)
        wrapper = ScaledCanvas(real, scale=4, content_height=16)
        surface = make_rotation_surface(wrapper)
        assert isinstance(surface.target, ScaledCanvas)
        inner = surface.target.real
        assert isinstance(inner, PixelBuffer)
        assert (inner.width, inner.height) == (256, 64)
        assert surface.target.scale == 4
        assert surface.target.content_height == 16

    def test_scale1_blit_matches_v1_rotate_blit(self) -> None:
        """Byte-identity: surface.blit == direct rotate_blit at scale 1."""
        from led_ticker.rotate import make_rotation_surface

        direct_src = _buf_with_pixel(16, 16, 11, 8)
        direct_dst = _RecordingDst()
        rotate_blit(direct_dst, direct_src, 90.0, 8.0, 8.0)

        dst = _RecordingDst()
        surface = make_rotation_surface(dst)
        surface.target.SetPixel(11, 8, 255, 0, 0)
        surface.blit(dst, 90.0, 8.0)
        assert dst.pixels == direct_dst.pixels

    def test_scaled_blit_is_physical_granularity(self) -> None:
        """A 45-deg physical rotation must NOT be constant over each
        scale-x-scale block (that would mean logical-then-expanded)."""
        from led_ticker.rotate import make_rotation_surface
        from led_ticker.scaled_canvas import ScaledCanvas

        real = _RecordingDst(64, 64)
        wrapper = ScaledCanvas(real, scale=4, content_height=16)
        surface = make_rotation_surface(wrapper)
        # a full logical row through the wrapper -> 4px-tall physical bar
        for x in range(16):
            surface.target.SetPixel(x, 8, 200, 200, 200)
        surface.blit(wrapper, 45.0, 8.0)
        # group painted physical pixels by their 4x4 logical block; at
        # 45 deg some blocks MUST be partially lit (physical granularity)
        from collections import defaultdict

        blocks: dict[tuple[int, int], int] = defaultdict(int)
        for (x, y) in real.pixels:
            blocks[(x // 4, y // 4)] += 1
        assert any(0 < n < 16 for n in blocks.values()), (
            "every touched block fully lit — rotation happened at logical, "
            "not physical, granularity"
        )

    def test_scaled_pivot_maps_continuously(self) -> None:
        """180-deg physical rotation maps lit pixels through
        (x, y) -> (2*cx_phys - 1 - x, 2*cy_phys - 1 - y)-ish reflection;
        assert against the exact inverse-map: a pixel at physical
        (px, py) lands where the inverse of R(180) about
        (cx_logical*scale, h_real/2) sends it. Simplest exact check:
        one lit physical pixel, assert its single rotated position."""
        from led_ticker.rotate import make_rotation_surface
        from led_ticker.scaled_canvas import ScaledCanvas

        real = _RecordingDst(64, 64)
        wrapper = ScaledCanvas(real, scale=4, content_height=16)
        surface = make_rotation_surface(wrapper)
        inner = surface.target.real
        inner.SetPixel(44, 32, 255, 0, 0)  # physical coords, direct
        surface.blit(wrapper, 180.0, 8.0)  # cx_phys = 32.0, cy_phys = 32.0
        assert real.pixels.get((20, 32)) == (255, 0, 0)  # 2*32-44=20, 2*32-32=32

    def test_reuse_two_cycles_no_bleed(self) -> None:
        """Construct-once contract: clear() between frames — frame 2's
        output contains nothing from frame 1."""
        from led_ticker.rotate import make_rotation_surface

        dst1 = _RecordingDst()
        surface = make_rotation_surface(dst1)
        surface.target.SetPixel(11, 8, 255, 0, 0)
        surface.blit(dst1, 0.1, 8.0)
        assert dst1.pixels

        surface.clear()
        dst2 = _RecordingDst()
        surface.target.SetPixel(4, 2, 0, 255, 0)
        surface.blit(dst2, 0.1, 8.0)
        reds = [p for p in dst2.pixels.values() if p == (255, 0, 0)]
        assert not reds, "frame 1 content bled into frame 2"

    def test_matches_validates_cache(self) -> None:
        from led_ticker.rotate import make_rotation_surface
        from led_ticker.scaled_canvas import ScaledCanvas

        dst = _RecordingDst(160, 16)
        surface = make_rotation_surface(dst)
        assert surface.matches(dst)
        assert not surface.matches(_RecordingDst(320, 16))
        real = _RecordingDst(256, 64)
        wrapper = ScaledCanvas(real, scale=4, content_height=16)
        assert not surface.matches(wrapper)
        scaled_surface = make_rotation_surface(wrapper)
        assert scaled_surface.matches(wrapper)

    def test_matches_rejects_content_height_change(self) -> None:
        """Antagonist plan-review finding 1: widgets are shared across
        sections while content_height is section-level — a surface built
        at content_height=16 must NOT match a content_height=8 wrapper
        over the same real canvas (different y_offset_real centering)."""
        from led_ticker.rotate import make_rotation_surface
        from led_ticker.scaled_canvas import ScaledCanvas

        real = _RecordingDst(256, 64)
        wrapper16 = ScaledCanvas(real, scale=4, content_height=16)
        wrapper8 = ScaledCanvas(real, scale=4, content_height=8)
        surface = make_rotation_surface(wrapper16)
        assert surface.matches(wrapper16)
        assert not surface.matches(wrapper8)
```

- [ ] **Step 2: Run to verify failures**

Run: `uv run --extra dev pytest tests/test_rotate.py -k RotationSurface -v`
Expected: FAIL — `ImportError: cannot import name 'make_rotation_surface'`.

- [ ] **Step 3: Implement**

Add to `src/led_ticker/rotate.py` (module docstring gains a RotationSurface paragraph; imports of `ScaledCanvas`/`is_scaled`/`unwrap_to_real` go INSIDE the factory with `# noqa: PLC0415` if a module-level import would create a cycle — check: `scaled_canvas.py` does not import `rotate`, so a top-level import is safe; prefer top-level):

```python
class RotationSurface:
    """Construct-once offscreen rotation surface (spec §1).

    Draw into ``target`` using LOGICAL coordinates (on scaled displays the
    target is a panel-shaped ScaledCanvas wrapper, so hires fonts/emoji
    paint physical pixels through their existing gates). Call ``clear()``
    at the top of each frame and ``blit(canvas, angle, cx_logical)`` after
    drawing. Construct once per consumer and reuse — per-frame
    construction is allocator/GC waste (antagonist finding 4).

    Mechanism/policy split: rotate_blit stays the pure transform; ALL
    scale policy (buffer dims, wrapper, pivot mapping) lives here.
    """

    def __init__(self, canvas: Any) -> None:
        if is_scaled(canvas):
            real = unwrap_to_real(canvas)
            self._scale = canvas.scale
            self._content_height = canvas.content_height
            self._buffer = PixelBuffer(real.width, real.height)
            self.target: Any = ScaledCanvas(
                self._buffer,
                scale=canvas.scale,
                content_height=canvas.content_height,
            )
            self.logical_width = canvas.width
            self.logical_height = canvas.height
        else:
            self._scale = 1
            self._content_height = None
            self._buffer = PixelBuffer(canvas.width, canvas.height)
            self.target = self._buffer
            self.logical_width = canvas.width
            self.logical_height = canvas.height

    def matches(self, canvas: Any) -> bool:
        """Cache validity: same scale, dims, AND content_height.

        content_height is REQUIRED (antagonist plan-review finding 1):
        widget instances are cached by config dict and shared across
        sections (app/factories._cache_key), while content_height is a
        SECTION-level field — a shared widget drawn under two valid
        content_heights (e.g. 16 then 8 at scale 4) must rebuild, or it
        reuses a wrapper whose y_offset_real centers the wrong band.
        """
        if is_scaled(canvas):
            real = unwrap_to_real(canvas)
            return (
                self._scale == canvas.scale
                and self._content_height == canvas.content_height
                and self._buffer.width == real.width
                and self._buffer.height == real.height
            )
        return (
            self._scale == 1
            and self._buffer.width == canvas.width
            and self._buffer.height == canvas.height
        )

    def clear(self) -> None:
        self._buffer.clear()

    def blit(self, canvas: Any, angle_deg: float, cx_logical: float) -> None:
        """Inverse-rotate the buffer onto the canvas. Continuous-coordinate
        pivot: logical x maps to physical x*scale (NO half-block offset —
        the midpoint formula already carries half-pixel semantics, spec §1)."""
        if self._scale == 1:
            rotate_blit(
                canvas, self._buffer, angle_deg, cx_logical, canvas.height / 2
            )
        else:
            real = unwrap_to_real(canvas)
            rotate_blit(
                real,
                self._buffer,
                angle_deg,
                cx_logical * self._scale,
                self._buffer.height / 2,
            )


def make_rotation_surface(canvas: Any) -> RotationSurface:
    """Factory for a construct-once rotation surface bound to the canvas's
    scale policy (not to the canvas object — blit takes the live canvas)."""
    return RotationSurface(canvas)
```

- [ ] **Step 4: Run to verify pass + full module**

Run: `uv run --extra dev pytest tests/test_rotate.py -q`
Expected: all PASS.

- [ ] **Step 5: Lint, pyright, commit**

```bash
uv run --extra dev ruff check src/ tests/ && uv run --extra dev ruff format src/ tests/
uv run --extra dev pyright src/led_ticker/rotate.py
git add src/led_ticker/rotate.py tests/test_rotate.py
git commit -m "feat(rotate): RotationSurface — construct-once scale-aware rotation seam

Scale policy (buffer dims, ScaledCanvas wrapping, continuous-coordinate
pivot mapping) lives in ONE place; rotate_blit stays the pure transform.
Consumers construct once, clear() per frame, blit(canvas, angle, cx).
Widget-agnostic by design — a future rotation transition calls the same
three methods. Physical-resolution rotation spec §1."
```

---

### Task 3: `TickerMessage` — swap v1 inline policy for the cached surface

**Files:**
- Modify: `src/led_ticker/widgets/message.py` (the rotation branch, ~lines 239-338)
- Test: `tests/test_widgets/test_message_rotation.py` (extend + minimally adapt)

**Interfaces:**
- Consumes: `make_rotation_surface` / `RotationSurface` (Task 2).
- The widget gains `_rotation_surface: Any = attrs.field(init=False, default=None)` (match the class's private-field style).
- The hires guard SHRINKS to scale-1 only: `if not is_scaled(canvas) and isinstance(self.font, HiresFont)` → warn once + unrotated (message drops the "until physical-resolution rotation ships" clause; now says hires fonts don't rotate on scale-1 displays — see rule 59). On scaled canvases hires fonts go through the surface like everything else.
- Replacement shape for the branch (verify exact locals against the live code — line numbers are hints):

```python
        rotate_surface = None
        if rotation % 360 != 0:
            if not is_scaled(canvas) and isinstance(self.font, HiresFont):
                # scale-1 + hires: the bare buffer can't host real-pixel
                # glyphs (rule 59 territory); draw unrotated + warn once.
                if not self._warned_hires_rotation:
                    logging.warning(
                        "%s: rotation animation ignored — hires fonts don't "
                        "rotate on scale-1 displays (see validate rules 59 "
                        "and 63); switch to a BDF font to spin this widget",
                        type(self).__name__,
                    )
                    self._warned_hires_rotation = True
            else:
                if self._rotation_surface is None or not self._rotation_surface.matches(canvas):
                    self._rotation_surface = make_rotation_surface(canvas)
                self._rotation_surface.clear()
                rotate_surface = self._rotation_surface

        draw_canvas: Any = rotate_surface.target if rotate_surface is not None else canvas
        ...  # three text branches unchanged (they already use draw_canvas)
        if rotate_surface is not None:
            visible_left = max(0.0, float(start_pos))
            visible_right = min(float(canvas.width), float(start_pos) + float(content_width))
            rotate_surface.blit(canvas, rotation, (visible_left + visible_right) / 2)
```

  (`import is_scaled` from scaled_canvas at module top; drop the now-unused direct `PixelBuffer`/`rotate_blit` imports if nothing else uses them.)

- [ ] **Step 1: Adapt + extend the tests**

In `tests/test_widgets/test_message_rotation.py`:
- The existing `test_zero_rotation_never_builds_buffer` patches the v1 construction — update its patch target to `make_rotation_surface` (assert NOT called at rotation=0). Pixel-output assertions in ALL other existing tests stay untouched and must pass as-is.
- The `TestPerBranchRedirect` spy patches `rotate_blit` in the message module — that symbol may no longer be imported there; re-point the spy at `led_ticker.rotate.rotate_blit` (the surface calls it) or at `RotationSurface.blit`. Keep the three per-branch assertions identical in spirit: branch draws land in the buffer, canvas stays clean when blit is no-op'd.
- New tests:

```python
class TestScaledRotation:
    # Construct a ScaledCanvas(stub_real 256x64, scale=4, content_height=16)
    # widget draw with the _StubSpin(90.0) — follow the scaled-canvas stub
    # patterns in tests/test_scaled_canvas.py / tests/test_widgets tests.

    def test_scaled_draw_rotates_at_physical_granularity(self) -> None:
        """Lit physical pixels at 45 deg are NOT constant per 4x4 block
        (same assertion shape as the Task-2 surface test but through the
        WIDGET's full draw path)."""

    def test_hires_font_rotates_on_scaled_canvas_no_warning(self, caplog) -> None:
        """A HiresFont widget on a scaled canvas draws THROUGH the surface:
        physical pixels present at rotation=90, and NO hires-guard warning
        logged. (Obtain a HiresFont via resolve_font like the existing
        hires-guard test does.)"""

    def test_hires_guard_still_fires_at_scale1(self, caplog) -> None:
        """Unchanged v1 behavior at scale 1 (existing test may already
        cover; keep exactly one canonical version)."""

    def test_hires_emoji_present_in_rotated_output(self) -> None:
        """Scaled canvas + ':sun:' text + rotation=90: hires sprite pixels
        land in the physical output (the settle-pop eraser). Check how
        hires emoji tests construct their expectations in
        tests/test_pixel_emoji.py — reuse the availability gate/skip if
        the hires registry lacks the slug."""

    def test_surface_cached_across_draws(self) -> None:
        """Two rotating draws construct make_rotation_surface ONCE
        (spy/patch on the factory; count == 1) — the construct-once
        contract at the widget."""

    def test_surface_rebuilds_on_content_height_change(self) -> None:
        """Antagonist plan-review finding 1, widget-level: ONE widget
        instance drawn into two wrappers differing only in content_height
        (16 then 8, same real canvas, scale 4) rebuilds the surface —
        factory spy count == 2, and the second draw's lit physical rows
        center in the content_height=8 band (y_offset_real=16), not the
        stale 16-band."""
```

  Every test body must be fully implemented with real assertions (the
  docstrings above are the requirements). Copy scaled-canvas stub
  construction from existing tests; do not invent fixture shapes.

- [ ] **Step 2: Run to verify failures**

Run: `uv run --extra dev pytest tests/test_widgets/test_message_rotation.py -v`
Expected: new tests FAIL (scaled draws currently rotate at logical granularity / guard fires on scaled); existing pixel tests still pass.

- [ ] **Step 3: Implement** (the replacement shape above; keep the border/baseline/cursor logic untouched)

- [ ] **Step 4: Run the full affected set**

Run: `uv run --extra dev pytest tests/test_widgets/test_message_rotation.py tests/test_widgets/test_message.py tests/test_rotate.py tests/test_frames_to_rest.py -q`
Expected: all PASS.

- [ ] **Step 5: Lint, pyright, commit**

```bash
uv run --extra dev ruff check src/ tests/ && uv run --extra dev ruff format src/ tests/
uv run --extra dev pyright src/led_ticker/widgets/message.py
git add src/led_ticker/widgets/message.py tests/test_widgets/test_message_rotation.py
git commit -m "feat(message): physical-resolution rotation via cached RotationSurface

Scaled canvases rotate at physical granularity (hires fonts + emoji spin;
settle pop gone). Hires guard shrinks to scale-1 only (rule 59
territory). Surface cached on the widget — no per-draw allocation
(fixes v1's per-tick buffer construction too)."
```

---

### Task 4: rule 63 gates on `section.scale`

**Files:**
- Modify: `src/led_ticker/validate.py` (`_check_rotation_hires_font`)
- Test: `tests/test_validate_rotation_rules.py` (extend)

**Steps:**

- [ ] **Step 1: Failing tests** — extend the existing harness (same TOML builder): (a) a scale-4 display (`default_scale = 4` in `[display]`) with a rotation-emitting stub animation + hires font → rule 63 does NOT fire; (b) scale-1 (default) → still fires (existing test is the pin); (c) a section-level `scale = 1` override under a scale-4 display → fires for that section. Verify how a section-level `scale` key is written in TOML against `config.py` (~line 514) before writing (c).
- [ ] **Step 2:** Expected: (a) and (c) FAIL against current code (rule fires regardless of scale).
- [ ] **Step 3:** Implement: in the section loop add `if getattr(section, "scale", 1) != 1: continue`. CONFIRMED by the antagonist plan review: `section.scale` is the resolved per-section field (populated at config.py ~514 with `display.default_scale` as its default) — the plain attribute is correct; the `getattr` default is reload-safety only. Update the message: `"rotation animation will not spin the hires font {font_name!r} on a scale-1 section; the text will display normally (unrotated)"` — drop the "until physical-resolution rotation ships" clause. Docstring notes the per-section gate (antagonist finding 5).
- [ ] **Step 4:** `uv run --extra dev pytest tests/test_validate_rotation_rules.py tests/ -k "validate" -q` — green.
- [ ] **Step 5:** Lint/format/pyright; commit `feat(validate): rule 63 gates on the per-section resolved scale`.

---

### Task 5: performance benchmark (the gate — measured, not assumed)

**Files:**
- Create: scratch script only (session scratchpad — NOT committed); numbers land in the task report + PR description.

**Steps:**

- [ ] **Step 1:** Write a benchmark script that, per spec §5, times BOTH halves per frame at bigsign dims (256×64, scale 4), p95 over ≥200 iterations per angle:
  - (a) draw-into-wrapped-buffer: `surface.clear()` + BDF text (~20 chars) through the wrapper, AND — **mandatory, this is the gating worst case** (antagonist plan review): the same text through a HIRES font (per-physical-pixel SetPixel loops into list slots, the slowest draw path);
  - (b) `surface.blit` at angles 0.1°, 45°, 90°, 137°;
  - report per-half and combined per-frame times, gating on the hires-draw + 45°-blit combination.
- [ ] **Step 2:** Run on the dev machine; apply the ×3 Pi-5 factor. ALSO run the headless smoke-harness engine-tick timing at bigsign dims (spec §5 asks for both; the harness run is not optional). **Acceptance: combined p95 ≤ 15 ms on-target-equivalent** (i.e. ≤ 5 ms measured on desktop).
- [ ] **Step 3:** If the gate FAILS: stop, report the numbers, and implement the documented half-resolution fallback (spec §5) as a follow-on task — do NOT invent other optimizations without a measurement showing where the time goes (profile first: `python -X importtime` no — use `cProfile` on the hot loop).
- [ ] **Step 4:** Record the numbers (both halves, all angles, desktop + on-target-equivalent) in the task report for the PR description.

---

### Task 6: docs + spec/plan ride-along

**Files:**
- Modify: `docs/site/src/content/docs/plugins/api-reference.mdx` (the rotation prose: hires fonts/emoji now rotate on scaled displays; the scale-1 caveat; the construct-once surface note for plugin authors)
- Modify: `docs/site/src/content/docs/concepts/animations.mdx` (the one-sentence seam note: drop any "logical resolution" caveat if present)
- Also commit: the spec + this plan (`docs/superpowers/specs/2026-07-02-physical-resolution-rotation-design.md`, `docs/superpowers/plans/2026-07-02-physical-resolution-rotation.md`)

**Steps:**
- [ ] Read `docs/DOCS-STYLE.md` + both pages; make the edits; `uv run --extra dev pytest tests/test_docs_plugin_api_drift.py -q && make docs-format && make docs-lint` green; commit.
- [ ] NOTE (not this repo): flair's README "BDF fonts only for now" caveat becomes stale once this ships — a one-line monorepo follow-up PR after merge; record it in the task report so the controller queues it.

---

### Task 7: full verification + visual matrix

- [ ] **Step 1:** `make test` (full suite; meta-tripwires). `uv run --extra dev ruff check src/ tests/ && uv run --extra dev ruff format --check src/ tests/ && uv run --extra dev pyright src/` — clean.
- [ ] **Step 2:** Visual matrix per `docs/visual-validation.md`, BIGSIGN geometry (`default_scale = 4`, 256×64 display config), rendered with the flair plugin installed (editable, as in the flair PR's Task 4 — same driver pattern): propeller + BDF text; propeller + hires font (the headline feature); propeller + `:sun:` emoji (**assert NO settle pop**: the frames around the settle boundary show no sprite-resolution change); overflow at scale 4; `direction = "ccw"`; plus ONE smallsign config as the byte-identity regression render.
- [ ] **Step 3:** Frame-profile each (lit-pixel counts — zero fully-black frames; deduped long frames at rest) and eyeball the extracted frames. Fix anything found (fail-first), re-run.

---

## PLAN ADDENDUM — Revision 2/3 tasks (replace original Task 5; Tasks 6-7 amended)

Spec Revisions 2-3 (artifact architecture + corrected gate) supersede the
per-frame draw model that Tasks 2-3 shipped. Tasks 5A-5C below revise the
shipped code on this branch. Prototype code with MEASURED, identical-output
implementations lives in the session scratchpad (`bench_optblit.py`,
`bench_corrected.py`) — implementers transcribe the algorithms from the
spec + this addendum, not the scratchpad (which is not committed).

### Task 5A: rotate.py — lit-extent tracking, optimized blit, artifact surface

**Files:** Modify `src/led_ticker/rotate.py`; extend `tests/test_rotate.py`.

**Interfaces produced:**
- `PixelBuffer.lit_extent -> tuple[int, int, int, int] | None` — (x0, y0,
  x1exclusive, y1exclusive) of lit slots, tracked incrementally in
  `SetPixel`/`SubFill` (4 comparisons per write; `clear()` resets to None).
- `rotate_blit(dst, src, angle_deg, cx, cy, src_extent=None)` — optional
  extent limits the scan region to the AABB of the ROTATED extent corners
  (default: full src rect — back-compat, existing tests unchanged). Inner
  loop rewritten: per-row DDA forward differencing (`sx += cos_t; sy -=
  sin_t`), `int(sx)` truncation with the `+0.5` fold into the row-start
  terms, hoisted `src._pixels` direct indexing with explicit bounds check.
  OUTPUT MUST BE BYTE-IDENTICAL to the previous implementation — new test:
  parametrized arbitrary angles (7.3°, 45°, 61.7°, 137°, 289°) comparing
  the new implementation against a preserved reference implementation
  (keep the old loop as `_rotate_blit_reference` in the TEST file, not in
  src) on a random-ish lit pattern, with and without src_extent.
- `RotationSurface` revised per spec R2/R3:
  - `snapshot()` — extent-scoped any-lit box downsample full→half
    (scale > 1) or a validity-mark only (scale == 1); sets
    `self.has_snapshot = True`.
  - `invalidate()` — clears `has_snapshot` (widget calls on visit reset).
  - `clear()` — unchanged (clears the full-res target + invalidates).
  - `blit(canvas, angle_deg, cx_logical)` — scale > 1: blits the HALF
    buffer through a construct-once `ScaledCanvas(real, scale=2,
    content_height=h_real // 2)` dst wrapper (REBOUND to the live real
    each call: `self._dst_wrapper.real = unwrap_to_real(canvas)` — one
    assignment, constraint #9), pivot `(cx_logical * scale / 2,
    h_real / 4)`, passing the half buffer's lit_extent. scale == 1:
    direct blit of the artifact with its extent.
  - `matches()` unchanged (scale + dims + content_height).

**Tests (all real assertions):** extent tracking across SetPixel/SubFill/
clear; blit identity old-vs-new (angles × extent on/off); downsample
preserves 1-px strokes (draw a 1-px hires-style line at an odd physical
coordinate, assert it survives in the half buffer — the any-lit pin);
emoji-size-in-artifact (hi-res sprite spans its full physical rows in the
artifact, and the downsampled copy spans half — size-correct); snapshot/
invalidate lifecycle; half-space pivot exactness (180° single-pixel map
through the scale-2 dst wrapper, asserting the SubFill'd 2×2 block
position); two-cycle no-bleed via snapshot.

### Task 5B: TickerMessage — snapshot lifecycle

**Files:** Modify `src/led_ticker/widgets/message.py`; extend
`tests/test_widgets/test_message_rotation.py`.

Replace the per-frame clear+draw with: on a rotating draw, if
`self._rotation_surface` missing/mismatched → rebuild + invalidate; if
`not surface.has_snapshot` → `surface.clear()`, run the three text
branches into `surface.target`, then `surface.snapshot()`; ALWAYS
`surface.blit(canvas, rotation, cx)` (cx from the cached
start_pos/content_width — both stable across the spin; verify against the
animation-path cursor recompute). On non-rotating draws: normal live path
(unchanged), and the artifact is NOT invalidated by rotation==0 (spec R3
resolution H3) — invalidation happens in `reset_frame()` (add
`if self._rotation_surface is not None: self._rotation_surface.invalidate()`
— check reset_frame lives on FrameAwareBase; override or hook in the
widget per the existing pattern) and on matches-rebuild.

**Tests:** branches called ONCE across N rotating draws (spy on
draw_text/the branch entry, count == 1 while blit count == N); artifact
survives a mid-spin exact-0 angle frame (draw with rotation=0 mid-
sequence → live draw that frame, artifact still valid after — blit
resumes without re-snapshot); visit restart re-snapshots (reset_frame →
next rotating draw re-runs branches); ANIMATED provider frozen mid-spin
(rainbow font_color: artifact pixels identical across two rotating draws
even though frame_for advanced — the freeze pin); settle resumes live
colors (rotation 0 draw output differs from the frozen artifact's colors
when the provider advanced — sample a char pixel).

### Task 5C: benchmark (methodology pinned by spec R3.4)

Scratch script (not committed): full-panel dst geometry
(content_height=h_real//2), any-lit downsample, C-call-modeled dst
SubFill, warmed p95 ≥150 iters, angles 0.1/45/90/137, BDF + hires draw
halves both mandatory. Report: one-time (draw + downsample) and per-frame
(blit) separately. Acceptance: per-frame p95 ≤ 15 ms on-target-equivalent
(×3); one-time ≤ 50 ms on-target. Numbers into the task report + PR body.

### Task 6 (amended): docs also disclose the R2.3 color freeze (animated
font_color sweeps pause during the spin, resume at settle) and the
settle "detail sharpening" (mid-spin renders at half detail). Task 7
(amended): the visual matrix adds a rainbow+propeller bigsign config
(verify the freeze looks acceptable and colors resume at settle) and
keeps the emoji no-art-swap check (hi-res art at half detail mid-spin,
NOT the lo-res sprite).
