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


# ---------------------------------------------------------------------------
# Pikachu running sprite (chases the pokeball)
# Facing right, forward-leaning run pose. 2 leg frames.
# Body ~12px wide, tail adds ~6px behind = ~18px total, 14px tall
# ---------------------------------------------------------------------------

# Pikachu palette
_YL = (255, 216, 0)  # yellow (body)
_YD = (200, 168, 0)  # dark yellow (shading)
_BR = (139, 90, 0)  # brown (stripes/ear tips)
_BK = (0, 0, 0)  # black (outline/eyes)
_RC = (220, 50, 50)  # red (cheeks)
_WT = (255, 255, 255)  # white (eye highlight)

PIKACHU_WIDTH: int = 18
PIKACHU_HEIGHT: int = 14
PIKACHU_Y_OFFSET: int = 1  # centers 14px sprite in 16px display
PIKACHU_GAP: int = 6  # gap between pokeball and pikachu
PIKACHU_FRAMES_PER_STEP: int = 6  # pixels of travel per leg swap


def _build_pikachu_frame_a() -> PixelData:
    """Pikachu running frame A — left leg forward, right leg back."""
    p: PixelData = []

    # Tail (lightning bolt, extends left from body) — cols 0-5
    # Tail base at y=2-3, zigzags up to y=0
    for dx, dy, r, g, b in [
        (0, 0, *_YL), (1, 0, *_YL), (2, 0, *_YL),
        (2, 1, *_YL), (3, 1, *_YL),
        (3, 2, *_YL), (4, 2, *_YL),
        (4, 3, *_YL), (5, 3, *_YL),
        (5, 4, *_YL), (6, 4, *_YL),
        # Outline
        (0, 1, *_BK), (1, 1, *_BK), (2, 2, *_BK),
        (3, 0, *_BK), (3, 3, *_BK), (4, 1, *_BK),
        (4, 4, *_BK), (5, 2, *_BK), (5, 5, *_BK),
        (6, 3, *_BK), (6, 5, *_BK),
    ]:
        p.append((dx, dy, r, g, b))

    # Ears — cols 8-9 (left ear) and 13-14 (right ear)
    for dx, dy, r, g, b in [
        # Left ear
        (8, 0, *_BK), (9, 0, *_BR), (9, 1, *_BK), (8, 1, *_YL),
        (8, 2, *_YL), (9, 2, *_YL),
        # Right ear
        (14, 0, *_BR), (15, 0, *_BK), (14, 1, *_YL), (15, 1, *_BK),
        (14, 2, *_YL), (15, 2, *_YL),
    ]:
        p.append((dx, dy, r, g, b))

    # Head — rows 3-6, cols 7-16
    for dx, dy, r, g, b in [
        # Row 3 (top of head)
        (9, 3, *_YL), (10, 3, *_YL), (11, 3, *_YL),
        (12, 3, *_YL), (13, 3, *_YL), (14, 3, *_YL),
        # Row 4
        (8, 4, *_YL), (9, 4, *_YL), (10, 4, *_YL), (11, 4, *_YL),
        (12, 4, *_YL), (13, 4, *_YL), (14, 4, *_YL), (15, 4, *_YL),
        # Row 5 (eyes)
        (8, 5, *_YL), (9, 5, *_YL),
        (10, 5, *_BK), (11, 5, *_WT),  # left eye
        (12, 5, *_YL),
        (13, 5, *_BK), (14, 5, *_WT),  # right eye
        (15, 5, *_YL), (16, 5, *_YL),
        # Row 6 (cheeks/mouth)
        (8, 6, *_YL), (9, 6, *_RC),  # left cheek
        (10, 6, *_YL), (11, 6, *_YL), (12, 6, *_YL),
        (13, 6, *_YL), (14, 6, *_RC),  # right cheek
        (15, 6, *_YL), (16, 6, *_YL),
        (17, 6, *_YL),  # nose area
    ]:
        p.append((dx, dy, r, g, b))

    # Body — rows 7-10, cols 7-17
    for dx, dy, r, g, b in [
        # Row 7
        (7, 7, *_YL), (8, 7, *_YL), (9, 7, *_YL), (10, 7, *_YL),
        (11, 7, *_YL), (12, 7, *_YL), (13, 7, *_YL), (14, 7, *_YL),
        (15, 7, *_YL), (16, 7, *_YL), (17, 7, *_YL),
        # Row 8 (brown stripe)
        (7, 8, *_YL), (8, 8, *_YD), (9, 8, *_BR), (10, 8, *_BR),
        (11, 8, *_YL), (12, 8, *_YL), (13, 8, *_YL), (14, 8, *_YL),
        (15, 8, *_YL), (16, 8, *_YL), (17, 8, *_YD),
        # Row 9
        (7, 9, *_YL), (8, 9, *_YL), (9, 9, *_YD), (10, 9, *_YL),
        (11, 9, *_YL), (12, 9, *_YL), (13, 9, *_YL), (14, 9, *_YL),
        (15, 9, *_YL), (16, 9, *_YD),
        # Row 10 (belly)
        (8, 10, *_YL), (9, 10, *_YL), (10, 10, *_YL), (11, 10, *_YL),
        (12, 10, *_YL), (13, 10, *_YL), (14, 10, *_YL), (15, 10, *_YL),
    ]:
        p.append((dx, dy, r, g, b))

    # Legs frame A — left forward, right back
    for dx, dy, r, g, b in [
        # Left leg (forward) — reaching ahead
        (14, 11, *_YL), (15, 11, *_YL), (16, 11, *_YL),
        (16, 12, *_YL), (17, 12, *_YL),
        (17, 13, *_BK),  # foot
        # Right leg (back) — pushing off behind
        (8, 11, *_YL), (9, 11, *_YL),
        (7, 12, *_YL), (8, 12, *_YL),
        (7, 13, *_BK),  # foot
    ]:
        p.append((dx, dy, r, g, b))

    return p


