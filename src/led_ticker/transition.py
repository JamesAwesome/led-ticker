"""Transition effects between widgets."""

from __future__ import annotations

import asyncio
from typing import Any, Protocol, runtime_checkable

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
    """Run a transition between two widgets over `duration` seconds."""
    ease_fn = EASING.get(easing, linear)
    frame_count = max(1, int(duration / scroll_speed))

    for i in range(frame_count):
        t = ease_fn(i / max(1, frame_count - 1))
        canvas.Clear()
        transition.frame_at(t, canvas, outgoing, incoming)
        frame.matrix.SwapOnVSync(canvas)
        await asyncio.sleep(scroll_speed)

    # Final frame: fully incoming
    canvas.Clear()
    incoming.draw(canvas, cursor_pos=0)
    frame.matrix.SwapOnVSync(canvas)


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


@register_transition("wipe_left")
class WipeLeft:
    """New content revealed left-to-right via pixel compositing."""

    def frame_at(self, t, canvas, outgoing, incoming):
        from led_ticker.shadow_canvas import (
            ShadowCanvas,
            composite_wipe,
        )

        w, h = canvas.width, getattr(canvas, "height", 16)
        old_buf = ShadowCanvas(w, h)
        new_buf = ShadowCanvas(w, h)
        outgoing.draw(old_buf, cursor_pos=0)
        incoming.draw(new_buf, cursor_pos=0)

        boundary = int(t * w)
        composite_wipe(old_buf, new_buf, boundary, canvas, "left")
        return canvas


@register_transition("wipe_right")
class WipeRight:
    """New content revealed right-to-left via pixel compositing."""

    def frame_at(self, t, canvas, outgoing, incoming):
        from led_ticker.shadow_canvas import (
            ShadowCanvas,
            composite_wipe,
        )

        w, h = canvas.width, getattr(canvas, "height", 16)
        old_buf = ShadowCanvas(w, h)
        new_buf = ShadowCanvas(w, h)
        outgoing.draw(old_buf, cursor_pos=0)
        incoming.draw(new_buf, cursor_pos=0)

        boundary = int(t * w)
        composite_wipe(old_buf, new_buf, boundary, canvas, "right")
        return canvas


@register_transition("dissolve")
class Dissolve:
    """Random pixel dissolve from old to new content."""

    def __init__(self, seed: int = 42):
        self.seed = seed

    def frame_at(self, t, canvas, outgoing, incoming):
        from led_ticker.shadow_canvas import (
            ShadowCanvas,
            composite_dissolve,
        )

        w, h = canvas.width, getattr(canvas, "height", 16)
        old_buf = ShadowCanvas(w, h)
        new_buf = ShadowCanvas(w, h)
        outgoing.draw(old_buf, cursor_pos=0)
        incoming.draw(new_buf, cursor_pos=0)

        composite_dissolve(old_buf, new_buf, t, canvas, self.seed)
        return canvas


@register_transition("split")
class SplitHorizontal:
    """Content revealed from center outward."""

    def frame_at(self, t, canvas, outgoing, incoming):
        from led_ticker.shadow_canvas import (
            ShadowCanvas,
            composite_split,
        )

        w, h = canvas.width, getattr(canvas, "height", 16)
        old_buf = ShadowCanvas(w, h)
        new_buf = ShadowCanvas(w, h)
        outgoing.draw(old_buf, cursor_pos=0)
        incoming.draw(new_buf, cursor_pos=0)

        composite_split(old_buf, new_buf, t, canvas)
        return canvas


@register_transition("curtain")
class Curtain:
    """Old content slides apart revealing new content underneath."""

    def frame_at(self, t, canvas, outgoing, incoming):
        from led_ticker.shadow_canvas import (
            ShadowCanvas,
            composite_curtain,
        )

        w, h = canvas.width, getattr(canvas, "height", 16)
        old_buf = ShadowCanvas(w, h)
        new_buf = ShadowCanvas(w, h)
        outgoing.draw(old_buf, cursor_pos=0)
        incoming.draw(new_buf, cursor_pos=0)

        composite_curtain(old_buf, new_buf, t, canvas)
        return canvas
