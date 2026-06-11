# `ColorBandsBorder` (`style = "bands"`) — Design

**Date:** 2026-06-11
**Status:** Approved (brainstorm with James)

## Summary

A new core `BorderEffect`: discrete solid-color bands marching around the
panel perimeter. The geometry of `RainbowChaseBorder` (continuous per-pixel
perimeter walk via `_perimeter_pixels`, no bulb sprites) but with a
user-supplied list of solid colors instead of a continuous hue ramp.
Candy-cane / barber-pole / flag-tricolor ribbons around the panel edge.

Lives in core (`src/led_ticker/borders.py`), not a plugin.

## TOML surface

```toml
# named palette shorthand
border = {style = "bands", colors = "candy_cane"}

# explicit list: italy, wider bands, slow reverse march
border = {style = "bands", colors = [[0,146,70], [255,255,255], [206,43,55]], band_width = 8, speed = -1}
```

| Field | Type | Default | Notes |
|---|---|---|---|
| `colors` | list of `[r,g,b]` OR palette name string | **required** | list: ≥ 2 entries; bands repeat in list order clockwise. String: named palette from `BAND_PALETTES` |
| `band_width` | int ≥ 1 | `6` | perimeter pixels per band |
| `speed` | int | `1` | perimeter px the pattern advances per 50 ms frame; negative reverses; `0` = static bands |
| `thickness` | int | `1` | concentric rings, same as other borders |
| `align_rings` | bool | `false` | at `thickness > 1`: radially align band boundaries across rings (stacked stripes) instead of the continuous-index woven look |

**No string shorthand.** `colors` is the essence of the effect and has no
sensible default, so the effect is table-only (precedent: `constant`).
Bare `border = "bands"` needs no special-case code: the string path's
generic `_BORDER_REGISTRY` fallback runs `_build_plugin_style`, which
introspects the constructor and raises
`ValueError("border style 'bands' missing required keys ['colors']")` —
already the right error.

**Color spec: explicit list or named palette** — no `from`/`to`.
`from`/`to` arc semantics stay exclusive to `rainbow` / `color_cycle`;
a quantized-gradient generator was considered and dropped (YAGNI).
Unknown keys (including `from`/`to`) get the standard unknown-keys error.

### Named palettes

`colors` accepts a palette-name string, resolved at coercion time into the
same RGB-tuple list as the explicit form (single code path after coercion).
Registry: `BAND_PALETTES: dict[str, list[tuple[int, int, int]]]` in
`borders.py` (sibling of `_BORDER_REGISTRY`; distinct from `colors.py`'s
`lazy_palette`, which maps name → single color). Unknown palette names
raise ValueError listing `sorted(BAND_PALETTES)`. Saturated primaries read
best on the panels; black is invisible, so palettes exclude it.

| Name | Colors |
|---|---|
| `rainbow` | red `[255,0,0]`, orange `[255,128,0]`, yellow `[255,255,0]`, green `[0,255,0]`, blue `[0,0,255]`, purple `[128,0,255]` — discrete ROYGBIV bands (vs. the continuous `style = "rainbow"` chase) |
| `rasta` | red `[255,0,0]`, gold `[255,191,0]`, green `[0,255,0]` |
| `usa` | red `[255,0,0]`, white `[255,255,255]`, blue `[0,0,255]` |
| `christmas` | red `[255,0,0]`, green `[0,255,0]` |
| `halloween` | orange `[255,100,0]`, purple `[128,0,255]` |
| `candy_cane` | red `[255,0,0]`, white `[255,255,255]` |

## Effect class

`ColorBandsBorder(BorderEffectBase)` in `src/led_ticker/borders.py`,
registered as `"bands"` in `_BORDER_REGISTRY`.

- `colors` materialized to plain `(r, g, b)` tuples at construction
  (hot-loop friendly, same trick as `ConstantBorder`).
- Paint loop:

  ```python
  real = unwrap_to_real(canvas)
  offset = frame_count * self.speed
  for idx, (x, y) in enumerate(_perimeter_pixels(real.width, real.height, self.thickness)):
      band = ((idx - offset) // self.band_width) % len(self._colors)
      r, g, b = self._colors[band]
      real.SetPixel(x, y, r, g, b)
  ```

  Positive `speed` marches the pattern clockwise. Python floor division
  gives correct wraparound for negative offsets.
