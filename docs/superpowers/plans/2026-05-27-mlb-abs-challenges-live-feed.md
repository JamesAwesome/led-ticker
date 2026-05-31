# MLB ABS Challenges — Live Feed Hydration Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix ABS challenge pip display by reading from the live game feed instead of the schedule endpoint, and document the MLB Stats API surface for future reference.

**Architecture:** The schedule API's `challenges` hydrate is a no-op — confirmed against live games. Challenge counts live in `/api/v1.1/game/{pk}/feed/live` under `gameData.absChallenges`. For each live game in the current series, one additional async fetch is made concurrently alongside the main schedule call.

**Tech Stack:** Python asyncio, aiohttp, MLB Stats API (free, no auth)

---

### Task 1: Write `src/led_ticker/widgets/mlb_README.md`

**Files:**
- Create: `src/led_ticker/widgets/mlb_README.md`

Document exactly what we know about the MLB Stats API endpoints used by this widget. This file is the reference to consult when API shape questions come up, so future engineers don't have to re-discover the same things.

- [ ] **Step 1: Create the README**

```markdown
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
update cycle.

**`hydrate=challenges` does NOT work.** Confirmed 2026-05-27 against 4 live
games — the `challenges` key is always absent from game objects in the schedule
response, for Final, Preview, and Live states alike.

### Live Game Feed
```
GET https://statsapi.mlb.com/api/v1.1/game/{gamePk}/feed/live
  ?fields=gameData,absChallenges
```

Returns the full real-time game state. Used only for live games to hydrate ABS
challenge counts. One call per live game per update cycle.

**`gameData.absChallenges` structure:**

When ABS is active:
```json
{
  "hasChallenges": true,
  "home": { "remaining": 2, "usedSuccessful": 0, "usedFailed": 0 },
  "away": { "remaining": 0, "usedSuccessful": 2, "usedFailed": 2 }
}
```

When ABS is not active (game or park doesn't use it):
```json
{}
```

The relevant field is `remaining` (integer). `hasChallenges: true` is the
reliable gate — an empty dict means ABS is not in effect for this game.

### Team Lookup
```
GET https://statsapi.mlb.com/api/v1/teams?sportId=1
```

Called once at startup to resolve `team` abbreviation → `teamId`.

## Notes

- ABS (Automated Ball-Strike) is not universally deployed. Petco Park (SD)
  confirmed active as of 2026-05-26. Empty `absChallenges` dict = not active.
- The schedule endpoint hydrate list (`team`, `linescore`) is stable and fast.
  Do not add unverified hydrate names — they fail silently (absent key, no error).
- `_INTERVAL_LIVE = 45` and `_INTERVAL_IDLE = 300` are defined in `mlb.py` but
  not yet wired into `run_monitor_loop`. They document intent, not current
  behaviour.
```

- [ ] **Step 2: Commit**

```bash
git add src/led_ticker/widgets/mlb_README.md
git commit -m "docs: add MLB Stats API reference for widget engineers"
```

---

### Task 2: Clean up URL and parsing

**Files:**
- Modify: `src/led_ticker/widgets/mlb.py` (lines ~847–850, ~1020–1040)

- [ ] **Step 1: Drop `challenges` from the hydrate URL**

In `update()`, change:
```python
f"&hydrate=team,linescore,challenges"
```
to:
```python
f"&hydrate=team,linescore"
```

- [ ] **Step 2: Simplify challenges parsing to `remaining` only**

The `_parse_games` challenges block currently tries both `remaining` and
`remainingChallenges`. Now that we know `remaining` is the confirmed field name
(from the live feed which is the only source that works), simplify to just read
`remaining`:

```python
# ABS challenges — hydrated separately via live feed for live games.
# _parse_games always leaves these None; update() fills them in.
home_challenges: int | None = None
away_challenges: int | None = None
```

