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
