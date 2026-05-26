# LightbulbBorder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `LightbulbBorder` class to `src/led_ticker/borders.py` that paints discrete `N×N` bulb sprites around the panel perimeter, with three classic-marquee animation modes (chase, alternate, unison), configurable lit/unlit colors and bulb size, and an auto-1×1 fallback for smallsign-class panels.

**Architecture:** New class extending `BorderEffectBase` alongside the existing `RainbowChaseBorder` / `ColorCycleBorder` / `ConstantBorder` family. Bulb positions are a pure function of `(panel_w, panel_h, bulb_size, gap)` and cached via `@functools.cache`. Per-frame logic derives a "lit-set mask" from `frame_count // speed_frames` (the `phase`); each of the 3 modes is one formula. All painting goes through `unwrap_to_real(canvas).SetPixel` at physical resolution, same as the existing border classes. TOML surface piggybacks on the existing `border = ...` field via a new style string (`"lightbulbs"`) in `_coerce_border` in `app/coercion.py`. Validation adds 8 new rules (42-49) to `validate.py`. Docs pages get a new section and rule entries.

**Tech Stack:** Python 3.13, `functools.cache`, existing `BorderEffectBase` / `unwrap_to_real` / `_FrameAware` machinery, pytest, Astro Starlight (docs).

**Spec:** `docs/superpowers/specs/2026-05-26-lightbulb-border-design.md` on this branch (commit `28294cd`).

**Context the implementer needs (gathered during planning):**

- The `border = ...` field is coerced by `_coerce_border` at `src/led_ticker/app/coercion.py:306`. Existing patterns: shorthand string (`"rainbow"`, `"color_cycle"`), inline table (`{style = "..."}`), list (`[r,g,b]`). The dispatch `match style` block is the insertion point for the new `"lightbulbs"` style.
- `BorderEffectBase.__init_subclass__` at `borders.py:82` enforces that every subclass declares `frame_invariant` as a class attribute. If you omit it, `TypeError` at class definition time. Don't forget.
- `_perimeter_pixels(w, h, thickness)` at `borders.py:103` is the model for caching geometry. New helper `_lightbulb_positions(w, h, bulb_size, gap)` mirrors that pattern.
- All existing borders paint at PHYSICAL resolution by calling `unwrap_to_real(canvas).SetPixel(...)`. They do NOT use the wrapper's SetPixel which would block-expand by `scale`. The new class follows the same rule.
- `frame_count` comes from `widget.frame_for("border")` via `_FrameAware._effect_frames` (per-effect counter). The widget passes it to `paint()` per the protocol.
- Latest validation rule number in use is 41 (verified by `grep "rule=[0-9]+" validate.py`). New rules start at 42.
- Panel dimensions are NOT known at `_coerce_border` time. Auto bulb_size resolution happens lazily inside `LightbulbBorder.paint()` based on `unwrap_to_real(canvas).height`. The user-supplied `bulb_size` is stored as `_bulb_size_override`. Validation against panel height happens in `validate.py` where `_panel_h_real(display)` (at `validate.py:687`) is available.
- For panel-height validation, `_panel_h_real` is `display.rows * display.parallel` which is accurate even with pixel_mappers (vertical-serpentine layouts preserve panel height). Width-based validation is skipped — width is always ≥ height on sane panels, so a bulb that fits height-wise fits width-wise.

---

## File Map

| File | Status | Purpose |
| --- | --- | --- |
| `src/led_ticker/borders.py` | modify | Add `_lightbulb_positions` helper + `LightbulbBorder` class |
| `src/led_ticker/app/coercion.py` | modify | Extend `_coerce_border` to recognize `"lightbulbs"` shorthand + table form |
| `src/led_ticker/validate.py` | modify | Add rules 42-49 (bulb_size, mode, direction, chase_density, gap, advisory warnings) |
| `tests/test_borders.py` | modify | Tripwires for placement, animation modes, physical-resolution paint, auto-bulb-size |
| `tests/test_app_coerce_border.py` (verify location) | modify | Tests for the new `"lightbulbs"` coercion form |
| `tests/test_validate.py` | modify | Tests for rules 42-49 |
| `docs/site/src/content/docs/concepts/borders.mdx` | modify | New `## Lightbulbs` section + style row in the summary table |
| `docs/site/src/content/docs/pitfalls.mdx` | modify | New rule entries for 42-49 |

---

### Task 1: Add `_lightbulb_positions` placement helper

**Files:**
- Modify: `src/led_ticker/borders.py`
- Test: `tests/test_borders.py`

This task adds the cached pure function that computes the clockwise bulb-corner list. It's the geometric foundation everything else builds on.

- [ ] **Step 1: Write the failing test for bigsign 3×3 bulb count**

Append to `tests/test_borders.py` (at the bottom, before any `if __name__` guard):

```python
import pytest

from led_ticker.borders import _lightbulb_positions


class TestLightbulbPositions:
    def test_bigsign_3x3_gap3_count(self):
        """Exact bulb count for bigsign-default geometry.

        Formula: top edge has bulbs at x0 ∈ {N+gap, 2*(N+gap), ...} where
        x0 ≤ w - 2N - gap. For w=256, h=64, N=3, gap=3, stride=6:
        - Top between-corner: x0 ∈ {6, 12, ..., 246} → 41 bulbs
        - Right between-corner: y0 ∈ {6, 12, ..., 54} → 9 bulbs
        - Bottom mirrors top: 41 bulbs
        - Left mirrors right: 9 bulbs
        - 4 corners
        - Total: 4 + 41 + 9 + 41 + 9 = 104
        """
        positions = _lightbulb_positions(256, 64, bulb_size=3, gap=3)
        assert len(positions) == 104

    def test_includes_four_corners(self):
        """Corner bulbs appear in the clockwise list exactly once each."""
        positions = _lightbulb_positions(256, 64, bulb_size=3, gap=3)
        assert (0, 0) in positions
        assert (256 - 3, 0) in positions
        assert (256 - 3, 64 - 3) in positions
        assert (0, 64 - 3) in positions

    def test_clockwise_order(self):
        """First bulb is top-left, sequence walks clockwise."""
        positions = _lightbulb_positions(256, 64, bulb_size=3, gap=3)
        # First bulb is top-left corner
        assert positions[0] == (0, 0)
        # Last bulb (just before wrapping back to top-left) is on the left edge
        # going up — y decreasing, x = 0.
        assert positions[-1][0] == 0
        # The second bulb should be on the top edge (y=0)
        assert positions[1][1] == 0
        # Walk continues clockwise: top edge x increases
        top_edge = [(x, y) for x, y in positions if y == 0]
        xs = [x for x, _ in top_edge]
        assert xs == sorted(xs)

    def test_no_duplicates(self):
        """Each bulb position appears exactly once."""
        positions = _lightbulb_positions(256, 64, bulb_size=3, gap=3)
        assert len(positions) == len(set(positions))

    def test_smallsign_1x1_gap1(self):
        """1x1 bulbs on smallsign-class panel, exact count."""
        # Top: x0 ∈ {N+gap=2, ..., ≤ w-2N-gap = 157}. Largest even ≤ 157 = 156.
        # Count = (156-2)/2+1 = 78.
        # Right: y0 ∈ {2, ..., ≤ h-2N-gap = 13}. Largest even ≤ 13 = 12.
        # Count = (12-2)/2+1 = 6.
        # Total: 4 + 78 + 6 + 78 + 6 = 172.
        positions = _lightbulb_positions(160, 16, bulb_size=1, gap=1)
        assert len(positions) == 172

    def test_cached(self):
        """Repeated calls with identical args return the SAME list object."""
        a = _lightbulb_positions(256, 64, bulb_size=3, gap=3)
        b = _lightbulb_positions(256, 64, bulb_size=3, gap=3)
        assert a is b  # functools.cache returns the same object
```

