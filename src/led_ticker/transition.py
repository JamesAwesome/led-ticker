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
    if hasattr(transition, "min_frames"):
        frame_count = max(frame_count, transition.min_frames)

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
            x_range = range(clear_start, w)
            for y in range(h):
                for x in x_range:
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

        # Incoming slides in from off-screen left
        incoming_pos = -w + boundary

        # 1. Draw incoming sliding in from left
        incoming.draw(canvas, cursor_pos=incoming_pos)

        # 2. Black out right zone — clip incoming to left zone only
        x_range = range(boundary, w)
        for y in range(h):
            for x in x_range:
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


class _BaseWipe:
    """Base class for wipe transitions. Not registered as a transition."""

    DEFAULT_COLOR = (0, 255, 255)
    min_frames = 40

    def __init__(self, color=None, **kwargs):
        self.color = tuple(color) if color else self.DEFAULT_COLOR


@register_transition("wipe_up")
class WipeUp(_BaseWipe):
    """Bottom-to-top wipe with sweep line moving upward."""

    DEFAULT_COLOR = (255, 255, 255)
    min_frames = 16

    def frame_at(self, t, canvas, outgoing, incoming, **kwargs):
        w = canvas.width
        h = getattr(canvas, "height", 16)
        outgoing_scroll_pos = kwargs.get("outgoing_scroll_pos", 0)
        # Sweep line moves from bottom (h-1) to top (0)
        sweep_row = max(0, h - 1 - min(int(t * h), h - 1))

        if t >= 1.0:
            incoming.draw(canvas, cursor_pos=0)
        else:
            outgoing.draw(canvas, cursor_pos=outgoing_scroll_pos)
            # Black out rows below sweep (erased region)
            if sweep_row < h - 1:
                for y in range(sweep_row + 1, h):
                    for x in range(w):
                        canvas.SetPixel(x, y, 0, 0, 0)
            # Sweep line (2px thick)
            for dy in range(2):
                row = sweep_row + dy
                if 0 <= row < h:
                    for x in range(w):
                        canvas.SetPixel(x, row, *self.color)
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
class WipeLeft(_BaseWipe):
    """Right-to-left wipe — sweep moves toward the left."""

    DEFAULT_COLOR = (0, 255, 255)

    def frame_at(self, t, canvas, outgoing, incoming, **kwargs):
        w = canvas.width
        h = getattr(canvas, "height", 16)
        outgoing_scroll_pos = kwargs.get("outgoing_scroll_pos", 0)
        boundary = min(int(t * (w + 1)), w)

        if t >= 1.0:
            incoming.draw(canvas, cursor_pos=0)
        else:
            outgoing.draw(canvas, cursor_pos=outgoing_scroll_pos)
            line_x = w - boundary
            # Black out right of sweep line (erased region)
            if boundary > 0:
                x_range = range(line_x, w)
                for y in range(h):
                    for x in x_range:
                        canvas.SetPixel(x, y, 0, 0, 0)
            # Sweep line at line_x
            sweep_w = min(2, line_x)
            if sweep_w > 0:
                for y in range(h):
                    for dx in range(sweep_w):
                        canvas.SetPixel(line_x - 1 - dx, y, *self.color)
        return canvas


@register_transition("wipe_right")
class WipeRight(_BaseWipe):
    """Left-to-right wipe — sweep moves toward the right."""

    DEFAULT_COLOR = (255, 0, 255)

    def frame_at(self, t, canvas, outgoing, incoming, **kwargs):
        w = canvas.width
        h = getattr(canvas, "height", 16)
        outgoing_scroll_pos = kwargs.get("outgoing_scroll_pos", 0)
        boundary = min(int(t * (w + 1)), w)

        if t >= 1.0:
            incoming.draw(canvas, cursor_pos=0)
        else:
            outgoing.draw(canvas, cursor_pos=outgoing_scroll_pos)
            # Black out left of boundary (erased region)
            if boundary > 0:
                x_range = range(boundary)
                for y in range(h):
                    for x in x_range:
                        canvas.SetPixel(x, y, 0, 0, 0)
            # Sweep line at boundary
            sweep_w = min(2, w - boundary)
            if sweep_w > 0:
                for y in range(h):
                    for dx in range(sweep_w):
                        canvas.SetPixel(boundary + dx, y, *self.color)
        return canvas


