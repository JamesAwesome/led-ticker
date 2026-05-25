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
from led_ticker.text_render import draw_text, draw_text_per_char
from led_ticker.widgets import register
from led_ticker.widgets._frame_aware import _FrameAware


def _coerce_font_color(value: Any) -> ColorProvider:
    """Coerce a raw Color or ColorProvider to a ColorProvider.

    Wraps ``graphics.Color`` in ``_ConstantColor`` so ``draw()`` can
    always call ``provider.color_for(...)``.  Handles direct construction
    (test paths, MLB widget building TickerMessages with
    ``font_color=Color(...)``) as well as the already-coerced TOML path.
    """
    if not hasattr(value, "color_for"):
        return _ConstantColor(value)
    return value


@register("message")
@attrs.define
class TickerMessage(_FrameAware):
    """A static text message for the LED display."""

    text: str
    font: Font = attrs.Factory(lambda: FONT_DEFAULT)
    font_color: ColorProvider = attrs.field(
        default=attrs.Factory(lambda: DEFAULT_COLOR),
        converter=_coerce_font_color,
    )
    bg_color: Color | None = attrs.field(default=None, kw_only=True)
    center: bool = True
    padding: int = 6
    animation: Any | None = attrs.field(default=None, kw_only=True)
    # Optional perimeter border effect (rainbow chase, constant color,
    # etc.). When set, paints a 1-px ring around the panel perimeter
    # at PHYSICAL resolution (bypasses ScaledCanvas block expansion)
    # before the text is drawn. None = no border (default behavior).
    # The widget passes `self.frame_for("border")` so the effect's
    # per-effect counter advances independently — transitions freeze
    # the chase and visit-resets honor `restart_on_visit`. See
    # `borders.py` for available effects.
    border: Any | None = attrs.field(default=None, kw_only=True)
    _content_width: int = attrs.field(init=False, default=-1)
    _has_emoji: bool = attrs.field(init=False, default=False)
    _baseline_y: int = attrs.field(init=False, default=-1)

    def __attrs_post_init__(self) -> None:
        self._has_emoji = bool(EMOJI_PATTERN.search(self.text))

    def draw(
        self,
        canvas: Canvas,
        cursor_pos: int = 0,
        *,
        y_offset: int = 0,
        font_color: Any = None,
    ) -> DrawResult:
        # Allow callers to override font_color, but coerce raw Color to
        # provider for uniform handling below.
        if font_color is not None and not hasattr(font_color, "color_for"):
            font_color = _ConstantColor(font_color)
        provider: ColorProvider = font_color or self.font_color

        # If animation is set, ask it for the slice. Animations don't
        # currently override cursor position (Bounce was removed); if a
        # future animation needs that, re-add the override branch.
        full_text = self.text
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
                self.frame_for("animation"),
                full_text,
                canvas.width,
                self._content_width,
            )
            visible_text = anim_frame.visible_text
        else:
            visible_text = full_text

        if self._content_width < 0:
            if self._has_emoji:
                from led_ticker.pixel_emoji import measure_width

                self._content_width = measure_width(
                    self.font,
                    self.text,
                    canvas,
                )
            else:
                self._content_width = get_text_width(
                    self.font, self.text, padding=0, canvas=canvas
                )
        content_width = self._content_width
        cursor_pos, end_padding = compute_cursor(
            canvas.width, content_width, cursor_pos, self.padding, self.center
        )
        # Capture the start position BEFORE the draw_* branches mutate
        # cursor_pos. Used below to recompute the returned cursor_pos
        # against full content_width when an animation is sliced
        # `visible_text` shorter than the full message.
        start_pos = cursor_pos

        if self._baseline_y < 0:
            self._baseline_y = compute_baseline(self.font, canvas, valign="center")
        baseline_y = self._baseline_y

        # Paint border BEFORE text so text overlaps the border on
        # collision (border frames the panel; text floats inside).
        # Reads its per-effect counter via `frame_for("border")` for
        # animation — transitions freeze it (no chase phase drift)
        # and visit resets honor `restart_on_visit`. Painted at
        # physical resolution so a 1-px border on bigsign is 1 LED,
        # not a 4×4 block.
        if self.border is not None:
            self.border.paint(canvas, self.frame_for("border"))

        if self._has_emoji:
            from led_ticker.pixel_emoji import count_text_chars, draw_with_emoji

            # Per-char providers (rainbow/gradient) survive emoji
            # segments: draw_with_emoji takes the provider directly,
            # renders sprites for emoji slugs, and runs the per-char
            # path on text segments — char_index advances continuously
            # across segments so the rainbow sweep doesn't reset at
            # each :slug:. `total_chars` is anchored to the FULL
            # message's text-char count (excluding emoji slugs) so
            # typewriter mid-cycle doesn't shift each char's hue as
            # more chars reveal — char N's hue at frame=t is the same
            # hue char N will have when typewriter completes. Mirrors
            # the image-widget contract in `_BaseImageWidget._draw_text`.
            cursor_pos += draw_with_emoji(
                canvas,
                self.font,
                cursor_pos,
                baseline_y,
                provider,
                visible_text,
                y_offset=y_offset,
                frame=self.frame_for("font_color"),
                total_chars=count_text_chars(self.text),
            )
        elif provider.per_char:
            # Per-char rendering: iterate visible_text, draw each char
            # with its own color (rainbow / gradient). The shared
            # `draw_text_per_char` helper handles the HiresFont
            # real-pixel cursor tracking that avoids the per-char
            # ceil-divide drift. `total_chars=len(self.text)`
            # anchors each char's hue to its position in the FULL
            # text — typewriter mid-cycle reveals char N at the
            # hue char N will have at completion, not a hue
            # compressed to the visible slice. Mirrors the image-
            # widget contract in `_BaseImageWidget._draw_text`.
            cursor_pos += draw_text_per_char(
                canvas,
                self.font,
                cursor_pos,
                baseline_y + y_offset,
                visible_text,
                lambda idx, total: provider.color_for(
                    self.frame_for("font_color"), idx, total
                ),
                total_chars=len(self.text),
            )
        else:
            color = provider.color_for(
                self.frame_for("font_color"), 0, len(visible_text)
            )
            cursor_pos += draw_text(
                canvas,
                self.font,
                cursor_pos,
                baseline_y + y_offset,
                color,
                visible_text,
            )
        cursor_pos += end_padding

        # When an animation is sliced (typewriter at frame=0 shows just
        # "R"), the engine in `_swap_and_scroll` checks
        # `cursor_pos > canvas.width` ONCE to decide hold vs scroll.
        # If cursor_pos reflects only the slice, the engine picks the
        # held-text path and the message overflows the right edge
        # without ever scrolling. Override cursor_pos to reflect FULL
        # content width so the engine sees the eventual overflow and
        # picks the scroll path; typewriter then completes during the
        # pre-scroll hold and the scroll runs afterwards.
        if self.animation is not None:
            cursor_pos = start_pos + content_width + end_padding

        return canvas, cursor_pos


