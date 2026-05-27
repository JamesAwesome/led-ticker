# MLB Widget — API Reference

## Endpoints

### Schedule
```
GET https://statsapi.mlb.com/api/v1/schedule
  ?teamId={teamId}
  &startDate={YYYY-MM-DD}
  &endDate={YYYY-MM-DD}
  &sportId=1
  &hydrate=team,linescore
```

Returns the full schedule window used by `update()`. One call per widget per
update cycle (±7 days from today).

**`hydrate=challenges` does NOT work.** Confirmed 2026-05-27 against 4 live
games (MIA@TOR, WSH@CLE, STL@MIL, SEA@ATH) — the `challenges` key is always
absent from game objects in the schedule response, for Final, Preview, and Live
states alike. Do not add it to the URL.

Valid hydrates confirmed working: `team`, `linescore`.

### Live Game Feed
```
GET https://statsapi.mlb.com/api/v1.1/game/{gamePk}/feed/live
  ?fields=gameData,absChallenges
```

Returns the full real-time game state. Used only for live games to hydrate ABS
challenge counts. One call per live game per update cycle.

**`gameData.absChallenges` structure when ABS is active:**
```json
{
  "hasChallenges": true,
  "home": { "remaining": 2, "usedSuccessful": 0, "usedFailed": 0 },
  "away": { "remaining": 0, "usedSuccessful": 2, "usedFailed": 2 }
}
```

**`gameData.absChallenges` when ABS is not active:**
```json
{}
```

The relevant field is `remaining` (integer). Use `hasChallenges: true` as the
gate — an empty dict means ABS is not in effect for this game.

Confirmed active at Petco Park (SD) on 2026-05-26. The four live games checked
on 2026-05-27 (MIA@TOR, WSH@CLE, STL@MIL, SEA@ATH) all returned `{}` —
ABS is not universally deployed.

### Team Lookup
```
GET https://statsapi.mlb.com/api/v1/teams?sportId=1
```

Called once at startup (inside `_resolve_team_id`) to resolve the `team`
abbreviation → numeric `teamId` used in the schedule URL.

## Notes

- ABS (Automated Ball-Strike) is not universally deployed. Empty
  `absChallenges` dict means not active for this game — treat as `None`.
- The schedule endpoint hydrate list (`team`, `linescore`) is stable.
  Do not add unverified hydrate names — they fail silently (key absent, no
  error, no warning from the API).
- `_INTERVAL_LIVE = 45` and `_INTERVAL_IDLE = 300` are defined in `mlb.py`
  but not yet wired into `run_monitor_loop`. They document intent.
- `gamePk` is the unique integer game identifier used in the live feed URL.
  It is present on every game object in the schedule response.
