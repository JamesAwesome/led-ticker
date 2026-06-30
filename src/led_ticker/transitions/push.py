"""Push-based transition effects (rapid scroll)."""

import random
from typing import Any

from led_ticker._types import Canvas
from led_ticker.transitions import (
    Transition,
    _OutgoingScaleSweep,
    _phys,
    register_transition,
)


@register_transition("push_left")
class PushLeft(_OutgoingScaleSweep):
    """Rapid scroll — outgoing slides left, incoming enters from right.

    Uses draw-blackout-draw: draw outgoing at its scroll position,
    black out the right portion where incoming will appear, then
    draw incoming.  This prevents overlap since DrawText cannot be
    clipped.
    """

    GAP: int = 10  # pixels between outgoing right edge and incoming left edge

    def __init__(self, **kwargs: Any) -> None:
        pass

    def frame_at(
        self, t: float, canvas: Canvas, outgoing: Any, incoming: Any, **kwargs: Any
    ) -> Canvas:
        real, rw, rh, scale, _yo = _phys(canvas)
        w = canvas.width  # logical width (cursor_pos units for draw)
        outgoing_scroll_pos: int = kwargs.get("outgoing_scroll_pos", 0)

        if t >= 1.0:
            incoming.draw(canvas, cursor_pos=0)
            return canvas

        # scroll_offset sweeps from 0 to (logical width + gap) in logical units
        total_travel = w + self.GAP
        scroll_offset = int(t * total_travel)

        # Outgoing continues scrolling left from where _swap_and_scroll stopped
        outgoing_pos = outgoing_scroll_pos - scroll_offset
        # Incoming enters from the right edge
        incoming_pos = w + self.GAP - scroll_offset

        # 1. Draw outgoing (may bleed across entire canvas)
        outgoing.draw(canvas, cursor_pos=outgoing_pos)

        # 2. Black out from incoming_pos to canvas right edge at FULL physical
        #    height — prevents text bleed AND clears the letterbox bands.
        clear_start_logical = max(0, incoming_pos)
        if clear_start_logical < w:
            clear_start_phys = clear_start_logical * scale
            real.SubFill(clear_start_phys, 0, rw - clear_start_phys, rh, 0, 0, 0)

        # 3. Draw incoming on the cleared right side
        if incoming_pos < w:
            incoming.draw(canvas, cursor_pos=incoming_pos)

        return canvas


@register_transition("push_right")
class PushRight(_OutgoingScaleSweep):
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

    def __init__(self, **kwargs: Any) -> None:
        pass

    def frame_at(
        self, t: float, canvas: Canvas, outgoing: Any, incoming: Any, **kwargs: Any
    ) -> Canvas:
        real, rw, rh, scale, _yo = _phys(canvas)
        w = canvas.width  # logical width (cursor_pos units for draw)
        outgoing_scroll_pos: int = kwargs.get("outgoing_scroll_pos", 0)

        if t >= 1.0:
            incoming.draw(canvas, cursor_pos=0)
            return canvas

        boundary = int(t * w)  # logical units (cursor_pos)

        if boundary <= 0:
            # First frame: show outgoing at its natural hold position
            outgoing.draw(canvas, cursor_pos=outgoing_scroll_pos)
            return canvas

        # Incoming slides in from off-screen left
        incoming_pos = -w + boundary

        # 1. Draw incoming sliding in from left
        incoming.draw(canvas, cursor_pos=incoming_pos)

        # 2. Black out right zone at FULL physical height — clips incoming bleed
        #    and also clears the letterbox bands.
        boundary_phys = boundary * scale
        real.SubFill(boundary_phys, 0, rw - boundary_phys, rh, 0, 0, 0)

        # 3. Draw outgoing starting at boundary (no bleed into left zone
        #    since DrawText only renders rightward from cursor_pos)
        outgoing.draw(canvas, cursor_pos=boundary)

        return canvas


@register_transition("push_up")
class PushUp(_OutgoingScaleSweep):
    """Rapid scroll — outgoing slides up, incoming enters from bottom.

    Vertical version of PushLeft.  Uses y_offset to shift both widgets
    vertically, with a row-based blackout to prevent overlap.
    """

    GAP: int = 4  # vertical gap in pixels (smaller than horizontal)

    def __init__(self, **kwargs: Any) -> None:
        pass

    def frame_at(
        self, t: float, canvas: Canvas, outgoing: Any, incoming: Any, **kwargs: Any
    ) -> Canvas:
        real, rw, rh, scale, y_offset_real = _phys(canvas)
        h = canvas.height  # logical content height (y_offset units for draw)

        if t >= 1.0:
            incoming.draw(canvas, cursor_pos=0)
            return canvas

        total_travel = h + self.GAP
        scroll_offset = int(t * total_travel)

        # Outgoing slides up
        outgoing_y = -scroll_offset
        # Incoming enters from the bottom
        incoming_y = h + self.GAP - scroll_offset

        outgoing_scroll_pos: int = kwargs.get("outgoing_scroll_pos", 0)

        # 1. Draw outgoing shifted up (at its scrolled position)
        outgoing.draw(canvas, cursor_pos=outgoing_scroll_pos, y_offset=outgoing_y)

        # 2. Black out rows from the incoming boundary downward at FULL physical
        #    width — includes letterbox bands so the incoming zone is fully clear.
        boundary_row = max(0, min(h, incoming_y))  # logical
        boundary_row_phys = boundary_row * scale + y_offset_real
        if boundary_row_phys < rh:
            real.SubFill(0, boundary_row_phys, rw, rh - boundary_row_phys, 0, 0, 0)

        # 3. Draw incoming on the cleared bottom zone
        if incoming_y < h:
            incoming.draw(canvas, cursor_pos=0, y_offset=incoming_y)

        return canvas


