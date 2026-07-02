# Visual-validation checklist for render-path changes

Unit tests pin math; they don't watch the panel. Twice in this repo's
history a rendered gif caught what the full suite plus multiple review
rounds missed (the propeller overflow blackout, 2026-07-02 — the pivot
formula was "correct" against every fitting-text test while blacking out
the panel for overflowing text). When a change touches the render path —
widgets, animations, transitions, color providers, borders, the engine's
draw loops — render gifs BEFORE merging, and actually look at them.

Use `make render-demo CONFIG=<scratch>.toml OUT=<scratch>.gif` (headless,
no hardware). Keep scratch configs out of the repo.

## The matrix

Render at least the configs that intersect your change; each line exists
because the plain "short text, one widget" demo cannot fail there.

- [ ] **Short/fitting text** — the baseline everyone renders anyway.
- [ ] **Overflowing text** (> 2× canvas width) — exercises the scroll
      branches, off-canvas geometry, `start_pos`/width math. The propeller
      pivot bug lived ONLY here.
- [ ] **Emoji in the text** (`:slug:`) — exercises the emoji draw path and
      its layout gates; on bigsign also the hires-sprite path.
- [ ] **Two+ widgets in a section, differing configs** — exercises
      transitions between states, per-widget effect counters, and visit
      restarts (`restart_on_visit` behavior is invisible with one widget).
- [ ] **A `cut` transition into/out of the feature** — cut is instant and
      masks nothing; blends hide phase/state discontinuities.
- [ ] **Short hold_time** (shorter than the effect's natural duration) —
      exercises mid-flight interruption, the settle seam, and validate's
      duration warnings.
- [ ] **Bigsign geometry when scaled behavior differs** (`default_scale >
      1` config) — the ScaledCanvas / hires gates flip here.

## How to look

- Don't just eyeball the gif once — extract frames. Gif writers dedupe
  static frames, so **long-duration frames ARE the rest states** (a
  multi-second single frame proves pixel-identical stability; conversely,
  missing long frames where you expect rest means something still moves).
- Profile lit-pixel counts across frames (a few lines of Pillow): a
  fully-black frame count > 0 during content display is almost always a
  bug, not an effect.
- Check the boundaries: first frame, the frame right before/after a
  transition, the settle instant.

## Scope

This is a pre-merge confidence pass, not CI (the suite's tripwires stay
the regression net). It complements, never replaces, the pixel-level unit
tests — when a gif catches something, turn it into a failing unit test
first (fail-first), then fix.
