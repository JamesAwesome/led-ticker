# Visit-Reset / Continuous-Phase Design

**Date:** 2026-05-07
**Status:** Approved (pending implementation plan)

## Goal

Stop animated chases (`RainbowChaseBorder`, `Rainbow` color provider,
`ColorCycle` color provider) from snapping their phase back to 0 at
every `loop_count > 1` iteration of a single-widget section. Keep
today's "retype each loop" behavior for `Typewriter`.

## Background

`_show_one` in `ticker.py:729-730` unconditionally calls
`widget.reset_frame()` on every visit entry. The behavior is correct
for typewriter (each visit = restart typing from char 0) but visibly
wrong for animated borders / color providers — the chase phase snaps
back to 0 at every `loop_count` boundary mid-section.

Hardware-observed on §5 of the rainbow border smoke (PIKA gif on
`loop_count = 3`). Mitigated in PR #10 via the smoke config (collapsed
`loop_count = 3 × gif_loops = 3` to `loop_count = 1 × gif_loops = 9`)
and a CLAUDE.md hedge documenting the workaround. This spec is the
principled fix.

## Scope

**In:**
- New attribute convention: effect classes that want continuous phase
  across `loop_count > 1` iterations set `restart_on_visit: bool = False`
  as a class attribute.
- Engine logic: `_show_one` skips `reset_frame()` when ANY effect on the
  widget opts out via `restart_on_visit = False`.
- Per-effect defaults set on `Rainbow`, `ColorCycle`,
  `RainbowChaseBorder`. Other effect classes keep the protocol-default
  `True` (back-compat via `getattr` fallback).
- Documentation in `borders.py` / `color_providers.py` /
  `animations.py` module docstrings.
- Smoke config revert: §4, §5, §7 of the rainbow border smoke can go
  back to exercising real `loop_count > 1` behavior.

**Out:**
- Per-effect `_frame_count` counters (Approach C from brainstorming —
  bigger refactor, no current need).
- New `_show_one` distinction between section-entry and inner-loop
  iteration (Approach D — not needed; per-effect flag covers the
  use case because `run_transition._reset_presenter` already handles
  section-entry resets).
- Per-widget TOML knob to override the engine's choice (future
  addition if composition collisions become a real friction point).

## Architecture

### Engine logic

One change to `_show_one` in `ticker.py:729-730`. Currently:

```python
if hasattr(widget, "reset_frame"):
    widget.reset_frame()
```

Becomes:

```python
def _should_reset_frame(widget: Any) -> bool:
    """ANY effect on the widget that opts out of `restart_on_visit`
    blocks the reset. Favors continuity over restart — the safer
    default for animated chases that should advance smoothly across
    loop_count boundaries.

    Composition tradeoff: a widget with both `Typewriter` (wants
    restart) and `RainbowChaseBorder` (wants continuous) gets the
    continuous semantics — typewriter doesn't retype on inner loop
    iterations. Niche combo; documented in CLAUDE.md.
    """
    for attr in ("font_color", "top_color", "bottom_color", "border", "animation"):
        effect = getattr(widget, attr, None)
        if effect is None:
            continue
        if not getattr(effect, "restart_on_visit", True):
            return False
    return True

# In _show_one:
if hasattr(widget, "reset_frame") and _should_reset_frame(widget):
    widget.reset_frame()
```

### Section-entry handling

**Unchanged.** `run_transition` already calls `_reset_presenter(incoming)`
at the start of every inter-section / inter-widget transition. That
behavior is preserved as-is — every section entry gets a fresh
`_frame_count` regardless of effect flags. Our change only affects the
`_show_one` reset, which is the inner-loop-iteration path.

For the very first section of a playlist on first run (where
`just_transitioned` is False and no transition fires),
`_FrameAware._frame_count` defaults to 0 at widget construction —
no reset needed.

### Convention, not protocol surface change

Effects that want continuous phase set `restart_on_visit: bool = False`
as a class attribute. Effects that don't set anything get `True` via
`getattr` fallback — preserves today's behavior for any third-party
or unknown effect class.

The `BorderEffect`, `ColorProvider`, and `Animation` Protocol
docstrings get a one-liner documenting the convention. No mandatory
new fields on the protocols themselves; same loose-typing approach
already used for `frame_invariant`.

## Per-effect defaults

### Continuous-phase effects (set `restart_on_visit = False`)

| Effect | Module | Rationale |
|---|---|---|
| `Rainbow` | `color_providers.py` | Continuous hue sweep; restart snaps the rainbow back |
| `ColorCycle` | `color_providers.py` | Continuous cycle through hues |
| `RainbowChaseBorder` | `borders.py` | Continuous perimeter chase |

### Restart-on-visit effects (default `True`, no class change)

| Effect | Module | Rationale |
|---|---|---|
| `Typewriter` | `animations.py` | User explicitly wants retype each loop (per Q1 from brainstorming) |
| `Random` | `color_providers.py` | Re-roll the random pick on each visit — sensible refresh; `frame_invariant` so the engine reset still triggers a re-roll |

