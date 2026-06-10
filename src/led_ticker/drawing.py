"""Shared drawing helpers for LED canvas rendering."""

import math
from typing import Any

import attrs

from led_ticker.fonts.hires_loader import HiresFont


@attrs.define(frozen=True, slots=True)
class Region:
    """A rectangular sub-area of a canvas.

    Plumbed through draw() and run_transition() for forward compatibility
    with zoned layouts. Currently always equals the full canvas.
    """

    x: int
    y: int
    width: int
    height: int


def get_widget_padding(widget: Any, default: int = 6) -> int:
    """Get a widget's padding attribute, with fallback for mocks."""
    padding = getattr(widget, "padding", None)
    return padding if isinstance(padding, int) else default


# Fallback scale used by `get_text_width` when no canvas is provided.
# Hi-res fonts only make sense on the bigsign at scale=4 today, so
# this preserves the pre-canvas-aware behavior for callers (e.g.
# `TickerMessage.__init__`) that don't have a canvas yet. If hi-res
# use spreads beyond the bigsign, audit no-canvas call sites — they'll
# under-report widths on a small sign at scale=1.
SCALE_FALLBACK: int = 4


def safe_scale(canvas: Any) -> int:
    """Read `canvas.scale` defensively, falling back to 1.

    The real `RGBMatrix` canvas has no `scale` attribute (it IS the
    physical panel — real and logical coords coincide). The
    `ScaledCanvas` wrapper exposes an int `scale`. Test fixtures use
    `Mock` canvases where `getattr(c, "scale", 1)` returns a Mock
    object (auto-generated), not 1.

    This helper handles all three: an int ≥ 1 passes through; anything
    else (Mock, missing, negative, zero) falls back to scale=1. Used
    by every code path that reads `canvas.scale` for layout math.
    """
    attr = getattr(canvas, "scale", 1)
    return attr if isinstance(attr, int) and attr >= 1 else 1


# Module-level memoization for `get_text_width`. Keyed by
# `(id(font), text, padding, scale)` — `id(font)` is stable for the
# lifetime of the module-level BDF/HiresFont objects, `padding` is
# usually 0/3/6, and `scale` reflects the canvas the width was measured
# against (so a width measured on the bigsign at scale=4 doesn't
# pollute a small-sign measurement at scale=1). Bounded to keep memory
# predictable even if widget configs spawn many unique strings (e.g.
# countdown messages). Unbounded `dict` would grow forever as new
# strings appear.
_TEXT_WIDTH_CACHE: dict[tuple[int, str, int, int], int] = {}
_TEXT_WIDTH_CACHE_MAXSIZE: int = 256


