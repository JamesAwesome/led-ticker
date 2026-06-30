<!-- Derived from CLAUDE.md sections: Widget Protocol, Key Patterns, Configuration, Color providers and animations, Adding a New Widget. Last synced: 2026-05-07. -->

# Snippet Catalog

Each snippet cites its source file + line range. The skill copies the snippet verbatim, then customizes the fields listed under "must customize".

## Index by (use_case, widget, sign)

| Use case | Widget | Sign | Snippet ID |
|----------|--------|------|------------|
| store_window | message | big | `message.store_window.bigsign.welcome` |
| store_window | two_row | big | `two_row.store_window.bigsign.handle` |
| store_window | gif | big | `gif.store_window.bigsign.logo` |
| store_window | weather | big | `weather.store_window.bigsign.brand` |
| store_window | countdown | big | `countdown.store_window.bigsign.hours` |
| personal_feed | rss.feed | small | `rss_feed.personal_feed.smallsign.headlines` |
| personal_feed | rss.feed | big | `rss_feed.personal_feed.bigsign.headlines` |
| personal_feed | weather.current | small | `weather.personal_feed.smallsign.simple` |
| personal_feed | weather.current | big | `weather.personal_feed.bigsign.simple` |
| event | countdown | small | `countdown.event.smallsign` |
| event | countdown | big | `countdown.event.bigsign` |
| sports | baseball.scores (plugin) | small | `mlb.sports.smallsign` |
| sports | baseball.scores (plugin) | big | `mlb.sports.bigsign` |
| sports | baseball.standings (plugin) | big | `mlb_standings.sports.bigsign` |
| art | gif | big | `gif.art.bigsign.full_panel` |
| art | image | big | `image.art.bigsign.full_panel` |
| art | message | big | `message.art.bigsign.rainbow_border` |
| mixed | message | small | `message.mixed.smallsign` |
| mixed | message | big | `message.mixed.bigsign` |
| mixed | two_row | big | `two_row.mixed.bigsign.dual_message` |

---

## Snippets

### snippet: message.store_window.bigsign.welcome

**source:** `config/config.firebird.example.toml` lines 59–76

**use when:** bigsign + brand presence + welcoming banner scrolling in `ticker` mode. Good opener for any storefront section.

**must customize:** `text` (brand message), `font_color` (brand color), `loop_count`, and the title `text` + `font_color`.

**copy verbatim:**

```toml
[[playlist.section]]
mode = "ticker"
loop_count = 2

[playlist.section.title]
type = "message"
text = "FIREBIRD YOGA"
font_color = [255, 92, 38]

[[playlist.section.widget]]
type = "message"
text = "Breathe Deep :heart: Flow Strong :heart_green: Rise Together"
font_color = [255, 244, 214]

[[playlist.section.widget]]
type = "message"
text = "Beginner Friendly - Drop-Ins Welcome - Every Body Welcome"
font_color = [255, 183, 3]
```

---

### snippet: two_row.store_window.bigsign.handle

**source:** `config/config.firebird.example.toml` lines 183–227

**use when:** bigsign + storefront window layout with a persistent handle on top and rotating promotional copy scrolling on the bottom. `scale = 2` widens the logical canvas to 128px so long handles fit.

**must customize:** `top_text` (handle / brand name), `top_color`, `bottom_text` (promo copy — one widget per message), `bottom_color`, `hold_time`.

**copy verbatim:**

```toml
[[playlist.section]]
mode = "slideshow"
scale = 2
content_height = 20
loop_count = 1
hold_time = 3.0
transition = "dissolve"
transition_duration = 0.8

[[playlist.section.widget]]
type = "two_row"
top_text = ":instagram: @firebirdyoga.demo"
top_color = [255, 92, 38]
top_align = "center"
bottom_text = "Now booking spring sessions — your first class is free."
bottom_color = [255, 244, 214]
bottom_align = "left"

[[playlist.section.widget]]
type = "two_row"
top_text = ":instagram: @firebirdyoga.demo"
top_color = [255, 92, 38]
top_align = "center"
bottom_text = "BEGINNER SERIES :star: NOW ENROLLING :star: ALL LEVELS WELCOME"
bottom_color = [255, 183, 3]
bottom_align = "left"
```

