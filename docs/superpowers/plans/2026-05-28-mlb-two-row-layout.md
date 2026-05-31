# MLB Two-Row Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `layout = "two_row"` to the `mlb` widget — a two-band hires display with matchup/score on top and status/situation on the bottom, with per-team colors and ABS challenge pips.

**Architecture:** A new `MLBTwoRowMessage` custom draw class (mirrors `MLBScoreboardMessage`) stores pre-computed `top_segments` and `bottom_segments` lists populated by `_build_two_row_message()`. `draw()` renders both bands using `resolve_band_heights` + `row_layout` from `_row_layout.py`. `MLBScoreMonitor` dispatches to it when `layout == "two_row"`. Field wiring (top_font, top_row_height) mirrors the pool widget's pattern exactly.

**Tech Stack:** Python 3.13, attrs, pytest, led-ticker internal rendering primitives (`draw_with_emoji`, `resolve_band_heights`, `row_layout`, `compute_baseline_for_band`).

---

### Task 1: `MLBScoreMonitor` fields + dispatch skeleton

**Files:**
- Modify: `src/led_ticker/widgets/mlb.py` (class `MLBScoreMonitor`, ~line 695–948)
- Test: `tests/test_widgets/test_mlb.py`

- [ ] **Step 1: Write failing tests**

Add at the bottom of `tests/test_widgets/test_mlb.py`:

```python
class TestMLBTwoRowLayout:
    """MLBTwoRowMessage class + MLBScoreMonitor dispatch for layout='two_row'."""

    def test_monitor_top_font_default_is_none(self):
        from unittest import mock
        m = MLBScoreMonitor(session=mock.Mock(), team="PHI")
        assert m.top_font is None

    def test_monitor_top_row_height_default_is_none(self):
        from unittest import mock
        m = MLBScoreMonitor(session=mock.Mock(), team="PHI")
        assert m.top_row_height is None

    def test_monitor_layout_default_is_ticker(self):
        from unittest import mock
        m = MLBScoreMonitor(session=mock.Mock(), team="PHI")
        assert m.layout == "ticker"

    def test_two_row_message_type_imported(self):
        from led_ticker.widgets.mlb import MLBTwoRowMessage  # noqa: F401

    def test_two_row_stories_are_mlb_two_row_message_instances(self):
        """Tripwire: all stories are MLBTwoRowMessage when layout='two_row'.
        Catches a regression where dispatch routes to SegmentMessage instead.
        """
        from unittest import mock
        from led_ticker.widgets.mlb import MLBTwoRowMessage

        m = MLBScoreMonitor(session=mock.Mock(), team="PHI", layout="two_row")
        game = GameInfo(
            away_abbr="NYM", home_abbr="PHI",
            away_score=5, home_score=3, state="final",
        )
        from zoneinfo import ZoneInfo
        from led_ticker.widgets.mlb import SeriesInfo, _build_two_row_message
        # Simulate what update() would build
        from led_ticker.widgets.mlb import _build_two_row_message
        msg = _build_two_row_message(game, "PHI", ZoneInfo("America/New_York"))
        assert isinstance(msg, MLBTwoRowMessage)
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /path/to/repo && python -m pytest tests/test_widgets/test_mlb.py::TestMLBTwoRowLayout -v
```

Expected: `ImportError: cannot import name 'MLBTwoRowMessage'` or `AttributeError: 'MLBScoreMonitor' has no attribute 'top_font'`

- [ ] **Step 3: Add attrs fields to `MLBScoreMonitor`**

In `src/led_ticker/widgets/mlb.py`, after the `layout` field (line ~699):

```python
    top_font: Font | None = attrs.field(default=None, kw_only=True)
    top_row_height: int | None = attrs.field(default=None, kw_only=True)
```

Widen the `feed_stories` type annotation (line ~706) to include `MLBTwoRowMessage`:

```python
    feed_stories: list[TickerMessage | SegmentMessage | MLBScoreboardMessage | MLBTwoRowMessage] = (
        attrs.field(init=False, factory=list)
    )
```

Also widen `feed_title`:

```python
    feed_title: TickerMessage | SegmentMessage | MLBScoreboardMessage | MLBTwoRowMessage | None = (
        attrs.field(init=False, default=None)
    )
```

- [ ] **Step 4: Add `MLBTwoRowMessage` stub class**

Add just before `class MLBScoreMonitor` (after `MLBScoreboardMessage`):

```python
@attrs.define
class MLBTwoRowMessage(_FrameAware):
    """Two-band game display: score/matchup on top, status on bottom."""

    game: GameInfo
    team_abbr: str
    tz: ZoneInfo | None = None
    bg_color: Color | None = None
    font_color: Color | ColorProvider | None = attrs.field(default=None, kw_only=True)
    font: Font = attrs.field(default=FONT_DEFAULT, kw_only=True)
    small_font: Font = attrs.field(default=FONT_SMALL, kw_only=True)
    top_font: Font | None = attrs.field(default=None, kw_only=True)
    top_row_height: int | None = attrs.field(default=None, kw_only=True)
    top_segments: list[tuple[str, Color]] = attrs.field(factory=list)
    bottom_segments: list[tuple[str, Color]] = attrs.field(factory=list)

    def draw(
        self,
        canvas: Canvas,
        cursor_pos: int = 0,
        *,
        y_offset: int = 0,
        font_color: Any = None,
    ) -> DrawResult:
        return canvas, canvas.width  # stub — implemented in later tasks
```

- [ ] **Step 5: Add `_build_two_row_message` stub**

After `_build_scoreboard_message`:

```python
def _build_two_row_message(
    game: GameInfo,
    team_abbr: str,
    tz: ZoneInfo,
    bg_color: Color | None = None,
    font: Font | None = None,
    small_font: Font | None = None,
    top_font: Font | None = None,
    top_row_height: int | None = None,
    font_color: Color | ColorProvider | None = None,
) -> MLBTwoRowMessage:
    """Build a two-row layout message for a single game."""
    return MLBTwoRowMessage(
        game=game,
        team_abbr=team_abbr,
        tz=tz,
        bg_color=bg_color,
        font=font if font is not None else FONT_DEFAULT,
        small_font=small_font if small_font is not None else FONT_SMALL,
        top_font=top_font,
        top_row_height=top_row_height,
        font_color=font_color,
    )
```

