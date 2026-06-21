# Web Config Editor (Spec B) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an operator edit the running `config.toml` from the web UI — a full-TOML editor that validates, guards against clobber, writes atomically, and lets the display's existing hot-reload apply the change — surfacing whether the edit applied live or needs a restart.

**Architecture:** The webui sidecar gains a token-gated `PUT /api/config` that validates the submitted TOML, restores any redacted `•••` placeholder from disk (defense-in-depth net), conflict-checks against a base hash, backs up to `config.toml.bak`, and atomically writes `config.toml`. The display process's existing `ConfigWatcher` (hot-reload, PR #250) detects the write and applies it — no new apply code. The editor UI shows the post-save verdict from the status board's `last_reload` record. Spec A already made first-party config secret-free, so the editor serves/saves verbatim in practice (redaction is a no-op then).

**Tech Stack:** Python 3.14, aiohttp, stdlib `hashlib`/`os`/`tempfile`, pytest, vanilla JS (existing `webui/static/index.html`).

## Global Constraints

- Python 3.14; no `from __future__ import annotations`.
- Run `uv run --extra dev ruff check src/ tests/` before every push (CI lint).
- **Broken local git pre-commit/pre-push hook** — commit AND push with `--no-verify`; run `uv run pytest` + ruff manually. `make docs-lint` for docs.
- Never commit on `main`; branch off `main` (Spec A merged). No "gun"/"footgun" metaphors; docs follow `docs/DOCS-STYLE.md` (no release-history framing).
- No merge or tag without explicit user consent.
- Depends on Spec A (merged): config is secret-free; tokens resolve env-first.
- **Writes require a token:** with no token configured, the instance is read-only — write endpoints return `403`. (The token is resolved via `resolve_secret_token("LED_TICKER_WEB_TOKEN", web_cfg.token, ...)` already wired in `run_webui`.)
- Redaction sentinel is `REDACTED = '"•••"'` in `webui/redact.py`.

---

### Task 1: `config_hash` helper + GET /api/config returns the hash

**Files:**
- Modify: `src/led_ticker/reload.py` (add module-level `config_hash`)
- Modify: `src/led_ticker/webui/__init__.py` (`config_handler` returns `hash`)
- Test: `tests/test_reload.py` (or new `tests/test_config_hash.py`); `tests/test_webui/` config-handler test

**Interfaces:**
- Produces: `led_ticker.reload.config_hash(path: Path) -> str | None` — `sha256` hex of the file bytes, or `None` if unreadable. Same digest `ConfigWatcher` uses internally.
- Produces: `GET /api/config` JSON gains `"hash": "<sha256-hex>"` (None→absent/empty) alongside the existing `state`/`toml`/`geometry`.

- [ ] **Step 1: Branch + failing test for `config_hash`**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker
git checkout main && git pull --ff-only origin main
git checkout -b feat/web-config-editor
git branch --show-current   # MUST be feat/web-config-editor — if main, STOP
```
Add to `tests/test_reload.py`:
```python
def test_config_hash_matches_sha256(tmp_path):
    import hashlib
    from led_ticker.reload import config_hash

    p = tmp_path / "c.toml"
    p.write_bytes(b"[display]\nrows = 16\n")
    assert config_hash(p) == hashlib.sha256(b"[display]\nrows = 16\n").hexdigest()


def test_config_hash_missing_file_is_none(tmp_path):
    from led_ticker.reload import config_hash

    assert config_hash(tmp_path / "nope.toml") is None
```

- [ ] **Step 2: Run — fails**

```bash
uv run pytest tests/test_reload.py -k config_hash -v
```
Expected: FAIL (`ImportError: cannot import name 'config_hash'`).

- [ ] **Step 3: Add `config_hash` to `reload.py`**

In `src/led_ticker/reload.py` (it already imports `hashlib`, `os`, `Path`), add at module level:
```python
def config_hash(path: Path) -> str | None:
    """The sha256 hex of the file's bytes (the same digest ConfigWatcher uses
    to confirm a change), or None when the file is unreadable. The web editor
    uses this as a conflict-detection version stamp."""
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None
```
(Optionally refactor `ConfigWatcher._hash` to call it — only if trivial; do not change its behavior.)

- [ ] **Step 4: Return the hash from GET /api/config**

In `src/led_ticker/webui/__init__.py` `config_handler`, add `from led_ticker.reload import config_hash` (top of file) and include the hash in the response. Change the final return to:
```python
        return web.json_response(
            {
                "state": "ok",
                "toml": redact_toml(text),
                "geometry": geometry,
                "hash": config_hash(target) or "",
            }
        )
