"""CLI entry point for the led-ticker demo-gif planner.

Usage:
    uv run python tools/gif_plan/plan.py <config.toml> [--json]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Mirror tools/render_demo/render.py — make the repo root importable so
# `from tools.gif_plan.x import y` works when invoked as a script.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Python 3.11+ has tomllib in stdlib.
try:
    import tomllib
except ImportError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]

from tools.gif_plan.flags import check_all  # noqa: E402
from tools.gif_plan.totals import (  # noqa: E402
    playlist_total_ms,
    recommended_render_duration_s,
    section_total_ms,
)
from tools.gif_plan.widgets import (  # noqa: E402
    canvas_width_logical,
    gif_visit_ms,
    image_visit_ms,
    ticker_message_visit_ms,
    two_row_visit_ms,
)

# Exit codes. 0/1/2 come from flag severity (see `_exit_code`); 3 is
# reserved for tool/usage errors (missing file, malformed TOML) so a
# caller can tell "config has warnings" (1/2) apart from "tool failed".
EXIT_TOOL_ERROR = 3


class PlanError(Exception):
    """Recoverable, user-facing planner error (bad path / malformed TOML)."""


_HEADER_RE = re.compile(r"^\s*#\s*render-duration\s*:\s*(\d+)\s*$", re.MULTILINE)


def _read_render_duration_header(text: str) -> int | None:
    m = _HEADER_RE.search(text)
    return int(m.group(1)) if m else None


_WIDGET_DISPATCH = {
    "message": ticker_message_visit_ms,
    "countdown": ticker_message_visit_ms,
    "two_row": two_row_visit_ms,
    "image": image_visit_ms,
    "still": image_visit_ms,
    "gif": gif_visit_ms,
}


def _summarize_widget(
    widget: dict, section: dict, canvas_w: int, display: dict
) -> dict:
    fn = _WIDGET_DISPATCH.get(widget.get("type", ""))
    if fn is None:
        return {
            "type": widget.get("type", "unknown"),
            "visit_ms": 0,
            "note": "widget type not modelled deterministically",
        }
    visit_ms = fn(widget, section, canvas_w, display)
    return {"type": widget.get("type"), "visit_ms": visit_ms}


def _resolve_widget_paths(config: dict, config_dir: Path) -> None:
    """Rewrite non-absolute gif/image widget paths to be relative to the
    config file's directory, in place.

    Mirrors the engine exactly (`app.py:652-659`): file-backed widgets
    take config-relative paths. Without this, `gif_visit_ms` would
    `Path(widget["path"])` against the CALLER's cwd — pinned demos use
    paths like `../../../config/assets/foo.gif` that only resolve from
    the config dir, so every such gif would silently hit the
    1000ms/loop fallback and the predicted duration would be wrong.
    """
    # SPIKE POC: the resolution RULE is now imported from the engine's
    # dependency-free leaf instead of hand-mirrored here. One definition
    # both `app._build_widget` and this function obey — the round-3
    # CRITICAL bug (planner re-derived it, resolved against cwd) becomes
    # structurally impossible. The leaf is pure stdlib, so this import
    # costs microseconds (measured: no PIL/aiohttp/asyncio pulled).
    from led_ticker._planning_contract import resolve_widget_path

    sections = (config.get("playlist") or {}).get("section") or []
    for section in sections:
        for widget in section.get("widget", []):
            if widget.get("type") not in ("gif", "image", "still"):
                continue
            raw_path = widget.get("path")
            if not raw_path:
                continue
            widget["path"] = resolve_widget_path(config_dir, raw_path)


def plan(config_path: Path) -> dict:
    try:
        raw = config_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise PlanError(f"config not found: {config_path}") from exc
    except (IsADirectoryError, PermissionError, OSError) as exc:
        raise PlanError(f"cannot read config {config_path}: {exc}") from exc
    header = _read_render_duration_header(raw)
    try:
        config = tomllib.loads(raw)
    except tomllib.TOMLDecodeError as exc:
        raise PlanError(f"malformed TOML in {config_path}: {exc}") from exc
    _resolve_widget_paths(config, config_path.parent)
    display = config.get("display", {})
    sections_raw = (config.get("playlist") or {}).get("section") or []

    sections_summary: list[dict] = []
    for i, s in enumerate(sections_raw):
        canvas_w = canvas_width_logical(display, s)
        widgets = [
            _summarize_widget(w, s, canvas_w, display) for w in s.get("widget", [])
        ]
        total = section_total_ms(s, display)
        sections_summary.append(
            {
                "index": i,
                "mode": s.get("mode", "swap"),
                "hold_time": s.get("hold_time"),
                "scroll_step_ms": s.get("scroll_step_ms"),
                "loop_count": s.get("loop_count", 1),
                "canvas_w": canvas_w,
                "widgets": widgets,
                "section_total_ms": total,
            }
        )

    total_ms = playlist_total_ms(config)
    flags = check_all(
        config=config,
        playlist_total_ms=total_ms,
        render_duration_header=header,
        sections_summary=sections_summary,
    )

    return {
        "config_path": str(config_path),
        "render_duration_header": header,
        "sections": sections_summary,
        "total_ms": total_ms,
        "recommended_render_duration_s": recommended_render_duration_s(total_ms),
        "flags": flags,
    }


def _exit_code(flags: list[dict]) -> int:
    severities = {f["severity"] for f in flags}
    if "error" in severities:
        return 2
    if "warning" in severities:
        return 1
    return 0


def _human_render(plan_data: dict) -> str:
    """Plain-text summary for terminal use."""
    lines: list[str] = []
    lines.append(f"config: {plan_data['config_path']}")
    lines.append(f"playlist_total: {plan_data['total_ms']}ms")
    lines.append(
        f"recommended_render_duration: {plan_data['recommended_render_duration_s']}s"
    )
    header = plan_data["render_duration_header"]
    if header is not None:
        lines.append(f"header `# render-duration:` found: {header}s")
    lines.append("")
    for s in plan_data["sections"]:
        total = s["section_total_ms"]
        total_str = (
            f"{total}ms"
            if total is not None
            else "runtime-dependent (forever_scroll / loop_count=0)"
        )
        idx = s["index"]
        mode = s["mode"]
        loops = s["loop_count"]
        lines.append(f"section[{idx}] mode={mode} loop_count={loops} → {total_str}")
        for j, w in enumerate(s["widgets"]):
            lines.append(
                f"  widget[{j}] type={w['type']} visit={w.get('visit_ms', 0)}ms"
            )
    if plan_data["flags"]:
        lines.append("")
        lines.append("flags:")
        for f in plan_data["flags"]:
            lines.append(f"  [{f['severity'].upper()}] {f['location']} :: {f['code']}")
            lines.append(f"    {f['message']}")
            lines.append(f"    fix: {f['fix']}")
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser(description="Plan a led-ticker demo gif")
    p.add_argument("config", type=Path, help="Path to the demo config TOML")
    p.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    args = p.parse_args()

    try:
        data = plan(args.config)
    except PlanError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_TOOL_ERROR
    if args.json:
        print(json.dumps(data, indent=2))
    else:
        print(_human_render(data))
    return _exit_code(data["flags"])


if __name__ == "__main__":
    sys.exit(main())
