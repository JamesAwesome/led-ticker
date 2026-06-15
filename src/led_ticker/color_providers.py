"""Color providers — runtime-derived colors for frame-aware text
rendering.

Replaces the `WidgetPresenter`-wrapped presentation effects (rainbow,
color_cycle, pulse) with widget-level ColorProvider instances bound
to the `font_color` (and `top_color` / `bottom_color`) field. Widgets
ask the provider for a Color via `color_for(frame, char_index, total)`
each tick.

Two flavors:
- `per_char = False` providers (constant, color_cycle, random)
  return one Color per call — widgets do a single `draw_text` for the
  whole string.
- `per_char = True` providers (rainbow, gradient) return a different
  Color per character — widgets iterate chars and draw each separately.

The `_ConstantColor` provider exists so that plain `font_color = [r,g,b]`
configs route through the same interface as effects-based configs.
The widget-side code is uniform: `provider.color_for(...)`.

**`restart_on_visit` convention**: providers that want continuous
phase across `loop_count > 1` iterations of a section set
`restart_on_visit: bool = False` as a class attribute. Read by
`FrameAwareBase.reset_frame` in `widgets/_frame_aware.py`. Default `True` (via
`getattr` fallback) keeps today's "every visit = fresh start"
behavior for unknown provider classes. `Rainbow` and `ColorCycle`
opt out (continuous sweep / cycle); the others keep the default
(frame-invariant or visit-driven re-roll).
"""

import math
import random
from typing import Protocol

from led_ticker._types import Color
from led_ticker.color_lut import hue_color


class ColorProviderBase:
    """Optional base for ColorProvider implementations.

    Enforces that every subclass declares ``frame_invariant`` explicitly
    (as a class attribute or ``@property``) so the fast-path gate in
    ``_play_with_text`` / ``_play_with_two_row_text`` never silently
    freezes an animated widget.

    Lying *True-when-False* makes the widget freeze with no error; lying
    *False-when-True* wastes one per-tick redraw but renders correctly.
    Neither lie is detectable at runtime — the only protection is forcing
    authors to answer the question at class definition time.
    """

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        if "frame_invariant" not in cls.__dict__:
            raise TypeError(
                f"{cls.__name__} must define 'frame_invariant' as a class "
                "attribute or property. Set True if color_for() output is "
                "independent of the frame argument (constant, gradient); "
                "False if it varies per frame (rainbow, color_cycle)."
            )


class ColorProvider(Protocol):
    """Returns a Color given a frame counter and (for per-char
    providers) a character index within the string being drawn.

    `frame_invariant` declares whether `color_for`'s output depends on
    the `frame` argument. True providers (constant, gradient, random)
    let the engine take a paint-once-and-sleep fast path on otherwise-
    static content; False providers (rainbow, color_cycle) force the
    per-tick render loop so animation actually animates."""

    per_char: bool
    frame_invariant: bool

    def color_for(self, frame: int, char_index: int, total_chars: int) -> Color: ...


class _ConstantColor(ColorProviderBase):
    """Wraps a single Color so plain `font_color = [r,g,b]` configs
    route through the same `color_for` interface as effects."""

    per_char: bool = False
    frame_invariant: bool = True

    def __init__(self, color: Color) -> None:
        self._color = color

    def color_for(self, frame: int, char_index: int, total_chars: int) -> Color:
        return self._color


def as_color_provider(color: Color) -> ColorProvider:
    """Wrap a constant ``Color`` as a uniform (non-animated) ``ColorProvider``.

    The public way to get a constant-color provider — e.g. a widget's default
    font color. ``_ConstantColor`` stays private; this is the supported surface.
    """
    return _ConstantColor(color)


class Random(ColorProviderBase):
    """Picks a single random color at construction; returns it for
    every call. Matches the existing `font_color = "random"` sentinel
    semantic — one stable color per widget instance, not a per-frame
    flicker."""

    per_char: bool = False
    frame_invariant: bool = True

    def __init__(self) -> None:
        # Random color: pick a hue uniformly per call (independent of
        # app.py's section-title RANDOM_COLOR cycle).
        self._color = hue_color(random.random() * 360)

    def color_for(self, frame: int, char_index: int, total_chars: int) -> Color:
        return self._color


class Rainbow(ColorProviderBase):
    """Per-character hue offset, advancing per frame.

    `speed` is degrees of hue advanced per frame. `char_offset` is the
    hue gap between consecutive characters. Defaults match the legacy
    Rainbow presentation (speed=8, char_offset=30)."""

    per_char: bool = True
    frame_invariant: bool = False
    restart_on_visit: bool = False  # continuous hue sweep across loop_count boundaries

    def __init__(self, speed: int = 8, char_offset: int = 30) -> None:
        self.speed = speed
        self.char_offset = char_offset

    def color_for(self, frame: int, char_index: int, total_chars: int) -> Color:
        hue_int = (frame * self.speed + char_index * self.char_offset) % 360
        return hue_color(hue_int)