- [ ] **Step 6: Add dispatch branch in `update()`**

In `MLBScoreMonitor.update()`, find the layout dispatch block (~line 923):

```python
        if self.layout == "scoreboard":
            stories.extend(...)
        else:
            stories.extend(...)
```

Replace with:

```python
        if self.layout == "scoreboard":
            stories.extend(
                _build_scoreboard_message(
                    g,
                    self.team,
                    tz,
                    bg_color=self.bg_color,
                    font=self.font,
                    small_font=self.small_font,
                    font_color=self.font_color,
                )
                for g in current.games
            )
        elif self.layout == "two_row":
            stories.extend(
                _build_two_row_message(
                    g,
                    self.team,
                    tz,
                    bg_color=self.bg_color,
                    font=self.font,
                    small_font=self.small_font,
                    top_font=self.top_font,
                    top_row_height=self.top_row_height,
                    font_color=self.font_color,
                )
                for g in current.games
            )
        else:
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

- [ ] **Step 7: Run tests to confirm they pass**

```bash
python -m pytest tests/test_widgets/test_mlb.py::TestMLBTwoRowLayout -v
```

Expected: 4 PASS

- [ ] **Step 8: Run full suite to confirm no regressions**

```bash
python -m pytest tests/test_widgets/test_mlb.py -v
```

Expected: All existing tests still pass.

- [ ] **Step 9: Commit**

```bash
git add src/led_ticker/widgets/mlb.py tests/test_widgets/test_mlb.py
git commit -m "feat: add MLBTwoRowMessage stub + MLBScoreMonitor dispatch for layout=two_row"
```

---

### Task 2: Preview state segments

**Files:**
- Modify: `src/led_ticker/widgets/mlb.py` (`_build_two_row_message`)
- Test: `tests/test_widgets/test_mlb.py` (`TestMLBTwoRowLayout`)

The preview state shows `AWAY @ HOME (W-L)` on top, game time on bottom.

- [ ] **Step 1: Write failing tests**

Add inside `TestMLBTwoRowLayout` in `tests/test_widgets/test_mlb.py`:

```python
    def test_preview_top_has_away_at_home(self):
        """Top segments contain AWAY, '@', HOME with team colors."""
        from zoneinfo import ZoneInfo
        from led_ticker.widgets.mlb import _build_two_row_message, _team_color

        game = GameInfo(
            away_abbr="NYM", home_abbr="PHI", state="preview",
            start_time=None,
        )
        series = SeriesInfo(opponent_abbr="NYM", games=[game])
        msg = _build_two_row_message(game, "PHI", ZoneInfo("America/New_York"))
        texts = [t for t, _ in msg.top_segments]
        colors = [c for _, c in msg.top_segments]
        assert "NYM" in texts
        assert "@" in " ".join(texts)
        assert "PHI" in texts
        nym_idx = texts.index("NYM")
        phi_idx = texts.index("PHI")
        assert colors[nym_idx] == _team_color("NYM")
        assert colors[phi_idx] == _team_color("PHI")

    def test_preview_bottom_has_game_time(self):
        """Bottom segments contain a formatted start time."""
        import datetime
        from zoneinfo import ZoneInfo
        from led_ticker.widgets.mlb import _build_two_row_message

        tz = ZoneInfo("America/New_York")
        # today at 7:10 PM ET
        now = datetime.datetime.now(tz).replace(hour=19, minute=10, second=0, microsecond=0)
        game = GameInfo(away_abbr="NYM", home_abbr="PHI", state="preview", start_time=now)
        msg = _build_two_row_message(game, "PHI", tz)
        bottom_text = "".join(t for t, _ in msg.bottom_segments)
        assert "7:10" in bottom_text or "PM" in bottom_text

    def test_preview_top_includes_series_record_when_decided(self):
        """Series record appears in top segments when total_decided > 0."""
        from zoneinfo import ZoneInfo
        from led_ticker.widgets.mlb import _build_two_row_message

        game = GameInfo(away_abbr="NYM", home_abbr="PHI", state="preview", start_time=None)
        msg = _build_two_row_message(
            game, "PHI", ZoneInfo("America/New_York"),
            series_wins=2, series_losses=1,
        )
        top_text = "".join(t for t, _ in msg.top_segments)
        assert "2-1" in top_text or "2" in top_text

    def test_preview_top_omits_record_when_no_games_decided(self):
        """No record segment when series_wins + series_losses == 0."""
        from zoneinfo import ZoneInfo
        from led_ticker.widgets.mlb import _build_two_row_message

        game = GameInfo(away_abbr="NYM", home_abbr="PHI", state="preview", start_time=None)
        msg = _build_two_row_message(
            game, "PHI", ZoneInfo("America/New_York"),
            series_wins=0, series_losses=0,
        )
        top_text = "".join(t for t, _ in msg.top_segments)
        # no record numbers
        assert "0-0" not in top_text
        assert "1-0" not in top_text
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
python -m pytest tests/test_widgets/test_mlb.py::TestMLBTwoRowLayout::test_preview_top_has_away_at_home -v
```

Expected: FAIL — `top_segments` is empty.

- [ ] **Step 3: Add `series_wins` / `series_losses` params to `_build_two_row_message`**

Update `_build_two_row_message` signature and `MLBTwoRowMessage.__init__` to accept series record context:

```python
def _build_two_row_message(
    game: GameInfo,
    team_abbr: str,
    tz: ZoneInfo,
    bg_color: Color | None = None,
    font: Font | None = None,
    small_font: Font | None = None,
    top_font: Font | None = None,
    top_row_height: int | None = None,
    font_color: Color | ColorProvider | None = None,
    series_wins: int = 0,
    series_losses: int = 0,
) -> MLBTwoRowMessage:
    top_segs, bot_segs = _compute_two_row_segments_preview(
        game, team_abbr, tz, series_wins, series_losses
    ) if game.state == "preview" else ([], [])
    return MLBTwoRowMessage(
        game=game,
        team_abbr=team_abbr,
        tz=tz,
        bg_color=bg_color,
        font=font if font is not None else FONT_DEFAULT,
        small_font=small_font if small_font is not None else FONT_SMALL,
        top_font=top_font,
        top_row_height=top_row_height,
        font_color=font_color,
        top_segments=top_segs,
        bottom_segments=bot_segs,
    )
