# image Widget Options

## Image source

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `path` | string | required | Path to source file. Relative paths resolve against the config.toml directory. Single PNG / JPG / single-frame GIF are the primary use cases. For animated files, only frame 0 is decoded — use the `gif` widget for animation. |
| `fit` | string | `"pillarbox"` | How the image fills the panel: `"pillarbox"` (scale by height, black bands on sides), `"letterbox"` (scale by width, black bands top/bottom), `"stretch"` (fill panel, distorts aspect ratio), `"crop"` (scale to cover, center-crop excess). |
| `image_align` | string | `"center"` | Horizontal anchor for `pillarbox`: `"left"`, `"center"`, or `"right"`. Ignored by the other three fit modes (they always fill panel width). |

## Display duration

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `hold_seconds` | float | `5.0` | How long to display the image per visit. With `text_loops > 0`, becomes a duration **floor**: the section runs for `max(hold_seconds, text_loops × traversal)` so a long marquee always completes. Minimum `0.05`. |

## Single-row text overlay

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `text` | string | `""` | Optional text rendered alongside the image. Inline `:slug:` emoji are rendered as pixel art. Leave empty for a silent image with no text. |
| `text_align` | string | `"auto"` | Where text appears: `"auto"` picks the side opposite `image_align` so they don't overlap; `"left"` / `"right"` place text statically; `"scroll"` scrolls text behind a transparent image silhouette; `"scroll_over"` scrolls text in front of the image. |
| `text_valign` | string | `"center"` | Vertical text anchor: `"top"`, `"center"`, or `"bottom"`. |
| `text_y_offset` | int | `0` | Logical-pixel shift on top of the `text_valign` baseline. Negative = up, positive = down. |
| `text_x_offset` | int | `0` | Horizontal nudge for static text (`text_align = "left"` or `"right"`). Positive = right, negative = left. Rejected when used with scroll modes. |
| `scroll_direction` | string | `"left"` | Direction the marquee travels: `"left"` or `"right"`. Only applies when `text_align` is `"scroll"` or `"scroll_over"`. |
| `scroll_speed_ms` | int | `50` | Tick cadence in milliseconds when text scrolls. Minimum 20. |
| `font` | string | `"6x12"` | BDF font alias (e.g. `"5x8"`, `"6x12"`) or hires font name (e.g. `"Inter-Regular"`). Default is the 6×12 BDF. |
| `font_size` | int | none | Real-pixel font size. For BDF: snaps down to the nearest integer multiple of cell height, defaults to `cell_h × section_scale` (12 on the small sign, 48 on bigsign at scale=4). For hires fonts: required — raises at config-load without a hint if unset. |
| `font_threshold` | int 0–255 | `128` | Rasterization threshold for hires fonts. Lower = thicker glyphs; useful for thin-stroked fonts like Beloved Sans Regular at ~80. BDF fonts ignore this. |
| `font_color` | RGB list / string / table | `[255, 255, 0]` | Text color. Constant `[r,g,b]`, `"rainbow"`, `"color_cycle"`, `"random"`, or `{style="gradient", from=[...], to=[...]}`. |
| `text_loops` | int | `0` | Minimum number of full marquee traversals before the section transitions. Only meaningful with `text_align = "scroll"` or `"scroll_over"`. `0` = no floor (one traversal is always guaranteed). In wrap mode (`text_wrap = true`), counts complete cycle traversals (one cycle = text + separator) instead. |
| `text_wrap` | bool | `false` | Seamless wrap mode for the marquee. When `true`, the text repeats with a separator between copies and at least one full copy is on the panel at every tick. Requires `text_align` to be `"scroll"` or `"scroll_over"`; rejected in two-row mode. |
| `text_separator` | string | `" • "` (when `text_wrap = true`) | Glyph(s) drawn between repeats in wrap mode. `""` falls back to a two-space gap. Rendered in the widget's `font` — per-separator font override isn't supported in v1. |
| `text_separator_color` | color spec | inherit `font_color` | Color for the separator in wrap mode. Whole-string provider (one hue per frame); accepts the same value types as `font_color`. |

## Two-row text overlay

Setting `bottom_text` to a non-empty string switches the widget to **two-row mode**: the image sits underneath, a held top row sits at the chosen alignment, and the bottom row scrolls when its text overflows the canvas width. Single-row `text_align`, `text_valign`, `text_x_offset`, and `font_size` are rejected in this mode — use the per-row knobs below.

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `bottom_text` | string | `""` | Setting this non-empty activates two-row mode. Text for the scrolling bottom row; auto-scrolls left when it overflows. |
| `top_text` | string | `""` | Text for the held top row. Falls back to `text` when unset (back-compat alias — set one or the other, not both). |
| `top_color` | RGB list / string / table | (same as `font_color`) | Top-row text color. Same value types as `font_color`. Defaults to `font_color` when unset. |
| `bottom_color` | RGB list / string / table | (same as `font_color`) | Bottom-row text color. Defaults to `font_color` when unset. |
| `top_align` | string | `"center"` | Top-row horizontal alignment when text fits: `"left"`, `"center"`, or `"right"`. |
| `bottom_align` | string | `"center"` | Bottom-row alignment when text fits without scrolling. Ignored when the bottom row overflows. |
| `top_font` | string | (same as `font`) | Per-row font override for the top row. Falls back to `font` when unset. |
| `top_font_size` | int | (BDF cell height) | Real-pixel font size for hires `top_font`. Required when `top_font` is a hires font name. |
| `top_font_threshold` | int 0–255 | `128` | Rasterization threshold for hires `top_font`. |
| `bottom_font` | string | (same as `font`) | Per-row font override for the bottom row. Falls back to `font` when unset. |
| `bottom_font_size` | int | (BDF cell height) | Real-pixel font size for hires `bottom_font`. Required when `bottom_font` is a hires font name. |
| `bottom_font_threshold` | int 0–255 | `128` | Rasterization threshold for hires `bottom_font`. |
| `top_text_y_offset` | int | `0` | Vertical nudge for the top row's text in logical rows. Negative = up. |
| `bottom_text_y_offset` | int | `0` | Vertical nudge for the bottom row's text in logical rows. |
| `top_emoji_y_offset` | int | `0` | Vertical nudge for the top row's emoji in logical rows. Set equal to `top_text_y_offset` to shift the whole row together. |
| `bottom_emoji_y_offset` | int | `0` | Vertical nudge for the bottom row's emoji in logical rows. |
| `top_row_height` | int | none | Give the top band exactly N logical rows; the bottom gets the remainder. Default `None` splits 50/50. Use when the top and bottom rows need different font sizes. Must be `> 0` and `< canvas.height`. |

## Animation

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `animation` | string | none | `"typewriter"` for character-by-character text reveal. Single-row only — raises if `bottom_text` is set or `text_align` is `"scroll"` / `"scroll_over"`. See rule 14. |

## Border and background

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `border` | string / table | none | Perimeter border effect — `"rainbow"`, `[r,g,b]` constant, or `{style="rainbow", thickness=N, speed=N, char_offset=N}`. Paints at physical panel resolution (bypasses ScaledCanvas), so the border traces the real panel edge. Paints after the image and before text. |
| `bg_color` | RGB list | none | Background fill for the full canvas before image and text. When set, pillarbox bands and alpha-transparent regions reveal this color instead of black. Use with a transparent-background PNG to blend the silhouette against a solid color. |
