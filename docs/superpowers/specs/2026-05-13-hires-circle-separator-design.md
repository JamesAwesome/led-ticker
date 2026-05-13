# Design: Hi-res circle as the default `forever_scroll` separator

**Date:** 2026-05-13
**Status:** Proposed
**Builds on:** `2026-05-13-forever-scroll-separator-design.md` (per-section separator config)

## Overview

Today's `DEFAULT_BUFFER_MSG` is `TickerMessage(" • ", font_color=RGB_WHITE)`. On bigsign (`default_scale = 4`) the BDF bullet renders as a chunky 4×4-physical-pixel block — visually jarring next to hi-res fonts and hi-res emoji that share the same canvas.

Change: when a section's separator config is unspecified AND the canvas is a `ScaledCanvas`, paint a smooth filled circle at physical resolution. Smallsign keeps the existing BDF bullet exactly. `separator_color` (already in the schema from #55) controls the circle color when set.

**No new TOML fields.** The four existing separator fields cover every case; the change is in render-time behavior, not config surface.

---

## Auto-promote rules

Evaluated in `_resolve_buffer_msg` (`app.py:685`):

| TOML state | Result |
| --- | --- |
| All four `separator_*` unset | inherit `DEFAULT_BUFFER_MSG` (now a `_CircleBufferMsg` instance, white) |
| `separator_color` set; `separator` / `separator_font` / `separator_font_size` all unset | `_CircleBufferMsg(color=<resolved>)` — circle painted with user's color/provider |
| `separator` or `separator_font` or `separator_font_size` set (any one) | `TickerMessage(...)` — exactly today's behavior; no circle |

The opt-in trigger for "I want a custom glyph" is "user specified text or a font." Once they did that, they get literal glyph rendering — same contract as the existing spec, including the `separator = ""` → two-space gap path.

This is a slight semantic shift from the existing spec, which had `separator_color` alone build a `TickerMessage("•", font_color=…)`. New behavior: `separator_color` alone still produces the visible result the user wants ("a recolored dot"), but routes through `_CircleBufferMsg` so they get the hi-res circle on bigsign. On smallsign the rendered pixels are identical to the old spec because `_CircleBufferMsg` delegates to the embedded BDF bullet there.

---

## `_CircleBufferMsg` — TickerMessage subclass

A small private class in `ticker.py`, next to the existing `DEFAULT_BUFFER_MSG` definition. Not a registered widget; not exported. Subclasses `TickerMessage` with `text=" • "`, `center=False`, and the user-resolved color so the smallsign path inherits everything for free.

```python
class _CircleBufferMsg(TickerMessage):
    """forever_scroll buffer separator. Auto-routes to a hi-res circle when
    the canvas is a ScaledCanvas; falls back to TickerMessage's BDF rendering
    of " • " on plain canvases (smallsign / scale=1)."""

    def __init__(self, color: Color | ColorProvider = RGB_WHITE) -> None:
        super().__init__(text=" • ", center=False, font_color=color)

    def draw(self, canvas, cursor_pos: int = 0, **kwargs):
        if isinstance(canvas, ScaledCanvas):
            return _draw_hires_circle(canvas, cursor_pos, self._color_for_frame())
        return super().draw(canvas, cursor_pos=cursor_pos, **kwargs)

    def _color_for_frame(self) -> Color:
        # The parent normalizes font_color into a ColorProvider during __init__;
        # implementation will resolve the attribute name from TickerMessage's
        # internals (e.g. self._font_color_provider or whatever it's called).
        return self._font_color_provider.color_for(self.frame_for("color"), 0, 1)
```

`_FrameAware` is inherited from `TickerMessage` — frame counters, `frame_for(...)`, advance-frame plumbing all just work.

**`restart_on_visit`:** `TickerMessage` defaults to True (text reveal restarts per visit). For a continuous-phase color sweep on the buffer message we want False, so Rainbow / ColorCycle stay smooth across loop iterations. Override as a class attribute on `_CircleBufferMsg` only — don't touch `TickerMessage`'s default.

### `_draw_hires_circle(canvas, cursor_pos, color) -> (canvas, int)`

