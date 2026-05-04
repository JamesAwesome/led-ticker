"""Two-row widget for tall LED canvases (mainly the Pi 5 bigsign).

Renders TWO independent text strings on the same canvas:
- Top row stays at a fixed position (held)
- Bottom row scrolls left when its content overflows the canvas width

Best in `swap` mode: each `TwoRowMessage` is its own display unit. The
top-row string is meant for a stable identifier (handle, headline, brand
tag) and the bottom row for promotional copy that can be longer than
the canvas width.

Layout: by default the widget splits `canvas.height` 50/50 between top
and bottom; each row's baseline is centered within its band. Override
the split with `top_row_height = N` (logical rows) to give the bottom
a larger band for a bigger font:

  canvas.height = 16, top_row_height = None  →  top: 8 rows, bottom: 8 rows
  canvas.height = 16, top_row_height = 4     →  top: 4 rows, bottom: 12 rows
  canvas.height = 16, top_row_height = 6     →  top: 6 rows, bottom: 10 rows

The asymmetric mode is the path to "small tag on top + larger marquee
below" — pair `top_row_height = 4` with FONT_SMALL on top + Beloved
Sans Bold @ ~22 on the bottom row.

**Hard ceiling**: `canvas.height * scale ≤ panel_h_real`. On bigsign
(scale=4, panel=64 real rows) the cap is `content_height = 16`.
Higher values overflow the wrapper into negative `_y_offset`
territory; rows near the top/bottom logical edges clip silently.
This is most visible with hi-res `:instagram:` etc. emoji where 4-8
real px of the sprite get cut off at the panel edge. For per-row
breathing room, prefer `text_y_offset` on TickerMessage or a smaller
`font_size` instead of over-spec'ing `content_height`.

Caller controls per-row horizontal alignment via `top_align` and
`bottom_align` (`"left"`, `"center"`, `"right"`). Both default to
`"center"` for visual symmetry. The bottom row's alignment only takes
effect when the text fits without scrolling — if it overflows, the
framework scrolls it left regardless.

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


def _row_layout(
    canvas: Canvas,
    font: Font,
    band_height: int,
    band_offset: int,
) -> tuple[int, int]:
    """Return (text_baseline_y, emoji_top_y) for one row's band.

    `band_height` is the number of logical rows allocated to this row;
    `band_offset` is the logical y of the band's top edge. With a
    50/50 split on a 16-row canvas these are (8, 0) for top and
    (8, 8) for bottom. With an asymmetric `top_row_height = 4`, top
    is (4, 0) and bottom is (12, 4).

    Builds a virtual canvas the size of the band so `compute_baseline`
    centers the glyph correctly within it, then offsets by
    `band_offset`. Inherits `canvas.scale` so hi-res math (real →
    logical via scale) lands in the right units. The emoji top is
    centered on an `_EMOJI_ROW_CAP`-tall sub-band so 8-px emoji
    coexist with any text size; the cap independent of band height.
    """
    emoji_y = (band_height - _EMOJI_ROW_CAP) // 2 + band_offset
    band_canvas = SimpleNamespace(height=band_height, scale=getattr(canvas, "scale", 1))
    baseline = compute_baseline(font, band_canvas, valign="center")
    text_baseline = baseline + band_offset
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
    # Per-row font overrides. Default `None` falls back to `font`, so
    # legacy configs that set only `font` keep working unchanged. Set
    # `top_font` and/or `bottom_font` in TOML for split fonts (e.g.
    # bold handle on top + lighter promo line below).
    top_font: Font | None = attrs.field(default=None, kw_only=True)
    bottom_font: Font | None = attrs.field(default=None, kw_only=True)
    top_color: Color = attrs.Factory(lambda: DEFAULT_COLOR)
    bottom_color: Color = attrs.Factory(lambda: DEFAULT_COLOR)
    bg_color: Color | None = attrs.field(default=None, kw_only=True)
    top_bg_color: Color | None = attrs.field(default=None, kw_only=True)
    bottom_bg_color: Color | None = attrs.field(default=None, kw_only=True)
    # Horizontal alignment per row: "left", "center", or "right". The
    # bottom row's alignment only matters when its text fits — when it
    # overflows, the framework scrolls it from cursor_pos regardless.
    top_align: str = "center"
    bottom_align: str = "center"
    padding: int = 6
    # Backwards-compat: top_center=True is the same as top_align="center".
    # If you set top_center=False, top_align="left" is used (legacy default).
    top_center: bool | None = None
    # Asymmetric row split. Default `None` means 50/50 — top and bottom
    # each get `canvas.height // 2` logical rows. Override with an int
    # to give the top a different (typically smaller) band so the
    # bottom can fit a larger font. E.g. `top_row_height = 4` on a
    # 16-row canvas leaves 12 rows for the bottom — enough room for
    # Beloved Sans Bold @ ~22 (line_height ~10 logical) on the bottom
    # row while the top stays compact for a 5×8 BDF tag.
    top_row_height: int | None = attrs.field(default=None, kw_only=True)

    _top_width: int = attrs.field(init=False, default=-1)
    _bottom_width: int = attrs.field(init=False, default=-1)

    def __attrs_post_init__(self) -> None:
        if self.top_center is False:
            self.top_align = "left"
        elif self.top_center is True:
            self.top_align = "center"
        if self.top_row_height is not None and self.top_row_height <= 0:
            raise ValueError(
                f"top_row_height must be > 0; got {self.top_row_height!r}. "
                f"Drop the field or set None to use the default 50/50 split."
            )

    def _font_for_row(self, row_index: int) -> Font:
        """Resolve the font for a row, falling back to `self.font`."""
        if row_index == 0:
            return self.top_font if self.top_font is not None else self.font
        return self.bottom_font if self.bottom_font is not None else self.font

    def draw(self, canvas: Canvas, cursor_pos: int = 0, **kwargs: Any) -> DrawResult:
        del kwargs  # widget is meant for swap mode; y_offset/transitions ignored

        canvas_height = getattr(canvas, "height", 16)

        # Compute the per-row band heights. Default 50/50; user can
        # override `top_row_height` for an asymmetric split (e.g. small
        # tag on top + larger marquee below). Validate the override
        # leaves at least one row for the bottom.
        if self.top_row_height is None:
            top_h = canvas_height // 2
        else:
            if self.top_row_height >= canvas_height:
                raise ValueError(
                    f"top_row_height={self.top_row_height} leaves no room "
                    f"for the bottom row on a {canvas_height}-tall canvas. "
                    f"Must be < canvas.height (current = {canvas_height})."
                )
            top_h = self.top_row_height
        bottom_h = canvas_height - top_h

        top_font = self._font_for_row(0)
        bottom_font = self._font_for_row(1)

        # Validate each row's font fits within its band (logical units).
        # For BDF the metric is logical px; for HiresFont it's real px and
        # we ceil-divide by canvas.scale to compare in logical units.
        # Tolerate non-int `scale` (Mock canvases in tests, real
        # RGBMatrix canvases without scale) as scale=1.
        scale_attr = getattr(canvas, "scale", 1)
        scale = scale_attr if isinstance(scale_attr, int) and scale_attr >= 1 else 1
        for row_label, row_font, band_h in (
            ("top", top_font, top_h),
            ("bottom", bottom_font, bottom_h),
        ):
            font_lh = font_line_height(row_font)
            font_lh_logical = (
                -(-font_lh // scale) if isinstance(row_font, _HiresFont) else font_lh
            )
            if font_lh_logical > band_h:
                raise ValueError(
                    f"{row_label} font line-height ({font_lh_logical} logical "
                    f"rows) exceeds the per-row band ({band_h} rows on a "
                    f"{canvas_height}-tall canvas). Pick a smaller font_size, "
                    f"increase the section's content_height, adjust "
                    f"top_row_height for an asymmetric split, or use a BDF "
                    f"alias (5x8, 6x12)."
                )

        if self.top_bg_color is not None:
            fill_band(canvas, 0, top_h, self.top_bg_color)
        if self.bottom_bg_color is not None:
            fill_band(canvas, top_h, canvas_height, self.bottom_bg_color)

        top_text_y, top_emoji_y = _row_layout(
            canvas, top_font, band_height=top_h, band_offset=0
        )
        bottom_text_y, bottom_emoji_y = _row_layout(
            canvas, bottom_font, band_height=bottom_h, band_offset=top_h
        )

        # Cap each row's emoji height so a hi-res sprite doesn't overflow
        # into the other row. Independent of the text font's line height.
        row_emoji_cap = _EMOJI_ROW_CAP

        # Measure widths now that we have the canvas + row cap (so hi-res
        # vs. low-res fallback matches what `draw_with_emoji` will do).
        if self._top_width < 0:
            self._top_width = measure_width(
                top_font, self.top_text, canvas, row_emoji_cap
            )
        if self._bottom_width < 0:
            self._bottom_width = measure_width(
                bottom_font, self.bottom_text, canvas, row_emoji_cap
            )

        # Top row at a fixed x — held while the bottom scrolls.
        top_x = _aligned_x(canvas.width, self._top_width, self.top_align)

        draw_with_emoji(
            canvas,
            top_font,
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
            bottom_font,
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
