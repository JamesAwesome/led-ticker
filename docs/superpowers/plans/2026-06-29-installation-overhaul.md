# Installation Overhaul Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make led-ticker dead-simple to set up with **one deploy path** (Docker) — drop systemd, add a no-hardware "try it" mode, a bootstrap with Docker-install help, a clean repo-hygiene convention, and a docs rewrite.

**Architecture:** Five sequential phases, each its own PR: A drop systemd, B `.gitignore`/user-content convention, C slim-headless try-it image + compose profile, D bootstrap + Docker preflight, E docs rewrite. Mostly file/Docker/shell/docs work; lean on clean-clone git-status checks, `make docs-build`/`docs-lint`, repo-wide ref greps, and flagged maintainer deploy-smokes.

**Tech Stack:** Docker + compose v2, Python 3.14, Make, shell, Astro/Starlight docs.

**Spec:** `docs/superpowers/specs/2026-06-29-installation-overhaul-design.md`

## Global Constraints
- **Docker is the single deploy path.** Never lose the **no-hardware run** (the `headless`/`telnet` backends — the try-it depends on it).
- **The slim try-it image must build WITHOUT the rgbmatrix C library** — core's `_compat` stub covers any rgbmatrix reference; `headless` never constructs `RGBMatrix`.
- **Production deploy runtime behavior is UNCHANGED** — this is docs/bootstrap/packaging *around* it. Don't edit the prod `Dockerfile`/render path.
- **Repo hygiene goal:** after `clone → add config.toml + private media (in the documented place)`, `git status` is clean.
- Webui stays rgbmatrix-pure (`tests/test_webui_purity.py`); **PEP 649** (no `from __future__ import annotations`); **DOCS-STYLE.md** for all docs (no release-history framing, no "footgun").
- Commit trailer on every commit:
  ```
  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01P7r9q2YjKvWBsTSfdPotAh
  ```
- Core gates where code changes: `PYTHONPATH=tests/stubs uv run --extra dev pytest`; `uv run --extra dev ruff check src/ tests/` + `ruff format`; `pyright src/`.
- **NON-GOALS:** a prebuilt/published image (future); any engine/render change; the brightness-override seam; changing the deploy's runtime behavior.
- **Each phase is its own PR; pause for merge go-ahead per PR.** Several phases are non-unit-testable — they FLAG a maintainer deploy-smoke, never fake one.

---

## Phase A — Drop systemd, Docker single deploy path

### Task A1: Remove the systemd/bare-metal deploy machinery + handle code refs

**Files:**
- Delete: `deploy/install.sh`, `deploy/led-ticker.service`, `deploy/led-ticker-webui.service` (KEEP `deploy/busy-light-camera-watcher.lua`)
- Modify: any code/Makefile/test refs found below (doc refs deferred to Phase E)

- [ ] **Step 1: enumerate every reference** (record the list in the report):
```bash
grep -rnE "install\.sh|led-ticker\.service|led-ticker-webui\.service|systemctl|/opt/led-ticker|systemd" . \
  | grep -vE "^\./\.git/|docs/superpowers/"
```
Classify each hit: **(a) the deploy files themselves** (being deleted), **(b) code/Makefile/tests** (handle in this task), **(c) docs-site `.mdx` + README + llms.txt** (defer to Phase E — note them).

- [ ] **Step 2: delete the three files.**
```bash
git rm deploy/install.sh deploy/led-ticker.service deploy/led-ticker-webui.service
```

- [ ] **Step 3: handle code/test refs.** For each non-doc hit from Step 1:
  - A **test that exercises install.sh / bare-metal / a systemd assumption** (candidates from the grep: `tests/test_plugin_requirements.py`, `tests/test_build_ref.py`, `tests/test_plugins/test_plugin_cli.py`, `tests/test_webui_app.py`) — READ it; if it asserts on the removed files/paths, update or remove that assertion. If a ref is incidental (e.g. a `/opt`-unrelated match, or a `systemd`-in-a-comment), leave it. Do NOT remove a test wholesale unless it exists solely to test the dropped path.
  - `Makefile`, `src/led_ticker/_build.py`, `src/led_ticker/app/plugin_cmd.py`, `src/led_ticker/webui/static/index.html`, `config/config.example.toml`, `CLAUDE.md`: if the ref names install.sh/the units//opt/led-ticker as a deploy instruction, update to the Docker path or remove; if incidental, leave. (Record each decision in the report.)

