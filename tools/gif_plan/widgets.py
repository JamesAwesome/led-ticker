"""Per-widget math helpers for the gif planner.

Each function takes raw config dicts (parsed from TOML) and returns
integer ms or pixel values. No led_ticker engine import — the tool
works on raw config data.
"""

from __future__ import annotations

import math
import re
from pathlib import Path

try:
    from PIL import Image as PILImage
except ImportError:  # pragma: no cover
    PILImage = None  # Pillow is in the repo env; guard for portability.

# BDF font alias → cell width in pixels. Covers the canonical aliases
# from src/led_ticker/fonts/__init__.py. Unknown aliases fall back to 6.
_BDF_CELL_WIDTH = {
    "5x8": 5,
    "6x10": 6,
    "6x12": 6,
    "7x13": 7,
}

# Pattern matching :slug: inline emoji. Mirrors src/led_ticker/pixel_emoji.py
# EMOJI_PATTERN: lowercase letters + underscore, no digits. Each slug
# renders as an 8-px sprite by default; the band cap may scale this up
# but 8 is a safe baseline for the planner.
_EMOJI_SPRITE_WIDTH = 8
_EMOJI_PATTERN = re.compile(r":[a-z_]+:")


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


def ticker_message_visit_ms(
    widget: dict,
    section: dict,
    canvas_w: int,
) -> int:
    """Visit time in ms for a TickerMessage widget.

    Three paths:
      - text_wrap=True: marquee. visit = max(loops × cycle_ms,
        hold × 1000).
      - Text overflow (content_w > canvas_w): single-pass scroll.
        visit = (canvas_w + content_w) × scroll_step_ms.
      - Static fit: hold_time × 1000.
    """
    font = widget.get("font", "5x8")
    font_size = widget.get("font_size")
    step_ms = int(section.get("scroll_step_ms") or 50)
    hold_ms = int(float(section.get("hold_time") or 0) * 1000)

    text_wrap = bool(widget.get("text_wrap", False))
    if text_wrap:
        sep = widget.get("text_separator") or " • "
        cycle_px = estimate_content_width_logical(
            widget.get("text", ""), font, font_size
        ) + estimate_content_width_logical(sep, font, font_size)
        cycle_ms = cycle_px * step_ms
        loops = int(widget.get("text_loops") or 0)
        loops_ms = loops * cycle_ms
        return max(loops_ms, hold_ms)

    content_w = estimate_content_width_logical(widget.get("text", ""), font, font_size)
    if content_w > canvas_w:
        return (canvas_w + content_w) * step_ms
    return hold_ms


def two_row_visit_ms(
    widget: dict,
    section: dict,
    canvas_w: int,
) -> int:
    """Visit time in ms for a TwoRowMessage widget.

    Branches on bottom_text_scroll, bottom_text_wrap, and overflow:
      - bottom_text_scroll='scroll_through': max(loops × cycle_ms,
        hold × 1000). cycle = canvas_w + bottom_width.
      - bottom_text_wrap=True: max(loops × cycle_ms, hold × 1000).
        cycle = bottom_width + separator_width.
      - Default + overflow: (canvas_w + bottom_width) × step_ms.
      - Default + fits: hold_time × 1000.
    """
    font = widget.get("bottom_font") or widget.get("font", "5x8")
    font_size = widget.get("bottom_font_size") or widget.get("font_size")
    bottom_text = widget.get("bottom_text", "")
    step_ms = int(section.get("scroll_step_ms") or 50)
    hold_ms = int(float(section.get("hold_time") or 0) * 1000)
    bottom_w = estimate_content_width_logical(bottom_text, font, font_size)

    if widget.get("bottom_text_scroll") == "scroll_through":
        cycle_px = canvas_w + bottom_w
        cycle_ms = cycle_px * step_ms
        loops = int(widget.get("bottom_text_loops") or 0) or 1
        return max(loops * cycle_ms, hold_ms)

    if widget.get("bottom_text_wrap"):
        sep = widget.get("bottom_text_separator") or " • "
        sep_w = estimate_content_width_logical(sep, font, font_size)
        cycle_ms = (bottom_w + sep_w) * step_ms
        loops = int(widget.get("bottom_text_loops") or 0)
        return max(loops * cycle_ms, hold_ms)

    if bottom_w > canvas_w:
        return (canvas_w + bottom_w) * step_ms
    return hold_ms


def image_visit_ms(
    widget: dict,
    section: dict,
    canvas_w: int,
) -> int:
    """Visit time in ms for an image widget.

    If `bottom_text` is set → two-row text-overlay path (delegates
    to two_row_visit_ms shape). Otherwise: hold_seconds × 1000.

    NOTE: image widget `hold_seconds` is a widget-level field
    (unlike message/two_row's section-level `hold_time`). We read
    widget.hold_seconds here, not section.hold_time.
    """
    if widget.get("bottom_text"):
        # Inject a synthetic section dict so two_row's math can run
        # using hold_seconds (widget) instead of hold_time (section).
        synth_section = dict(section)
        synth_section["hold_time"] = widget.get("hold_seconds") or 0.0
        return two_row_visit_ms(widget, synth_section, canvas_w)
    return int(float(widget.get("hold_seconds") or 0) * 1000)


def _gif_frame_durations_ms(path: Path) -> list[int]:
    """Read per-frame durations from a gif. Returns ms per frame.

    Raises FileNotFoundError or generic Exception on bad input.
    """
    if PILImage is None:
        raise RuntimeError("Pillow not available")
    durations: list[int] = []
    with PILImage.open(path) as im:
        n = getattr(im, "n_frames", 1)
        for i in range(n):
            im.seek(i)
            dur = im.info.get("duration", 100)
            durations.append(int(dur))
    return durations


def gif_visit_ms(
    widget: dict,
    section: dict,
    canvas_w: int,
) -> int:
    """Visit time in ms for a gif widget.

    gif_loops > 0: sum(frame_durations) × gif_loops.
    gif_loops == 0: hold_seconds × 1000 (PR-64 unified behavior).

    If the path can't be resolved → fall back to 100ms × 10 frames =
    1000 ms per loop. Caller flags this separately via the warning
    pathway; this function doesn't raise.
    """
    if widget.get("bottom_text"):
        # Same delegation as image_visit_ms for the text-overlay case.
        synth_section = dict(section)
        synth_section["hold_time"] = widget.get("hold_seconds") or 0.0
        return two_row_visit_ms(widget, synth_section, canvas_w)

    loops = int(widget.get("gif_loops") or 0)
    if loops == 0:
        return int(float(widget.get("hold_seconds") or 0) * 1000)

    path = Path(widget.get("path", ""))
    try:
        durations = _gif_frame_durations_ms(path)
        per_loop = sum(durations)
    except Exception:
        per_loop = 100 * 10  # 1000 ms fallback for unresolvable paths.
    return per_loop * loops
