# CoinGecko Widget Options

`CoinGeckoPriceMonitor` fetches the current price and 24-hour change for a cryptocurrency from the [CoinGecko API](https://api.coingecko.com). It shares the same on-screen layout as the `coinbase` widget (symbol · price · change%) and renders via the same drawing helper. No API key is required for the public tier, but CoinGecko's free tier has stricter rate limits than Coinbase.

CoinGecko uses a **coin ID** (`symbol_id`) rather than a trading pair symbol — `"bitcoin"` instead of `"BTC-USD"`. The display label is the short `symbol` you provide (e.g. `"BTC"`). You must supply both fields: `symbol` for what appears on screen and `symbol_id` for the API query.

**Trend coloring:** The price change value (e.g. `+2.35%`) is automatically colored using shared color constants — green (`UP_TREND_COLOR`) when the price is up, red (`DOWN_TREND_COLOR`) when it is down, and gray (`NEUTRAL_TREND_COLOR`) when the change is zero or on the very first fetch. This coloring is automatic and not a TOML-tunable knob. Use `font_color` to style the label (the coin symbol), and the trend colors will apply automatically to the price and change percentage field.

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `symbol` | string | required | Short ticker shown on screen, e.g. `"BTC"`, `"ETH"`, `"SOL"`. This is purely a display label — it does not affect the API query. |
| `symbol_id` | string | required | CoinGecko coin ID used in the API query, e.g. `"bitcoin"`, `"ethereum"`, `"solana"`. Look up IDs at [coingecko.com/en/coins/list](https://www.coingecko.com/en/coins/list). |
| `currency` | string | required | Quote currency for the price, e.g. `"usd"`, `"eur"`. Must match a CoinGecko-supported vs_currency string (lowercase). |
| `center` | bool | `true` | Center the content on the canvas. Set `false` to left-align. |
| `padding` | int | `6` | Horizontal padding (logical pixels) added between segments and at the end when scrolling. |
| `bg_color` | RGB list | none | Background fill color painted behind all content. |
| `update_interval` | int | `300` | Seconds between CoinGecko API fetches (passed to `start()`). Default is 5 minutes. The CoinGecko free tier allows ~10–30 calls per minute — keep this at 60 seconds or above to stay safe. |