```
(Redaction stays — for secret-free first-party config it's a no-op; it remains the net for a third-party inline secret.)

- [ ] **Step 5: Test the handler returns a hash**

Add to the existing webui config-handler test file (find it: `grep -rl "api/config" tests/`) a case asserting `GET /api/config` JSON has a non-empty `hash` equal to `config_hash(config_path)`. Mirror the existing handler-test harness (aiohttp test client or the project's pattern). Run it; expect PASS.

- [ ] **Step 6: Full suite + lint + commit**

```bash
uv run pytest -q 2>&1 | tail -5
uv run --extra dev ruff check src/ tests/ 2>&1 | tail -2
git add src/led_ticker/reload.py src/led_ticker/webui/__init__.py tests/
git commit --no-verify -m "feat(webui): config_hash helper + GET /api/config returns it (editor version stamp)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: `restore_redacted` helper (redaction net for save)

**Files:**
- Modify: `src/led_ticker/webui/redact.py` (add `restore_redacted`)
- Test: `tests/test_webui/test_redact.py` (find existing redact test: `grep -rl redact tests/`)

**Interfaces:**
- Produces: `led_ticker.webui.redact.restore_redacted(submitted: str, disk: str) -> str` — returns `submitted` with every line whose redact-matched value is the `•••` sentinel replaced by the corresponding key's line from `disk`. Lines with a real (non-sentinel) value pass through unchanged. A sentinel whose key is not found in `disk` is left as-is (the caller rejects on any remaining sentinel — see Task 3).

- [ ] **Step 1: Branch check + failing test**

```bash
git branch --show-current   # MUST be feat/web-config-editor — if main, STOP
```
Read `src/led_ticker/webui/redact.py` to reuse its `_KV` regex / key-matching. Add to the redact test file:
```python
from led_ticker.webui.redact import restore_redacted


def test_restore_replaces_sentinel_from_disk():
    disk = 'name = "feed"\ntoken = "real-secret"\n'
    submitted = 'name = "feed renamed"\ntoken = "•••"\n'
    out = restore_redacted(submitted, disk)
    assert 'token = "real-secret"' in out
    assert 'name = "feed renamed"' in out  # non-secret edit preserved


def test_restore_passes_through_when_no_sentinel():
    disk = 'token = "real"\n'
    submitted = 'token = "new-real-value"\n'  # user typed a new secret
    assert restore_redacted(submitted, disk) == submitted  # writes through verbatim


def test_restore_leaves_unmatched_sentinel():
    # sentinel for a key absent from disk → left as-is (caller rejects)
    disk = "other = 1\n"
    submitted = 'token = "•••"\n'
    assert '"•••"' in restore_redacted(submitted, disk)
```

- [ ] **Step 2: Run — fails**

```bash
uv run pytest tests/test_webui/test_redact.py -k restore -v
```
Expected: FAIL (`ImportError`).

- [ ] **Step 3: Implement `restore_redacted`**

In `redact.py`, add (reuse the existing `_KV` pattern's key group; match line-by-line):
```python
def restore_redacted(submitted: str, disk: str) -> str:
    """Replace each redacted-sentinel value in `submitted` with the real value
    for that key from `disk`. A line whose value is not the sentinel passes
    through unchanged; a sentinel whose key is absent from disk is left as-is
    (the caller refuses to write a literal sentinel). Defense-in-depth for a
    third-party plugin that left a secret in config.toml — a no-op when config
    is secret-free (the normal first-party case)."""
    disk_values: dict[str, str] = {}
    for line in disk.splitlines():
        m = _KV.match(line)
        if m:
            disk_values[m.group("key").strip()] = line

    out: list[str] = []
    for line in submitted.splitlines():
        m = _KV.match(line)
        if m and m.group("value").strip() == REDACTED.strip():
            key = m.group("key").strip()
            out.append(disk_values.get(key, line))
        else:
            out.append(line)
    return "\n".join(out) + ("\n" if submitted.endswith("\n") else "")
```
> NOTE: `_KV` must expose named groups `key` and `value`. Read the current pattern — it has `prefix`/`key`/`eq` and a value alternation; ensure (or add) a `(?P<value>...)` group around the value alternation so this helper can read it. If adding the group, keep `redact_toml`'s replacement (`m.group("prefix")+m.group("key")+m.group("eq")+REDACTED`) working unchanged. Adjust the group names in this helper to whatever the actual pattern uses (`eq` vs the test's `=`). The behavioral tests above are the contract.