class ColorCycle(ColorProviderBase):
    """Whole-string hue rotation; char_index ignored.

    `speed` is degrees of hue advanced per frame. Default matches the
    legacy ColorCycle (speed=5).

    Optional `from_hue` / `to_hue` (degrees, 0–360) restrict the sweep
    to a hue arc instead of the full wheel. The shorter arc is always
    chosen: e.g. from_hue=0 (red) + to_hue=240 (blue) sweeps the 120°
    arc through magenta rather than the 240° arc through yellow/green.
    Pass as keyword args from the parser after RGB→hue conversion;
    not exposed directly in TOML (users write `from = [r,g,b]`)."""

    per_char: bool = False
    frame_invariant: bool = False
    restart_on_visit: bool = False  # continuous cycle across loop_count boundaries

    def __init__(
        self,
        speed: int = 5,
        from_hue: float | None = None,
        to_hue: float | None = None,
    ) -> None:
        self.speed = speed
        if from_hue is not None and to_hue is not None:
            diff = (to_hue - from_hue) % 360
            if diff > 180:
                diff -= 360  # take the shorter arc (may be negative = backward)
            self._from_hue: float = from_hue
            self._span: float = diff  # signed; 0 means same hue (caught by parser)
        else:
            self._from_hue = 0.0
            self._span = 360.0  # full wheel

    def color_for(self, frame: int, char_index: int, total_chars: int) -> Color:
        span = self._span if self._span != 0 else 360.0
        progress = (frame * self.speed) % abs(span)
        if span < 0:
            hue = (self._from_hue - progress) % 360
        else:
            hue = (self._from_hue + progress) % 360
        return hue_color(hue)


class Gradient(ColorProviderBase):
    """Linear left-to-right gradient between `from_color` and
    `to_color`. char_index drives interpolation; frame is ignored."""

    per_char: bool = True
    frame_invariant: bool = True

    def __init__(self, from_color: Color, to_color: Color) -> None:
        self._from = from_color
        self._to = to_color

    def color_for(self, frame: int, char_index: int, total_chars: int) -> Color:
        from led_ticker._compat import require_graphics

        graphics = require_graphics()
        if total_chars <= 1:
            return self._from
        t = char_index / (total_chars - 1)
        r = int(self._from.red + (self._to.red - self._from.red) * t)
        g = int(self._from.green + (self._to.green - self._from.green) * t)
        b = int(self._from.blue + (self._to.blue - self._from.blue) * t)
        return graphics.Color(r, g, b)


_SHIMMER_FPS = 30.0


class Shimmer(ColorProviderBase):
    """Cosine bright-spot sweep across text characters.

    A `shimmer_color` spot glides left-to-right over the `base_color`
    text, then pauses, then repeats. `speed` (chars/second), `width`
    (chars), and `pause` (seconds) tune the feel.
    """

    per_char: bool = True
    frame_invariant: bool = False
    restart_on_visit: bool = False  # continuous glide across loop_count boundaries

    def __init__(
        self,
        base_color: Color,
        shimmer_color: Color,
        speed: float = 14.0,
        width: float = 8.0,
        pause: float = 0.5,
    ) -> None:
        if speed <= 0:
            raise ValueError(f"Shimmer speed must be > 0; got {speed!r}")
        if width <= 0:
            raise ValueError(f"Shimmer width must be > 0; got {width!r}")
        if pause < 0:
            raise ValueError(f"Shimmer pause must be >= 0; got {pause!r}")
        self._base = base_color
        self._shimmer = shimmer_color
        self.speed = speed
        self.width = width
        self.pause = pause

    def color_for(self, frame: int, char_index: int, total_chars: int) -> Color:
        from led_ticker._compat import require_graphics

        graphics = require_graphics()
        chars = max(total_chars, 1)
        sweep_frames = chars / self.speed * _SHIMMER_FPS
        pause_frames = self.pause * _SHIMMER_FPS
        cycle_frames = sweep_frames + pause_frames

        t = float(frame) % cycle_frames

        if t >= sweep_frames:
            return self._base

        center = t / sweep_frames * chars
        d = abs(char_index - center)
        half_width = self.width / 2.0

        if d >= half_width:
            return self._base

        factor = 0.5 + 0.5 * math.cos(math.pi * d / half_width)
        r = int(self._base.red + (self._shimmer.red - self._base.red) * factor)
        g = int(self._base.green + (self._shimmer.green - self._base.green) * factor)
        b = int(self._base.blue + (self._shimmer.blue - self._base.blue) * factor)
        return graphics.Color(r, g, b)


# Registry of color-provider styles. Built-ins below; plugins add namespaced
# entries via PluginAPI.color_provider(). coercion._provider_from_style looks
# styles up here.
_PROVIDER_REGISTRY: dict[str, type] = {
    "random": Random,
    "rainbow": Rainbow,
    "color_cycle": ColorCycle,
    "gradient": Gradient,
    "shimmer": Shimmer,
}
