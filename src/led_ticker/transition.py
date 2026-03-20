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
    """New content sweeps in from right to left (push-based)."""

    def frame_at(self, t, canvas, outgoing, incoming):
        offset = int(t * canvas.width)
        outgoing.draw(canvas, cursor_pos=-offset)
        incoming.draw(canvas, cursor_pos=canvas.width - offset)
        return canvas


@register_transition("wipe_right")
class WipeRight:
    """New content sweeps in from left to right (push-based)."""

    def frame_at(self, t, canvas, outgoing, incoming):
        offset = int(t * canvas.width)
        outgoing.draw(canvas, cursor_pos=offset)
        incoming.draw(canvas, cursor_pos=-canvas.width + offset)
        return canvas


@register_transition("dissolve")
class Dissolve:
    """Cross-dissolve using timed cut (pixel-level needs PIL+SetImage).

    At the midpoint, switches from old to new. Combined with
    ease_in_out easing this creates a smooth-feeling transition.
    """

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
    """Old content splits apart from center, new underneath."""

    def frame_at(self, t, canvas, outgoing, incoming):
        w = canvas.width
        half = w // 2
        offset = int(t * half)

        if offset == 0:
            # No split yet — show outgoing only (no bleed-through)
            outgoing.draw(canvas, cursor_pos=0)
        elif t >= 1.0:
            incoming.draw(canvas, cursor_pos=0)
        else:
            incoming.draw(canvas, cursor_pos=0)
            outgoing.draw(canvas, cursor_pos=-offset)
        return canvas


@register_transition("curtain")
class Curtain:
    """Old content slides left like a curtain opening."""

    def frame_at(self, t, canvas, outgoing, incoming):
        w = canvas.width
        offset = int(t * w)

        if offset == 0:
            outgoing.draw(canvas, cursor_pos=0)
        elif t >= 1.0:
            incoming.draw(canvas, cursor_pos=0)
        else:
            incoming.draw(canvas, cursor_pos=0)
            outgoing.draw(canvas, cursor_pos=-offset)
        return canvas


@register_transition("nyancat")
class NyanCat:
    """Nyan Cat flies across the screen trailing a rainbow.

    The cat sprite enters from the left, trails a rainbow behind it,
    and the new content is revealed in the rainbow's wake.
    """

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
            # Rainbow passed entirely — show incoming only
            incoming.draw(canvas, cursor_pos=0)
        elif trail_end <= 0:
            # Rainbow hasn't entered — show outgoing only
            outgoing.draw(canvas, cursor_pos=0)
        else:
            # Rainbow partially across: outgoing as base, clear
            # the revealed region, draw incoming, then rainbow+cat
            outgoing.draw(canvas, cursor_pos=0)
            for y in range(height):
                for x in range(trail_end):
                    canvas.SetPixel(x, y, 0, 0, 0)
            incoming.draw(canvas, cursor_pos=0)
            draw_nyan_frame(canvas, t, width=width, height=height)

        return canvas
