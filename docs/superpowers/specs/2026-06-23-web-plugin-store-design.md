# Web Plugin Store — Design (Spec 2)

**Date:** 2026-06-23
**Status:** Approved (brainstorm + visual layout selection + hobbyist-persona review)
**Builds on:** Spec 1 (no-rebuild plugin install, MERGED #274) — startup reconcile against `config/requirements-plugins.txt` (the manifest = source of truth); the webui sidecar mounts the plugins volume `:ro` (visibility via `apply_volume_visibility`) and config `:rw`; the manifest is authoritative.

## Goal

A **"Store" tab** in the existing web UI: browse the curated plugin catalog, see each plugin's install/run state, and **install/remove** (which writes `requirements-plugins.txt`) — all from the browser, behind the existing token. Install/remove take effect on the next display restart (Spec 1's restart-to-activate model), made painless with a clear banner + copyable command.

## Settled decisions (brainstorm + hobbyist review)

1. **Layout:** flat list (one row per catalog plugin) — chosen over a card grid / grouped list via the visual companion.
2. **Activation:** write-manifest + **restart-to-activate** (v1). A prominent banner + the exact copyable `docker compose restart` command + a how-to link. The one-click webui-triggered restart is a **deferred fast-follow** (not v1).
3. **Remove-in-use:** the Store **blocks** removal when `config.toml` still references the plugin, and tells the user *which* widgets/transitions (section + type) — surfaced before any write.
4. **Security:** **catalog-only** web writes (the browser sends a namespace; the server writes the catalog's vetted requirement line — arbitrary specs impossible). Behind the existing webui token. Auth state is shown on landing, not on silent failure.
5. **State badges (4):** Active / Restart to activate / Available / Externally installed. "In use" is not a separate badge — it's a **Remove-lock + note** on an Active row.
6. **Purity:** the webui stays rgbmatrix-pure (`tests/test_webui_purity.py`).

## Architecture / Components

The webui is a single aiohttp sidecar (`src/led_ticker/webui/__init__.py`) serving `static/index.html` (a tabbed single page). Spec 2 adds **one new tab** + **three routes** + a small pure backend module, reusing the config editor's token-gate and atomic-write machinery.

### 1. Backend routes (in `webui/__init__.py`)
- **`GET /api/store`** (read-only) — returns one entry per **catalog** plugin plus any non-catalog manifest lines:
  `{namespace, name, description, provides: {widgets[], transitions[], emoji[]}, source, state, removable, in_use_by: [{section, type}]}`.
  Plus a top-level `{display_online: bool, pending_count: int, auth_required: bool}`.
- **`POST /api/store/install`** (token-gated) — body `{namespace}`. Catalog-only: resolve the namespace in the catalog → write **the catalog's requirement line** to the manifest (unknown namespace → 400). Mirrors `save_handler`: `asyncio.Lock` → `.bak` backup → atomic temp + `os.replace`. Returns the updated entry (state = "restart_to_activate").
- **`DELETE /api/store/remove`** (token-gated) — body `{namespace}`. Catalog-only. Pre-check config references (§3): if referenced → **409** with `in_use_by`. Else remove the manifest line atomically. Returns the updated entry (state = "available", pending uninstall on restart).

All three live behind the existing token middleware; without a token, `GET` works and the mutations return 403 (the UI reflects this — §5).

### 2. State derivation (a pure helper, `webui/store.py`)
Per catalog plugin, derived from three inputs — the **catalog** (`load_catalog`), the **manifest** declared keys/namespaces, and **status.json** (the display's loaded plugins + the `plugin_reconcile` block):
- **Active** — declared in manifest AND loaded per status.json.
- **Restart to activate** — declared but not yet loaded (just added; display hasn't reconciled).
- **Available** — not declared.
- **Externally installed** — loaded/installed but NOT in the catalog (e.g. a hand-added manifest line or a manual pip install) → shown read-only (the Store only manages catalog plugins). Tooltip explains it.
- **Display offline** — if status.json is absent/stale, `display_online=false`: "active" is unknowable, so Active rows relabel to **"Installed (display offline)"** and a top banner says state reflects installed-not-live. (Same graceful-degrade the config editor already does for a missing display.)
- **Removable** = declared AND in the catalog AND not in-use. `in_use_by` lists the referencing `{section, type}`.

`webui/store.py` is pure (filesystem + catalog + the parsed status dict); no rgbmatrix, no display imports.

### 3. Remove-in-use guard (config-reference pre-check)
Before any remove write, scan the loaded `config.toml` for widget `type` values and `transition` / `entry_transition` / `widget_transition` values whose namespace matches the target plugin (the same surface Spec 1's reconcile guard checks — keep them consistent). Collect `[{section_title, type}]`. If non-empty → 409 with that list; the UI shows "Used in: 'Pool' → pool.monitor" + a **"Go to Config"** link that opens the editor tab. This catches it before the manifest write, so the user never reaches the confusing "removed but still there" state.

### 4. Security & purity
- **Catalog-only is the boundary:** install/remove accept a *namespace*; the server writes the *catalog's* requirement line. A namespace absent from the catalog → 400. The browser can never supply an arbitrary pip spec.
- **Token:** reuse `resolve_secret_token` / the existing `X-Web-Token` gate. `GET /api/store` is open (browse); install/remove require the token (403 without). `auth_required` in the GET payload lets the UI show the auth prompt up front (§5).
- **Purity:** `webui/store.py` + the catalog loader must import clean. If `app/plugin_cmd.py`'s manifest helpers (`_apply_to_manifest`/`_update_requirements`/`_remove_requirement`/`_declared_keys`) pull rgbmatrix-tainted modules, extract a pure `manifest_io` helper (or move those functions) that both the CLI and the webui import. Verify with `tests/test_webui_purity.py`.

### 5. Frontend (the Store tab in `static/index.html`)
- A new "Store" tab alongside Status/Config. On load, `GET /api/store`.
- **Flat list:** each row = name + description + "provides" chips + state badge + Install/Remove. An Active row that's in-use shows the Remove control **locked** with a "config depends on this" note.
- **Auth on landing:** if `auth_required` and no token set, a top prompt ("Enter your token to install or remove plugins") + the install/remove controls indicate they need the token — never a silent 403 on click.
- **Pending banner:** when `pending_count > 0`, a prominent top banner: *"N plugin(s) added — restart the display to activate."* with a copyable `docker compose restart` code block + a docs link. (The Restart button is the deferred fast-follow.)
- **Display-offline banner** (§2) when `display_online=false`.
- **Catalog-only note** under the heading: "Only verified plugins are shown — for community plugins, see the docs."
- Reuses the editor's token field + fetch/refresh patterns.

### 6. Reuse (don't reinvent)
Catalog: `load_catalog` / `plugins_catalog`. Manifest writes: `_apply_to_manifest` / `_update_requirements` / `_remove_requirement` / `_declared_keys` / `_pip_dist_name` (via a pure surface — §4). Atomic-write + lock + backup pattern: the existing `save_handler`. Status reading: the webui's existing `_read_status`.

## Testing
- **State derivation (`webui/store.py`)** — every combo: active / restart-pending / available / externally-installed / display-offline; `removable` + `in_use_by` correctness (widgets AND transitions).
- **Endpoints** — install writes the catalog line atomically (mirror `save_handler` conflict/backup/atomic tests); install of a non-catalog namespace → 400; remove of an in-use plugin → 409 with the referencing list; remove when clear → manifest line gone; all mutations → 403 without a token; `GET` works without a token.
- **Purity** — `tests/test_webui_purity.py` stays green (the new module + any extracted manifest helper import clean).
- **Frontend** — assert the Store tab + the markers (badges, pending banner, auth prompt) render; the `/api/store` payload carries the documented shape (mirror the existing webui app tests).

## Non-goals (v1)
- **One-click webui-triggered restart** (the Restart button) — deferred fast-follow.
- **Live hot-load** without a restart.
- **Arbitrary pip specs** from the browser (catalog-only).
- **Plugin discovery beyond the bundled catalog** (no remote registry, search, ratings).
- **Managing non-catalog manifest entries** — shown read-only ("Externally installed"), not editable via the Store.
- Editing plugin *config* — that's the existing config editor; the Store only manages presence.

## Risks / open items
- **Manifest-helper purity:** if `app/plugin_cmd.py` taints the webui import graph, the extraction in §4 is required before the endpoints can land — confirm early in the plan.
- **status.json shape dependency:** the Store reads the display's loaded-plugins + reconcile block; if that schema differs from assumed, state derivation needs the real keys (verify against the merged Spec 1 status schema v7 during the plan).
- **Concurrent writes:** the Store and the config editor both write into `config/` — the Store's manifest writes use the same lock discipline; confirm they don't need to share a lock (different files: `requirements-plugins.txt` vs `config.toml`, so separate locks are fine).
- **Deferred-restart UX:** v1 leans on the banner + copyable command; if user feedback shows the manual restart is still too rough, pull the deferred Restart button forward.
