# Countdown Widget Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `text` | string | required | Label shown before the day count, e.g. `"Until Summer"` renders as `"Until Summer: 42"`. |
| `countdown_date` | date | required | Target date in TOML date syntax: `2026-12-25`. The day count is recomputed on every draw so the value updates at midnight without restarting the process. |
| `font` | string | `"6x12"` | BDF font name (e.g., `"5x8"`, `"6x12"`) or hires font (e.g., `"Inter-Bold"`). |
| `font_size` | int | (BDF cell height) | Real-pixel font size for hires fonts. Required if `font` is a hires font name. |
| `font_threshold` | int 0–255 | `128` | Rasterization threshold for hires fonts. Lower = thicker glyphs. |
| `font_color` | RGB list / string / table | `[255, 255, 0]` | Constant `[r,g,b]`, `"rainbow"`, `"color_cycle"`, `"random"`, or `{style="gradient", from=[...], to=[...]}`. |
| `bg_color` | RGB list | none | Background fill color. Painted across the full panel before text. |
| `border` | string / table | none | `"rainbow"`, `[r,g,b]` constant, or `{style="rainbow", thickness=N, speed=N, char_offset=N}`. |
| `padding` | int | `6` | Horizontal padding (logical pixels) added when text scrolls. |
