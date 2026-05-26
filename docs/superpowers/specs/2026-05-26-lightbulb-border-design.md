# Design: `LightbulbBorder` — marquee-style discrete-bulb border

**Date:** 2026-05-26
**Status:** Approved (brainstorm), pending spec review → implementation plan

## Problem

The existing `BorderEffect` family (`RainbowChaseBorder`, `ColorCycleBorder`, `ConstantBorder`) all paint a **continuous 1- or 2-pixel-wide ring** around the panel perimeter. They animate by varying hue/value along the ring. None of them produce the **discrete-bulb marquee look** — that classic Vegas / theater-front aesthetic where individual lightbulb shapes are spaced around the perimeter and turn on/off in patterns.

This is intentionally a different visual language from the existing borders. Continuous rings read as "outline" or "halo"; discrete bulbs read as "physical object." The bigsign's 256×64 physical resolution is large enough to make individual 3×3 bulb sprites legible, which makes this aesthetic feasible.

## Goal / non-goals

**Goal:** a new `BorderEffect` class that paints discrete `N×N` bulb sprites around the panel perimeter, with three classic-marquee animation modes (chase, alternate, unison).

**Non-goals:**
- Random sparkle / stage-marquee twinkle (deliberately deferred — easy follow-up)
- Bulb glow / halo / anti-aliasing
- Per-edge speed control (different chase speeds on top vs sides)
- A new TOML widget surface — this is just a new `border = ...` style

## Design

### Bulb placement

New class `LightbulbBorder` in `src/led_ticker/borders.py` alongside the existing three. Same `BorderEffect` protocol; same `BorderEffectBase` enforcement; paints at PHYSICAL resolution via `unwrap_to_real`.

**Anchoring:** each bulb is an `N×N` square anchored by its **top-left corner** at `(x0, y0)`. The bulb occupies pixels `(x0..x0+N-1, y0..y0+N-1)`. Top-left anchoring (vs. center) means `bulb_size` can be even — 2×2 has no center pixel, but its top-left corner is well-defined.

**`bulb_size` default** — when omitted from TOML, auto-detect based on physical panel height:
- `panel_h_real ≥ 32` → `bulb_size = 3` (bigsign and any other big-class panel)
- `panel_h_real < 32` → `bulb_size = 1` (smallsign auto-fallback)

The threshold (32) is chosen to cleanly separate the two reference builds (bigsign h=64, smallsign h=16) while leaving headroom for hypothetical mid-size panels.

**Placement formula** — for an `N×N` bulb with stride `S = N + gap`, walking clockwise from top-left:

| Position | corner / edge | `(x0, y0)` |
| --- | --- | --- |
| 1 | top-left corner | `(0, 0)` |
| 2..M+1 | top edge (between corners) | `(S, 0)`, `(2S, 0)`, ... last bulb has `x0 + N ≤ w - N` |
| M+2 | top-right corner | `(w-N, 0)` |
| ... | right edge (between corners) | `(w-N, S)`, `(w-N, 2S)`, ... |
| ... | bottom-right corner | `(w-N, h-N)` |
| ... | bottom edge (right-to-left) | `(w-N-S, h-N)`, `(w-N-2S, h-N)`, ... |
| ... | bottom-left corner | `(0, h-N)` |
| ... | left edge (bottom-to-top) | `(0, h-N-S)`, `(0, h-N-2S)`, ... |

Corner bulbs are included exactly once each. The list is built clockwise so the chase animation naturally walks clockwise without an explicit direction transform (the `direction = "ccw"` knob negates the step instead).

**Caching** — placement is a pure function of `(panel_w, panel_h, bulb_size, gap)` and never changes per frame. Wrap in `@functools.cache` keyed on that tuple (same pattern as `_perimeter_pixels`).

**Bulb count for sample configs** (counts computed from the formula `4 corners + 2*top_count + 2*right_count` where `top_count = floor((w - 2*N - gap - (N+gap))/stride) + 1` etc; recompute exactly during implementation — the `test_lightbulb_bulb_count_bigsign_3x3` tripwire pins the exact value):

| Panel | bulb_size | gap | stride | approx total bulbs |
| --- | --- | --- | --- | --- |
| Bigsign 256×64 | 3 | 3 | 6 | ~100 |
| Bigsign 256×64 | 2 | 2 | 4 | ~155 |
| Bigsign 256×64 | 5 | 3 | 8 | ~75 |
| Smallsign 160×16 | 1 | 1 | 2 | ~170 |
| Smallsign 160×16 | 1 | 3 | 4 | ~85 |

### Animation modes

