# Widget Selection Guide

Use this guide to **choose** widgets — what each one is for, when to reach for it, and the constraints that bear on whether it fits a section. It is the catalog the wizard offers for "what kind of section do you want?".

**For a widget's option/parameter details (every field, type, default), read its fact-pack:** `docs/content-source/widgets/<type>.md` (e.g. `docs/content-source/widgets/message.md`). Those fact-packs are the source of truth for params — author TOML from them, not from this guide.

---

## `message` (TickerMessage)

**Purpose:** One-line scrolling text message. The bread-and-butter widget.

**When to use:**
- Welcome banners, announcements.
- Anywhere you need plain text with optional inline `:slug:` emoji.
- Use with `border = "rainbow"` for an attention-grabbing section.

**Selection notes:**
- The only widget that supports `animation = "typewriter"` — config-load raises if you set it on any other widget.

---

## `countdown` (TickerCountdown)

**Purpose:** Counts down to a date (e.g. "New Year: 42 days").

**When to use:**
- Holiday countdowns, event deadlines.
- Updates daily; no network needed.

**Selection notes:**
- **Day-resolution only.** `countdown_date` is a `date`, not a `datetime`; the widget computes `(target - today).days`. There is no hours/minutes countdown. For "open until 6pm tonight" use cases, frame it as "Closing today" or use a `message` widget with formatted text instead.
- At zero (count ≤ 0) the message still displays with the count.

---

## `two_row` (TwoRowMessage)

**Purpose:** Held top row + scrolling bottom row for tall canvases.

**When to use:**
- Handle + scrolling status (e.g. "@User: New subscriber!").
- Best in `swap` mode so each widget is a complete display unit.

**Selection notes:**
- Needs vertical room: hard ceiling `content_height × scale ≤ panel_h_real` (on bigsign at scale=4, max `content_height = 16`). Don't pick `two_row` for a short canvas.
- Pair with `scale = 2` on bigsign so content fits comfortably.

---

## `weather` (WeatherWidget)

**Purpose:** Current temperature + condition icon from WeatherAPI.com.

**When to use:**
- Local weather display with auto-refresh.

**Selection notes:**
- Requires `WEATHERAPI_KEY` in `.env` (free tier available). Missing key → the widget logs an error and shows stale data (or zeros on first run). Confirm the user has a key before choosing this.

---

## `rss_feed` (RSSFeedMonitor)

**Purpose:** Fetches RSS/Atom headlines and displays them as scrolling messages.

**When to use:**
- News feeds, blog updates, any RSS-compatible source.

**Selection notes:**
- Each story expands into a scrolling line internally; stories refresh on a ~30-minute interval, so this is for slowly-changing content, not live data.

---

## `gif` (GifPlayer)

**Purpose:** Plays an animated GIF or other multi-frame format (webp, apng, multi-frame tiff).

**When to use:**
- Animated graphics, video clips, frame-by-frame sequences.
- Paints at native physical resolution (each pixel is an LED), not scaled.

**Selection notes:**
- For a *still* image, use `image` instead — the difference is `gif` loops frames (`play_count`) while `image` holds (`hold_time`).
- Supports optional overlay text with the same text surface as `image`.

---

## `image` (StillImage)

**Purpose:** Displays a single PNG / JPG / single-frame GIF with optional text overlay.

**When to use:**
- Static images (logos, photos), promotional graphics.

**Selection notes:**
- Same text-overlay surface as `gif`; the difference is duration (`image` holds for `hold_time`, `gif` loops for `play_count`).
- For animated files only frame 0 is decoded — use `gif` for animation.
- Transparent PNGs / palette-transparent GIFs composite onto black (or `bg_color` if set), so scroll text can walk "behind" the silhouette.

---

## Plugin widgets (not built-in)

These widgets are NOT part of core — they ship as separate plugins and must be installed (added to `config/requirements-plugins.txt`, then rebuild) before a config that uses them will load. Don't offer them as built-in choices; only reach for them if the user already has the plugin installed.

- **`baseball.scores`** / **`baseball.standings`** — live MLB game scores and standings. Ship as the [`led-ticker-baseball`](https://github.com/JamesAwesome/led-ticker-baseball) plugin (which also brings the `baseball.roll*` transition and `:baseball.ball:` emoji). If installed, see fact-packs `docs/content-source/widgets/mlb.md` (scores) and `docs/content-source/widgets/mlb_standings.md` (standings) for purpose and options.
- **`pool.monitor`** — pool water temperature from InfluxDB. Ships as the [`led-ticker-pool`](https://github.com/JamesAwesome/led-ticker-pool) plugin. If installed, see fact-pack `docs/content-source/widgets/pool.md` for purpose and options.
- **`crypto.coingecko`** — live CoinGecko price ticker for any supported coin/currency pair; no API key required (free tier). Ships as the [`led-ticker-crypto`](https://github.com/JamesAwesome/led-ticker-crypto) plugin. If installed, see the plugin's README for `symbol_id`, `symbol`, `currency`, and `font_color` options.
