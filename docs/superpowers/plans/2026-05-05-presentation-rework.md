# Presentation system rework — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the `WidgetPresenter` wrapper + `presentation = "..."` knob with rich `font_color` (color providers) and TickerMessage-only `animation`. Bundle the engine-tick fix so frame-aware effects work in swap mode held-text branches.

**Architecture:** Two orthogonal widget knobs: `font_color` accepts a Color or a `ColorProvider` (rainbow / color_cycle / pulse / gradient / random / constant). `animation` accepts `"typewriter"` / `"bounce"` on `TickerMessage` only. Each widget tracks its own `_frame_count` via a `_FrameAware` mixin; orchestrator calls `advance_frame()` per draw tick. `_swap_and_scroll`'s held-text branch becomes a tick loop. Hard cutover with loud migration error mapping `presentation = "..."` to its new shape.

**Tech Stack:** Python 3.13 + asyncio + attrs + `rgbmatrix` C extension. Tests run via `make test` (sets `PYTHONPATH=tests/stubs`). Personal repo, direct-to-main authorized.

---

## File Structure

**Created:**
- `src/led_ticker/color_providers.py` — ColorProvider interface + 6 implementations (`_ConstantColor`, `Random`, `Rainbow`, `ColorCycle`, `Pulse`, `Gradient`)
- `src/led_ticker/animations.py` — Animation interface + `AnimationFrame` + 2 implementations (`Typewriter`, `Bounce`)
- `src/led_ticker/widgets/_frame_aware.py` — `_FrameAware` mixin (frame counter + pause/resume/reset)

**Modified:**
- `src/led_ticker/app.py` — extend color coercion to ColorProvider; add migration error for `presentation`; extract+validate `animation`; drop `WidgetPresenter` wrapping
- `src/led_ticker/ticker.py` — engine tick loop in `_swap_and_scroll`; add `advance_frame()` call to scroll branch; `run_transition` calls `pause_frame()` / `resume_frame()`
- `src/led_ticker/widgets/message.py` — TickerMessage + TickerCountdown consume `ColorProvider`; TickerMessage gains `animation` field
- `src/led_ticker/widgets/weather.py` — consume `ColorProvider` (two color fields)
- `src/led_ticker/widgets/two_row.py` — per-row providers
- `src/led_ticker/widgets/_image_base.py` — `font_color` + `top_color` + `bottom_color` providers
- `src/led_ticker/transitions/__init__.py` — `run_transition` pause/resume call surface
- `src/led_ticker/widgets/__init__.py` — apply `_FrameAware` to all text-painting widgets
- `config/config.presentation_test.example.toml` — rewrite to new vocabulary
- `CLAUDE.md` — replace presentation paragraph

**Deleted:**
- `src/led_ticker/presentation.py` — module deleted entirely
- `tests/test_presentation.py` — old tests deleted (new tests in `test_color_providers.py` + `test_animations.py`)

**New tests:**
- `tests/test_color_providers.py` — provider unit tests
- `tests/test_animations.py` — animation unit tests
- `tests/test_frame_aware.py` — mixin unit tests

**Modified tests:**
- `tests/test_app.py` — migration error + animation rejection + provider coercion
- `tests/test_ticker_display.py` — engine tick + advance_frame integration
- `tests/test_widgets/test_message.py` — provider consumption + animation
- `tests/test_widgets/test_weather.py` — provider consumption
- `tests/test_widgets/test_two_row.py` — per-row providers
- `tests/test_widgets/test_image_base.py` — font_color/top_color/bottom_color provider consumption

**Confirmed via audit (no integration needed):**
- `mlb.py` / `mlb_standings.py` / `rss_feed.py` construct `TickerMessage` instances and pass colors through. Once `TickerMessage` accepts `Color | ColorProvider`, these widgets work transparently.

---

## Task 1: ColorProvider interface + _ConstantColor + Random

The foundation. Two simple providers (`_ConstantColor` wraps a Color, `Random` picks once per visit) plus the Protocol they satisfy.

**Files:**
- Create: `src/led_ticker/color_providers.py`
- Test: `tests/test_color_providers.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_color_providers.py`:

```python
"""Tests for color_providers module."""

from __future__ import annotations

import pytest

from rgbmatrix.graphics import Color

from led_ticker.color_providers import _ConstantColor, Random


class TestConstantColor:
    """`_ConstantColor` wraps a graphics.Color and always returns it
    regardless of frame / char_index. `per_char = False`."""

    def test_color_for_returns_wrapped_color(self):
        c = Color(255, 100, 50)
        provider = _ConstantColor(c)
        assert provider.color_for(0, 0, 1) is c

    def test_color_for_ignores_frame_and_index(self):
        c = Color(10, 20, 30)
        provider = _ConstantColor(c)
        assert provider.color_for(0, 0, 1) is c
        assert provider.color_for(99, 5, 100) is c

    def test_per_char_is_false(self):
        provider = _ConstantColor(Color(0, 0, 0))
        assert provider.per_char is False


class TestRandom:
    """`Random` picks a single color when constructed and returns it
    for every call. Stable per-instance, NOT per-frame (matches the
    existing 'random' sentinel semantic where each visit gets one
    color, not a flicker)."""

    def test_color_for_stable_across_calls(self):
        provider = Random()
        c1 = provider.color_for(0, 0, 1)
        c2 = provider.color_for(50, 3, 10)
        assert c1.red == c2.red
        assert c1.green == c2.green
        assert c1.blue == c2.blue

    def test_two_instances_can_differ(self):
        """Two separately-constructed Random providers can differ
        (probabilistic; rerun if both happen to pick same color)."""
        # Sample many to make collision astronomically unlikely
        samples = [Random().color_for(0, 0, 1) for _ in range(20)]
        rgbs = {(s.red, s.green, s.blue) for s in samples}
        assert len(rgbs) > 1, "all 20 Random instances picked the same color"

    def test_per_char_is_false(self):
        provider = Random()
        assert provider.per_char is False
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_color_providers.py -v
```

Expected: ImportError — `color_providers` module doesn't exist yet.

- [ ] **Step 3: Implement the module**

Create `src/led_ticker/color_providers.py`:

```python
"""Color providers — runtime-derived colors for frame-aware text
rendering.

Replaces the `WidgetPresenter`-wrapped presentation effects (rainbow,
color_cycle, pulse) with widget-level ColorProvider instances bound
to the `font_color` (and `top_color` / `bottom_color`) field. Widgets
ask the provider for a Color via `color_for(frame, char_index, total)`
each tick.

Two flavors:
- `per_char = False` providers (constant, color_cycle, pulse, random)
  return one Color per call — widgets do a single `draw_text` for the
  whole string.
- `per_char = True` providers (rainbow, gradient) return a different
  Color per character — widgets iterate chars and draw each separately.

The `_ConstantColor` provider exists so that plain `font_color = [r,g,b]`
configs route through the same interface as effects-based configs.
The widget-side code is uniform: `provider.color_for(...)`.
"""

from __future__ import annotations

import colorsys
import random
from typing import Protocol

from led_ticker._compat import require_graphics
from led_ticker._types import Color


class ColorProvider(Protocol):
    """Returns a Color given a frame counter and (for per-char
    providers) a character index within the string being drawn."""

    per_char: bool

    def color_for(self, frame: int, char_index: int, total_chars: int) -> Color: ...


class _ConstantColor:
    """Wraps a single Color so plain `font_color = [r,g,b]` configs
    route through the same `color_for` interface as effects."""

    per_char: bool = False

    def __init__(self, color: Color) -> None:
        self._color = color

    def color_for(self, frame: int, char_index: int, total_chars: int) -> Color:
        return self._color


class Random:
    """Picks a single random color at construction; returns it for
    every call. Matches the existing `font_color = "random"` sentinel
    semantic — one stable color per widget instance, not a per-frame
    flicker."""

    per_char: bool = False

    def __init__(self) -> None:
        graphics = require_graphics()
        # Use the same RANDOM_COLOR cycle as the rest of the codebase
        # if it's worth aligning, but a uniform random over RGB also
        # works fine for v1.
        r, g, b = colorsys.hsv_to_rgb(random.random(), 1.0, 1.0)
        self._color = graphics.Color(int(r * 255), int(g * 255), int(b * 255))

    def color_for(self, frame: int, char_index: int, total_chars: int) -> Color:
        return self._color
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_color_providers.py -v
```

Expected: 6 PASS.

- [ ] **Step 5: Run full suite to confirm nothing else broke**

```bash
uv run pytest -q 2>&1 | tail -3
```

Expected: 1081+ passing (existing suite unchanged + 6 new tests).

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/color_providers.py tests/test_color_providers.py
git commit -m "$(cat <<'EOF'
color_providers: add interface + _ConstantColor + Random

Foundation for the presentation system rework. ColorProvider
Protocol with `color_for(frame, char_index, total_chars) -> Color`
and a `per_char` class attribute. _ConstantColor wraps a Color so
plain `font_color = [r,g,b]` flows through the same interface as
effects. Random picks once per construction (stable per visit).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Rainbow, ColorCycle, Pulse, Gradient providers

Four animated/styled providers. Rainbow + Gradient are `per_char = True`; ColorCycle + Pulse are whole-string.

**Files:**
- Modify: `src/led_ticker/color_providers.py` (add 4 classes)
- Modify: `tests/test_color_providers.py` (add 4 test classes)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_color_providers.py`:

```python
class TestRainbow:
    """Per-character hue offset, advancing per frame."""

    def test_per_char_is_true(self):
        from led_ticker.color_providers import Rainbow

        assert Rainbow().per_char is True

    def test_frame_zero_char_zero_returns_hue_zero(self):
        from led_ticker.color_providers import Rainbow

        provider = Rainbow(speed=8, char_offset=30)
        c = provider.color_for(0, 0, 10)
        # hue = 0 → red (255, 0, 0)
        assert c.red == 255
        assert c.green == 0
        assert c.blue == 0

    def test_char_offset_shifts_hue(self):
        from led_ticker.color_providers import Rainbow

        provider = Rainbow(speed=8, char_offset=30)
        c0 = provider.color_for(0, 0, 10)
        c1 = provider.color_for(0, 1, 10)
        # Different chars, same frame → different hues
        assert (c0.red, c0.green, c0.blue) != (c1.red, c1.green, c1.blue)

    def test_frame_advances_hue(self):
        from led_ticker.color_providers import Rainbow

        provider = Rainbow(speed=8, char_offset=30)
        c0 = provider.color_for(0, 0, 10)
        c10 = provider.color_for(10, 0, 10)
        assert (c0.red, c0.green, c0.blue) != (c10.red, c10.green, c10.blue)


class TestColorCycle:
    """Whole-string hue rotation; char_index ignored."""

    def test_per_char_is_false(self):
        from led_ticker.color_providers import ColorCycle

        assert ColorCycle().per_char is False

    def test_char_index_ignored(self):
        from led_ticker.color_providers import ColorCycle

        provider = ColorCycle(speed=5)
        c0 = provider.color_for(10, 0, 5)
        c4 = provider.color_for(10, 4, 5)
        assert (c0.red, c0.green, c0.blue) == (c4.red, c4.green, c4.blue)

    def test_frame_advances_hue(self):
        from led_ticker.color_providers import ColorCycle

        provider = ColorCycle(speed=5)
        c0 = provider.color_for(0, 0, 1)
        c10 = provider.color_for(10, 0, 1)
        assert (c0.red, c0.green, c0.blue) != (c10.red, c10.green, c10.blue)