- [ ] **Step 2: Run the tests, verify they fail**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_borders.py::TestLightbulbPositions -v
```
Expected: 6 failures with `ImportError: cannot import name '_lightbulb_positions'`.

- [ ] **Step 3: Implement `_lightbulb_positions`**

Open `src/led_ticker/borders.py`. After the existing `_perimeter_pixels` function (ends around line 155) and before the `RainbowChaseBorder` class, insert:

```python
@functools.cache
def _lightbulb_positions(
    width: int,
    height: int,
    bulb_size: int,
    gap: int,
) -> list[tuple[int, int]]:
    """Return the list of bulb top-left corners around the perimeter.

    Clockwise from the top-left corner. Includes the 4 corner bulbs
    exactly once each. Between-corner bulbs leave `gap` pixels of empty
    space against neighboring bulbs (including against the corner
    bulbs).

    Each bulb occupies pixels (x0..x0+N-1, y0..y0+N-1), where
    N = bulb_size. Top-left anchoring (vs. center) means bulb_size can
    be even — 2x2 has no center pixel but its top-left corner is well-
    defined.

    `width` and `height` are PHYSICAL panel dimensions — feed
    `unwrap_to_real(canvas).width / .height` when working from a
    ScaledCanvas. The function is cached so repeated calls with the
    same geometry return the same list object.
    """
    n = bulb_size
    stride = n + gap
    positions: list[tuple[int, int]] = []

    # Top-left corner
    positions.append((0, 0))
    # Top edge (between corners), left-to-right.
    # First non-corner bulb: x0 = n + gap. Last non-corner bulb: x0 <= w - 2n - gap.
    x = stride
    while x <= width - 2 * n - gap:
        positions.append((x, 0))
        x += stride
    # Top-right corner
    positions.append((width - n, 0))
    # Right edge (between corners), top-to-bottom.
    y = stride
    while y <= height - 2 * n - gap:
        positions.append((width - n, y))
        y += stride
    # Bottom-right corner
    positions.append((width - n, height - n))
    # Bottom edge (between corners), right-to-left.
    x = width - n - stride
    while x >= stride:
        positions.append((x, height - n))
        x -= stride
    # Bottom-left corner
    positions.append((0, height - n))
    # Left edge (between corners), bottom-to-top.
    y = height - n - stride
    while y >= stride:
        positions.append((0, y))
        y -= stride
    return positions
```

- [ ] **Step 4: Run the tests, verify they pass**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_borders.py::TestLightbulbPositions -v
```
Expected: 6 passed.

- [ ] **Step 5: Commit**

Re-verify pwd + branch first:
```bash
pwd
git rev-parse --abbrev-ref HEAD
```
Expected: worktree path + `feat/lightbulb-border`.

```bash
git add src/led_ticker/borders.py tests/test_borders.py
git commit -m "$(cat <<'EOF'
feat: _lightbulb_positions helper for marquee border geometry

Pure function returning the clockwise list of bulb top-left corners
around the panel perimeter. Each bulb is an NxN sprite anchored by
its top-left, occupying (x0..x0+N-1, y0..y0+N-1). Cached via
functools.cache so repeated calls with the same (w, h, bulb_size,
gap) return the same list object. Tripwires assert the exact bulb
count for bigsign (256x64, 3x3, gap=3) -> 104 bulbs and smallsign
(160x16, 1x1, gap=1) -> 172 bulbs.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Add `LightbulbBorder` class with chase mode

**Files:**
- Modify: `src/led_ticker/borders.py`
- Test: `tests/test_borders.py`

This task adds the class shell, the `paint()` method, and the chase mode. Alternate and unison modes follow in Task 3.

- [ ] **Step 1: Write the failing tests for class shape + chase mode**

Append to `tests/test_borders.py`:

```python
from led_ticker.borders import LightbulbBorder


class _FakeRealCanvas:
    """Minimal stub: just records SetPixel calls."""
    def __init__(self, w, h):
        self.width = w
        self.height = h
        self.pixels: dict[tuple[int, int], tuple[int, int, int]] = {}

    def SetPixel(self, x, y, r, g, b):
        self.pixels[(x, y)] = (r, g, b)


class TestLightbulbBorderConstruction:
    def test_class_attrs(self):
        """frame_invariant=False (animates), restart_on_visit=False (continuous)."""
        b = LightbulbBorder(mode="chase")
        assert b.frame_invariant is False
        # restart_on_visit is a CLASS attribute
        assert LightbulbBorder.restart_on_visit is False

    def test_defaults(self):
        """Default mode='chase', gap=3, sensible defaults for everything else."""
        b = LightbulbBorder(mode="chase")
        assert b.mode == "chase"
        assert b.gap == 3
        assert b.lit_color == (255, 220, 140)
        assert b.unlit_color == (40, 20, 0)
        assert b.direction == "cw"
        assert b.chase_density == 3

    def test_mode_dependent_speed_default_chase(self):
        """Default speed_frames=2 for chase."""
        b = LightbulbBorder(mode="chase")
        assert b.speed_frames == 2

    def test_explicit_speed_frames_overrides_default(self):
        b = LightbulbBorder(mode="chase", speed_frames=10)
        assert b.speed_frames == 10


class TestLightbulbBorderChase:
    def test_paints_lit_and_unlit_colors(self):
        """At frame=0 with chase_density=3, every 3rd bulb is lit;
        the rest get unlit_color."""
        canvas = _FakeRealCanvas(256, 64)
        b = LightbulbBorder(
            mode="chase", chase_density=3, lit_color=(255, 0, 0),
            unlit_color=(10, 0, 0), bulb_size=3, gap=3,
        )
        b.paint(canvas, frame_count=0)
        # Every pixel of the canvas perimeter region got SOME color
        # (either lit_color or unlit_color). Sample: pixel (0,0) is
        # part of the top-left corner bulb (idx=0); idx % 3 == 0 so lit.
        assert canvas.pixels[(0, 0)] == (255, 0, 0)
        # Idx 1 (next clockwise) is on the top edge — unlit (1 % 3 != 0).
        # Find its position: second bulb in the list at gap+N from top-left = 6.
        assert canvas.pixels[(6, 0)] == (10, 0, 0)

    def test_chase_advances_clockwise(self):
        """Frame=speed_frames vs frame=0: lit set rotated by 1 bulb cw."""
        canvas_0 = _FakeRealCanvas(256, 64)
        canvas_1 = _FakeRealCanvas(256, 64)
        b = LightbulbBorder(
            mode="chase", chase_density=3, speed_frames=2,
            lit_color=(255, 0, 0), unlit_color=(0, 0, 0),
            bulb_size=3, gap=3,
        )
        b.paint(canvas_0, frame_count=0)
        b.paint(canvas_1, frame_count=2)
        # Bulb idx 0 (top-left corner at (0,0)) is lit at frame=0,
        # unlit at frame=speed_frames (step advanced by 1, so
        # (0 - 1) % 3 != 0).
        assert canvas_0.pixels[(0, 0)] == (255, 0, 0)
        assert canvas_1.pixels[(0, 0)] == (0, 0, 0)
        # Bulb idx 1 (top edge x=6) was unlit at frame=0, becomes lit at
        # frame=speed_frames: (1 - 1) % 3 == 0.
        assert canvas_0.pixels[(6, 0)] == (0, 0, 0)
        assert canvas_1.pixels[(6, 0)] == (255, 0, 0)

    def test_chase_ccw_reverses(self):
        """direction='ccw' rotates the opposite way."""
        canvas_cw = _FakeRealCanvas(256, 64)
        canvas_ccw = _FakeRealCanvas(256, 64)
        b_cw = LightbulbBorder(
            mode="chase", direction="cw", chase_density=3, speed_frames=2,
            lit_color=(255, 0, 0), unlit_color=(0, 0, 0),
            bulb_size=3, gap=3,
        )
        b_ccw = LightbulbBorder(
            mode="chase", direction="ccw", chase_density=3, speed_frames=2,
            lit_color=(255, 0, 0), unlit_color=(0, 0, 0),
            bulb_size=3, gap=3,
        )
        b_cw.paint(canvas_cw, frame_count=2)
        b_ccw.paint(canvas_ccw, frame_count=2)
        # At frame=2 in cw: step=1, so bulb 0 unlit ((0-1)%3=2), bulb 1 lit.
        # At frame=2 in ccw: step=-1, so bulb 0 lit ((0+1)%3=1, not 0)
        # Wait — let me recompute. (0 - (-1)) % 3 = 1. So bulb 0 unlit in ccw too.
        # Better check: bulb 2 (idx=2). cw: (2-1)%3=1, unlit. ccw: (2+1)%3=0, lit.
        bulb_2_pos = (12, 0)  # third bulb on top edge, x=2*stride=12
        assert canvas_cw.pixels[bulb_2_pos] == (0, 0, 0)
        assert canvas_ccw.pixels[bulb_2_pos] == (255, 0, 0)

    def test_bulb_size_paints_NxN_block(self):
        """A 3x3 bulb covers all 9 pixels of its NxN square."""
        canvas = _FakeRealCanvas(256, 64)
        b = LightbulbBorder(
            mode="chase", chase_density=1,  # all lit
            lit_color=(123, 45, 67), unlit_color=(0, 0, 0),
            bulb_size=3, gap=3,
        )
        b.paint(canvas, frame_count=0)
        # Top-left corner bulb at (0,0) lit; should fill (0..2, 0..2).
        for dy in range(3):
            for dx in range(3):
                assert canvas.pixels[(dx, dy)] == (123, 45, 67), \
                    f"bulb pixel ({dx},{dy}) not painted lit"
