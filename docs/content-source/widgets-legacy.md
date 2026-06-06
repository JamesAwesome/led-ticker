<!-- Derived from CLAUDE.md sections: Package Layout, Inline Emoji, Two-row widget, GIF widget and Still-image widget. Last synced: 2026-05-07. -->

# Widget Catalog

## `message` (TickerMessage)

**Purpose:** One-line scrolling text message. The bread-and-butter widget.

**When to use:**
- Welcome banners, announcements
- Anywhere you need plain text with optional inline `:slug:` emoji
- Use with `border = "rainbow"` for attention-grabbing

**Key TOML params:**
- `text` (required): the message string. Supports `:emoji:` slugs (baseball, taco, flower, star, sun, moon, cloud, partly_cloudy, rain, snow, thunder, fog, instagram, email).
- `font_color`: constant `[r,g,b]`, `"rainbow"`, `"color_cycle"`, or table `{style="gradient", from=..., to=...}`. Per-char providers sweep across emoji.
- `font` / `font_size` / `font_threshold`: optional. Required together for hires (TTF/OTF).
- `animation`: `"typewriter"` to type out characters one-by-one.
- `border`: `"rainbow"`, table `{style="rainbow", speed=N, char_offset=N, thickness=N}`, or constant `[r,g,b]`.
- `bg_color`: `[r,g,b]` background fill.
- `center`: `true` (default) to center horizontally; `false` left-aligns.
- `padding`: `6` (default) pixels of trailing space for scrolling separation.

**Gotchas:**
- Hires fonts MUST specify `font_size` (loader raises otherwise).
- `animation = "typewriter"` only supported on `message` — config-load raises on other widgets.
- BDF `font_size < cell_h` is invalid.
- Inline emoji carry their own colors; the surrounding `font_color` applies to the text.

---

## `countdown` (TickerCountdown)

**Purpose:** Displays a countdown to a date (e.g., "New Year: 42 days").

**When to use:**
- Holiday countdowns, event deadlines
- Updates daily; no network needed

**Key TOML params:**
- `message`: template string with `{count}` placeholder for the number (e.g., `"Days until launch: {count}"`).
- `countdown_date`: target date in `YYYY-MM-DD` format (e.g., `2026-12-25`). TOML date literal — not a string.
- `font_color`: same as `message` — constant, `"rainbow"`, `"color_cycle"`, or gradient table.
- `font` / `font_size` / `font_threshold`: optional; same rules as `message`.
- `border`: rainbow or constant; same as `message`.
- `bg_color`: background fill.
- `center`: horizontal alignment.
- `padding`: trailing space.

**Gotchas:**
- Target date is fixed at config load — updates happen per-visit, not per-tick.
- **Day-resolution only.** `countdown_date` is a `date` (not `datetime`); the widget computes `(target - today).days`. There's no hours/minutes countdown. For "open until 6pm tonight" use cases, frame as "Closing today" or use `message` widget with formatted text instead.
- When the countdown reaches zero (count ≤ 0), the message still displays with the count.

---

## `two_row` (TwoRowMessage)

**Purpose:** Held top row + scrolling bottom row for tall canvases (bigsign).

**When to use:**
- Handle + scrolling status (e.g., "@User: New subscriber!").
- Best in `swap` mode so each widget is a complete display unit.
- Pair with `scale = 2` on bigsign so content fits comfortably.

**Key TOML params:**
- `top_text`: held text (e.g., "@MoonBunny").
- `bottom_text`: scrolling text when it overflows (e.g., promotional copy).
- `top_color` / `bottom_color`: per-row color providers (constant, "rainbow", "color_cycle", or gradient table).
- `font` / `top_font` / `bottom_font`: shared or per-row fonts.
- `font_size` / `top_font_size` / `bottom_font_size`: per-row sizes (real pixels for hires).
- `font_threshold` / `top_font_threshold` / `bottom_font_threshold`: per-row rasterization cutoff (0-255, default 128). Match Bold to Regular's value within a family.
- `top_align` / `bottom_align`: `"left"`, `"center"`, `"right"` (bottom alignment only applies when text fits).
- `top_row_height`: logical rows for the top band (default `None` = 50/50 split).
- `top_text_y_offset` / `bottom_text_y_offset`, `top_emoji_y_offset` / `bottom_emoji_y_offset`: per-row pixel nudges.
- `border`: rainbow or constant; paints around the physical panel.
- `bg_color`: background.
- `padding`: trailing space.

**Gotchas:**
- Hard ceiling: `content_height * scale ≤ panel_h_real`. On bigsign (scale=4), max is `content_height = 16`.
- Hi-res `:instagram:` emoji at `top_row_height < 4` may clip vertically; use `text_y_offset` to nudge instead.
- Inline emoji in both rows get `top_emoji_y_offset` and `bottom_emoji_y_offset` nudges (not shared).

---

## `weather` (WeatherWidget)

**Purpose:** Current temperature + condition icon from WeatherAPI.com.

