# basketball.scores Widget Options

`teams` is required (non-empty) in the default `teams` mode. No API key — the ESPN feed is public. `small_font` is not accepted (`led-ticker validate` rejects it): the smallsign board is one 16-row band drawn in `font`.

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `mode` | `"teams"` \| `"league"` \| `"live"` | `"teams"` | Which games to show. See [Three ways to pick games](#three-ways-to-pick-games). |
| `teams` | list of strings | `[]` | ESPN team codes, case-insensitive (`["PHI", "NY"]`; note the Knicks are `NY`, not `NYK`, and `GS`, `SA`, `NO`, `UTAH`, `WSH`, `BKN`, `PHX`). An unknown code fails `led-ticker validate` with a close-match hint (`NYK` suggests `NY`). In `league` / `live` modes it sets priority and which teams celebrate a win. |
| `max_games` | int | `8` | Cap on games per rotation in `league` / `live` modes. A positive int. |
| `final_hold_hours` | int | `6` | How long a final stays in the rotation, counted from tip-off + 2 h 30 min (the feed carries no end time). Teams play most nights, so the default clears a result soon enough for the next game to show; raise it to keep last night's result up through the morning. An int >= 0. |
| `timezone` | IANA name | `"America/New_York"` | Timezone for tip-off times (`TODAY`, `TONIGHT`, dates) and the day boundary. Rejected at config-load if it isn't a real IANA name. |
| `layout` | `"auto"` \| `"scoreboard"` \| `"ticker"` | `"auto"` | Render shape. `auto` picks the held scoreboard on every sign. See [Layouts](#layouts-one-held-board-per-sign-shape). |
| `logos` | bool | `true` | Paint the bundled team logos on the bigsign and longboi. `false` paints two-tone team-colour chips with the abbreviation instead. Ignored on the smallsign, which never shows logos. |
| `update_interval` | int seconds | `15` | How often this widget refreshes its cards and asks the shared source to poll. Lower than 15 speeds live polling up (**floored at 10** — ESPN caches for 10 s); a higher value makes that widget refresh less often. See [How often it polls](#how-often-does-it-poll-espn). |
| `hold_time` | float seconds | `0.0` | Minimum per-card hold. The engine uses the larger of this and the section's `hold_time`. A pending win celebration extends it automatically. |
| `demo` | bool | `false` | Render four fixture games — a live clutch-time 4th quarter whose win celebrates, halftime, an OT final and the next game — with `PHI` and `NY`, no network. Every GIF on this page was rendered this way. |
| `padding` | int | `6` | Horizontal padding (logical pixels) after the line on the scale > 1 ticker crawl only (`layout = "ticker"`); it also counts toward whether the line fits and holds instead of scrolling. A number >= 0. |
| `bg_color` | RGB list | none | Background fill behind every board, the ticker line and the win celebration, at any scale. |
| `font_color` | RGB list / string / table | unset | Override all text color on the scale-1 `layout = "ticker"` line only. The boards, the celebration and the scale > 1 renderers keep their fixed palette. |
| `font` | string | core default | BDF font for the smallsign board and the scale-1 ticker line (6x12 by default). |
