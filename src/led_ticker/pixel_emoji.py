# ruff: noqa: E501
"""Pixel art emoji for inline rendering in text.

Use `:slug:` in any TickerMessage text to render a pixel art icon.
Example: ":baseball: MLB Scores" renders a baseball icon then text.

Each emoji is a list of (x, y, r, g, b) tuples relative to origin.
"""

EMOJI_WIDTH = 8
EMOJI_HEIGHT = 8
EMOJI_PADDING = 2  # px after icon before text resumes

# ⚾ Baseball — white ball with red stitching
BASEBALL = [
    # White ball outline
    (2, 0, 255, 255, 255), (3, 0, 255, 255, 255), (4, 0, 255, 255, 255), (5, 0, 255, 255, 255),
    (1, 1, 255, 255, 255), (6, 1, 255, 255, 255),
    (0, 2, 255, 255, 255), (7, 2, 255, 255, 255),
    (0, 3, 255, 255, 255), (7, 3, 255, 255, 255),
    (0, 4, 255, 255, 255), (7, 4, 255, 255, 255),
    (0, 5, 255, 255, 255), (7, 5, 255, 255, 255),
    (1, 6, 255, 255, 255), (6, 6, 255, 255, 255),
    (2, 7, 255, 255, 255), (3, 7, 255, 255, 255), (4, 7, 255, 255, 255), (5, 7, 255, 255, 255),
    # White fill
    (2, 1, 240, 240, 240), (3, 1, 240, 240, 240), (4, 1, 240, 240, 240), (5, 1, 240, 240, 240),
    (1, 2, 240, 240, 240), (1, 3, 240, 240, 240),
    (6, 4, 240, 240, 240), (6, 5, 240, 240, 240),
    (2, 6, 240, 240, 240), (3, 6, 240, 240, 240), (4, 6, 240, 240, 240), (5, 6, 240, 240, 240),
    # Red stitching — left curve
    (2, 2, 255, 30, 30), (3, 3, 255, 30, 30), (3, 4, 255, 30, 30), (2, 5, 255, 30, 30),
    # Red stitching — right curve
    (5, 2, 255, 30, 30), (4, 3, 255, 30, 30), (4, 4, 255, 30, 30), (5, 5, 255, 30, 30),
    # Center fill
    (3, 2, 240, 240, 240), (4, 2, 240, 240, 240),
    (2, 3, 240, 240, 240), (5, 3, 240, 240, 240),
    (2, 4, 240, 240, 240), (5, 4, 240, 240, 240),
    (3, 5, 240, 240, 240), (4, 5, 240, 240, 240),
    (6, 2, 240, 240, 240), (6, 3, 240, 240, 240),
    (1, 4, 240, 240, 240), (1, 5, 240, 240, 240),
]

# Registry: slug → pixel data
EMOJI_REGISTRY = {
    "baseball": BASEBALL,
}


def _parse_segments(text):
    """Split text into segments of (type, value).

    Returns list of ("text", "hello ") or ("emoji", "baseball").
    """
    import re

    parts = re.split(r"(:[a-z_]+:)", text)
    segments = []
    for part in parts:
        if not part:
            continue
        if part.startswith(":") and part.endswith(":"):
            slug = part[1:-1]
            if slug in EMOJI_REGISTRY:
                segments.append(("emoji", slug))
            else:
                segments.append(("text", part))
        else:
            segments.append(("text", part))
    return segments


def measure_width(font, text):
    """Measure total width of text with emoji slugs expanded."""
    from led_ticker.drawing import get_text_width

    segments = _parse_segments(text)
    width = 0
    for seg_type, value in segments:
        if seg_type == "emoji":
            width += EMOJI_WIDTH + EMOJI_PADDING
        else:
            width += get_text_width(font, value, padding=0)
    return width


def draw_with_emoji(canvas, font, cursor_pos, y, color, text, y_offset=0):
    """Draw text with inline emoji. Returns pixels advanced."""
    graphics_mod = None
    segments = _parse_segments(text)
    total = 0

    for seg_type, value in segments:
        if seg_type == "emoji":
            icon = EMOJI_REGISTRY[value]
            # Center 8px icon vertically: y_offset=4 on 16px display
            ix = int(cursor_pos + total)
            iy = 4 + y_offset
            w = canvas.width
            h = getattr(canvas, "height", 16)
            for px, py, r, g, b in icon:
                dx = ix + px
                dy = iy + py
                if 0 <= dx < w and 0 <= dy < h:
                    canvas.SetPixel(dx, dy, r, g, b)
            total += EMOJI_WIDTH + EMOJI_PADDING
        else:
            if graphics_mod is None:
                from led_ticker._compat import require_graphics

                graphics_mod = require_graphics()
            total += graphics_mod.DrawText(
                canvas, font, int(cursor_pos + total),
                y + y_offset, color, value,
            )

    return total
