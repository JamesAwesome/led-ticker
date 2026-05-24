"""Pokeball sprite and rolling animation for LED matrix transitions."""

from __future__ import annotations

from typing import Any, ClassVar

from led_ticker._types import Canvas, PixelData
from led_ticker.scaled_canvas import ScaledCanvas
from led_ticker.transitions import Transition, register_transition
from led_ticker.transitions._hires_registry import HIRES_REGISTRY

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
# 4-frame run cycle matching the classic pixel-art animation:
#   Frame 1: Crouched/compact — legs tucked, tail steep up-left
#   Frame 2: Pushing off — body elongating, tail zigzags right
#   Frame 3: Full stretch — longest, legs extended, tail back
#   Frame 4: Landing — body low, legs gathering, tail down
# ---------------------------------------------------------------------------

# Pikachu palette
_YL = (255, 216, 0)  # yellow (body)
_YD = (200, 168, 0)  # dark yellow (shading)
_BR = (139, 90, 0)  # brown (stripes/ear tips)
_BK = (0, 0, 0)  # black (outline/eyes)
_RC = (220, 50, 50)  # red (cheeks)
_WT = (255, 255, 255)  # white (eye highlight)

PIKACHU_WIDTH: int = 21
PIKACHU_HEIGHT: int = 14
PIKACHU_Y_OFFSET: int = 1  # centers in 16px display
PIKACHU_GAP: int = 6  # gap between pokeball and pikachu
PIKACHU_FRAMES_PER_STEP: int = 4  # pixels per frame swap (16px = full cycle)


def _build_pikachu_frame_1() -> PixelData:
    """Frame 1: Crouched — compact bean body, legs tucked, tail steep up-left.
    Side profile view. Head and rump are one continuous shape."""
    return [
        # Tail — steep lightning bolt going up-left
        (0, 0, *_YL),
        (1, 0, *_YL),
        (1, 1, *_YL),
        (2, 1, *_YL),
        (2, 2, *_YL),
        (3, 2, *_YL),
        (3, 3, *_YL),
        (4, 3, *_YL),
        (5, 3, *_YL),
        (5, 4, *_YL),
        (6, 4, *_YL),
        # Tail outline
        (0, 1, *_BK),
        (2, 0, *_BK),
        (2, 3, *_BK),
        (3, 1, *_BK),
        (4, 2, *_BK),
        (4, 4, *_BK),
        (5, 5, *_BK),
        (6, 3, *_BK),
        (6, 5, *_BK),
        # Ear (single, profile — brown tip)
        (12, 0, *_BR),
        (13, 0, *_BK),
        (12, 1, *_YL),
        (13, 1, *_BK),
        (12, 2, *_YL),
        (13, 2, *_YL),
        # Unified bean body — head flows into rump, no neck gap
        # Top curve (row 3-4: head/back)
        (8, 3, *_YL),
        (9, 3, *_YL),
        (10, 3, *_YL),
        (11, 3, *_YL),
        (12, 3, *_YL),
        (13, 3, *_YL),
        (14, 3, *_YL),
        (7, 4, *_YL),
        (8, 4, *_YL),
        (9, 4, *_YL),
        (10, 4, *_YL),
        (11, 4, *_YL),
        (12, 4, *_YL),
        (13, 4, *_YL),
        (14, 4, *_YL),
        (15, 4, *_YL),
        # Face row (row 5: eye pushed forward, nose extends)
        (7, 5, *_YL),
        (8, 5, *_YL),
        (9, 5, *_YL),
        (10, 5, *_YL),
        (11, 5, *_YL),
        (12, 5, *_YL),
        (13, 5, *_BK),
        (14, 5, *_WT),
        (15, 5, *_YL),
        # Cheek + widest body row (row 6: cheek forward, nose tip)
        (7, 6, *_YL),
        (8, 6, *_YL),
        (9, 6, *_YL),
        (10, 6, *_YL),
        (11, 6, *_YL),
        (12, 6, *_YL),
        (13, 6, *_RC),
        (14, 6, *_YL),
        (15, 6, *_YL),
        # Mid body (row 7: brown stripes on back)
        (7, 7, *_YL),
        (8, 7, *_BR),
        (9, 7, *_BR),
        (10, 7, *_YL),
        (11, 7, *_YL),
        (12, 7, *_YL),
        (13, 7, *_YL),
        (14, 7, *_YL),
        (15, 7, *_YL),
        # Lower body / belly (row 8)
        (7, 8, *_YD),
        (8, 8, *_YL),
        (9, 8, *_YL),
        (10, 8, *_YL),
        (11, 8, *_YL),
        (12, 8, *_YL),
        (13, 8, *_YL),
        (14, 8, *_YL),
        (15, 8, *_YD),
        # Bottom curve (row 9)
        (8, 9, *_YL),
        (9, 9, *_YL),
        (10, 9, *_YL),
        (11, 9, *_YL),
        (12, 9, *_YL),
        (13, 9, *_YL),
        (14, 9, *_YL),
        # Legs — tucked close together under body
        (9, 10, *_YL),
        (10, 10, *_YL),
        (11, 10, *_YL),
        (12, 10, *_YL),
        (9, 11, *_YL),
        (10, 11, *_YL),
        (11, 11, *_YL),
        (12, 11, *_YL),
        (9, 12, *_BK),
        (10, 12, *_BK),
        (11, 12, *_BK),
        (12, 12, *_BK),  # feet
    ]