- [ ] **Step 4: verify** — `grep -rnE "install\.sh|led-ticker\.service|led-ticker-webui\.service" . | grep -vE "^\./\.git/|docs/"` returns nothing outside docs (docs handled in E). Full suite green: `PYTHONPATH=tests/stubs uv run --extra dev pytest -q`. ruff + pyright clean.

- [ ] **Step 5: commit** (`feat(deploy): drop the systemd/bare-metal path — Docker is the single deploy path`). Open the Phase-A PR; pause for merge.

---

## Phase B — `.gitignore` + user-content convention

### Task B1: Pattern-based ignores + a gitignored `config/local/` for user content

**Files:**
- Modify: `.gitignore`
- Create: `config/local/.gitkeep` (so the dir + the convention are discoverable) — OR document the dir without committing it (decide in Step 3)
- Test: `tests/test_gitignore_user_content.py`

**Convention (decided — do NOT churn the committed fixtures):** the ~27 committed non-example `config/*.toml` are dev/test/demo fixtures (referenced by Makefile render targets + tests) and `config/assets/*` holds committed CC0 samples — **all stay tracked, untouched.** User content gets a clean home: the running config is `config/config.toml` (already ignored); the operator's per-sign configs + private media live under a **gitignored `config/local/`** (referenced from their config by relative path, e.g. `config/local/my.gif`; the whole `config/` dir is already mounted into the container, so paths resolve). Remove the hardcoded per-sign lines.

- [ ] **Step 1: write the failing test** (`tests/test_gitignore_user_content.py`):
```python
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _ignored(relpath: str) -> bool:
    # git check-ignore exits 0 if the path IS ignored.
    return subprocess.run(
        ["git", "check-ignore", "-q", relpath], cwd=REPO
    ).returncode == 0


def test_user_content_locations_are_gitignored():
    # The operator's running config + private content must never show as untracked.
    assert _ignored("config/config.toml")
    assert _ignored("config/requirements-plugins.txt")
    assert _ignored("config/local/my-sign.toml")
    assert _ignored("config/local/media/logo.gif")


def test_committed_samples_are_not_ignored():
    # Tracked fixtures + examples must stay visible to git.
    assert not _ignored("config/config.example.toml")
    assert not _ignored("config/config.baseball.toml")
    assert not _ignored("config/assets/phoenix.png")
```

- [ ] **Step 2: run, expect fail** — `PYTHONPATH=tests/stubs uv run --extra dev pytest tests/test_gitignore_user_content.py -q` (the `config/local/...` assertions fail — not ignored yet).

- [ ] **Step 3: implement the `.gitignore` change.** In `.gitignore`, replace the per-host block (currently lines ~146–152: `config/config.toml`, `config/config.*.production.toml`, `config/config.pool_bigsign.toml`, `config/requirements-plugins.txt`, `config/fonts/`) with:
```gitignore
# --- Operator (per-host) content — never committed ---
# Your running config (copy from a config/*.example.toml to start):
config/config.toml
# Installed plugins manifest + user fonts (per-host):
config/requirements-plugins.txt
config/fonts/
# Your private configs + media live here (mounted into the container via ./config):
config/local/
```
Remove the hardcoded `config/config.*.production.toml` + `config/config.pool_bigsign.toml` lines (the operator moves those to `config/local/`). Add a committed `config/local/.gitkeep` so the convention is self-documenting; ensure `config/local/` ignores everything EXCEPT `.gitkeep`:
```gitignore
config/local/
!config/local/.gitkeep
```
Create `config/local/.gitkeep` with a one-line comment: `# Operator-private configs + media (gitignored). Reference from your config.toml by relative path.`

- [ ] **Step 4: run, expect pass.** Confirm a clean tree: `git status --porcelain` is empty after creating `config/local/foo.toml` + `config/local/media/x.gif` (then delete them). Full suite green.

- [ ] **Step 5: commit** (`feat(repo): gitignore config/local for operator content; drop hardcoded per-sign ignores`). Open the Phase-B PR; pause for merge.

---

## Phase C — Laptop try-it (slim headless image)

### Task C1: Slim headless `Dockerfile.try` + try-it sample config

**Files:**
- Create: `Dockerfile.try` (repo root), `config/config.try.example.toml`

**Reference:** the telnet plugin's `plugins/telnet/Dockerfile.smoke` (in the led-ticker-plugins repo) is the pattern — core needs its own. The try-it runs core's `headless` backend + the webui; the user opens the webui **preview** in a browser (no hardware, no telnet client).