- [ ] **Step 4: Run — passes**

```bash
uv run pytest tests/test_webui/test_redact.py -v
```
Expected: PASS (new + existing redact tests).

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/webui/redact.py tests/test_webui/test_redact.py
git commit --no-verify -m "feat(webui): restore_redacted — preserve secrets across an edit-save round-trip

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: `PUT /api/config` — validate → restore → conflict → backup → atomic write

**Files:**
- Modify: `src/led_ticker/webui/__init__.py` (`_add_config_routes` gains the save handler; pass `token` in)
- Test: the webui handler test file

**Interfaces:**
- Consumes: `config_hash` (Task 1), `restore_redacted` (Task 2), `validate_config_text` + `_result_to_json` (existing), `REDACTED` (redact).
- Produces: `PUT /api/config` — request body `{"toml": "<text>", "base_hash": "<hex>"}`. Responses: `200 {"state":"saved","hash":"<new>"}`; `403 {"error":"editing disabled"}` (no token); `413` (oversize); `422 {...validation errors...}`; `409 {"error":"conflict","hash":"<disk>"}` (base_hash≠disk); `400` (malformed body or remaining `•••` sentinel that couldn't be restored).

- [ ] **Step 1: Branch check + thread `token` into `_add_config_routes`**

```bash
git branch --show-current   # MUST be feat/web-config-editor — if main, STOP
```
In `build_webui_app`, change `_add_config_routes(app, config_path)` → `_add_config_routes(app, config_path, token)` and update the def signature: `def _add_config_routes(app, config_path: Path, token: str = "") -> None:`. (The save handler needs `token` to enforce write-requires-token; reads stay open.)

- [ ] **Step 2: Failing tests for the save handler**

Add to the webui handler test file (mirror its client harness). Cover every branch:
```python
async def test_put_config_rejects_without_token(...):
    # app built with token="" → PUT returns 403, file unchanged
    ...

async def test_put_config_writes_valid_toml(...):
    # app built with token="t"; PUT valid toml + correct base_hash + token header
    # → 200, file updated, .bak holds the prior contents, response hash == new disk hash
    ...

async def test_put_config_rejects_invalid_toml(...):
    # invalid config → 422, file unchanged, no .bak churn
    ...

async def test_put_config_conflict_on_stale_base_hash(...):
    # base_hash != current disk hash → 409, file unchanged
    ...

async def test_put_config_restores_redacted_secret(...):
    # disk has token="real"; submit body with token="•••" + valid otherwise
    # → 200, written file contains token="real" (restored), not the sentinel
    ...
```
Write these against the project's existing webui test harness (find it under `tests/test_webui/`; reuse its app/client fixtures). Each asserts the on-disk file state after the call.

- [ ] **Step 3: Run — fails**

```bash
uv run pytest tests/test_webui/ -k put_config -v
```
Expected: FAIL (no PUT route).

- [ ] **Step 4: Implement the save handler**

In `_add_config_routes`, add (and register `app.router.add_put("/api/config", save_handler)`):
```python
    async def save_handler(request: web.Request) -> web.Response:
        if not token:
            return web.json_response({"error": "editing disabled"}, status=403)
        if (request.content_length or 0) > MAX_VALIDATE_BODY:
            return web.json_response({"error": "body too large"}, status=413)
        try:
            payload = await request.json()
        except ValueError:
            return web.json_response({"error": "body must be JSON"}, status=400)
        toml_text = payload.get("toml") if isinstance(payload, dict) else None
        base_hash = payload.get("base_hash") if isinstance(payload, dict) else None
        if not isinstance(toml_text, str) or not isinstance(base_hash, str):
            return web.json_response({"error": "missing toml/base_hash"}, status=400)
        if len(toml_text.encode()) > MAX_VALIDATE_BODY:
            return web.json_response({"error": "body too large"}, status=413)

        # Conflict check FIRST — never validate/work against a file that moved.
        current = config_hash(config_path)
        if current is not None and base_hash != current:
            return web.json_response(
                {"error": "conflict", "hash": current}, status=409
            )

        # Restore any redacted secret from disk (no-op for secret-free config).
        try:
            disk_text = config_path.read_text(encoding="utf-8")
        except OSError:
            disk_text = ""
        merged = restore_redacted(toml_text, disk_text)
        if REDACTED.strip() in merged:
            return web.json_response(
                {"error": "unresolved redacted value; replace ••• with the real "
                          "value or edit the file directly"},
                status=400,
            )

        result = await validate_config_text(merged)
        if not result.valid:
            return web.json_response(_result_to_json(result), status=422)

        # Backup + atomic write.
        try:
            if config_path.exists():
                shutil.copy2(config_path, config_path.with_suffix(config_path.suffix + ".bak"))
            tmp = config_path.with_name(config_path.name + ".tmp")
            tmp.write_text(merged, encoding="utf-8")
            os.replace(tmp, config_path)
        except OSError as e:
            return web.json_response({"error": f"write failed: {e}"}, status=500)

        return web.json_response(
            {"state": "saved", "hash": config_hash(config_path) or ""}
        )
```
Add imports at the top of `webui/__init__.py`: `import os`, `import shutil`, and `from led_ticker.webui.redact import redact_toml, restore_redacted` (extend the existing redact import), and `from led_ticker.reload import config_hash` (from Task 1). `MAX_VALIDATE_BODY`, `validate_config_text`, `_result_to_json`, `REDACTED` are already imported/defined.

- [ ] **Step 5: Run — passes**

```bash
uv run pytest tests/test_webui/ -k put_config -v
```
Expected: all PUT branch tests PASS. Then full suite + ruff:
```bash
uv run pytest -q 2>&1 | tail -5
uv run --extra dev ruff check src/ tests/ 2>&1 | tail -2
```

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/webui/__init__.py tests/test_webui/
git commit --no-verify -m "feat(webui): PUT /api/config — token-gated validate/conflict/backup/atomic write

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Editor UI — make the config tab editable + Save + feedback

**Files:**
- Modify: `src/led_ticker/webui/static/index.html`

**Interfaces:**
- Consumes: `GET /api/config` (`toml` + `hash`), `POST /api/validate` (existing), `PUT /api/config` (Task 3), `GET /api/status` (`last_reload` with `ok`/`errors`/`restart_required`).

- [ ] **Step 1: Branch check**

```bash
git branch --show-current   # MUST be feat/web-config-editor — if main, STOP
```

- [ ] **Step 2: Make the config tab an editor**

Read the current `#tab-config` section (≈ lines 86–93). Replace the read-only `<pre id="config-toml">` with an editable `<textarea id="config-editor">` (keep the line-gutter pattern used in the validate tab), and add a control row:
```html
  <section id="tab-config" class="tab">
    <div class="card">
      <strong>Live config</strong> <span id="geometry" class="muted"></span>
      <div id="config-editor-wrap" style="display:flex;gap:.5rem;">
        <pre id="config-gutter" class="line-gutter" aria-hidden="true">1</pre>
        <textarea id="config-editor" class="editor-content" spellcheck="false">loading…</textarea>
      </div>
      <div style="display:flex;gap:.5rem;align-items:center;margin-top:.6rem;">
        <button id="config-validate">Validate</button>
        <button id="config-save">Save</button>
        <span id="config-status" class="muted"></span>
      </div>
      <pre id="config-errors" class="muted" style="display:none;"></pre>
    </div>
  </section>
```

- [ ] **Step 3: Wire load / validate / save (vanilla JS, matching the file's existing fetch style)**

Add to the page script. Use the existing token handling (the page already sends the token on its fetches — reuse that helper; if it reads `?token=` from the URL, include it on the PUT too):
```javascript
  let configBaseHash = "";
  async function loadConfigEditor() {
    const r = await apiFetch("/api/config");      // reuse the page's fetch helper
    const j = await r.json();
    document.getElementById("config-editor").value = j.toml || "";
    configBaseHash = j.hash || "";
    if (j.geometry) renderGeometry(j.geometry);   // reuse existing geometry render
    updateGutter();
  }
  document.getElementById("config-validate").onclick = async () => {
    const body = document.getElementById("config-editor").value;
    const r = await apiFetch("/api/validate", {method:"POST", body});
    const j = await r.json();
    showConfigErrors(j);  // reuse the validate tab's error renderer if present
  };
  document.getElementById("config-save").onclick = async () => {
    const toml = document.getElementById("config-editor").value;
    const r = await apiFetch("/api/config", {
      method:"PUT",
      headers:{"Content-Type":"application/json"},
      body: JSON.stringify({toml, base_hash: configBaseHash}),
    });
    const status = document.getElementById("config-status");
    if (r.status === 200) {
      const j = await r.json(); configBaseHash = j.hash || "";
      status.textContent = "saved — applying…";
      setTimeout(pollReloadOutcome, 1500);   // give the loop a cycle
    } else if (r.status === 409) {
      status.textContent = "changed on disk — reload the editor before saving";
    } else if (r.status === 403) {
      status.textContent = "editing disabled (no token configured)";
    } else {
      const j = await r.json().catch(()=>({}));
      status.textContent = "rejected"; showConfigErrors(j);
    }
  };
  async function pollReloadOutcome() {
    const r = await apiFetch("/api/status"); const j = await r.json();
    const lr = j.last_reload || {};
    const status = document.getElementById("config-status");
    if (lr.ok && (lr.restart_required||[]).length === 0) status.textContent = "applied live ✓";
    else if (lr.ok) status.textContent = "saved — restart required for: " + lr.restart_required.join(", ");
    else if ((lr.errors||[]).length) status.textContent = "reload rejected: " + lr.errors.join("; ");
  }
```
Adapt the helper names (`apiFetch`, `renderGeometry`, `showConfigErrors`, `updateGutter`) to whatever the file actually defines — read the existing script first and reuse its real functions; don't invent parallel ones. Call `loadConfigEditor()` where the page currently loads the config tab.

- [ ] **Step 4: Manual smoke + commit**

Build/serve isn't required for a static file, but sanity-check the HTML parses and the JS has no obvious syntax error:
```bash
cd /Users/james/projects/github/jamesawesome/led-ticker
python3 -c "import pathlib,html.parser; html.parser.HTMLParser().feed(pathlib.Path('src/led_ticker/webui/static/index.html').read_text()); print('html parses')"
```
(If the project has a webui static-asset test, run it.) Commit:
```bash
git add src/led_ticker/webui/static/index.html
git commit --no-verify -m "feat(webui): editable config tab — validate, save, applied/restart feedback

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: `:rw` mount + docs + posture update

**Files:**
- Modify: `compose.yaml` (webui service config mount `:ro` → `:rw`)
- Modify: `src/led_ticker/webui/__init__.py` (module docstring — posture change)
- Modify: `docs/site/src/content/docs/concepts/web-status-ui.mdx` (editing section + deploy note)
- Modify: `CLAUDE.md` (webui invariant)

- [ ] **Step 1: Branch check**

```bash
git branch --show-current   # MUST be feat/web-config-editor — if main, STOP
```

- [ ] **Step 2: `compose.yaml` — webui config mount rw**

In `compose.yaml`, the `webui` service's volume `- ./config:/code/config:ro` → `- ./config:/code/config:rw`. Leave the display service `:ro`. Add a comment: `# rw so the web config editor can write config.toml; the display still mounts :ro and hot-reloads the change.`

- [ ] **Step 3: Posture docstring**

Update the `webui/__init__.py` module docstring (top of file) — it currently says the sidecar "never writes status.json and never touches the config file." Change to reflect: it never writes status.json, and it touches `config.toml` only through the **token-gated** `PUT /api/config` editor (validate → conflict-check → backup → atomic write); reads/preview remain unauthenticated-friendly.

- [ ] **Step 4: Docs — editing section + deploy note**

In `docs/site/src/content/docs/concepts/web-status-ui.mdx`, add a "Editing the config" subsection: the editor lives on the Config tab; **a token is required** (`LED_TICKER_WEB_TOKEN`) — without it the editor is read-only; Save validates first (invalid TOML is rejected, nothing written), backs up to `config.toml.bak`, writes atomically, and the running display hot-reloads it; the tab shows "applied live" or "restart required for …". Add a **deploy note**: the webui container must mount the config dir `:rw` and run as a user that can write the host-bind-mounted `config.toml` (compose `user:`/dir perms on the Pi). Matter-of-fact, no release-history framing.

- [ ] **Step 5: CLAUDE.md invariant**

Update the webui line in `CLAUDE.md`: the webui is a sidecar that is read-only EXCEPT the token-gated `PUT /api/config` editor (validate→conflict→backup→atomic write); it writes `config.toml` and nothing else; the display applies the change via hot-reload. Note the `:rw` mount requirement.

- [ ] **Step 6: Lint + commit**

```bash
make docs-lint 2>&1 | tail -3
git add compose.yaml src/led_ticker/webui/__init__.py docs/ CLAUDE.md
git commit --no-verify -m "feat(webui): rw config mount + editor docs + posture update

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: Verify + open PR

- [ ] **Step 1: Full suite + lint + docs-lint**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker
uv run --extra dev ruff check src/ tests/ && uv run pytest -q 2>&1 | tail -5
make docs-lint 2>&1 | tail -3
```
Expected: all green.

- [ ] **Step 2: Push + PR (no merge without consent)**

```bash
git push --no-verify -u origin feat/web-config-editor
gh pr create --repo JamesAwesome/led-ticker --base main --head feat/web-config-editor \
  --title "feat: edit the running config from the web UI (Spec B)" \
  --body "Full-TOML web config editor. PUT /api/config (token-gated): validate → conflict-check (base hash) → restore redacted secrets from disk → backup config.toml.bak → atomic write; the display's hot-reload (PR #250) applies it. GET /api/config returns a version hash. Editor tab: textarea + Validate + Save + applied/restart-required feedback from the status board. webui config mount → :rw; posture updated (read-only EXCEPT the token-gated editor); writes require LED_TICKER_WEB_TOKEN (open = read-only). Builds on Spec A (config is secret-free; redaction kept as a net via restore_redacted). Do NOT merge without consent. Deploy: webui needs :rw + a writable-by-its-UID config dir."
```

- [ ] **Step 3: Confirm CI green** (`gh pr checks <PR#>`).

---

## Self-review

**Spec coverage (Spec B):**
- Save endpoint validate→conflict→backup→atomic, token-required, 422/409/403/413 → Task 3. ✓
- GET returns hash + verbatim(redacted-no-op) text → Task 1. ✓
- Redaction-as-net with save-time placeholder restore → Task 2 + wired in Task 3. ✓
- Editor UI textarea + validate + save + applied/restart feedback → Task 4. ✓
- `:rw` mount + posture docstring + docs + CLAUDE.md → Task 5. ✓
- Deploy note (UID/ownership) → Task 5 Step 4. ✓
- Out of scope (structured editor, editing non-running configs, multi-undo, per-user auth/TLS) → not in any task. ✓

**Placeholder scan:** No TBD/TODO. Task 4's JS names (`apiFetch`/`renderGeometry`/`showConfigErrors`/`updateGutter`) are explicitly "adapt to the file's real helpers — read first"; the behavior (load/validate/save/poll) is concrete. Task 2 Step 3 flags that `_KV` may need a named `value` group and makes the behavioral tests the contract.

**Type/name consistency:** `config_hash(path)->str|None` (Task 1) consumed in Task 3; `restore_redacted(submitted, disk)->str` (Task 2) consumed in Task 3; `PUT /api/config` body `{toml, base_hash}` and responses (200/403/409/413/422/400) are identical across Tasks 3 and 4; `REDACTED`/`MAX_VALIDATE_BODY`/`validate_config_text`/`_result_to_json` are existing symbols, named consistently.

**Pitfalls flagged:** conflict-check BEFORE validate/write (never act on a moved file); atomic write via tmp+os.replace (no partial file for the watcher); `.bak` before overwrite; write-requires-token (403 when open); `_KV` may need a `value` group (don't break `redact_toml`); reuse the page's real JS helpers; broken local hook → `--no-verify`; never main; no merge without consent.
