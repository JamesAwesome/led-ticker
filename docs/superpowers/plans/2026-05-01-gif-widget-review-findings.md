# GIF widget — review findings

Aggregated from six parallel reviewers (hot-path perf, DRY, API/naming, test
effectiveness, documentation, holistic spec compliance).

**Bottom line:** holistic reviewer says **ship-ready** — no correctness or
hardware-constraint violations. Five other reviewers found a long list of
should-fixes ranging from a real performance win (~20×) to misleading docs.

## Pre-merge — recommended actions

In priority order. The first five are "fix before merge"; the rest could go
either way.

### 1. Performance: use `canvas.SetImage` for full-frame paint

**Severity:** big perf win on bigsign (~20× hot path).
**Location:** `src/led_ticker/widgets/gif.py:_paint_full` (line 109).

Today's triple-nested Python loop hits 16,384 iterations × 3 indexed bytes
reads × 1 SetPixel call per frame. The real `rgbmatrix` library exposes
`canvas.SetImage(pil_image, 0, 0)` — a single C call that pushes the whole
RGB buffer. Cache a `PIL.Image` per frame at decode time
(`frames.append((pil_rgb, fitted_bytes, duration))`), use it in `_paint_full`.
For `_paint_skip_black`, pre-compute a flat list of non-black `(x, y, r, g, b)`
tuples at decode time and iterate that — typically 30–60% the pixel count.

Test stub: add `SetImage` to `tests/stubs/rgbmatrix/__init__.py`.

### 2. Add range validation to numeric fields

**Severity:** silent footgun.
**Location:** `GifPlayer.__attrs_post_init__`.

Today: `text_scale = 0` silently behaves like 1; `text_scale = -1` crashes
deep inside `ScaledCanvas`; `loops = 0` is silently rewritten to 1 by
`max(1, …)`; `scroll_speed_ms = -10` falls back to 20 silently. Add explicit
`raise ValueError` for `text_scale < 1`, `loops < 1`, `text_loops < 0`,
`scroll_speed_ms < MIN_SCROLL_SPEED_MS`. Move `text_align` validation out of
the `if self.text` guard for symmetry with `gif_align`.

Also: `text_loops > 0` with static `text_align ∈ ("left", "right")` is
silently ignored. Either raise in `__attrs_post_init__` or honor it as a
generic minimum-playback-ticks floor.

### 3. Unify the ScaledCanvas unwrap strategy

**Severity:** latent footgun (no current bug, but inconsistent).
**Location:** `gif.py::_real_canvas` (single-level), `ticker.py::_play_widget`
(recursive), `ticker.py::_run_gif` (recursive).

Three different unwrap shapes for the same operation. The single-level one
in `gif.py` would silently miss a nested wrapper if anything ever creates
one. Add `unwrap_to_real(canvas)` to `src/led_ticker/scaled_canvas.py`:

```python
def unwrap_to_real(canvas):
    while isinstance(canvas, ScaledCanvas):
        canvas = canvas.real
    return canvas
```

Replace all three sites. Keep `_play_widget`'s `innermost` pointer separately
for the rebind step.

### 4. Five missing tests (one is the actual user config)

**Severity:** real regression risk.

- **`_frame_for_elapsed` direct unit test** — zero coverage today. Boundary
  bugs (`< cum` vs `<= cum`, wrap at exactly `loop_ms`) ship green. Add a
  param test with synthetic 3-frame data.
- **Scroll wrap-around** — neither
  `test_play_scroll_text_advances_position` (5 ticks) nor
  `test_play_scroll_text_visible_through_black_pillars` (one tick) ever sees
  `scroll_pos` reset to `text_w`. Off-by-one in the wrap condition ships
  green. Run for `(text_w + text_width + 5)` ticks and assert wrap occurs.
- **Emoji × text_scale > 1 × scroll** — each axis individually tested but
  not the combination, which is the actual user-config (Section 15 in
  `config.gif_test.example.toml`).
- **Static-text overflow clamp** — `text_x_right = max(2, …)` (gif.py:274)
  is never exercised with text wider than canvas. Drop the `max` and tests
  still pass.
- **Cross-scale dissolve into a `play()` widget** — `run_transition` with
  `incoming_scale=N` followed by `widget.play()` is the actual on-hardware
  path; only mock-widget tests cover the dissolve change.

### 5. CLAUDE.md gaps

**Severity:** docs that mislead future-us.

Four missing sections:
- **Package Layout** doesn't mention `widgets/gif.py` or
  `widgets/_gif_decode.py`.
- The "paint native pixels via `canvas.real`" pattern (now used by gif
  AND the Dissolve fix) isn't documented.
