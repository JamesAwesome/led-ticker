# src/led_ticker/fonts/hires_loader.py
"""Hi-res TTF/OTF font loader, glyph rasterizer, and cache.

Bundled fonts live at `src/led_ticker/fonts/hires/`. User-supplied
fonts (e.g. licensed Adobe Fonts) live at `config/fonts/` (gitignored).

`load_hires_font(name, size)` resolves a name through both dirs,
rasterizes glyphs once via Pillow, thresholds them to a 1-bit mask
at 50% intensity, and returns a frozen `HiresFont` cached forever.

The renderer (`text_render._draw_hires_text`) then paints lit pixels
directly to the unwrapped real canvas at native physical resolution.
"""

from __future__ import annotations

import functools
import string
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

# 50% of 0-255 — pixels at or above this are "on" after rasterization.
# Higher = thicker strokes; lower = thinner. 128 matches the natural
# midpoint and produces clean glyphs at 24-32px on a 64-row LED panel.
THRESHOLD: int = 128

BUNDLED_HIRES_DIR: Path = Path(__file__).parent / "hires"
USER_FONT_DIR: Path = Path(__file__).parent.parent.parent.parent / "config" / "fonts"
# USER_FONT_DIR resolves to <repo_root>/config/fonts in dev. In a wheel
# install, the user's working dir matters — Path("config/fonts").resolve()
# would be relative to invocation. We re-resolve at lookup time below.

# Most common Latin-1 accented characters. Pre-rasterized along with
# string.printable so widgets handling European-language feeds (Spanish,
# French, German, etc) render correctly. Other characters fall back to
# the '?' glyph at render time.
EXTENDED_LATIN: str = "àáâãäåæçèéêëìíîïñòóôõöøùúûüýÿÀÁÂÃÄÅÆÇÈÉÊËÌÍÎÏÑÒÓÔÕÖØÙÚÛÜÝŸ"

# Common Unicode punctuation typesetters reach for in headlines and
# storefront copy. Pre-rasterized so they actually render instead of
# falling back to '?'. Bullet (•) is the canonical list separator on
# the bigsign two_row pattern; em-dash and curly quotes are standard
# in promotional copy from RSS feeds and brand sources.
EXTENDED_PUNCTUATION: str = "•·…—–’‘“”«»"

# Geometric shapes used by the MLB scoreboard center zone: inning-half
# triangles, filled/open circles (outs/pips), filled/open diamonds (bases).
GEOMETRIC_SHAPES: str = "▲▼●○◆◇"


@dataclass(frozen=True)
class HiresGlyph:
    """Rasterized glyph at a specific size, post-threshold.

    Coordinates are RELATIVE to the glyph's bbox: `(0, 0)` is the
    top-left of the bbox, NOT the canvas. The renderer adds the
    glyph's `bearing_x` / `bearing_y` to position relative to the
    cursor + baseline.
    """

    width: int
    height: int
    advance: int
    bearing_x: int
    bearing_y: int
    lit: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class HiresFont:
    """A loaded TTF/OTF font at one specific pixel size.

    `glyphs` maps each rasterized character to its `HiresGlyph`.
    Characters not in `glyphs` fall back to `'?'` at render time.
    """

    name: str
    size: int
    ascent: int
    descent: int
    line_height: int
    glyphs: dict[str, HiresGlyph] = field(default_factory=dict)


def _find_font_path(name: str) -> Path | None:
    """Look up a font by name across user + bundled dirs.

    User dir wins on collisions so users can override bundled fonts.
    Tries `.otf` first, then `.ttf`. Returns None if not found.
    """
    for ext in (".otf", ".ttf"):
        for base in (USER_FONT_DIR, BUNDLED_HIRES_DIR):
            candidate = base / f"{name}{ext}"
            if candidate.exists():
                return candidate.resolve()
    return None


def list_available_hires_fonts() -> list[str]:
    """Return sorted list of all hi-res font names across both dirs."""
    names: set[str] = set()
    for base in (USER_FONT_DIR, BUNDLED_HIRES_DIR):
        if not base.exists():
            continue
        for path in base.iterdir():
            if path.suffix.lower() in (".otf", ".ttf"):
                names.add(path.stem)
    return sorted(names)


