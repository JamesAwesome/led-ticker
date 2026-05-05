# Presentation system rework — design

**Status:** Draft for review
**Date:** 2026-05-05
**Scope:** Replace the `WidgetPresenter` wrapper + `presentation = "..."` knob
with two orthogonal widget knobs: rich `font_color` (color providers) and
`animation` (TickerMessage-only, scoped). Engine tick fix bundled.

## Background

led-ticker has a `WidgetPresenter` wrapper that adds frame-aware effects
(`typewriter`, `color_cycle`, `rainbow`, `pulse`, `bounce`) to any widget
via `presentation = "..."` in TOML. Two issues with the current shape:

1. **Held-text swap mode doesn't tick.** `_swap_and_scroll` (`ticker.py:805`)
   draws once then `await asyncio.sleep(hold_time)` for non-overflowing text.
   `WidgetPresenter.frame_count` is locked at 0 for the entire hold, so
   typewriter shows just the first character, color_cycle/pulse stay at
   frame 0 colors, bounce sits off-screen at frame=0 forever. Smoke-tested
   on hardware: typewriter showed only "W". Hard crash also observed
   during the smoke session — likely bounce off-canvas at cursor_pos =
   width, but unconfirmed without logs.

2. **Categorical mismatch between effects.** `rainbow` / `color_cycle` /
   `pulse` are visual styling — they tweak the color used for text. They
   should work on every widget that has customizable text (TickerMessage,
   countdown, weather, MLB, image-widget overlays, two-row). `typewriter`
   / `bounce` are animations — they manipulate position and slice over
   time. They only make sense on message-bearing widgets. The current
   `presentation = "..."` knob doesn't distinguish, and applying
   `presentation = "typewriter"` to e.g. a gif widget is silently wrong
   (the wrapper short-circuits but the user gets no error).

The user's framing: color effects are universal styling; animation
effects are widget-specific behavior. The rework codifies that split.

## Goals

1. **One mental model.** Two orthogonal knobs: `font_color` (color
   provider) and `animation` (TickerMessage only). No wrapper, no
   compatibility matrix.
2. **Color providers fire everywhere.** Any widget that paints text with
   a `font_color` field gets the new effects automatically.
3. **Animations stay scoped.** `animation` is a `TickerMessage`-only
   field; `_build_widget` rejects it on other widget types at config-load.
4. **Engine fix.** `_swap_and_scroll`'s held-text branch becomes a tick
   loop so frame-aware widgets actually animate during their hold.
5. **Hard cutover.** `presentation = "..."` removed entirely with a loud
   migration error including the verbatim conversion table.

## Non-goals

- Per-char color provider routing **through emoji slugs.** Today's rainbow
  renders e.g. `:taco:` as 6 colored ASCII characters instead of the taco
  sprite. Fixing this requires plumbing the provider into
  `pixel_emoji.draw_with_emoji`, which is bigger than this rework. v1
  limitation, documented.
- Configurable tick cadence. Engine tick loop hardcodes 50ms (20 fps).
  Make it a knob if/when someone needs it.
- New widget type `animated_message`. Two widget types where one would
  do — `animation` is a knob on existing `TickerMessage`.
- Adding new effect types beyond what exists today plus `gradient`.
  Scope creep deferred.

## Architecture

### One mental model

Two orthogonal knobs:

- **`font_color`** (existing field, semantics extended) — accepts
  `[r,g,b]` (existing), `"random"` (existing), `"rainbow"` /
  `"color_cycle"` (new shorthand), or an inline table
  `{style = "...", ...}` (new). All values normalize to a `ColorProvider`
  internally. Constant colors implement the provider as a no-op (always
  return the same Color).

- **`animation`** (new field on `TickerMessage` only) — accepts omitted,
  `"typewriter"`, `"bounce"`, or an inline table for tuning. Internally
  an `Animation` interface produces position/visibility per frame.

### No wrapper

`WidgetPresenter` is deleted. Each widget tracks its own
`_frame_count: int` (init=False, default=0) and exposes
`advance_frame()` / `pause_frame()` / `resume_frame()` /
`reset_frame()`. The orchestrator calls these directly.

