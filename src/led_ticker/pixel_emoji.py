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

import re
from dataclasses import dataclass
from typing import Any

from led_ticker._types import Canvas, Font, PixelData
from led_ticker.scaled_canvas import ScaledCanvas
from led_ticker.text_render import draw_text, draw_text_per_char

# Canonical emoji slug pattern shared by `_parse_segments` and any
# widget that needs to detect emoji presence in text. Match a `:slug:`
# token where slug is lowercase letters and underscores. Widgets use
# `EMOJI_PATTERN.search(text)` to cache `has_emoji` at construction
# time so per-tick draws don't re-run the regex.
EMOJI_PATTERN: re.Pattern[str] = re.compile(r":[a-z_]+:")

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

    `physical_width` overrides the layout footprint for emojis whose
    visible content doesn't fill the full physical_size canvas (e.g.
    the crescent moon, which only spans 19 of 32 cols — without an
    override the empty cols still consume logical-width and create
    visible gaps in inline rows). Defaults to physical_size when
    unset.
    """

    pixels: tuple[tuple[int, int, int, int, int], ...]
    physical_size: int  # e.g. 32 means 32×32 canvas
    physical_width: int | None = None  # override for layout (default = physical_size)

    def logical_width(self, scale: int) -> int:
        w = (
            self.physical_width
            if self.physical_width is not None
            else self.physical_size
        )
        return w // max(1, scale)


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


# ❤️ 8×8 Heart — two humps at top tapering to a point at the bottom.
# Flat solid color, no highlight. Generated for each rainbow variant
# below.
_HEART_LOWRES_CELLS: tuple[tuple[int, int], ...] = (
    # Row 0: two humps with a 1-px notch in the middle
    (1, 0),
    (2, 0),
    (4, 0),
    (5, 0),
    # Rows 1-3: full body
    (0, 1),
    (1, 1),
    (2, 1),
    (3, 1),
    (4, 1),
    (5, 1),
    (6, 1),
    (0, 2),
    (1, 2),
    (2, 2),
    (3, 2),
    (4, 2),
    (5, 2),
    (6, 2),
    (0, 3),
    (1, 3),
    (2, 3),
    (3, 3),
    (4, 3),
    (5, 3),
    (6, 3),
    # Row 4: tapering
    (1, 4),
    (2, 4),
    (3, 4),
    (4, 4),
    (5, 4),
    # Row 5: narrower
    (2, 5),
    (3, 5),
    (4, 5),
    # Row 6: tip
    (3, 6),
)


def _heart_lowres(body: tuple[int, int, int]) -> PixelData:
    """Build a low-res heart sprite in the given solid color."""
    return [(x, y, *body) for x, y in _HEART_LOWRES_CELLS]


# Rainbow palette: (slug_suffix, body, outline). Outline is a darker
# shade of the body, used by the hi-res variant for a crisp edge.
_HEART_PALETTE: tuple[tuple[str, tuple[int, int, int], tuple[int, int, int]], ...] = (
    ("red", (220, 30, 50), (90, 10, 25)),
    ("orange", (255, 130, 30), (140, 60, 10)),
    ("yellow", (255, 210, 50), (150, 120, 20)),
    ("green", (50, 200, 80), (20, 110, 40)),
    ("blue", (60, 130, 230), (20, 60, 120)),
    ("purple", (175, 80, 220), (90, 30, 130)),
    ("pink", (255, 130, 180), (170, 50, 100)),
)

HEART = _heart_lowres(_HEART_PALETTE[0][1])  # default :heart: → red
HEART_LOWRES_VARIANTS: dict[str, PixelData] = {
    f"heart_{name}": _heart_lowres(body) for name, body, _ in _HEART_PALETTE
}


# 🏳️‍🌈 Pride flag emojis — horizontal stripes filling the canvas, plus
# the demisexual flag's left-side black triangle as a special case.
#
# Each flag is defined by (slug_suffix, list_of_(color, weight)) tuples.
# Weights determine relative stripe heights. For most flags the weights
# are all 1 (equal stripes); the bisexual flag uses 2/1/2 to match the
# canonical 40/20/40 proportion.
_PRIDE_FLAGS: tuple[tuple[str, tuple[tuple[tuple[int, int, int], int], ...]], ...] = (
    (
        "rainbow",
        (
            ((228, 3, 3), 1),  # red
            ((255, 140, 0), 1),  # orange
            ((255, 237, 0), 1),  # yellow
            ((0, 128, 38), 1),  # green
            ((0, 77, 255), 1),  # blue
            ((117, 7, 135), 1),  # violet
        ),
    ),
    (
        "bi",
        (
            ((214, 2, 112), 2),  # magenta (40%)
            ((155, 79, 150), 1),  # purple (20%)
            ((0, 56, 168), 2),  # blue (40%)
        ),
    ),
    (
        "trans",
        (
            ((91, 206, 250), 1),  # light blue
            ((245, 169, 184), 1),  # pink
            ((255, 255, 255), 1),  # white
            ((245, 169, 184), 1),  # pink
            ((91, 206, 250), 1),  # light blue
        ),
    ),
    (
        "lesbian",
        (
            ((213, 45, 0), 1),  # dark orange
            ((239, 118, 39), 1),  # orange
            ((255, 154, 86), 1),  # light orange
            ((255, 255, 255), 1),  # white
            ((209, 98, 164), 1),  # light pink
            ((181, 86, 144), 1),  # pink
            ((163, 2, 98), 1),  # dark pink/red
        ),
    ),
    (
        "ace",
        (
            # Use (44, 44, 44) instead of pure black so the stripe is
            # visible on the LED panel (pure black = unlit pixel).
            ((44, 44, 44), 1),  # black
            ((164, 164, 164), 1),  # gray
            ((255, 255, 255), 1),  # white
            ((129, 0, 129), 1),  # purple
        ),
    ),
    (
        "nb",
        (
            ((252, 244, 52), 1),  # yellow
            ((255, 255, 255), 1),  # white
            ((156, 89, 209), 1),  # purple
            ((44, 44, 44), 1),  # black
        ),
    ),
)

# Demisexual flag — special case: 3 horizontal stripes (white/purple/gray)
# with a black triangle protruding from the LEFT edge.
_DEMI_STRIPES: tuple[tuple[tuple[int, int, int], int], ...] = (
    ((255, 255, 255), 2),  # white (top, 40%)
    ((129, 0, 129), 1),  # purple (middle, 20%)
    ((128, 128, 128), 2),  # gray (bottom, 40%)
)
_DEMI_TRIANGLE = (44, 44, 44)  # visible-black to match :pride_nb: / :pride_ace:


def _flag_stripes_pixels(
    stripes: tuple[tuple[tuple[int, int, int], int], ...],
    width: int,
    height: int,
) -> dict[tuple[int, int], tuple[int, int, int]]:
    """Distribute stripes across `height` rows, weighted. Returns a
    pixel dict mapping (x, y) → color for the full width × height area.
    """
    total = sum(w for _, w in stripes)
    boundaries: list[tuple[float, tuple[int, int, int]]] = []
    cum = 0
    for color, w in stripes:
        cum += w
        boundaries.append((cum / total * height, color))
    pixels: dict[tuple[int, int], tuple[int, int, int]] = {}
    for y in range(height):
        for cutoff, color in boundaries:
            if y < cutoff:
                row_color = color
                break
        else:
            row_color = boundaries[-1][1]
        for x in range(width):
            pixels[(x, y)] = row_color
    return pixels


def _demi_triangle_pixels(
    width: int,
    height: int,
) -> set[tuple[int, int]]:
    """Black triangle protruding from the left edge — fills cells where
    the horizontal distance from the left edge < the vertical distance
    from the canvas center. Triangle apex points right at the center y.
    """
    cells: set[tuple[int, int]] = set()
    cy = (height - 1) / 2.0
    # Triangle width = ~40% of canvas
    tri_w = width * 0.4
    for y in range(height):
        # Distance from center y, normalized to [0, 1]
        dy_norm = abs(y - cy) / cy if cy > 0 else 0
        # Width of triangle at this row
        row_w = tri_w * (1 - dy_norm)
        for x in range(width):
            if x < row_w:
                cells.add((x, y))
    return cells


def _flag_lowres(slug: str) -> PixelData:
    """Generate an 8×8 horizontal-stripe pride flag sprite."""
    width, height = 8, 8
    if slug == "demi":
        base = _flag_stripes_pixels(_DEMI_STRIPES, width, height)
        for tx, ty in _demi_triangle_pixels(width, height):
            base[(tx, ty)] = _DEMI_TRIANGLE
    else:
        for s, stripes in _PRIDE_FLAGS:
            if s == slug:
                base = _flag_stripes_pixels(stripes, width, height)
                break
        else:
            raise KeyError(slug)
    return [(x, y, *c) for (x, y), c in base.items()]


PRIDE = _flag_lowres("rainbow")  # default :pride: → rainbow
PRIDE_LOWRES_VARIANTS: dict[str, PixelData] = {
    f"pride_{slug}": _flag_lowres(slug)
    for slug in tuple(s for s, _ in _PRIDE_FLAGS) + ("demi",)
}


# 🔴⚪ 8×8 Pokeball — round ball, red top, white bottom, black band
# across the middle with a white button.
_PB_R = (220, 0, 0)  # classic pokeball red
_PB_W = (245, 245, 245)
_PB_K = (40, 40, 40)  # black band / outline
POKEBALL: PixelData = [
    # Row 0: top of ball (rounded)
    (1, 0, *_PB_R),
    (2, 0, *_PB_R),
    (3, 0, *_PB_R),
    (4, 0, *_PB_R),
    (5, 0, *_PB_R),
    (6, 0, *_PB_R),
    # Row 1: full red
    *((x, 1, *_PB_R) for x in range(8)),
    # Row 2: full red
    *((x, 2, *_PB_R) for x in range(8)),
    # Row 3: black band (top of band)
    *((x, 3, *_PB_K) for x in range(8)),
    # Row 4: black band with white button at center
    (0, 4, *_PB_K),
    (1, 4, *_PB_K),
    (2, 4, *_PB_K),
    (3, 4, *_PB_W),
    (4, 4, *_PB_W),
    (5, 4, *_PB_K),
    (6, 4, *_PB_K),
    (7, 4, *_PB_K),
    # Row 5: full white
    *((x, 5, *_PB_W) for x in range(8)),
    # Row 6: full white
    *((x, 6, *_PB_W) for x in range(8)),
    # Row 7: bottom (rounded)
    (1, 7, *_PB_W),
    (2, 7, *_PB_W),
    (3, 7, *_PB_W),
    (4, 7, *_PB_W),
    (5, 7, *_PB_W),
    (6, 7, *_PB_W),
]


# 🐱 8×8 Cat — pointy triangular ears, round face, two eyes, small
# nose. Multiple color variants (gray, orange, white, black, etc.)
# generated from a shared layout helper.
_CAT_NOSE_PINK = (255, 130, 170)


def _cat_lowres(face: tuple[int, int, int], eye: tuple[int, int, int]) -> PixelData:
    """Build a low-res 8×8 cat face sprite with the given colors."""
    F = face
    B = eye
    N = _CAT_NOSE_PINK
    cells: list[tuple[int, int, tuple[int, int, int]]] = []
    # Row 0: ear tops (cols 1-2 and 5-6)
    for x in (1, 2, 5, 6):
        cells.append((x, 0, F))
    # Row 1: ear bottoms widening (cols 0-2 and 5-7)
    for x in (0, 1, 5, 6, 7):
        cells.append((x, 1, F))
    # Row 2: face top (full row)
    for x in range(8):
        cells.append((x, 2, F))
    # Row 3: eyes (cols 2, 5)
    for x in range(8):
        cells.append((x, 3, B if x in (2, 5) else F))
    # Row 4: face
    for x in range(8):
        cells.append((x, 4, F))
    # Row 5: pink nose at center (cols 3-4)
    for x in range(8):
        cells.append((x, 5, N if x in (3, 4) else F))
    # Row 6: face (slight inset)
    for x in range(1, 7):
        cells.append((x, 6, F))
    # Row 7: chin point
    for x in range(2, 6):
        cells.append((x, 7, F))
    return [(x, y, *c) for x, y, c in cells]


# Cat color palette: (slug_suffix, face_color, eye_color)
_CAT_PALETTE: tuple[tuple[str, tuple[int, int, int], tuple[int, int, int]], ...] = (
    ("gray", (180, 180, 195), (245, 200, 50)),  # default — gray with yellow eyes
    ("orange", (240, 140, 60), (255, 220, 80)),
    ("white", (240, 240, 245), (100, 180, 240)),  # blue eyes
    ("black", (60, 60, 70), (255, 220, 50)),
    ("brown", (130, 80, 50), (255, 220, 50)),
    ("cream", (220, 195, 160), (110, 180, 230)),
)

CAT = _cat_lowres(_CAT_PALETTE[0][1], _CAT_PALETTE[0][2])  # default :cat: → gray
CAT_LOWRES_VARIANTS: dict[str, PixelData] = {
    f"cat_{name}": _cat_lowres(face, eye) for name, face, eye in _CAT_PALETTE
}


# 🐰 8×8 Bunny — two long ears with pink inner lining, white face with
# black eyes and a pink nose. Matches the canonical 🐰 emoji silhouette.
_BN_W = (245, 245, 245)  # white body / face
_BN_P = (255, 175, 200)  # pink inner ear / nose
_BN_B = (40, 40, 40)  # black eyes
BUNNY: PixelData = [
    # Row 0: ear tops (2-px wide each, gap of 2 between)
    (1, 0, *_BN_W),
    (2, 0, *_BN_W),
    (5, 0, *_BN_W),
    (6, 0, *_BN_W),
    # Row 1: ears with pink inner lining
    (1, 1, *_BN_W),
    (2, 1, *_BN_P),
    (5, 1, *_BN_P),
    (6, 1, *_BN_W),
    # Row 2: ears continue with pink
    (1, 2, *_BN_W),
    (2, 2, *_BN_P),
    (5, 2, *_BN_P),
    (6, 2, *_BN_W),
    # Row 3: head top (full width)
    (0, 3, *_BN_W),
    (1, 3, *_BN_W),
    (2, 3, *_BN_W),
    (3, 3, *_BN_W),
    (4, 3, *_BN_W),
    (5, 3, *_BN_W),
    (6, 3, *_BN_W),
    (7, 3, *_BN_W),
    # Row 4: eyes (black at cols 2 and 5)
    (0, 4, *_BN_W),
    (1, 4, *_BN_W),
    (2, 4, *_BN_B),
    (3, 4, *_BN_W),
    (4, 4, *_BN_W),
    (5, 4, *_BN_B),
    (6, 4, *_BN_W),
    (7, 4, *_BN_W),
    # Row 5: pink nose at center
    (0, 5, *_BN_W),
    (1, 5, *_BN_W),
    (2, 5, *_BN_W),
    (3, 5, *_BN_P),
    (4, 5, *_BN_P),
    (5, 5, *_BN_W),
    (6, 5, *_BN_W),
    (7, 5, *_BN_W),
    # Row 6: face/cheeks (slightly narrower)
    (1, 6, *_BN_W),
    (2, 6, *_BN_W),
    (3, 6, *_BN_W),
    (4, 6, *_BN_W),
    (5, 6, *_BN_W),
    (6, 6, *_BN_W),
    # Row 7: chin/feet
    (2, 7, *_BN_W),
    (3, 7, *_BN_W),
    (4, 7, *_BN_W),
    (5, 7, *_BN_W),
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
    # Row 0: 2-px top tip (cols 3-4)
    (3, 0, *_ST),
    (4, 0, *_ST),
    # Row 1: same (top continues thin) — gives the long-spike feel
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
    # Crescent's lit pixels span cols 1-19 (width 19). Use physical_width=20
    # so the moon takes 5 logical columns at scale=4, matching the low-res
    # MOON's 5-col footprint and leaving no awkward gap to the next emoji.
    physical_width=20,
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


# ✉️ 32×32 Email — landscape envelope outline with TOP and BOTTOM V-flaps
# meeting at the rectangle's horizontal center, forming an X pattern.
# All-white (no body fill / no color tint) — the unlit panel itself
# provides the negative-space background.
_EMAIL_COLOR = (255, 255, 255)


def _generate_email_hires(size: int = 32) -> tuple[tuple[int, int, int, int, int], ...]:
    """30×20 landscape envelope outline with the classic kite-flap shape.

    - 2-px-thick rectangle border
    - LARGE top V: from inner-top corners DOWN to a meeting point near
      the bottom (~85% down). This is the closed flap covering most of
      the envelope front.
    - SMALL bottom V: from inner-bottom corners UP to the SAME meeting
      point. This is the small triangular pinch at the bottom of the
      envelope — the front-of-envelope edges visible below the flap.

    Together they read as a closed envelope (front-flap dominates with
    a small lip at the bottom) rather than a box-with-X.
    """
    pixels: set[tuple[int, int]] = set()

    # Odd width + odd height so the center column / row are exact
    # integers — otherwise integer Bresenham gives the left and right
    # diagonals subtly different slopes (left half spans 15 cols, right
    # spans 16) and the V looks lopsided.
    rect_w, rect_h = 31, 23
    rect_left = (size - rect_w) // 2  # 0
    rect_right = rect_left + rect_w - 1  # 30
    rect_top = (size - rect_h) // 2  # 4
    rect_bottom = rect_top + rect_h - 1  # 26

    # 2-px-thick rectangle border
    for x in range(rect_left, rect_right + 1):
        pixels.add((x, rect_top))
        pixels.add((x, rect_top + 1))
        pixels.add((x, rect_bottom))
        pixels.add((x, rect_bottom - 1))
    for y in range(rect_top, rect_bottom + 1):
        pixels.add((rect_left, y))
        pixels.add((rect_left + 1, y))
        pixels.add((rect_right, y))
        pixels.add((rect_right - 1, y))

    cx = (rect_left + rect_right) // 2  # 15
    inner_top = rect_top + 2
    inner_bottom = rect_bottom - 2
    inner_left = rect_left + 2
    inner_right = rect_right - 2

    # Top V's tip sits ~65% down the body; bottom V's tip mirrors that
    # height from the bottom edge so both Vs have the SAME ANGLE. The
    # bottom V's tip is ABOVE the top V's tip (visually inside the top
    # flap area) — its diagonals get clipped where they meet the top V,
    # leaving the bottom V's tip hidden behind the closed front flap.
    body_h = inner_bottom - inner_top
    top_meet_y = inner_top + body_h * 75 // 100
    bottom_meet_y = inner_bottom - (top_meet_y - inner_top)

    def _thick_line(x0: int, y0: int, x1: int, y1: int, thickness: int = 3) -> None:
        """N-px-thick Bresenham — each rasterized cell stamps a thickness×
        thickness square so the line reads as bold on the LED panel."""
        dx = abs(x1 - x0)
        dy = abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx - dy
        x, y = x0, y0
        offset = thickness // 2
        while True:
            for tx in range(-offset, thickness - offset):
                for ty in range(-offset, thickness - offset):
                    if 0 <= x + tx < size and 0 <= y + ty < size:
                        pixels.add((x + tx, y + ty))
            if x == x1 and y == y1:
                break
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                x += sx
            if e2 < dx:
                err += dx
                y += sy

    def _line_intersection(
        p1: tuple[float, float],
        p2: tuple[float, float],
        p3: tuple[float, float],
        p4: tuple[float, float],
    ) -> tuple[float, float] | None:
        """Find the intersection of line segments p1-p2 and p3-p4."""
        x1, y1 = p1
        x2, y2 = p2
        x3, y3 = p3
        x4, y4 = p4
        denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
        if denom == 0:
            return None
        t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denom
        return (x1 + t * (x2 - x1), y1 + t * (y2 - y1))

    # Top V flap (full): inner-top corners → top meeting point
    _thick_line(inner_left, inner_top, cx, top_meet_y, thickness=2)
    _thick_line(inner_right, inner_top, cx, top_meet_y, thickness=2)

    # Bottom V — same angle as top V, but the diagonals are CLIPPED at
    # the point where they cross the top V's diagonals. The "true" tip
    # at (cx, bottom_meet_y) is hidden behind the front flap; only the
    # outer corner stubs are visible.
    left_clip = _line_intersection(
        (inner_left, inner_top),
        (cx, top_meet_y),
        (inner_left, inner_bottom),
        (cx, bottom_meet_y),
    )
    right_clip = _line_intersection(
        (inner_right, inner_top),
        (cx, top_meet_y),
        (inner_right, inner_bottom),
        (cx, bottom_meet_y),
    )
    if left_clip is not None:
        _thick_line(
            inner_left,
            inner_bottom,
            int(round(left_clip[0])),
            int(round(left_clip[1])),
            thickness=2,
        )
    if right_clip is not None:
        _thick_line(
            inner_right,
            inner_bottom,
            int(round(right_clip[0])),
            int(round(right_clip[1])),
            thickness=2,
        )

    return tuple((x, y, *_EMAIL_COLOR) for (x, y) in pixels)


EMAIL_HIRES = HiResEmoji(
    pixels=_generate_email_hires(size=32),
    physical_size=32,
)


# ⚾ Hi-res baseball — white ball with two diagonal seams forming an
# offset figure-8, plus red hash stitches alongside each seam (matches
# the standard pixel-art baseball convention). Earlier "closed-eye"
# version had the seams meeting at top/bottom poles, which read more
# as a flat football than a 3D ball.
_BASEBALL_WHITE = (250, 250, 245)
_BASEBALL_EDGE = (200, 200, 210)
_BASEBALL_RED = (200, 30, 40)


def _generate_baseball_hires(
    size: int = 32,
) -> tuple[tuple[int, int, int, int, int], ...]:
    import math

    cx = cy = (size - 1) / 2.0
    body_r = size / 2 - 0.5  # use full canvas

    pixels: dict[tuple[int, int], tuple[int, int, int]] = {}

    # Step 1: solid white ball with subtle 1-px gray edge so the round
    # silhouette reads cleanly against a black panel.
    for y in range(size):
        for x in range(size):
            dx = x - cx
            dy = y - cy
            d = math.sqrt(dx * dx + dy * dy)
            if d > body_r:
                continue
            if d > body_r - 1.0:
                pixels[(x, y)] = _BASEBALL_EDGE
            else:
                pixels[(x, y)] = _BASEBALL_WHITE

    # Step 2: two seam curves traced as quadratic Béziers. Together they
    # form an offset figure-8: the upper seam sweeps from upper-right
    # down toward mid-left, and the lower seam sweeps from mid-right
    # down toward lower-left. The control points sit just past center
    # so each curve has a gentle S-shape rather than a tight arc.
    def bezier(
        p0: tuple[float, float],
        p1: tuple[float, float],
        p2: tuple[float, float],
        t: float,
    ) -> tuple[float, float]:
        u = 1 - t
        return (
            u * u * p0[0] + 2 * u * t * p1[0] + t * t * p2[0],
            u * u * p0[1] + 2 * u * t * p1[1] + t * t * p2[1],
        )

    def trace_seam(
        p0: tuple[float, float],
        p1: tuple[float, float],
        p2: tuple[float, float],
        n: int = 64,
    ) -> list[tuple[float, float]]:
        path: list[tuple[float, float]] = []
        for i in range(n + 1):
            t = i / n
            sx, sy = bezier(p0, p1, p2, t)
            path.append((sx, sy))
            ix, iy = int(round(sx)), int(round(sy))
            if (ix, iy) in pixels and pixels[(ix, iy)] != _BASEBALL_EDGE:
                pixels[(ix, iy)] = _BASEBALL_RED
        return path

    # Upper seam: top-left → mid-right (leans /). Top stitches sit in
    # the upper-right quadrant of the ball.
    seam1 = trace_seam(
        p0=(cx - 2, cy - body_r * 0.92),  # near top, slightly left of center
        p1=(cx + 0, cy - body_r * 0.20),  # control: above center
        p2=(cx + body_r * 0.92, cy + 2),  # mid-right, slightly below center
    )
    # Lower seam: mid-left → bottom-right (also leans /). Both seams
    # lean the same way — two parallel diagonal stripes — matching the
    # reference baseball where the seams trace a 3D figure-8 that
    # projects to two parallel arcs on one side of the ball.
    seam2 = trace_seam(
        p0=(cx - body_r * 0.92, cy - 2),  # mid-left, slightly above center
        p1=(cx + 0, cy + body_r * 0.20),  # control: below center
        p2=(cx + 2, cy + body_r * 0.92),  # near bottom, slightly right of center
    )

    # Step 3: hash stitches — small red squares offset perpendicular to
    # each seam at evenly-spaced points along the curve. Reads as the
    # cross-stitch threads visible on a real baseball.
    n_stitches = 9
    for path in (seam1, seam2):
        for i in range(n_stitches):
            t_idx = int((i + 0.5) / n_stitches * (len(path) - 1))
            if t_idx >= len(path) - 1:
                continue
            sx, sy = path[t_idx]
            sx_next, sy_next = path[t_idx + 1]
            tx, ty = sx_next - sx, sy_next - sy
            tlen = math.sqrt(tx * tx + ty * ty)
            if tlen == 0:
                continue
            tx, ty = tx / tlen, ty / tlen
            # Drop a 1-px stitch on each side of the seam, perpendicular
            # to the local tangent (rotate tangent by ±90°).
            for sign in (-1, 1):
                px = sx + sign * 1.5 * ty
                py = sy - sign * 1.5 * tx
                ix, iy = int(round(px)), int(round(py))
                if (ix, iy) in pixels and pixels[(ix, iy)] != _BASEBALL_EDGE:
                    pixels[(ix, iy)] = _BASEBALL_RED

    return tuple((x, y, *c) for (x, y), c in pixels.items())


BASEBALL_HIRES = HiResEmoji(
    pixels=_generate_baseball_hires(size=32),
    physical_size=32,
)


# 🌸 Hi-res flower — cherry-blossom layout: 5 pink petals at 72° intervals
# with notched tips, a yellow center, and red stamen dots. No stem (the
# 8×8 fallback keeps its stem-and-leaf since it has no room for proper
# petals; this hi-res variant matches the canonical 🌸 silhouette).
_PETAL_PINK = (255, 175, 205)
_PETAL_LIGHT = (255, 210, 225)  # tip highlight
_PETAL_DARK = (230, 125, 165)  # base shadow
_FLOWER_YELLOW = (255, 220, 80)
_FLOWER_YELLOW_DARK = (220, 180, 50)
_FLOWER_RED = (220, 60, 80)


def _generate_flower_hires(
    size: int = 32,
) -> tuple[tuple[int, int, int, int, int], ...]:
    import math

    cx = cy = (size - 1) / 2.0

    # Petal placement: ovals oriented along their radial direction.
    # `petal_dist` = distance from flower center to petal center.
    # `petal_major`/`petal_minor` = ellipse semi-axes (radial / tangential).
    petal_dist = size * 0.27
    petal_major = size * 0.27  # = petal_dist → inner edge sits at flower center
    petal_minor = size * 0.15  # narrow enough that adjacent petals don't merge
    # Notch: a small triangular cutout at each petal tip, creating the
    # cherry-blossom indent. Implemented as a circle subtraction; tuned
    # so the cut is visible without leaving ear-nub pixels.
    notch_dist = size * 0.55  # past the tip — only the "near side" carves
    notch_r = size * 0.06

    center_r = size * 0.18  # large enough to cover petal-base overlap
    stamen_r_dist = center_r * 0.6  # how far out the stamen dots sit

    pixels: dict[tuple[int, int], tuple[int, int, int]] = {}

    angles = [-math.pi / 2 + i * 2 * math.pi / 5 for i in range(5)]

    # Step 1: paint the 5 petals
    for angle in angles:
        # Petal centerpoint
        pcx = cx + petal_dist * math.cos(angle)
        pcy = cy + petal_dist * math.sin(angle)
        # Notch centerpoint (further out along the same radial direction)
        ncx = cx + notch_dist * math.cos(angle)
        ncy = cy + notch_dist * math.sin(angle)
        # Petal local axes
        rx, ry = math.cos(angle), math.sin(angle)
        px_, py_ = -math.sin(angle), math.cos(angle)

        for y in range(size):
            for x in range(size):
                dx = x - pcx
                dy = y - pcy
                u = dx * rx + dy * ry  # along radial (length)
                v = dx * px_ + dy * py_  # perpendicular (width)
                if (u / petal_major) ** 2 + (v / petal_minor) ** 2 > 1:
                    continue
                # Notch cutout (subtracts a circle past the tip so the
                # petal apex is concave, not pointed)
                ndx = x - ncx
                ndy = y - ncy
                if ndx * ndx + ndy * ndy <= notch_r * notch_r:
                    continue

                # Radial-position-based shading: tip lighter, base darker
                if u > petal_major * 0.45:
                    color = _PETAL_LIGHT
                elif u < -petal_major * 0.25:
                    color = _PETAL_DARK
                else:
                    color = _PETAL_PINK
                pixels[(x, y)] = color

    # Step 2: paint the yellow center on top of petal overlap
    for y in range(size):
        for x in range(size):
            dx = x - cx
            dy = y - cy
            d = math.sqrt(dx * dx + dy * dy)
            if d <= center_r:
                if d > center_r - 0.9:
                    pixels[(x, y)] = _FLOWER_YELLOW_DARK
                else:
                    pixels[(x, y)] = _FLOWER_YELLOW

    # Step 3: red stamen dots — 5 single-pixel dots inside the yellow
    # center, aligned WITH the petals so each stamen "points to" its
    # petal. Single pixels at this density; a plus-pattern reads as
    # a single blob.
    for angle in angles:
        sx = cx + stamen_r_dist * math.cos(angle)
        sy = cy + stamen_r_dist * math.sin(angle)
        p = (int(round(sx)), int(round(sy)))
        if p in pixels:
            pixels[p] = _FLOWER_RED

    return tuple((x, y, *c) for (x, y), c in pixels.items())


FLOWER_HIRES = HiResEmoji(
    pixels=_generate_flower_hires(size=32),
    physical_size=32,
)


# 🌮 Hi-res taco — landscape half-moon shell with filling along the top
# edge and sesame-seed dots on the shell body. Matches the reference
# pixel-art convention: cheese-yellow shell with a darker rim along
# the bottom curve, dark-brown outline, and lettuce/tomato/meat
# chunks bulging out above the shell opening.
_TACO_SHELL = (245, 195, 80)
_TACO_SHELL_RIM = (210, 150, 45)
_TACO_OUTLINE = (90, 55, 20)
_TACO_LETTUCE = (95, 175, 55)
_TACO_LETTUCE_DARK = (60, 130, 35)
_TACO_TOMATO = (220, 60, 50)
_TACO_MEAT = (135, 75, 40)
_TACO_SEED = (200, 140, 40)


def _generate_taco_hires(
    size: int = 32,
) -> tuple[tuple[int, int, int, int, int], ...]:
    pixels: dict[tuple[int, int], tuple[int, int, int]] = {}

    cx = (size - 1) / 2.0  # 15.5

    # Dome silhouette: FLAT bottom (taco resting on a surface) + curved
    # top + sides curving inward. Geometrically the UPPER half of an
    # ellipse anchored at (cx, bottom_y). Slightly oversized vs the
    # toppings so the upper-left toppings sit on shell color, not
    # black panel.
    bottom_y = 27  # flat bottom of shell (3-row margin to canvas edge)
    shell_a = 15.0  # horizontal semi-axis
    shell_b = 15.5  # vertical semi-axis (apex of dome at bottom_y - b)

    # Step 1: fill the shell body (upper half of ellipse)
    for y in range(size):
        for x in range(size):
            dx = x - cx
            dy = bottom_y - y  # positive when above the flat bottom
            if dy < 0 or dy > shell_b:
                continue
            r2 = (dx * dx) / (shell_a * shell_a) + (dy * dy) / (shell_b * shell_b)
            if r2 > 1.0:
                continue
            pixels[(x, y)] = _TACO_SHELL

    # Step 2: 1-px-thick darker rim along the FLAT bottom and a thin
    # band along the curved top of the shell where it meets the
    # filling. (The flat bottom rim is the "crust"; the top rim
    # separates the shell color from the filling cluster.)
    for x in range(size):
        if (x, bottom_y) in pixels:
            pixels[(x, bottom_y)] = _TACO_SHELL_RIM
            # 1-row outline below the bottom edge
            if bottom_y + 1 < size:
                pixels[(x, bottom_y + 1)] = _TACO_OUTLINE

    # Step 3: dark-brown outline along the curved sides of the shell
    # (left + right + curved top). For each row, find the leftmost and
    # rightmost shell pixel and place an outline pixel just outside.
    for y in range(size):
        shell_xs = [
            x for x in range(size) if (x, y) in pixels and pixels[(x, y)] == _TACO_SHELL
        ]
        if not shell_xs:
            continue
        x_min, x_max = min(shell_xs), max(shell_xs)
        for ox in (x_min - 1, x_max + 1):
            if 0 <= ox < size and (ox, y) not in pixels:
                pixels[(ox, y)] = _TACO_OUTLINE

    # Step 4: filling cascade — replicates the low-res taco's pattern.
    # The low-res has a WIDE cluster across rows 0-2 then narrows
    # sharply and shifts LEFT for rows 3-5. This scaled-up version
    # keeps the same structure: wide+stable at the top, then a tail
    # that cascades down into the dome's lower-left interior.
    L = _TACO_LETTUCE
    LD = _TACO_LETTUCE_DARK
    R = _TACO_TOMATO
    M = _TACO_MEAT
    palette = [L, R, M, L, R, L, M, L, R, L, M, R]

    # Each row: (y, col_start, col_end). Mirrors the low-res cascade
    # but shifted DOWN so the cluster sits INSIDE the shell silhouette
    # rather than floating above it. The top sits ~2 rows above the
    # shell apex (slight peek), and the cascade descends through the
    # shell's upper-left interior, ending in the lower-left.
    fill_rows: list[tuple[int, int, int]] = [
        # Tiny lettuce cap peeks just above the shell apex — single
        # narrow row so the topping mound doesn't break the silhouette.
        (11, 13, 17),
        # Main cascade with HOURGLASS-style pinch (v17 dimensions).
        # The slightly enlarged shell (shell_a=15, shell_b=15.5) now
        # covers all the topping pixels — no floating over black.
        (12, 11, 19),
        (13, 10, 19),
        (14, 8, 20),
        (15, 6, 18),
        (16, 5, 14),  # right edge pinches in
        (17, 4, 11),  # most pinched — front shell illusion
        (18, 4, 10),
        (19, 3, 10),
        (20, 3, 9),
        (21, 2, 7),
        (22, 1, 5),
        (23, 1, 3),  # reaches lower-left interior of shell
        (24, 1, 2),
    ]
    for y, col_l, col_r in fill_rows:
        for x in range(col_l, col_r + 1):
            # Color picker. Top row gets darker green tips for a leafy
            # cap; rest cycles through the palette by position.
            if y == fill_rows[0][0]:
                color = LD if (x - col_l) % 3 == 1 else L
            else:
                color = palette[(x * 2 + y * 3) % len(palette)]
            if 0 <= x < size and 0 <= y < size:
                pixels[(x, y)] = color

    # Step 5: outline around the filling's outer top
    filling_keys = [
        k
        for k, v in pixels.items()
        if v
        in (
            _TACO_LETTUCE,
            _TACO_LETTUCE_DARK,
            _TACO_TOMATO,
            _TACO_MEAT,
        )
    ]
    for x, y in filling_keys:
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1)):
            if 0 <= nx < size and 0 <= ny < size and (nx, ny) not in pixels:
                pixels[(nx, ny)] = _TACO_OUTLINE

    # Step 6: sesame-seed dots scattered on the shell body
    for sx, sy in ((6, 20), (10, 24), (14, 22), (19, 24), (24, 21), (12, 26), (20, 26)):
        if (sx, sy) in pixels and pixels[(sx, sy)] == _TACO_SHELL:
            pixels[(sx, sy)] = _TACO_SEED

    return tuple((x, y, *c) for (x, y), c in pixels.items())


TACO_HIRES = HiResEmoji(
    pixels=_generate_taco_hires(size=32),
    physical_size=32,
)


# 🐰 Hi-res bunny — two long pink-lined ears at top, white head with
# black eyes, pink nose. Matches the canonical 🐰 emoji silhouette.
_BUNNY_WHITE = (245, 245, 245)
_BUNNY_PINK = (255, 175, 200)
_BUNNY_BLACK = (40, 40, 40)
_BUNNY_OUTLINE = (175, 175, 180)  # subtle gray edge


def _generate_bunny_hires(
    size: int = 32,
) -> tuple[tuple[int, int, int, int, int], ...]:
    pixels: dict[tuple[int, int], tuple[int, int, int]] = {}

    cx = (size - 1) / 2.0  # 15.5

    # Ears — two vertical ellipses at the top with white outer + pink
    # inner lining. Centered ~5 cols to each side of cx.
    ear_a = 3.0  # horizontal semi-axis
    ear_b = 9.0  # vertical semi-axis
    ear_cy = 10.0
    ear_offset = 5.0  # distance from cx to each ear's center
    for ear_cx in (cx - ear_offset, cx + ear_offset):
        for y in range(size):
            for x in range(size):
                dx = x - ear_cx
                dy = y - ear_cy
                r2 = (dx * dx) / (ear_a * ear_a) + (dy * dy) / (ear_b * ear_b)
                if r2 <= 1.0:
                    # Outer ring is white, inner is pink (the inside of the ear)
                    if r2 > 0.45:
                        pixels[(x, y)] = _BUNNY_WHITE
                    else:
                        pixels[(x, y)] = _BUNNY_PINK

    # Head — horizontal ellipse below the ears.
    head_cx = cx
    head_cy = 21.0
    head_a = 11.0
    head_b = 7.5
    for y in range(size):
        for x in range(size):
            dx = x - head_cx
            dy = y - head_cy
            r2 = (dx * dx) / (head_a * head_a) + (dy * dy) / (head_b * head_b)
            if r2 <= 1.0:
                pixels[(x, y)] = _BUNNY_WHITE

    # Eyes — two small black ovals on the head
    eye_y = 19
    eye_offset = 4.5
    for ex in (cx - eye_offset, cx + eye_offset):
        for dy in range(-1, 2):
            for dx in range(-1, 2):
                px = int(round(ex)) + dx
                py = eye_y + dy
                if (px, py) in pixels and dx * dx + dy * dy <= 2:
                    pixels[(px, py)] = _BUNNY_BLACK

    # Pink nose — small triangle/diamond at center
    nose_cy = 22
    for dy in (-1, 0):
        for dx in (-1, 0, 1):
            if abs(dx) + abs(dy) <= 1:
                px = int(round(cx)) + dx
                py = nose_cy + dy
                if (px, py) in pixels:
                    pixels[(px, py)] = _BUNNY_PINK

    # Subtle outline — for any white body pixel, if any 4-neighbor is
    # outside the bunny, paint the neighbor as a soft gray edge.
    body_keys = [k for k, v in pixels.items() if v == _BUNNY_WHITE]
    for x, y in body_keys:
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if 0 <= nx < size and 0 <= ny < size and (nx, ny) not in pixels:
                pixels[(nx, ny)] = _BUNNY_OUTLINE

    return tuple((x, y, *c) for (x, y), c in pixels.items())


BUNNY_HIRES = HiResEmoji(
    pixels=_generate_bunny_hires(size=32),
    physical_size=32,
)


# 🐱 Hi-res cat — round face with triangular pointy ears, two large
# eyes with pupils, small pink nose, and pink cheek blushes. Color
# variants share the same geometry; only face/eye colors differ.
def _generate_cat_hires(
    face: tuple[int, int, int],
    eye: tuple[int, int, int],
    size: int = 32,
) -> tuple[tuple[int, int, int, int, int], ...]:
    pixels: dict[tuple[int, int], tuple[int, int, int]] = {}

    cx = (size - 1) / 2.0
    nose_pink = (255, 140, 175)
    cheek_pink = (255, 160, 195)
    inner_ear = (250, 130, 170)
    pupil = (35, 35, 40)

    # Step 1: triangular ears, FULLY ABOVE the head (no overlap).
    # Each ear is a small triangle: apex (1 px) at row 5, base (7 px
    # wide) at row 9 — just above where the head's top arc begins.
    # NB: ear centers are explicit integers so int rounding doesn't
    # create gaps in the triangle (cx is .5 → banker's rounding loses
    # alternate columns).
    def _fill_triangle(
        v0: tuple[int, int],
        v1: tuple[int, int],
        v2: tuple[int, int],
        color: tuple[int, int, int],
        only_existing: bool = False,
    ) -> None:
        """Rasterize a triangle defined by 3 vertices into `pixels`.
        If `only_existing` is True, paint only cells already present
        (used for the inner-pink layer, which sits inside the outer
        ear and shouldn't extend beyond it).
        """

        def edge(p, a, b):
            return (p[0] - b[0]) * (a[1] - b[1]) - (a[0] - b[0]) * (p[1] - b[1])

        xs = (v0[0], v1[0], v2[0])
        ys = (v0[1], v1[1], v2[1])
        for y in range(min(ys), max(ys) + 1):
            for x in range(min(xs), max(xs) + 1):
                if not (0 <= x < size and 0 <= y < size):
                    continue
                p = (x, y)
                d1 = edge(p, v0, v1)
                d2 = edge(p, v1, v2)
                d3 = edge(p, v2, v0)
                has_neg = d1 < 0 or d2 < 0 or d3 < 0
                has_pos = d1 > 0 or d2 > 0 or d3 > 0
                if has_neg and has_pos:
                    continue
                if only_existing and (x, y) not in pixels:
                    continue
                pixels[(x, y)] = color

    cx_int = int(round(cx))
    ear_offset = 7
    # Each ear is a triangle with 3 explicit vertices:
    #   - apex: top, slightly OUTWARD of the outer base corner
    #   - outer_base: bottom-OUTER corner (lower)
    #   - inner_base: bottom-INNER corner (HIGHER than outer_base)
    # The base tilts up toward the head's center, mirroring the head's
    # curve so the ears don't look pasted on flat.
    # Apex column matches the outer base column (no single-pixel apex
    # overhang). Visual outward lean comes from the TILTED BASE alone
    # (inner base higher than outer), not from an outward-shifted apex.
    apex_outward_off = 3
    base_outer_half_w = 3
    base_inner_half_w = 4  # 1 col WIDER on the inner side — thickens the
    # ear's inner edge so it tapers more gradually toward the head
    ear_apex_y = 7
    outer_base_y = 16
    inner_base_y = 13  # tilt: inner base 3 rows higher than outer
    for ear_cx_int, dir_sign in (
        (cx_int - ear_offset, -1),
        (cx_int + ear_offset, 1),
    ):
        # 2-px-wide flat apex (avoids single-pixel point at the top).
        # Two overlapping triangles whose apexes are at adjacent cols
        # union into a small trapezoid.
        outer_apex = (ear_cx_int + dir_sign * apex_outward_off, ear_apex_y)
        inner_apex = (
            ear_cx_int + dir_sign * (apex_outward_off - 1),
            ear_apex_y,
        )
        outer_base = (ear_cx_int + dir_sign * base_outer_half_w, outer_base_y)
        inner_base = (ear_cx_int - dir_sign * base_inner_half_w, inner_base_y)
        _fill_triangle(outer_apex, outer_base, inner_base, face)
        _fill_triangle(inner_apex, outer_base, inner_base, face)

    # Inner pink — same tilted-triangle shape, inset 1-2 rows/cols.
    # `inner_apex_outward` matches `inner_outer_half_w` so the top pink
    # pixel aligns with the rest of the pink body (no single-pixel
    # overhang at the inner apex).
    inner_apex_outward = 2
    inner_outer_half_w = 2
    inner_inner_half_w = 3  # 1 wider on inner side (matches outer ear)
    inner_apex_y = ear_apex_y + 2
    inner_outer_base_y = outer_base_y - 2
    inner_inner_base_y = inner_base_y - 1
    for ear_cx_int, dir_sign in (
        (cx_int - ear_offset, -1),
        (cx_int + ear_offset, 1),
    ):
        apex = (ear_cx_int + dir_sign * inner_apex_outward, inner_apex_y)
        outer_base = (ear_cx_int + dir_sign * inner_outer_half_w, inner_outer_base_y)
        inner_base = (ear_cx_int - dir_sign * inner_inner_half_w, inner_inner_base_y)
        _fill_triangle(apex, outer_base, inner_base, inner_ear, only_existing=True)

    # Step 2: round head — slightly taller ellipse so it meets the ears
    head_cx = cx
    head_cy = 19.5
    head_a = 11.5
    head_b = 9.5
    for y in range(size):
        for x in range(size):
            dx = x - head_cx
            dy = y - head_cy
            r2 = (dx * dx) / (head_a * head_a) + (dy * dy) / (head_b * head_b)
            if r2 <= 1.0 and (x, y) not in pixels:
                pixels[(x, y)] = face

    # Step 3: eyes — two oval shapes with pupil dots
    eye_y = 19
    eye_offset = 5
    eye_w = 2.0
    eye_h = 2.5
    for ex in (cx - eye_offset, cx + eye_offset):
        for y in range(size):
            for x in range(size):
                dx = x - ex
                dy = y - eye_y
                if (dx * dx) / (eye_w * eye_w) + (dy * dy) / (eye_h * eye_h) <= 1 and (
                    x,
                    y,
                ) in pixels:
                    pixels[(x, y)] = eye
        # Pupil — small black dot in the center of each eye
        ix = int(round(ex))
        for dy in range(-1, 1):
            p = (ix, eye_y + dy)
            if p in pixels:
                pixels[p] = pupil

    # Step 4: small pink nose — 3-px triangle at face center
    nose_y = 23
    pixels[(cx_int - 1, nose_y)] = nose_pink
    pixels[(cx_int, nose_y)] = nose_pink
    pixels[(cx_int, nose_y + 1)] = nose_pink

    # Step 5: pink cheek blush — 2×2 dots on each side
    cheek_y = 24
    for dx_offset in (-7, 6):
        for dx in (0, 1):
            for dy in (0, 1):
                p = (cx_int + dx_offset + dx, cheek_y + dy)
                if p in pixels and pixels[p] == face:
                    pixels[p] = cheek_pink

    return tuple((x, y, *c) for (x, y), c in pixels.items())


CAT_HIRES = HiResEmoji(
    pixels=_generate_cat_hires(_CAT_PALETTE[0][1], _CAT_PALETTE[0][2]),
    physical_size=32,
)
CAT_HIRES_VARIANTS: dict[str, HiResEmoji] = {
    f"cat_{name}": HiResEmoji(
        pixels=_generate_cat_hires(face, eye),
        physical_size=32,
    )
    for name, face, eye in _CAT_PALETTE
}


# ❤️ Hi-res heart — uses the classic implicit heart curve to generate
# a smooth shape: two rounded humps at top, tapering to a point at
# the bottom. Flat solid color body with a 1-px darker outline.
def _generate_heart_hires(
    body: tuple[int, int, int],
    outline: tuple[int, int, int],
    size: int = 32,
) -> tuple[tuple[int, int, int, int, int], ...]:
    """Heart shape via implicit curve `(x²+y²-1)³ - x²·y³ < 0`.

    Coordinates are normalized to [-1.3, 1.3] so the heart fills most
    of the canvas with a small margin. y is flipped so the heart's
    point sits at the bottom of the image. `body` is the solid fill
    color; `outline` is a 1-px darker rim along the silhouette.
    """
    pixels: dict[tuple[int, int], tuple[int, int, int]] = {}

    cx = (size - 1) / 2.0
    cy = (size - 1) / 2.0
    scale = size / 2.6

    for y in range(size):
        for x in range(size):
            nx = (x - cx) / scale
            ny = (cy - y) / scale + 0.25  # vertical bias: shift down a bit
            inside = (nx * nx + ny * ny - 1) ** 3 - nx * nx * ny * ny * ny < 0
            if inside:
                pixels[(x, y)] = body

    # 1-px darker rim — crisp edge against the unlit LED panel.
    body_keys = list(pixels.keys())
    for x, y in body_keys:
        for nx_off, ny_off in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if (
                0 <= nx_off < size
                and 0 <= ny_off < size
                and (nx_off, ny_off) not in pixels
            ):
                pixels[(nx_off, ny_off)] = outline

    return tuple((x, y, *c) for (x, y), c in pixels.items())


HEART_HIRES = HiResEmoji(
    pixels=_generate_heart_hires(_HEART_PALETTE[0][1], _HEART_PALETTE[0][2]),
    physical_size=32,
)
HEART_HIRES_VARIANTS: dict[str, HiResEmoji] = {
    f"heart_{name}": HiResEmoji(
        pixels=_generate_heart_hires(body, outline),
        physical_size=32,
    )
    for name, body, outline in _HEART_PALETTE
}


# 🏳️‍🌈 Hi-res pride flags — same horizontal-stripe layouts as the
# 8×8 versions, scaled to 32×32 so each stripe is a clean band.
def _generate_pride_hires(
    slug: str, size: int = 32
) -> tuple[tuple[int, int, int, int, int], ...]:
    if slug == "demi":
        base = _flag_stripes_pixels(_DEMI_STRIPES, size, size)
        for tx, ty in _demi_triangle_pixels(size, size):
            base[(tx, ty)] = _DEMI_TRIANGLE
    else:
        for s, stripes in _PRIDE_FLAGS:
            if s == slug:
                base = _flag_stripes_pixels(stripes, size, size)
                break
        else:
            raise KeyError(slug)
    return tuple((x, y, *c) for (x, y), c in base.items())


PRIDE_HIRES = HiResEmoji(
    pixels=_generate_pride_hires("rainbow"),
    physical_size=32,
)
PRIDE_HIRES_VARIANTS: dict[str, HiResEmoji] = {
    f"pride_{slug}": HiResEmoji(
        pixels=_generate_pride_hires(slug),
        physical_size=32,
    )
    for slug in tuple(s for s, _ in _PRIDE_FLAGS) + ("demi",)
}


# 🔴⚪ Hi-res pokeball — round ball with red top, white bottom, black
# band across the middle with a white button. 1-px black outline along
# the silhouette.
def _generate_pokeball_hires(
    size: int = 32,
) -> tuple[tuple[int, int, int, int, int], ...]:
    import math

    pixels: dict[tuple[int, int], tuple[int, int, int]] = {}

    cx = cy = (size - 1) / 2.0
    body_r = size / 2 - 0.5
    band_half_h = 1.5  # 3-px-thick band — thinner so the button pops out
    button_outer_r = body_r * 0.30  # outer black ring of the button
    button_inner_r = button_outer_r - 1.5  # white center

    # Step 1: fill the ball — red above the equator, white below.
    for y in range(size):
        for x in range(size):
            dx = x - cx
            dy = y - cy
            d = math.sqrt(dx * dx + dy * dy)
            if d > body_r:
                continue
            pixels[(x, y)] = _PB_R if dy < 0 else _PB_W

    # Step 2: black band across the middle (3 rows)
    for y in range(size):
        for x in range(size):
            dx = x - cx
            dy = y - cy
            d = math.sqrt(dx * dx + dy * dy)
            if d > body_r:
                continue
            if abs(dy) <= band_half_h:
                pixels[(x, y)] = _PB_K

    # Step 3: button — black outer ring + white inner, large enough that
    # it extends BEYOND the band into both halves (the iconic pokeball
    # button pops out of the band).
    for y in range(size):
        for x in range(size):
            dx = x - cx
            dy = y - cy
            d2 = dx * dx + dy * dy
            if d2 <= button_outer_r * button_outer_r:
                pixels[(x, y)] = _PB_K
    for y in range(size):
        for x in range(size):
            dx = x - cx
            dy = y - cy
            d2 = dx * dx + dy * dy
            if d2 <= button_inner_r * button_inner_r:
                pixels[(x, y)] = _PB_W

    # Step 4: 1-px black outline along the silhouette — paint any
    # not-yet-set cell whose 4-neighbor is inside the ball.
    body_keys = list(pixels.keys())
    for x, y in body_keys:
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if 0 <= nx < size and 0 <= ny < size and (nx, ny) not in pixels:
                pixels[(nx, ny)] = _PB_K

    return tuple((x, y, *c) for (x, y), c in pixels.items())


POKEBALL_HIRES = HiResEmoji(
    pixels=_generate_pokeball_hires(size=32),
    physical_size=32,
)


def _build_emoji_registry() -> dict[str, PixelData]:
    """Build the emoji registry with all available icons."""
    from led_ticker.widgets.weather_icons import (
        CLOUD,
        FOG,
        PARTLY_CLOUDY,
        RAIN,
        SNOW,
        SUN,
        THUNDER,
    )

    registry = {
        # Sports
        "baseball": BASEBALL,
        "flower": FLOWER,
        "star": STAR,
        # Food
        "taco": TACO,
        # Weather
        "sun": SUN,
        "cloud": CLOUD,
        "partly_cloudy": PARTLY_CLOUDY,
        "rain": RAIN,
        "snow": SNOW,
        "thunder": THUNDER,
        "fog": FOG,
        # Celestial
        "moon": MOON,
        # Social
        "instagram": INSTAGRAM,
        "email": EMAIL,
        # Animals
        "bunny": BUNNY,
        "cat": CAT,
        # Symbols
        "heart": HEART,
    }
    # Rainbow heart variants — :heart_red:, :heart_blue:, etc.
    registry.update(HEART_LOWRES_VARIANTS)
    # Pride flags — :pride: (rainbow), :pride_bi:, :pride_trans:, etc.
    registry["pride"] = PRIDE
    registry.update(PRIDE_LOWRES_VARIANTS)
    # Pokeball
    registry["pokeball"] = POKEBALL
    # Cat color variants
    registry.update(CAT_LOWRES_VARIANTS)
    return registry


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
    # Sports
    "baseball": BASEBALL_HIRES,
    # Botanical
    "flower": FLOWER_HIRES,
    # Food
    "taco": TACO_HIRES,
    # Animals
    "bunny": BUNNY_HIRES,
    "cat": CAT_HIRES,
    **CAT_HIRES_VARIANTS,
    # Symbols
    "heart": HEART_HIRES,
    **HEART_HIRES_VARIANTS,
    # Pride flags
    "pride": PRIDE_HIRES,
    **PRIDE_HIRES_VARIANTS,
    # Games
    "pokeball": POKEBALL_HIRES,
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


def measure_width(
    font: Font,
    text: str,
    canvas: Canvas | None = None,
    max_emoji_height: int | None = None,
) -> int:
    """Measure total width of text with emoji slugs expanded.

    When `canvas` is a `ScaledCanvas` AND the slug has a hi-res variant
    that fits within `max_emoji_height`, use the hi-res sprite's logical
    width — otherwise this underestimates the rendered width (low-res
    FLOWER is 5 wide; hi-res FLOWER at scale=4 is 8 logical wide), and
    overflow-scroll detection silently fails when the rendered content
    doesn't fit.

    The `max_emoji_height` mirrors `draw_with_emoji`'s parameter — when
    a hi-res sprite would exceed the row band (e.g. two_row at scale=2),
    the renderer falls back to low-res, and so should the measurement.
    """
    from led_ticker.drawing import get_text_width

    segments = _parse_segments(text)
    width = 0
    use_hires = isinstance(canvas, ScaledCanvas)
    for seg_type, value in segments:
        if seg_type == "emoji":
            measured = None
            if use_hires and value in HIRES_REGISTRY:
                hires = HIRES_REGISTRY[value]
                logical_h = hires.physical_size // canvas.scale
                if max_emoji_height is None or logical_h <= max_emoji_height:
                    measured = hires.logical_width(canvas.scale)
            if measured is None:
                measured = _emoji_width(_get_registry()[value])
            width += measured + EMOJI_PADDING
        else:
            width += get_text_width(font, value, padding=0, canvas=canvas)
    return width


def draw_with_emoji(
    canvas: Canvas,
    font: Font,
    cursor_pos: int,
    y: int,
    color: Any,
    text: str,
    y_offset: int = 0,
    emoji_y: int | None = None,
    max_emoji_height: int | None = None,
    frame: int = 0,
) -> int:
    """Draw text with inline emoji. Returns pixels advanced.

    `color` accepts either a `graphics.Color` (legacy path; whole-string
    color) or a `ColorProvider` (rainbow / gradient / color_cycle / etc).
    When a per-char provider is passed, text segments render
    character-by-character with `provider.color_for(frame, char_index,
    total_text_chars)`. The character index is GLOBAL across segments,
    so a rainbow sweep continues seamlessly across emoji slugs without
    resetting at each `:slug:`. `total_text_chars` excludes emoji slugs
    (sprites get their own colors and don't participate in the sweep).

    `emoji_y` overrides the icon's top-row position. Default is derived
    from the font: for BDF fonts it remains `4 + y_offset` (preserving
    visuals validated on real hardware); for HiresFont it is
    `(line_height - 8) // 2 + y_offset` to center the 8×8 sprite in the
    taller glyph cell. Multi-row widgets (e.g. `two_row`) pass an
    explicit `emoji_y` per row so the icon aligns with the row's text
    baseline instead of the canvas center.

    `max_emoji_height` is the maximum logical height the emoji is
    allowed to occupy (used by multi-row widgets). When the hi-res
    sprite's logical height exceeds this, the renderer falls back to
    the 8×8 low-res sprite — prevents a hi-res icon from overflowing
    the row's vertical space and overlapping the next row.

    `frame` is forwarded to `provider.color_for(...)` for frame-aware
    effects. Defaults to 0 for legacy callers passing a raw `Color`.
    """
    segments = _parse_segments(text)
    total: int = 0

    # Detect a ColorProvider — duck-typed so we don't import the
    # protocol class here just to isinstance against it.
    is_provider = hasattr(color, "color_for")
    per_char = is_provider and getattr(color, "per_char", False)

    # Pre-compute the total count of TEXT characters across all
    # segments. Emoji slugs don't participate in the per-char color
    # sweep — their sprites carry their own pixel colors. Using this
    # total means the rainbow distributes evenly across the visible
    # letters rather than e.g. compressing because the slug expanded
    # the segment count.
    total_text_chars = sum(
        len(value) for seg_type, value in segments if seg_type == "text"
    )

    # Default emoji_y anchors the 8-logical-px-tall sprite to the text
    # baseline (`iy = y - 8`). The lowres 8×8 sprite and the hires
    # 32×32-at-scale=4 sprite both occupy 8 logical rows, so a single
    # baseline-anchored formula works for both. For BDF (baseline=12)
    # this evaluates to iy=4, matching the previously-hardcoded
    # visually-validated value. For HiresFont (baseline depends on
    # font + canvas) it computes the correct anchor — the previous
    # `(line_h - 8) // 2` formula mixed real-px line_h with logical
    # iy, producing iy=10 for Inter-Bold @ 24 and clipping the emoji
    # off the bottom of the panel.
    # Callers (e.g. two_row) can always override via explicit emoji_y.
    iy_default = (y + y_offset) - 8

    # Hi-res path is only available on a ScaledCanvas — anywhere else we
    # fall back to the regular 8×8 sprite.
    use_hires = isinstance(canvas, ScaledCanvas)

    # Running global text-char index for per-char providers — incremented
    # only by text segments, not emoji.
    char_index = 0

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
            seg_x = int(cursor_pos + total)
            if per_char:
                # Per-char rendering with the global char index so the
                # rainbow / gradient sweeps continuously across emoji
                # boundaries. The shared helper handles the HiresFont
                # real-pixel cursor tracking that avoids per-char
                # ceil-divide drift.
                total += draw_text_per_char(
                    canvas,
                    font,
                    seg_x,
                    y + y_offset,
                    value,
                    lambda idx, tot: color.color_for(frame, idx, tot),
                    char_offset=char_index,
                    total_chars=total_text_chars,
                )
                char_index += len(value)
            else:
                # Whole-string provider OR raw Color: materialize once
                # per segment, single draw_text call.
                materialized = (
                    color.color_for(frame, char_index, total_text_chars)
                    if is_provider
                    else color
                )
                total += draw_text(
                    canvas,
                    font,
                    seg_x,
                    y + y_offset,
                    materialized,
                    value,
                )
                char_index += len(value)

    return total


def _draw_hires_emoji(
    canvas: ScaledCanvas,
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
