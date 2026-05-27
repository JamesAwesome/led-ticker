"""Coarse demo-gif duration estimator for the making-a-gif skill.

Single purpose: tell Claude the `--duration` to render a led-ticker
demo with, and flag when a pinned `# render-duration:` header is too
short (the gif would clip and need re-rendering). Deliberately rough —
it models only the dominant timing terms. Precision is not the goal;
not wasting a render is. See
docs/superpowers/specs/2026-05-18-gif-plan-reduction-design.md.
"""

from __future__ import annotations

import math
import re
import sys
import tomllib
from pathlib import Path

_FONT_CELL_W = 6  # FONT_DEFAULT (6x12) cell width, px
_EMOJI_W = 8  # inline :slug: sprite width, px
_DEFAULT_HOLD_S = 3.0  # SectionConfig.hold_time default
_DEFAULT_HOLD_SECONDS = 5.0  # StillImage.hold_time default
_DEFAULT_STEP_MS = 50  # scroll step when a section omits scroll_step_ms
_GIF_FALLBACK_LOOP_MS = 1000  # used when a gif path can't be read

_EMOJI_RE = re.compile(r":[a-z_]+:")
_HEADER_RE = re.compile(r"^\s*#\s*render-duration\s*:\s*(\d+)", re.MULTILINE)

EXIT_OK = 0
EXIT_CUTOFF = 2
EXIT_TOOL_ERROR = 3


class PlanError(Exception):
    """Recoverable tool/usage error (missing or malformed TOML)."""


def _canvas_w(display: dict, section: dict) -> int:
    cols = int(display.get("cols", 64))
    chain = int(display.get("chain", 1))
    scale = int(section.get("scale") or display.get("default_scale") or 1)
    return cols * chain // max(1, scale)


def _content_w(text: str) -> int:
    if not text:
        return 0
    emoji = len(_EMOJI_RE.findall(text))
    stripped = _EMOJI_RE.sub("", text)
    return len(stripped) * _FONT_CELL_W + emoji * _EMOJI_W


def _gif_loop_ms(path: Path) -> int:
    try:
        from PIL import Image
    except ImportError:
        return _GIF_FALLBACK_LOOP_MS
    try:
        with Image.open(path) as im:
            total = 0
            for i in range(getattr(im, "n_frames", 1)):
                im.seek(i)
                total += int(im.info.get("duration", 100))
            return max(1, total)
    except (FileNotFoundError, OSError, ValueError):
        return _GIF_FALLBACK_LOOP_MS


def widget_ms(widget: dict, section: dict, canvas_w: int, config_dir: Path) -> int:
    """Coarse per-widget visit time in ms. Dominant terms only."""
    wtype = widget.get("type", "")
    hold_ms = int(float(section.get("hold_time", _DEFAULT_HOLD_S)) * 1000)
    if wtype in ("message", "countdown", "two_row"):
        text = widget.get("bottom_text") or widget.get("text", "")
        step = int(section.get("scroll_step_ms") or _DEFAULT_STEP_MS)
        overflow = max(0, _content_w(text) - canvas_w)
        return hold_ms + overflow * step
    if wtype in ("image",):
        return int(float(widget.get("hold_time", _DEFAULT_HOLD_SECONDS)) * 1000)
    if wtype == "gif":
        loops = int(widget.get("loops", 1))
        if loops == 0:
            return hold_ms
        p = Path(widget.get("path", ""))
        if not p.is_absolute():
            p = (config_dir / p).resolve()
        return _gif_loop_ms(p) * loops
    return 0  # data-fetch / unknown — runtime-dependent, contributes 0


def total_ms(config: dict, config_dir: Path) -> int:
    display = config.get("display", {})
    sections = (config.get("playlist") or {}).get("section") or []
    total = 0
    for s in sections:
        if s.get("mode", "swap") != "swap" or s.get("loop_count") == 0:
            continue  # forever/infini/loop-forever — runtime-dependent
        cw = _canvas_w(display, s)
        loop = int(s.get("loop_count") or 1)
        per = sum(widget_ms(w, s, cw, config_dir) for w in s.get("widget", []))
        total += per * loop
    return total


def recommended_s(total: int) -> int:
    return max(1, math.ceil(total / 1000) + 1)


def _read_header(raw: str) -> int | None:
    m = _HEADER_RE.search(raw)
    return int(m.group(1)) if m else None


def plan(config_path: Path) -> tuple[int, int | None, int]:
    """Return (recommended_s, header_s_or_None, total_ms)."""
    try:
        raw = config_path.read_text(encoding="utf-8")
    except (FileNotFoundError, IsADirectoryError, PermissionError, OSError) as e:
        raise PlanError(f"cannot read config {config_path}: {e}") from e
    try:
        config = tomllib.loads(raw)
    except tomllib.TOMLDecodeError as e:
        raise PlanError(f"malformed TOML in {config_path}: {e}") from e
    tot = total_ms(config, config_path.parent)
    return recommended_s(tot), _read_header(raw), tot


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: plan.py <config.toml>", file=sys.stderr)
        return EXIT_TOOL_ERROR
    try:
        rec, header, tot = plan(Path(args[0]))
    except PlanError as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_TOOL_ERROR
    print(f"duration: {rec}")
    if header is not None and header * 1000 < tot:
        print(f"cutoff: header {header}s < ~{math.ceil(tot / 1000)}s needed")
        return EXIT_CUTOFF
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
