# Coherent, profile-agnostic docker-lifecycle Make targets — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename the misleading docker-lifecycle Make targets and add the missing ones so every name matches its function, with no target forcing a compose profile, plus a uv preflight on `make dev`.

**Architecture:** Hard-rename `build-docker`→`build` and `rebuild`→`update`; add thin `docker compose` wrappers `up`/`down`/`restart`/`logs` that inherit `COMPOSE_PROFILES` from the environment; add a uv check to `make dev`; sweep all docs/scripts/Dockerfile references; lock it with a text-scan tripwire. No back-compat aliases.

**Tech Stack:** GNU Make, Docker Compose, POSIX sh, pytest (text-scan tripwire), Astro/Markdown docs.

## Global Constraints

- **No target hardcodes `COMPOSE_PROFILES`** — lifecycle verbs inherit it from the environment / `.env`. (Tripwired.)
- **Hard rename, no aliases:** `build-docker`→`build`, `rebuild`→`update`. The old names must not survive as targets or in any shipped doc/script command.
- **`update`** is today's `rebuild` recipe minus `COMPOSE_PROFILES=webui`. **`build`** is today's `build-docker` recipe unchanged but for the name.
- **`make dev`** must fail with install guidance when `uv` is absent.
- Makefile recipes use **TAB** indentation (spaces → "missing separator").
- CI is not involved (no workflow calls these targets). Run `uv run --extra dev ruff check` before pushing Python; run `make dev` once in the worktree before tests.
- Repo workflow: branch `refactor/make-lifecycle-targets` (worktree `../led-ticker-make-targets`); never commit to `main`.

---

## Prerequisite (once)

- [ ] **Set up the worktree venv**

Run: `cd /Users/james/projects/github/jamesawesome/led-ticker-make-targets && make dev`
Expected: `uv sync` + hooks install succeed.

- [ ] **Confirm branch**

Run: `git branch --show-current`
Expected: `refactor/make-lifecycle-targets`.

---

### Task 1: Makefile — rename, new verbs, dev uv guard, help text + tripwire

**Files:**
- Modify: `Makefile` (`.PHONY`; `dev`; panel-test-docker + panel-map comments; `build-docker`→`build`; `rebuild`→`update`; add `up`/`down`/`restart`/`logs`; `clean` help)
- Test: `tests/test_make_targets.py` (new)

**Interfaces:**
- Produces: make targets `build`, `up`, `update`, `restart`, `down`, `logs` (plus kept `setup`/`try`/`try-down`/`clean`). Consumed by Tasks 2-4 (docs/scripts reference these names).

- [ ] **Step 1: Write the failing tripwire (Makefile-scoped assertions)**

Create `tests/test_make_targets.py`:

```python
"""Tripwire for the docker-lifecycle make targets (2026-06-30 rename).

Locks: build-docker->build, rebuild->update, new up/down/restart/logs, the
profile-agnostic invariant (no recipe hardcodes COMPOSE_PROFILES), and the
`make dev` uv preflight. A cross-file "no retired names in shipped docs"
assertion is added in the docs-sweep task.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MAKEFILE = (REPO_ROOT / "Makefile").read_text()

LIFECYCLE_TARGETS = [
    "setup", "build", "up", "update", "restart", "down", "logs",
    "try", "try-down", "clean",
]
RETIRED_TARGETS = ["build-docker", "rebuild"]
NEW_PHONY = ["build", "up", "update", "restart", "down", "logs"]


def _target_defined(name):
    return re.search(rf"(?m)^{re.escape(name)}:", MAKEFILE) is not None


def test_lifecycle_targets_defined():
    missing = [t for t in LIFECYCLE_TARGETS if not _target_defined(t)]
    assert not missing, f"missing make targets: {missing}"


def test_retired_targets_gone():
    present = [t for t in RETIRED_TARGETS if _target_defined(t)]
    assert not present, f"retired make targets still defined: {present}"


def test_phony_updated():
    phony = next(ln for ln in MAKEFILE.splitlines() if ln.startswith(".PHONY:"))
    for t in NEW_PHONY:
        assert re.search(rf"(?<![\w-]){re.escape(t)}(?![\w-])", phony), f"{t} not in .PHONY"
    for t in RETIRED_TARGETS:
        assert not re.search(rf"(?<![\w-]){re.escape(t)}(?![\w-])", phony), f"{t} still in .PHONY"


def test_no_recipe_hardcodes_compose_profiles():
    # Only recipe lines (tab-indented) matter; help text/comments may mention it.
    offenders = [ln for ln in MAKEFILE.splitlines()
                 if ln.startswith("\t") and "COMPOSE_PROFILES=" in ln]
    assert not offenders, f"recipe hardcodes COMPOSE_PROFILES: {offenders}"


def test_dev_preflights_uv():
    m = re.search(r"(?ms)^dev:.*?(?=^\S)", MAKEFILE)
    assert m, "dev target not found"
    assert "command -v uv" in m.group(0), "make dev must preflight uv"
```

