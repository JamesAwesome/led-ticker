# MLB Scoreboard Small-Font Hires Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the hardcoded `FONT_SMALL` (5×8 BDF) in `MLBScoreboardMessage.draw()` with a configurable `small_font` field, so bigsign users can pass a `HiresFont` for the inning, outs, ball/strike count, and diamond bases zones.

**Architecture:** Add `small_font: Font` to `MLBScoreboardMessage` and `MLBScoreMonitor`. Thread it through `_build_scoreboard_message()`. Update `factories._resolve_fonts()` to coerce the new `small_font` / `small_font_size` / `small_font_threshold` TOML keys. The rendering helpers (`draw_with_emoji`, `measure_width`, `compute_baseline_for_band`) already dispatch on font type — no changes needed there.

**Tech Stack:** Python 3.13, attrs, pytest, `src/led_ticker/widgets/mlb.py`, `src/led_ticker/app/factories.py`

---

## Files

- **Modify:** `src/led_ticker/widgets/mlb.py`
  - Add `FONT_SMALL` to module-level imports
  - Add `small_font: Font` field to `MLBScoreboardMessage`
  - Replace every `FONT_SMALL` reference in `draw()` with `self.small_font`
  - Add `small_font` param to `_build_scoreboard_message()`
  - Add `small_font: Font` field to `MLBScoreMonitor`; thread through `update()`
- **Modify:** `src/led_ticker/app/factories.py`
  - Add `"small_font"` to the prefix loop in `_resolve_fonts()`
  - Add `FIELD_HINTS` entries for `small_font`, `small_font_size`, `small_font_threshold`
- **Test:** `tests/test_mlb_scoreboard.py` (append to existing file)

---

## Task 1: `small_font` field exists and defaults to `FONT_SMALL`

**Files:**
- Test: `tests/test_mlb_scoreboard.py`
- Modify: `src/led_ticker/widgets/mlb.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_mlb_scoreboard.py`:

```python
# ---------------------------------------------------------------------------
# small_font field
# ---------------------------------------------------------------------------


def test_scoreboard_small_font_defaults_to_font_small():
    """small_font attr exists and defaults to FONT_SMALL."""
    from led_ticker.fonts import FONT_SMALL

    msg = MLBScoreboardMessage(game=_live_game(), team_abbr="PHI")
    assert msg.small_font is FONT_SMALL


def test_scoreboard_small_font_accepted_as_kwarg():
    """small_font can be overridden at construction time."""
    from led_ticker.fonts import FONT_DEFAULT

    msg = MLBScoreboardMessage(
        game=_live_game(), team_abbr="PHI", small_font=FONT_DEFAULT
    )
    assert msg.small_font is FONT_DEFAULT


def test_build_scoreboard_message_threads_small_font():
    """_build_scoreboard_message passes small_font into the built object."""
    from zoneinfo import ZoneInfo

    from led_ticker.fonts import FONT_DEFAULT
    from led_ticker.widgets.mlb import _build_scoreboard_message

    game = _live_game()
    msg = _build_scoreboard_message(
        game,
        team_abbr="PHI",
        tz=ZoneInfo("America/New_York"),
        small_font=FONT_DEFAULT,
    )
    assert msg.small_font is FONT_DEFAULT
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_mlb_scoreboard.py::test_scoreboard_small_font_defaults_to_font_small tests/test_mlb_scoreboard.py::test_scoreboard_small_font_accepted_as_kwarg tests/test_mlb_scoreboard.py::test_build_scoreboard_message_threads_small_font -v
```

Expected: all three FAIL with `AttributeError: 'MLBScoreboardMessage' object has no attribute 'small_font'` (or similar).

- [ ] **Step 3: Add `FONT_SMALL` module-level import and `small_font` field**

In `src/led_ticker/widgets/mlb.py`, change the font import at the top (currently line 20):

```python
from led_ticker.fonts import FONT_DEFAULT
```

to:

```python
from led_ticker.fonts import FONT_DEFAULT, FONT_SMALL
```

Then in the `MLBScoreboardMessage` class (currently lines 548–549), add `small_font` right after `font`:

```python
    font: Font = attrs.field(default=FONT_DEFAULT, kw_only=True)
    small_font: Font = attrs.field(default=FONT_SMALL, kw_only=True)
```