def _build_pikachu_frame_b() -> PixelData:
    """Pikachu running frame B — right leg forward, left leg back."""
    p: PixelData = []

    # Tail — same as frame A
    for dx, dy, r, g, b in [
        (0, 0, *_YL), (1, 0, *_YL), (2, 0, *_YL),
        (2, 1, *_YL), (3, 1, *_YL),
        (3, 2, *_YL), (4, 2, *_YL),
        (4, 3, *_YL), (5, 3, *_YL),
        (5, 4, *_YL), (6, 4, *_YL),
        (0, 1, *_BK), (1, 1, *_BK), (2, 2, *_BK),
        (3, 0, *_BK), (3, 3, *_BK), (4, 1, *_BK),
        (4, 4, *_BK), (5, 2, *_BK), (5, 5, *_BK),
        (6, 3, *_BK), (6, 5, *_BK),
    ]:
        p.append((dx, dy, r, g, b))

    # Ears — same as frame A
    for dx, dy, r, g, b in [
        (8, 0, *_BK), (9, 0, *_BR), (9, 1, *_BK), (8, 1, *_YL),
        (8, 2, *_YL), (9, 2, *_YL),
        (14, 0, *_BR), (15, 0, *_BK), (14, 1, *_YL), (15, 1, *_BK),
        (14, 2, *_YL), (15, 2, *_YL),
    ]:
        p.append((dx, dy, r, g, b))

    # Head — same as frame A
    for dx, dy, r, g, b in [
        (9, 3, *_YL), (10, 3, *_YL), (11, 3, *_YL),
        (12, 3, *_YL), (13, 3, *_YL), (14, 3, *_YL),
        (8, 4, *_YL), (9, 4, *_YL), (10, 4, *_YL), (11, 4, *_YL),
        (12, 4, *_YL), (13, 4, *_YL), (14, 4, *_YL), (15, 4, *_YL),
        (8, 5, *_YL), (9, 5, *_YL),
        (10, 5, *_BK), (11, 5, *_WT),
        (12, 5, *_YL),
        (13, 5, *_BK), (14, 5, *_WT),
        (15, 5, *_YL), (16, 5, *_YL),
        (8, 6, *_YL), (9, 6, *_RC),
        (10, 6, *_YL), (11, 6, *_YL), (12, 6, *_YL),
        (13, 6, *_YL), (14, 6, *_RC),
        (15, 6, *_YL), (16, 6, *_YL),
        (17, 6, *_YL),
    ]:
        p.append((dx, dy, r, g, b))

    # Body — same as frame A
    for dx, dy, r, g, b in [
        (7, 7, *_YL), (8, 7, *_YL), (9, 7, *_YL), (10, 7, *_YL),
        (11, 7, *_YL), (12, 7, *_YL), (13, 7, *_YL), (14, 7, *_YL),
        (15, 7, *_YL), (16, 7, *_YL), (17, 7, *_YL),
        (7, 8, *_YL), (8, 8, *_YD), (9, 8, *_BR), (10, 8, *_BR),
        (11, 8, *_YL), (12, 8, *_YL), (13, 8, *_YL), (14, 8, *_YL),
        (15, 8, *_YL), (16, 8, *_YL), (17, 8, *_YD),
        (7, 9, *_YL), (8, 9, *_YL), (9, 9, *_YD), (10, 9, *_YL),
        (11, 9, *_YL), (12, 9, *_YL), (13, 9, *_YL), (14, 9, *_YL),
        (15, 9, *_YL), (16, 9, *_YD),
        (8, 10, *_YL), (9, 10, *_YL), (10, 10, *_YL), (11, 10, *_YL),
        (12, 10, *_YL), (13, 10, *_YL), (14, 10, *_YL), (15, 10, *_YL),
    ]:
        p.append((dx, dy, r, g, b))

    # Legs frame B — right forward, left back (swapped from A)
    for dx, dy, r, g, b in [
        # Right leg (forward) — reaching ahead
        (14, 11, *_YL), (15, 11, *_YL), (16, 11, *_YL),
        (15, 12, *_YL), (16, 12, *_YL),
        (16, 13, *_BK),  # foot
        # Left leg (back) — pushing off behind
        (9, 11, *_YL), (10, 11, *_YL),
        (8, 12, *_YL), (9, 12, *_YL),
        (8, 13, *_BK),  # foot
    ]:
        p.append((dx, dy, r, g, b))

    return p