def _build_pikachu_frame_2() -> PixelData:
    """Frame 2: Pushing off — body elongating, tail zigzags, legs extending.
    Side profile. Continuous bean shape, slightly longer than frame 1."""
    return [
        # Tail — zigzags up
        (0, 2, *_YL),
        (1, 2, *_YL),
        (1, 1, *_YL),
        (2, 1, *_YL),
        (2, 2, *_YL),
        (3, 2, *_YL),
        (3, 1, *_YL),
        (4, 1, *_YL),
        (4, 2, *_YL),
        (5, 2, *_YL),
        (5, 3, *_YL),
        # Tail outline
        (0, 1, *_BK),
        (0, 3, *_BK),
        (1, 0, *_BK),
        (1, 3, *_BK),
        (2, 0, *_BK),
        (2, 3, *_BK),
        (3, 0, *_BK),
        (3, 3, *_BK),
        (4, 0, *_BK),
        (4, 3, *_BK),
        (5, 1, *_BK),
        (5, 4, *_BK),
        (6, 3, *_BK),
        # Ear (single, swept back)
        (13, 0, *_BR),
        (14, 0, *_BK),
        (13, 1, *_YL),
        (14, 1, *_BK),
        (13, 2, *_YL),
        (14, 2, *_YL),
        # Unified bean body — elongating
        # Top curve (row 2-3: head/back start)
        (9, 2, *_YL),
        (10, 2, *_YL),
        (11, 2, *_YL),
        (12, 2, *_YL),
        (7, 3, *_YL),
        (8, 3, *_YL),
        (9, 3, *_YL),
        (10, 3, *_YL),
        (11, 3, *_YL),
        (12, 3, *_YL),
        (13, 3, *_YL),
        (14, 3, *_YL),
        (15, 3, *_YL),
        (16, 3, *_YL),
        # Face row (row 4: eye pushed forward, nose extends)
        (6, 4, *_YL),
        (7, 4, *_YL),
        (8, 4, *_YL),
        (9, 4, *_YL),
        (10, 4, *_YL),
        (11, 4, *_YL),
        (12, 4, *_YL),
        (13, 4, *_YL),
        (14, 4, *_BK),
        (15, 4, *_WT),
        (16, 4, *_YL),
        (17, 4, *_YL),
        # Cheek + wide body (row 5: cheek forward)
        (6, 5, *_YL),
        (7, 5, *_YL),
        (8, 5, *_YL),
        (9, 5, *_YL),
        (10, 5, *_YL),
        (11, 5, *_YL),
        (12, 5, *_YL),
        (13, 5, *_YL),
        (14, 5, *_RC),
        (15, 5, *_YL),
        (16, 5, *_YL),
        (17, 5, *_YL),
        # Mid body (row 6: stripes)
        (6, 6, *_YL),
        (7, 6, *_BR),
        (8, 6, *_BR),
        (9, 6, *_YL),
        (10, 6, *_YL),
        (11, 6, *_YL),
        (12, 6, *_YL),
        (13, 6, *_YL),
        (14, 6, *_YL),
        (15, 6, *_YL),
        (16, 6, *_YL),
        (17, 6, *_YL),
        # Lower body (row 7) — extends to match face
        (6, 7, *_YD),
        (7, 7, *_YL),
        (8, 7, *_YL),
        (9, 7, *_YL),
        (10, 7, *_YL),
        (11, 7, *_YL),
        (12, 7, *_YL),
        (13, 7, *_YL),
        (14, 7, *_YL),
        (15, 7, *_YL),
        (16, 7, *_YL),
        (17, 7, *_YD),
        # Bottom curve (row 8) — extends to match face
        (7, 8, *_YL),
        (8, 8, *_YL),
        (9, 8, *_YL),
        (10, 8, *_YL),
        (11, 8, *_YL),
        (12, 8, *_YL),
        (13, 8, *_YL),
        (14, 8, *_YL),
        (15, 8, *_YL),
        (16, 8, *_YL),
        # Legs — back pushing slightly, front reaching slightly
        # Front leg (shifted 2px ahead)
        (13, 9, *_YL),
        (14, 9, *_YL),
        (13, 10, *_YL),
        (14, 10, *_YL),
        (13, 11, *_BK),
        (14, 11, *_BK),  # front foot
        # Back leg (under body, not past face)
        (9, 9, *_YL),
        (10, 9, *_YL),
        (9, 10, *_YL),
        (10, 10, *_YL),
        (9, 11, *_BK),
        (10, 11, *_BK),  # back foot
    ]