```

Add the helper:

```python
def _compute_preview_two_row(
    game: GameInfo,
    team_abbr: str,
    tz: ZoneInfo,
    series_wins: int,
    series_losses: int,
) -> tuple[list[tuple[str, Color]], list[tuple[str, Color]]]:
    away_c = _team_color(game.away_abbr)
    home_c = _team_color(game.home_abbr)
    top: list[tuple[str, Color]] = [
        (game.away_abbr, away_c),
        (" @ ", RGB_WHITE),
        (game.home_abbr, home_c),
    ]
    if series_wins + series_losses > 0:
        top.append((f" ({series_wins}-{series_losses})", make_color(150, 150, 150)))
    time_str = _format_game_time(game.start_time, tz) if game.start_time else "TBD"
    bot: list[tuple[str, Color]] = [(time_str, RGB_WHITE)]
    return top, bot
```

Update `_build_two_row_message` to call this for preview state:

```python
    if game.state == "preview":
        top_segs, bot_segs = _compute_preview_two_row(
            game, team_abbr, tz, series_wins, series_losses
        )
    else:
        top_segs, bot_segs = [], []
```

Update the dispatch in `update()` to pass series record:

```python
        elif self.layout == "two_row":
            stories.extend(
                _build_two_row_message(
                    g,
                    self.team,
                    tz,
                    bg_color=self.bg_color,
                    font=self.font,
                    small_font=self.small_font,
                    top_font=self.top_font,
                    top_row_height=self.top_row_height,
                    font_color=self.font_color,
                    series_wins=current.team_wins,
                    series_losses=current.team_losses,
                )
                for g in current.games
            )
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
python -m pytest tests/test_widgets/test_mlb.py::TestMLBTwoRowLayout -k "preview" -v
```

Expected: 4 PASS

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/widgets/mlb.py tests/test_widgets/test_mlb.py
git commit -m "feat: MLBTwoRowMessage preview state segments"
```

---

### Task 3: Final state segments

**Files:**
- Modify: `src/led_ticker/widgets/mlb.py`
- Test: `tests/test_widgets/test_mlb.py`

Final: top = `AWAY score HOME score` with win/loss colors; bottom = `FINAL · TEAM leads W-L`.

- [ ] **Step 1: Write failing tests**

Add inside `TestMLBTwoRowLayout`:

```python
    def test_final_top_away_wins_scores_use_win_loss_colors(self):
        """Away win: away score = WIN_COLOR, home score = LOSS_COLOR."""
        from zoneinfo import ZoneInfo
        from led_ticker.widgets.mlb import WIN_COLOR, LOSS_COLOR, _build_two_row_message

        game = GameInfo(
            away_abbr="NYM", home_abbr="PHI",
            away_score=5, home_score=3, state="final",
        )
        msg = _build_two_row_message(game, "PHI", ZoneInfo("America/New_York"))
        # top_segments: NYM, score, ..., PHI, score, ...
        texts = [t for t, _ in msg.top_segments]
        colors = [c for _, c in msg.top_segments]
        # NYM (away) won 5-3
        score_idx_away = texts.index("5")
        score_idx_home = texts.index("3")
        assert colors[score_idx_away] is WIN_COLOR
        assert colors[score_idx_home] is LOSS_COLOR

    def test_final_top_home_wins_colors_flipped(self):
        from zoneinfo import ZoneInfo
        from led_ticker.widgets.mlb import WIN_COLOR, LOSS_COLOR, _build_two_row_message

        game = GameInfo(
            away_abbr="NYM", home_abbr="PHI",
            away_score=3, home_score=8, state="final",
        )
        msg = _build_two_row_message(game, "PHI", ZoneInfo("America/New_York"))
        texts = [t for t, _ in msg.top_segments]
        colors = [c for _, c in msg.top_segments]
        score_idx_away = texts.index("3")
        score_idx_home = texts.index("8")
        assert colors[score_idx_away] is LOSS_COLOR
        assert colors[score_idx_home] is WIN_COLOR

    def test_final_bottom_has_final_text(self):
        from zoneinfo import ZoneInfo
        from led_ticker.widgets.mlb import _build_two_row_message

        game = GameInfo(
            away_abbr="NYM", home_abbr="PHI",
            away_score=5, home_score=3, state="final",
        )
        msg = _build_two_row_message(game, "PHI", ZoneInfo("America/New_York"))
        bottom_text = "".join(t for t, _ in msg.bottom_segments)
        assert "FINAL" in bottom_text

    def test_final_bottom_has_series_record_when_multi_game(self):
        from zoneinfo import ZoneInfo
        from led_ticker.widgets.mlb import _build_two_row_message

        game = GameInfo(
            away_abbr="NYM", home_abbr="PHI",
            away_score=5, home_score=3, state="final",
        )
        msg = _build_two_row_message(
            game, "PHI", ZoneInfo("America/New_York"),
            series_wins=2, series_losses=1,
        )
        bottom_text = "".join(t for t, _ in msg.bottom_segments)
        assert "leads" in bottom_text or "Tied" in bottom_text

    def test_final_bottom_omits_record_on_single_game(self):
        from zoneinfo import ZoneInfo
        from led_ticker.widgets.mlb import _build_two_row_message

        game = GameInfo(
            away_abbr="NYM", home_abbr="PHI",
            away_score=5, home_score=3, state="final",
        )
        msg = _build_two_row_message(
            game, "PHI", ZoneInfo("America/New_York"),
            series_wins=1, series_losses=0,
            series_total_games=1,
        )
        bottom_text = "".join(t for t, _ in msg.bottom_segments)
        assert "leads" not in bottom_text
        assert "FINAL" in bottom_text
```

- [ ] **Step 2: Run to confirm failure**

```bash
python -m pytest tests/test_widgets/test_mlb.py::TestMLBTwoRowLayout -k "final" -v
```

Expected: FAIL — `top_segments` is empty for final state.

- [ ] **Step 3: Add `series_total_games` param and implement final state**

Update `_build_two_row_message` signature to add `series_total_games: int = 1` and update calls in `update()` to pass `series_total_games=len(current.games)`.

Add the helper:

