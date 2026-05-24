"""Pac-Man and ghost sprites for LED matrix transitions."""

from __future__ import annotations

from typing import Any

from led_ticker._types import Canvas, PixelData
from led_ticker.transitions import Transition, register_transition

# --- Pac-Man sprite ---

PACMAN_SIZE: int = 14
PACMAN_Y_OFFSET: int = 1  # centers 14px sprite in 16px display
PACMAN_FRAMES_PER_STEP: int = 4  # pixels per mouth frame change

# Pac-Man palette
_PY = (255, 255, 0)  # yellow
_PK = (0, 0, 0)  # black (outline / mouth)

# --- Ghost sprite ---

GHOST_WIDTH: int = 10
GHOST_HEIGHT: int = 12
GHOST_Y_OFFSET: int = 2  # centers 12px ghost in 16px display
GHOST_FRAMES_PER_STEP: int = 6
GHOST_GAP: int = 4  # gap between ghosts
PACMAN_GHOST_GAP: int = 8  # gap between Pac-Man and first ghost

# Ghost colors (signature colors with scared expression)
_BLINKY = (255, 0, 0)  # red
_PINKY = (255, 184, 222)  # pink
_INKY = (0, 255, 222)  # cyan
_GW = (255, 255, 255)  # white (eyes)
_GK = (0, 0, 0)  # black (pupils)

GHOST_COLORS: list[tuple[int, int, int]] = [_BLINKY, _PINKY, _INKY]
NUM_GHOSTS: int = 3

# Total group width: Pac-Man + gap + (ghost + gap) * 3 - last gap
GROUP_WIDTH: int = (
    PACMAN_SIZE
    + PACMAN_GHOST_GAP
    + NUM_GHOSTS * GHOST_WIDTH
    + (NUM_GHOSTS - 1) * GHOST_GAP
)


def _pacman_circle() -> set[tuple[int, int]]:
    """Circle mask for 14px Pac-Man."""
    cx, cy = 6.5, 6.5
    r = 6.5
    mask: set[tuple[int, int]] = set()
    for dy in range(PACMAN_SIZE):
        for dx in range(PACMAN_SIZE):
            if (dx - cx) ** 2 + (dy - cy) ** 2 <= r * r:
                mask.add((dx, dy))
    return mask


def _pacman_outline(interior: set[tuple[int, int]]) -> set[tuple[int, int]]:
    """Edge pixels of the circle."""
    outline: set[tuple[int, int]] = set()
    for dx, dy in interior:
        for ndx, ndy in [(dx - 1, dy), (dx + 1, dy), (dx, dy - 1), (dx, dy + 1)]:
            if (ndx, ndy) not in interior:
                outline.add((dx, dy))
                break
    return outline


def _build_pacman_closed() -> PixelData:
    """Pac-Man with mouth closed (full circle)."""
    interior = _pacman_circle()
    outline = _pacman_outline(interior)
    pixels: PixelData = []
    for dx, dy in sorted(interior):
        if (dx, dy) in outline:
            pixels.append((dx, dy, *_PK))
        else:
            pixels.append((dx, dy, *_PY))
    return pixels


def _build_pacman_half() -> PixelData:
    """Pac-Man with mouth half open (small wedge removed on right)."""
    interior = _pacman_circle()
    outline = _pacman_outline(interior)
    # Remove wedge: rows 6-7 (center), cols 11-13 (right side)
    mouth: set[tuple[int, int]] = set()
    for dy in range(6, 8):
        for dx in range(11, 14):
            mouth.add((dx, dy))
    pixels: PixelData = []
    for dx, dy in sorted(interior):
        if (dx, dy) in mouth:
            continue
        is_mouth_edge = (
            (dx + 1, dy) in mouth or (dx, dy + 1) in mouth or (dx, dy - 1) in mouth
        )
        if (dx, dy) in outline or is_mouth_edge:
            pixels.append((dx, dy, *_PK))
        else:
            pixels.append((dx, dy, *_PY))
    return pixels


def _build_pacman_open() -> PixelData:
    """Pac-Man with mouth fully open (large wedge removed on right)."""
    interior = _pacman_circle()
    outline = _pacman_outline(interior)
    # Remove larger wedge: rows 4-9 tapering to a point at center-right
    mouth: set[tuple[int, int]] = set()
    cx, cy = 6.5, 6.5
    for dy in range(PACMAN_SIZE):
        for dx in range(PACMAN_SIZE):
            if (dx, dy) not in interior:
                continue
            # Wedge opens to the right from center
            rel_x = dx - cx
            rel_y = abs(dy - cy)
            if rel_x > 0 and rel_y < rel_x * 0.7:
                mouth.add((dx, dy))
    pixels: PixelData = []
    for dx, dy in sorted(interior):
        if (dx, dy) in mouth:
            continue
        is_mouth_edge = (
            (dx + 1, dy) in mouth or (dx, dy + 1) in mouth or (dx, dy - 1) in mouth
        )
        if (dx, dy) in outline or is_mouth_edge:
            pixels.append((dx, dy, *_PK))
        else:
            pixels.append((dx, dy, *_PY))
    return pixels


