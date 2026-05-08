# Design: `wipe_random` and `push_random` Transitions

**Date:** 2026-05-07
**Status:** Approved

## Overview

Two new transition modes that pick a random direction on each swap, avoiding immediate direction repeats. `wipe_random` also picks a random sweep-line color from a configurable palette. Both follow the existing alternating-transition pattern (delegate to sub-transition instances) and are drop-in replacements for any existing transition name in TOML.

## `WipeRandom`

**Registered name:** `"wipe_random"`
**File:** `src/led_ticker/transitions/wipe.py`

### Constructor

```python
def __init__(
    self,
    colors: list[ColorTuple] | None = None,
    color: ColorTuple | None = None,
    **kwargs: Any,
) -> None:
```

Color pool resolution (priority order):
1. `colors` kwarg — use as-is
2. `color` kwarg — single-element pool `[color]`
3. Default — the four direction `DEFAULT_COLOR`s: `WipeLeft.DEFAULT_COLOR` (cyan), `WipeRight.DEFAULT_COLOR` (magenta), `WipeUp.DEFAULT_COLOR` (white), `WipeDown.DEFAULT_COLOR` (green)

### State

- `_color_pool: list[ColorTuple]` — resolved at construction
- `_wipe_classes = [WipeLeft, WipeRight, WipeUp, WipeDown]`
- `_rng = random.Random()` — unseeded (system entropy)
- `_last_cls: type | None = None` — tracks last direction to prevent repeats
- `_last_t: float = 1.0` — detects swap boundary (`t < _last_t`)
- `_current: _BaseWipe | None = None` — active sub-transition instance

### Behavior

On each swap (when `t < _last_t`):
1. Pick a random class from `_wipe_classes` **excluding** `_last_cls` (3 candidates)
2. Pick a random color from `_color_pool`
3. Instantiate fresh: `cls(color=color)`
4. Store as `_current`, update `_last_cls`

`frame_at` delegates entirely to `_current.frame_at(t, canvas, outgoing, incoming, **kwargs)`.

`min_frames` property delegates to `_current.min_frames`. Before the first swap (`_current is None`), returns `40` — the `_BaseWipe` base-class default and the highest value among all four wipe directions. `run_transition` reads `min_frames` before calling `frame_at`, so the fallback must be a safe upper bound, not an arbitrary low value.

On the **first** swap `_last_cls` is `None`; filtering `None` from `_wipe_classes` is a no-op, so all four directions are candidates. From the second swap onward, 3 candidates remain.

Direction and color are picked **independently** — the same color can pair with any direction.

## `PushRandom`

**Registered name:** `"push_random"`
**File:** `src/led_ticker/transitions/push.py`

### Constructor

```python
def __init__(self, **kwargs: Any) -> None:
```

No color params — push transitions have no sweep-line color concept.

### State

- `_push_classes = [PushLeft, PushRight, PushUp, PushDown]`
- `_rng = random.Random()` — unseeded
- `_last_cls: type | None = None`
- `_last_t: float = 1.0`
- `_current: Transition | None = None`

### Behavior

On each swap: pick a random class excluding `_last_cls` (all 4 on first swap when `_last_cls` is `None`, 3 thereafter), instantiate fresh `cls()`, store as `_current`. `frame_at` and `min_frames` delegate to `_current`. `min_frames` before the first swap returns `10` (push directions have no custom `min_frames`).

## TOML Configuration

No new keys. Both drop in as standard transition names:

```toml
transition = "wipe_random"
transition = "push_random"
```

`wipe_random` color pool override via the existing `transition_colors` key:

```toml
transition = "wipe_random"
transition_colors = [[255, 0, 0], [0, 255, 255], [255, 0, 255]]
```

Single-color shorthand also works (becomes a one-element pool — random direction, fixed color):

```toml
transition = "wipe_random"
transition_color = [0, 255, 255]
```

`_build_trans_obj` in `app.py` already plumbs `colors` and `color` kwargs through to the constructor — no changes to config or app layer needed.

## Files Changed

| File | Change |
|------|--------|
| `src/led_ticker/transitions/wipe.py` | Add `WipeRandom` class |
| `src/led_ticker/transitions/push.py` | Add `PushRandom` class |
| `src/led_ticker/transitions/__init__.py` | Import + re-export both classes |
| `tests/test_transitions.py` | Add test classes below |

## Tests

Four test classes in `tests/test_transitions.py`:

**`TestWipeRandomNeverRepeatsDirection`**
Simulate 20 consecutive swaps (reset `t` to 0 each time to trigger the swap-detection branch). Assert no two consecutive swaps produce the same direction class on `_current`.

**`TestWipeRandomColorPool`**
Three sub-cases:
- No args → pool equals `[WipeLeft.DEFAULT_COLOR, WipeRight.DEFAULT_COLOR, WipeUp.DEFAULT_COLOR, WipeDown.DEFAULT_COLOR]`
- `color=(255, 0, 0)` → pool is `[(255, 0, 0)]`
- `colors=[(1,2,3),(4,5,6)]` → pool is `[(1,2,3),(4,5,6)]`

**`TestPushRandomNeverRepeatsDirection`**
Same 20-swap no-consecutive-repeat check for `PushRandom`.

**`TestPushRandomDelegatesFrameAt`**
Assert that calling `frame_at` on the outer object calls `_current.frame_at` with identical positional and keyword args.
