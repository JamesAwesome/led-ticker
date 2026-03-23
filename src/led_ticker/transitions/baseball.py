"""Baseball sprite and rolling animation for LED matrix transitions."""

from __future__ import annotations

from typing import Any

from led_ticker._types import Canvas, PixelData
from led_ticker.transitions import Transition, register_transition

SPRITE_SIZE: int = 14
SPRITE_Y_OFFSET: int = 1  # centers 14px sprite in 16px display
PIXELS_PER_ROTATION: int = 44  # circumference of 14px circle ≈ π×14
NUM_FRAMES: int = 4

# Color palette
_WH = (255, 255, 255)  # white (ball)
_RD = (220, 40, 40)  # red (stitches)
_OL = (40, 40, 40)  # outline (dark gray)
_SH = (220, 220, 220)  # shadow/off-white


def _circle_mask() -> set[tuple[int, int]]:
    """Pre-compute which (dx, dy) are inside a 14px diameter circle."""
    cx, cy = 6.5, 6.5
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
    """Frame 0: Vertical stitch curves on left and right sides."""
    interior = _circle_mask()
    outline = _outline_mask(interior)
    # Stitch positions: S-curves on left (x=3-4) and right (x=9-10)
    stitches: set[tuple[int, int]] = set()
    # Left stitch curve (top-right to bottom-left arc)
    for dx, dy in [
        (4, 2),
        (3, 3),
        (3, 4),
        (2, 5),
        (2, 6),
        (2, 7),
        (3, 8),
        (3, 9),
        (4, 10),
        (4, 11),
    ]:
        if (dx, dy) in interior:
            stitches.add((dx, dy))
    # Right stitch curve (mirrored)
    for dx, dy in [
        (9, 2),
        (10, 3),
        (10, 4),
        (11, 5),
        (11, 6),
        (11, 7),
        (10, 8),
        (10, 9),
        (9, 10),
        (9, 11),
    ]:
        if (dx, dy) in interior:
            stitches.add((dx, dy))

    pixels: PixelData = []
    for dx, dy in sorted(interior):
        if (dx, dy) in outline:
            pixels.append((dx, dy, *_OL))
        elif (dx, dy) in stitches:
            pixels.append((dx, dy, *_RD))
        else:
            pixels.append((dx, dy, *_WH))
    return pixels


def _build_frame_1() -> PixelData:
    """Frame 1: 90° — horizontal stitch curves on top and bottom."""
    interior = _circle_mask()
    outline = _outline_mask(interior)
    stitches: set[tuple[int, int]] = set()
    # Top stitch curve
    for dx, dy in [
        (2, 4),
        (3, 3),
        (4, 3),
        (5, 2),
        (6, 2),
        (7, 2),
        (8, 3),
        (9, 3),
        (10, 4),
        (11, 4),
    ]:
        if (dx, dy) in interior:
            stitches.add((dx, dy))
    # Bottom stitch curve
    for dx, dy in [
        (2, 9),
        (3, 10),
        (4, 10),
        (5, 11),
        (6, 11),
        (7, 11),
        (8, 10),
        (9, 10),
        (10, 9),
        (11, 9),
    ]:
        if (dx, dy) in interior:
            stitches.add((dx, dy))

    pixels: PixelData = []
    for dx, dy in sorted(interior):
        if (dx, dy) in outline:
            pixels.append((dx, dy, *_OL))
        elif (dx, dy) in stitches:
            pixels.append((dx, dy, *_RD))
        else:
            pixels.append((dx, dy, *_WH))
    return pixels


def _build_frame_2() -> PixelData:
    """Frame 2: 180° — vertical stitch curves, mirrored from frame 0."""
    interior = _circle_mask()
    outline = _outline_mask(interior)
    stitches: set[tuple[int, int]] = set()
    # Left stitch (mirrored vertical from frame 0)
    for dx, dy in [
        (4, 2),
        (3, 3),
        (3, 4),
        (3, 5),
        (2, 6),
        (3, 7),
        (3, 8),
        (3, 9),
        (4, 10),
        (5, 11),
    ]:
        if (dx, dy) in interior:
            stitches.add((dx, dy))
    # Right stitch (mirrored)
    for dx, dy in [
        (9, 2),
        (10, 3),
        (10, 4),
        (10, 5),
        (11, 6),
        (10, 7),
        (10, 8),
        (10, 9),
        (9, 10),
        (8, 11),
    ]:
        if (dx, dy) in interior:
            stitches.add((dx, dy))

    pixels: PixelData = []
    for dx, dy in sorted(interior):
        if (dx, dy) in outline:
            pixels.append((dx, dy, *_OL))
        elif (dx, dy) in stitches:
            pixels.append((dx, dy, *_RD))
        else:
            pixels.append((dx, dy, *_WH))
    return pixels


def _build_frame_3() -> PixelData:
    """Frame 3: 270° — horizontal stitch curves, mirrored from frame 1."""
    interior = _circle_mask()
    outline = _outline_mask(interior)
    stitches: set[tuple[int, int]] = set()
    # Top stitch curve (mirrored from frame 1)
    for dx, dy in [
        (2, 4),
        (3, 3),
        (4, 3),
        (5, 3),
        (6, 2),
        (7, 3),
        (8, 3),
        (9, 3),
        (10, 4),
        (11, 5),
    ]:
        if (dx, dy) in interior:
            stitches.add((dx, dy))
    # Bottom stitch curve (mirrored)
    for dx, dy in [
        (2, 9),
        (3, 10),
        (4, 10),
        (5, 10),
        (6, 11),
        (7, 10),
        (8, 10),
        (9, 10),
        (10, 9),
        (11, 8),
    ]:
        if (dx, dy) in interior:
            stitches.add((dx, dy))

    pixels: PixelData = []
    for dx, dy in sorted(interior):
        if (dx, dy) in outline:
            pixels.append((dx, dy, *_OL))
        elif (dx, dy) in stitches:
            pixels.append((dx, dy, *_RD))
        else:
            pixels.append((dx, dy, *_WH))
    return pixels


