# Propeller Core Seam Implementation Plan (led-ticker PR 1 of 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the core rotation seam (`AnimationFrame.rotation`, the `rotate.py` engine, TickerMessage integration, validate rules 62/63, `ENGINE_TICK_MS` plugin export) so the flair plugin's `flair.propeller` animation can be built against it.

**Architecture:** An animation emits `rotation` degrees per frame; TickerMessage redirects its normal text draw into an owned `PixelBuffer` and inverse-rotate-blits it onto the canvas around the text block's center. Validate gains a generic animation-duration rule (62) and a rotation-on-hires-font rule (63), both duck-typed and best-effort (they fire only when the animation coerces).

**Tech Stack:** Python 3.14, attrs, pytest (stubs auto-on-path), ruff, pyright.

**Spec:** `docs/superpowers/specs/2026-07-02-flair-spin-animation-design.md` (two-round validated; the spec governs on ambiguity).

## Global Constraints

- Work on the feature branch ONLY. `git branch --show-current` first; abort if `main`.
- No `from __future__ import annotations`. Lazy in-function imports need `# noqa: PLC0415`.
- "sanity"/"sane" are BANNED repo-wide (full-suite grep test); use "correctness check"/"quick check". No "footgun"/gun metaphors.
- `except ValueError, TypeError:` (un-parenthesized tuple) is PROJECT STYLE (PEP 758; ruff format normalizes TO it) — copy rule 61's form; do not "fix" it.
- Rotation convention: degrees, clockwise-positive; `rotation % 360 == 0` means "no rotation" and MUST take the normal (non-buffer) draw path.
- The hires-font guard is LOAD-BEARING (a HiresFont rendered into a logical buffer is garbage, not merely unrotated) — never remove it as a "simplification".
- Rules 62/63 are best-effort: a failed `_coerce_animation` is swallowed (`continue`) — the unknown-style error with its plugin install-hint owns that messaging.
- Never commit anything under `.superpowers/` (gitignored scratch; no `git add -f`). Stage files by explicit path.
- Before every commit: `uv run --extra dev ruff check src/ tests/ && uv run --extra dev ruff format src/ tests/`. Run `uv run --extra dev pyright src/` at least once per task.
- Final gate is the FULL `make test` (meta-tripwires only fire on the full suite).

---

### Task 1: `AnimationFrame.rotation` + `ENGINE_TICK_MS` plugin export

**Files:**
- Modify: `src/led_ticker/animations.py` (the `AnimationFrame` dataclass, ~line 20)
- Modify: `src/led_ticker/plugin.py` (import block ~line 38 area; `__all__` list ~line 98)
- Test: `tests/test_animations_rotation.py` (create)

**Interfaces:**
- Produces: `AnimationFrame.rotation: float = 0.0` (Task 3 reads it); `from led_ticker.plugin import ENGINE_TICK_MS` works (the flair PR hard-blocks on this — it is an explicit acceptance criterion).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_animations_rotation.py`:

```python
"""AnimationFrame.rotation seam + ENGINE_TICK_MS plugin export
(propeller spec §1/§2)."""

from led_ticker.animations import AnimationFrame, Typewriter


def test_rotation_defaults_to_zero() -> None:
    frame = AnimationFrame(visible_text="HI")
    assert frame.rotation == 0.0


def test_rotation_keyword_settable() -> None:
    frame = AnimationFrame(visible_text="HI", rotation=90.0)
    assert frame.rotation == 90.0


def test_typewriter_emits_zero_rotation() -> None:
    """Back-compat: Typewriter's frames carry the default rotation."""
    tw = Typewriter()
    assert tw.frame_for(5, "HELLO", 160, 40).rotation == 0.0


def test_engine_tick_ms_on_plugin_surface() -> None:
    """Acceptance criterion (spec §2): flair imports ENGINE_TICK_MS from
    led_ticker.plugin — its import-purity test forbids any other path."""
    from led_ticker import constants, plugin

    assert plugin.ENGINE_TICK_MS is constants.ENGINE_TICK_MS
    assert "ENGINE_TICK_MS" in plugin.__all__
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run --extra dev pytest tests/test_animations_rotation.py -v`
Expected: FAIL — `AnimationFrame.__init__() got an unexpected keyword argument 'rotation'` (or attribute missing) and the plugin-surface test fails.

- [ ] **Step 3: Implement**

(a) In `src/led_ticker/animations.py`, extend the dataclass:

```python
@dataclass
class AnimationFrame:
    """What the widget should render at the current frame.

    visible_text: The slice (or full text) to draw. Typewriter returns
                  growing prefixes.
    rotation:     In-plane rotation of the rendered text in degrees,
                  clockwise-positive. 0.0 (the default) means no rotation
                  and takes the widget's normal draw path. Non-zero routes
                  the text through an offscreen buffer + rotate_blit
                  (see led_ticker.rotate). Emitted by rotation-capable
                  animations (e.g. the flair plugin's propeller).
    """

    visible_text: str
    rotation: float = 0.0
