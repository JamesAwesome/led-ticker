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


# 🌙 Crescent moon — slim crescent opening right, tilted slightly so the
# top tip leans left and the bottom tip leans right (gives the moon a
# leaning, dynamic feel that pairs with the aerial-circus aesthetic). The
# middle has a single-pixel pinch so the shape reads as a CURVE rather
# than a stack of chunky blocks. Color is moonlight gold so it reads as
# "moon" rather than "sun" against pinks/lavender. Bunny silhouette is
# intentionally omitted — at 8×8 the resolution can't carry both. Use
# `:moon:` in any message.
_MN = (255, 220, 130)
MOON: PixelData = [
    # Row 0: top arc (5 wide)
    (2, 0, *_MN),
    (3, 0, *_MN),
    (4, 0, *_MN),
    (5, 0, *_MN),
    # Row 1: outer crescent narrows
    (1, 1, *_MN),
    (2, 1, *_MN),
    (3, 1, *_MN),
    (4, 1, *_MN),
    # Row 2: left side starts thinning
    (0, 2, *_MN),
    (1, 2, *_MN),
    (2, 2, *_MN),
    # Row 3: thinnest part (left edge only)
    (0, 3, *_MN),
    (1, 3, *_MN),
    # Row 4: thinnest part (left edge only)
    (0, 4, *_MN),
    (1, 4, *_MN),
    # Row 5: starts to widen back
    (0, 5, *_MN),
    (1, 5, *_MN),
    (2, 5, *_MN),
    # Row 6: outer crescent widens
    (1, 6, *_MN),
    (2, 6, *_MN),
    (3, 6, *_MN),
    (4, 6, *_MN),
    # Row 7: bottom arc (5 wide)
    (2, 7, *_MN),
    (3, 7, *_MN),
    (4, 7, *_MN),
    (5, 7, *_MN),
]


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
    """
    cx = cy = (size - 1) / 2.0
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
      - Hollow lens circle centered (radius ~size/4.5), inner cut out
      - Indicator dot in the upper-right quadrant
    """
    cx = cy = (size - 1) / 2.0
    half = (size - 1) / 2.0
    corner_radius = size / 5.0  # ~6.4 for 32

    lens_outer_r = size / 4.5  # ~7.1
    lens_inner_r = lens_outer_r - 1.5  # ~5.6 — gradient ring around dark eye

    dot_cx = size - size / 5.0
    dot_cy = size / 5.0
    dot_r = size / 12.0  # ~2.7

    pixels: list[tuple[int, int, int, int, int]] = []
    for y in range(size):
        for x in range(size):
            # Rounded-rect test: inside the cross OR within corner_radius
            # of one of the four corner centers.
            dx = abs(x - cx)
            dy = abs(y - cy)
            inner = half - corner_radius
            if dx <= inner or dy <= inner:
                in_body = dx <= half and dy <= half
            else:
                cdx = dx - inner
                cdy = dy - inner
                in_body = (cdx * cdx + cdy * cdy) <= corner_radius * corner_radius
            if not in_body:
                continue

            # Indicator dot — solid white, drawn over the gradient
            ddx = x - dot_cx
            ddy = y - dot_cy
            if ddx * ddx + ddy * ddy <= dot_r * dot_r:
                pixels.append((x, y, 255, 255, 255))
                continue

            # Lens hole: skip pixels inside lens_inner_r (creates the
            # dark "eye" in the middle of the camera).
            ldx = x - cx
            ldy = y - cy
            lens_dist_sq = ldx * ldx + ldy * ldy
            if lens_dist_sq <= lens_inner_r * lens_inner_r:
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
    fan — that's the difference from the previous version which produced
    extra "fan" pixels at the outer ends of the rays.
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
    """Envelope outline with flap diagonals INSIDE the rectangle.

    Previous version drew the V-flap as separate antennas above the
    rectangle — read as a TV/computer monitor with rabbit ears, not as
    an envelope. The classic envelope icon has a single rectangle with
    the flap diagonals running INSIDE it, from the top corners down to
    a point in the upper third of the rectangle. That's what reads as
    "closed envelope viewed from the front".

    Layout:
      - 1-px outline rectangle inset 2 px from canvas edges
      - Two flap diagonals inside: (left, top) → (mid, top + h/3) and
        (right, top) → (mid, top + h/3)
    """
    pixels: list[tuple[int, int, int, int, int]] = []
    inset = 2
    left = inset
    right = size - 1 - inset
    top = inset
    bottom = size - 1 - inset

    # 1-px rectangle outline (top, bottom, left, right edges)
    for x in range(left, right + 1):
        pixels.append((x, top, *_EMAIL_COLOR))
        pixels.append((x, bottom, *_EMAIL_COLOR))
    for y in range(top, bottom + 1):
        pixels.append((left, y, *_EMAIL_COLOR))
        pixels.append((right, y, *_EMAIL_COLOR))

    # Flap diagonals INSIDE the rectangle: from top-left and top-right
    # corners down to a meeting point at mid-x, ~1/3 down the body.
    mid_x = (left + right) // 2
    flap_meet_y = top + (bottom - top) // 3

    def _draw_line(x0: int, y0: int, x1: int, y1: int) -> None:
        # Standard Bresenham, 1-px line (no thickness — the rectangle
        # gives enough visual weight already).
        dx = abs(x1 - x0)
        dy = abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx - dy
        x, y = x0, y0
        while True:
            if 0 <= x < size and 0 <= y < size:
                pixels.append((x, y, *_EMAIL_COLOR))
            if x == x1 and y == y1:
                break
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                x += sx
            if e2 < dx:
                err += dx
                y += sy

    _draw_line(left, top, mid_x, flap_meet_y)
    _draw_line(right, top, mid_x, flap_meet_y)

    return tuple(set(pixels))


EMAIL_HIRES = HiResEmoji(
    pixels=_generate_email_hires(size=32),
    physical_size=32,
)


def _build_emoji_registry() -> dict[str, PixelData]:
    """Build the emoji registry with all available icons."""
    from led_ticker.widgets.mlb_icons import FLOWER, STAR
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
            hires_ok = use_hires and value in HIRES_REGISTRY
            if hires_ok:
                hires = HIRES_REGISTRY[value]
                logical_h = hires.physical_size // canvas.scale
                if max_emoji_height is not None and logical_h > max_emoji_height:
                    hires_ok = False

            if hires_ok:
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
