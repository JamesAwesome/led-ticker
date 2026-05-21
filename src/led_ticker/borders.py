"""Border effects — animated perimeter outlines for TickerMessage.

Mirrors the `color_providers` design but for the panel perimeter
instead of text characters. A `BorderEffect` paints a 1-or-2-pixel
ring around the panel edge at PHYSICAL resolution (bypasses
`ScaledCanvas`'s scale × scale block expansion via `unwrap_to_real`)
so a 1-px border on bigsign actually draws as 1 real LED, not a 4×4
block.

Three flavors today:

- `RainbowChaseBorder` — per-pixel hue indexed by perimeter position
  (clockwise from top-left, hop count 0..N-1) advancing per frame.
  Same `((idx * char_offset) + frame * speed) % 360` formula
  `Rainbow.color_for` uses for letters, just indexed differently.
- `ColorCycleBorder` — whole-border single animated hue. The entire
  perimeter is one color per frame; the hue advances by `speed`
  degrees per frame. Optionally restricted to a hue arc via
  `from_hue` / `to_hue` (shorter-arc sweep, same semantics as the
  `ColorCycle` text provider). Complement to `RainbowChaseBorder`
  (which varies hue per perimeter pixel; this does not).
- `ConstantBorder` — solid-color outline; no animation. Marked
  `frame_invariant=True` so the static-text fast path in image
  widgets (and any future BorderEffect-aware fast paths) can opt
  out of per-tick redraws.

The `BorderEffect` Protocol exposes:
- `paint(canvas, frame_count)` — paints the perimeter on `canvas`.
  The host widget passes `self.frame_for("border")` so the effect
  ticks with its own per-effect counter (visit-resets honor
  `restart_on_visit`, transition pauses freeze the count).
- `frame_invariant: bool` — whether `paint` produces the same output
  every frame. Constant=True; rainbow chase=False.

Consumed by `TickerMessage`, `TickerCountdown`, `TwoRowMessage`,
`GifPlayer`, and `StillImage`. The API is generic — adding to a
future widget is just wiring the field + dispatch, no protocol
changes.

**Static-text fast-path contract**: any widget that BOTH owns its
own render loop AND accepts `border` must include
`border.frame_invariant` in its fast-path predicate (same shape as
the existing `font_color.frame_invariant` check) — otherwise a
`RainbowChaseBorder` would silently freeze on the paint-once-and-
sleep path. Current consumers of this contract:
`_BaseImageWidget._play_with_text`, `_play_with_two_row_text`, and
`StillImage._play_no_text`. The shared predicate is
`getattr(self.border, "frame_invariant", True) if self.border else True`
— `True` (= "is static, allow fast path") when border is None or
explicitly frame-invariant. Same contract applies to any future
effect class that drives per-frame output on a render surface.

**`restart_on_visit` convention**: effect classes that want
continuous phase across `loop_count > 1` iterations of a section
set `restart_on_visit: bool = False` as a class attribute. Read
by `_FrameAware.reset_frame` in `widgets/_frame_aware.py`. Default `True` (via
`getattr` fallback) keeps today's "every visit = fresh start"
behavior for unknown effect classes. `RainbowChaseBorder` opts
out (continuous chase); `ConstantBorder` keeps the default
(frame-invariant, so the value is a no-op).
"""

from __future__ import annotations

import colorsys
from typing import Any, Protocol

from led_ticker._types import Canvas
from led_ticker.scaled_canvas import unwrap_to_real


class BorderEffectBase:
    """Optional base for BorderEffect implementations.

    Enforces that every subclass declares ``frame_invariant`` explicitly
    (class attribute or ``@property``) so the fast-path predicate in
    image widgets cannot silently freeze an animated border. Analogous
    to ``ColorProviderBase`` — see its docstring for the full rationale.
    """

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        if "frame_invariant" not in cls.__dict__:
            raise TypeError(
                f"{cls.__name__} must define 'frame_invariant' as a class "
                "attribute or property. Set True if paint() output is "
                "frame-independent (ConstantBorder); False if it varies per "
                "frame (RainbowChaseBorder, ColorCycleBorder)."
            )


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