- [ ] **Step 2: Run it — expect failures**

Run: `uv run pytest tests/test_make_targets.py -v`
Expected: FAIL — `build`/`up`/`update`/`restart`/`down`/`logs` not defined, `build-docker`/`rebuild` still defined, `dev` has no uv check.

- [ ] **Step 3: Update `.PHONY`**

In `Makefile` line 1, replace the token sequence `clean build-docker rebuild try try-down setup` with `clean build up update restart down logs try try-down setup`. (Only that span changes; leave the rest of the `.PHONY` list intact.)

- [ ] **Step 4: Add the uv preflight to `dev`**

Replace the `dev` target:

```make
dev:  ## Install package with dev dependencies and pre-commit hooks
	uv sync --extra dev
	uv run pre-commit install
	uv run pre-commit install --hook-type pre-push
```

with:

```make
dev:  ## Install package with dev dependencies and pre-commit hooks
	@command -v uv >/dev/null 2>&1 || { \
	  echo "uv is required for development but was not found."; \
	  echo "Install it:  curl -LsSf https://astral.sh/uv/install.sh | sh"; \
	  echo "(or 'brew install uv' — see https://docs.astral.sh/uv/getting-started/installation/)"; \
	  exit 1; }
	uv sync --extra dev
	uv run pre-commit install
	uv run pre-commit install --hook-type pre-push
```

- [ ] **Step 5: Rename `build-docker` → `build`**

Replace:

```make
build-docker:  ## Build the production image only (no start; used by the *-docker diagnostics)
	@VER="$$(sh scripts/compute-version.sh)" || exit 1; \
	docker build -t led-ticker \
	  --build-arg BUILD_REF="$(BUILD_REF)" \
	  --build-arg SETUPTOOLS_SCM_PRETEND_VERSION="$$VER" .
```

with:

```make
build:  ## Build the production image only (no start; prerequisite for the *-docker diagnostics)
	@VER="$$(sh scripts/compute-version.sh)" || exit 1; \
	docker build -t led-ticker \
	  --build-arg BUILD_REF="$(BUILD_REF)" \
	  --build-arg SETUPTOOLS_SCM_PRETEND_VERSION="$$VER" .
```

- [ ] **Step 6: Rename `rebuild` → `update` (drop the forced profile) and add `up`/`restart`/`down`/`logs`**

Replace:

```make
rebuild:  ## Update a running deploy after 'git pull' — rebuild + recreate all services (incl. webui)
	@git fetch --tags --quiet 2>/dev/null || true; \
	VER="$$(sh scripts/compute-version.sh)" || exit 1; \
	BUILD_REF="$(BUILD_REF)" SETUPTOOLS_SCM_PRETEND_VERSION="$$VER" COMPOSE_PROFILES=webui docker compose up -d --build --force-recreate
```

with:

