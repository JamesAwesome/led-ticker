"""Border effects — animated perimeter outlines for TickerMessage.

Mirrors the `color_providers` design but for the panel perimeter
instead of text characters. A `BorderEffect` paints a 1-or-2-pixel
ring around the panel edge at PHYSICAL resolution (bypasses
`ScaledCanvas`'s scale × scale block expansion via `unwrap_to_real`)
so a 1-px border on bigsign actually draws as 1 real LED, not a 4×4
block.

Two flavors today:

- `RainbowChaseBorder` — per-pixel hue indexed by perimeter position
  (clockwise from top-left, hop count 0..N-1) advancing per frame.
  Same `((idx * char_offset) + frame * speed) % 360` formula
  `Rainbow.color_for` uses for letters, just indexed differently.
- `ConstantBorder` — solid-color outline; no animation. Marked
  `frame_invariant=True` so the static-text fast path in image
  widgets (and any future BorderEffect-aware fast paths) can opt
  out of per-tick redraws.

The `BorderEffect` Protocol exposes:
- `paint(canvas, frame_count)` — paints the perimeter on `canvas`.
  Reads from `_FrameAware._frame_count` so the effect ticks with
  the host widget's animation state (visit-resets, transition
  pauses).
- `frame_invariant: bool` — whether `paint` produces the same output
  every frame. Constant=True; rainbow chase=False.

Currently consumed only by `TickerMessage` (per the v1 scope), but
the API is generic — adding to `TickerCountdown` or a future widget
is just wiring the field + dispatch, no protocol changes.

**Static-text fast-path note**: `_BaseImageWidget._play_with_text`
gates its paint-once-and-sleep fast path on `font_color.frame_invariant`
only. Image widgets don't accept `border` today, so this is fine.
But: if a future widget BOTH owns its own render loop AND accepts
`border`, that fast-path predicate must additionally check
`border.frame_invariant` — otherwise a `RainbowChaseBorder` would
silently freeze on the held-text fast path. Ditto for any future
effect class that drives per-frame output on TickerMessage's render
surface.
"""

from __future__ import annotations

import colorsys
from typing import Any, Protocol

from led_ticker._types import Canvas
from led_ticker.scaled_canvas import unwrap_to_real


class BorderEffect(Protocol):
    """Paints a perimeter outline on `canvas` at frame-aware state."""

    frame_invariant: bool

    def paint(self, canvas: Canvas, frame_count: int) -> None: ...


def _perimeter_pixels(
    width: int,
    height: int,
    thickness: int = 1,
) -> list[tuple[int, int]]:
    """Return the list of `(x, y)` tuples on the panel perimeter.

    Clockwise starting from top-left. Each pixel appears EXACTLY ONCE
    (corners are not double-counted — the function walks
    top-edge → right-edge → bottom-edge → left-edge with each edge
    excluding the corner already claimed by the prior edge).

    For `thickness > 1`, returns multiple concentric rings (outer
    first, inner last). Each ring has its own clockwise sequence so
    `enumerate(_perimeter_pixels(...))` gives a continuous index
    from outer-corner around → inner ring 1 → inner ring 2 etc.

    The perimeter geometry is in PHYSICAL panel coordinates — feed
    `width = canvas.real.width` and `height = canvas.real.height`
    when working from a `ScaledCanvas`. (`paint` does this for you.)
    """
    pixels: list[tuple[int, int]] = []
    for ring in range(thickness):
        # Inset each ring by `ring` pixels from the outer edge.
        x0 = ring
        y0 = ring
        x1 = width - 1 - ring
        y1 = height - 1 - ring
        # Bail when the ring would degenerate to a single column or
        # row (`x1 == x0` or `y1 == y0`): the right-edge and left-edge
        # walks would traverse the same column twice (and similarly
        # for top/bottom on a 1-row ring), producing duplicate pixels
        # in the output. Painting a duplicated pixel twice with two
        # different hues from the chase formula produces last-write-
        # wins-and-misaligns-the-pattern artifacts. Skipping is the
        # right call — a 1-px-wide ring isn't visually meaningful as
        # a border anyway. Latent on healthy aspect ratios; surfaces
        # on degenerate cases like `_perimeter_pixels(3, 10, 2)`.
        if x1 <= x0 or y1 <= y0:
            break  # ring collapsed (panel too small for thickness)
        # Top edge: (x0..x1-1, y0)
        for x in range(x0, x1):
            pixels.append((x, y0))
        # Right edge: (x1, y0..y1-1)
        for y in range(y0, y1):
            pixels.append((x1, y))
        # Bottom edge: (x1..x0+1, y1) — reversed so we go right-to-left
        for x in range(x1, x0, -1):
            pixels.append((x, y1))
        # Left edge: (x0, y1..y0+1) — reversed so we go bottom-to-top
        for y in range(y1, y0, -1):
            pixels.append((x0, y))
    return pixels


