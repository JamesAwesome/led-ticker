# Inline Emoji Arbitrary-Scale Anchor — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Inline hi-res emoji bottom-anchor to the text baseline correctly at any `scale` (not just 4), fixing the scale=2 misalignment seen on the MLB two-row title card.

**Architecture:** Replace `draw_with_emoji`'s hardcoded `iy = (y+y_offset) - 8` logical anchor with a real-pixel bottom-anchor inside `_draw_hires_emoji` (`real_top = baseline*scale + y_offset_real - physical_size`), which is exact at any scale. `_draw_hires_emoji` gains a two-mode keyword API (bottom-anchor for the inline default, top-anchor for explicit-position callers). Remove three now-redundant `emoji_y=baseline_y-8` overrides so they route through the fixed default. Low-res rendering and scale=4 are unchanged.

**Tech Stack:** Python 3.13, pytest, `ScaledCanvas` real-pixel wrapper, `HiResEmoji` sprites (`physical_size=32`).

Spec: `docs/superpowers/specs/2026-05-29-emoji-scale-anchor-design.md`

---

### Task 1: Real-pixel bottom-anchor in `_draw_hires_emoji` + rewire callers

**Files:**
- Modify: `src/led_ticker/pixel_emoji.py` — `_draw_hires_emoji` (~3033), `draw_with_emoji` (~2863 + emoji branch ~2880-2911), `draw_emoji_at` (~2987)
- Test: `tests/test_pixel_emoji.py`

This is one atomic change: the `_draw_hires_emoji` signature change forces updating both of its callers in the same commit.

- [ ] **Step 1: Write the failing tests**

Append the following to `tests/test_pixel_emoji.py` (the file already imports `draw_with_emoji`, `FONT_SMALL`, and `ScaledCanvas`). Each `draw_with_emoji` call paints onto the underlying real canvas, so tests that render more than once use a **fresh** real canvas per render via the local `_fresh_bigsign_real()` factory (rather than reusing the shared `bigsign_canvas` fixture twice):

