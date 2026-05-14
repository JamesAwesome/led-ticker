# Two-row Widget Options

## Top row

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `top_text` | string | required | Text for the held top row. Inline `:slug:` emoji are rendered as pixel art. |
| `top_color` | RGB list / string / table | `[255, 255, 0]` | Top-row color. Constant `[r,g,b]`, `"rainbow"`, `"color_cycle"`, `"random"`, or `{style="gradient", from=[...], to=[...]}`. |
| `top_align` | string | `"center"` | Horizontal alignment when text fits: `"left"`, `"center"`, or `"right"`. |
| `top_font` | string | (same as `font`) | Per-row font override. Falls back to `font` when unset. |
| `top_font_size` | int | (BDF cell height) | Real-pixel font size for hires `top_font`. Required when `top_font` is a hires font name. |
| `top_font_threshold` | int 0–255 | `128` | Rasterization threshold for hires `top_font`. Lower = thicker glyphs. |
| `top_text_y_offset` | int | `0` | Vertical nudge for the top row's text in logical rows. Negative = up. |
| `top_emoji_y_offset` | int | `0` | Vertical nudge for the top row's emoji in logical rows. Set equal to `top_text_y_offset` to shift the whole row together. |
| `top_bg_color` | RGB list | none | Per-band background fill for the top row only. Painted over any `bg_color`. |

## Bottom row

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `bottom_text` | string | required | Text for the scrolling bottom row. Scrolls left when it overflows the canvas width. |
| `bottom_color` | RGB list / string / table | `[255, 255, 0]` | Bottom-row color. Same value types as `top_color`. |
| `bottom_align` | string | `"center"` | Alignment when bottom text fits without scrolling. Ignored when text overflows. |
| `bottom_font` | string | (same as `font`) | Per-row font override for the bottom row. Falls back to `font` when unset. |
| `bottom_font_size` | int | (BDF cell height) | Real-pixel font size for hires `bottom_font`. Required when `bottom_font` is a hires font name. |
| `bottom_font_threshold` | int 0–255 | `128` | Rasterization threshold for hires `bottom_font`. Lower = thicker glyphs. |
| `bottom_text_y_offset` | int | `0` | Vertical nudge for the bottom row's text in logical rows. Negative = up. |
| `bottom_emoji_y_offset` | int | `0` | Vertical nudge for the bottom row's emoji in logical rows. |
| `bottom_bg_color` | RGB list | none | Per-band background fill for the bottom row only. Painted over any `bg_color`. |
| `bottom_text_wrap` | bool | `false` | Seamless wrap mode for the bottom row. When `true`, the bottom row repeats with a separator between copies and at least one full copy is on the panel at every tick. Top row never wraps. Only allowed in `mode = "swap"`. |
| `bottom_text_separator` | string | `" • "` (when `bottom_text_wrap = true`) | Glyph(s) drawn between bottom-row repeats in wrap mode. `""` falls back to a two-space gap. Rendered in the bottom row's font. |
| `bottom_text_separator_color` | color spec | inherit `bottom_color` | Color for the bottom separator in wrap mode. Whole-string provider (one hue per frame); accepts the same value types as `bottom_color`. Inherits `bottom_color` (NOT `font_color`). |

## Layout

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `top_row_height` | int | none | Give the top band exactly N logical rows; bottom gets the remainder. Default `None` splits 50/50. Use with a small `font` on top + a larger `bottom_font` to achieve a compact tag + wide marquee. Must be `> 0` and `< canvas.height`. |
| `padding` | int | `6` | Horizontal padding added to the bottom row's cursor position when scrolling (spacing between repeats). |

> `scale` and `content_height` are **section-level** fields, not widget fields. Typical bigsign deployments use `scale = 2` (doubles logical canvas width to 128 px so handles fit on the top row) and `content_height = 16` (hard ceiling: `content_height × scale ≤ panel_h_real`). See [display concepts](/concepts/display) for details.

## Shared

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `font` | string | `"5x8"` | Default font for both rows when `top_font` / `bottom_font` are unset. BDF alias (e.g. `"5x8"`, `"6x12"`) or hires font name (e.g. `"Inter-Bold"`). |
| `bg_color` | RGB list | none | Background fill for the full panel before text. Per-band `top_bg_color` / `bottom_bg_color` paint on top of this. |
| `border` | string / table | none | Perimeter border effect — `"rainbow"`, `[r,g,b]` constant, or `{style="rainbow", thickness=N, speed=N, char_offset=N}`. Paints at physical panel resolution (bypasses ScaledCanvas), so the border traces the real panel edge, not the logical canvas edge. |
