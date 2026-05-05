"""Static text widgets: TickerMessage and TickerCountdown."""

from __future__ import annotations

from datetime import date
from typing import Any

import attrs

from led_ticker._types import Canvas, Color, DrawResult, Font
from led_ticker.color_providers import ColorProvider, _ConstantColor
from led_ticker.colors import DEFAULT_COLOR
from led_ticker.drawing import compute_baseline, compute_cursor, get_text_width
from led_ticker.fonts import FONT_DEFAULT
from led_ticker.pixel_emoji import EMOJI_PATTERN
from led_ticker.text_render import draw_text
from led_ticker.widgets import register
from led_ticker.widgets._frame_aware import _FrameAware


@register("message")
@attrs.define
class TickerMessage(_FrameAware):
    """A static text message for the LED display."""

    message: str
    font: Font = attrs.Factory(lambda: FONT_DEFAULT)
    font_color: Color | ColorProvider = attrs.Factory(lambda: DEFAULT_COLOR)
    bg_color: Color | None = attrs.field(default=None, kw_only=True)
    center: bool = True
    padding: int = 6
    animation: Any | None = attrs.field(default=None, kw_only=True)
    _content_width: int = attrs.field(init=False, default=-1)
    _has_emoji: bool = attrs.field(init=False, default=False)

    def __attrs_post_init__(self) -> None:
        # Coerce raw graphics.Color into _ConstantColor so draw() can
        # uniformly call self.font_color.color_for(...). _build_widget
        # already does this for TOML configs; this handles direct
        # construction (test paths, MLB widget building TickerMessages
        # programmatically with font_color=Color(...)).
        if not hasattr(self.font_color, "color_for"):
            self.font_color = _ConstantColor(self.font_color)
        self._has_emoji = bool(EMOJI_PATTERN.search(self.message))

    def draw(self, canvas: Canvas, cursor_pos: int = 0, **kwargs: Any) -> DrawResult:
        # Allow callers to override font_color via kwargs (legacy path),
        # but coerce raw Color to provider for uniform handling below.
        provider_kwarg = kwargs.get("font_color")
        if provider_kwarg is not None and not hasattr(provider_kwarg, "color_for"):
            provider_kwarg = _ConstantColor(provider_kwarg)
        provider: ColorProvider = provider_kwarg or self.font_color

        y_offset: int = kwargs.get("y_offset", 0)

        # If animation is set, ask it for the slice + cursor override.
        full_text = self.message
        if self.animation is not None:
            if self._content_width < 0:
                # Measure once for animation use; emoji path measures below.
                if self._has_emoji:
                    from led_ticker.pixel_emoji import measure_width

                    self._content_width = measure_width(self.font, full_text, canvas)
                else:
                    self._content_width = get_text_width(
                        self.font, full_text, padding=0, canvas=canvas
                    )
            anim_frame = self.animation.frame_for(
                self._frame_count, full_text, canvas.width, self._content_width
            )
            visible_text = anim_frame.visible_text
            if anim_frame.cursor_override is not None:
                cursor_pos = anim_frame.cursor_override
                # Skip compute_cursor — animation owns the position.
                baseline_y = compute_baseline(self.font, canvas, valign="center")
                color = provider.color_for(self._frame_count, 0, len(visible_text))
                if self._has_emoji:
                    from led_ticker.pixel_emoji import draw_with_emoji

                    cursor_pos += draw_with_emoji(
                        canvas,
                        self.font,
                        cursor_pos,
                        baseline_y,
                        color,
                        visible_text,
                        y_offset=y_offset,
                    )
                else:
                    cursor_pos += draw_text(
                        canvas,
                        self.font,
                        cursor_pos,
                        baseline_y + y_offset,
                        color,
                        visible_text,
                    )
                return canvas, cursor_pos + self.padding
        else:
            visible_text = full_text

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

            # v1 limit: per-char providers + emoji slugs use whole-string
            # color semantics (slugs render as units, not per-char).
            color = provider.color_for(self._frame_count, 0, len(visible_text))
            cursor_pos += draw_with_emoji(
                canvas,
                self.font,
                cursor_pos,
                baseline_y,
                color,
                visible_text,
                y_offset=y_offset,
            )
        elif provider.per_char:
            # Per-char rendering: iterate visible_text, draw each char
            # with its own color (rainbow / gradient).
            x = cursor_pos
            total = len(visible_text)
            for i, char in enumerate(visible_text):
                color = provider.color_for(self._frame_count, i, total)
                x += draw_text(canvas, self.font, x, baseline_y + y_offset, color, char)
            cursor_pos = x
        else:
            color = provider.color_for(self._frame_count, 0, len(visible_text))
            cursor_pos += draw_text(
                canvas,
                self.font,
                cursor_pos,
                baseline_y + y_offset,
                color,
                visible_text,
            )
        cursor_pos += end_padding

        return canvas, cursor_pos


@register("countdown")
@attrs.define
class TickerCountdown(_FrameAware):
    """A countdown to a specific date."""

    message: str
    countdown_date: date
    font: Font = attrs.Factory(lambda: FONT_DEFAULT)
    font_color: Color | ColorProvider = attrs.Factory(lambda: DEFAULT_COLOR)
    bg_color: Color | None = attrs.field(default=None, kw_only=True)
    center: bool = True
    padding: int = 6

    def __attrs_post_init__(self) -> None:
        # Coerce raw graphics.Color into _ConstantColor so draw() can
        # uniformly call self.font_color.color_for(...).
        if not hasattr(self.font_color, "color_for"):
            self.font_color = _ConstantColor(self.font_color)

    def draw(self, canvas: Canvas, cursor_pos: int = 0, **kwargs: Any) -> DrawResult:
        # Allow callers to override font_color via kwargs (legacy path),
        # but coerce raw Color to provider for uniform handling below.
        provider_kwarg = kwargs.get("font_color")
        if provider_kwarg is not None and not hasattr(provider_kwarg, "color_for"):
            provider_kwarg = _ConstantColor(provider_kwarg)
        provider: ColorProvider = provider_kwarg or self.font_color

        y_offset: int = kwargs.get("y_offset", 0)

        today = date.today()
        days_until = (self.countdown_date - today).days
        text = f"{self.message}: {days_until}"

        content_width = get_text_width(self.font, text, padding=0, canvas=canvas)
        cursor_pos, end_padding = compute_cursor(
            canvas.width, content_width, cursor_pos, self.padding, self.center
        )

        baseline_y = compute_baseline(self.font, canvas, valign="center")
        color = provider.color_for(self._frame_count, 0, len(text))
        cursor_pos += draw_text(
            canvas, self.font, cursor_pos, baseline_y + y_offset, color, text
        )
        cursor_pos += end_padding

        return canvas, cursor_pos
