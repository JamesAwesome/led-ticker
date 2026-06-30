"""Shared separator rendering: one renderer for the ticker-mode circle and
the scroll-transition dot. Leaf module — must NOT import ticker/transitions.

A SeparatorSpec describes HOW a separator looks; render_separator paints it
at a logical x and returns the mark's logical width (no padding — callers add
their own). frame drives the color provider.
"""

import functools
from typing import Any

import attrs

from led_ticker._types import Canvas, ColorTuple
from led_ticker.color_providers import ColorProvider, _ConstantColor
from led_ticker.colors import RGB_WHITE
from led_ticker.scaled_canvas import ScaledCanvas, is_scaled, paint_hires

# Circle separator footprint (moved from ticker.py): 1 left pad + 8 disk + 1
# right pad = 10 logical px advance at the default size.
_CIRCLE_LOGICAL_PAD = 1
SCROLL_GAP: int = 6  # px of black on each side of the scroll dot


def _as_provider(color: Any) -> ColorProvider:
    return color if hasattr(color, "color_for") else _ConstantColor(color)


@attrs.define
class SeparatorSpec:
    kind: str  # "dot" | "circle"  (Phase 2 adds "glyph")
    color: Any = RGB_WHITE  # ColorTuple or ColorProvider; normalized on read
    size: int = 2  # dot: square side; circle: disk diameter (logical px)
    glyph: str = ""  # Phase 2
    font: Any = None  # Phase 2


# Per-site defaults reproducing today's appearance exactly.
DEFAULT_DOT_SPEC = SeparatorSpec(kind="dot", color=RGB_WHITE, size=2)
DEFAULT_CIRCLE_SPEC = SeparatorSpec(kind="circle", color=RGB_WHITE, size=8)


@functools.cache
def _build_circle_offsets(radius_physical: int) -> tuple[tuple[int, int], ...]:
    offsets: list[tuple[int, int]] = []
    r_sq = radius_physical * radius_physical
    for dy in range(-radius_physical, radius_physical + 1):
        dx_max = 0
        while (dx_max + 1) * (dx_max + 1) + dy * dy <= r_sq:
            dx_max += 1
        for dx in range(-dx_max, dx_max + 1):
            offsets.append((dx, dy))
    return tuple(offsets)  # immutable; safe to cache


def _resolve_rgb(color: Any, frame: int) -> ColorTuple:
    c = _as_provider(color).color_for(frame, 0, 1)
    if isinstance(c, tuple):
        return c
    return (c.red, c.green, c.blue)


def _render_dot(canvas: Canvas, x: int, rgb: ColorTuple, size: int) -> int:
    h = getattr(canvas, "height", 16)
    y_center = h // 2
    r, g, b = rgb
    top = -(size // 2)  # size 2 -> rows -1, 0
    for dy in range(top, size + top):
        for dx in range(size):
            px, py = x + dx, y_center + dy
            if 0 <= px < canvas.width and 0 <= py < h:
                canvas.SetPixel(px, py, r, g, b)
    return size


def _render_circle(canvas: ScaledCanvas, x: int, rgb: ColorTuple, size: int) -> int:
    radius_logical = size // 2  # size 8 -> radius 4
    r, g, b = rgb

    def _paint(real: Any, scale: int, y_offset_real: int) -> None:
        radius_physical = radius_logical * scale
        offsets = _build_circle_offsets(radius_physical)
        cx = x * scale + radius_physical
        cy = y_offset_real + (canvas.height * scale) // 2
        set_px = real.SetPixel
        for dx, dy in offsets:
            set_px(cx + dx, cy + dy, r, g, b)

    paint_hires(canvas, _paint)
    return size


def _render_glyph(canvas: Canvas, x: int, frame: int, spec: SeparatorSpec) -> int:
    from led_ticker.colors import make_color
    from led_ticker.drawing import compute_baseline, get_text_width
    from led_ticker.text_render import draw_text

    c = _as_provider(spec.color).color_for(frame, 0, 1)
    color = c if hasattr(c, "red") else make_color(*c)
    baseline_y = compute_baseline(spec.font, canvas, "center")
    draw_text(canvas, spec.font, x, baseline_y, color, spec.glyph)
    return get_text_width(spec.font, spec.glyph, padding=0, canvas=canvas)


def render_separator(canvas: Canvas, x: int, frame: int, spec: SeparatorSpec) -> int:
    """Paint the separator mark at logical x; return its logical width (no pad)."""
    if spec.kind == "glyph":
        return _render_glyph(canvas, x, frame, spec)
    rgb = _resolve_rgb(spec.color, frame)
    if spec.kind == "circle" and is_scaled(canvas):
        return _render_circle(canvas, x, rgb, spec.size)
    # dot (and circle on a plain canvas is handled by the widget's BDF path,
    # so it does not reach here in Phase 1)
    return _render_dot(canvas, x, rgb, spec.size)


def separator_width(spec: SeparatorSpec) -> int:
    """The mark's own logical width (no padding)."""
    if spec.kind == "glyph":
        from led_ticker.drawing import get_text_width

        return get_text_width(spec.font, spec.glyph, padding=0)
    return spec.size


def scroll_separator_width(
    spec: SeparatorSpec = DEFAULT_DOT_SPEC, gap: int = SCROLL_GAP
) -> int:
    """Total scroll separator width: gap + mark + gap."""
    return gap + separator_width(spec) + gap
