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
        **kwargs: Any,
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
    outgoing_scroll_pos: int = 0,
):
    """Run a transition. Returns the current back-buffer canvas."""
    ease_fn = EASING.get(easing, linear)
    frame_count = max(1, int(duration / scroll_speed))

    for i in range(frame_count + 1):
        t = ease_fn(i / max(1, frame_count))
        canvas.Clear()
        transition.frame_at(
            t, canvas, outgoing, incoming,
            outgoing_scroll_pos=outgoing_scroll_pos,
        )
        canvas = frame.matrix.SwapOnVSync(canvas)
        await asyncio.sleep(scroll_speed)

    return canvas


# --- Built-in transitions ---


@register_transition("cut")
class Cut:
    """Instant switch, no animation."""

    def __init__(self, **kwargs):
        pass

    def frame_at(self, t, canvas, outgoing, incoming, **kwargs):
        incoming.draw(canvas, cursor_pos=0)
        return canvas


@register_transition("push_left")
class PushLeft:
    """Rapid scroll — outgoing slides left, incoming enters from right.

    Uses draw-blackout-draw: draw outgoing at its scroll position,
    black out the right portion where incoming will appear, then
    draw incoming.  This prevents overlap since DrawText cannot be
    clipped.
    """

    GAP = 10  # pixels between outgoing right edge and incoming left edge

    def __init__(self, **kwargs):
        pass

    def frame_at(self, t, canvas, outgoing, incoming, **kwargs):
        w = canvas.width
        h = getattr(canvas, "height", 16)
        outgoing_scroll_pos = kwargs.get("outgoing_scroll_pos", 0)

        if t >= 1.0:
            incoming.draw(canvas, cursor_pos=0)
            return canvas

        # scroll_offset sweeps from 0 to (canvas.width + gap)
        total_travel = w + self.GAP
        scroll_offset = int(t * total_travel)

        # Outgoing continues scrolling left from where _swap_and_scroll stopped
        outgoing_pos = outgoing_scroll_pos - scroll_offset
        # Incoming enters from the right edge
        incoming_pos = w + self.GAP - scroll_offset

        # 1. Draw outgoing (may bleed across entire canvas)
        outgoing.draw(canvas, cursor_pos=outgoing_pos)

        # 2. Black out from incoming_pos to canvas width (clear the right zone)
        clear_start = max(0, incoming_pos)
        if clear_start < w:
            for y in range(h):
                for x in range(clear_start, w):
                    canvas.SetPixel(x, y, 0, 0, 0)

        # 3. Draw incoming on the cleared right side
        if incoming_pos < w:
            incoming.draw(canvas, cursor_pos=incoming_pos)

        return canvas


@register_transition("push_right")
class PushRight:
    """Rightward push — incoming enters from left, outgoing exits right.

    DrawText always renders rightward from cursor_pos, so we cannot
    draw outgoing at its scroll position (it would bleed into the
    incoming zone).  Instead we draw outgoing at cursor_pos=boundary
    which confines it to the right zone.  For short outgoing text
    this creates a natural sliding-right effect.  For long text the
    right zone shrinks so rapidly that the content change is masked.

    Rendering order (no overlap possible):
      1. Draw incoming at cursor_pos=0 (left-aligned)
      2. Black out right zone (boundary to w) — clips incoming
      3. Draw outgoing at cursor_pos=boundary — confined to right zone
    """

    def __init__(self, **kwargs):
        pass

    def frame_at(self, t, canvas, outgoing, incoming, **kwargs):
        w = canvas.width
        h = getattr(canvas, "height", 16)
        outgoing_scroll_pos = kwargs.get("outgoing_scroll_pos", 0)

        if t >= 1.0:
            incoming.draw(canvas, cursor_pos=0)
            return canvas

        boundary = int(t * w)

        if boundary <= 0:
            # First frame: show outgoing at its natural hold position
            outgoing.draw(canvas, cursor_pos=outgoing_scroll_pos)
            return canvas

        # 1. Draw incoming at cursor_pos=0 (beginning visible from left)
        incoming.draw(canvas, cursor_pos=0)

        # 2. Black out right zone — clip incoming to left zone only
        for y in range(h):
            for x in range(boundary, w):
                canvas.SetPixel(x, y, 0, 0, 0)

        # 3. Draw outgoing starting at boundary (no bleed into left zone
        #    since DrawText only renders rightward from cursor_pos)
        outgoing.draw(canvas, cursor_pos=boundary)

        return canvas


