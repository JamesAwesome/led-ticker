# Per-Effect Frame Counters Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate the composition tradeoff from PR #11 — a widget with both `Typewriter` (wants restart-on-visit) and a continuous-phase effect (`Rainbow` / `ColorCycle` / `RainbowChaseBorder`) should now have BOTH behaviors work as designed simultaneously.

**Architecture:** `_FrameAware` mixin gains a `_effect_frames: dict[str, int]` field tracking per-attribute frame counters. Widget code reads `self.frame_for(attr_name)` instead of `self._frame_count`. The widget's `_frame_count` is preserved with today's semantic for back-compat. `_show_one`'s `_should_reset_frame()` gate is deleted; the widget's `reset_frame()` itself does the per-effect work.

**Tech Stack:** Python 3.13, attrs, asyncio, pytest, ruff. No new dependencies.

**Spec:** [`docs/superpowers/specs/2026-05-07-per-effect-counters-design.md`](../specs/2026-05-07-per-effect-counters-design.md)

**Worktree:** `.claude/worktrees/per-effect-counters` (branch `feat/per-effect-counters`)

---

## File Inventory

**Modified:**
- `src/led_ticker/widgets/_frame_aware.py` — add `_EFFECT_ATTRS` class constant, `_effect_frames` field, `_iter_effects()`, update `advance_frame()` / `reset_frame()`, add `frame_for()`.
- `src/led_ticker/widgets/message.py` — 5 call sites change from `self._frame_count` to `self.frame_for(attr_name)`.
- `src/led_ticker/widgets/two_row.py` — 3 call sites change.
- `src/led_ticker/widgets/_image_base.py` — 10 call sites change.
- `src/led_ticker/ticker.py` — delete `_should_reset_frame()` helper (lines 709-739); revert `_show_one` gate (line 766) to unconditional `reset_frame()` call.
- `tests/test_frame_aware.py` — append new `TestEffectFrames` class (5 tests).
- `tests/test_ticker_display.py` — delete `TestShouldResetFrame` (5 tests, lines ~1251-1320) and `TestShouldResetFrameComposition` (1 test, lines ~1321+); add `TestTypewriterPlusRainbowBorderComposition` (3 tests).
- `config/config.rainbow_border_test.example.toml` — rewrite §17 comment header.
- `CLAUDE.md` — replace the composition-rule paragraph in the Rainbow border section.

**Not modified (referenced):**
- `src/led_ticker/borders.py`, `src/led_ticker/color_providers.py`, `src/led_ticker/animations.py` — effect classes unchanged. The `restart_on_visit = False` class attributes set in PR #11 stay; only their consumer location moves.
- `src/led_ticker/transitions/__init__.py:184` — `_reset_presenter(incoming)` already resets at every transition entry. Section-entry reset path is preserved by construction.

---

## Implementation Conventions

**TDD discipline:** every task writes the failing test first, runs to confirm fail, implements, runs to confirm pass, commits.

**Migration order is safe step-by-step:**
- After T1 (mixin update): infrastructure exists but widgets don't use it; behavior unchanged because the gate is still in effect.
- After T2–T4 (widget call site migration): `frame_for(attr)` returns identical values to `self._frame_count` while the gate is still in place; behavior unchanged.
- After T5 (gate delete): the new behavior activates. `_show_one` resets unconditionally; `reset_frame()` itself does the per-effect work. Composition tradeoff disappears.

This means each task can land on its own without breaking existing tests. The full behavior change is gated by T5.

**Test commands** (from worktree root):
- One file: `PYTHONPATH=tests/stubs uv run pytest tests/test_frame_aware.py -v`
- One test: `PYTHONPATH=tests/stubs uv run pytest tests/test_frame_aware.py::TestEffectFrames::test_advance_increments_per_effect_counter -v`
- Full suite: `PYTHONPATH=tests/stubs uv run pytest -x -q`

**Lint:** `uv run ruff check src/led_ticker tests` after each task.

---

### Task 1: `_FrameAware` mixin refactor + per-effect tests

**Files:**
- Modify: `src/led_ticker/widgets/_frame_aware.py` (entire mixin body)
- Test: `tests/test_frame_aware.py` (append new `TestEffectFrames` class)