---

### snippet: gif.store_window.bigsign.logo

**source:** `config/config.gif_text.example.toml` lines 75–91

**use when:** bigsign + animated logo or mascot GIF in the left pillar with a brand handle or tagline held statically in the right pillar.

**must customize:** `path` (your GIF asset path), `text` (brand text in pillar), `font_color`, `font_size`, `loop_count`.

**copy verbatim:**

```toml
[[playlist.section]]
mode = "gif"
loop_count = 17
transition = "dissolve"
transition_duration = 0.6

[[playlist.section.widget]]
type = "gif"
path = "assets/logo.gif"
fit = "pillarbox"
image_align = "left"
text = "@yourbrand"
text_align = "right"
font = "Inter-Bold"
font_size = 24
font_color = [255, 220, 50]
```

---

### snippet: weather.store_window.bigsign.brand

**source:** `config/config.showroom-bigsign.example.toml` lines 231–248

**use when:** bigsign + live weather with hi-res condition icon, city label, and brand-colored temperature. Demonstrates live data in a store-window setting.

**must customize:** `text` (city label shown on panel), `location` (city/zip/lat-lon for API), `font_color` (brand color for label), `font_color_temp` (temperature color — keep white for readability), `font_size`, `hold_time`.

**copy verbatim:**

```toml
[[playlist.section]]
mode = "slideshow"
hold_time = 7.0
loop_count = 1
transition = "nyancat.forward"
transition_duration = 1.5

[[playlist.section.widget]]
type = "weather.current"
text = "Brooklyn"
location = "Brooklyn"
units = "imperial"
show_icon = true
font = "Inter-Regular"
font_size = 14
font_color = "color_cycle"
font_color_temp = [255, 255, 255]
```

---

### snippet: countdown.store_window.bigsign.hours

**source:** `config/config.showroom-bigsign.example.toml` lines 383–397

**use when:** bigsign + countdown to a real future date with hi-res rainbow font. Good storefront finale (e.g. "Days to Grand Opening", "Days to Next Event").

**must customize:** `text` (label text), `countdown_date` (YYYY-MM-DD), `font_color` (or replace `"rainbow"` with a brand color `[r,g,b]`), `hold_time`.

**copy verbatim:**

```toml
[[playlist.section]]
mode = "slideshow"
hold_time = 7.0
loop_count = 1
transition = "nyancat.alternating"
transition_duration = 1.5

[[playlist.section.widget]]
type = "countdown"
text = "Days to NYE"
countdown_date = 2027-01-01
font = "Inter-Bold"
font_size = 24
font_color = "rainbow"
```

---

### snippet: rss_feed.personal_feed.smallsign.headlines

**source:** `config/config.small_sign.toml` lines 125–141

**use when:** small sign (160×16) + RSS headlines scrolling in `ticker` mode. Good for news, blog, or any Atom/RSS feed.

**must customize:** `feed_url`, `update_interval` (seconds between fetches), title `text` + `color`.

**copy verbatim:**

```toml
[[playlist.section]]
mode = "slideshow"
transition = "pokeball.alternating"
transition_duration = 2.0
continuous_scroll = true
loop_count = 1

[playlist.section.title]
type = "message"
text = "Nintendo Life"
font_color = "random"

[[playlist.section.widget]]
type = "rss.feed"
feed_url = "https://www.nintendolife.com/feeds/news"
update_interval = 3000
```

---

### snippet: rss_feed.personal_feed.bigsign.headlines

**source:** `config/config.presentation_test.example.toml` lines 371–387

**use when:** bigsign + RSS headlines with per-character rainbow color. The `max_stories = 1` cap keeps the section short in a demo; raise it for real use.

**must customize:** `feed_url`, `max_stories` (omit to show all), `font_color` (remove or change if rainbow is too busy), title `text` + `color`.

**copy verbatim:**

