"""Sailor Moon wand transition with sparkle trail."""

from __future__ import annotations

from typing import Any, ClassVar

from led_ticker._types import Canvas, PixelData
from led_ticker.transitions import Transition, register_transition

# --- Sprite dimensions ---

WAND_WIDTH: int = 8
WAND_HEIGHT: int = 16
SPARKLE_ZONE: int = 30

# --- Color palette ---

_GOLD = (255, 215, 0)
_PINK = (255, 105, 180)
_MAGENTA = (255, 50, 150)
_WHITE = (255, 255, 255)
_LPINK = (255, 182, 213)
_BLUE = (0, 100, 255)

_SPARKLE_COLORS: list[tuple[int, int, int]] = [_GOLD, _PINK, _WHITE, _MAGENTA, _BLUE]

# --- Moon Stick sprite (8x16) ---
# Crescent moon at top (open right — left arc visible), jewel, pink rod below

MOON_STICK: PixelData = [
    # Row 0: crescent top curve
    (3, 0, *_GOLD),
    (4, 0, *_GOLD),
    (5, 0, *_GOLD),
    # Row 1: crescent upper arc
    (2, 1, *_GOLD),
    (3, 1, *_GOLD),
    # Row 2: crescent thick left edge
    (2, 2, *_GOLD),
    (3, 2, *_GOLD),
    # Row 3: crescent lower arc + blue jewel inside
    (2, 3, *_GOLD),
    (3, 3, *_GOLD),
    (4, 3, *_BLUE),
    # Row 4: crescent bottom curve
    (3, 4, *_GOLD),
    (4, 4, *_GOLD),
    (5, 4, *_GOLD),
    # Row 5: jewel
    (4, 5, *_MAGENTA),
    (5, 5, *_MAGENTA),
    # Row 6: jewel glow
    (4, 6, *_LPINK),
    # Row 7-15: rod
    (4, 7, *_PINK),
    (4, 8, *_PINK),
    (4, 9, *_PINK),
    (4, 10, *_PINK),
    (4, 11, *_PINK),
    (4, 12, *_PINK),
    (4, 13, *_PINK),
    (4, 14, *_PINK),
    (4, 15, *_PINK),
]


def _sparkle_hash(x: int, y: int) -> int:
    """Deterministic hash for sparkle placement."""
    return ((x * 7919) ^ (y * 6271)) & 0xFFFF


def draw_sailor_moon_frame(
    canvas: Canvas,
    progress: float,
    width: int = 160,
    height: int = 16,
) -> None:
    """Draw one frame of the Moon Stick wipe transition (left-to-right).

    The wand sweeps right, trailing sparkles that erase outgoing content.
    """
    total_travel = width + WAND_WIDTH + SPARKLE_ZONE * 2
    wand_x = int(-WAND_WIDTH - SPARKLE_ZONE + progress * total_travel)
    pixels_traveled = int(progress * total_travel)

    # Black out everything left of sparkle zone
    blackout_end = min(width, max(0, wand_x - SPARKLE_ZONE))
    for y in range(height):
        for x in range(blackout_end):
            canvas.SetPixel(x, y, 0, 0, 0)

    # Draw sparkle zone (between wand_x - SPARKLE_ZONE and wand_x)
    sparkle_start = max(0, wand_x - SPARKLE_ZONE)
    sparkle_end = min(width, max(0, wand_x))
    for x in range(sparkle_start, sparkle_end):
        # Density falloff: closer to wand = more sparkles
        dist_from_wand = wand_x - x
        density = max(0.0, 1.0 - dist_from_wand / SPARKLE_ZONE)
        threshold = int(density * 0.25 * 0xFFFF)

        for y in range(height):
            h = _sparkle_hash(x, y)
            if h < threshold:
                # Twinkle: skip 1/3 of sparkles each frame
                if (h + pixels_traveled) % 3 == 0:
                    canvas.SetPixel(x, y, 0, 0, 0)
                    continue
                color = _SPARKLE_COLORS[h % len(_SPARKLE_COLORS)]
                canvas.SetPixel(x, y, *color)
            else:
                # Not a sparkle pixel — black it out
                canvas.SetPixel(x, y, 0, 0, 0)

    # Draw wand sprite
    for dx, dy, r, g, b in MOON_STICK:
        x = wand_x + dx
        y = dy
        if 0 <= x < width and 0 <= y < height:
            canvas.SetPixel(x, y, r, g, b)


