"""Font loading for LED display with generic naming.

Each loaded font is paired with a Python-side `BDFFont` (via `get_bdf_for()`)
so the bigsign rendering path can rasterize text without going through the
C-only `graphics.DrawText`.
"""

import os

from led_ticker._compat import require_graphics
from led_ticker._types import Font
from led_ticker.fonts.bdf_parser import BDFFont, parse_bdf

_graphics = require_graphics()
FONT_DIR: str = os.path.dirname(os.path.realpath(__file__))

# Maps `id(c_font)` to its parsed BDFFont. Indexed by id() because the
# C Font objects from rgbmatrix aren't hashable. This relies on the fonts
# being stored in module-level globals (FONT_DEFAULT, FONT_SMALL, etc.) so
# they're never garbage-collected and their id() stays stable. If font
# construction is ever moved into a function, switch to a different keying
# strategy (e.g., a wrapper class or path-based dict).
_BDF_BY_ID: dict[int, BDFFont] = {}


def _load_font(filename: str) -> Font:
    path = os.path.join(FONT_DIR, filename)
    c_font = _graphics.Font()
    c_font.LoadFont(path)
    with open(path) as f:
        bdf = parse_bdf(f.read())
    _BDF_BY_ID[id(c_font)] = bdf
    return c_font


def get_bdf_for(font: Font) -> BDFFont:
    """Return the parsed BDF data for a font previously loaded via _load_font.

    Falls back to `font._bdf` for fonts that carry their own parsed BDF
    (e.g. the test stub's `Font` after `LoadFont`). Raises `KeyError` only
    when neither source is available.
    """
    bdf = _BDF_BY_ID.get(id(font))
    if bdf is not None:
        return bdf
    # Stub fonts (and any font that parsed its own BDF) expose `_bdf`.
    bdf = getattr(font, "_bdf", None)
    if bdf is not None:
        return bdf
    raise KeyError(id(font))


# Generic font names (replacing crypto-specific FONT_PRICE, FONT_SYMBOL, etc.)
FONT_DEFAULT: Font = _load_font("6x12.bdf")
FONT_SMALL: Font = _load_font("5x8.bdf")
FONT_LABEL: Font = _load_font("7x13.bdf")  # was FONT_SYMBOL
FONT_DELTA: Font = _load_font("6x10.bdf")  # was FONT_CHANGE

from led_ticker.fonts.hires_loader import (  # noqa: E402
    HiresFont,
    list_available_hires_fonts,
    load_hires_font,
)

# Map from BDF "alias name" (used in TOML) to the loaded C font object.
# These names match the .bdf filename stems for consistency.
_BDF_ALIASES: dict[str, Font] = {
    "6x12": FONT_DEFAULT,
    "5x8": FONT_SMALL,
    "7x13": FONT_LABEL,
    "6x10": FONT_DELTA,
}


class UnknownFontError(ValueError):
    """Raised when a TOML font name resolves to nothing.

    The message lists all known fonts so the user can fix typos.
    """


def resolve_font(
    name: str, size: int | None = None, threshold: int | None = None
) -> Font | HiresFont:
    """Resolve a TOML font name to a loaded font object.

    Resolution order:
      1. BDF aliases (`6x12`, `5x8`, etc.) — size is irrelevant for BDF.
      2. Hi-res fonts (config/fonts/ overrides bundled fonts/hires/).
      3. Raise `UnknownFontError`.

    `size` is only meaningful for hi-res fonts; BDF aliases ignore it.
    Pass `size=None` for BDF configs (smart default kicks in at paint).
    For HiresFont, `size` is required — the rasterizer needs a real-px
    target and there is no sensible default.
    `threshold` (0-255) is the rasterization cutoff for hi-res fonts;
    `None` uses the loader default (128 = 50%). Lower it (~80) for
    thin-stroked fonts whose antialiased edges otherwise get clipped.
    Ignored for BDF.

    Raises `ValueError` if `size < 8` (glyphs unreadable below that),
    if `size` is None for a HiresFont name, if `threshold` isn't an
    int, or if it's outside 0-255.
    """
    # BDF first — cells are fixed by the .bdf file, size is irrelevant
    # there. This also lets the caller pass `size=None` for BDF without
    # tripping the `size < 8` legibility check.
    if name in _BDF_ALIASES:
        return _BDF_ALIASES[name]

    # HiresFont path — size is required (rasterizer needs a real-px
    # target).
    if size is None:
        raise ValueError(f"HiresFont {name!r} requires a size (real pixels).")
    if size < 8:
        raise ValueError(f"font_size must be >= 8 for legible rendering; got {size}")
    if threshold is not None:
        # Reject str / float / bool early so they can't pollute the
        # `@functools.cache` key in `load_hires_font`. Floats hash
        # distinctly from int-equal values, double-rasterizing the
        # same glyphs; strings give a confusing TypeError later.
        # bool is a subclass of int — exclude explicitly.
        if not isinstance(threshold, int) or isinstance(threshold, bool):
            raise ValueError(
                f"font_threshold must be an int 0-255; got {type(threshold).__name__} "
                f"({threshold!r})"
            )
        if not (0 <= threshold <= 255):
            raise ValueError(f"font_threshold must be 0-255; got {threshold}")
    from led_ticker.fonts.hires_loader import THRESHOLD

    effective = THRESHOLD if threshold is None else threshold
    hires = load_hires_font(name, size, effective)
    if hires is not None:
        return hires
    from led_ticker.fonts.hires_loader import _PLUGIN_FONTS

    if name in _PLUGIN_FONTS:
        raise UnknownFontError(
            f"plugin font {name!r} is registered but its file is missing: "
            f"{_PLUGIN_FONTS[name]}"
        )
    available = list_available_fonts()
    raise UnknownFontError(f"unknown font {name!r}; available: {available}")


