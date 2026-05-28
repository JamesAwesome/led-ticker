# Pool Widget: Two-Row Layout — Design Spec

**Date:** 2026-05-28
**Status:** Draft — pending implementation plan.
**Author:** James + Claude (brainstorming session)

## Summary

Add a two-row rendering layout to the pool widget. The bigsign (`default_scale = 4`) and longboi (`default_scale = 4`) panels have vertical headroom that the current single-row "ticker" layout doesn't exploit — a label-on-top / big-number-on-bottom layout reads better from across a pool deck than a single dense line of mixed-color segments.

This spec covers:

- A new `layout = "two_row"` value on `PoolMonitor` (default stays `"ticker"`).
- Per-screen content + color mapping for the two-row variant.
- Five new fields on `PoolMonitor` that thread through to the existing `TwoRowMessage` primitive.
- Validation rules to reject dead-knob configurations.
- Tests covering the layout switch, per-screen content, color application, font/threshold/row-height threading, and validation.
- A new bigsign testing config (`config/config.pool_bigsign.toml`).

## Goals

- Pool widget renders two-row on bigsign / longboi by user choice.
- Hi-res Inter font sizing matches what the longboi config already uses for MLB.
- Configurable `label_color` (added in PR #125) continues to apply to the top label.
- Section semantics stay one widget per section — the cycle just gets one more screen because the season screen splits HI / LO.

## Non-goals (out of scope)

- No segmented per-row content. Top row is a single-color label; bottom row is a single-color value. If a future widget genuinely needs multi-segment two-row, that is a separate `TwoRowSegmentMessage` refactor in `widgets/message.py`. **Do not** prematurely build it.
- No animated trend arrow on the today screen in two-row mode. The bottom row is the headline value only. Users who want the trend signal use `layout = "ticker"`.
- No automatic layout-based default-font switching. The widget's defaults stay simple (`FONT_DEFAULT`); the bigsign testing config sets hi-res fonts explicitly. (Magic-on-layout defaults would surprise users moving a working config between sign sizes.)
- No `docs/site/...` user-facing docs in the same PR. Reasonable to defer to a follow-up to keep this PR focused. A short docs follow-up PR ships after.

## Architecture

The codebase already has a coherent ladder of layout primitives:

| Primitive | Shape | Used by |
|---|---|---|
| `SegmentMessage` | one row, list of `(text, Color)` segments | TickerMessage, MLB ticker, pool (ticker), title cards |
| `TwoRowMessage` | two rows, one string per row, per-row font/color | `two_row` widget type, image overlays |
| `MLBScoreboardMessage` | scoreboard zones, custom math | MLB scoreboard layout |

Pool's two-row need fits squarely in the middle tier: bottom row is one short value (1 color) and top is one short label (1 color). That is exactly what `TwoRowMessage` was built for.

The pool widget picks the right builder based on its `layout` field. Both builders produce the same observable surface (`feed_title` + `feed_stories`), so the engine, the `Container` Protocol conformance, and section-cycle semantics are all unchanged.

```
PoolMonitor.update()
  └─ self.layout == "ticker"   ─→ _build_ticker_screens()    → SegmentMessage stories
     self.layout == "two_row"  ─→ _build_two_row_screens()   → TwoRowMessage stories
```

## Field additions

The codebase splits field handling into two layers:

- **Runtime fields** — attrs fields declared on the widget class. Live for the widget's lifetime.
- **Dispatch-time fields** — recognized by `app/factories.py` before widget construction. Examples: `font` + `font_size` + `font_threshold` get resolved into a single `Font` object that's then passed to the widget as the `font` attrs field. Per-row fonts work the same way (`top_font` + `top_font_size` + `top_font_threshold` → resolved `top_font: Font` passed to the widget).

### New runtime attrs fields on `PoolMonitor`

```python
layout: str = attrs.field(default="ticker", kw_only=True)
top_font: Font | None = attrs.field(default=None, kw_only=True)
bottom_font: Font | None = attrs.field(default=None, kw_only=True)
top_row_height: int | None = attrs.field(default=None, kw_only=True)
```

All `kw_only`, all optional. `top_font` and `bottom_font` receive already-resolved `Font` objects from the dispatch layer (sizes/thresholds baked in). `top_row_height` is in logical rows (matches `TwoRowMessage`'s field).

### Dispatch-level field updates in `app/factories.py`

The dispatch layer already handles `top_font` / `top_font_size` / `top_font_threshold` / `bottom_font` / `bottom_font_size` / `bottom_font_threshold` — restricted today to `{"two_row"}` (`_DISPATCH_APPLICABLE_TYPES`). Widen each set to `{"two_row", "pool"}`:

```python
# app/factories.py — _DISPATCH_APPLICABLE_TYPES
"top_font":             {"two_row", "pool"},  # was {"two_row"}
"top_font_size":        {"two_row", "pool"},
"top_font_threshold":   {"two_row", "pool"},
"bottom_font":          {"two_row", "pool"},
"bottom_font_size":     {"two_row", "pool"},
"bottom_font_threshold":{"two_row", "pool"},
```

`top_row_height` is currently in `TWO_ROW_OVERLAY_FIELDS` for documentation purposes only — pool needs no change there. The runtime `top_row_height: int | None` field on PoolMonitor passes through to TwoRowMessage's constructor directly.

### Font resolution behavior

Matches `TwoRowMessage`'s existing fallback chain so the mental model is consistent widget-to-widget:

- `top_font = None` (runtime) → falls back to `self.font` inside `_build_two_row_screens`.
- `bottom_font = None` (runtime) → falls back to `self.font`.
- Omitting `top_font_size` in TOML → dispatch falls back to `font_size` (already applies to all widgets).
- Omitting `top_font_threshold` in TOML → dispatch falls back to `font_threshold`.
- `top_row_height = None` (runtime) → symmetric 8/8 logical split (the `TwoRowMessage` default).

### Field thread-through into `TwoRowMessage`

When `_build_two_row_screens` constructs a `TwoRowMessage`, it passes:

| Pool field/source | TwoRowMessage kwarg |
|---|---|
| `self.font` | `font` |
| `self.top_font` (resolved) | `top_font` |
| `self.bottom_font` (resolved) | `bottom_font` |
| `self.top_row_height` | `top_row_height` |
| `self.label_color` | `top_color` |
| per-screen semantic color | `bottom_color` |

Per-row font sizes and thresholds are NOT passed at runtime — they're already baked into the `top_font` / `bottom_font` Font objects produced by the dispatch layer.

## Per-screen content map (two_row layout)

Five screens cycle in this order:

| # | Screen | `top_text` | `bottom_text` | `top_color` | `bottom_color` |
|---|---|---|---|---|---|
| 0 | Title | `POOL` | `TEMPS` | `label_color` | `RGB_WHITE` |
| 1 | Today | `POOL 24H` | `_fmt_temp(now_display, units)` (e.g. `82F`) | `label_color` | `_zone_color(zone_f)` or `DIM` if stale |
| 2 | 7-day | `POOL 7D AVG` | `_disp(d7_mean_c)` (e.g. `78`) | `label_color` | `AVG_COLOR` |
| 3 | Season HI | `POOL SEASON HI` | `_disp(season_max_c)` (e.g. `95`) | `label_color` | `HI_COLOR` |
| 4 | Season LO | `POOL SEASON LO` | `_disp(season_min_c)` (e.g. `72`) | `label_color` | `LO_COLOR` |

`feed_title` is the screen-0 title `TwoRowMessage`. `feed_stories` is screens 1-4 (length 4 in two_row vs length 3 in ticker, because the single season screen splits).

### Placeholder (no data / before first successful query)

| # | Screen | `top_text` | `bottom_text` | `top_color` | `bottom_color` |
|---|---|---|---|---|---|
| 0 | Title | `POOL` | `TEMPS` | `label_color` | `RGB_WHITE` |
| 1 | No data | `{self.title}` (default `POOL TEMPS`) | `--` | `label_color` | `label_color` |

## Color application

- `top_color`: always `self.label_color` (configurable, default `RGB_WHITE`).
- `bottom_color` is screen-specific per the table above.
- Stale signal: when `current_age_s > self.stale_after`, the today screen's `bottom_color` is `DIM`. Top label stays at `label_color`. (Matches the ticker layout's stale handling.)
- `DIM`, `AVG_COLOR`, `HI_COLOR`, `LO_COLOR` come from the existing pool color palette — no new constants.

## Trend arrow

**Dropped in two_row mode.** The bottom row of the today screen is just the temperature value, no arrow glyph. Documented as a deliberate tradeoff in the spec, the docs, and the field-hint string for `layout`.

Test asserts there is no `^` / `v` / `-` arrow glyph anywhere in the today screen's segments in two_row mode.

## Validation

Added to the pool widget's section in `validate.py` / `factories.py`:

1. **Layout enum.** `layout` accepts only `"ticker"` or `"two_row"`. Anything else raises `ValueError` at config-load with a did-you-mean suggestion (`difflib.get_close_matches`).
2. **Dead knobs under ticker.** Setting any of `top_font` / `bottom_font` / `top_font_size` / `bottom_font_size` / `top_row_height` while `layout = "ticker"` (or while `layout` is omitted) raises a `MigrationError`-style message: `"<field> only applies when layout='two_row'; remove the field or set layout='two_row'."` Stops silent dead-knob configs.
3. **Font-size floor.** `TwoRowMessage`'s existing `font_size < cell_h` check fires automatically since pool delegates rendering to it — no new validation here.

## Testing

### Behavioral tests (`tests/test_widgets/test_pool.py`, new `TestTwoRowLayout` class)

1. `test_layout_default_is_ticker` — tripwire against surprise default flips.
2. `test_layout_two_row_yields_title_plus_four_stories` — `len(feed_stories) == 4` (season split).
3. `test_layout_two_row_title_is_two_row_message` — `isinstance(m.feed_title, TwoRowMessage)`.
4. `test_layout_two_row_all_stories_are_two_row_messages` — same check across feed_stories.
5. `test_layout_two_row_today_bottom_uses_zone_color` — at `current_c=27.78`, bottom `top_color`/`bottom_color` carry `_zone_color(zone_f=82)` (ORANGE).
6. `test_layout_two_row_stale_today_bottom_uses_dim` — `current_age_s > stale_after` → bottom_color is `DIM`.
7. `test_layout_two_row_seven_day_bottom_uses_avg_color` — bottom is `AVG_COLOR`.
8. `test_layout_two_row_season_hi_bottom_uses_hi_color` — bottom is `HI_COLOR`.
9. `test_layout_two_row_season_lo_bottom_uses_lo_color` — bottom is `LO_COLOR`.
10. `test_layout_two_row_drops_trend_arrow` — no `^` / `v` / `-` glyph anywhere in the today screen.
11. `test_layout_two_row_label_color_threads_through` — sentinel `label_color` reaches every `top_color`.
12. `test_layout_two_row_threads_per_row_fonts` — `top_font`, `bottom_font`, and `top_row_height` reach the constructed `TwoRowMessage` instances. (Per-row sizes/thresholds are baked into the resolved Font objects upstream and don't need separate runtime assertions.)
13. `test_layout_two_row_placeholder_uses_two_row_message` — placeholder path also produces `TwoRowMessage` instances.

### Validation tests (`tests/test_validate.py`)

14. `test_layout_unknown_value_raises` — `layout = "scoreboard"` raises with did-you-mean.
15. `test_top_font_with_ticker_layout_raises` — dead knob under ticker.
16. `test_bottom_font_size_with_ticker_layout_raises` — dead knob under ticker.
17. `test_top_row_height_with_ticker_layout_raises` — dead knob under ticker.

### Tripwire (`tests/test_widgets/test_pool.py`)

18. `test_feed_stories_type_widens_to_segment_or_two_row` — explicit `isinstance` check on every member.

## Files affected

| File | Change |
|---|---|
| `src/led_ticker/widgets/pool.py` | Add runtime fields `layout`, `top_font`, `bottom_font`, `top_row_height`; rename `_build_screens` → `_build_ticker_screens`; add `_build_two_row_screens`; `update()` dispatches on `self.layout`. |
| `src/led_ticker/app/factories.py` | Widen `_DISPATCH_APPLICABLE_TYPES` entries for `top_font` / `top_font_size` / `top_font_threshold` / `bottom_font` / `bottom_font_size` / `bottom_font_threshold` to include `"pool"`. Add field hints for `layout` and `top_row_height` under the pool section. |
| `src/led_ticker/app/coercion.py` | None expected — `layout` is a plain string and `label_color` already lives in `_COLOR_KEYS`. |
| `src/led_ticker/validate.py` | Layout enum + dead-knob-under-ticker checks (see Validation). |
| `tests/test_widgets/test_pool.py` | New `TestTwoRowLayout` class (~13 tests) + tripwire. |
| `tests/test_validate.py` | 4 validation tests. |
| `config/config.pool_bigsign.toml` | **Create.** Bigsign testing config with `layout = "two_row"`. |
| `CLAUDE.md` | One bullet under "Load-bearing invariants by subsystem" — pool layout switch parallel to MLB's. |

## Bigsign testing config

`config/config.pool_bigsign.toml`:

```toml
# Pool widget — bigsign (256×64) hardware testing config (two_row layout)
#
# Mirrors config.bigsign.example.toml for display/RP1 tuning; single
# section, single pool widget in two_row mode. Soak-test the
# title → today → 7-day → season HI → season LO cycle on a 2×4
# vertical-serpentine panel and watch the periodic INFO log
# confirm update() is firing.

[display]
rows = 32
cols = 64
chain_length = 8
parallel = 1
pixel_mapper_config = "Remap:256,64|192,32n|192,0n|128,32n|128,0n|64,32n|64,0n|0,32n|0,0n"
brightness = 60
default_scale = 4
hardware_mapping = "adafruit-hat"
gpio_slowdown = 3
rp1_rio = 1
pwm_bits = 8
show_refresh_rate = true

[[playlist.section]]
mode = "swap"
hold_time = 5
loop_count = 0

[[playlist.section.widget]]
type = "pool"
title = "POOL TEMPS"
units = "imperial"
update_interval = 60
stale_after = 900
layout = "two_row"
font = "Inter-Regular"
font_size = 32          # default for both rows; top_font_size overrides
font_threshold = 80
top_font_size = 16      # smaller label on top, ~50% of the 32-real top band
label_color = [130, 220, 255]
```

Notes:
- Symmetric 8/8 split: `top_row_height` left at the `TwoRowMessage` default.
- `bottom_font_size` is omitted — it falls back to `font_size = 32` which fills the bottom band.
- For an asymmetric split (smaller label, bigger value), raise `top_row_height = 4` and bump `bottom_font_size` to 44–48 explicitly.

## Open questions

None blocking implementation. Possible follow-ups:

- Should the title screen merge to a single centered "POOL TEMPS" instead of split "POOL" / "TEMPS"? (Decision in spec: split for consistency. Revisit if it reads worse on hardware.)
- Should the season split keep `hold_time` synced (1 cycle = title + 4 screens × hold_time) or get a half-hold for HI/LO pair? (Out of scope — `hold_time` is section-level today.)

## Acceptance criteria

The PR ships when:

- All 18 listed tests pass.
- `make lint` clean.
- `make validate CONFIG=config/config.pool_bigsign.toml` clean.
- `make validate CONFIG=config/config.pool_longboi.toml` still clean.
- `make validate CONFIG=config/config.pool_smallsign.toml` still clean.
- Hardware verification: pool widget cycles all five screens correctly on a bigsign or longboi panel, with the cyan label color, the per-screen bottom colors, and no trend arrow on today.