Remove the entire challenges parsing block from `_parse_games` — it never
receives challenge data (schedule endpoint doesn't return it). The fields stay
on `GameInfo`; they'll be populated by the new `_fetch_abs_challenges` call.

- [ ] **Step 3: Run tests to confirm nothing broke**

```bash
make test
```

Expected: same pass count as before (challenges block was dead code anyway).

- [ ] **Step 4: Commit**

```bash
git add src/led_ticker/widgets/mlb.py
git commit -m "fix: remove dead challenges hydrate from schedule URL and parsing"
```

---

### Task 3: Add `_fetch_abs_challenges` helper

**Files:**
- Modify: `src/led_ticker/widgets/mlb.py`

- [ ] **Step 1: Write the failing test first**

In `tests/test_mlb_scoreboard.py`:

```python
@pytest.mark.asyncio
async def test_fetch_abs_challenges_active_game():
    """Returns (home, away) remaining counts when ABS is active."""
    import unittest.mock as mock

    session = mock.MagicMock()
    monitor = MLBScoreMonitor(session=session, team="PHI")

    resp = mock.AsyncMock()
    resp.json = mock.AsyncMock(return_value={
        "gameData": {
            "absChallenges": {
                "hasChallenges": True,
                "home": {"remaining": 2, "usedSuccessful": 0, "usedFailed": 0},
                "away": {"remaining": 0, "usedSuccessful": 2, "usedFailed": 2},
            }
        }
    })
    session.get.return_value.__aenter__ = mock.AsyncMock(return_value=resp)
    session.get.return_value.__aexit__ = mock.AsyncMock(return_value=False)

    home, away = await monitor._fetch_abs_challenges(823294)
    assert home == 2
    assert away == 0


@pytest.mark.asyncio
async def test_fetch_abs_challenges_inactive_returns_none():
    """Returns (None, None) when absChallenges is empty (ABS not active)."""
    import unittest.mock as mock

    session = mock.MagicMock()
    monitor = MLBScoreMonitor(session=session, team="PHI")

    resp = mock.AsyncMock()
    resp.json = mock.AsyncMock(return_value={"gameData": {"absChallenges": {}}})
    session.get.return_value.__aenter__ = mock.AsyncMock(return_value=resp)
    session.get.return_value.__aexit__ = mock.AsyncMock(return_value=False)

    home, away = await monitor._fetch_abs_challenges(823294)
    assert home is None
    assert away is None


@pytest.mark.asyncio
async def test_fetch_abs_challenges_error_returns_none():
    """Network errors return (None, None) without raising."""
    import unittest.mock as mock

    session = mock.MagicMock()
    monitor = MLBScoreMonitor(session=session, team="PHI")
    session.get.side_effect = Exception("network error")

    home, away = await monitor._fetch_abs_challenges(823294)
    assert home is None
    assert away is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
make test 2>&1 | grep "test_fetch_abs"
```

Expected: 3 failures (method doesn't exist yet).

- [ ] **Step 3: Implement the method**

Add to `MLBScoreMonitor` after `_find_next_game`:

```python
async def _fetch_abs_challenges(
    self, game_pk: int
) -> tuple[int | None, int | None]:
    """Fetch ABS challenge remaining counts from the live game feed.

    Returns (home_remaining, away_remaining), or (None, None) if ABS is
    not active for this game or the request fails.
    """
    url = f"{MLB_API[:-3]}.1/game/{game_pk}/feed/live?fields=gameData,absChallenges"
    try:
        async with self.session.get(url) as resp:
            data = await resp.json()
    except Exception:
        logger.exception("ABS challenge fetch failed for gamePk=%s", game_pk)
        return None, None

    abs_ch = data.get("gameData", {}).get("absChallenges", {})
    if not abs_ch or not abs_ch.get("hasChallenges"):
        return None, None

    home = abs_ch.get("home", {})
    away = abs_ch.get("away", {})
    with contextlib.suppress(TypeError, ValueError):
        return int(home.get("remaining", 0)), int(away.get("remaining", 0))
    return None, None
```

Note: `MLB_API = "https://statsapi.mlb.com/api/v1"` → strip `v1`, append `v1.1`.
So `MLB_API[:-3]` → `"https://statsapi.mlb.com/api/"`, then `.1/game/...`.
Or just define the base separately:

```python
_MLB_LIVE_API = "https://statsapi.mlb.com/api/v1.1"
```

Add `_MLB_LIVE_API` as a module-level constant near `MLB_API`.

- [ ] **Step 4: Run tests — all 3 should pass**

```bash
make test 2>&1 | grep "test_fetch_abs"
```

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/widgets/mlb.py tests/test_mlb_scoreboard.py
git commit -m "feat: add _fetch_abs_challenges from live game feed"
```

---

### Task 4: Wire `_fetch_abs_challenges` into `update()`

**Files:**
- Modify: `src/led_ticker/widgets/mlb.py`

Fetch challenge counts for all live games concurrently, then patch the `GameInfo`
objects before grouping into series.

- [ ] **Step 1: Write the failing test first**

In `tests/test_mlb_scoreboard.py`:

```python
@pytest.mark.asyncio
async def test_update_hydrates_abs_challenges_for_live_game():
    """Live games in update() get abs challenge counts from the live feed."""
    import unittest.mock as mock
    from zoneinfo import ZoneInfo

    session = mock.MagicMock()
    monitor = MLBScoreMonitor(session=session, team="PHI", layout="scoreboard")
    monitor._team_id = 143
    monitor._tz = ZoneInfo("America/New_York")

    schedule_resp = mock.AsyncMock()
    schedule_resp.json = mock.AsyncMock(return_value=_phi_nym_schedule("live"))

    live_resp = mock.AsyncMock()
    live_resp.json = mock.AsyncMock(return_value={
        "gameData": {
            "absChallenges": {
                "hasChallenges": True,
                "home": {"remaining": 2, "usedSuccessful": 0, "usedFailed": 0},
                "away": {"remaining": 1, "usedSuccessful": 1, "usedFailed": 0},
            }
        }
    })

    # First call → schedule, second call → live feed
    call_count = 0
    async def mock_get(url):
        nonlocal call_count
        call_count += 1
        return live_resp if "v1.1" in url else schedule_resp

    session.get = mock.MagicMock(side_effect=lambda url: mock_get(url))
    # wire up context manager
    for r in (schedule_resp, live_resp):
        r.__aenter__ = mock.AsyncMock(return_value=r)
        r.__aexit__ = mock.AsyncMock(return_value=False)

    await monitor.update()

    scoreboard_msgs = [
        s for s in monitor.feed_stories if isinstance(s, MLBScoreboardMessage)
    ]
    assert len(scoreboard_msgs) >= 1
    assert scoreboard_msgs[0].game.home_challenges == 2
    assert scoreboard_msgs[0].game.away_challenges == 1
```

- [ ] **Step 2: Run to confirm it fails**

```bash
make test 2>&1 | grep "test_update_hydrates"
```

- [ ] **Step 3: Implement the wiring in `update()`**

After `games = self._parse_games(data, tz)` and its try/except, add:

```python
# Concurrently hydrate ABS challenge counts for all live games.
live_games = [g for g in games if g.state == "live" and g.game_pk]
if live_games:
    results = await asyncio.gather(
        *(self._fetch_abs_challenges(g.game_pk) for g in live_games),
        return_exceptions=False,
    )
    for g, (home_ch, away_ch) in zip(live_games, results):
        g.home_challenges = home_ch
        g.away_challenges = away_ch
```

`asyncio.gather` runs the fetches concurrently — a 3-game series with all live
games fires 3 requests in parallel, adds one network round-trip total.

- [ ] **Step 4: Run the new test + full suite**

```bash
make test
```

Expected: all passing including `test_update_hydrates_abs_challenges_for_live_game`.

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/widgets/mlb.py tests/test_mlb_scoreboard.py
git commit -m "feat: hydrate ABS challenge counts concurrently for live games"
```

---

### Task 5: Clean up stale tests

**Files:**
- Modify: `tests/test_mlb_scoreboard.py`

The tests `test_parse_games_extracts_abs_challenges_remaining_field` and
`test_parse_games_extracts_abs_challenges_remaining_challenges_field` tested
parsing logic that's now removed from `_parse_games`. Remove or update them.

- [ ] **Step 1: Delete the two now-dead parse tests**

Remove:
- `test_parse_games_extracts_abs_challenges_remaining_field`
- `test_parse_games_extracts_abs_challenges_remaining_challenges_field`

These tested a code path that no longer exists. The `_fetch_abs_challenges`
tests (Task 3) cover the real path.

- [ ] **Step 2: Run tests to confirm count is clean**

```bash
make test
```

- [ ] **Step 3: Commit**

```bash
git add tests/test_mlb_scoreboard.py
git commit -m "test: remove parse tests for dead challenges block"
```

---

## Files Changed

| File | Change |
|---|---|
| `src/led_ticker/widgets/mlb_README.md` | New — MLB Stats API reference |
| `src/led_ticker/widgets/mlb.py` | Remove `challenges` hydrate, remove dead parsing block, add `_MLB_LIVE_API`, add `_fetch_abs_challenges`, wire into `update()` |
| `tests/test_mlb_scoreboard.py` | Add `_fetch_abs_challenges` tests + `update()` integration test, remove two dead parse tests |