- The play() dispatch in `_run_swap` (`_has_play` / `_play_widget` /
  `_show_one`) isn't documented.
- Two new hardware constraints (#10 text-canvas rebind, #11 dissolve at
  physical resolution) aren't in the CRITICAL section.

Also tiny: gif.py line 54 inline comment is missing `"scroll_over"`.

## Pre-merge — quick wins (low cost, do all)

- `_validate_choice(name, val, allowed)` helper to collapse 4 near-identical
  validation sites in `gif.py` and `_gif_decode.py`. (DRY reviewer.)
- Magic `2` margin → `_TEXT_EDGE_PADDING_PX` constant (used twice
  consecutively in `_play_with_text`). (DRY reviewer.)
- Tighten `test_text_loops_extends_section_duration` from `>= 524` to
  `524 <= count <= 525`. (Test reviewer.)
- Loosen `test_play_uses_per_frame_durations` and friends from `len == N` to
  `len >= N`, plus a separate cap test. (Test reviewer.)
- Move sample point in `test_transparent_pixels_become_black_not_palette_color`
  from `px(20, 5)` to `px(2, 2)` for Lanczos-bleed safety. (Test reviewer.)

## Should-fix — pick & choose

- **Rename `loops` → `gif_loops`** for symmetry with `text_loops` and
  visible distinction from section `loop_count`. Breaking change for any
  config files using `loops = N`; we'd need to update both example configs.
  (API reviewer.)
- **Unify `gif_align` (widget) with `h_align` (decode kwarg)** — pick one.
  (API reviewer.)
- **Smarter `text_align` default** — currently `"right"` regardless of
  `gif_align`, which overlaps the gif when `gif_align = "center"` (the
  default). Either default to `"scroll_over"` or compute from `gif_align`
  (left gif → right text, right gif → left text). (API reviewer.)
- **`font` field** — publicly settable on every widget but unusable from
  TOML. Make private (`_font`) or add a string-factory mapping.
  (API reviewer; same issue exists on `TickerMessage`.)
- **Spec/plan archival** — `docs/superpowers/specs/2026-05-01-gif-widget-design.md`
  explicitly says "Non-goals: per-row blending of GIFs with text" — which
  the current code does via `text_align="scroll"`. Either move both
  spec+plan to `docs/superpowers/archive/` with a one-line note, or add a
  post-merge addendum. (Documentation reviewer.)
- **Schema-at-a-glance doc** — no single place lists every GifPlayer field
  with type + default + valid values + interactions. Add a docstring block
  at the top of `gif.py` or a `docs/widgets/gif.md`. Same gap exists for
  most widgets. (API reviewer.)
- **`_render_tick` extraction** — `_play_with_text` is 85 lines with three
  branches. Extract a per-tick helper to flatten. (Holistic reviewer.)
- **`run_gif` docstring** — currently says it "Skip[s] the section title";
  more accurate: "`mode = "gif"` suppresses titles entirely; for title +
  gif use `mode = "swap"`." (Documentation reviewer.)

## Defer / nice-to-have

These are real but low-value relative to the work — flag for a follow-up:

- Vertical text alignment (`text_valign: top|center|bottom`).
- Scroll direction (right-to-left only today).
- `_MIN_FRAME_DURATION_MS` clamp is silent — log on first hit.
- `padding = 0` on `GifPlayer` is for protocol compliance only — make
  `init=False` to remove from public surface.
- Per-fit `h_align` for non-pillarbox modes is silently ignored — works
  fine but worth a test asserting the no-op behavior.
- `struct.iter_unpack` micro-optimization on `_paint_*` if `SetImage` route
  is rejected — only matters as a fallback.
- `_play_widget` test uses `mock.MagicMock` instead of `_StubCanvas` — works
  but a real canvas would catch attribute-access bugs.

## Considered & rejected (for record)

- **Collapse `_play_no_text` and `_play_with_text` into one path** — DRY
  reviewer evaluated and recommended against. The no-text fast path uses
  the gif's native frame-duration cadence; collapsing would force the
  slower scroll-cadence loop on the no-text path, regressing the simple
  case. Net loss in clarity.
- **Move `_has_play` / `_play_widget` from `ticker.py` to `widget.py`** —
  DRY reviewer evaluated and recommended against. The helpers are tightly
  coupled to ticker's canvas-wrapper bookkeeping; moving them would drag
  `ScaledCanvas` into the protocol module for no caller benefit.
- **Refactor `_apply_fit` into a generic helper** — DRY reviewer evaluated
  and recommended against. The four branches are linear and clear; the
  shared `_flatten_onto_black` already covers the actual duplication.
