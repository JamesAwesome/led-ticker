# ruff: noqa: E501
"""Pixel art emoji for inline rendering in text.

Use `:slug:` in any TickerMessage text to render a pixel art icon.
Example: ":baseball: MLB Scores" renders a baseball icon then text.

Each emoji is a list of (x, y, r, g, b) tuples relative to origin.
"""

from __future__ import annotations

from led_ticker._types import Canvas, Color, Font, PixelData
from led_ticker.text_render import draw_text

EMOJI_DEFAULT_WIDTH: int = 8
EMOJI_PADDING: int = 2  # px after icon before text resumes


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
    # Row 0: top arc, leans LEFT (cols 1-4 — original was 2-5).
    (1, 0, *_MN),
    (2, 0, *_MN),
    (3, 0, *_MN),
    (4, 0, *_MN),
    # Row 1: arc widens into the body (cols 0-4).
    (0, 1, *_MN),
    (1, 1, *_MN),
    (2, 1, *_MN),
    (3, 1, *_MN),
    (4, 1, *_MN),
    # Row 2: full-body bulge (cols 0-3).
    (0, 2, *_MN),
    (1, 2, *_MN),
    (2, 2, *_MN),
    (3, 2, *_MN),
    # Row 3: body narrows (cols 0-2).
    (0, 3, *_MN),
    (1, 3, *_MN),
    (2, 3, *_MN),
    # Row 4: body narrows (cols 0-2). The two 3-wide rows are the
    # crescent's "waist" — solid, not pinched. Keeps the moon reading
    # as a body rather than a thin C / chevron.
    (0, 4, *_MN),
    (1, 4, *_MN),
    (2, 4, *_MN),
    # Row 5: widening back (cols 0-3).
    (0, 5, *_MN),
    (1, 5, *_MN),
    (2, 5, *_MN),
    (3, 5, *_MN),
    # Row 6: lower arc (cols 1-5 — bottom shifts RIGHT relative to the
    # top, completing the LEFT-leaning tilt).
    (1, 6, *_MN),
    (2, 6, *_MN),
    (3, 6, *_MN),
    (4, 6, *_MN),
    (5, 6, *_MN),
    # Row 7: bottom arc (cols 2-5).
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
) -> int:
    """Draw text with inline emoji. Returns pixels advanced.

    `emoji_y` overrides the icon's top-row position. Default is
    `4 + y_offset` — vertically centered on the 16-tall logical canvas
    plus any caller-supplied offset. Multi-row widgets (e.g. `two_row`)
    pass an explicit `emoji_y` per row so the icon aligns with the row's
    text baseline instead of the canvas center.
    """
    segments = _parse_segments(text)
    total: int = 0

    iy_default = 4 + y_offset

    for seg_type, value in segments:
        if seg_type == "emoji":
            icon = _get_registry()[value]
            iw = _emoji_width(icon)
            ix = int(cursor_pos + total)
            iy = iy_default if emoji_y is None else emoji_y
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
