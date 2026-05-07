# Image Typewriter — Single-Row Design

**Status:** Spec — ready for implementation plan
**Author:** James Awesome (with Claude Opus 4.7)
**Date:** 2026-05-07
**Predecessor:** PR #12 (per-effect counters) — eliminated the composition tradeoff that made this feature awkward to add

## Goal

Add `animation = "typewriter"` to single-row image widgets (`gif`, `image`).
Per-effect counters from PR #12 mean typewriter composes cleanly with
`font_color = "rainbow"` and `border = "rainbow"` on the same widget — three
independent frame systems, no shared state.

## Non-Goals

Listed explicitly so the PR review knows what NOT to ask about:

- Two-row typewriter (top row + bottom row composition) — separate spec if needed
- Typewriter on `text_align ∈ ("scroll", "scroll_over")` — explicitly forbidden
- Per-image typewriter speed override (no widget-specific knob; use existing
  `frames_per_char` field on the Typewriter inline-table syntax)
- Bounce or other animations — only Typewriter has a `visible_chars` surface;
  future animations need their own design

## Architecture

One field added to `_BaseImageWidget`:

```python
animation: Any | None = attrs.field(default=None, kw_only=True)
```

Both `GifPlayer` and `StillImage` inherit from `_BaseImageWidget`, so the field
applies to both subclasses without per-subclass changes.

Three layers of change:

1. **Field + post-init validation** on `_BaseImageWidget` — three new error paths
2. **Render-tick slice** — `_render_tick` calls `_visible_text(frame_count)`
   helper instead of `self.text` when animation is set
3. **Fast-path gate** — `_play_with_text` static-text predicate gains
   `AND self.animation is None` (one line)

`app._build_widget` extends its existing animation-allowlist from `{message}` to
`{message, gif, image}`. The animation construction (string shorthand
→ `Typewriter()` defaults; inline table → `Typewriter(frames_per_char=N)`) is
already shared via the existing builder — image widgets reuse it unchanged.

## Validation Rules

Three config-load errors raised in `_BaseImageWidget.__attrs_post_init__`:

```python
if self.animation is not None:
    if self.bottom_text:
        raise ValueError(
            "animation is not supported in two-row mode "
            "(set on a single-row image widget; remove bottom_text)"
        )
    if self.text_align in ("scroll", "scroll_over"):
        raise ValueError(
            f"animation is not compatible with text_align={self.text_align!r} "
            "(typewriter on a moving marquee is incoherent; "
            "use text_align=auto/left/right)"
        )
    if not self.text:
        raise ValueError(
            "animation requires non-empty text "
            "(typewriter has nothing to type out)"
        )
```

Each error message names the conflicting fields and the resolution. Mirrors the
existing footgun-validation style in `_BaseImageWidget` (BDF font_size < cell_h,
hold_seconds < 0.05, text_x_offset + scroll, etc.).

## Render-Tick Slice + Layout Anchoring

A small helper on `_BaseImageWidget`:

```python
def _visible_text(self, frame_count: int) -> str:
    """Apply animation to text. Returns full text when no animation
    is configured. Layout (cursor position, alignment math) operates
    against `self.text` regardless — the anchored layout uses the
    eventual full-text width while only the visible slice gets
    drawn. This is what makes typewriter feel 'anchored' under
    right-align: the partial text appears in the position the
    final text will occupy."""
    if self.animation is None:
        return self.text
    return self.animation.visible_chars(frame_count, self.text)
```

`_render_tick` changes one line in the `left`/`right`/`auto` branch:

```python
# before:
self._draw_text(text_canvas, text_x, baseline_y, provider)

# after:
self._draw_text(
    text_canvas, text_x, baseline_y, provider,
    text_override=self._visible_text(self.frame_for("animation")),
)
```

`_draw_text` gains an optional `text_override: str | None = None` parameter —
when set, it draws that string instead of `self.text`. Layout helpers
(`_measure_text`, `aligned_x` calculation) keep using `self.text` so the
anchor position is locked to the eventual full-text dimensions.

**Layout invariant:** the cursor x-position, baseline y, and aligned_x are
computed once per visit (before the tick loop) using `self.text`. Inside the
loop, only the rendered string changes. Result: characters appear in their
final positions, never shifting.

**Per-char providers (rainbow / gradient) on partial text:**
`draw_text_per_char` takes the visible-text slice and iterates its chars. Pass
`total_chars=len(self.text)` (the EVENTUAL full length, not the current
visible length) so each typed char gets the hue it'll have at completion. This
matches TickerMessage's behavior: a char that types in at position 4 of "Hello"
shows the same hue at frame=12 (mid-type) as at frame=99 (long after typing
completed).

## Fast-Path Gate

Existing static-text fast path in `_play_with_text` (paraphrased):