PIKACHU_FRAME_A: PixelData = _build_pikachu_frame_a()
PIKACHU_FRAME_B: PixelData = _build_pikachu_frame_b()
PIKACHU_FRAMES: list[PixelData] = [PIKACHU_FRAME_A, PIKACHU_FRAME_B]


POKEBALL_FRAME_0: PixelData = _build_frame_0()
POKEBALL_FRAME_1: PixelData = _build_frame_1()
POKEBALL_FRAME_2: PixelData = _build_frame_2()
POKEBALL_FRAME_3: PixelData = _build_frame_3()

POKEBALL_FRAMES: list[PixelData] = [
    POKEBALL_FRAME_0,
    POKEBALL_FRAME_3,
    POKEBALL_FRAME_2,
    POKEBALL_FRAME_1,
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

    # Draw Pikachu chasing the pokeball
    pika_x = ball_x - PIKACHU_WIDTH - PIKACHU_GAP
    pika_frame_idx = (max(0, ball_x) // PIKACHU_FRAMES_PER_STEP) % len(
        PIKACHU_FRAMES
    )
    pika_sprite = PIKACHU_FRAMES[pika_frame_idx]
    for dx, dy, r, g, b in pika_sprite:
        x = pika_x + dx
        y = PIKACHU_Y_OFFSET + dy
        if 0 <= x < width and 0 <= y < height:
            canvas.SetPixel(x, y, r, g, b)
