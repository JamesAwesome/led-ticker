"""Static text widgets: TickerMessage and TickerCountdown."""

from __future__ import annotations

from datetime import date
from typing import Any

import attrs

from led_ticker._types import Canvas, Color, DrawResult, Font
from led_ticker.colors import DEFAULT_COLOR
from led_ticker.drawing import compute_baseline, compute_cursor, get_text_width
from led_ticker.fonts import FONT_DEFAULT
from led_ticker.pixel_emoji import EMOJI_PATTERN
from led_ticker.text_render import draw_text
from led_ticker.widgets import register


@register("message")
@attrs.define
class TickerMessage:
    """A static text message for the LED display."""

    message: str
    font: Font = attrs.Factory(lambda: FONT_DEFAULT)
    font_color: Color = attrs.Factory(lambda: DEFAULT_COLOR)
    bg_color: Color | None = attrs.field(default=None, kw_only=True)
    center: bool = True
    padding: int = 6
    animation: Any | None = attrs.field(default=None, kw_only=True)
    _content_width: int = attrs.field(init=False, default=-1)
    _has_emoji: bool = attrs.field(init=False, default=False)

    def __attrs_post_init__(self) -> None:
        self._has_emoji = bool(EMOJI_PATTERN.search(self.message))

    def draw(self, canvas: Canvas, cursor_pos: int = 0, **kwargs: Any) -> DrawResult:
        font_color = kwargs.get("font_color") or self.font_color
        y_offset: int = kwargs.get("y_offset", 0)

        if self._content_width < 0:
            if self._has_emoji:
                from led_ticker.pixel_emoji import measure_width

                self._content_width = measure_width(
                    self.font,
                    self.message,
                    canvas,
                )
            else:
                self._content_width = get_text_width(
                    self.font, self.message, padding=0, canvas=canvas
                )
        content_width = self._content_width
        cursor_pos, end_padding = compute_cursor(
            canvas.width, content_width, cursor_pos, self.padding, self.center
        )

        baseline_y = compute_baseline(self.font, canvas, valign="center")

        if self._has_emoji:
            from led_ticker.pixel_emoji import draw_with_emoji

            cursor_pos += draw_with_emoji(
                canvas,
                self.font,
                cursor_pos,
                baseline_y,
                font_color,
                self.message,
                y_offset=y_offset,
            )
        else:
            cursor_pos += draw_text(
                canvas,
                self.font,
                cursor_pos,
                baseline_y + y_offset,
                font_color,
                self.message,
            )
        cursor_pos += end_padding

        return canvas, cursor_pos


@register("countdown")
@attrs.define
class TickerCountdown:
    """A countdown to a specific date."""

    message: str
    countdown_date: date
    font: Font = attrs.Factory(lambda: FONT_DEFAULT)
    font_color: Color = attrs.Factory(lambda: DEFAULT_COLOR)
    bg_color: Color | None = attrs.field(default=None, kw_only=True)
    center: bool = True
    padding: int = 6

    def draw(self, canvas: Canvas, cursor_pos: int = 0, **kwargs: Any) -> DrawResult:
        font_color = kwargs.get("font_color") or self.font_color
        y_offset: int = kwargs.get("y_offset", 0)

        today = date.today()
        days_until = (self.countdown_date - today).days
        text = f"{self.message}: {days_until}"

        content_width = get_text_width(self.font, text, padding=0, canvas=canvas)
        cursor_pos, end_padding = compute_cursor(
            canvas.width, content_width, cursor_pos, self.padding, self.center
        )

        baseline_y = compute_baseline(self.font, canvas, valign="center")
        cursor_pos += draw_text(
            canvas, self.font, cursor_pos, baseline_y + y_offset, font_color, text
        )
        cursor_pos += end_padding

        return canvas, cursor_pos
