"""Section + playlist aggregation for the gif planner."""

from __future__ import annotations

import math

from tools.gif_plan.widgets import (
    canvas_width_logical,
    gif_visit_ms,
    image_visit_ms,
    ticker_message_visit_ms,
    two_row_visit_ms,
)

_WIDGET_DISPATCH = {
    "message": ticker_message_visit_ms,
    "countdown": ticker_message_visit_ms,  # same engine path as message.
    "two_row": two_row_visit_ms,
    "image": image_visit_ms,
    "still": image_visit_ms,
    "gif": gif_visit_ms,
}


def _widget_visit_ms(widget: dict, section: dict, canvas_w: int, display: dict) -> int:
    """Dispatch a single widget to its visit-time computer.
    Returns 0 for widget types the planner doesn't cover yet
    (weather, mlb, crypto, rss_feed, etc) — those have data-fetch
    timing that's not deterministic from config alone."""
    fn = _WIDGET_DISPATCH.get(widget.get("type", ""))
    if fn is None:
        return 0
    return fn(widget, section, canvas_w, display)


def section_total_ms(section: dict, display: dict) -> int | None:
    """Total ms for one section. Returns None for forever_scroll /
    infini_scroll (runtime-dependent — caller flags as info)."""
    mode = section.get("mode", "swap")
    if mode in ("forever_scroll", "infini_scroll"):
        return None
    canvas_w = canvas_width_logical(display, section)
    widgets = section.get("widget", [])
    per_visit = sum(_widget_visit_ms(w, section, canvas_w, display) for w in widgets)
    loop_count = int(section.get("loop_count") or 1)
    return per_visit * loop_count


def playlist_total_ms(config: dict) -> int:
    """Total ms across all swap-mode sections. forever_scroll and
    infini_scroll sections contribute 0 (their durations are
    runtime-dependent)."""
    display = config.get("display", {})
    sections = (config.get("playlist") or {}).get("section") or []
    total = 0
    for s in sections:
        section_ms = section_total_ms(s, display)
        if section_ms is not None:
            total += section_ms
    return total


def recommended_render_duration_s(total_ms: int) -> int:
    """Ceiling-of-seconds + 1 sec buffer to capture the trailing
    transition. Floor of 1 so empty playlists still produce something."""
    return max(1, math.ceil(total_ms / 1000) + 1)
