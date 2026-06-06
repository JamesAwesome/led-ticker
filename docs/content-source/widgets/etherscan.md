# Etherscan Widget Options

`EtherscanGasMonitor` fetches current Ethereum network gas prices from the [Etherscan Gas Oracle API](https://api.etherscan.io) and displays three tiers: `Low` (SafeGasPrice), `Avg` (ProposeGasPrice), and `High` (FastGasPrice), all in Gwei. **Requires an `ETHERSCAN_API_KEY` environment variable** — get a free key at [etherscan.io/apis](https://etherscan.io/apis).

**Gas price coloring:** Unlike the `coinbase` and `coingecko` widgets, the etherscan widget colors each gas value by absolute price level rather than delta — green (`UP_TREND_COLOR`) for ≤ 50 Gwei (cheap), yellow for 51–70 Gwei (moderate), and red (`DOWN_TREND_COLOR`) for > 70 Gwei (expensive). The traffic-light tier coloring on the gas values is automatic and not a TOML-tunable knob — `font_color` styles the label only; the gas values are always colored by threshold.

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `api_key` | string | none | Etherscan API key. The widget reads `ETHERSCAN_API_KEY` from your `.env` file, so you normally leave this unset; alternatively, set `api_key` here to put the key directly in config. The widget raises `ValueError` at startup if the API returns an error (e.g. bad or missing key). |
| `bg_color` | RGB list | none | Background fill color painted behind all content. |
| `font_color` | RGB list / string / table | yellow | Color of the label text. Accepts a constant `[r,g,b]`, the string shorthands `"rainbow"` / `"color_cycle"` / `"random"`, or an inline table for a gradient. The traffic-light tier coloring on the gas values is independent and always applies. |
| `update_interval` | int | `300` | Seconds between Etherscan API fetches (passed to `start()`). Default is 5 minutes. The Etherscan free tier allows 5 calls per second / 100,000 calls per day — 5 minutes is comfortably within limits. |