PACMAN_CLOSED: PixelData = _build_pacman_closed()
PACMAN_HALF: PixelData = _build_pacman_half()
PACMAN_OPEN: PixelData = _build_pacman_open()
PACMAN_FRAMES: list[PixelData] = [PACMAN_CLOSED, PACMAN_HALF, PACMAN_OPEN, PACMAN_HALF]


def _ghost_body(color: tuple[int, int, int]) -> set[tuple[int, int]]:
    """Compute which pixels are inside the ghost shape."""
    # Rounded top (semi-circle), rectangular middle, wavy bottom
    body: set[tuple[int, int]] = set()
    cx = 4.5
    r = 4.5
    for dy in range(GHOST_HEIGHT):
        for dx in range(GHOST_WIDTH):
            # Top: semi-circle (rows 0-4)
            if dy <= 4:
                if (dx - cx) ** 2 + (dy - cx) ** 2 <= r * r:
                    body.add((dx, dy))
            # Middle: full rectangle (rows 5-9)
            elif dy <= 9 and 0 <= dx < GHOST_WIDTH:
                body.add((dx, dy))
    return body


def _build_ghost_frame(color: tuple[int, int, int], wave_offset: int) -> PixelData:
    """Build one ghost frame with given body color and wave pattern."""
    body = _ghost_body(color)
    pixels: PixelData = []

    for dx, dy in sorted(body):
        # Eyes: white with black pupils at rows 3-4
        if dy == 3 and dx in (2, 3, 6, 7):
            pixels.append((dx, dy, *_GW))
        elif dy == 4 and dx in (3, 7):
            pixels.append((dx, dy, *_GK))  # pupils
        elif (dy == 4 and dx in (2, 6)) or (dy == 7 and dx in (2, 3, 4, 5, 6, 7)):
            pixels.append((dx, dy, *_GW))
        else:
            pixels.append((dx, dy, *color))

    # Wavy bottom edge (rows 10-11)
    for dx in range(GHOST_WIDTH):
        # Alternate bumps based on wave_offset
        if (dx + wave_offset) % 4 < 2:
            pixels.append((dx, 10, *color))
            pixels.append((dx, 11, *color))
        else:
            pixels.append((dx, 10, *color))
            # row 11 left empty (creates wave)

    return pixels


def _build_ghost_frames(
    color: tuple[int, int, int],
) -> list[PixelData]:
    """Build 2 wave animation frames for a ghost."""
    return [_build_ghost_frame(color, 0), _build_ghost_frame(color, 2)]


GHOST_FRAMES: list[list[PixelData]] = [
    _build_ghost_frames(_BLINKY),
    _build_ghost_frames(_PINKY),
    _build_ghost_frames(_INKY),
]