```python
def _compute_final_two_row(
    game: GameInfo,
    team_abbr: str,
    series_wins: int,
    series_losses: int,
    series_total_games: int,
) -> tuple[list[tuple[str, Color]], list[tuple[str, Color]]]:
    win_c = _team_palette("WIN_COLOR")
    loss_c = _team_palette("LOSS_COLOR")
    away_c = _team_color(game.away_abbr)
    home_c = _team_color(game.home_abbr)
    away_won = (game.away_score or 0) > (game.home_score or 0)
    away_score_c = win_c if away_won else loss_c
    home_score_c = loss_c if away_won else win_c

    away_score_str = str(game.away_score) if game.away_score is not None else "–"
    home_score_str = str(game.home_score) if game.home_score is not None else "–"

    top: list[tuple[str, Color]] = [
        (game.away_abbr, away_c),
        (f" {away_score_str}", away_score_c),
        ("  ", RGB_WHITE),
        (game.home_abbr, home_c),
        (f" {home_score_str}", home_score_c),
    ]

    grey = make_color(180, 180, 180)
    bot: list[tuple[str, Color]] = [("FINAL", grey)]

    if series_total_games > 1 and (series_wins + series_losses) > 0:
        bot.append((" · ", grey))
        total_decided = series_wins + series_losses
        if series_wins > series_losses:
            leader_abbr = team_abbr
        elif series_losses > series_wins:
            # find opponent abbr
            opp = game.home_abbr if game.away_abbr == team_abbr else game.away_abbr
            leader_abbr = opp
        else:
            leader_abbr = None

        if leader_abbr is None:
            bot.append((f"Tied {series_wins}-{series_losses}", RGB_WHITE))
        else:
            bot.append((leader_abbr, _team_color(leader_abbr)))
            bot.append((f" leads {series_wins}-{series_losses}", RGB_WHITE))

    return top, bot
```

Update `_build_two_row_message` to call `_compute_final_two_row` when `game.state == "final"`.

- [ ] **Step 4: Run to confirm tests pass**

```bash
python -m pytest tests/test_widgets/test_mlb.py::TestMLBTwoRowLayout -k "final" -v
```

Expected: All final tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/widgets/mlb.py tests/test_widgets/test_mlb.py
git commit -m "feat: MLBTwoRowMessage final state segments with win/loss colors and series record"
```

---

### Task 4: Live state segments

**Files:**
- Modify: `src/led_ticker/widgets/mlb.py`
- Test: `tests/test_widgets/test_mlb.py`

Live: top = `AWAY score HOME score` (white scores); bottom = `▼7 ◇◆◇ 2·1·1` with BSO colors.

- [ ] **Step 1: Write failing tests**

```python
    def test_live_top_has_team_abbrs_and_scores(self):
        from zoneinfo import ZoneInfo
        from led_ticker.widgets.mlb import _build_two_row_message

        game = GameInfo(
            away_abbr="NYM", home_abbr="PHI",
            away_score=3, home_score=5, state="live",
            inning="▼7", balls=2, strikes=1, outs=1,
        )
        msg = _build_two_row_message(game, "PHI", ZoneInfo("America/New_York"))
        texts = [t for t, _ in msg.top_segments]
        full = "".join(texts)
        assert "NYM" in full
        assert "PHI" in full
        assert "3" in full
        assert "5" in full

    def test_live_bottom_has_inning(self):
        from zoneinfo import ZoneInfo
        from led_ticker.widgets.mlb import _build_two_row_message

        game = GameInfo(
            away_abbr="NYM", home_abbr="PHI",
            away_score=3, home_score=5, state="live",
            inning="▼7", balls=2, strikes=1, outs=1,
        )
        msg = _build_two_row_message(game, "PHI", ZoneInfo("America/New_York"))
        bottom_text = "".join(t for t, _ in msg.bottom_segments)
        assert "▼7" in bottom_text or "7" in bottom_text

    def test_live_bottom_has_base_diamonds(self):
        from zoneinfo import ZoneInfo
        from led_ticker.widgets.mlb import _build_two_row_message

        game = GameInfo(
            away_abbr="NYM", home_abbr="PHI",
            away_score=3, home_score=5, state="live",
            inning="▼7", balls=2, strikes=1, outs=1,
            on_first=True, on_second=False, on_third=True,
        )
        msg = _build_two_row_message(game, "PHI", ZoneInfo("America/New_York"))
        bottom_text = "".join(t for t, _ in msg.bottom_segments)
        # 3B on, 2B empty, 1B on
        assert "◆" in bottom_text  # occupied
        assert "◇" in bottom_text  # empty

    def test_live_bottom_bso_colors(self):
        """BSO values: balls=green, strikes=yellow, outs=red.
        Use 3/2/1 so all three values are distinct — avoids dict key collision
        when strikes and outs share a value like '1'.
        """
        from zoneinfo import ZoneInfo
        from led_ticker.widgets.mlb import _build_two_row_message
        from led_ticker.colors import make_color

        game = GameInfo(
            away_abbr="NYM", home_abbr="PHI",
            away_score=3, home_score=5, state="live",
            inning="▼7", balls=3, strikes=2, outs=1,
        )
        msg = _build_two_row_message(game, "PHI", ZoneInfo("America/New_York"))
        ball_c = make_color(80, 255, 80)
        strike_c = make_color(255, 255, 80)
        out_c = make_color(255, 80, 80)
        seg_map = {t: c for t, c in msg.bottom_segments}
        assert seg_map.get("3") == ball_c    # balls
        assert seg_map.get("2") == strike_c  # strikes
        assert seg_map.get("1") == out_c     # outs