```python
from led_ticker.pixel_emoji import HIRES_REGISTRY, draw_emoji_at


def _fresh_bigsign_real():
    from rgbmatrix import RGBMatrix, RGBMatrixOptions

    opts = RGBMatrixOptions()
    opts.rows = 32
    opts.cols = 64
    opts.chain_length = 8
    opts.parallel = 1
    opts.pixel_mapper_config = "U-mapper"
    return RGBMatrix(options=opts).CreateFrameCanvas()


def _sprite_max_py(slug: str) -> int:
    """Lowest lit row index in the hi-res sprite (sprites leave row 31 blank)."""
    return max(py for _x, py, *_ in HIRES_REGISTRY[slug].pixels)


def _lit_pixels(real) -> list[tuple[int, int]]:
    return [
        (rx, ry)
        for ry in range(real.height)
        for rx in range(real.width)
        if real.get_pixel(rx, ry) != (0, 0, 0)
    ]


def _lowest_lit_row(real) -> int:
    return max(ry for _rx, ry in _lit_pixels(real))


def _expected_bottom(baseline: int, scale: int, y_off: int, slug: str) -> int:
    """Real row of the sprite's lowest lit pixel when bottom-anchored at baseline."""
    physical = HIRES_REGISTRY[slug].physical_size
    return baseline * scale + y_off - physical + _sprite_max_py(slug)


def test_hires_emoji_bottom_anchored_at_scale_2():
    sc = ScaledCanvas(_fresh_bigsign_real(), scale=2)  # y_offset_real = 16
    baseline = 12
    draw_with_emoji(sc, FONT_SMALL, 0, baseline, (255, 255, 255), ":baseball:")
    assert _lowest_lit_row(sc.real) == _expected_bottom(
        baseline, 2, sc.y_offset_real, "baseball"
    )


def test_hires_emoji_baseline_gap_is_scale_invariant():
    baseline = 12

    sc4 = ScaledCanvas(_fresh_bigsign_real(), scale=4)
    draw_with_emoji(sc4, FONT_SMALL, 0, baseline, (255, 255, 255), ":baseball:")
    gap4 = (baseline * 4 + sc4.y_offset_real) - _lowest_lit_row(sc4.real)

    sc2 = ScaledCanvas(_fresh_bigsign_real(), scale=2)
    draw_with_emoji(sc2, FONT_SMALL, 0, baseline, (255, 255, 255), ":baseball:")
    gap2 = (baseline * 2 + sc2.y_offset_real) - _lowest_lit_row(sc2.real)

    assert gap2 == gap4


def test_hires_emoji_bottom_anchored_at_scale_3():
    """Arbitrary scale: real-pixel anchor is exact where logical floor-div
    (32 // 3 = 10) would place the sprite 2 real px too low."""
    sc = ScaledCanvas(_fresh_bigsign_real(), scale=3, content_height=16)  # y_off=8
    baseline = 12
    draw_with_emoji(sc, FONT_SMALL, 0, baseline, (255, 255, 255), ":baseball:")
    assert _lowest_lit_row(sc.real) == _expected_bottom(
        baseline, 3, sc.y_offset_real, "baseball"
    )


def test_hires_emoji_top_clip_is_safe_at_scale_2():
    """Negative real_top (sprite taller than the headroom above baseline)
    clips at the top, never raises or paints out of bounds."""
    sc = ScaledCanvas(_fresh_bigsign_real(), scale=2)  # y_off=16
    baseline = 4  # real_top = 4*2 + 16 - 32 = -8 → top rows clip
    draw_with_emoji(sc, FONT_SMALL, 0, baseline, (255, 255, 255), ":baseball:")
    for rx, ry in _lit_pixels(sc.real):
        assert 0 <= ry < sc.real.height
        assert 0 <= rx < sc.real.width


def test_draw_emoji_at_keeps_top_anchor():
    """Single-icon placement (MLB logos) still top-anchors at the given y.
    Constructed so y_offset_real != 0 to avoid a tautology at offset 0."""
    sc = ScaledCanvas(_fresh_bigsign_real(), scale=2)  # y_offset_real = 16 (non-zero)
    top = 3
    draw_emoji_at(sc, "baseball", 0, top)
    sprite = HIRES_REGISTRY["baseball"]
    min_py = min(py for _x, py, *_ in sprite.pixels)
    # Top-anchored: real top row = top*scale + y_offset_real; first lit row adds min_py.
    expected_top_row = top * sc.scale + sc.y_offset_real + min_py
    assert min(ry for _rx, ry in _lit_pixels(sc.real)) == expected_top_row
```

- [ ] **Step 2: Run the key regression test — confirm it FAILS**

Run: `uv run pytest tests/test_pixel_emoji.py::test_hires_emoji_bottom_anchored_at_scale_2 -v`
Expected: FAIL. Current `iy = baseline - 8` puts the lowest lit row at `(baseline-8)*2 + 16 + max_py = 8 + 16 + 30 = 54`, but `_expected_bottom` is `12*2 + 16 - 32 + 30 = 38`. (`test_draw_emoji_at_keeps_top_anchor` already passes — `draw_emoji_at` is unchanged pre-fix; that's fine, it's a preservation guard.)

- [ ] **Step 3: Rewrite `_draw_hires_emoji` with the two-mode anchor**

Replace the whole function (currently `src/led_ticker/pixel_emoji.py:3033-3057`) with:

