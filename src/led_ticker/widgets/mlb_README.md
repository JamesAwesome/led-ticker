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
```

Returns the full real-time game state. Used only for live games to hydrate ABS
challenge counts. One call per live game per update cycle.

**Do NOT add `?fields=gameData,absChallenges`** — that filter causes the
endpoint to return `{}` for `absChallenges` even when ABS is active. Confirmed
2026-05-27 against PHI@SD (gamePk=823295) at Petco Park.

**`gameData.absChallenges` when ABS is active and a challenge has been made:**
```json
{
  "hasChallenges": true,
  "home": { "remaining": 1, "usedSuccessful": 0, "usedFailed": 1 },
  "away": { "remaining": 2, "usedSuccessful": 0, "usedFailed": 0 }
}
```

**`gameData.absChallenges` when ABS is active but no challenge made yet:**
```json
{
  "hasChallenges": false,
  "home": { "remaining": 2, "usedSuccessful": 0, "usedFailed": 0 },
  "away": { "remaining": 2, "usedSuccessful": 0, "usedFailed": 0 }
}
```

**`gameData.absChallenges` when ABS is not active at this park:**
```json
{}
```

The relevant field is `remaining` (integer). **Gate on the dict being non-empty
(`"home" in abs_ch`), NOT on `hasChallenges`.** `hasChallenges` is `false` for
the entire game until the first challenge is thrown — it would suppress the pip
display for all games that haven't yet challenged. The empty dict is the
reliable "ABS not active" signal.

Confirmed 2026-05-27:
- Petco Park (SD): `hasChallenges: true` mid-game (PHI@SD, gamePk=823295)
- Citi Field (NYM): `hasChallenges: false`, `remaining: 2` both teams (CIN@NYM, gamePk=823626) — ABS active, no challenge made yet
- Other venues checked returned `{}` — ABS not deployed

### Team Lookup
```
GET https://statsapi.mlb.com/api/v1/teams?sportId=1
```

Called once at startup (inside `_resolve_team_id`) to resolve the `team`
abbreviation → numeric `teamId` used in the schedule URL.

## Notes

- ABS (Automated Ball-Strike) is not universally deployed. Empty
  `absChallenges` dict (`{}`) means not active for this game — treat as `None`.
  `hasChallenges: false` does NOT mean inactive — it means no challenge has been
  thrown yet (initial state for every ABS-equipped game).
- The schedule endpoint hydrate list (`team`, `linescore`) is stable.
  Do not add unverified hydrate names — they fail silently (key absent, no
  error, no warning from the API).
- `_INTERVAL_LIVE = 45` and `_INTERVAL_IDLE = 300` are defined in `mlb.py`
  but not yet wired into `run_monitor_loop`. They document intent.
- `gamePk` is the unique integer game identifier used in the live feed URL.
  It is present on every game object in the schedule response.
