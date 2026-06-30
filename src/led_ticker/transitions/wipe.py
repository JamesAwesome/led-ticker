"""Wipe-based transition effects."""

import random
from typing import Any

from led_ticker._types import Canvas, ColorTuple
from led_ticker.transitions import _OutgoingScaleSweep, _phys, register_transition


class _BaseWipe(_OutgoingScaleSweep):
    """Base class for wipe transitions. Not registered as a transition."""

    DEFAULT_COLOR: ColorTuple = (0, 255, 255)
    min_frames: int = 40

    def __init__(self, color: ColorTuple | None = None, **kwargs: Any) -> None:
        c = color
        self.color: ColorTuple = (c[0], c[1], c[2]) if c else self.DEFAULT_COLOR

    def frame_at(
        self, t: float, canvas: Canvas, outgoing: Any, incoming: Any, **kwargs: Any
    ) -> Canvas:
        raise NotImplementedError


@register_transition("wipe_up")
class WipeUp(_BaseWipe):
    """Bottom-to-top wipe with sweep line moving upward."""

    DEFAULT_COLOR: ColorTuple = (255, 255, 255)
    min_frames: int = 16

    def frame_at(
        self, t: float, canvas: Canvas, outgoing: Any, incoming: Any, **kwargs: Any
    ) -> Canvas:
        real, rw, rh, scale, _yo = _phys(canvas)
        outgoing_scroll_pos: int = kwargs.get("outgoing_scroll_pos", 0)
        # Sweep line moves from bottom (rh-1) to top (0) in physical rows.
        sweep_row = max(0, rh - 1 - min(int(t * rh), rh - 1))

        if t >= 1.0:
            incoming.draw(canvas, cursor_pos=0)
        else:
            outgoing.draw(canvas, cursor_pos=outgoing_scroll_pos)
            # Black out rows below sweep at full physical width/height.
            if sweep_row < rh - 1:
                real.SubFill(0, sweep_row + 1, rw, rh - sweep_row - 1, 0, 0, 0)
            # Sweep line (2*scale px thick) spans full physical width.
            for dy in range(2 * scale):
                row = sweep_row + dy
                if 0 <= row < rh:
                    for x in range(rw):
                        real.SetPixel(x, row, *self.color)
        return canvas


@register_transition("wipe_left")
class WipeLeft(_BaseWipe):
    """Right-to-left wipe — sweep moves toward the left."""

    DEFAULT_COLOR: ColorTuple = (0, 255, 255)

    def frame_at(
        self, t: float, canvas: Canvas, outgoing: Any, incoming: Any, **kwargs: Any
    ) -> Canvas:
        real, rw, rh, scale, _yo = _phys(canvas)
        outgoing_scroll_pos: int = kwargs.get("outgoing_scroll_pos", 0)
        boundary = min(int(t * (rw + 1)), rw)

        if t >= 1.0:
            incoming.draw(canvas, cursor_pos=0)
        else:
            outgoing.draw(canvas, cursor_pos=outgoing_scroll_pos)
            line_x = rw - boundary
            # Black out right of sweep line at full physical height.
            if boundary > 0:
                real.SubFill(line_x, 0, rw - line_x, rh, 0, 0, 0)
            # Sweep line (2*scale px thick) spans full physical height.
            sweep_w = min(2 * scale, line_x)
            if sweep_w > 0:
                for y in range(rh):
                    for dx in range(sweep_w):
                        real.SetPixel(line_x - 1 - dx, y, *self.color)
        return canvas


@register_transition("wipe_right")
class WipeRight(_BaseWipe):
    """Left-to-right wipe — sweep moves toward the right."""

    DEFAULT_COLOR: ColorTuple = (255, 0, 255)

    def frame_at(
        self, t: float, canvas: Canvas, outgoing: Any, incoming: Any, **kwargs: Any
    ) -> Canvas:
        real, rw, rh, scale, _yo = _phys(canvas)
        outgoing_scroll_pos: int = kwargs.get("outgoing_scroll_pos", 0)
        boundary = min(int(t * (rw + 1)), rw)

        if t >= 1.0:
            incoming.draw(canvas, cursor_pos=0)
        else:
            outgoing.draw(canvas, cursor_pos=outgoing_scroll_pos)
            # Black out left of boundary at full physical height.
            if boundary > 0:
                real.SubFill(0, 0, boundary, rh, 0, 0, 0)
            # Sweep line (2*scale px thick) spans full physical height.
            sweep_w = min(2 * scale, rw - boundary)
            if sweep_w > 0:
                for y in range(rh):
                    for dx in range(sweep_w):
                        real.SetPixel(boundary + dx, y, *self.color)
        return canvas


