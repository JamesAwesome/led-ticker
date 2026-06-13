# Clock Widget Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `format` | `"12h"` \| `"24h"` \| strftime template | `"12h"` | Time display format. The presets produce locale-independent output built from datetime fields (not strftime), so they render identically on every platform. A string containing `%` is passed to `strftime` verbatim — e.g. `"%H:%M"` or `"%a %b %d  %H:%M"` for an inline date. Note: `%-` codes (no-zero-pad) are a Linux-ism and will not work on macOS or Windows. |
| `timezone` | IANA name \| none | system local | Timezone override, e.g. `"America/New_York"`. Uses stdlib `zoneinfo` — no extra dependencies. Defaults to the system local timezone. |
| `font` | string | `"6x12"` | BDF font name (e.g., `"5x8"`, `"6x12"`) or hires font (e.g., `"Inter-Bold"`). |
| `font_size` | int | (BDF cell height) | Real-pixel font size for hires fonts. Required if `font` is a hires font name. |
| `font_color` | RGB list / string / table | `[255, 255, 255]` | Constant `[r,g,b]`, `"rainbow"`, `"color_cycle"`, `"random"`, or `{style="gradient", from=[...], to=[...]}`. |
| `bg_color` | RGB list | none | Background fill color. Painted across the full panel before text. |
| `border` | `"rainbow"` \| `"color_cycle"` \| `"lightbulbs"` \| `[r,g,b]` \| `{style="...", ...}` | none | Perimeter border ring — five styles (rainbow chase, color cycle, constant, bands, lightbulbs); see [/concepts/borders/](/concepts/borders/). |
| `center` | bool | `true` | Center the time string horizontally. Set to `false` to left-align. |
| `padding` | int | `6` | Horizontal padding (logical pixels) added at the end when the widget scrolls. |
