# Image Borders Design

**Date:** 2026-05-07
**Status:** Approved (pending implementation plan)

## Goal

Extend the existing `border` feature to image widgets — `GifPlayer`
(`type="gif"`) and `StillImage` (`type="image"`). Today borders only
work on `TickerMessage`, `TickerCountdown`, and `TwoRowMessage`. The
deferred-from-original-PR rationale ("fast-path gate interaction
estimated ~3× this PR's cost") is paid here.

## Scope

**In:**
- `border` field on `_BaseImageWidget` (inherited by `GifPlayer` and
  `StillImage`).
- TOML vocabulary mirrors TickerMessage exactly: `border = "rainbow"`,
  `border = {style="rainbow", speed=N, char_offset=N, thickness=N}`,
  `border = {style="constant", color=[r,g,b], thickness=N}`, or
  `border = [r,g,b]`.
- Border integration on **all four** image render paths:
  1. `_render_tick` (single-row text overlay)
  2. `_render_two_row_tick` (two-row text overlay)
  3. `StillImage._play_no_text` (no-text still)
  4. `GifPlayer._play_no_text` (no-text gif)
- Fast-path gates updated on three sites to also check
  `border.frame_invariant`.
- `GifPlayer._play_no_text` refactored to engine 50ms cadence
  (matches `_play_with_text`'s elapsed-time pattern).
- Allow-list in `_build_widget` extended to accept `border` on `gif`
  and `image` widget types.

**Out:**
- WeatherWidget, MLB, crypto, RSS — same readability rationale as
  the original spec. Decorative borders on data widgets fight legibility.
- Section-level borders (engine paints regardless of widget) — bigger
  architectural conversation, still deferred.

## Architecture

### `border` field on `_BaseImageWidget`

`_BaseImageWidget` already inherits `_FrameAware` (provides
`_frame_count`, `advance_frame`, `pause_frame`, `resume_frame`,
`reset_frame`). Add a `border: BorderEffect | None = None` attrs
field. `GifPlayer` and `StillImage` inherit it for free.

### Paint order

Convention is "border frames the panel, content fits inside" — same
as TickerMessage / TwoRowMessage. The border always paints AFTER the
image (so it overlays image edges) and BEFORE text rows (text
overlaps border on collision).

| Path | Order |
|---|---|
| `_render_tick` non-scroll (`text_align ∈ {auto, left, right}`) | reset → image → **border** → text |
| `_render_tick` scroll (skip-black) | reset → text → image (skip-black) → **border** |
| `_render_tick` scroll_over | reset → image → **border** → text |
| `_render_two_row_tick` | reset → image → **border** → top row → bottom row |
| `StillImage._play_no_text` | reset → image → **border** → swap |
| `GifPlayer._play_no_text` | reset → image → **border** → swap (per 50ms tick) |

Skip-black scroll mode is the only path where image paints after
text (existing behavior — text walks behind silhouette). Border
still lands LAST in that path so it remains visible over both image
and any scrolled text at the panel edges.

### Physical resolution painting

Border paints via `unwrap_to_real(canvas)` (existing `BorderEffect`
contract — see `borders.py`). This already handles ScaledCanvas
wrappers correctly. For two-row image widgets at `_logical_scale=2`
on bigsign, the border traces the 256×64 panel edge — same behavior
as TwoRowMessage's existing border integration.

### Frame counter

`border.paint(canvas, self._frame_count)` — same call shape used by
TickerMessage and TwoRowMessage. Visit-resets, transition pauses,
and `_swap_and_scroll`'s frame-advance contract all Just Work via
the existing `_FrameAware` mixin.

## Engine refactor: `GifPlayer._play_no_text` to 50ms cadence

Today's `_play_no_text` loops at the gif's natural per-frame cadence
(durations from `img.info["duration"]`). Adding an animated border
would make rainbow motion vary with the gif's frame timing — a 100ms
gif gets 10Hz chase, a 200ms gif gets 5Hz chase, the rainbow looks
slower on slower gifs. To preserve uniform border motion, refactor
to engine 50ms cadence using the elapsed-time pattern that
`_play_with_text` already uses.

**New shape:**

```python
async def _play_no_text(self, real_canvas, frame, loop_count):
    loops = max(1, loop_count)
    canvas = real_canvas
    total_ms = sum(d for _, d in self._frames) * loops
    n_ticks = max(1, total_ms // ENGINE_TICK_MS)

    for tick in range(n_ticks):
        self._pick_frame_for_elapsed(tick * ENGINE_TICK_MS)
        self.advance_frame()
        reset_canvas(canvas, self.bg_color)
        self._paint_image(canvas)
        if self.border is not None:
            self.border.paint(canvas, self._frame_count)
        canvas = frame.matrix.SwapOnVSync(canvas)
        await asyncio.sleep(ENGINE_TICK_MS / 1000)

    self._current_frame_idx = len(self._frames) - 1
    return canvas
```

`_pick_frame_for_elapsed` already exists and handles wrapping for
multi-loop playback (it's what `_play_with_text` uses to pick gif
frames at 50ms cadence).

**Side effect (intentional):** even WITHOUT a border, gif animation
now ticks at 50ms rather than the gif's native frame cadence. For
gifs with frame durations ≥ 50ms (the common case), visual output
is identical to today — `_pick_frame_for_elapsed` just returns the
same frame index for multiple consecutive 50ms ticks. For gifs with
sub-50ms frame durations (rare; ~30Hz playback), the engine cadence
caps at 20Hz — the same cap `_play_with_text` already imposes for
text-overlay gifs. Behavior unification is the point.

## `StillImage._play_no_text` two-mode pattern

`StillImage._play_no_text` currently paints once and sleeps for the
full `hold_seconds`. With a non-frame-invariant border (rainbow
chase with `speed > 0`), this would freeze the rainbow.

**Mirror the existing `_play_with_text` fast-path gate:**

```python
async def _play_no_text(self, real_canvas, frame):
    canvas = real_canvas
    border_is_static = (
        getattr(self.border, "frame_invariant", True) if self.border else True
    )

    if border_is_static:
        # Fast path: paint once, sleep, return.
        reset_canvas(canvas, self.bg_color)
        self._paint_image(canvas)
        if self.border is not None:
            self.border.paint(canvas, self._frame_count)
        canvas = frame.matrix.SwapOnVSync(canvas)
        await asyncio.sleep(self.hold_seconds)
        return canvas

    # Slow path: per-tick loop for animated border.
    n_ticks = max(1, int(self.hold_seconds * 1000) // ENGINE_TICK_MS)
    for tick in range(n_ticks):
        self.advance_frame()
        reset_canvas(canvas, self.bg_color)
        self._paint_image(canvas)
        self.border.paint(canvas, self._frame_count)
        canvas = frame.matrix.SwapOnVSync(canvas)
        await asyncio.sleep(ENGINE_TICK_MS / 1000)
    return canvas
```

`hold_seconds` rounds down to whole 50ms ticks (e.g. 0.5s → 10
ticks). The static fast path is unchanged for any non-bordered or
constant-bordered still — no perf regression on the common case.

## Fast-path gates updated

Three existing fast-path gates need a `border_is_static` term added
to their predicate:

1. `_play_with_text` static fast path (~line 725):
```python
border_is_static = (
    getattr(self.border, "frame_invariant", True) if self.border else True
)
if (
    not scrolling
    and self.text_loops == 0
    and self._is_static()
    and color_is_static
    and border_is_static  # ← added
):
    # paint once, sleep, return
```

2. `_play_with_two_row_text` static fast path (~line 905): same
   `border_is_static` term added.

3. `StillImage._play_no_text` (new gate as shown above).

The same `getattr(border, "frame_invariant", True)` pattern works
for all three sites:
- `border = None` → `True` (no border, no animation cost).
- `ConstantBorder` → `True` (class attribute).
- `RainbowChaseBorder(speed=0)` → `True` (property; matches no-chase
  case).
- `RainbowChaseBorder(speed>0)` → `False` (forces per-tick loop).

## Config-load: `_build_widget` allow-list

One change in `app.py`:

```python
if border_value is not None and widget_type not in (
    "message", "countdown", "two_row",
    "gif", "image",   # ← added
):
    raise ValueError(...)
```

The existing `_coerce_border` helper produces `BorderEffect` instances
for every TOML shape. Image widget classes accept the field through
attrs the same way `TwoRowMessage` does today.

Restriction kept: `weather`, `mlb`, `mlb_standings`, `crypto.*`, RSS
all still raise — readability over decoration.

## Testing

8 new tests across `tests/test_app.py`,
`tests/test_widgets/test_image_base.py`, `test_widgets/test_gif.py`,
and `test_widgets/test_still.py`:

1. **Config-load** — `test_image_widget_with_border_string`:
   `border = "rainbow"` on `type="gif"` and `type="image"` builds a
   `RainbowChaseBorder`. Mirrors existing
   `test_two_row_with_border_string`.

2. **Allow-list rejection holds** — extend the existing test that
   asserts borders raise on weather/mlb. Add gif/image to the accept
   list, leave the others raising.

3. **Per-path paint order tripwires** — for each of the 4 paths,
   record `border.paint` call order vs image paint vs text paint
   using a `BorderEffect` whose `paint` appends to a recording list.
   Assert the order matches the table in the Architecture section.

4. **Static-text fast-path bypass with animated border**:
   `_play_with_text` with `border=RainbowChaseBorder(speed=4)` runs
   the per-tick loop, NOT the fast path. Assert `_render_tick` call
   count == n_ticks, not 1. Same shape for `_play_with_two_row_text`
   and `StillImage._play_no_text`.

5. **Static-text fast path stays valid with constant border** —
   one test per fast-path site:
   - `_play_with_text` with `text="Hi"` (static) +
     `border=ConstantBorder([255,0,0])` takes the fast path
     (`_render_tick` called once).
   - `_play_with_two_row_text` with two static rows + a
     `ConstantBorder` takes its fast path (`_render_two_row_tick`
     called once).
   - `StillImage._play_no_text` with a `ConstantBorder` takes the
     paint-once-and-sleep fast path (single SwapOnVSync call).
   Catches a future regression that drops the `frame_invariant`
   short-circuit at any of the three sites.

6. **GifPlayer no-text refactor preserves animation**: 3-frame gif
   with 100ms durations + `loop_count=1` produces 3 distinct frame
   indices over its 300ms run (6 ticks at 50ms cadence). Verifies
   the elapsed-time refactor doesn't regress non-bordered gif
   playback.

7. **GifPlayer no-text border ticks**: single-frame gif with a
   500ms native frame duration + `loop_count=1` (so total run =
   500ms = 10 ticks at 50ms cadence) + `RainbowChaseBorder(speed=4)`
   calls `border.paint` 10× with strictly increasing `frame_count`.
   Catches a refactor that drops `advance_frame()` from the new
   no-text loop.

8. **Border paints at physical resolution on bigsign-style
   ScaledCanvas**: wrap a real bigsign canvas at scale=4, render one
   tick of `_render_tick` with `border=RainbowChaseBorder()`,
   verify pixels land on the real 256×64 panel perimeter (not the
   logical 64×16 wrapper perimeter). Same tripwire shape as
   TwoRowMessage's existing physical-resolution test.

## Documentation

Extend the existing "Rainbow border" section in `CLAUDE.md`:
- List `gif` and `image` in the allowed widget types (currently
  "Border is restricted to `message`, `countdown`, and `two_row`").
- Add a one-line note about the `GifPlayer._play_no_text` 50ms
  cadence refactor and its frame_invariant fast-path gate.
- Cross-reference the per-path paint-order table for image widgets
  if anyone needs to debug a future "where does the border land"
  question.

## Open / deferred

- **Section-level border** (engine paints regardless of widget) —
  still deferred. Would need a section-level config knob and a
  paint hook in the section run loop. No user demand today.
- **Per-corner / partial borders** — not requested. The current
  perimeter-only model covers the use cases.
- **Border on RSS feed stories** — RSS expands into TickerMessages,
  so technically each story COULD inherit a border via the existing
  TickerMessage path; today it doesn't because RSS doesn't surface
  a `border` knob. Out of scope.
