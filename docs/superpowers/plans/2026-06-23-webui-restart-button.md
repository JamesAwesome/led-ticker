# Web UI Restart Control Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A token-gated "restart the display" control in the webui (Store pending banner + config-editor restart-required notice) that bounces the display process so a restart-to-activate change takes effect — no SSH.

**Architecture:** The webui writes a `restart-requested` sentinel into the shared `ticker-status` volume (mirroring the existing `preview-requested` marker); the display polls it in its main loop, deletes it, and `sys.exit(0)`s; the supervisor (`restart: unless-stopped`) restarts → Spec-1 reconcile runs. Gated by a new `[web] allow_restart` flag (default off; Docker example on) + the existing token.

**Tech Stack:** Python 3.14, aiohttp webui, attrs/dataclass config, the shared `ticker-status` tmpfs volume.

**Spec:** `docs/superpowers/specs/2026-06-23-webui-restart-button-design.md`

## Global Constraints

- **Webui rgbmatrix-pure** — `tests/test_webui_purity.py` stays green.
- **Restart is double-gated:** token (not in `_OPEN_PATHS`) AND `[web] allow_restart` (default `False`).
- **Loop-safety:** the display deletes the marker BEFORE exiting (the restarted process must not re-see it). Tripwire the ordering.
- **Clean exit only:** `sys.exit(0)` — never a crash path.
- **Marker:** `status_path.parent / "restart-requested"` (the shared `ticker-status` volume; same dir as `preview-requested`). Both containers derive the dir from `[web] status_path`.
- **`allow_restart`** surfaces in `GET /api/status` and `GET /api/store` (public flag, like `auth_required`) so the UI enables/disables the button.
- **Gates:** `PYTHONPATH=tests/stubs uv run --extra dev pytest`; `uv run --extra dev ruff check src/ tests/` + `ruff format`; `pyright src/`; `make docs-build` + `docs-lint` (docs task).
- **NON-GOALS:** container/host reboot; auto-restart on manifest/config change; working without a supervisor (the flag guards it); any arbitrary-command surface (only this one marker).

## File Structure
- `src/led_ticker/config.py` — `WebConfig.allow_restart` + parse.
- `src/led_ticker/app/run.py` — restart-marker poll helper + wire into the main loop.
- `src/led_ticker/webui/__init__.py` — `POST /api/restart` + thread `allow_restart` + expose it in status/store payloads.
- `src/led_ticker/webui/static/index.html` — the reusable restart button.
- `config/config.example.toml` — `[web] allow_restart = true`.
- Docs: webui/plugins pages — the supervisor requirement + how to enable.
- Tests: `tests/test_config.py`, `tests/test_status_instrumentation.py` (or run.py tests), `tests/test_webui_app.py`.

---

## Task 1: `WebConfig.allow_restart`

**Files:** Modify `src/led_ticker/config.py`; Test `tests/test_config.py`

**Interfaces — Produces:** `WebConfig.allow_restart: bool = False`, parsed from `[web] allow_restart` (bool-validated).

- [ ] **Step 1: failing test** — `tests/test_config.py` (mirror existing `_parse_web_block`/WebConfig tests):
```python
def test_web_block_allow_restart_parsed():
    from led_ticker.config import _parse_web_block
    cfg = _parse_web_block({"web": {"allow_restart": True}})
    assert cfg is not None and cfg.allow_restart is True

def test_web_block_allow_restart_defaults_false():
    from led_ticker.config import _parse_web_block
    cfg = _parse_web_block({"web": {}})
    assert cfg is not None and cfg.allow_restart is False
```

- [ ] **Step 2: run, expect fail** — `PYTHONPATH=tests/stubs uv run --extra dev pytest tests/test_config.py -k allow_restart -v`.
- [ ] **Step 3: implement** — add to the `WebConfig` dataclass (after `status_path`, ~line 206):
```python
    allow_restart: bool = False  # enables the web UI "restart display" control; requires a process supervisor
```
In `_parse_web_block` (the `WebConfig(...)` constructor ~line 287), add `allow_restart=w_raw.get("allow_restart", False),` and add a bool-validation next to the existing `http_port` bool check (~line 298):
```python
    if not isinstance(cfg.allow_restart, bool):
        raise ValueError("[web] allow_restart must be a boolean (true/false)")
```
- [ ] **Step 4: run, expect pass.** **Step 5: commit** (`feat(config): [web] allow_restart flag`).

