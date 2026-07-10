# Plugin Store "Check for updates" — design

**Date:** 2026-07-10
**Status:** approved (brainstorm with James)

## Problem

The web-UI Plugin Store renders an "Upgrade" button on **every** declared plugin,
regardless of whether a newer version actually exists. It can't know: "latest" is
resolved (PyPI JSON / `git ls-remote`) only when the button is clicked. So the
Store always invites an upgrade it can't substantiate — a plugin already on the
latest version still shows "Upgrade," which is misleading. (Reported after #363
shipped the upgrade feature; #370 fixed the reconcile self-constraint.)

## Decisions made during brainstorming

- **Trigger:** on-demand. A single "Check for updates" action resolves all
  declared plugins; no eager-on-load resolve, no background polling.
- **Availability basis: "line would change."** An upgrade is available iff
  `resolve_latest(current_line) != current_line` — the *exact* no-op check the
  upgrade action already uses. Needs no installed-version info (the webui has
  none — `status.json` carries plugin namespaces, not versions; the stamp holds
  only the line-as-installed). For an unpinned line already at latest, this still
  offers "Upgrade → pin to X.Y.Z", a real, docs-recommended change. Rejected the
  "strictly newer version" basis: it would require publishing plugin versions
  across the display→sidecar boundary (a status-schema bump), out of scope.
- **Result lifetime: ephemeral, client-side.** The check runs, the browser holds
  the results and re-renders; a reload clears them until checked again. The
  endpoint is stateless — nothing written to disk (important: the sidecar mounts
  the plugin volume `:ro`).

## Architecture

Three units, each independently testable.

### 1. Shared comparison helper (`app/plugin_upgrade.py`)

Extract the "would an upgrade change the line?" decision into one function so the
CLI verb, the webui upgrade action, and the new check share a single definition
(they can't drift into offering an upgrade the action then treats as a no-op):

```
def resolve_upgrade(current_line: str, *, catalog_name: str | None,
                    resolve=resolve_latest) -> tuple[str, bool]:
    """Return (latest_line, changed). `changed` is latest_line != current_line.
    Raises UpgradeError on resolve failure. `resolve` injectable for tests."""
```

`_upgrade_one_line` refactors to call `resolve_upgrade` for its resolve+no-op
branch (behavior unchanged; existing upgrade tests must stay green).

### 2. Endpoint `POST /api/store/check-updates` (`webui/__init__.py`)

Token-gated (NOT added to `_OPEN_PATHS`; resolving hits the network — gate it like
install/upgrade). Read-only: resolves only, never writes the manifest.

- **Scope:** declared catalog plugins only. Skip plugins whose store state is
  `restart_to_activate` / `restart_to_upgrade` (a pending action already exists).
- **Shared-package dedup:** group declared plugins by their manifest line
  (comment-stripped) and resolve ONCE per line; apply the result to every sibling
  namespace sharing it (`led-ticker-flair` → nyancat/pacman/pokeball/sailor_moon:
  one resolve, four response entries).
- **Concurrency:** each resolve runs via `asyncio.to_thread` (bounded) so the
  event loop isn't blocked by `git ls-remote` / PyPI I/O.
- **Response `200`:** `{"results": [{namespace, current, latest, upgrade_available,
  error?}, ...]}` — one entry per checked namespace. A single plugin's
  `UpgradeError` becomes that entry's `error` string; the others still return; the
  endpoint never 500s on one bad plugin.
- **Status codes:** `403` no token configured; `401` token required but missing
  (auth middleware); `200` empty `results` when the manifest is absent/empty.

### 3. Frontend (`webui/static/index.html`)

- **Remove** the always-on per-row Upgrade button (the regression this fixes).
- **Add** a single "Check for updates" button in the Store toolbar, auth-gated
  (absent/disabled without a token, like the other write actions). Click →
  `POST /api/store/check-updates` → inline "checking…" state → re-render.
- **After a check**, each declared row reflects its result:
  - `upgrade_available` → an "Upgrade → `<target>`" button wired to the existing
    `POST /api/store/upgrade` (label names the concrete target version).
  - resolved, no change → muted "Up to date".
  - `error` → muted "check failed: `<reason>`".
  - Pending-restart rows keep their existing badge.
- **Ephemeral:** results held in a JS variable, cleared on any `loadStore()` /
  reload, so before a check (and after a refresh) no row invites an unsubstantiated
  upgrade.

## Data flow

1. User clicks "Check for updates."
2. Endpoint dedups declared plugins by manifest line, resolves each concurrently,
   returns per-namespace `{current, latest, upgrade_available, error?}`.
3. Browser stores the results and re-renders rows.
4. User clicks "Upgrade → X.Y.Z" on an available row → existing upgrade flow
   (manifest rewrite + restart), unchanged.

## Error handling

- Per-plugin resolve failure → that entry's `error`; siblings/others unaffected;
  `200`. UI shows "check failed: `<reason>`" on that row, leaves the rest actionable.
- No token → `403`; missing token → `401` (existing middleware).
- Empty/absent manifest → `200` empty results; UI shows "nothing declared to check."
- Read-only: no partial-write/rollback surface — the rewrite still only happens on
  the existing Upgrade action.

## Testing

- **Shared helper (`resolve_upgrade`) unit tests:** equal → `changed=False`; newer
  → `changed=True`; `UpgradeError` propagates. Tripwire that `_upgrade_one_line`
  routes through it (definition can't drift).
- **Endpoint tests** (network injected, mirroring the upgrade-handler suite):
  mixed available/up-to-date; per-plugin error isolation (one fails, others return,
  `200`); token gate (`401`/`403`); shared-package dedup (one resolve → 4 entries);
  pending-state plugins skipped; empty manifest → empty results.
- **Frontend:** HTML smoke asserts `/api/store/check-updates` is wired AND the
  always-on per-row Upgrade button is gone (guards the reported regression).

## Out of scope

- Publishing installed plugin versions into `status.json` (the "strictly newer"
  basis) — deferred; the line-would-change basis needs none of it.
- Caching / "last checked N ago" / background auto-check — deferred (ephemeral only).
- Off-catalog / externally-installed plugins (no catalog entry to resolve against).
