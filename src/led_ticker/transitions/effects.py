"""Instant, flash, dissolve, split, and scroll transition effects."""

from __future__ import annotations

from typing import Any

from led_ticker._types import Canvas, ColorTuple
from led_ticker.transitions import register_transition


@register_transition("cut")
class Cut:
    """Instant switch, no animation."""

    def __init__(self, **kwargs: Any) -> None:
        pass

    def frame_at(
        self, t: float, canvas: Canvas, outgoing: Any, incoming: Any, **kwargs: Any
    ) -> Canvas:
        incoming.draw(canvas, cursor_pos=0)
        return canvas


@register_transition("color_flash")
class ColorFlash:
    """Brief solid color flash between old and new content."""

    def __init__(self, color: ColorTuple | None = None, **kwargs: Any) -> None:
        c = color
        self.color: ColorTuple = (c[0], c[1], c[2]) if c else (255, 255, 255)

    def frame_at(
        self, t: float, canvas: Canvas, outgoing: Any, incoming: Any, **kwargs: Any
    ) -> Canvas:
        outgoing_scroll_pos: int = kwargs.get("outgoing_scroll_pos", 0)
        if t < 0.33:
            outgoing.draw(canvas, cursor_pos=outgoing_scroll_pos)
        elif t < 0.66:
            canvas.Fill(*self.color)
        else:
            incoming.draw(canvas, cursor_pos=0)
        return canvas


@register_transition("dissolve")
class Dissolve:
    """Random pixel scatter dissolve.

    Pre-computes a shuffled pixel sequence at first use, then slices
    it per frame — avoids per-frame RNG overhead on the Pi.
    """

    def __init__(self, seed: int = 42, **kwargs: Any) -> None:
        self.seed: int = seed
        self._sequence: list[tuple[int, int]] | None = None

    def _get_sequence(self, w: int, h: int) -> list[tuple[int, int]]:
        if self._sequence is None or len(self._sequence) != w * h:
            import random

            rng = random.Random(self.seed)
            coords = [(x, y) for y in range(h) for x in range(w)]
            rng.shuffle(coords)
            self._sequence = coords
        return self._sequence

    def frame_at(
        self, t: float, canvas: Canvas, outgoing: Any, incoming: Any, **kwargs: Any
    ) -> Canvas:
        w = canvas.width
        h = getattr(canvas, "height", 16)
        outgoing_scroll_pos: int = kwargs.get("outgoing_scroll_pos", 0)
        skip_final_incoming: bool = kwargs.get("skip_final_incoming", False)

        if t >= 1.0:
            if not skip_final_incoming:
                incoming.draw(canvas, cursor_pos=0)
            # else: leave the canvas cleared; the caller's next render
            # (the new section's first draw at its correct scale) handles
            # showing the incoming widget without a wrong-scale flash.
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
            elif skip_final_incoming:
                # Don't reveal the incoming widget at the wrong scale; the
                # canvas is already cleared from run_transition's loop.
                pass
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

    def __init__(self, **kwargs: Any) -> None:
        pass

    def frame_at(
        self, t: float, canvas: Canvas, outgoing: Any, incoming: Any, **kwargs: Any
    ) -> Canvas:
        w = canvas.width
        h = getattr(canvas, "height", 16)
        outgoing_scroll_pos: int = kwargs.get("outgoing_scroll_pos", 0)
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


@register_transition("scroll")
class Scroll:
    """Seamless continuous scroll with bullet separator.

    Outgoing, bullet, and incoming scroll left together as one
    continuous strip — like forever_scroll between two widgets.
    The bullet (" * ") separates the two texts visually.

    Recommended: transition_duration = 4.0, easing = "linear".
    """

    def __init__(self, **kwargs: Any) -> None:
        from led_ticker.ticker import SCROLL_GAP, scroll_separator_width

        self._sep_w: int = scroll_separator_width()
        self._gap: int = SCROLL_GAP

    def frame_at(
        self, t: float, canvas: Canvas, outgoing: Any, incoming: Any, **kwargs: Any
    ) -> Canvas:
        from led_ticker.ticker import _draw_scroll_frame

        w = canvas.width
        outgoing_scroll_pos: int = kwargs.get("outgoing_scroll_pos", 0)

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
            canvas,
            outgoing,
            incoming,
            outgoing_pos,
            bullet_x,
            incoming_pos,
            clear_start,
        )

        return canvas
