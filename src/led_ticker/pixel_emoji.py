# ruff: noqa: E501
"""Pixel art emoji for inline rendering in text.

Use `:slug:` in any TickerMessage text to render a pixel art icon.
Example: ":baseball: MLB Scores" renders a baseball icon then text.

Each emoji is a list of (x, y, r, g, b) tuples relative to origin.

Two resolutions are supported:

1. **Low-res (8×8 logical)** — `EMOJI_REGISTRY`. Coordinates are
   logical-canvas pixels. On a `ScaledCanvas` each pixel is expanded to
   a `scale × scale` block, so an 8×8 emoji at scale=4 occupies
   32×32 physical LEDs. Works on every canvas (small sign, bigsign).

2. **Hi-res (e.g. 32×32 physical)** — `HIRES_REGISTRY`. Coordinates are
   PHYSICAL pixels and the renderer paints directly to the underlying
   real canvas, bypassing the wrapper's block expansion. The same
   horizontal footprint as the equivalent 8×8 emoji at the wrapper's
   scale, but with `scale²×` more detail. Falls back to the low-res
   version if no `ScaledCanvas` is in use.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from led_ticker._types import Canvas, Color, Font, PixelData
from led_ticker.text_render import draw_text

if TYPE_CHECKING:
    from led_ticker.scaled_canvas import ScaledCanvas

EMOJI_DEFAULT_WIDTH: int = 8
EMOJI_PADDING: int = 2  # px after icon before text resumes


@dataclass(frozen=True)
class HiResEmoji:
    """A high-resolution emoji that paints directly to a real canvas.

    `pixels` are stored in PHYSICAL coordinates (e.g. 0-31 for a 32×32
    sprite). When rendered on a ScaledCanvas with `scale=N`, the sprite
    occupies the same horizontal logical-width as a low-res emoji of
    `physical_size // N` (so a 32×32 sprite at scale=4 takes 8 logical
    columns — same as an 8×8 low-res emoji).
    """

    pixels: tuple[tuple[int, int, int, int, int], ...]
    physical_size: int  # e.g. 32 means 32×32

    def logical_width(self, scale: int) -> int:
        return self.physical_size // max(1, scale)


def _emoji_width(icon: PixelData) -> int:
    """Compute the width of an icon from its pixel data."""
    if not icon:
        return 0
    return max(px for px, _, _, _, _ in icon) + 1


# ⚾ Baseball — white ball with two vertical red stitch lines
# Inspired by classic pixel baseball sprites: stitches run vertically
# through the center, curving outward at top and bottom.
_W = (240, 240, 240)  # white fill
_B = (255, 255, 255)  # bright white edge
_R = (200, 20, 20)  # red stitching
BASEBALL: PixelData = [
    # Row 0: top of ball
    (2, 0, *_B),
    (3, 0, *_B),
    (4, 0, *_B),
    (5, 0, *_B),
    # Row 1: stitches curve outward at top
    (1, 1, *_B),
    (2, 1, *_R),
    (3, 1, *_W),
    (4, 1, *_W),
    (5, 1, *_R),
    (6, 1, *_B),
    # Row 2: stitches widen
    (0, 2, *_B),
    (1, 2, *_W),
    (2, 2, *_R),
    (3, 2, *_W),
    (4, 2, *_W),
    (5, 2, *_R),
    (6, 2, *_W),
    (7, 2, *_B),
    # Row 3: two vertical stitch lines
    (0, 3, *_B),
    (1, 3, *_W),
    (2, 3, *_R),
    (3, 3, *_W),
    (4, 3, *_W),
    (5, 3, *_R),
    (6, 3, *_W),
    (7, 3, *_B),
    # Row 4: two vertical stitch lines
    (0, 4, *_B),
    (1, 4, *_W),
    (2, 4, *_R),
    (3, 4, *_W),
    (4, 4, *_W),
    (5, 4, *_R),
    (6, 4, *_W),
    (7, 4, *_B),
    # Row 5: stitches widen
    (0, 5, *_B),
    (1, 5, *_W),
    (2, 5, *_R),
    (3, 5, *_W),
    (4, 5, *_W),
    (5, 5, *_R),
    (6, 5, *_W),
    (7, 5, *_B),
    # Row 6: stitches curve outward at bottom
    (1, 6, *_B),
    (2, 6, *_R),
    (3, 6, *_W),
    (4, 6, *_W),
    (5, 6, *_R),
    (6, 6, *_B),
    # Row 7: bottom of ball
    (2, 7, *_B),
    (3, 7, *_B),
    (4, 7, *_B),
    (5, 7, *_B),
]


# 🌮 Taco — wide landscape taco with filling peeking out top-left
_TK = (0, 0, 0)  # black outline
_TS = (230, 160, 50)  # orange shell
_TL = (200, 140, 40)  # lighter shell highlight
_TG = (40, 160, 40)  # green (lettuce)
_TR = (220, 40, 30)  # red (tomato)
_TM = (140, 70, 30)  # brown (meat)
TACO: PixelData = [
    # Row 0: filling peeks above shell
    (5, 0, *_TK),
    (6, 0, *_TK),
    (7, 0, *_TK),
    (8, 0, *_TK),
    # Row 1: filling — lettuce, tomato, meat, green
    (4, 1, *_TK),
    (5, 1, *_TR),
    (6, 1, *_TG),
    (7, 1, *_TM),
    (8, 1, *_TG),
    (9, 1, *_TK),
    # Row 2: shell curves up from right toward filling
    (3, 2, *_TK),
    (4, 2, *_TG),
    (5, 2, *_TM),
    (6, 2, *_TR),
    (7, 2, *_TG),
    (8, 2, *_TK),
    (9, 2, *_TS),
    (10, 2, *_TS),
    (11, 2, *_TK),
    # Row 3: shell wraps around, filling spills left
    (2, 3, *_TK),
    (3, 3, *_TG),
    (4, 3, *_TM),
    (5, 3, *_TS),
    (6, 3, *_TS),
    (7, 3, *_TS),
    (8, 3, *_TS),
    (9, 3, *_TS),
    (10, 3, *_TS),
    (11, 3, *_TL),
    (12, 3, *_TK),
    # Row 4: shell widens, filling visible on left
    (1, 4, *_TK),
    (2, 4, *_TR),
    (3, 4, *_TG),
    (4, 4, *_TS),
    (5, 4, *_TS),
    (6, 4, *_TS),
    (7, 4, *_TS),
    (8, 4, *_TL),
    (9, 4, *_TS),
    (10, 4, *_TS),
    (11, 4, *_TS),
    (12, 4, *_TK),
    # Row 5: widest shell, filling at left edge
    (0, 5, *_TK),
    (1, 5, *_TG),
    (2, 5, *_TS),
    (3, 5, *_TS),
    (4, 5, *_TS),
    (5, 5, *_TS),
    (6, 5, *_TS),
    (7, 5, *_TS),
    (8, 5, *_TS),
    (9, 5, *_TS),
    (10, 5, *_TS),
    (11, 5, *_TS),
    (12, 5, *_TS),
    (13, 5, *_TK),
    # Row 6: widest bottom with highlights
    (0, 6, *_TK),
    (1, 6, *_TS),
    (2, 6, *_TL),
    (3, 6, *_TS),
    (4, 6, *_TS),
    (5, 6, *_TS),
    (6, 6, *_TS),
    (7, 6, *_TS),
    (8, 6, *_TS),
    (9, 6, *_TL),
    (10, 6, *_TS),
    (11, 6, *_TS),
    (12, 6, *_TS),
    (13, 6, *_TK),
    # Row 7: wide bottom edge
    (0, 7, *_TK),
    (1, 7, *_TK),
    (2, 7, *_TK),
    (3, 7, *_TK),
    (4, 7, *_TK),
    (5, 7, *_TK),
    (6, 7, *_TK),
    (7, 7, *_TK),
    (8, 7, *_TK),
    (9, 7, *_TK),
    (10, 7, *_TK),
    (11, 7, *_TK),
    (12, 7, *_TK),
    (13, 7, *_TK),
]


# 📷 Instagram — rounded square camera body + lens ring + indicator dot.
# Uses the iconic Instagram magenta (#E1306C). On a dark LED panel the
# magenta reads more "pink" than on a screen, which suits the brand fine.
_IG = (225, 48, 108)
INSTAGRAM: PixelData = [
    # Row 0: top edge with rounded corners (no pixels at x=0,7)
    (1, 0, *_IG),
    (2, 0, *_IG),
    (3, 0, *_IG),
    (4, 0, *_IG),
    (5, 0, *_IG),
    (6, 0, *_IG),
    # Row 1: left/right walls + indicator dot at (5,1)
    (0, 1, *_IG),
    (5, 1, *_IG),
    (7, 1, *_IG),
    # Row 2: walls + lens top
    (0, 2, *_IG),
    (2, 2, *_IG),
    (3, 2, *_IG),
    (4, 2, *_IG),
    (5, 2, *_IG),
    (7, 2, *_IG),
    # Row 3: walls + lens left/right
    (0, 3, *_IG),
    (2, 3, *_IG),
    (5, 3, *_IG),
    (7, 3, *_IG),
    # Row 4: walls + lens left/right
    (0, 4, *_IG),
    (2, 4, *_IG),
    (5, 4, *_IG),
    (7, 4, *_IG),
    # Row 5: walls + lens bottom
    (0, 5, *_IG),
    (2, 5, *_IG),
    (3, 5, *_IG),
    (4, 5, *_IG),
    (5, 5, *_IG),
    (7, 5, *_IG),
    # Row 6: left/right walls
    (0, 6, *_IG),
    (7, 6, *_IG),
    # Row 7: bottom edge with rounded corners
    (1, 7, *_IG),
    (2, 7, *_IG),
    (3, 7, *_IG),
    (4, 7, *_IG),
    (5, 7, *_IG),
    (6, 7, *_IG),
]


# 🌸 8×8 Flower — pink petals around a yellow center, with a green stem
# and one leaf. Used for MLB Spring Training games (originally lived in
# widgets/mlb_icons.py, moved here as part of the DRY consolidation).
FLOWER: PixelData = [
    # Pink petals
    (2, 0, 255, 130, 170),
    (1, 1, 255, 130, 170),
    (3, 1, 255, 130, 170),
    (0, 2, 255, 130, 170),
    (2, 2, 255, 220, 50),  # yellow center
    (4, 2, 255, 130, 170),
    (1, 3, 255, 130, 170),
    (3, 3, 255, 130, 170),
    # Green stem
    (2, 4, 0, 180, 0),
    (2, 5, 0, 180, 0),
    (2, 6, 0, 150, 0),
    (2, 7, 0, 120, 0),
    # Leaf
    (3, 5, 0, 200, 0),
    (1, 6, 0, 200, 0),
]


# ⭐ 8×8 Star — algorithmically derived from the 32×32 hi-res star.
# Shape comes from generating a 5-point star polygon at 32×32, then
# downsampling 4× with a "majority-lit" threshold and mirror enforcement
# so the result is symmetric. Row 7 corner-leg pixels added manually
# so the star reaches the bottom of the canvas (the polygon math at
# 8×8 naturally falls 1 row short of filling the grid; without the
# corners the star floats with bottom margin).
#
# Algorithm (run once, output baked into the list below):
#   for x, y in STAR_HIRES.pixels: counts[y//4][x//4] += 1
#   for y, x in 8x8: lit if counts[y][x] >= 4 or counts[y][7-x] >= 4
#   then add row 7 corner-legs (cols 0,1,6,7).
_ST = (255, 215, 0)  # gold body
_SH = (255, 255, 80)  # brighter highlight at the inner cells
STAR: PixelData = [
    # Row 0: 1-px tip (col 3, slight left-lean since 8-cols has no true
    # center). Drops the previous 2x2 block at rows 0-1 that read as
    # "blocky" rather than pointy.
    (3, 0, *_ST),
    # Row 1: 2-px (cols 3-4) — broadens into the arms
    (3, 1, *_SH),
    (4, 1, *_SH),
    # Row 2: full-width horizontal arms (8-px)
    (0, 2, *_ST),
    (1, 2, *_ST),
    (2, 2, *_SH),
    (3, 2, *_SH),
    (4, 2, *_SH),
    (5, 2, *_SH),
    (6, 2, *_ST),
    (7, 2, *_ST),
    # Row 3: taper after arms (6-px, cols 1-6)
    (1, 3, *_ST),
    (2, 3, *_SH),
    (3, 3, *_SH),
    (4, 3, *_SH),
    (5, 3, *_SH),
    (6, 3, *_ST),
    # Row 4: body (4-px, cols 2-5)
    (2, 4, *_ST),
    (3, 4, *_SH),
    (4, 4, *_SH),
    (5, 4, *_ST),
    # Row 5: body continues (cols 2-5)
    (2, 5, *_ST),
    (3, 5, *_SH),
    (4, 5, *_SH),
    (5, 5, *_ST),
    # Row 6: legs split (cols 1-2 + 5-6)
    (1, 6, *_ST),
    (2, 6, *_ST),
    (5, 6, *_ST),
    (6, 6, *_ST),
    # Row 7: corner-legs (added so the star reaches the canvas bottom)
    (0, 7, *_ST),
    (1, 7, *_ST),
    (6, 7, *_ST),
    (7, 7, *_ST),
]


# 🌙 Crescent moon — generated by the SAME circle-subtraction algorithm as
# the hi-res 32×32 variant, so the 8×8 sprite reads as a downsampled
# version of it. Uniform 3-wide body with stair-stepped curves on both
# edges — closer to the hi-res shape than the previous hand-coded chunky
# C. Color is moonlight gold so it reads as "moon" rather than "sun"
# against pinks/lavender.
_MN = (255, 220, 130)


def _moon_8x8_pixels() -> list[tuple[int, int, int, int, int]]:
    """Generate the low-res :moon: by circle subtraction (same algorithm
    as the hi-res, tuned for an 8×8 grid).

    `outer_r=4.0` (full half-size) so all 8 rows fill — the hi-res's
    `size/2 - 0.5` inset would leave rows 0 and 7 empty at this size.
    `bite_offset=0.35` gives a uniform 3-wide crescent that matches the
    hi-res's ~28% body-to-canvas ratio.
    """
    cx = cy = 3.5
    outer_r = 4.0
    inner_cx = cx + 8 * 0.35  # = 6.3
    pixels: list[tuple[int, int, int, int, int]] = []
    for y in range(8):
        for x in range(8):
            d_outer_sq = (x - cx) ** 2 + (y - cy) ** 2
            d_inner_sq = (x - inner_cx) ** 2 + (y - cy) ** 2
            if d_outer_sq <= outer_r * outer_r and d_inner_sq > outer_r * outer_r:
                pixels.append((x, y, *_MN))
    return pixels


MOON: PixelData = _moon_8x8_pixels()


# ✉ Email — envelope with V-shaped flap. White so it reads on any
# background; widgets pass `color` for surrounding text but the icon
# carries its own color in the pixel data.
_EM = (240, 240, 240)
EMAIL: PixelData = [
    # Row 0: top edge
    (0, 0, *_EM),
    (1, 0, *_EM),
    (2, 0, *_EM),
    (3, 0, *_EM),
    (4, 0, *_EM),
    (5, 0, *_EM),
    (6, 0, *_EM),
    (7, 0, *_EM),
    # Row 1: walls + flap diagonals starting
    (0, 1, *_EM),
    (1, 1, *_EM),
    (6, 1, *_EM),
    (7, 1, *_EM),
    # Row 2: walls + flap diagonals
    (0, 2, *_EM),
    (2, 2, *_EM),
    (5, 2, *_EM),
    (7, 2, *_EM),
    # Row 3: walls + flap diagonals meet in middle
    (0, 3, *_EM),
    (3, 3, *_EM),
    (4, 3, *_EM),
    (7, 3, *_EM),
    # Row 4: walls (interior of envelope)
    (0, 4, *_EM),
    (7, 4, *_EM),
    # Row 5: walls
    (0, 5, *_EM),
    (7, 5, *_EM),
    # Row 6: walls
    (0, 6, *_EM),
    (7, 6, *_EM),
    # Row 7: bottom edge
    (0, 7, *_EM),
    (1, 7, *_EM),
    (2, 7, *_EM),
    (3, 7, *_EM),
    (4, 7, *_EM),
    (5, 7, *_EM),
    (6, 7, *_EM),
    (7, 7, *_EM),
]


# --- High-resolution emoji ---------------------------------------------------
#
# 🌙 32×32 moon — generated by circle subtraction (outer disk minus an
# inner disk offset to the right, creating the bite). At scale=4 on the
# bigsign this paints 32 physical LEDs per side — same horizontal
# footprint as the 8×8 low-res :moon: but with 16× more detail per
# pixel.


def _generate_moon_hires(
    size: int = 32,
    color: tuple[int, int, int] = (255, 220, 130),
    bite_offset: float = 0.20,
    outer_r: float | None = None,
) -> tuple[tuple[int, int, int, int, int], ...]:
    """Generate a crescent moon by circle subtraction.

    `bite_offset` is how far the inner ("bite") disk's center is
    shifted from the outer disk's center, as a fraction of `size`.
    The inner disk has the same radius as the outer; their overlap
    is everything except a thin crescent on one side.

      0.10 → very thin crescent (sliver)
      0.20 → balanced crescent (default)
      0.35 → fat crescent (almost half-moon)
      0.50+ → mostly full disk (small bite)

    `outer_r` defaults to `size/2 - 0.5` (smooth curves on big sprites).
    For tiny sprites (size=8) the inset leaves rows 0 and 7 empty —
    pass `outer_r=size/2.0` to fill the full grid.
    """
    cx = cy = (size - 1) / 2.0
    if outer_r is None:
        outer_r = size / 2.0 - 0.5
    inner_r = outer_r  # same radius as outer; the offset creates the bite
    inner_cx = cx + size * bite_offset

    pixels: list[tuple[int, int, int, int, int]] = []
    for y in range(size):
        for x in range(size):
            d_outer_sq = (x - cx) ** 2 + (y - cy) ** 2
            d_inner_sq = (x - inner_cx) ** 2 + (y - cy) ** 2
            if d_outer_sq <= outer_r * outer_r and d_inner_sq > inner_r * inner_r:
                pixels.append((x, y, *color))
    return tuple(pixels)


MOON_HIRES = HiResEmoji(
    pixels=_generate_moon_hires(size=32, color=_MN, bite_offset=0.30),
    physical_size=32,
)


# 📷 32×32 Instagram — rounded square with the iconic 3-stop gradient
# (yellow → pink → purple), hollow lens circle in the center, and a
# small white indicator dot in the upper-right. Far more recognizable
# than the 8×8 single-color version.

# Brand gradient stops (eyeballed from IG's logo gradient).
_IG_YELLOW = (254, 218, 119)
_IG_PINK = (225, 48, 108)
_IG_PURPLE = (131, 58, 180)


def _lerp(
    c1: tuple[int, int, int], c2: tuple[int, int, int], t: float
) -> tuple[int, int, int]:
    return (
        int(c1[0] + (c2[0] - c1[0]) * t),
        int(c1[1] + (c2[1] - c1[1]) * t),
        int(c1[2] + (c2[2] - c1[2]) * t),
    )


def _ig_gradient_color(x: int, y: int, size: int) -> tuple[int, int, int]:
    """Diagonal IG gradient: yellow at bottom-left → pink at middle → purple at top-right."""
    pos = (x + (size - 1 - y)) / (2 * (size - 1))
    pos = max(0.0, min(1.0, pos))
    if pos < 0.5:
        return _lerp(_IG_YELLOW, _IG_PINK, pos * 2)
    return _lerp(_IG_PINK, _IG_PURPLE, (pos - 0.5) * 2)


def _generate_instagram_hires(
    size: int = 32,
) -> tuple[tuple[int, int, int, int, int], ...]:
    """Build Instagram's rounded square + lens + indicator dot at PHYSICAL res.

    Layout (for size=32):
      - Outer rounded square inset 1 px from the canvas edge
      - Corner radius ~size/5
      - 1-px white frame just inside the rounded-rect edge (the body
        outline of the IG glyph)
      - Hollow lens with a white aperture ring around a dark eye
      - Indicator dot in the upper-right quadrant
    """
    cx = cy = (size - 1) / 2.0
    half = (size - 1) / 2.0
    corner_radius = size / 5.0  # ~6.4 for 32

    body_border = 1.2  # white frame thickness on the inside of the rounded rect

    lens_inner_r = size / 4.5 - 1.5  # ~5.6 — outer edge of dark eye
    aperture_border = 1.2  # white ring around the dark eye

    dot_cx = size - size / 5.0
    dot_cy = size / 5.0
    dot_r = size / 12.0  # ~2.7

    pixels: list[tuple[int, int, int, int, int]] = []
    for y in range(size):
        for x in range(size):
            # Rounded-rect test + distance to the body's outer edge.
            dx = abs(x - cx)
            dy = abs(y - cy)
            inner = half - corner_radius
            if dx <= inner or dy <= inner:
                in_body = dx <= half and dy <= half
                # In the cross-arms region, distance to edge is the
                # closer of (half - dx, half - dy)
                edge_dist = min(half - dx, half - dy)
            else:
                cdx = dx - inner
                cdy = dy - inner
                corner_dist = (cdx * cdx + cdy * cdy) ** 0.5
                in_body = corner_dist <= corner_radius
                edge_dist = corner_radius - corner_dist
            if not in_body:
                continue

            # Indicator dot — solid white, drawn over everything else
            ddx = x - dot_cx
            ddy = y - dot_cy
            if ddx * ddx + ddy * ddy <= dot_r * dot_r:
                pixels.append((x, y, 255, 255, 255))
                continue

            # Outer white frame — thin ring along the inside of the
            # rounded-rect edge. Defines the IG body outline.
            if edge_dist <= body_border:
                pixels.append((x, y, 255, 255, 255))
                continue

            # Lens hole — skip pixels inside `lens_inner_r` (dark eye).
            ldx = x - cx
            ldy = y - cy
            lens_dist = (ldx * ldx + ldy * ldy) ** 0.5
            if lens_dist <= lens_inner_r:
                continue

            # White aperture ring around the dark eye.
            if lens_dist <= lens_inner_r + aperture_border:
                pixels.append((x, y, 255, 255, 255))
                continue

            # Otherwise paint the gradient.
            r, g, b = _ig_gradient_color(x, y, size)
            pixels.append((x, y, r, g, b))

    return tuple(pixels)


INSTAGRAM_HIRES = HiResEmoji(
    pixels=_generate_instagram_hires(size=32),
    physical_size=32,
)


# ☀️ 32×32 Sun — solid disk + 8 radial rays. Smooth circle at hi-res
# instead of the chunky 8×8 cross-pattern.
_SUN_COLOR = (255, 220, 80)


def _generate_sun_hires(size: int = 32) -> tuple[tuple[int, int, int, int, int], ...]:
    """Solid disk + 8 thin rays. Each ray is a fixed-thickness line in
    pixel space (perpendicular distance to the ray axis), NOT an angular
    fan — that's the difference from the original version which produced
    extra "fan" pixels at the outer ends of the rays.

    Restored from commit dc78f1e after experimenting with a hardcoded
    4-cardinal + 4-diagonal version (786657f) that read as too "compass"
    -ish. The 8-ray uniform style with perpendicular-distance ray
    detection is the design that landed best on hardware.
    """
    import math

    cx = cy = (size - 1) / 2.0
    disk_r = size / 4.5  # ~7.1
    ray_inner_r = disk_r + 1.0
    ray_outer_r = size / 2.0 - 0.5
    ray_thickness = 1.0  # absolute pixel thickness — keeps rays uniformly thin

    # 8 rays at 45° intervals, each as a unit direction vector
    ray_dirs = [
        (math.cos(i * math.pi / 4), math.sin(i * math.pi / 4)) for i in range(8)
    ]

    pixels: list[tuple[int, int, int, int, int]] = []
    for y in range(size):
        for x in range(size):
            dx = x - cx
            dy = y - cy
            dist_sq = dx * dx + dy * dy

            # Solid disk
            if dist_sq <= disk_r * disk_r:
                pixels.append((x, y, *_SUN_COLOR))
                continue

            # Rays — only in the ring between inner and outer radii
            if ray_inner_r * ray_inner_r <= dist_sq <= ray_outer_r * ray_outer_r:
                for ux, uy in ray_dirs:
                    # Project onto ray direction; positive means same side
                    along = dx * ux + dy * uy
                    if along <= 0:
                        continue  # behind the center — wrong half of the axis
                    # Perpendicular distance from the ray axis line
                    perp = abs(dx * uy - dy * ux)
                    if perp <= ray_thickness:
                        pixels.append((x, y, *_SUN_COLOR))
                        break

    return tuple(pixels)


SUN_HIRES = HiResEmoji(
    pixels=_generate_sun_hires(size=32),
    physical_size=32,
)


# ☁️ 32×32 Cloud — 3-bump silhouette via union of overlapping circles
# PLUS a flat horizontal baseline. The naked circle union tapers to
# single pixels at the bottom of each circle, producing 3 visible
# "dots" below the cloud. The baseline slab (from the widest row of
# the side circles down to the common bottom, spanning full horizontal
# extent) replaces the curved tapers with a clean flat bottom edge.
_CLOUD_COLOR = (220, 225, 240)


def _cloud_silhouette_pixels(
    size: int,
    circles: list[tuple[int, int, int]],
    color: tuple[int, int, int],
) -> list[tuple[int, int, int, int, int]]:
    """Build a cloud silhouette as the union of circles, with two
    cleanups applied:

    1. Bottom-row trim: skip each circle's `dy=r` pixel (which would
       render as a single-pixel nub below the cloud).
    2. Cardinal-extreme widen: for each circle, the top, left, and
       right cardinal-extreme pixels are single-pixel protrusions
       sticking out from the curve. The TOP peak (`dy=-r, dx=0`) is
       widened horizontally (add the same row at `cx-1` and `cx+1`).
       The LEFT and RIGHT equator extremes (`dy=0, |dx|=r`) are
       widened vertically (add the same column at `cy-1` and `cy+1`).
       Both turn 1-pixel "stuck dot" features into 3-pixel rounded
       edges that blend into the curve.

    The bottom extreme is trimmed (not widened) because a fat 3-pixel
    bottom would make the cloud look bottom-heavy.
    """
    pixels: list[tuple[int, int, int, int, int]] = []
    for y in range(size):
        for x in range(size):
            for cx, cy, r in circles:
                if (x - cx) ** 2 + (y - cy) ** 2 <= r * r and y < cy + r:
                    pixels.append((x, y, *color))
                    break

    # Widen the cardinal-extreme protrusions (top horizontally, left/right
    # vertically). Only adds pixels that weren't already lit — interior
    # overlaps from other circles are no-ops.
    pixel_set = {(p[0], p[1]) for p in pixels}

    def _add(x: int, y: int) -> None:
        if 0 <= x < size and 0 <= y < size and (x, y) not in pixel_set:
            pixels.append((x, y, *color))
            pixel_set.add((x, y))

    for cx, cy, r in circles:
        # TOP peak — widen horizontally
        if (cx, cy - r) in pixel_set:
            _add(cx - 1, cy - r)
            _add(cx + 1, cy - r)
        # LEFT and RIGHT equator extremes — widen vertically
        for ex in (cx - r, cx + r):
            if (ex, cy) not in pixel_set:
                continue
            _add(ex, cy - 1)
            _add(ex, cy + 1)
    return pixels


def _generate_cloud_hires(
    size: int = 32, color: tuple[int, int, int] = _CLOUD_COLOR
) -> tuple[tuple[int, int, int, int, int], ...]:
    """3-bump cloud silhouette with smooth flat bottom."""
    circles = [
        (9, 17, 5),  # left bump (small)
        (17, 14, 8),  # middle bump (largest, tallest)
        (25, 17, 5),  # right bump (small)
    ]
    return tuple(set(_cloud_silhouette_pixels(size, circles, color)))


CLOUD_HIRES = HiResEmoji(
    pixels=_generate_cloud_hires(size=32),
    physical_size=32,
)


# 🌧️ 32×32 Rain — smaller cloud at top + 4 vertical drops below
_RAIN_DROP_COLOR = (90, 160, 230)


def _generate_rain_hires(size: int = 32) -> tuple[tuple[int, int, int, int, int], ...]:
    pixels: list[tuple[int, int, int, int, int]] = []

    # Cloud (smaller, sits in upper half) — uses the shared silhouette
    # builder so it gets a smooth flat bottom instead of three tapered
    # dots.
    cloud_circles = [
        (9, 11, 4),  # left bump
        (16, 8, 6),  # middle bump
        (24, 11, 4),  # right bump
    ]
    pixels.extend(_cloud_silhouette_pixels(size, cloud_circles, _CLOUD_COLOR))

    # 4 rain drops below the cloud, staggered vertically for motion
    drop_specs = [
        (8, 18, 4),
        (14, 20, 5),
        (20, 19, 4),
        (26, 21, 4),
    ]
    for col, top_y, length in drop_specs:
        for y in range(top_y, top_y + length):
            for dx in (0, 1):
                pixels.append((col + dx, y, *_RAIN_DROP_COLOR))

    return tuple(set(pixels))


RAIN_HIRES = HiResEmoji(
    pixels=_generate_rain_hires(size=32),
    physical_size=32,
)


# ❄️ 32×32 Snow — single bold 6-armed snowflake (NOT a cloud + flakes;
# the standalone snowflake has more graphic punch at LED resolution).
# 4 axes (H, V, NE-SW, NW-SE) with 2-px thick lines and forked tips.
_SNOW_COLOR = (220, 240, 255)


def _generate_snow_hires(size: int = 32) -> tuple[tuple[int, int, int, int, int], ...]:
    """8-armed snowflake — 4 cardinal arms (2-px thick) + 4 diagonal arms
    (1-px wide, 45°), with T-tips on the cardinals and diagonal V-branches
    near each cardinal-arm tip.

    Earlier attempts: (a) 4 cardinal + 4 diagonal stair-step (2-px wide)
    arms converged into a `######` blob at the equator; (b) cardinal-only
    with perpendicular mid-arm stubs looked like floating pixels. The
    fix is a 1-px diagonal that originates from the *corner* of the
    center cross (not the center itself) — it touches each cardinal arm
    at exactly one cell, then extends cleanly outward at 45°.
    """
    pixels: list[tuple[int, int, int, int, int]] = []
    cx = cy = 15
    arm = 11

    # 4 cardinal arms — 2-px thick
    for x in range(cx - arm, cx + arm + 1):
        pixels.append((x, cy, *_SNOW_COLOR))
        pixels.append((x, cy + 1, *_SNOW_COLOR))
    for y in range(cy - arm, cy + arm + 1):
        pixels.append((cx, y, *_SNOW_COLOR))
        pixels.append((cx + 1, y, *_SNOW_COLOR))

    # T-tips at cardinal arm ends — perpendicular 4-px-wide bars
    for x in range(cx - 1, cx + 3):  # cols 14-17
        pixels.append((x, cy - arm - 1, *_SNOW_COLOR))  # top tip
        pixels.append((x, cy + arm + 1, *_SNOW_COLOR))  # bottom tip
    for y in range(cy - 1, cy + 3):  # rows 14-17
        pixels.append((cx - arm - 1, y, *_SNOW_COLOR))  # left tip
        pixels.append((cx + arm + 1, y, *_SNOW_COLOR))  # right tip

    # Diagonal V-branches at mid-arm. Each branch is a short stair-step
    # fanning OUTWARD from the arm: 2 pixels starting flush with the
    # arm and stepping one cell out + one cell further along the arm.
    # Visually a small "Y" off each cardinal arm.
    branch_dist = 6  # cells from center along the arm to start the branch

    # Vertical arms (top + bottom): branches at rows cy ± branch_dist,
    # stepping OUT along the y-axis (toward the arm tip) and AWAY from
    # the vertical arm cols (15-16).
    for sign in (-1, 1):  # -1 = top arm, +1 = bottom arm
        anchor_y = cy + sign * branch_dist + (1 if sign == 1 else 0)
        for d in (1, 2):
            # Left V-leg
            pixels.append((cx - d, anchor_y + sign * d, *_SNOW_COLOR))
            # Right V-leg
            pixels.append((cx + 1 + d, anchor_y + sign * d, *_SNOW_COLOR))

    # Horizontal arms (left + right): branches at cols cx ± branch_dist,
    # stepping OUT along the x-axis and AWAY from the horizontal arm
    # rows (15-16).
    for sign in (-1, 1):
        anchor_x = cx + sign * branch_dist + (1 if sign == 1 else 0)
        for d in (1, 2):
            # Top V-leg
            pixels.append((anchor_x + sign * d, cy - d, *_SNOW_COLOR))
            # Bottom V-leg
            pixels.append((anchor_x + sign * d, cy + 1 + d, *_SNOW_COLOR))

    # 4 diagonal arms — 1-px wide, originating from the corners of the
    # center cross. Each pixel (cx ± (d+offset), cy ± (d+offset)) sits
    # exactly one cell off the cardinal arm at d=0 and extends outward
    # at 45° without colliding with the cross.
    diag_arm = 9
    for d in range(1, diag_arm + 1):
        # NW (top-left)
        pixels.append((cx - d, cy - d, *_SNOW_COLOR))
        # NE (top-right) — shift by +1 to land on the right side of the
        # 2-px-thick cardinal arm
        pixels.append((cx + 1 + d, cy - d, *_SNOW_COLOR))
        # SW (bottom-left) — shift by +1 vertically to land below the arm
        pixels.append((cx - d, cy + 1 + d, *_SNOW_COLOR))
        # SE (bottom-right)
        pixels.append((cx + 1 + d, cy + 1 + d, *_SNOW_COLOR))

    # Diagonal arm tips — 2-px stub perpendicular to the diagonal,
    # making a small "+" at each diagonal tip (mirrors the cardinal
    # T-tips at a smaller scale).
    tip_d = diag_arm + 1
    for sx, sy in ((-1, -1), (-1, 1), (1, -1), (1, 1)):
        # corner-of-cross offset
        ox = 0 if sx == -1 else 1
        oy = 0 if sy == -1 else 1
        # tip_x = cx + ox + sx*tip_d, tip_y = cy + oy + sy*tip_d
        tx = cx + ox + sx * tip_d
        ty = cy + oy + sy * tip_d
        # 2-px stub running perpendicular: place a single pixel one step
        # along each axis, forming a small chevron at the tip
        pixels.append((tx, ty - sy, *_SNOW_COLOR))
        pixels.append((tx - sx, ty, *_SNOW_COLOR))

    return tuple(set(pixels))


SNOW_HIRES = HiResEmoji(
    pixels=_generate_snow_hires(size=32),
    physical_size=32,
)


# ⚡ 32×32 Thunder — dark cloud + bright yellow Z-shaped lightning bolt
_THUNDER_CLOUD_COLOR = (110, 110, 140)
_THUNDER_BOLT_COLOR = (255, 220, 50)


def _generate_thunder_hires(
    size: int = 32,
) -> tuple[tuple[int, int, int, int, int], ...]:
    pixels: list[tuple[int, int, int, int, int]] = []

    # Dark cloud at top — uses the shared silhouette builder for a
    # smooth flat bottom (same fix as the regular :cloud:).
    cloud_circles = [
        (9, 10, 4),
        (16, 7, 6),
        (24, 10, 4),
    ]
    pixels.extend(_cloud_silhouette_pixels(size, cloud_circles, _THUNDER_CLOUD_COLOR))

    # Lightning bolt — hand-coded Z-shape, 3-px thick. Cuts down from the
    # cloud center, jogs right, continues down to the bottom.
    # Pixels stored as (x_offset_from_left, y) and shifted into place.
    bolt = [
        # Top segment (going down-left from cloud bottom)
        (18, 14),
        (18, 15),
        (17, 15),
        (17, 16),
        (16, 16),
        (16, 17),
        (15, 17),
        (15, 18),
        (14, 18),
        (14, 19),
        (13, 19),
        (13, 20),
        # Horizontal jog (the "Z" middle segment) — wider
        (14, 20),
        (15, 20),
        (16, 20),
        (17, 20),
        (18, 20),
        (19, 20),
        (20, 20),
        # Lower segment (going down-left from jog)
        (19, 21),
        (18, 21),
        (18, 22),
        (17, 22),
        (17, 23),
        (16, 23),
        (16, 24),
        (15, 24),
        (15, 25),
        (14, 25),
        (14, 26),
        (13, 26),
        (13, 27),
        (12, 27),
        (12, 28),
    ]
    # Thicken to 2-3 px by also painting one pixel right
    for x, y in bolt:
        pixels.append((x, y, *_THUNDER_BOLT_COLOR))
        pixels.append((x + 1, y, *_THUNDER_BOLT_COLOR))

    return tuple(set(pixels))


THUNDER_HIRES = HiResEmoji(
    pixels=_generate_thunder_hires(size=32),
    physical_size=32,
)


# 🌫️ 32×32 Fog — 4 horizontal wavy bands (suggest layered fog)
_FOG_COLOR = (190, 195, 205)


def _generate_fog_hires(size: int = 32) -> tuple[tuple[int, int, int, int, int], ...]:
    """Fog: 4 horizontal 2-px-thick bands, each shifted slightly to suggest
    the mist drifting. Bands are short of full width on alternating sides
    so the eye doesn't read them as solid bars.
    """
    pixels: list[tuple[int, int, int, int, int]] = []
    # (top_y, left, right) — left/right define the band's horizontal extent
    bands = [
        (7, 4, 26),
        (12, 7, 28),
        (17, 3, 25),
        (22, 6, 27),
    ]
    for top_y, left, right in bands:
        for x in range(left, right + 1):
            for dy in (0, 1):  # 2-px tall
                pixels.append((x, top_y + dy, *_FOG_COLOR))
    return tuple(set(pixels))


FOG_HIRES = HiResEmoji(
    pixels=_generate_fog_hires(size=32),
    physical_size=32,
)


# ⭐ 32×32 Star — clean 5-pointed star using a mathematical generator.
_STAR_COLOR = (255, 215, 0)


def _generate_star_hires(size: int = 32) -> tuple[tuple[int, int, int, int, int], ...]:
    """5-pointed star using point-in-polygon for a clean filled shape."""
    import math

    cx = cy = (size - 1) / 2.0
    outer_r = size / 2.0 - 1.0
    inner_r = outer_r * 0.4

    # 10 vertices alternating outer/inner, starting at top
    vertices: list[tuple[float, float]] = []
    for i in range(10):
        angle = -math.pi / 2 + i * math.pi / 5  # start at top, step 36°
        r = outer_r if i % 2 == 0 else inner_r
        vertices.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))

    def _inside(px: float, py: float) -> bool:
        # Ray-casting: count crossings of horizontal ray from (px, py)
        crossings = 0
        n = len(vertices)
        for i in range(n):
            ax, ay = vertices[i]
            bx, by = vertices[(i + 1) % n]
            if (ay > py) != (by > py):
                t = (py - ay) / (by - ay)
                xc = ax + t * (bx - ax)
                if px < xc:
                    crossings += 1
        return crossings % 2 == 1

    pixels: list[tuple[int, int, int, int, int]] = []
    for y in range(size):
        for x in range(size):
            if _inside(x + 0.5, y + 0.5):
                pixels.append((x, y, *_STAR_COLOR))
    return tuple(pixels)


STAR_HIRES = HiResEmoji(
    pixels=_generate_star_hires(size=32),
    physical_size=32,
)


# ✉️ 32×32 Email — envelope with V-shaped flap. Simple linear-edge geometry
# (no curves) so a programmatic generator scales cleanly.
_EMAIL_COLOR = (240, 240, 240)


def _generate_email_hires(size: int = 32) -> tuple[tuple[int, int, int, int, int], ...]:
    """Envelope sized to mirror the proportions of the working 8×8 low-res.

    Research notes from the design pass:
      - The 8×8 version's V-flap diagonals are 1 px wide on an 8-px
        canvas → 12.5% of width. To match RELATIVE visual weight at
        32×32, the hi-res diagonals need to be ~3-4 px thick.
      - The 8×8 V meets at a 2-px flat segment (cols 3-4, row 3), NOT a
        single point. Translating proportionally: hi-res should meet at
        a 4-px flat segment (cols 14-17). Drawing the V to a single
        point produces a sharp tip that reads as a stray dot at LED
        brightness, fighting the symmetric flap shape.

    This version applies both: 3-px-thick V diagonals meeting at a
    4-px flat segment. Plus a subtle 2×2 cream-yellow accent at the
    lower-center as an "anchor" feature — gives the eye something to
    land on in the otherwise-empty envelope body.
    """
    pixels: list[tuple[int, int, int, int, int]] = []
    inset = 1
    border = 2
    left = inset
    right = size - 1 - inset
    top = inset
    bottom = size - 1 - inset

    # 2-px-thick rectangle border on all four sides
    for x in range(left, right + 1):
        for dy in range(border):
            pixels.append((x, top + dy, *_EMAIL_COLOR))
            pixels.append((x, bottom - dy, *_EMAIL_COLOR))
    for y in range(top, bottom + 1):
        for dx in range(border):
            pixels.append((left + dx, y, *_EMAIL_COLOR))
            pixels.append((right - dx, y, *_EMAIL_COLOR))

    inner_left = left + border
    inner_right = right - border
    inner_top = top + border
    inner_bottom = bottom - border

    # V-flap meeting parameters — flat 4-px segment, not a single point.
    flap_meet_y = inner_top + int((inner_bottom - inner_top) * 0.40)
    flat_half = 2  # → 4-px-wide flat at the meeting
    cx = (inner_left + inner_right) // 2
    flat_left = cx - flat_half
    flat_right = cx + flat_half - 1  # inclusive

    def _draw_thick_line(
        x0: int, y0: int, x1: int, y1: int, thickness: int = 3
    ) -> None:
        """N-px-thick Bresenham. Each line pixel paints itself plus
        `thickness - 1` pixels below — 3-px is the sweet spot for V-flap
        weight at 32×32 LED resolution.
        """
        dx = abs(x1 - x0)
        dy = abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx - dy
        x, y = x0, y0
        while True:
            for thick_dy in range(thickness):
                ty = y + thick_dy
                if 0 <= x < size and 0 <= ty < size:
                    pixels.append((x, ty, *_EMAIL_COLOR))
            if x == x1 and y == y1:
                break
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                x += sx
            if e2 < dx:
                err += dx
                y += sy

    # 3-px V diagonals from the inner top corners to the flat segment ends
    _draw_thick_line(inner_left, inner_top, flat_left, flap_meet_y)
    _draw_thick_line(inner_right, inner_top, flat_right, flap_meet_y)

    # 3-px-thick flat segment at the V meeting — connects the diagonals
    # cleanly so the bottom of the flap is a horizontal seam, not a tip.
    for x in range(flat_left, flat_right + 1):
        for dy in range(3):
            pixels.append((x, flap_meet_y + dy, *_EMAIL_COLOR))

    # Anchor accent: small 3×2 dot in the lower-center of the body.
    # Same color as the rest — subtle but gives the eye a landing point.
    accent_cy = inner_bottom - 5
    for dy in range(2):
        for dx in range(-1, 2):
            pixels.append((cx + dx, accent_cy + dy, *_EMAIL_COLOR))

    return tuple(set(pixels))


EMAIL_HIRES = HiResEmoji(
    pixels=_generate_email_hires(size=32),
    physical_size=32,
)


def _build_emoji_registry() -> dict[str, PixelData]:
    """Build the emoji registry with all available icons."""
    from led_ticker.widgets.weather_icons import (
        CLOUD,
        FOG,
        RAIN,
        SNOW,
        SUN,
        THUNDER,
    )

    return {
        # Sports
        "baseball": BASEBALL,
        "flower": FLOWER,
        "star": STAR,
        # Food
        "taco": TACO,
        # Weather
        "sun": SUN,
        "cloud": CLOUD,
        "rain": RAIN,
        "snow": SNOW,
        "thunder": THUNDER,
        "fog": FOG,
        # Celestial
        "moon": MOON,
        # Social
        "instagram": INSTAGRAM,
        "email": EMAIL,
    }


EMOJI_REGISTRY: dict[str, PixelData] = {}

# Hi-res variants of the same slugs — used preferentially when the
# canvas is a `ScaledCanvas`. Falls back to `EMOJI_REGISTRY` if the
# slug isn't here.
HIRES_REGISTRY: dict[str, HiResEmoji] = {
    "moon": MOON_HIRES,
    "instagram": INSTAGRAM_HIRES,
    "sun": SUN_HIRES,
    "star": STAR_HIRES,
    "email": EMAIL_HIRES,
    # Weather
    "cloud": CLOUD_HIRES,
    "rain": RAIN_HIRES,
    "snow": SNOW_HIRES,
    "thunder": THUNDER_HIRES,
    "fog": FOG_HIRES,
}


def _get_registry() -> dict[str, PixelData]:
    global EMOJI_REGISTRY  # noqa: PLW0603
    if not EMOJI_REGISTRY:
        EMOJI_REGISTRY.update(_build_emoji_registry())
    return EMOJI_REGISTRY


def _parse_segments(text: str) -> list[tuple[str, str]]:
    """Split text into segments of (type, value).

    Returns list of ("text", "hello ") or ("emoji", "baseball").
    """
    import re

    parts = re.split(r"(:[a-z_]+:)", text)
    segments: list[tuple[str, str]] = []
    for part in parts:
        if not part:
            continue
        if part.startswith(":") and part.endswith(":"):
            slug = part[1:-1]
            if slug in _get_registry():
                segments.append(("emoji", slug))
            else:
                segments.append(("text", part))
        else:
            segments.append(("text", part))
    return segments


def measure_width(font: Font, text: str) -> int:
    """Measure total width of text with emoji slugs expanded."""
    from led_ticker.drawing import get_text_width

    segments = _parse_segments(text)
    width = 0
    for seg_type, value in segments:
        if seg_type == "emoji":
            width += _emoji_width(_get_registry()[value]) + EMOJI_PADDING
        else:
            width += get_text_width(font, value, padding=0)
    return width


def draw_with_emoji(
    canvas: Canvas,
    font: Font,
    cursor_pos: int,
    y: int,
    color: Color,
    text: str,
    y_offset: int = 0,
    emoji_y: int | None = None,
    max_emoji_height: int | None = None,
) -> int:
    """Draw text with inline emoji. Returns pixels advanced.

    `emoji_y` overrides the icon's top-row position. Default is
    `4 + y_offset` — vertically centered on the 16-tall logical canvas
    plus any caller-supplied offset. Multi-row widgets (e.g. `two_row`)
    pass an explicit `emoji_y` per row so the icon aligns with the row's
    text baseline instead of the canvas center.

    `max_emoji_height` is the maximum logical height the emoji is
    allowed to occupy (used by multi-row widgets). When the hi-res
    sprite's logical height exceeds this, the renderer falls back to
    the 8×8 low-res sprite — prevents a hi-res icon from overflowing
    the row's vertical space and overlapping the next row.
    """
    segments = _parse_segments(text)
    total: int = 0

    iy_default = 4 + y_offset

    # Hi-res path is only available on a ScaledCanvas — anywhere else we
    # fall back to the regular 8×8 sprite.
    from led_ticker.scaled_canvas import ScaledCanvas

    use_hires = isinstance(canvas, ScaledCanvas)

    for seg_type, value in segments:
        if seg_type == "emoji":
            ix = int(cursor_pos + total)
            iy = iy_default if emoji_y is None else emoji_y

            # Hi-res only fires if (a) we're on a ScaledCanvas, (b) a hi-res
            # variant exists, and (c) the sprite fits within the caller's
            # max_emoji_height (if specified). Otherwise: low-res fallback.
            hires: HiResEmoji | None = None
            if use_hires and value in HIRES_REGISTRY:
                candidate = HIRES_REGISTRY[value]
                logical_h = candidate.physical_size // canvas.scale
                if max_emoji_height is None or logical_h <= max_emoji_height:
                    hires = candidate

            if hires is not None:
                _draw_hires_emoji(canvas, hires, ix, iy)
                total += hires.logical_width(canvas.scale) + EMOJI_PADDING
            else:
                icon = _get_registry()[value]
                iw = _emoji_width(icon)
                w = canvas.width
                h = getattr(canvas, "height", 16)
                for px, py, r, g, b in icon:
                    dx = ix + px
                    dy = iy + py
                    if 0 <= dx < w and 0 <= dy < h:
                        canvas.SetPixel(dx, dy, r, g, b)
                total += iw + EMOJI_PADDING
        else:
            total += draw_text(
                canvas,
                font,
                int(cursor_pos + total),
                y + y_offset,
                color,
                value,
            )

    return total


def _draw_hires_emoji(
    canvas: ScaledCanvas,  # noqa: F821
    hires: HiResEmoji,
    ix_logical: int,
    iy_logical: int,
) -> None:
    """Paint a hi-res sprite directly to the ScaledCanvas's real canvas.

    The wrapper's `SetPixel` would expand each pixel to a `scale × scale`
    block, defeating the purpose of the hi-res sprite. Calling
    `real.SetPixel` writes individual physical LEDs.
    """
    real = canvas.real
    scale = canvas.scale
    real_y_offset = canvas._y_offset

    real_x_anchor = ix_logical * scale
    real_y_anchor = iy_logical * scale + real_y_offset

    real_w = real.width
    real_h = real.height

    for px, py, r, g, b in hires.pixels:
        rx = real_x_anchor + px
        ry = real_y_anchor + py
        if 0 <= rx < real_w and 0 <= ry < real_h:
            real.SetPixel(rx, ry, r, g, b)