### Engine tick loop

`_swap_and_scroll`'s held-text branch (`ticker.py:805`) becomes a tick
loop calling `advance_frame() + draw + swap + sleep(50ms)` for the
duration of `hold_time`, replacing the single `asyncio.sleep(hold_time)`.
This is the single pre-req that unblocks frame-aware behavior in swap
mode for held text.

### Color providers fire on every text-painting widget

Every widget that currently calls `draw_text(canvas, font, x, y, color, text)`
materializes a Color from the provider per call site. Widgets dispatch
on `provider.per_char`:

- `False` (constant, color_cycle, pulse): one call to
  `provider.color_for(frame, 0, total)`, single Color, single draw_text
  call. Fast, emoji-safe.
- `True` (rainbow, gradient): widget iterates chars within text segments,
  calls per char. Emoji segments still render via the emoji renderer
  (slugs unchanged).

### Animation scoped to TickerMessage

Only `TickerMessage` accepts `animation`. The widget consumes it in its
own `draw()` — no wrapper indirection. `_build_widget` rejects
`animation` on any other widget type at config-load.

## Components

### 1. `ColorProvider` interface — new module `src/led_ticker/color_providers.py`

```python
from typing import Protocol
from led_ticker._types import Color

class ColorProvider(Protocol):
    per_char: bool  # class-level attribute

    def color_for(
        self, frame: int, char_index: int, total_chars: int
    ) -> Color: ...

class _ConstantColor:
    """Wraps a graphics.Color so existing widgets work unchanged when
    the provider is constant — every widget already accepts a Color."""
    per_char = False
    def __init__(self, color: Color) -> None:
        self._color = color
    def color_for(self, frame, char_index, total_chars) -> Color:
        return self._color

class Rainbow:
    """Per-char hue offset, advancing per frame."""
    per_char = True
    def __init__(self, speed: int = 8, char_offset: int = 30) -> None: ...

class ColorCycle:
    """Whole-string hue rotation; char_index ignored."""
    per_char = False
    def __init__(self, speed: int = 5) -> None: ...

class Pulse:
    """Entry flash to white; settles to base after `duration_frames`."""
    per_char = False
    def __init__(self, base: Color, duration_frames: int = 6) -> None: ...

class Gradient:
    """Linear left-to-right; char_index spaces hues; frame static."""
    per_char = True
    def __init__(self, from_color: Color, to_color: Color) -> None: ...

class Random:
    """Existing 'random' sentinel — picks a stable random color per
    visit (not per frame). Implemented as a provider for uniform
    handling at the coercion site."""
    per_char = False
    def __init__(self) -> None: ...
```

### 2. `Animation` interface — new module `src/led_ticker/animations.py`

```python
from dataclasses import dataclass
from typing import Protocol

@dataclass
class AnimationFrame:
    visible_text: str
    cursor_override: int | None  # None = use orchestrator's cursor_pos

class Animation(Protocol):
    def frame_for(
        self, frame: int, full_text: str, canvas_width: int, text_width: int
    ) -> AnimationFrame: ...

class Typewriter:
    """Slice grows one character per frame."""
    def __init__(self, chars_per_frame: int = 1) -> None: ...

class Bounce:
    """Slide in from right (ease_out), hold center, slide out left
    (ease_in). Returns the full text with a cursor override."""
    def __init__(self, hold_frames: int = 40, scroll_frames: int = 20) -> None: ...
```

### 3. `_coerce_color_provider` — extends app's color-coercion block

Single helper covering `font_color`, `top_color`, `bottom_color`, and
title `color`. Coerces:

- `[r, g, b]` (list) → `_ConstantColor(graphics.Color(r, g, b))`
- `"rainbow"` / `"color_cycle"` (string) → instantiate named provider with defaults
- `"random"` (string) → `Random()` (sentinel preserved)
- `{style = "...", ...}` (dict) → instantiate named provider with kwargs
- Anything else → raise with available names