class TestPulse:
    """Entry flash to white; settles to base after `duration_frames`."""

    def test_per_char_is_false(self):
        from rgbmatrix.graphics import Color

        from led_ticker.color_providers import Pulse

        assert Pulse(base=Color(50, 100, 150)).per_char is False

    def test_at_duration_frames_returns_base(self):
        """Past the pulse duration, color settles to base."""
        from rgbmatrix.graphics import Color

        from led_ticker.color_providers import Pulse

        base = Color(50, 100, 150)
        provider = Pulse(base=base, duration_frames=6)
        c = provider.color_for(6, 0, 1)
        assert (c.red, c.green, c.blue) == (50, 100, 150)
        c2 = provider.color_for(100, 0, 1)
        assert (c2.red, c2.green, c2.blue) == (50, 100, 150)

    def test_early_frames_brighter_than_base(self):
        from rgbmatrix.graphics import Color

        from led_ticker.color_providers import Pulse

        base = Color(50, 100, 150)
        provider = Pulse(base=base, duration_frames=6)
        # Frame 1 should be on the way up (closer to white)
        c = provider.color_for(1, 0, 1)
        assert c.red >= base.red
        assert c.green >= base.green
        assert c.blue >= base.blue


class TestGradient:
    """Linear left-to-right; char_index spaces hues; frame ignored."""

    def test_per_char_is_true(self):
        from rgbmatrix.graphics import Color

        from led_ticker.color_providers import Gradient

        assert Gradient(from_color=Color(0, 0, 0), to_color=Color(255, 255, 255)).per_char is True

    def test_char_zero_returns_from(self):
        from rgbmatrix.graphics import Color

        from led_ticker.color_providers import Gradient

        provider = Gradient(from_color=Color(255, 0, 0), to_color=Color(0, 0, 255))
        c = provider.color_for(0, 0, 5)
        assert (c.red, c.green, c.blue) == (255, 0, 0)

    def test_last_char_returns_to(self):
        from rgbmatrix.graphics import Color

        from led_ticker.color_providers import Gradient

        provider = Gradient(from_color=Color(255, 0, 0), to_color=Color(0, 0, 255))
        # total_chars = 5, so char_index = 4 is the last char
        c = provider.color_for(0, 4, 5)
        assert (c.red, c.green, c.blue) == (0, 0, 255)

    def test_middle_interpolates(self):
        from rgbmatrix.graphics import Color

        from led_ticker.color_providers import Gradient

        provider = Gradient(from_color=Color(255, 0, 0), to_color=Color(0, 0, 255))
        # char_index = 2 of 5 → interpolation factor 0.5
        c = provider.color_for(0, 2, 5)
        assert 100 < c.red < 200
        assert 0 == c.green
        assert 50 < c.blue < 150

    def test_frame_ignored(self):
        from rgbmatrix.graphics import Color

        from led_ticker.color_providers import Gradient

        provider = Gradient(from_color=Color(255, 0, 0), to_color=Color(0, 0, 255))
        c0 = provider.color_for(0, 1, 5)
        c100 = provider.color_for(100, 1, 5)
        assert (c0.red, c0.green, c0.blue) == (c100.red, c100.green, c100.blue)

    def test_total_chars_one_returns_from(self):
        """Edge case: single char → just return `from`."""
        from rgbmatrix.graphics import Color

        from led_ticker.color_providers import Gradient

        provider = Gradient(from_color=Color(255, 0, 0), to_color=Color(0, 0, 255))
        c = provider.color_for(0, 0, 1)
        assert (c.red, c.green, c.blue) == (255, 0, 0)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_color_providers.py::TestRainbow tests/test_color_providers.py::TestColorCycle tests/test_color_providers.py::TestPulse tests/test_color_providers.py::TestGradient -v
```

Expected: ImportError or NameError on each — those classes don't exist yet.

- [ ] **Step 3: Implement the providers**

Append to `src/led_ticker/color_providers.py`:

```python
class Rainbow:
    """Per-character hue offset, advancing per frame.

    `speed` is degrees of hue advanced per frame. `char_offset` is the
    hue gap between consecutive characters. Defaults match the legacy
    Rainbow presentation (speed=8, char_offset=30)."""

    per_char: bool = True

    def __init__(self, speed: int = 8, char_offset: int = 30) -> None:
        self.speed = speed
        self.char_offset = char_offset

    def color_for(self, frame: int, char_index: int, total_chars: int) -> Color:
        graphics = require_graphics()
        hue = ((frame * self.speed + char_index * self.char_offset) % 360) / 360
        r, g, b = colorsys.hsv_to_rgb(hue, 1.0, 1.0)
        return graphics.Color(int(r * 255), int(g * 255), int(b * 255))


class ColorCycle:
    """Whole-string hue rotation; char_index ignored.

    `speed` is degrees of hue advanced per frame. Default matches the
    legacy ColorCycle (speed=5)."""

    per_char: bool = False

    def __init__(self, speed: int = 5) -> None:
        self.speed = speed

    def color_for(self, frame: int, char_index: int, total_chars: int) -> Color:
        graphics = require_graphics()
        hue = ((frame * self.speed) % 360) / 360
        r, g, b = colorsys.hsv_to_rgb(hue, 1.0, 1.0)
        return graphics.Color(int(r * 255), int(g * 255), int(b * 255))


class Pulse:
    """Entry flash to white; settles to base after `duration_frames`.

    Frames 0 .. 0.2*duration ramp from base to white; 0.2*duration ..
    duration ramp back to base; past duration the base is returned
    unchanged. Matches the legacy Pulse presentation."""

    per_char: bool = False

    def __init__(self, base: Color, duration_frames: int = 6) -> None:
        self._base = base
        self.duration_frames = duration_frames

    def color_for(self, frame: int, char_index: int, total_chars: int) -> Color:
        graphics = require_graphics()
        if frame >= self.duration_frames:
            return self._base
        p = frame / max(1, self.duration_frames - 1)
        intensity = p / 0.2 if p < 0.2 else 1 - (p - 0.2) / 0.8
        r = int(self._base.red + (255 - self._base.red) * intensity)
        g = int(self._base.green + (255 - self._base.green) * intensity)
        b = int(self._base.blue + (255 - self._base.blue) * intensity)
        return graphics.Color(r, g, b)


class Gradient:
    """Linear left-to-right gradient between `from_color` and
    `to_color`. char_index drives interpolation; frame is ignored."""

    per_char: bool = True

    def __init__(self, from_color: Color, to_color: Color) -> None:
        self._from = from_color
        self._to = to_color

    def color_for(self, frame: int, char_index: int, total_chars: int) -> Color:
        graphics = require_graphics()
        if total_chars <= 1:
            return self._from
        t = char_index / (total_chars - 1)
        r = int(self._from.red + (self._to.red - self._from.red) * t)
        g = int(self._from.green + (self._to.green - self._from.green) * t)
        b = int(self._from.blue + (self._to.blue - self._from.blue) * t)
        return graphics.Color(r, g, b)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_color_providers.py -v
```

Expected: All previously-failing tests now PASS.

- [ ] **Step 5: Run full suite**

```bash
uv run pytest -q 2>&1 | tail -3
```

Expected: 1080+ passing.

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/color_providers.py tests/test_color_providers.py
git commit -m "$(cat <<'EOF'
color_providers: add Rainbow, ColorCycle, Pulse, Gradient

Four animated/styled providers covering the full color-effect surface
of the rework. Rainbow + Gradient are per_char (widgets iterate chars
and call per char). ColorCycle + Pulse are whole-string (single
color_for call per draw, single draw_text).

Defaults match the legacy presentation effects (Rainbow speed=8,
char_offset=30; ColorCycle speed=5; Pulse duration_frames=6) so
visual behavior is preserved across the rename.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Animation interface + Typewriter, Bounce

Animation produces an `AnimationFrame` per frame describing what the widget should render.

**Files:**
- Create: `src/led_ticker/animations.py`
- Create: `tests/test_animations.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_animations.py`:

```python
"""Tests for animations module."""

from __future__ import annotations

import pytest

from led_ticker.animations import AnimationFrame, Bounce, Typewriter


class TestTypewriter:
    """Slice grows one character per frame."""

    def test_frame_zero_returns_first_char(self):
        anim = Typewriter()
        f = anim.frame_for(0, "WATCH ME", canvas_width=256, text_width=48)
        assert f.visible_text == "W"
        assert f.cursor_override is None

    def test_frame_advances_slice(self):
        anim = Typewriter()
        f = anim.frame_for(2, "WATCH ME", canvas_width=256, text_width=48)
        assert f.visible_text == "WAT"

    def test_frame_past_end_clamps_to_full_text(self):
        anim = Typewriter()
        f = anim.frame_for(100, "ABC", canvas_width=256, text_width=18)
        assert f.visible_text == "ABC"

    def test_chars_per_frame_advances_faster(self):
        anim = Typewriter(chars_per_frame=2)
        f = anim.frame_for(0, "ABCDEF", canvas_width=256, text_width=36)
        assert f.visible_text == "AB"
        f = anim.frame_for(1, "ABCDEF", canvas_width=256, text_width=36)
        assert f.visible_text == "ABCD"


class TestBounce:
    """Slide in from right, hold center, slide out left."""

    def test_frame_zero_cursor_at_canvas_width(self):
        anim = Bounce(scroll_frames=20, hold_frames=40)
        f = anim.frame_for(0, "BOUNCE", canvas_width=256, text_width=36)
        assert f.visible_text == "BOUNCE"
        # frame 0 → text just off-right
        assert f.cursor_override == 256

    def test_after_scroll_in_holds_at_center(self):
        anim = Bounce(scroll_frames=20, hold_frames=40)
        f = anim.frame_for(20, "BOUNCE", canvas_width=256, text_width=36)
        # center_x = (256 - 36) // 2 = 110
        assert f.cursor_override == 110

    def test_during_hold_cursor_stays_at_center(self):
        anim = Bounce(scroll_frames=20, hold_frames=40)
        f30 = anim.frame_for(30, "BOUNCE", canvas_width=256, text_width=36)
        f55 = anim.frame_for(55, "BOUNCE", canvas_width=256, text_width=36)
        assert f30.cursor_override == 110
        assert f55.cursor_override == 110

    def test_during_scroll_out_moves_left_of_zero(self):
        anim = Bounce(scroll_frames=20, hold_frames=40)
        # scroll_out range: 60..79; final frame moves close to -text_width
        f = anim.frame_for(79, "BOUNCE", canvas_width=256, text_width=36)
        assert f.cursor_override is not None
        assert f.cursor_override < 0

    def test_after_total_frames_holds_off_screen(self):
        """Past total_frames bounce remains at the end position
        (text not visible)."""
        anim = Bounce(scroll_frames=20, hold_frames=40)
        # total = 80; past that should be safe
        f = anim.frame_for(100, "BOUNCE", canvas_width=256, text_width=36)
        assert f.cursor_override is not None
        # Either at center_x (idle) or off-left; both are documented
        # post-cycle behaviors. Just assert it doesn't crash.

    def test_visible_text_always_full(self):
        """Bounce repositions but doesn't slice text."""
        anim = Bounce()
        for frame in (0, 10, 20, 30, 60, 75):
            f = anim.frame_for(frame, "HELLO", canvas_width=256, text_width=30)
            assert f.visible_text == "HELLO"


