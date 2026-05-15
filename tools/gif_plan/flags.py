"""Heuristic flags for the gif planner.

Each flag is a dict: {severity, location, code, message, fix}.
Severities: info | warning | error. Errors set the CLI exit code 2;
warnings set 1; info-only is 0.
"""

from __future__ import annotations

from tools.gif_plan.totals import recommended_render_duration_s
from tools.gif_plan.widgets import (
    estimate_content_width_logical,
)

SCROLL_STEP_MIN = 20
SCROLL_STEP_MAX = 80


def _flag(severity: str, location: str, code: str, message: str, fix: str) -> dict:
    return {
        "severity": severity,
        "location": location,
        "code": code,
        "message": message,
        "fix": fix,
    }


def check_all(
    *,
    config: dict,
    playlist_total_ms: int,
    render_duration_header: int | None,
    sections_summary: list[dict],
) -> list[dict]:
    """Run every heuristic check and return the combined flag list."""
    flags: list[dict] = []
    flags.extend(_check_render_duration(playlist_total_ms, render_duration_header))
    flags.extend(_check_scroll_steps(config))
    flags.extend(_check_zero_cycles(config))
    flags.extend(_check_pixel_mapper(config))
    flags.extend(_check_loop_count_zero(config))
    return flags


def _check_render_duration(
    playlist_total_ms: int,
    header: int | None,
) -> list[dict]:
    recommended = recommended_render_duration_s(playlist_total_ms)
    if header is None:
        if playlist_total_ms > 0:
            msg = (
                f"No `# render-duration:` header found; recommended value "
                f"is {recommended}."
            )
            fix = (
                f"Add a `# render-duration: {recommended}` comment to the "
                f"top of the TOML."
            )
            return [_flag("info", "playlist", "render_duration_suggestion", msg, fix)]
        return []
    if header * 1000 < playlist_total_ms:
        cut_ms = playlist_total_ms - header * 1000
        msg = (
            f"render-duration: {header} cuts ~{cut_ms}ms of playlist content mid-pass."
        )
        fix = (
            f"Bump to {recommended} (matches the deterministic playlist "
            f"total + 1s buffer)."
        )
        return [_flag("error", "playlist", "mid_pass_cutoff", msg, fix)]
    return []


def _check_scroll_steps(config: dict) -> list[dict]:
    flags: list[dict] = []
    sections = (config.get("playlist") or {}).get("section") or []
    band = f"{SCROLL_STEP_MIN}-{SCROLL_STEP_MAX}ms"
    for i, section in enumerate(sections):
        step = int(section.get("scroll_step_ms") or 50)
        if step < SCROLL_STEP_MIN:
            msg = (
                f"scroll_step_ms={step} below the readable range "
                f"({band}); canonical is 25-30."
            )
            flags.append(
                _flag(
                    "warning",
                    f"section[{i}]",
                    "scroll_step_too_fast",
                    msg,
                    "Raise scroll_step_ms to 25 (canonical) or higher.",
                )
            )
        elif step > SCROLL_STEP_MAX:
            msg = (
                f"scroll_step_ms={step} above the readable range "
                f"({band}); canonical is 25-30."
            )
            flags.append(
                _flag(
                    "warning",
                    f"section[{i}]",
                    "scroll_step_too_slow",
                    msg,
                    "Lower scroll_step_ms to 30 (canonical) or below.",
                )
            )
    return flags


def _check_zero_cycles(config: dict) -> list[dict]:
    """Detect wrap/scroll_through widgets with zero content_width."""
    flags: list[dict] = []
    sections = (config.get("playlist") or {}).get("section") or []
    for i, section in enumerate(sections):
        for j, w in enumerate(section.get("widget", [])):
            wrap = w.get("text_wrap") or w.get("bottom_text_wrap")
            scroll_through = w.get("bottom_text_scroll") == "scroll_through"
            if not (wrap or scroll_through):
                continue
            text = (
                w.get("bottom_text")
                if (w.get("bottom_text_wrap") or scroll_through)
                else w.get("text", "")
            )
            font = w.get("font", "5x8")
            content_w = estimate_content_width_logical(text or "", font)
            if content_w == 0:
                msg = (
                    "Widget has wrap/scroll_through enabled but the relevant "
                    "text is empty — there's no cycle to count."
                )
                flags.append(
                    _flag(
                        "error",
                        f"section[{i}].widget[{j}]",
                        "zero_cycle_width",
                        msg,
                        "Set non-empty text or disable wrap/scroll_through.",
                    )
                )
    return flags


def _check_pixel_mapper(config: dict) -> list[dict]:
    display = config.get("display", {})
    if "pixel_mapper" in display or "pixel_mapper_config" in display:
        msg = (
            "pixel_mapper detected; canvas-width math is approximate for "
            "bigsign-style configs in v1."
        )
        fix = "Sanity-check the recommended render-duration against the visual output."
        return [_flag("info", "display", "pixel_mapper_present", msg, fix)]
    return []


def _check_loop_count_zero(config: dict) -> list[dict]:
    """loop_count=0 means 'loop forever' (itertools.cycle in the engine).
    The planner can't compute a finite duration; surface as info."""
    flags: list[dict] = []
    sections = (config.get("playlist") or {}).get("section") or []
    for i, section in enumerate(sections):
        if section.get("loop_count") == 0:
            msg = (
                "loop_count=0 makes this section loop forever "
                "(itertools.cycle in the engine); playlist total is "
                "runtime-dependent."
            )
            fix = (
                "Set loop_count to a positive integer for deterministic "
                "planning, or accept the runtime-dependent estimate."
            )
            flags.append(
                _flag(
                    "info",
                    f"section[{i}]",
                    "loop_count_zero_runtime",
                    msg,
                    fix,
                )
            )
    return flags
