# Rainbow lightbulbs + docs uplift — design

**Date:** 2026-05-28
**Status:** Approved (brainstorming complete)
**Area:** `src/led_ticker/borders.py`, `app/coercion.py`, `validate.py`, `docs/site/.../concepts/borders.mdx`, pinned demos

## Summary

Add a **rainbow coloring option** to the existing `LightbulbBorder` and bring its
documentation up to parity with the other three border styles (gifs + a
"Common patterns" subsection).

The rainbow option is a *coloring* choice, fully orthogonal to the existing
`mode` knob (`chase` / `alternate` / `unison`). When a bulb is lit, its color
comes from a hue fixed to that bulb's clockwise perimeter position; the hue is
**static in space** (it does not rotate over time). The lit/unlit pattern still
animates via `mode`, so `chase` reads as a traveling lit-window sweeping over a
fixed string of colored bulbs — the classic party-/Christmas-lights look.

## Part 1 — Feature

### User-facing config surface

Opt in by setting the existing `lit_color` field to the string sentinel
`"rainbow"`:

```toml
# Simplest — rainbow chase
border = { style = "lightbulbs", mode = "chase", lit_color = "rainbow" }

# Two full spectra tiled around the ring
border = { style = "lightbulbs", lit_color = "rainbow", hue_wraps = 2 }
```

- `lit_color` accepts its existing `[r, g, b]` list **or** the string `"rainbow"`.
- New `hue_wraps` (float, default `1.0`): number of full spectra tiled around
  the perimeter. Hue for bulb `i` of `N` total bulbs:

  ```
  hue = (i / N) * 360 * hue_wraps   (mod 360)
  ```

  `hue_wraps = 1.0` wraps one complete rainbow once around the whole perimeter
  (adjacent bulbs differ subtly). Higher values tile more rainbows / widen
  per-bulb contrast.
- `unlit_color` is unchanged and still paints the off-bulbs (dim warm-orange
  default), so off-bulbs glow like unpowered incandescents regardless of the
  rainbow setting.

### Code changes

**`src/led_ticker/borders.py` — `LightbulbBorder`**

- `__init__`: widen `lit_color` to `tuple[int, int, int] | str`. If the value is
  the string `"rainbow"`, set `self._rainbow_lit = True` (and leave the stored
  `lit_color` as a harmless sentinel / unused for lit bulbs). Otherwise
  `self._rainbow_lit = False` and behavior is unchanged. Add parameter
  `hue_wraps: float = 1.0`, stored as `self.hue_wraps`.
- `paint`: when a bulb `is_lit` and `self._rainbow_lit`, compute the per-bulb
  hue from its index and the total bulb count (`len(positions)`) using the
  formula above and `hue_color(hue)` (already imported from `color_lut`).
  Materialize to an `(r, g, b)` tuple and pass to `_paint_bulb`. When not
  rainbow, the existing `lit_color` path runs verbatim. Unlit bulbs always use
  `unlit_color`.
- `frame_invariant` stays `False` (the lit/unlit pattern always animates — even
  `unison` blinks). No fast-path predicate change.
- Update the class docstring to document the rainbow option.

**`src/led_ticker/app/coercion.py` — `"lightbulbs"` case**

- Add `"hue_wraps"` to the `allowed` keys set.
- Allow `lit_color == "rainbow"` to pass through untouched (skip
  `_validate_rgb` only for that exact sentinel string). Any other `lit_color`
  value still goes through `_validate_rgb`.

**`src/led_ticker/validate.py` — `_check_lightbulb_border`**

- **Rule 50 (error):** `hue_wraps`, when set, must be a number (`int`/`float`,
  not `bool`) and `> 0`.
- **Rule 51 (warning, dead-knob):** `hue_wraps` set while `lit_color != "rainbow"`
  is ignored — warn, mirroring the existing rules 48/49 dead-knob warnings for
  `chase_density` / `direction` on non-chase modes.
- (`lit_color = "rainbow"` itself needs no new range rule — coercion accepts the
  sentinel and rejects any other non-RGB value.)

### Tests

`tests/test_borders.py` (and `tests/test_validate.py` for rules):

- Rainbow lit bulbs receive distinct hues spread around the ring; bulb 0 differs
  from a bulb a quarter-way around.
- `hue_wraps = 2` produces two full spectra (a bulb halfway around repeats
  bulb 0's hue region).
- Unlit bulbs still paint `unlit_color` in rainbow mode.
- Rainbow composes with each `mode` (`chase` / `alternate` / `unison`): the lit
  *set* matches the non-rainbow behavior for the same frame; only lit colors
  differ.
- Coercion: `lit_color = "rainbow"` builds a `LightbulbBorder` with
  `_rainbow_lit = True`; a junk string (`"banana"`) for `lit_color` still raises;
  `hue_wraps` is accepted and stored.
- Validation: Rule 50 rejects `hue_wraps = 0`, negative, and non-numeric; Rule 51
  warns when `hue_wraps` is set without `lit_color = "rainbow"`.

## Part 2 — Docs uplift

User-facing page: `docs/site/src/content/docs/concepts/borders.mdx`
(the "Lightbulbs" section, currently lines ~212–254 — the only border style
with no demo gif and no "Common patterns" subsection).

### New pinned demos + gifs (4)

Follow the existing pinned-demo convention:
`docs/site/demos-pinned/<slug>.toml` rendered to
`docs/site/public/demos-pinned/<slug>.gif`.

| slug | shows |
|---|---|
| `border-lightbulbs-chase` | warm-white chase (flagship marquee) |
| `border-lightbulbs-alternate` | even/odd twinkle |
| `border-lightbulbs-unison` | all-blink |
| `border-lightbulbs-rainbow` | new `lit_color = "rainbow"` static party-lights |

- Render each via the `making-a-gif` skill to get a correct `--duration` —
  lightbulb cycles need enough frames to show a full chase revolution / a couple
  of blink cycles.
- Render at bigsign scale so the 3×3 bulbs are clearly visible.

### `borders.mdx` section rewrite

- Add a `<DemoGif>` under each mode bullet in the **Modes** list
  (chase / alternate / unison), giving the section visuals like the other three
  styles.
- New **Rainbow bulbs** subsection documenting `lit_color = "rainbow"` and
  `hue_wraps`, with the rainbow gif.
- New **Common patterns** subsection (same structure as the rainbow /
  color_cycle "Common patterns" blocks), covering exactly three patterns:
  1. **Vegas / theatrical marquee** — warm-white `chase`, tuned `speed_frames`
     and `chase_density`.
  2. **Rainbow party lights** — `lit_color = "rainbow"`, calm static colored
     string.
  3. **Holiday / themed two-color** — `lit_color` + `unlit_color` palette
     (e.g. red/green) with `alternate` or `unison`.
- Update the full-table-form example to include `hue_wraps`, and keep the
  in-prose defaults list (`mode`, `bulb_size`, `gap`, …) in sync with the new
  `hue_wraps = 1.0` default.
- Update the top-of-page description / style table note if needed (the intro
  currently frames the page around the original three styles).

### Drift checks

`test_docs_config_options_drift.py` audits `[display]` defaults and per-section
field sets, not border sub-knobs — so no doc-drift test breaks. Keep the
documented defaults list aligned with `coercion.py` by hand.

## Out of scope (YAGNI)

- Time-rotating rainbow hues (explicitly chose "static in space").
- A dedicated `mode = "rainbow"` (rainbow is a coloring option, not a mode).
- Per-bulb rainbow on the *unlit* bulbs (off-bulbs keep `unlit_color`).
- Pairing-with-`font_color` pattern in docs (deselected during brainstorming).
