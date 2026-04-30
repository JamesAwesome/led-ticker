"""Two-row widget for tall LED canvases (mainly the Pi 5 bigsign).

Renders TWO independent text strings on the same canvas:
- Top row stays at a fixed position (held)
- Bottom row scrolls left when its content overflows the canvas width

Best in `swap` mode: each `TwoRowMessage` is its own display unit. The
top-row string is meant for a stable identifier (handle, headline, brand
tag) and the bottom row for promotional copy that can be longer than
the canvas width.

Layout: the widget computes baselines from `canvas.height` so that
each row is centered in its half. Each row uses 8 logical rows (the
height of FONT_SMALL); any extra height becomes a gap between the rows.

  canvas.height = 16  →  no gap, rows immediately adjacent
  canvas.height = 18  →  1-row gap (cleanest for 8-tall fonts)
  canvas.height = 20  →  2-row gap (recommended for breathing room)
  canvas.height = 24  →  4-row gap (very airy)

Set the section's `content_height` to a value larger than 16 to enable
the gap. Caller controls per-row horizontal alignment via `top_align`
and `bottom_align` (`"left"`, `"center"`, `"right"`). The bottom row's
alignment only takes effect when the text fits without scrolling — if it
overflows, the framework scrolls it left regardless.

Inline emoji slugs (`:instagram:`, `:email:`, etc.) work in both rows.
"""

from __future__ import annotations

from typing import Any

import attrs

from led_ticker._types import Canvas, Color, DrawResult, Font
from led_ticker.colors import DEFAULT_COLOR
from led_ticker.fonts import FONT_SMALL
from led_ticker.pixel_emoji import draw_with_emoji, measure_width
from led_ticker.widgets import register

# Glyph height used to size rows. FONT_SMALL is 5x8 — 8-tall cells.
_ROW_HEIGHT = 8


def _row_y(canvas_height: int, row_index: int) -> tuple[int, int]:
    """Return (text_baseline_y, emoji_top_y) for the given row index.

    Splits canvas_height into two equal halves; centers the 8-row glyph
    band vertically inside each half. Any extra height becomes a gap
    between the rows.
    """
    half = canvas_height // 2
    # Center an 8-tall glyph band in `half` rows
    emoji_y = (half - _ROW_HEIGHT) // 2 + row_index * half
    text_baseline = emoji_y + _ROW_HEIGHT - 1  # baseline at bottom of glyph cell
    return text_baseline, emoji_y


def _aligned_x(canvas_width: int, content_width: int, align: str) -> int:
    """Compute the x position for a row given its alignment."""
    if align == "left":
        return 0
    if align == "right":
        return max(0, canvas_width - content_width)
    # center (default) — falls through for unknown values too
    if content_width >= canvas_width:
        return 0  # too wide; left-align so we at least see the start
    return (canvas_width - content_width) // 2


@register("two_row")
@attrs.define
class TwoRowMessage:
    """Two-row display: held top, scrolling bottom."""

    top_text: str
    bottom_text: str
    font: Font = attrs.Factory(lambda: FONT_SMALL)
    top_color: Color = attrs.Factory(lambda: DEFAULT_COLOR)
    bottom_color: Color = attrs.Factory(lambda: DEFAULT_COLOR)
    # Horizontal alignment per row: "left", "center", or "right". The
    # bottom row's alignment only matters when its text fits — when it
    # overflows, the framework scrolls it from cursor_pos regardless.
    top_align: str = "center"
    bottom_align: str = "left"
    padding: int = 6
    # Backwards-compat: top_center=True is the same as top_align="center".
    # If you set top_center=False, top_align="left" is used (legacy default).
    top_center: bool | None = None

    _top_width: int = attrs.field(init=False, default=-1)
    _bottom_width: int = attrs.field(init=False, default=-1)

    def __attrs_post_init__(self) -> None:
        if self.top_center is False:
            self.top_align = "left"
        elif self.top_center is True:
            self.top_align = "center"

    def _ensure_widths(self) -> None:
        if self._top_width < 0:
            self._top_width = measure_width(self.font, self.top_text)
        if self._bottom_width < 0:
            self._bottom_width = measure_width(self.font, self.bottom_text)

    def draw(self, canvas: Canvas, cursor_pos: int = 0, **kwargs: Any) -> DrawResult:
        del kwargs  # widget is meant for swap mode; y_offset/transitions ignored
        self._ensure_widths()

        canvas_height = getattr(canvas, "height", 16)
        top_text_y, top_emoji_y = _row_y(canvas_height, row_index=0)
        bottom_text_y, bottom_emoji_y = _row_y(canvas_height, row_index=1)

        # Top row at a fixed x — held while the bottom scrolls.
        top_x = _aligned_x(canvas.width, self._top_width, self.top_align)

        draw_with_emoji(
            canvas,
            self.font,
            top_x,
            top_text_y,
            self.top_color,
            self.top_text,
            emoji_y=top_emoji_y,
        )

        # Bottom row: cursor_pos is supplied by the framework. On the
        # first frame it's whatever start_pos says (typically 0). When
        # the bottom row fits without overflow, we use bottom_align to
        # nudge it; when it overflows, cursor_pos drives the scroll.
        if self._bottom_width <= canvas.width and cursor_pos == 0:
            bottom_x = _aligned_x(canvas.width, self._bottom_width, self.bottom_align)
        else:
            bottom_x = cursor_pos

        draw_with_emoji(
            canvas,
            self.font,
            bottom_x,
            bottom_text_y,
            self.bottom_color,
            self.bottom_text,
            emoji_y=bottom_emoji_y,
        )

        # Report cursor at the bottom-row's right edge so `_swap_and_scroll`
        # knows whether to scroll, and where to stop.
        return canvas, cursor_pos + self._bottom_width + self.padding
