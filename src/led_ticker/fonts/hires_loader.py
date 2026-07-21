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

import functools
import logging
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

# General scoreboard / symbol glyphs: filled/open triangles, circles, and
# diamonds. Used by scoreboard-style widgets (e.g. the baseball plugin's
# center zone: inning-half triangles, outs/pips, bases) for status pips.
GEOMETRIC_SHAPES: str = "▲▼●○◆◇"

# Measurement / unit symbols. Pre-rasterized so they render instead of
# falling back to '?'. The degree sign (°) is used by weather/temperature
# copy — e.g. the baseball plugin's attendance widget renders "72° Clear",
# which showed as "72?" on the bigsign before this was added.
SYMBOLS: str = "°"

# Typographic codepoints that number/text formatters emit but that aren't in
# the rasterized charset above and have no dedicated glyph — map each to a
# look-alike ASCII char that IS in the charset (so the font's real glyph is
# used) instead of letting the caller draw the '?' tofu. U+2212 MINUS SIGN is
# the load-bearing one: any source rendering a negative ("-1.98%") emits it,
# and it showed as "?" on the panel. Consulted by `HiresFont.resolve_glyph`;
# extend it as new formatter glyphs surface (keep BOTH sides visually close —
# this substitutes silently). NOT for chars already in the charset (em/en
# dash, middle dot) — those rasterize directly.
_ASCII_GLYPH_FALLBACKS: dict[str, str] = {
    "−": "-",  # U+2212 MINUS SIGN -> HYPHEN-MINUS
}

# A private-use codepoint is guaranteed unassigned, so rasterizing it yields
# the font's notdef glyph (a box, or empty if the font has no notdef). We
# fingerprint it once per font and treat any glyph whose lit pixels match as
# MISSING — this is what makes "▲ in a font that lacks it" a detectable miss
# instead of a silently-painted tofu box.
_NOTDEF_PROBE = ""  # PUA U+E000


def _is_notdef(glyph: HiresGlyph, notdef_lit: tuple[tuple[int, int], ...]) -> bool:
    """A glyph is 'missing' if it matches the font's notdef fingerprint, or
    is empty for a non-whitespace request (fonts with no notdef render
    nothing for unknown chars)."""
    return glyph.lit == notdef_lit or (not glyph.lit and notdef_lit == ())


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


# Sentinel cached in `glyphs` for a char proven missing (notdef) — avoids
# re-rasterizing a known miss on every draw tick.
_MISSING = HiresGlyph(width=0, height=0, advance=0, bearing_x=0, bearing_y=0, lit=())


@dataclass(frozen=True)
class HiresFont:
    """A loaded TTF/OTF font at one specific pixel size.

    `glyphs` maps each rasterized character to its `HiresGlyph`, seeded
    eagerly by `_rasterize` for the common charset and grown lazily by
    `resolve_glyph` for anything outside it. Characters this font truly
    lacks (detected via the notdef fingerprint) fall back to `'?'` at
    render time.
    """

    name: str
    size: int
    ascent: int
    descent: int
    line_height: int
    glyphs: dict[str, HiresGlyph] = field(default_factory=dict)
    threshold: int = THRESHOLD
    notdef_lit: tuple[tuple[int, int], ...] = ()
    pil_font: Any = field(default=None, compare=False, repr=False)

    def resolve_glyph(self, ch: str) -> HiresGlyph | None:
        """Glyph for `ch` via the resolution ladder.

        Order: (1) cached hit — a real glyph returns immediately; a
        cached `_MISSING` sentinel (this font proved it lacks `ch` on a
        prior call) skips straight to rung 2 rather than short-circuiting
        to None, since a repeat lookup must still get a chance at DejaVu
        → (2) the ASCII look-alike table for typographic codepoints that
        substitute silently (e.g. U+2212 MINUS SIGN -> '-') — checked
        BEFORE lazy rasterization so a font that happens to ship its own
        (differently-advanced) real glyph for that codepoint doesn't
        desync width math from the substituted glyph elsewhere in the
        pipeline → (3) lazily rasterize an unseen char in THIS font and
        cache the result, treating a notdef/empty result as MISSING →
        (4) DejaVu Sans, rasterized at this font's own pixel size — real
        arrows/math/currency/punctuation glyphs the chosen font lacks.
        Returns None only when DejaVu ALSO lacks `ch`; that ultimately
        draws '?' (rung 3, a future task).
        """
        glyph = self.glyphs.get(ch)
        if glyph is not None and glyph is not _MISSING:
            return glyph
        if glyph is None:
            alt = _ASCII_GLYPH_FALLBACKS.get(ch)
            if alt is not None:
                return self.glyphs.get(alt)
            if self.pil_font is not None and ch:
                glyph = _rasterize_glyph(
                    self.pil_font, ch, self.ascent, self.descent, self.threshold
                )
                if _is_notdef(glyph, self.notdef_lit):
                    self.glyphs[ch] = _MISSING  # cache the miss (sentinel)
                else:
                    self.glyphs[ch] = glyph  # cache the hit
                    return glyph
        # Rung 2: DejaVu fallback. Not itself cached per-font (a cached
        # _MISSING here only records "rung 1 lacks it"), but `_dejavu_glyph`
        # has its own lru_cache so a repeat lookup is a dict hit, not a
        # re-rasterize.
        return _dejavu_glyph(ch, self.size, self.ascent, self.descent, self.threshold)


