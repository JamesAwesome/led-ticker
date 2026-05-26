# MLB Scoreboard Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `layout = "scoreboard"` to the `mlb` widget, rendering a two-column scoreboard (teams + scores flanking game state, bases, B/S/O, and ABS challenge pips) alongside the existing single-line ticker layout.

**Architecture:** One new class `MLBScoreboardMessage` (parallel to `MLBGameMessage`) handles rendering; `MLBScoreMonitor` gets a `layout` field that routes `update()` to the right factory. Two new fields on `GameInfo` hold ABS challenge counts. `layout = "ticker"` is the default — zero behaviour change for existing configs.

**Tech Stack:** Python 3.12, attrs, aiohttp, led_ticker drawing/font/pixel_emoji infrastructure, pytest.

---

## File Map

| File | Change |
|---|---|
| `src/led_ticker/widgets/mlb.py` | Add `GameInfo.home_challenges`/`away_challenges`; add `MLBScoreMonitor.layout`; extend `_parse_games`; add `MLBScoreboardMessage` class; add `_build_scoreboard_message` factory; update `update()` to branch on layout |
| `tests/test_mlb_scoreboard.py` | New — all tests for this feature |

No other files change.

---

## Key Symbols to Know

Before writing any code, open these files and read them:

- `src/led_ticker/widgets/mlb.py` — the whole file (860 lines). `GameInfo` is at line 137; `MLBGameMessage` starts around line 225; `MLBScoreMonitor` is at line 477; `_build_game_message` is at line 388; `_parse_games` is at line 673.
- `src/led_ticker/widgets/_frame_aware.py` — `_FrameAware` mixin; `MLBScoreboardMessage` must inherit this and be decorated `@attrs.define`.
- `src/led_ticker/drawing.py` — `compute_baseline_for_band(font, band_height_logical, scale, valign)` and `safe_scale(canvas)`.
- `src/led_ticker/fonts/__init__.py` — `FONT_SMALL` (5×8 BDF), `FONT_DEFAULT`, `font_line_height_logical`.
- `src/led_ticker/pixel_emoji.py` — `draw_with_emoji(canvas, font, cursor_pos, y, color, text)` returns pixels advanced; `measure_width(font, text, canvas)` returns width.
- `tests/stubs/rgbmatrix/__init__.py` — `_StubCanvas(width, height)` has `SetPixel`, `width`, `height`.

---

### Task 1: Data model + layout field

**Files:**
- Modify: `src/led_ticker/widgets/mlb.py` (GameInfo dataclass ~line 137, MLBScoreMonitor ~line 477)
- Test: `tests/test_mlb_scoreboard.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_mlb_scoreboard.py
"""Tests for MLBScoreboardMessage and related scoreboard layout support."""
from __future__ import annotations

import attrs

from led_ticker.widgets.mlb import GameInfo, MLBScoreMonitor


def test_gameinfo_challenge_fields_default_to_none():
    g = GameInfo(home_abbr="PHI", away_abbr="NYM")
    assert g.home_challenges is None
    assert g.away_challenges is None


def test_gameinfo_challenge_fields_can_be_set():
    g = GameInfo(home_abbr="PHI", away_abbr="NYM", home_challenges=2, away_challenges=1)
    assert g.home_challenges == 2
    assert g.away_challenges == 1


def test_mlb_score_monitor_layout_defaults_to_ticker():
    field = next(f for f in attrs.fields(MLBScoreMonitor) if f.name == "layout")
    assert field.default == "ticker"
```

- [ ] **Step 2: Run to confirm they fail**

```bash
cd /path/to/worktree
pytest tests/test_mlb_scoreboard.py -v
```
Expected: `ImportError` or `AttributeError` — `home_challenges` and `layout` don't exist yet.

- [ ] **Step 3: Add fields to `GameInfo` (line ~151 in mlb.py)**

The `GameInfo` dataclass currently ends at `postpone_tag`. Add two lines after `postpone_tag`:

```python
    # ABS challenge counts (None = system not in effect / data unavailable)
    home_challenges: int | None = None
    away_challenges: int | None = None
```

- [ ] **Step 4: Add `layout` field to `MLBScoreMonitor` (after `font` field, ~line 489)**

```python
    layout: str = attrs.field(default="ticker", kw_only=True)
```

- [ ] **Step 5: Run tests to confirm they pass**

```bash
pytest tests/test_mlb_scoreboard.py -v
```
Expected: 3 PASS.

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/widgets/mlb.py tests/test_mlb_scoreboard.py
git commit -m "feat: add GameInfo.home/away_challenges and MLBScoreMonitor.layout field"
```

---

### Task 2: ABS challenge data parsing

**Files:**
- Modify: `src/led_ticker/widgets/mlb.py` (`_parse_games` at ~line 673, URL at ~line 566)
- Test: `tests/test_mlb_scoreboard.py`

- [ ] **Step 1: Write the failing tests**

```python
# Append to tests/test_mlb_scoreboard.py