```toml
[[playlist.section]]
mode = "ticker"
loop_count = 1

[playlist.section.title]
type = "message"
text = "Nintendo Life"
font_color = "random"

[[playlist.section.widget]]
type = "rss.feed"
feed_url = "https://www.nintendolife.com/feeds/news"
max_stories = 1
font_color = "rainbow"
update_interval = 3000
```

---

### snippet: weather.personal_feed.smallsign.simple

**source:** `config/config.small_sign.toml` lines 45–86

**use when:** small sign (160×16) + weather for one or more cities. Uses default BDF font. Requires `WEATHERAPI_KEY` in `.env`.

**must customize:** `text` (city label), `location` (city/zip), `units` (`"imperial"` or `"metric"`). Add/remove widget blocks for additional cities.

**copy verbatim:**

```toml
[[playlist.section]]
mode = "slideshow"
transition = "push_alternating"
hold_time = 6
loop_count = 2

[playlist.section.title]
type = "message"
text = "Weather"
font_color = "random"

[[playlist.section.widget]]
type = "weather.current"
text = "New York"
location = "New York"
units = "imperial"
show_icon = true
```

---

### snippet: weather.personal_feed.bigsign.simple

**source:** `config/config.bigsign.example.toml` lines 45–62 (adapted — the bigsign baseline uses `type = "message"` widgets; the weather widget is sourced from `config.small_sign.toml` and adapted for bigsign scale)

**use when:** bigsign + weather widget in default BDF at `default_scale = 4`. The widget draws at logical scale; no `font` override required for basic use.

**must customize:** `text`, `location`, `units`, `hold_time`.

**copy verbatim:**

```toml
[[playlist.section]]
mode = "slideshow"
hold_time = 6
loop_count = 1

[playlist.section.title]
type = "message"
text = "Weather"
font_color = "random"

[[playlist.section.widget]]
type = "weather.current"
text = "New York"
location = "New York"
units = "imperial"
show_icon = true
```

---

### snippet: countdown.event.smallsign

**source:** `config/config.example.toml` lines 62–81

**use when:** small sign (160×16) + one or more countdown widgets to upcoming dates. Default BDF font; no API key required.

**must customize:** `text` (event name), `countdown_date` (YYYY-MM-DD). Add/remove widget blocks for additional events.

**copy verbatim:**

```toml
[[playlist.section]]
mode = "ticker"
loop_count = 2

[playlist.section.title]
type = "message"
text = "Count Downs"
font_color = "random"

[[playlist.section.widget]]
type = "countdown"
text = "Days Until Spring"
countdown_date = 2026-03-20

[[playlist.section.widget]]
type = "countdown"
text = "Days Until Summer"
countdown_date = 2026-06-20
```

---

### snippet: countdown.event.bigsign

**source:** `config/config.bigsign.example.toml` lines 65–84

**use when:** bigsign + countdown at `scale = 2` (letterboxed — 32px content centered in the 64px panel). Good visual variety against full-height content. No API key required.

**must customize:** `text`, `countdown_date`. Adjust `scale` to `4` to fill the full panel height.

**copy verbatim:**

```toml
[[playlist.section]]
mode = "ticker"
loop_count = 2
scale = 2

[playlist.section.title]
type = "message"
text = "Count Downs"
font_color = "random"

[[playlist.section.widget]]
type = "countdown"
text = "Days Until Summer"
countdown_date = 2026-06-20

[[playlist.section.widget]]
type = "countdown"
text = "Days Until Fall"
countdown_date = 2026-09-22
```

---

### snippet: mlb.sports.smallsign

**source:** `config/config.mlb.toml` lines 26–46

**requires plugin:** `led-ticker-baseball` — the `baseball.scores` widget, `baseball.roll*` transition, and `:baseball.ball:` emoji ship as that plugin, not as core. Add `led-ticker-baseball` to `config/requirements-plugins.txt` and rebuild before using this snippet.

**use when:** small sign (160×16) + live MLB scores for one or more teams. No API key required. `loop_count = 0` means loop until new data arrives.

**must customize:** `team` (3-letter abbreviation, e.g. `"NYM"`, `"LAD"`), `timezone`, `hold_time`, title `text`.

**copy verbatim:**

