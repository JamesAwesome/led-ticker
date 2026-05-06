# Rainbow Flashing Border for TickerMessage

> **Status: design locked. Animation style confirmed by user: rainbow
> chase along the perimeter, mirroring the per-character rainbow on
> letters. Hue formula:
> `((perimeter_index * char_offset) + frame * speed) % 360` — the
> same shape as `Rainbow.color_for` indexed by perimeter position
> instead of character index. Remaining open questions answered with
> sensible defaults below.**

**Goal:** Add a configurable animated border effect to `TickerMessage` so
sections can frame their text with a moving rainbow perimeter. Targeted
at showcase / attention-getting moments (storefront window, opening
section, sale announcements). Targeted JUST at TickerMessage per the
user's request — not a general widget feature.

**Architecture:** New `border` field on TickerMessage that takes either
None (no border, current behavior) or a `BorderEffect` instance.
`BorderEffect` is a small protocol with a `paint(canvas, frame_count)`
method. Concrete implementations: `RainbowChaseBorder` (per-pixel hue
shifts around the perimeter, advancing per frame) and possibly a few
sibling styles. Border paints at PHYSICAL pixel resolution (bypasses
ScaledCanvas's 4×4 block expansion via `unwrap_to_real(canvas)`) so a
1-pixel border on bigsign actually draws as 1 real LED, not a 4×4
block.

---

## Design choices (tentative — confirm)

### A. Where the border paints

- **Around the entire panel perimeter** (top edge + bottom edge + left
  edge + right edge). 1 pixel thick by default; `border_thickness`
  knob for 2-pixel borders.
- Paints at **physical resolution** (1 real LED per border pixel),
  matching the hires emoji / hires font convention. On bigsign a
  1px border at scale=4 = 1 real pixel, not a 4×4 block — looks
  proportionate to the hires text inside.
- **Drawn AFTER the canvas reset but BEFORE the text**. Order: clear → bg_color fill → border → text. Means text drawn near the panel edge can overlap the border (text wins on overlap because it's drawn later). User can choose smaller `font_size` if they want
  margin between text and border. Auto-margining is more complexity than this feature warrants for v1.

### B. Border animation style — RAINBOW CHASE (confirmed)

Per-pixel rainbow that moves around the perimeter over time. Each
pixel's hue is indexed by its position on the perimeter (clockwise
starting from top-left, hop count 0..N-1), advancing per frame:

```
hue = ((perimeter_index * char_offset) + frame_count * speed) % 360
```

Same formula as `Rainbow.color_for` for letters. Default speed and
char_offset will match `Rainbow`'s defaults (8°/frame, 30°/char) but
adjusted for perimeter scale — see "remaining defaults" below.

### C. Configuration shape

TOML-side, mirror the `font_color` / `animation` vocabulary:

```toml
# Shorthand for the default chase style
border = "rainbow"

# Inline table for tunable params
border = {style = "rainbow", thickness = 1, speed = 8, char_offset = 12}

# Explicit constant color (single-color border, no animation)
border = {style = "constant", color = [255, 0, 0]}
```

`_build_widget` coerces these into `BorderEffect` instances at config
load (similar to how `font_color` strings/tables are coerced into
`ColorProvider` instances).

### D. Frame coupling

Border animation reads `widget._frame_count` (the same counter that
drives `font_color` rainbow / typewriter). This means:

- During a transition, frame is paused → border freezes (consistent
  with text behavior, no phase drift).
- Each visit, frame_count resets to 0 → border restarts at the same
  hue position.
- Border ticks at the engine's standard 50ms cadence with the text.

This is a free property of the `_FrameAware` mixin TickerMessage
already uses — no new infrastructure.

---

## Implementation sketch (200 LOC est.)

**New file**: `src/led_ticker/borders.py`
- `BorderEffect` Protocol with `paint(canvas, frame_count)` and
  `frame_invariant: bool` (parallel to ColorProvider).
- `RainbowChaseBorder(speed=8, char_offset=12, thickness=1)` —
  per-pixel rainbow chase around the perimeter.
- `ConstantBorder(color, thickness=1)` — single-color border, no
  animation. `frame_invariant = True`.
- `_perimeter_pixels(canvas, thickness)` helper — returns the list
  of `(real_x, real_y)` tuples on the panel perimeter, in
  clockwise order starting from top-left, indexed for hue offsets.
  This is where the physical-resolution painting happens via
  `unwrap_to_real(canvas).SetPixel(rx, ry, r, g, b)`.

**Modified files**:
- `src/led_ticker/widgets/message.py` — add `border` field to
  `TickerMessage`; in `draw()`, after `compute_baseline`, call
  `self.border.paint(canvas, self._frame_count)` if border is set
  (BEFORE the text-rendering branches).
- `src/led_ticker/app.py` — add `_coerce_border` helper that maps
  TOML `border = "rainbow"` / inline-table into a `BorderEffect`.
  Mirror the `_coerce_color_provider` pattern.
- `CLAUDE.md` — document the new field, the physical-resolution
  paint convention, and the frame-coupling behavior.

**Tests**:
- `tests/test_borders.py` — perimeter geometry (all 4 edges hit, no
  duplicates at corners, correct count for various thicknesses);
  rainbow chase frame-evolution (frame=0 vs frame=N produces
  different hue at the same perimeter position).
- `tests/test_widgets/test_message.py` — TickerMessage with border
  paints to the unwrapped real canvas (verify via SetPixel spy on
  the real canvas, not the wrapper). Border hue advances when
  frame_count advances. Border respects pause_frame (transition
  consistency). Frame-invariant border (ConstantBorder) eligible
  for the static-text fast path.

**Smoke**: add a section to `config.showroom-bigsign.example.toml`
that uses `border = "rainbow"` on a hero message, e.g. the WELCOME
section. Make the border the headline visual on first appearance.

---

## Remaining defaults (locking with sensible values)

1. **Animation style** — RAINBOW CHASE (confirmed, see section B).

2. **Thickness** — **1 pixel** by default. Cleaner "neon outline" feel,
   matches the hires-aesthetic of the rest of the panel. `thickness =
   2` available via the inline-table form for users who want a
   thicker frame.

3. **bg_color interaction** — Border paints **on top of bg_color**.
   The full perimeter is rainbow; bg_color fills the interior. No
   blending mode for v1. (If a section sets `bg_color = [255, 230,
   80]` yellow + a rainbow border, the result is a yellow box with
   a rainbow chase frame — exactly the "negative slogan with
   rainbow frame" pairing you'd want.)

4. **TickerCountdown** — **NOT included** in v1. Adding the field to
   `TickerCountdown` is trivial (~10 LOC) but expands the test
   surface and the user explicitly said "targeted at just ticker
   message". If the countdown use case comes up later, follow-up
   PR. Easy to extend.

5. **Speed / char_offset** — **Independent** from `font_color`'s
   rainbow. Border has its own `RainbowChaseBorder(speed,
   char_offset)`. Defaults tuned for perimeter (which is much longer
   than text in pixels — 256 + 64 + 256 + 64 = 640 perimeter pixels
   on bigsign vs ~30 chars). Probably `speed = 4`, `char_offset = 6`
   so the chase visibly moves at a comfortable pace and the rainbow
   tiles ~3 times around the perimeter. Will tune on hardware.

---

## Ready to execute

All design choices locked. Implementation plan above is ~200 LOC
across `borders.py` (new), `widgets/message.py`, `app.py`, plus
tests + smoke. Single branch + PR.

Estimated effort: ~2 hours including hardware verification iteration
(tuning the chase speed / char_offset on bigsign).
