# Design: `bottom_text_loops` on `TwoRowMessage`

**Date:** 2026-05-14
**Status:** Approved

## Overview

`TwoRowMessage` gained a `bottom_text_wrap` mode in PR #59 (seamless marquee with separator). That work didn't add a way to control HOW MANY wrap cycles the bottom row plays before the section transitions — today the engine times out via `hold_time` alone. Image widgets (`gif`, `image`) already have `text_loops` for exactly this control on their two-row mode.

This spec adds **`bottom_text_loops`** to `TwoRowMessage` to close that gap. The semantics match `_BaseImageWidget.text_loops` in two-row wrap mode: minimum number of full wrap cycles (one cycle = `bottom_text` + separator).

Motivating case: a section with `bottom_text_wrap = true` should be able to declare "play this marquee 4 times before transitioning" rather than guessing the right `hold_time` value.

---

## Field surface

```toml
[[playlist.section.widget]]
type = "two_row"
top_text = ":instagram: @moonbunnyaerial"
bottom_text = "Now booking spring classes — all levels welcome!"
bottom_text_wrap = true
bottom_text_loops = 4    # minimum cycles before the section can end
```

- **Type:** `bottom_text_loops: int = 0`
- **Default:** `0` (matches `_BaseImageWidget.text_loops` default — no minimum, today's behavior preserved)
- **Semantics:**
  - `0` (default): engine uses `hold_time` alone (today's behavior; no change)
  - `> 0`: engine extends section duration so the bottom row completes at least N full wrap cycles. If `hold_time / scroll_speed` already exceeds `N × cycle_ticks`, the longer duration wins (same `max(...)` semantics as `_BaseImageWidget`).
  - `< 0`: validation error.

### Why `bottom_text_loops` and not `text_loops`

TwoRowMessage uses the `bottom_*` prefix convention for per-row knobs (matches `bottom_text_wrap`, `bottom_text_separator`, `bottom_text_separator_color`). CLAUDE.md explicitly documents this convention. Naming it unprefixed `text_loops` would violate it.

The asymmetry with image widgets is acknowledged: image widgets are fundamentally single-row that optionally become two-row, so they use unprefixed `text_loops` for both modes. TwoRowMessage is always two-row, so prefix conveys precision. The validator gap fix (separate work) makes the user-side cost low — copy-pasting `text_loops` from a gif into a `two_row` widget surfaces a clear error pointing at `bottom_text_loops`.

---

## Scope: wrap mode only

`bottom_text_loops > 0` is **only meaningful when `bottom_text_wrap = true`**.

In non-wrap mode the bottom row scrolls once over its overflow distance, then stops at its natural end-of-content position. There's no concept of "cycle" without the wrap separator. The engine already handles overflow termination via cursor_pos overshoot — there's no clean way to retrofit "scroll N times" onto that path without adding new engine state.

**Validation:** `bottom_text_loops > 0` with `bottom_text_wrap = false` → error. Tells the user to either turn on wrap or drop the loop count.

---

## Engine cooperation

`TwoRowMessage.draw()` in wrap mode ALREADY returns `cycle_width` as the second tuple element (`return canvas, cycle_width` at `two_row.py:492`). The engine's wrap-forever branch (`ticker.py:1027-1042`) currently discards it:

```python
canvas, _ = ticker_obj.draw(canvas, cursor_pos=pos)
```

Replace with a first-iteration capture. The engine extends `n_ticks` on tick 0 using the cycle width the widget just measured:

```python
n_ticks = max(1, int(hold_time / scroll_speed))
loops_floor = getattr(ticker_obj, "bottom_text_loops", 0)
tick = 0
while tick < n_ticks:
    _advance_frame_if_supported(ticker_obj)
    reset_canvas(canvas, bg_color)
    canvas, cycle_width = ticker_obj.draw(canvas, cursor_pos=pos)
    if tick == 0 and loops_floor > 0 and cycle_width > 0:
        n_ticks = max(n_ticks, loops_floor * cycle_width)
    canvas = _swap(canvas, frame)
    pos -= 1
    await asyncio.sleep(scroll_speed)
    tick += 1
```

### Why not a separate property

The cycle width depends on canvas + font metrics; the widget can't compute it without a canvas reference. The widget already does the measurement inside `draw()`. Returning it from `draw()` is the smallest contract; the engine captures it on the first tick and that's the whole mechanism. No new property, no new method.

### Cycle width is in logical pixels per tick

The wrap branch's `cycle_width = self._bottom_width + sep_width` is in LOGICAL pixels. The engine advances `pos -= 1` per tick (one logical pixel per tick). So `cycle_width` literally IS "ticks per one wrap cycle." `loops_floor * cycle_width` is the n_ticks floor. No unit conversion.

---

## Validation (rule 27)

Two checks, mirroring the shape of rule 25 / 26:

| Location | Trigger | Severity |
| --- | --- | --- |
| `section[i].widget[j]` | `bottom_text_loops < 0` | error |
| `section[i].widget[j]` | `bottom_text_loops > 0` AND `bottom_text_wrap = false` | error |

Both checks live in `_check_static` at the widget level. The widget's own `__attrs_post_init__` should also raise on `bottom_text_loops < 0` (defensive, matches `text_loops` on `_BaseImageWidget`); the validator surfaces the same check earlier.

---

## Architecture

### File map

1. **`src/led_ticker/widgets/two_row.py`**:
   - Add `bottom_text_loops: int = attrs.field(default=0, kw_only=True)`
   - Validate `bottom_text_loops >= 0` in `__attrs_post_init__`
   - Validate `bottom_text_loops > 0` requires `bottom_text_wrap = True` in `__attrs_post_init__`
   - No new property — engine reads cycle_width from `draw()`'s existing return value

2. **`src/led_ticker/ticker.py`**:
   - Extend the `wraps_forever` branch in `_swap_and_scroll` to incorporate `bottom_text_loops`

3. **`src/led_ticker/validate.py`**:
   - Rule 27: section-level / widget-level check for the same two conditions enforced in `__attrs_post_init__`

4. **`tests/test_widgets/test_two_row_wrap.py`** — widget-level tests:
   - `bottom_text_loops = 0` preserves today's behavior (default)
   - `bottom_text_loops = 4` with `bottom_text_wrap = False` raises in `__attrs_post_init__`
   - `bottom_text_loops < 0` raises in `__attrs_post_init__`
   - `bottom_text_loops = 4` with wrap=True constructs cleanly

5. **`tests/test_ticker_wraps_forever.py`** — engine cooperation:
   - When `bottom_text_loops > 0`, engine runs at least `bottom_text_loops × bottom_loop_ticks` ticks
   - When `bottom_text_loops = 0`, engine ticks unchanged from today's behavior
   - When `hold_time` would produce more ticks than `bottom_text_loops × bottom_loop_ticks`, the longer duration wins

6. **`tests/test_validate.py`** — rule 27 tests:
   - `bottom_text_loops > 0` with wrap=off → error
   - `bottom_text_loops < 0` → error
   - `bottom_text_loops > 0` with wrap=on → clean
   - `bottom_text_loops = 0` (default) → clean

7. **Meta-tripwire** — `tests/test_docs_config_options_drift.py`. NOTE: `bottom_text_loops` is a widget field, not a section field; check whether the drift-test covers widget-level keys. If yes, update the allow-list in the same commit as the docs row. If no, no change needed.

8. **Docs**:
   - `docs/site/.../widgets/two_row.mdx` — add `bottom_text_loops` to the field table, explain the wrap-only constraint, link to the image widget's `text_loops` for cross-reference
   - `docs/site/.../pitfalls.mdx` — Rule 27 entry under Errors
   - `docs/site/.../tools/validate.mdx` — Rule 27 row in reference table

---

## Test plan

Beyond the per-file test list above:

- **Regression sweep:** validate every existing example config in `config/` and `docs/site/demos-*/`. None set `bottom_text_loops` today, so zero rule-27 hits expected.
- **Smoke test on the moonbunny scenario:**
  ```toml
  [[playlist.section.widget]]
  type = "two_row"
  bottom_text = "Now booking spring classes — all levels welcome!"
  bottom_text_wrap = true
  bottom_text_loops = 4
  ```
  Validates clean. Runtime plays the marquee 4 times.

---

## Out of scope

- **`text_loops` on TwoRowMessage as alias for `bottom_text_loops`.** Decided against in the brainstorming phase — would complicate the bottom_* convention. The validator gap fix (separate work, see below) makes the typo case surface clearly.
- **`bottom_text_loops` for non-wrap mode.** Would need new engine logic to repeat the natural-overflow scroll. Not requested and adds surface area; rejected via rule 27.
- **`top_text_loops`.** The top row is held; loops don't apply.
- **Renaming `text_loops` on `_BaseImageWidget` to `bottom_text_loops` in two-row mode.** Would create alias surface there too. Skip — image widgets are different shape (single-row that optionally becomes two-row).

---

## Related follow-up: validator unknown-kwarg check

This spec deliberately does NOT cover the broader validator gap that allowed the user's `text_loops = 4` on a `two_row` widget to slip past `make validate`. That gap is a separate bug fix:

> `_build_widget(validate_only=True)` returns `None` BEFORE the `cls(**widget_cfg)` call, so unknown TOML keys (typos like `text_loops` on `two_row`) never surface as validation errors. Pre-construction strict-kwarg check against `cls.__attrs_attrs__` would catch this for attrs-based widgets without async `start()` hooks.

That fix is recommended as a separate small PR after (or in parallel with) this feature. Without it, after this spec lands a user who STILL writes `text_loops = 4` on `two_row` (out of habit from gif/image) would see the runtime crash again — the new `bottom_text_loops` is the answer, but the validator should point them at it.

---

## Implementation notes

- The widget's wrap cycle width math is already implemented in `draw()` and is already returned as the second tuple element. No new widget code paths.
- Engine cooperation: convert the existing `for _ in range(n_ticks)` loop to a `while tick < n_ticks` loop so n_ticks can be extended after the first iteration's `draw()` returns the cycle width.
- The post-init validation in `TwoRowMessage` mirrors `_BaseImageWidget.__attrs_post_init__`'s `text_loops < 0` check (line ~315). Pattern-match the error message phrasing.
- For the engine test, use a Mock widget with `wraps_forever=True`, `bottom_text_loops=N`, and a `draw()` side_effect that returns `(canvas, W)` (a constant cycle width). Assert `draw()` is called at least `N*W` times when `hold_time / scroll_speed < N*W`, and exactly the hold_time-based number when `hold_time / scroll_speed >= N*W`.