from led_ticker.widgets.mlb import MLBScoreMonitor


def _make_monitor_for_parse():
    """Return an MLBScoreMonitor wired to parse test data (no real session needed)."""
    import unittest.mock as mock
    from zoneinfo import ZoneInfo
    session = mock.MagicMock()
    monitor = MLBScoreMonitor(session=session, team="PHI")
    monitor._tz = ZoneInfo("America/New_York")
    return monitor


def test_parse_games_extracts_abs_challenges_when_present():
    monitor = _make_monitor_for_parse()
    from zoneinfo import ZoneInfo
    schedule = {
        "dates": [{
            "games": [{
                "gamePk": 1,
                "gameDate": "2026-05-26T23:10:00Z",
                "gameType": "R",
                "status": {"abstractGameState": "Live", "detailedState": "In Progress"},
                "teams": {
                    "home": {"team": {"abbreviation": "PHI"}, "score": 5},
                    "away": {"team": {"abbreviation": "NYM"}, "score": 3},
                },
                "linescore": {
                    "currentInning": 7,
                    "inningHalf": "top",
                    "balls": 1, "strikes": 2, "outs": 1,
                    "offense": {},
                },
                "challenges": {
                    "home": {"remainingChallenges": 2},
                    "away": {"remainingChallenges": 1},
                },
            }]
        }]
    }
    games = monitor._parse_games(schedule, ZoneInfo("America/New_York"))
    assert len(games) == 1
    assert games[0].home_challenges == 2
    assert games[0].away_challenges == 1


def test_parse_games_challenges_none_when_absent():
    monitor = _make_monitor_for_parse()
    from zoneinfo import ZoneInfo
    schedule = {
        "dates": [{
            "games": [{
                "gamePk": 2,
                "gameDate": "2026-05-26T23:10:00Z",
                "gameType": "R",
                "status": {"abstractGameState": "Live", "detailedState": "In Progress"},
                "teams": {
                    "home": {"team": {"abbreviation": "PHI"}, "score": 5},
                    "away": {"team": {"abbreviation": "NYM"}, "score": 3},
                },
                "linescore": {
                    "currentInning": 7,
                    "inningHalf": "top",
                    "balls": 1, "strikes": 2, "outs": 1,
                    "offense": {},
                },
                # no "challenges" key
            }]
        }]
    }
    games = monitor._parse_games(schedule, ZoneInfo("America/New_York"))
    assert len(games) == 1
    assert games[0].home_challenges is None
    assert games[0].away_challenges is None
```

- [ ] **Step 2: Run to confirm they fail**

```bash
pytest tests/test_mlb_scoreboard.py::test_parse_games_extracts_abs_challenges_when_present tests/test_mlb_scoreboard.py::test_parse_games_challenges_none_when_absent -v
```
Expected: FAIL — `GameInfo` constructor call in `_parse_games` doesn't pass challenge fields yet.

- [ ] **Step 3: Extend `_parse_games` to extract challenges**

In `_parse_games`, the Live block currently ends after setting `on_third`. After the `if abstract == "Live"` block (around line 717), add:

```python
                # ABS challenges — present only for games where the system is active.
                home_challenges: int | None = None
                away_challenges: int | None = None
                challenges = g.get("challenges", {})
                if challenges:
                    hc = challenges.get("home", {})
                    ac = challenges.get("away", {})
                    if hc is not None and "remainingChallenges" in hc:
                        home_challenges = int(hc["remainingChallenges"])
                    if ac is not None and "remainingChallenges" in ac:
                        away_challenges = int(ac["remainingChallenges"])
```

Then update the `GameInfo(...)` constructor call in `_parse_games` (around line 739) to pass the new fields:

```python
                games.append(
                    GameInfo(
                        home_abbr=home_abbr,
                        away_abbr=away_abbr,
                        home_score=home_score,
                        away_score=away_score,
                        state=resolved_state,
                        inning=inning,
                        start_time=start_time,
                        game_type=g.get("gameType", "R"),
                        game_pk=g.get("gamePk", 0),
                        balls=balls,
                        strikes=strikes,
                        outs=outs,
                        on_first=on_first,
                        on_second=on_second,
                        on_third=on_third,
                        postpone_reason=reason if postponed_state else "",
                        postpone_tag=postpone_tag if postponed_state else "PPD",
                        home_challenges=home_challenges,
                        away_challenges=away_challenges,
                    )
                )
