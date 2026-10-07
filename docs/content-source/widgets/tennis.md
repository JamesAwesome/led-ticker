# tennis.scores Widget Options

No option is required — the API key comes from the `LIVETENNIS_API_KEY` environment variable.

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `tours` | list of strings | `[]` (all) | Any of `"atp"`, `"wta"`, `"challenger"`, `"itf"`, `"juniors"`. Filtered on the sign after the fetch, so narrowing it never costs extra API requests. |
| `draw` | `"all"` \| `"singles"` \| `"doubles"` | `"all"` | Which draw to show. Doubles teams render as the pairing, e.g. `CASH/GLASSPOOL`. |
| `max_matches` | int | `8` | Cap on matches per rotation. Ordering is main tours first (ATP, WTA, then Challenger, ITF, juniors), then earliest scheduled. |
| `layout` | `"auto"` \| `"ticker"` \| `"scoreboard"` | `"auto"` | Render shape. `auto` picks the scrolling ticker at scale 1 and the held scoreboard at scale > 1. See [Layouts](#layouts-one-per-sign-shape). |
| `show_ranking` | bool | `false` | Append each player's official singles ranking on the ticker layouts, e.g. `LEHECKA (21)`. Not shown on the held scoreboard, where the numeric columns own that space. |
| `timezone` | IANA name | `"America/New_York"` | Timezone for fixture start times (`Today 3:00 PM`). Rejected at config-load if it isn't a real IANA name. |
| `update_interval` | int seconds | `900` | Seconds between API polls. **Floored at 900** whatever you set — see [Staying inside the free tier](#staying-inside-the-free-tier). |
| `demo` | bool | `false` | Render four fixture matches — a break point, a tiebreak, a retirement and an upcoming fixture — with no API key and no network. Every GIF on this page was rendered this way. |
| `api_key` | string | `""` | Live Tennis API key. `LIVETENNIS_API_KEY` in the environment takes precedence; prefer that and keep credentials out of `config.toml`. |
| `padding` | int | `6` | Horizontal padding (logical pixels) after each story when the layout scrolls. |
| `bg_color` | RGB list | none | Background fill. Scale 1 only — the scale > 1 renderers paint their own palette. |
| `font_color` | RGB list / string / table | unset | Override all text color. Scale 1 only, for the same reason. |
| `font` | string | `"6x12"` | BDF font for the scale-1 ticker line. |
| `small_font` | string | `"5x8"` | BDF font for the scale-1 two-band scoreboard. |
