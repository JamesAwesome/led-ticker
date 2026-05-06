"""Unified text-drawing helper that picks the right rendering path.

For a real `RGBMatrix` canvas (existing sign), forwards to `graphics.DrawText`
unchanged. For a `ScaledCanvas` (bigsign at scale > 1), uses the pure-Python
BDF rasterizer. For a `HiresFont`, uses the per-glyph hi-res renderer
that paints to the unwrapped real canvas at native physical resolution.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from led_ticker._compat import require_graphics
from led_ticker.fonts import get_bdf_for
from led_ticker.fonts.hires_loader import HiresFont
from led_ticker.scaled_canvas import ScaledCanvas, unwrap_to_real

_graphics = require_graphics()


def draw_text(canvas: Any, font: Any, x: int, y: int, color: Any, text: str) -> int:
    """Draw `text` at (x, y) baseline. Returns total advance width."""
    if isinstance(font, HiresFont):
        return _draw_hires_text(canvas, font, x, y, color, text)
    if isinstance(canvas, ScaledCanvas):
        bdf = get_bdf_for(font)
        return canvas.draw_bdf_text(bdf, x, y, color, text)
    return _graphics.DrawText(canvas, font, x, y, color, text)


def _draw_hires_text(
    canvas: Any, font: HiresFont, x: int, y: int, color: Any, text: str
) -> int:
    """Paint hi-res glyphs at native physical resolution.

    `(x, y)` are LOGICAL coords (consistent with BDF callers). The
    renderer multiplies by canvas scale (and adds the wrapper's
    y-offset) to get real pixel coords, then paints glyph pixels
    directly to the unwrapped real canvas — bypasses the wrapper's
    4×4 block expansion. Out-of-bounds pixels clip silently.

    Returns the advance width in LOGICAL pixels (matching BDF semantics
    so callers like TickerMessage can do `cursor_pos += advance` in
    consistent units). Internally tracks real-pixel cursor position
    for sub-logical-pixel glyph placement; converts to logical at
    return via ceil-division.
    """
    real = unwrap_to_real(canvas)
    scale = getattr(canvas, "scale", 1)
    y_offset = getattr(canvas, "_y_offset", 0)
    real_baseline_y = y * scale + y_offset
    real_x = x * scale

    set_px = real.SetPixel
    panel_w = real.width
    panel_h = real.height
    r, g, b = color.red, color.green, color.blue

    cursor_x = real_x
    fallback = font.glyphs.get("?")
    for ch in text:
        glyph = font.glyphs.get(ch, fallback)
        if glyph is None:
            continue
        gx0 = cursor_x + glyph.bearing_x
        gy0 = real_baseline_y - glyph.bearing_y
        # Per-glyph clip-rect early-out: skip the lit-pixel loop when
        # the entire glyph bbox sits off-canvas. Saves ~25% on long
        # scrolling text (most glyphs are off-screen at any given
        # moment). Safe because off-canvas glyphs would have every
        # SetPixel call rejected by the per-pixel bounds check anyway.
        if (
            gx0 + glyph.width <= 0
            or gx0 >= panel_w
            or gy0 + glyph.height <= 0
            or gy0 >= panel_h
        ):
            cursor_x += glyph.advance
            continue
        for dx, dy in glyph.lit:
            px = gx0 + dx
            py = gy0 + dy
            if 0 <= px < panel_w and 0 <= py < panel_h:
                set_px(px, py, r, g, b)
        cursor_x += glyph.advance

    # Return logical-pixel advance so callers' `cursor_pos += advance`
    # stays in consistent units. Ceil-division so the reported width
    # is never less than the text actually occupies (under-reporting
    # would break overflow detection for text that just barely fits).
    real_advance = cursor_x - real_x
    return -(-real_advance // scale)  # ceil division


def draw_text_per_char(
    canvas: Any,
    font: Any,
    x_logical: int,
    y: int,
    text: str,
    color_fn: Callable[[int, int], Any],
    char_offset: int = 0,
    total_chars: int | None = None,
) -> int:
    """Draw `text` with a per-character color from `color_fn(idx, total)`.

    Used by per-char ColorProviders (rainbow, gradient) so each char
    in the rendered text gets its own color while the cursor advances
    cleanly without rounding drift.

    `color_fn(idx, total)` receives the global character index (offset
    by `char_offset`) and the total span the provider is sweeping
    across. `char_offset` lets a caller resume an in-flight sweep —
    used by `draw_with_emoji` to keep the rainbow continuous across
    text segments interrupted by emoji sprites. `total_chars` defaults
    to `len(text)` (a self-contained sweep).

    The callback is `(idx, total) -> Color`; callers pre-bind the
    `frame` parameter via closure so this helper stays frame-agnostic.
    The widget call sites all do the same:
    `lambda idx, total: provider.color_for(self._frame_count, idx, total)`.

    Returns logical advance in pixels.

    HiresFont gotcha: a naive `for ch in text: x += draw_text(...)`
    loop accumulates per-char ceil-divisions and overshoots the
    holistic `get_text_width` measurement. This helper tracks the
    cursor in real pixels for HiresFont and ceil-divides ONCE at the
    end, so the returned advance matches the holistic measurement and
    scroll-detection works correctly.
    """
    total = total_chars if total_chars is not None else len(text)

    if isinstance(font, HiresFont):
        # Real-px cursor inside the loop avoids per-char ceil drift.
        # Mirrors the structure of `_draw_hires_text` but materializes
        # a different Color per glyph from `color_fn`.
        real = unwrap_to_real(canvas)
        scale = getattr(canvas, "scale", 1)
        y_offset = getattr(canvas, "_y_offset", 0)
        real_baseline_y = y * scale + y_offset
        real_x = x_logical * scale

        set_px = real.SetPixel
        panel_w = real.width
        panel_h = real.height
        fallback = font.glyphs.get("?")

        cursor_x = real_x
        for i, ch in enumerate(text):
            color = color_fn(char_offset + i, total)
            r, g, b = color.red, color.green, color.blue
            glyph = font.glyphs.get(ch, fallback)
            if glyph is None:
                continue
            gx0 = cursor_x + glyph.bearing_x
            gy0 = real_baseline_y - glyph.bearing_y
            if (
                gx0 + glyph.width <= 0
                or gx0 >= panel_w
                or gy0 + glyph.height <= 0
                or gy0 >= panel_h
            ):
                cursor_x += glyph.advance
                continue
            for dx, dy in glyph.lit:
                px = gx0 + dx
                py = gy0 + dy
                if 0 <= px < panel_w and 0 <= py < panel_h:
                    set_px(px, py, r, g, b)
            cursor_x += glyph.advance

        real_advance = cursor_x - real_x
        return -(-real_advance // scale)

    # BDF: per-char draw_text returns logical advance directly; no drift.
    x = x_logical
    for i, ch in enumerate(text):
        color = color_fn(char_offset + i, total)
        x += draw_text(canvas, font, x, y, color, ch)
    return x - x_logical
