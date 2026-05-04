"""Font loading for LED display with generic naming.

Each loaded font is paired with a Python-side `BDFFont` (via `get_bdf_for()`)
so the bigsign rendering path can rasterize text without going through the
C-only `graphics.DrawText`.
"""

from __future__ import annotations

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
    """Return the parsed BDF data for a font previously loaded via _load_font."""
    return _BDF_BY_ID[id(font)]


# Generic font names (replacing crypto-specific FONT_PRICE, FONT_SYMBOL, etc.)
FONT_DEFAULT: Font = _load_font("6x12.bdf")
FONT_SMALL: Font = _load_font("5x8.bdf")
FONT_LABEL: Font = _load_font("7x13.bdf")  # was FONT_SYMBOL
FONT_VALUE: Font = FONT_DEFAULT  # alias — same as 6x12.bdf
FONT_VALUE_SMALL: Font = FONT_SMALL  # alias — same as 5x8.bdf
FONT_DELTA: Font = _load_font("6x10.bdf")  # was FONT_CHANGE

from led_ticker.fonts.hires_loader import (  # noqa: E402
    HiresFont,
    list_available_hires_fonts,
    load_hires_font,
)

# Default size when TOML specifies `font = "..."` without `font_size`.
# 24 pixels is a reasonable "body text" size on a 64-row bigsign panel.
DEFAULT_HIRES_SIZE: int = 24

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
    name: str, size: int = DEFAULT_HIRES_SIZE, threshold: int | None = None
) -> Font | HiresFont:
    """Resolve a TOML font name to a loaded font object.

    Resolution order:
      1. Hi-res fonts (config/fonts/ overrides bundled fonts/hires/).
      2. BDF aliases (`6x12`, `5x8`, etc.).
      3. Raise `UnknownFontError`.

    `size` is only meaningful for hi-res fonts; BDF aliases ignore it.
    `threshold` (0-255) is the rasterization cutoff for hi-res fonts;
    `None` uses the loader default (128 = 50%). Lower it (~80) for
    thin-stroked fonts whose antialiased edges otherwise get clipped.
    Ignored for BDF.

    Raises `ValueError` if `size < 8` (glyphs unreadable below that),
    if `threshold` isn't an int, or if it's outside 0-255.
    """
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
    if name in _BDF_ALIASES:
        return _BDF_ALIASES[name]
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
    # BDF path: font.height() is the C bitmap height attribute.
    # The stub mirrors this via the FONTBOUNDINGBOX height field.
    return font.height()
