# ruff: noqa: E501
"""5x5 pixel art icons for MLB widget on LED matrix display.

Each icon is a list of (x, y, r, g, b) tuples relative to the
top-left corner. Only non-black pixels are stored.
"""

ICON_WIDTH = 5
ICON_HEIGHT = 5
ICON_PADDING = 1

# Pink/green flower for Spring Training
FLOWER = [
    # Pink petals
    (2, 0, 255, 130, 170),
    (1, 1, 255, 130, 170),
    (3, 1, 255, 130, 170),
    (0, 2, 255, 130, 170),
    (2, 2, 255, 220, 50),   # yellow center
    (4, 2, 255, 130, 170),
    (1, 3, 255, 130, 170),
    (3, 3, 255, 130, 170),
    (2, 4, 0, 180, 0),      # green stem
]

# Gold star for All-Star Game
STAR = [
    (2, 0, 255, 215, 0),
    (1, 1, 255, 215, 0),
    (2, 1, 255, 215, 0),
    (3, 1, 255, 215, 0),
    (0, 2, 255, 215, 0),
    (1, 2, 255, 255, 50),
    (2, 2, 255, 255, 50),
    (3, 2, 255, 255, 50),
    (4, 2, 255, 215, 0),
    (1, 3, 255, 215, 0),
    (3, 3, 255, 215, 0),
    (0, 4, 255, 215, 0),
    (4, 4, 255, 215, 0),
]


def draw_mlb_icon(canvas, icon, x, y_offset=5):
    """Draw a 5x5 MLB icon on the canvas.

    Args:
        canvas: LED canvas with SetPixel
        icon: list of (x, y, r, g, b) tuples
        x: left edge x position
        y_offset: top edge y position (default 5 centers in 16px)

    Returns:
        The x position after the icon (x + ICON_WIDTH + ICON_PADDING).
    """
    w = canvas.width
    h = getattr(canvas, "height", 16)
    for px, py, r, g, b in icon:
        dx = x + px
        dy = y_offset + py
        if 0 <= dx < w and 0 <= dy < h:
            canvas.SetPixel(dx, dy, r, g, b)
    return x + ICON_WIDTH + ICON_PADDING
