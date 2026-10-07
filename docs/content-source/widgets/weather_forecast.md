# weather.forecast Widget Options

`location` is the only required option, and only when `demo = false`. The API key comes from the `WEATHERAPI_KEY` environment variable, never from `config.toml`.

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `location` | string or table | — | What to forecast: a city name (`"Boston"`), a postal code, or a lat/lon table (`{ lat = 42.36, lon = -71.06 }`), same convention as [`weather.current`](/widgets/weather/). Required unless `demo = true`. |
| `layout` | `"auto"` \| `"strip"` \| `"big"` \| `"long"` | `"auto"` | Render shape. `auto` resolves per sign on every draw: `strip` at scale 1, `big` on hi-res panels under 400 physical px, `long` at 400 px and wider. See [Layouts](#layouts-one-per-sign-shape). |
| `units` | `"imperial"` \| `"metric"` | `"imperial"` | Temperature units. Rejected at config-load if it is anything else. |
| `update_interval` | int seconds | `10800` | Seconds between API polls — 3 hours by default, which is plenty for a forecast and keeps a free key well inside its monthly allowance. Must be positive. |
| `demo` | bool | `false` | Render a fixed sample week with no API key and no network. Every GIF on this page was rendered this way. |
| `demo_days` | int | `0` | Demo-only: truncate the sample week to this many day columns (`0` = the full 6) to preview a **short feed** — the strip spreading fewer days across the panel. Ignored unless `demo = true`. |
| `bg_color` | RGB list | none | Background fill. Declared for the engine, which paints the background; the layouts themselves never fill. |
