# football.scores Widget Options

`teams` is required (non-empty) in the default `teams` mode. No API key — the ESPN feed is public.

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `mode` | `"teams"` \| `"league"` \| `"live"` | `"teams"` | Which games to show. See [Three ways to pick games](#three-ways-to-pick-games). |
| `teams` | list of strings | `[]` | ESPN team codes, case-insensitive (`["PHI", "NYG"]`; note `WSH`, `LAR`, `JAX`, `LV`, `LAC`). An unknown code fails `led-ticker validate` with a close-match hint. In `league` / `live` modes it sets priority and which teams celebrate a score. |
| `max_games` | int | `8` | Cap on games per rotation in `league` / `live` modes. A positive int. |
| `final_hold_hours` | int | `24` | How long a final stays in the rotation, counted from kickoff + 3 h 30 min (the feed carries no end time). A team plays once a week, so Sunday's result stays up through Monday by default; lower it to see the next game sooner. An int >= 0. |
| `timezone` | IANA name | `"America/New_York"` | Timezone for kickoff times (`TODAY`, `TONIGHT`, dates) and the day boundary. Rejected at config-load if it isn't a real IANA name. |
| `layout` | `"auto"` \| `"scoreboard"` \| `"ticker"` | `"auto"` | Render shape. `auto` picks the held scoreboard on every sign. See [Layouts](#layouts-one-held-board-per-sign-shape). |
| `update_interval` | int seconds | `15` | How often this widget refreshes its cards and asks the shared source to poll. Lower than 15 speeds live polling up (**floored at 10** — ESPN caches for 10 s); a higher value makes that widget refresh less often. See [How often it polls](#how-often-does-it-poll-espn). |
| `hold_time` | float seconds | `0.0` | Minimum per-card hold. The engine uses the larger of this and the section's `hold_time`. A pending scoring celebration extends it automatically. |
| `demo` | bool | `false` | Render five fixture games — a live 4th quarter with a touchdown, halftime, an OT final, the next game and a bye week — with no network. Every GIF on this page was rendered this way. |
| `padding` | int | `6` | Horizontal padding (logical pixels) after the line on the scale > 1 ticker crawl only (`layout = "ticker"`); it also counts toward whether the line fits and holds instead of scrolling. A number >= 0. |
| `bg_color` | RGB list | none | Background fill behind every board, the ticker line and the scoring celebration, at any scale. |
| `font_color` | RGB list / string / table | unset | Override all text color on the scale-1 `layout = "ticker"` line only. The smallsign band board, the celebration and the scale > 1 boards and crawl keep their fixed palette. |
| `font` | string | core default | BDF font for the scale-1 ticker line. |
| `small_font` | string | `"5x8"` | BDF font for the scale-1 two-band scoreboard. |