Replaces the existing `_coerce_color` block in `_build_widget` /
`_build_title`. Same call sites: `font_color`, `top_color`,
`bottom_color`, `color` (title).

### 4. `_coerce_animation` — new helper

Accepts a string (`"typewriter"` / `"bounce"`) or inline table
(`{style = "...", chars_per_frame = 2}`). Returns an `Animation`
instance or raises with the available names.

### 5. Frame counter on widgets

Each widget that supports color providers / animations gains:

```python
_frame_count: int = attrs.field(init=False, default=0)
_frame_paused: bool = attrs.field(init=False, default=False)

def advance_frame(self) -> None:
    if not self._frame_paused:
        self._frame_count += 1

def pause_frame(self) -> None:
    self._frame_paused = True

def resume_frame(self) -> None:
    self._frame_paused = False

def reset_frame(self) -> None:
    self._frame_count = 0
```

Implemented as a small mixin (`_FrameAware` in
`src/led_ticker/widgets/_frame_aware.py`) or repeated on each widget —
~6 widgets affected, mixin is cleaner.

Widget's `draw()` reads `self._frame_count` and passes to
provider/animation. Widgets that paint text accept a `font_color` that
is now a `ColorProvider`; they call `provider.color_for(...)` to
materialize a Color.

### 6. Engine tick loop

Replace `_swap_and_scroll`'s held-text branch:

```python
# Before:
else:
    await asyncio.sleep(hold_time)

# After:
else:
    tick_ms = 50  # 20 fps; hardcoded for v1
    n_ticks = max(1, int(hold_time * 1000) // tick_ms)
    for _ in range(n_ticks):
        ticker_obj.advance_frame()
        reset_canvas(canvas, bg_color)
        canvas, _ = ticker_obj.draw(canvas, pos)
        canvas = _swap(canvas, frame)
        await asyncio.sleep(tick_ms / 1000)
```

Existing scroll branch already calls `draw()` per tick. Add
`advance_frame()` to that loop too.

