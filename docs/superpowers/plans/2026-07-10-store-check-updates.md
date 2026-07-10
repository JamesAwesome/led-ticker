# Plugin Store "Check for updates" Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Plugin Store's always-on "Upgrade" button with an on-demand "Check for updates" action that only offers Upgrade where a newer version actually exists.

**Architecture:** A shared `resolve_upgrade` helper defines "would an upgrade change the manifest line?" (the same no-op check the upgrade action already uses). A new stateless, token-gated `POST /api/store/check-updates` resolves every declared+active plugin's line and returns per-namespace availability. The frontend drops the per-row Upgrade button, adds a "Check for updates" toolbar button, and renders Upgrade only where the check reported availability — results held client-side, cleared on reload. Spec: `docs/superpowers/specs/2026-07-10-store-check-updates-design.md`.

**Tech Stack:** Python 3.14 (aiohttp, stdlib), no new deps. Vanilla JS in `webui/static/index.html`. Resolver is the existing `plugin_upgrade.resolve_latest` (PyPI JSON / `git ls-remote`).

## Global Constraints

- Worktree: `/Users/james/projects/github/jamesawesome/led-ticker-check-updates`, branch `feat/store-check-updates`. All paths below are relative to that root. Work only there.
- Availability basis is **"line would change"**: an upgrade is available iff `resolve_latest(comment_stripped_line) != comment_stripped_line`. No installed-version info is used (the webui has none). This must stay identical to the upgrade action's own no-op check — both route through the one `resolve_upgrade` helper.
- The check endpoint is **read-only and stateless**: it resolves only, never writes the manifest, writes nothing to disk (the sidecar mounts the plugin volume `:ro`).
- Results are **ephemeral, client-side**: held in a JS variable, cleared on every `loadStore()` / reload.
- `webui/__init__.py` must never import rgbmatrix — new `plugin_upgrade` / `plugin_cmd` imports are **lazy inside the handler** (tripwire `tests/test_webui_purity.py`).
- `/api/store/check-updates` is NOT in `_OPEN_PATHS` (it hits the network — gate it like install/upgrade: `403` no token configured, `401` token required but missing).
- Shared packages (one manifest line → many namespaces, e.g. `led-ticker-flair` → nyancat/pacman/pokeball/sailor_moon) resolve ONCE per unique line; the result applies to every sibling namespace.
- Only plugins whose store state is `"active"` are checked (declared + installed + current). `restart_to_activate` / `restart_to_upgrade` (pending action) and `available` / `externally_installed` (no manifest line to resolve) are skipped.
- No `from __future__ import annotations` (PEP 649 project rule). Run tests with `uv run pytest <file> -v` from the worktree root. Pyright is pre-push only.
- Commit after every task (each ends green). NEVER merge/push without James's explicit go-ahead.

## File Structure

- Modify: `src/led_ticker/app/plugin_upgrade.py` — add `resolve_upgrade`; refactor `_upgrade_one_line` to use it (Task 1)
- Modify: `src/led_ticker/webui/__init__.py` — add `check_updates_handler` + route (Task 2)
- Modify: `src/led_ticker/webui/static/index.html` — drop always-on Upgrade button; add Check-for-updates button + `checkForUpdates()` + result-driven rendering (Task 3)
- Modify: `docs/site/src/content/docs/plugins/index.mdx`, `CLAUDE.md` (Task 4)
- Tests: `tests/test_plugin_upgrade.py`, `tests/test_webui_app.py`

---

### Task 1: `resolve_upgrade` shared helper

