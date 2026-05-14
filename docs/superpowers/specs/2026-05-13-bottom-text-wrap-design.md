# Design: `bottom_text_wrap` for two-row mode

**Date:** 2026-05-13
**Status:** Approved

## Overview

Extend the v1 `text_wrap` feature (single-row marquee on `gif` / `image` widgets, merged in PR #58) to two-row mode. Three new fields on the bottom row of:

- `_BaseImageWidget` (when `bottom_text` is set — two-row image text overlay)
- `TwoRowMessage` (the standalone two-row widget)

The fields turn the bottom-row marquee into a seamless wrap with a configurable separator between repeats. Top row remains held; only bottom row wraps. v1's `text_wrap` knobs stay single-row-only.

The motivating case: a TwoRowMessage with a brief held title on top (`@moonbunny`) and a longer slogan on the bottom (`tap to subscribe`) — wrap mode keeps the slogan continuously visible instead of leaving the bottom canvas empty between off-right→off-left passes.

## Field surface

Three new `kw_only` attrs fields, applied identically to both `_BaseImageWidget` and `TwoRowMessage`:

```toml
# Two-row image widget
[[playlist.section.widget]]
type = "image"
path = "config/assets/bunny-transparent.png"
top_text = "BREAKING"
bottom_text = "tap to subscribe"
bottom_text_wrap = true
bottom_text_separator = " * "
bottom_text_separator_color = "rainbow"

# TwoRowMessage standalone
[[playlist.section.widget]]
type = "two_row"
top_text = "BREAKING"
bottom_text = "tap to subscribe"
bottom_text_wrap = true
bottom_text_separator = " * "
bottom_text_separator_color = "rainbow"
```

- **Types:**
  - `bottom_text_wrap: bool = False`
  - `bottom_text_separator: str | None = None`
  - `bottom_text_separator_color: Any | None = None`
- **Defaults:** all falsy / `None` — zero behavior change for existing two-row configs.
- **Naming convention:** mirrors the existing `top_*` / `bottom_*` prefix used everywhere in two-row knobs (`top_color`, `bottom_color`, `bottom_align`, `bottom_font`). v1's unprefixed `text_wrap` / `text_separator` / `text_separator_color` stay single-row-only; they remain refused in two-row mode by the existing validation.

### Literal-text semantics

`bottom_text_separator` follows the v1 / forever_scroll convention:

| TOML | Rendered text |
| --- | --- |
| (unset / `None`) | `" • "` (default bullet) |
| `bottom_text_separator = ""` | `"  "` (two-space minimum gap so adjacent copies don't visually butt up) |
| `bottom_text_separator = " * "` | `" * "` (as-is) |

### Color inheritance

`bottom_text_separator_color = None` inherits `bottom_color` (the bottom-row color), NOT `font_color`. This matches how other `bottom_*` knobs cascade in the two-row design — the separator is a piece of the bottom row, so it inherits the bottom row's color.

When set explicitly to a `ColorProvider` (constant / `"rainbow"` / `"color_cycle"` / `{style = "gradient", ...}`), the separator uses its own provider with its own per-effect frame counter. Continuous-phase providers (Rainbow, ColorCycle) stay in phase with the bottom row by reading the counter, not restarting on visit.

### Always-wrap semantics

When `bottom_text_wrap = True`, the bottom row wraps continuously **regardless of whether the text fits the canvas**. Even a short string that would normally be held at `bottom_align` gets the wrap treatment — chases itself across the canvas with the separator between copies. Predictable: setting the flag always changes behavior.

This contrasts with the default two-row behavior, where the bottom row is held when `bottom_width <= canvas_w` and only auto-scrolls when it overflows.

## Validation

Config-load errors mirror v1's pattern. In `_validate_common` (for image widgets) and `__attrs_post_init__` (for TwoRowMessage):

| Trigger | Error |
|---|---|
| `bottom_text_wrap=True` AND `bottom_text == ""` | `ValueError: bottom_text_wrap=True requires non-empty bottom_text` |
| `bottom_text_wrap=True` on a non-two-row image widget (no `bottom_text`) | `ValueError: bottom_text_wrap is only valid in two-row mode (bottom_text non-empty); use text_wrap for single-row marquees` |
| `bottom_text_separator` set without `bottom_text_wrap=True` | `ValueError: bottom_text_separator requires bottom_text_wrap=True` |
| `bottom_text_separator_color` set without `bottom_text_wrap=True` | `ValueError: bottom_text_separator_color requires bottom_text_wrap=True` |

**Cross-mode hygiene:**
- The existing v1 validation refuses `text_wrap=True` when `bottom_text` is set. Sharpen the error message to mention `bottom_text_wrap` as the right knob.
- No `top_text_wrap` field is introduced — the top row never wraps.

**Upfront `_build_widget` guard** (in `app.py`, mirroring v1's pattern for `text_wrap`):
- `bottom_text_wrap` / `bottom_text_separator` / `bottom_text_separator_color` are only valid on `gif`, `image`, and `two_row`. On other widget types (`message`, `weather`, `countdown`, etc.), drop falsy/None values silently and raise `ValueError` on truthy values.
- `bottom_text_separator_color` joins `_PROVIDER_COLOR_KEYS` (for TOML coercion to a `ColorProvider`).
- `bottom_text_separator_color` joins `_FrameAware._EFFECT_ATTRS` (for its own per-effect frame counter).

## Implementation architecture

The two widgets diverge structurally — image two-row owns its tick loop via `_play_with_two_row_text`; TwoRowMessage delegates scroll to the engine's `_swap_and_scroll`.

### Image two-row (`_BaseImageWidget._play_with_two_row_text`)

Wrap math lives inside the play method, mirroring v1 single-row's approach.

- Reuse v1 helpers: `_resolved_separator_text`, `_measure_separator`, `_draw_separator` (already implemented; v2 doesn't add new generic helpers — see note below).
- New helper `_render_two_row_wrap_tick` mirrors `_render_wrap_tick` but composes with the existing `_render_two_row_tick`'s top-row paint (top stays held; bottom is wrap-chained).
- Compute `cycle_width = bottom_width + sep_width` once outside the loop.
- When `bottom_text_wrap=True`, override the existing `bottom_scrolls = bottom_width > canvas_w` branch — enter a wrap-rendering path that always loops.
- Per-tick: paint image (unwrapped) + top row (held) + `n_copies` of `bottom_text + separator` at `scroll_pos - cycle_width + i * cycle_width` for `i in [0, n_copies)`.
- `scroll_pos %= cycle_width` per tick.

**Note on `_draw_separator` reuse:** v1's helper computes the separator color via `font_color` / `text_separator_color`. For two-row we need it to use `bottom_color` / `bottom_text_separator_color`. Either (a) parameterize the helper with the provider + frame_key, or (b) add a thin `_draw_bottom_separator` variant. Decide in the implementation plan; both are reasonable.

Concretely: one new render helper, ~40 LOC inside `_play_with_two_row_text`. Existing fast-path / static-text branch becomes inaccessible when `bottom_text_wrap=True` (wrap implies per-tick redraw — same gate as v1).

### TwoRowMessage (`widgets/two_row.py`)

TwoRowMessage's `draw(canvas, cursor_pos) -> (canvas, content_width)` is called by `_swap_and_scroll`, which decides when to stop. For wrap mode the engine must NOT stop based on cursor_pos.

**Cooperation contract:**

1. **Widget exposes `wraps_forever` property:**
   ```python
   @property
   def wraps_forever(self) -> bool:
       return self.bottom_text_wrap and bool(self.bottom_text)
   ```

2. **Engine respects the signal:** `_swap_and_scroll` (and any other engine loop that drives `draw()` with a cursor_pos sequence) reads `getattr(widget, "wraps_forever", False)` and, when True:
   - Skips the cursor_pos-based stop condition
   - Keeps incrementing cursor_pos modulo `cycle_width` (or just lets it increment naturally — the widget normalizes via `%= cycle_width` internally anyway)
   - Continues until the section's natural termination signal (duration / loop_count) fires

3. **Widget's `draw()` in wrap mode:**
   - Bottom branch: renders `n_copies` of `bottom_text + separator` at `cursor_pos % cycle_width`
   - Top branch: unchanged (held at `top_align`)
   - Returns `(canvas, cycle_width)` so the engine has a sane "step" value (one cycle = one logical traversal)

**Why this over a `play()`-style refactor:**
- Smaller blast radius (~5 lines of engine change, plus widget changes)
- Preserves TwoRowMessage's draw-based design (consistent with the rest of the widget)
- YAGNI: if a future widget needs broader self-loop semantics, the `wraps_forever` flag generalizes

## Testing strategy

Two new test files mirroring v1's `test_image_text_wrap.py` shape:

### `tests/test_widgets/test_image_two_row_wrap.py`

Covers image two-row wrap (`_BaseImageWidget` path):

- Field defaults
- 4 validation rules (refused on non-two-row, empty `bottom_text`, separator without wrap, separator_color without wrap)
- Cross-mode refusal: `text_wrap=True` + `bottom_text != ""` → error mentions `bottom_text_wrap` as the right knob
- Defining wrap test using v1's per-tick analysis: every tick has ≥2 bottom-text copies, x-positions form arithmetic progression at `cycle_width` spacing (±2px), top row stays at `top_align`
- `bottom_text_wrap` on a fitting bottom text — confirms wrap engages even without overflow
- Separator color inherits `bottom_color` (NOT `font_color`) — capture `draw_text` calls, verify the color
- Separator with `Rainbow` provider — phase counter independent of `bottom_color`'s counter
- Wrap + `border` test (border paints separately in two-row render path)
- GifPlayer two-row wrap (multi-frame source) — locks in `_pick_frame_for_elapsed` interaction

### `tests/test_widgets/test_two_row_wrap.py` (new)

Covers TwoRowMessage:

- Field defaults
- Same 4 validation rules
- `wraps_forever` property: `True` only when `bottom_text_wrap=True` AND `bottom_text` non-empty
- `draw(canvas, cursor_pos)` in wrap mode renders multiple copies at distinct x positions (per-tick analysis)
- Top row alignment held during bottom wrap
- Cross-scale (bigsign): wrap math operates on logical px through ScaledCanvas wrapper

### Engine tests (`tests/test_ticker_display.py` or similar)

- `_swap_and_scroll` respects `wraps_forever` — never exits the scroll loop based on cursor_pos when set
- Section duration / loop_count still terminates as expected (wrap doesn't break loop_count enforcement)
- Mixed: widget with `wraps_forever=False` (default) behaves exactly as before — no regression in non-wrap two-row scrolling

### Tripwires

- The existing `tests/test_engine_redraw_contract.py` AST scan: confirm the wrap-mode engine branch still calls `_advance_frame_if_supported` per tick.
- One new per-function tripwire if `_swap_and_scroll` gains a wrap-mode-specific sub-branch that the AST scanner can't see.

**Estimated test count:** ~25-30 across the two widget files, ~3-5 engine tests.

## Docs & demos

### Widget pages

Add a "Wrap mode (bottom row)" common-pattern subsection to:

- `docs/site/src/content/docs/widgets/gif.mdx`
- `docs/site/src/content/docs/widgets/image.mdx`
- `docs/site/src/content/docs/widgets/two_row.mdx` (TwoRowMessage's own page)

Plus fact-pack rows in `docs/content-source/widgets/{gif,image,two_row}.md` for the auto-generated options table.

### Pinned demos

Two new pinned demos committed to `docs/site/public/demos-pinned/`:

- `gif-two_row-wrap.gif` — pikachu + held magenta `BREAKING` top + cyan `"tap to subscribe"` wrapping bottom with `*` separator
- `two_row-wrap.gif` — standalone TwoRowMessage: held `BREAKING` title + scrolling-wrap `"tap to subscribe • new episode"` bottom

Configs in `docs/site/demos-pinned/{gif-two_row-wrap,two_row-wrap}.toml`, rendered via `make render-pinned-demos`.

### Notes per subsection

- `bottom_text_wrap` always wraps when set, even if the text fits
- Top row never wraps (refused by validation; no `top_text_wrap` exists)
- `bottom_text_separator_color` inherits `bottom_color`, NOT `font_color`
- v1's `text_wrap` stays single-row-only — pointer to `bottom_text_wrap` if user mistakenly applies the wrong knob in two-row mode
- Rainbow on `bottom_color` resets hue per copy in wrap mode (matches v1 single-row behavior); document as a known artifact

## Out of scope

Deferred to future v3 work, called out explicitly to keep this PR focused:

- **`top_text_wrap`** — top row stays held forever in this design. If someone wants both rows to wrap, that's a different layout (probably a single-row variant or a custom widget).
- **`bottom_text_separator_font` / `bottom_text_separator_font_size`** — separator inherits the bottom row's font. v1 also deferred this; same rationale.
- **Two-row wrap interaction with `text_loops`** — image two-row has `text_loops` on `_BaseImageWidget`. In v2 it reinterprets as "minimum bottom-row cycle traversals" (one cycle = bottom_text + separator), mirroring v1 single-row's reinterpretation exactly. `TwoRowMessage` has no `text_loops` field today; v2 does not add one (the engine's section duration / loop_count drives termination).
- **`Forever_scroll` mode + TwoRowMessage wrap** — wrap mode is per-widget; forever_scroll is section-level. They compose by accident if at all; not designed for explicitly.