@register_transition("dissolve")
class Dissolve:
    """Random pixel scatter dissolve.

    Pre-computes a shuffled pixel sequence at first use, then slices
    it per frame — avoids per-frame RNG overhead on the Pi.
    """

    def __init__(self, seed: int = 42, **kwargs):
        self.seed = seed
        self._sequence: list | None = None

    def _get_sequence(self, w, h):
        if self._sequence is None or len(self._sequence) != w * h:
            import random

            rng = random.Random(self.seed)
            coords = [(x, y) for y in range(h) for x in range(w)]
            rng.shuffle(coords)
            self._sequence = coords
        return self._sequence

    def frame_at(self, t, canvas, outgoing, incoming, **kwargs):
        w = canvas.width
        h = getattr(canvas, "height", 16)
        outgoing_scroll_pos = kwargs.get("outgoing_scroll_pos", 0)

        if t >= 1.0:
            incoming.draw(canvas, cursor_pos=0)
        elif t <= 0.0:
            outgoing.draw(canvas, cursor_pos=outgoing_scroll_pos)
        else:
            seq = self._get_sequence(w, h)
            total = len(seq)
            if t < 0.5:
                # Outgoing with increasing black scatter
                outgoing.draw(canvas, cursor_pos=outgoing_scroll_pos)
                count = int(t * 2 * total)
                for x, y in seq[:count]:
                    canvas.SetPixel(x, y, 0, 0, 0)
            else:
                # Incoming with decreasing black scatter
                incoming.draw(canvas, cursor_pos=0)
                count = int((1.0 - t) * 2 * total)
                for x, y in seq[:count]:
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
class WipeDown(_BaseWipe):
    """Top-to-bottom wipe with sweep line moving downward (formerly 'curtain')."""

    DEFAULT_COLOR = (0, 255, 0)
    min_frames = 16

    def frame_at(self, t, canvas, outgoing, incoming, **kwargs):
        w = canvas.width
        h = getattr(canvas, "height", 16)
        outgoing_scroll_pos = kwargs.get("outgoing_scroll_pos", 0)
        sweep_row = min(int(t * (h + 1)), h)

        if t >= 1.0:
            incoming.draw(canvas, cursor_pos=0)
        else:
            outgoing.draw(canvas, cursor_pos=outgoing_scroll_pos)
            # Black out rows above sweep (erased region)
            if sweep_row > 0:
                for y in range(min(sweep_row, h)):
                    for x in range(w):
                        canvas.SetPixel(x, y, 0, 0, 0)
            # Sweep line (2px thick)
            for dy in range(2):
                row = sweep_row - dy
                if 0 <= row < h:
                    for x in range(w):
                        canvas.SetPixel(x, row, *self.color)
        return canvas


@register_transition("nyancat")
class NyanCat:
    """Nyan Cat flies left-to-right, rainbow fills screen before cut."""

    def __init__(self, **kwargs):
        pass

    def frame_at(self, t, canvas, outgoing, incoming, **kwargs):
        from led_ticker.widgets.nyancat import draw_nyan_frame

        if t >= 1.0:
            incoming.draw(canvas, cursor_pos=0)
            return canvas

        outgoing_scroll_pos = kwargs.get("outgoing_scroll_pos", 0)
        outgoing.draw(canvas, cursor_pos=outgoing_scroll_pos)
        draw_nyan_frame(
            canvas, t,
            width=canvas.width,
            height=getattr(canvas, "height", 16),
        )
        return canvas


@register_transition("nyancat_reverse")
class NyanCatReverse:
    """Nyan Cat flies right-to-left, rainbow fills screen before cut."""

    def __init__(self, **kwargs):
        pass

    def frame_at(self, t, canvas, outgoing, incoming, **kwargs):
        from led_ticker.widgets.nyancat import draw_nyan_frame_rtl

        if t >= 1.0:
            incoming.draw(canvas, cursor_pos=0)
            return canvas

        outgoing_scroll_pos = kwargs.get("outgoing_scroll_pos", 0)
        outgoing.draw(canvas, cursor_pos=outgoing_scroll_pos)
        draw_nyan_frame_rtl(
            canvas, t,
            width=canvas.width,
            height=getattr(canvas, "height", 16),
        )
        return canvas


