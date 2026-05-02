# Still-image — review findings

Aggregated from six parallel reviewers (hot-path perf, DRY, API/naming,
test effectiveness, documentation, holistic spec compliance).

**Bottom line:** holistic reviewer says **ship-ready** — no correctness or
hardware-constraint violations. Other reviewers found a meaningful punch list
focused on (1) a real perf win for static text, (2) a sizable DRY refactor
opportunity, (3) one naming change worth doing now, and (4) several hidden
footguns + test gaps.

## Pre-merge — recommended actions, priority order

### 1. Static-text fast path (perf win)

**Severity:** ~100× redundant draws on the hot path for static text.
**Location:** `still.py:_play_with_text` (gate the per-tick loop when
text_align is left/right and text_loops is 0).

For non-scrolling text, `_play_with_text` redraws an identical frame every
tick — the image, text x, baseline are all constant. Fast-path:

```python
scrolling = self.text_align in ("scroll", "scroll_over")
if not scrolling and self.text_loops == 0:
    self._render_tick(canvas, text_canvas, scroll_pos, baseline_y,
                      text_x_left, text_x_right)
    canvas = frame.matrix.SwapOnVSync(canvas)
    await asyncio.sleep(self.hold_seconds)
    return canvas
```

Same opportunity exists in `gif.py` for the (rare) static-text + 1-frame-gif
edge case — fix in lockstep.

### 2. DRY refactor — extract `_BaseImageWidget`

**Severity:** ~150 duplicate lines between `gif.py` and `still.py`; schema
drift risk grows with each future field.
**Location:** new `src/led_ticker/widgets/_image_base.py`; both widgets
inherit.

Reviewer recommends extracting an attrs base class with:
- All shared module constants (`_VALID_TEXT_ALIGNS`,
  `_VALID_TEXT_VALIGNS`, `_VALID_SCROLL_DIRECTIONS`,
  `_AUTO_TEXT_ALIGN_FOR_GIF`, `_EMOJI_PATTERN`, `_TEXT_EDGE_PADDING_PX`,
  `_MIN_SCROLL_SPEED_MS`)
- Fields: `text`, `text_align`, `text_valign`, `text_y_offset`,
  `text_x_offset`, `scroll_direction`, `font_color`, `scroll_speed_ms`,
  `text_scale`, `text_loops`, `font`, `padding`, `_panel_w`, `_panel_h`
- Methods: `_baseline_y`, `_has_emoji`, `_measure_text`, `_draw_text`,
  `_render_tick` (parameterized on a `paint_full_fn` callable),
  `_play_with_text` (parameterized on a `frame_chooser` callable +
  `tick_budget` hook), shared validation helper
- Subclass-specific stays: `path`, `fit`, `gif_align`, decode glue,
  `_paint_full` / `_paint_skip_black` signatures, `_play_no_text`,
  `draw`, plus per-widget extras (gif: `gif_loops` + frame state;
  still: `hold_seconds` + `_pixels` + `_pil_image`)

DRY reviewer's argument: "this is exactly the threshold where the prior
'don't extract for one widget' recommendation flips" — at 2 widgets sharing
~150 lines, extraction wins on clarity AND prevents drift.

Also fold in: rename `_VALID_FITS` / `_VALID_GIF_ALIGNS` (drop the
underscore prefix — they're imported by name from 4 modules so the
"private" signal is a lie). Inline `_still_decode.py` into `still.py`
(only 8 lines of real logic). Keep `_gif_decode.py` separate
(meaningful logic with frame-duration clamp + logging).

### 3. Rename `gif_align` → `image_align` on both widgets

**Severity:** name lies on `StillImage` (alignment of an *image*, not a
gif).
**Location:** both widgets + `_image_fit.py` + `decode_still` + decode_gif
kwarg + example configs.

Add `image_align` as canonical, keep `gif_align` as a deprecated alias
that emits `DeprecationWarning` for one release. Same for
`_AUTO_TEXT_ALIGN_FOR_GIF` → `_AUTO_TEXT_ALIGN_FOR_IMAGE`. Worth the
cross-widget churn since the name is wrong on *both* widgets — `gif_align`
always described image placement.

### 4. Add explicit footgun validation

**Severity:** silent failures users won't catch.
**Locations:** `__attrs_post_init__` on both widgets.

Three new validators:

- **`text_align = "scroll"` + `fit = "stretch"`** → no transparent
  regions, text is invisible. Raise: "scroll text needs transparent /
  pillarbox regions to show through; got fit=stretch."
- **`hold_seconds = 0`** → instant flash; semantics undefined.
  Raise: "hold_seconds must be ≥ 0.05; for marquee-driven duration,
  use text_loops > 0 with hold_seconds=0.05".
- **`text_x_offset != 0` + scroll mode** → silent no-op (offset is only
  applied to static positions). Raise: "text_x_offset only applies to
  static text_align=left/right; got text_align=scroll".

Plus a low-stakes extra: validate `text_align` even when `text=""`
(currently the validator skips, so `text_align="bogus"` + `text=""`
silently accepts). Same gap exists in `gif.py` — fix both.

