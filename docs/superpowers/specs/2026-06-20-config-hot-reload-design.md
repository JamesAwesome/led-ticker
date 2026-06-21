# Config hot-reload (adoption item #7)

**Date:** 2026-06-20
**Status:** approved (design) — revised after independent spec review (perf + correctness/concurrency + architecture + operator + edge/test lenses)
**Goal:** Editing `config.toml` while the display is running takes effect **without
restarting the process** — the engine rebuilds its sections / widgets / transitions /
schedule from the new config at a safe boundary (between render cycles, never
mid-render). A bad new config must never crash or freeze the running display: validate
first, and on failure keep running the old config.

## Background / why

`run()` (`src/led_ticker/app/run.py`) loads the config once
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
   `RGBMatrix()` drops root → `daemon`, render constraint #13). Hardware `[display]`
   settings therefore cannot hot-reload, and a re-exec could not re-acquire root to
   rebuild the matrix. Hot-reload is scoped to the parts that live *above* the frame.

This extends the project's isolation philosophy (plugin-load failures, render failures)
to config edits: a malformed edit is contained, logged, and surfaced — the panel keeps
running.

## Decisions (from brainstorming, refined by spec review)

1. **In-place hot-swap**, not full re-setup or re-exec. On change: validate → load →
   swap the `config` object, evict only changed/removed widgets (cancel their tasks),
   reset the breaker + clear its status mirror, respawn the schedule ticker. Frame,
   status board, preview tee, busy-light persist. (Re-exec is infeasible under the
   root-drop constraint — it would crash rebuilding the matrix.)