`paint()` dispatches on `self.mode`. Shared structure: read precomputed bulb list, derive a per-frame "lit-set" mask, fill lit bulbs with `lit_color`, fill unlit bulbs with `unlit_color`. Both colors are always painted per frame — no expectation that "off" pixels are black.

**Unified speed knob:** `speed_frames` (int, frames per state transition). Higher = slower. Per-mode defaults:

| Mode | default `speed_frames` | corresponds to (at 50ms tick) |
| --- | --- | --- |
| chase | 2 | advance 1 bulb every ~100ms; ~10s full revolution on bigsign-default |
| alternate | 5 | toggle every ~250ms |
| unison | 8 | blink every ~400ms |

Phase advancement is identical for all modes:
```python
phase = frame_count // self.speed_frames
```

**Chase mode**
- Extra knobs: `direction` (`"cw" | "ccw"`, default `"cw"`), `chase_density` (int ≥ 1, default 3 — meaning every 3rd bulb is lit)
- Lit-set logic:
  ```python
  step = phase if direction == "cw" else -phase
  for idx, bulb in enumerate(bulbs):
      is_lit = ((idx - step) % chase_density) == 0
  ```
- With 106 bulbs and `chase_density=3`, ~35 bulbs are lit at any moment, forming a clockwise traveling-light pattern (classic marquee chase).

**Alternate mode**
- No extra knobs
- Lit-set logic:
  ```python
  flip = phase % 2
  for idx, bulb in enumerate(bulbs):
      is_lit = ((idx + flip) % 2) == 0
  ```
- Half the bulbs lit at any time; toggles on each phase advance. Looks like a shimmer / twinkle without directional motion.

**Unison mode**
- No extra knobs
- Lit-set logic:
  ```python
  all_lit = (phase % 2) == 0
  ```
- All bulbs share state. Classic Vegas attention-grabber blink.

**`_paint_bulb` helper** (private, in `LightbulbBorder`):
```python
def _paint_bulb(real, x0, y0, size, rgb):
    r, g, b = rgb
    for dy in range(size):
        for dx in range(size):
            real.SetPixel(x0 + dx, y0 + dy, r, g, b)
```
Collapses to a single `SetPixel` call for `size=1` (smallsign fallback). No special-casing.

### Class attributes

```python
class LightbulbBorder(BorderEffectBase):
    frame_invariant: bool = False    # all 3 modes animate per-frame
    restart_on_visit: bool = False   # phase is continuous across loop_count visits
```

Same `BorderEffectBase` enforcement as the other animated borders. Same fast-path predicate behavior — `False` → image widgets cannot fast-path-freeze.

### TOML surface

Extends the existing `border = ...` field. New style string, new shorthand:

```toml
# Shorthand: defaults mode="chase", auto bulb_size, per-mode default speed_frames
border = "lightbulbs"

# Inline table: full control
border = { style = "lightbulbs",
           mode = "chase",                # "chase" | "alternate" | "unison"
           bulb_size = 3,                 # optional; auto from panel_h_real if omitted
           gap = 3,                       # pixels between bulb edges; default 3
           lit_color = [255, 220, 140],   # warm white default
           unlit_color = [40, 20, 0],     # dim warm-orange default
           speed_frames = 2,              # mode-dependent default if omitted
           chase_density = 3,             # default 3; only used by mode="chase"
           direction = "cw" }             # default "cw"; only used by mode="chase"
```

Added to the existing `border` accept-list on `message` / `countdown` / `two_row` / `gif` / `image` widgets. No other widget types accept `border` today — no surface widening.

### Validation rules (`validate.py`)

New rule numbers — verify next-available during implementation.

| Rule | Severity | Trigger | Fix message |
| --- | --- | --- | --- |
| NN-1 | error | `bulb_size` not a positive int | "set `bulb_size` to a positive integer, or omit it for the panel-size auto-default" |
| NN-2 | error | `bulb_size > min(panel_w, panel_h) // 2` | "bulb_size=X exceeds max=Y for a WxH panel; reduce or omit" |
| NN-3 | error | `mode` not in `{"chase", "alternate", "unison"}` | did-you-mean hint |
| NN-4 | error | `direction` not in `{"cw", "ccw"}` (only when `mode="chase"`) | "direction must be `cw` or `ccw`" |
| NN-5 | error | `chase_density < 1` (only when `mode="chase"`) | "set chase_density ≥ 1" |
| NN-6 | error | `gap < 0` | "gap must be ≥ 0 (bulbs would overlap)" |
| NN-7 | warning | `chase_density` set when `mode != "chase"` | "field ignored — only used in chase mode" |
| NN-8 | warning | `direction` set when `mode != "chase"` | "field ignored — only used in chase mode" |