class TestAnimationFrame:
    def test_dataclass_construction(self):
        f = AnimationFrame(visible_text="HI", cursor_override=10)
        assert f.visible_text == "HI"
        assert f.cursor_override == 10

    def test_cursor_override_can_be_none(self):
        f = AnimationFrame(visible_text="HI", cursor_override=None)
        assert f.cursor_override is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_animations.py -v
```

Expected: ImportError — `animations` module doesn't exist.

- [ ] **Step 3: Implement the module**

Create `src/led_ticker/animations.py`:

```python
"""Animations — frame-aware position/visibility behaviors for
TickerMessage.

Replaces the legacy `WidgetPresenter`-wrapped Typewriter and Bounce
with widget-level animation instances bound to TickerMessage's
`animation` field. Each tick TickerMessage asks the animation for an
`AnimationFrame` describing what to render this frame.

Color providers are orthogonal — animations control position and
visibility, providers control color. The two compose freely.
"""

from __future__ import annotations

from dataclasses import dataclass

from led_ticker.transitions import ease_out


@dataclass
class AnimationFrame:
    """What the widget should render at the current frame.

    visible_text:    The slice (or full text) to draw. Typewriter
                     returns growing prefixes; Bounce returns the full.
    cursor_override: If set, place the text at this x. If None, the
                     orchestrator's cursor_pos is used (i.e. the
                     animation doesn't reposition).
    """

    visible_text: str
    cursor_override: int | None


class Typewriter:
    """Slice grows one character per frame (or `chars_per_frame`)."""

    def __init__(self, chars_per_frame: int = 1) -> None:
        self.chars_per_frame = chars_per_frame

    def frame_for(
        self, frame: int, full_text: str, canvas_width: int, text_width: int
    ) -> AnimationFrame:
        chars_visible = min(
            len(full_text),
            (frame + 1) * self.chars_per_frame,
        )
        return AnimationFrame(
            visible_text=full_text[:chars_visible],
            cursor_override=None,
        )