```

(b) In the `Animation` Protocol docstring (same file), append one
paragraph documenting the two optional rotation hooks (spec §5):

```
    Rotation-capable animations set ``rotation`` (degrees, clockwise-
    positive) on the frames they return, and declare the class attribute
    ``emits_rotation = True`` — a duck-typed marker validate rule 63
    reads to warn about hires-font widgets (whose text cannot rotate
    until physical-resolution rotation ships). Animations without the
    attribute never rotate.
```

(c) In `src/led_ticker/plugin.py`: add `ENGINE_TICK_MS` to the import block —

```python
from led_ticker.constants import ENGINE_TICK_MS
```

(placed alphabetically among the `from led_ticker...` imports, after the `colors` import) and add `"ENGINE_TICK_MS",` to `__all__` (match the list's existing grouping — near the other ALL-CAPS constants like `EMOJI_ROW_CAP`).

- [ ] **Step 4: Run to verify pass + drift guard**

Run: `uv run --extra dev pytest tests/test_animations_rotation.py tests/test_docs_plugin_api_drift.py tests/test_frames_to_rest.py -q`
Expected: the new tests pass. NOTE: `test_docs_plugin_api_drift.py` checks `__all__` names against the docs API-reference page — if it FAILS on the new export, add `ENGINE_TICK_MS` to the exported-names region of `docs/site/src/content/docs/plugins/api-reference.mdx` (inside the guarded region, one entry, matching the page's format) and re-run.

- [ ] **Step 5: Lint, format, commit**

```bash
uv run --extra dev ruff check src/ tests/ && uv run --extra dev ruff format src/ tests/
git add src/led_ticker/animations.py src/led_ticker/plugin.py tests/test_animations_rotation.py
# plus docs/site/.../api-reference.mdx if the drift guard required it
git commit -m "feat(animations): AnimationFrame.rotation field + ENGINE_TICK_MS plugin export

Seam for rotation-emitting animations (flair.propeller). rotation
defaults 0.0 — every existing animation is untouched. ENGINE_TICK_MS
joins the public plugin surface (flair's import-purity forbids any
other path). Part of the propeller spec (PR 1 of 2)."
```

---

### Task 2: rotation engine — `src/led_ticker/rotate.py`

**Files:**
- Create: `src/led_ticker/rotate.py`
- Test: `tests/test_rotate.py` (create)

**Interfaces:**
- Produces: `PixelBuffer(width, height)` with `.SetPixel(x,y,r,g,b)`, `.width`, `.height`, `.get(x,y) -> tuple[int,int,int] | None`; `rotate_blit(dst, src, angle_deg, cx, cy)` — Task 3 consumes both.
- Resolution-agnostic by contract: NO logical-vs-physical assumptions anywhere in this module (the physical-resolution follow-up depends on it).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_rotate.py`:

```python
"""PixelBuffer + rotate_blit (propeller spec §3): inverse-mapped
nearest-neighbor rotation; unset pixels are transparent."""

from led_ticker.rotate import PixelBuffer, rotate_blit
from led_ticker.scaled_canvas import unwrap_to_real


def _buf_with_pixel(w: int, h: int, x: int, y: int) -> PixelBuffer:
    buf = PixelBuffer(w, h)
    buf.SetPixel(x, y, 255, 0, 0)
    return buf


class TestPixelBuffer:
    def test_set_and_get(self) -> None:
        buf = PixelBuffer(8, 8)
        buf.SetPixel(2, 3, 10, 20, 30)
        assert buf.get(2, 3) == (10, 20, 30)
        assert buf.get(0, 0) is None  # unset = transparent

    def test_out_of_bounds_setpixel_ignored(self) -> None:
        buf = PixelBuffer(4, 4)
        buf.SetPixel(-1, 0, 1, 1, 1)
        buf.SetPixel(4, 0, 1, 1, 1)
        buf.SetPixel(0, 99, 1, 1, 1)
        assert all(buf.get(x, y) is None for x in range(4) for y in range(4))

    def test_unwrap_to_real_identity(self) -> None:
        """PM round-2 finding 11: the no-`.real` base case of
        unwrap_to_real must return the buffer itself."""
        buf = PixelBuffer(4, 4)
        assert unwrap_to_real(buf) is buf


class _RecordingDst:
    """Minimal SetPixel recorder standing in for a canvas."""

    def __init__(self, w: int = 16, h: int = 16) -> None:
        self.width = w
        self.height = h
        self.pixels: dict[tuple[int, int], tuple[int, int, int]] = {}

    def SetPixel(self, x: int, y: int, r: int, g: int, b: int) -> None:
        self.pixels[(x, y)] = (r, g, b)


class TestRotateBlit:
    def test_90_degrees_exact_permutation(self) -> None:
        """A pixel at (cx+3, cy) rotated 90 deg clockwise about (cx, cy)
        lands at (cx, cy+3)."""
        src = _buf_with_pixel(16, 16, 11, 8)  # (cx+3, cy) with cx=8, cy=8
        dst = _RecordingDst()
        rotate_blit(dst, src, 90.0, 8.0, 8.0)
        assert dst.pixels.get((8, 11)) == (255, 0, 0)

    def test_180_degrees_exact(self) -> None:
        src = _buf_with_pixel(16, 16, 11, 8)
        dst = _RecordingDst()
        rotate_blit(dst, src, 180.0, 8.0, 8.0)
        assert dst.pixels.get((5, 8)) == (255, 0, 0)

    def test_270_degrees_exact(self) -> None:
        src = _buf_with_pixel(16, 16, 11, 8)
        dst = _RecordingDst()
        rotate_blit(dst, src, 270.0, 8.0, 8.0)
        assert dst.pixels.get((8, 5)) == (255, 0, 0)

    def test_center_pixel_invariant_at_any_angle(self) -> None:
        for angle in (0.0, 33.0, 45.0, 137.5, 359.0):
            src = _buf_with_pixel(16, 16, 8, 8)  # exactly the center
            dst = _RecordingDst()
            rotate_blit(dst, src, angle, 8.0, 8.0)
            assert dst.pixels.get((8, 8)) == (255, 0, 0), f"angle={angle}"

    def test_transparency_never_paints_unset(self) -> None:
        """Unset src pixels must not overwrite dst — dst records NOTHING
        outside the rotated lit pixel."""
        src = _buf_with_pixel(16, 16, 11, 8)
        dst = _RecordingDst()
        rotate_blit(dst, src, 45.0, 8.0, 8.0)
        assert 0 < len(dst.pixels) <= 4  # the one lit pixel (nearest-neighbor spread), nothing else

    def test_all_painted_pixels_in_dst_bounds(self) -> None:
        src = PixelBuffer(16, 16)
        for x in range(16):
            src.SetPixel(x, 8, 200, 200, 200)  # full-width line
        dst = _RecordingDst(16, 16)
        for angle in (17.0, 45.0, 90.0, 245.0):
            rotate_blit(dst, src, angle, 8.0, 8.0)
        assert all(
            0 <= x < 16 and 0 <= y < 16 for (x, y) in dst.pixels
        )
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run --extra dev pytest tests/test_rotate.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'led_ticker.rotate'`.

- [ ] **Step 3: Implement**

Create `src/led_ticker/rotate.py`:

