# Web Plugin Store (Spec 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Store" tab to the webui sidecar to browse the plugin catalog and install/remove plugins (writing `requirements-plugins.txt`), behind the existing token, taking effect on the next display restart.

**Architecture:** A new pure module `src/led_ticker/webui/store.py` derives per-plugin state from (catalog ∪ manifest ∪ status.json ∪ config refs). Three routes in `webui/__init__.py` expose it: `GET /api/store` (open) + token-gated `POST /api/store/install` and `DELETE /api/store/remove` (atomic manifest writes mirroring the existing `save_handler`). A flat-list Store tab in `static/index.html` renders it. Layers on the merged Spec 1 (manifest = source of truth; restart-to-activate).

**Tech Stack:** Python 3.14, aiohttp, attrs, tomllib, the bundled `plugins_catalog.json` (schema v3), the existing webui token gate.

**Spec:** `docs/superpowers/specs/2026-06-23-web-plugin-store-design.md`

## Global Constraints

- **Webui stays rgbmatrix-pure** — `tests/test_webui_purity.py` MUST stay green. `store.py` and anything `webui/__init__.py` imports must not pull rgbmatrix. (`app/plugin_cmd.py` + `plugins_catalog.py` are already pure — verified — so importing their helpers is fine; re-confirm with the purity test, don't assume.)
- **Catalog-only writes:** install/remove accept a *namespace*; the server writes the *catalog's* requirement line (`CatalogEntry.requirement()`). A namespace absent from the catalog → **400**. The browser can never supply an arbitrary pip spec.
- **Token:** `GET /api/store` is open; install/remove require the token (mirror the existing gate: no token configured → 403 "editing disabled"; token configured but wrong/absent → 401). Reuse the existing middleware.
- **Atomic manifest writes:** under an `asyncio.Lock`, back up `.bak`, write tmp + `os.replace` — mirror `save_handler` (`webui/__init__.py:263-351`).
- **Catalog field names (verified):** `CatalogEntry.name`, `.namespace`, `.summary` (NOT "description"), `.provides` (a `PluginProvides` with per-surface tuples + `.all_names()`), `.sources`, `.requirement(*, source=None, pinned=True)`. `Catalog.get(name)`, `.search(q)`, `.entries`. `load_catalog()` returns a `Catalog`.
- **Status keys (verified):** `status["plugins"]` = list of loaded-plugin dicts; `status["plugin_reconcile"]` = list of `{namespace, action, detail}`; `status["schema"]`. The webui reads it via `_read_status(status_path)` (returns `{}` when absent).
- **State names:** `active` / `restart_to_activate` / `available` / `externally_installed`.
- **NON-GOALS:** the one-click Restart button (deferred), live hot-load, arbitrary specs, remote registry/search, managing non-catalog manifest entries (read-only), editing plugin config.

## File Structure

- `src/led_ticker/webui/store.py` — NEW, pure: `config_references()`, `build_store()` + helpers. State derivation only; no HTTP, no rgbmatrix.
- `src/led_ticker/webui/__init__.py` — MODIFY: add the three routes + a shared atomic manifest-write helper; register routes.
- `src/led_ticker/webui/static/index.html` — MODIFY: the Store tab (nav button + section + JS).
- Docs: `docs/site/src/content/docs/plugins/index.mdx` (or the webui page) — MODIFY: a note about installing from the Store tab.
- Tests: `tests/test_webui_store.py` (NEW, pure-logic), extend `tests/test_webui_app.py` (routes), `tests/test_webui_purity.py` (stays green).

---

## Task 1: `store.py` — `config_references()`

**Files:** Create `src/led_ticker/webui/store.py`; Test `tests/test_webui_store.py`

**Interfaces — Produces:** `def config_references(config_path: Path) -> dict[str, list[dict[str, str]]]` → maps each referenced plugin namespace to a list of `{"section": <title-or-index>, "type": <full type/transition string>}`. Scans widget `type` keys AND `transition`/`entry_transition`/`widget_transition` string values (same surface as Spec 1's reconcile guard). NEVER raises (bad/missing config → `{}`).

- [ ] **Step 1: failing test** — `tests/test_webui_store.py`:
```python
from pathlib import Path
from led_ticker.webui.store import config_references


def test_config_references_widget_and_transition(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        '[[playlist.section]]\nmode="swap"\ntransition="nyancat.forward"\n'
        '[[playlist.section.widget]]\ntype="rss.feed"\n'
    )
    refs = config_references(cfg)
    assert "rss" in refs and refs["rss"][0]["type"] == "rss.feed"
    assert "nyancat" in refs  # via the transition key


def test_config_references_missing_or_bad_is_empty(tmp_path):
    assert config_references(tmp_path / "absent.toml") == {}
    bad = tmp_path / "config.toml"; bad.write_text("[[[ not toml")
    assert config_references(bad) == {}
```

- [ ] **Step 2: run, expect fail** — `PYTHONPATH=tests/stubs uv run --extra dev pytest tests/test_webui_store.py -v`.
- [ ] **Step 3: implement** (module header + the function):
```python
"""Pure state derivation for the web Plugin Store (no rgbmatrix, no HTTP).

Combines the catalog, the manifest, status.json, and config references into
the payload the Store tab renders. Verified pure by tests/test_webui_purity.py.
"""

import tomllib
from pathlib import Path

_TRANSITION_KEYS = ("transition", "entry_transition", "widget_transition")


def config_references(config_path: Path) -> dict[str, list[dict[str, str]]]:
    try:
        data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError, UnicodeDecodeError):
        return {}
    out: dict[str, list[dict[str, str]]] = {}

    def add(ns_source: str, section: str) -> None:
        if "." in ns_source:
            ns = ns_source.split(".")[0]
            out.setdefault(ns, []).append({"section": section, "type": ns_source})

    def walk(obj: object, section: str) -> None:
        if isinstance(obj, dict):
            title = obj.get("title")
            sec = title.get("text") if isinstance(title, dict) else section
            sec = sec if isinstance(sec, str) and sec else section
            t = obj.get("type")
            if isinstance(t, str):
                add(t, sec)
            for key in _TRANSITION_KEYS:
                v = obj.get(key)
                if isinstance(v, str):
                    add(v, sec)
            for v in obj.values():
                walk(v, sec)
        elif isinstance(obj, list):
            for v in obj:
                walk(v, section)

    walk(data, "config")
    return out
```

- [ ] **Step 4: run, expect pass.** **Step 5: commit** (`build: webui store config_references`).

---

## Task 2: `store.py` — `build_store()` state derivation

**Files:** Modify `src/led_ticker/webui/store.py`; Test `tests/test_webui_store.py`

**Interfaces — Consumes:** `config_references` (Task 1); `led_ticker.plugins_catalog.load_catalog`/`Catalog`/`CatalogEntry`; `led_ticker.app.plugin_cmd._declared_keys` (pure dedup keys of manifest lines). **Produces:**
`def build_store(*, manifest_path: Path, config_path: Path, status: dict, token_configured: bool, catalog=None) -> dict` → returns
```
{
  "display_online": bool, "pending_count": int, "auth_required": bool,
  "plugins": [ {namespace, name, summary, provides: {...lists...}, source,
                state, removable, in_use_by: [{section,type}]} , ... ]
}
```
Helper `def _active_namespaces(status: dict) -> set[str]` (the namespaces in `status["plugins"]`).

**Implementer notes (verify the live shapes first):**
- A plugin is **declared** if its catalog `namespace` maps to a manifest line. Build `declared: set[str]` by matching each catalog entry to the manifest: an entry is declared iff its requirement dedup key is in `_declared_keys(manifest_path)` (read the actual `_declared_keys` return + `CatalogEntry.requirement()`/`_requirement_key` to map entry→key — mirror how `plugin_reconcile._declared_namespaces` does it, but DO NOT import `plugin_reconcile` if it taints purity; replicate the small mapping here using the pure catalog + `_declared_keys`/`_requirement_key`).
- **active** namespaces come from `status["plugins"]` — READ the exact dict shape in the merged `status_board.py` (each loaded-plugin dict's namespace key) before coding `_active_namespaces`.
- `display_online = bool(status)` (status.json present/fresh; the webui's `_read_status` returns `{}` when absent).
- State per catalog entry: declared & active → `active`; declared & not active → `restart_to_activate`; not declared → `available`. A namespace that is active/declared-key present but **not in the catalog** → an extra `externally_installed` entry (read-only). When `not display_online`, `active` entries still report `state="active"` but the FRONTEND relabels (the payload carries `display_online` so the UI does the relabel — keep the state name stable).
- `removable = declared and (namespace in catalog) and (namespace not in config_references)`. `in_use_by = config_references.get(namespace, [])`.
- `pending_count = number of entries with state == "restart_to_activate"`.
- `auth_required = token_configured` (the UI shows the prompt when a token is needed).

- [ ] **Step 1: failing tests** (drive each state with a synthetic catalog + manifest + status):
```python
from led_ticker.webui.store import build_store
from led_ticker.plugins_catalog import load_catalog


def test_build_store_states(tmp_path):
    cat = load_catalog()
    ns = cat.entries[0].namespace            # a real catalog plugin
    man = tmp_path / "requirements-plugins.txt"
    man.write_text(cat.entries[0].requirement() + "\n")   # declared
    cfg = tmp_path / "config.toml"; cfg.write_text("")
    # declared + active -> active
    res = build_store(manifest_path=man, config_path=cfg,
                      status={"plugins": [{"namespace": ns}]}, token_configured=True)
    entry = next(p for p in res["plugins"] if p["namespace"] == ns)
    assert entry["state"] == "active"
    assert res["auth_required"] is True and res["display_online"] is True
    # declared + not active -> restart_to_activate, counts as pending
    res2 = build_store(manifest_path=man, config_path=cfg, status={}, token_configured=True)
    e2 = next(p for p in res2["plugins"] if p["namespace"] == ns)
    assert e2["state"] == "restart_to_activate"
    assert res2["display_online"] is False and res2["pending_count"] >= 1


def test_build_store_available_and_in_use(tmp_path):
    cat = load_catalog(); ns = cat.entries[0].namespace
    man = tmp_path / "requirements-plugins.txt"; man.write_text("")  # nothing declared
    cfg = tmp_path / "config.toml"; cfg.write_text("")
    res = build_store(manifest_path=man, config_path=cfg, status={}, token_configured=False)
    entry = next(p for p in res["plugins"] if p["namespace"] == ns)
    assert entry["state"] == "available" and entry["removable"] is False
    assert res["auth_required"] is False
```
(Add an `externally_installed` test: status lists a namespace not in the catalog → an entry with that state.)

- [ ] **Step 2: run, expect fail.**
- [ ] **Step 3: implement** `build_store` + `_active_namespaces` + the declared-mapping helper per the notes (read `_declared_keys`, `_requirement_key`, `CatalogEntry.requirement`, and `status_board.py`'s plugin dict shape first).
- [ ] **Step 4: run, expect pass** + **purity gate:** `PYTHONPATH=tests/stubs uv run --extra dev pytest tests/test_webui_store.py tests/test_webui_purity.py -v` (purity MUST stay green; if it fails because a helper taints, extract a pure `manifest_io` per the spec and import that instead). **Step 5: commit** (`build: webui store state derivation`).

---

## Task 3: `GET /api/store` route

**Files:** Modify `src/led_ticker/webui/__init__.py`; Test `tests/test_webui_app.py`

**Interfaces — Consumes:** `build_store` (Task 2), the existing `_read_status`, the configured `token`, the `config_path` (manifest is `config_path.parent / "requirements-plugins.txt"`).

- [ ] **Step 1: failing test** — an aiohttp test (mirror the existing webui app tests): `GET /api/store` returns 200 with `plugins` (list) + `display_online`/`pending_count`/`auth_required` keys; works WITHOUT a token.
- [ ] **Step 2: run, expect fail.**
- [ ] **Step 3: implement** a `store_handler` that reads status (`_read_status`), resolves the manifest path, calls `build_store(manifest_path=..., config_path=config_path, status=..., token_configured=bool(token))`, returns `web.json_response(payload)`. Register `app.router.add_get("/api/store", store_handler)` next to the other GET routes (~line 369). Keep it OPEN (no token).
- [ ] **Step 4: run, expect pass** (+ full webui test file). **Step 5: commit** (`feat(webui): GET /api/store`).

---

## Task 4: `POST /api/store/install`

**Files:** Modify `src/led_ticker/webui/__init__.py`; Test `tests/test_webui_app.py`

**Interfaces — Produces:** a shared `async def _write_manifest_atomic(manifest_path, new_text, lock)` (lock → `.bak` backup → tmp + `os.replace`, mirroring `save_handler:343-351`).

- [ ] **Step 1: failing tests:** install a known catalog namespace with the token → 200, the manifest now contains the catalog requirement line; install with NO token (token configured) → 401/403 per the gate; install a namespace NOT in the catalog → 400; the manifest write is atomic + a `.bak` exists.
- [ ] **Step 2: run, expect fail.**
- [ ] **Step 3: implement** `install_handler` (token-gated like `save_handler`): parse `{namespace}`; `cat = load_catalog()`; `entry = cat.get_by_namespace(namespace)` (use `Catalog.get`/a namespace lookup — add one if absent) → if None: 400 `{"error":"unknown plugin"}`; read the current manifest text; if the entry's requirement isn't already present, append `entry.requirement() + "\n"`; `_write_manifest_atomic`. Return the rebuilt single entry (call `build_store` and pick it) so the UI refreshes its state. Register `add_post("/api/store/install", install_handler)` behind the token. Reuse the manifest-line dedup from `_apply_to_manifest`/`_update_requirements` if it fits (text-level).
- [ ] **Step 4: run, expect pass.** **Step 5: commit** (`feat(webui): POST /api/store/install (catalog-only, atomic)`).

---

## Task 5: `DELETE /api/store/remove`

**Files:** Modify `src/led_ticker/webui/__init__.py`; Test `tests/test_webui_app.py`

- [ ] **Step 1: failing tests:** remove a declared catalog namespace whose config does NOT reference it → 200, the manifest line is gone; remove one that the config DOES reference → **409** with `in_use_by` listing `{section,type}`; remove without token → 401/403; remove a non-catalog namespace → 400.
- [ ] **Step 2: run, expect fail.**
- [ ] **Step 3: implement** `remove_handler` (token-gated): parse `{namespace}`; catalog lookup → 400 if unknown; `refs = config_references(config_path).get(namespace, [])` → if non-empty: `web.json_response({"error":"in_use","in_use_by":refs}, status=409)`; else read manifest, drop the line whose dedup key matches the entry (reuse `_remove_requirement`'s line-matching at text level), `_write_manifest_atomic`. Return the rebuilt entry. Register `add_delete("/api/store/remove", remove_handler)` behind the token.
- [ ] **Step 4: run, expect pass** (+ full webui test file + purity). **Step 5: commit** (`feat(webui): DELETE /api/store/remove (config-ref guard, atomic)`).

---

## Task 6: Frontend — the Store tab

**Files:** Modify `src/led_ticker/webui/static/index.html`; Test: extend `tests/test_webui_app.py` (page markers + payload shape)

- [ ] **Step 1:** Read the existing tab wiring (`<nav><button data-tab>`, `<section id="tab-X" class="tab">`, the tab-switch JS, and how the config tab uses the token field + fetch). 
- [ ] **Step 2:** Add `<button data-tab="store">Store</button>` to `<nav>` and a `<section id="tab-store" class="tab">` containing: a catalog-only note line; an auth prompt shown when `auth_required` and no token entered; a pending banner (shown when `pending_count>0`) with a **copyable `docker compose restart`** code block + a docs link (NO restart button); a display-offline banner (when `!display_online`); and a flat list (one row per plugin: name + `summary` + provides chips + a state badge + Install/Remove). For `active` + `in_use_by.length` rows, render Remove **disabled** with a "config depends on this — used in: …" note. On `!display_online`, relabel `active` badges to "Installed (display offline)". Install → `POST /api/store/install` with the token header; Remove → `DELETE /api/store/remove`, and on 409 show the `in_use_by` list + a "Go to Config" link that switches to the config tab. Refresh via `GET /api/store` after each action. Escape all user/catalog strings (reuse the page's `esc`).
- [ ] **Step 3:** Extend `tests/test_webui_app.py`: assert the page contains the Store tab markers (`data-tab="store"`, `tab-store`, the catalog-only note text) and that `GET /api/store` returns the documented shape. (No JS test runner — note the interactive flows are a **manual/maintainer check**.)
- [ ] **Step 4:** `PYTHONPATH=tests/stubs uv run --extra dev pytest tests/test_webui_app.py tests/test_webui_purity.py -q` green. **Step 5: commit** (`feat(webui): Store tab UI (flat list, states, pending banner)`).

---

## Task 7: Docs

**Files:** Modify the Plugins docs page (`docs/site/src/content/docs/plugins/index.mdx`)

- [ ] **Step 1:** Add a short "Install from the web UI" subsection: the Store tab lists catalog plugins; click Install/Remove (needs the webui token); changes apply on the next `docker compose restart` (link to the no-rebuild section); removal is blocked while your config still uses the plugin. Note catalog-only (community plugins via the manifest/CLI).
- [ ] **Step 2:** `make docs-build` + `make docs-lint` clean. **Step 3: commit** (`docs: install plugins from the web Store tab`).

---

## Self-Review

**Spec coverage:** flat list→T6; GET/install/remove routes→T3/4/5; state model + display-offline + externally_installed→T2/T6; remove-in-use 409→T5/T6; catalog-only + token→T4/T5 (+ global constraints); purity→gates in T2/T5/T6; auth-on-landing + pending banner + copyable command + catalog-only note→T6; docs→T7. ✅

**Placeholder scan:** code blocks concrete for the pure logic (T1/T2); T2/T4/T5 carry "read the live shape first" directed reads (the exact `status["plugins"]` dict key + `_declared_keys`/`_requirement_key` mapping must be read from current code, not guessed) — these are explicit verifications, not vague TODOs. T6 is a directed-read + integration task (frontend, no JS runner).

**Type consistency:** `config_references -> dict[str, list[{section,type}]]` consumed by `build_store` (in_use_by) and `remove_handler` (409). `build_store(...) -> {display_online,pending_count,auth_required,plugins[...]}` consumed by T3/T6. State names (`active`/`restart_to_activate`/`available`/`externally_installed`) consistent across T2/T6.

**Notes for the executor:** (1) **Purity is a hard gate** on T2/T5/T6 — if importing `plugin_cmd` helpers taints the webui, extract a pure `manifest_io` (spec §4) before proceeding. (2) The **Store frontend interactions can't be unit-tested** (no JS runner) — flag a manual/maintainer check. (3) A **webui plugin-install round-trip on a sign** (click Install → manifest written → restart → active) is a maintainer **deploy-smoke** — flag it, don't fake it. (4) Verify the exact `status["plugins"]` dict shape + the catalog namespace-lookup (`Catalog.get` vs a new `get_by_namespace`) against current code in T2/T4.