BASEBALL_FRAME_0: PixelData = _build_frame_0()
BASEBALL_FRAME_1: PixelData = _build_frame_1()
BASEBALL_FRAME_2: PixelData = _build_frame_2()
BASEBALL_FRAME_3: PixelData = _build_frame_3()

BASEBALL_FRAMES: list[PixelData] = [
    BASEBALL_FRAME_0,
    BASEBALL_FRAME_1,
    BASEBALL_FRAME_2,
    BASEBALL_FRAME_3,
]


def draw_baseball_frame(
    canvas: Canvas,
    progress: float,
    width: int = 160,
    height: int = 16,
) -> None:
    """Draw one frame of the baseball rolling transition (left-to-right).

    The baseball rolls from off-screen left to off-screen right.
    Everything to its left is blacked out (erased).
    """
    total_travel = width + SPRITE_SIZE
    ball_x = int(-SPRITE_SIZE + progress * total_travel)

    # Select rotation frame based on distance traveled
    pixels_per_frame = PIXELS_PER_ROTATION // NUM_FRAMES
    frame_idx = (max(0, ball_x) // pixels_per_frame) % NUM_FRAMES
    sprite = BASEBALL_FRAMES[frame_idx]

    # Black out everything to the left of the ball
    blackout_end = min(width, max(0, ball_x))
    for y in range(height):
        for x in range(blackout_end):
            canvas.SetPixel(x, y, 0, 0, 0)

    # Draw the baseball sprite (clipped to canvas bounds)
    for dx, dy, r, g, b in sprite:
        x = ball_x + dx
        y = SPRITE_Y_OFFSET + dy
        if 0 <= x < width and 0 <= y < height:
            canvas.SetPixel(x, y, r, g, b)


def draw_baseball_frame_rtl(
    canvas: Canvas,
    progress: float,
    width: int = 160,
    height: int = 16,
) -> None:
    """Draw one frame of the baseball rolling transition (right-to-left).

    Mirror of draw_baseball_frame: ball rolls from right to left,
    blackout is on the right, sprite is horizontally flipped.
    """
    total_travel = width + SPRITE_SIZE
    ball_x = int(width - progress * total_travel)

    # Select rotation frame
    pixels_traveled = int(progress * total_travel)
    pixels_per_frame = PIXELS_PER_ROTATION // NUM_FRAMES
    frame_idx = (pixels_traveled // pixels_per_frame) % NUM_FRAMES
    sprite = BASEBALL_FRAMES[frame_idx]

    # Black out everything to the right of the ball
    blackout_start = max(0, min(width, ball_x + SPRITE_SIZE))
    for y in range(height):
        for x in range(blackout_start, width):
            canvas.SetPixel(x, y, 0, 0, 0)

    # Draw the baseball sprite (flipped horizontally)
    for dx, dy, r, g, b in sprite:
        x = ball_x + (SPRITE_SIZE - 1 - dx)
        y = SPRITE_Y_OFFSET + dy
        if 0 <= x < width and 0 <= y < height:
            canvas.SetPixel(x, y, r, g, b)


# --- Transition classes ---


@register_transition("baseball")
class Baseball:
    """Baseball rolls left-to-right, erasing outgoing content."""

    min_frames: int = 40

    def __init__(self, **kwargs: Any) -> None:
        pass

    def frame_at(
        self, t: float, canvas: Canvas, outgoing: Any, incoming: Any, **kwargs: Any
    ) -> Canvas:
        if t >= 1.0:
            incoming.draw(canvas, cursor_pos=0)
            return canvas

        outgoing_scroll_pos: int = kwargs.get("outgoing_scroll_pos", 0)
        outgoing.draw(canvas, cursor_pos=outgoing_scroll_pos)
        draw_baseball_frame(
            canvas,
            t,
            width=canvas.width,
            height=getattr(canvas, "height", 16),
        )
        return canvas


@register_transition("baseball_reverse")
class BaseballReverse:
    """Baseball rolls right-to-left, erasing outgoing content."""

    min_frames: int = 40

    def __init__(self, **kwargs: Any) -> None:
        pass

    def frame_at(
        self, t: float, canvas: Canvas, outgoing: Any, incoming: Any, **kwargs: Any
    ) -> Canvas:
        if t >= 1.0:
            incoming.draw(canvas, cursor_pos=0)
            return canvas

        outgoing_scroll_pos: int = kwargs.get("outgoing_scroll_pos", 0)
        outgoing.draw(canvas, cursor_pos=outgoing_scroll_pos)
        draw_baseball_frame_rtl(
            canvas,
            t,
            width=canvas.width,
            height=getattr(canvas, "height", 16),
        )
        return canvas


@register_transition("baseball_alternating")
class BaseballAlternating:
    """Cycles through baseball -> baseball_reverse."""

    def __init__(self, **kwargs: Any) -> None:
        self._transitions: list[Transition] = [
            Baseball(**kwargs),
            BaseballReverse(**kwargs),
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
