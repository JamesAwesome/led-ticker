"""Two-row widget for tall LED canvases (mainly the Pi 5 bigsign).

Renders TWO independent text strings on the same canvas:
- Top row stays at a fixed position (held)
- Bottom row scrolls left when its content overflows the canvas width

Best in `swap` mode: each `TwoRowMessage` is its own display unit. The
top-row string is meant for a stable identifier (handle, headline, brand
tag) and the bottom row for promotional copy that can be longer than
the canvas width.

Layout (assumes a 16-tall logical canvas — the standard ScaledCanvas
content_height):

  rows  0..7   top row       (text baseline y=7,  emoji top y=0)
  rows  8..15  bottom row    (text baseline y=15, emoji top y=8)

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

# Per-row baselines/emoji-top for a 16-tall logical canvas split in half.
# 5x8 fonts (FONT_SMALL) fit in 8-pixel rows with no overlap.
_TOP_TEXT_Y = 7
_TOP_EMOJI_Y = 0
_BOTTOM_TEXT_Y = 15
_BOTTOM_EMOJI_Y = 8


@register("two_row")
@attrs.define
class TwoRowMessage:
    """Two-row display: held top, scrolling bottom."""

    top_text: str
    bottom_text: str
    font: Font = attrs.Factory(lambda: FONT_SMALL)
    top_color: Color = attrs.Factory(lambda: DEFAULT_COLOR)
    bottom_color: Color = attrs.Factory(lambda: DEFAULT_COLOR)
    top_center: bool = True
    padding: int = 6

    _top_width: int = attrs.field(init=False, default=-1)
    _bottom_width: int = attrs.field(init=False, default=-1)

    def _ensure_widths(self) -> None:
        if self._top_width < 0:
            self._top_width = measure_width(self.font, self.top_text)
        if self._bottom_width < 0:
            self._bottom_width = measure_width(self.font, self.bottom_text)

    def draw(self, canvas: Canvas, cursor_pos: int = 0, **kwargs: Any) -> DrawResult:
        del kwargs  # widget is meant for swap mode; y_offset/transitions ignored
        self._ensure_widths()

        # Top row at a fixed x — held while the bottom scrolls.
        if self.top_center and self._top_width <= canvas.width:
            top_x = (canvas.width - self._top_width) // 2
        else:
            top_x = 0  # left-align if it doesn't fit (will clip at right edge)

        draw_with_emoji(
            canvas,
            self.font,
            top_x,
            _TOP_TEXT_Y,
            self.top_color,
            self.top_text,
            emoji_y=_TOP_EMOJI_Y,
        )

        # Bottom row scrolls — start at the caller-supplied cursor_pos.
        draw_with_emoji(
            canvas,
            self.font,
            cursor_pos,
            _BOTTOM_TEXT_Y,
            self.bottom_color,
            self.bottom_text,
            emoji_y=_BOTTOM_EMOJI_Y,
        )

        # Report cursor at the bottom-row's right edge so `_swap_and_scroll`
        # knows whether to scroll, and where to stop.
        return canvas, cursor_pos + self._bottom_width + self.padding