### Integration

- **`borders.py`** — add the new class; export
- **`app/coercion.py`** (or wherever `_coerce_border` lives) — recognize `style = "lightbulbs"` in the table form and the bare shorthand string `"lightbulbs"`
- **No widget changes** — `BorderEffect` is consumed polymorphically; the new class drops in
- **No `_FrameAware` changes** — `restart_on_visit = False` matches the established animated-border pattern
- **No image-widget fast-path changes** — `frame_invariant = False` (always); the existing predicate correctly forces per-tick redraws

### Testing

Tripwires (in `tests/test_borders.py` or its current home):

- **`test_lightbulb_bulb_count_bigsign_3x3`** — sample `(w=256, h=64, bulb_size=3, gap=3)` returns exactly the expected count (~106; exact number derived from the formula). Catches off-by-ones in corner / edge math.
- **`test_lightbulb_auto_bulb_size_smallsign`** — construct with `bulb_size=None` for a 16-tall panel, assert `_bulb_size == 1`. Mirror with 64-tall asserting 3.
- **`test_lightbulb_chase_advances_with_frame`** — paint at `frame=0` and `frame=speed_frames`, assert the lit-set rotated by exactly 1 bulb position clockwise. Catches direction / phase bugs.
- **`test_lightbulb_chase_ccw_reverses`** — same with `direction="ccw"`, lit-set should rotate the opposite direction.
- **`test_lightbulb_alternate_toggles`** — `frame=0` and `frame=speed_frames` produce complementary lit-sets (XOR of the two is the full bulb set).
- **`test_lightbulb_unison_blinks`** — `frame=0` paints with `lit_color`, `frame=speed_frames` paints with `unlit_color`. All bulbs share state.
- **`test_lightbulb_paints_at_physical_resolution_on_scaled_canvas`** — via a stub `ScaledCanvas`, verify `paint()` calls `unwrap_to_real(canvas).SetPixel`, NOT the wrapper. Mirror of the existing physical-resolution tripwires on the other border classes.
- **Validation tests** (in `tests/test_validate.py` or its home):
  - `test_validate_lightbulb_bulb_too_large` — `bulb_size=8` on 16-tall panel raises rule NN-2 with the actual ceiling in the message.
  - `test_validate_lightbulb_unknown_mode` — `mode="wave"` raises rule NN-3 with did-you-mean hint.
  - `test_validate_lightbulb_direction_on_non_chase` — `mode="unison"` + `direction="ccw"` emits rule NN-8 warning.

### Docs

- **`docs/site/src/content/docs/concepts/borders.mdx`** — add a `lightbulbs` section covering the 3 modes, with the field table, default values, and a per-mode descriptive paragraph. The page already documents the existing `rainbow_chase` / `color_cycle` / constant border styles; mirror that structure.
- **`docs/site/src/content/docs/pitfalls.mdx`** — add entries for rules NN-1 through NN-8 in the rules table, with the same severity / quick-fix columns as the existing rules.
- No new top-level docs page — `lightbulbs` is a style under the existing `border` concept, not a standalone tool.

## Out of scope (deliberately)

- Random sparkle mode (easy to add later — same architecture, just a different `is_lit` formula seeded by `frame_count`)
- Bulb glow / halo (would require non-uniform per-pixel intensity inside a bulb sprite; not worth the complexity for the marquee aesthetic)
- Per-edge speed control
- Variable per-bulb color (3rd color field `lit_color_alt`)
- Anything special on smallsign beyond the auto 1×1 fallback

## Verification plan

**On the dev laptop:**
- `make lint` clean
- `make test` clean — new tripwires pass, no regression on the existing 2101-test suite
- `make docs-build` and `make docs-lint` clean — new docs section parses and lints

**Manual visual on bigsign (longboi or showroom):**
- Construct a test config that uses `border = "lightbulbs"` on a `message` widget; verify default chase animation looks right
- Switch `mode = "alternate"` and `mode = "unison"`, verify each looks right
- Try custom colors (e.g. `lit_color = [255, 0, 0]`, `unlit_color = [60, 0, 0]` — red marquee)
- Try `bulb_size = 5` and verify the larger bulbs render correctly
- Test on a section with `loop_count > 1` — verify phase is continuous across visits (`restart_on_visit = False`)
- Test transitions between widgets where one has the lightbulb border and one doesn't — verify the border disappears cleanly during the transition (existing `run_transition` machinery handles this)
