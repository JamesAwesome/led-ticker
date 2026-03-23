# ruff: noqa: E501
"""Pixel art emoji for inline rendering in text.

Use `:slug:` in any TickerMessage text to render a pixel art icon.
Example: ":baseball: MLB Scores" renders a baseball icon then text.

Each emoji is a list of (x, y, r, g, b) tuples relative to origin.
"""

from __future__ import annotations

from typing import Any

from led_ticker._types import Canvas, Color, Font, PixelData

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
    # Row 0: filling peeks above shell (left side)
    (2, 0, *_TK), (3, 0, *_TK), (4, 0, *_TK), (5, 0, *_TK),
    # Row 1: filling — lettuce, tomato, meat, green
    (1, 1, *_TK), (2, 1, *_TR), (3, 1, *_TG),
    (4, 1, *_TM), (5, 1, *_TG), (6, 1, *_TK),
    # Row 2: shell curves up from right toward filling
    (0, 2, *_TK), (1, 2, *_TG), (2, 2, *_TM), (3, 2, *_TR),
    (4, 2, *_TG), (5, 2, *_TK), (6, 2, *_TS),
    (7, 2, *_TS), (8, 2, *_TK),
    # Row 3: shell wraps around — wide orange, curves up right side
    (0, 3, *_TK), (1, 3, *_TS), (2, 3, *_TS), (3, 3, *_TS),
    (4, 3, *_TS), (5, 3, *_TS), (6, 3, *_TS), (7, 3, *_TS),
    (8, 3, *_TS), (9, 3, *_TL), (10, 3, *_TK),
    # Row 4: widest shell
    (0, 4, *_TK), (1, 4, *_TS), (2, 4, *_TL), (3, 4, *_TS),
    (4, 4, *_TS), (5, 4, *_TS), (6, 4, *_TL), (7, 4, *_TS),
    (8, 4, *_TS), (9, 4, *_TS), (10, 4, *_TK),
    # Row 5: flat bottom — same width as row 4
    (0, 5, *_TK), (1, 5, *_TS), (2, 5, *_TS), (3, 5, *_TS),
    (4, 5, *_TS), (5, 5, *_TS), (6, 5, *_TS), (7, 5, *_TS),
    (8, 5, *_TS), (9, 5, *_TS), (10, 5, *_TK),
    # Row 6: flat bottom edge
    (0, 6, *_TK), (1, 6, *_TK), (2, 6, *_TK), (3, 6, *_TK),
    (4, 6, *_TK), (5, 6, *_TK), (6, 6, *_TK), (7, 6, *_TK),
    (8, 6, *_TK), (9, 6, *_TK), (10, 6, *_TK),
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
) -> int:
    """Draw text with inline emoji. Returns pixels advanced."""
    graphics_mod: Any = None
    segments = _parse_segments(text)
    total: int = 0

    for seg_type, value in segments:
        if seg_type == "emoji":
            icon = _get_registry()[value]
            iw = _emoji_width(icon)
            # Center icon vertically on 16px display
            ix = int(cursor_pos + total)
            iy = 4 + y_offset
            w = canvas.width
            h = getattr(canvas, "height", 16)
            for px, py, r, g, b in icon:
                dx = ix + px
                dy = iy + py
                if 0 <= dx < w and 0 <= dy < h:
                    canvas.SetPixel(dx, dy, r, g, b)
            total += iw + EMOJI_PADDING
        else:
            if graphics_mod is None:
                from led_ticker._compat import require_graphics

                graphics_mod = require_graphics()
            total += graphics_mod.DrawText(
                canvas,
                font,
                int(cursor_pos + total),
                y + y_offset,
                color,
                value,
            )

    return total
