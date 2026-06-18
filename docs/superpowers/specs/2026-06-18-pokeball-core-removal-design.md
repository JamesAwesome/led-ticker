# Remove the dormant procedural pokeball from core — Design

**Date:** 2026-06-18
**Status:** Approved (brainstorm with James)
**Parent:** led-ticker issue #231 (this is the standalone "Step B"; supersedes that
issue's Phase 1/2 LeadingEntity seam — see the 2026-06-18 issue comment)
**Sibling:** `led-ticker-arcade` PR #4 (merged) — the pre-render Step A.

## Context

The four sprite-trail transitions (`nyancat` / `pokeball` / `pacman` /
`sailor_moon`) and the pokeball emoji were extracted to
[led-ticker-arcade](https://github.com/JamesAwesome/led-ticker-arcade) in #229.
Core **retained** the public hi-res infra (`render_hires_frame`, `HiresSpec`,
`_hires_loader.py`) that the arcade transitions consume — and, as a documented
"retained hook", core kept the **pokeball-specific procedural ball** inside
`render_hires_frame`, gated by `show_pokeball` / `show_pikachu` kwargs that the
arcade pokeball passed through (#230 routes those from TOML via
`TransitionConfig.extra`).

**As of arcade PR #4 (merged), that hook is dormant.** The arcade pokeball now
renders from pre-baked combined sprites through `render_hires_frame`'s **generic
sprite-only path** (the same path `nyancat` uses) and no longer passes
`show_pokeball` / `show_pikachu`. Core itself has no pokeball transition. So
**nothing anywhere passes those kwargs to `render_hires_frame`** — the ball
branch is dead code.

This PR deletes it. After this, `render_hires_frame` is purely "a hi-res sprite
traverses the panel leaving a trail" — no entity-specific knowledge.

## Key finding: the deletion is behavior-preserving for live consumers

`render_hires_frame` already has two branches (`_hires_loader.py` ~L306):

- `if show_pokeball:` — the ball-leading geometry (ball is the leading entity,
  sprite chases it, trail extends behind the ball's far edge) + a later
  `_paint_procedural_pokeball` paint block. **No live caller reaches this** (it
  requires `show_pokeball=True`, which nothing passes anymore).
- `else:` — the **sprite-leads** path: `travel = panel_w + sprite.width`,
  `sprite_x`/`leading_x` from the sprite, trail behind the sprite's far edge.
  **This is what `nyancat` and the new arcade `pokeball` both hit today.**

Removing the `if show_pokeball:` branch (and the `show_pikachu` gate around the
sprite paint, since the sprite is now unconditionally the entity) collapses the
function to the `else` path **unchanged** for every live consumer. The existing
trail/sprite/snap tests in `tests/test_hires_loader.py` exercise exactly this
path and are the regression net.

## Scope

### A. `src/led_ticker/transitions/_hires_loader.py`
- **Delete** `_paint_procedural_pokeball(...)` (the ~62-line procedural-ball
  rasterizer).
- **Refactor** `render_hires_frame`:
  - Remove the `show_pokeball = bool(kwargs.get("show_pokeball", False))` /
    `show_pikachu = kwargs.get("show_pikachu", True)` reads.
  - Remove the entire `if show_pokeball: ... else: ...` block, keeping ONLY the
    `else` body (sprite-leads geometry: `travel`, `sprite_x`, `leading_x`,
    `sprite_y`). Drop the now-unused `ball_radius`/`ball_cx`/`ball_cy`
    type-checker placeholders.
  - Trail gate `if (show_pokeball or show_pikachu) and sprite.trail != "none":`
    → `if sprite.trail != "none":` (the sprite is always the visible entity).
  - **Delete** the "5. Paint procedural pokeball" block (the
    `if show_pokeball:` rotation + `_paint_procedural_pokeball(...)` call).
  - The "6. Paint sprite" block: drop the `if show_pikachu:` wrapper so the
    sprite always paints. KEEP the `if sprite.trail != "black":` bbox
    black-fill optimization (it is about trail COLOR, not `show_*`) and its
    comment (reword the "pokeball case" phrasing to "black-trail case").
  - Rewrite the docstring + the narrative comments (the docstring names
    `Pokeball`/`PokeballReverse`; the L292-302 / L324-329 / L344-347 /
    L374-378 / L396 comments narrate the pokeball ball layout). New docstring:
    "Paint one frame of a hi-res sprite traversing the panel, leaving a trail.
    Used by sprite-trail transitions (e.g. led-ticker-arcade's nyancat /
    pokeball) on a `ScaledCanvas`." No mention of a procedural ball or `show_*`.
- `math` import: KEEP only if still used after the ball deletion; if
  `_paint_procedural_pokeball` was its only user, remove the `import math`
  (verify with grep + ruff).

### B. `tests/test_hires_loader.py`
- **Delete** `test_render_hires_frame_honors_show_pokeball_and_pikachu` (the
  retained-hook smoke test, ~L230) — it is the only test that drives
  `show_pokeball=True`/`show_pikachu=` and asserts the procedural ball.
- KEEP every other test (frame timing, decode/cache, flip, snap, all the
  trail-fill/hold tests, signature, unregistered-spec) — they cover the
  retained sprite-leads path and must stay green **unchanged**.

### C. Docs (reframe `show_*` as plugin config; fix the one stale core-API line)
- `docs/site/src/content/docs/plugins/api-reference.mdx:192` — the
  `render_hires_frame` row says "(use on a `ScaledCanvas`; pass
  `show_pokeball=True` for a procedural leading ball)". **Remove the
  `show_pokeball` clause** — that kwarg no longer exists. New cell ends at
  "(use on a `ScaledCanvas`)".
- **Audit (likely no change needed):** `docs/content-source/transitions/sprite.md`
  (L22-23 knob table), `docs/site/.../transitions/sprite.mdx` (L29 caption),
  `docs/site/.../transitions/index.mdx` (L65) already attribute `show_*` to the
  **arcade plugin** and describe user-facing behavior that the pre-render
  approach **preserves** (`show_pokeball=false` → Pikachu-only;
  `show_pikachu=false` → ball-only). Confirm none of them claim `show_*` is a
  core `render_hires_frame` mechanism; if any does, reword to "arcade pokeball
  config (via TOML `extra`)". The committed demo GIFs are kept static assets
  (#229 removed the arcade transitions from core's render pipeline) — no
  regeneration.

### D. `CLAUDE.md`
- **"Hi-res transitions"** invariant: drop the sentence(s) describing the
  procedural pokeball ball / `show_*` as a retained core mechanism; state that
  `render_hires_frame` is generic sprite-trail infra (no entity-specific code).
- **"Extracted widgets retain core hooks"**: the pokeball procedural ball is no
  longer a retained hook — remove it from that list if listed; the other hooks
  (`_DISPATCH_APPLICABLE_TYPES`, `lazy_palette`, `GEOMETRIC_SHAPES`,
  `small_font`) are unaffected.

### Keep (correct, NOT dead — do not touch)
- `src/led_ticker/plugins_catalog.json` arcade entry.
- `src/led_ticker/transitions/__init__.py` migration hints (bare `pokeball` →
  `arcade.pokeball`) and bg-color comments.
- `tests/test_config.py` (`arcade.pokeball` + `show_*` → `extra` passthrough)
  and `tests/test_docs_config_options_drift.py` comments — they test the generic
  `extra` mechanism; `arcade.pokeball` is just the example. Still valid.

## Testing
- `make test` green: the deleted smoke test is the only removal; all retained
  `test_hires_loader.py` cases pass **unchanged** (proof the sprite-leads path
  is untouched).
- `make lint` (ruff) clean — confirm no unused `math` import / dead names.
- `make docs-lint` clean (prettier) — after the api-reference edit; run
  `make docs-format` if needed.
- Drift tripwires green: `test_docs_config_options_drift.py`,
  `test_docs_plugin_api_drift.py` (the api-reference edit must not break the
  plugin-API drift guard — the `render_hires_frame` signature itself is
  unchanged; only the prose clause is removed).
- Behavioral sanity: a `ScaledCanvas` render through `render_hires_frame` with a
  trail spec still paints sprite + trail + snap (existing tests assert this);
  there is no longer any `show_pokeball` code path to exercise.

## Out of scope
- Any change to `HiresSpec`, `load_hires`, `_decode`, `snap_reset`, or the trail
  model — all retained as-is.
- The generic "leading procedural entity" seam (#231 Phase 1) — explicitly
  dropped; the pre-render approach removed the need. A future plugin wanting a
  runtime-procedural leading entity would propose it separately.
- `config/requirements-plugins.example.txt` arcade line (a separate gap if it
  exists; not part of this deletion).
- Re-rendering any demo GIFs.

## Delivery
A single core PR on `feat/remove-procedural-pokeball` (off `origin/main`),
executed subagent-driven with per-task spec + quality review, merge-gated on
explicit per-PR consent. Completes the pokeball cleanup (issue #231).