- `frame_invariant` is a **dynamic property**: `self.speed == 0` — same
  shape as `RainbowChaseBorder`. Static bands ride the image-widget
  static-text fast path; animated bands are forced through the per-tick
  loop (see the fast-path contract in the `borders.py` module docstring).
- `restart_on_visit = False` — continuous march across `loop_count`
  boundaries within a section, like the other animated borders.
- `thickness = 2`, default: perimeter index continues from the outer ring
  into the inner ring (same continuous enumeration `RainbowChaseBorder`
  uses). Bands will not align ring-to-ring — reads as a woven texture.
- `align_rings = true` (bool, default `false`; added post-review on
  2026-06-11): paints each ring with its own enumeration, scaling each
  ring-local index to outer-ring units before the band formula —
  `eff_idx = (j * outer_len + ring_len // 2) // ring_len` (integer
  rounding). Both rings start band 0 at the top-left corner and march at
  the same angular speed, so band boundaries stay radially aligned: crisp
  stacked stripes instead of the woven default. A no-op at
  `thickness = 1`. Requires a `_ring_lengths(width, height, thickness)`
  cached helper whose collapse-bail logic MUST mirror `_perimeter_pixels`
  (tripwire test asserting the two stay consistent).
- Paints at PHYSICAL resolution via `unwrap_to_real` — a 1 px border is
  1 real LED on bigsign.

## Coercion (`_coerce_border` in `app/coercion.py`)

- Registry entry `"bands": ColorBandsBorder`; new `case "bands":` arm in
  the inline-table match.
- Allowed keys: `{colors, band_width, speed, thickness}`; unknown keys
  rejected with the standard sorted-keys message.
- `colors` validation:
  - missing → ValueError naming the required key with an example
  - string → resolved via `BAND_PALETTES`; unknown name → ValueError
    listing available palettes
  - non-list/non-string / empty → ValueError
  - exactly 1 entry → ValueError with hint "use border = [r, g, b] instead"
  - each list entry through `_validate_rgb` (rejects bools, out-of-range,
    wrong shape)
- `band_width`: int ≥ 1, bool excluded.
- `speed`: int, bool excluded, `0` allowed (static — unlike `color_cycle`,
  where `speed=0` is rejected, static bands are a meaningful pattern with
  no simpler equivalent spelling).

No widget-side changes: the `border` field already exists on `message`,
`countdown`, `two_row`, `gif`, `image` and dispatches through the shared
coercion, so `bands` works on all five for free.

## Tests

In `tests/test_borders.py` (effect behavior) and the existing border
coercion test module, following the current tripwire style:

- **Pattern correctness**: at `frame=0`, first `band_width` perimeter
  pixels are color 0, next `band_width` are color 1, wraps modulo
  `len(colors)`.
- **Motion**: frame advance shifts the pattern by exactly `speed` px;
  negative speed shifts the opposite way; `speed=0` produces identical
  output across frames.
- **Flags**: `frame_invariant` True iff `speed == 0`;
  `restart_on_visit` is False.
- **Physical resolution**: paints through `ScaledCanvas` to the real
  canvas (mirrors `TestImageBorderPhysicalResolution`).
- **Fast-path gate**: image widget with bands `speed=0` takes the
  static fast path; `speed=1` is forced through the per-tick loop.
- **Thickness**: `thickness=2` paints both rings.
- **Coercion matrix**: valid table; missing `colors`; 1-entry `colors`
  (hint message); empty/non-list `colors`; invalid RGB entry; unknown
  keys; bool `speed`/`band_width` rejection; bare string `"bands"`
  raises the missing-required-keys error from `_build_plugin_style`.
- **Palettes**: each named palette resolves (`colors = "rasta"` builds
  with the registry's tuples); unknown palette name raises listing
  available; every `BAND_PALETTES` entry has ≥ 2 colors and valid
  0–255 components (registry sanity tripwire).

## Docs + housekeeping

- Docs-site borders concept page (`/concepts/borders/`) gets a `bands`
  section per `docs/DOCS-STYLE.md`, with palette-shorthand and explicit-
  list TOML examples, the field table, and the named-palette table.
- Preview asset rendered via the render-demo tooling — PNG/GIF to `/tmp`
  for review before committing.
- `borders.py` module docstring: "Four flavors today" → five, with a
  `ColorBandsBorder` bullet.
- CLAUDE.md package-layout line for `borders.py` updated to include the
  new class.

## Delivery

Feature branch + PR (no direct-to-main). Staged commits:
effect class → coercion → tests → docs/preview.
