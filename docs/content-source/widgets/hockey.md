# hockey.scores Widget Options

`teams` is required (non-empty) in the default `teams` mode. No API key — the NHL feed is public.

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `mode` | `"teams"` \| `"league"` \| `"live"` | `"teams"` | Which games to show. See [Three ways to pick games](#three-ways-to-pick-games). |
| `teams` | list of strings | `[]` | NHL three-letter codes, case-insensitive (`["PHI", "NYI"]`). An unknown code fails `led-ticker validate` with a close-match hint. In `league` / `live` modes it sets priority and which teams celebrate a goal. |
| `max_games` | int | `8` | Cap on games per rotation in `league` / `live` modes. A positive int. |
| `final_hold_hours` | int | `6` | How long a final stays in the rotation, counted from the game's start time + 2 h 30 min (the feed carries no end time). An int >= 0. |
| `timezone` | IANA name | `"America/New_York"` | Timezone for start times (`TODAY`, `TONIGHT`, dates) and the day boundary. Rejected at config-load if it isn't a real IANA name. |
| `layout` | `"auto"` \| `"scoreboard"` \| `"ticker"` | `"auto"` | Render shape. `auto` picks the held scoreboard on every sign. See [Layouts](#layouts-one-held-board-per-sign-shape). |
| `update_interval` | int seconds | `15` | Live poll cadence. **Floored at 10.** Lower than 15 speeds live polling up; higher does not slow the shared source below 15 s while a game is live. See [How often it polls](#how-often-does-it-poll-the-nhl). |
| `hold_time` | float seconds | `0.0` | Minimum per-card hold. The engine uses the larger of this and the section's `hold_time`. A pending goal celebration extends it automatically. |
| `demo` | bool | `false` | Render four fixture games — a live power play with a goal, an intermission, an OT final and the next game — with no network. Every GIF on this page was rendered this way. |
| `padding` | int | `6` | Horizontal padding (logical pixels) after each story when the layout scrolls. A number >= 0. |
| `bg_color` | RGB list | none | Background fill. Scale 1 / ticker only — the scale > 1 boards paint their own palette. |
| `font_color` | RGB list / string / table | unset | Override all text color. Scale 1 / ticker only, for the same reason. |
| `font` | string | core default | BDF font for the scale-1 ticker line. |
| `small_font` | string | `"5x8"` | BDF font for the scale-1 two-band scoreboard. |