Then update `_build_scoreboard_message()` (currently around line 515) to accept and pass the new field:

```python
def _build_scoreboard_message(
    game: GameInfo,
    team_abbr: str,
    tz: ZoneInfo,
    bg_color: Color | None = None,
    font: Font | None = None,
    small_font: Font | None = None,
    font_color: Color | ColorProvider | None = None,
) -> MLBScoreboardMessage:
    """Build a scoreboard-layout message for a single game."""
    return MLBScoreboardMessage(
        game=game,
        team_abbr=team_abbr,
        tz=tz,
        bg_color=bg_color,
        font=font if font is not None else FONT_DEFAULT,
        small_font=small_font if small_font is not None else FONT_SMALL,
        font_color=font_color,
    )
```

Note: the `from led_ticker.fonts import FONT_DEFAULT as _FONT_DEFAULT` local import inside `_build_scoreboard_message` can now be removed since both constants are available at module level.

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_mlb_scoreboard.py::test_scoreboard_small_font_defaults_to_font_small tests/test_mlb_scoreboard.py::test_scoreboard_small_font_accepted_as_kwarg tests/test_mlb_scoreboard.py::test_build_scoreboard_message_threads_small_font -v
```

Expected: all three PASS.

- [ ] **Step 5: Run full test suite to confirm no regressions**

```bash
make test
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/widgets/mlb.py tests/test_mlb_scoreboard.py
git commit -m "feat: add small_font field to MLBScoreboardMessage (defaults to FONT_SMALL)"
```

---

## Task 2: `draw()` uses `self.small_font` instead of hardcoded `FONT_SMALL`

**Files:**
- Test: `tests/test_mlb_scoreboard.py`
- Modify: `src/led_ticker/widgets/mlb.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_mlb_scoreboard.py`:

```python
def test_scoreboard_draw_uses_self_small_font_not_hardcoded():
    """Center zone draws must route through self.small_font, not FONT_SMALL.

    Strategy: pass FONT_DEFAULT as small_font (a different object than FONT_SMALL),
    then spy on draw_with_emoji and measure_width calls to verify FONT_SMALL is
    never passed when a custom small_font is set.
    """
    from unittest.mock import call, patch

    from led_ticker.fonts import FONT_DEFAULT, FONT_SMALL

    canvas = _stub_canvas()
    game = GameInfo(
        home_abbr="PHI",
        away_abbr="NYM",
        state="live",
        home_score=5,
        away_score=3,
        inning="▲7",
        outs=2,
        balls=1,
        strikes=2,
        on_first=True,
        on_second=False,
        on_third=False,
    )
    msg = MLBScoreboardMessage(game=game, team_abbr="PHI", small_font=FONT_DEFAULT)

    fonts_drawn = []
    original_dwe = __import__(
        "led_ticker.pixel_emoji", fromlist=["draw_with_emoji"]
    ).draw_with_emoji

    def _spy_dwe(canvas, font, *args, **kwargs):
        fonts_drawn.append(font)
        return original_dwe(canvas, font, *args, **kwargs)

    with patch("led_ticker.pixel_emoji.draw_with_emoji", side_effect=_spy_dwe):
        msg.draw(canvas)

    assert FONT_DEFAULT in fonts_drawn, "small_font (FONT_DEFAULT) was never used"
    assert FONT_SMALL not in fonts_drawn, "hardcoded FONT_SMALL is still being used"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_mlb_scoreboard.py::test_scoreboard_draw_uses_self_small_font_not_hardcoded -v
```

Expected: FAIL — `FONT_SMALL not in fonts_drawn` assertion fires because `draw()` still has the hardcoded `FONT_SMALL`.

- [ ] **Step 3: Replace all `FONT_SMALL` references in `draw()`**

In `src/led_ticker/widgets/mlb.py`, inside `MLBScoreboardMessage.draw()`:

**3a.** Remove the local import (it's now at module level):
```python
# DELETE this line inside draw():
from led_ticker.fonts import FONT_SMALL
```

**3b.** Replace every occurrence of `FONT_SMALL` with `self.small_font`. There are 8 sites. Search for `FONT_SMALL` inside `draw()` and replace all:

- `compute_baseline_for_band(FONT_SMALL, ...)` (×2) → `compute_baseline_for_band(self.small_font, ...)`
- `measure_width(FONT_SMALL, ...)` (×3) → `measure_width(self.small_font, ...)`
- `draw_with_emoji(canvas, FONT_SMALL, ...)` (×2 direct + the closure `_draw_small`) → `draw_with_emoji(canvas, self.small_font, ...)`

The affected closures/helpers inside `draw()`:

```python
# _draw_pips: challenge pip measurement
pip_w = measure_width(self.small_font, "●", canvas)
# ...
draw_with_emoji(
    canvas,
    self.small_font,
    pip_x + i * (pip_w + 1),
    y=y + y_offset,
    color=color,
    text="●",
)