```python
if (
    self._is_static()
    and self.text_align in ("left", "right")
    and self.text_loops == 0
    and getattr(self.font_color, "frame_invariant", False)
    and (self.border is None or self.border.frame_invariant)
):
    # Paint once, sleep cumulative duration, return.
```

Typewriter is per-tick by definition. One predicate addition:

```python
    and self.animation is None
):
```

Same shape as the `font_color.frame_invariant` and `border.frame_invariant`
clauses already in the gate. No new abstraction.

## Frame Counter Wiring

`Typewriter.restart_on_visit` is `True` (the default in `animations.py`) — so
per the per-effect-counter contract from PR #12, the typewriter counter
resets on each visit-entry call to `reset_frame()`. That gives "type once per
visit" automatically.

Composition with continuous-phase effects on the same widget:
- `border.frame_for("border")` keeps phase across visits when border is
  `RainbowChaseBorder` (`restart_on_visit = False`)
- `font_color.frame_for("font_color")` keeps phase when provider is
  continuous-phase (`Rainbow` / `ColorCycle`)
- `animation.frame_for("animation")` resets each visit

All three counters tick independently. No new infrastructure needed — this is
exactly the case PR #12 was built for.

`pause_frame()` during transitions still freezes all three together via
`_FrameAware`. Existing transition contract holds.

## Testing

Five tests in `tests/test_widgets/test_image_base.py`, one new class:

```python
class TestImageTypewriter:
    """Single-row typewriter on image widgets. Validation + render
    + fast-path bypass + per-effect counter wiring."""
```

1. `test_animation_with_bottom_text_raises` — config with both `animation`
   and `bottom_text` raises `ValueError` mentioning two-row mode.
2. `test_animation_with_scroll_align_raises` — `text_align ∈ ("scroll",
   "scroll_over")` + animation raises `ValueError`.
3. `test_animation_with_empty_text_raises` — empty `text` + animation raises
   `ValueError`.
4. `test_visible_text_slices_per_frame` — pre-populate
   `_effect_frames["animation"]` to specific values, call `_visible_text(frame)`,
   assert slice progresses (e.g. frame=0 → "", frame=3 → "H", frame=6 → "He"
   at default `frames_per_char=3`).
5. `test_fast_path_bypassed_with_animation` — static image + animation +
   `text_align="left"` runs the per-tick loop (assert `SwapOnVSync.call_count
   > 1`). Mirrors `TestPlayWithTextBorderFastPath::
   test_fast_path_bypassed_with_animated_border`.

One additional test in `tests/test_app.py`:

6. `test_animation_field_accepted_on_image_widget` — TOML config with `type
   = "image"` + `animation = "typewriter"` builds without error. Mirrors the
   existing TickerMessage acceptance test.

**Total: 6 tests.** All bug-catching; each covers a distinct code path.

## Smoke Config Update (Optional)

Add §19 to `config/config.rainbow_border_test.example.toml` to demonstrate
three-effect composition on hardware:

```toml
# §19 — typewriter on image: caption types in over a held still.
# Composes typewriter (restart_on_visit=True) + rainbow font color
# + rainbow border (both restart_on_visit=False) on the SAME image
# widget. Border keeps its chase phase across loop_count > 1; font
# rainbow sweeps continuously; caption retypes each loop.
[[sections]]
hold_time = 6
loop_count = 3

  [[sections.widgets]]
  type = "image"
  path = "config/test.png"
  text = "Hello!"
  text_align = "left"
  animation = "typewriter"
  font_color = "rainbow"
  border = "rainbow"
```

§19 demonstrates **three-effect composition** — the architectural payoff of
PR #12 extended to image widgets. Skip if you want a minimum-viable PR.

## Migration / Backwards Compatibility

None. Pure addition: new field defaults to `None`, existing configs load
unchanged. The new validation only fires when `animation` is set, so prior
configs with `bottom_text` + `text_align="scroll"` etc. keep working.

`app._build_widget`'s allowlist update is the one config-surface change: an
explicit `animation = ...` on a `gif` / `image` widget now builds where it
previously raised. No prior config could rely on the old rejection.

## Estimated Effort

~2-3 hours of code work + ~1 hour of test work. Half-day end-to-end including
spec → plan → subagent-driven implementation → review → PR cycle. Same
workflow as PR #12.

## CLAUDE.md Update

Add a short paragraph to the existing `_image_base` section:

> **Typewriter on image widgets** (`animation = "typewriter"` on `gif` /
> `image`): single-row only — raises if `bottom_text != ""`, `text_align ∈
> ("scroll", "scroll_over")`, or `text == ""`. Reads its per-effect counter
> via `frame_for("animation")` so it composes cleanly with continuous-phase
> `font_color` and `border` (rainbow text + rainbow border + typewriter all
> tick on independent counters). Forces the slow path in `_play_with_text`
> (gate predicate adds `AND animation is None`). Layout uses full-text width;
> only the visible slice is drawn — characters appear in their final
> positions, never shifting.