```

- [ ] **Step 2: Run the tests, verify they fail**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_borders.py::TestLightbulbBorderConstruction tests/test_borders.py::TestLightbulbBorderChase -v
```
Expected: All fail with `ImportError: cannot import name 'LightbulbBorder'`.

- [ ] **Step 3: Implement the class with chase mode only**

In `src/led_ticker/borders.py`, append after the `ConstantBorder` class:

```python
class LightbulbBorder(BorderEffectBase):
    """Marquee-style border: discrete bulb sprites around the perimeter.

    Each bulb is an NxN sprite (default 3x3 on big panels, auto-falls
    back to 1x1 on small panels). Bulbs are evenly spaced around the
    perimeter and animate via three modes:

    - "chase": every Nth bulb is lit, the lit set walks around the
      perimeter (clockwise by default). Classic marquee.
    - "alternate": even/odd bulbs flip on each phase. Looks like a
      shimmering twinkle.
    - "unison": all bulbs blink on/off in unison. Vegas attention.

    All modes paint BOTH lit and unlit colors per frame — there's no
    expectation that "off" pixels are black. Default lit_color is a
    warm white; default unlit_color is a dim warm orange that mimics
    the soft glow of unpowered incandescent bulbs.

    Paints at PHYSICAL resolution via `unwrap_to_real` — bypasses
    ScaledCanvas block expansion.
    """

    frame_invariant: bool = False
    restart_on_visit: bool = False

    def __init__(
        self,
        *,
        mode: str = "chase",
        bulb_size: int | None = None,
        gap: int = 3,
        lit_color: tuple[int, int, int] = (255, 220, 140),
        unlit_color: tuple[int, int, int] = (40, 20, 0),
        speed_frames: int | None = None,
        chase_density: int = 3,
        direction: str = "cw",
    ) -> None:
        self.mode = mode
        # bulb_size=None means "auto-detect on first paint". Resolution
        # is lazy because panel height isn't known at construction
        # time (the border is built during config-load before any
        # canvas exists).
        self._bulb_size_override = bulb_size
        self.gap = gap
        self.lit_color = lit_color
        self.unlit_color = unlit_color
        # Per-mode default speed_frames. Picked for a 50ms engine tick:
        #   chase=2     -> 100ms/step,  ~10s/rev on 100-bulb bigsign
        #   alternate=5 -> 250ms/toggle
        #   unison=8    -> 400ms/blink
        if speed_frames is None:
            speed_frames = {"chase": 2, "alternate": 5, "unison": 8}.get(mode, 2)
        self.speed_frames = speed_frames
        self.chase_density = chase_density
        self.direction = direction

    def _resolve_bulb_size(self, real_height: int) -> int:
        if self._bulb_size_override is not None:
            return self._bulb_size_override
        # Auto-fallback: small panels (smallsign) get 1x1; everything
        # else gets 3x3. Threshold of 32 cleanly separates the two
        # reference builds (bigsign h=64, smallsign h=16).
        return 3 if real_height >= 32 else 1

    def paint(self, canvas: Canvas, frame_count: int) -> None:
        real = unwrap_to_real(canvas)
        bulb_size = self._resolve_bulb_size(real.height)
        positions = _lightbulb_positions(
            real.width, real.height, bulb_size, self.gap
        )
        phase = frame_count // self.speed_frames

        if self.mode == "chase":
            step = phase if self.direction == "cw" else -phase
            for idx, (x0, y0) in enumerate(positions):
                is_lit = ((idx - step) % self.chase_density) == 0
                rgb = self.lit_color if is_lit else self.unlit_color
                self._paint_bulb(real, x0, y0, bulb_size, rgb)
        elif self.mode == "alternate":
            flip = phase % 2
            for idx, (x0, y0) in enumerate(positions):
                is_lit = ((idx + flip) % 2) == 0
                rgb = self.lit_color if is_lit else self.unlit_color
                self._paint_bulb(real, x0, y0, bulb_size, rgb)
        elif self.mode == "unison":
            rgb = self.lit_color if (phase % 2) == 0 else self.unlit_color
            for x0, y0 in positions:
                self._paint_bulb(real, x0, y0, bulb_size, rgb)
        else:
            raise ValueError(
                f"LightbulbBorder.mode must be 'chase', 'alternate', or "
                f"'unison'; got {self.mode!r}"
            )

    @staticmethod
    def _paint_bulb(
        real: Any,
        x0: int,
        y0: int,
        size: int,
        rgb: tuple[int, int, int],
    ) -> None:
        r, g, b = rgb
        for dy in range(size):
            for dx in range(size):
                real.SetPixel(x0 + dx, y0 + dy, r, g, b)
```

- [ ] **Step 4: Run the chase tests, verify they pass**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_borders.py::TestLightbulbBorderConstruction tests/test_borders.py::TestLightbulbBorderChase -v
```
Expected: All pass.

- [ ] **Step 5: Run the full borders test suite to confirm no regression**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_borders.py -v 2>&1 | tail -20
```
Expected: All existing tests still pass; new ones pass.

- [ ] **Step 6: Commit**

Re-verify pwd + branch first.

```bash
git add src/led_ticker/borders.py tests/test_borders.py
git commit -m "$(cat <<'EOF'
feat: LightbulbBorder class with chase mode

Discrete NxN bulb sprites around the panel perimeter; chase mode
animates a traveling-light pattern clockwise (or ccw) by rotating
which bulbs are lit. Both lit_color and unlit_color are painted per
frame so "off" bulbs glow dimly like physical incandescents. Paints
at physical resolution via unwrap_to_real. Default 3x3 bulbs with
1x1 auto-fallback on panels shorter than 32 physical pixels.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Tripwires for alternate and unison modes + physical-resolution paint + auto bulb_size

The class already supports all 3 modes (Task 2 implemented them). This task adds the missing tripwires.

**Files:**
- Test: `tests/test_borders.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_borders.py`:

```python
from led_ticker.scaled_canvas import ScaledCanvas


