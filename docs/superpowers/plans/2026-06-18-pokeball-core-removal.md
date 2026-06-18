# Remove the dormant procedural pokeball from core — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Delete the dead pokeball-specific procedural-ball logic from `render_hires_frame` (and `_paint_procedural_pokeball`), collapsing the function to the generic sprite-leads path that nyancat + the arcade pokeball already use — then reframe the now-stale docs/CLAUDE.md references.

**Architecture:** `render_hires_frame` currently has an `if show_pokeball: ... else: ...` split. No live caller passes `show_pokeball`/`show_pikachu` anymore (arcade PR #4 made the pokeball render from baked sprites via the `else` path; core has no pokeball transition). Removing the `if` branch + the ball rasterizer leaves the `else` (sprite-leads) path **byte-identical** for every live consumer; the existing trail/sprite/snap tests are the regression net. A second task sweeps the docs.

**Tech Stack:** Python 3.14, Pillow (sprite decode), pytest (`make test`, `PYTHONPATH=tests/stubs` auto-set), ruff (`make lint`), prettier/astro (`make docs-lint`, `make docs-format`).

**Branch/workflow:** Work in `/Users/james/projects/github/jamesawesome/led-ticker` on `feat/remove-procedural-pokeball` (already created off `origin/main`). NEVER touch `main`. Subagents `git add -A` and STOP — the controller commits (sandbox blocks subagent `git commit`). No `git push`/`merge`/`checkout <branch>`. No merge without explicit per-PR consent.

**Reference (current code, for context):**
- `src/led_ticker/transitions/_hires_loader.py`:
  - `import math` (L15) — used ONLY by the ball code (L201-202 in `_paint_procedural_pokeball`, L386 in the ball-paint block). Becomes unused → remove.
  - `_paint_procedural_pokeball(...)` ~L179-240 — delete entirely.
  - `render_hires_frame` ~L252-434 — refactor (see Task 1).
- `tests/test_hires_loader.py`: `test_render_hires_frame_honors_show_pokeball_and_pikachu` at L230-248 — delete.

---

### Task 1: Delete the procedural ball + collapse `render_hires_frame` to sprite-only

**Files:**
- Modify: `src/led_ticker/transitions/_hires_loader.py`
- Modify: `tests/test_hires_loader.py`

- [ ] **Step 1: Confirm the regression net is green BEFORE editing**

Run the retained-path tests (everything except the smoke test) so we have a known-green baseline:
```bash
cd /Users/james/projects/github/jamesawesome/led-ticker
make test 2>&1 | tail -15
```
Expected: full suite PASSES (this is the baseline; the trail/sprite/snap tests in `tests/test_hires_loader.py` are what must stay green after the deletion).

- [ ] **Step 2: Delete `_paint_procedural_pokeball`**

In `src/led_ticker/transitions/_hires_loader.py`, delete the entire function `_paint_procedural_pokeball(canvas, cx, cy, radius, band_angle_rad, panel_w, panel_h)` (def + docstring + body — currently ~L179-240, the function whose docstring begins `"""Paint a procedural pokeball via SetPixel."""`). Delete the trailing blank line so `@functools.cache\ndef load_hires(...)` follows the preceding function cleanly.

- [ ] **Step 3: Rewrite `render_hires_frame` — remove the `show_*` reads + the `if show_pokeball:` branch, keep ONLY the sprite-leads geometry**

In `render_hires_frame`, replace the block that currently starts at the comment `# 3. x-position.` and runs through the `sprite_y = (panel_h - sprite.height) // 2` line (the part containing `show_pokeball = bool(...)`, `show_pikachu = ...`, and the whole `if show_pokeball: ... else: ...`) with exactly this:

```python
    # 3. x-position. flip_horizontal drives both art mirroring AND
    #    traversal direction -- the sprite faces its travel direction.
    #    effective_t scales position so the leading edge reaches the far
    #    edge by TRAIL_SATURATION_T (well before SNAP_THRESHOLD), giving
    #    the trail time to fully fill the panel and hold before the cut.
    #    leading_x is the FRONT edge of the sprite (where it's moving to),
    #    so the trail extends THROUGH the sprite's region; the sprite then
    #    paints on top of the trail, and transparent / alpha-zero regions
    #    of the sprite reveal trail color rather than outgoing text.
    effective_t = min(1.0, t / TRAIL_SATURATION_T)
    travel = panel_w + sprite.width
    if sprite.flip_horizontal:
        sprite_x = panel_w - int(effective_t * travel)
        leading_x = sprite_x  # left edge — front of RTL traversal
    else:
        sprite_x = -sprite.width + int(effective_t * travel)
        leading_x = sprite_x + sprite.width  # right edge — front of LTR
    sprite_y = (panel_h - sprite.height) // 2
```

- [ ] **Step 4: Simplify the trail gate**

Still in `render_hires_frame`, the trail block currently opens with:
```python
    if (show_pokeball or show_pikachu) and sprite.trail != "none":
```
Replace that single line with (the sprite is now always the visible entity):
```python
    if sprite.trail != "none":
```
Leave the body of the trail block (the `if sprite.flip_horizontal:` start/end computation and the `black`/`rainbow` fills) unchanged.

- [ ] **Step 5: Delete the ball-paint block (old step 5)**

Delete the entire block that begins with the comment `# 5. Paint procedural pokeball BEFORE Pikachu ...` and the following `if show_pokeball:` through its `_paint_procedural_pokeball(real, ball_cx, ball_cy, ball_radius, band_angle, panel_w, panel_h)` call (the block that computes `pixels_per_rotation_frame`, `travel_done`, `ball_rotation_idx`, `rotation_step`, `band_angle`). Nothing after it depends on `ball_*`.

- [ ] **Step 6: Unconditionally paint the sprite (drop the `if show_pikachu:` wrapper) + renumber comments**

The sprite-paint block currently reads (comment `# 6. Paint sprite pixels ...`) and is wrapped in `if show_pikachu:`. Replace that block with the following (de-indented out of the `if`, renumbered to step 5, and with the "pokeball case" phrasing reworded):

```python
    # 5. Paint sprite pixels to the native physical canvas (skip-black).
    #    Before painting, blacken the sprite's bounding box so transparent
    #    (alpha=0) regions read as black instead of revealing the trail
    #    color underneath. Skip the bbox black-fill when the trail is
    #    already black across the sprite's bbox (black-trail case) — saves
    #    ~5600 SetPixel calls per frame on the bigsign. Still needed for the
    #    rainbow trail (must convert to black under the sprite) and
    #    trail="none" (prevents text bleed).
    if sprite.trail != "black":
        bbox_x_start = max(0, sprite_x)
        bbox_x_end = min(panel_w, sprite_x + sprite.width)
        bbox_y_start = max(0, sprite_y)
        bbox_y_end = min(panel_h, sprite_y + sprite.height)
        for y in range(bbox_y_start, bbox_y_end):
            for x in range(bbox_x_start, bbox_x_end):
                set_px(x, y, 0, 0, 0)
    # Sprite paint. We only x-clip — y is invariantly in-bounds because
    # `_decode` forces `new_h = panel_h` and `sprite_y = (panel_h -
    # sprite.height) // 2 = 0`, so `sprite_y + y ∈ [0, panel_h)`. If a
    # future change decouples sprite.height from panel_h (e.g. a
    # `fit="letterbox"` mode), add a `0 <= ry < panel_h` guard.
    for x, y, r, g, b in sprite.non_black[frame_idx]:
        rx = sprite_x + x
        if 0 <= rx < panel_w:
            set_px(rx, sprite_y + y, r, g, b)
```

Then the existing `# 7. At t>=0.95, snap to incoming ...` block follows unchanged — renumber its leading comment from `# 7.` to `# 6.`.

- [ ] **Step 7: Rewrite the `render_hires_frame` docstring + remove the now-stale narrative comments**

Replace the `render_hires_frame` docstring (currently mentions `NyanCat`/`Pokeball`) with:
```python
    """Paint one frame of a hi-res sprite traversing the panel, leaving a trail.

    Generic sprite-trail infra: a single sprite (from `spec`) moves
    horizontally across a `ScaledCanvas`, a trail fills behind its leading
    edge to erase outgoing content, and the frame snaps to `incoming` near
    t=1.0. Used by external sprite-trail transition plugins (e.g.
    led-ticker-arcade's nyancat / pokeball). No entity-specific logic.
    """
```
Also update the module docstring at the top of the file (L9-11) — replace the sentence naming `NyanCat`, `NyanCatReverse`, `Pokeball`, `PokeballReverse` with: `` `render_hires_frame` paints a single sprite that traverses horizontally leaving a trail and snaps to incoming near t=1.0; it is consumed by external sprite-trail transition plugins. `` Remove any remaining inline comment text that narrates the procedural ball / `show_pokeball` / `show_pikachu` convention (the comment lines that referenced "Pokeball layout", "The procedural ball is opt-in", "for the pokeball family", "pokeball the leading edge is the ball's far side"). The CAUTION comment about `unwrap_to_real` stays but reword "the dispatch in nyancat.py / pokeball.py" to "the transition's own dispatch".

- [ ] **Step 8: Remove the now-unused `import math`**

Confirm no `math.` remains in the file, then delete the `import math` line (L15):
```bash
cd /Users/james/projects/github/jamesawesome/led-ticker
grep -n "math\." src/led_ticker/transitions/_hires_loader.py || echo "no math usage — safe to drop import"
```
Expected: `no math usage — safe to drop import`. Then delete the `import math` line.

- [ ] **Step 9: Delete the retained-hook smoke test**

In `tests/test_hires_loader.py`, delete the method `test_render_hires_frame_honors_show_pokeball_and_pikachu` (L230-248 — the `def` through its `assert lit > 0`, plus the two-comment preamble `# Retained public hook: ...`). Delete the trailing blank line so the following `class TestRenderHiresTrail:` keeps correct spacing. Do NOT touch any other test.

- [ ] **Step 10: Run the suite — the regression net must be green**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker
make test 2>&1 | tail -15
```
Expected: PASS. The only removed test is the smoke test; every trail/sprite/snap/decode test passes UNCHANGED, proving the sprite-leads path is byte-identical. If any retained test fails, the refactor changed live behavior — STOP and reconcile (do not adjust the retained tests to fit).

- [ ] **Step 11: Lint**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker
make lint 2>&1 | tail -15
```
Expected: clean (catches a stray unused name / the dropped `math` import). If ruff flags formatting, run `make format` and re-run `make lint`.

- [ ] **Step 12: Stage**

`git add -A` for `src/led_ticker/transitions/_hires_loader.py` + `tests/test_hires_loader.py`. STOP — controller commits (`feat: remove dormant procedural pokeball from render_hires_frame`).

---

### Task 2: Reframe the stale docs + CLAUDE.md

**Files:**
- Modify: `docs/site/src/content/docs/plugins/api-reference.mdx:192`
- Audit: `docs/content-source/transitions/sprite.md`, `docs/site/src/content/docs/transitions/sprite.mdx`, `docs/site/src/content/docs/transitions/index.mdx`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Fix the stale core-API line**

In `docs/site/src/content/docs/plugins/api-reference.mdx`, line 192, the `render_hires_frame` table row ends with:
```
(use on a `ScaledCanvas`; pass `show_pokeball=True` for a procedural leading ball)
```
Remove the `show_pokeball` clause so it reads:
```
(use on a `ScaledCanvas`)
```
Keep the rest of the row (the signature `render_hires_frame(t, canvas, outgoing, incoming, spec, **kwargs)` and the "Paint one frame of a hi-res sprite traversing the panel for the given `HiresSpec`" description) unchanged — the signature itself did not change, so `test_docs_plugin_api_drift.py` stays green.

- [ ] **Step 2: Audit the three plugin-facing docs (likely no change)**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker
grep -n "show_pokeball\|show_pikachu" docs/content-source/transitions/sprite.md docs/site/src/content/docs/transitions/sprite.mdx docs/site/src/content/docs/transitions/index.mdx
```
For each hit, confirm it describes `show_*` as **arcade plugin** (`arcade.pokeball`) config and user-facing behavior (which the pre-render approach preserves: `show_pokeball=false` → Pikachu-only, `show_pikachu=false` → ball-only). Expected state — already correct, no edit:
- `sprite.md:22-23` — knob table for the arcade pokeball; the knobs still work via `extra`. Keep.
- `sprite.mdx:29` — image caption "arcade.pokeball — single-sprite modes via show_pikachu / show_pokeball". Keep.
- `index.mdx:65` — "toggle sprite elements on the `arcade.pokeball` family (led-ticker-arcade plugin)". Keep.
If (and only if) any of these asserts `show_*` is a core `render_hires_frame` mechanism, reword that clause to "arcade pokeball config (set in TOML, passed via `extra`)". Otherwise make NO edit.

- [ ] **Step 3: Update CLAUDE.md — "Hi-res transitions" invariant**

Open `CLAUDE.md` and find the **Hi-res transitions** load-bearing-invariant paragraph (under "Load-bearing invariants by subsystem"). Remove any sentence describing the procedural pokeball ball / `show_pokeball` / `show_pikachu` as a core mechanism inside `render_hires_frame`, and ensure it states that `render_hires_frame` / `HiresSpec` / `_hires_loader.py` are **generic** sprite-trail infra (a sprite traverses leaving a trail; no entity-specific code) consumed by external plugins (led-ticker-arcade, led-ticker-baseball). Keep the `HiresSpec.trail` / `TRAIL_SATURATION_T` / `SNAP_THRESHOLD` facts.

- [ ] **Step 4: Update CLAUDE.md — "Extracted widgets retain core hooks"**

In the **Extracted widgets retain core hooks** paragraph, if the pokeball procedural ball / `show_pokeball` is listed as a retained hook, remove it (it is no longer retained). Leave the other retained hooks — `_DISPATCH_APPLICABLE_TYPES`, `lazy_palette`, `GEOMETRIC_SHAPES`, `small_font` — untouched.

- [ ] **Step 5: Docs lint + drift tests**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker
make docs-lint 2>&1 | tail -15
make test 2>&1 | tail -8
```
Expected: `make docs-lint` clean (run `make docs-format` then re-run if prettier reformats the `.mdx`); `make test` still PASSES — specifically `test_docs_plugin_api_drift.py` and `test_docs_config_options_drift.py` green (the api-reference signature is unchanged; only prose was removed).

- [ ] **Step 6: Stage**

`git add -A` for the touched docs + `CLAUDE.md`. STOP — controller commits (`docs: reframe show_pokeball/show_pikachu as arcade plugin config`).

---

## Notes for the executor
- This is a **deletion**, not a feature: the "test" is the existing suite. The retained `tests/test_hires_loader.py` cases are the proof of behavior-preservation — they must pass UNCHANGED. Never edit a retained test to make it pass; if one fails, the refactor altered live behavior.
- Touch ONLY the files named per task. Do NOT touch `plugins_catalog.json`, `transitions/__init__.py` (migration hints are correct), or the `test_config.py`/drift `extra`-passthrough assertions (they test the generic mechanism, not the deleted core ball).
- Subagents stage with `git add -A` and STOP; the controller commits after spec + quality review.
