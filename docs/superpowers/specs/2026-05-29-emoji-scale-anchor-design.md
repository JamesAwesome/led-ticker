# Inline Emoji Vertical Anchor at Arbitrary Scale — Design Spec

**Date:** 2026-05-29
**Status:** Draft — pending implementation plan.
**Author:** James + Claude (brainstorming session)

## Summary

Inline hi-res emoji (`:baseball:`, `:moon:`, etc.) render vertically misaligned — hanging below the text baseline — at any `scale` other than 4. The bug surfaced on the `config.mlb_two_row_test.toml` "MLB Two-Row" title card (a `message` widget) running at `scale=2`, where the `:baseball:` emoji sits ~16 real px below the text line.

The fix anchors the hi-res sprite's **bottom to the text baseline in real pixels**, which is exact for any scale (not just divisors of the sprite's physical size). The low-res path and `scale=4` rendering are unchanged.

**Impact / who hits this:** narrow but real. `scale=1` (smallsign) uses the low-res path and is unaffected; `scale=4` (the default bigsign) is byte-identical. Only a `scale=2` config with inline hi-res emoji misaligns — e.g. two-row bigsign layouts, which need `scale=2`/`content_height=32` to fit their bands. Low frequency today, but every `scale=2` config with `:slug:` emoji in held text hits it.

## Root cause

`draw_with_emoji` (`src/led_ticker/pixel_emoji.py`) computes the inline emoji's top-row position as:

```python
iy_default = (y + y_offset) - 8
```

The `- 8` hardcodes an **8-logical-row** emoji height. A hi-res sprite is `physical_size` real pixels tall (32 for every current sprite). Painted on a `ScaledCanvas`, it occupies `physical_size / scale` logical rows:

- `scale=4`: `32 / 4 = 8` logical → `- 8` is correct, bottom lands on the baseline.
- `scale=2`: `32 / 2 = 16` logical → the sprite is 16 rows tall but anchored as if 8, so its bottom falls `8` logical rows (16 real px) **below** the baseline.

The same `- 8` assumption is duplicated at three explicit `emoji_y=baseline_y - 8` call sites (see "Redundant overrides" below).

### Why a logical-pixel fix is not arbitrary-scale

A logical-space correction (`emoji_logical_h = physical_size // scale`, then `iy = baseline - emoji_logical_h`) is only exact when `scale` divides `physical_size`. The painted sprite spans `physical_size` **real** rows, but `iy` is multiplied by `scale` (`real_y_anchor = iy_logical * scale + y_offset_real`), so floor division loses up to `scale - 1` real px:

| scale | `32 // scale` | bottom error |
|---|---|---|
| 4 | 8 (exact) | 0 |
| 2 | 16 (exact) | 0 |
| 3 | 10 (floors 10.67) | +2 real px |
| 5 | 6 (floors 6.4) | +2 real px |

Exact only at scales that divide 32 (1/2/4/8/16/32). Today's configs use 1/2/4, but the fix should be scale-agnostic.

## The fix: bottom-anchor in real pixels

Anchor the hi-res sprite so its bottom row lands on the baseline's **real** position, computed in real pixels:

```
real_top = baseline_logical * scale + y_offset_real - hires.physical_size
```

The sprite's last row is then at `baseline_logical * scale + y_offset_real`, i.e. exactly the text baseline, for **any** scale — no rounding.

### Coordinate-space rationale

- **Hi-res** sprites paint directly to the real canvas (`_draw_hires_emoji` → `real.SetPixel`), so their height is fixed in *real* pixels (`physical_size`). The logical→real multiplication (`iy_logical * scale`) is the lossy step; anchoring in real pixels removes it.
- **Low-res** (8×8) sprites paint through the wrapper's `SetPixel`, which block-expands uniformly, so they live in *logical* space. `iy = baseline_logical - 8` bottom-anchors an 8-logical-row sprite exactly at any scale (no real-pixel division). **Unchanged.**

### Top-clip is the expected trade-off at scale=2

