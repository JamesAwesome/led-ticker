"""Text presentation effects for widgets."""

from __future__ import annotations

import colorsys

from led_ticker._compat import require_graphics
from led_ticker.drawing import get_text_width
from led_ticker.transition import ease_out

# --- Presentation registry ---

_PRESENTATION_REGISTRY: dict[str, type] = {}


def register_presentation(name: str):
    def decorator(cls):
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

    def __init__(self, widget, mode):
        self.widget = widget
        self.mode = mode
        self.frame_count = 0

    def draw(self, canvas, cursor_pos=0, **kwargs):
        result = self.mode.draw(
            self.widget,
            canvas,
            cursor_pos,
            self.frame_count,
            **kwargs,
        )
        self.frame_count += 1
        return result


# --- Built-in presentation modes ---


@register_presentation("typewriter")
class Typewriter:
    """Characters appear one at a time, left to right."""

    def __init__(self, chars_per_frame=1):
        self.chars_per_frame = chars_per_frame

    def draw(self, widget, canvas, cursor_pos, frame, **kwargs):
        if not hasattr(widget, "message") or not isinstance(widget.message, str):
            return widget.draw(canvas, cursor_pos, **kwargs)

        graphics = require_graphics()
        full_text = widget.message
        chars_visible = min(
            len(full_text),
            (frame + 1) * self.chars_per_frame,
        )
        visible_text = full_text[:chars_visible]

        font_color = kwargs.get("font_color") or widget.font_color

        from led_ticker.drawing import compute_cursor

        content_width = get_text_width(widget.font, full_text, padding=0)
        pos, end_padding = compute_cursor(
            canvas.width,
            content_width,
            cursor_pos,
            widget.padding,
            widget.center,
        )

        pos += graphics.DrawText(
            canvas,
            widget.font,
            pos,
            12,
            font_color,
            visible_text,
        )
        pos += end_padding

        return canvas, pos


@register_presentation("color_cycle")
class ColorCycle:
    """Text color cycles through the rainbow."""

    def __init__(self, speed=5):
        self.speed = speed  # degrees of hue per frame

    def draw(self, widget, canvas, cursor_pos, frame, **kwargs):
        graphics = require_graphics()

        hue = (frame * self.speed) % 360
        r, g, b = colorsys.hsv_to_rgb(hue / 360, 1.0, 1.0)
        color = graphics.Color(int(r * 255), int(g * 255), int(b * 255))

        return widget.draw(canvas, cursor_pos, font_color=color, **kwargs)


@register_presentation("rainbow")
class Rainbow:
    """Per-character rainbow sweep across text."""

    def __init__(self, speed=8, char_offset=30):
        self.speed = speed
        self.char_offset = char_offset

    def draw(self, widget, canvas, cursor_pos, frame, **kwargs):
        if not hasattr(widget, "message") or not isinstance(widget.message, str):
            return widget.draw(canvas, cursor_pos, **kwargs)

        graphics = require_graphics()

        from led_ticker.drawing import compute_cursor

        full_text = widget.message
        content_width = get_text_width(widget.font, full_text, padding=0)
        pos, end_padding = compute_cursor(
            canvas.width,
            content_width,
            cursor_pos,
            widget.padding,
            widget.center,
        )

        phase = frame * self.speed
        for i, char in enumerate(full_text):
            hue = ((phase + i * self.char_offset) % 360) / 360
            r, g, b = colorsys.hsv_to_rgb(hue, 1.0, 1.0)
            color = graphics.Color(
                int(r * 255),
                int(g * 255),
                int(b * 255),
            )
            pos += graphics.DrawText(
                canvas,
                widget.font,
                pos,
                12,
                color,
                char,
            )

        pos += end_padding
        return canvas, pos


@register_presentation("pulse")
class Pulse:
    """Text briefly brightens to white then returns to base color."""

    def __init__(self, duration_frames=6):
        self.duration_frames = duration_frames

    def draw(self, widget, canvas, cursor_pos, frame, **kwargs):
        if frame >= self.duration_frames:
            return widget.draw(canvas, cursor_pos, **kwargs)

        graphics = require_graphics()

        p = frame / max(1, self.duration_frames - 1)
        intensity = p / 0.2 if p < 0.2 else 1 - (p - 0.2) / 0.8

        base = widget.font_color
        r = int(base.red + (255 - base.red) * intensity)
        g = int(base.green + (255 - base.green) * intensity)
        b = int(base.blue + (255 - base.blue) * intensity)
        color = graphics.Color(r, g, b)

        return widget.draw(canvas, cursor_pos, font_color=color, **kwargs)


@register_presentation("bounce")
class Bounce:
    """Text scrolls in from right, pauses at center, scrolls off left."""

    def __init__(self, hold_frames=40, scroll_frames=20):
        self.hold_frames = hold_frames
        self.scroll_frames = scroll_frames

    @property
    def total_frames(self):
        return self.scroll_frames + self.hold_frames + self.scroll_frames

    def draw(self, widget, canvas, cursor_pos, frame, **kwargs):
        width = canvas.width
        text_width = 0
        if hasattr(widget, "message") and isinstance(widget.message, str):
            text_width = get_text_width(
                widget.font,
                widget.message,
                padding=0,
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