### Frame-invariant effects (default `True`, value is a no-op)

`_ConstantColor`, `Gradient`, `ConstantBorder` — all `frame_invariant`,
so resetting `_frame_count` to 0 doesn't change their rendered output.
Either default value renders identically. Stay at `True` for
back-compat and predicate simplicity.

### Naming

`restart_on_visit` mirrors `frame_invariant` — both express what the
effect needs from the engine, not what the engine does. Default `True`
is the back-compat option; effects that want continuous phase opt OUT
explicitly. Rejected alternatives:

- `continuous` — inverse polarity, harder to reason about defaults
- `restart_on_loop` — too narrow; the convention also applies to
  inter-section visits (though `run_transition` handles those
  separately)
- `frame_resets_on_visit` — less natural; the effect doesn't reset
  itself, the engine does

## Testing

### New tests in `tests/test_ticker_display.py`

**`TestShouldResetFrame`** — 4 tests on the gate function:

1. `test_no_effects_resets` — widget with `font_color=_ConstantColor`,
   no border / animation → returns True.
2. `test_continuous_color_provider_blocks_reset` — widget with
   `font_color=Rainbow()` → returns False.
3. `test_continuous_border_blocks_reset` — widget with
   `border=RainbowChaseBorder()` → returns False.
4. `test_typewriter_alone_resets` — widget with `animation=Typewriter()`
   and constant color, no border → returns True.

**`TestShowOneVisitReset`** — 2 integration tests on `_show_one`:

5. `test_show_one_advances_frame_count_across_loop_iterations` — drive
   `_show_one` twice on a bordered widget (simulating `loop_count = 2`),
   assert `_frame_count` is non-zero on entry to iteration 2.
6. `test_show_one_resets_for_typewriter_widget` — same shape with
   typewriter → assert `_frame_count` IS reset to 0 between iterations.

**`TestShouldResetFrameComposition`** — 1 test on the composition rule:

7. `test_typewriter_plus_rainbow_border_skips_reset` — widget with both
   typewriter and rainbow border. `_should_reset_frame` returns False
   (composition rule: any opt-out wins).

### Per-effect tripwires (one each)

- `tests/test_color_providers.py`: assert
  `Rainbow.restart_on_visit is False` and
  `ColorCycle.restart_on_visit is False`.
- `tests/test_borders.py`: assert
  `RainbowChaseBorder.restart_on_visit is False`.

These are class-attribute pins — catches a future change that flips a
default silently.

## Documentation

### CLAUDE.md update

Replace the visit-reset hedge in the Rainbow border section (currently
warns about the `loop_count > 1` footgun + smoke config workaround)
with:

> Continuous-phase effects (`Rainbow`, `ColorCycle`,
> `RainbowChaseBorder`) set `restart_on_visit = False` so their phase
> advances continuously across `loop_count > 1` iterations within a
> section. Section transitions still reset (via `run_transition`'s
> `_reset_presenter`) — entry-to-section is always fresh state.
>
> Composition rule: a widget with both a continuous effect and a
> restart-on-visit effect (e.g. typewriter + rainbow border) gets
> the continuous semantics — typewriter won't retype on inner loop
> iterations. Niche combo; if you need typewriter to retype on a
> bordered widget, drop the border and use a different framing
> approach.

### Module docstring notes

Short pointers at the top of `borders.py` and `color_providers.py`
documenting the convention:

> **`restart_on_visit` convention**: effect classes that want
> continuous phase across `loop_count > 1` iterations of a section
> set `restart_on_visit: bool = False` as a class attribute.
> Read by `_show_one._should_reset_frame` in `ticker.py`. Default
> `True` (via `getattr` fallback) keeps today's "every visit = fresh
> start" behavior for unknown effect classes.

## Smoke config revert

In `config/config.rainbow_border_test.example.toml`, §4 / §5 / §7
were collapsed to `loop_count = 1 × gif_loops = 9` to work around
the chase restart. After this fix lands, revert to the original
intent (`loop_count = 3 × gif_loops = 3`) so the smoke exercises
the real fix on hardware. The §5 inline comment about the
visit-reset workaround can come out.

## Open / deferred

- **Per-effect `_frame_count` counters** — Approach C from brainstorming
  (each effect tracks its own state). Conceptually cleanest but bigger
  refactor; no current need since per-effect flag handles the visible
  artifact and composition collisions are niche.
- **Per-widget TOML knob** — `restart_on_loop = false` field on widgets
  to override the engine's choice. Future addition if composition
  tradeoff becomes a real friction point. Not needed today.
- **Section-entry-vs-inner-loop distinction in `_show_one`** —
  Approach D considered during brainstorming. Not needed because
  `run_transition._reset_presenter` already handles section-entry
  resets, so our `_show_one` change only affects inner iterations
  by construction.