**When to use:**
- Local weather display with auto-refreshing.
- Requires `WEATHERAPI_KEY` in `.env` (free tier available).

**Key TOML params:**
- `location`: query string — "New York", ZIP code, or lat/lon comma-separated (e.g., `"40.71,-74.01"`).
- `message`: template string for label (e.g., `"Brooklyn:"`).
- `units`: `"imperial"` (Fahrenheit, default) or `"metric"` (Celsius).
- `font_color`: label color (constant, "rainbow", "color_cycle", or gradient).
- `font_color_temp`: temperature value color (separate from label; default white for contrast).
- `show_icon`: `true` (default) to draw the 8×8 weather condition icon.
- `font` / `font_size` / `font_threshold`: label font (optional).
- `bg_color`: background fill.
- `center`: horizontal alignment.
- `padding`: trailing space.

**Gotchas:**
- Two color knobs: `font_color` (label) and `font_color_temp` (value) are independent so you can rainbow the label while keeping the temp bright.
- API key missing → widget logs error and shows stale data (or zeros on first run).
- Icon placement is automatic and centered; no separate positioning param.

---

## `rss_feed` (RSSFeedMonitor)

**Purpose:** Fetches RSS feed headlines and displays them as scrolling messages.

**When to use:**
- News feeds, blog updates, any RSS-compatible source
- Stories expand into TickerMessage widgets internally (no native draw method).

**Key TOML params:**
- `feed_url`: URL to the RSS/Atom feed (e.g., `"https://feeds.example.com/news"`).
- `font_color`: per-story color (constant, "rainbow", "color_cycle", or gradient). If unset, rotates between DEFAULT / DOWN / UP trend colors.
- `max_stories`: `5` (default) maximum headlines to fetch.
- `bg_color`: background for all stories.
- `padding`: trailing space.

**Gotchas:**
- The widget builds TickerMessage objects for each story internally; no `draw()` method exposed.
- Stories are refreshed on `update_interval` (default 30 minutes).
- `font_color` applies to ALL stories; omit it for the legacy 3-color rotation.
- Feed title becomes the first "story" if the feed defines it.

---

## `mlb` (MLBMonitor)

**Purpose:** Live MLB game scores for specified teams.

**When to use:**
- Baseball fans; updates during games (~45s cadence), otherwise every 5 minutes.
- Uses the free MLB Stats API (no key needed).

**Key TOML params:**
- `teams`: list of 3-letter team abbreviations (e.g., `["NYY", "BOS", "TB"]`).
- `title`: section title string (e.g., `"AL East"`).
- `timezone`: IANA timezone string (default `"America/New_York"`).
- `bg_color`: background.
- `font`: widget font.
- `padding`: trailing space.

**Gotchas:**
- Displays live games with scores; pre-game shows countdown, post-game shows final score.
- Off-season (no games scheduled) enters daily-update mode.
- Team colors are baked in (red Yankees, blue Red Sox, etc.).

---

## `mlb_standings` (MLBStandingsMonitor)

**Purpose:** MLB standings showing top N teams + your tracked teams.

**When to use:**
- Season overview; refreshes daily (no need for live updates).

**Key TOML params:**
- `teams`: list of team abbreviations to always show (e.g., `["NYY", "TB"]`).
- `title`: section title (e.g., `"MLB Standings"`).
- `top_n`: `3` (default) highest-ranked teams to show.
- `timezone`: IANA timezone (default `"America/New_York"`).
- `bg_color`: background.
- `font`: widget font.
- `padding`: trailing space.

**Gotchas:**
- Shows top N teams PLUS any from your `teams` list not already in top N.
- Updates once per day (off-season or regular season).
- Off-season detection suppresses "Games Back" column.

---

## `gif` (GifPlayer)

**Purpose:** Plays an animated GIF or other Pillow-supported format (webp, apng, multi-frame tiff).

**When to use:**
- Animated graphics, video clips, frame-by-frame sequences.
- Paints at native physical resolution (not scaled), so each pixel is an LED.

**Key TOML params (image surface):**
- `path`: path to file (relative to config.toml dir).
- `fit`: `"pillarbox"` (default), `"letterbox"`, `"stretch"`, or `"crop"`.
- `image_align`: `"left"`, `"center"`, `"right"` (pillarbox anchor; default center).
- `text` / `top_text` / `bottom_text`: optional overlay text(s); supports `:slug:` emoji.
- `text_align`: `"auto"`, `"left"`, `"right"`, `"scroll"`, `"scroll_over"` (how text positions relative to image).
- `text_valign`: `"top"`, `"center"`, `"bottom"`.
- `text_y_offset` / `text_x_offset`: pixel nudges.
- `scroll_direction`: `"left"` or `"right"` (marquee travel direction).
- `font_color`: overlay text color.
- `scroll_speed_ms`: `50` (default) tick cadence for scrolling.
- `font` / `font_size` / `font_threshold`: overlay text font.
- `bg_color`: background (lettebox/pillarbox fill).
- `animation`: `"typewriter"` (single-row text only); typed per-frame on canvas.
- `border`: rainbow or constant perimeter border.