@register_transition("push_up")
class PushUp:
    """Rapid scroll — outgoing slides up, incoming enters from bottom.

    Vertical version of PushLeft.  Uses y_offset to shift both widgets
    vertically, with a row-based blackout to prevent overlap.
    """

    GAP = 4  # vertical gap in pixels (smaller than horizontal)

    def __init__(self, **kwargs):
        pass

    def frame_at(self, t, canvas, outgoing, incoming, **kwargs):
        w = canvas.width
        h = getattr(canvas, "height", 16)

        if t >= 1.0:
            incoming.draw(canvas, cursor_pos=0)
            return canvas

        total_travel = h + self.GAP
        scroll_offset = int(t * total_travel)

        # Outgoing slides up
        outgoing_y = -scroll_offset
        # Incoming enters from the bottom
        incoming_y = h + self.GAP - scroll_offset

        outgoing_scroll_pos = kwargs.get("outgoing_scroll_pos", 0)

        # 1. Draw outgoing shifted up (at its scrolled position)
        outgoing.draw(canvas, cursor_pos=outgoing_scroll_pos, y_offset=outgoing_y)

        # 2. Black out rows from boundary downward (incoming zone)
        boundary_row = max(0, min(h, incoming_y))
        if boundary_row < h:
            for y in range(boundary_row, h):
                for x in range(w):
                    canvas.SetPixel(x, y, 0, 0, 0)

        # 3. Draw incoming on the cleared bottom zone
        if incoming_y < h:
            incoming.draw(canvas, cursor_pos=0, y_offset=incoming_y)

        return canvas


@register_transition("push_down")
class PushDown:
    """Rapid scroll — outgoing slides down, incoming enters from top.

    Mirror of PushUp.  Uses y_offset to shift both widgets vertically,
    with a row-based blackout to prevent overlap.
    """

    GAP = 4

    def __init__(self, **kwargs):
        pass

    def frame_at(self, t, canvas, outgoing, incoming, **kwargs):
        w = canvas.width
        h = getattr(canvas, "height", 16)

        if t >= 1.0:
            incoming.draw(canvas, cursor_pos=0)
            return canvas

        total_travel = h + self.GAP
        scroll_offset = int(t * total_travel)

        outgoing_scroll_pos = kwargs.get("outgoing_scroll_pos", 0)

        # Outgoing slides down
        outgoing_y = scroll_offset
        # Incoming enters from the top
        incoming_y = -(h + self.GAP) + scroll_offset

        # 1. Draw incoming shifted down from top
        if incoming_y + h > 0:
            incoming.draw(canvas, cursor_pos=0, y_offset=incoming_y)

        # 2. Black out rows from boundary downward (outgoing zone)
        boundary_row = max(0, min(h, incoming_y + h))
        if boundary_row < h:
            for y in range(boundary_row, h):
                for x in range(w):
                    canvas.SetPixel(x, y, 0, 0, 0)

        # 3. Draw outgoing shifted down on the cleared bottom zone
        outgoing.draw(
            canvas, cursor_pos=outgoing_scroll_pos, y_offset=outgoing_y,
        )

        return canvas


@register_transition("wipe_up")
class WipeUp:
    """Top-down wipe with sweep line."""

    def __init__(self, color=None, **kwargs):
        self.color = tuple(color) if color else (255, 255, 255)

    def frame_at(self, t, canvas, outgoing, incoming, **kwargs):
        w = canvas.width
        h = getattr(canvas, "height", 16)
        outgoing_scroll_pos = kwargs.get("outgoing_scroll_pos", 0)
        sweep_row = int(t * h)

        if t >= 1.0:
            incoming.draw(canvas, cursor_pos=0)
        elif sweep_row <= 0:
            outgoing.draw(canvas, cursor_pos=outgoing_scroll_pos)
        else:
            outgoing.draw(canvas, cursor_pos=outgoing_scroll_pos)
            for y in range(min(sweep_row, h)):
                for x in range(w):
                    canvas.SetPixel(x, y, 0, 0, 0)
            if sweep_row < h:
                for x in range(w):
                    canvas.SetPixel(x, sweep_row, *self.color)
        return canvas


@register_transition("color_flash")
class ColorFlash:
    """Brief solid color flash between old and new content."""

    def __init__(self, color=None, **kwargs):
        self.color = tuple(color) if color else (255, 255, 255)

    def frame_at(self, t, canvas, outgoing, incoming, **kwargs):
        outgoing_scroll_pos = kwargs.get("outgoing_scroll_pos", 0)
        if t < 0.33:
            outgoing.draw(canvas, cursor_pos=outgoing_scroll_pos)
        elif t < 0.66:
            canvas.Fill(*self.color)
        else:
            incoming.draw(canvas, cursor_pos=0)
        return canvas


@register_transition("wipe_left")
class WipeLeft:
    """Right-to-left wipe with sweep line."""

    def __init__(self, color=None, **kwargs):
        self.color = tuple(color) if color else (0, 255, 255)

    def frame_at(self, t, canvas, outgoing, incoming, **kwargs):
        w = canvas.width
        h = getattr(canvas, "height", 16)
        outgoing_scroll_pos = kwargs.get("outgoing_scroll_pos", 0)
        boundary = int(t * w)

        if t >= 1.0:
            incoming.draw(canvas, cursor_pos=0)
        elif boundary <= 0:
            outgoing.draw(canvas, cursor_pos=outgoing_scroll_pos)
        else:
            # Draw outgoing stationary
            outgoing.draw(canvas, cursor_pos=outgoing_scroll_pos)
            # Black out left of boundary (erased region)
            for y in range(h):
                for x in range(boundary):
                    canvas.SetPixel(x, y, 0, 0, 0)
            # Draw sweep line at boundary
            for y in range(h):
                for dx in range(min(2, w - boundary)):
                    canvas.SetPixel(boundary + dx, y, *self.color)
        return canvas