A 32-real-px sprite bottom-anchored at the baseline extends 32 real px **up** from it. On a short canvas (`content_height=16`, `scale=2` → 32 real rows) with a high baseline, `real_top` can be small or negative, clipping the sprite's top at the panel edge. This is acceptable and intended: `_draw_hires_emoji`'s paint loop already guards `0 <= ry < real_h` (it `SetPixel`s only in-bounds), so it clips silently — it never wraps, errors, or paints out of bounds. Avoiding the clip is a *sizing* concern (non-goal #1), not an *alignment* concern. A test asserts the clipped case paints only in-bounds and does not raise.

### scale=4 is byte-identical

For every current sprite `physical_size = 32`. At `scale=4`:

- Old: `real_y_anchor = (baseline - 8) * 4 + y_off = baseline*4 - 32 + y_off`
- New: `real_top = baseline*4 + y_off - 32`

Identical. Only `scale != 4` rendering changes. This preserves the hardware-validated bigsign appearance.

## Component changes

### `_draw_hires_emoji` (pixel_emoji.py)

This is a private helper with **two callers**: `draw_with_emoji` (inline emoji) and `draw_emoji_at` (single-icon placement at a known (x, y), e.g. MLB team logos). Today it top-anchors at a logical `iy`:

```python
real_y_anchor = iy_logical * scale + y_offset_real
```

New contract — exactly one of two y-anchors is supplied (signature: `_draw_hires_emoji(canvas, hires, ix_logical, *, top_logical=None, bottom_baseline_logical=None)`):

- **`bottom_baseline_logical`** (inline default path): `real_y_anchor = bottom_baseline_logical * scale + y_offset_real - hires.physical_size` — bottom-anchors the sprite at the baseline, exact at any scale.
- **`top_logical`** (explicit-position callers): `real_y_anchor = top_logical * scale + y_offset_real` — existing top-anchor behavior, unchanged.

The `ix_logical` horizontal anchor is unchanged.

Both existing callers map to `top_logical` except `draw_with_emoji`'s default path:

- `draw_emoji_at` → `top_logical=y` (the caller specifies the icon's top position; behavior preserved exactly).
- `draw_with_emoji` explicit-`emoji_y` path → `top_logical=emoji_y` (two-row band placement; preserved).
- `draw_with_emoji` default path → `bottom_baseline_logical=(y + y_offset)` (the fix).

### `draw_with_emoji` (pixel_emoji.py)

In the per-emoji loop, the default (`emoji_y is None`) path:

- **hi-res:** call `_draw_hires_emoji(canvas, hires, ix, bottom_baseline_logical=(y + y_offset))`.
- **low-res:** `iy = (y + y_offset) - 8` (logical, unchanged), then paint as today.

When the caller passes an explicit `emoji_y`, the hi-res path uses `top_logical=emoji_y` (existing top-anchor) and the low-res path uses `iy = emoji_y` — both unchanged.

The pre-loop `iy_default = (y + y_offset) - 8` is removed; anchoring is decided per-emoji once the hi-res/low-res branch is known.

### Redundant overrides removed

Three call sites pass `emoji_y=baseline_y - 8` while also passing `y=baseline_y`, so they hand `draw_with_emoji` the exact value its default would compute — redundant today, and they bypass the fix. Remove the `emoji_y` argument at each so they route through the corrected default:

- `src/led_ticker/widgets/_image_base.py` — separator draw (~line 809) and text draw (~line 865)
- `src/led_ticker/widgets/two_row.py` — separator draw (~line 399)

After removal: `scale=4` unchanged (default computes the same `- 8`-equivalent); `scale=2` corrected.

### `draw_emoji_at` bottom-anchor mode (fifth site: weather)

`WeatherWidget` (`weather.py` ~line 185) draws its condition icon via `draw_emoji_at(canvas, slug, x, baseline_y - 8)` — the same `- 8` bug, but through the single-icon API rather than an `emoji_y` override, so it can't simply "drop the override." `draw_emoji_at` is top-anchor only.

Give `draw_emoji_at` the same two-mode treatment as `_draw_hires_emoji` — add a `bottom_baseline: int | None` keyword; exactly one of `y` (logical top, existing) or `bottom_baseline` (logical baseline; the icon's bottom anchors here, exact at any scale) must be supplied:

- hires + `bottom_baseline` → `_draw_hires_emoji(..., bottom_baseline_logical=bottom_baseline)`
- hires + `y` → `_draw_hires_emoji(..., top_logical=y)` (unchanged)
- low-res + `bottom_baseline` → top row = `bottom_baseline - 8` (8×8 sprite, logical, exact at any scale)
- low-res + `y` → top row = `y` (unchanged)

`measure_emoji_at` is width-only and unchanged, so weather's `measure_emoji_at`-based layout stays in sync. Weather then calls `draw_emoji_at(canvas, slug, x, bottom_baseline=baseline_y)` (drop the `- 8`). `draw_emoji_at` has no other callers, so this is its only consumer.

### Untouched

- **`draw_emoji_at` / single-icon placement** (e.g. MLB team logos): the caller supplies the icon's top position, so it keeps the top-anchor path (`top_logical=y`). Behavior preserved exactly.
- **Two-row band call sites** (`two_row.py` ~345/589/624): pass real per-band `emoji_y` (top position from `row_layout`) **and** `max_emoji_height`, which forces a low-res 8×8 fallback when a hi-res sprite would exceed the band. They keep the explicit top-anchor path and are **deliberately not baseline-corrected**: their `emoji_y` is a band-relative top, not a baseline, so the real-pixel bottom-anchor does not apply. In the rare case a hi-res sprite *fits* the band cap on an explicit-`emoji_y` path, it stays top-anchored at `emoji_y` (unchanged old behavior). This is in scope-by-omission: two-row band emoji placement is governed by `row_layout`, not this fix. The plan and any future reader should not assume band emoji are baseline-anchored.
- **Low-res rendering** at every scale.
- **Horizontal advance:** `HiResEmoji.logical_width(scale)` already ceil-divides and is consistent between `measure_width` and `draw_with_emoji` — already arbitrary-scale. No change.
- **`scale=1` (smallsign):** the canvas is not a `ScaledCanvas`, so `use_hires` is false and the low-res path runs. Unaffected.

## Non-goals

- **Emoji size relative to text.** At `scale=2` a correctly-anchored hi-res sprite (32 real px) is taller than ~25px text. This is expected (emoji are commonly larger than text) and out of scope; this spec only fixes vertical *alignment*, not sizing. No new `max_emoji_height` defaults.
- **Vertical-centering semantics.** Emoji stay bottom-anchored to the baseline (matches `scale=4`); we do not switch to center-on-text, which would change the validated `scale=4` look.
- **The series title and other full-name matchup rendering** — unrelated to emoji.

## Testing

### Regression (`tests/test_pixel_emoji.py`)

**Sprite metric — do NOT assume the sprite fills to row 31.** Current hires sprites (`baseball`, `moon`, `sun`) have `physical_size=32` but their lowest *lit* pixel is at `py=30` (auto-trim removes unlit columns, not rows, and the source art leaves the bottom row blank). So the lowest lit real row is `real_top + max_py`, where `real_top = baseline*scale + y_offset_real - physical_size`. Tests derive the expected row from the sprite's own pixels — `max_py = max(py for _,py,*_ in sprite.pixels)` — rather than hardcoding `-1`. The baseline-relative gap is `physical_size - max_py` (currently 2) and is **scale-invariant** — that invariance is the property under test. Choose a baseline with headroom so the sprite isn't top-clipped (test 3b covers clipping).

Define a helper in the test: `expected_bottom(baseline, scale, y_off, sprite) = baseline*scale + y_off - sprite.physical_size + max_py(sprite)`.

1. **`scale=2` bottom-anchor:** render the chosen hi-res emoji on a `scale=2` `ScaledCanvas` at a known logical baseline; assert the lowest lit real row equals `expected_bottom(...)` exactly, NOT ~16 real px below. Fails before the fix, passes after.
2. **Cross-scale invariant (sprite-agnostic):** render the same emoji at the same logical baseline on `scale=2` and `scale=4`; assert the baseline-relative gap `(baseline*scale + y_offset_real) - lowest_lit_real_row` is **equal** in both. The buggy `-8` anchor makes the scale=2 gap larger, so this directly catches the regression without depending on sprite metrics.
3. **Arbitrary scale (scale=3):** render at `scale=3`; assert the lowest lit real row equals `expected_bottom(baseline, 3, y_off, sprite)` exactly — proves the real-pixel anchor is exact where logical floor-division (`32 // 3 = 10`) would place the bottom 2 real px low.
3b. **Top-clip safety (scale=2, short canvas):** render the emoji at a low baseline on a `content_height=16` `scale=2` canvas so `real_top < 0` (e.g. `baseline=4`: `real_top = 4*2 + 16 - 32 = -8`); assert `draw_with_emoji` does not raise and paints no pixel outside `0 <= ry < real_h` (the sprite clips at the top, never wraps).
4. **scale=4 preserved:** the existing `test_hires_moon_paints_real_canvas_at_physical_resolution` (and siblings) must still pass unchanged — guards against any drift in the validated `scale=4` path.

### Call-site regression

5. The de-redundified `_image_base` (separator + text) and `two_row` (separator) paths keep their existing tests green; add a `scale=2` hi-res emoji assertion on one image/two-row text path mirroring test #1, to lock the call-site fix.

### Low-res guard

6. Low-res path (`scale=1` / no `ScaledCanvas`): an inline emoji still bottom-anchors at `baseline - 8` logical — assert an existing low-res position test still passes (e.g. `test_hires_falls_back_to_lowres_on_real_canvas`).

### `draw_emoji_at` preserved

7. Single-icon placement keeps top-anchor: render `draw_emoji_at(sc, slug, x, y)` and assert the sprite's top real row is `y * scale + y_offset_real` (unchanged) — the signature change must not shift single-icon placement (MLB logos). Construct the `ScaledCanvas` with a real height that yields a **non-zero `y_offset_real`** (i.e. `content_height * scale < real_height`) so the assertion isn't tautological at offset 0.

## Files affected

| File | Change |
|---|---|
| `src/led_ticker/pixel_emoji.py` | `_draw_hires_emoji` bottom-anchor mode; `draw_with_emoji` per-emoji anchor (hi-res real-pixel bottom-anchor, low-res logical `- 8`); remove pre-loop `iy_default`. |
| `src/led_ticker/widgets/_image_base.py` | Remove redundant `emoji_y=baseline_y - 8` at the separator and text draws. |
| `src/led_ticker/widgets/two_row.py` | Remove redundant `emoji_y=baseline_y - 8` at the separator draw. |
| `src/led_ticker/pixel_emoji.py` (`draw_emoji_at`) | Add `bottom_baseline` keyword (two-mode anchor); fixes the fifth site. |
| `src/led_ticker/widgets/weather.py` | Use `draw_emoji_at(..., bottom_baseline=baseline_y)`; drop the `- 8`. |
| `tests/test_pixel_emoji.py` | Regression + cross-scale + arbitrary-scale (scale=3) + preserved-scale-4 tests. |
| `tests/test_widgets/test_image_base.py` / `test_two_row.py` | Call-site `scale=2` hi-res anchor assertion (one each, if a clean harness exists). |
| `CLAUDE.md` | Update the inline-emoji invariant note to state the anchor is real-pixel bottom-anchored (was the `iy = y - 8` 8-row assumption). |

## Acceptance criteria

- All new tests pass; existing `scale=4` emoji tests unchanged and green.
- `make test`, `make lint`, `make typecheck` clean.
- `make validate CONFIG=config/config.mlb_two_row_test.toml` clean (no behavioral config change; the title `:baseball:` now renders baseline-aligned).
- Hardware: on the bigsign two-row config (`scale=2`), the title-card `:baseball:` emoji sits inline with the text.
