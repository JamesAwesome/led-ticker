# TwoRowMessage Rainbow Border — Design Spec

**Status:** Design locked. Awaiting confirmation before writing the
implementation plan.

**Goal:** Add the `border` field already on `TickerMessage` and
`TickerCountdown` to `TwoRowMessage`, so storefront-style brand
layouts (held handle on top, scrolling tagline on bottom) can wear
a rainbow chase frame.

**Branch:** `feat/tworow-border` off main. Single PR.

---

## Scope

**In:**
- `TwoRowMessage` accepts a `border` field with the same TOML
  vocabulary as TickerMessage (`"rainbow"` shorthand, inline
  tables, `[r,g,b]` constant shorthand).
- Border paints before both rows' text on every tick at physical
  resolution (bypasses ScaledCanvas's block expansion via
  `unwrap_to_real`, same as on TickerMessage).
- Border reads `_frame_count` so the chase ticks during holds,
  freezes through transitions, and resets on visit entry.

**Deferred (separate future PR if requested):**
- Image widgets (`GifPlayer`, `StillImage`) — fast-path gate
  interaction estimated ~3× this PR's cost, not justified by
  current use cases.
- RSS feed propagation — same deferral; the "rainbow news ticker"
  use case isn't in any committed config today.
- Section-level border (engine paints regardless of widget) —
  bigger architectural conversation, deferred.

**Out:**
- WeatherWidget, MLB, crypto widgets — decorative borders
  fight data readability. Not adding.

---

## Architecture

The pattern is identical to TickerMessage's border integration:

1. **Field** — `border: Any | None = attrs.field(default=None, kw_only=True)`
   on `TwoRowMessage`. Type is `Any` (duck-typed via `paint` and
   `frame_invariant`) so the existing `BorderEffect` Protocol
   doesn't need to be imported by widget modules.

2. **Paint call** — inside `TwoRowMessage.draw`, after canvas reset
   but BEFORE either row's text rendering. The paint contract is
   "border frames the panel; text floats inside" — text drawn after
   border wins on collision (text near the panel edge overlaps the
   border, which is the right visual).

3. **Frame coupling** — `border.paint(canvas, self._frame_count)`.
   Same call shape as TickerMessage. `_FrameAware` already provides
   `_frame_count` on TwoRowMessage; transitions freeze it via
   `pause_frame`; `_show_one` resets it via `reset_frame`. No new
   infrastructure.

4. **TOML config** — `_build_widget`'s widget-type check expands
   from `("message", "countdown")` to also include `("two_row")`.
   `_coerce_border` is unchanged — same shapes accepted.

5. **Physical-resolution paint** — `RainbowChaseBorder.paint`
   already calls `unwrap_to_real(canvas)` internally, so a 1-px
   border on bigsign is 1 LED regardless of which widget hosts it.
   No widget-specific work needed.

---

## What this means for two-row layouts

TwoRowMessage runs at any scale (default 1, often 2 for
horizontally-scrollable handles, or 4 for full bigsign). The border
paints to the unwrapped real canvas at native panel resolution
regardless. So:

- At `scale = 4` (full bigsign): border = 1 real LED ring around
  256×64 panel.
- At `scale = 2`: border = 1 real LED ring around the 256×64 panel
  (the wrapper's logical 128×32 is painted to the same 256×64
  real surface; the border traces the real perimeter, not the
  logical one).
- At `scale = 1` (small sign): border = 1 LED ring around 160×16.

Both rows' text is drawn through the wrapper (block-expanded by
ScaledCanvas) and so will appear at the WIDGET's intended size; the
border, painting through `unwrap_to_real`, lives outside that
expansion. They're independent rendering paths that compose
correctly because the border paints the actual panel edges.

**Visual question**: at `scale = 2` and `content_height = 32` (the
showroom config), the wrapper's logical canvas is 128×32. Both
rows draw through the wrapper. Border draws the real 256×64 panel
edge — i.e., the actual visible panel boundary, not the logical
canvas boundary. This is the correct behavior (border frames the
sign, not the logical canvas). Worth a sentence in the doc string.

---

## Test plan

Mirror the TickerMessage border tests in `tests/test_borders.py` for
TwoRowMessage. New `TestTwoRowBorder` class with:

1. `test_border_paint_called_with_widget_frame_count` — assert
   `border.paint(canvas, widget._frame_count)` fires once per
   `widget.draw()` call.
2. `test_border_paints_before_text_on_tworow` — paint-order
   tripwire mirroring `test_border_paint_called_before_draw_text`.
   Border first, then text rendering for both rows.
3. `test_no_border_no_paint` — TwoRowMessage without `border`
   doesn't reach for one. Defaults work.

Additional in `tests/test_app.py::TestBuildWidgetWithBorder`:
4. `test_two_row_with_border_string` — `_build_widget` accepts
   `border = "rainbow"` on `type="two_row"` and produces a
   `TwoRowMessage` with a `RainbowChaseBorder`.
5. `test_two_row_without_border_has_none` — counter test.

The existing `test_border_on_unsupported_widget_type_raises` still
applies (e.g., weather still rejects).

---

## Smoke

Add a section to `config.rainbow_border_test.example.toml` so the
focused-iteration smoke covers TwoRow:

```toml
# 7. Two-row brand layout + rainbow border
#    Mirrors a storefront window: handle on top, scrolling tagline
#    on bottom, rainbow chase framing the whole panel. The border
#    paints at REAL panel resolution (256×64 on bigsign) regardless
#    of the section's scale=2 wrapper — frames the sign edge, not
#    the logical canvas.
[[playlist.section]]
mode = "swap"
scale = 2
content_height = 32
hold_time = 5.0
loop_count = 1
transition = "cut"

[[playlist.section.widget]]
type = "two_row"
top_text = ":instagram: @ledticker"
top_color = [225, 48, 108]
top_align = "center"
top_font = "Inter-Bold"
top_font_size = 14
bottom_text = "Storefronts, lobbies, stages"
bottom_color = [255, 240, 200]
bottom_align = "center"
bottom_font = "Inter-Regular"
bottom_font_size = 14
border = "rainbow"
```

(`:instagram:` falls back to lowres because `EMOJI_ROW_CAP=8`
restricts the top band — that's an existing TwoRow constraint
documented in `_row_layout.py`, not a border issue. The handle
still reads fine; the showcase here is the border, not the emoji.)

The showroom config (`config.showroom-bigsign.example.toml`) is
NOT updated in this PR — current §6 is text-only and we don't have
a strong case for adding border there. The smoke covers
verification; showroom integration can be a separate config tweak
if it looks right on hardware.

---

## Effort

- Code: ~25 LOC (field + paint call + `_build_widget` check)
- Tests: ~80 LOC (5 new tests)
- Smoke: ~20 LOC (one section)
- CLAUDE.md: 1 sentence note that TwoRowMessage now also accepts `border`

Total: ~125 LOC. Should land cleanly in one commit.

---

## Open questions

None. Pattern is fully established by the TickerMessage / Countdown
work; TwoRowMessage follows the same recipe.

---

## Ready signal

Confirm the spec looks right and I'll write the implementation plan
+ execute on a branch + open the PR.