@register_transition("wipe_right")
class WipeRight:
    """Left-to-right wipe with sweep line."""

    def __init__(self, color=None, **kwargs):
        self.color = tuple(color) if color else (0, 255, 255)

    def frame_at(self, t, canvas, outgoing, incoming, **kwargs):
        w = canvas.width
        h = getattr(canvas, "height", 16)
        outgoing_scroll_pos = kwargs.get("outgoing_scroll_pos", 0)
        boundary = int(t * w)

        if t >= 1.0:
            incoming.draw(canvas, cursor_pos=0)
        elif boundary <= 0:
            outgoing.draw(canvas, cursor_pos=outgoing_scroll_pos)
        else:
            outgoing.draw(canvas, cursor_pos=outgoing_scroll_pos)
            # Black out right of boundary
            for y in range(h):
                for x in range(w - boundary, w):
                    canvas.SetPixel(x, y, 0, 0, 0)
            # Sweep line
            line_x = w - boundary
            for y in range(h):
                for dx in range(min(2, line_x)):
                    canvas.SetPixel(line_x - 1 - dx, y, *self.color)
        return canvas


@register_transition("dissolve")
class Dissolve:
    """Random pixel scatter dissolve."""

    def __init__(self, seed: int = 42, **kwargs):
        self.seed = seed

    def frame_at(self, t, canvas, outgoing, incoming, **kwargs):
        import random

        w = canvas.width
        h = getattr(canvas, "height", 16)
        outgoing_scroll_pos = kwargs.get("outgoing_scroll_pos", 0)

        if t >= 1.0:
            incoming.draw(canvas, cursor_pos=0)
        elif t <= 0.0:
            outgoing.draw(canvas, cursor_pos=outgoing_scroll_pos)
        elif t < 0.5:
            # Outgoing with increasing black scatter
            outgoing.draw(canvas, cursor_pos=outgoing_scroll_pos)
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

    def __init__(self, **kwargs):
        pass

    def frame_at(self, t, canvas, outgoing, incoming, **kwargs):
        w = canvas.width
        h = getattr(canvas, "height", 16)
        outgoing_scroll_pos = kwargs.get("outgoing_scroll_pos", 0)
        half = w // 2
        reveal = int(t * half)

        if t >= 1.0:
            incoming.draw(canvas, cursor_pos=0)
        elif reveal <= 0:
            outgoing.draw(canvas, cursor_pos=outgoing_scroll_pos)
        else:
            outgoing.draw(canvas, cursor_pos=outgoing_scroll_pos)
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


@register_transition("wipe_down")
class WipeDown:
    """Top-down wipe with sweep line (formerly 'curtain')."""

    def __init__(self, color=None, **kwargs):
        self.color = tuple(color) if color else (0, 255, 0)

    def frame_at(self, t, canvas, outgoing, incoming, **kwargs):
        w = canvas.width
        h = getattr(canvas, "height", 16)
        outgoing_scroll_pos = kwargs.get("outgoing_scroll_pos", 0)
        sweep_row = int(t * h)

        if t >= 1.0:
            incoming.draw(canvas, cursor_pos=0)
        elif sweep_row <= 0:
            outgoing.draw(canvas, cursor_pos=outgoing_scroll_pos)
        else:
            outgoing.draw(canvas, cursor_pos=outgoing_scroll_pos)
            # Black out rows above sweep
            for y in range(min(sweep_row, h)):
                for x in range(w):
                    canvas.SetPixel(x, y, 0, 0, 0)
            # Sweep line
            if sweep_row < h:
                for x in range(w):
                    canvas.SetPixel(x, sweep_row, *self.color)
        return canvas


@register_transition("nyancat")
class NyanCat:
    """Nyan Cat flies across trailing a rainbow."""

    def __init__(self, **kwargs):
        pass

    def frame_at(self, t, canvas, outgoing, incoming, **kwargs):
        from led_ticker.widgets.nyancat import (
            SPRITE_WIDTH,
            draw_nyan_frame,
        )

        outgoing_scroll_pos = kwargs.get("outgoing_scroll_pos", 0)
        width = canvas.width
        height = getattr(canvas, "height", 16)
        total_travel = width + SPRITE_WIDTH
        cat_x = int(-SPRITE_WIDTH + t * total_travel)

        if cat_x >= width:
            # Cat exited -- show incoming
            incoming.draw(canvas, cursor_pos=0)
        else:
            # Draw outgoing as base, rainbow + cat on top
            outgoing.draw(canvas, cursor_pos=outgoing_scroll_pos)
            draw_nyan_frame(canvas, t, width=width, height=height)

        return canvas