`reset_frame()` is called by the section orchestrator at the start of
each visit (so `_frame_count` doesn't carry over between widgets).

### 7. Pause/resume during transitions

`run_transition` currently calls `pause()` / `resume()` on outgoing/
incoming widgets if they expose those methods (duck-typed for
WidgetPresenter). After the rework, every frame-aware widget has
`pause_frame()` / `resume_frame()` via the mixin, so the transition
loop calls those directly — no behavioral change.

### 8. Migration error

In `_build_widget`, before any other processing:

```python
if "presentation" in widget_cfg:
    raise ValueError(
        "presentation removed in favor of font_color (color effects) + "
        "animation (typewriter/bounce on TickerMessage). Migration:\n"
        "  presentation = 'typewriter'  → animation = 'typewriter' (type='message' only)\n"
        "  presentation = 'bounce'      → animation = 'bounce' (type='message' only)\n"
        "  presentation = 'rainbow'     → font_color = 'rainbow'\n"
        "  presentation = 'color_cycle' → font_color = 'color_cycle'\n"
        "  presentation = 'pulse'       → font_color = {style='pulse', base=[your existing font_color]}"
    )
```

### 9. Animation rejection on non-message widgets

After extracting `animation = widget_cfg.pop("animation", None)`:

```python
if animation is not None and widget_type != "message":
    raise ValueError(
        f"animation is only valid on type=\"message\"; got type={widget_type!r}. "
        f"For color effects on other widgets, use font_color = 'rainbow' "
        f"(or similar)."
    )
```

## Data flow

### Per-tick lifecycle (swap mode, held text)

```
Section start
  └─ widget.reset_frame()                        # _frame_count = 0
  └─ for tick in range(n_ticks):
       ├─ widget.advance_frame()                 # _frame_count += 1
       ├─ reset_canvas(canvas, bg_color)
       ├─ canvas, _ = widget.draw(canvas, pos)
       │    ├─ reads self._frame_count
       │    ├─ asks self.font_color (a ColorProvider) for Color(s)
       │    ├─ if self.animation, asks for AnimationFrame
       │    └─ paints
       ├─ canvas = SwapOnVSync(canvas)
       └─ await asyncio.sleep(tick_ms / 1000)

Section end → transition (widget.pause_frame() / resume_frame() bookend
              the dissolve compositing)
```

### Per-tick lifecycle (swap mode, scrolling text)

Existing scroll loop, with `widget.advance_frame()` added to each
iteration. Same effect: providers and animations animate naturally.

### Per-char vs whole-string rendering

```
widget.draw():
    provider = self.font_color
    if isinstance(provider, _ConstantColor):
        color = provider.color_for(...)  # always same; trivial
        draw_text(canvas, font, x, y, color, full_text)
    elif provider.per_char:              # rainbow, gradient
        x = start_x
        for i, char in enumerate(full_text):
            color = provider.color_for(self._frame_count, i, len(full_text))
            x += draw_text(canvas, font, x, y, color, char)
    else:                                # color_cycle, pulse
        color = provider.color_for(self._frame_count, 0, len(full_text))
        draw_text(canvas, font, x, y, color, full_text)
```

For widgets with `:slug:` emoji support, the per-char branch operates
on TEXT segments only; emoji segments render via
`pixel_emoji.draw_with_emoji` unchanged. v1 limitation: per-char
providers don't penetrate emoji slugs. (Documented; fix deferred.)

### TickerMessage with animation

```
animation_frame = self.animation.frame_for(
    self._frame_count, full_text, canvas_width, text_width
)
draw_pos = animation_frame.cursor_override or default_cursor
visible = animation_frame.visible_text
# then proceed with the color-provider rendering above using `visible`
# and `draw_pos`.
```

## Migration

Single PR:

1. **Code changes**:
   - New: `color_providers.py`, `animations.py`, `widgets/_frame_aware.py`.
   - Modify: `app.py` (coercion + migration error), `ticker.py`
     (engine tick), every text-painting widget (frame mixin + provider
     consumption), `presentation.py` (deleted entirely or kept as a
     stub that raises if imported).

2. **In-tree config migration** — search/replace across all in-tree
   configs that use `presentation = "..."`:

   ```bash
   grep -rn 'presentation = ' config/*.toml
   ```

   Apply the migration table to each hit.

3. **CLAUDE.md update** — replace the existing "Text Presentation
   Effects" section with the new font_color/animation model and the
   migration formula.

4. **User's bigsign Pi `config.toml`** — migrate via the same
   search/replace; out of repo. Migration error catches misses at
   startup.

## Error handling

Three classes:

1. **Migration errors** at config-load:
   - `presentation = "..."` raises with full mapping table.

2. **Construction-time validation** in `_build_widget`:
   - `animation` on non-message widget → raises with "type=\"message\" only" hint.
   - Unknown color provider name → raises with available names list.
   - Unknown animation name → raises with available names.
   - Inline-table missing required key (e.g. `pulse` without `base`,
     `gradient` without `from`/`to`) → raises with the required-key
     name and example.
   - Inline-table unknown key for the named style → raises with
     accepted-keys list.

3. **Paint-time** — none planned. Bounce off-canvas is handled by
   existing draw clip logic; provider edge cases (empty text,
   total_chars=0) handled defensively in providers themselves.

## Testing

### Unit — providers

- `Rainbow`: `color_for(0, 0, 10)` produces hue 0; `frame=10` advances;
  `char_index=10` differs by `char_offset` degrees.
- `ColorCycle`: ignores `char_index`; `frame=10` advances by `10*speed`
  degrees.
- `Pulse`: `frame=0` returns near-white; `frame=duration_frames` returns
  base; `frame=duration_frames * 2` still returns base (no re-trigger).
- `Gradient`: `char_index=0` returns `from_color`;
  `char_index=total_chars-1` returns `to_color`; `frame` ignored.
- `Random`: `color_for(0,0,1)` and `color_for(10,0,1)` return same
  Color (stable per-instance, not per-frame).

### Unit — animations

- `Typewriter`: `frame_for(0, "WATCH", 256, 30)` → visible="W",
  cursor_override=None. `frame_for(2, "WATCH", 256, 30)` → "WAT".
- `Bounce`: `frame_for(0, "BOUNCE", 256, 36)` → cursor_override=256;
  `frame_for(20, ..., ...)` → cursor at center; `frame_for(75, ..., ...)`
  → cursor near -text_width.

### Unit — coercion

- `_coerce_color_provider([255, 0, 0])` → `_ConstantColor`.
- `_coerce_color_provider("rainbow")` → `Rainbow()` (defaults).
- `_coerce_color_provider({"style": "rainbow", "speed": 8})` →
  `Rainbow(speed=8)`.
- `_coerce_color_provider({"style": "pulse"})` → raises (missing base).
- `_coerce_color_provider("blarghbargh")` → raises with available names.

### Unit — `_build_widget` migration

- `_build_widget({"presentation": "typewriter", ...})` raises with
  full mapping table verbatim (regex match a few key lines).
- `_build_widget({"animation": "typewriter", "type": "weather", ...})`
  raises with "type=\"message\" only" hint.
- `_build_widget({"animation": "typewriter", "type": "message", ...})`
  succeeds; widget has `_animation` field set.

### Behavioral — engine tick loop

- `_swap_and_scroll` with held text + a frame-aware widget: spy on
  `widget.advance_frame()` and `widget.draw()` calls; assert both
  fire roughly `hold_time / 50ms` times.
- Pause/resume: dispatch a transition compositing call between two
  widgets with frame-aware draws; assert frame_count doesn't advance
  during the transition window.

### Behavioral — providers in widgets

- `TickerMessage(font_color="rainbow")`: draw it on a stub canvas with
  spy on `draw_text`; assert `draw_text` called once per character of
  the message.
- `TickerMessage(font_color="color_cycle")`: `draw_text` called once
  with a single Color; that color shifts between draws as frame
  advances.
- `TickerMessage(font_color=[255,0,0])`: `draw_text` called once;
  Color is the constant.

### Visual / integration

`config.presentation_test.example.toml` rewritten to the new
vocabulary in the same PR. On-hardware proof remains a manual smoke
pass; document expected behavior per section.

## Open questions

None. The two pivotal questions (TOML syntax for color providers,
hard-vs-phased cutover) were resolved during brainstorming.

## Appendix — files touched

```
src/led_ticker/color_providers.py             (new)
src/led_ticker/animations.py                  (new)
src/led_ticker/widgets/_frame_aware.py        (new mixin)
src/led_ticker/app.py                         (coercion + migration error)
src/led_ticker/ticker.py                      (engine tick + advance_frame call)
src/led_ticker/widgets/message.py             (TickerMessage adds animation; consumes provider)
src/led_ticker/widgets/weather.py             (consumes provider)
src/led_ticker/widgets/mlb.py                 (consumes provider)
src/led_ticker/widgets/mlb_standings.py       (consumes provider)
src/led_ticker/widgets/two_row.py             (per-row providers)
src/led_ticker/widgets/_image_base.py         (font_color/top_color/bottom_color providers)
src/led_ticker/widgets/rss_feed.py            (verify expanded messages flow providers)
src/led_ticker/widgets/crypto/*.py            (consume provider where applicable)
src/led_ticker/presentation.py                (delete or stub-raise)
src/led_ticker/transitions/__init__.py        (run_transition pause/resume call surface)
tests/test_color_providers.py                 (new)
tests/test_animations.py                      (new)
tests/test_app.py                             (migration error + animation rejection)
tests/test_ticker_display.py                  (engine tick + pause/resume tests)
tests/test_widgets/*                          (per-widget provider consumption tests)
config/config.presentation_test.example.toml  (rewrite to new vocabulary)
config/*.toml                                 (search/replace text_scale residuals — n/a; 
                                               grep config/*.toml for presentation = "..." 
                                               and migrate hits)
CLAUDE.md                                     (replace presentation paragraph)
docs/superpowers/specs/*.md                   (this file, committed)
```