```make
up:  ## Start the sign without rebuilding (set COMPOSE_PROFILES=webui in .env to include the web UI)
	docker compose up -d

update:  ## Update a running deploy after 'git pull': rebuild the image (real version) + recreate services
	@git fetch --tags --quiet 2>/dev/null || true; \
	VER="$$(sh scripts/compute-version.sh)" || exit 1; \
	BUILD_REF="$(BUILD_REF)" SETUPTOOLS_SCM_PRETEND_VERSION="$$VER" docker compose up -d --build --force-recreate

restart:  ## Restart the sign without rebuilding
	docker compose restart

down:  ## Stop and remove the sign's containers
	docker compose down

logs:  ## Follow the sign's logs (Ctrl-C to stop)
	docker compose logs -f
```

(`up`/`restart`/`down`/`logs` set no `COMPOSE_PROFILES` and no build-args — they inherit the profile from `.env`/env. `update` keeps the version compute + `--build`, minus the forced profile.)

- [ ] **Step 7: Clarify the `clean` help text**

Replace:

```make
clean:  ## Remove build artifacts and caches
```

with:

```make
clean:  ## Remove build artifacts and caches (does NOT stop containers — use 'make down' for that)
```

- [ ] **Step 8: Update the two `make build-docker` mentions in comments**

In the panel-test-docker comment (around the "Run the panel-test inside the production Docker image" block), change `Requires \`make build-docker\` to` → `Requires \`make build\` to`. In the panel-map comment ("On a deployed sign use the -docker targets … needs"), change `needs \`make build-docker\` once` → `needs \`make build\` once`. In the same panel-test-docker comment, change the hand-rolled stop/start lines:

```
#   docker compose stop
#   make panel-test-docker
#   docker compose start
```

to:

```
#   make down
#   make panel-test-docker
#   make up
```

- [ ] **Step 9: Run the tripwire + a Make dry-run sanity**

Run: `uv run pytest tests/test_make_targets.py -v`
Expected: PASS (all 5 tests).
Run: `make -n update && make -n up && make -n down`
Expected: `update` expands to `git fetch … ; … docker compose up -d --build --force-recreate` with **no** `COMPOSE_PROFILES=`; `up`→`docker compose up -d`; `down`→`docker compose down`. No "missing separator" error.

- [ ] **Step 10: Lint + commit**

```bash
uv run --extra dev ruff check tests/test_make_targets.py
git add Makefile tests/test_make_targets.py
git commit -m "refactor(make): rename build-docker->build, rebuild->update; add up/down/restart/logs; uv preflight"
```

---

### Task 2: Dockerfile — update the guard + BUILD_REF comment

**Files:**
- Modify: `Dockerfile` (the `0.0.0` guard message; the BUILD_REF comment)

**Interfaces:** Consumes the new target names from Task 1.

- [ ] **Step 1: Update the guard message**

In `Dockerfile`, replace:

```dockerfile
        echo "Deploy with 'make setup' (first time) or 'make rebuild' (update); they compute it." >&2; \
```

with:

```dockerfile
        echo "Deploy with 'make setup' (first time) or 'make update' (subsequent); they compute it." >&2; \
```

- [ ] **Step 2: Update the BUILD_REF comment**

In `Dockerfile`, the comment block near the `ARG BUILD_REF=` line reads (around lines 84-87):

```dockerfile
# Build stamp — branch@shortsha, computed on the host by `make build-docker` /
# `make rebuild` and passed as BUILD_REF. A bare `docker compose build` (no arg)
# leaves it empty and the header shows "unknown" — deploy with `make rebuild` to
```

Replace the target names: `make build-docker` → `make build`, both `make rebuild` → `make update`.

- [ ] **Step 3: Verify no retired names remain in the Dockerfile**

Run: `grep -n 'make build-docker\|make rebuild' Dockerfile`
Expected: no output.

- [ ] **Step 4: Commit**

```bash
git add Dockerfile
git commit -m "refactor(docker): point the 0.0.0 guard + build-stamp comment at make build/update"
```

---

### Task 3: Scripts — sweep setup.sh, panel_map.py, compute-version.sh

**Files:**
- Modify: `scripts/setup.sh`, `scripts/panel_map.py`, `scripts/compute-version.sh`

**Interfaces:** Consumes the new target names from Task 1.

- [ ] **Step 1: `scripts/setup.sh` — point the printed guidance at the new verbs**