The mixin gains `_EFFECT_ATTRS` (class constant), `_effect_frames` (instance dict), `_iter_effects()`, `frame_for()`, and per-effect logic in `advance_frame()` / `reset_frame()`. The existing `_frame_count` field stays — its semantic is preserved.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_frame_aware.py` (after the existing `TestFrameAware` class):

```python
class TestEffectFrames:
    """Per-effect frame counter behavior. The mixin tracks one
    counter per effect attribute (`font_color`, `top_color`,
    `bottom_color`, `border`, `animation`). Each counter follows
    its effect's `restart_on_visit` policy: True (default) zeros on
    `reset_frame()`; False keeps climbing for continuous phase."""

    def _make_widget_with_effects(self, **effects):
        """Construct a `_Dummy` subclass with the requested effect
        attributes. Effect classes inline so each test is self-
        contained."""
        @attrs.define
        class _WithEffects(_FrameAware):
            font_color: object = attrs.field(default=None, kw_only=True)
            border: object = attrs.field(default=None, kw_only=True)
            animation: object = attrs.field(default=None, kw_only=True)

        return _WithEffects(**effects)

    def test_advance_increments_per_effect_counter(self):
        """Per-effect counter climbs in lockstep with `_frame_count`."""

        class _Border:
            restart_on_visit = False

        widget = self._make_widget_with_effects(border=_Border())
        for _ in range(5):
            widget.advance_frame()
        assert widget._frame_count == 5
        assert widget._effect_frames["border"] == 5

    def test_reset_zeros_only_opted_in_effects(self):
        """Continuous-phase effects (restart_on_visit=False) keep
        their counter; restart-on-visit effects zero theirs."""

        class _Typewriter:
            restart_on_visit = True

        class _RainbowBorder:
            restart_on_visit = False

        widget = self._make_widget_with_effects(
            animation=_Typewriter(),
            border=_RainbowBorder(),
        )
        for _ in range(7):
            widget.advance_frame()
        assert widget._effect_frames["animation"] == 7
        assert widget._effect_frames["border"] == 7

        widget.reset_frame()
        assert widget._frame_count == 0
        # Restart-on-visit effect: zeroed
        assert widget._effect_frames["animation"] == 0
        # Continuous-phase effect: unchanged
        assert widget._effect_frames["border"] == 7

    def test_pause_freezes_all_counters(self):
        """Paused widget = all counters frozen, both primary and
        per-effect."""

        class _Border:
            restart_on_visit = False

        widget = self._make_widget_with_effects(border=_Border())
        widget.advance_frame()  # counters at 1
        widget.pause_frame()
        for _ in range(10):
            widget.advance_frame()
        assert widget._frame_count == 1
        assert widget._effect_frames["border"] == 1

    def test_frame_for_falls_back_to_frame_count(self):
        """Lookup of an attr_name not in the dict returns
        `_frame_count`. Covers the case where a test sets
        `_frame_count` directly without going through `advance_frame`."""

        class _Border:
            restart_on_visit = False

        widget = self._make_widget_with_effects(border=_Border())
        widget._frame_count = 42  # direct write, no advance_frame
        # `_effect_frames` is empty (no advance has populated it yet)
        assert widget._effect_frames == {}
        # frame_for falls back to _frame_count
        assert widget.frame_for("border") == 42

    def test_unknown_effect_class_resets_by_default(self):
        """Effect class without a `restart_on_visit` attribute uses
        the `getattr` default of True — same as the engine-side
        gate did in PR #11. Back-compat for any third-party effect."""

        class _CustomEffect:
            pass  # no restart_on_visit attribute

        widget = self._make_widget_with_effects(font_color=_CustomEffect())
        for _ in range(3):
            widget.advance_frame()
        assert widget._effect_frames["font_color"] == 3

        widget.reset_frame()
        # No restart_on_visit attribute → defaults to True → zeroes
        assert widget._effect_frames["font_color"] == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_frame_aware.py::TestEffectFrames -v`

Expected: FAIL with `AttributeError: 'X' object has no attribute '_effect_frames'` (and similar for `frame_for`).

- [ ] **Step 3: Refactor the `_FrameAware` mixin**

Replace the entire body of `src/led_ticker/widgets/_frame_aware.py` with:

```python
"""Frame counter mixin shared by every text-painting widget.

Each widget tracks its own `_frame_count` (engine tick counter,
resets per visit) AND a parallel `_effect_frames` dict tracking
per-effect-attribute counters that follow each effect's
`restart_on_visit` policy.

The orchestrator calls `advance_frame()` per draw tick (both the
primary counter and all per-effect counters increment). Transitions
call `pause_frame()` / `resume_frame()` around their compositing
loop so the count doesn't drift while the widget is being re-
rendered for a dissolve. `reset_frame()` is called by
`ticker._show_one` at the start of each visit; the primary counter
always resets, while per-effect counters reset only for effects
that opted into restart-on-visit (default `True` via `getattr`
fallback).

Widget code reads `self.frame_for(attr_name)` instead of
`self._frame_count` when calling effect APIs. This lets a widget
with both `Typewriter` (restart=True) and `RainbowChaseBorder`
(restart=False) get correct behavior on `loop_count > 1`: the
typewriter retypes each loop while the chase phase advances
continuously.

Use as a mixin alongside `@attrs.define` on each widget class. The
`init=False` fields don't show up in TOML; they're internal state.
"""

from __future__ import annotations

import attrs


