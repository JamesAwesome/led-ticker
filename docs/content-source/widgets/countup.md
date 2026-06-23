# Countup Widget Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `text` | string | required | Label shown before the day count, e.g. `"Days since launch"` renders as `"Days since launch: 42"`. |
| `countup_date` | date | required | Start date in TOML date syntax: `2024-01-01`. The day count is recomputed on every draw so the value updates at midnight without restarting the process. Widget does not display until this date arrives. |
| `font` | string | `"6x12"` | BDF font name (e.g., `"5x8"`, `"6x12"`) or hires font (e.g., `"Inter-Bold"`). |
| `font_size` | int | (BDF cell height) | Real-pixel font size for hires fonts. Required if `font` is a hires font name. |
| `font_threshold` | int 0–255 | `128` | Rasterization threshold for hires fonts. Lower = thicker glyphs. |
| `font_color` | RGB list / string / table | `[255, 255, 0]` | Constant `[r,g,b]`, `"rainbow"`, `"color_cycle"`, `"random"`, or `{style="gradient", from=[...], to=[...]}`. |
| `bg_color` | RGB list | none | Background fill color. Painted across the full panel before text. |
| `border` | `"rainbow"` \| `"color_cycle"` \| `"lightbulbs"` \| `[r,g,b]` \| `{style="...", ...}` | none | Perimeter border ring — five styles (rainbow chase, color cycle, constant, bands, lightbulbs); see [/concepts/borders/](/concepts/borders/). |
| `padding` | int | `6` | Horizontal padding (logical pixels) added when text scrolls. |
| `timezone` | IANA name \| none | system local | Timezone for computing the day count and the show/hide boundary, e.g. `"America/New_York"`. Uses stdlib `zoneinfo` — no extra dependencies. Defaults to the sign's local date. |
