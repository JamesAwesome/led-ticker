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
    """Left sweep — outgoing erased left-to-right, then incoming appears."""

    def frame_at(self, t, canvas, outgoing, incoming):
        w = canvas.width
        h = getattr(canvas, "height", 16)
        boundary = int(t * w)

        if t >= 1.0:
            incoming.draw(canvas, cursor_pos=0)
        elif boundary <= 0:
            outgoing.draw(canvas, cursor_pos=0)
        else:
            outgoing.draw(canvas, cursor_pos=0)
            for y in range(h):
                for x in range(boundary):
                    canvas.SetPixel(x, y, 0, 0, 0)
            for y in range(h):
                for dx in range(min(2, w - boundary)):
                    canvas.SetPixel(boundary + dx, y, 255, 255, 255)
        return canvas


@register_transition("push_right")
class PushRight:
    """Right sweep — outgoing erased right-to-left, then incoming appears."""

    def frame_at(self, t, canvas, outgoing, incoming):
        w = canvas.width
        h = getattr(canvas, "height", 16)
        boundary = int(t * w)

        if t >= 1.0:
            incoming.draw(canvas, cursor_pos=0)
        elif boundary <= 0:
            outgoing.draw(canvas, cursor_pos=0)
        else:
            outgoing.draw(canvas, cursor_pos=0)
            for y in range(h):
                for x in range(w - boundary, w):
                    canvas.SetPixel(x, y, 0, 0, 0)
            line_x = w - boundary
            for y in range(h):
                for dx in range(min(2, line_x)):
                    canvas.SetPixel(line_x - 1 - dx, y, 255, 255, 255)
        return canvas


@register_transition("push_up")
class PushUp:
    """Top sweep — outgoing erased top-to-bottom, then incoming appears."""

    def frame_at(self, t, canvas, outgoing, incoming):
        w = canvas.width
        h = getattr(canvas, "height", 16)
        sweep_row = int(t * h)

        if t >= 1.0:
            incoming.draw(canvas, cursor_pos=0)
        elif sweep_row <= 0:
            outgoing.draw(canvas, cursor_pos=0)
        else:
            outgoing.draw(canvas, cursor_pos=0)
            for y in range(min(sweep_row, h)):
                for x in range(w):
                    canvas.SetPixel(x, y, 0, 0, 0)
            if sweep_row < h:
                for x in range(w):
                    canvas.SetPixel(x, sweep_row, 255, 255, 255)
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
    """Right-to-left wipe with sweep line."""

    def frame_at(self, t, canvas, outgoing, incoming):
        w = canvas.width
        h = getattr(canvas, "height", 16)
        boundary = int(t * w)

        if t >= 1.0:
            incoming.draw(canvas, cursor_pos=0)
        elif boundary <= 0:
            outgoing.draw(canvas, cursor_pos=0)
        else:
            # Draw outgoing stationary
            outgoing.draw(canvas, cursor_pos=0)
            # Black out left of boundary (erased region)
            for y in range(h):
                for x in range(boundary):
                    canvas.SetPixel(x, y, 0, 0, 0)
            # Draw cyan sweep line at boundary
            for y in range(h):
                for dx in range(min(2, w - boundary)):
                    canvas.SetPixel(boundary + dx, y, 0, 255, 255)
        return canvas


@register_transition("wipe_right")
class WipeRight:
    """Left-to-right wipe with sweep line."""

    def frame_at(self, t, canvas, outgoing, incoming):
        w = canvas.width
        h = getattr(canvas, "height", 16)
        boundary = int(t * w)

        if t >= 1.0:
            incoming.draw(canvas, cursor_pos=0)
        elif boundary <= 0:
            outgoing.draw(canvas, cursor_pos=0)
        else:
            outgoing.draw(canvas, cursor_pos=0)
            # Black out right of boundary
            for y in range(h):
                for x in range(w - boundary, w):
                    canvas.SetPixel(x, y, 0, 0, 0)
            # Sweep line
            line_x = w - boundary
            for y in range(h):
                for dx in range(min(2, line_x)):
                    canvas.SetPixel(line_x - 1 - dx, y, 0, 255, 255)
        return canvas


@register_transition("dissolve")
class Dissolve:
    """Random pixel scatter dissolve."""

    def __init__(self, seed: int = 42):
        self.seed = seed

    def frame_at(self, t, canvas, outgoing, incoming):
        import random

        w = canvas.width
        h = getattr(canvas, "height", 16)

        if t >= 1.0:
            incoming.draw(canvas, cursor_pos=0)
        elif t <= 0.0:
            outgoing.draw(canvas, cursor_pos=0)
        elif t < 0.5:
            # Outgoing with increasing black scatter
            outgoing.draw(canvas, cursor_pos=0)
            rng = random.Random(self.seed + int(t * 1000))
            scatter_count = int(t * 2 * w * h)
            for _ in range(scatter_count):
                x = rng.randint(0, w - 1)
                y = rng.randint(0, h - 1)
                canvas.SetPixel(x, y, 0, 0, 0)
        else:
            # Incoming with decreasing black scatter
            incoming.draw(canvas, cursor_pos=0)
            rng = random.Random(self.seed + int(t * 1000))
            scatter_count = int((1.0 - t) * 2 * w * h)
            for _ in range(scatter_count):
                x = rng.randint(0, w - 1)
                y = rng.randint(0, h - 1)
                canvas.SetPixel(x, y, 0, 0, 0)
        return canvas


@register_transition("split")
class SplitHorizontal:
    """Center-outward expanding black band with edge lines."""

    def frame_at(self, t, canvas, outgoing, incoming):
        w = canvas.width
        h = getattr(canvas, "height", 16)
        half = w // 2
        reveal = int(t * half)

        if t >= 1.0:
            incoming.draw(canvas, cursor_pos=0)
        elif reveal <= 0:
            outgoing.draw(canvas, cursor_pos=0)
        else:
            outgoing.draw(canvas, cursor_pos=0)
            left = half - reveal
            right = half + reveal
            # Black out center band
            for y in range(h):
                for x in range(max(0, left), min(right, w)):
                    canvas.SetPixel(x, y, 0, 0, 0)
            # Magenta edge lines
            for y in range(h):
                if 0 <= left < w:
                    canvas.SetPixel(left, y, 255, 0, 255)
                if 0 <= right - 1 < w:
                    canvas.SetPixel(right - 1, y, 255, 0, 255)
        return canvas


@register_transition("curtain")
class Curtain:
    """Top-down curtain drop with sweep line."""

    def frame_at(self, t, canvas, outgoing, incoming):
        w = canvas.width
        h = getattr(canvas, "height", 16)
        sweep_row = int(t * h)

        if t >= 1.0:
            incoming.draw(canvas, cursor_pos=0)
        elif sweep_row <= 0:
            outgoing.draw(canvas, cursor_pos=0)
        else:
            outgoing.draw(canvas, cursor_pos=0)
            # Black out rows above sweep
            for y in range(min(sweep_row, h)):
                for x in range(w):
                    canvas.SetPixel(x, y, 0, 0, 0)
            # Green sweep line
            if sweep_row < h:
                for x in range(w):
                    canvas.SetPixel(x, sweep_row, 0, 255, 0)
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
