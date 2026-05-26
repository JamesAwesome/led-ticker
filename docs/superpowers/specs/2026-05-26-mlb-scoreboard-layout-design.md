# MLB Scoreboard Layout Design

## Goal

Add a `layout = "scoreboard"` mode to the `mlb` widget that renders a two-column scoreboard
(teams + scores flanking game state) instead of the existing left-to-right ticker line.
The ticker layout remains the default and is unchanged.

---

## Background

The existing `MLBGameMessage` renders everything on a single horizontal line:
`PHI 5 NYM 3 ▲7 ◇◆◆ 1·2·1`. With hires fonts at scale=4 (longboi: 128×16 logical px)
this already works — `draw_with_emoji` and `compute_baseline` both handle `HiresFont`
transparently. The scoreboard layout gives that same canvas a richer visual structure.

---

## Config

```toml
[[playlist.section.widget]]
type = "mlb"
team = "PHI"
layout = "scoreboard"   # "ticker" (default) | "scoreboard"
font = "Inter-Regular"
font_size = 16
font_threshold = 80
```

`layout` defaults to `"ticker"`, preserving all existing behaviour. No other config
fields change.

`MLBScoreMonitor` gains one new attrs field:

```python
layout: str = attrs.field(default="ticker", kw_only=True)  # "ticker" | "scoreboard"
```

---

## Data Model

Two new optional fields on `GameInfo`:

```python
home_challenges: int | None = None  # None = ABS not in effect or data unavailable
away_challenges: int | None = None
```

Semantics:
- `None` — ABS challenge row is hidden entirely (backwards-compatible default)
- `0` — all challenges used; render dim dots
- `1` or `2` — remaining challenges; render that many filled amber dots

The existing `&hydrate=team,linescore` API call is extended to fetch challenge data.
The exact field path in the response must be confirmed against a live game response
during implementation (check `game.challenges` or `linescore.challenges` in the
MLB Stats API v1 live feed). If the field is absent, leave both values as `None`.

---

## New Class: `MLBScoreboardMessage`

Lives in `src/led_ticker/widgets/mlb.py` alongside `MLBGameMessage`.

Inherits `_FrameAware` (same as `MLBGameMessage`) so `advance_frame(*, visit_id=...)` is
covered by the mixin — do not hand-roll it.

### Constructor

```python
@attrs.define
class MLBScoreboardMessage:
    game: GameInfo
    team_abbr: str          # the team being tracked (determines home/away orientation)
    font: Font
    bg_color: Color | None = None
    font_color: Color | ColorProvider | None = None
```

`team_abbr` is used to determine which team is "ours" for color highlighting. Layout is
always away (left) vs home (right) per standard baseball convention, same as the ticker.

### Layout Zones (128px logical width, 16px logical height)

```
┌─────────────┬──────────────────┬──────────────┬─────────────┐
│  away team  │  inning / B·S    │   diamond    │  home team  │
│  score      │  outs            │              │  score      │
│  (ABS pips) │                  │              │  (ABS pips) │
└─────────────┴──────────────────┴──────────────┴─────────────┘
  ~30%              ~20%              ~20%           ~30%
```

Zone widths are approximate; implementation should measure the font and adjust so the
team columns are equal width and the center content is centred.

**Team columns (left and right):**
- Row 1: team abbreviation in team color, with ABS challenge pips as superscript
  (small amber-colored dots immediately to the right of the abbreviation)
- Row 2: score in team win/loss color (final) or white (live/preview)
- ABS pips: filled amber `●` for remaining, dim `●` for used, row hidden if `None`

**Center-left zone (rows 1–2):**
- Row 1: inning string (`▲7`) + outs as colored dots (red filled = recorded, dim = remaining)
- Row 2: ball count (blue) + `B` + space + strike count (yellow) + `S`

**Center-right zone (rows 1–2):**
- True baseball diamond rendered across both rows:
  - Row 1, center cell: 2B (◆ if occupied, ◇ if empty)
  - Row 2, left cell: 3B; right cell: 1B

