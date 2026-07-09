"""Config hot-reload: change detection, validation, and the field-scope diff.

Editing config.toml while the display runs takes effect at the top of the next
render cycle. Validation gates the swap; a bad/missing config never reaches the
loop (the panel keeps running the old config)."""

import hashlib
import logging
import os
from dataclasses import fields
from pathlib import Path
from typing import Any

_log = logging.getLogger(__name__)


def config_hash(path: Path) -> str | None:
    """The sha256 hex of the file's bytes (the same digest ConfigWatcher uses
    to confirm a change), or None when the file is unreadable. The web editor
    uses this as a conflict-detection version stamp."""
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


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
        return config_hash(self.path)

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

# Top-level TOML keys that core's own load_config() reads. Any other top-level
# key is a plugin-owned block (e.g. [storefront]) that a plugin captured at
# startup and never re-reads — hot-reload cannot make it take effect, so a
# change to one is always restart-required. MUST track load_config's `raw.get(...)`
# reads in config.py — add a new key here whenever load_config starts reading one.
_CORE_OWNED_TOP_LEVEL_KEYS = frozenset(
    {
        "display",
        "transitions",
        "busy_light",
        "title",
        "source",
        "playlist",
        "plugins",
        "web",
    }
)


def nonreloadable_changed(old: Any, new: Any) -> list[str]:
    """Names of restart-required fields that differ between old and new config.
    Derived from the dataclass fields (NOT hand-listed) so a new DisplayConfig field
    is restart-required by default. Empty -> a fully-reloadable change.

    Also flags any changed plugin-owned top-level TOML block (a key not in
    _CORE_OWNED_TOP_LEVEL_KEYS, e.g. [storefront]) by comparing the raw parsed
    TOML on both configs' `_raw` — plugins read their block once at startup, so
    core cannot hot-reload it; the block name itself is reported (e.g.
    "storefront") so the user knows what needs a restart."""
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

    old_raw = getattr(old, "_raw", {}) or {}
    new_raw = getattr(new, "_raw", {}) or {}
    plugin_keys = (set(old_raw) | set(new_raw)) - _CORE_OWNED_TOP_LEVEL_KEYS
    for key in sorted(plugin_keys):
        if old_raw.get(key) != new_raw.get(key):
            changed.append(key)
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
    source_refresh_task: Any = None,
    session: Any = None,
) -> tuple[Any, Any, list[str]]:
    """Apply a validated new config in place. Evicts changed/removed widgets
    (cancelling their captured background tasks), resets the render breaker and its
    status mirror, respawns the schedule ticker, and atomically swaps the source
    registry + respawns the 1 Hz source-refresh ticker. Returns
    (schedule_task, new_source_refresh_task_list, restart_required). The CALLER swaps
    `config`, rebuilds the section-default transition, drains coerce warnings,
    logs, and records status.

    ``source_refresh_task`` is a LIST of task handles (the 1 Hz sync task + one
    ``run_monitor_loop`` per polled source) as returned by ``spawn_source_refresh``.
    On a successful swap every handle in the list is cancelled and a new list is
    spawned; on a build failure the old list is returned unchanged (atomic-or-nothing).
    ``session`` is the shared aiohttp.ClientSession; forwarded to ``build_source`` so
    polled (network-backed) sources constructed during a reload share the same session
    as those built at startup."""
    from led_ticker import status_board  # noqa: PLC0415
    from led_ticker.app.factories import _cache_key, build_source  # noqa: PLC0415
    from led_ticker.sources import (  # noqa: PLC0415
        DataRegistry,
        set_data_registry,
        spawn_source_refresh,
    )

    restart_required = nonreloadable_changed(old_config, new_config)

    valid_keys = {_cache_key(dict(w)) for s in new_config.sections for w in s.widgets}
    for key in list(widget_cache):
        if key not in valid_keys:
            for t in widget_tasks.pop(key, ()):
                t.cancel()  # cancel-and-move-on; not awaited at the boundary
            widget_cache.pop(key, None)

    render_breaker.reset()
    status_board.clear_disabled_widgets()
    status_board.clear_monitors()  # respawned source/widget loops re-register
    schedule_task = await respawn_schedule(schedule_task, new_config)

    # Atomic registry swap: build the new registry fully before installing it,
    # so the concurrent 1 Hz ticker never iterates a half-built dict.
    # Then cancel ALL old task handles (the list holds the 1 Hz sync task + one
    # run_monitor_loop per polled source) and spawn a new list for the fresh
    # registry. Mirror the schedule-respawn pattern: cancel old, spawn new,
    # return the new list so the caller can cancel them all on the next reload.
    #
    # Safety net (atomic-or-nothing): if any build_source call raises (e.g.
    # unknown source type from a hand-edited config.toml typo) we MUST NOT
    # crash the display loop and MUST NOT leave a half-applied registry or cancel
    # any old handles. On error, keep the old registry + old task list live and
    # let the rest of the reload (widgets, schedule) proceed on the last-good
    # sources. The user can fix their typo and reload again.
    try:
        new_reg = DataRegistry()
        for source_cfg in new_config.sources:
            new_reg.add(build_source(source_cfg, session=session))
    except Exception as exc:  # noqa: BLE001 - a bad source must not crash the loop
        _log.error(
            "reload: source registry rebuild failed (%s: %s) — "
            "keeping old sources; fix the config and reload again",
            type(exc).__name__,
            exc,
        )
        return schedule_task, source_refresh_task, restart_required
    set_data_registry(new_reg)
    # Cancel every old handle: the 1 Hz sync task AND any polled-source loops.
    # source_refresh_task is a list (Task 5 shape from spawn_source_refresh), or
    # None (very first startup before any reload). Normalise defensively so the
    # cancel loop is uniform regardless of shape.
    if source_refresh_task is not None:
        handles = (
            source_refresh_task
            if isinstance(source_refresh_task, list)
            else [source_refresh_task]
        )
        for handle in handles:
            handle.cancel()
    new_source_refresh_tasks = spawn_source_refresh(new_reg)

    return schedule_task, new_source_refresh_tasks, restart_required