class TestLightbulbBorderAlternate:
    def test_complementary_toggle(self):
        """frame=0 and frame=speed_frames produce complementary lit-sets
        (every bulb is in exactly one of the two)."""
        canvas_0 = _FakeRealCanvas(256, 64)
        canvas_1 = _FakeRealCanvas(256, 64)
        b = LightbulbBorder(
            mode="alternate", speed_frames=5,
            lit_color=(255, 0, 0), unlit_color=(0, 0, 0),
            bulb_size=3, gap=3,
        )
        b.paint(canvas_0, frame_count=0)
        b.paint(canvas_1, frame_count=5)
        # Bulb idx 0 lit at frame=0 (0+0)%2=0; unlit at frame=5 (0+1)%2=1.
        assert canvas_0.pixels[(0, 0)] == (255, 0, 0)
        assert canvas_1.pixels[(0, 0)] == (0, 0, 0)
        # Bulb idx 1 unlit at frame=0 (1+0)%2=1; lit at frame=5 (1+1)%2=0.
        assert canvas_0.pixels[(6, 0)] == (0, 0, 0)
        assert canvas_1.pixels[(6, 0)] == (255, 0, 0)


class TestLightbulbBorderUnison:
    def test_all_lit_then_all_unlit(self):
        """frame=0 paints lit; frame=speed_frames paints unlit; all bulbs
        share state."""
        canvas_lit = _FakeRealCanvas(256, 64)
        canvas_dark = _FakeRealCanvas(256, 64)
        b = LightbulbBorder(
            mode="unison", speed_frames=8,
            lit_color=(255, 0, 0), unlit_color=(20, 0, 0),
            bulb_size=3, gap=3,
        )
        b.paint(canvas_lit, frame_count=0)
        b.paint(canvas_dark, frame_count=8)
        # Sample multiple bulb positions: all should be lit at frame=0.
        for pos in [(0, 0), (6, 0), (256 - 3, 0), (0, 64 - 3)]:
            assert canvas_lit.pixels[pos] == (255, 0, 0), \
                f"bulb at {pos} not lit at frame=0"
            assert canvas_dark.pixels[pos] == (20, 0, 0), \
                f"bulb at {pos} not unlit at frame=8"


class TestLightbulbAutoBulbSize:
    def test_bigsign_auto_3x3(self):
        """No bulb_size override on a 64-tall panel → 3x3 bulbs."""
        canvas = _FakeRealCanvas(256, 64)
        b = LightbulbBorder(mode="chase", lit_color=(1, 1, 1), unlit_color=(0, 0, 0))
        b.paint(canvas, frame_count=0)
        # Top-left corner bulb is 3x3 → pixel (2, 2) painted with the
        # corner bulb's color (idx=0, chase_density=3 → lit).
        assert (2, 2) in canvas.pixels

    def test_smallsign_auto_1x1(self):
        """No bulb_size override on a 16-tall panel → 1x1 bulbs."""
        canvas = _FakeRealCanvas(160, 16)
        b = LightbulbBorder(mode="chase", lit_color=(1, 1, 1), unlit_color=(0, 0, 0))
        b.paint(canvas, frame_count=0)
        # 1x1 means each bulb is a single pixel. Top-left corner is (0,0)
        # painted; pixel (1, 1) should NOT have been touched.
        assert (0, 0) in canvas.pixels
        assert (1, 1) not in canvas.pixels


class TestLightbulbPhysicalResolution:
    def test_paints_through_unwrap_to_real(self):
        """When given a ScaledCanvas, paint() targets the real canvas
        underneath (1-pixel sprites, not block-expanded)."""
        # Build a ScaledCanvas wrapping a fake real canvas; verify
        # SetPixel calls land on .real, not the wrapper.
        real = _FakeRealCanvas(256, 64)
        # Mimic ScaledCanvas's expected interface: .real attribute and
        # .width/.height for the logical canvas.
        wrapped = ScaledCanvas(real, scale=4, y_offset_real=0)
        b = LightbulbBorder(
            mode="unison", speed_frames=1,
            lit_color=(255, 0, 0), unlit_color=(0, 0, 0),
            bulb_size=1, gap=1,
        )
        b.paint(wrapped, frame_count=0)
        # Real canvas pixels should be set at physical positions, NOT
        # at logical positions * scale.
        assert (0, 0) in real.pixels
        # If paint had used wrapped.SetPixel, it would have block-
        # expanded the 1x1 bulb to a 4x4 region, painting (0..3, 0..3).
        # In physical-resolution mode only (0, 0) gets painted from
        # that one bulb.
        # Note: more bulbs are also at physical-pixel level along the
        # perimeter, but (1, 1) should NOT be painted (inside the
        # rectangle, not on the perimeter).
        assert (1, 1) not in real.pixels
```

- [ ] **Step 2: Run the tests, verify they pass**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_borders.py::TestLightbulbBorderAlternate tests/test_borders.py::TestLightbulbBorderUnison tests/test_borders.py::TestLightbulbAutoBulbSize tests/test_borders.py::TestLightbulbPhysicalResolution -v
```
Expected: All pass — Task 2's implementation already supports these modes; this task is just locking them in with tripwires.

If a test fails, investigate before touching the implementation: it might mean the bulb positions are different than the test assumes (e.g. if gap defaults change, the test position (6, 0) for "second top-edge bulb" would need updating).

- [ ] **Step 3: Commit**

Re-verify pwd + branch first.

```bash
git add tests/test_borders.py
git commit -m "$(cat <<'EOF'
test: LightbulbBorder tripwires for alternate, unison, auto-size,
and physical-resolution paint

Locks in the remaining behaviors: alternate mode produces a
complementary lit-set on toggle; unison mode blinks all bulbs in
unison; bulb_size=None auto-resolves to 3 on tall panels and 1 on
short panels; paint() targets unwrap_to_real(canvas) so ScaledCanvas
wrappers don't block-expand the sprites.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Extend `_coerce_border` for the `"lightbulbs"` style

**Files:**
- Modify: `src/led_ticker/app/coercion.py`
- Test: search for the existing border-coercion tests with `grep "_coerce_border\|coerce_border" tests/`; the existing tests are the model for the new ones. Most likely location: `tests/test_app_coerce_border.py` or `tests/test_app_coercion.py` — add the new tests in the same file.

- [ ] **Step 1: Find the existing border-coercion test file**

```bash
grep -l "coerce_border\|_coerce_border" tests/
```

Note which file holds the existing tests (e.g. `tests/test_app_coerce_border.py`). The new tests go in the same file. If no such file exists, create `tests/test_app_coerce_border_lightbulbs.py`.

- [ ] **Step 2: Write the failing tests**

Append to the file identified in Step 1 (substitute the actual path):

```python
import pytest

from led_ticker.app.coercion import _coerce_border
from led_ticker.borders import LightbulbBorder


class TestCoerceLightbulbsShorthand:
    def test_string_shorthand(self):
        """border = "lightbulbs" → LightbulbBorder with defaults."""
        result = _coerce_border("lightbulbs")
        assert isinstance(result, LightbulbBorder)
        assert result.mode == "chase"
        assert result._bulb_size_override is None
        assert result.gap == 3