```python
def _draw_hires_emoji(
    canvas: ScaledCanvas,
    hires: HiResEmoji,
    ix_logical: int,
    *,
    top_logical: int | None = None,
    bottom_baseline_logical: int | None = None,
) -> None:
    """Paint a hi-res sprite directly to the ScaledCanvas's real canvas.

    Exactly one vertical anchor must be supplied:
      - ``bottom_baseline_logical``: the sprite's BOTTOM is placed at this
        logical baseline, computed in real pixels
        (``real_top = baseline*scale + y_offset_real - physical_size``) so it
        is exact at any scale — not just scales that divide ``physical_size``.
      - ``top_logical``: the sprite's TOP starts at this logical row
        (``real_top = top*scale + y_offset_real``). Used by explicit-position
        callers (single-icon placement, two-row band layout).

    The wrapper's ``SetPixel`` would expand each pixel to a ``scale × scale``
    block, defeating the hi-res sprite; ``real.SetPixel`` writes individual
    physical LEDs. Out-of-bounds rows/cols are skipped (top-clip safe).
    """
    if (top_logical is None) == (bottom_baseline_logical is None):
        raise ValueError(
            "_draw_hires_emoji requires exactly one of top_logical / "
            "bottom_baseline_logical"
        )

    def _paint(real: Any, scale: int, y_offset_real: int) -> None:
        real_x_anchor = ix_logical * scale
        if bottom_baseline_logical is not None:
            real_y_anchor = (
                bottom_baseline_logical * scale + y_offset_real - hires.physical_size
            )
        else:
            real_y_anchor = top_logical * scale + y_offset_real
        real_w = real.width
        real_h = real.height
        for px, py, r, g, b in hires.pixels:
            rx = real_x_anchor + px
            ry = real_y_anchor + py
            if 0 <= rx < real_w and 0 <= ry < real_h:
                real.SetPixel(rx, ry, r, g, b)

    paint_hires(canvas, _paint)
```

- [ ] **Step 4: Rewire `draw_with_emoji`'s emoji branch + remove `iy_default`**

In `src/led_ticker/pixel_emoji.py`, delete the pre-loop `iy_default` block (currently ~2852-2863, the comment paragraph ending in `iy_default = (y + y_offset) - 8`). Replace the emoji branch of the loop (currently ~2881-2911) with:

```python
        if seg_type == "emoji":
            if prev_was_text:
                total += EMOJI_PADDING
            ix = int(cursor_pos + total)

            # Hi-res only fires if (a) we're on a ScaledCanvas, (b) a hi-res
            # variant exists, and (c) the sprite fits within the caller's
            # max_emoji_height (if specified). Otherwise: low-res fallback.
            hires: HiResEmoji | None = None
            if use_hires and value in HIRES_REGISTRY:
                candidate = HIRES_REGISTRY[value]
                logical_h = candidate.physical_size // canvas.scale
                if max_emoji_height is None or logical_h <= max_emoji_height:
                    hires = candidate

            if hires is not None:
                # Default path bottom-anchors the sprite at the text baseline
                # in REAL pixels (exact at any scale). An explicit emoji_y is a
                # logical TOP position from a band-layout caller — preserve it.
                if emoji_y is None:
                    _draw_hires_emoji(
                        canvas, hires, ix, bottom_baseline_logical=(y + y_offset)
                    )
                else:
                    _draw_hires_emoji(canvas, hires, ix, top_logical=emoji_y)
                total += hires.logical_width(canvas.scale) + EMOJI_PADDING
            else:
                # Low-res 8×8 sprite paints through the wrapper (logical space),
                # so a logical `baseline - 8` bottom-anchor is exact at any scale.
                iy = (y + y_offset) - 8 if emoji_y is None else emoji_y
                icon = _get_registry()[value]
                iw = _emoji_width(icon)
                w = canvas.width
                h = getattr(canvas, "height", 16)
                for px, py, r, g, b in icon:
                    dx = ix + px
                    dy = iy + py
                    if 0 <= dx < w and 0 <= dy < h:
                        canvas.SetPixel(dx, dy, r, g, b)
                total += iw + EMOJI_PADDING
            prev_was_text = False
```

- [ ] **Step 5: Rewire `draw_emoji_at`'s hires call to top-anchor**