def list_available_fonts() -> list[str]:
    """Sorted list of all font names: hi-res + BDF aliases."""
    names = set(list_available_hires_fonts())
    names.update(_BDF_ALIASES.keys())
    return sorted(names)


def font_line_height(font: Font | HiresFont) -> int:
    """Return the font's line height in logical pixels.

    For BDF fonts: the FONTBOUNDINGBOX height from the .bdf file.
    For HiresFont: `ascent + descent` from the loaded TTF metrics.

    Used by `pixel_emoji` to position emoji icons relative to the font's
    natural cell, instead of hardcoded 12-row BDF assumptions.
    """
    if isinstance(font, HiresFont):
        return font.line_height
    # BDF C font: `height` is an INT ATTRIBUTE on real hardware (the
    # rgbmatrix C extension), but the test stub historically exposed
    # it as a callable. Tolerate both — call if callable, else read.
    from typing import Any as _Any
    from typing import cast as _cast

    h: _Any = font.height
    raw = h() if callable(h) else h
    return _cast(int, raw)


def font_ascent(font: Font | HiresFont) -> int:
    """Return the font's ascent (baseline-to-top distance) in pixels.

    For BDF fonts: the parsed FONT_ASCENT field from the .bdf file
    (logical pixels). For HiresFont: the FreeType-reported ascent
    (real pixels). Used by `drawing.compute_baseline` to position
    text vertically without hardcoded BDF cell assumptions.
    """
    if isinstance(font, HiresFont):
        return font.ascent
    # BDF C font isn't directly inspectable for ascent — pull from the
    # parsed BDF kept alongside it during _load_font.
    return get_bdf_for(font).ascent


def font_line_height_logical(font: Font | HiresFont, scale: int) -> int:
    """Return font line-height in LOGICAL pixels for a canvas at `scale`.

    BDF metrics are already logical (a 6×12 cell is 12 logical px on
    any canvas). HiresFont metrics are REAL pixels and need ceil-
    division by canvas scale to express as logical rows. This helper
    consolidates that branch — three sites (`drawing.get_text_width`,
    `widgets/_image_base._play_with_text`, `widgets/two_row.draw`)
    were duplicating the same `-(-x // scale) if isinstance(...)`
    pattern.
    """
    line_h = font_line_height(font)
    if isinstance(font, HiresFont):
        # Ceil-division so we never under-report the height (which
        # would let a font claim to fit a band it actually overflows).
        return -(-line_h // max(1, scale))
    return line_h


def block_scale_for_font_size(font: Font | HiresFont, font_size: int) -> int:
    """Return the integer block scale to wrap the canvas at, given a
    target `font_size` in real pixels.

    For BDF: cells are bitmaps; the wrapper block-expands them by the
    returned scale. We round down `font_size` to the nearest integer
    multiple of the font's cell height. Floor: the BDF cell can't
    render below its natural height, so `font_size < cell_h` raises
    with a hint pointing at smaller bundled BDFs.

    For HiresFont: always returns 1. HiresFont rasterizes at the real
    `font_size` at construction time and paints to the unwrapped real
    canvas, so the wrapper has no glyph-size impact.

    Raises ValueError on `font_size <= 0` or BDF `font_size < cell_h`.
    """
    if font_size <= 0:
        raise ValueError(f"font_size must be > 0; got {font_size!r}.")

    if isinstance(font, HiresFont):
        return 1

    cell_h = font_line_height(font)
    if font_size < cell_h:
        raise ValueError(
            f"font_size={font_size} below cell height {cell_h} for BDF "
            f"font. For smaller text use BDF '5x8' (cell_h=8) or a "
            f"HiresFont."
        )
    return font_size // cell_h