@attrs.define
class _FrameAware:
    """Mixin providing per-widget + per-effect frame counters."""

    _EFFECT_ATTRS: tuple[str, ...] = (
        "font_color",
        "top_color",
        "bottom_color",
        "border",
        "animation",
    )

    _frame_count: int = attrs.field(init=False, default=0)
    _frame_paused: bool = attrs.field(init=False, default=False)
    _effect_frames: dict[str, int] = attrs.field(init=False, factory=dict)

    def _iter_effects(self):
        """Yield (attr_name, effect_instance) for each non-None
        effect on the widget. Centralized so `advance_frame`,
        `reset_frame`, and any future callers can't drift."""
        for attr in self._EFFECT_ATTRS:
            effect = getattr(self, attr, None)
            if effect is not None:
                yield attr, effect

    def advance_frame(self) -> None:
        """Increment the primary counter AND all per-effect counters.
        No-op if paused."""
        if self._frame_paused:
            return
        self._frame_count += 1
        for attr_name, _ in self._iter_effects():
            self._effect_frames[attr_name] = (
                self._effect_frames.get(attr_name, 0) + 1
            )

    def pause_frame(self) -> None:
        """Stop advancing the frame counters — used by `run_transition`
        so an outgoing widget mid-typewriter (etc.) doesn't keep
        ticking while it's only being re-rendered for compositing."""
        self._frame_paused = True

    def resume_frame(self) -> None:
        self._frame_paused = False

    def reset_frame(self) -> None:
        """Visit-entry reset. The primary counter always resets;
        per-effect counters reset only for effects that opted in
        via `restart_on_visit = True` (the default). Effects with
        `restart_on_visit = False` keep their counter — that's what
        gives `RainbowChaseBorder` continuous phase across loop_count
        boundaries while still letting `Typewriter` retype.

        Does NOT clear the pause flag — pause/resume are
        transition-scoped, reset is visit-scoped, the two are
        independent."""
        self._frame_count = 0
        for attr_name, effect in self._iter_effects():
            if getattr(effect, "restart_on_visit", True):
                self._effect_frames[attr_name] = 0

    def frame_for(self, attr_name: str) -> int:
        """Return the per-effect frame counter, or `_frame_count` as
        a fallback for unknown / unset entries.

        Widget code calls this when invoking an effect API:
        `border.paint(canvas, self.frame_for("border"))`. The
        fallback to `_frame_count` covers the lazy-init case where
        a test sets `_frame_count` directly without going through
        `advance_frame`."""
        return self._effect_frames.get(attr_name, self._frame_count)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_frame_aware.py -v`

Expected: PASS — both the existing 6-test `TestFrameAware` class (because `_Dummy` has no effect attributes, the new dict-iteration is a no-op) and the 5 new tests in `TestEffectFrames`.

- [ ] **Step 5: Run full suite**

Run: `PYTHONPATH=tests/stubs uv run pytest -x -q`

Expected: all green. Behavior is unchanged from main because (a) widgets still pass `self._frame_count` to effects (haven't migrated yet), and (b) the `_should_reset_frame()` gate in `ticker.py` still blocks per-visit resets for continuous-phase widgets.

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/widgets/_frame_aware.py tests/test_frame_aware.py
git commit -m "per-effect-counters: _FrameAware mixin gains per-effect counter dict + frame_for()"
```

---

### Task 2: Migrate `widgets/message.py` call sites

**Files:**
- Modify: `src/led_ticker/widgets/message.py` (5 call sites: TickerMessage at lines 80, 118, 137, 155, 158; TickerCountdown at lines 232, 244, 247)

Wait — `widgets/message.py` actually has 8 call sites total (5 in TickerMessage, 3 in TickerCountdown). The plan handles all 8 in this task. Each `self._frame_count` reference becomes `self.frame_for(attr_name)` where `attr_name` matches the effect attribute being read.

- [ ] **Step 1: Read the current `TickerMessage.draw` method (lines 54-180)**

Run: `sed -n '54,180p' src/led_ticker/widgets/message.py`

Verify the current call sites:
- Line 80: `self.animation.frame_for(self._frame_count, full_text, ...)` — animation
- Line 118: `self.border.paint(canvas, self._frame_count)` — border
- Line 137: `frame=self._frame_count` (passed to `draw_with_emoji`) — font_color
- Line 155: `lambda idx, total: provider.color_for(self._frame_count, idx, total)` — font_color
- Line 158: `provider.color_for(self._frame_count, 0, len(visible_text))` — font_color

- [ ] **Step 2: Update TickerMessage call sites**

In `src/led_ticker/widgets/message.py`, replace each occurrence in `TickerMessage.draw`:

```python
# Line 80 (inside animation branch):
            anim_frame = self.animation.frame_for(
                self.frame_for("animation"), full_text, canvas.width, self._content_width
            )
```

```python
# Line 118 (border paint):
        if self.border is not None:
            self.border.paint(canvas, self.frame_for("border"))
```

```python
# Line 137 (draw_with_emoji frame):
            cursor_pos += draw_with_emoji(
                canvas,
                self.font,
                cursor_pos,
                baseline_y,
                provider,
                visible_text,
                y_offset=y_offset,
                frame=self.frame_for("font_color"),
            )
```

```python
# Line 155 (per-char provider lambda):
            cursor_pos += draw_text_per_char(
                canvas,
                self.font,
                cursor_pos,
                baseline_y + y_offset,
                visible_text,
                lambda idx, total: provider.color_for(
                    self.frame_for("font_color"), idx, total
                ),
            )
```

```python
# Line 158 (single-color provider call):
        else:
            color = provider.color_for(
                self.frame_for("font_color"), 0, len(visible_text)
            )
```

- [ ] **Step 3: Update TickerCountdown call sites**

In `src/led_ticker/widgets/message.py`, in `TickerCountdown.draw` (lines ~207-253), replace:

```python
# Line 232 (border paint):
        if self.border is not None:
            self.border.paint(canvas, self.frame_for("border"))
```

```python
# Line 244 (per-char provider lambda):
            cursor_pos += draw_text_per_char(
                canvas,
                self.font,
                cursor_pos,
                baseline_y + y_offset,
                text,
                lambda idx, total: provider.color_for(
                    self.frame_for("font_color"), idx, total
                ),
            )
```

```python
# Line 247 (single-color provider call):
        else:
            color = provider.color_for(
                self.frame_for("font_color"), 0, len(text)
            )
```

- [ ] **Step 4: Run the existing TickerMessage / TickerCountdown tests to verify no regressions**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_widgets/test_message.py -v 2>&1 | tail -20`

Expected: all PASS. Behavior is unchanged because `frame_for(attr)` falls back to `_frame_count` when the dict is empty (which is the case before `advance_frame` populates it). After `advance_frame` populates entries, those entries climb in lockstep with `_frame_count` — so reads return the same values until the gate is removed in T5.

- [ ] **Step 5: Run full suite**

Run: `PYTHONPATH=tests/stubs uv run pytest -x -q`

Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/widgets/message.py
git commit -m "per-effect-counters: migrate widgets/message.py call sites to frame_for()"
```