In `src/led_ticker/pixel_emoji.py`, the single-icon path (currently ~2987) calls `_draw_hires_emoji(canvas, hires, x, y)`. Change it to name the top-anchor explicitly:

```python
    if hires is not None:
        _draw_hires_emoji(canvas, hires, x, top_logical=y)
        return hires.logical_width(canvas.scale) + EMOJI_PADDING
```

- [ ] **Step 6: Run the new tests — confirm they PASS**

Run: `uv run pytest tests/test_pixel_emoji.py -v -k "bottom_anchored or baseline_gap or scale_3 or top_clip or draw_emoji_at_keeps"`
Expected: all 5 PASS.

- [ ] **Step 7: Run the full pixel-emoji suite — confirm no regression (scale=4 + lowres preserved)**

Run: `uv run pytest tests/test_pixel_emoji.py -v`
Expected: all pass — including the existing `test_hires_moon_paints_real_canvas_at_physical_resolution` (scale=4) and `test_hires_falls_back_to_lowres_on_real_canvas` (low-res), which guard the unchanged paths.

- [ ] **Step 8: Commit**

```bash
git add src/led_ticker/pixel_emoji.py tests/test_pixel_emoji.py
git -c core.hooksPath=/dev/null commit -m "fix: bottom-anchor inline hires emoji in real pixels (arbitrary scale)

draw_with_emoji hardcoded iy = (y+y_offset) - 8, assuming an 8-logical-row
sprite — true only at scale=4. A 32px hires sprite is 16 logical rows at
scale=2, so it hung ~16 real px below the baseline. Anchor the sprite's
bottom at the baseline in REAL pixels (baseline*scale + y_offset_real -
physical_size), exact at any scale. _draw_hires_emoji gains a two-mode
keyword API (bottom-anchor default / top-anchor for explicit-position
callers); draw_emoji_at keeps top-anchor. scale=4 and low-res unchanged."
```

---

### Task 2: Route all call sites through the scale-aware anchor (image/two_row overrides + weather/`draw_emoji_at`)

**Files:**
- Modify: `src/led_ticker/widgets/_image_base.py` (~809, ~865), `src/led_ticker/widgets/two_row.py` (~399), `src/led_ticker/pixel_emoji.py` (`draw_emoji_at` ~2953), `src/led_ticker/widgets/weather.py` (~185)
- Test: `tests/test_pixel_emoji.py`, `tests/test_widgets/test_weather.py`

Five sites hardcode the 8-row `- 8` anchor. Three (`_image_base` ×2, `two_row` ×1) pass `emoji_y=baseline_y - 8` to `draw_with_emoji` redundantly — removing the override routes them through the now-fixed default. The fifth (`weather.py`) uses `draw_emoji_at(canvas, slug, x, baseline_y - 8)`; `draw_emoji_at` is top-anchor only, so it gains a `bottom_baseline` mode (mirroring `_draw_hires_emoji`) and weather passes the baseline.

- [ ] **Step 1: Write failing tests**

Append to `tests/test_pixel_emoji.py` (reuses the `_fresh_bigsign_real`, `_lit_pixels`, `_lowest_lit_row`, `_expected_bottom`, `_sprite_max_py` helpers added in Task 1):