class TestCoerceLightbulbsTable:
    def test_minimal_table(self):
        """border = {style="lightbulbs"} → LightbulbBorder with defaults."""
        result = _coerce_border({"style": "lightbulbs"})
        assert isinstance(result, LightbulbBorder)
        assert result.mode == "chase"

    def test_full_table(self):
        """All knobs round-trip through coercion."""
        result = _coerce_border({
            "style": "lightbulbs",
            "mode": "alternate",
            "bulb_size": 2,
            "gap": 4,
            "lit_color": [200, 100, 50],
            "unlit_color": [10, 5, 0],
            "speed_frames": 6,
            "chase_density": 2,
            "direction": "ccw",
        })
        assert isinstance(result, LightbulbBorder)
        assert result.mode == "alternate"
        assert result._bulb_size_override == 2
        assert result.gap == 4
        assert result.lit_color == (200, 100, 50)
        assert result.unlit_color == (10, 5, 0)
        assert result.speed_frames == 6
        assert result.chase_density == 2
        assert result.direction == "ccw"

    def test_rejects_unknown_key(self):
        with pytest.raises(ValueError, match="unknown keys"):
            _coerce_border({
                "style": "lightbulbs",
                "mode": "chase",
                "wattage": 60,  # not a real field
            })

    def test_rgb_validation_lit_color(self):
        """lit_color = [r,g,b] must pass _validate_rgb."""
        with pytest.raises(ValueError):
            _coerce_border({
                "style": "lightbulbs",
                "lit_color": [300, 0, 0],  # > 255
            })

    def test_rgb_validation_unlit_color(self):
        with pytest.raises(ValueError):
            _coerce_border({
                "style": "lightbulbs",
                "unlit_color": [-1, 0, 0],
            })
```

- [ ] **Step 3: Run the tests, verify they fail**

```bash
PYTHONPATH=tests/stubs uv run pytest <test-file-from-step-1> -v -k lightbulb
```
Expected: failures with `ValueError: unknown border style 'lightbulbs'` (or similar from the existing `case _` fallback).

- [ ] **Step 4: Extend `_coerce_border`**

Open `src/led_ticker/app/coercion.py`. Two edits.

Edit 1 — the import line at the top of `_coerce_border` (currently line 324). Replace:
```python
    from led_ticker.borders import ColorCycleBorder, ConstantBorder, RainbowChaseBorder
```
With:
```python
    from led_ticker.borders import (
        ColorCycleBorder, ConstantBorder, LightbulbBorder, RainbowChaseBorder,
    )
```

Edit 2 — string-shorthand match block (currently the `match value:` around line 339). Add a `"lightbulbs"` case before the existing fallback `case _:`. The block becomes:
```python
        match value:
            case "rainbow":
                return RainbowChaseBorder()
            case "color_cycle":
                return ColorCycleBorder()
            case "lightbulbs":
                return LightbulbBorder()
            case _:
                raise ValueError(
                    f"unknown border style {value!r}; "
                    "available: 'rainbow', 'color_cycle', 'lightbulbs', "
                    "or use an inline table"
                )
```

Edit 3 — inline-table style match block. Add a new `case "lightbulbs":` before the existing fallback `case _:` (which is around line 439). Insert:
```python
            case "lightbulbs":
                allowed = {
                    "mode", "bulb_size", "gap",
                    "lit_color", "unlit_color",
                    "speed_frames", "chase_density", "direction",
                }
                unknown = set(kwargs.keys()) - allowed
                if unknown:
                    raise ValueError(
                        f"border style 'lightbulbs' got unknown keys "
                        f"{sorted(unknown)!r}; allowed: {sorted(allowed)}"
                    )
                # Coerce RGB-list color fields to tuples; _validate_rgb
                # rejects out-of-range / wrong-shape values.
                if "lit_color" in kwargs:
                    kwargs["lit_color"] = tuple(_validate_rgb(
                        kwargs["lit_color"], "border lightbulbs lit_color"
                    ))
                if "unlit_color" in kwargs:
                    kwargs["unlit_color"] = tuple(_validate_rgb(
                        kwargs["unlit_color"], "border lightbulbs unlit_color"
                    ))
                return LightbulbBorder(**kwargs)
```

Edit 4 — the fallback message in the inline-table match block (currently line 442). Update to include `lightbulbs`:
```python
            case _:
                raise ValueError(
                    f"unknown border style {style!r}; "
                    "available: 'rainbow', 'constant', 'color_cycle', 'lightbulbs'"
                )
```

Note: type-of-value checks (e.g. `bulb_size` is positive int, `mode` ∈ `{chase, alternate, unison}`) are NOT enforced here. They land in `validate.py` rules 42-49 in Task 5. The class constructor accepts anything that's structurally valid; validate.py does the value-range checks.

- [ ] **Step 5: Run the tests, verify they pass**

```bash
PYTHONPATH=tests/stubs uv run pytest <test-file-from-step-1> -v -k lightbulb
```
Expected: All pass.

- [ ] **Step 6: Run the full coercion test suite to confirm no regression**

```bash
PYTHONPATH=tests/stubs uv run pytest <test-file-from-step-1> -v 2>&1 | tail -10
```
Expected: All existing tests still pass.

- [ ] **Step 7: Commit**

Re-verify pwd + branch first.

```bash
git add src/led_ticker/app/coercion.py <test-file-from-step-1>
git commit -m "$(cat <<'EOF'
feat: _coerce_border recognizes 'lightbulbs' style

Both the string shorthand (border = "lightbulbs") and the inline-
table form (border = {style="lightbulbs", mode="chase", ...}) are
supported. RGB fields go through _validate_rgb. Unknown keys are
rejected with the standard message. Value-range checks (mode in
{chase, alternate, unison}, etc.) land in validate.py rules 42-49.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Validation rules 42-49

**Files:**
- Modify: `src/led_ticker/validate.py`
- Test: `tests/test_validate.py` (or wherever validation tests live)

This task adds 8 new rules covering value-range checks for the lightbulb style. They operate on the raw widget config (pre-coercion) so the user gets clear error messages before the coercion error fires.

The pattern matches existing validation rules — find a similar one (e.g. animation validation around `validate.py:1067` for "requires font_size") and mirror the structure.

- [ ] **Step 1: Find the right insertion point in `validate.py`**

```bash
grep -n "def _check\|def validate" src/led_ticker/validate.py | head -20
```

Look for an existing `_check_*` function that operates on widget-level config (e.g. `_check_band_layout`). The new lightbulb rules go in a new `_check_lightbulb_border` function, called from the main `validate()` entry point alongside the other widget-level checks.

- [ ] **Step 2: Write the failing tests**

Find where existing rule tests live:
```bash
grep -l "rule=41\|rule=40\|rule=39" tests/
```

Append to that file (likely `tests/test_validate.py`):

