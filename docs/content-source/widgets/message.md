# Message Widget Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `text` | string | required | The text to display. Inline `:slug:` emoji are rendered as pixel art. |
| `font` | string | `"6x12"` | BDF font name (e.g., `"5x8"`, `"6x12"`) or hires font (e.g., `"Inter-Bold"`). |
| `font_size` | int | (BDF cell height) | Real-pixel font size for hires fonts. Required if `font` is hires. |
| `font_threshold` | int 0–255 | `128` | Rasterization threshold for hires fonts. Lower = thicker glyphs. |
| `font_color` | RGB list / string / table | `[255, 255, 0]` | Constant `[r,g,b]`, `"rainbow"`, `"color_cycle"`, `"random"`, or `{style="gradient", from=[...], to=[...]}`. |
| `bg_color` | RGB list | none | Background fill color. Painted across the full panel before text. |
| `border` | string / table | none | `"rainbow"`, `[r,g,b]` constant, or `{style="rainbow", thickness=N, speed=N, char_offset=N}`. |
| `animation` | string / table | none | `"typewriter"` for character-by-character reveal. Use the inline-table form to tune speed: `animation = {style = "typewriter", frames_per_char = 6}` (default `frames_per_char = 3` ≈ 150 ms/char at the 50 ms engine tick). |
| `padding` | int | `6` | Horizontal padding (in logical pixels) when scrolling. |
| `text_y_offset` | int | `0` | Vertical text nudge in logical rows. Negative = up. |
