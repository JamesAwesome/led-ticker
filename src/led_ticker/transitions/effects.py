"""Instant, flash, dissolve, split, and scroll transition effects."""

import functools
from typing import Any

from led_ticker._types import Canvas, ColorTuple
from led_ticker.separator import (
    DEFAULT_DOT_SPEC,
    SCROLL_GAP,
    render_separator,
    scroll_separator_width,
)
from led_ticker.transitions import _OutgoingScaleSweep, _phys, register_transition

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
class SplitHorizontal(_OutgoingScaleSweep):
    """Center-outward expanding black band with edge lines."""

    def __init__(self, **kwargs: Any) -> None:
        pass

    def frame_at(
        self, t: float, canvas: Canvas, outgoing: Any, incoming: Any, **kwargs: Any
    ) -> Canvas:
        real, rw, rh, scale, _yo = _phys(canvas)
        outgoing_scroll_pos: int = kwargs.get("outgoing_scroll_pos", 0)
        # Sweep geometry in physical columns so the band spans the full panel.
        half = rw // 2
        reveal = int(t * half)

        if t >= 1.0:
            incoming.draw(canvas, cursor_pos=0)
        elif reveal <= 0:
            outgoing.draw(canvas, cursor_pos=outgoing_scroll_pos)
        else:
            outgoing.draw(canvas, cursor_pos=outgoing_scroll_pos)
            left = half - reveal
            right = half + reveal
            # Black out center band at full physical height.
            band_x = max(0, left)
            band_w = min(right, rw) - band_x
            if band_w > 0:
                real.SubFill(band_x, 0, band_w, rh, 0, 0, 0)
            # Magenta edge lines spanning full physical height.
            for y in range(rh):
                if 0 <= left < rw:
                    real.SetPixel(left, y, 255, 0, 255)
                if 0 <= right - 1 < rw:
                    real.SetPixel(right - 1, y, 255, 0, 255)
        return canvas


@register_transition("scroll")
class Scroll(_OutgoingScaleSweep):
    """Seamless continuous scroll with bullet separator.

    Outgoing, bullet, and incoming scroll left together as one
    continuous strip — like ticker mode between two widgets.
    The bullet (" * ") separates the two texts visually.

    Recommended: transition_duration = 4.0, easing = "linear".

    Note: Scroll inherits _OutgoingScaleSweep for `scale_switch_at = 1.0`
    but deliberately does NOT use `_phys` or physical-resolution geometry.
    There is no persistent sweep bar or blackout edge — content scrolls
    seamlessly, and `run_transition` already `Clear()`s the full real panel
    before each `frame_at` call. Using logical canvas dimensions here is
    intentional and correct; do not "fix" this to use `_phys`.
    """

    def __init__(self, **kwargs: Any) -> None:
        self._spec = DEFAULT_DOT_SPEC
        self._sep_w: int = scroll_separator_width(self._spec)
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
            canvas.SubFill(clear_start, 0, w - clear_start, h, 0, 0, 0)

        render_separator(canvas, bullet_x, scroll_offset, self._spec)

        if incoming_pos < w:
            incoming.draw(canvas, cursor_pos=incoming_pos)

        return canvas
