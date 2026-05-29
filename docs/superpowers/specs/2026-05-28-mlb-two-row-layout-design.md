# MLB Widget: Two-Row Layout — Design Spec

**Date:** 2026-05-28
**Status:** Draft — pending implementation plan.
**Author:** James + Claude (brainstorming session)

## Summary

Add a `layout = "two_row"` rendering mode to the `mlb` widget. On the bigsign (`default_scale = 4`) and longboi (`default_scale = 4`) the logical canvas is 64×16px — at `font_size = 32` (8 logical px tall) there are two usable bands. The current ticker and scoreboard layouts don't exploit this split for game-time and final views. Two-row mode puts the matchup / score on the top band and the status / situation detail on the bottom band, making the widget more scannable at a glance.

This spec covers:

- A new `layout = "two_row"` value on `MLBScoreMonitor` (existing values `"ticker"` and `"scoreboard"` are unchanged).
- A new `MLBTwoRowMessage` draw class for multi-segment two-band rendering.
- Per-state content and color mapping for all four game states.
- ABS challenge pip placement (trailing each score, Option B).
- Per-row font fields and their wiring through `factories.py`.
- Validation rules.
- Tests.
- Updates to the bigsign smoketest config.

## Goals

- MLB widget renders an informative two-band layout on hires panels.
- Scoreboard layout (`layout = "scoreboard"`) is completely unchanged.
- Ticker layout (`layout = "ticker"`) is completely unchanged.
- Per-team colors, win/loss score colors, and ABS challenge pips all survive in the two-row view.
- Architecture mirrors the pool widget's `layout` field + dispatch pattern.

## Non-goals

- No changes to `layout = "ticker"` or `layout = "scoreboard"` rendering.
- No `TwoRowSegmentMessage` general primitive in this PR. MLB gets its own `MLBTwoRowMessage` draw class. A general `TwoRowSegmentMessage(top: SegmentMessage, bottom: SegmentMessage)` abstraction is a legitimate future refactor if weather, standings, or crypto develop the same need — but building it prematurely adds scope without a second consumer.
- No automatic layout switching based on `default_scale`. Users set `layout = "two_row"` explicitly in TOML.
- No changes to `mlb_standings` in this PR.
- No docs site changes in this PR (defer to a follow-up, same pattern as pool).

## Architecture

The codebase already has a clear rendering primitive ladder:

| Primitive | Shape | Used by |
|---|---|---|
| `SegmentMessage` | one row, `list[(text, Color)]` segments | ticker messages, pool ticker, title cards |
| `TwoRowMessage` | two rows, one string + one color per row | `two_row` widget, pool two_row, image overlays |
| `MLBScoreboardMessage` | custom zone layout, full draw math | MLB scoreboard layout |
| **`MLBTwoRowMessage`** (new) | two bands, multi-segment per band | MLB two_row layout |

`MLBTwoRowMessage` sits above `TwoRowMessage` on the ladder because MLB's bands require multi-colored segments. It uses the same `resolve_band_heights` + `row_layout` helpers from `widgets/_row_layout.py` that `TwoRowMessage` uses for band geometry, then renders segments directly via `draw_with_emoji`.

### Dispatch flow

```
MLBScoreMonitor._build_stories()
  └─ layout == "ticker"     → _build_game_message()         → SegmentMessage
     layout == "scoreboard" → _build_scoreboard_message()   → MLBScoreboardMessage
     layout == "two_row"    → _build_two_row_message()      → MLBTwoRowMessage
```

### Field additions

#### Runtime attrs fields on `MLBScoreMonitor`

```python
top_font: Font | None = attrs.field(default=None, kw_only=True)
top_row_height: int | None = attrs.field(default=None, kw_only=True)
```

