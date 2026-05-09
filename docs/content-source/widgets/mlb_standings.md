# MLB Standings Widget Options

`MLBStandingsMonitor` fetches overall MLB league standings from the free MLB StatsAPI (no API key required) and renders them as a scrolling list. It shows the top-N teams by overall rank and then appends any `teams` entries that didn't already appear in that list — so your tracked teams are always visible regardless of where they sit in the standings.

Each entry scrolls as: `rank. TeamName W-L GB` with the team name rendered in the team's brand color.

When the season hasn't started yet (all wins and losses are 0), the widget switches to a pre-season message — `Opens Mar 27` (or `Opens soon` if schedule data is unavailable) — and stays there until games are played. After the World Series and before Spring Training opens, the API still returns the previous season's final standings, so the widget keeps displaying those rather than going blank.

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `teams` | list of strings | required | Three-letter MLB abbreviations for your tracked teams (e.g. `["NYY", "BOS"]`). Case-insensitive. These teams are always shown even if they fall outside the top-N. |
| `top_n` | int | `3` | How many overall top teams to show before tracked teams. Set to `0` to show only your tracked teams. |
| `title` | string | `"MLB Standings"` | Section header shown before the standings list. |
| `timezone` | string | `"America/New_York"` | IANA timezone used for offseason detection and opening-day date formatting. |
| `padding` | int | `6` | Horizontal padding (logical pixels) added after each message when scrolling. |
| `bg_color` | RGB list | none | Background fill color painted behind all standings messages. |
| `font` | string / Font | `"6x12"` (FONT_DEFAULT) | BDF font name or hires font for standings text. |
| `update_interval` | int | `86400` | Seconds between StatsAPI fetches. Default is 24 hours — standings don't change minute-to-minute. Lower to `3600` during a tight pennant race if you want hourly refreshes. |

## Team codes

Same abbreviations as the `mlb` widget:

`ARI` D-backs · `ATL` Braves · `BAL` Orioles · `BOS` Red Sox · `CHC` Cubs · `CIN` Reds · `CLE` Guardians · `COL` Rockies · `CWS` White Sox · `DET` Tigers · `HOU` Astros · `KC` Royals · `LAA` Angels · `LAD` Dodgers · `MIA` Marlins · `MIL` Brewers · `MIN` Twins · `NYM` Mets · `NYY` Yankees · `OAK` Athletics · `PHI` Phillies · `PIT` Pirates · `SD` Padres · `SEA` Mariners · `SF` Giants · `STL` Cardinals · `TB` Rays · `TEX` Rangers · `TOR` Blue Jays · `WSH` Nationals