A module-private helper in `ticker.py`. Paints a filled disk at physical resolution to `unwrap_to_real(canvas)`.

- **Logical footprint:** 10 logical pixels wide total (1 left pad + 8 circle + 1 right pad). Matches today's `" • "` BDF advance closely enough that `_scroll_side_by_side` layout doesn't shift.
- **Physical extent on bigsign:** 40 physical px wide, with the 8-logical-px circle at scale=4 = 32 physical px diameter — same footprint as a hi-res inline emoji.
- **Vertical centering:** centered in the canvas's physical content band. The center physical-y is `canvas._y_offset + (canvas.height * canvas.scale) // 2`. Implementation plan should pin the exact pixel via a test fixture against a `ScaledCanvas(scale=4, content_height=16)` to lock in the answer.
- **Rasterization:** filled-disk scan — for each `dy ∈ [-r, r]`, the row spans `[-sqrt(r² - dy²), +sqrt(r² - dy²)]` inclusive. Integer math; `r = (32 // 2) = 16` physical px on bigsign. Same approach as `_generate_moon_hires` minus the subtraction step.
- **Color application:** uniform fill — every disk pixel gets `SetPixel(x, y, color.r, color.g, color.b)`.
- **Return:** `(canvas, cursor_pos + 10)`. The advance is the logical footprint so `_scroll_side_by_side`'s cursor tracking stays in logical units consistent with `TickerMessage`'s `cursor_pos` semantics.

### Why a subclass, not a fresh class

`TickerMessage` already carries: `_FrameAware` mixin, `_font_color` resolution (Color or ColorProvider), `_end_padding`, `center`, BDF rendering of `" • "`. Reimplementing those for the smallsign fallback path would duplicate ~50 lines. Subclassing keeps the smallsign branch as a one-line `super().draw(...)` and the new logic confined to the hires branch.

---

## Wiring

### `ticker.py`

```python
DEFAULT_BUFFER_MSG: TickerMessage = _CircleBufferMsg()  # was TickerMessage(" • ", ...)
```

Type annotation stays `TickerMessage` since `_CircleBufferMsg` IS-A `TickerMessage`. No call sites change.

### `app.py:_resolve_buffer_msg`

Today the function returns `None` (inherit `DEFAULT_BUFFER_MSG`) when all four fields are unset, and builds a `TickerMessage` otherwise. New logic adds one branch for color-only overrides:

```python
def _resolve_buffer_msg(section: SectionConfig) -> TickerMessage | None:
    text_or_font_set = (
        section.separator is not None
        or section.separator_font is not None
        or section.separator_font_size is not None
    )
    color_set = section.separator_color is not None

    if not text_or_font_set and not color_set:
        return None  # inherit DEFAULT_BUFFER_MSG (white _CircleBufferMsg)

    color = (
        _coerce_color_provider(section.separator_color)
        if color_set
        else RGB_WHITE
    )

    if not text_or_font_set:
        # Color-only: still want the hi-res circle, just in a different color.
        return _CircleBufferMsg(color=color)

    # Explicit text / font: today's behavior, unchanged.
    text = section.separator if section.separator is not None else "•"
    if text == "":
        text = "  "
    kwargs: dict[str, Any] = {"text": text, "center": False, "font_color": color}
    if section.separator_font is not None:
        kwargs["font"] = _resolve_font(section.separator_font, section.separator_font_size)
    if section.separator_font_size is not None:
        kwargs["font_size"] = section.separator_font_size
    return TickerMessage(**kwargs)
```

`_CircleBufferMsg` is imported from `ticker.py`.

---

## Constraint compliance

Cross-checked against the load-bearing invariants in `CLAUDE.md`:

- **#1 (capture SwapOnVSync)** — the buffer message doesn't own its own swap loop. The engine (`_scroll_side_by_side`) captures swaps. No change.
- **#2 (DrawText requires real canvas)** — the smallsign branch calls `super().draw(...)` which goes through `TickerMessage.draw → DrawText` on a real canvas. The hires branch uses `SetPixel` on the unwrapped real canvas. No `DrawText` on wrappers.
- **#5 (swap-then-sleep)** — engine-controlled. No change.
- **#9 (ScaledCanvas wrapper survival)** — `_CircleBufferMsg.draw` does not re-wrap or rebind. The wrapper passed in is the engine's wrapper; we paint via `unwrap_to_real(canvas)` and leave the wrapper alone.
- **#11 (per-pixel scatter at physical res on ScaledCanvas)** — disk rasterization writes directly to `unwrap_to_real(canvas)` so a 32-physical-px circle is 32 physical px, not a 8-logical-px circle expanded to a chunky 32-px block. This is the entire point of the feature.
- **#12 (`advance_frame` per tick)** — `_scroll_side_by_side` already advances the buffer message per outer tick (deduped by `id()`). `_CircleBufferMsg` inherits `_FrameAware`, so `frame_for("color")` advances each tick and Rainbow / ColorCycle providers animate. `restart_on_visit = False` means the phase carries across loop iterations — continuous sweep rather than reset-per-loop, which is what users will want for the separator.

---

## Architecture

### File map

1. **`src/led_ticker/ticker.py`**:
   - Add `_CircleBufferMsg(TickerMessage)` private class.
   - Add `_draw_hires_circle(canvas, cursor_pos, color)` module-private helper.
   - Change `DEFAULT_BUFFER_MSG` value to `_CircleBufferMsg()`.

2. **`src/led_ticker/app.py`**:
   - Update `_resolve_buffer_msg` to route color-only configs through `_CircleBufferMsg` (new branch above).
   - Import `_CircleBufferMsg` from `ticker.py`.

3. **Tests** (`tests/test_ticker.py` or a new `tests/test_buffer_separator.py`):
   - Hires path: paints to unwrapped real canvas, 32×32 physical extent on a `ScaledCanvas(scale=4)`, color matches a constant provider.
   - Hires + Rainbow: color advances frame-to-frame.
   - Smallsign path: delegates to BDF `" • "` rendering, pixel-identical to today's `DEFAULT_BUFFER_MSG`.
   - Advance width: returns `cursor_pos + 10` on hires; `TickerMessage`-equivalent on smallsign. Layout-stable.
   - `tests/test_app.py`: `_resolve_buffer_msg` returns `_CircleBufferMsg` (not `TickerMessage`) when only `separator_color` is set.
   - `tests/test_ticker_display.py::TestScrollSideBySide`: tripwire that the default buffer renders a hi-res circle (no BDF text bleed) when fed a ScaledCanvas.

4. **Regression sweep**:
   - Every bundled example config + demo config validates with no rule changes.
   - Smallsign visual demos render byte-identical pixels to current main.
   - Bigsign demos: forever_scroll demos visibly improve (no chunky bullet); rule-26-clear configs unchanged.

5. **Docs**:
   - `docs/site/.../reference/config-options.mdx` — note in `separator` row: "On bigsign, the default separator renders as a smooth hi-res circle. Set `separator = '•'` (or anything else) to opt out and use BDF rendering."
   - `docs/site/.../concepts/sections-and-modes.mdx` — short paragraph if the forever_scroll section discusses the separator. One-line mention is enough.

### What stays the same

- TOML schema (`SectionConfig` fields unchanged).
- Validator rules (rule 26 still catches `separator_*` on wrong mode).
- `Ticker.__init__` signature and `buffer_msg` parameter.
- `_scroll_side_by_side` internals — it calls `buffer_message.draw(canvas, cursor_pos)` and trusts the duck-typed return. Both old and new code satisfy that contract.
- Smallsign behavior — zero pixel drift.

---

## Test plan

### `tests/test_buffer_separator.py` (new file)

