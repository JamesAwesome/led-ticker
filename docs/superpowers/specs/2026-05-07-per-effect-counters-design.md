# Per-Effect Frame Counters Design

**Date:** 2026-05-07
**Status:** Approved (pending implementation plan)

## Goal

Eliminate the composition tradeoff documented in PR #11. Today, a widget
with both `Typewriter` (wants restart-on-visit) and `RainbowChaseBorder`
(wants continuous phase) gets the continuous semantics — typewriter
doesn't retype on inner loop iterations because the shared `_frame_count`
can't satisfy both effects simultaneously. After this refactor, both
effects work as designed on the same widget.

## Background

PR #11 (visit-reset / continuous-phase fix) introduced a
`_should_reset_frame()` gate in `_show_one`: any effect with
`restart_on_visit = False` blocks the reset. This solved the
hardware-visible chase artifact (chase snapping back to phase 0 on
loop iterations) but at the cost of a "ANY opt-out wins" composition
rule. Smoke §17 demonstrates the limitation on hardware: a TickerMessage
with both typewriter and rainbow border types ONCE on iteration 1 and
holds for the remaining 2 loops.

The root cause is one shared `_frame_count` per widget. Typewriter reads
it to compute "how many characters to reveal" — so it needs to reset on
visit. RainbowChaseBorder reads it to compute "perimeter hue offset" —
so it needs to NOT reset on visit. Same counter, contradictory needs.

The fix: per-effect counters. Each effect on the widget tracks its own
frame state, follows its own `restart_on_visit` policy, and renders
correctly regardless of what other effects exist on the same widget.

## Scope

**In:**
- `_FrameAware` mixin gains an `_effect_frames: dict[str, int]` field
  tracking per-effect-attribute frame counters.
- New `frame_for(attr_name) -> int` helper on the mixin returns the
  per-effect counter (with fallback to `_frame_count` for unknown /
  unset entries).
- `advance_frame()` increments all per-effect counters together.
- `reset_frame()` resets only the per-effect counters whose effect has
  `restart_on_visit = True` (the existing flag, repurposed).
- Widget call sites change from `effect.api(self._frame_count, ...)`
  to `effect.api(self.frame_for(attr_name), ...)` — ~17 sites across
  3 widget files.
- `_should_reset_frame()` helper in `ticker.py` is **deleted**; the
  `_show_one` gate reverts to unconditional `widget.reset_frame()`.
- Smoke §17 comment is rewritten — same hardware test, but now
  demonstrates the win (both behaviors compose) instead of the
  limitation.
- CLAUDE.md updated: composition rule disappears.

**Out:**
- Per-effect pause/resume (no demand; pause stays widget-level).
- TOML knob to override per-effect counter behavior (no use case).
- Migrating effect classes to be stateful (Approach A from
  brainstorming — bigger API change, no current value over Approach B).

## Architecture

### `_FrameAware` mixin shape

```python
@attrs.define
class _FrameAware:
    """Mixin providing per-widget + per-effect frame counters."""

    _EFFECT_ATTRS = ("font_color", "top_color", "bottom_color", "border", "animation")

    _frame_count: int = attrs.field(init=False, default=0)
    _frame_paused: bool = attrs.field(init=False, default=False)
    _effect_frames: dict[str, int] = attrs.field(init=False, factory=dict)

    def _iter_effects(self):
        for attr in self._EFFECT_ATTRS:
            effect = getattr(self, attr, None)
            if effect is not None:
                yield attr, effect

    def advance_frame(self) -> None:
        if self._frame_paused:
            return
        self._frame_count += 1
        for attr_name, _ in self._iter_effects():
            self._effect_frames[attr_name] = (
                self._effect_frames.get(attr_name, 0) + 1
            )

    def pause_frame(self) -> None:
        self._frame_paused = True

    def resume_frame(self) -> None:
        self._frame_paused = False

    def reset_frame(self) -> None:
        """Visit-entry reset. The primary counter always resets;
        per-effect counters reset only for effects that opted in
        via `restart_on_visit = True` (the default)."""
        self._frame_count = 0
        for attr_name, effect in self._iter_effects():
            if getattr(effect, "restart_on_visit", True):
                self._effect_frames[attr_name] = 0

    def frame_for(self, attr_name: str) -> int:
        """Return the per-effect frame counter, or `_frame_count`
        as a fallback for unknown / unset entries."""
        return self._effect_frames.get(attr_name, self._frame_count)
```