```

- [ ] **Step 2: Run to confirm failure**

```bash
python -m pytest tests/test_widgets/test_mlb.py::TestMLBTwoRowLayout -k "live" -v
```

- [ ] **Step 3: Implement live state helper**

```python
def _compute_live_two_row(
    game: GameInfo,
) -> tuple[list[tuple[str, Color]], list[tuple[str, Color]]]:
    away_c = _team_color(game.away_abbr)
    home_c = _team_color(game.home_abbr)
    away_score_str = str(game.away_score) if game.away_score is not None else "–"
    home_score_str = str(game.home_score) if game.home_score is not None else "–"

    top: list[tuple[str, Color]] = [
        (game.away_abbr, away_c),
        (f" {away_score_str}", RGB_WHITE),
        ("  ", RGB_WHITE),
        (game.home_abbr, home_c),
        (f" {home_score_str}", RGB_WHITE),
    ]

    live_c = _team_palette("LIVE_COLOR")
    ball_c = make_color(80, 255, 80)
    strike_c = make_color(255, 255, 80)
    out_c = make_color(255, 80, 80)
    occupied_c = make_color(255, 220, 50)
    empty_c = make_color(50, 50, 50)

    inning_str = game.inning or "–"
    b3 = "◆" if game.on_third else "◇"
    b2 = "◆" if game.on_second else "◇"
    b1 = "◆" if game.on_first else "◇"
    b3_c = occupied_c if game.on_third else empty_c
    b2_c = occupied_c if game.on_second else empty_c
    b1_c = occupied_c if game.on_first else empty_c

    bot: list[tuple[str, Color]] = [
        (inning_str, live_c),
        ("  ", RGB_WHITE),
        (b3, b3_c),
        (b2, b2_c),
        (b1, b1_c),
        ("  ", RGB_WHITE),
        (str(game.balls), ball_c),
        ("·", RGB_WHITE),
        (str(game.strikes), strike_c),
        ("·", RGB_WHITE),
        (str(game.outs), out_c),
    ]
    return top, bot
```

Update `_build_two_row_message` to call `_compute_live_two_row` when `game.state == "live"`.

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_widgets/test_mlb.py::TestMLBTwoRowLayout -k "live" -v
```

Expected: All live tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/widgets/mlb.py tests/test_widgets/test_mlb.py
git commit -m "feat: MLBTwoRowMessage live state segments with inning/bases/BSO"
```

---

### Task 5: Postponed state segments

**Files:**
- Modify: `src/led_ticker/widgets/mlb.py`
- Test: `tests/test_widgets/test_mlb.py`

- [ ] **Step 1: Write failing tests**

```python
    def test_postponed_top_has_matchup(self):
        from zoneinfo import ZoneInfo
        from led_ticker.widgets.mlb import _build_two_row_message, _team_color

        game = GameInfo(
            away_abbr="NYM", home_abbr="PHI", state="postponed",
            postpone_tag="PPD", postpone_reason="Rain",
        )
        msg = _build_two_row_message(game, "PHI", ZoneInfo("America/New_York"))
        texts = [t for t, _ in msg.top_segments]
        colors = [c for _, c in msg.top_segments]
        assert "NYM" in texts
        assert "PHI" in texts
        assert colors[texts.index("NYM")] == _team_color("NYM")
        assert colors[texts.index("PHI")] == _team_color("PHI")

    def test_postponed_bottom_has_tag_and_reason(self):
        from zoneinfo import ZoneInfo
        from led_ticker.widgets.mlb import _build_two_row_message

        game = GameInfo(
            away_abbr="NYM", home_abbr="PHI", state="postponed",
            postpone_tag="PPD", postpone_reason="Rain",
        )
        msg = _build_two_row_message(game, "PHI", ZoneInfo("America/New_York"))
        bottom_text = "".join(t for t, _ in msg.bottom_segments)
        assert "PPD" in bottom_text
        assert "Rain" in bottom_text

    def test_postponed_bottom_tag_only_when_no_reason(self):
        from zoneinfo import ZoneInfo
        from led_ticker.widgets.mlb import _build_two_row_message

        game = GameInfo(
            away_abbr="NYM", home_abbr="PHI", state="postponed",
            postpone_tag="CANC", postpone_reason="",
        )
        msg = _build_two_row_message(game, "PHI", ZoneInfo("America/New_York"))
        bottom_text = "".join(t for t, _ in msg.bottom_segments)
        assert "CANC" in bottom_text
```

- [ ] **Step 2: Run to confirm failure**

```bash
python -m pytest tests/test_widgets/test_mlb.py::TestMLBTwoRowLayout -k "postponed" -v
```

- [ ] **Step 3: Implement postponed helper**

```python
def _compute_postponed_two_row(
    game: GameInfo,
) -> tuple[list[tuple[str, Color]], list[tuple[str, Color]]]:
    away_c = _team_color(game.away_abbr)
    home_c = _team_color(game.home_abbr)
    top: list[tuple[str, Color]] = [
        (game.away_abbr, away_c),
        (" @ ", RGB_WHITE),
        (game.home_abbr, home_c),
    ]
    tag_color = make_color(255, 200, 60)
    if game.postpone_reason:
        tag = f"{game.postpone_tag}: {game.postpone_reason}"
    else:
        tag = game.postpone_tag
    bot: list[tuple[str, Color]] = [(tag, tag_color)]
    return top, bot