```python
class TestRule42BulbSizeNonPositive:
    def test_zero_raises(self, tmp_path):
        cfg = tmp_path / "c.toml"
        cfg.write_text("""
[display]
rows = 64
cols = 128
chain = 2

[[section]]
mode = "swap"

[[section.widget]]
type = "message"
text = "hi"
border = {style = "lightbulbs", bulb_size = 0}
""")
        result = validate_config(cfg)
        assert any(i.rule == 42 for i in result.errors)


class TestRule43BulbSizeTooLarge:
    def test_too_large_for_panel(self, tmp_path):
        cfg = tmp_path / "c.toml"
        cfg.write_text("""
[display]
rows = 16
cols = 32
chain = 5

[[section]]
mode = "swap"

[[section.widget]]
type = "message"
text = "hi"
border = {style = "lightbulbs", bulb_size = 9}
""")
        result = validate_config(cfg)
        # max allowed = 16 // 2 = 8; 9 > 8 → rule 43
        assert any(i.rule == 43 and "9" in i.message for i in result.errors)


class TestRule44UnknownMode:
    def test_unknown_mode(self, tmp_path):
        cfg = tmp_path / "c.toml"
        cfg.write_text("""
[display]
rows = 64
cols = 128

[[section]]
mode = "swap"

[[section.widget]]
type = "message"
text = "hi"
border = {style = "lightbulbs", mode = "sparkle"}
""")
        result = validate_config(cfg)
        assert any(i.rule == 44 for i in result.errors)


class TestRule45BadDirection:
    def test_bad_direction(self, tmp_path):
        cfg = tmp_path / "c.toml"
        cfg.write_text("""
[display]
rows = 64
cols = 128

[[section]]
mode = "swap"

[[section.widget]]
type = "message"
text = "hi"
border = {style = "lightbulbs", mode = "chase", direction = "diag"}
""")
        result = validate_config(cfg)
        assert any(i.rule == 45 for i in result.errors)


class TestRule46BadChaseDensity:
    def test_chase_density_zero(self, tmp_path):
        cfg = tmp_path / "c.toml"
        cfg.write_text("""
[display]
rows = 64
cols = 128

[[section]]
mode = "swap"

[[section.widget]]
type = "message"
text = "hi"
border = {style = "lightbulbs", mode = "chase", chase_density = 0}
""")
        result = validate_config(cfg)
        assert any(i.rule == 46 for i in result.errors)


class TestRule47NegativeGap:
    def test_negative_gap(self, tmp_path):
        cfg = tmp_path / "c.toml"
        cfg.write_text("""
[display]
rows = 64
cols = 128

[[section]]
mode = "swap"

[[section.widget]]
type = "message"
text = "hi"
border = {style = "lightbulbs", gap = -1}
""")
        result = validate_config(cfg)
        assert any(i.rule == 47 for i in result.errors)


class TestRule48ChaseDensityOnNonChase:
    def test_warning_on_non_chase(self, tmp_path):
        cfg = tmp_path / "c.toml"
        cfg.write_text("""
[display]
rows = 64
cols = 128

[[section]]
mode = "swap"

[[section.widget]]
type = "message"
text = "hi"
border = {style = "lightbulbs", mode = "unison", chase_density = 5}
""")
        result = validate_config(cfg)
        assert any(i.rule == 48 for i in result.warnings)


class TestRule49DirectionOnNonChase:
    def test_warning_on_non_chase(self, tmp_path):
        cfg = tmp_path / "c.toml"
        cfg.write_text("""
[display]
rows = 64
cols = 128

[[section]]
mode = "swap"

[[section.widget]]
type = "message"
text = "hi"
border = {style = "lightbulbs", mode = "alternate", direction = "ccw"}
""")
        result = validate_config(cfg)
        assert any(i.rule == 49 for i in result.warnings)
```

Note: the test entry-point function (`validate_config` here) may have a different name in the actual codebase — check what existing rule tests import and use the same name.

- [ ] **Step 3: Run the tests, verify they fail**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_validate.py -v -k "Rule4[2-9]"
```
Expected: 8 failures (rules don't exist yet).

- [ ] **Step 4: Implement `_check_lightbulb_border` in `validate.py`**

Find a good location alongside other widget-level checks (e.g. near `_check_band_layout`). Insert the new function:

```python
def _check_lightbulb_border(config: AppConfig) -> list[ValidationIssue]:
    """Rules 42-49: value-range checks for the 'lightbulbs' border style.

    These run BEFORE _coerce_border so users get clear, ruled errors
    instead of ValueError stack traces. Coercion still rejects malformed
    types (e.g. bulb_size as a string); these rules add value-range
    semantics.
    """
    issues: list[ValidationIssue] = []
    panel_h = _panel_h_real(config.display)

    valid_modes = {"chase", "alternate", "unison"}
    valid_directions = {"cw", "ccw"}

    for sec_idx, section in enumerate(config.sections):
        for w_idx, widget_cfg in enumerate(section.widgets):
            border_raw = widget_cfg.get("border")
            # Only inspect inline-table lightbulb borders; shorthand
            # string and other styles are out of scope.
            if not isinstance(border_raw, dict):
                continue
            if border_raw.get("style") != "lightbulbs":
                continue

            loc = f"section[{sec_idx}].widget[{w_idx}].border"
            mode = border_raw.get("mode", "chase")

            # Rule 42: bulb_size must be a positive int (when set).
            bulb_size = border_raw.get("bulb_size")
            if bulb_size is not None:
                if not isinstance(bulb_size, int) or isinstance(bulb_size, bool):
                    issues.append(ValidationIssue(
                        rule=42, location=loc, severity="error",
                        message=f"bulb_size must be a positive integer; "
                                f"got {type(bulb_size).__name__}",
                        fix="Set bulb_size to a positive integer, or omit "
                            "it for the panel-size auto-default.",
                    ))
                elif bulb_size <= 0:
                    issues.append(ValidationIssue(
                        rule=42, location=loc, severity="error",
                        message=f"bulb_size must be a positive integer; got {bulb_size}",
                        fix="Set bulb_size to a positive integer, or omit "
                            "it for the panel-size auto-default.",
                    ))
                else:
                    # Rule 43: bulb_size must fit the panel height.
                    max_bulb = panel_h // 2
                    if bulb_size > max_bulb:
                        issues.append(ValidationIssue(
                            rule=43, location=loc, severity="error",
                            message=f"bulb_size={bulb_size} exceeds max={max_bulb} "
                                    f"for a panel of physical height {panel_h}",
                            fix=f"Reduce bulb_size to ≤ {max_bulb}, or omit it "
                                f"to use the panel-size auto-default.",
                        ))

            # Rule 44: mode must be one of {chase, alternate, unison}.
            if mode not in valid_modes:
                issues.append(ValidationIssue(
                    rule=44, location=loc, severity="error",
                    message=f"mode={mode!r} unknown; expected one of "
                            f"{sorted(valid_modes)}",
                    fix=f"Set mode to one of {sorted(valid_modes)}.",
                ))

            # Rule 45: direction (when set) must be 'cw' or 'ccw'.
            direction = border_raw.get("direction")
            if direction is not None and direction not in valid_directions:
                issues.append(ValidationIssue(
                    rule=45, location=loc, severity="error",
                    message=f"direction={direction!r} unknown; expected 'cw' or 'ccw'",
                    fix="Set direction to 'cw' or 'ccw'.",
                ))

            # Rule 46: chase_density (when set) must be ≥ 1.
            chase_density = border_raw.get("chase_density")
            if chase_density is not None:
                if (not isinstance(chase_density, int)
                        or isinstance(chase_density, bool)
                        or chase_density < 1):
                    issues.append(ValidationIssue(
                        rule=46, location=loc, severity="error",
                        message=f"chase_density must be an integer ≥ 1; got {chase_density!r}",
                        fix="Set chase_density to a positive integer.",
                    ))

            # Rule 47: gap must be ≥ 0 (when set).
            gap = border_raw.get("gap")
            if gap is not None:
                if (not isinstance(gap, int)
                        or isinstance(gap, bool)
                        or gap < 0):
                    issues.append(ValidationIssue(
                        rule=47, location=loc, severity="error",
                        message=f"gap must be an integer ≥ 0; got {gap!r}",
                        fix="Set gap to 0 or a positive integer (bulbs would "
                            "overlap with a negative gap).",
                    ))

            # Rule 48: chase_density set on non-chase mode is ignored — warn.
            if chase_density is not None and mode in valid_modes and mode != "chase":
                issues.append(ValidationIssue(
                    rule=48, location=loc, severity="warning",
                    message=f"chase_density is only used by mode='chase'; "
                            f"ignored for mode={mode!r}",
                    fix=f"Remove chase_density, or change mode to 'chase'.",
                ))

            # Rule 49: direction set on non-chase mode is ignored — warn.
            if direction is not None and mode in valid_modes and mode != "chase":
                issues.append(ValidationIssue(
                    rule=49, location=loc, severity="warning",
                    message=f"direction is only used by mode='chase'; "
                            f"ignored for mode={mode!r}",
                    fix=f"Remove direction, or change mode to 'chase'.",
                ))

    return issues
