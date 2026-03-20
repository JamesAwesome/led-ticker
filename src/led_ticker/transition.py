"""Transition effects between widgets."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)

# --- Easing functions ---


def linear(p: float) -> float:
    return p


def ease_out(p: float) -> float:
    return 1 - (1 - p) ** 2


def ease_in_out(p: float) -> float:
    return 3 * p * p - 2 * p * p * p


EASING = {
    "linear": linear,
    "ease_out": ease_out,
    "ease_in_out": ease_in_out,
}


# --- Transition protocol and registry ---


@runtime_checkable
class Transition(Protocol):
    def frame_at(
        self,
        t: float,
        canvas: Any,
        outgoing: Any,
        incoming: Any,
    ) -> Any:
        """Render one frame at progress t (0.0 to 1.0)."""
        ...


_TRANSITION_REGISTRY: dict[str, type] = {}


def register_transition(name: str):
    def decorator(cls):
        _TRANSITION_REGISTRY[name] = cls
        return cls

    return decorator


def get_transition_class(name: str) -> type:
    if name not in _TRANSITION_REGISTRY:
        raise ValueError(
            f"Unknown transition: {name!r}. "
            f"Available: {list(_TRANSITION_REGISTRY.keys())}"
        )
    return _TRANSITION_REGISTRY[name]


# --- Transition runner ---


async def run_transition(
    canvas,
    frame,
    outgoing,
    incoming,
    transition: Transition,
    duration: float = 0.5,
    easing: str = "linear",
    scroll_speed: float = 0.05,
):
    """Run a transition between two widgets over ``duration`` seconds.

    The loop runs from t=0.0 to t=1.0 inclusive. At t=1.0 every
    built-in transition draws only the incoming widget at cursor_pos=0,
    so no separate "final frame" is needed.
    """
    ease_fn = EASING.get(easing, linear)
    frame_count = max(1, int(duration / scroll_speed))

    for i in range(frame_count + 1):
        t = ease_fn(i / max(1, frame_count))
        canvas.Clear()
        transition.frame_at(t, canvas, outgoing, incoming)
        frame.matrix.SwapOnVSync(canvas)
        await asyncio.sleep(scroll_speed)


# --- Compositing helper ---


def _render_to_shadow(widget, width, height):
    """Try to render a widget to a ShadowCanvas.

    Returns the ShadowCanvas on success, or None if the widget's
    draw() calls real rgbmatrix DrawText (which rejects ShadowCanvas).
    """
    from led_ticker.shadow_canvas import ShadowCanvas

    buf = ShadowCanvas(width, height)
    try:
        widget.draw(buf, cursor_pos=0)
        return buf
    except TypeError:
        return None


# --- Built-in transitions ---


@register_transition("cut")
class Cut:
    """Instant switch, no animation."""

    def frame_at(self, t, canvas, outgoing, incoming):
        incoming.draw(canvas, cursor_pos=0)
        return canvas


@register_transition("push_left")
class PushLeft:
    """Old content pushes off left, new enters from right."""

    def frame_at(self, t, canvas, outgoing, incoming):
        offset = int(t * canvas.width)
        outgoing.draw(canvas, cursor_pos=-offset)
        incoming.draw(canvas, cursor_pos=canvas.width - offset)
        return canvas


@register_transition("push_right")
class PushRight:
    """Old content pushes off right, new enters from left."""

    def frame_at(self, t, canvas, outgoing, incoming):
        offset = int(t * canvas.width)
        outgoing.draw(canvas, cursor_pos=offset)
        incoming.draw(canvas, cursor_pos=-canvas.width + offset)
        return canvas


@register_transition("push_up")
class PushUp:
    """Old content pushes up, new enters from bottom."""

    def frame_at(self, t, canvas, outgoing, incoming):
        # Widgets hardcode y=12 in DrawText, so vertical push
        # falls back to a timed cut at the midpoint
        if t < 0.5:
            outgoing.draw(canvas, cursor_pos=0)
        else:
            incoming.draw(canvas, cursor_pos=0)
        return canvas


@register_transition("color_flash")
class ColorFlash:
    """Brief solid color flash between old and new content."""

    def __init__(self, flash_color=(255, 255, 255)):
        self.flash_color = flash_color

    def frame_at(self, t, canvas, outgoing, incoming):
        if t < 0.33:
            outgoing.draw(canvas, cursor_pos=0)
        elif t < 0.66:
            canvas.Fill(*self.flash_color)
        else:
            incoming.draw(canvas, cursor_pos=0)
        return canvas


def _composite_regions(canvas, outgoing, incoming, region_fn, w, h):
    """Composite two widgets using pixel-level ShadowCanvas rendering.

    ``region_fn(x, y)`` returns True for pixels from incoming, False
    for pixels from outgoing. Falls back to push-based rendering if
    ShadowCanvas is rejected by the real rgbmatrix DrawText.
    """
    old_buf = _render_to_shadow(outgoing, w, h)
    new_buf = _render_to_shadow(incoming, w, h)

    if old_buf is None or new_buf is None:
        # Real hardware — can't use ShadowCanvas with DrawText.
        # Fall back: draw outgoing, then incoming on top.
        outgoing.draw(canvas, cursor_pos=0)
        incoming.draw(canvas, cursor_pos=0)
        return

    for y in range(h):
        for x in range(w):
            if region_fn(x, y):
                r, g, b = new_buf.get_pixel(x, y)
            else:
                r, g, b = old_buf.get_pixel(x, y)
            if r or g or b:
                canvas.SetPixel(x, y, r, g, b)


@register_transition("wipe_left")
class WipeLeft:
    """New content revealed left-to-right with a hard edge."""

    def frame_at(self, t, canvas, outgoing, incoming):
        w = canvas.width
        h = getattr(canvas, "height", 16)
        boundary = int(t * w)

        if boundary <= 0:
            outgoing.draw(canvas, cursor_pos=0)
        elif boundary >= w:
            incoming.draw(canvas, cursor_pos=0)
        else:
            _composite_regions(
                canvas,
                outgoing,
                incoming,
                lambda x, y: x < boundary,
                w,
                h,
            )
        return canvas


@register_transition("wipe_right")
class WipeRight:
    """New content revealed right-to-left with a hard edge."""

    def frame_at(self, t, canvas, outgoing, incoming):
        w = canvas.width
        h = getattr(canvas, "height", 16)
        boundary = int(t * w)

        if boundary <= 0:
            outgoing.draw(canvas, cursor_pos=0)
        elif boundary >= w:
            incoming.draw(canvas, cursor_pos=0)
        else:
            _composite_regions(
                canvas,
                outgoing,
                incoming,
                lambda x, y: x >= w - boundary,
                w,
                h,
            )
        return canvas


@register_transition("dissolve")
class Dissolve:
    """Random pixel dissolve from old to new content."""

    def __init__(self, seed: int = 42):
        self.seed = seed

    def frame_at(self, t, canvas, outgoing, incoming):
        old_buf = _render_to_shadow(
            outgoing,
            canvas.width,
            getattr(canvas, "height", 16),
        )
        if old_buf is None:
            # Fallback: timed cut
            if t < 0.5:
                outgoing.draw(canvas, cursor_pos=0)
            else:
                incoming.draw(canvas, cursor_pos=0)
            return canvas

        from led_ticker.shadow_canvas import composite_dissolve

        w, h = canvas.width, getattr(canvas, "height", 16)
        new_buf = _render_to_shadow(incoming, w, h)
        if new_buf is None:
            if t < 0.5:
                outgoing.draw(canvas, cursor_pos=0)
            else:
                incoming.draw(canvas, cursor_pos=0)
            return canvas

        composite_dissolve(old_buf, new_buf, t, canvas, self.seed)
        return canvas


@register_transition("split")
class SplitHorizontal:
    """Old content splits apart from center, new underneath."""

    def frame_at(self, t, canvas, outgoing, incoming):
        w = canvas.width
        h = getattr(canvas, "height", 16)
        half = w // 2
        reveal = int(t * half)

        if reveal <= 0:
            outgoing.draw(canvas, cursor_pos=0)
        elif t >= 1.0:
            incoming.draw(canvas, cursor_pos=0)
        else:
            left = half - reveal
            right = half + reveal
            _composite_regions(
                canvas,
                outgoing,
                incoming,
                lambda x, y: left <= x < right,
                w,
                h,
            )
        return canvas


@register_transition("curtain")
class Curtain:
    """Old content slides apart like curtains opening."""

    def frame_at(self, t, canvas, outgoing, incoming):
        w = canvas.width
        h = getattr(canvas, "height", 16)
        half = w // 2
        offset = int(t * half)

        if offset <= 0:
            outgoing.draw(canvas, cursor_pos=0)
        elif t >= 1.0:
            incoming.draw(canvas, cursor_pos=0)
        else:
            left = half - offset
            right = half + offset
            _composite_regions(
                canvas,
                outgoing,
                incoming,
                lambda x, y: left <= x < right,
                w,
                h,
            )
        return canvas


@register_transition("nyancat")
class NyanCat:
    """Nyan Cat flies across trailing a rainbow."""

    def frame_at(self, t, canvas, outgoing, incoming):
        from led_ticker.widgets.nyancat import (
            SPRITE_WIDTH,
            draw_nyan_frame,
        )

        width = canvas.width
        height = getattr(canvas, "height", 16)
        total_travel = width + SPRITE_WIDTH
        cat_x = int(-SPRITE_WIDTH + t * total_travel)
        trail_end = cat_x

        if trail_end >= width:
            incoming.draw(canvas, cursor_pos=0)
        elif trail_end <= 0:
            outgoing.draw(canvas, cursor_pos=0)
        else:
            _composite_regions(
                canvas,
                outgoing,
                incoming,
                lambda x, y: x < trail_end,
                width,
                height,
            )
            draw_nyan_frame(canvas, t, width=width, height=height)

        return canvas
