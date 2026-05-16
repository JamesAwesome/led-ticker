"""Dependency-free shared contract between the engine and out-of-tree
planning tools (`tools/gif_plan/`).

SPIKE POC — proves a leaf module can carry the pure facts that
`tools/gif_plan` currently hand-mirrors, so the source-of-truth
coupling is by *import*, not by comment.

HARD RULE: this module imports **only the standard library**. It must
never import anything from `led_ticker` (or PIL / rgbmatrix / aiohttp).
That is what lets `tools/gif_plan` `from led_ticker._planning_contract
import …` for a few microseconds instead of dragging in the ~365-module
widget/async/HTTP world (measured: `led_ticker.widgets._image_base`
pulls PIL + aiohttp + asyncio; this module pulls nothing).

Scope: pure constants and pure functions only. Emergent timing (the
per-tick `play()` / `_swap_and_scroll` loop outcomes) is NOT shareable
and stays reimplemented in the planner, pinned by its dogfood tripwire.
"""

from __future__ import annotations

from pathlib import Path

# --- Engine defaults (mirror SectionConfig in config.py) -------------
# config.py keeps these as dataclass field defaults; the planner needs
# the same numbers. Defining them here lets config.py use them as the
# field defaults AND the planner import them — one definition.
DEFAULT_HOLD_TIME_S: float = 3.0
DEFAULT_LOOP_COUNT: int = 1

# --- Image/gif text-overlay constants (currently in _image_base) -----
# Pure constants trapped in a heavy module. AUTO_TEXT_ALIGN_FOR_IMAGE
# resolves `text_align="auto"` against `image_align`.
AUTO_TEXT_ALIGN_FOR_IMAGE: dict[str, str] = {
    "left": "right",
    "right": "left",
    "center": "scroll_over",
}
TEXT_EDGE_PADDING_PX: int = 2
MIN_SCROLL_SPEED_MS: int = 20

# Widget types whose `path` is config-relative and resolved at load.
PATH_BACKED_WIDGET_TYPES: tuple[str, ...] = ("gif", "image")


def resolve_widget_path(config_dir: Path, raw_path: str) -> str:
    """Resolve a file-backed widget's `path` the way the engine does.

    Single definition of the rule both `app._build_widget` and
    `tools/gif_plan/plan._resolve_widget_paths` must obey: a relative
    path is anchored to the config file's directory; an absolute path
    is left as-is. (Round-3 of PR #66 was a CRITICAL bug because the
    planner re-derived this and got it wrong — resolved against cwd.)
    """
    candidate = Path(raw_path)
    if candidate.is_absolute():
        return raw_path
    return str((config_dir / candidate).resolve())
