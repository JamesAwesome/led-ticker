"""Day-count widgets: TickerCountdown (days until) and TickerCountup (days since).

Both share `_CountWidget`, which owns the full render surface (font, color
provider, border, centering — identical to the old TickerCountdown). The
subclasses differ only by their date field and the sign of `_days()`.

Out of range (countdown past its date / countup before its date) a widget
returns `should_display() == False`; the engine's `_expand_sources` drops it
from the rotation that pass (see ticker.py), so it disappears instead of
rendering a negative number.
"""

from datetime import date
from typing import Any

import attrs

from led_ticker._types import Canvas, Color, DrawResult, Font
from led_ticker.color_providers import ColorProvider, _ConstantColor
from led_ticker.colors import DEFAULT_COLOR
from led_ticker.drawing import compute_baseline, compute_cursor, get_text_width
from led_ticker.fonts import FONT_DEFAULT
from led_ticker.text_render import draw_text, draw_text_per_char
from led_ticker.widgets import register
from led_ticker.widgets._frame_aware import FrameAwareBase


def _coerce_font_color(value: Any) -> ColorProvider:
    """Coerce a raw Color or ColorProvider to a ColorProvider (wraps a raw
    graphics.Color in _ConstantColor so draw() can always call color_for)."""
    if not hasattr(value, "color_for"):
        return _ConstantColor(value)
    return value


@attrs.define
class _CountWidget(FrameAwareBase):
    """Shared base for day-count widgets. Renders `f"{text}: {days}"`; `days`
    comes from the subclass `_days()`. Subclasses add the date field + sign."""

    text: str
    font: Font = attrs.Factory(lambda: FONT_DEFAULT)
    font_color: ColorProvider = attrs.field(
        default=attrs.Factory(lambda: DEFAULT_COLOR),
        converter=_coerce_font_color,
    )
    bg_color: Color | None = attrs.field(default=None, kw_only=True)
    center: bool = True
    padding: int = 6
    # Optional perimeter border — same contract as TickerMessage.border.
    border: Any | None = attrs.field(default=None, kw_only=True)
    _baseline_y: int = attrs.field(init=False, default=-1)

    def _days(self) -> int:
        """Signed day distance from today. Subclass responsibility."""
        raise NotImplementedError

    def should_display(self) -> bool:
        """Engine visibility hook (filtered in ticker._expand_sources): a count
        widget shows only while its count is non-negative. Out of range it drops
        from the rotation."""
        return self._days() >= 0

    def draw(
        self,
        canvas: Canvas,
        cursor_pos: int = 0,
        *,
        y_offset: int = 0,
        font_color: Any = None,
    ) -> DrawResult:
        if font_color is not None and not hasattr(font_color, "color_for"):
            font_color = _ConstantColor(font_color)
        provider: ColorProvider = font_color or self.font_color

        text = f"{self.text}: {self._days()}"

        content_width = get_text_width(self.font, text, padding=0, canvas=canvas)
        cursor_pos, end_padding = compute_cursor(
            canvas.width, content_width, cursor_pos, self.padding, center=self.center
        )

        if self._baseline_y < 0:
            self._baseline_y = compute_baseline(self.font, canvas, valign="center")
        baseline_y = self._baseline_y

        if self.border is not None:
            self.border.paint(canvas, self.frame_for("border"))

        if provider.per_char:
            cursor_pos += draw_text_per_char(
                canvas,
                self.font,
                cursor_pos,
                baseline_y + y_offset,
                text,
                lambda idx, total: provider.color_for(
                    self.frame_for("font_color"), idx, total
                ),
            )
        else:
            color = provider.color_for(self.frame_for("font_color"), 0, len(text))
            cursor_pos += draw_text(
                canvas, self.font, cursor_pos, baseline_y + y_offset, color, text
            )
        cursor_pos += end_padding

        return canvas, cursor_pos


@register("countdown")
@attrs.define
class TickerCountdown(_CountWidget):
    """Days until a future date. Disappears from rotation once the date passes."""

    countdown_date: date = attrs.field(kw_only=True)

    def _days(self) -> int:
        return (self.countdown_date - date.today()).days


@register("countup")
@attrs.define
class TickerCountup(_CountWidget):
    """Days since a past date. Hidden until the date arrives, then counts up."""

    countup_date: date = attrs.field(kw_only=True)

    def _days(self) -> int:
        return (date.today() - self.countup_date).days
