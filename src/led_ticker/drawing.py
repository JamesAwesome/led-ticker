"""Shared drawing helpers for LED canvas rendering."""

from __future__ import annotations

import math
from typing import Any

import attrs

from led_ticker.fonts.hires_loader import HiresFont


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


# Fallback scale used by `get_text_width` when no canvas is provided.
# Hi-res fonts only make sense on the bigsign at scale=4 today, so
# this preserves the pre-canvas-aware behavior for callers (e.g.
# `TickerMessage.__init__`) that don't have a canvas yet. If hi-res
# use spreads beyond the bigsign, audit no-canvas call sites — they'll
# under-report widths on a small sign at scale=1.
SCALE_FALLBACK: int = 4


def get_text_width(font: Any, text: str, padding: int = 6, canvas: Any = None) -> int:
    """Get the pixel width of rendered text plus padding.

    Dispatches on font type: HiresFont sums glyph advances (with ``?``
    fallback for unknown chars), then converts the real-pixel total to
    logical pixels so layout math stays in consistent units with the
    BDF path. BDF C font uses ``CharacterWidth(ord(c))`` as before.

    `canvas` (optional) supplies the scale for the real→logical
    conversion. Pass it from any draw-time call site to get the
    correct width on any scale; the function reads ``getattr(canvas,
    "scale", 1)`` so plain real canvases are treated as scale=1.
    When `canvas` is None, falls back to ``SCALE_FALLBACK = 4`` —
    used by callers that pre-compute width before a canvas exists
    (e.g. ``TickerMessage.__init__``). The fallback preserves the
    original bigsign-only behavior.
    """
    if isinstance(font, HiresFont):
        fallback = font.glyphs.get("?")
        fallback_advance = fallback.advance if fallback else 0
        total_real = sum(
            font.glyphs[c].advance if c in font.glyphs else fallback_advance
            for c in text
        )
        # Hi-res glyph advances are REAL pixels. Logical (cf.
        # canvas.width on a ScaledCanvas) needs ceil-division by
        # scale; ceil so we never undercount and break overflow
        # detection on text that just barely fits.
        scale = getattr(canvas, "scale", None) if canvas is not None else None
        if scale is None or scale < 1:
            scale = SCALE_FALLBACK
        return -(-total_real // scale) + padding
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
