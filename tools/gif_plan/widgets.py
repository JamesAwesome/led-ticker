"""Per-widget math helpers for the gif planner.

Each function takes raw config dicts (parsed from TOML) and returns
integer ms or pixel values. No led_ticker engine import — the tool
works on raw config data.
"""

from __future__ import annotations

import math
import re

# BDF font alias → cell width in pixels. Covers the canonical aliases
# used across the demo configs. Unknown aliases fall back to 6.
_BDF_CELL_WIDTH = {
    "5x8": 5,
    "6x12": 6,
    "7x13": 7,
    "FONT_SMALL": 5,
    "FONT_DEFAULT": 6,
}

# Pattern matching :slug: inline emoji. Each slug renders as an 8-px
# sprite by default; the band cap may scale this up but 8 is a safe
# baseline for the planner.
_EMOJI_SPRITE_WIDTH = 8
_EMOJI_PATTERN = re.compile(r":[a-z0-9_]+:")


def canvas_width_logical(display: dict, section: dict) -> int:
    """Compute the section's logical canvas width in pixels.

    Formula: (display.cols × display.chain) / scale, where scale =
    section.scale OR display.default_scale OR 1.

    Caveat: pixel_mapper-based configs (e.g., bigsign U-mapper) have
    a transformed layout this naive formula gets wrong. Callers
    should flag pixel_mapper presence at the section level.
    """
    cols = int(display.get("cols", 0))
    chain = int(display.get("chain", 1))
    scale = int(section.get("scale") or display.get("default_scale") or 1)
    if scale <= 0:
        scale = 1
    return (cols * chain) // scale


def estimate_content_width_logical(
    text: str,
    font: str = "5x8",
    font_size: int | None = None,
) -> int:
    """Estimate the rendered width of `text` in logical pixels.

    BDF fonts: `len × cell_width` from `_BDF_CELL_WIDTH`. Inline
    `:slug:` emoji counted as 8 logical px each.

    Hi-res fonts (anything not in the BDF map): `len × ceil(font_size
    × 0.55)`. The 0.55 ratio is an Inter-Bold-ish approximation —
    conservative (slight overestimate) so "will it fit in
    render-duration" checks err on the safe side. Caller must pass
    `font_size` for hi-res fonts.
    """
    if not text:
        return 0

    # Count inline emoji separately — each is 8 px regardless of font.
    emoji_count = len(_EMOJI_PATTERN.findall(text))
    stripped = _EMOJI_PATTERN.sub("", text)

    if font in _BDF_CELL_WIDTH:
        cell_w = _BDF_CELL_WIDTH[font]
    elif font_size is not None:
        cell_w = math.ceil(font_size * 0.55)
    else:
        # Unknown font, no size given — fall back to default cell width.
        cell_w = 6

    return emoji_count * _EMOJI_SPRITE_WIDTH + len(stripped) * cell_w