@register_transition("wipe_down")
class WipeDown(_BaseWipe):
    """Top-to-bottom wipe with sweep line moving downward (formerly 'curtain')."""

    DEFAULT_COLOR: ColorTuple = (0, 255, 0)
    min_frames: int = 16

    def frame_at(
        self, t: float, canvas: Canvas, outgoing: Any, incoming: Any, **kwargs: Any
    ) -> Canvas:
        real, rw, rh, scale, _yo = _phys(canvas)
        outgoing_scroll_pos: int = kwargs.get("outgoing_scroll_pos", 0)
        sweep_row = min(int(t * (rh + 1)), rh)

        if t >= 1.0:
            incoming.draw(canvas, cursor_pos=0)
        else:
            outgoing.draw(canvas, cursor_pos=outgoing_scroll_pos)
            # Black out rows above sweep at full physical width.
            if sweep_row > 0:
                real.SubFill(0, 0, rw, min(sweep_row, rh), 0, 0, 0)
            # Sweep line (2*scale px thick) spans full physical width.
            for dy in range(2 * scale):
                row = sweep_row - dy
                if 0 <= row < rh:
                    for x in range(rw):
                        real.SetPixel(x, row, *self.color)
        return canvas


@register_transition("wipe_random")
class WipeRandom(_OutgoingScaleSweep):
    """Picks a random wipe direction and sweep color on each swap.

    Never repeats the same direction back-to-back. Color is drawn
    independently from the color pool, so direction and color can
    vary freely.
    """

    _WIPE_CLASSES: list[type[_BaseWipe]] = [WipeLeft, WipeRight, WipeUp, WipeDown]

    def __init__(
        self,
        colors: list[ColorTuple] | None = None,
        color: ColorTuple | None = None,
        **kwargs: Any,
    ) -> None:
        if colors is not None:
            self._color_pool: list[ColorTuple] = list(colors)
        elif color is not None:
            self._color_pool = [color]
        else:
            self._color_pool = [cls.DEFAULT_COLOR for cls in self._WIPE_CLASSES]

        self._rng = random.Random()
        self._last_cls: type[_BaseWipe] | None = None
        self._last_t: float = 1.0
        self._current: _BaseWipe | None = None

    @property
    def min_frames(self) -> int:
        if self._current is not None:
            return self._current.min_frames
        return 40  # _BaseWipe default; highest among all wipe directions

    def frame_at(
        self, t: float, canvas: Canvas, outgoing: Any, incoming: Any, **kwargs: Any
    ) -> Canvas:
        if t < self._last_t:
            candidates = [
                cls for cls in self._WIPE_CLASSES if cls is not self._last_cls
            ]
            chosen_cls = self._rng.choice(candidates)
            chosen_color = self._rng.choice(self._color_pool)
            self._current = chosen_cls(color=chosen_color)
            self._last_cls = chosen_cls
        self._last_t = t
        assert self._current is not None
        return self._current.frame_at(t, canvas, outgoing, incoming, **kwargs)


@register_transition("wipe_alternating")
class WipeAlternating(_OutgoingScaleSweep):
    """Cycles through wipe_left -> wipe_right -> wipe_up -> wipe_down."""

    def __init__(
        self,
        colors: list[ColorTuple] | None = None,
        color: ColorTuple | None = None,
        **kwargs: Any,
    ) -> None:
        wipe_classes: list[type[_BaseWipe]] = [WipeLeft, WipeRight, WipeUp, WipeDown]

        if colors and len(colors) >= len(wipe_classes):
            self._transitions: list[_BaseWipe] = [
                cls(color=c) for cls, c in zip(wipe_classes, colors, strict=False)
            ]
        elif color:
            self._transitions = [cls(color=color) for cls in wipe_classes]
        else:
            # Each uses its own DEFAULT_COLOR
            self._transitions = [cls() for cls in wipe_classes]

        self._index: int = -1
        self._last_t: float = 1.0

    @property
    def min_frames(self) -> int:
        """Return min_frames for the NEXT sub-transition."""
        next_idx = (self._index + 1) % len(self._transitions)
        return getattr(self._transitions[next_idx], "min_frames", 10)

    def frame_at(
        self, t: float, canvas: Canvas, outgoing: Any, incoming: Any, **kwargs: Any
    ) -> Canvas:
        if t < self._last_t:
            self._index = (self._index + 1) % len(self._transitions)
        self._last_t = t
        return self._transitions[self._index].frame_at(
            t, canvas, outgoing, incoming, **kwargs
        )
