# Monitor-health web UI — design

**Date:** 2026-07-01
**Status:** Approved (brainstorm complete, PM + engineer reviewed) — ready for an implementation plan.

## Goal

Let a user tell, **at a glance in the web UI**, whether each live-data monitor — polled `[[source]]` value-tokens (e.g. `:weather.nyc:`) and data widgets (weather, RSS, crypto, calendar, sports, pool) — is **running, erroring, or stale**.

## Framing (do not skip)

This is a **"publish monitor health, then display it"** feature, not "add a Status panel." Today `status.json` publishes only `monitor_updates[name] = last-success-timestamp`; the **error** — the single most valuable signal — lives only in `logger.exception` lines and is never published. The load-bearing work is the **publisher** (emit per-monitor error + last-OK + interval + retry hint); the panel is the last ~30%. Plan and estimate accordingly.

## Existing foundation (verified against code)

- `status_board.py` — a best-effort JSON publisher (`SCHEMA_VERSION = 8`, self-disables on any write failure, throttled `_flush` + heartbeat-serialized, `prepare_dir()` opens the dir pre-privilege-drop per hardware constraint #13). Already has `record_monitor_update(name)` → `monitor_updates[name] = time.time()` and an `overlay_roster` (a set-once roster precedent).
- `widget.py` `run_monitor_loop(widget, interval, splay, immediate)` — the ONE shared supervised poll loop. **Verified** every data widget (via each plugin's `start()`) AND every polled source (via `sources.py:spawn_source_refresh`) spawns through it; enforced by `tests/test_task_tracking.py`. It tracks `consecutive_errors` (exponential backoff 60s→1h), logs on failure, and calls `record_monitor_update(...)` on success. **`busy_light` also rides this loop** (`app/run.py` `_start_busy_light`) but is an overlay, not a data monitor.
- `sources.py` — `PolledDataSource` has `.id`, `.polled`, `.interval`, `._set_value` (no `.name`); data widgets have `.draw` (Widget protocol) but often no `.id`/`.name`.
- Web UI — `src/led_ticker/webui/static/index.html` renders `status.json` (it currently reads `st.monitor_updates` ~line 493) across Status / Preview / Config / Store tabs.

## Global constraints

- **Never block or raise into the render loop.** All health recording is best-effort; `record_monitor_error` is internally `try/except`-wrapped (it runs *inside* `run_monitor_loop`'s `except`, so it must never escape). The board already self-disables on a write failure ("status publish failed; panel unaffected"). Nothing here touches the swap/draw path; `time.time()` in the board is fine.
- **No per-plugin changes.** All wiring is in core (`run_monitor_loop` + `status_board` + the reload path). Data-widget plugins are untouched.
- **No circular import.** `sources.py` imports `widget.py` (one-directional); `widget.py` must NOT import `sources`. Source-vs-widget is decided by duck-typing (below).
- **Web UI is read-only.** This panel adds no endpoint — it consumes the existing `status.json`.
- PEP 649; DOCS-STYLE (no "footgun"); worktree + PR; never `main`.

## 1. The publisher (core)

### One `monitors` structure
Replace the "roster + `monitor_updates` + error dicts merged in snapshot" idea with **a single dict** on `StatusBoard`:

```
monitors: dict[str, dict] = {}   # name -> {kind, interval, last_ok, error}
#   kind:     "source" | "widget"
#   interval: float (seconds)
#   last_ok:  float epoch or None (last successful update)
#   error:    None or {message: str, consecutive: int, at: float, retry_in: float}
```

- **`register_monitor(name, kind, interval)`** — creates/updates the entry (preserving `last_ok`/`error` on re-register). Idempotent. On a **name collision** (two same-type widgets, both lacking `.id`/`.name`) it appends a `#2`, `#3` suffix so each monitor gets a distinct row.
- **`record_monitor_update(name)`** — keep the existing internal `monitor_updates[name] = time.time()` store as the last-OK source of truth (so existing semantics/tests are preserved), AND set `monitors[name].last_ok` + **clear** `monitors[name].error`.
- **`record_monitor_error(name, message, consecutive, retry_in)`** — sets `monitors[name].error = {message, consecutive, at: time.time(), retry_in}`. Internally guarded (never raises).
- All three are pure setters (no `await`); the heartbeat's existing per-beat publish serializes them.

### Wiring in `run_monitor_loop` (the choke point)
- **Name resolution** (a shared helper): `_monitor_name(obj) = getattr(obj, "id", None) or getattr(obj, "name", None) or type(obj).__name__`. Fixes the confirmed latent bug where two polled sources both key as `"WeatherSource"` (sources now key by `.id`).
- **Kind + busy_light exclusion by duck-typing:** register **only** if the object is a source (`getattr(obj, "polled", False)`) → `kind="source"`, or a drawable widget (`hasattr(obj, "draw")`) → `kind="widget"`. Anything that is **neither** (busy_light — an overlay with `.update()`/`.paint()` but no `.draw`/`.polled`) is **not registered**. (Verify `BusyLight` has no `.draw`; if it ever gains one, fall back to an explicit `register_monitor: bool = True` kwarg on `run_monitor_loop` that `_start_busy_light` passes `False`.)
- **Placement:** `register_monitor(...)` is the **first statement** in `run_monitor_loop` (before the `splay`/first `await`) so a monitor appears immediately as "waiting for first update."
- **On success:** `record_monitor_update(name)` (already called — extend to the new store).
- **On failure (`except Exception`):** `record_monitor_error(name, str(exc)[:200], consecutive_errors, retry_in=backoff)` — the message is truncated (≤200 chars) so a huge exception can't bloat `status.json`; `run_monitor_loop` already computes the next `backoff`, so `retry_in` is free.
- **`CancelledError`** is re-raised (not caught by `except Exception`) → a reload-cancel leaves no spurious error. Good.

### Reload
`_apply_reload` cancels + respawns monitors but nothing prunes the roster today. Add **`clear_monitors()`** on the status board, called alongside the existing `clear_disabled_widgets()` in `_apply_reload` — the fresh loops re-register and rebuild the set. (Brief empty window between clear and first loop-body-run is acceptable; the heartbeat refills within one interval.)

### Snapshot / schema
Bump `SCHEMA_VERSION` **8 → 9** (new top-level key). `snapshot()` serializes a `monitors` array built **synchronously** from the dict:
```
"monitors": [{name, kind, interval, last_ok, error}, ...]
```
Keep `monitor_updates` internal (as the last-OK store) but **stop serializing it top-level** — and in the SAME change migrate the web UI JS (currently reads `st.monitor_updates`) to `st.monitors`, and update the 4 test assertions (`tests/test_status_instrumentation.py`, `tests/test_status_board.py`) + the schema-version tripwire (`EXPECTED_TOP_LEVEL_KEYS` / `== 8` literals in `tests/test_status_board.py`).

## 2. State model (computed in the browser)

Per monitor, from `(interval, last_ok, error, now)` — recomputed each client tick so relative times count up live:

- **🟢 ok** — no error and `now − last_ok ≤ interval + grace`.
- **🔴 error** — `error` is present (`consecutive ≥ 1`). Shows `error.message` + `×consecutive` and a **retry hint** ("retrying in ~4m" from `retry_in`). **Error wins over stale** — a failing monitor is red, not amber. A monitor in backoff is therefore `error` (retrying), never stale.
- **🟠 stale** — no error, but `now − last_ok > interval + grace` (a silently-wedged loop). `grace = interval + SPLAY_ALLOWANCE` (SPLAY_ALLOWANCE ≈ 60s, covering `run_monitor_loop`'s up-to-60s splay) — so a healthy 30-min weather monitor never false-alarms. Effectively ~2× interval with a splay floor; a single tunable.
- **⚪ waiting** — registered, `last_ok` is None and no error yet (before the first fetch). A neutral row ("waiting for first update"), **not** its own alarm color and **not** counted as a problem in the badge.

**Roll-up badge:** counts by state (`4 ok · 1 stale · 1 error`); badge color = worst present (any red → red, else any amber → amber, else green). "waiting" doesn't drive the color.

**Sign-liveness gate:** the badge/panel defers to the sign's own liveness. If the snapshot itself is stale (the existing `published_at`/`swap_count` liveness signal shows the sign isn't reporting), show **"sign not reporting"** and grey the monitor rows rather than asserting per-monitor health from a frozen file — the worst real failure (sign offline) must not read as all-green.

## 3. Web UI (`webui/static/index.html`)

- A **"Monitors" panel on the Status tab** (the landing view) + the roll-up **badge** near the top — health visible the instant the page opens, no click.
- **Per row:** state dot · `name` · a `src`/`widget` kind tag · state word · `updated 12s ago` (live relative time from `last_ok`) · `interval` · inline error (`401 Unauthorized ×3 · retrying in ~4m`) when present. Sorted **worst-state-first**, then by name.
- **Empty / absent:** if `monitors` is missing (older `status.json`, schema < 9) or empty (a config with no polled sources or data widgets), show a quiet "No live-data monitors configured" — graceful degradation, matching how the page already handles optional fields.
- Match the page's existing hand-rendered styling/JS (no new framework). If practical, factor the state-computation into a small pure JS function so it can be unit-tested.

## 4. Testing

- **Board unit tests** (extend `tests/test_status_board.py` / `tests/test_status_instrumentation.py`): `register_monitor` creates an entry (incl. the `#2` collision suffix); `record_monitor_update` sets `last_ok` + clears error; `record_monitor_error` sets the error record; `clear_monitors()` empties it; `_monitor_name` prefers `.id` (source) / `.name` / classname; the source-collision case now yields two distinct rows.
- **Never-raise:** make `record_monitor_error`'s internals throw and assert `run_monitor_loop` survives (the poll loop keeps running).
- **`run_monitor_loop` instrumentation** (extend the existing test that drives it with a fake monitor): register-on-entry, update-on-success (clears error), error-on-failure (with `retry_in`), and that `busy_light`-like objects (no `.draw`/`.polled`) are NOT registered.
- **Reload prune:** register two, `clear_monitors()`, re-register one → the dropped one is gone.
- **Schema tripwire** bumped to 9; snapshot contains `monitors`, not top-level `monitor_updates`.
- **Web UI:** if the state-compute is factored out, unit-test the ok/error/stale/waiting transitions + the sign-liveness gate.

## Scope

**In (v1):** read-only at-a-glance health (running / error / stale / waiting) for polled sources + data widgets, with the roll-up badge, live relative times, retry hints, worst-first sort, sign-liveness gate, graceful empty state.

**Out (YAGNI — possible later behind the same data):** manual retry/restart buttons; per-monitor history / graphs; alerting / notifications; a dedicated Monitors tab; an error taxonomy beyond faithfully showing the message.

## Sequencing

**One coordinated effort** (core + web UI are the same repo). Order: (1) the board's `monitors` dict + `register_monitor`/`record_monitor_error`/`clear_monitors` + `_monitor_name`; (2) `run_monitor_loop` wiring (duck-typed kind, busy_light exclusion, register-first-line, error+retry_in); (3) reload prune; (4) snapshot schema 8→9 + drop top-level `monitor_updates` + migrate tests; (5) the web UI panel + badge + sign-liveness gate — data exists before the UI consumes it.