```

Then wire it into the main `validate()` function alongside the other widget-level checks. Search for an existing `_check_*` call near the end of `validate()` and append this one:
```python
    issues.extend(_check_lightbulb_border(config))
```

- [ ] **Step 5: Run the tests, verify they pass**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_validate.py -v -k "Rule4[2-9]"
```
Expected: All 8 pass.

- [ ] **Step 6: Run the full validate test suite**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_validate.py 2>&1 | tail -10
```
Expected: All existing tests still pass.

- [ ] **Step 7: Commit**

Re-verify pwd + branch first.

```bash
git add src/led_ticker/validate.py tests/test_validate.py
git commit -m "$(cat <<'EOF'
feat: validate rules 42-49 for lightbulbs border style

Eight new rules cover value-range checks for the 'lightbulbs' border
inline-table form, running BEFORE _coerce_border so users get
rule-numbered errors instead of ValueError stack traces:

- 42: bulb_size not a positive int
- 43: bulb_size exceeds panel-height ceiling
- 44: mode not in {chase, alternate, unison}
- 45: direction not in {cw, ccw}
- 46: chase_density < 1
- 47: gap < 0
- 48 (warning): chase_density set on non-chase mode (ignored)
- 49 (warning): direction set on non-chase mode (ignored)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Docs — new section on `concepts/borders.mdx`

**Files:**
- Modify: `docs/site/src/content/docs/concepts/borders.mdx`

- [ ] **Step 1: Find the existing summary table + section structure**

Open `docs/site/src/content/docs/concepts/borders.mdx`. Note the structure: lead paragraph, summary table (`| Style | Shorthand | …`), then `### Rainbow chase`, `### Color_cycle`, `### Constant`. The new `### Lightbulbs` section goes after the existing three.

- [ ] **Step 2: Update the summary table**

Find the existing summary table. Append a row for `lightbulbs`. The table currently looks like:

```markdown
| Style         | Shorthand                | Per-pixel color?          | Animates? |
| ------------- | ------------------------ | ------------------------- | --------- |
| `rainbow`     | `border = "rainbow"`     | yes — hue chase           | yes       |
| `color_cycle` | `border = "color_cycle"` | no — whole border one hue | yes       |
| `constant`    | `border = [r,g,b]`       | no — uniform              | no        |
```

Append:
```markdown
| `lightbulbs`  | `border = "lightbulbs"`  | no — discrete bulb sprites | yes       |
```

Prettier may reformat column alignment — accept its reformat.

- [ ] **Step 3: Add the `### Lightbulbs` section**

Append at the end of the file (before any `<RelatedPages>` block — keep that at the bottom):

```mdx
## Lightbulbs

The `lightbulbs` style paints discrete NxN bulb sprites around the perimeter — the classic Vegas-marquee aesthetic. Each bulb is a fixed-size square sprite at one of ~100 (bigsign-default) clockwise-ordered positions; the animation modes flip which bulbs are "lit" vs "unlit" per frame. Both colors paint every frame, so "off" bulbs glow dimly like physical incandescent bulbs without power — the default is a warm-white lit color over a dim warm-orange unlit color.

The simplest form is the string shorthand:

<TomlExample
  code={`[[section]]
[[section.widget]]
type = "message"
text = "HELLO"
border = "lightbulbs"`}
/>

Defaults: `mode = "chase"`, `bulb_size = 3` on big panels (auto-falls back to `1` on panels shorter than 32 physical pixels), `gap = 3`, warm-white lit / dim-warm-orange unlit colors.

### Modes

- **`chase`** — every Nth bulb (default 3rd) is lit; the lit set walks clockwise (or `direction = "ccw"`) around the perimeter, advancing one bulb position every `speed_frames` engine ticks. Classic traveling-marquee look.
- **`alternate`** — even/odd bulbs flip on each phase. Half the bulbs lit at any time, switching every `speed_frames` ticks. Looks like a shimmer or twinkle without directional motion.
- **`unison`** — all bulbs share state. All lit, then all unlit, alternating every `speed_frames` ticks. Loud attention-grabber.

### Full table form

<TomlExample
  code={`border = { style = "lightbulbs",
           mode = "chase",                # "chase" | "alternate" | "unison"
           bulb_size = 3,                 # optional; auto from panel height
           gap = 3,                       # pixels between bulb edges
           lit_color = [255, 220, 140],   # warm white default
           unlit_color = [40, 20, 0],     # dim warm-orange default
           speed_frames = 2,              # frames per state transition
           chase_density = 3,             # only used by mode="chase"
           direction = "cw" }             # "cw" | "ccw", only used by mode="chase"`}
/>

`speed_frames` defaults differ by mode: `2` for chase (~100 ms per bulb step), `5` for alternate (~250 ms per toggle), `8` for unison (~400 ms per blink). Higher values slow the animation; the engine ticks at 50 ms.

### When to use each style

`lightbulbs` reads as a **physical object** (a marquee of light fixtures). `rainbow` / `color_cycle` read as a **graphical effect** (a halo or outline). Pick the former for theatrical / vintage / sports-bar / Vegas-pastiche aesthetics; pick the latter for clean / modern / decorative work.

`lightbulbs` is unconditionally animated (`frame_invariant = False`) — image-widget fast paths correctly force per-tick redraws on it, same as the other animated borders.
```

Note: the `<TomlExample>` component is already imported at the top of the file — don't re-import.

- [ ] **Step 4: Verify docs build + lint**

```bash
source "$HOME/.nvm/nvm.sh" && make docs-build && make docs-lint
```
Expected: both clean. If prettier reformats anything, accept the reformat.

- [ ] **Step 5: Commit**

Re-verify pwd + branch first.

```bash
git add docs/site/src/content/docs/concepts/borders.mdx
git commit -m "$(cat <<'EOF'
docs: lightbulbs border style on concepts/borders

Adds the lightbulbs row to the summary table and a new "## Lightbulbs"
section covering the 3 animation modes (chase / alternate / unison),
the field table, default values, and guidance on when to pick this
style vs the existing rainbow/color_cycle/constant options.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: Docs — rule entries in `pitfalls.mdx`

**Files:**
- Modify: `docs/site/src/content/docs/pitfalls.mdx`

- [ ] **Step 1: Add detailed entries for rules 42-49**

Open `docs/site/src/content/docs/pitfalls.mdx`. Find the last existing rule entry (rule 41). After it, append:

```mdx
### Rule 42 — `bulb_size` must be a positive integer

The `bulb_size` field on a `lightbulbs` border must be a positive integer (or omitted to use the panel-size auto-default).

**Fix:** Set `bulb_size = 3` (typical bigsign value) or omit the field.

### Rule 43 — `bulb_size` exceeds panel-height ceiling

A `lightbulbs` border with `bulb_size > panel_height // 2` would have its top-edge and bottom-edge bulbs overlap. Catches: `bulb_size = 9` on a smallsign-class 16-row panel (max=8).

**Fix:** Reduce `bulb_size` to ≤ `panel_height // 2`, or omit it to use the auto-default (3 on big panels, 1 on small).

### Rule 44 — `mode` must be `chase`, `alternate`, or `unison`

Typo in the `mode` field, or a mode that doesn't exist yet.

**Fix:** Set `mode` to one of `chase`, `alternate`, or `unison`.

### Rule 45 — `direction` must be `cw` or `ccw`

The `direction` field on a chase-mode lightbulbs border must be one of those two values.

**Fix:** Set `direction = "cw"` (clockwise) or `direction = "ccw"` (counter-clockwise).