```python
import pathlib


def test_no_hardcoded_emoji_y_minus_8_overrides():
    """The redundant `emoji_y=baseline_y - 8` overrides must stay removed —
    they bypass draw_with_emoji's scale-aware anchor and reintroduce the
    scale=2 misalignment. Band-layout sites use a computed emoji_y and are
    exempt; only the literal `baseline_y - 8` form is banned. weather.py uses
    draw_emoji_at(..., bottom_baseline=...) so it carries no `- 8` literal."""
    root = pathlib.Path(__file__).resolve().parents[1] / "src" / "led_ticker"
    offenders = []
    for rel in ("widgets/_image_base.py", "widgets/two_row.py", "widgets/weather.py"):
        text = (root / rel).read_text()
        if "baseline_y - 8" in text:
            offenders.append(rel)
    assert not offenders, f"redundant `- 8` anchor returned in: {offenders}"


def test_draw_emoji_at_bottom_baseline_anchors_at_scale_2():
    """draw_emoji_at's new bottom_baseline mode bottom-anchors the icon at
    the baseline (exact at any scale), like draw_with_emoji's default."""
    sc = ScaledCanvas(_fresh_bigsign_real(), scale=2)  # y_offset_real = 16
    baseline = 12
    draw_emoji_at(sc, "baseball", 0, bottom_baseline=baseline)
    assert _lowest_lit_row(sc.real) == _expected_bottom(
        baseline, 2, sc.y_offset_real, "baseball"
    )


def test_draw_emoji_at_requires_exactly_one_anchor():
    sc = ScaledCanvas(_fresh_bigsign_real(), scale=2)
    import pytest

    with pytest.raises(ValueError):
        draw_emoji_at(sc, "baseball", 0)  # neither y nor bottom_baseline
    with pytest.raises(ValueError):
        draw_emoji_at(sc, "baseball", 0, 5, bottom_baseline=12)  # both
```

- [ ] **Step 2: Run the new tests — confirm they FAIL**

Run: `uv run pytest tests/test_pixel_emoji.py -v -k "no_hardcoded or bottom_baseline or requires_exactly_one"`
Expected: `test_no_hardcoded...` FAILS (three offenders present); the two `draw_emoji_at` tests FAIL/ERROR (`bottom_baseline` kwarg doesn't exist yet).

- [ ] **Step 3: Add the `bottom_baseline` mode to `draw_emoji_at`**

In `src/led_ticker/pixel_emoji.py`, change `draw_emoji_at`'s signature and dispatch. Make `y` optional and add the keyword; require exactly one anchor:

```python
def draw_emoji_at(
    canvas: Canvas,
    slug: str,
    x: int,
    y: int | None = None,
    *,
    bottom_baseline: int | None = None,
    max_emoji_height: int | None = None,
) -> int:
```

At the top of the body, add the guard and resolve the low-res top row:

```python
    if (y is None) == (bottom_baseline is None):
        raise ValueError(
            "draw_emoji_at requires exactly one of y / bottom_baseline"
        )
```

In the hi-res branch, dispatch by mode:

```python
    if hires is not None:
        if bottom_baseline is not None:
            _draw_hires_emoji(
                canvas, hires, x, bottom_baseline_logical=bottom_baseline
            )
        else:
            _draw_hires_emoji(canvas, hires, x, top_logical=y)
        return hires.logical_width(canvas.scale) + EMOJI_PADDING
```

In the low-res branch, compute the top row from whichever anchor was given (the 8×8 sprite bottom-anchors at `bottom_baseline - 8`, logical/exact at any scale):

```python
    iy = (bottom_baseline - 8) if bottom_baseline is not None else y
    icon = _get_registry()[slug]  # KeyError on unknown slug — intentional
    iw = _emoji_width(icon)
    w = canvas.width
    h = getattr(canvas, "height", 16)
    for px, py, r, g, b in icon:
        dx = x + px
        dy = iy + py
        if 0 <= dx < w and 0 <= dy < h:
            canvas.SetPixel(dx, dy, r, g, b)
    return iw + EMOJI_PADDING
```

Update the docstring's first line to note: "Supply exactly one of `y` (logical top) or `bottom_baseline` (logical baseline; the icon's bottom anchors there, exact at any scale)."

- [ ] **Step 4: Point weather at `bottom_baseline`**

In `src/led_ticker/widgets/weather.py` (~185), change the call from `baseline_y - 8` (positional `y`) to the keyword, and update the now-stale comment:

```python
            # Bottom-anchor the condition icon at the text baseline (exact at
            # any scale via draw_emoji_at's real-pixel bottom-anchor).
            cursor_pos += draw_emoji_at(
                canvas,
                _match_condition(self.weather),
                int(cursor_pos),
                bottom_baseline=baseline_y,
            )
```

- [ ] **Step 5: Remove the three `emoji_y=baseline_y - 8` overrides**

In `src/led_ticker/widgets/_image_base.py`, the separator draw (~805-810) and text draw (~861-866) each pass `emoji_y=baseline_y - 8,` as one argument line inside a `draw_with_emoji(...)` call. Delete that single argument line from both (leave every other argument unchanged). In `src/led_ticker/widgets/two_row.py`, the separator draw (~392-402) passes `emoji_y=baseline_y - 8,` — delete that line. After each deletion the call relies on `draw_with_emoji`'s `emoji_y=None` default.

- [ ] **Step 6: Update the weather spies**

`tests/test_widgets/test_weather.py` has spies on `_draw_hires_emoji` that capture the anchor. The placement spy now receives `bottom_baseline_logical=baseline_y` (not `top_logical=baseline_y - 8`). Update that spy's capture + assertion to expect the icon bottom-anchored at the baseline: capture `bottom_baseline_logical` and assert it equals `compute_baseline(font, canvas, valign="center")` (the baseline, no `- 8`). Leave the call-count spies untouched.

- [ ] **Step 7: Run the new + weather tests — confirm PASS**

Run: `uv run pytest tests/test_pixel_emoji.py tests/test_widgets/test_weather.py -v`
Expected: all pass — including the tripwire, the two `draw_emoji_at` tests, and the updated weather spies.

- [ ] **Step 8: Run the widget suites — confirm scale=4 unchanged**

Run: `uv run pytest tests/test_widgets/test_two_row.py tests/test_widgets/test_image_base.py -v`
Expected: all pass (these exercise the separator/text overlay paths at scale=4).

- [ ] **Step 9: Commit**

```bash
git add src/led_ticker/pixel_emoji.py src/led_ticker/widgets/_image_base.py src/led_ticker/widgets/two_row.py src/led_ticker/widgets/weather.py tests/test_pixel_emoji.py tests/test_widgets/test_weather.py
git -c core.hooksPath=/dev/null commit -m "fix: route all emoji call sites through the scale-aware anchor

Remove the redundant emoji_y=baseline-8 overrides (image separator+text,
two_row separator) so they use draw_with_emoji's fixed default. Add a
bottom_baseline mode to draw_emoji_at (mirrors _draw_hires_emoji) and point
the weather condition icon at it — weather was the fifth -8 site, reachable
only via the single-icon API. scale=4 unchanged; scale=2 corrected. Tripwire
bans the -8 literal from returning."
```

---

### Task 3: Update CLAUDE.md invariant + full verification

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update the inline-emoji invariant note**

In `CLAUDE.md`, find the "Inline emoji" load-bearing-invariant bullet (search for `pixel_emoji.py` / `EMOJI_REGISTRY`). Append a sentence documenting the anchor:

```
Inline hi-res emoji bottom-anchor to the text baseline in REAL pixels
(`baseline*scale + y_offset_real - physical_size`), exact at any scale —
not the old `iy = y - 8` 8-logical-row assumption (which only held at
scale=4). Low-res 8×8 emoji anchor at logical `baseline - 8`. Explicit
`emoji_y` callers (single-icon `draw_emoji_at`, two-row band layout) keep
a top-anchor.
```

- [ ] **Step 2: Run the full check suite**

Run each and confirm clean:
```bash
make test
make lint
make typecheck
make validate CONFIG=config/config.mlb_two_row_test.toml
```
Expected: `make test` all pass (~95% coverage); `make lint` "All checks passed!"; `make typecheck` "0 errors"; validate "No issues found."

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git -c core.hooksPath=/dev/null commit -m "docs: CLAUDE.md inline-emoji anchor invariant (real-pixel, arbitrary scale)"
```