class RainbowChaseBorder(BorderEffectBase):
    """Per-pixel rainbow chase around the perimeter.

    Without `from_hue`/`to_hue`, hue at perimeter index `idx` and
    frame `f` is:

        hue = ((idx * char_offset) + f * speed) % 360

    With `from_hue`/`to_hue` (shorter-arc restriction), the formula
    maps the same index+frame value into the arc:

        phase = (idx * char_offset + f * speed) % arc_width
        hue   = from_hue + phase        (arc_width > 0, forward arc)
        hue   = from_hue - phase        (arc_width < 0, backward arc)

    where `arc_width = (to_hue - from_hue) % 360`, adjusted to the
    shorter arc (< 180°). `char_offset` controls how many full arc
    widths tile around the perimeter — the same density semantics as
    the full-wheel case, just measured in arc-degrees instead of 360°.

    Defaults are tuned for bigsign-scale panels (256+64+256+64 = 640
    perimeter pixels at scale=4) so the chase moves at a comfortable
    pace and the rainbow tiles a few times around the perimeter.

    `speed = 4` advances the chase 4° per frame (~12s for one full
    revolution at 50ms/frame). `char_offset = 6` gives ~60 distinct
    hue cycles around the 640-pixel perimeter — visually dense
    enough to read as "rainbow" rather than "two-color gradient".
    With a narrow arc, the same `char_offset` tiles more full
    arc-cycles around the edge. `thickness = 1` is a 1-pixel border;
    `2` is a 2-pixel ring.

    `frame_invariant` is dynamic: True only when `speed == 0` (the
    chase doesn't advance per frame, so paint output is identical
    every tick). `char_offset` doesn't affect frame-invariance — it
    indexes by perimeter position, not by frame.
    """

    # Continuous chase: phase advances across loop_count boundaries
    # within a section. See `_FrameAware.reset_frame` in widgets/_frame_aware.py.
    restart_on_visit: bool = False

    def __init__(
        self,
        speed: int = 4,
        char_offset: int = 6,
        thickness: int = 1,
        from_hue: float | None = None,
        to_hue: float | None = None,
    ) -> None:
        self.speed = speed
        self.char_offset = char_offset
        self.thickness = thickness
        if from_hue is not None and to_hue is not None:
            diff = (to_hue - from_hue) % 360
            if diff > 180:
                diff -= 360
            self._from_hue: float = from_hue
            self._arc: float = diff
        else:
            self._from_hue = 0.0
            self._arc = 360.0  # sentinel: full wheel

    @property
    def frame_invariant(self) -> bool:
        return self.speed == 0

    def paint(self, canvas: Canvas, frame_count: int) -> None:
        real = unwrap_to_real(canvas)
        arc = self._arc if self._arc != 0 else 360.0
        abs_arc = abs(arc)
        for idx, (x, y) in enumerate(
            _perimeter_pixels(real.width, real.height, self.thickness)
        ):
            phase = (idx * self.char_offset + frame_count * self.speed) % abs_arc
            if arc < 0:
                hue = (self._from_hue - phase) % 360
            else:
                hue = (self._from_hue + phase) % 360
            r, g, b = colorsys.hsv_to_rgb(hue / 360.0, 1.0, 1.0)
            real.SetPixel(x, y, int(r * 255), int(g * 255), int(b * 255))


class ColorCycleBorder(BorderEffectBase):
    """Whole-border single animated hue.

    The entire perimeter is painted with one color per frame; the hue
    advances by `speed` degrees per frame. Optionally restricted to a
    hue arc via `from_hue` / `to_hue` (shorter-arc sweep, same
    semantics as `ColorCycle`). Without `from_hue` / `to_hue` the
    sweep covers the full 360° wheel.

    Complement to `RainbowChaseBorder` — that varies hue per perimeter
    pixel; this paints every pixel the same color and cycles over time.

    `speed = 0` is rejected at config-load (raises ValueError). Use
    `border = [r, g, b]` for a static single-color border instead."""

    frame_invariant: bool = False
    restart_on_visit: bool = False

    def __init__(
        self,
        speed: int = 5,
        from_hue: float | None = None,
        to_hue: float | None = None,
        thickness: int = 1,
    ) -> None:
        self.speed = speed
        self.thickness = thickness
        if from_hue is not None and to_hue is not None:
            diff = (to_hue - from_hue) % 360
            if diff > 180:
                diff -= 360
            self._from_hue: float = from_hue
            self._span: float = diff
        else:
            self._from_hue = 0.0
            self._span = 360.0

    def paint(self, canvas: Canvas, frame_count: int) -> None:
        span = self._span if self._span != 0 else 360.0
        progress = (frame_count * self.speed) % abs(span)
        if span < 0:
            hue = (self._from_hue - progress) % 360
        else:
            hue = (self._from_hue + progress) % 360
        r, g, b = colorsys.hsv_to_rgb(hue / 360.0, 1.0, 1.0)
        real = unwrap_to_real(canvas)
        ri, gi, bi = int(r * 255), int(g * 255), int(b * 255)
        for x, y in _perimeter_pixels(real.width, real.height, self.thickness):
            real.SetPixel(x, y, ri, gi, bi)


class ConstantBorder(BorderEffectBase):
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