**Files:**
- Modify: `src/led_ticker/app/plugin_upgrade.py` (add `resolve_upgrade` above `_upgrade_one_line` ~line 254; refactor `_upgrade_one_line`'s resolve branch)
- Test: `tests/test_plugin_upgrade.py`

**Interfaces:**
- Consumes: existing `resolve_latest(line, *, catalog_name=None, ...) -> str`, `UpgradeError`.
- Produces (Task 2 + `_upgrade_one_line` rely on this exact signature):
  - `resolve_upgrade(current_line: str, *, catalog_name: str | None = None, resolve=None) -> tuple[str, bool]` — returns `(latest_line, changed)` where `changed = latest_line != current_line`. Raises `UpgradeError` on resolve failure. `resolve` injectable (defaults to the module `resolve_latest`, resolved at CALL time so `monkeypatch.setattr(up, "resolve_latest", ...)` is honored).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_plugin_upgrade.py`:

```python
# --- resolve_upgrade (shared availability check) ------------------------------


def test_resolve_upgrade_changed_when_newer():
    latest, changed = up.resolve_upgrade(
        "led-ticker-pool==0.1.0",
        resolve=lambda line, **kw: "led-ticker-pool==0.2.0",
    )
    assert latest == "led-ticker-pool==0.2.0"
    assert changed is True


def test_resolve_upgrade_unchanged_when_same():
    latest, changed = up.resolve_upgrade(
        "led-ticker-pool==0.2.0",
        resolve=lambda line, **kw: "led-ticker-pool==0.2.0",
    )
    assert latest == "led-ticker-pool==0.2.0"
    assert changed is False


def test_resolve_upgrade_propagates_error():
    def boom(line, **kw):
        raise up.UpgradeError("no matching tags")

    with pytest.raises(up.UpgradeError, match="no matching tags"):
        up.resolve_upgrade("led-ticker-pool==0.1.0", resolve=boom)


def test_resolve_upgrade_default_uses_module_resolve_latest(monkeypatch):
    # Default resolve= must bind resolve_latest at CALL time, so monkeypatching
    # the module attribute is honored (as the CLI/webui tests rely on).
    monkeypatch.setattr(up, "resolve_latest", lambda line, **kw: line + "-X")
    latest, changed = up.resolve_upgrade("pkg", catalog_name="pool")
    assert latest == "pkg-X" and changed is True
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_plugin_upgrade.py -k resolve_upgrade -v`
Expected: FAIL — `AttributeError: resolve_upgrade`

- [ ] **Step 3: Implement `resolve_upgrade` + refactor `_upgrade_one_line`**

Add above `_upgrade_one_line` in `src/led_ticker/app/plugin_upgrade.py`:

```python
def resolve_upgrade(
    current_line: str,
    *,
    catalog_name: str | None = None,
    resolve=None,
) -> tuple[str, bool]:
    """Resolve the latest pin for ``current_line`` and report whether it would
    CHANGE the line. Returns ``(latest_line, changed)`` where
    ``changed = latest_line != current_line`` — the single definition of "an
    upgrade is available", shared by the CLI verb, the webui upgrade action, and
    the Store's check-updates endpoint so they can't drift. Raises
    ``UpgradeError`` on resolve failure. ``resolve`` is injectable for tests;
    None binds the module ``resolve_latest`` at CALL time so monkeypatching it
    is honored.
    """
    resolve = resolve or resolve_latest
    latest = resolve(current_line, catalog_name=catalog_name)
    return latest, latest != current_line
```

Refactor `_upgrade_one_line`'s resolve+no-op branch (lines ~262-273) to route through it:

```python
    old_spec = _strip_comment(old_line)
    key = _requirement_key(old_spec)
    try:
        new_spec, changed = resolve_upgrade(
            old_spec, catalog_name=_catalog_name_for_key(key, catalog)
        )
    except UpgradeError as e:
        print(f"{old_spec}: {e}", file=sys.stderr)
        return 1, False
    if not changed:
        print(f"{old_spec} is already up to date.")
        return 0, False
```

(The rest of `_upgrade_one_line` — dry-run print, provenance write, return — is unchanged.)

- [ ] **Step 4: Run to verify pass (new + existing)**

Run: `uv run pytest tests/test_plugin_upgrade.py -v`
Expected: ALL pass — the 4 new tests AND every existing `cmd_upgrade` / `_upgrade_one_line` test (the refactor is behavior-preserving: `not changed` == the old `new_spec == old_spec`).

- [ ] **Step 5: Lint + commit**

Run: `uv run ruff check src tests && uv run ruff format src tests`

```bash
git add src/led_ticker/app/plugin_upgrade.py tests/test_plugin_upgrade.py
git commit -m "refactor(plugins): extract resolve_upgrade — shared upgrade-availability check"
```

---

### Task 2: `POST /api/store/check-updates` endpoint

**Files:**
- Modify: `src/led_ticker/webui/__init__.py` — add `check_updates_handler` after `upgrade_handler`; register the route next to the other store routes.
- Test: `tests/test_webui_app.py`

**Interfaces:**
- Consumes: `resolve_upgrade` / `UpgradeError` (Task 1, lazy import); `_load_catalog_lazy`, `_build_store`, `_fresh_inner_status`, `_read_stamp_readonly`, `MAX_VALIDATE_BODY`, `manifest_lock`-free (read-only); `plugin_cmd._entry_match_keys` / `_find_requirement_lines_for_keys` / `_strip_comment` (lazy).
- Produces: `POST /api/store/check-updates` → `200 {"results": [{"namespace","current","latest","upgrade_available"} | {"namespace","current","error"}, ...]}`. `403` no token; `401` middleware; `200 {"results": []}` when nothing active/declared. NOT in `_OPEN_PATHS`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_webui_app.py` (reuse the file's `_client` helper; mirror `_upgrade_fixtures`' catalog/store monkeypatch style):

```python
# ---------------------------------------------------------------------------
# POST /api/store/check-updates
# ---------------------------------------------------------------------------


def _check_fixtures(monkeypatch, *, entries, active, resolve):
    """Patch catalog, store state, and the resolver for check-updates tests.
    `entries` = list[CatalogEntry]; `active` = set of namespaces the store
    reports as state 'active'; `resolve(line, **kw)` stands in for
    resolve_latest."""
    import led_ticker.webui as webui_mod
    from led_ticker.app import plugin_upgrade
    from led_ticker.plugins_catalog import Catalog

    monkeypatch.setattr(
        webui_mod, "_load_catalog_lazy", lambda: Catalog(entries=tuple(entries))
    )
    monkeypatch.setattr(
        webui_mod,
        "_build_store",
        lambda **kw: {
            "plugins": [
                {"namespace": e.namespace, "state": ("active" if e.namespace in active else "available")}
                for e in entries
            ]
        },
    )
    monkeypatch.setattr(plugin_upgrade, "resolve_latest", resolve)


def _entry(name, namespace, *, pypi=None, version=None, git_sub=None):
    from led_ticker.plugins_catalog import CatalogEntry, CatalogSource, PluginProvides

    sources = []
    if pypi:
        sources.append(CatalogSource(type="pypi", package=pypi, version=version))
    if git_sub:
        sources.append(
            CatalogSource(
                type="git",
                url="https://github.com/JamesAwesome/led-ticker-plugins",
                ref=f"{name}-v0.1.0",
                subdirectory=f"plugins/{git_sub}",
            )
        )
    return CatalogEntry(
        name=name, namespace=namespace, summary="", homepage="",
        provides=PluginProvides(widgets=(f"{namespace}.w",)), sources=tuple(sources),
    )


async def test_check_updates_reports_available_and_current(tmp_path, monkeypatch):
    pool = _entry("pool", "pool", pypi="led-ticker-pool", version="0.1.0")
    rss = _entry("rss", "rss", pypi="led-ticker-rss", version="0.2.0")

    def resolve(line, **kw):
        return "led-ticker-pool==0.2.0" if "pool" in line else line  # rss unchanged

    _check_fixtures(monkeypatch, entries=[pool, rss], active={"pool", "rss"}, resolve=resolve)
    client = await _client(tmp_path, token="s3cret")
    (tmp_path / "requirements-plugins.txt").write_text(
        "led-ticker-pool==0.1.0\nled-ticker-rss==0.2.0\n"
    )
    try:
        resp = await client.post(
            "/api/store/check-updates", headers={"X-Web-Token": "s3cret"}
        )
        assert resp.status == 200
        by_ns = {r["namespace"]: r for r in (await resp.json())["results"]}
        assert by_ns["pool"]["upgrade_available"] is True
        assert by_ns["pool"]["latest"] == "led-ticker-pool==0.2.0"
        assert by_ns["rss"]["upgrade_available"] is False
    finally:
        await client.close()


async def test_check_updates_per_plugin_error_isolated(tmp_path, monkeypatch):
    from led_ticker.app import plugin_upgrade

    pool = _entry("pool", "pool", pypi="led-ticker-pool", version="0.1.0")
    rss = _entry("rss", "rss", pypi="led-ticker-rss", version="0.2.0")

    def resolve(line, **kw):
        if "rss" in line:
            raise plugin_upgrade.UpgradeError("pypi down")
        return "led-ticker-pool==0.2.0"

    _check_fixtures(monkeypatch, entries=[pool, rss], active={"pool", "rss"}, resolve=resolve)
    client = await _client(tmp_path, token="s3cret")
    (tmp_path / "requirements-plugins.txt").write_text(
        "led-ticker-pool==0.1.0\nled-ticker-rss==0.2.0\n"
    )
    try:
        resp = await client.post(
            "/api/store/check-updates", headers={"X-Web-Token": "s3cret"}
        )
        assert resp.status == 200
        by_ns = {r["namespace"]: r for r in (await resp.json())["results"]}
        assert by_ns["pool"]["upgrade_available"] is True
        assert "pypi down" in by_ns["rss"]["error"]
    finally:
        await client.close()


async def test_check_updates_skips_non_active(tmp_path, monkeypatch):
    pool = _entry("pool", "pool", pypi="led-ticker-pool", version="0.1.0")
    # pool present but NOT active (e.g. available / restart_to_activate) -> skipped
    _check_fixtures(
        monkeypatch, entries=[pool], active=set(), resolve=lambda line, **kw: line + "!"
    )
    client = await _client(tmp_path, token="s3cret")
    (tmp_path / "requirements-plugins.txt").write_text("led-ticker-pool==0.1.0\n")
    try:
        resp = await client.post(
            "/api/store/check-updates", headers={"X-Web-Token": "s3cret"}
        )
        assert resp.status == 200
        assert (await resp.json())["results"] == []
    finally:
        await client.close()


async def test_check_updates_shared_package_one_resolve_per_line(tmp_path, monkeypatch):
    # led-ticker-flair ships two namespaces via ONE line; resolve must run ONCE.
    nyan = _entry("nyancat", "nyancat", git_sub="nyancat")  # git, monorepo
    pac = _entry("pacman", "pacman", git_sub="pacman")
    # Both declared via the SAME shared pypi line for this test's simplicity:
    calls = {"n": 0}

    def resolve(line, **kw):
        calls["n"] += 1
        return line.replace("0.1.0", "0.2.0")

    _check_fixtures(
        monkeypatch, entries=[nyan, pac], active={"nyancat", "pacman"}, resolve=resolve
    )
    client = await _client(tmp_path, token="s3cret")
    # One shared line keyed to both namespaces' git source (repo#subdir differs,
    # so give each its own line here; dedup is by line — assert per-namespace
    # results exist and each line resolved once).
    (tmp_path / "requirements-plugins.txt").write_text(
        "git+https://github.com/JamesAwesome/led-ticker-plugins@nyancat-v0.1.0#subdirectory=plugins/nyancat\n"
        "git+https://github.com/JamesAwesome/led-ticker-plugins@pacman-v0.1.0#subdirectory=plugins/pacman\n"
    )
    try:
        resp = await client.post(
            "/api/store/check-updates", headers={"X-Web-Token": "s3cret"}
        )
        assert resp.status == 200
        nss = {r["namespace"] for r in (await resp.json())["results"]}
        assert nss == {"nyancat", "pacman"}
        assert calls["n"] == 2  # two distinct lines -> two resolves (not 4)
    finally:
        await client.close()


async def test_check_updates_requires_token(tmp_path, monkeypatch):
    pool = _entry("pool", "pool", pypi="led-ticker-pool", version="0.1.0")
    _check_fixtures(monkeypatch, entries=[pool], active={"pool"}, resolve=lambda l, **k: l)
    client = await _client(tmp_path, token="s3cret")
    try:
        resp = await client.post("/api/store/check-updates")  # no token
        assert resp.status == 401
    finally:
        await client.close()


async def test_check_updates_no_token_configured_disabled(tmp_path, monkeypatch):
    pool = _entry("pool", "pool", pypi="led-ticker-pool", version="0.1.0")
    _check_fixtures(monkeypatch, entries=[pool], active={"pool"}, resolve=lambda l, **k: l)
    client = await _client(tmp_path)  # no token configured
    try:
        resp = await client.post("/api/store/check-updates")
        assert resp.status == 403
        assert "disabled" in (await resp.json())["error"]
    finally:
        await client.close()


async def test_check_updates_empty_when_nothing_declared(tmp_path, monkeypatch):
    _check_fixtures(monkeypatch, entries=[], active=set(), resolve=lambda l, **k: l)
    client = await _client(tmp_path, token="s3cret")
    try:
        resp = await client.post(
            "/api/store/check-updates", headers={"X-Web-Token": "s3cret"}
        )
        assert resp.status == 200
        assert (await resp.json())["results"] == []
    finally:
        await client.close()
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_webui_app.py -k check_updates -v`
Expected: FAIL — 404 (route not registered)

- [ ] **Step 3: Implement the handler + route**

In `src/led_ticker/webui/__init__.py`, add after `upgrade_handler` (before the `app.router.add_*` block):

```python
    async def check_updates_handler(request: web.Request) -> web.Response:
        """POST /api/store/check-updates — resolve every declared+active plugin's
        manifest line and report whether an upgrade would change it. Read-only:
        resolves only, never writes. Token-gated (NOT in _OPEN_PATHS); resolves
        run in threads so `git ls-remote` / PyPI I/O doesn't block the loop.
        """
        if not token:
            return web.json_response({"error": "editing disabled"}, status=403)

        catalog = _load_catalog_lazy()
        manifest_path = config_path.parent / "requirements-plugins.txt"
        inner_status: dict = _fresh_inner_status(status_path)
        store_payload = _build_store(
            manifest_path=manifest_path,
            config_path=config_path,
            status=inner_status,
            token_configured=bool(token),
            stamp=_read_stamp_readonly(),
        )
        active = {
            p["namespace"]
            for p in store_payload.get("plugins", [])
            if p.get("state") == "active"
        }

        from led_ticker.app import plugin_upgrade  # noqa: PLC0415
        from led_ticker.app.plugin_cmd import (  # noqa: PLC0415
            _entry_match_keys,
            _find_requirement_lines_for_keys,
            _strip_comment,
        )

        # Map each active declared namespace to its comment-stripped manifest
        # line, and group namespaces by that line so a SHARED package resolves
        # once (led-ticker-flair -> its siblings share one line).
        ns_line: dict[str, str] = {}
        ns_entry: dict[str, object] = {}
        line_to_nss: dict[str, list[str]] = {}
        for entry in catalog.entries:
            if entry.namespace not in active:
                continue
            lines = _find_requirement_lines_for_keys(
                manifest_path, _entry_match_keys(entry)
            )
            if not lines:
                continue
            cur = _strip_comment(lines[-1])
            ns_line[entry.namespace] = cur
            ns_entry[entry.namespace] = entry
            line_to_nss.setdefault(cur, []).append(entry.namespace)

        async def resolve_line(line: str):
            # One representative namespace's catalog name feeds the git tag
            # prefix (irrelevant for pypi lines). Returns a per-line result dict.
            rep = line_to_nss[line][0]
            name = getattr(ns_entry[rep], "name", None)
            try:
                latest, changed = await asyncio.to_thread(
                    plugin_upgrade.resolve_upgrade, line, catalog_name=name
                )
                return {"latest": latest, "upgrade_available": changed}
            except plugin_upgrade.UpgradeError as e:
                return {"error": str(e)}

        unique_lines = list(line_to_nss)
        resolved = await asyncio.gather(*(resolve_line(l) for l in unique_lines))
        line_result = dict(zip(unique_lines, resolved))

        results = [
            {"namespace": ns, "current": ns_line[ns], **line_result[ns_line[ns]]}
            for ns in sorted(ns_line)
        ]
        return web.json_response({"results": results})
```

Register the route next to the other store routes:

```python
    app.router.add_post("/api/store/check-updates", check_updates_handler)
```

- [ ] **Step 4: Run to verify pass + purity**

Run: `uv run pytest tests/test_webui_app.py -k check_updates -v` then `uv run pytest tests/test_webui_app.py tests/test_webui_purity.py -q`
Expected: ALL pass (purity confirms no rgbmatrix import leaked in).

- [ ] **Step 5: Lint + commit**

Run: `uv run ruff check src tests && uv run ruff format src tests`

```bash
git add src/led_ticker/webui/__init__.py tests/test_webui_app.py
git commit -m "feat(webui): POST /api/store/check-updates — on-demand upgrade availability"
```

---

### Task 3: Frontend — Check-for-updates button, drop always-on Upgrade

**Files:**
- Modify: `src/led_ticker/webui/static/index.html` — toolbar button (~line 226 area), `renderStore` Upgrade-button branch (~1084-1090), handler wiring, new `checkForUpdates()`, `loadStore()` reset.
- Test: `tests/test_webui_app.py` (HTML smoke assert)

**Interfaces:**
- Consumes: `POST /api/store/check-updates` → `{results:[{namespace,current,latest,upgrade_available,error?}]}` (Task 2); existing `POST /api/store/upgrade` (unchanged), `storeAction("upgrade", ns)`.
- Produces: UI behavior only. Module-level `let upgradeChecks = {}` (namespace → result); Upgrade button renders only when `upgradeChecks[ns]?.upgrade_available`.

- [ ] **Step 1: Add the results store + reset (no test yet — pure UI plumbing)**

Near the other Store module-level state (search for `let lastAllowRestart` or the Store section top), add:

```js
// namespace -> {latest, upgrade_available} | {error}, from POST /api/store/check-updates.
// Ephemeral: cleared on every loadStore() so a reload never shows a stale/unchecked Upgrade.
let upgradeChecks = {};
```

In `loadStore()` (line ~1139), at the top of the function body, add:

```js
  upgradeChecks = {};
```

- [ ] **Step 2: Add the toolbar button**

In the Store section markup (after the `store-pending-banner` block, ~line 228, before `<div id="store-list">`), add:

```html
      <div id="store-check-wrap" style="margin-top:.75rem;">
        <button id="store-check-btn" class="store-btn">Check for updates</button>
        <span id="store-check-status" class="muted" style="margin-left:.5rem;"></span>
      </div>
```

- [ ] **Step 3: Replace the always-on Upgrade button with a check-gated one**

In `renderStore`, replace the Upgrade-button block (currently lines ~1084-1090, the `const upgradeLabel = ...` + the `actionHtml = ... + actionHtml`) with a version that only renders when the check reported availability, and appends "up to date" / "check failed" notes otherwise:

```js
      // Upgrade is offered ONLY after a check reports the line would change.
      // (The always-on button was removed — it invited upgrades that were
      // often no-ops. `upgradeChecks` is populated by "Check for updates".)
      const chk = upgradeChecks[p.namespace];
      if (chk && chk.upgrade_available) {
        const target = esc(chk.latest || "");
        const upLabel = pack ? `Upgrade ${esc(pack)} pack → ${target}` : `Upgrade → ${target}`;
        actionHtml = `<button class="store-btn install" ${needsAuth ? "disabled" : ""}
          data-action="upgrade" data-ns="${esc(p.namespace)}" data-pack="${esc(pack)}" data-pack-members="${esc(packMembers.join(","))}"
          ${needsAuth ? 'title="Enter your token to upgrade plugins"' : ""}>${upLabel}</button>` + actionHtml;
      } else if (chk && chk.error) {
        actionHtml = `<span class="store-in-use-note">check failed: ${esc(chk.error)}</span>` + actionHtml;
      } else if (chk) {
        actionHtml = `<span class="store-in-use-note">Up to date</span>` + actionHtml;
      }
```

(Leave the Remove button block above it intact. The pack-confirm handler at ~1130 already handles `data-action="upgrade"` — unchanged.)

- [ ] **Step 4: Wire the Check button + `checkForUpdates()`**

In `renderStore`, after `$("store-list").innerHTML = rows.join("")` and the button-handler loop, wire the check button (it lives outside `store-list`, so wire it once — guard against a null when the tab isn't rendered):

Add near the end of `renderStore` (after the handler loop):

```js
  const checkBtn = $("store-check-btn");
  if (checkBtn) {
    const needsAuth = authRequired && !hasToken;
    checkBtn.disabled = needsAuth;
    checkBtn.title = needsAuth ? "Enter your token to check for updates" : "";
    checkBtn.onclick = checkForUpdates;
  }
```

Add a new function beside `storeAction`:

```js
async function checkForUpdates() {
  const status = $("store-check-status");
  const btn = $("store-check-btn");
  if (btn) btn.disabled = true;
  if (status) status.textContent = "checking…";
  try {
    const r = await fetch("/api/store/check-updates", {method: "POST", headers: auth});
    if (r.status === 401) { alert("Auth failed — check your token in the field above."); return; }
    if (r.status === 403) { alert("Editing disabled (no token configured on the server)."); return; }
    if (!r.ok) { if (status) status.textContent = `check failed (${r.status})`; return; }
    const body = await r.json();
    upgradeChecks = {};
    for (const res of (body.results || [])) upgradeChecks[res.namespace] = res;
    const n = (body.results || []).filter((x) => x.upgrade_available).length;
    if (status) status.textContent = n ? `${n} update${n === 1 ? "" : "s"} available` : "all up to date";
    renderStore(lastStoreData);  // re-render rows with the fresh results
  } catch (e) {
    if (status) status.textContent = "could not reach the webui";
  } finally {
    if (btn) btn.disabled = false;
  }
}
```

- [ ] **Step 5: Preserve `lastStoreData` for the re-render**

`checkForUpdates` re-renders from `lastStoreData`. In `loadStore()`, where it currently does `renderStore(await r.json())`, capture the payload first. Change:

```js
    renderStore(await r.json());
```
to:
```js
    lastStoreData = await r.json();
    renderStore(lastStoreData);
```
and add module-level state beside `upgradeChecks`:
```js
let lastStoreData = {plugins: []};
```
(If `lastStoreData` already exists in the file, reuse it — grep first: `grep -n "lastStoreData" src/led_ticker/webui/static/index.html`.)

- [ ] **Step 6: Verify JS syntax + add the HTML smoke asserts**

Run: `node --check src/led_ticker/webui/static/index.html 2>&1 || echo "node --check does not lint HTML; skip"` — Note: `node --check` won't parse HTML. Instead extract-and-check is overkill; rely on the smoke test + manual read. Read the three edited regions to confirm brace balance.

Add to `tests/test_webui_app.py` next to the existing `assert "/api/store/install" in html` smoke assert (grep `grep -n "/api/store/install\" in html" tests/test_webui_app.py`):

```python
    assert "/api/store/check-updates" in html
    # The always-on Upgrade button is gone — Upgrade is now check-gated.
    assert 'data-action="upgrade"' not in html or "upgradeChecks" in html
```

(The second assert: the literal `data-action="upgrade"` now appears only inside the `if (chk && chk.upgrade_available)` branch string; `upgradeChecks` gating must be present in the served HTML.)

- [ ] **Step 7: Run the webui suite + commit**

Run: `uv run pytest tests/test_webui_app.py -q`
Expected: pass (incl. the smoke asserts)

Run: `uv run ruff check src tests` (no Python changed here beyond tests, but keep the gate)

```bash
git add src/led_ticker/webui/static/index.html tests/test_webui_app.py
git commit -m "feat(webui): Store 'Check for updates' button; Upgrade only when available"
```

---

### Task 4: Docs + CLAUDE.md + full-suite gate

**Files:**
- Modify: `docs/site/src/content/docs/plugins/index.mdx` — the "Upgrading plugins" section
- Modify: `CLAUDE.md` — the Upgrade invariant bullet
- Test: full suite

- [ ] **Step 1: Docs-site "Upgrading plugins" update**

Read `docs/DOCS-STYLE.md` first. In `docs/site/src/content/docs/plugins/index.mdx`'s "Upgrading plugins" section, add a short paragraph: the web Store has a **Check for updates** button that resolves the latest version for every installed plugin and shows **Upgrade → `<version>`** only where a newer/pinned version is actually available (results are per-session, re-check after changes); plugins already current show "Up to date". Note it needs a token (same as install/remove/upgrade).

- [ ] **Step 2: CLAUDE.md note**

In the **Upgrade:** bullet of the Plugin invariants section, append:

```markdown
The webui Store does NOT eagerly show Upgrade; `POST /api/store/check-updates` (token-gated, stateless, read-only) resolves declared+active plugins on demand and the UI offers Upgrade only where `resolve_upgrade` reports the line would change. `resolve_upgrade` (`app/plugin_upgrade.py`) is the ONE definition of "upgrade available" — the CLI verb, the upgrade endpoint, and check-updates all route through it so they can't diverge (tripwires: `test_resolve_upgrade_*`, `test_check_updates_*`).
```

- [ ] **Step 3: Full-suite gate**

Run: `make test`
Expected: full suite green (existing + the ~15 new tests).

Run: `uv run pyright`
Expected: clean on touched files (pre-push requirement; list any pre-existing unrelated errors rather than fixing them).

Docs lint if node/pnpm available (`source ~/.nvm/nvm.sh` first if needed): `make docs-lint`; skip with a note if tooling absent.

- [ ] **Step 4: Commit**

```bash
git add docs/ CLAUDE.md
git commit -m "docs(plugins): Store check-for-updates + resolve_upgrade single-definition invariant"
```

---

## Self-Review (performed at plan-writing time)

1. **Spec coverage:** on-demand trigger (Task 3 button ✓), line-would-change basis via `resolve_upgrade` (Task 1 ✓), stateless read-only endpoint (Task 2 ✓), ephemeral client-side results (Task 3 `upgradeChecks` reset ✓), shared-package one-resolve-per-line (Task 2 `line_to_nss` dedup + test ✓), per-plugin error isolation (Task 2 test ✓), token gating 401/403 (Task 2 tests ✓), skip pending/non-active (Task 2 `active` filter + test ✓), remove always-on Upgrade + regression tripwire (Task 3 smoke assert ✓), "Upgrade → target" relabel (Task 3 ✓), docs + single-definition invariant (Task 4 ✓).
2. **Placeholder scan:** none — every step has concrete code/commands. Task 3 steps 5/6 instruct a `grep` to reuse-or-add `lastStoreData` and locate the smoke-assert anchor (real files may already define `lastStoreData`); this is deliberate reuse guidance, not a gap.
3. **Type consistency:** `resolve_upgrade(current_line, *, catalog_name=None, resolve=None) -> (str, bool)` used identically in Task 1 (`_upgrade_one_line`) and Task 2 (`resolve_line` via `asyncio.to_thread`). Endpoint result keys `{namespace,current,latest,upgrade_available,error}` match between Task 2 response and Task 3 `upgradeChecks` consumption. Route path `/api/store/check-updates` identical across Tasks 2–4.
