# Background Colors — Design

**Date:** 2026-05-02
**Status:** Approved, ready for implementation plan

## Goal

Add `bg_color` support across all widget types so users can specify a non-black background for any section or individual widget. Today every render starts with `canvas.Clear()` (LEDs off). With this feature, widgets can paint a solid color first so text and images sit on a colored field instead of black.

## Why now

Two real configs want it: a store-window bigsign that wants a brand color behind a `two_row` handle/caption, and a planned `:moon-bunny:` themed setup that wants a navy field behind the moon emoji. Both currently work around it by tinting text colors, which is the wrong knob.

## Resolution model

**One field name, two scopes:** `bg_color` exists at both section level (in `[[sections]]`) and widget level (in `[[sections.widgets]]`). Widget-level wins; section-level acts as a default that propagates to widgets that omit the key.

```toml
[[sections]]
mode = "swap"
bg_color = [26, 59, 142]  # navy — applies to every widget in this section

  [[sections.widgets]]
  type = "message"
  text = "@brand"
  font_color = [255, 126, 177]
  # bg_color omitted — inherits navy from section

  [[sections.widgets]]
  type = "two_row"
  top_text = "@brand"
  bottom_text = "live now"
  top_bg_color = [26, 59, 142]      # navy
  bottom_bg_color = [93, 42, 110]   # purple
  # widget-level overrides section bg_color via per-row keys
```

