# Hi-Res Circle Default Separator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When a `forever_scroll` section's `separator` and `separator_font` / `separator_font_size` are unset, render the default loop separator as a smooth hi-res circle on bigsign (instead of a chunky scaled BDF `•`). Smallsign behavior is pixel-identical to today. `separator_color` alone routes through the new path so a recolored circle replaces a recolored chunky bullet.

**Architecture:** A new private `_CircleBufferMsg(TickerMessage)` subclass in `ticker.py` overrides `draw()` to branch on `isinstance(canvas, ScaledCanvas)`. The hires branch paints a filled disk at physical resolution to `unwrap_to_real(canvas)`; the smallsign branch calls `super().draw()` (delegating to the inherited BDF " • " rendering). No new TOML schema; `_resolve_buffer_msg` in `app.py` gains one branch for color-only configs.

**Tech Stack:** Python 3.13, `attrs` for class definitions, `pytest` for tests. Existing helpers: `led_ticker.scaled_canvas.ScaledCanvas` / `unwrap_to_real`, `led_ticker.color_providers._ConstantColor` / `Rainbow`, `led_ticker.widgets._frame_aware._FrameAware`.

**Spec:** [`docs/superpowers/specs/2026-05-13-hires-circle-separator-design.md`](../specs/2026-05-13-hires-circle-separator-design.md)

---

## File map

**Modify:**
- `src/led_ticker/ticker.py` — add disk rasterization helper, `_CircleBufferMsg` class, change `DEFAULT_BUFFER_MSG` value
- `src/led_ticker/app.py` — branch `_resolve_buffer_msg` for color-only configs

**Test:**
- `tests/test_ticker.py` — add disk-helper unit tests + `_CircleBufferMsg.draw` behavior tests (hires + smallsign)
- `tests/test_app.py` — add `_resolve_buffer_msg` color-only branch test, update no-fields-set test if needed
- `tests/test_ticker_display.py` — add side-by-side scroll tripwire for hi-res circle rendering

**Docs:**
- `docs/site/src/content/docs/reference/config-options.mdx` — short note on the default's hi-res adaptation

**No file creation** — every change lives in an existing file.

---

## Task 1: Disk rasterization helper

**Files:**
- Modify: `src/led_ticker/ticker.py` (add module-private helper near line 22)
- Test: `tests/test_ticker.py` (append new tests)

The helper paints a filled disk centered in the canvas's content band at physical resolution. Uses integer math only — no `math.sqrt` per pixel. Returns `(canvas, cursor_pos + 10)` so layout stays consistent with today's `" • "` BDF advance.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_ticker.py`:

```python
def test_draw_hires_circle_paints_filled_disk_on_scaled_canvas():
    """The disk fills a 32x32 physical bounding box centered in the
    content band, with the documented row-half-widths."""
    from unittest.mock import MagicMock
    from led_ticker.scaled_canvas import ScaledCanvas
    from led_ticker.ticker import _draw_hires_circle
    from led_ticker.colors import RGB_WHITE

    real = MagicMock()
    real.width = 256
    real.height = 64
    canvas = ScaledCanvas(real, scale=4, content_height=16)
    # canvas._y_offset = (64 - 16*4) // 2 = 0

    out_canvas, cursor = _draw_hires_circle(canvas, cursor_pos=0, color=RGB_WHITE)

    assert out_canvas is canvas
    assert cursor == 10  # logical advance width

    # All SetPixel calls landed on the underlying real canvas
    # (constraint #11 — paint at physical resolution).
    assert real.SetPixel.called
    assert canvas is not None

    # Pixel set lives in a 32x32 physical bounding box. Cursor=0 puts
    # the circle at x=0 logical → x=0..40 physical (1px pad + 32px disk
    # + 1px pad after; the pad pixels do NOT SetPixel — they're advance
    # only). Disk pixels: x in [4, 35] physical (left pad 4 = 1 logical
    # * scale 4), y in [0, 31] physical.
    coords = {(c.args[0], c.args[1]) for c in real.SetPixel.call_args_list}
    xs = [x for x, _ in coords]
    ys = [y for _, y in coords]
    assert min(xs) >= 4 and max(xs) <= 35, f"x out of [4,35]: {min(xs)}..{max(xs)}"
    assert min(ys) >= 0 and max(ys) <= 31, f"y out of [0,31]: {min(ys)}..{max(ys)}"

    # Disk count is ~π * 16² ≈ 804. Allow ±5% for integer-math rounding.
    assert 760 <= len(coords) <= 850, f"disk pixel count {len(coords)} out of range"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_ticker.py::test_draw_hires_circle_paints_filled_disk_on_scaled_canvas -v`

Expected: `ImportError: cannot import name '_draw_hires_circle' from 'led_ticker.ticker'`.

- [ ] **Step 3: Add the helper to `src/led_ticker/ticker.py`**

Insert after the existing `DEFAULT_BUFFER_MSG` line (around line 22) but BEFORE the class is referenced. Actually insert near the top after imports, before `DEFAULT_BUFFER_MSG` so the constant can be replaced in a later task.

```python
# Logical footprint of the hi-res circle separator: 1 left pad + 8
# circle + 1 right pad = 10 logical px. Matches today's " • " BDF
# advance closely enough that _scroll_side_by_side layout doesn't
# shift. Disk diameter at scale=4 = 32 physical px (same horizontal
# footprint as a hi-res inline emoji).
_CIRCLE_LOGICAL_PAD = 1
_CIRCLE_LOGICAL_RADIUS = 4  # 8-logical-px diameter
_CIRCLE_LOGICAL_ADVANCE = 2 * _CIRCLE_LOGICAL_PAD + 2 * _CIRCLE_LOGICAL_RADIUS  # = 10


