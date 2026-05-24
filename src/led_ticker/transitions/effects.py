"""Instant, flash, dissolve, split, and scroll transition effects."""

from __future__ import annotations

import functools
from typing import Any

from led_ticker._types import Canvas, ColorTuple
from led_ticker.transitions import register_transition

# ColorFlash phase thresholds
_FLASH_ONSET: float = 1 / 3
_FLASH_FADEOUT: float = 2 / 3


@functools.cache
def _dissolve_sequence(w: int, h: int, seed: int) -> list[tuple[int, int]]:
    import random

    rng = random.Random(seed)
    coords = [(x, y) for y in range(h) for x in range(w)]
    rng.shuffle(coords)
    return coords


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
        if t < _FLASH_ONSET:
            outgoing.draw(canvas, cursor_pos=outgoing_scroll_pos)
        elif t < _FLASH_FADEOUT:
            canvas.Fill(*self.color)
        else:
            incoming.draw(canvas, cursor_pos=0)
        return canvas


@register_transition("dissolve")
class Dissolve:
    """Random pixel scatter dissolve.

    Pre-computes a shuffled pixel sequence at first use, then slices
    it per frame — avoids per-frame RNG overhead on the Pi.

    The scatter operates on the UNDERLYING real canvas (bypassing any
    ScaledCanvas wrapper) so the granularity matches native pixels.
    Without this, the dissolve at scale=4 would only have 64×16=1024
    logical pixels, each becoming a 4×4 block — at t=0.5 every block
    blacks out (count == total), turning the "dissolve" into a fade-
    through-black. On the bigsign the gif widget paints at physical
    resolution; the dissolve must too, or the gif appears to wipe
    rather than melt into the next frame.
    """

    def __init__(self, seed: int = 42, **kwargs: Any) -> None:
        self.seed: int = seed

    def _get_sequence(self, w: int, h: int) -> list[tuple[int, int]]:
        return _dissolve_sequence(w, h, self.seed)

    def frame_at(
        self, t: float, canvas: Canvas, outgoing: Any, incoming: Any, **kwargs: Any
    ) -> Canvas:
        # Scatter at physical resolution. `unwrap_to_real` checks the type
        # via isinstance so Mock canvases (which auto-generate attribute
        # access) don't get treated as wrappers in tests.
        from led_ticker.scaled_canvas import unwrap_to_real

        real = unwrap_to_real(canvas)
        w = real.width
        h = real.height
        outgoing_scroll_pos: int = kwargs.get("outgoing_scroll_pos", 0)

        if t >= 1.0:
            incoming.draw(canvas, cursor_pos=0)
        elif t <= 0.0:
            outgoing.draw(canvas, cursor_pos=outgoing_scroll_pos)
        else:
            seq = self._get_sequence(w, h)
            total = len(seq)
            # Physical-grain SetPixel: at scale=4 this is 16× more pixels
            # than the wrapper's logical SetPixel would touch, but at
            # peak (t=0.5) the wrapper's `count` already equaled `total`
            # — meaning EVERY logical block was blacked out, i.e. a fade-
            # through-black. Going physical recovers the actual scatter.
            set_px = real.SetPixel
            if t < 0.5:
                # Outgoing with increasing black scatter
                outgoing.draw(canvas, cursor_pos=outgoing_scroll_pos)
                count = int(t * 2 * total)
            else:
                # Incoming with decreasing black scatter
                incoming.draw(canvas, cursor_pos=0)
                count = int((1.0 - t) * 2 * total)
            # Iterate by index to avoid allocating `seq[:count]` per frame.
            # On the bigsign at t=0.5 that slice is ~8K tuples × 20fps.
            for i in range(count):
                x, y = seq[i]
                set_px(x, y, 0, 0, 0)
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
        w = canvas.width
        h = getattr(canvas, "height", 16)
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

        outgoing.draw(canvas, cursor_pos=outgoing_pos)

        # Black out the tail region so outgoing text doesn't bleed
        # into the gap between outgoing and the bullet.
        if 0 <= clear_start < w:
            for y in range(h):
                for x in range(clear_start, w):
                    canvas.SetPixel(x, y, 0, 0, 0)

        # Bullet: 2×2 white dot centered vertically.
        y_center = h // 2
        for dy in range(-1, 1):
            for dx in range(2):
                px = bullet_x + dx
                py = y_center + dy
                if 0 <= px < w and 0 <= py < h:
                    canvas.SetPixel(px, py, 255, 255, 255)

        if incoming_pos < w:
            incoming.draw(canvas, cursor_pos=incoming_pos)

        return canvas
