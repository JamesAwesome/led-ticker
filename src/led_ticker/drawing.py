"""Shared drawing helpers for LED canvas rendering."""

from __future__ import annotations

import math
from typing import Any

import attrs

from led_ticker._types import Font


@attrs.define(frozen=True, slots=True)
class Region:
    """A rectangular sub-area of a canvas.

    Plumbed through draw() and run_transition() for forward compatibility
    with zoned layouts. Currently always equals the full canvas.
    """

    x: int
    y: int
    width: int
    height: int


def get_widget_padding(widget: Any, default: int = 6) -> int:
    """Get a widget's padding attribute, with fallback for mocks."""
    padding = getattr(widget, "padding", None)
    return padding if isinstance(padding, int) else default


def get_text_width(font: Font, text: str, padding: int = 6) -> int:
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
        center_pos = int(find_center(canvas_width, content_width))
        end_padding = canvas_width - (center_pos + content_width)
        cursor_pos += center_pos

    return cursor_pos, end_padding