def _build_circle_offsets(radius_physical: int) -> list[tuple[int, int]]:
    """Build the filled-disk offset table for a given physical radius.

    Integer math only: row half-width = floor(sqrt(r² - dy²)) computed
    via incremental search per row. Returns offsets relative to the
    disk center as (dx, dy). Used once per scale value and cached on
    the helper below.
    """
    offsets: list[tuple[int, int]] = []
    r_sq = radius_physical * radius_physical
    for dy in range(-radius_physical, radius_physical + 1):
        # Largest dx with dx² + dy² ≤ r².
        dx_max = 0
        while (dx_max + 1) * (dx_max + 1) + dy * dy <= r_sq:
            dx_max += 1
        for dx in range(-dx_max, dx_max + 1):
            offsets.append((dx, dy))
    return offsets


# Cache offset tables per (radius_physical) since scale changes are
# rare (smallsign=1, bigsign=4) and the table has ~800 entries.
_CIRCLE_OFFSET_CACHE: dict[int, list[tuple[int, int]]] = {}


def _draw_hires_circle(
    canvas: ScaledCanvas, cursor_pos: int, color: ColorTuple
) -> tuple[ScaledCanvas, int]:
    """Paint a filled disk at physical resolution centered in the
    canvas's content band. Used by _CircleBufferMsg on ScaledCanvas
    only — plain Canvas paths go through TickerMessage's BDF rendering.

    Logical footprint is 10 px wide (1 left pad + 8 disk + 1 right pad)
    matching today's " • " BDF advance so _scroll_side_by_side layout
    stays stable.
    """
    scale = canvas.scale
    real = unwrap_to_real(canvas)

    radius_physical = _CIRCLE_LOGICAL_RADIUS * scale
    offsets = _CIRCLE_OFFSET_CACHE.get(radius_physical)
    if offsets is None:
        offsets = _build_circle_offsets(radius_physical)
        _CIRCLE_OFFSET_CACHE[radius_physical] = offsets

    # Disk center in physical coords: skip the left pad, then add the
    # radius. y center is the middle of the content band (`_y_offset`
    # is the band's top in physical y).
    cx_physical = (cursor_pos + _CIRCLE_LOGICAL_PAD) * scale + radius_physical
    cy_physical = canvas._y_offset + (canvas.height * scale) // 2

    if isinstance(color, tuple):
        r, g, b = color
    else:
        r, g, b = color.red, color.green, color.blue

    set_px = real.SetPixel
    for dx, dy in offsets:
        set_px(cx_physical + dx, cy_physical + dy, r, g, b)

    return canvas, cursor_pos + _CIRCLE_LOGICAL_ADVANCE
```

Also add `ColorTuple` to the existing typing import line at the top — it already exists in `_types.py` and `ticker.py` already imports it (verified line 13). No new import.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_ticker.py::test_draw_hires_circle_paints_filled_disk_on_scaled_canvas -v`