def draw_pacman_frame(
    canvas: Canvas,
    progress: float,
    width: int = 160,
    height: int = 16,
) -> None:
    """Draw one frame of the Pac-Man wipe transition (left-to-right).

    Ghosts flee ahead, Pac-Man chases behind. Everything up to and
    including Pac-Man's front edge is blacked out — letters vanish
    as Pac-Man chews through them, while ghosts (further right) pass
    over still-visible letters until Pac-Man reaches that column.
    """
    total_travel = width + GROUP_WIDTH
    # Pac-Man position (leftmost sprite in the group)
    pacman_x = int(-GROUP_WIDTH + progress * total_travel)

    # Black out from the left edge up through Pac-Man's right (front)
    # edge. Pac-Man is then drawn ON TOP of this blackout band.
    blackout_end = min(width, max(0, pacman_x + PACMAN_SIZE))
    if blackout_end > 0:
        canvas.SubFill(0, 0, blackout_end, height, 0, 0, 0)

    # Draw ghosts (ahead of Pac-Man)
    pixels_traveled = max(0, int(progress * total_travel))
    ghost_frame_idx = (pixels_traveled // GHOST_FRAMES_PER_STEP) % 2
    ghost_start = pacman_x + PACMAN_SIZE + PACMAN_GHOST_GAP
    for gi in range(NUM_GHOSTS):
        gx = ghost_start + gi * (GHOST_WIDTH + GHOST_GAP)
        ghost_sprite = GHOST_FRAMES[gi][ghost_frame_idx]
        for dx, dy, r, g, b in ghost_sprite:
            x = gx + dx
            y = GHOST_Y_OFFSET + dy
            if 0 <= x < width and 0 <= y < height:
                canvas.SetPixel(x, y, r, g, b)

    # Draw Pac-Man (facing right)
    pacman_frame_idx = (pixels_traveled // PACMAN_FRAMES_PER_STEP) % len(PACMAN_FRAMES)
    pacman_sprite = PACMAN_FRAMES[pacman_frame_idx]
    for dx, dy, r, g, b in pacman_sprite:
        x = pacman_x + dx
        y = PACMAN_Y_OFFSET + dy
        if 0 <= x < width and 0 <= y < height:
            canvas.SetPixel(x, y, r, g, b)


def draw_pacman_frame_rtl(
    canvas: Canvas,
    progress: float,
    width: int = 160,
    height: int = 16,
) -> None:
    """Draw one frame of the Pac-Man wipe transition (right-to-left).

    Mirror of draw_pacman_frame: Pac-Man on the right side,
    ghosts flee to the left. Blackout extends from Pac-Man's left
    (front) edge to the right edge of the panel — letters vanish as
    Pac-Man reaches them; ghosts pass over still-visible letters.
    """
    total_travel = width + GROUP_WIDTH
    # Pac-Man position (rightmost sprite, moving left)
    pacman_x = int(width - PACMAN_SIZE + GROUP_WIDTH - progress * total_travel)

    # Black out from Pac-Man's left (front) edge to the right edge.
    # Pac-Man is then drawn ON TOP of this blackout band.
    blackout_start = max(0, min(width, pacman_x))
    if blackout_start < width:
        canvas.SubFill(blackout_start, 0, width - blackout_start, height, 0, 0, 0)

    # Draw ghosts (ahead of Pac-Man, to the left)
    pixels_traveled = max(0, int(progress * total_travel))
    ghost_frame_idx = (pixels_traveled // GHOST_FRAMES_PER_STEP) % 2
    ghost_start = pacman_x - PACMAN_GHOST_GAP
    for gi in range(NUM_GHOSTS):
        gx = ghost_start - (gi + 1) * GHOST_WIDTH - gi * GHOST_GAP
        ghost_sprite = GHOST_FRAMES[gi][ghost_frame_idx]
        for dx, dy, r, g, b in ghost_sprite:
            # Flip horizontally
            x = gx + (GHOST_WIDTH - 1 - dx)
            y = GHOST_Y_OFFSET + dy
            if 0 <= x < width and 0 <= y < height:
                canvas.SetPixel(x, y, r, g, b)

    # Draw Pac-Man (facing left = flipped horizontally)
    pacman_frame_idx = (pixels_traveled // PACMAN_FRAMES_PER_STEP) % len(PACMAN_FRAMES)
    pacman_sprite = PACMAN_FRAMES[pacman_frame_idx]
    for dx, dy, r, g, b in pacman_sprite:
        x = pacman_x + (PACMAN_SIZE - 1 - dx)
        y = PACMAN_Y_OFFSET + dy
        if 0 <= x < width and 0 <= y < height:
            canvas.SetPixel(x, y, r, g, b)


# --- Transition classes ---


@register_transition("pacman")
class Pacman:
    """Pac-Man chases scared ghosts left-to-right, erasing outgoing content."""

    min_frames: int = 50

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
        draw_pacman_frame(
            canvas,
            t,
            width=canvas.width,
            height=getattr(canvas, "height", 16),
        )
        return canvas


@register_transition("pacman_reverse")
class PacmanReverse:
    """Pac-Man chases scared ghosts right-to-left, erasing outgoing content."""

    min_frames: int = 50

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
        draw_pacman_frame_rtl(
            canvas,
            t,
            width=canvas.width,
            height=getattr(canvas, "height", 16),
        )
        return canvas


@register_transition("pacman_alternating")
class PacmanAlternating:
    """Cycles through pacman -> pacman_reverse."""

    def __init__(self, **kwargs: Any) -> None:
        self._transitions: list[Transition] = [
            Pacman(**kwargs),
            PacmanReverse(**kwargs),
        ]
        self._index: int = -1
        self._last_t: float = 1.0

    @property
    def min_frames(self) -> int:
        next_idx = (self._index + 1) % len(self._transitions)
        return getattr(self._transitions[next_idx], "min_frames", 50)

    def frame_at(
        self, t: float, canvas: Canvas, outgoing: Any, incoming: Any, **kwargs: Any
    ) -> Canvas:
        if t < self._last_t:
            self._index = (self._index + 1) % len(self._transitions)
        self._last_t = t
        return self._transitions[self._index].frame_at(
            t, canvas, outgoing, incoming, **kwargs
        )
