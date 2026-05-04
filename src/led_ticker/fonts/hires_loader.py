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
EXTENDED_LATIN: str = "àáâãäåæçèéêëìíîïñòóôõöøùúûüýÿ" "ÀÁÂÃÄÅÆÇÈÉÊËÌÍÎÏÑÒÓÔÕÖØÙÚÛÜÝŸ"


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


def _rasterize_glyph(pil_font: Any, ch: str) -> HiresGlyph:
    """Render a single character to a binarized HiresGlyph.

    Uses Pillow's `ImageFont.getbbox` to size the glyph, draws into
    a grayscale image, then thresholds to 1-bit. Lit pixel coords
    are bbox-relative (0,0 is glyph top-left).
    """
    bbox = pil_font.getbbox(ch)  # (x0, y0, x1, y1) in pixel space
    if bbox is None:
        # Whitespace or zero-width char — emit empty glyph with advance.
        advance = int(pil_font.getlength(ch))
        return HiresGlyph(
            width=0,
            height=0,
            advance=advance,
            bearing_x=0,
            bearing_y=0,
            lit=(),
        )

    width = max(1, bbox[2] - bbox[0])
    height = max(1, bbox[3] - bbox[1])
    img = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(img)
    # Offset by -bbox[0], -bbox[1] so the glyph fills the image at (0,0).
    draw.text((-bbox[0], -bbox[1]), ch, font=pil_font, fill=255)

    # Use tobytes() instead of img.load(): for mode "L" each byte is the
    # grayscale value, indexable as a flat array. Avoids pyright's union
    # over PixelAccess.__getitem__ return types AND is slightly faster
    # (no per-pixel function call overhead in the inner loop).
    pixels = img.tobytes()
    lit: list[tuple[int, int]] = []
    for dy in range(height):
        row_offset = dy * width
        for dx in range(width):
            if pixels[row_offset + dx] >= THRESHOLD:
                lit.append((dx, dy))

    advance = int(pil_font.getlength(ch))
    return HiresGlyph(
        width=width,
        height=height,
        advance=advance,
        bearing_x=bbox[0],
        bearing_y=-bbox[1],  # bbox[1] is negative (above baseline) in PIL
        lit=tuple(lit),
    )


def _rasterize(path: Path, size: int, name: str) -> HiresFont:
    """Load .otf/.ttf via Pillow at `size` and rasterize all glyphs."""
    pil_font = ImageFont.truetype(str(path), size)
    ascent, descent = pil_font.getmetrics()
    chars = string.printable + EXTENDED_LATIN
    glyphs: dict[str, HiresGlyph] = {}
    for ch in chars:
        glyphs[ch] = _rasterize_glyph(pil_font, ch)
    return HiresFont(
        name=name,
        size=size,
        ascent=ascent,
        descent=descent,
        line_height=ascent + descent,
        glyphs=glyphs,
    )


@functools.cache
def load_hires_font(name: str, size: int) -> HiresFont | None:
    """Load (or fetch from cache) a hi-res font by name and pixel size."""
    path = _find_font_path(name)
    if path is None:
        return None
    return _rasterize(path, size, name)