def _rasterize_glyph(
    pil_font: Any, ch: str, ascent: int, descent: int, threshold: int = THRESHOLD
) -> HiresGlyph:
    """Render a single character to a binarized HiresGlyph.

    Pillow's default `draw.text` anchor is "la" (left-ascender) —
    drawing at (0, 0) puts the ascender line at y=0 and the baseline
    at y=ascent. `pil_font.getbbox(ch)` returns coords IN THE SAME
    SPACE as that draw — so for capital "M" with cap height H, bbox
    might be (0, ascent-H, M_width, ascent), telling us the glyph
    occupies rows ascent-H..ascent in the rendered image.

    We render into an image tall enough for any glyph (ascent +
    descent rows), then crop the bbox region. `bearing_y` converts
    bbox[1] from image coords back to baseline-relative (positive
    distance above baseline) so `_draw_hires_text` can position
    glyphs against a baseline_y. Lit pixel coords are bbox-relative
    (0, 0 = glyph top-left within its own bbox).
    """
    advance = int(pil_font.getlength(ch))
    bbox = pil_font.getbbox(ch)
    if bbox is None or bbox[2] <= bbox[0] or bbox[3] <= bbox[1]:
        # Whitespace or zero-width char — emit empty glyph with advance.
        return HiresGlyph(
            width=0,
            height=0,
            advance=advance,
            bearing_x=0,
            bearing_y=0,
            lit=(),
        )

    width = bbox[2] - bbox[0]
    height = bbox[3] - bbox[1]

    # Image canvas large enough to hold ANY glyph in this font.
    # canvas_w covers from x=0 (where draw.text origin sits) past the
    # right edge of the rendered glyph and any natural advance. canvas_h
    # = ascent + descent so any glyph fits vertically.
    canvas_w = max(advance, bbox[2]) + 4  # extra slack on the right
    canvas_h = ascent + descent
    img = Image.new("L", (canvas_w, canvas_h), 0)
    draw = ImageDraw.Draw(img)
    draw.text((0, 0), ch, font=pil_font, fill=255)

    pixels = img.tobytes()
    lit: list[tuple[int, int]] = []
    # bbox is in image coords directly (anchor="la", drawn at y=0).
    img_top = bbox[1]
    img_left = bbox[0]
    for dy in range(height):
        img_y = img_top + dy
        if img_y < 0 or img_y >= canvas_h:
            continue
        row_offset = img_y * canvas_w
        for dx in range(width):
            img_x = img_left + dx
            if img_x < 0 or img_x >= canvas_w:
                continue
            if pixels[row_offset + img_x] >= threshold:
                lit.append((dx, dy))

    return HiresGlyph(
        width=width,
        height=height,
        advance=advance,
        bearing_x=bbox[0],
        # bearing_y = distance from baseline UP to glyph top. Image
        # baseline is at row `ascent`; glyph top is at row bbox[1].
        # Positive bearing_y means glyph top is ABOVE baseline (most
        # glyphs); negative means below (rare — e.g. underscore).
        bearing_y=ascent - bbox[1],
        lit=tuple(lit),
    )


def _rasterize(
    path: Path, size: int, name: str, threshold: int = THRESHOLD
) -> HiresFont:
    """Load .otf/.ttf via Pillow at `size` and rasterize all glyphs.

    `threshold` is the 0-255 cutoff applied to each anti-aliased pixel.
    Default 128 (50% intensity) gives clean LED output for medium-stroke
    fonts like Inter. Thin-stroked fonts (e.g. Beloved Sans Regular at
    24px) need a lower threshold (~80) so the antialiased edges of thin
    strokes survive instead of getting quantized to zero.
    """
    pil_font = ImageFont.truetype(str(path), size)
    ascent, descent = pil_font.getmetrics()
    chars = string.printable + EXTENDED_LATIN + EXTENDED_PUNCTUATION + GEOMETRIC_SHAPES
    glyphs: dict[str, HiresGlyph] = {}
    for ch in chars:
        glyphs[ch] = _rasterize_glyph(pil_font, ch, ascent, descent, threshold)
    return HiresFont(
        name=name,
        size=size,
        ascent=ascent,
        descent=descent,
        line_height=ascent + descent,
        glyphs=glyphs,
    )


# Cache cap. A real config would have at most a handful of distinct
# (name, size, threshold) combos — bigsign deployments typically use
# 2-4 fonts. 16 leaves comfortable headroom while bounding memory if
# someone misconfigures (e.g. animated `font_size` pulses) or a test
# suite spawns many one-off entries. Each entry is ~100-300 KB
# (rasterized glyph dict).
_FONT_CACHE_MAXSIZE: int = 16


@functools.lru_cache(maxsize=_FONT_CACHE_MAXSIZE)
def load_hires_font(
    name: str, size: int, threshold: int = THRESHOLD
) -> HiresFont | None:
    """Load (or fetch from cache) a hi-res font by name, pixel size, and threshold.

    `threshold` is part of the cache key so a widget that overrides the
    default still gets a freshly-rasterized font without polluting other
    widgets that use the same name+size at the standard threshold.

    Bounded at ``_FONT_CACHE_MAXSIZE`` entries; LRU eviction beyond
    that. A real config touches 2-4 fonts; 16 is comfortably above
    typical use.
    """
    path = _find_font_path(name)
    if path is None:
        return None
    return _rasterize(path, size, name, threshold)