Center content uses a smaller font — approximately half the primary font size. For hires
fonts, use the next smaller registered size in the font registry. For BDF fonts, use the
next smaller BDF size available. If no smaller size is available, use the primary font
and accept the overflow gracefully (clip to canvas).

### Game States

| State | Left/right columns | Center |
|---|---|---|
| `live` | team abbr + score + ABS pips | inning, outs, B·S, diamond |
| `final` | team abbr + score (win/loss color) + pips hidden | `F` top, `FINAL` bottom |
| `preview` | team abbr + `–` (no score) | start time top, timezone bottom |
| `postponed` | team abbr + `–` | PPD tag (amber), reason if available |
| `off_day` | left column: tracked team abbr + `OFF`; right column: empty (no opponent) | `–` |

### `draw()` Signature

```python
def draw(
    self,
    canvas: Canvas,
    cursor_pos: int = 0,
    *,
    y_offset: int = 0,
    font_color: Any = None,
) -> DrawResult:
```

Returns `(canvas, cursor_pos + canvas.width)` — same contract as `MLBGameMessage`.
`cursor_pos` is accepted but the scoreboard always fills the full canvas width; it does
not scroll.

---

## Factory Change

`_build_game_message` is the existing factory function. Add a parallel factory:

```python
def _build_scoreboard_message(
    game: GameInfo,
    team_abbr: str,
    tz: ZoneInfo,
    bg_color: Color | None = None,
    font: Font | None = None,
    font_color: Color | ColorProvider | None = None,
) -> MLBScoreboardMessage:
```

In `MLBScoreMonitor._build_feed` (and equivalent update paths), branch on `self.layout`:
- `"ticker"` → existing `_build_game_message` path (unchanged)
- `"scoreboard"` → `_build_scoreboard_message`

`feed_title` and `feed_stories` types expand to include `MLBScoreboardMessage`:

```python
feed_title: TickerMessage | MLBGameMessage | MLBScoreboardMessage | None
feed_stories: list[TickerMessage | MLBGameMessage | MLBScoreboardMessage]
```

---

## ABS Challenge Pips — Rendering Detail

Rendered as small Unicode filled circles `●` (U+25CF) and dim circles `●` using a
reduced-brightness color:

```python
CHALLENGE_COLOR = make_color(255, 180, 0)   # amber
CHALLENGE_USED  = make_color(60, 40, 0)     # dim amber
```

Maximum 2 pips per team (standard MLB ABS rules). If the API returns a value greater
than 2, clamp to 2 — do not break layout.

---

## Testing

New tests in `tests/test_mlb_scoreboard.py`:

1. `test_scoreboard_draw_live` — `draw()` on a `FakeCanvas` with a live `GameInfo`;
   assert no exception, cursor advances by canvas width.
2. `test_scoreboard_draw_final` — final state renders without score colors raising.
3. `test_scoreboard_draw_preview` — preview state (no scores, has start time).
4. `test_scoreboard_draw_postponed` — postponed state shows PPD tag.
5. `test_scoreboard_draw_off_day` — off-day state.
6. `test_abs_pips_two_remaining` — challenges=2 produces two filled amber pips.
7. `test_abs_pips_zero_remaining` — challenges=0 produces two dim pips.
8. `test_abs_pips_none_hidden` — challenges=None produces no pip content.
9. `test_scoreboard_layout_config` — `MLBScoreMonitor` with `layout="scoreboard"` builds
   `MLBScoreboardMessage` objects in `feed_stories`; `layout="ticker"` builds
   `MLBGameMessage` objects.
10. `test_advance_frame_contract` — already covered by `test_widget_contracts.py`;
    no additional test needed.

---

## Out of Scope

- Standings widget (`mlb_standings`) — separate widget, not touched.
- Live pitch-by-pitch animation or in-game notifications.
- ABS challenge *events* (flashing when a challenge is used) — static count only.
- Any changes to the single-line ticker layout or `MLBGameMessage`.