In the deploy "Next steps" heredoc, replace:

```sh
    • View live logs:       docker compose logs -f
    • Open the web UI:      http://localhost:8080
                            (requires COMPOSE_PROFILES=webui — see below)
    • Stop:                 docker compose down
```

with:

```sh
    • View live logs:       make logs
    • Open the web UI:      http://localhost:8080
                            (requires COMPOSE_PROFILES=webui — see below)
    • Stop:                 make down
```

And in the "Web UI (optional sidecar)" block, replace:

```sh
    Bring everything up with the web UI enabled:
      make rebuild
    (or add COMPOSE_PROFILES=webui to a .env and re-run make setup)
```

with:

```sh
    Bring everything up with the web UI enabled:
      COMPOSE_PROFILES=webui make up
    (or add COMPOSE_PROFILES=webui to a .env so every make up/update includes it)
```

- [ ] **Step 2: `scripts/panel_map.py` — fix the printed instruction**

In `scripts/panel_map.py` line ~115, replace `build once with \`make build-docker\`` → `build once with \`make build\``.

- [ ] **Step 3: `scripts/compute-version.sh` — fix the comment**

In `scripts/compute-version.sh` (the header comment ~line 5) replace `build-docker/rebuild, scripts/setup.sh` → `build/update, scripts/setup.sh`.

- [ ] **Step 4: Verify + lint**

Run: `grep -rn 'make build-docker\|make rebuild\|build-docker/rebuild' scripts/`
Expected: no output.
Run: `sh -n scripts/setup.sh && uv run --extra dev ruff check scripts/panel_map.py`
Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add scripts/setup.sh scripts/panel_map.py scripts/compute-version.sh
git commit -m "refactor(scripts): point setup/panel-map/compute-version at make build/update/logs/down"
```

---

### Task 4: Docs + compose.yaml + README sweep + cross-file tripwire

**Files:**
- Modify: `compose.yaml` (header), `README.md`, `docs/site/src/content/docs/hardware/building-your-own.mdx`, `docs/site/src/content/docs/concepts/web-status-ui.mdx`, `docs/site/src/content/docs/tools/panel-map.mdx`, `docs/site/src/content/docs/tools/panel-test.mdx`, `docs/site/src/content/docs/reference/cli.mdx`
- Test: `tests/test_make_targets.py` (append one assertion)

**Interfaces:** Consumes the new target names; final regression lock.

- [ ] **Step 1: `compose.yaml` header — advertise the make verbs**

Replace the Usage block:

```yaml
#   make setup                         # first time: preflight + seed + build + start
#   make rebuild                       # rebuild image (real version) + restart all services
#   docker compose logs -f             # tail logs
#   docker compose restart             # restart after editing config
#   docker compose down                # stop and remove
```

with:

```yaml
#   make setup                         # first time: preflight + seed + build + start
#   make update                        # rebuild image (real version) + recreate services
#   make logs                          # tail logs
#   make restart                       # restart after editing config
#   make down                          # stop and remove
```

- [ ] **Step 2: `README.md` — Deployment + Web UI**

In the "### Web UI (optional)" paragraph, replace `COMPOSE_PROFILES=webui docker compose up -d` → `COMPOSE_PROFILES=webui make up`.

Replace the final Deployment sentence:

```
The header shows the deployed build (`build <branch>@<sha>`). Use `make rebuild` to update the display **and** the webui sidecar together — it rebuilds the image with a real version baked in and restarts both services at once.
```

with:

```
The header shows the deployed build (`build <branch>@<sha>`). Use `make update` to rebuild the image (with a real version baked in) and recreate the running services. The webui sidecar is included when you've enabled the `webui` profile (e.g. `COMPOSE_PROFILES=webui` in `.env`).
```

- [ ] **Step 3: `building-your-own.mdx` — token swap**

Replace `make rebuild` → `make update` at both occurrences (the `make rebuild    # rebuild the image …` code-block line and the following prose sentence `After that, \`make rebuild\` rebuilds the image …`). In the code-block comment, also change `restart everything` → `recreate services` for accuracy.

