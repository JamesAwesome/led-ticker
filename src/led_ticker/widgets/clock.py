"""Clock widget: current time as a held/centered text display.

format_clock is a pure, timezone-agnostic formatter (it formats an
already-localized datetime). Presets are built from datetime fields rather
than via %- strftime codes, which are a libc passthrough Python does not
guarantee — building from fields keeps preset output deterministic across
platforms. A custom format string (containing %) is passed to strftime
verbatim.

The Clock widget mirrors TickerCountdown.draw: it recomputes the time each
draw() (the engine's _hold_ticks redraws held widgets every 50ms tick, so the
display stays current with no special mechanism), then dispatches through the
shared text-render helpers so font_color / font / bg_color / border behave
exactly as on the message widget.
"""

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import attrs

from led_ticker._types import Canvas, Color, DrawResult, Font
from led_ticker.color_providers import ColorProvider, _ConstantColor
from led_ticker.colors import DEFAULT_COLOR
from led_ticker.drawing import compute_baseline, compute_cursor, get_text_width
from led_ticker.fonts import FONT_DEFAULT
from led_ticker.text_render import draw_text, draw_text_per_char
from led_ticker.widgets import register
from led_ticker.widgets._frame_aware import FrameAwareBase


def format_clock(now: datetime, fmt: str) -> str:
    """Format `now` per `fmt`: a preset ("12h"/"24h") or a strftime template.

    A value containing "%" is treated as a strftime template. Otherwise it
    must be a known preset keyword; an unknown preset raises ValueError.
    """
    if "%" in fmt:
        return now.strftime(fmt)
    if fmt == "12h":
        hour12 = now.hour % 12 or 12
        meridiem = "AM" if now.hour < 12 else "PM"
        return f"{hour12}:{now.minute:02d} {meridiem}"
    if fmt == "24h":
        return f"{now.hour:02d}:{now.minute:02d}"
    raise ValueError(
        f"clock format {fmt!r} is not a known preset (expected '12h' or '24h') "
        "and is not a strftime template (no '%'). "
        "Use '12h', '24h', or a strftime string like '%H:%M'."
    )


def _coerce_font_color(value: Any) -> ColorProvider:
    """Wrap a raw Color in _ConstantColor so draw() can always call color_for."""
    if not hasattr(value, "color_for"):
        return _ConstantColor(value)
    return value


@register("clock")
@attrs.define
class Clock(FrameAwareBase):
    """Displays the current time. Held/centered; intended for swap-mode sections.

    `format` is a preset ("12h"/"24h") or a strftime template; `timezone` is an
    optional IANA name (default: system local). Reuses the message widget's
    text-render path for color/font/border.
    """

    format: str = "12h"
    timezone: str | None = None
    font: Font = attrs.Factory(lambda: FONT_DEFAULT)
    font_color: ColorProvider = attrs.field(
        default=attrs.Factory(lambda: DEFAULT_COLOR),
        converter=_coerce_font_color,
    )
    bg_color: Color | None = attrs.field(default=None, kw_only=True)
    center: bool = True
    padding: int = 6
    # Optional perimeter border — same contract as TickerMessage.border;
    # declaring the field satisfies factories' border-type gate.
    border: Any | None = attrs.field(default=None, kw_only=True)
    _baseline_y: int = attrs.field(init=False, default=-1)

    @classmethod
    def validate_config(cls, cfg: dict[str, Any]) -> list[str]:
        """Value-level checks run at config load (factories._run_validate_config).
        Unknown FIELD names are caught generically elsewhere; this checks values."""
        errors: list[str] = []
        fmt = cfg.get("format", "12h")
        if isinstance(fmt, str) and "%" not in fmt and fmt not in ("12h", "24h"):
            errors.append(
                f"format {fmt!r} is not a known preset ('12h'/'24h') or a "
                "strftime template (no '%')"
            )
        tz = cfg.get("timezone")
        if tz is not None:
            try:
                ZoneInfo(tz)
            except ZoneInfoNotFoundError, ValueError:
                errors.append(f"timezone {tz!r} is not a valid IANA timezone name")
        return errors

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

        tz = ZoneInfo(self.timezone) if self.timezone else None
        now = datetime.now(tz)
        text = format_clock(now, self.format)

        content_width = get_text_width(self.font, text, padding=0, canvas=canvas)
        cursor_pos, end_padding = compute_cursor(
            canvas.width, content_width, cursor_pos, self.padding, center=self.center
        )

        if self._baseline_y < 0:
            self._baseline_y = compute_baseline(self.font, canvas, valign="center")
        baseline_y = self._baseline_y

        # Paint border BEFORE text — same contract as TickerMessage and
        # TickerCountdown. Border reads its per-effect counter via
        # frame_for("border") so transitions freeze and visit-resets honor
        # restart_on_visit.
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