# Plugin-contributed fonts: ``namespace.name`` -> absolute path to the font
# file. Populated by the plugin loader's commit; will be consulted by
# _find_font_path ahead of the user + bundled dirs (wired in C4).
# Cleared (dotted keys) by reset_plugins().
_PLUGIN_FONTS: dict[str, Path] = {}


def _find_font_path(name: str) -> Path | None:
    """Look up a font by name: plugin fonts first, then user + bundled dirs.

    Plugin fonts (namespaced, e.g. ``acme.Brand``) win because their names
    cannot collide with built-in/user font names. A registered-but-missing
    plugin path returns ``None`` (treated as "not found", same as the dir
    scan), so a broken plugin font surfaces as ``UnknownFontError`` rather
    than crashing. User dir then wins over bundled on collisions. Tries
    ``.otf`` first, then ``.ttf``.
    """
    plugin_path = _PLUGIN_FONTS.get(name)
    if plugin_path is not None:
        return plugin_path if plugin_path.exists() else None
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
    notdef = _rasterize_glyph(pil_font, _NOTDEF_PROBE, ascent, descent, threshold)
    notdef_lit = notdef.lit
    chars = (
        string.printable
        + EXTENDED_LATIN
        + EXTENDED_PUNCTUATION
        + GEOMETRIC_SHAPES
        + SYMBOLS
    )
    glyphs: dict[str, HiresGlyph] = {}
    for ch in chars:
        g = _rasterize_glyph(pil_font, ch, ascent, descent, threshold)
        # Prune eager notdef glyphs: GEOMETRIC_SHAPES (▲▼●○◆◇) rasterize to
        # a box in fonts that lack them — pre-ladder this WAS the tofu. Skip
        # ASCII space/control chars (string.printable) — their empty raster
        # is a legitimate glyph, not a miss.
        if _is_notdef(g, notdef_lit) and ch not in string.printable:
            continue
        glyphs[ch] = g
    return HiresFont(
        name=name,
        size=size,
        ascent=ascent,
        descent=descent,
        line_height=ascent + descent,
        glyphs=glyphs,
        threshold=threshold,
        notdef_lit=notdef_lit,
        pil_font=pil_font,
    )


# Cache cap. A real config would have at most a handful of distinct
# (name, size, threshold) combos — bigsign deployments typically use
# 2-4 fonts. 16 leaves comfortable headroom while bounding memory if
# someone misconfigures (e.g. animated `font_size` pulses) or a test
# suite spawns many one-off entries. Each entry is ~100-300 KB
# (rasterized glyph dict).
_FONT_CACHE_MAXSIZE: int = 16

# Bundled DejaVu Sans TTF — the glyph ladder's rung 2 (Task 2). Covers
# Latin/Cyrillic/Greek plus a wide swath of arrows, math, currency, and
# punctuation that many display/hires fonts don't ship. See
# THIRD_PARTY_NOTICES.md for licensing.
_DEJAVU_PATH: Path = Path(__file__).parent.parent / "assets" / "DejaVuSans.ttf"


@functools.lru_cache(maxsize=_FONT_CACHE_MAXSIZE)
def _dejavu_pil(size: int) -> Any:
    """DejaVu Sans PIL font at `size`, or None if the asset is missing.

    Degrades gracefully — a stripped-down install (e.g. someone deletes
    `src/led_ticker/assets/DejaVuSans.ttf` from a vendored copy) just loses
    rung 2; rung 1 and the eventual '?' fallback are unaffected.
    """
    try:
        return ImageFont.truetype(str(_DEJAVU_PATH), size)
    except OSError:
        logging.getLogger(__name__).warning(
            "DejaVu fallback font unavailable at %s — glyph ladder rung 2 disabled",
            _DEJAVU_PATH,
        )
        return None


@functools.lru_cache(maxsize=2048)
def _dejavu_glyph(
    ch: str, size: int, ascent: int, descent: int, threshold: int
) -> HiresGlyph | None:
    """Rasterize `ch` from DejaVu Sans at `size`/`threshold`, or None if
    DejaVu also lacks it (e.g. CJK ideographs — DejaVu is Latin/Cyrillic/
    Greek-focused).

    `ascent`/`descent` are the CALLING font's metrics — folded into the
    cache key (alongside `size`/`threshold`) purely to mirror
    `HiresFont`'s identity; the actual raster uses DejaVu's own metrics
    (`pil.getmetrics()`) so glyph shape/position is internally consistent
    regardless of which font missed the char. Cached across all fonts —
    `size` and `threshold` alone already determine the DejaVu render.
    """
    pil = _dejavu_pil(size)
    if pil is None:
        return None
    d_ascent, d_descent = pil.getmetrics()
    notdef = _rasterize_glyph(pil, _NOTDEF_PROBE, d_ascent, d_descent, threshold)
    g = _rasterize_glyph(pil, ch, d_ascent, d_descent, threshold)
    if _is_notdef(g, notdef.lit):
        return None
    return g


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