### Key semantics

- **`_frame_count`** retains today's meaning: ticks since the last
  visit reset. Tests that read `widget._frame_count` keep working
  under their existing semantic.
- **`_effect_frames[X]`** follows X's `restart_on_visit` policy:
  - `restart_on_visit = True` (default): resets per visit, climbs
    from 0 each loop. Typewriter, Random, frame-invariant effects.
  - `restart_on_visit = False`: never resets via `reset_frame()`,
    climbs continuously. Rainbow, ColorCycle, RainbowChaseBorder.
- **`frame_for(attr_name)`** is the lookup widgets use; falls back
  to `_frame_count` if the dict has no entry yet (lazy init handles
  first-tick cleanly).
- **Pause is widget-level** (existing semantic): paused widget =
  all counters frozen. No per-effect pause control needed today.

### Single source of truth for effect attribute names

`_EFFECT_ATTRS` becomes a class constant on `_FrameAware`. Today the
list is duplicated in `ticker.py:_should_reset_frame` and would
otherwise be duplicated again in the new mixin's `_iter_effects()`.
After this refactor the helper is deleted and the constant lives only
on the mixin.

## Widget call site updates

Every site that currently passes `self._frame_count` to an effect
changes to `self.frame_for(attr_name)`. The `attr_name` is the
attribute name the effect was assigned to on the widget — that's what
makes `_effect_frames["border"]` correspond to the actual border
instance.

| File | Sites | Pattern |
|---|---|---|
| `widgets/message.py` | 5 | `border` → `frame_for("border")`, `font_color` → `frame_for("font_color")`, `animation` → `frame_for("animation")` |
| `widgets/two_row.py` | 3 | `top_color` / `bottom_color` / `border` |
| `widgets/_image_base.py` | ~9 | `font_color` / `top_color` / `bottom_color` / `border` |

Total ~17 widget call sites change. Mechanical edits.

## Engine cleanup

`src/led_ticker/ticker.py`:
- `_should_reset_frame()` helper (added in PR #11) — **deleted**.
- `_show_one`'s line 765 — `if hasattr(widget, "reset_frame") and _should_reset_frame(widget):` reverts to `if hasattr(widget, "reset_frame"):` (unconditional).

The composition rule disappears. The widget's `reset_frame()` itself
does the per-effect work; the engine doesn't need to know.

## Effect classes

Unchanged. The `restart_on_visit = False` class attributes set in PR #11
(`Rainbow`, `ColorCycle`, `RainbowChaseBorder`) stay where they are.
The flag's consumer moves from `_show_one._should_reset_frame()` to
`_FrameAware.reset_frame()` — same flag, slightly different reader.

## Pause/resume

Unchanged from today. `pause_frame()` sets one bool; `advance_frame()`
short-circuits. All counters (primary + per-effect) freeze together.

## Testing

### New tests in `tests/test_frame_aware.py` (new file)

`_FrameAware` doesn't have its own dedicated test file today — it's
exercised indirectly via widget tests. This refactor adds enough
mixin-specific behavior to justify a focused test module.

**`TestEffectFrames`** — 5 tests on the per-effect counter logic:

1. `test_advance_increments_per_effect_counter` — widget with one
   continuous-phase effect (`border = RainbowChaseBorder()`); call
   `advance_frame()` N times; assert
   `widget._effect_frames["border"] == N`.

2. `test_reset_zeros_only_opted_in_effects` — widget with both
   `Typewriter` (restart_on_visit=True) and `RainbowChaseBorder`
   (restart_on_visit=False); advance, then reset; verify
   `_effect_frames["animation"] == 0` and `_effect_frames["border"]`
   unchanged.

3. `test_pause_freezes_all_counters` — pause, advance ×N, verify both
   `_frame_count` and all `_effect_frames` entries unchanged from
   pre-pause.

4. `test_frame_for_falls_back_to_frame_count` — lookup of an
   `attr_name` not in the dict returns `_frame_count`. Set
   `widget._frame_count = 42`, no advance yet; assert
   `widget.frame_for("border") == 42`.

5. `test_unknown_effect_class_resets_by_default` — widget with an
   effect that doesn't set `restart_on_visit`; assert that on reset,
   its per-effect counter zeros (default True via `getattr` fallback).

### Composition tripwire — replaces PR #11's rule with the new behavior

In `tests/test_ticker_display.py`:

**Delete**: `TestShouldResetFrame` (5 tests) — the gate function is
deleted; tests go with it.
**Delete**: `TestShouldResetFrameComposition` (1 test) — replaced by
the new integration test below.

**Add**: `TestTypewriterPlusRainbowBorderComposition` (3 tests) — drive
`_show_one` TWICE on a TickerMessage with both effects; assert:
1. Typewriter's per-effect counter resets between iterations (retypes).
2. Rainbow border's per-effect counter does NOT reset (chase advances
   continuously).
