# Coinbase Widget Options

`CoinbasePriceMonitor` fetches the current spot price for a cryptocurrency pair from [Coinbase's public API](https://api.coinbase.com) and displays it alongside the 24-hour change percentage. No API key is required.

**Trend coloring:** The price change value (e.g. `+2.35%`) is automatically colored using shared color constants — green (`UP_TREND_COLOR`) when the price is up vs the previous fetch, red (`DOWN_TREND_COLOR`) when it is down, and gray (`NEUTRAL_TREND_COLOR`) when the change is zero or on the very first fetch. This coloring is automatic and not a TOML-tunable knob. Use `font_color` to style the label (the coin symbol), and the trend colors will apply automatically to the price and change percentage field.

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `symbol` | string | required | Trading pair to display, e.g. `"BTC-USD"`, `"ETH-USD"`, `"SOL-USD"`. Must be a valid Coinbase spot price symbol — the widget constructs the API URL as `/v2/prices/<symbol>-<currency>/spot`. |
| `currency` | string | required | Quote currency for the price, e.g. `"USD"`, `"EUR"`. |
| `center` | bool | `true` | Center the content on the canvas. Set `false` to left-align. |
| `padding` | int | `6` | Horizontal padding (logical pixels) added between segments and at the end when scrolling. |
| `bg_color` | RGB list | none | Background fill color painted behind all content. |
| `font_color` | RGB list / string / table | yellow | Color of the symbol label and price text. Accepts a constant `[r,g,b]`, the string shorthands `"rainbow"` / `"color_cycle"` / `"random"`, or an inline table for a gradient. The trend coloring on the change percent (`UP_TREND_COLOR` / `DOWN_TREND_COLOR` / `NEUTRAL_TREND_COLOR`) is independent and always applies. |
| `update_interval` | int | `300` | Seconds between Coinbase API fetches (passed to `start()`). Default is 5 minutes. The Coinbase public API has no documented rate limit but aggressive polling is not recommended. |