2. **Reload boundary = top of the render cycle**, before `for section`. Never
   mid-render (constraints #1/#12). Latency = up to one cycle.
3. **Detection = mtime poll + content-hash gate.** One `os.stat` per cycle; on an mtime
   change, read the file and compare a content hash, proceeding only if the bytes
   actually differ. (Kills no-op-touch churn — some editors bump mtime on save with no
   content change — and the spurious breaker-reset/re-trip it would cause.) Re-stat the
   path each check so an atomic editor rename (new inode) is caught. Not watchdog/inotify
   (unreliable across Docker bind-mounts).
4. **Validate before swap, and validation NEVER raises into the loop.** `load_and_validate`
   is **async** (the real `validate_config` is a coroutine — see Components) and wraps
   its entire body so any exception becomes a rejected reload, never a propagated crash.
   On validation errors, keep the old config and record the messages. A transient
   file-missing (mid atomic-rename) is a *soft* skip (keep old config, retry next cycle,
   no recorded failure — so `last_reload` doesn't flap to "failed" on every save).
5. **Scope boundary — reloadable vs restart-required (inverted framing).** Rather than a
   hand-maintained list of restart-required fields (which drifts as new frame fields are
   added), enumerate the small set of **reloadable** `[display]` fields and treat every
   other `DisplayConfig` field as restart-required:
   `RELOADABLE_DISPLAY_FIELDS = {"schedule", "hot_reload", "brightness"}`; restart-required
   `= {f.name for f in fields(DisplayConfig)} - RELOADABLE_DISPLAY_FIELDS`. A drift-guard
   test asserts every `display.*` field that `build_frame_from_config` consumes is in the
   restart-required set, so a future frame field can never be silently treated as
   reloadable.
   - **Reloadable:** `[[section]]` (widgets, `[section.title]`, transitions, `mode`,
     `bg_color`), `[between_sections]`, `[display.schedule]`, `[display] brightness`, all
     per-widget settings.
   - **Restart-required (detected, logged + surfaced, NOT applied):** all other
     `[display]` hardware fields, `[busy_light]`, `[plugins]`, `[web]`. On such a change
     we apply the reloadable parts and surface a `restart_required: <fields>` warning.
6. **`brightness` is reloadable.** It is a live `matrix.brightness` setter (not just an
   init param), and the schedule ticker already writes it at runtime. On reload, when the
   schedule is disabled we set `matrix.brightness = new base`; when enabled, the respawned
   ticker uses the new base. (So it is excluded from restart-required.)
7. **On by default**, disable via `[display] hot_reload = false`.
8. **Reset the circuit breaker on a successful reload, AND clear its status mirror.**
   `render_breaker.reset()` clears the in-memory disabled set; the status board's
   `disabled_widgets` list is append-only, so a new `status_board.clear_disabled_widgets()`
   (instrumentation-safe) is called alongside it — otherwise the web UI shows
   phantom-disabled widgets for already-fixed widgets after a reload.
9. **Key-diff eviction.** `_cache_key(widget_cfg)` identifies an unchanged widget. The
   valid key set = every widget's key across the new config. Cache entries whose key is
   gone are evicted (their captured background tasks cancelled); unchanged widgets keep
   the same key, survive, and their pollers keep running (no re-fetch). Changed widgets
   get a new key → old entry evicted, new built on the next cache miss.
10. **Build-time failures are guarded too.** With reload, `_build_widget` runs against
    *user-edited* config at runtime (today it only runs at startup, where a crash is
    acceptable). A widget cfg that passes static validation but raises in `_build_widget`
    must not freeze the panel: the cache-miss build is wrapped — on failure, log + record
    + skip that widget for this pass + do **not** cache it (so a later good edit retries).
11. **The reload sequence is an extracted, testable async helper** (`_apply_reload`),
    not inline in `run()`'s `while True` — so the integration test can exercise it
    directly and `run()` stays small.

## Components

### New: `src/led_ticker/reload.py`

```python
import hashlib
import logging
import os
from dataclasses import fields
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class ConfigWatcher:
    """Detect config-file changes by mtime, confirmed by content hash. Disabled ->
    always reports no change. An mtime bump with identical bytes (no-op save) is NOT a
    change."""

    def __init__(self, path: Path, enabled: bool = True) -> None:
        self.path = path
        self.enabled = enabled
        self._last_mtime = self._stat_mtime()
        self._last_hash = self._hash()

    def _stat_mtime(self) -> float | None:
        try:
            return os.stat(self.path).st_mtime
        except OSError:
            return None  # absent mid atomic-write -> "no change yet"

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
        self._last_mtime = m
        h = self._hash()
        if h is None or h == self._last_hash:
            return False  # mtime moved but bytes identical (or file vanished) -> skip
        self._last_hash = h
        return True


async def load_and_validate(path: Path) -> tuple[Any, list[str], bool]:
    """Validate then load. Returns (config, errors, transient):
      - (config, [], False)  -> success
      - (None, [msgs], False) -> rejected (validation/load error); record + keep old
      - (None, [], True)     -> transient (file mid-rename); soft skip, retry next cycle
    NEVER raises — a bad/missing config must not reach the render loop (goal #1)."""
    from led_ticker.validate import validate_config  # noqa: PLC0415
    from led_ticker.config import load_config  # noqa: PLC0415

    try:
        result = await validate_config(path)  # async; raises FileNotFoundError if gone
    except FileNotFoundError:
        return None, [], True
    except Exception as exc:  # noqa: BLE001 - validation must never crash the loop
        return None, [f"{type(exc).__name__}: {exc}"], False
    if not result.valid:
        # result.errors are ValidationIssue dataclasses, not strings.
        return None, [f"{i.location}: {i.message}" for i in result.errors], False
    try:
        return load_config(path), [], False
    except FileNotFoundError:
        return None, [], True
    except Exception as exc:  # noqa: BLE001
        return None, [f"{type(exc).__name__}: {exc}"], False


# The ONLY hot-reloadable [display] fields; everything else feeds the frame at build
# time (root-dropped, built once) and is restart-required. brightness is a live matrix
# setter; schedule is handled by the schedule ticker; hot_reload is meta.
RELOADABLE_DISPLAY_FIELDS = frozenset({"schedule", "hot_reload", "brightness"})


def nonreloadable_changed(old: Any, new: Any) -> list[str]:
    """Names of restart-required fields that differ between old and new config.
    Derived (not hand-listed) so new DisplayConfig fields are restart-required by
    default. Empty list -> a fully-reloadable change."""
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
```

> `nonreloadable_changed` relies on the config dataclasses being value-comparable
> (`==`). `DisplayConfig` and the `[busy_light]`/`[plugins]`/`[web]` configs are
> dataclasses with default value equality — verified during implementation; if any is
> not, give it `eq=True` or compare a normalized dict.
> Note: `validate_config` re-runs plugin discovery (`load_plugins_for_config`) on each
> reload. The plugin registry is idempotent (entry points re-register to the same
> namespaced keys), so this is wasteful-but-safe; confirmed in implementation.

### `src/led_ticker/config.py`

Add `hot_reload: bool = True` to `DisplayConfig`. Config-options drift test + docs
reference gain the field.

### `src/led_ticker/render_breaker.py`

Add `reset(self) -> None: self.disabled.clear()`.

### `src/led_ticker/status_board.py`

- `last_reload: dict[str, Any] = attrs.field(factory=dict)` + `"last_reload": self.last_reload`
  in `snapshot()`; `SCHEMA_VERSION` 4 → 5; `EXPECTED_TOP_LEVEL_KEYS` gains `"last_reload"`;
  tripwire updated.
- `record_reload(*, ok, ts, error="", restart_required=None)` — instrumentation-safe
  (try/except → return), publishes with `force=True` (matches `record_section`). `ts` is
  passed by the caller (`datetime.now(tz).isoformat()`), keeping the recorder clock-free.
- `clear_disabled_widgets()` — instrumentation-safe; `_ACTIVE.disabled_widgets.clear()`
  + `publish()`. Called on a successful reload alongside `render_breaker.reset()`.

### `src/led_ticker/widget.py` — per-build task capture (contextvar sink)

The previous "snapshot `_BACKGROUND_TASKS` before/after build" idea is not safe:
`_build_widget` is `async` and awaits inside, so unrelated tracked tasks can be
spawned/completed during the window. Instead, `spawn_tracked` appends to a per-build
**sink** when one is active:

```python
import contextvars
_build_sink: contextvars.ContextVar[set | None] = contextvars.ContextVar(
    "led_ticker_build_sink", default=None
)

def spawn_tracked(coro: Any) -> asyncio.Task[Any]:
    task = asyncio.create_task(coro)
    sink = _build_sink.get()
    if sink is not None:
        sink.add(task)
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)
    task.add_done_callback(lambda t, s=sink: s.discard(t) if s is not None else None)
    return task
```

`run()` sets the sink only around the cache-miss `_build_widget` call, so each widget's
spawned tasks are captured exactly, regardless of await interleaving:

```python
sink: set[asyncio.Task[Any]] = set()
token = _build_sink.set(sink)
try:
    widget = await _build_widget(...)
except Exception as exc:                 # decision 10: build-time guard
    # No widget object exists to summarize, so log (the operator signal) + skip.
    # Cancel anything the partial build spawned; the `continue` runs `finally`
    # (the single reset) first, and we do NOT cache (a later good edit retries).
    logging.exception("widget build failed; skipping for this pass: %s", exc)
    for t in sink:
        t.cancel()
    continue
finally:
    _build_sink.reset(token)             # exactly once per token (success or skip)
widget_cache[key] = widget
widget_tasks[key] = sink
```

### `src/led_ticker/webui/static/index.html`

Render `last_reload` when present (timestamp, OK/failed + error, any `restart_required`
fields), mirroring the `failed_plugins` / `disabled_widgets` blocks. `web-status-ui.mdx`
documents the field and notes that reload feedback appears here or in the logs
(`journalctl`) — there is no on-panel indicator (a brief on-panel toast is a possible
future fast-follow).

### `src/led_ticker/app/run.py` + the extracted helper

- **`_apply_reload`** (in `reload.py`, async, testable) does the state mutations:

```python
async def _apply_reload(
    new_config, *, old_config, widget_cache, widget_tasks, render_breaker,
    schedule_task, led_frame,
) -> tuple[Any, list[str]]:
    """Evict changed/removed widgets, reset+clear the breaker, respawn the schedule.
    Returns (schedule_task, restart_required). Caller swaps config + rebuilds the
    section-default transition + logs + records status."""
    restart_required = nonreloadable_changed(old_config, new_config)
    valid_keys = {_cache_key(w) for s in new_config.sections for w in s.widgets}
    for key in list(widget_cache):
        if key not in valid_keys:
            for t in widget_tasks.pop(key, ()):
                t.cancel()                 # cancel-and-move-on; not awaited at boundary
            widget_cache.pop(key, None)
    render_breaker.reset()
    status_board.clear_disabled_widgets()
    schedule_task = await _respawn_schedule(schedule_task, new_config, led_frame)
    return schedule_task, restart_required
```

- **`_respawn_schedule(old_task, config, frame)`**: cancel `old_task` if present; if
  `config.display.schedule.enabled`, build a fresh `Scheduler.from_config` +
  `spawn_tracked(_supervised_schedule(...))`, return the new task; else set
  `frame.matrix.brightness = config.display.brightness` (the new base) and return `None`.
  Cancellation is best-effort; an `await asyncio.sleep(0)` lets the old task observe the
  cancel before the new one starts.

- **`ConfigWatcher`** created after the initial load, gated on `config.display.hot_reload`,
  seeded from the just-loaded file's mtime+hash (so the startup→watch window can't miss
  the first edit).

- **Reload sequence** at the top of `while True` (before `for section`):

```text
if watcher.changed():
    new_config, errors, transient = await load_and_validate(config_path)
    if transient:
        pass                                   # file mid-write; retry next cycle, no record
    elif new_config is None:
        ts = datetime.now(tz).isoformat()
        logging.error("config reload rejected: %s", "; ".join(errors))
        status_board.record_reload(ok=False, ts=ts, error="; ".join(errors))
        # keep old config
    else:
        ts = datetime.now(tz).isoformat()
        schedule_task, restart_required = await _apply_reload(
            new_config, old_config=config, widget_cache=widget_cache,
            widget_tasks=widget_tasks, render_breaker=render_breaker,
            schedule_task=schedule_task, led_frame=led_frame)
        default_section_trans = <rebuilt as at startup, from new_config.between_sections>
        for w in getattr(new_config, "_coerce_warnings", []):  # drain like startup
            logging.warning("config coerce: %s", w.message)
        config = new_config                    # the swap
        if restart_required:
            logging.warning("config reloaded (partial); restart required for: %s",
                            ", ".join(restart_required))
        else:
            logging.info("config reloaded")
        status_board.record_reload(ok=True, ts=ts, restart_required=restart_required)
# ... existing: for section_index, section in enumerate(config.sections): ...
```

- **Capture the schedule task handle** at startup (the `spawn_tracked(_supervised_schedule(...))`
  result) so `_respawn_schedule` can cancel + replace it.

## Data flow

```
edit config.toml (host; visible in the ro bind-mount)
   │
   ▼ (top of next render cycle)
ConfigWatcher.changed()  ──mtime same / bytes same──▶ render cycle as normal (old config)
   │ changed
   ▼
await load_and_validate(path)
   │ transient (mid-rename) ─▶ skip, retry next cycle (no record)
   │ invalid ──────────────▶ log + status.record_reload(ok=False, errors) + keep old config
   ▼ valid
_apply_reload: key-diff evict (cancel removed/changed pollers) · breaker.reset()
              · clear_disabled_widgets() · respawn schedule ticker
rebuild section-default transition · drain coerce warnings · config = new_config (swap)
log (partial?) · status.record_reload(ok=True, restart_required)
   │
   ▼
for section in config.sections:   (NEW sections; widgets rebuilt on cache-miss,
                                   each build wrapped so a bad widget is skipped not fatal)
```

## Error handling

- **Bad config never reaches the display:** `load_and_validate` wraps validate + load
  entirely; failure → keep old config + record. The transient file-missing window is a
  soft skip (no flapping).
- **Build-time failure** (validated cfg that raises in `_build_widget`): caught at the
  cache-miss site → logged + recorded + the widget skipped for the pass (not cached, so
  a later good edit retries). The loop survives.
- **Watcher errors** (file briefly missing): `_stat_mtime`/`_hash` return `None` → "no
  change yet".
- **Status instrumentation** (`record_reload`, `clear_disabled_widgets`) never raises
  into the loop (try/except → return).
- **Render constraints honored:** the swap happens only between cycles; the running
  cycle always finishes on one consistent `config` object. Evicted tasks are cancelled
  but not awaited at the boundary (cancel-and-move-on) so teardown can't stall the loop.

## Non-goals

- Hot-reloading hardware `[display]` geometry, `[busy_light]`, `[plugins]`, `[web]`
  (restart-required; detected + surfaced, not applied). `default_scale` stays
  restart-required (the wrapper's initial scale is fixed at startup; per-section `scale`
  already overrides at runtime).
- A push/HTTP "reload now" trigger (mtime poll only; a webhook could be a future
  fast-follow, mirroring the busy-light HTTP source).
- An on-panel reload indicator (feedback is logs + the web `last_reload` card).
- Awaiting evicted-task teardown at the boundary.

## Testing

- `ConfigWatcher`: unchanged → no change; mtime+content change → change; mtime bump with
  identical bytes → no change (no-op-touch gate); disabled → always no change; missing
  file → no change (no raise).
- `load_and_validate` (async): valid → `(config, [], False)`; invalid → `(None, [msgs], False)`
  where msgs are human strings built from `ValidationIssue.location/.message`; missing
  file → `(None, [], True)` (transient); never raises.
- `nonreloadable_changed`: a hardware `[display]` field change → listed; `[busy_light]`/
  `[plugins]`/`[web]` change → listed; a section/schedule/brightness-only change → `[]`.
- **Drift guard:** a test asserting every `display.*` field passed to
  `build_frame_from_config` corresponds to a `DisplayConfig` field NOT in
  `RELOADABLE_DISPLAY_FIELDS` (so a new frame field can't be silently reloadable).
- `RenderBreaker.reset`: clears the disabled set.
- `status_board`: `record_reload` ok/failure shapes in the snapshot;
  `clear_disabled_widgets` empties the list; `SCHEMA_VERSION == 5`; `last_reload` in
  `EXPECTED_TOP_LEVEL_KEYS` (tripwire).
- `spawn_tracked` build-sink: a task spawned inside an active sink lands in the sink AND
  `_BACKGROUND_TASKS`; outside any sink, only `_BACKGROUND_TASKS`.
- **`_apply_reload` (the integration test):** with configs A→B, assert (a) a widget
  removed in B has its captured task `.cancelled()`; (b) an unchanged widget keeps the
  SAME cached instance and its task is NOT cancelled (key-diff); (c) `render_breaker.reset`
  + `clear_disabled_widgets` ran; (d) the schedule task was respawned; (e) the returned
  `restart_required` reflects a hardware-field diff.
- **Build-time guard:** a widget cfg that raises in `_build_widget` is skipped (logged +
  recorded), not cached, and the loop continues (mirror with a stub raising widget).
- **Reject path:** an invalid B is rejected — old config retained, no eviction, breaker
  not reset, `record_reload(ok=False)` with the validator's message.
- Docs-lint for `web-status-ui.mdx` (`last_reload`) + `config-options` (`hot_reload`)
  drift test.

## Verification gates

- `PYTHONPATH=tests/stubs uv run pytest` green (new `tests/test_reload.py` + the
  `_apply_reload` engine test + status schema-5 tripwire + the restart-field drift guard
  + config-options drift).
- `uv run --extra dev ruff check src/ tests/` + `ruff format`.
- `uv run --extra dev pyright src/` clean.
- Docs-lint (prettier + astro) for the touched `.mdx`.

## Key constraints (carried into the plan)

- No `from __future__ import annotations` in `src/` (PEP 649).
- `asyncio_mode = "auto"` — async tests are bare `async def`.
- Status instrumentation must never raise into the engine.
- Render constraints #1/#12/#13 — swap only between cycles; frame is process-lifetime
  (root dropped); never touch the swap/advance discipline.
- The reload swap must keep the running cycle on a consistent `config` object.
- `validate_config` is **async** and raises `FileNotFoundError` for a missing path —
  `load_and_validate` awaits it and wraps every exception (no propagation into the loop).
- `ValidationResult.errors` is `list[ValidationIssue]` (`.location`, `.message`, `.fix`,
  `.severity`) — format to strings before logging/joining.