def _build_pikachu_frame_3() -> PixelData:
    """Frame 3: Full stretch — longest bean body, legs extended, tail back.
    Side profile. Head and rump at same level, long continuous shape."""
    return [
        # Tail — straight back, slightly up
        (0, 2, *_YL),
        (1, 2, *_YL),
        (1, 3, *_YL),
        (2, 3, *_YL),
        (2, 2, *_YL),
        (3, 2, *_YL),
        (3, 3, *_YL),
        (4, 3, *_YL),
        (4, 4, *_YL),
        # Tail outline
        (0, 1, *_BK),
        (0, 3, *_BK),
        (1, 1, *_BK),
        (1, 4, *_BK),
        (2, 1, *_BK),
        (2, 4, *_BK),
        (3, 1, *_BK),
        (3, 4, *_BK),
        (4, 2, *_BK),
        (4, 5, *_BK),
        (5, 4, *_BK),
        # Ear (single, flat back)
        (14, 0, *_BR),
        (15, 0, *_BK),
        (14, 1, *_YL),
        (15, 1, *_BK),
        (14, 2, *_YL),
        (15, 2, *_YL),
        # Unified bean body — longest, level back
        # Top curve (row 2-3)
        (10, 2, *_YL),
        (11, 2, *_YL),
        (12, 2, *_YL),
        (13, 2, *_YL),
        (7, 3, *_YL),
        (8, 3, *_YL),
        (9, 3, *_YL),
        (10, 3, *_YL),
        (11, 3, *_YL),
        (12, 3, *_YL),
        (13, 3, *_YL),
        (14, 3, *_YL),
        (15, 3, *_YL),
        (16, 3, *_YL),
        (17, 3, *_YL),
        # Face row (row 4: eye pushed forward)
        (5, 4, *_YL),
        (6, 4, *_YL),
        (7, 4, *_YL),
        (8, 4, *_YL),
        (9, 4, *_YL),
        (10, 4, *_YL),
        (11, 4, *_YL),
        (12, 4, *_YL),
        (13, 4, *_YL),
        (14, 4, *_YL),
        (15, 4, *_BK),
        (16, 4, *_WT),
        (17, 4, *_YL),
        # Cheek + widest (row 5: cheek forward)
        (5, 5, *_YL),
        (6, 5, *_YL),
        (7, 5, *_YL),
        (8, 5, *_YL),
        (9, 5, *_YL),
        (10, 5, *_YL),
        (11, 5, *_YL),
        (12, 5, *_YL),
        (13, 5, *_YL),
        (14, 5, *_YL),
        (15, 5, *_RC),
        (16, 5, *_YL),
        (17, 5, *_YL),
        # Mid body (row 6: stripes) — long flat
        (5, 6, *_YL),
        (6, 6, *_BR),
        (7, 6, *_BR),
        (8, 6, *_YL),
        (9, 6, *_YL),
        (10, 6, *_YL),
        (11, 6, *_YL),
        (12, 6, *_YL),
        (13, 6, *_YL),
        (14, 6, *_YL),
        (15, 6, *_YL),
        (16, 6, *_YL),
        (17, 6, *_YL),
        (18, 6, *_YL),
        # Lower body (row 7)
        (5, 7, *_YD),
        (6, 7, *_YL),
        (7, 7, *_YL),
        (8, 7, *_YL),
        (9, 7, *_YL),
        (10, 7, *_YL),
        (11, 7, *_YL),
        (12, 7, *_YL),
        (13, 7, *_YL),
        (14, 7, *_YL),
        (15, 7, *_YL),
        (16, 7, *_YL),
        (17, 7, *_YD),
        # Bottom curve (row 8) — extends to match face
        (6, 8, *_YL),
        (7, 8, *_YL),
        (8, 8, *_YL),
        (9, 8, *_YL),
        (10, 8, *_YL),
        (11, 8, *_YL),
        (12, 8, *_YL),
        (13, 8, *_YL),
        (14, 8, *_YL),
        (15, 8, *_YL),
        (16, 8, *_YL),
        (17, 8, *_YL),
        # Legs — widest spread, but still stubby
        # Front leg (shifted ahead)
        (14, 9, *_YL),
        (15, 9, *_YL),
        (14, 10, *_YL),
        (15, 10, *_YL),
        (14, 11, *_BK),
        (15, 11, *_BK),  # front foot
        # Back leg (under body, not past face)
        (8, 9, *_YL),
        (9, 9, *_YL),
        (8, 10, *_YL),
        (9, 10, *_YL),
        (8, 11, *_BK),
        (9, 11, *_BK),  # back foot
    ]


