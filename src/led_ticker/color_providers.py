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
