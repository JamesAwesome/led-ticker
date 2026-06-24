# Webui Build Stamp Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make "what commit is actually deployed" visible at a glance — bake a `branch@shortsha` build ref into the image, surface it in `status.json`, and show it in the webui header with a drift warning when the display and webui containers differ.

**Architecture:** A build ARG → ENV captured at image build (`LED_TICKER_BUILD_REF`), read through one helper `led_ticker._build.build_ref()`. The display writes it into `status.json` (schema 7→8); the webui adds its own ref to the served status payload and the header renders both, flagging drift.

**Tech Stack:** Python/attrs/pytest, aiohttp (webui), Docker, Make, vanilla JS (webui frontend).

## Global Constraints

- All work in the engine repo: `src/led_ticker/`, `tests/`, `Dockerfile`, `Makefile`, `compose.yaml`, docs. Tests: `PYTHONPATH=tests/stubs uv run pytest …`; lint: `uv run --extra dev ruff check src/ tests/`.
- The env var is `LED_TICKER_BUILD_REF`; the default when unset is the literal string `unknown`. Both the display and the webui read it ONLY through `led_ticker._build.build_ref()`.
- Stamp content is `branch@shortsha` plus `+dirty` when built from uncommitted changes; computed by the build path, not at runtime (the container has no git; `.git` is excluded from the build context).
- `status.json` schema bump is mandatory when its top-level key set changes: bump `SCHEMA_VERSION` AND update `EXPECTED_TOP_LEVEL_KEYS` in `tests/test_status_board.py`.
- `unknown` is an acceptable value (means "not built via the stamped path") — never make it an error.
- No hardware; the webui already degrades gracefully on `schema_mismatch` (don't change that).

---

### Task 1: `build_ref()` helper

**Files:**
- Create: `src/led_ticker/_build.py`
- Test: `tests/test_build_ref.py`

**Interfaces:**
- Produces: `led_ticker._build.build_ref() -> str` (env `LED_TICKER_BUILD_REF`, default `"unknown"`). Consumed by Tasks 2 and 4.

- [ ] **Step 1: Write the failing test**

Create `tests/test_build_ref.py`:
```python
from led_ticker._build import build_ref


def test_build_ref_reads_env(monkeypatch):
    monkeypatch.setenv("LED_TICKER_BUILD_REF", "feat/x@abc1234")
    assert build_ref() == "feat/x@abc1234"


def test_build_ref_defaults_unknown(monkeypatch):
    monkeypatch.delenv("LED_TICKER_BUILD_REF", raising=False)
    assert build_ref() == "unknown"
```

- [ ] **Step 2: Run it — expect FAIL**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_build_ref.py -q`
Expected: FAIL (`ModuleNotFoundError: led_ticker._build`).

- [ ] **Step 3: Implement**

Create `src/led_ticker/_build.py`:
```python
"""Build identity baked into the image at build time.

The Dockerfile sets `ENV LED_TICKER_BUILD_REF` from the `BUILD_REF` build arg
(see `make build-docker` / `compose.yaml`). The container has no git at runtime,
so this is the only source of "what commit is deployed". Default `"unknown"`
means the image was not built via a stamping build path.
"""

import os


def build_ref() -> str:
    return os.environ.get("LED_TICKER_BUILD_REF", "unknown")
```

- [ ] **Step 4: Run it — expect PASS**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_build_ref.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker
git add src/led_ticker/_build.py tests/test_build_ref.py
git commit --no-verify -m "feat: build_ref() — read LED_TICKER_BUILD_REF (default unknown)"
```

---

### Task 2: Display writes `build` into status.json (schema 7→8)

**Files:**
- Modify: `src/led_ticker/status_board.py` (`SCHEMA_VERSION`, `snapshot()`)
- Modify: `tests/test_status_board.py` (`EXPECTED_TOP_LEVEL_KEYS`, the `== 7` assertion, add a build test)

**Interfaces:**
- Consumes: `build_ref()` (Task 1).
- Produces: `status.json` carries top-level `"build"`; `SCHEMA_VERSION == 8`.

- [ ] **Step 1: Update the tripwire + add a build test (failing)**

In `tests/test_status_board.py`: add `"build",` to the `EXPECTED_TOP_LEVEL_KEYS` set, change the assertion `SCHEMA_VERSION == 7` to `== 8`, and append:
```python
def test_snapshot_carries_build_ref(tmp_path, monkeypatch):
    monkeypatch.setenv("LED_TICKER_BUILD_REF", "feat/x@abc1234")
    snap = _board(tmp_path).snapshot()
    assert snap["build"] == "feat/x@abc1234"
```

- [ ] **Step 2: Run it — expect FAIL**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_status_board.py -q`
Expected: FAIL — `test_schema_tripwire` (snapshot lacks `build`, version is 7) and `test_snapshot_carries_build_ref` (no `build` key).

- [ ] **Step 3: Implement**

In `src/led_ticker/status_board.py`:
1. Add the import near the top: `from led_ticker._build import build_ref`.
2. Bump the version: change `SCHEMA_VERSION = 7` to `SCHEMA_VERSION = 8`.
3. In `snapshot()`, add the field right after the `"schema": SCHEMA_VERSION,` line:
```python
            "build": build_ref(),
```

- [ ] **Step 4: Run it — expect PASS**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_status_board.py -q`
Expected: PASS (tripwire + build test green).

- [ ] **Step 5: Commit**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker
git add src/led_ticker/status_board.py tests/test_status_board.py
git commit --no-verify -m "feat: status.json carries build ref (schema 7->8)"
```

---

### Task 3: Capture the build ref at image-build time + `make rebuild`

**Files:**
- Modify: `Dockerfile` (final stage — `ARG`/`ENV` at the end)
- Modify: `Makefile` (`BUILD_REF` var, `build-docker`, new `rebuild`)
- Modify: `compose.yaml` (build args on both services)
- Test: `tests/test_build_stamp_plumbing.py`

**Interfaces:**
- Produces: an image with `ENV LED_TICKER_BUILD_REF` set from the `BUILD_REF` build arg.

- [ ] **Step 1: Write the plumbing tripwire (failing)**

Create `tests/test_build_stamp_plumbing.py`:
```python
"""The build paths stamp LED_TICKER_BUILD_REF into the image. Without this the
deployed commit is invisible (the motivating bug)."""

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_dockerfile_bakes_build_ref():
    df = (REPO / "Dockerfile").read_text()
    assert "ARG BUILD_REF" in df
    assert "ENV LED_TICKER_BUILD_REF=$BUILD_REF" in df


def test_makefile_passes_build_arg():
    mk = (REPO / "Makefile").read_text()
    assert "--build-arg BUILD_REF" in mk


def test_compose_forwards_build_ref():
    cf = (REPO / "compose.yaml").read_text()
    assert "BUILD_REF: ${BUILD_REF:-unknown}" in cf
```

- [ ] **Step 2: Run it — expect FAIL**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_build_stamp_plumbing.py -q`
Expected: FAIL (none of the plumbing exists yet).

- [ ] **Step 3: Dockerfile — bake the ARG/ENV at the end**

In `Dockerfile`, after the final `RUN pip install --no-deps .` line (the last line of the final stage), append:
```dockerfile

# Build stamp — set by `make build-docker` / `make rebuild` / compose build args.
# Placed last so changing it invalidates only this tiny layer, not the pip install.
ARG BUILD_REF=unknown
ENV LED_TICKER_BUILD_REF=$BUILD_REF
```

- [ ] **Step 4: Makefile — compute + pass the ref, add `rebuild`**

In `Makefile`: add `rebuild` to the `.PHONY` line. Above the `build-docker:` target, add the var, and update the targets:
```makefile
# branch@shortsha(+dirty) — baked into the image as LED_TICKER_BUILD_REF.
BUILD_REF ?= $(shell git rev-parse --abbrev-ref HEAD 2>/dev/null)@$(shell git rev-parse --short HEAD 2>/dev/null)$(shell git diff --quiet 2>/dev/null || echo +dirty)

build-docker:  ## Build the production Docker image (Pi 4 + Pi 5)
	docker build -t led-ticker --build-arg BUILD_REF="$(BUILD_REF)" .

rebuild:  ## Stamped rebuild + recreate ALL services incl. the webui sidecar
	BUILD_REF="$(BUILD_REF)" COMPOSE_PROFILES=webui docker compose up -d --build --force-recreate
```
(Replace the existing two-line `build-docker` target with the version above.)

- [ ] **Step 5: compose.yaml — forward the build arg on both services**

In `compose.yaml`, change the `led-ticker` service's `build: .` to:
```yaml
    build:
      context: .
      args:
        BUILD_REF: ${BUILD_REF:-unknown}
```
Make the identical change to the `webui` service's `build: .`.

- [ ] **Step 6: Run the tripwire + lint — expect PASS**

Run:
```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_build_stamp_plumbing.py -q
python3 -c "import yaml; yaml.safe_load(open('compose.yaml')); print('compose yaml ok')"
```
Expected: 3 passed; `compose yaml ok` (valid YAML after the edit). (If pyyaml isn't importable in plain python3, run it via `uv run python -c …`.)

- [ ] **Step 7: Commit**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker
git add Dockerfile Makefile compose.yaml tests/test_build_stamp_plumbing.py
git commit --no-verify -m "feat: stamp LED_TICKER_BUILD_REF at image build + make rebuild"
```

---

### Task 4: Webui serves `webui_build` + header stamp with drift check

**Files:**
- Modify: `src/led_ticker/webui/__init__.py` (`status_handler` — add `webui_build`)
- Modify: `src/led_ticker/webui/static/index.html` (header `#build-stamp` + `renderBuildStamp`)
- Test: `tests/test_webui_app.py`

**Interfaces:**
- Consumes: `build_ref()` (Task 1); the display's `body.status.build` (Task 2).
- Produces: `/api/status` payload includes `webui_build`; the header shows the stamp + drift `⚠`.

- [ ] **Step 1: Write the failing tests (content-presence, mirrors existing webui tests)**

Append to `tests/test_webui_app.py`:
```python
def test_status_handler_adds_webui_build():
    from pathlib import Path

    import led_ticker.webui as webui_pkg

    src = (Path(webui_pkg.__file__).parent / "__init__.py").read_text()
    # The served status payload is augmented with the webui's own build ref.
    assert 'payload["webui_build"] = build_ref()' in src
    assert "from led_ticker._build import build_ref" in src


def test_header_renders_build_stamp_with_drift():
    from pathlib import Path

    import led_ticker.webui as webui_pkg

    html = (Path(webui_pkg.__file__).parent / "static" / "index.html").read_text()
    assert 'id="build-stamp"' in html          # the header element
    assert "renderBuildStamp" in html          # the render fn
    assert "webui_build" in html               # reads the webui ref for drift
    assert "⚠" in html                     # the drift warning glyph
```

- [ ] **Step 2: Run them — expect FAIL**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_webui_app.py::test_status_handler_adds_webui_build tests/test_webui_app.py::test_header_renders_build_stamp_with_drift -q`
Expected: FAIL (none present yet).

- [ ] **Step 3: Webui handler — add `webui_build`**

In `src/led_ticker/webui/__init__.py`: add the import near the other `from led_ticker...` imports:
```python
from led_ticker._build import build_ref
```
In `status_handler` (currently `payload = _read_status(status_path)` then `return web.json_response(payload)`), insert between them:
```python
        payload["webui_build"] = build_ref()
```

- [ ] **Step 4: Header HTML — add the stamp element**

In `src/led_ticker/webui/static/index.html`, the header has `<span id="live" class="missing">connecting…</span>`. Add immediately after it:
```html
  <span id="build-stamp" class="muted" style="font-family:ui-monospace,monospace;font-size:.72rem;margin-left:.6rem;"></span>
```

- [ ] **Step 5: Frontend — render the stamp + drift**

In `index.html`, find the status-poll handler where `const body = await r.json();` is followed by `if (typeof body.allow_restart === "boolean") …`. Immediately after the `const body = await r.json();` line, add a call:
```js
    renderBuildStamp(body);
```
Then add the function itself near the other top-level helper functions (e.g. just above the poll handler / `async function poll`):
```js
function renderBuildStamp(body) {
  const el = $("build-stamp");
  if (!el) return;
  const disp = body.status && body.status.build;   // what's rendering the sign
  const web = body.webui_build;                     // this webui container's build
  if (!disp && !web) { el.textContent = ""; return; }
  if (disp) {
    el.textContent = "build " + disp;
    if (web && web !== disp) el.textContent += "  ⚠ webui " + web;
  } else {
    el.textContent = "webui " + web;                // display build unknown (old schema / no status)
  }
}
```

- [ ] **Step 6: Run tests + build + lint — expect PASS**

Run:
```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_webui_app.py -q
uv run --extra dev ruff check src/led_ticker/webui/__init__.py
```
Expected: webui suite passes; ruff clean. (The webui's Python imports `build_ref` at module load — confirm no import error: `PYTHONPATH=tests/stubs uv run python -c "import led_ticker.webui"`.)

- [ ] **Step 7: Commit**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker
git add src/led_ticker/webui/__init__.py src/led_ticker/webui/static/index.html tests/test_webui_app.py
git commit --no-verify -m "feat(webui): build stamp in the header with display/webui drift check"
```

---

### Task 5: Deploy docs — stamping + the profile gotcha

**Files:**
- Modify: `README.md` (the "Web UI (optional)" section)
- Modify: `docs/site/src/content/docs/concepts/web-status-ui.mdx` (a short "Which build is deployed?" note)

**Interfaces:** consumes the header stamp (Task 4) + `make rebuild` (Task 3).

- [ ] **Step 1: README — add the stamp + rebuild note**

In `README.md`, in the `### Web UI (optional)` section, after the existing sentence, add:
```markdown

The header shows the deployed build (`build <branch>@<sha>`). Rebuild the sign so the display **and** the webui sidecar both land on the new code with `make rebuild` (a stamped `docker compose up -d --build --force-recreate` with the `webui` profile) — a bare `docker compose up -d --build` rebuilds the image but leaves the profile-gated webui container on the old one.
```

- [ ] **Step 2: web-status-ui docs — a short note**

In `docs/site/src/content/docs/concepts/web-status-ui.mdx`, add a short subsection (DOCS-STYLE voice — no padded opener, no banned words) explaining: the header shows `build <branch>@<sha>` baked at image build; `unknown` means the image wasn't built via `make build-docker` / `make rebuild`; a `⚠ webui …` means the webui container is on a different build than the display (rerun `make rebuild`). Read the page's existing heading style first and match it.

- [ ] **Step 3: Build + lint the docs**

Run:
```bash
cd /Users/james/projects/github/jamesawesome/led-ticker
make docs-build && make docs-lint
```
Expected: `[build] Complete!`, lint clean.

- [ ] **Step 4: Commit**

```bash
git add README.md docs/site/src/content/docs/concepts/web-status-ui.mdx
git commit --no-verify -m "docs: how to read the build stamp + make rebuild (profile gotcha)"
```

---

## Final verification (before the PR)

- [ ] **Whole suite + lint:**
```bash
cd /Users/james/projects/github/jamesawesome/led-ticker
PYTHONPATH=tests/stubs uv run pytest tests/test_build_ref.py tests/test_status_board.py tests/test_build_stamp_plumbing.py tests/test_webui_app.py -q
uv run --extra dev ruff check src/ tests/
make docs-build && make docs-lint
```
Expected: all green.

- [ ] **Sanity-check the end-to-end value (no Docker needed):**
```bash
LED_TICKER_BUILD_REF="feat/demo@abc1234" PYTHONPATH=tests/stubs uv run python -c "
from led_ticker.status_board import StatusBoard, SCHEMA_VERSION
import tempfile, pathlib
b = StatusBoard(path=pathlib.Path(tempfile.mkdtemp())/'s.json')
s = b.snapshot()
print('schema:', s['schema'], '(expect 8)'); print('build:', s['build'], \"(expect feat/demo@abc1234)\")
"
```
Expected: `schema: 8`, `build: feat/demo@abc1234`.

- [ ] **Open the PR** (branch `feat/webui-build-stamp`; do NOT merge without explicit user go-ahead). Summarize the five pieces and note the `make rebuild` ergonomic that fixes both stamping and the profile gotcha.

## Self-Review notes (spec coverage)

- Spec A (capture: ARG/ENV, `_build.py`, make, compose) → Tasks 1 + 3.
- Spec B (status `build` field, schema 7→8 + tripwire) → Task 2.
- Spec C (webui serves `webui_build`, header stamp, drift check, degraded cases) → Task 4 (the `renderBuildStamp` branches cover display-only, drift, and webui-only/unknown).
- Spec D (deploy docs incl. the `COMPOSE_PROFILES=webui` gotcha) → Task 5 (+ `make rebuild` from Task 3 bakes the fix into a command).
- Spec testing (schema tripwire, `_build`, status content, webui augmentation, header render, build-path plumbing) → Tasks 1-4 each carry their tests; Final verification runs them together.
- Spec non-goals (panel display, `/version` API, package-version embedding, `unknown` acceptable) → respected by omission; `unknown` handled, never errored.