```python
"""Pixel-space rotation engine for rotation-emitting animations.

Resolution-agnostic BY CONTRACT: nothing here knows about logical vs
physical pixels or ScaledCanvas — the physical-resolution follow-up
(propeller spec) reuses this module unchanged at real-pixel dims.

PixelBuffer is an OWNED raster: reading it back is fine (hardware
constraint #3 forbids GetPixel on real canvases, not on our objects).
"""

import math


class PixelBuffer:
    """Minimal readable raster with real-canvas SetPixel semantics
    (out-of-bounds writes are silently ignored)."""

    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self._pixels: list[tuple[int, int, int] | None] = [None] * (width * height)

    def SetPixel(self, x: int, y: int, r: int, g: int, b: int) -> None:  # noqa: N802 - canvas API
        if 0 <= x < self.width and 0 <= y < self.height:
            self._pixels[y * self.width + x] = (r, g, b)

    def get(self, x: int, y: int) -> tuple[int, int, int] | None:
        """The pixel at (x, y), or None when unset (= transparent)."""
        if 0 <= x < self.width and 0 <= y < self.height:
            return self._pixels[y * self.width + x]
        return None


def rotate_blit(dst, src: PixelBuffer, angle_deg: float, cx: float, cy: float) -> None:
    """Paint `src` onto `dst` rotated `angle_deg` clockwise about (cx, cy).

    Inverse-mapped nearest-neighbor: for each dst pixel, sample src at
    R(-angle) — hole-free at every angle (a forward map leaves ~30% gaps
    at 45 deg). Unset src pixels are transparent (never painted), so the
    dst background survives outside the rotated content.

    `dst` is anything with SetPixel (real canvas, ScaledCanvas, another
    buffer). Callers gate the `angle % 360 == 0` no-op; this function
    always blits.
    """
    theta = math.radians(angle_deg)
    cos_t = math.cos(theta)
    sin_t = math.sin(theta)

    # Conservative dst scan region: the axis-aligned bounds of the src
    # rect's four rotated corners, clamped to dst dims.
    corners = [(0.0, 0.0), (src.width, 0.0), (0.0, src.height), (src.width, src.height)]
    xs = []
    ys = []
    for px, py in corners:
        dx, dy = px - cx, py - cy
        xs.append(cx + dx * cos_t - dy * sin_t)
        ys.append(cy + dx * sin_t + dy * cos_t)
    dst_w = getattr(dst, "width", src.width)
    dst_h = getattr(dst, "height", src.height)
    x0 = max(0, math.floor(min(xs)))
    x1 = min(dst_w - 1, math.ceil(max(xs)))
    y0 = max(0, math.floor(min(ys)))
    y1 = min(dst_h - 1, math.ceil(max(ys)))

    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            # Inverse map: where in src does this dst pixel come from?
            dx, dy = x - cx, y - cy
            sx = cx + dx * cos_t + dy * sin_t
            sy = cy - dx * sin_t + dy * cos_t
            pixel = src.get(round(sx), round(sy))
            if pixel is not None:
                dst.SetPixel(x, y, *pixel)
```

