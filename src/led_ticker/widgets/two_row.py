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

from types import SimpleNamespace
from typing import Any

import attrs

from led_ticker._types import Canvas, Color, DrawResult, Font
from led_ticker.colors import DEFAULT_COLOR
from led_ticker.drawing import compute_baseline
from led_ticker.fonts import FONT_SMALL, font_line_height
from led_ticker.fonts.hires_loader import HiresFont as _HiresFont
from led_ticker.pixel_emoji import draw_with_emoji, measure_width
from led_ticker.widgets import register
from led_ticker.widgets._image_fit import fill_band

# Cap on emoji vertical size per row. Inline emoji sprites are 8×8
# logical (low-res) or up to 32×32 real (hi-res). We cap at 8 logical
# rows so a hi-res sprite that would overflow the row band falls back
# to the 8×8 low-res sprite (`pixel_emoji.draw_with_emoji` honors
# `max_emoji_height`). Independent of the text font's line height.
_EMOJI_ROW_CAP = 8


def _row_layout(canvas: Canvas, font: Font, row_index: int) -> tuple[int, int]:
    """Return (text_baseline_y, emoji_top_y) for the given row index.

    Splits ``canvas.height`` into two equal halves and asks
    ``compute_baseline`` for the centered baseline within each half —
    works uniformly for BDF and HiresFont. The emoji top is centered
    on an ``_EMOJI_ROW_CAP``-tall band inside the same half (so emoji
    coexist with text of any size). Any extra canvas height becomes
    a gap between the rows.
    """
    half = canvas.height // 2
    emoji_y = (half - _EMOJI_ROW_CAP) // 2 + row_index * half
    # Build a half-height "virtual canvas" for compute_baseline so it
    # centers the glyph in this row's band. Inherit canvas.scale so
    # hi-res math (real → logical via scale) lands in the same units
    # the renderer expects.
    half_canvas = SimpleNamespace(height=half, scale=getattr(canvas, "scale", 1))
    baseline = compute_baseline(font, half_canvas, valign="center")
    text_baseline = baseline + row_index * half
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
    bg_color: Color | None = attrs.field(default=None, kw_only=True)
    top_bg_color: Color | None = attrs.field(default=None, kw_only=True)
    bottom_bg_color: Color | None = attrs.field(default=None, kw_only=True)
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

    def draw(self, canvas: Canvas, cursor_pos: int = 0, **kwargs: Any) -> DrawResult:
        del kwargs  # widget is meant for swap mode; y_offset/transitions ignored

        canvas_height = getattr(canvas, "height", 16)
        half = canvas_height // 2

        # Validate the font fits within a single row band (logical units).
        # For BDF the metric is logical px; for HiresFont it's real px and
        # we ceil-divide by canvas.scale to compare in logical units.
        # Tolerate non-int `scale` (Mock canvases in tests, real
        # RGBMatrix canvases without scale) as scale=1.
        scale_attr = getattr(canvas, "scale", 1)
        scale = scale_attr if isinstance(scale_attr, int) and scale_attr >= 1 else 1
        font_lh = font_line_height(self.font)
        font_lh_logical = (
            -(-font_lh // scale) if isinstance(self.font, _HiresFont) else font_lh
        )
        if font_lh_logical > half:
            raise ValueError(
                f"font line-height ({font_lh_logical} logical rows) exceeds "
                f"the per-row band ({half} rows on a {canvas_height}-tall "
                f"canvas). Pick a smaller font_size, increase the section's "
                f"content_height, or use a BDF alias (5x8, 6x12)."
            )

        mid = canvas_height // 2
        if self.top_bg_color is not None:
            fill_band(canvas, 0, mid, self.top_bg_color)
        if self.bottom_bg_color is not None:
            fill_band(canvas, mid, canvas_height, self.bottom_bg_color)

        top_text_y, top_emoji_y = _row_layout(canvas, self.font, row_index=0)
        bottom_text_y, bottom_emoji_y = _row_layout(canvas, self.font, row_index=1)

        # Cap each row's emoji height so a hi-res sprite doesn't overflow
        # into the other row. Independent of the text font's line height.
        row_emoji_cap = _EMOJI_ROW_CAP

        # Measure widths now that we have the canvas + row cap (so hi-res
        # vs. low-res fallback matches what `draw_with_emoji` will do).
        if self._top_width < 0:
            self._top_width = measure_width(
                self.font, self.top_text, canvas, row_emoji_cap
            )
        if self._bottom_width < 0:
            self._bottom_width = measure_width(
                self.font, self.bottom_text, canvas, row_emoji_cap
            )

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
            max_emoji_height=row_emoji_cap,
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
            max_emoji_height=row_emoji_cap,
        )

        # Report cursor at the bottom-row's right edge so `_swap_and_scroll`
        # knows whether to scroll, and where to stop.
        return canvas, cursor_pos + self._bottom_width + self.padding