# Center zone baselines
small_top = compute_baseline_for_band(
    self.small_font, half_h, scale, valign="center"
)
small_bottom = half_h + compute_baseline_for_band(
    self.small_font, half_h, scale, valign="center"
)

# _draw_small closure
def _draw_small(text: str, x: int, y: int, color: Color) -> None:
    draw_with_emoji(
        canvas, self.small_font, x, y=y + y_offset, color=color, text=text
    )

# Inline measure_width calls that remain outside _draw_small
inning_w = measure_width(self.small_font, inning_str, canvas)
# ...
char_w = measure_width(self.small_font, b2, canvas)
b1_w = measure_width(self.small_font, b1, canvas)
# ...
b_w = measure_width(self.small_font, str(game.balls), canvas)
bs_w = b_w + measure_width(self.small_font, "B ", canvas)
s_w = measure_width(self.small_font, str(game.strikes), canvas)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_mlb_scoreboard.py::test_scoreboard_draw_uses_self_small_font_not_hardcoded -v
```

Expected: PASS.

- [ ] **Step 5: Run the full scoreboard test file and full suite**

```bash
pytest tests/test_mlb_scoreboard.py -v
make test
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/widgets/mlb.py tests/test_mlb_scoreboard.py
git commit -m "fix: use self.small_font in MLBScoreboardMessage.draw() — removes hardcoded FONT_SMALL"
```

---

## Task 3: `MLBScoreMonitor` exposes and threads `small_font`

**Files:**
- Test: `tests/test_mlb_scoreboard.py`
- Modify: `src/led_ticker/widgets/mlb.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_mlb_scoreboard.py`:

```python
def test_monitor_small_font_defaults_to_font_small():
    """MLBScoreMonitor.small_font defaults to FONT_SMALL."""
    import unittest.mock as mock

    from led_ticker.fonts import FONT_SMALL

    session = mock.MagicMock()
    monitor = MLBScoreMonitor(session=session, team="PHI")
    assert monitor.small_font is FONT_SMALL


def test_monitor_threads_small_font_to_scoreboard_messages():
    """When layout=scoreboard, update() passes small_font to each built message."""
    import asyncio
    import unittest.mock as mock
    from datetime import UTC, datetime
    from zoneinfo import ZoneInfo

    from led_ticker.fonts import FONT_DEFAULT, FONT_SMALL

    session = mock.MagicMock()
    monitor = MLBScoreMonitor(
        session=session,
        team="PHI",
        layout="scoreboard",
        small_font=FONT_DEFAULT,
    )
    monitor._tz = ZoneInfo("America/New_York")
    monitor._team_id = 143  # PHI team id — skip resolve step

    schedule = {
        "dates": [
            {
                "games": [
                    {
                        "gamePk": 1,
                        "gameDate": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "gameType": "R",
                        "status": {
                            "abstractGameState": "Live",
                            "detailedState": "In Progress",
                        },
                        "teams": {
                            "home": {"team": {"abbreviation": "PHI"}, "score": 3},
                            "away": {"team": {"abbreviation": "NYM"}, "score": 1},
                        },
                        "linescore": {
                            "currentInning": 4,
                            "inningHalf": "top",
                            "balls": 0,
                            "strikes": 0,
                            "outs": 0,
                            "offense": {},
                        },
                    }
                ]
            }
        ]
    }

    async def _fake_get(*args, **kwargs):
        resp = mock.AsyncMock()
        resp.json.return_value = schedule
        return resp

    session.get.return_value.__aenter__ = _fake_get
    session.get.return_value.__aexit__ = mock.AsyncMock(return_value=False)

    asyncio.get_event_loop().run_until_complete(monitor.update())

    scoreboard_stories = [
        s for s in monitor.feed_stories if isinstance(s, MLBScoreboardMessage)
    ]
    assert scoreboard_stories, "no MLBScoreboardMessage in feed_stories"
    for story in scoreboard_stories:
        assert story.small_font is FONT_DEFAULT, (
            f"story.small_font is {story.small_font!r}, expected FONT_DEFAULT"
        )
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_mlb_scoreboard.py::test_monitor_small_font_defaults_to_font_small tests/test_mlb_scoreboard.py::test_monitor_threads_small_font_to_scoreboard_messages -v
```

Expected: both FAIL — `MLBScoreMonitor` has no `small_font` attribute yet.

- [ ] **Step 3: Add `small_font` to `MLBScoreMonitor` and thread through `update()`**

In `src/led_ticker/widgets/mlb.py`, inside `MLBScoreMonitor` (currently around line 768), add `small_font` after `font`:

```python
    font: Font = attrs.field(default=FONT_DEFAULT, kw_only=True)
    small_font: Font = attrs.field(default=FONT_SMALL, kw_only=True)