Expected: PASS.

If the disk pixel count is outside `[760, 850]`, dump the count and re-tune the bound. The integer-math disk for r=16 should be 797 pixels exactly; the range is just defensive against the half-step ambiguity at the radius edge.

- [ ] **Step 5: Add a follow-up test for color and an off-zero cursor position**

```python
def test_draw_hires_circle_color_applied_uniformly():
    from unittest.mock import MagicMock
    from led_ticker.scaled_canvas import ScaledCanvas
    from led_ticker.ticker import _draw_hires_circle

    real = MagicMock()
    real.width, real.height = 256, 64
    canvas = ScaledCanvas(real, scale=4, content_height=16)

    _draw_hires_circle(canvas, cursor_pos=0, color=(225, 48, 108))

    for call in real.SetPixel.call_args_list:
        _, _, r, g, b = call.args
        assert (r, g, b) == (225, 48, 108)


def test_draw_hires_circle_advance_is_ten_at_any_scale():
    from unittest.mock import MagicMock
    from led_ticker.scaled_canvas import ScaledCanvas
    from led_ticker.ticker import _draw_hires_circle
    from led_ticker.colors import RGB_WHITE

    real = MagicMock()
    real.width, real.height = 256, 64
    canvas = ScaledCanvas(real, scale=4, content_height=16)
    _, cursor = _draw_hires_circle(canvas, cursor_pos=42, color=RGB_WHITE)
    assert cursor == 42 + 10
```

Run: `pytest tests/test_ticker.py -k draw_hires_circle -v`

Expected: 3 PASS.

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/ticker.py tests/test_ticker.py
git commit -m "feat(ticker): _draw_hires_circle paints filled disk on ScaledCanvas