```toml
[[playlist.section]]
mode = "slideshow"
transition = "baseball.roll_alternating"
transition_duration = 2.0
hold_time = 6
loop_count = 0

[playlist.section.title]
type = "message"
text = ":baseball.ball: MLB Scores"
font_color = "random"

[[playlist.section.widget]]
type = "baseball.scores"
team = "PHI"
timezone = "America/New_York"

[[playlist.section.widget]]
type = "baseball.scores"
team = "NYM"
timezone = "America/New_York"
```

---

### snippet: mlb.sports.bigsign

**source:** `config/config.small_sign.toml` lines 145–166 (adapted for bigsign — same widget, `default_scale = 4` applies globally so no per-section override needed)

**requires plugin:** `led-ticker-baseball` — the `baseball.scores` widget, `baseball.roll*` transition, and `:baseball.ball:` emoji ship as that plugin, not as core. Add `led-ticker-baseball` to `config/requirements-plugins.txt` and rebuild before using this snippet.

**use when:** bigsign + live MLB scores. Same widget and section shape as `mlb.sports.smallsign`; bigsign renders at full 64px panel height automatically.

**must customize:** `team`, `timezone`, `hold_time`, title `text`.

**copy verbatim:**

```toml
[[playlist.section]]
mode = "slideshow"
transition = "baseball.roll_alternating"
transition_duration = 2.0
hold_time = 6
loop_count = 0

[playlist.section.title]
type = "message"
text = ":baseball.ball: MLB Scores"
font_color = "random"

[[playlist.section.widget]]
type = "baseball.scores"
team = "PHI"
timezone = "America/New_York"

[[playlist.section.widget]]
type = "baseball.scores"
team = "NYM"
timezone = "America/New_York"
```

---

### snippet: mlb_standings.sports.bigsign

**source:** `config/config.mlb_standings.toml` lines 26–43

**requires plugin:** `led-ticker-baseball` — the `baseball.standings` widget and `:baseball.ball:` emoji ship as that plugin, not as core. Add `led-ticker-baseball` to `config/requirements-plugins.txt` and rebuild before using this snippet.

**use when:** bigsign (or small sign) + MLB standings showing top-N teams plus your tracked teams. During offseason shows "Opens [date]". No API key required.

**must customize:** `teams` (list of tracked 3-letter abbreviations), `top_n` (how many top teams to show), `timezone`, `title` (standings header label), `hold_time`.

**copy verbatim:**

```toml
[[playlist.section]]
mode = "slideshow"
transition = "push_left"
transition_duration = 0.5
hold_time = 6
loop_count = 1

[playlist.section.title]
type = "message"
text = ":baseball.ball: MLB Standings"
font_color = "random"

[[playlist.section.widget]]
type = "baseball.standings"
teams = ["NYM", "PHI"]
title = "MLB Standings"
top_n = 3
timezone = "America/New_York"
```

---

### snippet: gif.art.bigsign.full_panel

**source:** `config/config.gif_test.example.toml` lines 60–87

**use when:** bigsign + animated GIF filling the full panel as a visual art piece. `mode = "slideshow"` allows an optional section title before the GIF plays.

**must customize:** `path` (GIF asset path), `fit` (`"pillarbox"` for portrait/square, `"stretch"` for wide/abstract, `"crop"` for no black bands), `play_count` (playback repetitions), title `text` + `font_color`.

**copy verbatim:**

```toml
[[playlist.section]]
mode = "slideshow"
loop_count = 1
hold_time = 2.0
transition = "dissolve"
transition_duration = 0.6

[playlist.section.title]
type = "message"
text = "NOW SHOWING"
font_color = [255, 220, 50]

[[playlist.section.widget]]
type = "gif"
path = "assets/example.gif"
fit = "pillarbox"
play_count = 17
```

---

### snippet: image.art.bigsign.full_panel

**source:** `config/config.image_test.example.toml` lines 62–72

**use when:** bigsign + a single still image (PNG/JPG) held on the panel. `mode = "slideshow"` with `hold_time` controls how long the image displays before the next section.

**must customize:** `path` (image asset path), `fit` (`"pillarbox"`, `"letterbox"`, `"stretch"`, `"crop"`), `hold_time`, `loop_count`.

