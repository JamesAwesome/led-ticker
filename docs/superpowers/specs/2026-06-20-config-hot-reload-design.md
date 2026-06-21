# Config hot-reload (adoption item #7)

**Date:** 2026-06-20
**Status:** approved (design), pre-implementation
**Goal:** Editing `config.toml` while the display is running takes effect **without
restarting the process** — the engine rebuilds its sections / widgets / transitions /
schedule from the new config at a safe boundary (between render cycles, never
mid-render). A bad new config must never crash or freeze the running display: validate
first, and on failure keep running the old config.

## Background / why

Today `run()` (`src/led_ticker/app/run.py`) loads the config once
(`config = await asyncio.to_thread(load_config, config_path)`), builds the frame, then
enters `while True: for section in config.sections: …`. Two facts make hot-reload
tractable:

1. **Widgets are already rebuilt from `config.sections` every cycle.** A
   `widget_cache: dict[str, Any]` keyed by `_cache_key(widget_cfg)` builds each widget
   once and reuses it across passes — explicitly "to avoid leaking background tasks."
   The section loop re-reads `config.sections` on every pass. So the engine already
   re-reads config each cycle; the reload work is mostly **swapping the `config`
   object**, **invalidating the right cache entries**, and **tearing down the right
   background tasks**.
2. **The frame/RGBMatrix is built once and drops root** (`build_frame_from_config` →
   `RGBMatrix()` drops root → `daemon`, render constraint #13). So hardware `[display]`
   settings fundamentally cannot hot-reload, and a process re-exec could not re-acquire
   root to rebuild the matrix. Hot-reload is therefore scoped to the parts that live
   *above* the frame.

This extends the project's existing isolation philosophy (plugin load failures, render
failures) to config edits: a malformed edit is contained, logged, and surfaced — the
panel keeps running.

## Decisions (from brainstorming)

1. **In-place hot-swap, not full re-setup or re-exec.** On change: validate → load →
   swap the `config` object, evict only changed/removed widgets (cancel their
   background tasks), reset the breaker, respawn the schedule ticker. Frame, status
   board, preview tee, and busy-light persist untouched. (Full re-setup needlessly
   tears down busy/preview and risks double-spawning; re-exec is infeasible under the
   root-drop constraint — it would crash rebuilding the matrix.)
