# Scroll Separator — Phase 1: behavior-preserving extraction — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract one shared separator renderer (`separator.py`) and route both the ticker-mode circle and the scroll-transition dot through it — with **zero pixel drift** and no new config.

**Architecture:** A leaf module `separator.py` defines `SeparatorSpec` (dot/circle kinds), `render_separator(canvas, x, frame, spec)`, and `separator_width(spec)`, plus the scroll geometry helpers. The ticker circle widget and the two scroll draw sites are rewired to call it; the duplicated hardcoded dot (`_draw_bullet` / inline in `Scroll`) and the circle helpers are removed from `ticker.py`. No config, no behavior change.

**Tech Stack:** Python 3.14, attrs, the rgbmatrix canvas/ScaledCanvas stubs, pytest.

## Global Constraints

- **Zero pixel drift.** Every existing ticker-separator and scroll tripwire must stay green. This is the acceptance bar for the whole phase.
- **`separator.py` is a leaf module** — it may import `_types`, `colors`, `color_providers`, `scaled_canvas`, `fonts`, `text_render`, `widgets.message`; it must **NOT** import `ticker` or `transitions` (avoids the registry cycle that forces `effects.py`'s deferred import today).
- **`render_separator` takes an explicit `frame: int`** (color provider source). Phase 1 colors are constant white, so `frame` doesn't change output yet — it's plumbed for Phase 2.
- **`separator_width(spec)` returns the mark's OWN logical width** (no padding); callers add padding (ticker `_CIRCLE_LOGICAL_PAD = 1` each side; scroll `SCROLL_GAP = 6` each side).
- **Dot stays a primitive** (size×size filled square), NOT a 1-char glyph. Circle on a plain canvas is **not** in scope for `render_separator` in Phase 1 — the widget keeps routing plain canvases to `TickerMessage`'s BDF "•".
- Repo workflow: branch `feat/configurable-scroll-separator`; never commit to `main`; `make dev` once in the worktree; `uv run --extra dev ruff check` before pushing.

---

## Prerequisite (once)

- [ ] **Worktree venv + branch check**

Run: `cd /Users/james/projects/github/jamesawesome/led-ticker-separator && make dev && git branch --show-current`
Expected: deps install; prints `feat/configurable-scroll-separator`.

---

### Task 1: `separator.py` — the shared renderer (new module, nothing rewired yet)

**Files:**
- Create: `src/led_ticker/separator.py`
- Test: `tests/test_separator.py`

**Interfaces:**
- Produces: `SeparatorSpec(kind, color, size, glyph="", font=None)`;
  `render_separator(canvas, x, frame, spec) -> int` (paints, returns mark width);
  `separator_width(spec) -> int`; `DEFAULT_DOT_SPEC`, `DEFAULT_CIRCLE_SPEC`;
  `SCROLL_GAP`, `scroll_separator_width(spec=DEFAULT_DOT_SPEC, gap=SCROLL_GAP)`;
  `_CIRCLE_LOGICAL_PAD`. Consumed by Tasks 2–3.

This task ADDS the module and proves it byte-identical against the still-present
`ticker._draw_hires_circle` / `ticker._draw_bullet`. Those originals are removed
in Tasks 2–3.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_separator.py`:

```python
"""Unit + parity tests for the shared separator renderer (Phase 1).

Parity tests compare render_separator against the still-present
ticker._draw_hires_circle / ticker._draw_bullet to prove byte-identical
output before the consumers are rewired.
"""

from unittest.mock import MagicMock

from led_ticker.colors import RGB_WHITE
from led_ticker.scaled_canvas import ScaledCanvas
from led_ticker.separator import (
    DEFAULT_CIRCLE_SPEC,
    DEFAULT_DOT_SPEC,
    SCROLL_GAP,
    SeparatorSpec,
    render_separator,
    scroll_separator_width,
    separator_width,
)


def _plain(width=160, height=16):
    c = MagicMock()
    c.width, c.height = width, height
    return c


def test_separator_width_dot_and_circle():
    assert separator_width(DEFAULT_DOT_SPEC) == 2
    assert separator_width(DEFAULT_CIRCLE_SPEC) == 8


def test_scroll_separator_width_default_is_14():
    assert scroll_separator_width(DEFAULT_DOT_SPEC) == SCROLL_GAP + 2 + SCROLL_GAP
    assert scroll_separator_width() == 14  # default dot, gap 6


def test_render_dot_paints_2x2_white_and_returns_width():
    canvas = _plain()
    width = render_separator(canvas, x=10, frame=0, spec=DEFAULT_DOT_SPEC)
    assert width == 2
    painted = {(c.args[0], c.args[1]) for c in canvas.SetPixel.call_args_list}
    # 2x2 block at x=10, rows y_center-1 and y_center (h//2 = 8)
    assert painted == {(10, 7), (11, 7), (10, 8), (11, 8)}
    for c in canvas.SetPixel.call_args_list:
        assert c.args[2:5] == (255, 255, 255)


def test_render_dot_parity_with_ticker_draw_bullet():
    """render_separator dot == the existing _draw_bullet (still present)."""
    from led_ticker.ticker import _draw_bullet

    a, b = _plain(), _plain()
    _draw_bullet(a, x=12)
    render_separator(b, x=12, frame=0, spec=DEFAULT_DOT_SPEC)
    assert a.SetPixel.call_args_list == b.SetPixel.call_args_list


def test_render_circle_parity_with_ticker_draw_hires_circle():
    """render_separator circle == the existing _draw_hires_circle (still present).

    The widget passes x = cursor_pos + _CIRCLE_LOGICAL_PAD; _draw_hires_circle
    bakes that pad into its own centering, so compare at matching x."""
    from led_ticker.separator import _CIRCLE_LOGICAL_PAD
    from led_ticker.ticker import _draw_hires_circle

    real_a = MagicMock()
    real_a.width, real_a.height = 256, 64
    canvas_a = ScaledCanvas(real_a, scale=4, content_height=16)
    real_b = MagicMock()
    real_b.width, real_b.height = 256, 64
    canvas_b = ScaledCanvas(real_b, scale=4, content_height=16)

    _draw_hires_circle(canvas_a, cursor_pos=0, color=(255, 255, 255))
    render_separator(
        canvas_b, x=0 + _CIRCLE_LOGICAL_PAD, frame=0, spec=DEFAULT_CIRCLE_SPEC
    )
    assert real_a.SetPixel.call_args_list == real_b.SetPixel.call_args_list


def test_render_circle_uses_provider_color_via_frame():
    real = MagicMock()
    real.width, real.height = 256, 64
    canvas = ScaledCanvas(real, scale=4, content_height=16)
    spec = SeparatorSpec(kind="circle", color=RGB_WHITE, size=8)
    render_separator(canvas, x=1, frame=0, spec=spec)
    assert real.SetPixel.called
```

- [ ] **Step 2: Run — expect failure**

Run: `uv run pytest tests/test_separator.py -v`
Expected: FAIL (`No module named led_ticker.separator`).

- [ ] **Step 3: Create `src/led_ticker/separator.py`**

```python
"""Shared separator rendering: one renderer for the ticker-mode circle and
the scroll-transition dot. Leaf module — must NOT import ticker/transitions.

A SeparatorSpec describes HOW a separator looks; render_separator paints it
at a logical x and returns the mark's logical width (no padding — callers add
their own). frame drives the color provider.
"""

import functools
from typing import Any

import attrs

from led_ticker._types import Canvas, ColorTuple
from led_ticker.color_providers import ColorProvider, _ConstantColor
from led_ticker.colors import RGB_WHITE
from led_ticker.scaled_canvas import ScaledCanvas, is_scaled, paint_hires

# Circle separator footprint (moved from ticker.py): 1 left pad + 8 disk + 1
# right pad = 10 logical px advance at the default size.
_CIRCLE_LOGICAL_PAD = 1
SCROLL_GAP: int = 6  # px of black on each side of the scroll dot


def _as_provider(color: Any) -> ColorProvider:
    return color if hasattr(color, "color_for") else _ConstantColor(color)


@attrs.define
class SeparatorSpec:
    kind: str  # "dot" | "circle"  (Phase 2 adds "glyph")
    color: Any = RGB_WHITE  # ColorTuple or ColorProvider; normalized on read
    size: int = 2  # dot: square side; circle: disk diameter (logical px)
    glyph: str = ""  # Phase 2
    font: Any = None  # Phase 2


# Per-site defaults reproducing today's appearance exactly.
DEFAULT_DOT_SPEC = SeparatorSpec(kind="dot", color=RGB_WHITE, size=2)
DEFAULT_CIRCLE_SPEC = SeparatorSpec(kind="circle", color=RGB_WHITE, size=8)


@functools.cache
def _build_circle_offsets(radius_physical: int) -> list[tuple[int, int]]:
    offsets: list[tuple[int, int]] = []
    r_sq = radius_physical * radius_physical
    for dy in range(-radius_physical, radius_physical + 1):
        dx_max = 0
        while (dx_max + 1) * (dx_max + 1) + dy * dy <= r_sq:
            dx_max += 1
        for dx in range(-dx_max, dx_max + 1):
            offsets.append((dx, dy))
    return offsets


def _resolve_rgb(color: Any, frame: int) -> ColorTuple:
    c = _as_provider(color).color_for(frame, 0, 1)
    if isinstance(c, tuple):
        return c
    return (c.red, c.green, c.blue)


def _render_dot(canvas: Canvas, x: int, rgb: ColorTuple, size: int) -> int:
    h = getattr(canvas, "height", 16)
    y_center = h // 2
    r, g, b = rgb
    top = -(size // 2)  # size 2 -> rows -1, 0
    for dy in range(top, size + top):
        for dx in range(size):
            px, py = x + dx, y_center + dy
            if 0 <= px < canvas.width and 0 <= py < h:
                canvas.SetPixel(px, py, r, g, b)
    return size


def _render_circle(canvas: ScaledCanvas, x: int, rgb: ColorTuple, size: int) -> int:
    radius_logical = size // 2  # size 8 -> radius 4
    r, g, b = rgb

    def _paint(real: Any, scale: int, y_offset_real: int) -> None:
        radius_physical = radius_logical * scale
        offsets = _build_circle_offsets(radius_physical)
        cx = x * scale + radius_physical
        cy = y_offset_real + (canvas.height * scale) // 2
        set_px = real.SetPixel
        for dx, dy in offsets:
            set_px(cx + dx, cy + dy, r, g, b)

    paint_hires(canvas, _paint)
    return size


def render_separator(canvas: Canvas, x: int, frame: int, spec: SeparatorSpec) -> int:
    """Paint the separator mark at logical x; return its logical width (no pad)."""
    rgb = _resolve_rgb(spec.color, frame)
    if spec.kind == "circle" and is_scaled(canvas):
        return _render_circle(canvas, x, rgb, spec.size)
    # dot (and circle on a plain canvas is handled by the widget's BDF path,
    # so it does not reach here in Phase 1)
    return _render_dot(canvas, x, rgb, spec.size)


def separator_width(spec: SeparatorSpec) -> int:
    """The mark's own logical width (no padding)."""
    return spec.size


def scroll_separator_width(
    spec: SeparatorSpec = DEFAULT_DOT_SPEC, gap: int = SCROLL_GAP
) -> int:
    """Total scroll separator width: gap + mark + gap."""
    return gap + separator_width(spec) + gap
```

- [ ] **Step 4: Run — expect pass**

Run: `uv run pytest tests/test_separator.py -v`
Expected: PASS (all 6 tests, including the two parity tests against ticker's originals).

- [ ] **Step 5: Lint + commit**

```bash
uv run --extra dev ruff check src/led_ticker/separator.py tests/test_separator.py
git add src/led_ticker/separator.py tests/test_separator.py
git commit -m "feat(separator): shared render_separator + SeparatorSpec (dot/circle), proven byte-identical"
```

---

### Task 2: Rewire the ticker circle to `render_separator`; remove the circle helpers from `ticker.py`

**Files:**
- Modify: `src/led_ticker/ticker.py` (`_CircleBufferMsg.draw`; delete `_draw_hires_circle`, `_build_circle_offsets`, `_CIRCLE_LOGICAL_PAD/RADIUS/ADVANCE`)
- Modify: `tests/test_ticker.py` (migrate the patch-target tripwire)

**Interfaces:**
- Consumes: `render_separator`, `DEFAULT_CIRCLE_SPEC`, `SeparatorSpec`, `_CIRCLE_LOGICAL_PAD` from `separator.py`.

- [ ] **Step 0: Remove the now-obsolete circle parity test**

Task 1's `test_render_circle_parity_with_ticker_draw_hires_circle` imports
`ticker._draw_hires_circle`, which this task deletes. It has served its purpose
(byte-identity is proven; the widget tripwires below now guard behavior). Delete
that one test function from `tests/test_separator.py`.

- [ ] **Step 1: Migrate the smallsign-delegation tripwire**

In `tests/test_ticker.py`, `test_circle_buffer_msg_smallsign_delegates_to_super_draw`
patches `led_ticker.ticker._draw_hires_circle`, which is being removed. Repoint it
at the new seam — the widget must NOT call `render_separator` on a plain canvas:

```python
    # Verify the hi-res renderer is NOT called on the smallsign path
    with patch("led_ticker.ticker.render_separator") as mock_render:
        out, cursor = msg.draw(plain_canvas, cursor_pos=0)
        assert not mock_render.called, (
            "smallsign path must delegate to super().draw(), "
            "not call render_separator"
        )
```

- [ ] **Step 2: Run — expect failure**

Run: `uv run pytest tests/test_ticker.py::test_circle_buffer_msg_smallsign_delegates_to_super_draw -v`
Expected: FAIL (`led_ticker.ticker` has no attribute `render_separator` yet).

- [ ] **Step 3: Rewire `_CircleBufferMsg.draw` and delete the moved helpers**

In `ticker.py`: add `from led_ticker.separator import (DEFAULT_CIRCLE_SPEC, render_separator, _CIRCLE_LOGICAL_PAD)` to the imports. Replace `_CircleBufferMsg.draw`'s scaled branch:

```python
        if is_scaled(canvas):
            advance = render_separator(
                canvas,
                cursor_pos + _CIRCLE_LOGICAL_PAD,
                self.frame_for("font_color"),
                attrs.evolve(DEFAULT_CIRCLE_SPEC, color=self.font_color),
            )
            return canvas, cursor_pos + _CIRCLE_LOGICAL_PAD + advance + _CIRCLE_LOGICAL_PAD
        return super().draw(
            canvas, cursor_pos, y_offset=y_offset, font_color=font_color
        )
```

Then DELETE from `ticker.py`: `_draw_hires_circle`, `_build_circle_offsets`, and the
constants `_CIRCLE_LOGICAL_PAD` / `_CIRCLE_LOGICAL_RADIUS` / `_CIRCLE_LOGICAL_ADVANCE`
(now in `separator.py`; `_CIRCLE_LOGICAL_PAD` is imported). Run
`grep -n '_draw_hires_circle\|_build_circle_offsets\|_CIRCLE_LOGICAL_RADIUS\|_CIRCLE_LOGICAL_ADVANCE' src/led_ticker/ticker.py`
and fix any remaining references (there should be none after the delete).

- [ ] **Step 4: Run the circle tripwires — expect pass**

Run: `uv run pytest tests/test_ticker.py -k "circle_buffer_msg or default_buffer_msg" -v`
Expected: PASS — `cursor == 10` (advance preserved), rainbow animates, smallsign delegates, default is circle.

- [ ] **Step 5: Lint + commit**

```bash
uv run --extra dev ruff check src/led_ticker/ticker.py tests/test_ticker.py
git add src/led_ticker/ticker.py tests/test_ticker.py
git commit -m "refactor(ticker): route the circle separator through render_separator"
```

---

### Task 3: Rewire the scroll dot; remove `_draw_bullet`/`BULLET_*` from `ticker.py`

**Files:**
- Modify: `src/led_ticker/ticker.py` (`_draw_scroll_frame`; delete `_draw_bullet`, `BULLET_WIDTH`, `BULLET_COLOR`, `SCROLL_GAP`, `scroll_separator_width`; import them from `separator.py`)
- Modify: `src/led_ticker/transitions/effects.py` (`Scroll` consumes the spec via `render_separator`)
- Modify: `tests/test_transitions.py` (migrate `test_separator_width`)

**Interfaces:**
- Consumes: `render_separator`, `separator_width`, `scroll_separator_width`, `SCROLL_GAP`, `DEFAULT_DOT_SPEC` from `separator.py`.

- [ ] **Step 0: Remove the now-obsolete dot parity test**

Task 1's `test_render_dot_parity_with_ticker_draw_bullet` imports `ticker._draw_bullet`,
which this task deletes. Delete that one test function from `tests/test_separator.py`
(byte-identity is proven; the scroll tripwires now guard behavior).

- [ ] **Step 1: Migrate the scroll separator-width tripwire**

In `tests/test_transitions.py`, `test_separator_width` imports `BULLET_WIDTH` (being
removed). Replace its body:

```python
    def test_separator_width(self):
        """Separator should be gap + mark + gap."""
        from led_ticker.separator import (
            DEFAULT_DOT_SPEC,
            SCROLL_GAP,
            scroll_separator_width,
        )

        scroll = Scroll()
        expected = SCROLL_GAP + 2 + SCROLL_GAP  # default dot mark width = 2
        assert scroll._sep_w == expected
        assert scroll._sep_w == scroll_separator_width(DEFAULT_DOT_SPEC)
```

- [ ] **Step 2: Run — expect failure**

Run: `uv run pytest tests/test_transitions.py::TestScroll::test_separator_width -v`
Expected: FAIL (`cannot import name DEFAULT_DOT_SPEC` is not it — it exists; the
failure is that `Scroll` still imports the old `scroll_separator_width()` and
`BULLET_WIDTH` path). If it errors on the OLD `from led_ticker.ticker import BULLET_WIDTH`
elsewhere, that confirms the symbol is still referenced — proceed to Step 3.

- [ ] **Step 3: Move scroll geometry + rewire both scroll draw sites**

In `ticker.py`:
- Replace the local `SCROLL_GAP` / `BULLET_WIDTH` / `BULLET_COLOR` / `_draw_bullet`
  / `scroll_separator_width` definitions by importing from `separator.py`:
  `from led_ticker.separator import (DEFAULT_DOT_SPEC, SCROLL_GAP, render_separator, scroll_separator_width, separator_width)`.
  Delete the four removed symbols (`BULLET_WIDTH`, `BULLET_COLOR`, `_draw_bullet`,
  and the local `scroll_separator_width` / `SCROLL_GAP`).
- In `_draw_scroll_frame`, replace `_draw_bullet(canvas, bullet_x)` with:
  `render_separator(canvas, bullet_x, bullet_x, DEFAULT_DOT_SPEC)`
  (the dot is constant white, so passing `bullet_x` as the frame is harmless;
  Phase 2 replaces the literal with the real derived frame + configured spec).

In `transitions/effects.py` `Scroll`:
- Replace the deferred `from led_ticker.ticker import SCROLL_GAP, scroll_separator_width`
  with a TOP-LEVEL `from led_ticker.separator import (DEFAULT_DOT_SPEC, SCROLL_GAP, render_separator, scroll_separator_width)`.
- `__init__`: `self._spec = DEFAULT_DOT_SPEC`; `self._sep_w = scroll_separator_width(self._spec)`; `self._gap = SCROLL_GAP`.
- In `frame_at`, replace the inline 2×2 dot loop with:
  `render_separator(canvas, bullet_x, scroll_offset, self._spec)`.

Run `grep -rn '_draw_bullet\|BULLET_WIDTH\|BULLET_COLOR' src/led_ticker/` and confirm
no references remain.

- [ ] **Step 4: Run the scroll tripwires — expect pass**

Run: `uv run pytest tests/test_transitions.py -k "Scroll or scroll" -v`
Expected: PASS — positions/geometry unchanged, separator width 14, outgoing_scroll_pos respected.

- [ ] **Step 5: Lint + commit**

```bash
uv run --extra dev ruff check src/led_ticker/ticker.py src/led_ticker/transitions/effects.py tests/test_transitions.py
git add src/led_ticker/ticker.py src/led_ticker/transitions/effects.py tests/test_transitions.py
git commit -m "refactor(scroll): route the scroll dot through render_separator; drop _draw_bullet/BULLET_*"
```

---

### Task 4: Meta-tripwire + full-suite verification

**Files:**
- Test: `tests/test_separator.py` (add the meta-tripwire)

- [ ] **Step 1: Add the meta-tripwire**

Append to `tests/test_separator.py`:

```python
def test_no_inline_hardcoded_dot_remains():
    """All separator pixels must go through render_separator — no inline
    255,255,255 dot loop survives in the scroll paths (Phase 1 unification)."""
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent / "src" / "led_ticker"
    for rel in ("ticker.py", "transitions/effects.py"):
        text = (root / rel).read_text()
        assert "BULLET_WIDTH" not in text, f"{rel} still references BULLET_WIDTH"
        assert "_draw_bullet" not in text, f"{rel} still defines/uses _draw_bullet"
        assert "255, 255, 255" not in text, (
            f"{rel} still has a hardcoded white dot literal"
        )
```

- [ ] **Step 2: Run the meta-tripwire**

Run: `uv run pytest tests/test_separator.py::test_no_inline_hardcoded_dot_remains -v`
Expected: PASS.

- [ ] **Step 3: Full suite + ruff (zero-drift acceptance gate)**

Run: `make test`
Expected: all pass — every pre-existing ticker-separator and scroll tripwire green (zero pixel drift), plus the new `test_separator.py`.
Run: `uv run --extra dev ruff check src/ tests/ tools/`
Expected: no violations.

- [ ] **Step 4: Commit**

```bash
git add tests/test_separator.py
git commit -m "test(separator): meta-tripwire — no inline hardcoded dot remains"
```

---

## Notes

- **Temporary duplication is intentional and removed within the phase:** Task 1's
  `separator.py` duplicates the circle/dot logic still in `ticker.py`; the parity
  tests exploit that coexistence to prove byte-identity, then Tasks 2–3 delete the
  `ticker.py` originals.
- **Out of scope (Phase 2/3):** any new config field, the glyph kind, the derived
  animated frame for a configured provider, variable-width geometry, validation, and
  docs. Phase 1 is appearance-identical by construction.