def get_text_width(font: Any, text: str, padding: int = 6, canvas: Any = None) -> int:
    """Get the pixel width of rendered text plus padding (memoized).

    Dispatches on font type: HiresFont sums glyph advances (with ``?``
    fallback for unknown chars), then converts the real-pixel total to
    logical pixels so layout math stays in consistent units with the
    BDF path. BDF C font uses ``CharacterWidth(ord(c))`` as before.

    `canvas` (optional) supplies the scale for the real→logical
    conversion. Pass it from any draw-time call site to get the
    correct width on any scale. The function reads ``canvas.scale``
    when it's an int ≥ 1 (a `ScaledCanvas` wrapper), otherwise:
      - canvas IS provided but has no usable `scale` → treat as
        scale=1 (a plain real canvas, e.g. small sign or unwrapped
        bigsign real canvas).
      - canvas is None → fall back to ``SCALE_FALLBACK = 4`` for
        callers that pre-compute width before any canvas exists
        (e.g. ``TickerMessage.__init__``). Preserves the original
        bigsign-only behavior in that lone case.

    **Caching**: results are memoized in a module-level dict keyed on
    `(id(font), text, padding, scale)`. Per-frame callers (weather,
    two-row tickers) hit the cache instead of re-summing glyph
    advances every draw — saves O(len(text)) dict lookups per call.
    Cache evicts the oldest entry at ``_TEXT_WIDTH_CACHE_MAXSIZE = 256``
    entries, staying at exactly maxsize instead of dropping to 1.
    """
    # Resolve effective scale once for both caching and computation.
    scale = SCALE_FALLBACK if canvas is None else safe_scale(canvas)

    key = (id(font), text, padding, scale)
    cached = _TEXT_WIDTH_CACHE.get(key)
    if cached is not None:
        return cached

    if isinstance(font, HiresFont):
        fallback = font.glyphs.get("?")
        fallback_advance = fallback.advance if fallback else 0
        total_real = sum(
            font.glyphs[c].advance if c in font.glyphs else fallback_advance
            for c in text
        )
        # Hi-res glyph advances are REAL pixels. Logical (cf.
        # canvas.width on a ScaledCanvas) needs ceil-division by
        # scale; ceil so we never undercount and break overflow
        # detection on text that just barely fits.
        width = -(-total_real // scale) + padding
    else:
        width = sum(font.CharacterWidth(ord(c)) for c in text) + padding

    if len(_TEXT_WIDTH_CACHE) >= _TEXT_WIDTH_CACHE_MAXSIZE:
        _TEXT_WIDTH_CACHE.pop(next(iter(_TEXT_WIDTH_CACHE)))
    _TEXT_WIDTH_CACHE[key] = width
    return width


def compute_baseline_for_band(
    font: Any, band_height_logical: int, scale: int, valign: str = "center"
) -> int:
    """Compute the logical-pixel baseline y for a single band.

    Lower-level primitive used by `compute_baseline` (operates on a
    canvas) and `widgets/two_row._row_layout` (operates on a sub-band
    inside a canvas). Takes explicit `band_height_logical` + `scale`
    args so callers don't have to fabricate canvas-shaped objects via
    SimpleNamespace just to ask "where would the glyph center inside
    these N logical rows?".

    Rounding rules differ by valign because integer division loses
    sub-scale-pixel precision: top rounds up (avoid clipping the
    ascender above the band edge), bottom rounds down (avoid clipping
    the descender below it), center rounds to nearest.

    Result is relative to the band's top edge — callers add the
    band's offset on the canvas to land on the right absolute y.
    """
    from led_ticker.fonts import font_ascent, font_line_height

    is_hires = isinstance(font, HiresFont)
    line_h_real = font_line_height(font)
    asc_real = font_ascent(font)
    if not is_hires:
        # BDF metrics are logical; multiply up so we can compose with
        # the band's real-pixel extent consistently.
        line_h_real *= scale
        asc_real *= scale

    band_h_real = band_height_logical * scale

    if valign == "top":
        baseline_real = asc_real
        # Round UP so the ascender doesn't clip above the band edge.
        return -(-baseline_real // scale)
    if valign == "bottom":
        descent_real = line_h_real - asc_real
        baseline_real = band_h_real - descent_real
        # Round DOWN so the descender doesn't clip below the band.
        return baseline_real // scale
    # center
    top_real = (band_h_real - line_h_real) // 2
    baseline_real = top_real + asc_real
    return (baseline_real + scale // 2) // scale  # round to nearest


def compute_baseline(font: Any, canvas: Any, valign: str = "center") -> int:
    """Return the logical-pixel baseline y for the requested valign.

    Canvas-shaped wrapper over `compute_baseline_for_band` — extracts
    the canvas's logical height + scale and delegates. Replaces the
    hardcoded ``y = 12`` (BDF 6×12) baseline that was embedded
    throughout TickerMessage / image widgets. Works for both BDF and
    HiresFont — `compute_baseline_for_band` handles the metric
    differences internally.

    For BDF on a non-scaled canvas this returns y=12 for "center" on a
    6×12 cell in a 16-row canvas — back-compat preserved.
    """
    return compute_baseline_for_band(font, canvas.height, safe_scale(canvas), valign)


def find_center(canvas_width: int, content_width: int) -> float:
    """Find the x position to center content on a canvas."""
    return (canvas_width / 2) - math.floor(content_width / 2)


def compute_cursor(
    canvas_width: int,
    content_width: int,
    cursor_pos: int,
    padding: int,
    *,
    center: bool,
) -> tuple[int, int]:
    """Compute cursor position and end padding, handling centering logic.

    Returns (adjusted_cursor_pos, end_padding).
    """
    end_padding = padding

    if center and content_width <= canvas_width:
        center_pos = int(find_center(canvas_width, content_width))
        end_padding = canvas_width - (center_pos + content_width)
        cursor_pos += center_pos

    return cursor_pos, end_padding