2. **Reload boundary = top of the render cycle.** Detection and the swap happen at the
   top of `while True`, before `for section in config.sections`. Never mid-section /
   mid-render (render constraints #1/#12). Latency = up to one full cycle.
3. **Detection = mtime poll**, not watchdog/inotify (unreliable across Docker
   bind-mounts and editor write-rename). One `os.stat` per cycle is trivially cheap.
   Re-stat the path each check so an atomic editor rename (new inode) is still caught.
4. **Validate before swap.** Reuse `validate_config(path)`; if invalid, log the errors,
   record the failure in status, and **keep the old config** (no teardown, no swap).
5. **Scope boundary — reloadable vs restart-required.**
   - **Reloadable:** `[[section]]` (widgets, `[section.title]`, transitions, `mode`,
     `bg_color`), `[between_sections]`, `[display.schedule]`, all per-widget settings.
   - **Restart-required (detected, logged, NOT applied):** hardware `[display]` fields
     (rows, cols, chain length, `hardware_mapping`, `pixel_mapper_config`,
     `gpio_slowdown`, `pwm_bits`, `default_scale`, `brightness`, etc.), `[busy_light]`,
     `[plugins]`, `[web]`. On such a change we apply the reloadable parts and log +
     surface a `restart_required: <fields>` warning.
6. **On by default**, disable via `[display] hot_reload = false`. The mtime check is
   cheap and live-edit is the expected behavior for this kind of sign.
7. **Reset the circuit breaker on a successful reload.** A reload is the user's explicit
   "I changed things" signal (a soft restart) — clear the disabled set so a widget the
   user just fixed renders again. Mirrors the existing "restart to retry a disabled
   widget" behavior (#6).
8. **Key-diff eviction.** `_cache_key(widget_cfg)` already identifies an unchanged
   widget. On reload, the valid key set = every widget's key across the new config.
   Cache entries whose key is no longer present are evicted (their captured background
   tasks cancelled); unchanged widgets keep the same key, survive, and their pollers
   keep running (no needless re-fetch). Changed widgets get a new key → old entry
   evicted, new built on the next cache miss.

## Components

### New: `src/led_ticker/reload.py`

```python
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class ConfigWatcher:
    """Detects config-file changes by mtime. Disabled -> always reports no change."""

    def __init__(self, path: Path, enabled: bool = True) -> None:
        self.path = path
        self.enabled = enabled
        self._last_mtime = self._stat_mtime()

    def _stat_mtime(self) -> float | None:
        try:
            return os.stat(self.path).st_mtime
        except OSError:
            # File briefly absent mid atomic-write -> treat as "no change yet".
            return None

    def changed(self) -> bool:
        if not self.enabled:
            return False
        m = self._stat_mtime()
        if m is None or m == self._last_mtime:
            return False
        self._last_mtime = m
        return True


def load_and_validate(path: Path, plugins: Any) -> tuple[Any, list[str]]:
    """Validate then load. Returns (config, []) on success, (None, errors) on failure.
    Never raises for a bad config — that is the whole point."""
    from led_ticker.validate import validate_config  # noqa: PLC0415
    from led_ticker.config import load_config  # noqa: PLC0415

    result = validate_config(path)
    if not result.valid:
        return None, list(result.errors)
    try:
        return load_config(path), []
    except Exception as exc:  # noqa: BLE001 - a load crash must not kill the display
        return None, [f"{type(exc).__name__}: {exc}"]


# Hardware/process-lifetime fields that cannot hot-reload (frame built once, root
# dropped; plugins/web/busy wired at startup). Compared between old/new [display]
# plus the [busy_light]/[plugins]/[web] blocks.
_DISPLAY_RESTART_FIELDS = (
    "rows", "cols", "chain_length", "parallel", "hardware_mapping",
    "pixel_mapper_config", "gpio_slowdown", "pwm_bits", "pwm_lsb_nanoseconds",
    "brightness", "default_scale", "panel_type", "limit_refresh_rate_hz",
    "rp1_pio",
)


def nonreloadable_changed(old: Any, new: Any) -> list[str]:
    """Names of restart-required fields that differ between old and new config.
    Empty list -> a fully-reloadable change."""
    changed: list[str] = []
    for f in _DISPLAY_RESTART_FIELDS:
        if getattr(old.display, f, None) != getattr(new.display, f, None):
            changed.append(f"display.{f}")
    if old.busy_light != new.busy_light:
        changed.append("busy_light")
    if old.plugins != new.plugins:
        changed.append("plugins")
    if getattr(old, "web", None) != getattr(new, "web", None):
        changed.append("web")
    return changed
```

> The exact `_DISPLAY_RESTART_FIELDS` set is finalized against `config.DisplayConfig`
> during implementation — every field that feeds `build_frame_from_config` is
> restart-required; every field that does not is fine to leave out (it just won't be
> diffed, which is harmless because the only reloadable `[display]` field is
> `schedule`, handled separately). `hot_reload` itself is excluded.

### `src/led_ticker/config.py`

Add `hot_reload: bool = True` to `DisplayConfig`. (One field, default on.) The
config-options drift test + docs reference get the new field.

### `src/led_ticker/render_breaker.py`

Add `reset(self) -> None: self.disabled.clear()`. Called on a successful reload.

### `src/led_ticker/status_board.py`

Add a `last_reload` block to the snapshot and a recorder, mirroring `failed_plugins` /
`disabled_widgets` (instrumentation-safe — never raises into the loop):

```python
# StatusBoard field:
last_reload: dict[str, Any] = attrs.field(factory=dict)
# snapshot(): "last_reload": self.last_reload
# SCHEMA_VERSION 4 -> 5, EXPECTED_TOP_LEVEL_KEYS gains "last_reload", tripwire updated.

def record_reload(*, ok: bool, ts: str, error: str = "",
                  restart_required: list[str] | None = None) -> None:
    """Record the outcome of a config reload attempt. Instrumentation only."""
    if _ACTIVE is None:
        return
    try:
        _ACTIVE.last_reload = {
            "ok": ok, "at": ts, "error": error,
            "restart_required": list(restart_required or []),
        }
        _ACTIVE.publish()
    except Exception:  # noqa: BLE001
        return
```

`ts` is passed in by the caller (run() stamps `datetime.now(...).isoformat()`), keeping
`record_reload` free of clock calls (testable).

### `src/led_ticker/webui/static/index.html`

Render `last_reload` when present: a small line/card showing the timestamp, OK/failed
state + error, and any `restart_required` fields — mirroring the `failed_plugins` /
`disabled_widgets` blocks. Docs note the field in `web-status-ui.mdx`.

### `src/led_ticker/app/run.py` — orchestration

The reload logic lives where the rebuildable handles live. Changes:

- **Capture per-widget background tasks.** In the cache-miss build path, snapshot
  `widget.spawn_tracked`'s registry around `_build_widget` to record exactly the tasks
  that widget spawned, and store them with the cache entry:
  `widget_cache[key] = widget` stays, plus a parallel `widget_tasks: dict[str, set[Task]]`.
  Capture = `before = set(_BACKGROUND_TASKS); … build …; widget_tasks[key] = _BACKGROUND_TASKS - before`.
  (Tasks spawned before the section loop — busy-light, schedule, heartbeat — are never
  captured, so they survive reload.)
- **Capture the schedule task handle** at startup (the `spawn_tracked(_supervised_schedule(...))`
  result) so it can be cancelled + respawned on reload.
- **`ConfigWatcher`** created after load, gated on `config.display.hot_reload`.
- **Reload sequence** at the top of `while True` (before `for section`):

```text
if watcher.changed():
    new_config, errors = await asyncio.to_thread(load_and_validate, config_path, plugins)
    ts = datetime.now(tz).isoformat()
    if new_config is None:
        logging.error("config reload rejected: %s", "; ".join(errors))
        status_board.record_reload(ok=False, ts=ts, error="; ".join(errors))
        # keep old config; fall through to render the current cycle
    else:
        restart_required = nonreloadable_changed(config, new_config)
        if restart_required:
            logging.warning("config reloaded; restart required for: %s",
                            ", ".join(restart_required))
        # key-diff eviction: cancel + drop widgets whose key is gone/changed
        valid_keys = {_cache_key(w) for s in new_config.sections for w in s.widgets}
        for key in list(widget_cache):
            if key not in valid_keys:
                for t in widget_tasks.pop(key, ()):  # cancel that widget's pollers
                    t.cancel()
                widget_cache.pop(key, None)
        # rebuild the section-default transition the same way startup does, from
        # new_config.between_sections (so an edited [between_sections] default applies)
        default_section_trans = <rebuilt exactly as at startup, from new_config.between_sections>
        render_breaker.reset()                       # decision 7
        schedule_task = _respawn_schedule(schedule_task, new_config, led_frame)  # cancel old + spawn new
        config = new_config                          # the swap
        logging.info("config reloaded%s",
                     "" if not restart_required else " (partial)")
        status_board.record_reload(ok=True, ts=ts, restart_required=restart_required)
# ... existing: for section_index, section in enumerate(config.sections): ...
```

- **`_respawn_schedule(old_task, config, frame)`** helper: cancel `old_task` if present;
  if `config.display.schedule.enabled`, build a fresh `Scheduler.from_config` and
  `spawn_tracked(_supervised_schedule(...))`, returning the new task; else set
  `frame.matrix.brightness = config.display.brightness` (base) and return `None`.
  Cancellation is best-effort (`task.cancel()`; the tracked-task done-callback cleans
  the registry — no await needed at the boundary, but a brief `await asyncio.sleep(0)`
  may be used to let cancellation propagate before respawn).

> Note: evicted widget tasks are cancelled (`task.cancel()`) but not awaited at the
> reload boundary — awaiting could stall the render loop on a slow teardown. The
> `spawn_tracked` done-callback removes them from `_BACKGROUND_TASKS`; a cancelled
> `run_monitor_loop` exits promptly on its next await. The plan verifies the task
> enters the cancelled state.

## Data flow

```
edit config.toml (host; visible in the ro bind-mount)
   │
   ▼ (top of next render cycle)
ConfigWatcher.changed()  ──no──▶ render cycle as normal (old config)
   │ yes
   ▼
load_and_validate(path)
   │                 ╲ invalid
   │ valid            ▶ log + status.record_reload(ok=False) + keep old config
   ▼
nonreloadable_changed(old, new) ─▶ log "restart required: …" (if any)
key-diff evict widget_cache (cancel removed/changed pollers)
rebuild section-default transition · render_breaker.reset() · respawn schedule ticker
config = new_config            ◀── the atomic swap
status.record_reload(ok=True, restart_required=…)
   │
   ▼
for section in config.sections:   (now the NEW sections; widgets rebuilt on cache-miss)
```

## Error handling

- **Bad config never reaches the display:** `validate_config` gates the swap; failure
  logs + records + retains the old config. The display never crashes/freezes on an
  edit.
- **Load crash** (validation passed but `load_config` raised — should be rare): caught
  in `load_and_validate`, treated as a rejected reload.
- **Watcher errors** (file briefly missing during atomic write): `_stat_mtime` returns
  `None` → "no change yet"; the next cycle re-checks.
- **Status instrumentation** (`record_reload`) never raises into the loop (try/except →
  return), same rule as `record_disabled_widget`.
- **Render constraints honored:** the swap only happens between cycles; the running
  cycle always finishes on a consistent `config`.

## Non-goals

- Hot-reloading hardware `[display]` geometry, `[busy_light]`, `[plugins]`, `[web]`
  (restart-required; detected + surfaced, not applied).
- A push/HTTP "reload now" trigger (mtime poll only; a webhook trigger could be a
  future fast-follow, mirroring the busy-light HTTP source).
- Partial/granular per-section reload latency below one cycle.
- Awaiting evicted-task teardown at the boundary (cancel-and-move-on).

## Testing

- `ConfigWatcher`: reports no change when unchanged; reports change after mtime bumps;
  disabled → always no change; missing file → no change (no raise).
- `load_and_validate`: valid config → `(config, [])`; invalid config → `(None, errors)`
  with the validator's messages; never raises.
- `nonreloadable_changed`: a hardware `[display]` field change → listed; `[busy_light]`
  / `[plugins]` / `[web]` change → listed; a section/schedule-only change → `[]`.
- `RenderBreaker.reset`: clears the disabled set; `is_disabled` false afterward.
- Engine-level (the integration test): with two configs A→B, drive the reload sequence
  and assert (a) the new sections are what the next pass iterates; (b) a widget removed
  in B has its captured task cancelled; (c) an unchanged widget keeps the SAME cached
  instance + its task is NOT cancelled (key-diff); (d) an INVALID B is rejected and the
  old config is retained (no eviction); (e) `render_breaker.reset` is called on success
  only.
- `status_board`: `record_reload` ok/failure shapes appear in the snapshot;
  `SCHEMA_VERSION == 5`; `last_reload` in `EXPECTED_TOP_LEVEL_KEYS` (tripwire).
- Docs-lint for the `web-status-ui.mdx` `last_reload` doc + the `config-options`
  `hot_reload` field (drift test).

## Verification gates

- `PYTHONPATH=tests/stubs uv run pytest` green (new `tests/test_reload.py` + engine
  reload test + status schema-5 tripwire + config-options drift).
- `uv run --extra dev ruff check src/ tests/` + `ruff format`.
- `uv run --extra dev pyright src/` clean.
- Docs-lint (prettier + astro) for the touched `.mdx`.

## Key constraints (carried into the plan)

- No `from __future__ import annotations` in `src/` (PEP 649).
- `asyncio_mode = "auto"` — async tests are bare `async def` (no decorator).
- Status instrumentation must never raise into the engine.
- Render constraints #1/#12/#13 — swap only between cycles; frame is process-lifetime
  (root dropped); never touch the swap/advance discipline.
- The reload swap must keep the running cycle on a consistent `config` object.
