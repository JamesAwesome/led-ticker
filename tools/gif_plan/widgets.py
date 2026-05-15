"""Per-widget math helpers for the gif planner.

Each function takes raw config dicts (parsed from TOML) and returns
integer ms or pixel values. No led_ticker engine import — the tool
works on raw config data.
"""

from __future__ import annotations


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
