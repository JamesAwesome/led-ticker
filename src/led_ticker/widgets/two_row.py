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

from typing import Any

import attrs

from led_ticker._types import Canvas, Color, DrawResult, Font
from led_ticker.color_providers import ColorProvider, _ConstantColor
from led_ticker.colors import DEFAULT_COLOR
from led_ticker.drawing import safe_scale
from led_ticker.fonts import FONT_SMALL, font_line_height_logical
from led_ticker.pixel_emoji import draw_with_emoji, measure_width
from led_ticker.widgets import register
from led_ticker.widgets._frame_aware import _FrameAware
from led_ticker.widgets._image_fit import fill_band
from led_ticker.widgets._row_layout import (
    EMOJI_ROW_CAP,
    aligned_x,
    resolve_band_heights,
    row_layout,
)

# Layout primitives moved to `widgets/_row_layout.py` so the same
# helpers serve both this widget and the two-row text-overlay path
# on `_BaseImageWidget`. Re-bind aliases for back-compat with any
# tests that import the underscore names from this module.
_EMOJI_ROW_CAP = EMOJI_ROW_CAP
_row_layout = row_layout
_aligned_x = aligned_x


@register("two_row")
@attrs.define
class TwoRowMessage(_FrameAware):
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
    top_color: Color | ColorProvider = attrs.Factory(lambda: DEFAULT_COLOR)
    bottom_color: Color | ColorProvider = attrs.Factory(lambda: DEFAULT_COLOR)
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
    # Per-row text and emoji nudges in logical rows. Default 0 keeps
    # them at their computed positions. Negative shifts up (text
    # ascender may clip the panel edge), positive shifts down
    # (descender may bleed into the next band's space). Set
    # text + emoji to the same value to shift the entire row
    # together, or use them independently to tune emoji-text vertical
    # alignment when the emoji sprite is taller than the band.
    top_text_y_offset: int = attrs.field(default=0, kw_only=True)
    bottom_text_y_offset: int = attrs.field(default=0, kw_only=True)
    top_emoji_y_offset: int = attrs.field(default=0, kw_only=True)
    bottom_emoji_y_offset: int = attrs.field(default=0, kw_only=True)

    # Optional perimeter border effect — same contract as
    # `TickerMessage.border` (see borders.py). Paints before either
    # row's text at PHYSICAL panel resolution (bypasses ScaledCanvas
    # block expansion via `unwrap_to_real`), so a 1-px border on
    # bigsign at scale=2 traces the actual 256x64 panel edge — not
    # the 128x32 logical canvas edge. Border frames the SIGN, text
    # floats inside. Reads `_frame_count` for animation; transitions
    # freeze the chase via `pause_frame`.
    border: Any | None = attrs.field(default=None, kw_only=True)

    _top_width: int = attrs.field(init=False, default=-1)
    _bottom_width: int = attrs.field(init=False, default=-1)

    def __attrs_post_init__(self) -> None:
        # Wrap raw Color → _ConstantColor for uniform provider dispatch in draw().
        if not hasattr(self.top_color, "color_for"):
            self.top_color = _ConstantColor(self.top_color)
        if not hasattr(self.bottom_color, "color_for"):
            self.bottom_color = _ConstantColor(self.bottom_color)
        if self.top_center is not None:
            # `top_center` is a backwards-compat alias for `top_align`. Old
            # configs used `top_center=True/False` before `top_align` existed.
            # Warn so existing setups still work but the canonical knob
            # surfaces. When both are set, `top_center` silently overrides
            # `top_align` — preserving prior behavior, but the warning
            # makes the override visible.
            import warnings

            warnings.warn(
                "TwoRowMessage `top_center` is deprecated; use "
                "`top_align='center'` (or 'left'). For now `top_center` "
                "still overrides `top_align` if both are set.",
                DeprecationWarning,
                stacklevel=2,
            )
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

        top_h, bottom_h = resolve_band_heights(canvas_height, self.top_row_height)

        top_font = self._font_for_row(0)
        bottom_font = self._font_for_row(1)

        # Validate each row's font fits within its band (logical units).
        # `font_line_height_logical` handles the BDF-vs-HiresFont
        # branch (BDF returns logical px, HiresFont ceil-divs by scale).
        scale = safe_scale(canvas)
        for row_label, row_font, band_h in (
            ("top", top_font, top_h),
            ("bottom", bottom_font, bottom_h),
        ):
            font_lh_logical = font_line_height_logical(row_font, scale)
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
        # Apply per-row text + emoji nudges. Negative shifts up
        # (may clip the panel edge), positive shifts down. Setting
        # text + emoji offsets to the same value moves the whole row
        # together; using them independently tunes emoji-text
        # vertical alignment when the emoji sprite is taller than
        # the band.
        top_text_y += self.top_text_y_offset
        bottom_text_y += self.bottom_text_y_offset
        top_emoji_y += self.top_emoji_y_offset
        bottom_emoji_y += self.bottom_emoji_y_offset

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

        # Pass providers (not materialized colors) to draw_with_emoji
        # so per-char effects (rainbow / gradient) sweep continuously
        # across emoji boundaries within each row. draw_with_emoji
        # detects ColorProvider via duck-typing on `color_for` and
        # iterates per-char text segments when `provider.per_char` is
        # True; otherwise it materializes a single Color per segment.

        # Paint border BEFORE either row's text so text overlaps the
        # border on collision (border frames the panel; text floats
        # inside). Same contract as `TickerMessage.border`. Border
        # paints at PHYSICAL panel resolution via `unwrap_to_real`,
        # so at scale=2 (logical canvas 128x32) the border traces
        # the real 256x64 panel edge — frames the SIGN, not the
        # logical canvas.
        if self.border is not None:
            self.border.paint(canvas, self._frame_count)

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
            frame=self._frame_count,
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
            frame=self._frame_count,
        )

        # Report cursor at the bottom-row's right edge so `_swap_and_scroll`
        # knows whether to scroll, and where to stop.
        return canvas, cursor_pos + self._bottom_width + self.padding
