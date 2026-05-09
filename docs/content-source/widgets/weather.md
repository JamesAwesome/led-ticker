# Weather Widget Options

Requires `WEATHERAPI_KEY` set in your `.env` file. Get a free key at [weatherapi.com](https://www.weatherapi.com/).

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `location` | string or table | required | WeatherAPI query: city name (`"Brooklyn, NY"`), ZIP code (`"10001"`), or `{lat = 40.71, lon = -74.01}`. |
| `message` | string | required | Label shown before the condition icon and temperature, e.g. `"Brooklyn"` renders as `Brooklyn: ☁ 64F`. |
| `units` | string | `"imperial"` | `"imperial"` (°F) or `"metric"` (°C). |
| `font` | string | `"6x12"` | BDF font name (e.g., `"5x8"`, `"6x12"`) or hires font (e.g., `"Inter-Bold"`). |
| `font_color` | RGB list / string / table | `[255, 255, 0]` | Color for the label text (`"Brooklyn: "`). Constant `[r,g,b]`, `"rainbow"`, `"color_cycle"`, `"random"`, or `{style="gradient", from=[...], to=[...]}`. |
| `font_color_temp` | RGB list / string / table | `[255, 255, 255]` | Color for the temperature value (`"64F"`). Defaults to white for high contrast. Set to the same provider as `font_color` to make them match. |
| `bg_color` | RGB list | none | Background fill color. Painted across the full panel before text. |
| `show_icon` | bool | `true` | When `true`, draws the 8×8 pixel-art condition icon (sun, cloud, rain, snow, thunder, fog, partly cloudy) between the label and the temperature. When `false`, shows the condition text string instead. |
| `center` | bool | `true` | Center the content on the canvas. Set `false` to left-align. |
| `padding` | int | `6` | Horizontal padding (logical pixels) added when scrolling. |
| `update_interval` | int | `10800` | Seconds between API fetches. Default is 3 hours. Do not set below 60 to avoid rate limiting. |