---

### Task 3: Migrate `widgets/two_row.py` call sites

**Files:**
- Modify: `src/led_ticker/widgets/two_row.py` (3 call sites: lines 254, 268, 289)

The two-row widget passes `self._frame_count` for the border (1 site) and for both top + bottom row's color providers (2 sites — one for top via `draw_with_emoji`, one for bottom).

- [ ] **Step 1: Read the current call sites**

Run: `sed -n '250,295p' src/led_ticker/widgets/two_row.py`

Verify the 3 call sites:
- Line 254: `self.border.paint(canvas, self._frame_count)` — border
- Line 268: `frame=self._frame_count` (top row's `draw_with_emoji`) — top_color
- Line 289: `frame=self._frame_count` (bottom row's `draw_with_emoji`) — bottom_color

- [ ] **Step 2: Update the call sites**

In `src/led_ticker/widgets/two_row.py`:

```python
# Line 254 (border paint):
        if self.border is not None:
            self.border.paint(canvas, self.frame_for("border"))
```

```python
# Line 268 (top row's draw_with_emoji):
        draw_with_emoji(
            canvas,
            top_font,
            top_x,
            top_text_y,
            self.top_color,
            self.top_text,
            y_offset=top_text_y_offset,
            emoji_y=top_emoji_y,
            frame=self.frame_for("top_color"),
        )
```

```python
# Line 289 (bottom row's draw_with_emoji):
        draw_with_emoji(
            canvas,
            bottom_font,
            bottom_x,
            bottom_text_y,
            self.bottom_color,
            self.bottom_text,
            y_offset=bottom_text_y_offset,
            emoji_y=bottom_emoji_y,
            frame=self.frame_for("bottom_color"),
        )
```

- [ ] **Step 3: Run the existing TwoRow tests**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_widgets/test_two_row.py -v 2>&1 | tail -20`

Expected: all PASS. Same back-compat reasoning as T2.

- [ ] **Step 4: Run full suite**

Run: `PYTHONPATH=tests/stubs uv run pytest -x -q`

Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/widgets/two_row.py
git commit -m "per-effect-counters: migrate widgets/two_row.py call sites to frame_for()"
```

---

### Task 4: Migrate `widgets/_image_base.py` call sites

**Files:**
- Modify: `src/led_ticker/widgets/_image_base.py` (10 call sites: lines 438, 450, 455, 505, 515, 520, 577, 581, 586, 621)

The image widget base has the most call sites because it covers single-row text path (`_render_tick`), two-row text path (`_render_two_row_tick`), and several border-paint sites across the single-row sub-modes.

- [ ] **Step 1: Read the current call sites**

Run: `grep -n "self._frame_count" src/led_ticker/widgets/_image_base.py`

Verify the 10 sites and group them by attribute:
- `font_color`: lines 438 (emoji frame), 450 (per-char lambda), 455 (single-color call). Single-row text path.
- `top_color`: line 505 (top emoji frame).
- `bottom_color`: lines 515 (per-char lambda), 520 (single-color call).
- `border`: lines 577, 581, 586 (single-row border paints across 3 sub-modes), 621 (two-row border paint).

- [ ] **Step 2: Update the `font_color` call sites (lines 438, 450, 455)**

In `src/led_ticker/widgets/_image_base.py`, in the single-row text helpers:

```python
# Line 438 (emoji frame for single-row text):
            cursor_pos = draw_with_emoji(
                text_canvas,
                self.font,
                x,
                baseline_y + self.text_y_offset,
                color,
                self.text,
                y_offset=0,
                frame=self.frame_for("font_color"),
            )
```

```python
# Line 450 (per-char lambda for single-row text):
            cursor_pos = draw_text_per_char(
                text_canvas,
                self.font,
                x,
                baseline_y + self.text_y_offset,
                self.text,
                lambda idx, total: color.color_for(
                    self.frame_for("font_color"), idx, total
                ),
            )
```

```python
# Line 455 (single-color call for single-row text):
        else:
            color_value = color.color_for(
                self.frame_for("font_color"), 0, len(self.text) if self.text else 1
            )
```

- [ ] **Step 3: Update `_draw_row_text` to accept a `frame_count` parameter**

`_draw_row_text` is the shared helper that renders one row's text + emoji. Today it reads `self._frame_count` directly (3 sites: 505, 515, 520). It doesn't know whether it's rendering the top or bottom row — the caller knows. Add a `frame_count: int` keyword-only parameter and have the caller pass the per-effect counter.

In `src/led_ticker/widgets/_image_base.py`, change the `_draw_row_text` signature (lines 474-483) to:

```python
    def _draw_row_text(
        self,
        canvas: Canvas,
        font: Any,
        text: str,
        color: Any,
        x: int,
        baseline_y: int,
        emoji_y: int,
        frame_count: int,
    ) -> None:
        """Draw one row's text given pre-resolved font / text / color.
        Caller (`_render_two_row_tick`) resolves these once outside the
        tick loop so per-row attribute lookups don't run every frame.
        Mirrors `_draw_text` but accepts an explicit `emoji_y` so the
        emoji can be nudged independently of the text baseline.

        `color` accepts a Color or a ColorProvider. Provider + emoji
        flows through `draw_with_emoji` for per-char rainbow support.
        `frame_count` is the per-effect counter the caller looked up
        via `self.frame_for("top_color")` or `self.frame_for("bottom_color")`
        — passed explicitly because this helper doesn't know which
        row it's drawing for.
        """
```

Then update the body — replace each `self._frame_count` with `frame_count`:

```python
# Line 505 (was: frame=self._frame_count):
            draw_with_emoji(
                canvas,
                font,
                x,
                baseline_y,
                color,
                text,
                emoji_y=emoji_y,
                max_emoji_height=EMOJI_ROW_CAP,
                frame=frame_count,
            )
```

```python
# Line 515 (was: lambda ... self._frame_count, idx, total):
            draw_text_per_char(
                canvas,
                font,
                x,
                baseline_y,
                text,
                lambda idx, total: color.color_for(frame_count, idx, total),
            )
```

```python
# Line 520 (was: color = color.color_for(self._frame_count, 0, len(text)...)):
            if hasattr(color, "color_for"):
                color = color.color_for(frame_count, 0, len(text) if text else 1)
```

- [ ] **Step 4: Update `_render_two_row_tick` to pass per-effect frames**

In `src/led_ticker/widgets/_image_base.py`, lines 622-623 currently splat row tuples. Add the per-effect frame as a trailing keyword argument:

```python
        self._draw_row_text(
            text_canvas, *top, frame_count=self.frame_for("top_color")
        )
        self._draw_row_text(
            text_canvas, *bottom, frame_count=self.frame_for("bottom_color")
        )
```

- [ ] **Step 5: Update the `border` call sites (lines 577, 581, 586, 621)**

In `_render_tick` (3 sub-modes: scroll, scroll_over, non-scroll) and `_render_two_row_tick`:

```python
# Line 577 (scroll mode — border last, after skip-black image paint):
            if self.border is not None:
                self.border.paint(canvas, self.frame_for("border"))
```

```python
# Line 581 (scroll_over mode — border between image and text):
            if self.border is not None:
                self.border.paint(canvas, self.frame_for("border"))
```

```python
# Line 586 (non-scroll mode — border between image and text):
            if self.border is not None:
                self.border.paint(canvas, self.frame_for("border"))
```

```python
# Line 621 (two-row mode — border on real_canvas, after image paint):
        if self.border is not None:
            self.border.paint(real_canvas, self.frame_for("border"))
```

- [ ] **Step 6: Run image widget tests**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_widgets/test_image_base.py tests/test_widgets/test_gif.py tests/test_widgets/test_still.py -v 2>&1 | tail -20`

Expected: all PASS. Same back-compat reasoning.

- [ ] **Step 7: Run full suite**

Run: `PYTHONPATH=tests/stubs uv run pytest -x -q`

Expected: all green.

- [ ] **Step 8: Commit**

```bash
git add src/led_ticker/widgets/_image_base.py
git commit -m "per-effect-counters: migrate widgets/_image_base.py call sites to frame_for()"
```

---

### Task 5: Delete `_should_reset_frame()` gate + replace test class

**Files:**
- Modify: `src/led_ticker/ticker.py` (delete `_should_reset_frame()` function lines 709-739; revert `_show_one` line 766)
- Modify: `tests/test_ticker_display.py` (delete `TestShouldResetFrame` and `TestShouldResetFrameComposition`; add `TestTypewriterPlusRainbowBorderComposition`)

This is the task that activates the new behavior. After this commit, `loop_count > 1` widgets with continuous-phase effects keep their phase AND restart-on-visit effects retype simultaneously.

- [ ] **Step 1: Delete `_should_reset_frame()` from `ticker.py`**

In `src/led_ticker/ticker.py`, delete lines 709-739 (the entire `_should_reset_frame()` function and its docstring). After this, `_show_one` no longer references the helper.

- [ ] **Step 2: Revert `_show_one`'s reset gate**

In `src/led_ticker/ticker.py`, line 766 currently reads:

```python
    if hasattr(widget, "reset_frame") and _should_reset_frame(widget):
        widget.reset_frame()
```

Replace with:

```python
    if hasattr(widget, "reset_frame"):
        widget.reset_frame()
```

Also update the `_show_one` docstring (lines ~750-765) to remove the gate reference. The gate's job is now done by `reset_frame()` itself (it selectively zeros per-effect counters). Suggested replacement docstring:

```python
async def _show_one(
    canvas: Canvas,
    frame: Any,
    widget: Any,
    hold_time: float,
    skip_initial_draw: bool = False,
    continuous: bool = False,
) -> tuple[Canvas, int]:
    """Display one widget for its full visit.

    Dispatches: widgets exposing `play()` run their own animation loop;
    everything else uses the standard hold-and-scroll path. Returns
    `(canvas, last_scroll_pos)` — `last_scroll_pos` is 0 for play()
    widgets since they don't have a scroll position.

    Resets the widget's frame counters at the start of each visit
    (via `reset_frame()` if the widget exposes it). The reset is
    selective per-effect: continuous-phase effects (those with
    `restart_on_visit = False` like `RainbowChaseBorder`) keep their
    counter so the chase phase advances smoothly across `loop_count`
    boundaries; restart-on-visit effects (`Typewriter`, default
    behavior) zero theirs so they restart cleanly. The widget's
    `_frame_count` (engine tick counter) always resets — see
    `_FrameAware.reset_frame` for details.
    """
```

- [ ] **Step 3: Delete the obsolete test classes from `tests/test_ticker_display.py`**

Find `class TestShouldResetFrame:` (around line 1251) and `class TestShouldResetFrameComposition:` (around line 1321). Delete both classes entirely — they tested the gate function which no longer exists.

Run: `grep -n "class TestShouldResetFrame\|class TestShouldResetFrameComposition" tests/test_ticker_display.py`

After deletion, this should return no matches.

- [ ] **Step 4: Add the new composition test class**

Append to `tests/test_ticker_display.py` (at the end of the file):

```python
class TestTypewriterPlusRainbowBorderComposition:
    """Per-effect counters let a widget with both Typewriter
    (restart=True) and RainbowChaseBorder (restart=False) get the
    correct behavior on `loop_count > 1`: typewriter retypes each
    loop AND the border chase phase advances continuously.

    This is the win the per-effect counter refactor was designed
    to deliver. Replaces `TestShouldResetFrameComposition` from
    PR #11, which asserted the OPPOSITE (continuous wins, typewriter
    doesn't retype) — that was the documented tradeoff under the
    old shared-counter model."""

    async def test_typewriter_counter_resets_per_loop(
        self, swapping_frame, no_sleep
    ):
        """The animation's per-effect counter zeros on every visit
        regardless of what other effects are present."""
        from rgbmatrix import _StubCanvas

        class _Typewriter:
            restart_on_visit = True

        class _RainbowBorder:
            restart_on_visit = False

        class _SpyWidget:
            def __init__(self):
                self._frame_count = 0
                self._frame_paused = False
                self._effect_frames = {}
                self.animation = _Typewriter()
                self.border = _RainbowBorder()

            def draw(self, canvas, cursor_pos=0, **kwargs):
                return canvas, 5

            def advance_frame(self):
                if self._frame_paused:
                    return
                self._frame_count += 1
                self._effect_frames["animation"] = (
                    self._effect_frames.get("animation", 0) + 1
                )
                self._effect_frames["border"] = (
                    self._effect_frames.get("border", 0) + 1
                )

            def reset_frame(self):
                self._frame_count = 0
                # Typewriter: restart_on_visit=True → zero
                self._effect_frames["animation"] = 0
                # Rainbow border: restart_on_visit=False → unchanged
                # (intentionally not in this dispatch)

            @property
            def bg_color(self):
                return None

        widget = _SpyWidget()
        canvas = _StubCanvas(width=160, height=16)
        swapping_frame.matrix.SwapOnVSync.return_value = _StubCanvas(
            width=160, height=16
        )

        # Run two visits in a row (simulates loop_count > 1)
        await _show_one(canvas, swapping_frame, widget, hold_time=0.1)
        animation_frame_after_iter1 = widget._effect_frames["animation"]
        border_frame_after_iter1 = widget._effect_frames["border"]
        assert animation_frame_after_iter1 > 0
        assert border_frame_after_iter1 > 0

        await _show_one(canvas, swapping_frame, widget, hold_time=0.1)
        # Typewriter counter zeroed at the start of iter 2, then
        # advanced through iter 2 — should be smaller than the
        # accumulated value from iter 1
        assert widget._effect_frames["animation"] < (
            animation_frame_after_iter1 + border_frame_after_iter1
        )
        # Border counter kept climbing — should be GREATER than iter 1's value
        assert widget._effect_frames["border"] > border_frame_after_iter1

    async def test_widget_frame_count_still_resets(
        self, swapping_frame, no_sleep
    ):
        """Back-compat: `widget._frame_count` retains today's
        per-visit reset semantic regardless of effect composition.
        Tests that read `_frame_count` directly keep working."""
        from rgbmatrix import _StubCanvas

        class _RainbowBorder:
            restart_on_visit = False

        class _SpyWidget:
            def __init__(self):
                self._frame_count = 99  # mid-something
                self._frame_paused = False
                self._effect_frames = {}
                self.border = _RainbowBorder()

            def draw(self, canvas, cursor_pos=0, **kwargs):
                return canvas, 5

            def advance_frame(self):
                if self._frame_paused:
                    return
                self._frame_count += 1
                self._effect_frames["border"] = (
                    self._effect_frames.get("border", 0) + 1
                )

            def reset_frame(self):
                self._frame_count = 0  # primary always resets

            @property
            def bg_color(self):
                return None

        widget = _SpyWidget()
        canvas = _StubCanvas(width=160, height=16)
        swapping_frame.matrix.SwapOnVSync.return_value = _StubCanvas(
            width=160, height=16
        )

        await _show_one(canvas, swapping_frame, widget, hold_time=0.1)
        # Iter 2 should see _frame_count reset to 0 at entry, then
        # climbing through the iter — small value, NOT 99 + N
        assert widget._frame_count < 99

    async def test_continuous_border_phase_uninterrupted(
        self, swapping_frame, no_sleep
    ):
        """Rainbow border's per-effect counter is monotonically
        increasing across visits. The chase phase never snaps back."""
        from rgbmatrix import _StubCanvas

        class _RainbowBorder:
            restart_on_visit = False

        class _SpyWidget:
            def __init__(self):
                self._frame_count = 0
                self._frame_paused = False
                self._effect_frames = {}
                self.border = _RainbowBorder()

            def draw(self, canvas, cursor_pos=0, **kwargs):
                return canvas, 5

            def advance_frame(self):
                if self._frame_paused:
                    return
                self._frame_count += 1
                self._effect_frames["border"] = (
                    self._effect_frames.get("border", 0) + 1
                )

            def reset_frame(self):
                self._frame_count = 0
                # Border opted out → don't touch its counter

            @property
            def bg_color(self):
                return None

        widget = _SpyWidget()
        canvas = _StubCanvas(width=160, height=16)
        swapping_frame.matrix.SwapOnVSync.return_value = _StubCanvas(
            width=160, height=16
        )

        await _show_one(canvas, swapping_frame, widget, hold_time=0.1)
        border_after_iter1 = widget._effect_frames["border"]

        await _show_one(canvas, swapping_frame, widget, hold_time=0.1)
        border_after_iter2 = widget._effect_frames["border"]

        # Strictly increasing: iter 2 added more ticks on top of iter 1
        assert border_after_iter2 > border_after_iter1
```

- [ ] **Step 5: Run the new composition tests**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_ticker_display.py::TestTypewriterPlusRainbowBorderComposition -v`

Expected: PASS (3 tests).

- [ ] **Step 6: Run full suite**

Run: `PYTHONPATH=tests/stubs uv run pytest -x -q`

Expected: all green. The deleted classes (`TestShouldResetFrame`, `TestShouldResetFrameComposition`) no longer exist in the suite — pytest reports the new totals. The `_should_reset_frame` import inside any test that may reference it must also be cleaned up. If you see `ImportError: cannot import name '_should_reset_frame'`, check `grep -rn "_should_reset_frame" tests/` and remove any stale imports.

- [ ] **Step 7: Run lint**

Run: `uv run ruff check src/led_ticker tests`

Expected: All checks passed!

- [ ] **Step 8: Commit**

```bash
git add src/led_ticker/ticker.py tests/test_ticker_display.py
git commit -m "per-effect-counters: delete _should_reset_frame gate; reset_frame is now per-effect"
```

---

### Task 6: Smoke config §17 + CLAUDE.md doc update

**Files:**
- Modify: `config/config.rainbow_border_test.example.toml` (§17 comment header rewrite)
- Modify: `CLAUDE.md` (Rainbow border section — replace the composition-rule paragraph)

Pure documentation. The smoke section's TOML widget block stays unchanged (typewriter + rainbow border on `loop_count = 3`); only the comment header is rewritten to describe what's now expected on hardware.

- [ ] **Step 1: Rewrite §17 comment header**

In `config/config.rainbow_border_test.example.toml`, find the §17 comment block and replace it with:

```
# ---------------------------------------------------------------------------
# 17. Typewriter + RainbowChaseBorder — both effects compose
#     simultaneously after the per-effect counter refactor.
#     Watch for: 3 distinct typing animations (typewriter retypes
#     each loop) AND a continuously-advancing rainbow chase around
#     the perimeter (no phase snap-back).
#
#     This was a documented tradeoff in PR #11 ("composition rule:
#     ANY opt-out wins") that became a positive test after the per-
#     effect counter refactor landed. The widget's primary
#     `_frame_count` resets per visit (typewriter restarts), while
#     `_effect_frames["border"]` keeps climbing (chase phase
#     preserved). Both work as designed because each effect has
#     its own counter following its own restart_on_visit policy.
# ---------------------------------------------------------------------------
```

The widget block (TickerMessage with text, font, animation, border) stays unchanged.

- [ ] **Step 2: Update CLAUDE.md Rainbow border section**

In `CLAUDE.md`, find the paragraph that currently reads:

```
Continuous-phase effects (`Rainbow`, `ColorCycle`,
`RainbowChaseBorder`) opt out of visit-reset by setting
`restart_on_visit = False` as a class attribute —
`_show_one._should_reset_frame` checks the widget's effects and
skips the reset if any is opted out. Their phase advances
continuously across `loop_count > 1` iterations within a section.
Section transitions still reset (via `run_transition`'s
`_reset_presenter`), so entry-to-section is always fresh state.
Composition rule: a widget with both a continuous effect and a
restart-on-visit effect (e.g. typewriter + rainbow border) gets
the continuous semantics — typewriter won't retype on inner loop
iterations. Niche combo; if you need typewriter to retype on a
bordered widget, drop the border or use a different framing.
```

Replace with:

```
Per-effect counters: each effect on a widget tracks its own visit-
reset state via `_FrameAware._effect_frames`. Continuous-phase
effects (`Rainbow`, `ColorCycle`, `RainbowChaseBorder`) set
`restart_on_visit = False` as a class attribute — their counter
doesn't reset on `_show_one`'s visit-entry call, so the chase /
sweep phase advances continuously across `loop_count > 1`
iterations. Restart-on-visit effects (`Typewriter`, default for
unknown classes) reset normally and behave as fresh on each
visit. Section transitions still reset via `run_transition`'s
`_reset_presenter` — entry-to-section is always fresh state.

Both behaviors compose simultaneously: a `TickerMessage` with both
`Typewriter` and `RainbowChaseBorder` retypes on each loop AND the
border chase keeps its phase. No tradeoff. Widget code reads
`self.frame_for(attr_name)` instead of `self._frame_count` when
calling effect APIs — the helper returns the per-effect counter
that follows the effect's `restart_on_visit` policy. The widget's
`_frame_count` is preserved as the engine tick counter (resets per
visit) for back-compat with any direct readers (tests, etc.).
Smoke §17 of the rainbow border test demonstrates both behaviors
on hardware.
```

- [ ] **Step 3: Verify the docs read correctly**

Run: `grep -n "per-effect counters\|frame_for(attr" CLAUDE.md`

Expected: at least 2 matches (the new paragraph references both phrases).

Run: `grep -n "loop_count = 3" config/config.rainbow_border_test.example.toml`

Expected: 3 matches (§4, §5, §7) plus §17 — 4 total.

- [ ] **Step 4: Commit**

```bash
git add config/config.rainbow_border_test.example.toml CLAUDE.md
git commit -m "per-effect-counters: docs — both behaviors compose simultaneously"
```

---

### Final task: lint + push + open PR

- [ ] **Step 1: Run lint**

```bash
uv run ruff check src/led_ticker tests
```

Expected: All checks passed!

- [ ] **Step 2: Run full test suite**

```bash
PYTHONPATH=tests/stubs uv run pytest -x -q
```

Expected: all tests pass (current count + 8 new tests added by this plan: 5 in `TestEffectFrames`, 3 in `TestTypewriterPlusRainbowBorderComposition`; minus 6 deleted tests from `TestShouldResetFrame` (5) + `TestShouldResetFrameComposition` (1)). Net +2 tests.

- [ ] **Step 3: Push the branch**

```bash
git push -u origin feat/per-effect-counters
```

- [ ] **Step 4: Open the PR**

```bash
gh pr create --title "per-effect frame counters: eliminate the composition tradeoff" \
  --body "$(cat <<'EOF'
## Summary

Eliminates the composition tradeoff documented in PR #11
(visit-reset). A widget with both `Typewriter` (wants restart-on-
visit) and a continuous-phase effect (`Rainbow` / `ColorCycle` /
`RainbowChaseBorder`) now gets BOTH behaviors as designed — typewriter
retypes on each loop AND the chase phase advances continuously
across `loop_count > 1` iterations.

## Architecture

`_FrameAware` mixin gains `_effect_frames: dict[str, int]` and a
`frame_for(attr_name)` helper. Each effect's counter follows its own
`restart_on_visit` policy. Widget code reads
`self.frame_for(attr_name)` instead of `self._frame_count`. The
widget's `_frame_count` is preserved (resets per visit, back-compat
for direct readers).

`_show_one`'s `_should_reset_frame()` gate is deleted; the widget's
`reset_frame()` itself does the per-effect work.

## Behavior change visible to users

- §17 of the rainbow border smoke (TickerMessage with typewriter +
  rainbow border on `loop_count = 3`) now retypes 3 times AND keeps
  the chase phase continuous. Comment header updated.
- The "ANY opt-out wins" composition rule disappears from CLAUDE.md.

## What stays the same

- `Rainbow.restart_on_visit = False`, `ColorCycle.restart_on_visit
  = False`, `RainbowChaseBorder.restart_on_visit = False` — class
  attributes preserved. Only the consumer location moves from
  `_show_one._should_reset_frame()` to `_FrameAware.reset_frame()`.
- `widget._frame_count` retains its current semantic (engine tick
  counter, resets per visit). Tests reading it directly continue
  working.
- Effects stay stateless (pure functions of frame value). The OOP
  alternative (stateful effects with their own counters) was
  considered and rejected — see spec for rationale.

## Test coverage

- Added: `TestEffectFrames` (5 tests in `tests/test_frame_aware.py`)
  on the new mixin behavior.
- Added: `TestTypewriterPlusRainbowBorderComposition` (3 tests in
  `tests/test_ticker_display.py`) — proves the composition works.
- Removed: `TestShouldResetFrame` (5 tests) and
  `TestShouldResetFrameComposition` (1 test) — gate function deleted,
  replaced by the integration test above which asserts the OPPOSITE
  outcome.
- Net: +2 tests.

## Spec

[`docs/superpowers/specs/2026-05-07-per-effect-counters-design.md`](https://github.com/JamesAwesome/led-ticker/blob/feat/per-effect-counters/docs/superpowers/specs/2026-05-07-per-effect-counters-design.md)

## Test plan

- [x] All tests pass (lint clean, pyright clean, pre-commit hooks)
- [ ] **Hardware verify on bigsign**: §17 of the rainbow border smoke
      now shows typewriter retyping 3 times AND the chase advancing
      continuously across all 3 inner loops. §4-§7 unchanged
      (continuous-phase effects keep working).

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Expected: PR URL returned.

---

## Summary of files touched

| Path | Change |
|---|---|
| `src/led_ticker/widgets/_frame_aware.py` | Mixin gains `_EFFECT_ATTRS` constant, `_effect_frames` dict, `_iter_effects()`, `frame_for()`; `advance_frame` / `reset_frame` updated |
| `src/led_ticker/widgets/message.py` | 8 call sites `self._frame_count` → `self.frame_for(attr)` |
| `src/led_ticker/widgets/two_row.py` | 3 call sites |
| `src/led_ticker/widgets/_image_base.py` | 10 call sites |
| `src/led_ticker/ticker.py` | Delete `_should_reset_frame()` (~30 lines); revert `_show_one` gate to unconditional |
| `tests/test_frame_aware.py` | + `TestEffectFrames` (5 tests) |
| `tests/test_ticker_display.py` | Delete `TestShouldResetFrame` + `TestShouldResetFrameComposition`; + `TestTypewriterPlusRainbowBorderComposition` (3 tests) |
| `config/config.rainbow_border_test.example.toml` | §17 comment header rewrite |
| `CLAUDE.md` | Rainbow border section — composition-rule paragraph replaced |

Total: 9 files, 8 new tests, 6 tests deleted, single-PR scope.
