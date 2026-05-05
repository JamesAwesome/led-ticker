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

        # If animation is set, ask it for the slice. Animations don't
        # currently override cursor position (Bounce was removed); if a
        # future animation needs that, re-add the override branch.
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
            #
            # HiresFont gotcha: `_draw_hires_text` returns advance in
            # logical px (ceil-divided by scale per char). Accumulating
            # those rounds up at every char and drifts past the
            # holistic `get_text_width` measurement (which ceil-divides
            # ONCE on the real-px total). The drift breaks scroll
            # detection: the widget reports cursor_pos = sum-of-ceils
            # which can be > canvas.width even though the text actually
            # fits in real px (or vice versa). Track the cursor in real
            # px for HiresFont and ceil once at the end so the returned
            # cursor_pos matches the holistic measurement.
            #
            # Gradient + Typewriter interaction: `total = len(visible_text)`
            # uses the slice length, so a Gradient compresses on the
            # first frame and stretches as Typewriter reveals more chars.
            # Final state matches the full-text gradient.
            from led_ticker.fonts.hires_loader import HiresFont as _HiresFont

            total = len(visible_text)
            scale = getattr(canvas, "scale", 1) or 1
            if isinstance(self.font, _HiresFont):
                # Track real-px cursor; convert to logical for draw_text
                # at each char. Single ceil-divide for the final return
                # value matches `get_text_width`'s rounding.
                fallback = self.font.glyphs.get("?")
                fallback_advance = fallback.advance if fallback else 0
                x_real = cursor_pos * scale
                for i, char in enumerate(visible_text):
                    color = provider.color_for(self._frame_count, i, total)
                    glyph = self.font.glyphs.get(char)
                    real_advance = glyph.advance if glyph else fallback_advance
                    x_logical = x_real // scale
                    draw_text(
                        canvas,
                        self.font,
                        x_logical,
                        baseline_y + y_offset,
                        color,
                        char,
                    )
                    x_real += real_advance
                cursor_pos = -(-x_real // scale)  # ceil-divide once
            else:
                # BDF: per-char advance is already logical (no scale-
                # dependent rounding), so the simple sum is correct.
                x = cursor_pos
                for i, char in enumerate(visible_text):
                    color = provider.color_for(self._frame_count, i, total)
                    x += draw_text(
                        canvas,
                        self.font,
                        x,
                        baseline_y + y_offset,
                        color,
                        char,
                    )
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