Integer-math disk rasterization with a per-scale offset cache.
Logical advance width is 10 (matches today's ' • ' BDF footprint).
Paints to unwrap_to_real(canvas) per constraint #11."
```

---

## Task 2: `_CircleBufferMsg` subclass with smallsign delegation

**Files:**
- Modify: `src/led_ticker/ticker.py` (add class after `_draw_hires_circle`)
- Test: `tests/test_ticker.py`

This is the duck-typed buffer message: a `TickerMessage` subclass that overrides `draw` to branch on canvas type. The smallsign branch is `super().draw(...)` — identical pixels to today's `DEFAULT_BUFFER_MSG`.

- [ ] **Step 1: Write the failing smallsign-delegation test**

```python
def test_circle_buffer_msg_smallsign_delegates_to_super_draw():
    """On a plain Canvas (no ScaledCanvas wrap), _CircleBufferMsg
    must call TickerMessage.draw — pixel-identical to today's
    DEFAULT_BUFFER_MSG. Tripwire for zero-drift on smallsign."""
    from unittest.mock import MagicMock
    from led_ticker.colors import RGB_WHITE
    from led_ticker.ticker import _CircleBufferMsg

    msg = _CircleBufferMsg(message=" • ", center=False, font_color=RGB_WHITE)

    plain_canvas = MagicMock()
    plain_canvas.width = 160
    plain_canvas.height = 16
    # Not a ScaledCanvas — isinstance(plain_canvas, ScaledCanvas) is False.

    out, cursor = msg.draw(plain_canvas, cursor_pos=0)

    # super().draw() routes through TickerMessage which calls DrawText.
    # We don't assert the exact pixel set here (that's TickerMessage's
    # responsibility) — only that _CircleBufferMsg did NOT call
    # SetPixel on the plain canvas, proving the hires branch was
    # skipped.
    assert not plain_canvas.SetPixel.called, (
        "smallsign path must delegate to BDF rendering, not SetPixel"
    )
    # And that draw returned an advance (TickerMessage's normal " • "
    # advance — exact value depends on the default font's bullet width
    # plus end padding; just assert non-zero).
    assert cursor > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_ticker.py::test_circle_buffer_msg_smallsign_delegates_to_super_draw -v`

Expected: `ImportError: cannot import name '_CircleBufferMsg' from 'led_ticker.ticker'`.

- [ ] **Step 3: Add the class**

Append to `src/led_ticker/ticker.py` directly after `_draw_hires_circle`:

```python
@attrs.define
class _CircleBufferMsg(TickerMessage):
    """forever_scroll buffer separator. Auto-routes to a hi-res circle
    when the canvas is a ScaledCanvas; falls back to TickerMessage's
    BDF rendering on plain canvases (smallsign / scale=1).

    Not a registered widget — users never configure this directly.
    Constructed by ticker.DEFAULT_BUFFER_MSG and by app._resolve_buffer_msg
    for color-only sections.

    Continuous-phase color sweep (Rainbow / ColorCycle) is provided
    automatically by the provider's class-level `restart_on_visit =
    False` — _FrameAware reads that attribute via getattr on the
    provider, not on the widget.
    """

    def draw(self, canvas: Canvas, cursor_pos: int = 0, **kwargs: Any):
        if isinstance(canvas, ScaledCanvas):
            color = self.font_color.color_for(
                self.frame_for("font_color"), 0, 1
            )
            return _draw_hires_circle(canvas, cursor_pos, color)
        return super().draw(canvas, cursor_pos, **kwargs)
```

`attrs.define` on a subclass that adds no new fields is fine — it just regenerates `__init__` from the parent's fields. Construction is identical to `TickerMessage(...)`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_ticker.py::test_circle_buffer_msg_smallsign_delegates_to_super_draw -v`

Expected: PASS.

- [ ] **Step 5: Add the hires-path test**

```python
def test_circle_buffer_msg_hires_path_paints_circle():
    """On ScaledCanvas, _CircleBufferMsg.draw must paint the hi-res
    disk via _draw_hires_circle (not delegate to BDF)."""
    from unittest.mock import MagicMock
    from led_ticker.scaled_canvas import ScaledCanvas
    from led_ticker.colors import RGB_WHITE
    from led_ticker.ticker import _CircleBufferMsg

    real = MagicMock()
    real.width, real.height = 256, 64
    canvas = ScaledCanvas(real, scale=4, content_height=16)

    msg = _CircleBufferMsg(message=" • ", center=False, font_color=RGB_WHITE)
    out, cursor = msg.draw(canvas, cursor_pos=0)

    assert out is canvas
    assert cursor == 10  # logical advance
    # Hires path painted SetPixel on the real canvas (not on the wrapper).
    assert real.SetPixel.called
```

- [ ] **Step 6: Add the rainbow-animates test**

```python
def test_circle_buffer_msg_hires_rainbow_animates_per_frame():
    """Rainbow font_color produces different colors on successive
    draws once advance_frame() ticks the counter."""
    from unittest.mock import MagicMock
    from led_ticker.scaled_canvas import ScaledCanvas
    from led_ticker.color_providers import Rainbow
    from led_ticker.ticker import _CircleBufferMsg

    real = MagicMock()
    real.width, real.height = 256, 64
    canvas = ScaledCanvas(real, scale=4, content_height=16)

    msg = _CircleBufferMsg(
        message=" • ", center=False, font_color=Rainbow()
    )

    msg.draw(canvas, cursor_pos=0)
    first_color = real.SetPixel.call_args_list[0].args[2:5]

    # Advance several frames to ensure the rainbow hue moves past
    # any quantization plateau.
    for _ in range(30):
        msg.advance_frame()
    real.SetPixel.reset_mock()
    msg.draw(canvas, cursor_pos=0)
    second_color = real.SetPixel.call_args_list[0].args[2:5]

    assert first_color != second_color, (
        f"rainbow did not animate: both frames painted {first_color}"
    )
```

- [ ] **Step 7: Run both tests**

Run: `pytest tests/test_ticker.py -k circle_buffer_msg -v`

Expected: 3 PASS.

- [ ] **Step 8: Commit**

```bash
git add src/led_ticker/ticker.py tests/test_ticker.py
git commit -m "feat(ticker): _CircleBufferMsg(TickerMessage) auto-routes by canvas type

Hires path paints _draw_hires_circle; smallsign path delegates to
super().draw() (TickerMessage's BDF rendering). Rainbow / ColorCycle
animate via the existing provider machinery — no widget-level
restart_on_visit override needed."
```

---

## Task 3: Replace `DEFAULT_BUFFER_MSG`

**Files:**
- Modify: `src/led_ticker/ticker.py` (line 20)
- Test: `tests/test_ticker.py`

Switch the module-level `DEFAULT_BUFFER_MSG` to a `_CircleBufferMsg` instance. The type annotation stays `TickerMessage` (subclass IS-A parent). No call sites change because the duck-typed interface is unchanged.

- [ ] **Step 1: Write a tripwire test**

```python
def test_default_buffer_msg_is_circle_buffer_msg():
    """DEFAULT_BUFFER_MSG must be a _CircleBufferMsg so bigsign sees
    the hi-res circle automatically. Tripwire against accidental
    revert to plain TickerMessage(' • ', ...)."""
    from led_ticker.ticker import DEFAULT_BUFFER_MSG, _CircleBufferMsg

    assert isinstance(DEFAULT_BUFFER_MSG, _CircleBufferMsg)
    assert DEFAULT_BUFFER_MSG.message == " • "
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_ticker.py::test_default_buffer_msg_is_circle_buffer_msg -v`

Expected: `AssertionError` (DEFAULT_BUFFER_MSG is a plain `TickerMessage`).

- [ ] **Step 3: Replace the constant**

In `src/led_ticker/ticker.py`, change the existing assignment (currently line 20-22):

```python
DEFAULT_BUFFER_MSG: TickerMessage = TickerMessage(
    " • ", center=False, font_color=RGB_WHITE
)
```

…to:

```python
DEFAULT_BUFFER_MSG: TickerMessage = _CircleBufferMsg(
    message=" • ", center=False, font_color=RGB_WHITE
)
```

Note: the previous code used positional `" • "` as the first arg. `TickerMessage`'s attrs init defines `message` as the first field, so positional works too — but explicit `message=` is clearer and matches the construction site in `app.py`. Either is correct; pick explicit.

Position the assignment AFTER the `_CircleBufferMsg` class definition (the class must be defined before instantiation). This means moving `DEFAULT_BUFFER_MSG` later in the file — currently it lives at line 20, before the class. Move it to just after `_CircleBufferMsg`'s closing brace.

- [ ] **Step 4: Run the tripwire and all existing ticker tests**

Run: `pytest tests/test_ticker.py -v`

Expected: ALL PASS. The smallsign delegation means today's `DEFAULT_BUFFER_MSG`-using tests render byte-identical pixels.

If any existing test breaks, it's almost certainly because it asserted `isinstance(DEFAULT_BUFFER_MSG, TickerMessage)` in a way that needs widening (subclass IS-A passes; identity-with-TickerMessage does not).

- [ ] **Step 5: Run the display engine tests too**

Run: `pytest tests/test_ticker_display.py -v`

Expected: ALL PASS.

Particularly important: `TestScrollSideBySide` exercises the buffer message in the engine path. If anything breaks here, the duck-typed interface is broken.

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/ticker.py tests/test_ticker.py
git commit -m "feat(ticker): DEFAULT_BUFFER_MSG uses _CircleBufferMsg

Default forever_scroll separator now adapts to the canvas type.
Smallsign keeps the BDF ' • '; bigsign renders a smooth hi-res circle.
No call sites change — duck-typed buffer_msg interface is preserved."
```

---

## Task 4: Color-only branch in `_resolve_buffer_msg`

**Files:**
- Modify: `src/led_ticker/app.py` (function around line 685)
- Test: `tests/test_app.py`

When the user sets only `separator_color` and leaves the text/font fields unset, return a `_CircleBufferMsg` with the user's color instead of a `TickerMessage("•")`. This ensures `separator_color = [255, 0, 0]` produces a red hi-res circle on bigsign, not a red chunky BDF bullet.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_app.py`, near the other `_resolve_buffer_msg` tests:

```python
def test_resolve_buffer_msg_color_only_returns_circle_buffer_msg():
    """separator_color set alone (no separator, no font) → _CircleBufferMsg
    routes through the hi-res circle path on bigsign."""
    from led_ticker.app import _resolve_buffer_msg
    from led_ticker.config import SectionConfig
    from led_ticker.ticker import _CircleBufferMsg

    section = SectionConfig(
        mode="forever_scroll", separator_color=[225, 48, 108]
    )
    msg = _resolve_buffer_msg(section)

    assert isinstance(msg, _CircleBufferMsg), (
        f"expected _CircleBufferMsg, got {type(msg).__name__}"
    )
    assert msg.message == " • "
    # Color provider returns the user's RGB.
    color = msg.font_color.color_for(0, 0, 1)
    assert (color.red, color.green, color.blue) == (225, 48, 108)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_app.py::test_resolve_buffer_msg_color_only_returns_circle_buffer_msg -v`

Expected: `AssertionError` — current code returns a `TickerMessage`, not `_CircleBufferMsg`.

- [ ] **Step 3: Update `_resolve_buffer_msg`**

In `src/led_ticker/app.py`, replace the body of `_resolve_buffer_msg` (currently lines 685-728) with:

```python
def _resolve_buffer_msg(section: SectionConfig) -> TickerMessage | None:
    """Build a per-section forever_scroll separator widget.

    Returns None when all four separator_* fields are unset — Ticker
    falls back to DEFAULT_BUFFER_MSG (a _CircleBufferMsg that adapts
    to canvas type at draw time).

    Routing:
    - All four unset → None (inherit default circle).
    - Color-only override → _CircleBufferMsg with the user's color
      (still adapts to canvas type — circle on bigsign, BDF '•' on
      smallsign — just with a different fill).
    - Any of separator / separator_font / separator_font_size set
      → TickerMessage with literal text/font rendering (today's
      behavior, unchanged).
    """
    text_or_font_set = (
        section.separator is not None
        or section.separator_font is not None
        or section.separator_font_size is not None
    )
    color_set = section.separator_color is not None

    if not text_or_font_set and not color_set:
        return None

    color_provider = _coerce_color_provider(
        section.separator_color if color_set else RGB_WHITE
    )

    if not text_or_font_set:
        # Color-only: still want the hi-res circle on bigsign.
        from led_ticker.ticker import _CircleBufferMsg

        return _CircleBufferMsg(
            message=" • ", center=False, font_color=color_provider
        )

    # Explicit text / font: TickerMessage with literal rendering.
    text = section.separator if section.separator is not None else "•"
    if text == "":
        text = "  "

    kwargs: dict[str, Any] = {
        "message": text,
        "center": False,
        "font_color": color_provider,
    }
    if section.separator_font is not None:
        from led_ticker.fonts import resolve_font

        kwargs["font"] = resolve_font(
            section.separator_font, section.separator_font_size
        )
    return TickerMessage(**kwargs)
```

The `_CircleBufferMsg` import is local to keep the `app.py` top-level import graph identical (avoids any circular-import risk; `app.py` already imports from `led_ticker.ticker`, so this is fine either way — local just keeps the new dependency narrow).

- [ ] **Step 4: Run the new test**

Run: `pytest tests/test_app.py::test_resolve_buffer_msg_color_only_returns_circle_buffer_msg -v`

Expected: PASS.

- [ ] **Step 5: Run all existing `_resolve_buffer_msg` tests**

Run: `pytest tests/test_app.py -k resolve_buffer_msg -v`

Expected: ALL PASS, including:
- `test_resolve_buffer_msg_returns_none_when_all_fields_unset`
- `test_resolve_buffer_msg_with_separator_text_only`
- `test_resolve_buffer_msg_empty_string_maps_to_two_spaces`
- `test_resolve_buffer_msg_with_custom_font_inherits_default_text`
- `test_resolve_buffer_msg_with_hires_font_resolves_via_resolve_font`
- `test_resolve_buffer_msg_with_constant_color` (this one sets both separator AND separator_color → TickerMessage path, unchanged)

If `test_resolve_buffer_msg_with_constant_color` fails, double-check the new logic preserves the TickerMessage path when both `separator` and `separator_color` are set. (It should — `text_or_font_set` is True.)

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/app.py tests/test_app.py
git commit -m "feat(app): route color-only separator config through _CircleBufferMsg

When separator_color is set alone (no separator text or font), build
a _CircleBufferMsg so bigsign renders a recolored hi-res circle instead
of a recolored chunky BDF bullet. Smallsign result is identical to
today's behavior."
```

---

## Task 5: Engine integration tripwire

**Files:**
- Modify: `tests/test_ticker_display.py`

Add a single test that exercises the full path — `_scroll_side_by_side` calling the buffer message between widgets on a ScaledCanvas. Catches regressions where the engine somehow bypasses the new draw branch.

- [ ] **Step 1: Read the existing `TestScrollSideBySide` to match its style**

Run: `grep -n "class TestScrollSideBySide\|def test_" tests/test_ticker_display.py | head -20`

Pick the existing test fixture pattern (which widgets are constructed, how the canvas is wrapped) and mirror it.

- [ ] **Step 2: Write the tripwire**

Append a method to the existing `TestScrollSideBySide` class (or add a sibling test function at module level — match what's already there):

```python
def test_side_by_side_default_separator_paints_hires_circle_on_bigsign():
    """At scale=4 with two widgets, the default buffer separator
    renders as a hi-res circle (SetPixel on real canvas), not as
    chunky BDF '•'. Tripwire that DEFAULT_BUFFER_MSG.draw routes
    through _draw_hires_circle."""
    from unittest.mock import MagicMock
    from led_ticker.scaled_canvas import ScaledCanvas
    from led_ticker.ticker import DEFAULT_BUFFER_MSG

    real = MagicMock()
    real.width, real.height = 256, 64
    canvas = ScaledCanvas(real, scale=4, content_height=16)

    out, cursor = DEFAULT_BUFFER_MSG.draw(canvas, cursor_pos=0)

    # Hi-res circle path: SetPixel called many times on real canvas
    # (not on the wrapper).
    assert real.SetPixel.call_count > 700, (
        f"expected disk paint (~800 pixels), got {real.SetPixel.call_count}"
    )
    # Logical advance matches the disk helper's contract.
    assert cursor == 10
```

This is intentionally LIGHTWEIGHT — it exercises just `DEFAULT_BUFFER_MSG.draw` on a ScaledCanvas, not the full engine. The full engine path is already covered by existing `TestScrollSideBySide` cases that pass because the duck-typed interface is preserved (Task 3 verified that).

- [ ] **Step 3: Run the tripwire**

Run: `pytest tests/test_ticker_display.py::test_side_by_side_default_separator_paints_hires_circle_on_bigsign -v`

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/test_ticker_display.py
git commit -m "test(ticker_display): tripwire that bigsign default separator is hi-res circle"
```

---

## Task 6: Regression sweep

**Files:** No code changes — just verification.

- [ ] **Step 1: Run the full test suite**

Run: `make test`

Expected: ALL PASS, no new failures. If anything in `tests/test_*.py` fails, investigate — likely a hidden `isinstance(x, TickerMessage)` check that needs widening (subclass passes) or a pixel assertion that drifted (which would mean the smallsign delegation is NOT pixel-identical and needs investigation).

- [ ] **Step 2: Validate every bundled example config**

Run: `for cfg in config/*.example.toml; do echo "--- $cfg"; led-ticker validate --config "$cfg" || break; done`

Expected: every config validates with no new errors and no new warnings.

- [ ] **Step 3: Render smallsign and bigsign demos**

The repo has `tools/render_demo`. Render a forever_scroll demo at both scales:

Run: `python -m tools.render_demo --config config/config.example.toml --out /tmp/smallsign_demo.gif` (or whatever the CLI is — read `tools/render_demo/README.md` first if unsure)

Run: `python -m tools.render_demo --config config/config.bigsign.example.toml --out /tmp/bigsign_demo.gif`

If `config/config.bigsign.example.toml` doesn't include a forever_scroll section, write a minimal one for verification:

```toml
[display]
default_scale = 4
# ... (mirror config/config.bigsign.example.toml's display block) ...

[[playlist.section]]
mode = "forever_scroll"

[[playlist.section.widget]]
type = "message"
text = "ONE"

[[playlist.section.widget]]
type = "message"
text = "TWO"
```

Save as `/tmp/forever_scroll_demo.toml` and render.

- [ ] **Step 4: Visually verify**

Open `/tmp/bigsign_demo.gif`. Confirm the separator between widgets is a smooth round circle, not a chunky 4x4 block.

Open `/tmp/smallsign_demo.gif`. Confirm the separator is the same BDF `•` as before (visually identical to current main).

This is a manual eyeball check. There's no automated visual-diff test for the demo renderer, so the engineer must look.

- [ ] **Step 5: No commit unless something fails**

If the regression sweep passes, no commit. If something fails, fix it (likely a missed call site or a test that asserts strict-type instead of duck-type).

---

## Task 7: Docs note

**Files:**
- Modify: `docs/site/src/content/docs/reference/config-options.mdx`

Add a short note to the `separator` row (or wherever the separator config is documented) explaining the bigsign default adapts to a hi-res circle.

- [ ] **Step 1: Find the existing separator docs**

Run: `grep -n "separator" docs/site/src/content/docs/reference/config-options.mdx | head -20`

Locate the table row for `separator`.

- [ ] **Step 2: Add the note**

Edit the description text for the `separator` row to add a sentence:

> "On bigsign (`default_scale > 1`), the default separator renders as a smooth hi-res circle painted at physical resolution. Set `separator = '•'` (or any other character) to opt out and use literal BDF rendering instead. Color comes from `separator_color`; defaults to white."

Or, if the docs follow a more terse table-style format, add a one-liner at the bottom of the row's description:

> "Default adapts to a hi-res circle on bigsign. Set explicitly to opt out."

Match the existing docs voice — if other rows have prose paragraphs, write a paragraph; if they're terse, be terse.

- [ ] **Step 3: Build the docs locally to confirm no MDX errors**

Run: `cd docs/site && pnpm install && pnpm build` (if docs are not built in CI, otherwise: `pnpm dev` and visually confirm the rendered page).

Expected: no build errors. MDX components and the table render cleanly.

- [ ] **Step 4: Run the docs-drift meta-tripwire**

Run: `pytest tests/test_docs_config_options_drift.py -v`

Expected: PASS. The drift test only catches missing/extra fields, not prose changes — but run it to confirm nothing unexpected drifted while editing the docs file.

- [ ] **Step 5: Commit**

```bash
git add docs/site/src/content/docs/reference/config-options.mdx
git commit -m "docs: note that bigsign default separator is a hi-res circle"
```

---

## Task 8: Open the PR

**Files:** None (git operation).

- [ ] **Step 1: Push the branch**

Run: `git push -u origin worktree-hires-circle-separator`

- [ ] **Step 2: Create the PR**

Run:

```bash
gh pr create --title "Hi-res circle as default forever_scroll separator on bigsign" --body "$(cat <<'EOF'
## Summary

- When a forever_scroll section's `separator`, `separator_font`, and `separator_font_size` are unset, the default loop separator now renders as a smooth hi-res circle on bigsign (32×32 physical px) instead of a chunky scaled BDF `•`.
- `separator_color` alone routes through the same path — recolored circle on bigsign, recolored BDF `•` on smallsign.
- Smallsign behavior is byte-identical to today's main (zero pixel drift).
- No new TOML schema; no validation rules added.

Spec: `docs/superpowers/specs/2026-05-13-hires-circle-separator-design.md`
Plan: `docs/superpowers/plans/2026-05-13-hires-circle-separator.md`

## Test plan

- [ ] `make test` clean — including new tripwires in `tests/test_ticker.py` and `tests/test_ticker_display.py`
- [ ] `led-ticker validate` clean against every bundled `config.*.example.toml`
- [ ] Smallsign demo gif: visually identical to current main
- [ ] Bigsign demo gif: smooth circle separator visible between widgets
- [ ] Rainbow `separator_color` animates hue across the circle over time

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 3: Capture the PR URL** for the user.

---

## Out-of-band notes

- **`restart_on_visit` is provider-side, not widget-side.** Reviewed in `src/led_ticker/widgets/_frame_aware.py:95` — `getattr(effect, "restart_on_visit", True)` reads the attribute on the effect (color provider), not the widget. `Rainbow` and `ColorCycle` carry `restart_on_visit = False` as class attributes; the buffer message inherits continuous-phase behavior for free.
- **Disk pixel count = 797 for r=16.** If the test bound `760 <= count <= 850` fails consistently, the integer rasterization differs from the spec's `π * r²` estimate — tighten the bound to the exact value once the implementation lands.
- **`_y_offset` semantics on `ScaledCanvas`.** `canvas._y_offset = (real.height - content_height * scale) // 2`. For default bigsign (`real.height = 64, content_height = 16, scale = 4`) that's 0; for a hypothetical taller panel it'd be the top-letterbox offset. The center-y formula `canvas._y_offset + (canvas.height * canvas.scale) // 2` accounts for both.
- **No CLAUDE.md update.** None of the load-bearing invariants change. The new code respects #11 (paint to `unwrap_to_real(canvas)`) and #12 (`_FrameAware` inheritance gives advance_frame compatibility) — both already documented.