@register_transition("scroll")
class Scroll:
    """Seamless continuous scroll with bullet separator.

    Outgoing, bullet, and incoming scroll left together as one
    continuous strip — like forever_scroll between two widgets.
    The bullet (" * ") separates the two texts visually.

    Recommended: transition_duration = 4.0, easing = "linear".
    """

    def __init__(self, **kwargs):
        from led_ticker.ticker import SCROLL_GAP, scroll_separator_width

        self._sep_w = scroll_separator_width()
        self._gap = SCROLL_GAP

    def frame_at(self, t, canvas, outgoing, incoming, **kwargs):
        from led_ticker.ticker import _draw_scroll_frame

        w = canvas.width
        outgoing_scroll_pos = kwargs.get("outgoing_scroll_pos", 0)

        if t >= 1.0:
            incoming.draw(canvas, cursor_pos=0)
            return canvas

        total_travel = w + self._sep_w
        scroll_offset = int(t * total_travel)

        outgoing_pos = outgoing_scroll_pos - scroll_offset
        clear_start = max(0, w - scroll_offset)
        bullet_x = w + self._gap - scroll_offset
        incoming_pos = w + self._sep_w - scroll_offset

        _draw_scroll_frame(
            canvas, outgoing, incoming,
            outgoing_pos, bullet_x, incoming_pos, clear_start,
        )

        return canvas


# --- Meta-transitions (cycle through sub-transitions) ---


@register_transition("push_alternating")
class PushAlternating:
    """Cycles through push_left → push_right → push_up → push_down."""

    def __init__(self, **kwargs):
        self._transitions = [
            PushLeft(**kwargs),
            PushRight(**kwargs),
            PushUp(**kwargs),
            PushDown(**kwargs),
        ]
        self._index = -1
        self._last_t = 1.0

    def frame_at(self, t, canvas, outgoing, incoming, **kwargs):
        if t < self._last_t:
            self._index = (self._index + 1) % len(self._transitions)
        self._last_t = t
        return self._transitions[self._index].frame_at(
            t, canvas, outgoing, incoming, **kwargs
        )


@register_transition("nyancat_alternating")
class NyanCatAlternating:
    """Cycles through nyancat → nyancat_reverse."""

    def __init__(self, **kwargs):
        self._transitions = [
            NyanCat(**kwargs),
            NyanCatReverse(**kwargs),
        ]
        self._index = -1
        self._last_t = 1.0

    def frame_at(self, t, canvas, outgoing, incoming, **kwargs):
        if t < self._last_t:
            self._index = (self._index + 1) % len(self._transitions)
        self._last_t = t
        return self._transitions[self._index].frame_at(
            t, canvas, outgoing, incoming, **kwargs
        )


@register_transition("wipe_alternating")
class WipeAlternating:
    """Cycles through wipe_left → wipe_right → wipe_up → wipe_down."""

    def __init__(self, colors=None, color=None, **kwargs):
        wipe_classes = [WipeLeft, WipeRight, WipeUp, WipeDown]

        if colors and len(colors) >= len(wipe_classes):
            self._transitions = [
                cls(color=c)
                for cls, c in zip(wipe_classes, colors, strict=False)
            ]
        elif color:
            self._transitions = [
                cls(color=color) for cls in wipe_classes
            ]
        else:
            # Each uses its own DEFAULT_COLOR
            self._transitions = [cls() for cls in wipe_classes]

        self._index = -1
        self._last_t = 1.0

    @property
    def min_frames(self):
        """Return min_frames for the NEXT sub-transition."""
        next_idx = (self._index + 1) % len(self._transitions)
        return getattr(self._transitions[next_idx], "min_frames", 10)

    def frame_at(self, t, canvas, outgoing, incoming, **kwargs):
        if t < self._last_t:
            self._index = (self._index + 1) % len(self._transitions)
        self._last_t = t
        return self._transitions[self._index].frame_at(
            t, canvas, outgoing, incoming, **kwargs
        )
