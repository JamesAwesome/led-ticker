# Still-image — re-review findings (after first round of fixes)

Aggregated from six parallel re-reviewers. Branch state: still-image @ 80949ce.

## Ship-blocker

**Static-text fast path freezes multi-frame GIFs.** Holistic reviewer caught it.
`_BaseImageWidget._play_with_text` short-circuits to "paint once + sleep" when
`text_align ∈ (left, right)` and `text_loops == 0`. Correct for stills (one
frame) but breaks gifs (frames stop advancing). Pre-refactor, gif's per-tick
loop always called `_frame_for_elapsed` to advance frames.

**Test gap:** `test_play_static_right_text_overlays_gif` and friends all use
single-frame fixtures; the cadence test uses `scroll_over` (sidestepping the
fast-path entirely).

**Fix:** add a `_is_static() -> bool` hook on the base. `StillImage` returns
`True`; `GifPlayer` returns `len(self._frames) <= 1`. Gate the fast path on
that hook AND-ed with the existing condition. Add a regression test:
2-frame gif + `text_align="left"` over a long enough hold, assert
`_current_frame_idx` advances past 0.

## Should-fix (post-blocker)

- **Delete dead `warn_deprecated_gif_align`** in `_image_base.py:345`. Defined
  but never called; we explicitly chose no-alias rename. Drop the helper +
  the `warnings` import.
- **Rename `VALID_GIF_ALIGNS` → `VALID_IMAGE_ALIGNS`** in `_image_fit.py`.
  Three reviewers flagged this — the name lies (validates `image_align`).
- **Fast-path swap-capture test** — `_play_with_text`'s static fast path has
  a `frame.matrix.SwapOnVSync(canvas)` call that needs the same return-capture
  guarantee as the per-tick loop. No test pins it. Use `swapping_frame`-style
  fake.
- **Wrapper-rebind back-buffer-follow at `text_scale > 1`** — current
  `text_canvas_follows_back_buffer` test only runs at `text_scale=1`. The
  wrapper branch (`text_canvas.real = canvas`) has no direct test.
- **`ticks_per_text_loop` at `text_scale > 1`** — formula uses logical width
  `text_w + text_width`; a regression to physical `canvas.width` would halve
  duration at scale=2 silently.
- **`text_scale` upper bound on multiple panel sizes** — current test only
  covers `panel_h=64`. Parametrize over panel sizes to pin the
  `panel_h // text_scale >= 12` invariant.
- **Wrap-around: assert which TICK fires the wrap.** Current tests assert the
  value AT the wrap; a regression flipping `<= 0` to `< 0` could still pass.
  Also assert the pre-wrap tick had value `-text_width` (left) or `text_w`
  (right).
- **Stale test name:** `test_no_text_skips_align_validation` is now factually
  wrong (validation no longer skipped when text=""). Rename + add positive
  test asserting bogus values raise even with empty text.
- **No dedicated test for `text_align="scroll" + fit="stretch"` raising** —
  only exercised indirectly. Add a 3-line test.
- **Schema docstring missing the runtime `panel_h // text_scale >= 12`
  constraint** in both `gif.py` and `still.py`.
- **CLAUDE.md missing the `text_scale` upper-bound footgun** in the validator
  list and missing the `_pick_frame_for_elapsed` hook in the subclass-hook
  description.

## Perf nits (low impact, all hot-path)

- `_pick_frame_for_elapsed` recomputes `loop_ms = sum(d for _, d in self._frames)`
  every tick. Cache once on `_load`.
- `_has_emoji()` runs `EMOJI_PATTERN.search(self.text)` per tick via
  `_render_tick → _draw_text`. `self.text` is invariant — cache once.
- `_ensure_paint_caches()` early-return called from each `_paint_*` per tick.
  Hoist to a one-time call before the loop in `_play_with_text`.

## DRY follow-ups (small, post-base-class)

- `_scan_non_black(pixels, w, h) -> list[(x,y,r,g,b)]` shared in
  `_image_fit.py`. Both `_ensure_paint_caches` impls have byte-for-byte
  identical inner loop.
- `tick_ms = max(MIN_SCROLL_SPEED_MS, scroll_speed_ms)` formula in 3
  places (gif play, still play, base play_with_text). Hoist to base
  property.
- `panel_w/h <= 0` defaulting block at top of both `_load`s. Shared
  helper `_resolve_panel_dims`.
- `still.py:249` does function-local import of `MIN_SCROLL_SPEED_MS`;
  gif imports at module top. Stylistic inconsistency (resolved once
  the tick_ms hoist lands).
- `_validate_common` validates `image_align` but not `fit` — fit
  validation is duplicated in each decoder. Pick one home.

## Doc nits

- CLAUDE.md GIF+StillImage paragraph: add `text_h >= 12 (text_scale upper
  bound)` to the footgun list; add `_pick_frame_for_elapsed (default
  no-op)` to the subclass-hook list.
- `still.py` schema docstring missing the `text_align="auto"` resolution
  explanation that `gif.py` has.
- `gif.py:66-67` references "CLAUDE.md 'GIF widget'" — that header no
  longer exists; now unified.

## Test cleanup (consolidation)

Most tests now live twice (gif + still) since they exercise base-class
behavior. Could extract a `tests/test_widgets/test_image_base.py` with a
minimal test subclass and dedupe `_baseline_y`/`text_y_offset`/
`text_x_offset`/`text_x_offset_with_scroll_raises`/`text_loops_with_static`/
`scroll_direction_right`/the parametrized baseline cases. Worth doing
to reduce ongoing maintenance cost.

## Considered & deferred

- Recipes / cookbook section: skip — example TOMLs already serve as
  executable cookbooks. (3 reviewers agreed.)
- struct.iter_unpack micro-opt for `_ensure_paint_caches`: skip — runs
  once per decode, sub-ms.
- `non-divisible text_scale` clamp/warn: skip — practically nobody uses
  scale=3 on a 64-tall panel.