- [ ] **Step 4: `web-status-ui.mdx` — token swaps + webui wording**

Replace `make build-docker` → `make build` and `make rebuild` → `make update` at every occurrence (3 lines). In the `⚠ webui build …` bullet, replace `Run \`make rebuild\` to bring both containers to the same image at once.` with `Run \`make update\` to rebuild and recreate the running services (the webui sidecar is included when its profile is enabled).`

- [ ] **Step 5: `panel-map.mdx`, `panel-test.mdx`, `cli.mdx` — token swap**

Replace every `make build-docker` → `make build` in these three files. In `panel-map.mdx`, verify the surrounding `-docker` suffix explanation still reads correctly after the swap (it explains that the `panel-map-*-docker` targets need the image that `make build` produces); adjust the sentence only if the swap made it ungrammatical.

- [ ] **Step 6: Append the cross-file regression lock to the tripwire**

Add to `tests/test_make_targets.py`:

```python
def test_no_shipped_file_references_retired_make_targets():
    roots = ["README.md", "compose.yaml", "Dockerfile", "scripts",
             "docs/site/src/content"]
    retired = ["make build-docker", "make rebuild"]
    offenders = []
    for root in roots:
        p = REPO_ROOT / root
        files = [p] if p.is_file() else [f for f in p.rglob("*") if f.is_file()]
        for f in files:
            try:
                text = f.read_text()
            except (UnicodeDecodeError, OSError):
                continue
            for tok in retired:
                if tok in text:
                    offenders.append(f"{f.relative_to(REPO_ROOT)}: {tok!r}")
    assert not offenders, f"retired target names still referenced: {offenders}"
```

- [ ] **Step 7: Run the tripwire + sweep grep**

Run: `uv run pytest tests/test_make_targets.py -v`
Expected: PASS (6 tests, including the new cross-file lock).
Run: `grep -rn 'make build-docker\|make rebuild' README.md compose.yaml Dockerfile scripts docs/site/src/content`
Expected: no output.

- [ ] **Step 8: Commit**

```bash
git add compose.yaml README.md docs/site/src/content tests/test_make_targets.py
git commit -m "docs: point deploy docs at make build/update/up/down/logs; lock against retired names"
```

---

### Task 5: Full-suite verification

**Files:** none (verification only).

- [ ] **Step 1: Full test suite**

Run: `make test`
Expected: all pass, including `tests/test_make_targets.py`. No regressions.

- [ ] **Step 2: Lint**

Run: `uv run --extra dev ruff check src/ tests/ tools/`
Expected: no violations.

- [ ] **Step 3: uv-preflight behavior check**

Run: `PATH=/usr/bin:/bin make -n dev` then read the `dev` recipe — confirm the first line is the `command -v uv` guard. (A true no-uv run isn't reproducible on a dev host that has uv; the recipe inspection + the tripwire cover it.)

- [ ] **Step 4 (optional, needs Docker + a built image): profile-agnostic teardown check**

This verifies the spec's `make down` note — that a webui started via profile is torn down by `make down` without forcing the profile.

```bash
make build                                  # build the image (real version)
COMPOSE_PROFILES=webui make up              # start display + webui
docker compose ps --services                # expect: led-ticker, led-ticker-webui
make down                                    # plain down, no profile
docker compose ps --services                # expect: empty (webui gone too)
```
Expected: after `make down`, no project containers remain. If the webui survives, add `--remove-orphans` to the `down` recipe (and only `down`) — do NOT add `COMPOSE_PROFILES`. If Docker isn't available, skip and note it; this is verified at deploy time.

---

## Notes / known minor

- `make up` on a host with no image present will trigger a versionless build → the existing Dockerfile `0.0.0` guard fails it loudly with the "deploy with make setup/update" message. Intended: first build is `setup`/`build`/`update`.
- Out-of-scope follow-ups (NOT this plan): `plan-gif`→`render-plan`, `setup-demo-fonts`→`fetch-demo-fonts`, `MODE=try` discoverability, `hooks` naming.
