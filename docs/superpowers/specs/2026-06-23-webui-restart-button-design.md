# Web UI Restart Control — Design

**Date:** 2026-06-23
**Status:** Approved (brainstorm + hobbyist-persona review)
**Scope:** The deferred one-click restart fast-follow for the web Plugin Store (Spec 2). A general "restart the display" control in the webui, reused by the Store (after install/remove) and the config editor (restart-required changes).

## Goal

Let an operator **apply a restart-to-activate change from the browser** instead of SSHing in to run `docker compose restart`. After a Store install/remove, or a config change that needs a restart, a token-gated button restarts the display process so the change takes effect.

A "restart" here is a **clean exit of the display process**, after which the container/service supervisor restarts it (re-running the Spec-1 startup reconcile). It is NOT a container or host reboot. The panel goes dark for a few seconds.

## Settled decisions (brainstorm + hobbyist review)

1. **Scope:** a GENERAL restart control — one endpoint + one reusable button, surfaced in BOTH the Store pending banner and the config editor's restart-required notice.
2. **Mechanism:** a **sentinel marker** the webui writes into the shared `ticker-status` volume; the display polls it, deletes it, and `exit(0)`s; the supervisor restarts. Mirrors the existing `preview-requested` marker pattern (`webui/__init__.py`).
3. **Safety flag:** `[web] allow_restart` (default **false**). The button only acts when it's true. The Docker example config sets it true (Docker has `restart: unless-stopped`); bare-metal opts in after configuring a supervisor.
4. **Loop-safety:** the display deletes the marker BEFORE exiting, so the restarted process doesn't see it and exit again.
5. **UX (hobbyist):** a confirmation with an explicit dark-panel warning; a light label ("Restart to apply") + subtext; an elapsed "restarting…" indicator; an actionable timeout message; a disabled-with-tooltip button (not hidden) when `allow_restart` is off.

## Architecture / Components

### 1. Display side (`src/led_ticker/app/run.py`)
In the main `while True` loop (alongside the existing `watcher.changed()` and the `preview-requested` poll), check for a `restart-requested` marker at `status_path.parent / "restart-requested"`. On present:
- Log `"restart requested via web UI — exiting for supervisor restart"`.
- **Delete the marker first** (loop-safety), then `sys.exit(0)`.

The supervisor (`restart: unless-stopped`) restarts the process → the Spec-1 startup reconcile installs/loads the pending plugins. A clean exit only — never a crash path. (The marker path is derived the same way the preview marker is, so both containers agree on the location via the shared `ticker-status` volume.)

### 2. webui side (`src/led_ticker/webui/__init__.py`)
- New **token-gated `POST /api/restart`** (NOT in `_OPEN_PATHS`):
  - If `[web] allow_restart` is false → **403** `{"error": "restart disabled"}`.
  - Else write the `restart-requested` marker into `status_path.parent` (atomic small-file write) → **200**.
- Web config gains `allow_restart: bool = False`.
- Expose `allow_restart` (bool) in the `GET /api/status` and `GET /api/store` payloads so the frontend knows whether to enable the button. (Public, non-sensitive — like `auth_required`.)

### 3. Frontend (`src/led_ticker/webui/static/index.html`) — a reusable restart control
- A **"Restart to apply"** button with subtext "Quick restart to activate your changes (~5–10s)", rendered in:
  - the Store **pending banner** (when `pending_count > 0`), and
  - the config editor's **restart-required** notice (when a saved config change is non-reloadable).
- **State of the button:**
  - `allow_restart` true + token set → enabled.
  - `allow_restart` true + no token → prompts for the token (consistent with install/remove).
  - `allow_restart` false → **disabled, with a tooltip**: "Browser restart is off — set `[web] allow_restart = true` if your service auto-restarts (e.g. Docker, or systemd `Restart=`)."
- **Click flow:**
  1. **Confirm:** "The sign will go dark for a few seconds while the display restarts. Continue?"
  2. `POST /api/restart` (token header).
  3. Show **"restarting… (usually ~5–10s)"** with a live elapsed counter.
  4. Poll `GET /api/status`: the display goes offline (marker → exit) then `display_online` recovers — when it's back (and, for the Store, the pending plugins are active), clear the banner / refresh.
  5. **Timeout** (e.g. ~60s): "The display hasn't come back. Try refreshing this page; if the sign is still dark, check that the container is running (`docker compose ps`) and view the logs." Link to the status/log surface if available.
- Escape all strings via `esc()`; the restart uses the `X-Web-Token` header (never the URL).

### 4. Safety & deploy
- `allow_restart` defaults **false** — no operator can accidentally dark-panel a sign that won't come back.
- The **Docker example config** (`config.example.toml` `[web]` block) sets `allow_restart = true`; the compose already ships `restart: unless-stopped`.
- **Docs:** bare-metal must ensure a supervisor restarts the process (systemd `Restart=always`/`on-success`) before enabling. Document the deploy assumption + how to enable.
- The reconcile's per-plugin failure isolation means a restart is safe even if a freshly-declared plugin fails to install (the panel boots; the failure is logged + surfaced).

## Testing
- **Display:** the loop detects the marker → deletes it → signals exit (test the handler in isolation: marker present → removed + exit-requested; assert the delete happens BEFORE the exit so no restart loop). Don't actually exit the test process.
- **webui:** `POST /api/restart` with token + `allow_restart=true` → 200 and the marker file is written to the shared dir; no token → 401/403; `allow_restart=false` → 403 and NO marker written; `allow_restart` appears in the `/api/status` + `/api/store` payloads.
- **Frontend:** static assertions that the restart button + the confirm + the disabled-tooltip path are present; the restarting/poll/timeout flow is a **manual/maintainer check** (no JS runner).
- **Deploy-smoke (maintainer, not unit-testable):** on a sign, Store install → "Restart to apply" → panel bounces ~seconds → plugin active; the marker is consumed (no restart loop); `allow_restart=false` hides/disables the button.

## Non-goals
- Container or host reboot (display-process restart only).
- Auto-restart on manifest/config change (the explicit button was chosen over implicit auto-bounce).
- Working without a process supervisor (`allow_restart` guards it; bare-metal must opt in).
- A general "run arbitrary command" surface — this writes one specific marker, nothing else.

## Risks / open items
- **Restart loop:** if the marker isn't deleted before exit, the restarted process re-reads it and exits again → crash-loop. Mitigated by delete-before-exit + a tripwire asserting that order.
- **No-supervisor dark panel:** mitigated by `allow_restart` default-off + the disabled-with-tooltip UI + docs.
- **Stale marker from a crash:** if the webui wrote the marker but the display crashed before consuming it, the next start consumes + immediately exits once. Low impact (one extra bounce); the delete-before-exit prevents a loop. Acceptable.
- **Marker path agreement:** both containers must resolve the same path (the shared `ticker-status` volume); derive it exactly as the existing preview marker does to avoid drift.