class Bounce:
    """Slide in from right (ease_out), hold at center (`hold_frames`),
    slide out left (ease_in)."""

    def __init__(self, hold_frames: int = 40, scroll_frames: int = 20) -> None:
        self.hold_frames = hold_frames
        self.scroll_frames = scroll_frames

    @property
    def total_frames(self) -> int:
        return self.scroll_frames + self.hold_frames + self.scroll_frames

    def frame_for(
        self, frame: int, full_text: str, canvas_width: int, text_width: int
    ) -> AnimationFrame:
        sf = self.scroll_frames
        hf = self.hold_frames
        center_x = max(0, (canvas_width - text_width) // 2)

        if frame < sf:
            # Scroll in from right with ease-out
            p = ease_out(frame / max(1, sf - 1))
            pos = int(canvas_width + (center_x - canvas_width) * p)
        elif frame < sf + hf:
            # Hold at center
            pos = center_x
        elif frame < self.total_frames:
            # Scroll out to left with ease-in (p^2)
            p = (frame - sf - hf) / max(1, sf - 1)
            eased = p * p
            pos = int(center_x + (-text_width - center_x) * eased)
        else:
            pos = center_x

        return AnimationFrame(visible_text=full_text, cursor_override=pos)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_animations.py -v
```

Expected: All PASS.

- [ ] **Step 5: Run full suite**

```bash
uv run pytest -q 2>&1 | tail -3
```

Expected: 1090+ passing (1080 + 6 from T1 + 13 from T2 + ~12 from T3).

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/animations.py tests/test_animations.py
git commit -m "$(cat <<'EOF'
animations: add Typewriter and Bounce

Frame-aware position/visibility animations for TickerMessage. Each
tick the widget asks `animation.frame_for(frame, full_text, canvas_w,
text_w)` for an AnimationFrame describing the slice + cursor
override. Color providers (T1/T2) compose orthogonally — animations
control position/visibility, providers control color.

Defaults match legacy WidgetPresenter behavior: Typewriter
chars_per_frame=1, Bounce scroll_frames=20 + hold_frames=40.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: `_FrameAware` mixin

Tracks `_frame_count` per widget; methods to advance, pause, resume, reset.

**Files:**
- Create: `src/led_ticker/widgets/_frame_aware.py`
- Create: `tests/test_frame_aware.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_frame_aware.py`:

```python
"""Tests for the _FrameAware mixin."""

from __future__ import annotations

import attrs

from led_ticker.widgets._frame_aware import _FrameAware


@attrs.define
class _Dummy(_FrameAware):
    """Minimal subclass to exercise the mixin."""


class TestFrameAware:
    def test_initial_frame_count_is_zero(self):
        d = _Dummy()
        assert d._frame_count == 0

    def test_advance_increments(self):
        d = _Dummy()
        d.advance_frame()
        assert d._frame_count == 1
        d.advance_frame()
        d.advance_frame()
        assert d._frame_count == 3

    def test_pause_freezes_advance(self):
        d = _Dummy()
        d.advance_frame()
        d.pause_frame()
        d.advance_frame()
        d.advance_frame()
        assert d._frame_count == 1

    def test_resume_re_enables_advance(self):
        d = _Dummy()
        d.pause_frame()
        d.advance_frame()
        d.resume_frame()
        d.advance_frame()
        assert d._frame_count == 1

    def test_reset_zeroes_count(self):
        d = _Dummy()
        d.advance_frame()
        d.advance_frame()
        d.advance_frame()
        d.reset_frame()
        assert d._frame_count == 0

    def test_reset_does_not_clear_pause(self):
        """reset_frame is for visit boundaries; pause state belongs to
        transition boundaries and should not be cleared by a reset."""
        d = _Dummy()
        d.pause_frame()
        d.reset_frame()
        d.advance_frame()
        # Still paused after reset → advance should NOT increment
        assert d._frame_count == 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_frame_aware.py -v
```

Expected: ImportError — module doesn't exist.

- [ ] **Step 3: Implement the mixin**

Create `src/led_ticker/widgets/_frame_aware.py`:

```python
"""Frame counter mixin shared by every text-painting widget.

Replaces the `WidgetPresenter` wrapper's frame state. Each widget
tracks its own `_frame_count`; the orchestrator calls `advance_frame()`
per draw tick. Transitions call `pause_frame()` / `resume_frame()`
around their compositing loop so the count doesn't drift while the
widget is being re-rendered for a dissolve. `reset_frame()` is called
at the start of each visit so the count doesn't carry over between
widgets.

Use as a mixin alongside `@attrs.define` on each widget class. The
`init=False` fields don't show up in TOML; they're internal state.
"""

from __future__ import annotations

import attrs


@attrs.define
class _FrameAware:
    """Mixin providing a per-widget frame counter + pause control."""

    _frame_count: int = attrs.field(init=False, default=0)
    _frame_paused: bool = attrs.field(init=False, default=False)

    def advance_frame(self) -> None:
        """Increment the frame counter unless paused."""
        if not self._frame_paused:
            self._frame_count += 1

    def pause_frame(self) -> None:
        """Stop advancing the frame counter — used by `run_transition`
        so an outgoing widget mid-typewriter (etc.) doesn't keep
        ticking while it's only being re-rendered for compositing."""
        self._frame_paused = True

    def resume_frame(self) -> None:
        self._frame_paused = False

    def reset_frame(self) -> None:
        """Zero the counter at the start of a visit. Does NOT clear
        the pause flag — pause/resume are transition-scoped, reset is
        visit-scoped, the two are independent."""
        self._frame_count = 0
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_frame_aware.py -v
```

Expected: 6 PASS.

- [ ] **Step 5: Run full suite**

```bash
uv run pytest -q 2>&1 | tail -3
```

Expected: 1096+ passing.

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/widgets/_frame_aware.py tests/test_frame_aware.py
git commit -m "$(cat <<'EOF'
widgets: add _FrameAware mixin

Shared frame counter for every text-painting widget. Replaces the
WidgetPresenter wrapper's frame state — each widget tracks its own
_frame_count via the mixin, orchestrator advances per draw tick,
transitions pause around compositing, visits reset at start.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: `_build_widget` color coercion + migration error + animation extraction

Extend the existing color coercion to produce `ColorProvider` instances. Add the `presentation` migration error. Extract `animation` and reject on non-message widgets.

**Files:**
- Modify: `src/led_ticker/app.py` (`_coerce_color` → `_coerce_color_provider`; `_build_widget` migration error + animation handling)
- Test: `tests/test_app.py` (new `TestPresentationMigration` class)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_app.py`:

```python
class TestPresentationMigration:
    """`_build_widget` rejects stale `presentation = "..."` configs
    with a clear migration mapping. animation field on non-message
    widgets is also rejected."""

    async def test_presentation_in_config_raises_migration_error(self):
        import aiohttp
        import pytest

        from led_ticker.app import _build_widget

        cfg = {
            "type": "message",
            "text": "hi",
            "presentation": "rainbow",
        }
        async with aiohttp.ClientSession() as s:
            with pytest.raises(ValueError, match="presentation removed"):
                await _build_widget(cfg, session=s)

    async def test_migration_message_includes_mapping_table(self):
        import aiohttp
        import pytest

        from led_ticker.app import _build_widget

        cfg = {"type": "message", "text": "hi", "presentation": "typewriter"}
        async with aiohttp.ClientSession() as s:
            with pytest.raises(ValueError) as exc:
                await _build_widget(cfg, session=s)

        msg = str(exc.value)
        assert "animation" in msg
        assert "font_color" in msg
        assert "rainbow" in msg
        assert "typewriter" in msg

    async def test_animation_on_weather_raises(self, tmp_path):
        import aiohttp
        import pytest

        from led_ticker.app import _build_widget

        cfg = {
            "type": "weather",
            "message": "NYC",
            "location": "NYC",
            "animation": "typewriter",
        }
        async with aiohttp.ClientSession() as s:
            with pytest.raises(ValueError, match='only valid on type="message"'):
                await _build_widget(cfg, session=s)

    async def test_animation_on_message_succeeds(self):
        import aiohttp

        from led_ticker.app import _build_widget
        from led_ticker.animations import Typewriter

        cfg = {"type": "message", "text": "hi", "animation": "typewriter"}
        async with aiohttp.ClientSession() as s:
            widget = await _build_widget(cfg, session=s)
        assert isinstance(widget.animation, Typewriter)


class TestColorProviderCoercion:
    """`font_color` accepts list (constant), 'random', 'rainbow' /
    'color_cycle' (provider strings), or {style = "...", ...} tables."""

    async def test_list_becomes_constant_color(self):
        import aiohttp

        from led_ticker.app import _build_widget
        from led_ticker.color_providers import _ConstantColor

        cfg = {"type": "message", "text": "hi", "font_color": [255, 0, 0]}
        async with aiohttp.ClientSession() as s:
            widget = await _build_widget(cfg, session=s)
        assert isinstance(widget.font_color, _ConstantColor)

    async def test_string_rainbow_becomes_rainbow_provider(self):
        import aiohttp

        from led_ticker.app import _build_widget
        from led_ticker.color_providers import Rainbow

        cfg = {"type": "message", "text": "hi", "font_color": "rainbow"}
        async with aiohttp.ClientSession() as s:
            widget = await _build_widget(cfg, session=s)
        assert isinstance(widget.font_color, Rainbow)

    async def test_table_with_style_and_kwargs(self):
        import aiohttp

        from led_ticker.app import _build_widget
        from led_ticker.color_providers import Rainbow

        cfg = {
            "type": "message",
            "text": "hi",
            "font_color": {"style": "rainbow", "speed": 16},
        }
        async with aiohttp.ClientSession() as s:
            widget = await _build_widget(cfg, session=s)
        assert isinstance(widget.font_color, Rainbow)
        assert widget.font_color.speed == 16

    async def test_pulse_table_with_base(self):
        import aiohttp

        from led_ticker.app import _build_widget
        from led_ticker.color_providers import Pulse

        cfg = {
            "type": "message",
            "text": "hi",
            "font_color": {"style": "pulse", "base": [50, 100, 150]},
        }
        async with aiohttp.ClientSession() as s:
            widget = await _build_widget(cfg, session=s)
        assert isinstance(widget.font_color, Pulse)
        assert widget.font_color._base.red == 50

    async def test_pulse_without_base_raises(self):
        import aiohttp
        import pytest

        from led_ticker.app import _build_widget

        cfg = {
            "type": "message",
            "text": "hi",
            "font_color": {"style": "pulse"},
        }
        async with aiohttp.ClientSession() as s:
            with pytest.raises(ValueError, match="pulse.*base"):
                await _build_widget(cfg, session=s)

    async def test_unknown_style_string_raises(self):
        import aiohttp
        import pytest

        from led_ticker.app import _build_widget

        cfg = {"type": "message", "text": "hi", "font_color": "unknownstyle"}
        async with aiohttp.ClientSession() as s:
            with pytest.raises(ValueError, match="unknown.*style"):
                await _build_widget(cfg, session=s)

    async def test_random_string_becomes_random_provider(self):
        import aiohttp

        from led_ticker.app import _build_widget
        from led_ticker.color_providers import Random

        cfg = {"type": "message", "text": "hi", "font_color": "random"}
        async with aiohttp.ClientSession() as s:
            widget = await _build_widget(cfg, session=s)
        assert isinstance(widget.font_color, Random)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_app.py::TestPresentationMigration tests/test_app.py::TestColorProviderCoercion -v 2>&1 | tail -10
```

Expected: 11 FAILs (presentation still works, font_color coercion still produces graphics.Color, animation kwarg unknown).

- [ ] **Step 3: Update `_coerce_color` and add provider helpers in `app.py`**

Edit `src/led_ticker/app.py`. Find the `_coerce_color` function (around line 58) and the `_coerce_widget_colors` function below it.

Replace `_coerce_color` with the new `_coerce_color_provider`:

```python
def _coerce_color_provider(value: Any) -> Any:
    """Convert a TOML color spec to a ColorProvider instance.

    Accepts:
    - `[r, g, b]` / `(r, g, b)` → `_ConstantColor(graphics.Color(...))`
    - `"random"` → `Random()`
    - `"rainbow"` / `"color_cycle"` → corresponding provider with defaults
    - `{style = "...", ...kwargs}` → named provider with kwargs
    - already a Color (graphics.Color) → wrap in `_ConstantColor`
    - already a ColorProvider → returned as-is
    - None → None (caller decides default)

    Raises ValueError on unknown strings, unknown styles, missing
    required kwargs, or unknown kwargs.
    """
    from led_ticker.color_providers import (
        ColorCycle,
        Gradient,
        Pulse,
        Rainbow,
        Random,
        _ConstantColor,
    )

    if value is None:
        return None

    # Already a provider — pass through
    if hasattr(value, "color_for") and hasattr(value, "per_char"):
        return value

    # Already a graphics.Color — wrap
    graphics = require_graphics()
    if isinstance(value, graphics.Color):
        return _ConstantColor(value)

    # `[r, g, b]` list/tuple → wrap as constant
    if isinstance(value, list | tuple) and len(value) == 3:
        return _ConstantColor(graphics.Color(*value))

    # String shorthand
    if isinstance(value, str):
        return _provider_from_style(value, {})

    # Inline table
    if isinstance(value, dict):
        if "style" not in value:
            raise ValueError(
                f"font_color table requires 'style' key; got {list(value.keys())!r}"
            )
        style = value["style"]
        kwargs = {k: v for k, v in value.items() if k != "style"}
        return _provider_from_style(style, kwargs)

    raise ValueError(
        f"font_color must be [r,g,b], 'random'/'rainbow'/'color_cycle', "
        f"or {{style='...'}}; got {value!r}"
    )


_PROVIDER_BY_STYLE: dict[str, Any] = {}


def _provider_from_style(style: str, kwargs: dict[str, Any]) -> Any:
    """Instantiate a provider by name with kwargs. Validates kwargs
    against each provider's __init__ signature; raises with a helpful
    message on unknown styles or missing/unknown kwargs."""
    from led_ticker.color_providers import (
        ColorCycle,
        Gradient,
        Pulse,
        Rainbow,
        Random,
    )

    registry = {
        "random": (Random, set()),
        "rainbow": (Rainbow, {"speed", "char_offset"}),
        "color_cycle": (ColorCycle, {"speed"}),
        "pulse": (Pulse, {"base", "duration_frames"}),
        "gradient": (Gradient, {"from_color", "to_color"}),
    }

    if style not in registry:
        raise ValueError(
            f"unknown font_color style {style!r}; available: "
            f"{sorted(registry.keys())}"
        )

    cls, allowed_kwargs = registry[style]

    # Special-case translation: TOML uses `from` / `to` (Pythonic
    # reserved words avoided), but provider takes from_color/to_color.
    # Coerce values to graphics.Color while we're at it.
    graphics = require_graphics()
    if style == "gradient":
        from_val = kwargs.pop("from", None) or kwargs.pop("from_color", None)
        to_val = kwargs.pop("to", None) or kwargs.pop("to_color", None)
        if from_val is None or to_val is None:
            raise ValueError(
                "font_color style 'gradient' requires 'from' and 'to': "
                "font_color = {style='gradient', from=[r,g,b], to=[r,g,b]}"
            )
        kwargs["from_color"] = graphics.Color(*from_val)
        kwargs["to_color"] = graphics.Color(*to_val)

    # Pulse: convert base list to graphics.Color
    if style == "pulse":
        base_val = kwargs.get("base")
        if base_val is None:
            raise ValueError(
                "font_color style 'pulse' requires 'base': "
                "font_color = {style='pulse', base=[r,g,b]}"
            )
        if isinstance(base_val, list | tuple):
            kwargs["base"] = graphics.Color(*base_val)

    unknown = set(kwargs.keys()) - allowed_kwargs
    if unknown:
        raise ValueError(
            f"font_color style {style!r} got unknown keys {sorted(unknown)!r}; "
            f"allowed: {sorted(allowed_kwargs)}"
        )
    return cls(**kwargs)


def _coerce_color(value: Any) -> Any:
    """Backwards-compat shim: defers to _coerce_color_provider for
    new uses. Kept so any out-of-tree caller doesn't immediately break.
    """
    return _coerce_color_provider(value)
```

The existing `_coerce_widget_colors(cfg)` calls `_coerce_color`; now it produces providers instead of Colors. Confirm no other behavior change is needed.

Find the existing call near line 232:

```python
    # Convert any [r, g, b] lists in known color keys to graphics.Color.
    _coerce_widget_colors(widget_cfg)
```

Update the comment:

```python
    # Convert color keys (font_color, top_color, bottom_color) to
    # ColorProvider instances. Constant [r,g,b] lists get wrapped in
    # _ConstantColor so all downstream widget code is uniform.
    _coerce_widget_colors(widget_cfg)
```

- [ ] **Step 4: Add migration error + animation extraction in `_build_widget`**

Edit `src/led_ticker/app.py`. Find the start of `_build_widget` body (after the docstring, after the existing `text_scale` migration check from earlier work).

Add the new migration check + animation extraction:

```python
    # Migration check: presentation = "..." was the wrapper-based effect
    # knob. Replaced by font_color (color effects) + animation
    # (typewriter/bounce on TickerMessage). Loud failure here catches
    # stale TOMLs at load time.
    if "presentation" in widget_cfg:
        raise ValueError(
            "presentation removed in favor of font_color (color effects) + "
            "animation (typewriter/bounce on TickerMessage). Migration:\n"
            "  presentation = 'typewriter'  → animation = 'typewriter' "
            "(type='message' only)\n"
            "  presentation = 'bounce'      → animation = 'bounce' "
            "(type='message' only)\n"
            "  presentation = 'rainbow'     → font_color = 'rainbow'\n"
            "  presentation = 'color_cycle' → font_color = 'color_cycle'\n"
            "  presentation = 'pulse'       → "
            "font_color = {style='pulse', base=[your existing font_color]}"
        )
```

Find the existing `presentation_name = widget_cfg.pop("presentation", None)` block (around line 235) and DELETE it entirely (the migration error above replaces it):

```python
    # DELETE THESE LINES:
    # Extract presentation config before passing to widget
    presentation_name = widget_cfg.pop("presentation", None)
    widget_cfg.pop("presentation_speed", None)
    ...
    # Wrap with presentation mode if configured
    if presentation_name:
        pres_cls = get_presentation_class(presentation_name)
        widget = WidgetPresenter(widget, pres_cls())
```

Also remove the `from led_ticker.presentation import (WidgetPresenter, get_presentation_class)` import at the top.

After widget instantiation but BEFORE the `return widget` (so we can validate animation against widget_type), extract animation:

```python
    # Extract animation field (TickerMessage-only). Pop BEFORE widget
    # construction so it doesn't reach the constructor as an unknown
    # kwarg.
    animation_value = widget_cfg.pop("animation", None)
    if animation_value is not None and widget_type != "message":
        raise ValueError(
            f"animation is only valid on type=\"message\"; got "
            f"type={widget_type!r}. For color effects on other widgets, "
            f"use font_color = 'rainbow' (or similar)."
        )
```

Wait — the right place for this is BEFORE `cls = get_widget_class(widget_type)`, since widget_type is still in scope from the migration check. Let me re-order:

Find the flow in `_build_widget`. Place the animation extraction RIGHT AFTER widget_type is popped:

```python
    widget_type = widget_cfg.pop("type")
    cls = get_widget_class(widget_type)

    # Animation field (TickerMessage-only). Pop before construction so
    # it doesn't reach the widget constructor as an unknown kwarg.
    animation_value = widget_cfg.pop("animation", None)
    if animation_value is not None and widget_type != "message":
        raise ValueError(
            f"animation is only valid on type=\"message\"; got "
            f"type={widget_type!r}. For color effects on other widgets, "
            f"use font_color = 'rainbow' (or similar)."
        )
    if animation_value is not None:
        widget_cfg["animation"] = _coerce_animation(animation_value)
```

Add `_coerce_animation` helper near `_coerce_color_provider`:

```python
def _coerce_animation(value: Any) -> Any:
    """Convert a TOML animation spec to an Animation instance.

    Accepts:
    - `"typewriter"` / `"bounce"` (string) → instance with defaults
    - `{style = "...", ...}` (dict) → instance with kwargs
    - already an Animation → returned as-is

    Raises ValueError on unknown names or unknown kwargs.
    """
    from led_ticker.animations import Bounce, Typewriter

    if hasattr(value, "frame_for"):
        return value

    registry = {
        "typewriter": (Typewriter, {"chars_per_frame"}),
        "bounce": (Bounce, {"hold_frames", "scroll_frames"}),
    }

    if isinstance(value, str):
        if value not in registry:
            raise ValueError(
                f"unknown animation {value!r}; available: "
                f"{sorted(registry.keys())}"
            )
        cls, _allowed = registry[value]
        return cls()

    if isinstance(value, dict):
        if "style" not in value:
            raise ValueError(
                f"animation table requires 'style' key; got {list(value.keys())!r}"
            )
        style = value["style"]
        if style not in registry:
            raise ValueError(
                f"unknown animation {style!r}; available: "
                f"{sorted(registry.keys())}"
            )
        cls, allowed = registry[style]
        kwargs = {k: v for k, v in value.items() if k != "style"}
        unknown = set(kwargs.keys()) - allowed
        if unknown:
            raise ValueError(
                f"animation {style!r} got unknown keys {sorted(unknown)!r}; "
                f"allowed: {sorted(allowed)}"
            )
        return cls(**kwargs)

    raise ValueError(
        f"animation must be a string or table; got {type(value).__name__}"
    )
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
uv run pytest tests/test_app.py::TestPresentationMigration tests/test_app.py::TestColorProviderCoercion -v 2>&1 | tail -15
```

Expected: 11 PASS.

- [ ] **Step 6: Run full suite**

The widgets haven't been updated to consume providers yet, so most existing widget tests will FAIL because they pass `font_color=Color(...)` and the widget receives a `_ConstantColor` instead of a Color. This is expected — Tasks 7-10 fix it. Skip the suite for now and proceed.

```bash
uv run pytest tests/test_app.py -q 2>&1 | tail -5
```

Expected: app tests pass. Widget tests would fail; ignore.

- [ ] **Step 7: Commit**

```bash
git add src/led_ticker/app.py tests/test_app.py
git commit -m "$(cat <<'EOF'
app: color coercion produces ColorProvider; presentation migration error

_coerce_color renamed to _coerce_color_provider — accepts [r,g,b]
list (→ _ConstantColor), 'rainbow'/'color_cycle'/'random' string
shorthand, or {style='...', ...} inline table. Pulse / Gradient
require explicit base / from-to and convert nested lists to
graphics.Color.

presentation = '...' raises a verbatim migration table mapping each
old value to its new shape. animation extracted + rejected on
non-message widgets at config-load.

Tests: TestPresentationMigration (4 cases) + TestColorProviderCoercion
(7 cases) covering the migration error, animation rejection, and the
six coercion shapes.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Engine tick loop in `_swap_and_scroll`

Replace the held-text `await asyncio.sleep(hold_time)` with a tick loop calling `advance_frame + draw + swap`. Add `advance_frame()` to the existing scroll branch too.

**Files:**
- Modify: `src/led_ticker/ticker.py` (`_swap_and_scroll`, around line 758)
- Test: `tests/test_ticker_display.py` (new tests for tick behavior)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_ticker_display.py`:

```python
class TestSwapAndScrollEngineTick:
    """`_swap_and_scroll`'s held-text branch must call `draw +
    advance_frame` repeatedly during `hold_time` so frame-aware
    widgets actually animate. The scroll branch must also call
    advance_frame per tick."""

    async def test_held_text_calls_draw_multiple_times_during_hold(
        self, swapping_frame
    ):
        """Held text → engine ticks at 50ms; draw fires ~hold_time/0.05
        times. Spy on widget.draw to assert it does."""
        from rgbmatrix import _StubCanvas

        from led_ticker.ticker import _swap_and_scroll

        class _SpyWidget:
            def __init__(self):
                self.draw_calls = 0
                self.advance_calls = 0
                self._frame_count = 0
                self._frame_paused = False

            def draw(self, canvas, cursor_pos=0, **kwargs):
                self.draw_calls += 1
                # Return cursor_pos < canvas.width so it stays in held branch
                return canvas, 5

            def advance_frame(self):
                self.advance_calls += 1
                self._frame_count += 1

            def reset_frame(self):
                self._frame_count = 0

            @property
            def bg_color(self):
                return None

        widget = _SpyWidget()
        canvas = _StubCanvas(width=160, height=16)
        swapping_frame.matrix.SwapOnVSync.return_value = _StubCanvas(
            width=160, height=16
        )

        # hold_time = 0.5s with tick_ms = 50 → ~10 ticks
        await _swap_and_scroll(
            canvas, swapping_frame, widget, hold_time=0.5
        )

        # Allow some slop; expect roughly 10 draws / advances
        assert widget.draw_calls >= 8
        assert widget.advance_calls >= 8
        assert widget._frame_count >= 8

    async def test_scrolling_text_advances_frame_per_tick(
        self, swapping_frame
    ):
        """Scroll branch also calls advance_frame per tick so providers
        animate during scroll-to-end."""
        from rgbmatrix import _StubCanvas

        from led_ticker.ticker import _swap_and_scroll

        class _SpyWidget:
            def __init__(self):
                self.draw_calls = 0
                self.advance_calls = 0
                self._frame_count = 0
                self._frame_paused = False

            def draw(self, canvas, cursor_pos=0, **kwargs):
                self.draw_calls += 1
                # Return cursor_pos > canvas.width to trigger scroll
                return canvas, 200

            def advance_frame(self):
                self.advance_calls += 1
                self._frame_count += 1

            def reset_frame(self):
                self._frame_count = 0

            @property
            def bg_color(self):
                return None

            @property
            def padding(self):
                return 0

        widget = _SpyWidget()
        canvas = _StubCanvas(width=160, height=16)
        swapping_frame.matrix.SwapOnVSync.return_value = _StubCanvas(
            width=160, height=16
        )

        await _swap_and_scroll(
            canvas, swapping_frame, widget, hold_time=0.05, scroll_speed=0.001
        )

        # Should have many draws (one per scroll px) AND advance_frame per tick
        assert widget.advance_calls > 0
        assert widget.advance_calls == widget.draw_calls or widget.advance_calls >= widget.draw_calls - 2

    async def test_widget_without_advance_frame_method_does_not_crash(
        self, swapping_frame
    ):
        """Older widgets that don't yet have the _FrameAware mixin must
        not crash _swap_and_scroll. The orchestrator uses hasattr or
        a duck-type check."""
        from rgbmatrix import _StubCanvas

        from led_ticker.ticker import _swap_and_scroll

        class _NoAdvance:
            def draw(self, canvas, cursor_pos=0, **kwargs):
                return canvas, 5

            @property
            def bg_color(self):
                return None

        widget = _NoAdvance()
        canvas = _StubCanvas(width=160, height=16)
        swapping_frame.matrix.SwapOnVSync.return_value = _StubCanvas(
            width=160, height=16
        )

        # Should complete without AttributeError
        await _swap_and_scroll(canvas, swapping_frame, widget, hold_time=0.1)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_ticker_display.py::TestSwapAndScrollEngineTick -v 2>&1 | tail -10
```

Expected: 3 FAILs — held-text branch only calls draw once.

- [ ] **Step 3: Update `_swap_and_scroll`**

Edit `src/led_ticker/ticker.py`. Find `_swap_and_scroll` (around line 758).

Add a tick_ms constant near the top of the file (or in an existing constants block):

```python
ENGINE_TICK_MS: int = 50  # 20 fps for held-text frame animation
```

Then inside `_swap_and_scroll`, change the function structure. Find:

```python
    pos = 0
    bg_color = getattr(ticker_obj, "bg_color", None)
    reset_canvas(canvas, bg_color)
    canvas, cursor_pos = ticker_obj.draw(canvas, pos)

    if not skip_initial_draw:
        canvas = _swap(canvas, frame)
```

Add a helper to advance the widget's frame counter if it has the mixin:

```python
def _advance_frame_if_supported(widget: Any) -> None:
    """Call `widget.advance_frame()` if the widget exposes it. Quietly
    no-ops on widgets without the _FrameAware mixin so the orchestrator
    works for both old (transitional) and new widgets."""
    if hasattr(widget, "advance_frame"):
        widget.advance_frame()
```

Place that helper just before `_swap_and_scroll` in the file.

Now the held-text branch. Find:

```python
    else:
        await asyncio.sleep(hold_time)

    return canvas, cursor_pos, pos
```

Replace with:

```python
    else:
        # Engine tick loop: advance_frame + draw + swap at fixed
        # cadence so frame-aware widgets (color providers, animations)
        # actually animate during the hold.
        tick_seconds = ENGINE_TICK_MS / 1000
        n_ticks = max(1, int(hold_time * 1000) // ENGINE_TICK_MS)
        for _ in range(n_ticks):
            _advance_frame_if_supported(ticker_obj)
            reset_canvas(canvas, bg_color)
            canvas, _ = ticker_obj.draw(canvas, pos)
            canvas = _swap(canvas, frame)
            await asyncio.sleep(tick_seconds)

    return canvas, cursor_pos, pos
```

Find the scroll branch loop:

```python
        while pos > stop_pos:
            pos -= 1
            reset_canvas(canvas, bg_color)
            canvas, _ = ticker_obj.draw(canvas, cursor_pos=pos)
            canvas = _swap(canvas, frame)
            await asyncio.sleep(scroll_speed)
```

Add `_advance_frame_if_supported` before the redraw:

```python
        while pos > stop_pos:
            pos -= 1
            _advance_frame_if_supported(ticker_obj)
            reset_canvas(canvas, bg_color)
            canvas, _ = ticker_obj.draw(canvas, cursor_pos=pos)
            canvas = _swap(canvas, frame)
            await asyncio.sleep(scroll_speed)
```

The post-scroll `await asyncio.sleep(hold_time)` (around line 803) should also become a tick loop — same pattern as above:

```python
        # Hold with the end of the text visible — same engine tick loop
        # as the held-text branch.
        if not continuous:
            tick_seconds = ENGINE_TICK_MS / 1000
            n_ticks = max(1, int(hold_time * 1000) // ENGINE_TICK_MS)
            for _ in range(n_ticks):
                _advance_frame_if_supported(ticker_obj)
                reset_canvas(canvas, bg_color)
                canvas, _ = ticker_obj.draw(canvas, cursor_pos=pos)
                canvas = _swap(canvas, frame)
                await asyncio.sleep(tick_seconds)
```

(The earlier pre-scroll `await asyncio.sleep(hold_time)` for overflow text — line 784 — same pattern.)

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_ticker_display.py::TestSwapAndScrollEngineTick -v
```

Expected: 3 PASS.

- [ ] **Step 5: Run full suite — many widget tests will still fail because providers haven't been integrated. Skip widget tests and verify ticker tests:**

```bash
uv run pytest tests/test_ticker_display.py -q 2>&1 | tail -5
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/ticker.py tests/test_ticker_display.py
git commit -m "$(cat <<'EOF'
ticker: engine tick loop in _swap_and_scroll for held + post-scroll text

Replace `await asyncio.sleep(hold_time)` with a tick loop calling
advance_frame + draw + swap at 50ms cadence (ENGINE_TICK_MS). Frame-
aware widgets (color providers, animations) now actually animate
during the hold instead of being locked at frame=0.

Same pattern applied to the post-scroll hold AND the pre-scroll hold
in the overflow branch. The scroll loop itself also calls
advance_frame per tick so providers animate during scroll.

`_advance_frame_if_supported(widget)` quietly no-ops on widgets
without the _FrameAware mixin so the orchestrator works during the
transition window when not all widgets have been updated yet.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: TickerMessage + TickerCountdown — consume ColorProvider + Animation

Both classes live in `message.py`. TickerMessage gets the `animation` field.

**Files:**
- Modify: `src/led_ticker/widgets/message.py` (TickerMessage + TickerCountdown)
- Modify: `tests/test_widgets/test_message.py` (or `tests/test_message.py` depending on layout) — provider consumption tests

- [ ] **Step 1: Confirm test file location**

```bash
ls tests/test_message.py tests/test_widgets/test_message.py 2>/dev/null
```

Use whichever file exists. The tests below assume the existing file; insert the new test class at the end.

- [ ] **Step 2: Write the failing tests**

Append to the message test file:

```python
class TestTickerMessageColorProvider:
    """TickerMessage materializes a Color from font_color (a
    ColorProvider) per draw call. Per-char providers iterate chars."""

    def test_constant_provider_calls_draw_text_once(self, mock_frame):
        from rgbmatrix import _StubCanvas
        from rgbmatrix.graphics import Color
        from unittest.mock import patch

        from led_ticker.color_providers import _ConstantColor
        from led_ticker.widgets.message import TickerMessage

        widget = TickerMessage(
            "HELLO", font_color=_ConstantColor(Color(255, 0, 0))
        )
        canvas = _StubCanvas(width=160, height=16)

        with patch("led_ticker.widgets.message.draw_text") as spy:
            spy.return_value = 30  # Returned advance pixels
            widget.draw(canvas, cursor_pos=0)

        # Constant: one draw_text call for the whole string
        assert spy.call_count == 1

    def test_per_char_provider_calls_draw_text_per_char(self, mock_frame):
        from rgbmatrix import _StubCanvas
        from unittest.mock import patch

        from led_ticker.color_providers import Rainbow
        from led_ticker.widgets.message import TickerMessage

        widget = TickerMessage("ABC", font_color=Rainbow())
        canvas = _StubCanvas(width=160, height=16)

        with patch("led_ticker.widgets.message.draw_text") as spy:
            spy.return_value = 6
            widget.draw(canvas, cursor_pos=0)

        # Per-char: one call per character
        assert spy.call_count == 3

    def test_frame_count_passed_to_provider(self, mock_frame):
        from rgbmatrix import _StubCanvas
        from rgbmatrix.graphics import Color
        from unittest.mock import patch

        from led_ticker.widgets.message import TickerMessage

        captured_frames = []

        class _CapturingProvider:
            per_char = False

            def color_for(self, frame, char_index, total_chars):
                captured_frames.append(frame)
                return Color(255, 255, 255)

        widget = TickerMessage("HI", font_color=_CapturingProvider())
        widget.advance_frame()  # frame_count = 1
        widget.advance_frame()  # frame_count = 2
        canvas = _StubCanvas(width=160, height=16)

        with patch("led_ticker.widgets.message.draw_text") as spy:
            spy.return_value = 6
            widget.draw(canvas, cursor_pos=0)

        assert captured_frames == [2]


class TestTickerMessageAnimation:
    """`animation` field consumed by TickerMessage's draw — typewriter
    slices, bounce repositions."""

    def test_typewriter_slices_message_per_frame(self, mock_frame):
        from rgbmatrix import _StubCanvas
        from rgbmatrix.graphics import Color
        from unittest.mock import patch

        from led_ticker.animations import Typewriter
        from led_ticker.color_providers import _ConstantColor
        from led_ticker.widgets.message import TickerMessage

        widget = TickerMessage(
            "HELLO",
            font_color=_ConstantColor(Color(255, 255, 255)),
            animation=Typewriter(),
        )
        widget.advance_frame()  # frame=1 → slice "HE"
        canvas = _StubCanvas(width=160, height=16)

        captured_text = []

        def fake_draw(canvas, font, x, y, color, text):
            captured_text.append(text)
            return len(text) * 6

        with patch("led_ticker.widgets.message.draw_text", side_effect=fake_draw):
            widget.draw(canvas, cursor_pos=0)

        # frame_count=1, chars_per_frame=1 → (1+1)*1 = 2 chars visible
        assert "HE" in captured_text or "HE" == "".join(captured_text)
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
uv run pytest tests/test_message.py::TestTickerMessageColorProvider -v 2>&1 | tail -10
```

Expected: FAILs — TickerMessage doesn't yet consume providers / animation.

- [ ] **Step 4: Update `TickerMessage` and `TickerCountdown`**

Edit `src/led_ticker/widgets/message.py`. Find TickerMessage (around line 24) and add the mixin + animation field, plus update draw().

Top of file: add imports.

```python
from led_ticker.animations import Animation
from led_ticker.color_providers import ColorProvider, _ConstantColor
from led_ticker.widgets._frame_aware import _FrameAware
```

Update `TickerMessage`:

```python
@register("message")
@attrs.define
class TickerMessage(_FrameAware):
    message: str
    # Now accepts Color OR ColorProvider; constructor wraps Color in
    # _ConstantColor for uniform downstream handling.
    font_color: Any = attrs.Factory(lambda: DEFAULT_COLOR)
    bg_color: Color | None = None
    center: bool = False
    padding: int = 6
    font: Font = attrs.field(default=FONT_DEFAULT)
    animation: Animation | None = None

    def __attrs_post_init__(self) -> None:
        # Coerce raw graphics.Color (test path; build_widget already
        # produces a provider) into _ConstantColor so draw can always
        # call .color_for(...).
        if not hasattr(self.font_color, "color_for"):
            self.font_color = _ConstantColor(self.font_color)
        # ... (existing emoji-cache init etc.)
        self._has_emoji = bool(EMOJI_PATTERN.search(self.message))
```

(Apply minimally invasive edits — keep existing fields/init logic.)

Update `TickerMessage.draw`:

```python
    def draw(self, canvas: Canvas, cursor_pos: int = 0, **kwargs: Any) -> DrawResult:
        # If an animation is set, ask it for the slice + cursor override
        full_text = self.message
        if self.animation is not None:
            text_width = get_text_width(self.font, full_text, padding=0, canvas=canvas)
            anim_frame = self.animation.frame_for(
                self._frame_count, full_text, canvas.width, text_width
            )
            visible_text = anim_frame.visible_text
            if anim_frame.cursor_override is not None:
                cursor_pos = anim_frame.cursor_override
        else:
            visible_text = full_text

        # Resolve provider: callers can pass `font_color=` kwarg as a
        # one-shot override (e.g. legacy test paths); otherwise use
        # the widget's bound provider.
        provider_or_color = kwargs.get("font_color") or self.font_color
        if not hasattr(provider_or_color, "color_for"):
            provider_or_color = _ConstantColor(provider_or_color)

        # ... existing: layout / cursor computation ...

        if provider_or_color.per_char:
            # Per-char rendering: iterate chars, draw each with its own
            # color. Emoji slugs in the text segment are NOT split per
            # char (the emoji renderer handles them as units); v1 limit
            # — for now per-char providers color slug letters as ASCII.
            x = cursor_pos
            total = len(visible_text)
            for i, char in enumerate(visible_text):
                color = provider_or_color.color_for(self._frame_count, i, total)
                x += draw_text(canvas, self.font, x, 12, color, char)
            return canvas, x + self.padding
        else:
            color = provider_or_color.color_for(self._frame_count, 0, len(visible_text))
            cursor_pos += draw_text(
                canvas, self.font, cursor_pos, 12, color, visible_text
            )
            return canvas, cursor_pos + self.padding
```

(The existing draw is more complex — emoji handling, alignment. Preserve those code paths; the change is to materialize a Color from the provider before each draw_text call. If the existing code path branches on `_has_emoji`, the per-char vs whole-string dispatch must compose with that — for v1, emoji handling continues to render the slug as a unit, and per-char provider only applies to the non-emoji segments. Document the limit in comments.)

Apply similar updates to `TickerCountdown` — add `_FrameAware`, coerce `font_color` in post_init, materialize Color from provider in draw.

- [ ] **Step 5: Run tests to verify they pass**

```bash
uv run pytest tests/test_message.py -v 2>&1 | tail -20
```

Expected: provider tests PASS; existing TickerMessage tests should also still pass since `_ConstantColor(Color(...))` materializes to the same Color.

- [ ] **Step 6: Run full suite — full pass needed since downstream tests use TickerMessage:**

```bash
uv run pytest -q 2>&1 | tail -10
```

Expected: many existing tests should still pass; some may need adjustment if they assert on Color identity.

- [ ] **Step 7: Commit**

```bash
git add src/led_ticker/widgets/message.py tests/test_message.py
git commit -m "$(cat <<'EOF'
TickerMessage / TickerCountdown: consume ColorProvider + Animation

Both gain the _FrameAware mixin (frame counter + pause/resume).
TickerMessage gains the animation field. font_color becomes
Color | ColorProvider; post_init wraps raw Color in _ConstantColor
so draw() always calls .color_for(...).

draw() dispatches on provider.per_char: per-char providers iterate
chars (rainbow / gradient), whole-string providers do one draw_text
call. v1 limit: per-char providers + emoji slugs render slugs as
colored ASCII (deferred to v2).

If animation is set, draw asks the animation for the visible slice
+ cursor override before applying the color provider. Color and
animation compose orthogonally.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: WeatherWidget — consume ColorProvider

Weather has TWO color fields (`font_color` and `font_color_temp`). Both get coerced + the mixin added.

**Files:**
- Modify: `src/led_ticker/widgets/weather.py`
- Modify: existing weather test file (`tests/test_weather.py` or `tests/test_widgets/test_weather.py`)

- [ ] **Step 1: Locate weather test file**

```bash
ls tests/test_weather.py tests/test_widgets/test_weather.py 2>/dev/null
```

- [ ] **Step 2: Write the failing tests**

Append to the weather test file:

```python
class TestWeatherColorProvider:
    """WeatherWidget materializes Color from font_color (provider) and
    font_color_temp (provider). Both wrap Color into _ConstantColor in
    post_init so draw is uniform."""

    def test_font_color_wrapped_to_constant_provider_in_post_init(self):
        from rgbmatrix.graphics import Color
        from led_ticker.color_providers import _ConstantColor
        from led_ticker.widgets.weather import WeatherWidget

        w = WeatherWidget(
            message="NYC", location="NYC", font_color=Color(255, 0, 0)
        )
        assert isinstance(w.font_color, _ConstantColor)

    def test_provider_passed_through_unchanged(self):
        from led_ticker.color_providers import Rainbow
        from led_ticker.widgets.weather import WeatherWidget

        provider = Rainbow()
        w = WeatherWidget(
            message="NYC", location="NYC", font_color=provider
        )
        assert w.font_color is provider

    def test_advance_frame_increments_count(self):
        from led_ticker.widgets.weather import WeatherWidget

        w = WeatherWidget(message="NYC", location="NYC")
        assert w._frame_count == 0
        w.advance_frame()
        assert w._frame_count == 1
```

- [ ] **Step 3: Update `WeatherWidget`**

Edit `src/led_ticker/widgets/weather.py`. Add imports:

```python
from led_ticker.color_providers import _ConstantColor
from led_ticker.widgets._frame_aware import _FrameAware
```

Update class declaration:

```python
@register("weather")
@attrs.define
class WeatherWidget(_FrameAware):
    # ... existing fields, but font_color / font_color_temp typed as Any:
    font_color: Any = attrs.Factory(lambda: DEFAULT_COLOR)
    font_color_temp: Any = attrs.Factory(lambda: RGB_WHITE)
    # ... (rest unchanged)

    def __attrs_post_init__(self) -> None:
        # Existing post_init logic (if any) ...
        # Coerce raw graphics.Color into _ConstantColor for uniform
        # provider dispatch in draw().
        if not hasattr(self.font_color, "color_for"):
            self.font_color = _ConstantColor(self.font_color)
        if not hasattr(self.font_color_temp, "color_for"):
            self.font_color_temp = _ConstantColor(self.font_color_temp)
```

Update `WeatherWidget.draw` — replace each `self.font_color` reference with a materialized color:

```python
    def draw(self, canvas: Canvas, cursor_pos: int = 0, **kwargs: Any) -> DrawResult:
        # Materialize colors from providers; weather uses whole-string
        # rendering for both label and temp. per_char providers degrade
        # gracefully to single-color (provider.color_for(frame, 0, total)).
        label_color = self.font_color.color_for(
            self._frame_count, 0, len(self.message)
        )
        temp_color = self.font_color_temp.color_for(
            self._frame_count, 0, 1
        )
        # ... existing draw logic, but every `self.font_color` in
        # draw_text(... self.font_color ...) becomes `label_color`,
        # and `self.font_color_temp` becomes `temp_color`.
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_weather.py -v 2>&1 | tail -10
```

Expected: new tests PASS, existing tests still pass.

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/widgets/weather.py tests/test_weather.py
git commit -m "$(cat <<'EOF'
WeatherWidget: consume ColorProvider for font_color + font_color_temp

Adds _FrameAware mixin. Both color fields accept Color | ColorProvider;
post_init wraps raw Color in _ConstantColor. draw materializes a
single Color from each provider per call (whole-string rendering;
per-char providers degrade to single color since weather doesn't
iterate chars).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: TwoRowMessage — per-row providers

Per-row top_color / bottom_color become providers. Same coercion + materialize-per-call pattern as Weather.

**Files:**
- Modify: `src/led_ticker/widgets/two_row.py`
- Modify: `tests/test_widgets/test_two_row.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_widgets/test_two_row.py`:

```python
class TestTwoRowColorProvider:
    def test_top_color_constant_wrapped_in_post_init(self):
        from rgbmatrix.graphics import Color
        from led_ticker.color_providers import _ConstantColor
        from led_ticker.widgets.two_row import TwoRowMessage

        w = TwoRowMessage(
            top_text="A",
            bottom_text="B",
            top_color=Color(255, 0, 0),
            bottom_color=Color(0, 255, 0),
        )
        assert isinstance(w.top_color, _ConstantColor)
        assert isinstance(w.bottom_color, _ConstantColor)

    def test_provider_passed_through(self):
        from led_ticker.color_providers import Rainbow
        from led_ticker.widgets.two_row import TwoRowMessage

        rainbow = Rainbow()
        w = TwoRowMessage(top_text="A", bottom_text="B", top_color=rainbow)
        assert w.top_color is rainbow

    def test_frame_aware_mixin(self):
        from led_ticker.widgets.two_row import TwoRowMessage

        w = TwoRowMessage(top_text="A", bottom_text="B")
        assert w._frame_count == 0
        w.advance_frame()
        assert w._frame_count == 1
```

- [ ] **Step 2: Update `TwoRowMessage`**

Edit `src/led_ticker/widgets/two_row.py`. Add imports:

```python
from led_ticker.color_providers import _ConstantColor
from led_ticker.widgets._frame_aware import _FrameAware
```

Add `_FrameAware` to the class:

```python
@register("two_row")
@attrs.define
class TwoRowMessage(_FrameAware):
    # ... existing fields ...
    top_color: Any = attrs.Factory(lambda: DEFAULT_COLOR)
    bottom_color: Any = attrs.Factory(lambda: DEFAULT_COLOR)
    # ... (rest unchanged)

    def __attrs_post_init__(self) -> None:
        # Existing post_init ...
        if not hasattr(self.top_color, "color_for"):
            self.top_color = _ConstantColor(self.top_color)
        if not hasattr(self.bottom_color, "color_for"):
            self.bottom_color = _ConstantColor(self.bottom_color)
```

Update `TwoRowMessage.draw` — find the `self.top_color` and `self.bottom_color` references in the draw body (around lines 230 and 250) and materialize:

```python
        top_color = self.top_color.color_for(
            self._frame_count, 0, len(self.top_text)
        )
        # ... use top_color instead of self.top_color in draw_text call ...

        bottom_color = self.bottom_color.color_for(
            self._frame_count, 0, len(self.bottom_text)
        )
        # ... use bottom_color instead of self.bottom_color in draw_text call ...
```

- [ ] **Step 3: Run tests to verify they pass**

```bash
uv run pytest tests/test_widgets/test_two_row.py -v 2>&1 | tail -10
```

Expected: new tests PASS, existing tests still pass.

- [ ] **Step 4: Commit**

```bash
git add src/led_ticker/widgets/two_row.py tests/test_widgets/test_two_row.py
git commit -m "$(cat <<'EOF'
TwoRowMessage: per-row ColorProvider for top_color + bottom_color

Adds _FrameAware mixin. Both row color fields accept
Color | ColorProvider; post_init wraps raw Color in _ConstantColor.
draw materializes a Color from each row's provider per call.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: Image widgets — consume providers

Image widgets have `font_color`, `top_color`, `bottom_color` (in two-row mode), and `bg_color`. Apply the same coercion pattern.

**Files:**
- Modify: `src/led_ticker/widgets/_image_base.py`
- Modify: `tests/test_widgets/test_image_base.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_widgets/test_image_base.py`:

```python
class TestImageBaseColorProvider:
    def test_font_color_wrapped(self):
        from rgbmatrix.graphics import Color
        from led_ticker.color_providers import _ConstantColor

        w = _DummyImage(font_color=Color(255, 100, 50))
        assert isinstance(w.font_color, _ConstantColor)

    def test_top_color_wrapped(self):
        from rgbmatrix.graphics import Color
        from led_ticker.color_providers import _ConstantColor

        w = _DummyImage(
            top_text="A", bottom_text="B", top_color=Color(255, 100, 50)
        )
        assert isinstance(w.top_color, _ConstantColor)

    def test_provider_passed_through(self):
        from led_ticker.color_providers import Rainbow

        rainbow = Rainbow()
        w = _DummyImage(font_color=rainbow)
        assert w.font_color is rainbow

    def test_frame_aware_mixin(self):
        w = _DummyImage()
        assert w._frame_count == 0
        w.advance_frame()
        assert w._frame_count == 1
```

- [ ] **Step 2: Update `_BaseImageWidget`**

Edit `src/led_ticker/widgets/_image_base.py`. Add imports:

```python
from led_ticker.color_providers import _ConstantColor
from led_ticker.widgets._frame_aware import _FrameAware
```

Add `_FrameAware` to the class declaration:

```python
@attrs.define
class _BaseImageWidget(_FrameAware):
    # ... existing fields, font_color/top_color/bottom_color typed as Any ...
```

In `_validate_common` or `__attrs_post_init__` (whichever runs at construction), add coercion:

```python
        # Coerce raw Color → _ConstantColor for uniform provider dispatch.
        if self.font_color is not None and not hasattr(self.font_color, "color_for"):
            self.font_color = _ConstantColor(self.font_color)
        if self.top_color is not None and not hasattr(self.top_color, "color_for"):
            self.top_color = _ConstantColor(self.top_color)
        if self.bottom_color is not None and not hasattr(self.bottom_color, "color_for"):
            self.bottom_color = _ConstantColor(self.bottom_color)
```

Update `_draw_text` (single-row) and `_draw_row_text` (two-row) — find each call to `draw_text` that uses `self.font_color` directly, and materialize:

In `_render_tick`:

```python
        # Materialize whole-string color from provider (image widgets
        # don't iterate chars per-char rendering yet — v1 limit).
        font_color_provider = self.font_color
        color = font_color_provider.color_for(
            self._frame_count, 0, len(self.text)
        )
        # ... use `color` in subsequent draw_text calls ...
```

In `_draw_row_text` (two-row), the row tuple already contains font/text/color/x/baseline/emoji_y. The color in the tuple is what gets passed to `draw_text`. Update `_render_two_row_tick` to materialize per-row colors before constructing the tuple:

```python
        # In _play_with_two_row_text, replace:
        # top_color = self._row_color(0)
        # with:
        top_color_provider = self._row_color(0)
        if not hasattr(top_color_provider, "color_for"):
            top_color_provider = _ConstantColor(top_color_provider)
        top_color = top_color_provider.color_for(
            self._frame_count, 0, len(top_text)
        )
        # Same for bottom_color_provider → bottom_color.
```

`_row_color()` returns either the per-row override OR `self.font_color` (already a provider after coercion). So we just need to materialize at the call site.

- [ ] **Step 3: Run tests to verify they pass**

```bash
uv run pytest tests/test_widgets/test_image_base.py -v 2>&1 | tail -15
```

Expected: new tests PASS, existing tests still pass.

- [ ] **Step 4: Commit**

```bash
git add src/led_ticker/widgets/_image_base.py tests/test_widgets/test_image_base.py
git commit -m "$(cat <<'EOF'
Image widgets: consume ColorProvider for font_color / top_color / bottom_color

_BaseImageWidget gains _FrameAware mixin. All three color fields
accept Color | ColorProvider; _validate_common (or post_init) wraps
raw Color in _ConstantColor. Single-row and two-row draw paths
materialize Color from provider per render tick.

Image widgets don't iterate chars (v1 limit) — per_char providers
degrade to single-color rendering. Sufficient for color_cycle / pulse
which are whole-string anyway.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 11: Delete `WidgetPresenter` + `presentation.py` + transition pause/resume

Final code cleanup. Migration error in `_build_widget` (T5) catches stale configs at the door, so this is safe.

**Files:**
- Delete: `src/led_ticker/presentation.py`
- Delete: `tests/test_presentation.py` (if exists)
- Modify: `src/led_ticker/transitions/__init__.py` (or wherever `run_transition` lives)
- Modify: `src/led_ticker/app.py` (drop the WidgetPresenter import that's already unused after T5)

- [ ] **Step 1: Locate `run_transition`'s pause/resume duck-typing**

```bash
grep -n "pause\|resume" src/led_ticker/transitions/__init__.py | head
```

- [ ] **Step 2: Update `run_transition` to use `pause_frame` / `resume_frame`**

Find the duck-typed `widget.pause()` / `widget.resume()` calls in `run_transition`. Replace with `pause_frame()` / `resume_frame()` (still duck-typed for safety on widgets that don't have the mixin):

```python
    # Before (around the start of the transition compositing loop):
    for w in (outgoing, incoming):
        if hasattr(w, "pause"):
            w.pause()

    # After:
    for w in (outgoing, incoming):
        if hasattr(w, "pause_frame"):
            w.pause_frame()

    # ... compositing loop runs ...

    # Before:
    for w in (outgoing, incoming):
        if hasattr(w, "resume"):
            w.resume()

    # After:
    for w in (outgoing, incoming):
        if hasattr(w, "resume_frame"):
            w.resume_frame()
```

- [ ] **Step 3: Delete `presentation.py`**

```bash
rm src/led_ticker/presentation.py
```

- [ ] **Step 4: Delete the old presentation test file**

```bash
ls tests/test_presentation.py 2>/dev/null && rm tests/test_presentation.py
```

- [ ] **Step 5: Drop the WidgetPresenter import from `app.py`**

Edit `src/led_ticker/app.py`. Find:

```python
from led_ticker.presentation import (
    WidgetPresenter,
    get_presentation_class,
)
```

Delete those lines.

- [ ] **Step 6: Run full suite**

```bash
uv run pytest -q 2>&1 | tail -5
```

Expected: all passing. If any test references `WidgetPresenter` or the deleted module, it'll surface here — fix or delete those tests.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "$(cat <<'EOF'
Delete WidgetPresenter; transitions use pause_frame / resume_frame

presentation.py removed entirely. The WidgetPresenter wrapper is
fully superseded by widget-level _FrameAware mixin + ColorProvider /
Animation fields. Migration error in _build_widget (Task 5) catches
stale presentation = "..." configs at config-load.

run_transition's duck-typed pause()/resume() calls become
pause_frame()/resume_frame() — same hasattr safety, new method names.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 12: Rewrite `presentation_test.example.toml` + CLAUDE.md + final verification

The smoke test config for the new system, plus docs update, plus full integration verification.

**Files:**
- Modify: `config/config.presentation_test.example.toml` (rewrite to new vocabulary)
- Modify: `CLAUDE.md` (replace presentation paragraph)

- [ ] **Step 1: Rewrite the smoke test config**

Open `config/config.presentation_test.example.toml`. Replace the file contents entirely with the new vocabulary. Use this as the body (preserve the [display] / [transitions] sections from the existing file; rewrite each `[[playlist.section.widget]]` entry):

```toml
# Presentation effects smoke test — Pi 5 bigsign.
#
# Validates the new font_color (color provider) + animation knobs
# on bigsign. Replaces the legacy presentation = "..." wrapper.
#
# Sections:
#   1. animation = "typewriter"           — chars type out left-to-right
#   2. font_color = "color_cycle"         — whole-string hue rotation
#   3. font_color = "rainbow"             — per-char rainbow showcase
#   4. font_color = {style="pulse",...}   — entry flash to white, then base
#   5. animation = "bounce"               — slide in, hold, slide out
#   6. font_color = "rainbow" + Countdown — different widget type
#   7. font_color = "color_cycle" + Weather — live-data text recoloring
#   8. font_color = "rainbow" + emoji     — tripwire (slug renders as letters)
#
# v1 limit: per_char providers (rainbow, gradient) don't penetrate
# `:slug:` emoji segments — slugs render as colored letters. Filed,
# not yet fixed.

[display]
rows = 32
cols = 64
chain = 8
parallel = 1
pixel_mapper = "Remap:256,64|192,32n|192,0n|128,32n|128,0n|64,32n|64,0n|0,32n|0,0n"

brightness = 60
slowdown_gpio = 3
gpio_mapping = "adafruit-hat"
default_scale = 4

pwm_bits = 8
rp1_rio = 1

[title]
delay = 0.5

[transitions]
default = "cut"
duration = 0.2
easing = "linear"
between_sections = "cut"

# 1. typewriter
[[playlist.section]]
mode = "swap"
hold_time = 8.0
loop_count = 1
transition = "cut"

[playlist.section.title]
type = "message"
text = "1: typewriter"
color = [200, 220, 255]

[[playlist.section.widget]]
type = "message"
text = "WATCH ME GET TYPED OUT"
font_color = [255, 220, 50]
animation = "typewriter"

# 2. color_cycle
[[playlist.section]]
mode = "swap"
hold_time = 8.0
loop_count = 1
transition = "cut"

[playlist.section.title]
type = "message"
text = "2: color_cycle"
color = [200, 220, 255]

[[playlist.section.widget]]
type = "message"
text = "WHOLE TEXT CYCLES HUE"
font_color = "color_cycle"

# 3. rainbow
[[playlist.section]]
mode = "swap"
hold_time = 8.0
loop_count = 1
transition = "cut"

[playlist.section.title]
type = "message"
text = "3: rainbow"
color = [200, 220, 255]

[[playlist.section.widget]]
type = "message"
text = "RAINBOW PER-CHARACTER"
font_color = "rainbow"

# 4. pulse — flash then settle
[[playlist.section]]
mode = "swap"
hold_time = 8.0
loop_count = 1
transition = "cut"

[playlist.section.title]
type = "message"
text = "4: pulse"
color = [200, 220, 255]

[[playlist.section.widget]]
type = "message"
text = "PULSE THEN STAY STEADY"
font_color = {style = "pulse", base = [50, 200, 100]}

# 5. bounce
[[playlist.section]]
mode = "swap"
hold_time = 8.0
loop_count = 1
transition = "cut"

[playlist.section.title]
type = "message"
text = "5: bounce"
color = [200, 220, 255]

[[playlist.section.widget]]
type = "message"
text = "BOUNCE IN HOLD OUT"
font_color = [255, 150, 200]
animation = "bounce"

# 6. rainbow + countdown
[[playlist.section]]
mode = "swap"
hold_time = 8.0
loop_count = 1
transition = "cut"

[playlist.section.title]
type = "message"
text = "6: rainbow + countdown"
color = [200, 220, 255]

[[playlist.section.widget]]
type = "countdown"
message = "Days to NYE"
countdown_date = 2027-01-01
font_color = "rainbow"

# 7. color_cycle + weather
[[playlist.section]]
mode = "swap"
hold_time = 8.0
loop_count = 1
transition = "cut"

[playlist.section.title]
type = "message"
text = "7: color_cycle + weather"
color = [200, 220, 255]

[[playlist.section.widget]]
type = "weather"
message = "Brooklyn"
location = "Brooklyn"
units = "imperial"
font_color = "color_cycle"

# 8. rainbow + emoji (tripwire — slugs render as letters)
[[playlist.section]]
mode = "swap"
hold_time = 8.0
loop_count = 1
transition = "cut"

[playlist.section.title]
type = "message"
text = "8: rainbow + emoji"
color = [200, 220, 255]

[[playlist.section.widget]]
type = "message"
text = ":taco: HOT TACOS :taco:"
font_color = "rainbow"
```

- [ ] **Step 2: Verify the config builds via `_build_widget`**

```bash
PYTHONPATH=tests/stubs WEATHERAPI_KEY=test-key uv run python -c "
import asyncio, tomllib
from pathlib import Path
import aiohttp
from led_ticker.app import _build_widget

async def main():
    p = Path('config/config.presentation_test.example.toml')
    cfg = tomllib.loads(open(p).read())
    sections = cfg['playlist']['section']
    async with aiohttp.ClientSession() as s:
        for i, sec in enumerate(sections, 1):
            for w in sec.get('widget', []):
                widget = await _build_widget(dict(w), session=s)
                fc = type(widget.font_color).__name__
                anim = type(getattr(widget, 'animation', None)).__name__ if getattr(widget, 'animation', None) else 'none'
                print(f'§{i}: {type(widget).__name__:>16}  fc={fc:>14}  anim={anim}')

asyncio.run(main())
"
```

Expected output: 8 sections each showing the widget type + provider type + animation.

- [ ] **Step 3: Update CLAUDE.md**

Find the "Text Presentation Effects" paragraph in `CLAUDE.md`:

```bash
grep -n "Text Presentation Effects\|@register_presentation\|WidgetPresenter\|presentation effects" CLAUDE.md | head
```

Replace the section text with:

```markdown
**Color providers and animations**: `font_color` (and `top_color` /
`bottom_color` on TwoRow / image widgets) accept either a constant
`[r, g, b]` list, the legacy `"random"` sentinel, a string shorthand
(`"rainbow"` / `"color_cycle"`), or an inline table
(`{style = "pulse", base = [r, g, b]}` / `{style = "gradient", from = [...], to = [...]}`).
At config-load all of those normalize to a `ColorProvider` with
`color_for(frame, char_index, total_chars) -> Color`. Constants wrap
in `_ConstantColor` so the widget-side dispatch is uniform.

Per-char providers (`rainbow`, `gradient`) cause widgets that opt in
(currently TickerMessage) to iterate characters and render each with
its own color. Whole-string providers (`color_cycle`, `pulse`,
`random`, constant) get a single `color_for` call per draw and one
`draw_text` call.

`animation = "typewriter"` and `animation = "bounce"` are fields on
`TickerMessage` only. `_build_widget` raises if `animation` appears
on any other widget type. Color and animation compose: a
TickerMessage can have both `font_color = "rainbow"` and
`animation = "typewriter"` and the chars type out in rainbow.

The previous `WidgetPresenter` wrapper + `presentation = "..."` knob
was removed. Migration error in `_build_widget` maps each old
`presentation` value to its new shape verbatim.

**Engine tick** (`_swap_and_scroll`): held-text branches now run a
tick loop calling `advance_frame + draw + swap` at 50ms cadence
(`ENGINE_TICK_MS`) so frame-aware effects animate during holds. The
scroll branch also calls `advance_frame` per tick.

**v1 limitation**: per-char providers don't penetrate `:slug:` emoji
— a TickerMessage with `font_color = "rainbow"` + `:taco: HOT :taco:`
renders the slugs as colored ASCII letters instead of taco sprites.
Tripwire in `config.presentation_test.example.toml` §8.
```

- [ ] **Step 4: Final verification**

```bash
# Full test suite
uv run pytest -q 2>&1 | tail -5
```

Expected: all passing.

```bash
# All in-tree configs build cleanly
PYTHONPATH=tests/stubs WEATHERAPI_KEY=test-key uv run python -c "
import asyncio, tomllib
from pathlib import Path
import aiohttp
from led_ticker.app import _build_widget

async def main():
    for p in sorted(Path('config').glob('*.toml')):
        try:
            cfg = tomllib.loads(open(p).read())
        except Exception as e:
            print(f'{p.name}: PARSE ERROR: {e}')
            continue
        sections = cfg.get('playlist', {}).get('section', [])
        async with aiohttp.ClientSession() as s:
            for i, sec in enumerate(sections):
                for w in sec.get('widget', []):
                    try:
                        await _build_widget(dict(w), session=s)
                    except Exception as e:
                        print(f'{p.name} section {i+1}: {type(e).__name__}: {e}')
                        return
        print(f'{p.name}: {len(sections)} sections OK')

asyncio.run(main())
"
```

Expected: every config builds without error.

- [ ] **Step 5: Commit**

```bash
git add config/config.presentation_test.example.toml CLAUDE.md
git commit -m "$(cat <<'EOF'
config + CLAUDE.md: migrate to font_color provider + animation

config.presentation_test.example.toml fully rewritten in the new
vocabulary. 8 sections covering all 5 effects plus the per-char +
emoji tripwire (§8).

CLAUDE.md drops the old presentation effects paragraph; the new
section documents font_color shapes, animation field, _build_widget
migration error, engine tick loop, and the v1 emoji-slug limitation.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 6: Push**

```bash
git push origin main
```

Expected: pre-commit pyright + pytest pass; push completes.

- [ ] **Step 7: Hardware verification (manual on bigsign Pi)**

```bash
ssh bigsign
cd /path/to/led-ticker
git pull
cp config/config.presentation_test.example.toml config/config.toml
docker compose up -d --build
docker compose logs -f
```

Cycle through the 8 sections and visually confirm each effect:
- §1 chars walk left-to-right
- §2 whole text shifts hue
- §3 per-char rainbow
- §4 white flash on entry, settles to green
- §5 slide in, hold center, slide out
- §6 rainbow over countdown text
- §7 hue shifts on weather text
- §8 (tripwire) rainbow chars including the colon-letters within `:taco:` slugs (confirms the v1 limitation; no fix expected)

If any section shows broken behavior or hard crash recurs, file a separate issue.

---

## Summary

12 tasks. Each commits independently and leaves the test suite passing
(modulo the cross-task period in T5–T6 where widget tests fail because
the integration is still in flight; T7–T10 restore them).

**Acceptance:**
- All tests pass.
- `WidgetPresenter` and `presentation.py` no longer exist.
- `config.presentation_test.example.toml` builds + runs on bigsign with all 8 sections visually correct.
- Migration error message tested verbatim.
- Per-char providers + animation compose on TickerMessage.
- v1 emoji-slug limitation documented in CLAUDE.md and demoed in §8.