@register("countdown")
@attrs.define
class TickerCountdown(_FrameAware):
    """A countdown to a specific date."""

    text: str
    countdown_date: date
    font: Font = attrs.Factory(lambda: FONT_DEFAULT)
    font_color: ColorProvider = attrs.field(
        default=attrs.Factory(lambda: DEFAULT_COLOR),
        converter=_coerce_font_color,
    )
    bg_color: Color | None = attrs.field(default=None, kw_only=True)
    center: bool = True
    padding: int = 6
    # Optional perimeter border effect — same contract as
    # `TickerMessage.border` (see borders.py). Paints before text at
    # physical resolution; advances on its per-effect counter
    # (read via `frame_for("border")`).
    border: Any | None = attrs.field(default=None, kw_only=True)
    _baseline_y: int = attrs.field(init=False, default=-1)

    def draw(
        self,
        canvas: Canvas,
        cursor_pos: int = 0,
        *,
        y_offset: int = 0,
        font_color: Any = None,
    ) -> DrawResult:
        # Allow callers to override font_color, but coerce raw Color to
        # provider for uniform handling below.
        if font_color is not None and not hasattr(font_color, "color_for"):
            font_color = _ConstantColor(font_color)
        provider: ColorProvider = font_color or self.font_color

        today = date.today()
        days_until = (self.countdown_date - today).days
        text = f"{self.text}: {days_until}"

        content_width = get_text_width(self.font, text, padding=0, canvas=canvas)
        cursor_pos, end_padding = compute_cursor(
            canvas.width, content_width, cursor_pos, self.padding, self.center
        )

        if self._baseline_y < 0:
            self._baseline_y = compute_baseline(self.font, canvas, valign="center")
        baseline_y = self._baseline_y

        # Paint border BEFORE text — same contract as `TickerMessage`.
        # Border frames the panel; text floats inside. Border reads
        # its per-effect counter via `frame_for("border")` so
        # transitions freeze and visit-resets honor `restart_on_visit`.
        if self.border is not None:
            self.border.paint(canvas, self.frame_for("border"))

        if provider.per_char:
            # Per-char provider on plain text: iterate chars so rainbow
            # / gradient render with per-character hue offsets. Mirrors
            # `TickerMessage.draw`'s per-char branch.
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
