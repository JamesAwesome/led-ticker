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
    font: str = "6x12",
    font_size: int | None = None,
    scale: int = 1,
) -> int:
    """Estimate the rendered width of `text` in logical pixels.

    BDF fonts: `len × cell_width` from `_BDF_CELL_WIDTH`. Inline
    `:slug:` emoji counted as 8 logical px each. BDF metrics are
    already logical, so `scale` is ignored.

    Hi-res fonts (anything not in the BDF map): per-char width is
    `ceil(font_size × 0.55)` REAL pixels. The 0.55 ratio is an
    Inter-Bold-ish approximation — conservative (slight overestimate)
    so "will it fit in render-duration" checks err on the safe side.
    Caller must pass `font_size` for hi-res fonts. Real-pixel total is
    ceil-divided by `scale` to convert to logical pixels (mirrors
    `drawing.get_text_width`'s real→logical conversion).
    """
    if not text:
        return 0

    # Count inline emoji separately — each is 8 px regardless of font.
    emoji_count = len(_EMOJI_PATTERN.findall(text))
    stripped = _EMOJI_PATTERN.sub("", text)

    if font in _BDF_CELL_WIDTH:
        # BDF: cell width is already logical pixels.
        cell_w = _BDF_CELL_WIDTH[font]
        return emoji_count * _EMOJI_SPRITE_WIDTH + len(stripped) * cell_w

    if font_size is not None:
        # Hi-res: cell width is real pixels; convert to logical via
        # ceil-division by scale.
        cell_w_real = math.ceil(font_size * 0.55)
        text_w_real = len(stripped) * cell_w_real
        text_w_logical = -(-text_w_real // max(1, scale))
        return emoji_count * _EMOJI_SPRITE_WIDTH + text_w_logical

    # Unknown font, no size given — fall back to default cell width
    # (treated as logical, matches the BDF branch).
    cell_w = 6
    return emoji_count * _EMOJI_SPRITE_WIDTH + len(stripped) * cell_w


# Engine defaults — these MUST track src/led_ticker. A section that omits
# `hold_time` holds for SectionConfig.hold_time (config.py) seconds, NOT 0.
# `message`/`countdown`/image text default to FONT_DEFAULT (6x12); a
# standalone `two_row` defaults to FONT_SMALL (5x8) — see two_row.py /
# _image_base.py / message.py.
_SECTION_HOLD_DEFAULT_S = 3.0
_FONT_DEFAULT = "6x12"  # message / countdown / image text overlay
_FONT_SMALL = "5x8"  # standalone two_row
# Widget-level `scroll_speed_ms` is floored at MIN_SCROLL_SPEED_MS in the
# engine (_image_base.py); section `scroll_step_ms` is not.
_MIN_SCROLL_SPEED_MS = 20

# `text_align="auto"` resolves against `image_align` — mirrors
# AUTO_TEXT_ALIGN_FOR_IMAGE in _image_base.py.
_AUTO_TEXT_ALIGN = {"left": "right", "right": "left", "center": "scroll_over"}


def _section_scale(section: dict, display: dict | None = None) -> int:
    """Return the effective scale for this section (>= 1)."""
    if display is None:
        display = {}
    scale = int(section.get("scale") or display.get("default_scale") or 1)
    return max(1, scale)


def _section_hold_ms(section: dict) -> int:
    """Per-visit hold for message/two_row, in ms.

    The engine's `SectionConfig.hold_time` defaults to 3.0s when the TOML
    omits it (config.py); an explicit `hold_time = 0` is honoured.
    """
    return int(float(section.get("hold_time", _SECTION_HOLD_DEFAULT_S)) * 1000)


def _section_step_ms(section: dict) -> int:
    """Per-tick scroll cadence for STANDALONE message/two_row widgets:
    section-level `scroll_step_ms` (engine default 50)."""
    return int(section.get("scroll_step_ms") or 50)


def _widget_tick_ms(widget: dict) -> int:
    """Per-tick cadence for image/gif text overlays: the WIDGET-level
    `scroll_speed_ms` (engine default 50), floored at MIN_SCROLL_SPEED_MS.

    Distinct from a section's `scroll_step_ms` — `_play_with_text` /
    `_play_with_two_row_text` tick on `max(MIN_SCROLL_SPEED_MS,
    self.scroll_speed_ms)`, never on the section knob (config.py:90-93).
    """
    return max(_MIN_SCROLL_SPEED_MS, int(widget.get("scroll_speed_ms") or 50))


def _single_row_scrolls(widget: dict) -> bool:
    """True when an image/gif's single-row caption marquees.

    No `text` → nothing to scroll. `bottom_text` → the two-row path
    handles it instead. `text_align="auto"` resolves against
    `image_align` (default "center" → "scroll_over"), so a captioned
    image with no explicit alignment DOES scroll by default.
    """
    if not widget.get("text") or widget.get("bottom_text"):
        return False
    align = widget.get("text_align", "auto")
    if align == "auto":
        align = _AUTO_TEXT_ALIGN.get(widget.get("image_align", "center"), "scroll_over")
    return align in ("scroll", "scroll_over")


def _single_row_floor_ticks(widget: dict, canvas_w: int, scale: int) -> int:
    """Marquee-traversal floor (in ticks) for a single-row image caption.

    Mirrors `_play_with_text`: non-wrap one loop = (canvas_w +
    text_width) ticks; wrap mode one loop = (text_width + sep_width).
    `text_loops` raises the floor; the implicit minimum is 1.
    """
    text = widget.get("text", "")
    font = widget.get("font", _FONT_DEFAULT)
    font_size = widget.get("font_size")
    text_w = estimate_content_width_logical(text, font, font_size, scale)
    if widget.get("text_wrap"):
        sep = widget.get("text_separator") or " • "
        sep_w = estimate_content_width_logical(sep, font, font_size, scale)
        ticks_per_loop = text_w + sep_w
    else:
        ticks_per_loop = canvas_w + text_w
    min_loops = max(1, int(widget.get("text_loops") or 0))
    return min_loops * ticks_per_loop


def ticker_message_visit_ms(
    widget: dict,
    section: dict,
    canvas_w: int,
    display: dict | None = None,
) -> int:
    """Visit time in ms for a TickerMessage widget.

    Three paths:
      - text_wrap=True: marquee. visit = max(loops × cycle_ms,
        hold × 1000).
      - Text overflow (content_w > canvas_w): single-pass scroll.
        Engine `_swap_and_scroll` scrolls only the visible overflow,
        not a full marquee: scroll = (content_w - canvas_w) ×
        scroll_step_ms, bracketed by pre/post-scroll holds.
      - Static fit: hold_time × 1000.
    """
    font = widget.get("font", _FONT_DEFAULT)
    font_size = widget.get("font_size")
    step_ms = _section_step_ms(section)
    hold_ms = _section_hold_ms(section)
    scale = _section_scale(section, display)

    text_wrap = bool(widget.get("text_wrap", False))
    if text_wrap:
        sep = widget.get("text_separator") or " • "
        cycle_px = estimate_content_width_logical(
            widget.get("text", ""), font, font_size, scale
        ) + estimate_content_width_logical(sep, font, font_size, scale)
        cycle_ms = cycle_px * step_ms
        loops = int(widget.get("text_loops") or 0)
        loops_ms = loops * cycle_ms
        return max(loops_ms, hold_ms)

    content_w = estimate_content_width_logical(
        widget.get("text", ""), font, font_size, scale
    )
    if content_w > canvas_w:
        # Engine in `_swap_and_scroll` overflow branch: pre-scroll hold
        # + scroll + post-scroll hold (each hold = hold_time × 1000 ms).
        # The engine stops at `stop_pos = -(cursor_pos - canvas.width)`,
        # so total scroll distance is (content_w - canvas_w) pixels —
        # NOT the classic marquee (content_w + canvas_w).
        scroll_ms = (content_w - canvas_w) * step_ms
        return hold_ms + scroll_ms + hold_ms
    return hold_ms


def two_row_visit_ms(
    widget: dict,
    section: dict,
    canvas_w: int,
    display: dict | None = None,
    *,
    include_pre_post_hold: bool = True,
) -> int:
    """Visit time in ms for a TwoRowMessage widget.

    Branches on bottom_text_scroll, bottom_text_wrap, and overflow:
      - bottom_text_scroll='scroll_through': max(loops × cycle_ms,
        hold × 1000). cycle = canvas_w + bottom_width.
      - bottom_text_wrap=True: max(loops × cycle_ms, hold × 1000).
        cycle = bottom_width + separator_width.
      - Default + overflow:
          * Standalone TwoRowMessage widget (include_pre_post_hold=True):
            engine `_swap_and_scroll` only traverses the overflow:
            (bottom_width - canvas_w) × step_ms, bracketed by
            pre/post-scroll holds.
          * Image/gif two-row text overlay (include_pre_post_hold=False):
            `_play_with_two_row_text` runs a full marquee:
            (canvas_w + bottom_width) × step_ms, floor-extended to one
            full traversal even if the source's natural duration is
            shorter.
      - Default + fits: hold_time × 1000.

    `include_pre_post_hold`: set False when this helper is invoked
    from `image_visit_ms` / `gif_visit_ms` — those widgets use
    `_play_with_two_row_text` which runs for a single n_ticks budget
    (no separate pre/post-scroll holds) and uses different scroll
    math (full marquee, not overflow-only).
    """
    if include_pre_post_hold:
        # Standalone TwoRowMessage: ticks on the SECTION's scroll_step_ms
        # and defaults to FONT_SMALL (two_row.py: `font = FONT_SMALL`).
        step_ms = _section_step_ms(section)
        default_font = _FONT_SMALL
    else:
        # Image/gif text overlay (`_play_with_two_row_text`): ticks on the
        # WIDGET's scroll_speed_ms and inherits the image widget's
        # FONT_DEFAULT (_image_base.py: `font = FONT_DEFAULT`).
        step_ms = _widget_tick_ms(widget)
        default_font = _FONT_DEFAULT
    font = widget.get("bottom_font") or widget.get("font", default_font)
    font_size = widget.get("bottom_font_size") or widget.get("font_size")
    bottom_text = widget.get("bottom_text", "")
    hold_ms = _section_hold_ms(section)
    scale = _section_scale(section, display)
    bottom_w = estimate_content_width_logical(bottom_text, font, font_size, scale)

    if widget.get("bottom_text_scroll") == "scroll_through":
        cycle_px = canvas_w + bottom_w
        cycle_ms = cycle_px * step_ms
        loops = int(widget.get("bottom_text_loops") or 0) or 1
        return max(loops * cycle_ms, hold_ms)

    if widget.get("bottom_text_wrap"):
        sep = widget.get("bottom_text_separator") or " • "
        sep_w = estimate_content_width_logical(sep, font, font_size, scale)
        cycle_ms = (bottom_w + sep_w) * step_ms
        loops = int(widget.get("bottom_text_loops") or 0)
        return max(loops * cycle_ms, hold_ms)

    if bottom_w > canvas_w:
        if include_pre_post_hold:
            # Standalone TwoRowMessage: engine `_swap_and_scroll` only
            # traverses the visible overflow (bottom_w - canvas_w pixels),
            # bracketed by pre/post-scroll holds. NOT a full marquee.
            scroll_ms = (bottom_w - canvas_w) * step_ms
            return hold_ms + scroll_ms + hold_ms
        # Image/gif two-row text overlay: `_play_with_two_row_text` runs
        # a FULL off-right→off-left marquee. ticks_per_loop in
        # _image_base.py line ~1554 is (canvas_w + bottom_width); the
        # marquee-floor extends n_ticks to at least one full traversal.
        scroll_ms = (canvas_w + bottom_w) * step_ms
        return max(scroll_ms, hold_ms)
    return hold_ms


def image_visit_ms(
    widget: dict,
    section: dict,
    canvas_w: int,
    display: dict | None = None,
) -> int:
    """Visit time in ms for an image widget.

    - `bottom_text` set → two-row text-overlay path (delegates to
      two_row_visit_ms with the image's widget-level tick rate / font).
    - Single-row scrolling caption (`text` set, resolved
      `text_align ∈ {scroll, scroll_over}` — the default for a
      center-aligned image) → `_play_with_text`'s marquee floor:
      max(hold_seconds, one full traversal) at scroll_speed_ms cadence.
    - Otherwise (no text, or static left/right/center text) →
      hold_seconds × 1000.

    NOTE: image widget `hold_seconds` is a widget-level field (default
    5.0 from `StillImage`, unlike message/two_row's section-level
    `hold_time`). We read widget.hold_seconds here, not section.hold_time.
    """
    if widget.get("bottom_text"):
        # Inject a synthetic section dict so two_row's math can run
        # using hold_seconds (widget) instead of hold_time (section).
        synth_section = dict(section)
        synth_section["hold_time"] = widget.get("hold_seconds", 5.0)
        return two_row_visit_ms(
            widget, synth_section, canvas_w, display, include_pre_post_hold=False
        )

    hold_ms = int(float(widget.get("hold_seconds", 5.0)) * 1000)
    if _single_row_scrolls(widget):
        # `_play_with_text`: n_ticks starts from hold_seconds, then the
        # marquee-traversal floor extends it to at least one full pass.
        tick_ms = _widget_tick_ms(widget)
        scale = _section_scale(section, display)
        source_ticks = max(1, hold_ms // tick_ms)
        floor_ticks = _single_row_floor_ticks(widget, canvas_w, scale)
        return max(source_ticks, floor_ticks) * tick_ms
    return hold_ms


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
    display: dict | None = None,
) -> int:
    """Visit time in ms for a gif widget.

    gif_loops > 0: sum(frame_durations) × gif_loops.
    gif_loops == 0: section.hold_time × 1000 (PR-64 behavior).
    Default gif_loops is 1 (from `GifPlayer`).

    GifPlayer has no widget-level `hold_seconds` — when `gif_loops=0`
    the engine reads SECTION `hold_time` to compute n_loops.

    If the path can't be resolved → fall back to 100ms × 10 frames =
    1000 ms per loop. Logged via narrow OSError/RuntimeError catch.

    `bottom_text` → two-row overlay. A single-row scrolling caption
    (`text` + resolved scroll alignment) extends the gif's natural
    duration to `_play_with_text`'s marquee floor, same as image.
    """
    if widget.get("bottom_text"):
        # Two-row text overlay: gif's effective hold is section.hold_time.
        return two_row_visit_ms(
            widget, section, canvas_w, display, include_pre_post_hold=False
        )

    loops = int(widget.get("gif_loops", 1))
    if loops == 0:
        # PR-64: the engine reads SECTION hold_time (default 3.0s).
        total_ms = _section_hold_ms(section)
    else:
        path = Path(widget.get("path", ""))
        try:
            durations = _gif_frame_durations_ms(path)
            per_loop = sum(durations)
        except (FileNotFoundError, PermissionError, OSError, RuntimeError):
            per_loop = 100 * 10  # 1000 ms fallback for unresolvable paths.
        total_ms = per_loop * loops

    if _single_row_scrolls(widget):
        # `_play_with_text`: n_ticks = total_ms // tick_ms, then the
        # marquee-traversal floor extends it to at least one full pass.
        tick_ms = _widget_tick_ms(widget)
        scale = _section_scale(section, display)
        source_ticks = max(1, total_ms // tick_ms)
        floor_ticks = _single_row_floor_ticks(widget, canvas_w, scale)
        return max(source_ticks, floor_ticks) * tick_ms
    return total_ms
