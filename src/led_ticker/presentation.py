"""Text presentation effects for widgets."""

from __future__ import annotations

import colorsys
from collections.abc import Callable
from typing import Any

from led_ticker._compat import require_graphics
from led_ticker._types import Canvas, Color, DrawResult
from led_ticker.drawing import get_text_width
from led_ticker.text_render import draw_text
from led_ticker.transitions import ease_out

# --- Presentation registry ---

_PRESENTATION_REGISTRY: dict[str, type] = {}


def register_presentation(name: str) -> Callable[[type], type]:
    def decorator(cls: type) -> type:
        _PRESENTATION_REGISTRY[name] = cls
        return cls

    return decorator


def get_presentation_class(name: str) -> type:
    if name not in _PRESENTATION_REGISTRY:
        raise ValueError(
            f"Unknown presentation: {name!r}. "
            f"Available: {list(_PRESENTATION_REGISTRY.keys())}"
        )
    return _PRESENTATION_REGISTRY[name]


class WidgetPresenter:
    """Wraps a Widget and adds frame-aware presentation effects.

    Satisfies the Widget protocol so the rest of the system is unaware.
    """

    def __init__(self, widget: Any, mode: Any) -> None:
        self.widget: Any = widget
        self.mode: Any = mode
        self.frame_count: int = 0
        self._paused: bool = False

    def pause(self) -> None:
        """Freeze frame_count so transition compositing doesn't advance the
        presentation. Without this, an outgoing widget mid-typewriter (or
        Bounce/Rainbow/ColorCycle) keeps ticking while it's only being
        re-rendered for a dissolve, then re-enters the next section at a
        wrong phase.
        """
        self._paused = True

    def resume(self) -> None:
        self._paused = False

    @property
    def bg_color(self) -> Color | None:
        """Forward bg_color from the wrapped widget so the orchestrator
        sees the correct background regardless of presentation wrapping."""
        return getattr(self.widget, "bg_color", None)

    def draw(self, canvas: Canvas, cursor_pos: int = 0, **kwargs: Any) -> DrawResult:
        result = self.mode.draw(
            self.widget,
            canvas,
            cursor_pos,
            self.frame_count,
            **kwargs,
        )
        if not self._paused:
            self.frame_count += 1
        return result


# --- Built-in presentation modes ---


@register_presentation("typewriter")
class Typewriter:
    """Characters appear one at a time, left to right."""

    def __init__(self, chars_per_frame: int = 1) -> None:
        self.chars_per_frame: int = chars_per_frame

    def draw(
        self, widget: Any, canvas: Canvas, cursor_pos: int, frame: int, **kwargs: Any
    ) -> DrawResult:
        if not hasattr(widget, "message") or not isinstance(widget.message, str):
            return widget.draw(canvas, cursor_pos, **kwargs)

        full_text = widget.message
        chars_visible = min(
            len(full_text),
            (frame + 1) * self.chars_per_frame,
        )
        visible_text = full_text[:chars_visible]

        font_color = kwargs.get("font_color") or widget.font_color
        y_offset: int = kwargs.get("y_offset", 0)

        from led_ticker.drawing import compute_cursor

        # `get_text_width` memoizes results module-wide on
        # `(id(font), text, padding, scale)`, so per-presentation
        # caching is redundant — call directly.
        content_width = get_text_width(widget.font, full_text, padding=0, canvas=canvas)
        pos, end_padding = compute_cursor(
            canvas.width,
            content_width,
            cursor_pos,
            widget.padding,
            widget.center,
        )

        pos += draw_text(
            canvas,
            widget.font,
            pos,
            12 + y_offset,
            font_color,
            visible_text,
        )
        pos += end_padding

        return canvas, pos


@register_presentation("color_cycle")
class ColorCycle:
    """Text color cycles through the rainbow."""

    def __init__(self, speed: int = 5) -> None:
        self.speed: int = speed  # degrees of hue per frame

    def draw(
        self, widget: Any, canvas: Canvas, cursor_pos: int, frame: int, **kwargs: Any
    ) -> DrawResult:
        graphics = require_graphics()

        hue = (frame * self.speed) % 360
        r, g, b = colorsys.hsv_to_rgb(hue / 360, 1.0, 1.0)
        color = graphics.Color(int(r * 255), int(g * 255), int(b * 255))

        return widget.draw(canvas, cursor_pos, font_color=color, **kwargs)


