"""Shared drawing helpers for LED canvas rendering."""

import math


def get_text_width(font, text: str, padding: int = 6) -> int:
    """Get the pixel width of rendered text plus padding."""
    return sum(font.CharacterWidth(ord(c)) for c in text) + padding


def find_center(canvas_width: int, content_width: int) -> float:
    """Find the x position to center content on a canvas."""
    return (canvas_width / 2) - math.floor(content_width / 2)


def compute_cursor(
    canvas_width: int,
    content_width: int,
    cursor_pos: int,
    padding: int,
    center: bool,
) -> tuple[int, int]:
    """Compute cursor position and end padding, handling centering logic.

    Returns (adjusted_cursor_pos, end_padding).
    """
    end_padding = padding

    if center and content_width <= canvas_width:
        center_pos = find_center(canvas_width, content_width)
        end_padding = canvas_width - (center_pos + content_width)
        cursor_pos += center_pos

    return cursor_pos, end_padding