### 5. Five missing tests + two over-specifications

**Severity:** real regression risk on the test gaps; flaky assertions on
the over-specs.

- **Scroll wrap-around in both directions** — neither default-left nor
  the explicit-right test exercises the reset condition; off-by-one in
  `<= 0` vs `< 0` ships green.
- **`_play_no_text` doesn't verify SwapOnVSync return capture** —
  uses MagicMock with `side_effect=lambda c: c`. Use the
  `swapping_frame` fixture from `tests/conftest.py` so a dropped
  capture would fail.
- **`_load` re-decode on panel-size change** — currently
  `if self._pixels: return` short-circuits; if the same widget is
  used across small sign + bigsign sections, the second size is silently
  served stale bytes. Add a test calling `_load(256, 64)` then
  `_load(160, 16)`.
- **Fit × gif_align matrix for stills** — only stretch + pillarbox
  center are tested. Mirror the gif-decode matrix tests.
- **`hold_seconds = 0` edge case** — both paths have edge math;
  `n_ticks = max(1, 0) = 1` works today but a refactor dropping the
  `max(1, ...)` floor would silently produce a 0-iteration loop.
- **Real-asset smoke tests skip silently on CI** —
  `if not asset.exists(): pytest.skip(...)` means missing assets pass
  green. Either `pytest.fail` in CI mode or commit small fixture PNGs
  to `tests/fixtures/`.

Over-specifications to relax:
- `test_top_valign_paints_at_panel_top_with_text_scale_2`: drop
  `seen_canvases[0].height == 32` (couples to implementation choice).
  Keep the `seen_y[0] == 10` behavioral assertion.
- `test_play_with_text_text_loops_extends_duration`: replace
  `524 <= count <= 525` with floor + ceiling that doesn't pin the exact
  formula.

Bonus: `test_animated_gif_uses_first_frame_only` doesn't actually verify
the `seek(0)` call — Pillow returns frame 0 by default. Either monkey-patch
`Image.seek` to record calls, or build a multi-frame gif where iteration
order matters.

## Quick wins (low cost, high signal — do all)

- **Hardware constraints #10 / #11 in CLAUDE.md** currently reference only
  `GifPlayer` / `Dissolve`. Add "applies equally to StillImage" — the
  `_play_with_text` rebind dance is the same.
- **Schema docstring parity** in `still.py`: align field descriptions with
  `gif.py`'s wording (especially `scroll_direction` enters-from / exits-to
  framing), add a "Constraints validated at construction" block.
- **`hold_seconds` description** should mention `text_loops` as second
  floor: `n_ticks = max(hold_seconds_ticks, text_loops × traversal)`.
- **Reciprocal cross-references** in `gif.py` and `still.py` module
  docstrings so a reader of either finds the sibling.
- **CLAUDE.md StillImage paragraph** add `text_y_offset` / `text_x_offset`
  + the `content_height = panel_h // scale` wrapper trick.
- **Section 10 index comment** in `config.image_test.example.toml` should
  call out `text_y_offset = -2`. Add a Section 11 that demos
  `text_x_offset`.
- **Drop `del loop_count`** in `StillImage.play` and document instead in
  the docstring that `gif_loops` / `loops` are no-ops on stills.
- **Hoist `text_is_wrapped = isinstance(text_canvas, ScaledCanvas)`** out
  of the per-tick loop in both widgets.
- **Hoist `tick_seconds = tick_ms / 1000`** out of the per-tick
  `asyncio.sleep` call.

## Defer / nice-to-have

- **`text_scale` upper bound** validated at first paint
  (`panel_h // text_scale >= 12` so the BDF cell fits).
- **Cookbook / recipes block** in CLAUDE.md or both widget docstrings
  showing common patterns (image-left + caption-right; fullscreen +
  bottom marquee; transparent silhouette + scroll-under; knockout text).
  This was deferred from the gif-widget review too.
- **Non-divisible `text_scale`** (e.g. 3 on 64-tall panel → 21 + 1 row
  letterbox) — bottom-valign drifts up to (scale-1) px from panel edge.
  Either reject non-divisible scales or document the gap.
- **`_paint_skip_black` direct unit test** for stills (currently only
  exercised via `text_align="scroll"`).
- **`text_x_offset` + `text_y_offset` combined test** — each tested
  individually; combo not pinned.
- **`struct.iter_unpack`** optimization in `_ensure_paint_caches` — runs
  once per widget, off the hot path. Cosmetic.

## Considered & rejected (for record)

- **Inline `_gif_decode.py`** — DRY reviewer evaluated and recommended
  against. Frame-duration clamp + logging makes it substantive enough
  to keep separate.
- **Collapse `_play_no_text` paths** — trivially small in still
  (5 lines), structurally different from the with-text path. Keep.
- **`_still_decode.py` as a separate file** — DRY reviewer said inline.
  Up for debate; the docstring framing of "this is the public decode
  helper" might be worth keeping a separate file for. User call.
