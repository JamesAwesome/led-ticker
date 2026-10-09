# weather.current Widget Options

Requires `WEATHERAPI_KEY` in the environment (your `.env` on a Docker deploy). Get a free key at [weatherapi.com](https://www.weatherapi.com/).

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `location` | string or table | required | WeatherAPI query: a city name (`"Brooklyn, NY"`), a postal code (`"10001"`), a `"lat,lon"` string, or a table `{ lat = 40.71, lon = -74.01 }`. |
| `text` | string | required | The label painted before the icon and temperature — `text = "BROOKLYN"` renders as `BROOKLYN: ☀ 71F`. It is a label, not a lookup; `location` decides whose weather you get. |
| `units` | `"imperial"` \| `"metric"` | `"imperial"` | `imperial` shows °F, `metric` shows °C. The unit letter is appended to the temperature. |
| `font` | string | `"6x12"` | BDF font name (e.g. `"5x8"`, `"6x12"`) or a hires font (e.g. `"Inter-Bold"`). |
| `font_size` | int | (BDF cell height) | Real-pixel font size for hires fonts. Required if `font` is hires. |
| `font_threshold` | int 0–255 | per font | Rasterization threshold for hires fonts; the default follows the font (Inter-Bold 128, Inter-Regular 80). See [font_threshold](/concepts/fonts/#font_threshold). |
| `font_color` | RGB list / string / table | `[255, 255, 0]` | Color for the label. Constant `[r,g,b]`, `"rainbow"`, `"color_cycle"`, `"random"`, or `{style="gradient", from=[...], to=[...]}`. |
| `font_color_temp` | RGB list / string / table | `[255, 255, 255]` | Color for the temperature value. Defaults to white so the number stands apart from the label; set it to the same provider as `font_color` to make them match. |
| `bg_color` | RGB list | none | Background fill, painted across the full panel before the text. |
| `show_icon` | bool | `true` | Draw the condition icon between the label and the temperature — a hi-res sprite on scaled signs, the hand-drawn 8×8 pixel icon at scale 1. `false` prints the condition as text instead (`BROOKLYN: Sunny 71F`). |
| `center` | bool | `true` | Center the line on the panel when it fits. `false` left-aligns. |
| `padding` | int | `6` | Horizontal padding (logical pixels) after the line when it is too wide to hold and scrolls instead. |
| `update_interval` | int seconds | `10800` | Seconds between fetches — three hours by default. Current conditions do not change minute to minute, and a slow poll keeps a free key far inside its monthly allowance. Do not go below 60. |
