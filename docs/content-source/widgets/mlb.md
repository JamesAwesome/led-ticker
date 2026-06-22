# MLB Widget Options

> **Plugin widget.** MLB scores ship as the **[baseball](https://github.com/JamesAwesome/led-ticker-plugins/tree/main/plugins/baseball)** package in the external led-ticker-plugins monorepo. Use `type = "baseball.scores"` and install the plugin (add `led-ticker-baseball` to `config/requirements-plugins.txt`, then rebuild).

`MLBScoreMonitor` fetches live game state from MLB's free StatsAPI (no API key required) and renders the tracked team's current series. Two layouts are available:

**`layout = "ticker"` (default)** — scrolling ticker line:

- **Pre-game** — `NYY @ BOS  Today 7:05 PM`
- **Live** — `NYY 3 BOS 5 ▲6 ◇◆◇ 1·2·1` (score + inning + bases + BSO in color)
- **Final** — `NYY 4 BOS 5 (Final)` (win in green, loss in red)
- **Postponed** — `NYY @ BOS (PPD: Rain)` (amber tag with short reason)

A series title is shown before the per-game messages, e.g. `NYY @ BOS 1-0`.

**`layout = "scoreboard"`** — two-column display for big-sign / longboi panels:

```
NYY  3  |  ▲6  ◇◆◇  |  5  BOS
         |  1·2·1    |
```

Away team name and score fill the left column; home team name and score fill the right column; the centre zone shows inning + outs (top) and ball/strike count + base diamonds (bottom). Team names are shown in their brand colour; scores are coloured by win/loss state (green/red) during final games. Geometric base diamonds are drawn in yellow (occupied) or dim grey (empty).

If ABS (Automated Ball-Strike) challenges are active at the park, two stacked dashes appear in the bottom-row outer corners — orange for remaining challenges, grey for used. The row is hidden entirely when ABS is not in effect.

Spring Training and All-Star games append `(ST)` or `(ASG)` in ticker mode.

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `team` | string | required | Three-letter MLB team abbreviation (e.g. `"NYY"`, `"LAD"`, `"BOS"`). Case-insensitive. See the full list of codes below. |
| `layout` | string | `"ticker"` | Display style: `"ticker"` (scrolling line) or `"scoreboard"` (two-column). |
| `timezone` | string | `"America/New_York"` | IANA timezone for game-time formatting (e.g. `"America/Los_Angeles"`, `"America/Chicago"`). |
| `padding` | int | `6` | Horizontal padding (logical pixels) after each message when scrolling. Ticker layout only. |
| `final_hold_hours` | int | `6` | Hours after a game ends to keep showing its final score. Default covers west-coast games for east-coast displays. |
| `bg_color` | RGB list | none | Background fill colour behind all game messages. |
| `font_color` | RGB list / string / table | unset | Override colour for all text. Default leaves per-segment colours intact (team brand colours, win/loss state on scores, etc.). |
| `font` | string | `"6x12"` | Font name for team names and scores. Use a hires font name (e.g. `"Inter-Regular"`) with `font_size` and `font_threshold` for big-sign panels. |
| `font_size` | int | none | Point size for hires fonts. Required when `font` is a TTF/OTF name. |
| `font_threshold` | int | `128` | Anti-alias threshold (0–255) for hires fonts. Lower values preserve thin strokes; `80` works well for Inter Regular. |
| `small_font` | string | same as `font` | Font for the centre zone (inning, B/S count, base diamonds). Scoreboard layout only. Defaults to the same font as `font`. |
| `small_font_size` | int | none | Point size for `small_font`. |
| `small_font_threshold` | int | same as `font_threshold` | Anti-alias threshold for `small_font`. |
| `update_interval` | int | `300` | Seconds between StatsAPI fetches. |

## Team codes

All 30 MLB teams:

`ARI` D-backs · `ATL` Braves · `BAL` Orioles · `BOS` Red Sox · `CHC` Cubs · `CIN` Reds · `CLE` Guardians · `COL` Rockies · `CWS` White Sox · `DET` Tigers · `HOU` Astros · `KC` Royals · `LAA` Angels · `LAD` Dodgers · `MIA` Marlins · `MIL` Brewers · `MIN` Twins · `NYM` Mets · `NYY` Yankees · `OAK` Athletics · `PHI` Phillies · `PIT` Pirates · `SD` Padres · `SEA` Mariners · `SF` Giants · `STL` Cardinals · `TB` Rays · `TEX` Rangers · `TOR` Blue Jays · `WSH` Nationals