**Key TOML params (gif-specific):**
- `gif_loops`: per-visit loop count (default `1`).
- `text_loops`: floor on marquee passes before section transition (default `0`).

**Gotchas:**
- Per-frame durations are read from the source; fastest cap is ~50ms (20 Hz).
- `text_loops > 0` forces the marquee to complete at least that many full passes, extending the section duration transparently.
- `text_align="scroll"` + `fit="stretch"` is invalid (scroll needs transparent regions).
- Typewriter single-row only; raises if `bottom_text != ""`.

---

## `image` (StillImage)

**Purpose:** Displays a single PNG / JPG / single-frame GIF with optional text overlay.

**When to use:**
- Static images (logos, photos), promotional graphics.
- Same text-overlay surface as `gif`; only difference is `hold_time` vs `gif_loops`.

**Key TOML params (image surface):**
- Same as `gif` (path, fit, image_align, text, text_align, etc.).
- `font` / `font_size` / `font_threshold`: overlay text font.
- `bg_color`: background fill.
- `animation`: `"typewriter"` (single-row text only).
- `border`: rainbow or constant.

**Key TOML params (image-specific):**
- `hold_time`: `5.0` (default) per-visit display duration. With `text_loops > 0`, becomes a FLOOR: `max(hold_time, text_loops × traversal)`.
- `text_loops`: floor on marquee passes (default `0`).

**Gotchas:**
- `hold_time < 0.05` is rejected.
- Transparent PNGs and palette-transparent GIFs composite onto black, so skip-black scroll text walks "behind" the silhouette.
- Static-text fast path (left/right align, no scroll) paints once and sleeps the duration instead of re-drawing every tick.

---

## `crypto.coinbase` (CoinbasePriceMonitor)

**Purpose:** Crypto price ticker using Coinbase API (no key needed, free tier).

**When to use:**
- Live crypto prices (Bitcoin, Ethereum, etc.).
- Updates every 5 minutes.

**Key TOML params:**
- `symbol`: crypto symbol (e.g., `"BTC"`, `"ETH"`).
- `currency`: fiat currency (e.g., `"USD"`, `"EUR"`).
- `center`: `true` (default) to center horizontally.
- `bg_color`: background fill.
- `padding`: trailing space.

**Gotchas:**
- Displays current price + 24h change with trend colors (green up, red down, grey neutral).
- Large prices (>10 digits) auto-scale to a smaller font to fit.
- Coinbase API may rate-limit; respects 5-minute update interval.

---

## `crypto.coingecko` (CoinGeckoPriceMonitor)

**Purpose:** Crypto price ticker using CoinGecko API (free, no key required).

**When to use:**
- Broader coin coverage than Coinbase (thousands of altcoins).
- Updates every 5 minutes.

**Key TOML params:**
- `symbol`: ticker symbol for display (e.g., `"BTC"`, `"SHIB"`).
- `symbol_id`: CoinGecko ID (e.g., `"bitcoin"`, `"shiba-inu"`); see CoinGecko's coin list.
- `currency`: fiat currency (e.g., `"USD"`, `"GBP"`).
- `center`: `true` (default).
- `bg_color`: background.
- `padding`: trailing space.

**Gotchas:**
- Symbol ID must match CoinGecko's internal naming; look it up on their API docs.
- Same 24h change color scheme as Coinbase (green/red/grey).
- Free tier has rate limits; 5-minute cadence is safe.

---

## `crypto.etherscan` (EtherscanGasMonitor)

**Purpose:** Ethereum gas price monitor (Gwei) using Etherscan API.

**When to use:**
- DeFi users watching transaction costs.
- Updates every 5 minutes.

**Key TOML params:**
- `api_key`: your free Etherscan API key (get one at etherscan.io).
- `bg_color`: background.
- `padding`: `0` (default) — uses hardcoded per-segment spacing.

**Gotchas:**
- Requires a valid Etherscan API key (free registration).
- Displays three gas tiers: Safe / Standard / Fast (in Gwei).
- Color feedback: green ≤50 (cheap), yellow 50–70 (ok), red >70 (expensive).
- Etherscan API requires the key in the params; no OAuth.

---

## Inline Emoji Reference

Available emoji slugs (8×8 pixels on small sign, 32×32 hi-res on bigsign where noted):

- Weather: `:sun:`, `:cloud:`, `:partly_cloudy:`, `:rain:`, `:snow:`, `:thunder:`, `:fog:`
- Objects: `:baseball:` (hi-res), `:taco:`, `:flower:`, `:star:` (hi-res), `:moon:` (hi-res)
- Social: `:instagram:` (hi-res), `:email:`

Add a new emoji by appending pixel data to `src/led_ticker/pixel_emoji.py` and registering the slug.