```

In `MLBScoreMonitor.update()`, the stories block currently reads:

```python
        _build_msg = (
            _build_scoreboard_message
            if self.layout == "scoreboard"
            else _build_game_message
        )
        stories: list[TickerMessage | MLBGameMessage | MLBScoreboardMessage] = [
            series_title
        ]
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

Replace with (note: `_build_game_message` doesn't take `small_font`, so inline the dispatch instead of sharing a single `_build_msg` variable):

```python
        stories: list[TickerMessage | MLBGameMessage | MLBScoreboardMessage] = [
            series_title
        ]
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

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_mlb_scoreboard.py::test_monitor_small_font_defaults_to_font_small tests/test_mlb_scoreboard.py::test_monitor_threads_small_font_to_scoreboard_messages -v
```

Expected: both PASS.

- [ ] **Step 5: Run full suite**

```bash
make test
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/widgets/mlb.py tests/test_mlb_scoreboard.py
git commit -m "feat: MLBScoreMonitor.small_font field threads to scoreboard messages"
```

---

## Task 4: TOML coercion — `small_font` / `small_font_size` / `small_font_threshold`

**Files:**
- Test: `tests/test_factories.py` (or whatever the factories test file is called — check with `find tests -name "test_factor*"`)
- Modify: `src/led_ticker/app/factories.py`

- [ ] **Step 1: Find the factories test file**

```bash
find tests -name "test_factor*" -o -name "test_coer*" | head -5
```

Use whatever file surfaces. If none exists, create `tests/test_factories_small_font.py`.

- [ ] **Step 2: Write the failing tests**

Add to the factories test file (or the new file):

```python
def test_resolve_fonts_coerces_small_font_bdf():
    """small_font = '5x8' resolves to the FONT_SMALL BDF object."""
    from led_ticker.app.factories import _resolve_fonts
    from led_ticker.fonts import FONT_SMALL

    cfg = {"small_font": "5x8"}
    _resolve_fonts(cfg, cls=None, panel_h_for_warning=None)
    assert cfg["small_font"] is FONT_SMALL


def test_resolve_fonts_small_font_hires_requires_size():
    """small_font with a hires name and no small_font_size raises ValueError."""
    import pytest
    from led_ticker.app.factories import _resolve_fonts
    from led_ticker.fonts import list_available_hires_fonts

    hires_names = list_available_hires_fonts()
    if not hires_names:
        pytest.skip("no hires fonts available in test environment")

    cfg = {"small_font": hires_names[0]}  # no small_font_size
    with pytest.raises(ValueError, match="small_font_size"):
        _resolve_fonts(cfg, cls=None, panel_h_for_warning=None)


def test_validate_widget_cfg_accepts_small_font_for_mlb():
    """validate_widget_cfg recognises small_font as a valid mlb field."""
    from led_ticker.app.factories import validate_widget_cfg

    # Should not raise — small_font is a recognised field on MLBScoreMonitor
    validate_widget_cfg(
        {
            "type": "mlb",
            "team": "PHI",
            "small_font": "5x8",
        }
    )
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
pytest <test_file>::test_resolve_fonts_coerces_small_font_bdf <test_file>::test_resolve_fonts_small_font_hires_requires_size <test_file>::test_validate_widget_cfg_accepts_small_font_for_mlb -v
```

Expected: first two fail (key not coerced / not popped), third may already pass if `_validate_cfg_fields` allows unknown keys to pass through — confirm either way.

- [ ] **Step 4: Add `small_font` prefix to `_resolve_fonts`**

In `src/led_ticker/app/factories.py`, inside `_resolve_fonts()`, find the loop over `top_font` / `bottom_font` (currently around line 407):

```python
    for prefix in ("top_font", "bottom_font"):
        row_name = widget_cfg.pop(prefix, None)
        row_size = widget_cfg.pop(f"{prefix}_size", None)
        row_threshold = widget_cfg.pop(f"{prefix}_threshold", None)
        if row_name is not None:
            if _is_hires_font_name(row_name) and row_size is None:
                raise ValueError(
                    f"HiresFont {row_name!r} requires {prefix}_size "
                    f"(real pixels). e.g. {prefix}_size = 22 for "
                    f"bigsign two-row layouts."
                )
            widget_cfg[prefix] = resolve_font(
                row_name, row_size, threshold=row_threshold
            )
```

Change the loop header to include `small_font`:

```python
    for prefix in ("top_font", "bottom_font", "small_font"):
```

(No other changes needed — the error message template `f"requires {prefix}_size"` is accurate for `small_font` too.)

- [ ] **Step 5: Add `FIELD_HINTS` entries**

In `src/led_ticker/app/factories.py`, in the `FIELD_HINTS` dict (currently around line 55), add after the existing `font_threshold` entry:

```python
    "small_font": FieldHint(
        "font name",
        "secondary font for scoreboard center zone (inning, outs, BSO, bases); BDF alias or hi-res font name",
        "5x8 (FONT_SMALL)",
    ),
    "small_font_size": FieldHint(
        "int (pixels)",
        "text height for small_font in real pixels; required when small_font is a hi-res font",
        "none",
    ),
    "small_font_threshold": FieldHint(
        "int 0–255",
        "bitmask threshold for small_font hi-res rendering",
        "128",
    ),
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
pytest <test_file>::test_resolve_fonts_coerces_small_font_bdf <test_file>::test_resolve_fonts_small_font_hires_requires_size <test_file>::test_validate_widget_cfg_accepts_small_font_for_mlb -v
```

Expected: all PASS.

- [ ] **Step 7: Run full suite**

```bash
make test
```

Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add src/led_ticker/app/factories.py <test_file>
git commit -m "feat: coerce small_font/small_font_size/small_font_threshold TOML keys for mlb scoreboard"
```

---

## Self-Review

### Spec coverage

| Requirement | Task |
|---|---|
| `small_font` field on `MLBScoreboardMessage` defaulting to `FONT_SMALL` | Task 1 |
| `draw()` center zone (inning, outs, B/S count, challenge pips, diamond bases) uses `self.small_font` | Task 2 |
| `_build_scoreboard_message()` threads `small_font` | Task 1 step 3 |
| `MLBScoreMonitor.small_font` field | Task 3 |
| `update()` passes `small_font` to scoreboard messages only (not game messages) | Task 3 |
| TOML `small_font = "FontName"` + `small_font_size = N` coercion | Task 4 |
| `--list-fields mlb` shows `small_font` | Task 4 step 5 (FIELD_HINTS) |

### Placeholder scan

None found. All steps include code, commands, and expected output.

### Type consistency

- `small_font: Font` — `Font` is the existing type alias used for the `font` field. `HiresFont` is a valid `Font` value at runtime (the type alias is broad enough; see existing `font: Font = FONT_DEFAULT` usage).
- `_build_scoreboard_message(small_font: Font | None = None)` — matches `MLBScoreboardMessage.small_font: Font` after the `None`-guard assigns `FONT_SMALL`.
- `MLBScoreMonitor.small_font: Font` — same alias, threaded as-is to `_build_scoreboard_message`.
- `_resolve_fonts` loop — `widget_cfg[prefix]` is set to a resolved `Font | HiresFont`; attrs accepts both for the `small_font` field.