```

Update `_build_two_row_message` to dispatch `_compute_postponed_two_row` for `game.state == "postponed"`.

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_widgets/test_mlb.py::TestMLBTwoRowLayout -k "postponed" -v
```

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/widgets/mlb.py tests/test_widgets/test_mlb.py
git commit -m "feat: MLBTwoRowMessage postponed state segments"
```

---

### Task 6: ABS challenge pips

**Files:**
- Modify: `src/led_ticker/widgets/mlb.py`
- Test: `tests/test_widgets/test_mlb.py`

Pips trail each score in the top band. Orange = remaining, grey = used. Hidden when `challenges is None`.

- [ ] **Step 1: Write failing tests**

```python
    def test_pips_hidden_when_challenges_none(self):
        """No pip segments when away/home challenges are None."""
        from zoneinfo import ZoneInfo
        from led_ticker.widgets.mlb import _build_two_row_message

        game = GameInfo(
            away_abbr="NYM", home_abbr="PHI",
            away_score=5, home_score=3, state="final",
            away_challenges=None, home_challenges=None,
        )
        msg = _build_two_row_message(game, "PHI", ZoneInfo("America/New_York"))
        # No dash segments in top_segments
        top_texts = [t for t, _ in msg.top_segments]
        assert "-" not in top_texts
        assert "–" not in "".join(top_texts).replace("–", "")  # no pip dashes

    def test_pips_trailing_away_score_one_remaining(self):
        """Away has 1 challenge remaining: 1 orange dash + 1 grey dash."""
        from zoneinfo import ZoneInfo
        from led_ticker.widgets.mlb import _build_two_row_message, CHALLENGE_COLOR, CHALLENGE_USED

        game = GameInfo(
            away_abbr="NYM", home_abbr="PHI",
            away_score=5, home_score=3, state="final",
            away_challenges=1, home_challenges=2,
        )
        msg = _build_two_row_message(game, "PHI", ZoneInfo("America/New_York"))
        # Find away pip segments — they appear after the away score "5"
        # Collect all "-" segments and their colors
        pip_segs = [(t, c) for t, c in msg.top_segments if t == "-"]
        # Total: 2 away pips + 2 home pips = 4
        assert len(pip_segs) == 4
        orange_pips = [c for t, c in pip_segs if c is CHALLENGE_COLOR]
        grey_pips = [c for t, c in pip_segs if c is CHALLENGE_USED]
        # away=1 remaining → 1 orange; home=2 remaining → 2 orange; total orange=3
        assert len(orange_pips) == 3
        assert len(grey_pips) == 1

    def test_pips_all_grey_when_zero_remaining(self):
        """Both teams used all challenges: 4 grey dashes."""
        from zoneinfo import ZoneInfo
        from led_ticker.widgets.mlb import _build_two_row_message, CHALLENGE_USED

        game = GameInfo(
            away_abbr="NYM", home_abbr="PHI",
            away_score=5, home_score=3, state="final",
            away_challenges=0, home_challenges=0,
        )
        msg = _build_two_row_message(game, "PHI", ZoneInfo("America/New_York"))
        pip_segs = [(t, c) for t, c in msg.top_segments if t == "-"]
        assert len(pip_segs) == 4
        assert all(c is CHALLENGE_USED for _, c in pip_segs)
```

- [ ] **Step 2: Run to confirm failure**

```bash
python -m pytest tests/test_widgets/test_mlb.py::TestMLBTwoRowLayout -k "pip" -v
```

- [ ] **Step 3: Add pip helper**

Add a helper that returns pip segments for one team:

```python
def _pip_segments(count: int | None) -> list[tuple[str, Color]]:
    """Return 0, 1, or 2 dash segments for ABS challenge pips.

    Returns empty list when count is None (ABS not in effect).
    Orange dashes for remaining challenges, grey for used.
    """
    if count is None:
        return []
    chal_c = _team_palette("CHALLENGE_COLOR")
    used_c = _team_palette("CHALLENGE_USED")
    n = min(count, 2)
    segs = []
    for i in range(2):
        segs.append(("-", chal_c if i < n else used_c))
    return segs
```

Update `_compute_final_two_row` and `_compute_live_two_row` to insert pip segments after each score:

In `_compute_final_two_row`, after building `top`:

```python
    away_pips = _pip_segments(game.away_challenges)
    home_pips = _pip_segments(game.home_challenges)
    if away_pips:
        top[2:2] = away_pips   # insert after away score (index 1), before spacer (index 2)
    if home_pips:
        top.extend(home_pips)  # append after home score
```

Similarly in `_compute_live_two_row`.

> **Note:** The exact insertion index depends on your `top` list construction. Adjust so pips appear immediately after the score token for each team. A cleaner approach: build top as a flat list and append pips right after each score string is added.

Cleaner implementation — build top in stages:

```python
    top: list[tuple[str, Color]] = []
    top.append((game.away_abbr, away_c))
    top.append((f" {away_score_str}", away_score_c))
    top.extend(_pip_segments(game.away_challenges))
    top.append(("  ", RGB_WHITE))
    top.append((game.home_abbr, home_c))
    top.append((f" {home_score_str}", home_score_c))
    top.extend(_pip_segments(game.home_challenges))
```

Apply the same pattern in `_compute_live_two_row`'s top construction.

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_widgets/test_mlb.py::TestMLBTwoRowLayout -k "pip" -v
```

Expected: All pip tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/widgets/mlb.py tests/test_widgets/test_mlb.py
git commit -m "feat: MLBTwoRowMessage ABS challenge pips trailing each score"
```

---

### Task 7: `MLBTwoRowMessage.draw()` implementation

**Files:**
- Modify: `src/led_ticker/widgets/mlb.py` (`MLBTwoRowMessage.draw`)
- Test: `tests/test_widgets/test_mlb.py`

Replace the stub `draw()` with a real implementation that renders both segment lists to their respective bands.

- [ ] **Step 1: Write failing test**

```python
    def test_draw_returns_canvas_and_does_not_crash(self, canvas):
        """draw() completes without error and returns (canvas, cursor_pos)."""
        from zoneinfo import ZoneInfo
        from led_ticker.widgets.mlb import _build_two_row_message

        game = GameInfo(
            away_abbr="NYM", home_abbr="PHI",
            away_score=5, home_score=3, state="final",
        )
        msg = _build_two_row_message(game, "PHI", ZoneInfo("America/New_York"))
        result_canvas, cursor = msg.draw(canvas)
        assert result_canvas is canvas
        assert cursor <= canvas.width

    def test_draw_live_does_not_crash(self, canvas):
        from zoneinfo import ZoneInfo
        from led_ticker.widgets.mlb import _build_two_row_message

        game = GameInfo(
            away_abbr="NYM", home_abbr="PHI",
            away_score=3, home_score=5, state="live",
            inning="▼7", balls=2, strikes=1, outs=1,
        )
        msg = _build_two_row_message(game, "PHI", ZoneInfo("America/New_York"))
        result_canvas, cursor = msg.draw(canvas)
        assert result_canvas is canvas
