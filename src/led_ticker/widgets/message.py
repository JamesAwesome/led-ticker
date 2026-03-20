"""Static text widgets: TickerMessage and TickerCountdown."""

from datetime import date

import attrs

from led_ticker._compat import require_graphics
from led_ticker.colors import DEFAULT_COLOR
from led_ticker.drawing import compute_cursor, get_text_width
from led_ticker.fonts import FONT_DEFAULT
from led_ticker.widgets import register


@register("message")
@attrs.define
class TickerMessage:
    """A static text message for the LED display."""

    message: str
    font: object = attrs.Factory(lambda: FONT_DEFAULT)
    font_color: object = attrs.Factory(lambda: DEFAULT_COLOR)
    center: bool = True
    padding: int = 6

    def draw(self, canvas, cursor_pos=0, **kwargs):
        graphics = require_graphics()
        font_color = kwargs.get("font_color") or self.font_color
        y_offset = kwargs.get("y_offset", 0)

        content_width = get_text_width(self.font, self.message, padding=0)
        cursor_pos, end_padding = compute_cursor(
            canvas.width, content_width, cursor_pos, self.padding, self.center
        )

        cursor_pos += graphics.DrawText(
            canvas, self.font, cursor_pos, 12 + y_offset, font_color, self.message
        )
        cursor_pos += end_padding

        return canvas, cursor_pos


@register("countdown")
@attrs.define
class TickerCountdown:
    """A countdown to a specific date."""

    message: str
    countdown_date: date
    font: object = attrs.Factory(lambda: FONT_DEFAULT)
    font_color: object = attrs.Factory(lambda: DEFAULT_COLOR)
    center: bool = True
    padding: int = 6

    def draw(self, canvas, cursor_pos=0, **kwargs):
        graphics = require_graphics()
        font_color = kwargs.get("font_color") or self.font_color
        y_offset = kwargs.get("y_offset", 0)

        today = date.today()
        days_until = (self.countdown_date - today).days
        text = f"{self.message}: {days_until}"

        content_width = get_text_width(self.font, text, padding=0)
        cursor_pos, end_padding = compute_cursor(
            canvas.width, content_width, cursor_pos, self.padding, self.center
        )

        cursor_pos += graphics.DrawText(
            canvas, self.font, cursor_pos, 12 + y_offset, font_color, text
        )
        cursor_pos += end_padding

        return canvas, cursor_pos