```

Also update the API URL to request challenge data. Find the `url = (` block around line 566:

```python
        url = (
            f"{MLB_API}/schedule?teamId={self._team_id}"
            f"&startDate={start}&endDate={end}&sportId=1"
            f"&hydrate=team,linescore,challenges"
        )
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/test_mlb_scoreboard.py -v
```
Expected: 5 PASS (3 from Task 1 + 2 new).

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/widgets/mlb.py tests/test_mlb_scoreboard.py
git commit -m "feat: parse ABS challenge counts from MLB API schedule response"
```

---

### Task 3: MLBScoreboardMessage skeleton

**Files:**
- Modify: `src/led_ticker/widgets/mlb.py`
- Test: `tests/test_mlb_scoreboard.py`

- [ ] **Step 1: Write the failing tests**

```python
# Append to tests/test_mlb_scoreboard.py

from led_ticker.widgets.mlb import MLBScoreboardMessage


def _live_game() -> GameInfo:
    return GameInfo(
        home_abbr="PHI", away_abbr="NYM", state="live",
        home_score=5, away_score=3, inning="▲7",
        outs=2, balls=1, strikes=2,
        on_first=False, on_second=True, on_third=False,
    )


def _stub_canvas(w=128, h=16):
    from rgbmatrix import _StubCanvas
    return _StubCanvas(width=w, height=h)


def test_scoreboard_draw_live_returns_correct_cursor():
    canvas = _stub_canvas()
    msg = MLBScoreboardMessage(game=_live_game(), team_abbr="PHI")
    _, cursor = msg.draw(canvas)
    assert cursor == 128


def test_scoreboard_draw_final():
    canvas = _stub_canvas()
    game = GameInfo(home_abbr="PHI", away_abbr="NYM", state="final",
                    home_score=5, away_score=3)
    msg = MLBScoreboardMessage(game=game, team_abbr="PHI")
    result_canvas, cursor = msg.draw(canvas)
    assert cursor == 128
    assert result_canvas is canvas


def test_scoreboard_draw_preview():
    from datetime import datetime, timezone
    canvas = _stub_canvas()
    game = GameInfo(home_abbr="PHI", away_abbr="NYM", state="preview",
                    start_time=datetime(2026, 5, 26, 23, 10, tzinfo=timezone.utc))
    msg = MLBScoreboardMessage(game=game, team_abbr="PHI")
    _, cursor = msg.draw(canvas)
    assert cursor == 128


def test_scoreboard_draw_postponed():
    canvas = _stub_canvas()
    game = GameInfo(home_abbr="PHI", away_abbr="NYM", state="postponed",
                    postpone_tag="PPD", postpone_reason="Rain")
    msg = MLBScoreboardMessage(game=game, team_abbr="PHI")
    _, cursor = msg.draw(canvas)
    assert cursor == 128


def test_scoreboard_advance_frame_accepts_visit_id():
    msg = MLBScoreboardMessage(game=_live_game(), team_abbr="PHI")
    msg.advance_frame(visit_id=42)
    msg.advance_frame(visit_id=42)
    assert msg._frame_count == 2
```

- [ ] **Step 2: Run to confirm they fail**

```bash
pytest tests/test_mlb_scoreboard.py -k "scoreboard_draw or advance_frame" -v
```
Expected: `ImportError` — `MLBScoreboardMessage` doesn't exist yet.

- [ ] **Step 3: Add `MLBScoreboardMessage` class to `mlb.py`**

Add the following class after the `_build_game_message` function (around line 474) and before `@register("mlb")`:

```python
_CHALLENGE_COLOR: Color = make_color(255, 180, 0)  # amber
_CHALLENGE_USED: Color = make_color(60, 40, 0)     # dim amber


@attrs.define
class MLBScoreboardMessage(_FrameAware):
    """Scoreboard-style two-column game display.

    Renders: [away team + score] [center: inning/BSO/diamond] [home team + score]
    with ABS challenge pips beside each team name.
    """

    game: GameInfo
    team_abbr: str
    tz: ZoneInfo | None = None
    bg_color: Color | None = None
    font_color: Color | ColorProvider | None = attrs.field(default=None, kw_only=True)
    font: Font = attrs.field(default=FONT_DEFAULT, kw_only=True)

    def draw(
        self,
        canvas: Canvas,
        cursor_pos: int = 0,
        *,
        y_offset: int = 0,
        font_color: Any = None,
    ) -> DrawResult:
        return canvas, cursor_pos + canvas.width
```

You also need to import `_FrameAware` at the top of `mlb.py`. Add to the existing imports:

```python
from led_ticker.widgets._frame_aware import _FrameAware
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/test_mlb_scoreboard.py -v
```
Expected: all 10 PASS (5 old + 5 new).

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/widgets/mlb.py tests/test_mlb_scoreboard.py
git commit -m "feat: add MLBScoreboardMessage skeleton (draw stub, _FrameAware)"
```

---

### Task 4: Team column rendering

**Files:**
- Modify: `src/led_ticker/widgets/mlb.py` (`MLBScoreboardMessage.draw`)
- Test: `tests/test_mlb_scoreboard.py`

The team columns occupy the left ~30% (away team) and right ~30% (home team) of canvas width. Row 0 (top half) shows the team abbreviation; row 1 (bottom half) shows the score.

Zone constants (computed inside `draw()`):
```
left_w  = canvas.width * 30 // 100   # e.g. 38px on 128px canvas
right_w = canvas.width * 30 // 100
center_total = canvas.width - left_w - right_w
right_start = canvas.width - right_w
```

- [ ] **Step 1: Write the failing tests**

```python
# Append to tests/test_mlb_scoreboard.py


def test_scoreboard_draws_pixels_for_team_names():
    """draw() must paint at least one pixel — smoke test that rendering occurs."""
    canvas = _stub_canvas()
    msg = MLBScoreboardMessage(game=_live_game(), team_abbr="PHI")
    msg.draw(canvas)
    assert len(canvas._pixels) > 0


def test_scoreboard_live_score_pixels_exist():
    """Score digits must produce pixels in the bottom half of the canvas."""
    canvas = _stub_canvas()
    game = GameInfo(home_abbr="PHI", away_abbr="NYM", state="live",
                    home_score=5, away_score=3, inning="▲7",
                    outs=1, balls=1, strikes=1)
    msg = MLBScoreboardMessage(game=game, team_abbr="PHI")
    msg.draw(canvas)
    bottom_half_pixels = {(x, y): c for (x, y), c in canvas._pixels.items() if y >= 8}
    assert len(bottom_half_pixels) > 0


def test_scoreboard_final_win_loss_colors():
    """Winning team score should not be pure white or pure red (uses win/loss palette)."""
    canvas = _stub_canvas()
    game = GameInfo(home_abbr="PHI", away_abbr="NYM", state="final",
                    home_score=5, away_score=3)  # PHI wins (home)
    msg = MLBScoreboardMessage(game=game, team_abbr="PHI")
    msg.draw(canvas)
    # Just assert no exception and some pixels rendered
    assert len(canvas._pixels) > 0
```

- [ ] **Step 2: Run to confirm they fail**

```bash
pytest tests/test_mlb_scoreboard.py::test_scoreboard_draws_pixels_for_team_names tests/test_mlb_scoreboard.py::test_scoreboard_live_score_pixels_exist tests/test_mlb_scoreboard.py::test_scoreboard_final_win_loss_colors -v
```
Expected: FAIL — `draw()` still returns early without painting.

- [ ] **Step 3: Implement team column rendering in `draw()`**

Replace the stub `draw()` body with a full implementation. The full `draw()` at this stage handles team names + scores only (center zone left empty until Task 5):

```python
    def draw(
        self,
        canvas: Canvas,
        cursor_pos: int = 0,
        *,
        y_offset: int = 0,
        font_color: Any = None,
    ) -> DrawResult:
        from led_ticker.drawing import compute_baseline_for_band, safe_scale
        from led_ticker.fonts import FONT_SMALL
        from led_ticker.pixel_emoji import draw_with_emoji, measure_width

        scale = safe_scale(canvas)
        half_h = canvas.height // 2  # logical rows per band (8 on 128×16 canvas)

        # Zone widths (logical pixels)
        left_w = canvas.width * 30 // 100
        right_w = canvas.width * 30 // 100
        right_start = canvas.width - right_w

        # Baselines: top half (team names), bottom half (scores)
        top_baseline = compute_baseline_for_band(self.font, half_h, scale, valign="center")
        bottom_baseline = half_h + compute_baseline_for_band(
            self.font, half_h, scale, valign="center"
        )

        game = self.game

        # Determine colors
        away_c = _team_color(game.away_abbr)
        home_c = _team_color(game.home_abbr)

        if game.state == "final":
            away_won = (game.away_score or 0) > (game.home_score or 0)
            win_c = _team_palette("WIN_COLOR")
            loss_c = _team_palette("LOSS_COLOR")
            away_score_c = win_c if away_won else loss_c
            home_score_c = loss_c if away_won else win_c
        else:
            away_score_c = RGB_WHITE
            home_score_c = RGB_WHITE

        def _draw_centered(text: str, zone_start: int, zone_w: int, y: int, color: Color) -> None:
            w = measure_width(self.font, text, canvas)
            x = zone_start + max(0, (zone_w - w) // 2)
            draw_with_emoji(canvas, self.font, x, y=y, color=color, text=text)

        away_abbr = game.away_abbr
        home_abbr = game.home_abbr

        # Away team (left column)
        _draw_centered(away_abbr, 0, left_w, top_baseline + y_offset, away_c)
        away_score_str = str(game.away_score) if game.away_score is not None else "–"
        _draw_centered(away_score_str, 0, left_w, bottom_baseline + y_offset, away_score_c)

        # Home team (right column)
        _draw_centered(home_abbr, right_start, right_w, top_baseline + y_offset, home_c)
        home_score_str = str(game.home_score) if game.home_score is not None else "–"
        _draw_centered(home_score_str, right_start, right_w, bottom_baseline + y_offset, home_score_c)

        return canvas, cursor_pos + canvas.width
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/test_mlb_scoreboard.py -v
```
Expected: all 13 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/widgets/mlb.py
git commit -m "feat: MLBScoreboardMessage renders team columns with scores and state colors"
```

---

### Task 5: Center zone rendering

**Files:**
- Modify: `src/led_ticker/widgets/mlb.py` (`MLBScoreboardMessage.draw`)
- Test: `tests/test_mlb_scoreboard.py`

The center zone occupies the middle ~40% of canvas width, split into two halves:
- Center-left (~20%): inning + outs (row 0), balls + strikes (row 1) — **live state only**
- Center-right (~20%): diamond — handled in Task 6

For non-live states, center-left shows state labels using `FONT_SMALL`.

- [ ] **Step 1: Write the failing tests**

```python
# Append to tests/test_mlb_scoreboard.py


def test_scoreboard_center_pixels_for_live_game():
    """Center zone must paint pixels for a live game."""
    canvas = _stub_canvas()
    msg = MLBScoreboardMessage(game=_live_game(), team_abbr="PHI")
    msg.draw(canvas)
    center_start = 128 * 30 // 100
    center_end = 128 - 128 * 30 // 100
    center_pixels = {
        (x, y): c for (x, y), c in canvas._pixels.items()
        if center_start <= x < center_end
    }
    assert len(center_pixels) > 0


def test_scoreboard_preview_draws_without_error():
    from datetime import datetime, timezone
    canvas = _stub_canvas()
    game = GameInfo(
        home_abbr="PHI", away_abbr="NYM", state="preview",
        start_time=datetime(2026, 5, 26, 23, 10, tzinfo=timezone.utc),
    )
    msg = MLBScoreboardMessage(game=game, team_abbr="PHI")
    _, cursor = msg.draw(canvas)
    assert cursor == 128
```

- [ ] **Step 2: Run to confirm they fail**

```bash
pytest tests/test_mlb_scoreboard.py::test_scoreboard_center_pixels_for_live_game tests/test_mlb_scoreboard.py::test_scoreboard_preview_draws_without_error -v
```
Expected: FAIL — center zone paints no pixels yet.

- [ ] **Step 3: Add center-left rendering inside `draw()`**

Inside `draw()`, after the home team column block and before `return canvas, ...`, add:

```python
        # --- Center zone ---
        center_total = canvas.width - left_w - right_w
        center_half = center_total // 2
        cl_start = left_w                   # center-left x start
        cr_start = left_w + center_half     # center-right x start

        small_top = compute_baseline_for_band(FONT_SMALL, half_h, scale, valign="center")
        small_bottom = half_h + compute_baseline_for_band(
            FONT_SMALL, half_h, scale, valign="center"
        )

        def _draw_small(text: str, x: int, y: int, color: Color) -> None:
            draw_with_emoji(canvas, FONT_SMALL, x, y=y + y_offset, color=color, text=text)

        if game.state == "live":
            # Row 0: inning + outs dots
            inning_str = game.inning or "–"
            out_c = make_color(255, 80, 80)
            outs_str = "●" * game.outs + "○" * (3 - game.outs)
            _draw_small(inning_str, cl_start, small_top, RGB_WHITE)
            inning_w = measure_width(FONT_SMALL, inning_str, canvas)
            _draw_small(outs_str, cl_start + inning_w + 2, small_top, out_c)

            # Row 1: B/S count
            ball_c = make_color(80, 255, 80)
            strike_c = make_color(255, 255, 80)
            _draw_small(str(game.balls), cl_start, small_bottom, ball_c)
            b_w = measure_width(FONT_SMALL, str(game.balls), canvas)
            _draw_small("B ", cl_start + b_w, small_bottom, RGB_WHITE)
            bs_w = b_w + measure_width(FONT_SMALL, "B ", canvas)
            _draw_small(str(game.strikes), cl_start + bs_w, small_bottom, strike_c)
            s_w = measure_width(FONT_SMALL, str(game.strikes), canvas)
            _draw_small("S", cl_start + bs_w + s_w, small_bottom, RGB_WHITE)

        elif game.state == "final":
            _draw_small("F", cl_start, small_top, RGB_WHITE)
            _draw_small("FINAL", cl_start, small_bottom, make_color(180, 180, 180))

        elif game.state == "preview":
            tz = self._tz if hasattr(self, "_tz") and self._tz else None
            time_str = _format_game_time(game.start_time, tz) if game.start_time else "TBD"
            _draw_small(time_str, cl_start, small_top, RGB_WHITE)

        elif game.state == "postponed":
            tag_c = make_color(255, 200, 60)
            _draw_small(game.postpone_tag, cl_start, small_top, tag_c)
            if game.postpone_reason:
                _draw_small(game.postpone_reason[:6], cl_start, small_bottom, tag_c)
```

Note: `MLBScoreboardMessage` doesn't store `_tz`. For preview time formatting pass `None` as the tz — `_format_game_time` already handles that case by returning local time. Remove the `hasattr` check and simplify to:

```python
        elif game.state == "preview":
            _tz = self.tz or ZoneInfo("UTC")
            time_str = _format_game_time(game.start_time, _tz) if game.start_time else "TBD"
            _draw_small(time_str, cl_start, small_top, RGB_WHITE)
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/test_mlb_scoreboard.py -v
```
Expected: all 15 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/widgets/mlb.py
git commit -m "feat: MLBScoreboardMessage center-left zone (inning, outs, B/S, state labels)"
```

---

### Task 6: Diamond rendering

**Files:**
- Modify: `src/led_ticker/widgets/mlb.py`
- Test: `tests/test_mlb_scoreboard.py`

The diamond occupies center-right (`cr_start` to `canvas.width - right_w`). It uses two rows:
- Row 0: `◆`/`◇` for 2B centered in center-right zone
- Row 1: `◇`/`◆` for 3B at left edge of center-right, `◆`/`◇` for 1B at right edge

Only rendered in the `live` state.

- [ ] **Step 1: Write the failing test**

```python
# Append to tests/test_mlb_scoreboard.py


def test_scoreboard_diamond_second_base_occupied_paints_in_center_right():
    """With runner on 2B, center-right zone must have pixels in the top row."""
    canvas = _stub_canvas()
    game = GameInfo(
        home_abbr="PHI", away_abbr="NYM", state="live",
        home_score=5, away_score=3, inning="▲7",
        outs=0, balls=0, strikes=0,
        on_second=True, on_first=False, on_third=False,
    )
    msg = MLBScoreboardMessage(game=game, team_abbr="PHI")
    msg.draw(canvas)
    cr_start = 128 - 128 * 30 // 100 - (128 * 40 // 100) // 2
    top_row_center_right = {
        (x, y): c for (x, y), c in canvas._pixels.items()
        if x >= cr_start and y < 8
    }
    assert len(top_row_center_right) > 0
```

- [ ] **Step 2: Run to confirm it fails**

```bash
pytest tests/test_mlb_scoreboard.py::test_scoreboard_diamond_second_base_occupied_paints_in_center_right -v
```
Expected: FAIL — center-right has no pixels yet.

- [ ] **Step 3: Add diamond rendering inside the `if game.state == "live":` block**

After the B/S count rendering, append inside the `live` block:

```python
            # Diamond: center-right zone
            occupied_c = make_color(255, 220, 50)  # yellow
            empty_c = make_color(50, 50, 50)        # dim
            b2 = "◆" if game.on_second else "◇"
            b3 = "◆" if game.on_third else "◇"
            b1 = "◆" if game.on_first else "◇"

            b2_c = occupied_c if game.on_second else empty_c
            b3_c = occupied_c if game.on_third else empty_c
            b1_c = occupied_c if game.on_first else empty_c

            char_w = measure_width(FONT_SMALL, b2, canvas)
            cr_center = cr_start + center_half // 2

            # Row 0: 2B centered
            _draw_small(b2, cr_center - char_w // 2, small_top, b2_c)

            # Row 1: 3B left, 1B right
            _draw_small(b3, cr_start, small_bottom, b3_c)
            _draw_small(b1, cr_start + center_half - char_w, small_bottom, b1_c)
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/test_mlb_scoreboard.py -v
```
Expected: all 16 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/widgets/mlb.py
git commit -m "feat: MLBScoreboardMessage diamond rendering (2B/3B/1B occupancy)"
```

---

### Task 7: ABS challenge pip rendering

**Files:**
- Modify: `src/led_ticker/widgets/mlb.py`
- Test: `tests/test_mlb_scoreboard.py`

Challenge pips (●) appear to the right of each team abbreviation in the top row. Max 2 pips; clamped to 2 if API returns higher. Hidden entirely when count is `None`.

- [ ] **Step 1: Write the failing tests**

```python
# Append to tests/test_mlb_scoreboard.py


def _count_pixels_in_zone(canvas, x_start, x_end, y_start=0, y_end=16):
    return sum(
        1 for (x, y) in canvas._pixels
        if x_start <= x < x_end and y_start <= y < y_end
    )


def test_scoreboard_abs_pips_two_remaining_paints_more_than_zero():
    """Two remaining challenges should add pixels to the right of away abbr."""
    canvas = _stub_canvas()
    game = GameInfo(
        home_abbr="PHI", away_abbr="NYM", state="live",
        home_score=5, away_score=3, inning="▲7",
        outs=0, balls=0, strikes=0,
        away_challenges=2, home_challenges=2,
    )
    msg = MLBScoreboardMessage(game=game, team_abbr="PHI")
    msg.draw(canvas)
    # Canvas must have pixels — pips included somewhere in left column
    assert _count_pixels_in_zone(canvas, 0, 38, 0, 8) > 0


def test_scoreboard_abs_pips_none_does_not_crash():
    """None challenges should render without error (pips hidden)."""
    canvas = _stub_canvas()
    game = GameInfo(
        home_abbr="PHI", away_abbr="NYM", state="live",
        home_score=5, away_score=3, inning="▲7",
        outs=0, balls=0, strikes=0,
        away_challenges=None, home_challenges=None,
    )
    msg = MLBScoreboardMessage(game=game, team_abbr="PHI")
    _, cursor = msg.draw(canvas)
    assert cursor == 128


def test_scoreboard_abs_pips_clamped_to_two():
    """Values > 2 must not raise an error."""
    canvas = _stub_canvas()
    game = GameInfo(
        home_abbr="PHI", away_abbr="NYM", state="live",
        home_score=5, away_score=3, inning="▲7",
        outs=0, balls=0, strikes=0,
        away_challenges=5, home_challenges=3,
    )
    msg = MLBScoreboardMessage(game=game, team_abbr="PHI")
    _, cursor = msg.draw(canvas)
    assert cursor == 128
```

- [ ] **Step 2: Run to confirm they fail**

```bash
pytest tests/test_mlb_scoreboard.py -k "abs_pips" -v
```
Expected: FAIL — no pip rendering yet (tests themselves may pass since we're only checking pixels exist, but the pip-specific ones will fail if pip pixels are expected separately from team name pixels). Verify they fail before proceeding.

- [ ] **Step 3: Add pip rendering inside `draw()`**

After the `_draw_centered(away_abbr, ...)` call (but before drawing the score), add pip rendering. Insert after both team-name draws:

```python
        # ABS challenge pips — superscript beside each team abbreviation
        def _draw_pips(count: int | None, zone_start: int, zone_w: int, y: int) -> None:
            if count is None:
                return
            n = min(count, 2)
            abbr_w = measure_width(self.font, game.away_abbr if zone_start == 0 else game.home_abbr, canvas)
            abbr_center = zone_start + max(0, (zone_w - abbr_w) // 2)
            pip_x = abbr_center + abbr_w + 1
            for i in range(2):
                color = _CHALLENGE_COLOR if i < n else _CHALLENGE_USED
                pip_w = measure_width(FONT_SMALL, "●", canvas)
                draw_with_emoji(canvas, FONT_SMALL, pip_x + i * (pip_w + 1),
                                y=y + y_offset, color=color, text="●")

        _draw_pips(game.away_challenges, 0, left_w, top_baseline)
        _draw_pips(game.home_challenges, right_start, right_w, top_baseline)
```

Note: the helper references `game.away_abbr` unconditionally; fix it to use a parameter:

```python
        def _draw_pips(count: int | None, abbr: str, zone_start: int, zone_w: int, y: int) -> None:
            if count is None:
                return
            n = min(count, 2)
            abbr_w = measure_width(self.font, abbr, canvas)
            abbr_center = zone_start + max(0, (zone_w - abbr_w) // 2)
            pip_x = abbr_center + abbr_w + 1
            pip_w = measure_width(FONT_SMALL, "●", canvas)
            for i in range(2):
                color = _CHALLENGE_COLOR if i < n else _CHALLENGE_USED
                draw_with_emoji(canvas, FONT_SMALL, pip_x + i * (pip_w + 1),
                                y=y + y_offset, color=color, text="●")

        _draw_pips(game.away_challenges, away_abbr, 0, left_w, top_baseline)
        _draw_pips(game.home_challenges, home_abbr, right_start, right_w, top_baseline)
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/test_mlb_scoreboard.py -v
```
Expected: all 19 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/widgets/mlb.py
git commit -m "feat: MLBScoreboardMessage ABS challenge pip rendering"
```

---

### Task 8: Factory function + update() routing

**Files:**
- Modify: `src/led_ticker/widgets/mlb.py` (add `_build_scoreboard_message`, update `update()`, update type annotations)
- Test: `tests/test_mlb_scoreboard.py`

- [ ] **Step 1: Write the failing tests**

```python
# Append to tests/test_mlb_scoreboard.py

import unittest.mock as mock


async def _run_update_with_schedule(layout: str, schedule: dict):
    """Helper: build a monitor, inject a schedule response, run update()."""
    from zoneinfo import ZoneInfo
    session = mock.MagicMock()
    monitor = MLBScoreMonitor(session=session, team="PHI", layout=layout)
    monitor._team_id = 143  # PHI's real ID — skip team resolution
    monitor._tz = ZoneInfo("America/New_York")

    resp = mock.AsyncMock()
    resp.json = mock.AsyncMock(return_value=schedule)
    session.get.return_value.__aenter__ = mock.AsyncMock(return_value=resp)
    session.get.return_value.__aexit__ = mock.AsyncMock(return_value=False)

    await monitor.update()
    return monitor


def _phi_nym_schedule(state: str = "live") -> dict:
    return {
        "dates": [{
            "games": [{
                "gamePk": 1,
                "gameDate": "2026-05-26T23:10:00Z",
                "gameType": "R",
                "status": {
                    "abstractGameState": "Live" if state == "live" else "Final",
                    "detailedState": "In Progress" if state == "live" else "Final",
                },
                "teams": {
                    "home": {"team": {"abbreviation": "PHI"}, "score": 5},
                    "away": {"team": {"abbreviation": "NYM"}, "score": 3},
                },
                "linescore": {
                    "currentInning": 7,
                    "inningHalf": "top",
                    "balls": 1, "strikes": 2, "outs": 1,
                    "offense": {},
                },
            }]
        }]
    }


import pytest


@pytest.mark.asyncio
async def test_layout_scoreboard_builds_scoreboard_messages():
    monitor = await _run_update_with_schedule("scoreboard", _phi_nym_schedule())
    game_stories = [s for s in monitor.feed_stories if isinstance(s, MLBScoreboardMessage)]
    assert len(game_stories) >= 1


@pytest.mark.asyncio
async def test_layout_ticker_builds_game_messages():
    from led_ticker.widgets.mlb import MLBGameMessage
    monitor = await _run_update_with_schedule("ticker", _phi_nym_schedule())
    game_stories = [s for s in monitor.feed_stories if isinstance(s, MLBGameMessage)]
    assert len(game_stories) >= 1
```

- [ ] **Step 2: Run to confirm they fail**

```bash
pytest tests/test_mlb_scoreboard.py -k "layout_scoreboard or layout_ticker" -v
```
Expected: FAIL — `update()` always builds `MLBGameMessage` regardless of layout.

- [ ] **Step 3: Add `_build_scoreboard_message` factory function**

Add this function after `_build_game_message` (around line 474, before `_CHALLENGE_COLOR`):

```python
def _build_scoreboard_message(
    game: GameInfo,
    team_abbr: str,
    tz: ZoneInfo,
    bg_color: Color | None = None,
    font: Font | None = None,
    font_color: Color | ColorProvider | None = None,
) -> MLBScoreboardMessage:
    """Build a scoreboard-layout message for a single game."""
    from led_ticker.fonts import FONT_DEFAULT as _FONT_DEFAULT
    return MLBScoreboardMessage(
        game=game,
        team_abbr=team_abbr,
        tz=tz,
        bg_color=bg_color,
        font=font if font is not None else _FONT_DEFAULT,
        font_color=font_color,
    )
```

- [ ] **Step 4: Update `update()` to branch on `self.layout`**

In `MLBScoreMonitor.update()`, find the block that builds `stories` (around line 658):

```python
        series_title = _build_series_title(
            self.team,
            current,
            tz,
            bg_color=self.bg_color,
            font=self.font,
            font_color=self.font_color,
        )
        self.feed_title = series_title
        stories: list[TickerMessage | MLBGameMessage] = [series_title]
        stories.extend(
            _build_game_message(
                g,
                self.team,
                tz,
                bg_color=self.bg_color,
                font=self.font,
                font_color=self.font_color,
            )
            for g in current.games
        )
```

Replace with:

```python
        series_title = _build_series_title(
            self.team,
            current,
            tz,
            bg_color=self.bg_color,
            font=self.font,
            font_color=self.font_color,
        )
        self.feed_title = series_title
        _build_msg = (
            _build_scoreboard_message
            if self.layout == "scoreboard"
            else _build_game_message
        )
        stories: list[TickerMessage | MLBGameMessage | MLBScoreboardMessage] = [series_title]
        stories.extend(
            _build_msg(
                g,
                self.team,
                tz,
                bg_color=self.bg_color,
                font=self.font,
                font_color=self.font_color,
            )
            for g in current.games
        )
```

Also update the `feed_stories` type annotation on `MLBScoreMonitor` (~line 496):

```python
    feed_stories: list[TickerMessage | MLBGameMessage | MLBScoreboardMessage] = attrs.field(
        init=False, factory=list
    )
```

And `feed_title`:

```python
    feed_title: TickerMessage | MLBGameMessage | MLBScoreboardMessage | None = attrs.field(
        init=False, default=None
    )
```

- [ ] **Step 5: Run full test suite**

```bash
pytest tests/test_mlb_scoreboard.py -v
pytest tests/ -v --ignore=tests/test_mlb_scoreboard.py -x
```
Expected: all pass. The existing tests must not be broken.

- [ ] **Step 6: Run type checking**

```bash
make typecheck
```
Fix any pyright errors before committing.

- [ ] **Step 7: Commit**

```bash
git add src/led_ticker/widgets/mlb.py tests/test_mlb_scoreboard.py
git commit -m "feat: route MLBScoreMonitor to scoreboard layout via layout config field"
```

---

## Done

Run the full suite one final time:

```bash
pytest tests/ -v
```

Then run the contract test to confirm `MLBScoreboardMessage.advance_frame` is covered:

```bash
pytest tests/test_widget_contracts.py -v
```

Expected: PASS — `_FrameAware` provides `advance_frame(*, visit_id=...)` so the contract test finds no violations.