**Resolution precedence** (highest first):
1. Widget-level `bg_color` (or `top_bg_color`/`bottom_bg_color` for `two_row`)
2. Section-level `bg_color`
3. `None` → `Clear()` (today's behavior)

**Type:** 3-int list/tuple → `graphics.Color`. Same coercion path as `font_color`/`top_color`/`bottom_color`. No string sentinels (no `"random"`).

**`(0, 0, 0)` is allowed** as "explicit black." Same visual result as `None`/Clear (LEDs off), but it counts as "set" for resolution — useful when a section sets a non-black bg and one widget wants to opt back to black.

## Architecture — where Fill happens

**Hybrid model:** the orchestrator handles bg resets for text widgets, image widgets handle their own internal resets.

### Shared helpers (`widgets/_image_fit.py`)

```python
def reset_canvas(canvas, bg_color):
    """Clear canvas, or Fill it with bg_color if set."""
    if bg_color is None:
        canvas.Clear()
    else:
        canvas.Fill(bg_color.red, bg_color.green, bg_color.blue)

def fill_band(canvas, y_start, y_end, color):
    """Fill a horizontal band [y_start, y_end) with color via SetPixel."""
    for y in range(y_start, y_end):
        for x in range(canvas.width):
            canvas.SetPixel(x, y, color.red, color.green, color.blue)
```

`reset_canvas` replaces every `canvas.Clear()` site that paints a widget. `fill_band` paints per-row bands for `TwoRowMessage` (Fill is whole-canvas only).

### Text widgets (TickerMessage, TickerCountdown, weather, RSS, MLB, crypto, etc.)

- Each widget gets `bg_color: Color | None = None` field.
- The orchestrator (`Ticker._swap_and_scroll`, `_scroll_one_by_one`, `_scroll_side_by_side`) calls `reset_canvas(canvas, widget.bg_color)` instead of `canvas.Clear()` before `widget.draw()`.
- Widget `draw()` methods are unchanged for the bg case — they already paint on top of whatever the canvas was reset to.

### Image widgets (GifPlayer, StillImage via `_BaseImageWidget`)

- Both gain `bg_color: Color | None = None` field.
- All current `canvas.Clear()` sites in `_play_no_text`, `_play_with_text`, `_render_tick` swap to `reset_canvas(canvas, self.bg_color)`.
- `_paint_full(canvas)` becomes conditional:
  - `bg_color is None` → SetImage fast path (today's behavior; pillars and transparent regions are black).
  - `bg_color` set → skip-black painting path always. Pillarbox bands, letterbox bands, and alpha-transparent regions all show bg color. Intentional-black source pixels (e.g. a Pikachu pupil) ALSO show bg — this is option A from the brainstorm, accepted as the simpler model.

### TwoRowMessage

- Gets three fields: `bg_color`, `top_bg_color`, `bottom_bg_color` — all `Color | None = None`.
- `draw()` paints per-row bands itself (orchestrator already called `reset_canvas` with widget-level `bg_color` so the canvas is either fully cleared or fully filled).
- Row split:
  - Top band = rows `0` through `content_height // 2 - 1`
  - Bottom band = rows `content_height // 2` through `content_height - 1`
  - At `content_height = 20`: top = 0-9, bottom = 10-19.
- Paint order: orchestrator's `reset_canvas` (whole canvas) → widget paints per-row bands on top → text on top of bands.
- If only one per-row is set, the other side stays at whatever `reset_canvas` left it.

### Config plumbing

- `SectionConfig` gains `bg_color: tuple | None = None` field (parsed from TOML).
- `app._build_widget(widget_cfg, ..., default_bg_color)` injects section bg into the widget kwargs only when the widget config lacks `bg_color`.
- `app._COLOR_KEYS` extends to include `bg_color`, `top_bg_color`, `bottom_bg_color` (3-int list → `graphics.Color` coercion).

## Validation & footguns

**Accepted footguns (documented, not fixed):**
- During transitions (`run_transition`), if section A has `bg_color = red` and section B has `bg_color = blue`, the transition will momentarily show whichever widget's `draw()` ran last writing its Fill. Wipe/dissolve transitions paint over with their own pixels; push transitions show the band color of whichever side is being drawn. Transitions are 200-300ms — unlikely to be jarring in practice.
- When `bg_color` is set on an image widget, pillarbox and letterbox bands take the bg color (no separate band-color knob today, none added).

**Image widget invariant:** `bg_color` set → skip-black path, regardless of fit mode (pillarbox/letterbox/stretch/crop) and regardless of whether the source has transparent regions.

## Out of scope / deferred

- `bg_color = "random"` or per-section cycling bg colors.
- Per-row backgrounds on non-TwoRow widgets (no generic "regions" abstraction).
- Transition-time bg color crossfading or morphing.
- Animated/gradient backgrounds (build as a Presentation effect later if desired, not a bg primitive).
- Separate pillarbox/letterbox color knob coexisting with `bg_color`.
- `bg_alpha` / partial transparency (LEDs are on/off per channel; alpha is meaningless).
- Separate `title_bg_color` field (titles use the existing per-widget `bg_color` resolution).

## Testing strategy

**Per-widget tests (parametrized where reasonable):**
- `bg_color` field accepts `Color`, defaults to `None`, plumbs through `app._build_widget` from both widget-level and section-level keys.
- When set: canvas is filled with bg color before text/image paints (assert via `SetPixel`/`Fill` recording on stub canvas).
- When `None`: behavior unchanged from today (Clear, no Fill).
- Section default propagates; widget-level wins when both are present.

**Cross-cutting regression tests:**

1. **`test_image_fit.py`** — `reset_canvas(canvas, None)` calls `Clear()`; `reset_canvas(canvas, Color(r,g,b))` calls `Fill(r,g,b)`. `fill_band(canvas, 0, 10, color)` writes only rows 0-9.

2. **`test_widgets/test_image_base.py`** — when `bg_color` is set on a `_BaseImageWidget` subclass:
   - `_paint_full` takes the skip-black branch even for an opaque image; SetImage fast path is NOT used.
   - Pillarbox bands show bg color (SetPixel on pillar columns paints bg, not black).
   - Transparent regions of an alpha-flattened gif show bg (fixture gif with known transparent pixels).
   - Intentional-black source pixels also show bg.

3. **`test_widgets/test_two_row.py`**:
   - `top_bg_color` only → top band filled, bottom band Clear/widget-bg.
   - `bottom_bg_color` only → bottom band filled.
   - Both set → both bands painted respectively.
   - Widget `bg_color` + per-row → per-row wins on its band.
   - At `content_height = 20`: assert exact row indices for top (0-9) and bottom (10-19).

4. **`test_ticker_display.py`** — `_swap_and_scroll` calls `reset_canvas` with widget's `bg_color`, not bare `Clear()`.

5. **`test_config.py`** — `SectionConfig.bg_color` parses from TOML, defaults to `None`. Section bg propagates to widgets via `_build_widget` only when widget config lacks the key.

**Estimated new tests:** 25-30, mostly small.

**Not testing:** real-hardware visual fidelity (rely on bigsign smoke test); transition-time bg leak between sections (accepted footgun); random/cycling bg colors (out of scope).

## Touch list (rough)

- `widgets/_image_fit.py` — add `reset_canvas`, `fill_band` helpers.
- `widgets/_image_base.py` — `bg_color` field, swap `Clear()` → `reset_canvas` (~5 sites), conditional `_paint_full`.
- `widgets/two_row.py` — `bg_color`, `top_bg_color`, `bottom_bg_color` fields; per-row band painting in `draw()`.
- `widgets/message.py`, `weather.py`, `rss_feed.py`, `mlb.py`, `mlb_standings.py`, `crypto/*.py` — `bg_color` field on each.
- `ticker.py` — replace `canvas.Clear()` with `reset_canvas(canvas, widget.bg_color)` in `_swap_and_scroll`, `_scroll_one_by_one`, `_scroll_side_by_side` (~3 sites).
- `app.py` — extend `_COLOR_KEYS` with `bg_color`/`top_bg_color`/`bottom_bg_color`; propagate section bg in `_build_widget`.
- `config.py` — `SectionConfig.bg_color` field.
- Test files above.

Estimated 15-20 small edits + tests.
