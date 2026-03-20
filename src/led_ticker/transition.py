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
    """Run a transition. Returns the current back-buffer canvas."""
    ease_fn = EASING.get(easing, linear)
    frame_count = max(1, int(duration / scroll_speed))

    for i in range(frame_count + 1):
        t = ease_fn(i / max(1, frame_count))
        canvas.Clear()
        transition.frame_at(t, canvas, outgoing, incoming)
        canvas = frame.matrix.SwapOnVSync(canvas)
        await asyncio.sleep(scroll_speed)

    return canvas


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
    """Timed cut at midpoint (vertical push not possible with fixed y)."""

    def frame_at(self, t, canvas, outgoing, incoming):
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
    """Wipe left (push-left approximation for hardware compat)."""

    def frame_at(self, t, canvas, outgoing, incoming):
        offset = int(t * canvas.width)
        outgoing.draw(canvas, cursor_pos=-offset)
        incoming.draw(canvas, cursor_pos=canvas.width - offset)
        return canvas


@register_transition("wipe_right")
class WipeRight:
    """Wipe right (push-right approximation for hardware compat)."""

    def frame_at(self, t, canvas, outgoing, incoming):
        offset = int(t * canvas.width)
        outgoing.draw(canvas, cursor_pos=offset)
        incoming.draw(canvas, cursor_pos=-canvas.width + offset)
        return canvas


@register_transition("dissolve")
class Dissolve:
    """Timed crossfade -- snaps from old to new at midpoint."""

    def __init__(self, seed: int = 42):
        self.seed = seed

    def frame_at(self, t, canvas, outgoing, incoming):
        if t < 0.5:
            outgoing.draw(canvas, cursor_pos=0)
        else:
            incoming.draw(canvas, cursor_pos=0)
        return canvas


@register_transition("split")
class SplitHorizontal:
    """Split -- timed cut approximation."""

    def frame_at(self, t, canvas, outgoing, incoming):
        if t < 0.5:
            outgoing.draw(canvas, cursor_pos=0)
        else:
            incoming.draw(canvas, cursor_pos=0)
        return canvas


@register_transition("curtain")
class Curtain:
    """Curtain -- timed cut approximation."""

    def frame_at(self, t, canvas, outgoing, incoming):
        if t < 0.5:
            outgoing.draw(canvas, cursor_pos=0)
        else:
            incoming.draw(canvas, cursor_pos=0)
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

        if cat_x >= width:
            # Cat exited -- show incoming
            incoming.draw(canvas, cursor_pos=0)
        else:
            # Draw outgoing as base, rainbow + cat on top
            outgoing.draw(canvas, cursor_pos=0)
            draw_nyan_frame(canvas, t, width=width, height=height)

        return canvas