@register_presentation("rainbow")
class Rainbow:
    """Per-character rainbow sweep across text."""

    def __init__(self, speed: int = 8, char_offset: int = 30) -> None:
        self.speed: int = speed
        self.char_offset: int = char_offset

    def draw(
        self, widget: Any, canvas: Canvas, cursor_pos: int, frame: int, **kwargs: Any
    ) -> DrawResult:
        if not hasattr(widget, "message") or not isinstance(widget.message, str):
            return widget.draw(canvas, cursor_pos, **kwargs)

        graphics = require_graphics()
        y_offset: int = kwargs.get("y_offset", 0)

        from led_ticker.drawing import compute_cursor

        full_text = widget.message
        # `get_text_width` is module-memoized on
        # `(id(font), text, padding, scale)` — per-instance caching
        # would be redundant.
        content_width = get_text_width(widget.font, full_text, padding=0, canvas=canvas)
        pos, end_padding = compute_cursor(
            canvas.width,
            content_width,
            cursor_pos,
            widget.padding,
            widget.center,
        )

        phase = frame * self.speed
        char_offset = self.char_offset  # hoist for inner loop
        for i, char in enumerate(full_text):
            hue = ((phase + i * char_offset) % 360) / 360
            r, g, b = colorsys.hsv_to_rgb(hue, 1.0, 1.0)
            color = graphics.Color(
                int(r * 255),
                int(g * 255),
                int(b * 255),
            )
            pos += draw_text(
                canvas,
                widget.font,
                pos,
                12 + y_offset,
                color,
                char,
            )

        pos += end_padding
        return canvas, pos


@register_presentation("pulse")
class Pulse:
    """Text briefly brightens to white then returns to base color."""

    def __init__(self, duration_frames: int = 6) -> None:
        self.duration_frames: int = duration_frames

    def draw(
        self, widget: Any, canvas: Canvas, cursor_pos: int, frame: int, **kwargs: Any
    ) -> DrawResult:
        if frame >= self.duration_frames:
            return widget.draw(canvas, cursor_pos, **kwargs)

        graphics = require_graphics()

        p = frame / max(1, self.duration_frames - 1)
        intensity = p / 0.2 if p < 0.2 else 1 - (p - 0.2) / 0.8

        font_color = widget.font_color
        # font_color may be a ColorProvider (_ConstantColor, Rainbow, etc.)
        # or a raw Color. Materialize to a concrete Color before blending.
        if hasattr(font_color, "color_for"):
            base = font_color.color_for(frame, 0, 1)
        else:
            base = font_color
        r = int(base.red + (255 - base.red) * intensity)
        g = int(base.green + (255 - base.green) * intensity)
        b = int(base.blue + (255 - base.blue) * intensity)
        color = graphics.Color(r, g, b)

        return widget.draw(canvas, cursor_pos, font_color=color, **kwargs)


@register_presentation("bounce")
class Bounce:
    """Text scrolls in from right, pauses at center, scrolls off left."""

    def __init__(self, hold_frames: int = 40, scroll_frames: int = 20) -> None:
        self.hold_frames: int = hold_frames
        self.scroll_frames: int = scroll_frames

    @property
    def total_frames(self) -> int:
        return self.scroll_frames + self.hold_frames + self.scroll_frames

    def draw(
        self, widget: Any, canvas: Canvas, cursor_pos: int, frame: int, **kwargs: Any
    ) -> DrawResult:
        width = canvas.width
        text_width = 0
        if hasattr(widget, "message") and isinstance(widget.message, str):
            text_width = get_text_width(
                widget.font,
                widget.message,
                padding=0,
                canvas=canvas,
            )
        center_x = max(0, (width - text_width) // 2)
        sf = self.scroll_frames
        hf = self.hold_frames

        if frame < sf:
            # Scroll in from right with ease-out
            p = ease_out(frame / max(1, sf - 1))
            pos = int(width + (center_x - width) * p)
        elif frame < sf + hf:
            # Hold at center
            pos = center_x
        elif frame < self.total_frames:
            # Scroll out to left with ease-in
            p = (frame - sf - hf) / max(1, sf - 1)
            eased = p * p
            pos = int(center_x + (-text_width - center_x) * eased)
        else:
            pos = center_x

        return widget.draw(canvas, cursor_pos=pos, **kwargs)