NOTE for the implementer on the rotation matrix: clockwise-positive in
screen coordinates (y grows DOWN) means forward map
`(dx·cos−dy·sin, dx·sin+dy·cos)`; the inverse (used per dst pixel) is the
transpose, as written. Verify against the 90° test: src (cx+3, cy) must
land at dst (cx, cy+3) — if your first run fails with (cx, cy−3), the
sin signs are flipped for screen coords; fix the implementation, not the
test (the test encodes the spec's clockwise convention).

- [ ] **Step 4: Run to verify pass**

Run: `uv run --extra dev pytest tests/test_rotate.py -v`
Expected: all PASS.

- [ ] **Step 5: Lint, format, pyright, commit**

```bash
uv run --extra dev ruff check src/ tests/ && uv run --extra dev ruff format src/ tests/
uv run --extra dev pyright src/led_ticker/rotate.py
git add src/led_ticker/rotate.py tests/test_rotate.py
git commit -m "feat(rotate): PixelBuffer + inverse-mapped rotate_blit

Resolution-agnostic rotation engine for rotation-emitting animations.
Inverse nearest-neighbor mapping (hole-free at every angle); unset
pixels transparent. Part of the propeller spec (PR 1 of 2)."
```

---

### Task 3: TickerMessage integration — buffer redirect + hires guard

**Files:**
- Modify: `src/led_ticker/widgets/message.py` (`TickerMessage.draw`, the branch region ~lines 175-290)
- Test: `tests/test_widgets/test_message_rotation.py` (create)

**Interfaces:**
- Consumes: `AnimationFrame.rotation` (Task 1); `PixelBuffer`, `rotate_blit` (Task 2); existing `start_pos` (~line 213) and `content_width` (~line 205) locals; `HiresFont` (`led_ticker.fonts.hires_loader`).
- Produces: the user-visible rotation behavior. Nothing downstream consumes new symbols.

- [ ] **Step 1: Read the integration region END TO END**

Read `TickerMessage.draw` fully (message.py ~lines 130-300) before editing: the animation slice (~182-188), `compute_cursor` → `start_pos` (~205-213), the border paint (~226-227), and the three text branches (emoji ~229-252 / per-char ~253-274 / whole-string ~275-287). The three branches all draw onto the local canvas reference — the redirect swaps that target.

- [ ] **Step 2: Write the failing tests**

Create `tests/test_widgets/test_message_rotation.py`. Model widget construction on `tests/test_widgets/test_message.py` (copy its minimal-kwargs pattern; use its canvas stub or `conftest` fixtures). The behaviors — write each as a real test:

```python
"""TickerMessage rotation seam (propeller spec §4): non-zero
AnimationFrame.rotation redirects text into a PixelBuffer and
rotate_blits it; rotation=0 is byte-identical to the normal path."""


class _StubSpin:
    """Animation stub emitting a fixed rotation with full text."""

    restart_on_visit = True

    def __init__(self, rotation: float) -> None:
        self.rotation = rotation

    def frame_for(self, frame, full_text, canvas_width, text_width):
        from led_ticker.animations import AnimationFrame

        return AnimationFrame(visible_text=full_text, rotation=self.rotation)


# Tests (fill in with the real harness):
# 1. test_zero_rotation_never_builds_buffer — rotation=0.0 stub; patch
#    led_ticker.widgets.message.PixelBuffer (or the rotate module) with a
#    Mock and assert it is NOT called; pixel output identical to a draw
#    with animation=None (compare stub-canvas pixel dicts).
# 2. test_rotation_180_flips_text_pixels — draw once with rotation=0,
#    record lit pixels; draw with rotation=180; assert the 180 set equals
#    the 0 set mapped through (x,y) -> (2*cx - x, 2*cy - y), rounded —
#    where cx = start_pos + content_width/2 and cy = canvas.height/2
#    (recompute start_pos/content_width the way the widget does, or
#    derive cx from the recorded unrotated pixel extent's midpoint).
# 3. test_border_stays_unrotated — widget with border=<stub border that
#    paints a known corner pixel> + rotation=90: the border pixel is at
#    its normal location, not rotated.
# 4. test_cursor_advance_unchanged_by_rotation — draw() return cursor_pos
#    equal between rotation=0 and rotation=90 runs.
# 5. test_hires_font_skips_rotation_with_warning — widget whose font is a
#    HiresFont instance (construct via fonts.resolve_font with a hires
#    name if available in the test env, else monkeypatch isinstance
#    target by assigning a HiresFont-typed dummy): rotation=90 draws the
#    NORMAL path (pixel output == rotation=0 output) and caplog captures
#    one warning; a second draw does NOT log again (once per instance).
# 6. test_emoji_rotates_with_text — text "GO :sun: GO" + rotation=180:
#    the sprite's lit pixels appear in the rotated positions (subset
#    check against the unrotated draw mapped through the 180 formula).
```

The comment block above is the requirements list — every numbered test MUST be implemented with real assertions. Where the harness details live in existing test files, copy them; do not invent fixture shapes.

- [ ] **Step 3: Run to verify failures**

Run: `uv run --extra dev pytest tests/test_widgets/test_message_rotation.py -v`
Expected: FAIL — rotation is currently ignored (tests 2/3/6 fail; test 1 may pass trivially — confirm it fails for the right reason by asserting the buffer module is imported/called only when expected).

- [ ] **Step 4: Implement the redirect in `TickerMessage.draw`**

Immediately after the animation slice resolves (`visible_text` assigned, ~line 188), capture the rotation:

```python
        rotation = getattr(anim_frame, "rotation", 0.0) if self.animation is not None else 0.0
```

After `start_pos` is captured (~line 213) and the border painted (~line 227), gate the text branches:

```python
        # Rotation seam (propeller spec): non-zero rotation redirects the
        # text branches into an owned PixelBuffer, then inverse-rotate-
        # blits around the text block's center. The border above stays
        # unrotated on purpose (it frames the panel, not the text).
        # LOAD-BEARING guard: a HiresFont renders real-pixel-sized glyphs
        # — routed into a logical buffer it produces garbage, so hires
        # fonts draw unrotated (validate rule 63 surfaces this at config
        # time; the log line covers hand-built widgets).
        rotate_target = None
        if rotation % 360 != 0:
            if isinstance(self.font, HiresFont):
                if not self._warned_hires_rotation:
                    logging.warning(
                        "%s: rotation animation ignored — hires fonts "
                        "cannot rotate until physical-resolution rotation "
                        "ships; switch to a BDF font to spin this widget",
                        type(self).__name__,
                    )
                    self._warned_hires_rotation = True
            else:
                rotate_target = PixelBuffer(canvas.width, canvas.height)

        draw_canvas = rotate_target if rotate_target is not None else canvas
```

Then: every canvas reference INSIDE the three text branches (and only
those — not the border, not compute_baseline) becomes `draw_canvas`.
After the branches complete:

```python
        if rotate_target is not None:
            cx = start_pos + content_width / 2
            cy = canvas.height / 2
            rotate_blit(canvas, rotate_target, rotation, cx, cy)
```

Supporting changes: module-level `import logging` (if absent) and
`from led_ticker.fonts.hires_loader import HiresFont`,
`from led_ticker.rotate import PixelBuffer, rotate_blit` at the top of
message.py; an attrs field `_warned_hires_rotation: bool =
attrs.field(init=False, default=False)` on TickerMessage (match the
class's existing private-field style).

Baseline note: `compute_baseline` was computed against the REAL canvas
(~line 200) — keep it that way (the buffer has the same logical dims, so
the baseline is valid for the buffer draw too; do not recompute).

- [ ] **Step 5: Run to verify pass + regressions**

Run: `uv run --extra dev pytest tests/test_widgets/test_message_rotation.py tests/test_widgets/test_message.py tests/test_frames_to_rest.py -q`
Expected: all PASS.

- [ ] **Step 6: Lint, format, pyright, commit**

```bash
uv run --extra dev ruff check src/ tests/ && uv run --extra dev ruff format src/ tests/
uv run --extra dev pyright src/led_ticker/widgets/message.py
git add src/led_ticker/widgets/message.py tests/test_widgets/test_message_rotation.py
git commit -m "feat(message): rotation seam — buffer redirect + rotate_blit

Non-zero AnimationFrame.rotation routes the text branches into a
PixelBuffer and inverse-rotate-blits around the text block's center.
Border stays unrotated; hires fonts draw unrotated with a once-per-
instance warning (load-bearing guard — logical-buffer hires render is
garbage). Part of the propeller spec (PR 1 of 2)."
```

---

### Task 4: validate rules 62 + 63

**Files:**
- Modify: `src/led_ticker/validate.py` (add two checkers next to `_check_typewriter_hold` ~line 1500; wire next to its call site — grep `_check_typewriter_hold(config)`)
- Test: `tests/test_validate_rotation_rules.py` (create)

**Interfaces:**
- Consumes: `_coerce_animation` (lazy, `# noqa: PLC0415`); `Typewriter` (to EXCLUDE from rule 62 — rule 61 owns it); `_is_hires_font_name` from `led_ticker.app.coercion` (~line 717, name-only hires check); duck-typed `frames_to_rest` / `emits_rotation` on coerced animation instances; `ENGINE_TICK_MS` from `led_ticker.constants`.
- Produces: rules 62 (generic animation-duration-vs-hold) and 63 (rotation on hires font). Both best-effort: failed coercion → `continue`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_validate_rotation_rules.py`. Copy the TOML-to-tmp_path harness from `tests/test_validate_typewriter_hold.py` (it is the direct template — same builder shape, same async `validate_config` invocation, same rule-filter helper). Since flair isn't installed in core's test env, use a STUB animation registered directly into `_ANIMATION_REGISTRY` via a fixture:

```python
import pytest

from led_ticker.animations import _ANIMATION_REGISTRY, AnimationFrame


class _StubPropeller:
    """Stands in for flair's Propeller: rotation-emitting, one-shot."""

    restart_on_visit = True
    emits_rotation = True

    def __init__(self, spin_seconds: float = 1.0) -> None:
        from led_ticker.constants import ENGINE_TICK_MS

        self.total_frames = max(1, int(spin_seconds * 1000) // ENGINE_TICK_MS)

    def frame_for(self, frame, full_text, canvas_width, text_width):
        return AnimationFrame(visible_text=full_text)

    def frames_to_rest(self, frame, total_chars):
        return max(0, self.total_frames - frame)


@pytest.fixture
def stub_propeller_registered():
    _ANIMATION_REGISTRY["teststub.propeller"] = _StubPropeller
    yield
    del _ANIMATION_REGISTRY["teststub.propeller"]
```

Test behaviors (each a real test using the harness + fixture):
- Rule 62 fires: `animation = {style = "teststub.propeller", spin_seconds = 5.0}` with `hold_time = 2.0` → one rule-62 warning; message contains `~5.0` and `2.0`; severity warning.
- Rule 62 no-fire when duration ≤ hold (`spin_seconds = 1.0`, `hold_time = 3.0`).
- Rule 62 EXCLUDES Typewriter (`animation = "typewriter"` long-text short-hold → rule 61 fires, rule 62 does NOT — assert no duplicate).
- Rule 62/63 best-effort: `animation = "flair.propeller"` (NOT registered) → neither rule fires AND the run doesn't crash (the unknown-style error from widget validation owns messaging — assert some error mentions the unknown animation, matching the existing behavior).
- Rule 63 fires: stub animation (`emits_rotation = True`) + a hires font name on the widget (find a bundled hires font name via `led_ticker.fonts.list_available_hires_fonts()` — use the first entry; skip the test if the list is empty) → rule-63 warning; message contains "BDF".
- Rule 63 no-fire: same animation + default/BDF font.
- Rule 63 no-fire for Typewriter (no `emits_rotation`) + hires font.

- [ ] **Step 2: Run to verify failures**

Run: `uv run --extra dev pytest tests/test_validate_rotation_rules.py -v`
Expected: FAIL — no rule 62/63 issues produced.

- [ ] **Step 3: Implement**

Add to `src/led_ticker/validate.py`, directly after `_check_typewriter_hold` (copy its loop skeleton — including the PEP 758 `except ValueError, TypeError:` form and the widget-hold bool guard):

```python
def _check_animation_duration_hold(config: AppConfig) -> list[ValidationIssue]:
    """Rule 62: a non-Typewriter animation's run time exceeds the
    effective hold — it will be cut mid-animation.

    Generalizes rule 61's mechanism via duck-typed frames_to_rest
    (duration = frames_to_rest(0, len(text)) x ENGINE_TICK_MS). Rule 61
    keeps Typewriter (its wording is typing-specific). Best-effort: the
    animation must coerce, so this fires only when the providing plugin
    is installed — a failed coercion is skipped (the unknown-style error
    owns that messaging), mirroring the plugin-transition rules.
    """
    from led_ticker.animations import Typewriter  # noqa: PLC0415
    from led_ticker.app.coercion import _coerce_animation  # noqa: PLC0415
    from led_ticker.constants import ENGINE_TICK_MS  # noqa: PLC0415

    warnings: list[ValidationIssue] = []
    for i, section in enumerate(config.sections):
        for j, widget_cfg in enumerate(section.widgets):
            anim_raw = widget_cfg.get("animation")
            if anim_raw is None:
                continue
            try:
                anim = _coerce_animation(anim_raw)
            except ValueError, TypeError:
                continue  # unknown/invalid animation — other rules own that
            if anim is None or isinstance(anim, Typewriter):
                continue  # rule 61 owns Typewriter
            rest_fn = getattr(anim, "frames_to_rest", None)
            if rest_fn is None:
                continue
            text = str(widget_cfg.get("text", "") or "")
            if not text:
                continue
            try:
                duration = rest_fn(0, len(text)) * ENGINE_TICK_MS / 1000.0
            except Exception:
                continue  # a readiness probe must never break validate
            widget_hold = widget_cfg.get("hold_time")
            if not isinstance(widget_hold, (int, float)) or isinstance(
                widget_hold, bool
            ):
                widget_hold = 0.0
            effective_hold = max(float(section.hold_time), float(widget_hold))
            if duration <= effective_hold:
                continue
            warnings.append(
                ValidationIssue(
                    rule=62,
                    location=f"section[{i}].widget[{j}]",
                    severity="warning",
                    message=(
                        f"animation runs ~{duration:.1f}s but the "
                        f"effective hold_time is {effective_hold:.1f}s — "
                        f"it will be cut mid-animation"
                    ),
                    fix=(
                        f"Raise hold_time to at least {duration:.1f}, or "
                        "shorten the animation (fewer revolutions / lower "
                        "spin_seconds for flair.propeller)."
                    ),
                )
            )
    return warnings


def _check_rotation_hires_font(config: AppConfig) -> list[ValidationIssue]:
    """Rule 63: a rotation-emitting animation on a hires font — the spin
    silently won't apply (the widget's load-bearing guard draws the text
    unrotated). Duck-typed on the animation's `emits_rotation` class
    attribute; hires detection is the name-only check the factories
    already use. Best-effort like rule 62 (see its docstring).
    """
    from led_ticker.app.coercion import (  # noqa: PLC0415
        _coerce_animation,
        _is_hires_font_name,
    )

    warnings: list[ValidationIssue] = []
    for i, section in enumerate(config.sections):
        for j, widget_cfg in enumerate(section.widgets):
            anim_raw = widget_cfg.get("animation")
            if anim_raw is None:
                continue
            try:
                anim = _coerce_animation(anim_raw)
            except ValueError, TypeError:
                continue
            if anim is None or not getattr(anim, "emits_rotation", False):
                continue
            font_name = widget_cfg.get("font")
            if not isinstance(font_name, str) or not _is_hires_font_name(font_name):
                continue
            warnings.append(
                ValidationIssue(
                    rule=63,
                    location=f"section[{i}].widget[{j}]",
                    severity="warning",
                    message=(
                        f"rotation animation will not spin the hires font "
                        f"{font_name!r} until physical-resolution rotation "
                        "ships; the text will display normally (unrotated)"
                    ),
                    fix=(
                        "Switch this widget to a BDF font to get the spin "
                        "effect now, or drop the animation."
                    ),
                )
            )
    return warnings
```

Wire both next to the existing call (find `warnings.extend(_check_typewriter_hold(config))` and add below, same guard block):

```python
        warnings.extend(_check_animation_duration_hold(config))
        warnings.extend(_check_rotation_hires_font(config))
```

- [ ] **Step 4: Run to verify pass + validate regression**

Run: `uv run --extra dev pytest tests/test_validate_rotation_rules.py tests/test_validate_typewriter_hold.py tests/ -k "validate" -q`
Expected: all PASS.

- [ ] **Step 5: Lint, format, pyright, commit**

```bash
uv run --extra dev ruff check src/ tests/ && uv run --extra dev ruff format src/ tests/
uv run --extra dev pyright src/led_ticker/validate.py
git add src/led_ticker/validate.py tests/test_validate_rotation_rules.py
git commit -m "feat(validate): rules 62 + 63 — animation duration vs hold, rotation on hires fonts

Rule 62 generalizes the rule-61 mechanism to any frames_to_rest-bearing
animation (Typewriter excluded — 61 owns it). Rule 63 warns when a
rotation-emitting animation meets a hires font (the widget guard draws
unrotated). Both best-effort: they fire only when the animation's plugin
is installed. Part of the propeller spec (PR 1 of 2)."
```

---

### Task 5: seam docs + spec/plan ride-along

**Files:**
- Modify: `docs/site/src/content/docs/plugins/api-reference.mdx` (the FrameAwareBase/animations prose section added by #343 — extend it)
- Modify: `docs/site/src/content/docs/concepts/animations.mdx` (one seam-level sentence; the full `flair.propeller` user docs ship in the post-flair docs PR, NOT here)
- Also commit: `docs/superpowers/specs/2026-07-02-flair-spin-animation-design.md`, `docs/superpowers/plans/2026-07-02-propeller-core-seam.md`

**Steps:**

- [ ] **Step 1:** Read `docs/DOCS-STYLE.md`, then both target pages fully.
- [ ] **Step 2:** In `api-reference.mdx` (OUTSIDE the drift-guarded regions unless Task 1 already added `ENGINE_TICK_MS` inside the guarded exported-names region): document `AnimationFrame.rotation` (degrees, clockwise-positive, default 0.0 = normal path), the `emits_rotation` class marker (opt-in signal that validate rule 63 reads), and that `ENGINE_TICK_MS` is now importable.
- [ ] **Step 3:** In `animations.mdx`, add ONE sentence to the protocol/overview area: animations may also emit a per-frame `rotation` (degrees) that the message widget renders through an offscreen rotate — the first consumer is the flair plugin's propeller. Do NOT add a "Where it works" row for `flair.propeller` yet (it doesn't exist until the flair PR; the row ships in the follow-up docs PR).
- [ ] **Step 4:** Verify: `uv run --extra dev pytest tests/test_docs_plugin_api_drift.py -q && make docs-format && make docs-lint` — all green.
- [ ] **Step 5:** Commit:

```bash
git add docs/site/src/content/docs/plugins/api-reference.mdx docs/site/src/content/docs/concepts/animations.mdx docs/superpowers/specs/2026-07-02-flair-spin-animation-design.md docs/superpowers/plans/2026-07-02-propeller-core-seam.md
git commit -m "docs: rotation seam surface — AnimationFrame.rotation, emits_rotation, ENGINE_TICK_MS

Seam-level docs only; the flair.propeller user docs (Where-it-works row,
demo gif, emoji-pop callout, tuning note) ship in the post-flair docs PR.
Ships the propeller spec + core plan."
```

---

### Task 6: full-suite verification

- [ ] **Step 1:** `make test` — full suite green (meta-tripwires included).
- [ ] **Step 2:** `uv run --extra dev ruff check src/ tests/ && uv run --extra dev ruff format --check src/ tests/ && uv run --extra dev pyright src/` — clean.
- [ ] **Step 3:** Smoke: register the Task-4 stub inline in a scratch script (or reuse the test fixture) is NOT needed — instead render a visual check using a scratch TOML with `animation = "typewriter"` to confirm zero-rotation back-compat renders identically (`make render-demo`), since no rotation-emitting animation ships in core. The rotation path's visual check happens in the flair PR's gif.
- [ ] **Step 4:** Report results honestly; fix anything found and re-run.