class RainbowChaseBorder:
    """Per-pixel rainbow chase around the perimeter.

    Hue at perimeter index `idx` and frame `f` is:

        hue = ((idx * char_offset) + f * speed) % 360

    Defaults are tuned for bigsign-scale panels (256+64+256+64 = 640
    perimeter pixels at scale=4) so the chase moves at a comfortable
    pace and the rainbow tiles a few times around the perimeter.

    `speed = 4` advances the chase 4° per frame (~12s for one full
    revolution at 50ms/frame). `char_offset = 6` gives ~60 distinct
    hue cycles around the 640-pixel perimeter — visually dense
    enough to read as "rainbow" rather than "two-color gradient".
    `thickness = 1` is a 1-pixel border; `2` is a 2-pixel ring.

    `frame_invariant` is dynamic: True only when `speed == 0` (the
    chase doesn't advance per frame, so paint output is identical
    every tick). Lets a future fast-path gate skip per-tick redraws
    on a pinned rainbow without animation. `char_offset` doesn't
    affect frame-invariance — it indexes by perimeter position, not
    by frame, so the per-pixel pattern still varies even with
    `char_offset = 0` if `speed > 0`.
    """

    def __init__(
        self,
        speed: int = 4,
        char_offset: int = 6,
        thickness: int = 1,
    ) -> None:
        self.speed = speed
        self.char_offset = char_offset
        self.thickness = thickness

    @property
    def frame_invariant(self) -> bool:
        return self.speed == 0

    def paint(self, canvas: Canvas, frame_count: int) -> None:
        real = unwrap_to_real(canvas)
        for idx, (x, y) in enumerate(
            _perimeter_pixels(real.width, real.height, self.thickness)
        ):
            hue = ((idx * self.char_offset) + frame_count * self.speed) % 360
            r, g, b = colorsys.hsv_to_rgb(hue / 360.0, 1.0, 1.0)
            real.SetPixel(x, y, int(r * 255), int(g * 255), int(b * 255))


class ConstantBorder:
    """Solid-color perimeter outline; no animation."""

    frame_invariant: bool = True

    def __init__(self, color: Any, thickness: int = 1) -> None:
        # `color` accepts either a `graphics.Color` or an `(r, g, b)`
        # tuple. Materialize to (r, g, b) at construction so paint()
        # is hot-loop friendly — no per-pixel attribute access.
        if hasattr(color, "red"):
            self._rgb = (color.red, color.green, color.blue)
        else:
            self._rgb = tuple(color)
        self.thickness = thickness

    def paint(self, canvas: Canvas, frame_count: int) -> None:
        del frame_count  # constant — frame doesn't matter
        real = unwrap_to_real(canvas)
        r, g, b = self._rgb
        for x, y in _perimeter_pixels(real.width, real.height, self.thickness):
            real.SetPixel(x, y, r, g, b)
