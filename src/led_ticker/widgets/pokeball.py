"""Pokeball sprite and rolling animation for LED matrix transitions."""

from __future__ import annotations

from led_ticker._types import Canvas, PixelData

SPRITE_SIZE: int = 14
SPRITE_Y_OFFSET: int = 1  # centers 14px sprite in 16px display
PIXELS_PER_ROTATION: int = 44  # circumference of 14px circle ≈ π×14
NUM_FRAMES: int = 4

# Color palette
_R = (220, 0, 0)  # red (top half)
_W = (255, 255, 255)  # white (bottom half / button)
_K = (0, 0, 0)  # black (center band / pupils)
_O = (40, 40, 40)  # outline (dark gray)
_B = (80, 80, 80)  # button border


def _circle_mask() -> set[tuple[int, int]]:
    """Pre-compute which (dx, dy) are inside a 14px diameter circle."""
    cx, cy = 6.5, 6.5  # center of 14x14 grid
    r = 6.5
    mask: set[tuple[int, int]] = set()
    for dy in range(SPRITE_SIZE):
        for dx in range(SPRITE_SIZE):
            if (dx - cx) ** 2 + (dy - cy) ** 2 <= r * r:
                mask.add((dx, dy))
    return mask


def _outline_mask(interior: set[tuple[int, int]]) -> set[tuple[int, int]]:
    """Find pixels on the edge of the circle (have a neighbor outside)."""
    outline: set[tuple[int, int]] = set()
    for dx, dy in interior:
        for ndx, ndy in [(dx - 1, dy), (dx + 1, dy), (dx, dy - 1), (dx, dy + 1)]:
            if (ndx, ndy) not in interior:
                outline.add((dx, dy))
                break
    return outline


def _build_frame_0() -> PixelData:
    """Frame 0: upright — red top, white bottom, horizontal band."""
    interior = _circle_mask()
    outline = _outline_mask(interior)
    pixels: PixelData = []
    for dx, dy in sorted(interior):
        if (dx, dy) in outline:
            pixels.append((dx, dy, *_O))
        elif dy == 6 or dy == 7:
            # Center band
            if 5 <= dx <= 8 and dy == 6:
                # Button border top
                if dx == 5 or dx == 8:
                    pixels.append((dx, dy, *_B))
                else:
                    pixels.append((dx, dy, *_W))
            elif 5 <= dx <= 8 and dy == 7:
                # Button border bottom
                if dx == 5 or dx == 8:
                    pixels.append((dx, dy, *_B))
                else:
                    pixels.append((dx, dy, *_W))
            else:
                pixels.append((dx, dy, *_K))
        elif dy < 6:
            pixels.append((dx, dy, *_R))
        else:
            pixels.append((dx, dy, *_W))
    return pixels


def _build_frame_1() -> PixelData:
    """Frame 1: 90° — red left, white right, vertical band."""
    interior = _circle_mask()
    outline = _outline_mask(interior)
    pixels: PixelData = []
    for dx, dy in sorted(interior):
        if (dx, dy) in outline:
            pixels.append((dx, dy, *_O))
        elif dx == 6 or dx == 7:
            # Vertical center band
            if 5 <= dy <= 8 and dx == 6 or 5 <= dy <= 8 and dx == 7:
                if dy == 5 or dy == 8:
                    pixels.append((dx, dy, *_B))
                else:
                    pixels.append((dx, dy, *_W))
            else:
                pixels.append((dx, dy, *_K))
        elif dx < 6:
            pixels.append((dx, dy, *_R))
        else:
            pixels.append((dx, dy, *_W))
    return pixels


def _build_frame_2() -> PixelData:
    """Frame 2: 180° — white top, red bottom, horizontal band."""
    interior = _circle_mask()
    outline = _outline_mask(interior)
    pixels: PixelData = []
    for dx, dy in sorted(interior):
        if (dx, dy) in outline:
            pixels.append((dx, dy, *_O))
        elif dy == 6 or dy == 7:
            # Center band
            if 5 <= dx <= 8 and dy == 6 or 5 <= dx <= 8 and dy == 7:
                if dx == 5 or dx == 8:
                    pixels.append((dx, dy, *_B))
                else:
                    pixels.append((dx, dy, *_W))
            else:
                pixels.append((dx, dy, *_K))
        elif dy < 6:
            pixels.append((dx, dy, *_W))
        else:
            pixels.append((dx, dy, *_R))
    return pixels


def _build_frame_3() -> PixelData:
    """Frame 3: 270° — white left, red right, vertical band."""
    interior = _circle_mask()
    outline = _outline_mask(interior)
    pixels: PixelData = []
    for dx, dy in sorted(interior):
        if (dx, dy) in outline:
            pixels.append((dx, dy, *_O))
        elif dx == 6 or dx == 7:
            # Vertical center band
            if 5 <= dy <= 8 and dx == 6 or 5 <= dy <= 8 and dx == 7:
                if dy == 5 or dy == 8:
                    pixels.append((dx, dy, *_B))
                else:
                    pixels.append((dx, dy, *_W))
            else:
                pixels.append((dx, dy, *_K))
        elif dx < 6:
            pixels.append((dx, dy, *_W))
        else:
            pixels.append((dx, dy, *_R))
    return pixels


POKEBALL_FRAME_0: PixelData = _build_frame_0()
POKEBALL_FRAME_1: PixelData = _build_frame_1()
POKEBALL_FRAME_2: PixelData = _build_frame_2()
POKEBALL_FRAME_3: PixelData = _build_frame_3()

POKEBALL_FRAMES: list[PixelData] = [
    POKEBALL_FRAME_0,
    POKEBALL_FRAME_1,
    POKEBALL_FRAME_2,
    POKEBALL_FRAME_3,
]


def draw_pokeball_frame(
    canvas: Canvas,
    progress: float,
    width: int = 160,
    height: int = 16,
) -> None:
    """Draw one frame of the pokeball rolling transition (left-to-right).

    The pokeball rolls from off-screen left to off-screen right.
    Everything to its left is blacked out (erased).
    """
    total_travel = width + SPRITE_SIZE
    ball_x = int(-SPRITE_SIZE + progress * total_travel)

    # Select rotation frame based on distance traveled
    pixels_per_frame = PIXELS_PER_ROTATION // NUM_FRAMES  # 11px per frame
    frame_idx = (max(0, ball_x) // pixels_per_frame) % NUM_FRAMES
    sprite = POKEBALL_FRAMES[frame_idx]

    # Black out everything to the left of the ball
    blackout_end = min(width, max(0, ball_x))
    for y in range(height):
        for x in range(blackout_end):
            canvas.SetPixel(x, y, 0, 0, 0)

    # Draw the pokeball sprite (clipped to canvas bounds)
    for dx, dy, r, g, b in sprite:
        x = ball_x + dx
        y = SPRITE_Y_OFFSET + dy
        if 0 <= x < width and 0 <= y < height:
            canvas.SetPixel(x, y, r, g, b)