Both `kw_only`, both optional. `top_font` receives an already-resolved `Font` from the dispatch layer. `top_row_height` is in logical rows (matches `TwoRowMessage`'s field). The main `font` field already exists and serves as the fallback for both bands.

`MLBTwoRowMessage` receives these fields:

```python
font: Font              # main font — fallback for both bands
small_font: Font        # for ABS pip dashes; same field already on MLBScoreMonitor
top_font: Font | None   # resolved top-band font; falls back to font
top_row_height: int | None  # None → symmetric 8/8 split
```

`small_font` is already an `attrs` field on `MLBScoreMonitor` (used by `MLBScoreboardMessage` for its center zone) and threads through to `MLBTwoRowMessage` unchanged — no new factory wiring needed.

#### Dispatch-layer updates in `app/factories.py`

`_DISPATCH_APPLICABLE_TYPES` already handles `top_font` / `top_font_size` / `top_font_threshold` for `{"two_row", "pool"}`. Widen each to include `"mlb"`:

```python
"top_font":           {"two_row", "pool", "mlb"},
"top_font_size":      {"two_row", "pool", "mlb"},
"top_font_threshold": {"two_row", "pool", "mlb"},
```

Bottom band uses `self.font` (the widget's main font). No `bottom_font` field — the scoreboard already uses `small_font` for its center zone, and two-row has no need for an independently sized bottom band in the initial implementation. Add `bottom_font` in a follow-up if hardware testing shows the bottom content needs a different size.

`top_row_height` passes through to `MLBTwoRowMessage` directly (same as pool → `TwoRowMessage`).

### Font fallback chain

- `top_font = None` → falls back to `self.font` inside `_build_two_row_message`.
- Omitting `top_font_size` in TOML → dispatch falls back to `font_size`.
- Omitting `top_font_threshold` → dispatch falls back to `font_threshold`.
- `top_row_height = None` → symmetric 8/8 logical split.

## Per-state content map

### Preview

| Band | Content | Colors |
|---|---|---|
| Top | `AWAY @ HOME (W-L)` | AWAY in team color · `@` white · HOME in team color · record grey |
| Bottom | `Today 7:10 PM` (or `Tmrw 6:05 PM` / `Fri 6:10 PM` etc.) | white |

Series record `(W-L)` omitted when `total_decided == 0` (no games played yet). `_fit_team_name` applies on both team names — long names fall back to abbreviations when the record takes space, same logic as scoreboard.

### Live

| Band | Content | Colors |
|---|---|---|
| Top | `AWAY score –– HOME score ––` | AWAY in team color · score white · pips (see ABS Pips) · HOME in team color · score white · pips |
| Bottom | `▼7  ◆◇◆  2·1·1` | inning arrow+number in LIVE_COLOR (red) · bases occupied=yellow dim=dark · balls=green · `·` white · strikes=yellow · `·` white · outs=red |

Base diamonds use main `font` glyphs (`◆` / `◇`). Diamond layout: 3B–2B–1B left to right inline on the bottom band (simpler than the scoreboard's stacked 2B-above / 3B-1B-below arrangement — the bottom band is a single row so stacking is not possible).

### Final

| Band | Content | Colors |
|---|---|---|
| Top | `AWAY score –– HOME score ––` | AWAY in team color · score in WIN_COLOR or LOSS_COLOR · pips · HOME in team color · score in LOSS_COLOR or WIN_COLOR · pips |
| Bottom | `FINAL · TEAM leads W-L` | `FINAL` grey · `·` grey · leading team in team color · record white |

Series record on bottom row: `FINAL · PHI leads 2-1` / `FINAL · NYM leads 1-2` / `FINAL · Tied 1-1`. Leading team name rendered in its team color; win/loss counts in white. Omit series summary when only a single game (no series context) — bottom row is just `FINAL` in grey. `FINAL` alone also when `total_decided == 0` (defensive; should not occur).

### Postponed

| Band | Content | Colors |
|---|---|---|
| Top | `AWAY @ HOME` | team colors, no series record |
| Bottom | `PPD: Rain` / `CANC` / `SUSP` / `EARLY` | amber (tag_color), same as ticker layout |

Mirrors preview structure — matchup on top, status on bottom. No series record since the game didn't complete.

## ABS challenge pips

Pips trail each team's score (Option B from brainstorming). Rendered using `small_font` (same font used by the scoreboard's center zone).

- `n` orange dashes (`CHALLENGE_COLOR`) for remaining challenges, `(2 - n)` grey dashes (`CHALLENGE_USED`) for used, where `n = min(count, 2)`.
- When `challenges is None` (ABS system not in effect / data unavailable): no pips rendered. Spacing between teams' scores tightens to compensate — no phantom gap.
- Pips share the same top band as the scores, trailing each score value.

## Validation

Added to `validate_widget_cfg` for the `mlb` widget type:

1. **Layout enum.** `layout` accepts only `"ticker"`, `"scoreboard"`, `"two_row"`. Anything else raises `ValueError` with `difflib.get_close_matches` suggestion.
2. **Dead knobs under non-two-row layouts.** Setting `top_font` / `top_font_size` / `top_font_threshold` / `top_row_height` while `layout` is `"ticker"` or `"scoreboard"` (or omitted) raises with: `"<field> only applies when layout='two_row'; remove the field or set layout='two_row'."` Matches pool's dead-knob check pattern exactly.

## Testing

### Behavioral tests (`tests/test_widgets/test_mlb.py`, new `TestMLBTwoRowMessage` class)

1. `test_two_row_preview_top_has_team_segments` — top band contains AWAY, `@`, HOME with correct team colors; series record present when `total_decided > 0`.
2. `test_two_row_preview_top_no_record_when_no_games_decided` — record segment absent when `total_decided == 0`.
3. `test_two_row_preview_bottom_has_game_time` — bottom band contains formatted start time.
4. `test_two_row_live_top_has_score_and_pips` — top band contains team abbrs, scores (white), trailing pip dashes in correct colors.
5. `test_two_row_live_bottom_has_inning_bases_bso` — bottom band has inning string, base diamond glyphs, BSO values in correct colors.
6. `test_two_row_final_top_uses_win_loss_colors` — winning team's score is WIN_COLOR, losing team's score is LOSS_COLOR.
7. `test_two_row_final_bottom_has_final_and_series_record` — bottom contains `FINAL` and series leader string.
8. `test_two_row_final_bottom_omits_record_on_single_game` — no series record when only one game.
9. `test_two_row_postponed_top_has_matchup` — top has AWAY @ HOME in team colors, no series record.
10. `test_two_row_postponed_bottom_has_tag` — bottom has amber `PPD: Rain` / `CANC` etc.
11. `test_two_row_pips_hidden_when_challenges_none` — no pip segments when `away_challenges is None`.
12. `test_two_row_pips_orange_and_grey_correct_count` — 1 remaining → 1 orange + 1 grey; 0 remaining → 2 grey; 2 remaining → 2 orange.
13. `test_two_row_top_font_threads_through` — sentinel `top_font` reaches `MLBTwoRowMessage.top_font`.
14. `test_two_row_top_row_height_threads_through` — sentinel `top_row_height` reaches the instance.

### Validation tests (`tests/test_validate.py` or `tests/test_widgets/test_mlb.py`)

15. `test_mlb_layout_unknown_raises` — `layout = "bigsign"` raises with did-you-mean.
16. `test_mlb_top_font_size_under_ticker_raises` — dead knob under default layout.
17. `test_mlb_top_row_height_under_scoreboard_raises` — dead knob under scoreboard.

### Tripwire

18. `test_two_row_message_is_mlb_two_row_message` — `isinstance(story, MLBTwoRowMessage)` for all stories when `layout = "two_row"`.

## Files affected

| File | Change |
|---|---|
| `src/led_ticker/widgets/mlb.py` | Add `MLBTwoRowMessage` class; add `_build_two_row_message()` factory; add `top_font: Font | None` and `top_row_height: int | None` attrs fields to `MLBScoreMonitor`; dispatch `layout == "two_row"` in `_build_stories()`. |
| `src/led_ticker/app/factories.py` | Widen `_DISPATCH_APPLICABLE_TYPES` for `top_font` / `top_font_size` / `top_font_threshold` to include `"mlb"`. |
| `src/led_ticker/validate.py` | Layout enum + dead-knob-under-non-two-row checks for `mlb`. |
| `tests/test_widgets/test_mlb.py` | New `TestMLBTwoRowMessage` class (~14 tests) + tripwire. |
| `tests/test_validate.py` | 3 validation tests. |
| `config/config.mlb_bigsign_test.toml` | Add a `layout = "two_row"` section alongside the existing ticker and scoreboard sections. |
| `CLAUDE.md` | One bullet under `mlb.py` noting `MLBTwoRowMessage` and the `layout` field values. |

## Future refactor note

`TwoRowSegmentMessage(top: SegmentMessage, bottom: SegmentMessage)` — a general two-band multi-segment primitive — is the natural abstraction once a second consumer (weather, standings, crypto) develops the same need. MLB's `MLBTwoRowMessage` is its own draw class now because it's the only consumer today. When a second widget needs multi-segment two-row, extract `TwoRowSegmentMessage` and migrate both. Do not extract it prematurely.

## Acceptance criteria

The PR ships when:

- All 18 listed tests pass.
- `make lint` clean.
- `make validate CONFIG=config/config.mlb_bigsign_test.toml` clean.
- All existing MLB tests still pass (`TestMLBScoreMonitor`, `TestMLBScoreboardMessage`).
- Hardware verification: all four game states render correctly on a bigsign or longboi panel with the two-row layout — team colors, win/loss score colors, ABS pips, bottom-band inning/BSO/time.