```

The test uses the `canvas` fixture from `conftest.py` (already available in the test file).

- [ ] **Step 2: Run to confirm stub still passes `cursor <= canvas.width` condition (it returns `canvas.width` from stub)**

```bash
python -m pytest tests/test_widgets/test_mlb.py::TestMLBTwoRowLayout::test_draw_returns_canvas_and_does_not_crash -v
```

This may pass with the stub — that's fine. The real value of this test is confirming the draw code path doesn't crash after implementation.

- [ ] **Step 3: Implement `draw()`**

Replace the stub in `MLBTwoRowMessage.draw()`:

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
        from led_ticker.pixel_emoji import draw_with_emoji
        from led_ticker.widgets._row_layout import resolve_band_heights

        scale = safe_scale(canvas)
        top_h, bot_h = resolve_band_heights(canvas.height, self.top_row_height)
        top_font = self.top_font if self.top_font is not None else self.font
        bot_font = self.font

        top_baseline = compute_baseline_for_band(top_font, top_h, scale, valign="center")
        bot_baseline = top_h + compute_baseline_for_band(bot_font, bot_h, scale, valign="center")

        def _draw_segments(
            segments: list[tuple[str, Color]],
            baseline: int,
            font: Font,
            center: bool = True,
        ) -> None:
            if not segments:
                return
            total_w = sum(
                draw_with_emoji.__wrapped__(canvas, font, 0, 0, c, t, measure_only=True)
                if hasattr(draw_with_emoji, "__wrapped__")
                else _measure(font, t, canvas)
                for t, c in segments
            )
            x = max(0, (canvas.width - total_w) // 2) if center else 0
            for text, color in segments:
                from led_ticker.pixel_emoji import measure_width
                x += draw_with_emoji(canvas, font, x, baseline + y_offset, color, text)

        _draw_segments(self.top_segments, top_baseline, top_font)
        _draw_segments(self.bottom_segments, bot_baseline, bot_font)

        return canvas, canvas.width
```

> **Note on width measurement:** Use `measure_width` from `led_ticker.pixel_emoji` — it's the same helper used by `SegmentMessage` and `MLBScoreboardMessage`. Import at the top of the method. The `_draw_segments` helper above should call `measure_width(font, text, canvas)` for each segment's width when computing the centering offset. Here is the corrected helper:

```python
        def _draw_segments(
            segments: list[tuple[str, Color]],
            baseline: int,
            font: Font,
        ) -> None:
            if not segments:
                return
            from led_ticker.pixel_emoji import measure_width
            total_w = sum(measure_width(font, t, canvas) for t, _ in segments)
            x = max(0, (canvas.width - total_w) // 2)
            for text, color in segments:
                x += draw_with_emoji(canvas, font, x, baseline + y_offset, color, text)
```

- [ ] **Step 4: Run draw tests**

```bash
python -m pytest tests/test_widgets/test_mlb.py::TestMLBTwoRowLayout -k "draw" -v
```

Expected: PASS.

- [ ] **Step 5: Run all MLB tests**

```bash
python -m pytest tests/test_widgets/test_mlb.py -v
```

Expected: All PASS.

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/widgets/mlb.py tests/test_widgets/test_mlb.py
git commit -m "feat: MLBTwoRowMessage draw() renders two-band segments with centering"
```

---

### Task 8: `factories.py` — widen `top_font` dispatch to include `"mlb"`

**Files:**
- Modify: `src/led_ticker/app/factories.py` (line ~316–321)
- Test: `tests/test_widgets/test_mlb.py`

- [ ] **Step 1: Write failing test**

Add to `TestMLBTwoRowLayout`:

```python
    def test_top_font_threads_through_from_monitor(self):
        """top_font set on MLBScoreMonitor reaches MLBTwoRowMessage instances."""
        from unittest import mock
        from led_ticker.fonts import FONT_DEFAULT
        m = MLBScoreMonitor(
            session=mock.Mock(), team="PHI",
            layout="two_row", top_font=FONT_DEFAULT,
        )
        assert m.top_font is FONT_DEFAULT

    def test_top_row_height_threads_through_to_message(self):
        """top_row_height on MLBScoreMonitor threads to MLBTwoRowMessage."""
        from zoneinfo import ZoneInfo
        from led_ticker.widgets.mlb import _build_two_row_message

        game = GameInfo(
            away_abbr="NYM", home_abbr="PHI",
            away_score=5, home_score=3, state="final",
        )
        msg = _build_two_row_message(
            game, "PHI", ZoneInfo("America/New_York"), top_row_height=4
        )
        assert msg.top_row_height == 4
```

Also add a factories integration test in `tests/test_validate.py` or a new section:

```python
@pytest.mark.asyncio
async def test_mlb_top_font_size_accepted_by_factories():
    """top_font_size passes through _DISPATCH_APPLICABLE_TYPES for mlb."""
    from led_ticker.app.factories import validate_widget_cfg
    cfg = {
        "type": "mlb",
        "team": "PHI",
        "layout": "two_row",
        "top_font_size": 16,
        "font_size": 32,
    }
    # Should not raise
    await validate_widget_cfg(cfg, session=None)
```

- [ ] **Step 2: Run to confirm failure**

```bash
python -m pytest tests/test_validate.py::test_mlb_top_font_size_accepted_by_factories -v
```

Expected: FAIL — `top_font_size` raises "not applicable to type mlb".

- [ ] **Step 3: Widen `_DISPATCH_APPLICABLE_TYPES` in `factories.py`**

At line ~316–321, change:

```python
    "top_font": {"two_row", "pool"},
    "top_font_size": {"two_row", "pool"},
    "top_font_threshold": {"two_row", "pool"},
    "bottom_font": {"two_row", "pool"},
    "bottom_font_size": {"two_row", "pool"},
    "bottom_font_threshold": {"two_row", "pool"},
```

to:

```python
    "top_font": {"two_row", "pool", "mlb"},
    "top_font_size": {"two_row", "pool", "mlb"},
    "top_font_threshold": {"two_row", "pool", "mlb"},
    "bottom_font": {"two_row", "pool"},
    "bottom_font_size": {"two_row", "pool"},
    "bottom_font_threshold": {"two_row", "pool"},
```

(`bottom_font` is NOT widened to `"mlb"` — the spec does not include a separate bottom band font for the MLB widget.)

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_validate.py::test_mlb_top_font_size_accepted_by_factories tests/test_widgets/test_mlb.py::TestMLBTwoRowLayout::test_top_font_threads_through_from_monitor -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/app/factories.py tests/test_validate.py tests/test_widgets/test_mlb.py
git commit -m "feat: widen factories top_font dispatch to include mlb widget"
```

---

### Task 9: Validation — layout enum + dead-knob checks

**Files:**
- Modify: `src/led_ticker/app/factories.py` (`validate_widget_cfg`)
- Test: `tests/test_validate.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_validate.py`:

```python
@pytest.mark.asyncio
async def test_mlb_layout_unknown_raises_with_did_you_mean():
    from led_ticker.app.factories import validate_widget_cfg
    cfg = {"type": "mlb", "team": "PHI", "layout": "two_rows"}  # typo
    with pytest.raises(ValueError, match="two_row"):
        await validate_widget_cfg(cfg, session=None)


@pytest.mark.asyncio
async def test_mlb_layout_scoreboard_accepted():
    from led_ticker.app.factories import validate_widget_cfg
    cfg = {"type": "mlb", "team": "PHI", "layout": "scoreboard"}
    await validate_widget_cfg(cfg, session=None)  # no raise


@pytest.mark.asyncio
async def test_mlb_top_font_size_under_ticker_raises():
    from led_ticker.app.factories import validate_widget_cfg
    cfg = {
        "type": "mlb", "team": "PHI",
        "layout": "ticker",
        "top_font_size": 16,
        "font_size": 32,
    }
    with pytest.raises((ValueError, Exception), match="two_row"):
        await validate_widget_cfg(cfg, session=None)


@pytest.mark.asyncio
async def test_mlb_top_row_height_under_scoreboard_raises():
    from led_ticker.app.factories import validate_widget_cfg
    cfg = {
        "type": "mlb", "team": "PHI",
        "layout": "scoreboard",
        "top_row_height": 4,
        "font_size": 32,
        "small_font_size": 20,
    }
    with pytest.raises((ValueError, Exception), match="two_row"):
        await validate_widget_cfg(cfg, session=None)
```

- [ ] **Step 2: Run to confirm failure**

```bash
python -m pytest tests/test_validate.py -k "mlb_layout" -v
```

Expected: FAIL.

- [ ] **Step 3: Add MLB layout validation in `validate_widget_cfg`**

In `src/led_ticker/app/factories.py`, inside `validate_widget_cfg`, after the existing migration checks, add:

```python
    # MLB layout validation
    if widget_cfg.get("type") == "mlb":
        import difflib
        _MLB_VALID_LAYOUTS = ("ticker", "scoreboard", "two_row")
        mlb_layout = widget_cfg.get("layout", "ticker")
        if mlb_layout not in _MLB_VALID_LAYOUTS:
            close = difflib.get_close_matches(mlb_layout, _MLB_VALID_LAYOUTS, n=1, cutoff=0.5)
            suggestion = f" Did you mean {close[0]!r}?" if close else ""
            raise ValueError(
                f"mlb layout={mlb_layout!r} is not valid. "
                f"Choose one of: {', '.join(repr(v) for v in _MLB_VALID_LAYOUTS)}.{suggestion}"
            )
        # Dead-knob check: per-row knobs only valid under two_row
        if mlb_layout != "two_row":
            _TWO_ROW_ONLY = ("top_font", "top_font_size", "top_font_threshold", "top_row_height")
            dead = [k for k in _TWO_ROW_ONLY if k in widget_cfg]
            if dead:
                raise ValueError(
                    f"{dead[0]!r} only applies when layout='two_row'; "
                    f"remove the field or set layout='two_row'."
                )
```

- [ ] **Step 4: Run validation tests**

```bash
python -m pytest tests/test_validate.py -k "mlb_layout or mlb_top_font or mlb_top_row" -v
```

Expected: All PASS.

- [ ] **Step 5: Run full suite**

```bash
python -m pytest tests/ -x -q
```

Expected: All pass, no regressions.

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/app/factories.py tests/test_validate.py
git commit -m "feat: mlb layout enum validation + dead-knob check for two_row-only fields"
```

---

### Task 10: Config update, CLAUDE.md, and spec commit

**Files:**
- Modify: `config/config.mlb_bigsign_test.toml`
- Modify: `CLAUDE.md`
- Add: `docs/superpowers/specs/2026-05-28-mlb-two-row-layout-design.md` (commit the spec written during brainstorming — it exists on disk but is untracked)

- [ ] **Step 1: Add a two_row section to the bigsign smoketest config**

In `config/config.mlb_bigsign_test.toml`, add after the existing scoreboard section:

```toml
# --- MLB Scores (two_row layout) ---

[[playlist.section]]
mode = "swap"
transition = "baseball_alternating"
transition_duration = 3.2
transition_fps = 40
hold_time = 8
loop_count = 0

[playlist.section.title]
type = "message"
text = ":baseball: MLB Two-Row :baseball:"
font = "Inter-Regular"
font_size = 32
font_threshold = 80
font_color = "random"

[[playlist.section.widget]]
type = "mlb"
team = "PHI"
layout = "two_row"
timezone = "America/New_York"
font = "Inter-Regular"
font_size = 32
font_threshold = 80

[[playlist.section.widget]]
type = "mlb"
team = "NYM"
layout = "two_row"
timezone = "America/New_York"
font = "Inter-Regular"
font_size = 32
font_threshold = 80

[[playlist.section.widget]]
type = "mlb"
team = "LAD"
layout = "two_row"
timezone = "America/Los_Angeles"
font = "Inter-Regular"
font_size = 32
font_threshold = 80
```

- [ ] **Step 2: Validate the config**

```bash
make validate CONFIG=config/config.mlb_bigsign_test.toml
```

Expected: `No issues found.`

- [ ] **Step 3: Add CLAUDE.md invariant**

In `CLAUDE.md`, find the `mlb.py` entry under the package layout and update it to note `MLBTwoRowMessage`:

Find:
```
    mlb.py              # Team logos render through pixel_emoji's standard 8x8 path
                        #   (the previous mlb_icons.py was folded in and deleted).
```

Add a line:
```
                        #   layout = "ticker" | "scoreboard" | "two_row"; two_row uses
                        #   MLBTwoRowMessage (custom draw, two-band, multi-color segments).
```

- [ ] **Step 4: Run full test suite**

```bash
make test
```

Expected: All tests pass, coverage ≥ 90%.

- [ ] **Step 5: Commit everything**

```bash
git add config/config.mlb_bigsign_test.toml CLAUDE.md docs/superpowers/specs/2026-05-28-mlb-two-row-layout-design.md
git commit -m "docs: add mlb two_row spec, update bigsign smoketest config and CLAUDE.md"
```

- [ ] **Step 6: Run lint**

```bash
make lint
```

Expected: No errors.
