"""Wipe-based transition effects."""

import random
from typing import Any

from led_ticker._types import Canvas, ColorTuple
from led_ticker.transitions import register_transition


class _BaseWipe:
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
        w = canvas.width
        h = getattr(canvas, "height", 16)
        outgoing_scroll_pos: int = kwargs.get("outgoing_scroll_pos", 0)
        # Sweep line moves from bottom (h-1) to top (0)
        sweep_row = max(0, h - 1 - min(int(t * h), h - 1))

        if t >= 1.0:
            incoming.draw(canvas, cursor_pos=0)
        else:
            outgoing.draw(canvas, cursor_pos=outgoing_scroll_pos)
            # Black out rows below sweep (erased region)
            if sweep_row < h - 1:
                canvas.SubFill(0, sweep_row + 1, w, h - sweep_row - 1, 0, 0, 0)
            # Sweep line (2px thick)
            for dy in range(2):
                row = sweep_row + dy
                if 0 <= row < h:
                    for x in range(w):
                        canvas.SetPixel(x, row, *self.color)
        return canvas


@register_transition("wipe_left")
class WipeLeft(_BaseWipe):
    """Right-to-left wipe — sweep moves toward the left."""

    DEFAULT_COLOR: ColorTuple = (0, 255, 255)

    def frame_at(
        self, t: float, canvas: Canvas, outgoing: Any, incoming: Any, **kwargs: Any
    ) -> Canvas:
        w = canvas.width
        h = getattr(canvas, "height", 16)
        outgoing_scroll_pos: int = kwargs.get("outgoing_scroll_pos", 0)
        boundary = min(int(t * (w + 1)), w)

        if t >= 1.0:
            incoming.draw(canvas, cursor_pos=0)
        else:
            outgoing.draw(canvas, cursor_pos=outgoing_scroll_pos)
            line_x = w - boundary
            # Black out right of sweep line (erased region)
            if boundary > 0:
                canvas.SubFill(line_x, 0, w - line_x, h, 0, 0, 0)
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

    DEFAULT_COLOR: ColorTuple = (255, 0, 255)

    def frame_at(
        self, t: float, canvas: Canvas, outgoing: Any, incoming: Any, **kwargs: Any
    ) -> Canvas:
        w = canvas.width
        h = getattr(canvas, "height", 16)
        outgoing_scroll_pos: int = kwargs.get("outgoing_scroll_pos", 0)
        boundary = min(int(t * (w + 1)), w)

        if t >= 1.0:
            incoming.draw(canvas, cursor_pos=0)
        else:
            outgoing.draw(canvas, cursor_pos=outgoing_scroll_pos)
            # Black out left of boundary (erased region)
            if boundary > 0:
                canvas.SubFill(0, 0, boundary, h, 0, 0, 0)
            # Sweep line at boundary
            sweep_w = min(2, w - boundary)
            if sweep_w > 0:
                for y in range(h):
                    for dx in range(sweep_w):
                        canvas.SetPixel(boundary + dx, y, *self.color)
        return canvas


@register_transition("wipe_down")
class WipeDown(_BaseWipe):
    """Top-to-bottom wipe with sweep line moving downward (formerly 'curtain')."""

    DEFAULT_COLOR: ColorTuple = (0, 255, 0)
    min_frames: int = 16

    def frame_at(
        self, t: float, canvas: Canvas, outgoing: Any, incoming: Any, **kwargs: Any
    ) -> Canvas:
        w = canvas.width
        h = getattr(canvas, "height", 16)
        outgoing_scroll_pos: int = kwargs.get("outgoing_scroll_pos", 0)
        sweep_row = min(int(t * (h + 1)), h)

        if t >= 1.0:
            incoming.draw(canvas, cursor_pos=0)
        else:
            outgoing.draw(canvas, cursor_pos=outgoing_scroll_pos)
            # Black out rows above sweep (erased region)
            if sweep_row > 0:
                canvas.SubFill(0, 0, w, min(sweep_row, h), 0, 0, 0)
            # Sweep line (2px thick)
            for dy in range(2):
                row = sweep_row - dy
                if 0 <= row < h:
                    for x in range(w):
                        canvas.SetPixel(x, row, *self.color)
        return canvas


@register_transition("wipe_random")
class WipeRandom:
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
class WipeAlternating:
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
