# RSS Feed Widget Options

`RSSFeedMonitor` fetches a remote RSS feed and expands each story into its own `TickerMessage` that scrolls within the section. The feed title and each headline become separate messages, cycling colors from the legacy three-color rotation unless `font_color` is explicitly set. Updates run in the background via async polling with exponential backoff so the display keeps running even if the feed is temporarily unreachable.

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `feed_url` | string | required | Full URL of the RSS feed to fetch (e.g. `"https://www.nintendolife.com/feeds/news"`). |
| `max_stories` | int | `5` | Maximum number of headlines to pull from the feed per fetch. The feed title is always shown first; stories are capped at this number. |
| `font_color` | RGB list / string / table | none | Color for all story TickerMessages. Constant `[r,g,b]`, `"rainbow"`, `"color_cycle"`, `"random"`, or `{style="gradient", from=[...], to=[...]}`. When unset, the widget cycles through three colors (yellow → red → green) per story. |
| `bg_color` | RGB list | none | Background fill color applied to every story TickerMessage. |
| `padding` | int | `6` | Horizontal padding (logical pixels) added to each story when scrolling. |
| `update_interval` | int | `1800` | Seconds between feed fetches. Default is 30 minutes. |
