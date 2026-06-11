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
# candy cane
border = {style = "bands", colors = [[255,0,0], [255,255,255]]}

# italy, wider bands, slow reverse march
border = {style = "bands", colors = [[0,146,70], [255,255,255], [206,43,55]], band_width = 8, speed = -1}
```

| Field | Type | Default | Notes |
|---|---|---|---|
| `colors` | list of `[r,g,b]` | **required** | ≥ 2 entries; bands repeat in list order clockwise |
| `band_width` | int ≥ 1 | `6` | perimeter pixels per band |
| `speed` | int | `1` | perimeter px the pattern advances per 50 ms frame; negative reverses; `0` = static bands |
| `thickness` | int | `1` | concentric rings, same as other borders |

**No string shorthand.** `colors` is the essence of the effect and has no
sensible default, so the effect is table-only (precedent: `constant`).
Bare `border = "bands"` needs no special-case code: the string path's
generic `_BORDER_REGISTRY` fallback runs `_build_plugin_style`, which
introspects the constructor and raises
`ValueError("border style 'bands' missing required keys ['colors']")` —
already the right error.

**Color spec is the `colors` list only** — no `from`/`to`, no named-string
entries. `from`/`to` arc semantics stay exclusive to `rainbow` /
`color_cycle`; a quantized-gradient generator was considered and dropped
(YAGNI). Unknown keys (including `from`/`to`) get the standard
unknown-keys error.

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
- `thickness = 2`: perimeter index continues from the outer ring into the
  inner ring (same continuous enumeration `RainbowChaseBorder` uses).
  Bands will not perfectly align ring-to-ring; accepted for consistency
  and simplicity.
- Paints at PHYSICAL resolution via `unwrap_to_real` — a 1 px border is
  1 real LED on bigsign.

## Coercion (`_coerce_border` in `app/coercion.py`)

- Registry entry `"bands": ColorBandsBorder`; new `case "bands":` arm in
  the inline-table match.
- Allowed keys: `{colors, band_width, speed, thickness}`; unknown keys
  rejected with the standard sorted-keys message.
- `colors` validation:
  - missing → ValueError naming the required key with an example
  - non-list / empty → ValueError
  - exactly 1 entry → ValueError with hint "use border = [r, g, b] instead"
  - each entry through `_validate_rgb` (rejects bools, out-of-range,
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

## Docs + housekeeping

- Docs-site borders concept page (`/concepts/borders/`) gets a `bands`
  section per `docs/DOCS-STYLE.md`, with candy-cane and tricolor TOML
  examples and the field table.
- Preview asset rendered via the render-demo tooling — PNG/GIF to `/tmp`
  for review before committing.
- `borders.py` module docstring: "Four flavors today" → five, with a
  `ColorBandsBorder` bullet.
- CLAUDE.md package-layout line for `borders.py` updated to include the
  new class.

## Delivery

Feature branch + PR (no direct-to-main). Staged commits:
effect class → coercion → tests → docs/preview.