- [ ] **Step 1: create `Dockerfile.try`:**
```dockerfile
# Slim, no-hardware "try it" image: the full engine + webui, headless backend,
# NO rgbmatrix compile (core's _compat stub covers any rgbmatrix reference; the
# headless backend never constructs RGBMatrix). Open the webui preview to watch.
FROM python:3.14-bookworm
WORKDIR /code
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .
COPY config/config.try.example.toml /code/config/config.toml
ENV PYTHONUNBUFFERED=1
EXPOSE 8080
# Run the engine (headless) in the background + the webui in the foreground so a
# single container serves the preview. (compose runs two services — see C2 —
# this CMD is the fallback for a bare `docker run`.)
CMD ["led-ticker", "--config", "/code/config/config.toml"]
```
(If `pip install .` of core pulls rgbmatrix, it must NOT — confirm rgbmatrix is not a runtime pip dependency of `led-ticker-core` before relying on this; it's built separately in the prod `Dockerfile`. If a dep does pull it, STOP and report.)

- [ ] **Step 2: create `config/config.try.example.toml`** — `[display] backend = "headless"`, a small smallsign-ish geometry (`rows=16, cols=32, chain_length=5, default_scale=1`), `[web]` enabled (so the preview serves), and lively content (adapt the telnet smoke config: a bordered, rainbow `message` + a dissolve/wipe between two sections). Header comment: "Try-it config — headless, no hardware; open the webui preview."

- [ ] **Step 3: verify (buildable assertion)** — `docker build -f Dockerfile.try -t led-ticker-try .` succeeds and does NOT compile rgbmatrix (grep the build log for the absence of a C compile / rpi-rgb-led-matrix clone). Record the result.

- [ ] **Step 4: commit** (`feat(try): slim headless Dockerfile.try + try-it sample config`).

### Task C2: compose `try` profile + `make try`

**Files:**
- Modify: `compose.yaml` (add a `try` service under a `try` profile), `Makefile` (add a `try` target)

- [ ] **Step 1:** add to `compose.yaml` a `try` service under `profiles: ["try"]`: builds `Dockerfile.try`, runs the engine headless + the webui (either two services `try` + `try-webui` both on the `try` profile sharing the image, mirroring the deploy/webui split, OR one service that runs both — pick the split for parity), publishes the webui port, mounts `./config`. No `privileged`/`network_mode: host` needed for headless (use a published port).
- [ ] **Step 2:** add a `Makefile` `try` target:
```make
try:  ## Try led-ticker with NO hardware: headless engine + webui preview at http://localhost:8080
	docker compose --profile try up --build
	@echo "open http://localhost:8080 and click the live preview"
```
- [ ] **Step 3: MAINTAINER SMOKE (flag, do not fake):** `make try` → open `http://localhost:8080` → the preview shows the animated sign; no hardware. Document the steps in the PR.
- [ ] **Step 4: commit** (`feat(try): compose try profile + make try`). Open the Phase-C PR; pause for merge.

---

## Phase D — Pi-deploy bootstrap + Docker-install preflight

### Task D1: `scripts/setup.sh` (Docker preflight + config/.env bootstrap) + `make setup`

**Files:**
- Create: `scripts/setup.sh`
- Modify: `Makefile` (add `setup`)
- Test: `tests/test_setup_preflight.py` (test the preflight logic if extracted to a testable form)

- [ ] **Step 1:** write `scripts/setup.sh` (POSIX sh): 
  - **Docker preflight:** if `docker` is missing OR `docker compose version` fails → print the OFFICIAL install guidance and exit non-zero:
    - Linux/Pi: `curl -fsSL https://get.docker.com | sh` (the official convenience script) + add user to the `docker` group.
    - macOS/Windows: install Docker Desktop (https://docs.docker.com/get-docker/).
    - Note `docker compose` v2 ships with modern Docker; old standalone `docker-compose` is not required.
  - **Config bootstrap:** if `config/config.toml` absent → `cp config/config.example.toml config/config.toml` (and echo which example was used + how to switch to bigsign). If `.env` absent → `cp .env.example .env`.
  - **Bring up:** accept an arg `try` | `deploy` (default `deploy`): `try` → `docker compose --profile try up --build`; `deploy` → `docker compose up -d --build` (+ `COMPOSE_PROFILES=webui` note). Echo the next step (open the preview / `docker compose logs`).
- [ ] **Step 2:** add `Makefile` `setup` target: `setup:  ## One-command setup: check Docker, seed config/.env, bring up. Usage: make setup [MODE=try|deploy]` → `bash scripts/setup.sh $(MODE)`.
- [ ] **Step 3 (TDD the testable core):** if the preflight/version-compare logic is non-trivial, extract it to a tiny testable unit (a shell function tested via `bats`-style, OR a small `scripts/_preflight.py` with a pytest). Minimum: a test asserting the script prints the official Docker URL when `docker` is absent (run `scripts/setup.sh` with a stubbed PATH lacking docker; assert the get.docker.com URL is in stdout + non-zero exit). Keep it simple; if a clean test isn't feasible, document the preflight as a maintainer smoke instead.
- [ ] **Step 4: MAINTAINER SMOKE (flag, do not fake):** fresh clone → `make setup MODE=try` → running + preview; and on a box without Docker → the official link prints.
- [ ] **Step 5: commit** (`feat(setup): make setup + scripts/setup.sh — Docker preflight + config bootstrap`). Open the Phase-D PR; pause for merge.

---

## Phase E — Docs rewrite

### Task E1: Rewrite the install/deploy docs for the single Docker path + the two quickstarts

**Files:**
- Modify: `docs/site/src/content/docs/getting-started.mdx`, `docs/site/src/content/docs/hardware/building-your-own.mdx`, `docs/site/src/content/docs/tutorial/01-setup.mdx`
- Sweep: `README.md`, `docs/site/.../*.mdx` (the Phase-A Step-1 doc list), `llms.txt` (regenerated via `make docs-check-llms`)

- [ ] **Step 1:** rewrite the three primary pages to:
  - **Step 0 — Install Docker** (official source: `get.docker.com` for Linux/Pi, Docker Desktop for Mac/Windows; `docker compose` v2 ships with it).
  - **Quickstart A — Try it on your computer (no hardware):** `make try` (or `docker compose --profile try up`) → open `http://localhost:8080` → the preview. 
  - **Quickstart B — Deploy to your Pi:** `make setup` (or `docker compose up -d --build`), copy a `config.*.example.toml` → `config/config.toml`, edit `.env`, the webui profile.
  - **Repo-hygiene note:** your config = `config/config.toml`; private media → `config/local/` (gitignored).
  - **Remove ALL systemd/bare-metal sections** (the "Run via systemd" + `install.sh` + bare-metal-pip sections in building-your-own.mdx).
- [ ] **Step 2:** sweep `README.md` + every doc page from the Phase-A grep that mentioned systemd/install.sh//opt/led-ticker; update or remove. 
- [ ] **Step 3: verify** — `make docs-build` + `make docs-lint` + `make docs-check-llms` clean; and `grep -rnE "systemctl|install\.sh|/opt/led-ticker|led-ticker\.service" docs/ README.md` returns nothing (a stray-ref tripwire).
- [ ] **Step 4: commit** (`docs: rewrite install/deploy for the single Docker path + the two quickstarts`). Open the Phase-E PR; pause for merge.

---

## Self-Review

**Spec coverage:** drop systemd → A1; .gitignore/user-content convention → B1; slim try-it image + try config → C1; compose try profile + make try → C2; bootstrap + Docker preflight → D1; docs rewrite + sweep → E1. ✅ (The spec's "audit committed configs" resolved to: keep fixtures tracked, add `config/local/` — no rename/move churn.)

**Placeholder scan:** testable bits carry real code (the gitignore `git check-ignore` test, the Dockerfile.try, the .gitignore block, the Makefile targets); the file-removal/docs/shell tasks give exact files + verification greps + flagged maintainer smokes. The one conditional ("if pip install pulls rgbmatrix, STOP") is a real guard, not a TODO.

**Type/name consistency:** `Dockerfile.try` + `config/config.try.example.toml` + the `try` compose profile + `make try` are named consistently across C1/C2/D1/E1; `config/local/` is the single user-content dir across B1/D1/E1; the webui port `8080` is consistent (matches compose's webui default).

**Notes for the executor:** (1) Phases are sequential PRs — A (removal) and B (.gitignore) should land before E (docs) so the docs describe the final state. (2) The rgbmatrix-not-a-pip-dep assumption (C1) is load-bearing for the slim image — verify it first. (3) The try-it + deploy + bootstrap + Docker-preflight are **maintainer deploy-smokes** — flag, don't fake. (4) Keep the production `Dockerfile` + render path untouched.