**copy verbatim:**

```toml
[[playlist.section]]
mode = "slideshow"
loop_count = 1
transition = "dissolve"
transition_duration = 0.6

[[playlist.section.widget]]
type = "image"
path = "assets/phoenix.png"
fit = "pillarbox"
hold_time = 5.0
```

---

### snippet: message.art.bigsign.rainbow_border

**source:** `config/config.showroom-bigsign.example.toml` lines 260–275

**use when:** bigsign + maximum-contrast "built-to-be-seen" message with a `bg_color` fill, black knockout text, and an animated rainbow border chasing the panel perimeter.

**must customize:** `text`, `bg_color` (section-level fill color), `font_color` (set to `[0, 0, 0]` for knockout, or a light color for positive text), `font_size`, `border` (tune `speed` / `char_offset` / `thickness`), `hold_time`.

**copy verbatim:**

```toml
[[playlist.section]]
mode = "slideshow"
hold_time = 5.0
loop_count = 1
transition = "dissolve"
transition_duration = 1.5
bg_color = [255, 230, 80]

[[playlist.section.widget]]
type = "message"
text = "BUILT TO BE SEEN"
font = "Inter-Bold"
font_size = 24
font_color = [0, 0, 0]
border = {style = "rainbow", speed = 8, char_offset = 12, thickness = 2}
```

---

### snippet: message.mixed.smallsign

**source:** `config/config.example.toml` lines 44–60

**use when:** small sign (160×16) + simple messages in `ticker` mode. The foundational pattern: section title, one or more text widgets, default BDF font and colors.

**must customize:** `text` (all widget texts), `color` (title color), `font_color` per widget, `loop_count`.

**copy verbatim:**

```toml
[[playlist.section]]
mode = "ticker"
loop_count = 1

[playlist.section.title]
type = "message"
text = "#DevOps News"
font_color = "random"

[[playlist.section.widget]]
type = "message"
text = "May the uptime be with you!"

[[playlist.section.widget]]
type = "message"
text = "Always be shipping!"
```

---

### snippet: message.mixed.bigsign

**source:** `config/config.showroom-bigsign.example.toml` lines 64–77

**use when:** bigsign + a single bold message in `slideshow` mode with hi-res Inter-Bold font and a per-character rainbow sweep. Good for hero openers or announcement banners.

**must customize:** `text`, `font_size` (max ~32 for bigsign panel height), `font_color` (replace `"rainbow"` with `[r,g,b]` for static brand color), `hold_time`, `transition`.

**copy verbatim:**

```toml
[[playlist.section]]
mode = "slideshow"
hold_time = 6.0
loop_count = 1
transition = "sailor_moon.forward"
transition_duration = 1.2

[[playlist.section.widget]]
type = "message"
text = "WELCOME"
font = "Inter-Bold"
font_size = 32
font_color = "rainbow"
```

---

### snippet: two_row.mixed.bigsign.dual_message

**source:** `config/config.showroom-bigsign.example.toml` lines 188–222

**use when:** bigsign + two-row layout with different messages in top and bottom rows at `scale = 2`. `content_height = 32` fills the full 64px panel. Both rows use hi-res Inter fonts with per-row color + font overrides.

**must customize:** `top_text`, `top_color`, `bottom_text`, `bottom_color`, `top_font_size` / `bottom_font_size`, `hold_time`. Adjust `top_font` / `bottom_font` to swap Inter weights or use a custom font.

**copy verbatim:**

```toml
[[playlist.section]]
mode = "slideshow"
scale = 2
content_height = 32
loop_count = 1
hold_time = 3.0
transition = "dissolve"
transition_duration = 0.8

[[playlist.section.widget]]
type = "two_row"
top_text = ":email: hello@example.com"
top_color = [255, 240, 200]
top_align = "center"
top_font = "Inter-Bold"
top_font_size = 14
bottom_text = "Custom playlists, live data feeds, and brand-matched motion graphics"
bottom_color = [180, 140, 230]
bottom_align = "center"
bottom_font = "Inter-Regular"
bottom_font_size = 14
```
