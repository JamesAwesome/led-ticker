# MLB Widget Options

`MLBScoreMonitor` fetches live game state from MLB's free StatsAPI (no API key required) and renders the tracked team's current series with different display modes depending on game state:

- **Pre-game** — `NYY @ BOS  Today 7:05 PM` (upcoming game with time)
- **Live** — `NYY 3 BOS 5 ▲6 ◇◆◇ 1·2·1` (score + inning + bases + BSO in color)
- **Final** — `NYY 4 BOS 5 (Final)` (win in green, loss in red)
- **Postponed** — `NYY @ BOS (PPD: Rain)` (amber tag with short reason)

A series title is shown before the per-game messages, e.g. `NYY @ BOS 1-0` (including the running series record once any game is decided). Spring Training and All-Star games append `(ST)` or `(ASG)` with a pixel-art icon.

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `team` | string | required | Three-letter MLB team abbreviation (e.g. `"NYY"`, `"LAD"`, `"BOS"`). Case-insensitive. See the full list of codes below. |
| `timezone` | string | `"America/New_York"` | IANA timezone for game-time formatting (e.g. `"America/Los_Angeles"`, `"America/Chicago"`). Affects how "Today 7:05 PM" vs "Tmrw" vs day-of-week labels are computed. |
| `padding` | int | `6` | Horizontal padding (logical pixels) added after each message when scrolling. |
| `final_hold_hours` | int | `6` | How many hours after a game ends to keep showing its final score before moving on to the next series. Default is 6 hours (covers west-coast game end times for east-coast displays). |
| `bg_color` | RGB list | none | Background fill color painted behind all game messages. |
| `font` | string / Font | `"6x12"` (FONT_DEFAULT) | BDF font name or hires font for all game message text. |
| `update_interval` | int | `300` | Seconds between StatsAPI fetches (passed to `start()`). Default is 5 minutes. The widget automatically shortens its internal poll to ~45 s during a live game and extends to 5 minutes during idle / offseason. |

## Team codes

All 30 MLB teams:

`ARI` D-backs · `ATL` Braves · `BAL` Orioles · `BOS` Red Sox · `CHC` Cubs · `CIN` Reds · `CLE` Guardians · `COL` Rockies · `CWS` White Sox · `DET` Tigers · `HOU` Astros · `KC` Royals · `LAA` Angels · `LAD` Dodgers · `MIA` Marlins · `MIL` Brewers · `MIN` Twins · `NYM` Mets · `NYY` Yankees · `OAK` Athletics · `PHI` Phillies · `PIT` Pirates · `SD` Padres · `SEA` Mariners · `SF` Giants · `STL` Cardinals · `TB` Rays · `TEX` Rangers · `TOR` Blue Jays · `WSH` Nationals