3. `widget._frame_count` resets between iterations (back-compat for
   any existing readers).

### Tests preserved (unchanged, still passing)

- `TestShowOneResetsFrame` (4 tests, including the 2 added in PR #11)
  — still meaningful: they assert `widget.reset_frame()` is called on
  visit. The internals of `reset_frame()` change but the call still
  fires for every widget that has the method.
- `TestContinuousProviderRestartOnVisit` (2 tests) and
  `TestRainbowChaseBorderRestartOnVisit` (1 test) — class-attribute
  pins still pass; the flag is repurposed but the value stays False.

## Smoke config update

`config/config.rainbow_border_test.example.toml` §17 — comment header
rewritten. Today the comment frames it as "composition tradeoff DEMO —
message types out ONCE." After this refactor:

```
# 17. Typewriter + RainbowChaseBorder — both effects compose
#     simultaneously after the per-effect counter refactor.
#     Watch for: 3 distinct typing animations (typewriter retypes
#     each loop) AND a continuously-advancing rainbow chase around
#     the perimeter (no phase snap-back).
#
#     This was a documented tradeoff in PR #11 ("composition rule:
#     ANY opt-out wins") that became a positive test after the per-
#     effect counter work landed.
```

The TOML widget block is unchanged. Same hardware test, different
expected outcome.

## Documentation

### CLAUDE.md update

Replace the "Composition rule: ANY opt-out wins" paragraph (the one
landed in PR #11's docs commit) with:

> Per-effect counters: each effect on a widget tracks its own
> visit-reset state. `Typewriter` retypes on each loop AND a rainbow
> border continues its chase phase simultaneously — no composition
> tradeoff. The widget's `_frame_count` is the engine tick counter
> (resets per visit); `widget.frame_for(attr_name)` returns the
> per-effect counter that follows the effect's `restart_on_visit`
> policy. Smoke §17 of the rainbow border test demonstrates both
> behaviors composing on hardware.

### Module docstring updates

- `widgets/_frame_aware.py` — module docstring explains the per-effect
  counter model. Today's 13-line docstring grows to ~25 lines.
- `borders.py` and `color_providers.py` — their `restart_on_visit`
  convention paragraphs stay as-is (the flag's semantic is
  unchanged; only its consumer location moved).

## Out / deferred

- **Stateful effects** (Approach A from brainstorming) — bigger API
  change, no current value over the chosen approach. Effects stay
  stateless / pure functions of frame value.
- **Per-effect pause/resume** — today's widget-level pause is
  sufficient for transitions. No use case for finer control.
- **Removing `_frame_count` entirely** — kept as the "primary tick
  counter" for back-compat with existing tests and any direct readers
  in widget code that don't dispatch to a specific effect (e.g.
  `draw_with_emoji(..., frame=...)` calls in image widgets).
