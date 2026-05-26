# Design: Unify `hold_time` / `hold_seconds` into a single `hold_time` field

**Date:** 2026-05-26
**Status:** Approved

## Problem

Two field names exist for the same concept — "how long should this item be on screen":

- `hold_time` — section-level TOML field (`SectionConfig`). Controls how long the engine holds each widget in the section.
- `hold_seconds` — widget-level field, only on `image`/`still` (`StillImage`). The per-widget minimum display duration.

The names are inconsistent (no unit suffix vs explicit `_seconds`), and `hold_seconds` does not signal that it is a floor rather than an absolute duration. Most widgets have no way to declare their own minimum hold at all.

## Solution

Introduce widget-level `hold_time` on a defined set of widgets. Rename `hold_seconds` → `hold_time` on `StillImage`. The engine resolves the effective hold duration as `max(section.hold_time, widget.hold_time)` — longer wins, silently. No migration error for the old `hold_seconds` key; example configs are updated.

## Semantics

```
effective_hold = max(section.hold_time, widget.hold_time)
```

- `widget.hold_time` defaults to `0.0`, which collapses to `section.hold_time` — no change in behavior for existing configs that don't set it.
- "Longer wins" is symmetric: the section can extend a widget's requested hold, and a widget can extend the section's default. Neither silently overrides the other.
- No validator warning when both are set — the behavior is transparent and composable, not a mistake.

## Widget coverage

| Widget | `hold_time` added? | Notes |
|---|---|---|
| `message` | Yes | |
| `two_row` | Yes | `bottom_text_loops` handles scroll repetition; `hold_time` handles raw duration |
| `weather` | Yes | |
| `mlb` | Yes | |
| `mlb_standings` | Yes | |
| `coinbase` | Yes | |
| `coingecko` | Yes | |
| `etherscan` | Yes | |
| `image` / `still` | Yes | `hold_seconds` → `hold_time`; behavior unchanged |
| `gif` | No | `play_count` already controls duration; two duration knobs would invite confusion |
| `countdown` | No | Has a natural terminal state; holding past zero shows a frozen display |
| `rss_feed` | No | Meta-widget; never renders itself |

## Engine changes

**`ticker.py` — `_run_swap`**

Before calling `_swap_and_scroll` or `_play_widget` for each widget, resolve effective hold:

```python
effective_hold = max(section.hold_time, getattr(widget, "hold_time", 0.0))
```

Pass `effective_hold` where `hold_time` was previously passed. No other engine changes required.

**`still.py` — `StillImage`**

- Rename field `hold_seconds` → `hold_time` (default `5.0` preserved).
- `play()` already computes `max(self.hold_seconds, hold_time_arg)` — rename field reference, behavior unchanged.
- Update internal validation (`HOLD_SECONDS_FLOOR` constant → `HOLD_TIME_FLOOR`; error messages updated).

**Widget fields (all newly covered widgets)**

Add `hold_time: float = 0.0` to each widget's attrs class. Default `0.0` means "defer to section."

## Validate changes

- Rule 8 (hold floor check): update key from `hold_seconds` to `hold_time` and apply to all widgets that now expose the field (not just `image`).
- Remove `hold_seconds`-specific mention from error messages; generalize to `hold_time`.

## Config examples

Update all `hold_seconds = ...` occurrences in `config/` to `hold_time = ...`. No other config changes required — all existing `hold_time` section-level usages are unaffected.

## Stale `hold_seconds` in user configs

No explicit migration error is added. The widget factory already raises `ValueError` with did-you-mean suggestions for unknown keys, so a user config that still contains `hold_seconds` will produce:

```
widget type='image' got unknown field: hold_seconds
  Did you mean: hold_time?
```

The did-you-mean lookup is fuzzy-matched, so `hold_seconds` will surface `hold_time` as the suggestion. No extra code required.

## What does NOT change

- Section-level `hold_time` on `SectionConfig` — name and behavior unchanged.
- `hold_time_specified` flag on `SectionConfig` — unchanged.
- Rule 30 (hold_time + bottom_text_loops warning) — unchanged.
- Rule 36 (play_count=0 + gif mode) — unchanged.
- `gif`, `countdown`, `rss_feed` — no new field.
- Internal ticker parameter names (`section_hold_time`, `hold_time_ticks`) — unchanged; these are implementation details.

## Testing

- Existing `StillImage` tests updated: `hold_seconds=` kwargs → `hold_time=`.
- New parametrized test: for each newly covered widget type, assert `effective_hold = max(section_hold, widget_hold)` by verifying tick count matches the longer of the two.
- Rule 8 validation test updated to use `hold_time` key.
- `test_app.py` field-listing test updated (`hold_seconds` → `hold_time`).
