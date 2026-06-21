"""Config hot-reload: change detection, validation, and the field-scope diff.

Editing config.toml while the display runs takes effect at the top of the next
render cycle. Validation gates the swap; a bad/missing config never reaches the
loop (the panel keeps running the old config)."""

import hashlib
import os
from dataclasses import fields
from pathlib import Path
from typing import Any


class ConfigWatcher:
    """Detect config-file changes by mtime, confirmed by content hash. Disabled ->
    always reports no change. An mtime bump with identical bytes (no-op save) is NOT
    a change, so it won't churn a reload/breaker-reset."""

    def __init__(self, path: Path, enabled: bool = True) -> None:
        self.path = path
        self.enabled = enabled
        self._last_mtime = self._stat_mtime()
        self._last_hash = self._hash()

    def _stat_mtime(self) -> float | None:
        try:
            return os.stat(self.path).st_mtime
        except OSError:
            return None

    def _hash(self) -> str | None:
        try:
            return hashlib.sha256(self.path.read_bytes()).hexdigest()
        except OSError:
            return None

    def changed(self) -> bool:
        if not self.enabled:
            return False
        m = self._stat_mtime()
        if m is None or m == self._last_mtime:
            return False
        h = self._hash()
        if h is None:
            return False  # vanished mid-check; do NOT advance mtime, retry next cycle
        self._last_mtime = m
        if h == self._last_hash:
            return False  # no-op touch; mtime advanced to avoid re-hash next cycle
        self._last_hash = h
        return True


async def load_and_validate(path: Path) -> tuple[Any, list[str], bool]:
    """Validate then load. Returns (config, errors, transient):
      (config, [], False)  -> success
      (None, [msgs], False) -> rejected; record + keep old config
      (None, [], True)     -> transient (file mid-rename); soft skip, retry next cycle
    NEVER raises — a bad/missing config must not reach the render loop."""
    from led_ticker.config import load_config  # noqa: PLC0415
    from led_ticker.validate import validate_config  # noqa: PLC0415

    try:
        result = await validate_config(path)
    except FileNotFoundError:
        return None, [], True
    except Exception as exc:  # noqa: BLE001 - validation must never crash the loop
        return None, [f"{type(exc).__name__}: {exc}"], False
    if not result.valid:
        return None, [f"{i.location}: {i.message}" for i in result.errors], False
    try:
        return load_config(path), [], False
    except FileNotFoundError:
        return None, [], True
    except Exception as exc:  # noqa: BLE001
        return None, [f"{type(exc).__name__}: {exc}"], False


# The ONLY hot-reloadable [display] fields. Everything else feeds the frame at build
# time (built once, root dropped) and is restart-required. brightness is a live
# matrix setter; schedule is driven by the schedule ticker; hot_reload is meta.
RELOADABLE_DISPLAY_FIELDS = frozenset({"schedule", "hot_reload", "brightness"})


def nonreloadable_changed(old: Any, new: Any) -> list[str]:
    """Names of restart-required fields that differ between old and new config.
    Derived from the dataclass fields (NOT hand-listed) so a new DisplayConfig field
    is restart-required by default. Empty -> a fully-reloadable change."""
    changed: list[str] = []
    for f in fields(type(new.display)):
        if f.name in RELOADABLE_DISPLAY_FIELDS:
            continue
        if getattr(old.display, f.name, None) != getattr(new.display, f.name, None):
            changed.append(f"display.{f.name}")
    if old.busy_light != new.busy_light:
        changed.append("busy_light")
    if old.plugins != new.plugins:
        changed.append("plugins")
    if getattr(old, "web", None) != getattr(new, "web", None):
        changed.append("web")
    return changed


async def _apply_reload(
    new_config: Any,
    *,
    old_config: Any,
    widget_cache: dict,
    widget_tasks: dict,
    render_breaker: Any,
    schedule_task: Any,
    respawn_schedule: Any,
) -> tuple[Any, list[str]]:
    """Apply a validated new config in place. Evicts changed/removed widgets
    (cancelling their captured background tasks), resets the render breaker and its
    status mirror, and respawns the schedule ticker. Returns (schedule_task,
    restart_required). The CALLER swaps `config`, rebuilds the section-default
    transition, drains coerce warnings, logs, and records status."""
    from led_ticker import status_board  # noqa: PLC0415
    from led_ticker.app.factories import _cache_key  # noqa: PLC0415

    restart_required = nonreloadable_changed(old_config, new_config)

    valid_keys = {_cache_key(dict(w)) for s in new_config.sections for w in s.widgets}
    for key in list(widget_cache):
        if key not in valid_keys:
            for t in widget_tasks.pop(key, ()):
                t.cancel()  # cancel-and-move-on; not awaited at the boundary
            widget_cache.pop(key, None)

    render_breaker.reset()
    status_board.clear_disabled_widgets()
    schedule_task = await respawn_schedule(schedule_task, new_config)
    return schedule_task, restart_required
