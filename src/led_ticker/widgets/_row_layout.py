"""Shared per-row layout helpers for multi-row text widgets.

Currently used by `TwoRowMessage` (`widgets/two_row.py`) and the
two-row text-overlay path on `_BaseImageWidget` (`widgets/_image_base.py`).
Both widgets split a canvas into vertically-stacked bands; the
helpers here compute baselines, emoji anchor points, and horizontal
alignment for an individual band.

These helpers are deliberately small wrappers over `drawing.py`'s
font-aware primitives (`compute_baseline_for_band`, `safe_scale`).
The split exists so that future row-based widgets (a 3-row variant,
a side-by-side stats card, etc.) can adopt them without importing
`two_row.py` directly.
"""

from __future__ import annotations

from typing import Any

from led_ticker._types import Canvas
from led_ticker.drawing import compute_baseline_for_band, safe_scale

# Cap on emoji vertical size per row. Inline emoji sprites are 8×8
# logical (low-res) or up to 32×32 real (hi-res). We cap at 8 logical
# rows so a hi-res sprite that would overflow the row band falls back
# to the 8×8 low-res sprite (`pixel_emoji.draw_with_emoji` honors
# `max_emoji_height`). Independent of the text font's line height.
EMOJI_ROW_CAP: int = 8


def row_layout(
    canvas: Canvas,
    font: Any,
    band_height: int,
    band_offset: int,
) -> tuple[int, int]:
    """Return (text_baseline_y, emoji_top_y) for one row's band.

    `band_height` is the number of logical rows allocated to this row;
    `band_offset` is the logical y of the band's top edge. With a
    50/50 split on a 16-row canvas these are (8, 0) for top and
    (8, 8) for bottom. With an asymmetric `top_row_height = 4`, top
    is (4, 0) and bottom is (12, 4).

    Delegates baseline math to `compute_baseline_for_band`; centers
    the emoji sprite on an `EMOJI_ROW_CAP`-tall sub-band so 8-px
    emoji coexist with any text size.

    For small bands (`band_height < EMOJI_ROW_CAP = 8`), the centered
    formula would produce a negative `emoji_y` relative to the band —
    clipping the top of the sprite above the band edge. Clamp to
    `band_offset` so the emoji top is at least the band's top edge
    (the bottom may then bleed into the next band's space, which is
    benign as long as that space isn't occupied — typical asymmetric
    layouts have a small top tag where this bleed lands harmlessly
    before the bottom row's text baseline).
    """
    emoji_y = max(band_offset, (band_height - EMOJI_ROW_CAP) // 2 + band_offset)
    baseline = compute_baseline_for_band(
        font, band_height, safe_scale(canvas), valign="center"
    )
    text_baseline = baseline + band_offset
    return text_baseline, emoji_y


def aligned_x(canvas_width: int, content_width: int, align: str) -> int:
    """Compute the x position for a row given its alignment.

    "left" anchors at 0, "right" anchors at the right edge minus
    content width (clamped to 0 if content overflows), "center"
    centers the content (falls back to "left" when content is wider
    than the canvas).
    """
    if align == "left":
        return 0
    if align == "right":
        return max(0, canvas_width - content_width)
    # center (default) — falls through for unknown values too
    if content_width >= canvas_width:
        return 0  # too wide; left-align so we at least see the start
    return (canvas_width - content_width) // 2


def resolve_band_heights(
    canvas_height: int, top_row_height: int | None
) -> tuple[int, int]:
    """Split `canvas_height` into (top_h, bottom_h) per the override.

    Default `top_row_height = None` → 50/50 split. Otherwise the top
    band gets exactly `top_row_height` logical rows and the bottom
    gets the remainder.

    Raises `ValueError` when `top_row_height >= canvas_height` —
    bottom would have zero rows. Validation here so multi-row widgets
    don't have to repeat it.
    """
    if top_row_height is None:
        top_h = canvas_height // 2
    else:
        if top_row_height >= canvas_height:
            raise ValueError(
                f"top_row_height={top_row_height} leaves no room for the "
                f"bottom row on a {canvas_height}-tall canvas. Must be "
                f"< canvas.height (current = {canvas_height})."
            )
        top_h = top_row_height
    return top_h, canvas_height - top_h


__all__ = [
    "EMOJI_ROW_CAP",
    "aligned_x",
    "resolve_band_heights",
    "row_layout",
]