def draw_sailor_moon_frame_rtl(
    canvas: Canvas,
    progress: float,
    width: int = 160,
    height: int = 16,
) -> None:
    """Draw one frame of the Moon Stick wipe transition (right-to-left).

    Mirror of LTR: wand sweeps left, sparkles trail to the right.
    """
    total_travel = width + WAND_WIDTH + SPARKLE_ZONE * 2
    wand_x = int(width + SPARKLE_ZONE - progress * total_travel)
    pixels_traveled = int(progress * total_travel)

    # Black out everything right of sparkle zone
    blackout_start = max(0, min(width, wand_x + WAND_WIDTH + SPARKLE_ZONE))
    for y in range(height):
        for x in range(blackout_start, width):
            canvas.SetPixel(x, y, 0, 0, 0)

    # Draw sparkle zone to the right of the wand
    sparkle_start = max(0, wand_x + WAND_WIDTH)
    sparkle_end = min(width, wand_x + WAND_WIDTH + SPARKLE_ZONE)
    for x in range(sparkle_start, sparkle_end):
        dist_from_wand = x - (wand_x + WAND_WIDTH)
        density = max(0.0, 1.0 - dist_from_wand / SPARKLE_ZONE)
        threshold = int(density * 0.25 * 0xFFFF)

        for y in range(height):
            h = _sparkle_hash(x, y)
            if h < threshold:
                if (h + pixels_traveled) % 3 == 0:
                    canvas.SetPixel(x, y, 0, 0, 0)
                    continue
                color = _SPARKLE_COLORS[h % len(_SPARKLE_COLORS)]
                canvas.SetPixel(x, y, *color)
            else:
                canvas.SetPixel(x, y, 0, 0, 0)

    # Draw wand sprite (flipped horizontally)
    for dx, dy, r, g, b in MOON_STICK:
        x = wand_x + (WAND_WIDTH - 1 - dx)
        y = dy
        if 0 <= x < width and 0 <= y < height:
            canvas.SetPixel(x, y, r, g, b)


# --- Transition classes ---


@register_transition("sailor_moon")
class SailorMoon:
    """Moon Stick wand sweeps left-to-right with sparkle trail."""

    min_frames: int = 40
    # Switch to the incoming section's scale before the very first frame so the
    # wand sprite stays physically consistent throughout.  Dissolve-style
    # transitions use the default (0.5) to blend both scales mid-transition.
    scale_switch_at: ClassVar[float] = 0.0

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
        draw_sailor_moon_frame(
            canvas,
            t,
            width=canvas.width,
            height=getattr(canvas, "height", 16),
        )
        return canvas


@register_transition("sailor_moon_reverse")
class SailorMoonReverse:
    """Moon Stick wand sweeps right-to-left with sparkle trail."""

    min_frames: int = 40
    scale_switch_at: ClassVar[float] = 0.0

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
        draw_sailor_moon_frame_rtl(
            canvas,
            t,
            width=canvas.width,
            height=getattr(canvas, "height", 16),
        )
        return canvas


@register_transition("sailor_moon_alternating")
class SailorMoonAlternating:
    """Cycles through sailor_moon -> sailor_moon_reverse."""

    scale_switch_at: ClassVar[float] = 0.0

    def __init__(self, **kwargs: Any) -> None:
        self._transitions: list[Transition] = [
            SailorMoon(**kwargs),
            SailorMoonReverse(**kwargs),
        ]
        self._index: int = -1
        self._last_t: float = 1.0

    @property
    def min_frames(self) -> int:
        next_idx = (self._index + 1) % len(self._transitions)
        return self._transitions[next_idx].min_frames

    def frame_at(
        self, t: float, canvas: Canvas, outgoing: Any, incoming: Any, **kwargs: Any
    ) -> Canvas:
        if t < self._last_t:
            self._index = (self._index + 1) % len(self._transitions)
        self._last_t = t
        return self._transitions[self._index].frame_at(
            t, canvas, outgoing, incoming, **kwargs
        )