- `test_circle_buffer_msg_hires_paints_filled_disk` — feed a `ScaledCanvas(scale=4)`, assert ~ `π * 16² ≈ 800` SetPixel calls on the unwrapped real canvas, all in the expected bounding box.
- `test_circle_buffer_msg_hires_color_applied_uniformly` — constant color provider; every painted pixel has that RGB.
- `test_circle_buffer_msg_hires_rainbow_animates_per_frame` — call `draw` twice with `advance_frame` between; assert the painted color differs (hue swept by frame counter).
- `test_circle_buffer_msg_smallsign_delegates_to_bdf` — feed a plain `Canvas` (no ScaledCanvas wrap); assert DrawText was called with `" • "` (or pixel-identity against today's `TickerMessage(" • ", font_color=WHITE).draw(canvas)`).
- `test_circle_buffer_msg_advance_width_logical_10` — return value on hires `(canvas, cursor_pos + 10)`.
- `test_circle_buffer_msg_advance_matches_today_on_smallsign` — return value on smallsign equals `TickerMessage(" • ").draw(canvas)`'s return.
- `test_circle_paints_to_unwrapped_canvas` — assert all painted pixels land on `canvas.real`, not on the wrapper (tripwire for constraint #11).

### `tests/test_app.py`

- `test_resolve_buffer_msg_color_only_returns_circle_buffer_msg` — only `separator_color = [255, 0, 0]` set; assert result is `_CircleBufferMsg` instance with red provider, NOT a `TickerMessage` with BDF "•".
- Existing `test_resolve_buffer_msg_returns_none_when_all_fields_unset` still passes (None → engine inherits `DEFAULT_BUFFER_MSG`, which is now a `_CircleBufferMsg`).
- Existing `test_resolve_buffer_msg_with_separator_text_only` still passes (explicit text → TickerMessage path).
- `test_resolve_buffer_msg_with_separator_font_only` — `separator_font` set, `separator_color` unset; returns TickerMessage with default WHITE color (no circle even though only one field is set, because font is in the "text-or-font" set).

### `tests/test_ticker_display.py`

- Extend `TestScrollSideBySide` with a case at `scale=4`: the default buffer between two widgets renders as a hi-res disk (assertion: bounding box of non-black pixels in the buffer's physical extent matches a circular pattern, not a vertically-tall BDF cell).

### Meta-tripwires

- `tests/test_docs_config_options_drift.py` — no change. No new fields added.
- `tests/test_engine_redraw_contract.py` — no change. The AST scan only looks at `ticker.py`'s `_swap_and_scroll` family; adding a new private class doesn't introduce per-tick draw loops.

### Regression sweep

- `make test` clean.
- `led-ticker validate` against every bundled `config.*.example.toml` — no new errors, no new warnings.
- `tools/render_demo` snapshot for smallsign forever_scroll demo: byte-identical to current main.
- `tools/render_demo` snapshot for bigsign forever_scroll demo: visibly different (hi-res circle replaces chunky bullet) — manual eyeball check during PR review.

---

## Out of scope

- Configurable circle radius / outline mode / non-circle shapes. If a user wants a different separator shape, the `separator = "★"` / `separator = ":some_emoji:"` paths already cover that (the latter only if emoji rendering inside TickerMessage works for buffer messages — separate question, not blocking).
- Animating the circle's size or shape (pulse, breathing). Color animation via existing providers is enough.
- A new global `[transitions]` default for the buffer-separator shape. Per-section knobs are sufficient; a global override invites the "which section wins" question for marginal benefit.
- Re-routing the `scroll` transition's bullet (`_draw_bullet` in `transitions/effects.py`) to a hi-res circle. That's a different code path with different layout rules; if it's worth doing, it's a separate spec.
- Smallsign visual change. Considered Option B (unified SetPixel circle on both displays) per the brainstorming agent review; rejected for asymmetric regression risk with no smallsign benefit.

---

## Implementation notes

- `_CircleBufferMsg.__init__` accepts `color: Color | ColorProvider`. Parent `TickerMessage.__init__` already normalizes `font_color` to a `ColorProvider`; we read `self._font_color` in the override.
- The disk rasterization should use integer math only — no `math.sqrt` per pixel in the hot path. Precompute row half-widths once at module import; the existing `_generate_moon_hires` integer scan is a working template.
- `_draw_hires_circle` is module-private to `ticker.py`. If a future spec wants a shared "draw a hi-res primitive" helper, factor out then — YAGNI for now.
- The `_CircleBufferMsg` is exported as part of `ticker.py`'s public surface only insofar as `app.py` needs to import it. No `__all__` change; not a user-facing API.
- Existing rule 26 wording in `validate.py` mentions four `separator_*` field names. No update needed — they're all still real config fields with their documented behavior.