---

## Task 2: Display restart-marker poll + main-loop wiring

**Files:** Modify `src/led_ticker/app/run.py`; Test `tests/test_status_instrumentation.py`

**Interfaces — Produces:** `def _consume_restart_marker(marker_path: Path) -> bool` — returns True iff a restart was requested, **deleting the marker first** (loop-safety). The main loop calls it each pass and `sys.exit(0)`s on True.

- [ ] **Step 1: failing tests** (the helper — no real exit):
```python
def test_consume_restart_marker_detects_and_deletes(tmp_path):
    from led_ticker.app.run import _consume_restart_marker
    m = tmp_path / "restart-requested"; m.write_text("")
    assert _consume_restart_marker(m) is True
    assert not m.exists()  # deleted BEFORE the caller exits — loop-safety

def test_consume_restart_marker_absent_is_false(tmp_path):
    from led_ticker.app.run import _consume_restart_marker
    assert _consume_restart_marker(tmp_path / "restart-requested") is False
```

- [ ] **Step 2: run, expect fail.**
- [ ] **Step 3: implement** the helper (module level in run.py):
```python
def _consume_restart_marker(marker_path: Path) -> bool:
    """True if a web-UI restart was requested. Deletes the marker FIRST so the
    restarted process doesn't re-read it and exit again (loop-safety)."""
    if not marker_path.exists():
        return False
    marker_path.unlink(missing_ok=True)
    return True
```
Wire it into the main `while True` loop (read run.py ~line 637 + the existing `preview-requested` poll at ~382 to place it consistently). Compute the marker once near the watcher/preview setup:
```python
    _restart_marker = Path(config.web.status_path).expanduser().parent / "restart-requested"
```
and at the top of each loop pass (next to `watcher.changed()`):
```python
                if _consume_restart_marker(_restart_marker):
                    logging.info("restart requested via web UI — exiting for supervisor restart")
                    sys.exit(0)
```
(Confirm `sys` is imported; the dir matches where the webui writes — both use `[web] status_path`'s parent.)
- [ ] **Step 4: run** the helper tests + the full suite (`PYTHONPATH=tests/stubs uv run --extra dev pytest -q`) → pass. **Step 5: commit** (`feat: display polls a web-UI restart marker (delete-before-exit)`).

---

## Task 3: `POST /api/restart` + expose `allow_restart`

**Files:** Modify `src/led_ticker/webui/__init__.py`; Test `tests/test_webui_app.py`

**Interfaces — Consumes:** `allow_restart: bool` (threaded from `web_cfg` through `build_webui_app`/`run_webui`), the configured `token`, `status_path`. **Produces:** `POST /api/restart` + `allow_restart` in the `/api/status` and `/api/store` payloads.

- [ ] **Step 1: failing tests:** `POST /api/restart` with token + `allow_restart=True` → 200 and `status_path.parent/"restart-requested"` exists; no token (token configured) → 401/403; `allow_restart=False` → 403 `{"error":"restart disabled"}` and NO marker; `GET /api/status` and `GET /api/store` include `allow_restart`. (Mirror the existing install/save handler tests for client + token wiring.)
- [ ] **Step 2: run, expect fail.**
- [ ] **Step 3: implement:**
  - Thread `allow_restart` through `build_webui_app(... allow_restart: bool = False)` and `run_webui` (pass `web_cfg.allow_restart`).
  - Add `restart_handler` (token-gated like the mutation handlers; NOT in `_OPEN_PATHS`):
```python
    async def restart_handler(request: web.Request) -> web.Response:
        if not token:
            return web.json_response({"error": "editing disabled"}, status=403)
        if not allow_restart:
            return web.json_response({"error": "restart disabled"}, status=403)
        (status_path.parent / "restart-requested").write_text("")
        return web.json_response({"ok": True})
```
  Register `app.router.add_post("/api/restart", restart_handler)`.
  - In the `status_handler` response and the `store_handler`/`build_store` payload, add `"allow_restart": allow_restart` (public flag).
- [ ] **Step 4: run** `tests/test_webui_app.py` + `tests/test_webui_purity.py` + full suite → pass; ruff + pyright. **Step 5: commit** (`feat(webui): token+flag-gated POST /api/restart + expose allow_restart`).

---

## Task 4: Frontend — the reusable "Restart to apply" button

**Files:** Modify `src/led_ticker/webui/static/index.html`; Test: extend `tests/test_webui_app.py` (static markers)

- [ ] **Step 1:** Read the existing Store **pending banner** + the config-editor **restart-required notice** + the token-field/auth handling in index.html.
- [ ] **Step 2:** Add a reusable **"Restart to apply"** button (with subtext "Quick restart to activate your changes — the sign goes dark ~5–10s") in BOTH places, driven by the `allow_restart` flag from the payload:
  - `allow_restart` true + token present → **enabled**.
  - `allow_restart` true + no token → the existing auth prompt (needs the token).
  - `allow_restart` false → **disabled**, with a `title` tooltip: "Browser restart is off — set `[web] allow_restart = true` (and ensure your service auto-restarts: Docker, or systemd Restart=)".
  - **Click:** `confirm("The sign will go dark for a few seconds while the display restarts. Continue?")` → `POST /api/restart` with the `X-Web-Token` header → show **"restarting… (usually ~5–10s)"** with a live elapsed counter (setInterval) → poll `GET /api/status` until `display_online` recovers (drops then returns) → clear the banner / refresh the Store. On ~60s timeout: "The display hasn't come back. Refresh this page; if the sign is still dark, check the container is running (`docker compose ps`) and view the logs." `esc()` all strings; token via header only.
- [ ] **Step 3:** Extend `tests/test_webui_app.py`: static assertions that index.html contains the restart button + the confirm text + the disabled-tooltip + reads `allow_restart`. (No JS runner — note the interactive restart/poll/timeout flow as a manual/maintainer check in your report.)
- [ ] **Step 4:** `PYTHONPATH=tests/stubs uv run --extra dev pytest tests/test_webui_app.py tests/test_webui_purity.py -q` green. **Step 5: commit** (`feat(webui): Restart to apply button (Store + config editor)`).

---

## Task 5: Config example + docs

**Files:** Modify `config/config.example.toml`; the webui + plugins docs pages.

- [ ] **Step 1:** In `config/config.example.toml`'s `[web]` block, add `allow_restart = true` with a comment that it enables the browser restart button and requires a process supervisor (Docker's `restart: unless-stopped` — shipped — or systemd `Restart=`). Verify other example configs' `[web]` blocks (if any) get the same treatment or a note.
- [ ] **Step 2:** Docs (`docs/site/.../concepts/web-status-ui.mdx` + the plugins page): document the "Restart to apply" button — what it does (bounces the display process, panel dark ~seconds, not a reboot), the `[web] allow_restart` flag (default off; on in the Docker example), and the **bare-metal requirement** (systemd `Restart=always`/`on-success`) before enabling.
- [ ] **Step 3:** `make docs-build` + `make docs-lint` clean. **Step 4: commit** (`docs: web UI restart control + allow_restart`).