def _build_pikachu_frame_4() -> PixelData:
    """Frame 4: Landing — compressed bean body, legs gathering, tail down.
    Side profile. Body squished low, continuous shape."""
    return [
        # Tail — angled down-left
        (0, 5, *_YL),
        (1, 5, *_YL),
        (1, 4, *_YL),
        (2, 4, *_YL),
        (2, 5, *_YL),
        (3, 5, *_YL),
        (3, 4, *_YL),
        (4, 4, *_YL),
        (4, 5, *_YL),
        (5, 5, *_YL),
        # Tail outline
        (0, 4, *_BK),
        (0, 6, *_BK),
        (1, 3, *_BK),
        (1, 6, *_BK),
        (2, 3, *_BK),
        (2, 6, *_BK),
        (3, 3, *_BK),
        (3, 6, *_BK),
        (4, 3, *_BK),
        (4, 6, *_BK),
        (5, 4, *_BK),
        (5, 6, *_BK),
        # Ear (single)
        (12, 0, *_BR),
        (13, 0, *_BK),
        (12, 1, *_YL),
        (13, 1, *_BK),
        (12, 2, *_YL),
        (13, 2, *_YL),
        # Unified bean body — compressed, wide
        # Top curve (row 3-4: head/back)
        (8, 3, *_YL),
        (9, 3, *_YL),
        (10, 3, *_YL),
        (11, 3, *_YL),
        (12, 3, *_YL),
        (13, 3, *_YL),
        (14, 3, *_YL),
        (7, 4, *_YL),
        (8, 4, *_YL),
        (9, 4, *_YL),
        (10, 4, *_YL),
        (11, 4, *_YL),
        (12, 4, *_YL),
        (13, 4, *_YL),
        (14, 4, *_YL),
        (15, 4, *_YL),
        # Face row (row 5: eye pushed forward, nose extends)
        (6, 5, *_YL),
        (7, 5, *_YL),
        (8, 5, *_YL),
        (9, 5, *_YL),
        (10, 5, *_YL),
        (11, 5, *_YL),
        (12, 5, *_YL),
        (13, 5, *_BK),
        (14, 5, *_WT),
        (15, 5, *_YL),
        (16, 5, *_YL),
        # Cheek + wide body (row 6: cheek forward)
        (6, 6, *_YL),
        (7, 6, *_YL),
        (8, 6, *_YL),
        (9, 6, *_YL),
        (10, 6, *_YL),
        (11, 6, *_YL),
        (12, 6, *_YL),
        (13, 6, *_RC),
        (14, 6, *_YL),
        (15, 6, *_YL),
        (16, 6, *_YL),
        # Mid body (row 7: stripes)
        (6, 7, *_YL),
        (7, 7, *_BR),
        (8, 7, *_BR),
        (9, 7, *_YL),
        (10, 7, *_YL),
        (11, 7, *_YL),
        (12, 7, *_YL),
        (13, 7, *_YL),
        (14, 7, *_YL),
        (15, 7, *_YL),
        (16, 7, *_YL),
        # Lower body (row 8) — extends to match face
        (6, 8, *_YD),
        (7, 8, *_YL),
        (8, 8, *_YL),
        (9, 8, *_YL),
        (10, 8, *_YL),
        (11, 8, *_YL),
        (12, 8, *_YL),
        (13, 8, *_YL),
        (14, 8, *_YL),
        (15, 8, *_YL),
        (16, 8, *_YD),
        # Bottom curve (row 9)
        (7, 9, *_YL),
        (8, 9, *_YL),
        (9, 9, *_YL),
        (10, 9, *_YL),
        (11, 9, *_YL),
        (12, 9, *_YL),
        (13, 9, *_YL),
        (14, 9, *_YL),
        (15, 9, *_YL),
        # Legs — gathering back together under body
        (9, 10, *_YL),
        (10, 10, *_YL),
        (11, 10, *_YL),
        (12, 10, *_YL),
        (10, 11, *_YL),
        (11, 11, *_YL),
        (12, 11, *_YL),
        (13, 11, *_YL),
        (10, 12, *_BK),
        (11, 12, *_BK),
        (12, 12, *_BK),
        (13, 12, *_BK),  # feet
    ]