@register_transition("push_down")
class PushDown(_OutgoingScaleSweep):
    """Rapid scroll — outgoing slides down, incoming enters from top.

    Mirror of PushUp.  Uses y_offset to shift both widgets vertically,
    with a row-based blackout to prevent overlap.
    """

    GAP: int = 4

    def __init__(self, **kwargs: Any) -> None:
        pass

    def frame_at(
        self, t: float, canvas: Canvas, outgoing: Any, incoming: Any, **kwargs: Any
    ) -> Canvas:
        real, rw, rh, scale, y_offset_real = _phys(canvas)
        h = canvas.height  # logical content height (y_offset units for draw)

        if t >= 1.0:
            incoming.draw(canvas, cursor_pos=0)
            return canvas

        total_travel = h + self.GAP
        scroll_offset = int(t * total_travel)

        outgoing_scroll_pos: int = kwargs.get("outgoing_scroll_pos", 0)

        # Outgoing slides down
        outgoing_y = scroll_offset
        # Incoming enters from the top
        incoming_y = -(h + self.GAP) + scroll_offset

        # 1. Draw incoming shifted down from top
        if incoming_y + h > 0:
            incoming.draw(canvas, cursor_pos=0, y_offset=incoming_y)

        # 2. Black out rows from the boundary downward (outgoing zone) at FULL
        #    physical width — includes letterbox bands.
        boundary_row = max(0, min(h, incoming_y + h))  # logical
        boundary_row_phys = boundary_row * scale + y_offset_real
        if boundary_row_phys < rh:
            real.SubFill(0, boundary_row_phys, rw, rh - boundary_row_phys, 0, 0, 0)

        # 3. Draw outgoing shifted down on the cleared bottom zone
        outgoing.draw(
            canvas,
            cursor_pos=outgoing_scroll_pos,
            y_offset=outgoing_y,
        )

        return canvas


@register_transition("push_random")
class PushRandom(_OutgoingScaleSweep):
    """Picks a random push direction on each swap.

    Never repeats the same direction back-to-back.
    """

    _PUSH_CLASSES: list[type[Transition]] = [PushLeft, PushRight, PushUp, PushDown]

    def __init__(self, **kwargs: Any) -> None:
        self._rng = random.Random()
        chosen_cls = self._rng.choice(self._PUSH_CLASSES)
        self._last_cls: type[Transition] = chosen_cls
        self._last_t: float = 1.0
        self._current: Transition = chosen_cls()

    @property
    def min_frames(self) -> int:
        return getattr(self._current, "min_frames", 10)

    def frame_at(
        self, t: float, canvas: Canvas, outgoing: Any, incoming: Any, **kwargs: Any
    ) -> Canvas:
        if t < self._last_t:
            candidates = [
                cls for cls in self._PUSH_CLASSES if cls is not self._last_cls
            ]
            chosen_cls = self._rng.choice(candidates)
            self._current = chosen_cls()
            self._last_cls = chosen_cls
        self._last_t = t
        assert self._current is not None
        return self._current.frame_at(t, canvas, outgoing, incoming, **kwargs)


@register_transition("push_alternating")
class PushAlternating(_OutgoingScaleSweep):
    """Cycles through push_left -> push_right -> push_up -> push_down."""

    def __init__(self, **kwargs: Any) -> None:
        self._transitions: list[Transition] = [
            PushLeft(**kwargs),
            PushRight(**kwargs),
            PushUp(**kwargs),
            PushDown(**kwargs),
        ]
        self._index: int = -1
        self._last_t: float = 1.0

    def frame_at(
        self, t: float, canvas: Canvas, outgoing: Any, incoming: Any, **kwargs: Any
    ) -> Canvas:
        if t < self._last_t:
            self._index = (self._index + 1) % len(self._transitions)
        self._last_t = t
        return self._transitions[self._index].frame_at(
            t, canvas, outgoing, incoming, **kwargs
        )