---

## Self-Review

**Spec coverage:** allow_restart flag→T1; display marker poll + delete-before-exit→T2; POST /api/restart (double-gated) + payload exposure→T3; reusable button + confirm/elapsed/timeout/disabled-tooltip→T4; Docker example + docs/supervisor→T5. ✅

**Placeholder scan:** concrete code for T1–T3; T4 (frontend) + T5 (docs) are directed-read + integration tasks against existing surfaces (the pending banner, the restart-required notice, the example `[web]` block) — explicit reads, not vague TODOs.

**Type consistency:** `_consume_restart_marker(Path)->bool` (T2) used in the run loop; `allow_restart: bool` threaded config→`_parse_web_block`(T1)→`build_webui_app`/`run_webui`/handlers(T3)→payload→frontend(T4); marker path `status_path.parent/"restart-requested"` identical in T2 (display) and T3 (webui).

**Notes for the executor:** (1) **Loop-safety is the load-bearing invariant** — T2's delete-before-exit must be asserted (the test checks the marker is gone when the helper returns True). (2) The webui must stay **rgbmatrix-pure** (T3/T4 — purity test). (3) The **restart round-trip** (marker→exit→supervisor→reconcile) + the frontend interactive flow are a **maintainer deploy-smoke** — not unit-testable; flag, don't fake.