PIKACHU_FRAME_1: PixelData = _build_pikachu_frame_1()
PIKACHU_FRAME_2: PixelData = _build_pikachu_frame_2()
PIKACHU_FRAME_3: PixelData = _build_pikachu_frame_3()
PIKACHU_FRAME_4: PixelData = _build_pikachu_frame_4()
PIKACHU_FRAMES: list[PixelData] = [
    PIKACHU_FRAME_1,
    PIKACHU_FRAME_2,
    PIKACHU_FRAME_3,
    PIKACHU_FRAME_4,
]


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
    show_pikachu: bool = True,
    show_pokeball: bool = True,
) -> None:
    """Draw one frame of the pokeball rolling transition (left-to-right).

    The pokeball rolls from off-screen left to off-screen right.
    Everything to its left is blacked out (erased).
    When pikachu is enabled, total travel extends so pikachu fully
    exits the screen before the cut.
    `show_pokeball=False` hides the ball sprite while keeping the
    blackout/Pikachu motion intact (Pikachu chases an invisible ball).
    """
    pikachu_trail = (PIKACHU_GAP + PIKACHU_WIDTH) if show_pikachu else 0
    total_travel = width + SPRITE_SIZE + pikachu_trail
    ball_x = int(-SPRITE_SIZE + progress * total_travel)

    # Select rotation frame based on distance traveled
    pixels_per_frame = PIXELS_PER_ROTATION // NUM_FRAMES  # 11px per frame
    frame_idx = (max(0, ball_x) // pixels_per_frame) % NUM_FRAMES
    sprite = POKEBALL_FRAMES[frame_idx]

    # Black out everything to the left of the ball
    blackout_end = min(width, max(0, ball_x))
    if blackout_end > 0:
        canvas.SubFill(0, 0, blackout_end, height, 0, 0, 0)

    # Draw the pokeball sprite (clipped to canvas bounds)
    if show_pokeball:
        for dx, dy, r, g, b in sprite:
            x = ball_x + dx
            y = SPRITE_Y_OFFSET + dy
            if 0 <= x < width and 0 <= y < height:
                canvas.SetPixel(x, y, r, g, b)

    # Draw Pikachu chasing the pokeball
    if show_pikachu:
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


def draw_pokeball_frame_rtl(
    canvas: Canvas,
    progress: float,
    width: int = 160,
    height: int = 16,
    show_pikachu: bool = True,
    show_pokeball: bool = True,
) -> None:
    """Draw one frame of the pokeball rolling transition (right-to-left).

    Mirror of draw_pokeball_frame: ball rolls from right to left,
    blackout is on the right, sprites are horizontally flipped.
    When pikachu is enabled, total travel extends so pikachu fully
    exits the screen before the cut.
    `show_pokeball=False` hides the ball sprite while keeping the
    blackout/Pikachu motion intact.
    """
    pikachu_trail = (PIKACHU_GAP + PIKACHU_WIDTH) if show_pikachu else 0
    total_travel = width + SPRITE_SIZE + pikachu_trail
    ball_x = int(width - progress * total_travel)

    # Select rotation frame (reverse direction = counter-clockwise)
    pixels_traveled = int(progress * total_travel)
    pixels_per_frame = PIXELS_PER_ROTATION // NUM_FRAMES
    frame_idx = (pixels_traveled // pixels_per_frame) % NUM_FRAMES
    sprite = POKEBALL_FRAMES[frame_idx]

    # Black out everything to the right of the ball
    blackout_start = max(0, min(width, ball_x + SPRITE_SIZE))
    if blackout_start < width:
        canvas.SubFill(blackout_start, 0, width - blackout_start, height, 0, 0, 0)

    # Draw the pokeball sprite (flipped horizontally)
    if show_pokeball:
        for dx, dy, r, g, b in sprite:
            x = ball_x + (SPRITE_SIZE - 1 - dx)
            y = SPRITE_Y_OFFSET + dy
            if 0 <= x < width and 0 <= y < height:
                canvas.SetPixel(x, y, r, g, b)

    # Draw Pikachu chasing the pokeball (flipped, trailing to the right)
    if show_pikachu:
        pika_x = ball_x + SPRITE_SIZE + PIKACHU_GAP
        pika_frame_idx = (pixels_traveled // PIKACHU_FRAMES_PER_STEP) % len(
            PIKACHU_FRAMES
        )
        pika_sprite = PIKACHU_FRAMES[pika_frame_idx]
        for dx, dy, r, g, b in pika_sprite:
            x = pika_x + (PIKACHU_WIDTH - 1 - dx)
            y = PIKACHU_Y_OFFSET + dy
            if 0 <= x < width and 0 <= y < height:
                canvas.SetPixel(x, y, r, g, b)


# --- Transition classes ---


@register_transition("pokeball")
class Pokeball:
    """Pokeball rolls left-to-right, erasing outgoing content.

    On a `ScaledCanvas` (bigsign), dispatches to the hi-res path which
    paints a real animated Pikachu sprite at native physical resolution.
    """

    min_frames: int = 40
    scale_switch_at: ClassVar[float] = 0.0
    _registry_name: str = "pokeball"

    def __init__(
        self,
        show_pikachu: bool = True,
        show_pokeball: bool = True,
        **kwargs: Any,
    ) -> None:
        # Coerce in case TOML user passes a string ("false" is truthy in Python).
        self._show_pikachu = bool(show_pikachu)
        self._show_pokeball = bool(show_pokeball)

    def frame_at(
        self, t: float, canvas: Canvas, outgoing: Any, incoming: Any, **kwargs: Any
    ) -> Canvas:
        if t >= 1.0:
            incoming.draw(canvas, cursor_pos=0)
            return canvas

        if isinstance(canvas, ScaledCanvas) and self._registry_name in HIRES_REGISTRY:
            return self._frame_at_hires(t, canvas, outgoing, incoming, **kwargs)
        return self._frame_at_lowres(t, canvas, outgoing, incoming, **kwargs)

    def _frame_at_lowres(
        self, t: float, canvas: Canvas, outgoing: Any, incoming: Any, **kwargs: Any
    ) -> Canvas:
        outgoing_scroll_pos: int = kwargs.get("outgoing_scroll_pos", 0)
        outgoing.draw(canvas, cursor_pos=outgoing_scroll_pos)
        draw_pokeball_frame(
            canvas,
            t,
            width=canvas.width,
            height=getattr(canvas, "height", 16),
            show_pikachu=self._show_pikachu,
            show_pokeball=self._show_pokeball,
        )
        return canvas

    def _frame_at_hires(
        self, t: float, canvas: Canvas, outgoing: Any, incoming: Any, **kwargs: Any
    ) -> Canvas:
        from led_ticker.transitions._hires_loader import render_hires_frame

        return render_hires_frame(
            t,
            canvas,
            outgoing,
            incoming,
            self._registry_name,
            show_pikachu=self._show_pikachu,
            show_pokeball=self._show_pokeball,
            **kwargs,
        )


@register_transition("pokeball_reverse")
class PokeballReverse:
    """Pokeball rolls right-to-left, erasing outgoing content."""

    min_frames: int = 40
    scale_switch_at: ClassVar[float] = 0.0
    _registry_name: str = "pokeball_reverse"

    def __init__(
        self,
        show_pikachu: bool = True,
        show_pokeball: bool = True,
        **kwargs: Any,
    ) -> None:
        # Coerce in case TOML user passes a string ("false" is truthy in Python).
        self._show_pikachu = bool(show_pikachu)
        self._show_pokeball = bool(show_pokeball)

    def frame_at(
        self, t: float, canvas: Canvas, outgoing: Any, incoming: Any, **kwargs: Any
    ) -> Canvas:
        if t >= 1.0:
            incoming.draw(canvas, cursor_pos=0)
            return canvas

        if isinstance(canvas, ScaledCanvas) and self._registry_name in HIRES_REGISTRY:
            return self._frame_at_hires(t, canvas, outgoing, incoming, **kwargs)
        return self._frame_at_lowres(t, canvas, outgoing, incoming, **kwargs)

    def _frame_at_lowres(
        self, t: float, canvas: Canvas, outgoing: Any, incoming: Any, **kwargs: Any
    ) -> Canvas:
        outgoing_scroll_pos: int = kwargs.get("outgoing_scroll_pos", 0)
        outgoing.draw(canvas, cursor_pos=outgoing_scroll_pos)
        draw_pokeball_frame_rtl(
            canvas,
            t,
            width=canvas.width,
            height=getattr(canvas, "height", 16),
            show_pikachu=self._show_pikachu,
            show_pokeball=self._show_pokeball,
        )
        return canvas

    def _frame_at_hires(
        self, t: float, canvas: Canvas, outgoing: Any, incoming: Any, **kwargs: Any
    ) -> Canvas:
        from led_ticker.transitions._hires_loader import render_hires_frame

        return render_hires_frame(
            t,
            canvas,
            outgoing,
            incoming,
            self._registry_name,
            show_pikachu=self._show_pikachu,
            show_pokeball=self._show_pokeball,
            **kwargs,
        )


@register_transition("pokeball_alternating")
class PokeballAlternating:
    """Cycles through pokeball -> pokeball_reverse."""

    scale_switch_at: ClassVar[float] = 0.0

    def __init__(self, **kwargs: Any) -> None:
        self._transitions: list[Transition] = [
            Pokeball(**kwargs),
            PokeballReverse(**kwargs),
        ]
        self._index: int = -1
        self._last_t: float = 1.0

    @property
    def min_frames(self) -> int:
        next_idx = (self._index + 1) % len(self._transitions)
        return getattr(self._transitions[next_idx], "min_frames", 40)

    def frame_at(
        self, t: float, canvas: Canvas, outgoing: Any, incoming: Any, **kwargs: Any
    ) -> Canvas:
        if t < self._last_t:
            self._index = (self._index + 1) % len(self._transitions)
        self._last_t = t
        return self._transitions[self._index].frame_at(
            t, canvas, outgoing, incoming, **kwargs
        )