### Rule 46 — `chase_density` must be an integer ≥ 1

`chase_density = N` means "1 in N bulbs is lit". Values less than 1 are nonsensical.

**Fix:** Set `chase_density` to 1 (every bulb lit), 2 (every other), 3 (every third — classic marquee), etc.

### Rule 47 — `gap` must be ≥ 0

Negative gaps would cause bulbs to overlap, producing an undefined visual.

**Fix:** Set `gap = 0` (bulbs touching) or a positive integer.

### Rule 48 — `chase_density` ignored outside chase mode (warning)

`chase_density` only affects the chase animation. Setting it on `mode = "alternate"` or `mode = "unison"` is silently ignored.

**Fix:** Either remove `chase_density`, or change `mode` to `chase`.

### Rule 49 — `direction` ignored outside chase mode (warning)

`direction` only affects the chase animation.

**Fix:** Either remove `direction`, or change `mode` to `chase`.
```

- [ ] **Step 2: Update the quick-reference table at the top of the page (if there is one)**

```bash
grep -n "Rule 41\|Rule 40\|Rule 39" docs/site/src/content/docs/pitfalls.mdx | head -5
```

If there's a summary table near the top of pitfalls.mdx listing recent rules, append rows for 42-49. Match the existing column style.

- [ ] **Step 3: Verify docs build + lint**

```bash
source "$HOME/.nvm/nvm.sh" && make docs-build && make docs-lint
```
Expected: both clean.

- [ ] **Step 4: Commit**

Re-verify pwd + branch first.

```bash
git add docs/site/src/content/docs/pitfalls.mdx
git commit -m "$(cat <<'EOF'
docs: rules 42-49 on pitfalls page (lightbulbs validation)

Entries for the 8 new validation rules: bulb_size constraints, mode/
direction/chase_density value ranges, gap ≥ 0, and the two advisory
warnings for fields ignored outside chase mode.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 8: Final verification + PR

**Files:**
- None (verification only)

- [ ] **Step 1: Full pre-push-style check**

```bash
source "$HOME/.nvm/nvm.sh"
make lint
PYTHONPATH=tests/stubs uv run pytest --tb=short
make docs-build
make docs-lint
```
Expected: all four clean.

- [ ] **Step 2: Visual integration smoke test (optional, dev-laptop)**

Create a minimal test config:
```toml
[display]
rows = 64
cols = 128
chain = 2

[[section]]
mode = "swap"

[[section.widget]]
type = "message"
text = "MARQUEE"
border = "lightbulbs"
```

Run validate to confirm the new config doesn't trigger any rule:
```bash
make validate CONFIG=<tmp-config-path>
```
Expected: zero errors, zero warnings.

- [ ] **Step 3: Push branch and open PR**

```bash
source "$HOME/.nvm/nvm.sh" && export PATH="$(dirname "$(which node)"):$PATH"
git push -u origin feat/lightbulb-border
```

The pre-push hook runs `docs-lint` which needs `node` on PATH — that's why the `export PATH=...` is in there.

Then:
```bash
gh pr create --title "feat: LightbulbBorder — marquee-style border with chase/alternate/unison modes" --body "$(cat <<'EOF'
## Summary

- New `LightbulbBorder` class in `borders.py` alongside the existing rainbow/color_cycle/constant family. Paints discrete NxN bulb sprites around the panel perimeter, with three classic-marquee animation modes: **chase** (lit set walks clockwise/ccw), **alternate** (even/odd bulbs flip), **unison** (all on / all off blink).
- Configurable `bulb_size` (default 3 on big panels, auto-1x1 fallback on panels shorter than 32 physical pixels), `gap`, `lit_color`, `unlit_color`, `speed_frames`, `chase_density`, `direction`.
- TOML surface piggybacks on the existing `border = ...` field — `border = "lightbulbs"` shorthand or `border = {style = "lightbulbs", ...}` inline table.
- 8 new validation rules (42-49) cover value-range checks for the new fields, with advisory warnings for fields ignored outside chase mode.

## Why this exists

The existing border classes all paint continuous 1- or 2-pixel rings — they read as a graphical "outline" or "halo". A lightbulb border reads as a **physical object** (a marquee of light fixtures), which is a different visual language. The bigsign's 256×64 physical resolution is large enough to make individual 3×3 bulb sprites legible, so the aesthetic is feasible.

## Test plan

- [x] `make lint` clean
- [x] `pytest` — all existing tests pass; new tripwires (bulb count, chase advance, alternate toggle, unison blink, auto-bulb-size, physical-resolution paint) pass
- [x] `make docs-build` and `make docs-lint` clean
- [x] `make validate` against a minimal `border = "lightbulbs"` config: zero errors/warnings
- [ ] **Hardware verification on bigsign** (not yet run — requires physical access):
  - [ ] All 3 modes render correctly with defaults
  - [ ] `lit_color` / `unlit_color` customization works (try red/dim-red marquee)
  - [ ] `bulb_size = 5` produces visibly chunkier bulbs
  - [ ] `direction = "ccw"` reverses the chase
  - [ ] Phase continuous across `loop_count > 1` (`restart_on_visit = False`)
  - [ ] Border disappears cleanly during widget transitions

## Spec / plan

- Spec: `docs/superpowers/specs/2026-05-26-lightbulb-border-design.md`
- Plan: `docs/superpowers/plans/2026-05-26-lightbulb-border.md`

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-Review

**1. Spec coverage:**

- LightbulbBorder class — Task 2 ✓
- 3 animation modes (chase/alternate/unison) — Task 2 (chase), Task 3 (alternate + unison tripwires; class already implements all 3 in Task 2) ✓
- Configurable bulb_size with auto-fallback — Task 2 (constructor + `_resolve_bulb_size`), Task 3 (auto-size tripwire) ✓
- Lit/unlit colors with marquee defaults — Task 2 ✓
- Direction (cw/ccw) — Task 2 (constructor + paint logic), test in Task 2 ✓
- Chase density — Task 2 ✓
- Unified speed_frames knob with per-mode defaults — Task 2 ✓
- Physical-resolution paint via unwrap_to_real — Task 2 (implemented), Task 3 (tripwire) ✓
- frame_invariant=False, restart_on_visit=False — Task 2 ✓
- TOML shorthand and inline-table coercion — Task 4 ✓
- RGB validation of lit/unlit colors — Task 4 ✓
- Validation rules 42-49 — Task 5 ✓
- Borders concept doc page — Task 6 ✓
- Pitfalls rule entries — Task 7 ✓
- Verification plan — Task 8 ✓

**2. Placeholder scan:** Some Task-5 details depend on "find the right function" in validate.py — those are bracketed by exact `grep` commands the implementer runs. No literal TBDs. Test file paths in Task 4 / Task 5 say "search for X" — that's because the test layout has multiple plausible files; the grep commands disambiguate. Acceptable per the plan template.

**3. Type consistency:**
- `LightbulbBorder.__init__` signature matches across the plan: `mode`, `bulb_size`, `gap`, `lit_color`, `unlit_color`, `speed_frames`, `chase_density`, `direction`.
- `_bulb_size_override` (private attribute) is consistent in Task 2 (set), Task 3 (asserted), Task 4 (asserted).
- `_resolve_bulb_size(real_height) -> int` matches between Task 2 (defined) and Task 3 (tripwire calls `paint` which uses it).
- `_lightbulb_positions(width, height, bulb_size, gap)` signature consistent across Task 1 (definition) and Task 2 (consumer).
- `_paint_bulb(real, x0, y0, size, rgb)` consistent.
- Rule numbers 42-49 consistent across Task 5 (assignment) and Task 7 (docs).
- `frame_invariant = False` and `restart_on_visit = False` (class attrs) consistent throughout.

All consistent. Plan ready for handoff.
