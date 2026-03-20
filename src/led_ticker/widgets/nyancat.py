# ruff: noqa: E501
"""Nyan Cat sprite and rainbow trail for LED matrix transitions.

The cat is 12px wide x 10px tall. The rainbow trail is 6 stripes,
each 2px tall (fills the 12px behind the cat, plus extends left).
The full display is 16px tall, so the cat is centered at y=3.
"""

# RGB colors for the rainbow trail (top to bottom, 2px each = 12px)
RAINBOW = [
    (255, 0, 0),  # red
    (255, 154, 0),  # orange
    (255, 255, 0),  # yellow
    (0, 255, 0),  # green
    (0, 100, 255),  # blue
    (100, 0, 255),  # purple
]

RAINBOW_TOP_Y = 2  # y offset where rainbow starts (centered in 16px)
RAINBOW_STRIPE_HEIGHT = 2

# Nyan Cat sprite: (dx, dy, r, g, b) relative to sprite origin
# 12px wide x 10px tall
# The pop-tart body is pink/tan, cat is dark gray, face details

_G = (100, 100, 100)  # gray (cat body)
_D = (60, 60, 60)  # dark gray (outlines)
_P = (255, 153, 204)  # pink (pop-tart frosting)
_T = (210, 150, 80)  # tan (pop-tart crust)
_W = (255, 255, 255)  # white (eyes/cheeks)
_B = (0, 0, 0)  # black (pupils)
_R = (255, 100, 100)  # rosy cheeks
_S = (255, 200, 200)  # sprinkles on frosting

NYAN_CAT = []

# Row 0 (ears)
_row0 = [
    (3, 0, *_D),
    (4, 0, *_G),
    (8, 0, *_G),
    (9, 0, *_D),
]
# Row 1 (ears + top of head)
_row1 = [
    (3, 1, *_G),
    (4, 1, *_G),
    (5, 1, *_D),
    (6, 1, *_D),
    (7, 1, *_D),
    (8, 1, *_G),
    (9, 1, *_G),
]
# Row 2 (pop-tart top + head)
_row2 = [
    (1, 2, *_T),
    (2, 2, *_T),
    (3, 2, *_T),
    (4, 2, *_T),
    (5, 2, *_G),
    (6, 2, *_G),
    (7, 2, *_G),
    (8, 2, *_T),
    (9, 2, *_T),
]
# Row 3 (pop-tart + face)
_row3 = [
    (0, 3, *_T),
    (1, 3, *_P),
    (2, 3, *_S),
    (3, 3, *_P),
    (4, 3, *_P),
    (5, 3, *_W),
    (6, 3, *_B),
    (7, 3, *_W),
    (8, 3, *_B),
    (9, 3, *_P),
    (10, 3, *_T),
]
# Row 4 (pop-tart + face)
_row4 = [
    (0, 4, *_T),
    (1, 4, *_P),
    (2, 4, *_P),
    (3, 4, *_S),
    (4, 4, *_P),
    (5, 4, *_G),
    (6, 4, *_G),
    (7, 4, *_G),
    (8, 4, *_G),
    (9, 4, *_P),
    (10, 4, *_T),
]
# Row 5 (pop-tart + mouth)
_row5 = [
    (0, 5, *_T),
    (1, 5, *_P),
    (2, 5, *_P),
    (3, 5, *_P),
    (4, 5, *_S),
    (5, 5, *_R),
    (6, 5, *_G),
    (7, 5, *_D),
    (8, 5, *_R),
    (9, 5, *_P),
    (10, 5, *_T),
]
# Row 6 (pop-tart bottom)
_row6 = [
    (0, 6, *_T),
    (1, 6, *_P),
    (2, 6, *_S),
    (3, 6, *_P),
    (4, 6, *_P),
    (5, 6, *_P),
    (6, 6, *_P),
    (7, 6, *_P),
    (8, 6, *_P),
    (9, 6, *_P),
    (10, 6, *_T),
]
# Row 7 (crust bottom + tail start)
_row7 = [
    (1, 7, *_T),
    (2, 7, *_T),
    (3, 7, *_T),
    (4, 7, *_T),
    (5, 7, *_T),
    (6, 7, *_T),
    (7, 7, *_T),
    (8, 7, *_T),
    (9, 7, *_T),
]
# Row 8 (legs)
_row8 = [
    (2, 8, *_G),
    (3, 8, *_G),
    (5, 8, *_G),
    (6, 8, *_G),
    (8, 8, *_G),
    (9, 8, *_G),
]
# Row 9 (feet)
_row9 = [
    (2, 9, *_D),
    (3, 9, *_D),
    (5, 9, *_D),
    (6, 9, *_D),
    (8, 9, *_D),
    (9, 9, *_D),
]

NYAN_CAT = _row0 + _row1 + _row2 + _row3 + _row4 + _row5 + _row6 + _row7 + _row8 + _row9

SPRITE_WIDTH = 12
SPRITE_HEIGHT = 10
SPRITE_Y_OFFSET = 3  # centers 10px sprite in 16px display


def draw_nyan_frame(canvas, progress, width=160, height=16):
    """Draw one frame of the Nyan Cat transition.

    The cat flies from left to right. Behind it, a rainbow trail.
    Old content should be drawn first, then this function draws
    the rainbow and cat on top.

    Args:
        canvas: LED canvas with SetPixel
        progress: 0.0 (cat off-screen left) to 1.0 (cat off-screen right)
        width: canvas width
        height: canvas height
    """
    # Cat position: travels from -SPRITE_WIDTH to width
    total_travel = width + SPRITE_WIDTH
    cat_x = int(-SPRITE_WIDTH + progress * total_travel)

    # Draw rainbow trail behind the cat
    trail_end = cat_x
    trail_start = max(0, trail_end - width)  # rainbow fills behind cat

    for stripe_idx, (r, g, b) in enumerate(RAINBOW):
        y_start = RAINBOW_TOP_Y + stripe_idx * RAINBOW_STRIPE_HEIGHT
        for dy in range(RAINBOW_STRIPE_HEIGHT):
            y = y_start + dy
            if 0 <= y < height:
                for x in range(max(0, trail_start), max(0, trail_end)):
                    if 0 <= x < width:
                        canvas.SetPixel(x, y, r, g, b)

    # Draw the cat sprite
    for dx, dy, r, g, b in NYAN_CAT:
        x = cat_x + dx
        y = SPRITE_Y_OFFSET + dy
        if 0 <= x < width and 0 <= y < height:
            canvas.SetPixel(x, y, r, g, b)
