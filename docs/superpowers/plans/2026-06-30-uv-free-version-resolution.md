# uv-free, fail-loud version resolution — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Docker image always bake a real `led-ticker-core` version (computed from git, no `uv` needed) so plugins install, and make a `0.0.0` image impossible to ship silently.

**Architecture:** A new POSIX-sh script `scripts/compute-version.sh` is the single source of truth for the PEP 440 version. Every host build entry point (`make build-docker`, `make rebuild`, `scripts/setup.sh`, CI's `docker-build` job) computes it and passes it as `SETUPTOOLS_SCM_PRETEND_VERSION_FOR_LED_TICKER_CORE`. The production `Dockerfile` hard-fails if the installed core is `0.0.0`. Docs stop teaching the bare `docker compose up --build` command (which the guard now rejects).

**Tech Stack:** POSIX `sh`, GNU Make, Docker, GitHub Actions, pytest (for the two tripwires), Astro/Markdown docs.

## Global Constraints

- **Version floor:** first-party plugins require `led-ticker-core>=2.1` (some `>=2.2`); any computed version MUST clear that under PEP 440 ordering.
- **No uv on the build path:** `make build-docker`/`rebuild`/`setup.sh`/CI must not call `uv`/`uvx`. (`make dev`/`test`/`lint`/render keep uv — developer-only.)
- **POSIX sh only** in `scripts/compute-version.sh` and `scripts/setup.sh` (`#!/bin/sh`, `set -eu` in setup.sh). No bashisms.
- **The guard lives in `Dockerfile` only**, never `Dockerfile.try` (the try image intentionally builds core at 0.0.0 and excludes it).
- **Repo workflow:** work on branch `fix/uv-free-version` (worktree at `../led-ticker-uv-free-version`); never commit to `main`. Run `uv run --extra dev ruff check` before pushing. Run `make dev` once in the worktree before running tests.

---

## Prerequisite (do once before Task 1)

- [ ] **Set up the worktree venv**

Run: `cd /Users/james/projects/github/jamesawesome/led-ticker-uv-free-version && make dev`
Expected: `uv sync` completes and pre-commit hooks install.

- [ ] **Confirm you are on the right branch**

Run: `git branch --show-current`
Expected: `fix/uv-free-version` (NOT `main`).

---

### Task 1: `scripts/compute-version.sh` + tripwire

**Files:**
- Create: `scripts/compute-version.sh`
- Test: `tests/test_compute_version.py`

**Interfaces:**
- Produces: an executable script `scripts/compute-version.sh` that, run with CWD anywhere, prints a PEP 440 version string to stdout and exits 0 on success; on failure prints guidance to stderr, prints nothing to stdout, exits non-zero. Consumed by Tasks 3, 4, 5.

- [ ] **Step 1: Write the failing test**

Create `tests/test_compute_version.py`:

```python
"""Tripwire for scripts/compute-version.sh — the uv-free version source.

Regression lock for the silent-0.0.0 bug that broke every plugin install. The
script must emit a real PEP 440 version from git, bumping the patch in the dev
case to match setuptools-scm (guess-next-dev) so plugin `>=2.x` floors clear.
"""

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_SRC = (REPO_ROOT / "scripts" / "compute-version.sh").read_text()


def _git(repo, *args):
    subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _place_script(repo):
    scripts_dir = repo / "scripts"
    scripts_dir.mkdir(exist_ok=True)
    dest = scripts_dir / "compute-version.sh"
    dest.write_text(SCRIPT_SRC)
    dest.chmod(0o755)


def _init_repo(repo):
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t.t")
    _git(repo, "config", "user.name", "t")
    _place_script(repo)
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "init")


def _run(repo):
    return subprocess.run(
        ["sh", "scripts/compute-version.sh"],
        cwd=repo,
        capture_output=True,
        text=True,
    )


def test_on_tag_emits_clean_version(tmp_path):
    _init_repo(tmp_path)
    _git(tmp_path, "tag", "v2.4.0")
    r = _run(tmp_path)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "2.4.0"


def test_commits_past_tag_bumps_patch(tmp_path):
    _init_repo(tmp_path)
    _git(tmp_path, "tag", "v2.4.0")
    for i in range(3):
        (tmp_path / f"f{i}").write_text("x")
        _git(tmp_path, "add", ".")
        _git(tmp_path, "commit", "-q", "-m", f"c{i}")
    r = _run(tmp_path)
    assert r.returncode == 0, r.stderr
    # guess-next-dev bumps the patch: tag 2.4.0 + 3 commits -> 2.4.1.dev3
    assert r.stdout.strip() == "2.4.1.dev3"


def test_no_tags_fails_loud_with_empty_stdout(tmp_path):
    _init_repo(tmp_path)  # has a commit, no tags
    r = _run(tmp_path)
    assert r.returncode != 0
    assert r.stdout.strip() == ""
    assert "no release tags" in r.stderr.lower()


def test_not_a_git_clone_fails_with_zip_hint(tmp_path):
    _place_script(tmp_path)  # no `git init` — simulates a ZIP download
    r = subprocess.run(
        ["sh", "scripts/compute-version.sh"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert r.returncode != 0
    assert r.stdout.strip() == ""
    assert "git clone" in r.stderr.lower()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_compute_version.py -v`
Expected: FAIL — `FileNotFoundError` / read fails because `scripts/compute-version.sh` does not exist yet.

- [ ] **Step 3: Write the script**

Create `scripts/compute-version.sh`:

```sh
#!/bin/sh
# scripts/compute-version.sh — print led-ticker-core's PEP 440 version from git.
#
# Single source of truth for the version the build entry points (Makefile
# build-docker/rebuild, scripts/setup.sh, CI docker-build) pass to Docker as
# SETUPTOOLS_SCM_PRETEND_VERSION_FOR_LED_TICKER_CORE. No uv, no Python — git only.
# The image has no .git, so the host must compute this; an empty/0.0.0 core
# blocks every plugin install (plugins require led-ticker-core>=2.x).
#
# Success: prints the version to stdout, exit 0.
# Failure: prints actionable guidance to stderr, nothing to stdout, exit 1.
set -u

# Resolve to the repo root regardless of caller CWD.
cd "$(dirname "$0")/.." || exit 1

REPO_URL="https://github.com/JamesAwesome/led-ticker.git"

fail() {
    for line in "$@"; do
        printf '%s\n' "$line" >&2
    done
    exit 1
}

if [ ! -e .git ]; then
    fail \
        "Couldn't determine the led-ticker version — this folder isn't a git clone." \
        "Plugins need version info that a ZIP download doesn't include." \
        "Re-install with:  git clone $REPO_URL"
fi

desc="$(git describe --tags --long --match 'v[0-9]*' 2>/dev/null || true)"
if [ -z "$desc" ]; then
    hint="git fetch --tags"
    git_dir="$(git rev-parse --git-dir 2>/dev/null || true)"
    if [ -n "$git_dir" ] && [ -f "$git_dir/shallow" ]; then
        hint="git fetch --tags --unshallow"
    fi
    fail \
        "Couldn't determine the led-ticker version — no release tags found." \
        "Run this, then retry:  $hint"
fi

# desc looks like: v2.4.0-3-g6d65f8d9
ver="${desc#v}"      # 2.4.0-3-g6d65f8d9
ver="${ver%-g*}"     # 2.4.0-3
dist="${ver##*-}"    # 3
base="${ver%-*}"     # 2.4.0

if [ "$dist" = "0" ]; then
    # HEAD is exactly on a tag — clean release version.
    printf '%s\n' "$base"
else
    # Match setuptools-scm guess-next-dev: bump the last numeric component of
    # the base, then append .dev<distance>.  2.4.0 + 3 commits -> 2.4.1.dev3
    last="${base##*.}"   # 0
    prefix="${base%.*}"  # 2.4
    next=$((last + 1))   # 1
    printf '%s.%s.dev%s\n' "$prefix" "$next" "$dist"
fi
```

- [ ] **Step 4: Make it executable**

Run: `chmod +x scripts/compute-version.sh`
Expected: no output.

- [ ] **Step 5: Run the test to verify it passes**

Run: `uv run pytest tests/test_compute_version.py -v`
Expected: PASS — all four tests green.

- [ ] **Step 6: Sanity-check against the real repo (should match setuptools-scm)**

Run: `sh scripts/compute-version.sh`
Expected: a non-empty PEP 440 version (e.g. `2.4.1.dev3`) — NOT `0.0.0`, NOT empty.

- [ ] **Step 7: Lint + commit**

```bash
uv run --extra dev ruff check tests/test_compute_version.py
git add scripts/compute-version.sh tests/test_compute_version.py
git commit -m "feat(build): add scripts/compute-version.sh (uv-free version source)"
```

---

### Task 2: Dockerfile 0.0.0 guard + try-image exemption + tripwire

**Files:**
- Modify: `Dockerfile:70-71` (the `pip install --no-deps .` + constraints RUN)
- Modify: `Dockerfile.try` (add a one-line "intentionally exempt" comment near :37)
- Test: `tests/test_dockerfile_version_guard.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: a build-time guard. No Python symbols.

- [ ] **Step 1: Write the failing test**

Create `tests/test_dockerfile_version_guard.py`:

```python
"""Tripwire: the production Dockerfile must hard-fail a 0.0.0 core build.

Regression lock for the silent-0.0.0 image that broke plugin installs. The guard
lives ONLY in the production Dockerfile; Dockerfile.try intentionally builds core
at 0.0.0 and excludes it from constraints, so it must NOT carry the guard.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_prod_dockerfile_hard_fails_on_0_0_0():
    text = (REPO_ROOT / "Dockerfile").read_text()
    assert "CORE_VER" in text
    assert '"$CORE_VER" = "0.0.0"' in text
    assert "exit 1" in text


def test_try_dockerfile_is_exempt_from_guard():
    text = (REPO_ROOT / "Dockerfile.try").read_text()
    assert '"$CORE_VER" = "0.0.0"' not in text
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_dockerfile_version_guard.py -v`
Expected: FAIL on `test_prod_dockerfile_hard_fails_on_0_0_0` — `CORE_VER` not yet in the Dockerfile.

- [ ] **Step 3: Add the guard to the production Dockerfile**

In `Dockerfile`, replace this block (currently lines 70-71):

```dockerfile
RUN pip install --no-deps . \
 && pip list --format=freeze > /code/constraints-core.txt
```

with:

```dockerfile
RUN pip install --no-deps . \
 && CORE_VER="$(pip show led-ticker-core | awk '/^Version:/{print $2}')" \
 && if [ "$CORE_VER" = "0.0.0" ]; then \
        echo "ERROR: led-ticker-core built as 0.0.0 — no version was passed to the build." >&2; \
        echo "Deploy with 'make setup' (first time) or 'make rebuild' (update); they compute it." >&2; \
        exit 1; \
    fi \
 && pip list --format=freeze > /code/constraints-core.txt
```

- [ ] **Step 4: Add the exemption comment to `Dockerfile.try`**

In `Dockerfile.try`, the existing comment block above the `grep -v '^led-ticker-core=='` line already explains the 0.0.0 exclusion. Append one line to that comment block (immediately above the `RUN pip install --no-cache-dir . \` line) so a future maintainer doesn't add the prod guard here:

```dockerfile
# NOTE: the production Dockerfile's "fail if core==0.0.0" guard is intentionally
# absent here — the try image is SUPPOSED to build core at 0.0.0 and pull the
# released core from PyPI. Do not copy that guard into this file.
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `uv run pytest tests/test_dockerfile_version_guard.py -v`
Expected: PASS — both tests green.

- [ ] **Step 6: Commit**

```bash
git add Dockerfile Dockerfile.try tests/test_dockerfile_version_guard.py
git commit -m "feat(build): hard-fail a 0.0.0 core image; exempt the try image"
```

---

### Task 3: Wire the version into the Makefile

**Files:**
- Modify: `Makefile` (remove the `uvx` `VERSION` var ~127-136; rewrite `build-docker` and `rebuild` recipes; sharpen their `##` help text)

**Interfaces:**
- Consumes: `scripts/compute-version.sh` from Task 1.

- [ ] **Step 1: Remove the uvx-based VERSION block**

In `Makefile`, delete the comment + assignment block that currently reads (the 6-line comment ending in `…clean tag = X.Y.Z.` plus the `VERSION ?= $(shell uvx …)` line) and replace it with:

```make
# Package version (PEP 440) is computed per-recipe from git by
# scripts/compute-version.sh — no uv required. It's passed to the build as
# SETUPTOOLS_SCM_PRETEND_VERSION_FOR_LED_TICKER_CORE so the image (which has no
# .git) bakes a real version instead of the 0.0.0 scm fallback. Computing it
# inside each recipe means a missing version aborts that build loudly.
```

(Leave the `BUILD_REF ?= …` block immediately above it untouched.)

- [ ] **Step 2: Rewrite the `build-docker` recipe**

Replace the existing `build-docker` target with:

```make
build-docker:  ## Build the production image only (no start; used by the *-docker diagnostics)
	@VER="$$(sh scripts/compute-version.sh)" || exit 1; \
	docker build -t led-ticker \
	  --build-arg BUILD_REF="$(BUILD_REF)" \
	  --build-arg SETUPTOOLS_SCM_PRETEND_VERSION_FOR_LED_TICKER_CORE="$$VER" .
```

- [ ] **Step 3: Rewrite the `rebuild` recipe**

Replace the existing `rebuild` target with:

```make
rebuild:  ## Update a running deploy after 'git pull' — rebuild + recreate all services (incl. webui)
	@VER="$$(sh scripts/compute-version.sh)" || exit 1; \
	BUILD_REF="$(BUILD_REF)" SETUPTOOLS_SCM_PRETEND_VERSION_FOR_LED_TICKER_CORE="$$VER" COMPOSE_PROFILES=webui docker compose up -d --build --force-recreate
```

- [ ] **Step 4: Verify no uvx remains and the recipes call the script**

Run: `grep -n 'uvx\|compute-version' Makefile`
Expected: zero `uvx` matches; two `compute-version` matches (in `build-docker` and `rebuild`).

- [ ] **Step 5: Verify the dry-run expands the script call**

Run: `make -n build-docker`
Expected: output contains `sh scripts/compute-version.sh` and `docker build -t led-ticker` — no `uvx`.

- [ ] **Step 6: Commit**

```bash
git add Makefile
git commit -m "feat(build): compute version from git in make build-docker/rebuild; sharpen help"
```

---

### Task 4: Wire the version into `scripts/setup.sh`

**Files:**
- Modify: `scripts/setup.sh` (deploy block — compute/export version + BUILD_REF before `docker compose up -d --build`; fix the webui printout)

**Interfaces:**
- Consumes: `scripts/compute-version.sh` from Task 1.

- [ ] **Step 1: Compute and export the version before bring-up**

In `scripts/setup.sh`, find these two lines in the deploy block:

```sh
    say "Starting production stack (this may take a minute on first build)..."
    docker compose up -d --build
```

Replace them with:

```sh
    # Compute the package version on the host (no uv needed) so the image bakes
    # a real version instead of the 0.0.0 scm fallback — a 0.0.0 core blocks
    # every plugin install. Best-effort tag refresh first so it's current.
    [ -e .git ] && git fetch --tags --quiet 2>/dev/null || true
    if ! VERSION="$(sh scripts/compute-version.sh)"; then
        exit 1   # compute-version.sh already printed actionable guidance to stderr.
    fi
    export SETUPTOOLS_SCM_PRETEND_VERSION_FOR_LED_TICKER_CORE="$VERSION"
    BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
    SHA="$(git rev-parse --short HEAD 2>/dev/null || true)"
    export BUILD_REF="${BRANCH}@${SHA}"

    say "Starting production stack (this may take a minute on first build)..."
    docker compose up -d --build
```

- [ ] **Step 2: Point the webui-enable printout at `make rebuild`**

In the deploy "Next steps" heredoc, find:

```sh
  Web UI (optional sidecar):
    Stop the stack, then bring it up with the webui profile:
      COMPOSE_PROFILES=webui docker compose up -d --build
    Or add it to a .env:    COMPOSE_PROFILES=webui
```

Replace with:

```sh
  Web UI (optional sidecar):
    Bring everything up with the web UI enabled:
      make rebuild
    (or add COMPOSE_PROFILES=webui to a .env and re-run make setup)
```

- [ ] **Step 3: Shell-lint the script (syntax + no bashisms)**

Run: `sh -n scripts/setup.sh`
Expected: no output (valid POSIX sh syntax).

- [ ] **Step 4: Verify the wiring**

Run: `grep -n 'compute-version\|SETUPTOOLS_SCM_PRETEND\|BUILD_REF' scripts/setup.sh`
Expected: the new compute/export lines are present.

- [ ] **Step 5: Commit**

```bash
git add scripts/setup.sh
git commit -m "fix(setup): compute + export version and BUILD_REF before compose build"
```

---

### Task 5: Keep CI green (the guard would otherwise redden `docker-build`)

**Files:**
- Modify: `.github/workflows/ci.yml` (`docker-build` job — add `fetch-depth: 0`, pass the build-arg)

**Interfaces:**
- Consumes: `scripts/compute-version.sh` from Task 1.

- [ ] **Step 1: Update the `docker-build` job**

In `.github/workflows/ci.yml`, find the `docker-build` job's steps:

```yaml
    steps:
      - uses: actions/checkout@df4cb1c069e1874edd31b4311f1884172cec0e10 # v6
      - name: Build Docker image
        run: docker build --no-cache -t led-ticker-ci-test .
```

Replace with:

```yaml
    steps:
      - uses: actions/checkout@df4cb1c069e1874edd31b4311f1884172cec0e10 # v6
        with:
          fetch-depth: 0   # tags needed so scripts/compute-version.sh resolves a real version
      - name: Build Docker image
        run: |
          docker build --no-cache -t led-ticker-ci-test \
            --build-arg SETUPTOOLS_SCM_PRETEND_VERSION_FOR_LED_TICKER_CORE="$(sh scripts/compute-version.sh)" .
```

- [ ] **Step 2: Validate the workflow YAML parses**

Run: `uv run python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/ci.yml')); print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: pass a real version to the docker-build smoke build (guard-safe)"
```

---

### Task 6: Stop documenting the now-failing bare-compose command

**Files:**
- Modify: `compose.yaml` (header Usage comment)
- Modify: `docs/site/src/content/docs/getting-started.mdx:112`
- Modify: `docs/site/src/content/docs/hardware/building-your-own.mdx:150,154-155,210`
- Modify: `README.md:110`

**Interfaces:** none (docs/comments only).

- [ ] **Step 1: Fix the `compose.yaml` header Usage block**

In `compose.yaml`, replace this Usage line:

```yaml
#   docker compose up -d --build       # build (or rebuild) and start detached
```

with these two lines:

```yaml
#   make setup                         # first time: preflight + seed + build + start
#   make rebuild                       # rebuild image (real version) + restart all services
```

(Leave the `logs -f` / `restart` / `down` lines unchanged. Bare
`docker compose up -d --build` is intentionally no longer advertised — it bakes a
0.0.0 image that the Dockerfile guard now rejects.)

- [ ] **Step 2: Fix `getting-started.mdx` "Bring up the stack"**

In `docs/site/src/content/docs/getting-started.mdx`, replace the fenced block at line ~112:

```
docker compose up -d --build
```

with:

```
make setup
```

(`make setup` seeds config/.env, computes the version, builds, and starts.)

- [ ] **Step 3: Fix `building-your-own.mdx` deploy block + prose**

In `docs/site/src/content/docs/hardware/building-your-own.mdx`, replace the fenced block at line ~148-150:

```
make setup      # Docker preflight + config/.env seed + bring-up (first time)
# or, on subsequent deploys:
docker compose up -d --build
```

with:

```
make setup      # Docker preflight + config/.env seed + bring-up (first time)
make rebuild    # rebuild the image (real version) + restart everything (subsequent deploys)
```

Then replace the prose sentence at line ~154-155:

```
`docker compose up -d`. After that, a plain `docker compose up -d --build`
is enough for every subsequent deploy.
```

with:

```
`docker compose up -d`. After that, `make rebuild` rebuilds the image (with a
real version baked in) and restarts the display **and** the webui together for
every subsequent deploy.
```

- [ ] **Step 4: Fix the explanatory note at `building-your-own.mdx:210`**

Replace:

```
the first `docker compose up --build` is typically faster than a bare
`pip install` on the Pi.
```

with:

```
the first build (via `make setup`) is typically faster than a bare
`pip install` on the Pi.
```

- [ ] **Step 5: Fix the README deploy command**

In `README.md`, under "### Docker on Raspberry Pi", replace the fenced block at line ~108-110:

```
docker compose up -d
```

with:

```
make setup
```

(Leave README:121's existing `make rebuild` guidance and the webui
`COMPOSE_PROFILES=webui docker compose up -d` line — that one starts the webui
from the already-built image and triggers no version-less build.)

- [ ] **Step 6: Sweep for any remaining build-teaching command in shipped docs**

Run: `grep -rn 'docker compose up -d --build\|docker compose up --build' README.md compose.yaml docs/site/src/content`
Expected: no matches in `README.md`, `compose.yaml`, or `docs/site/src/content/**` (matches under `docs/superpowers/**` are historical plans/specs — leave them). If `concepts/web-status-ui.mdx` shows a `--build` command, apply the same `make rebuild` substitution; a no-`--build` `COMPOSE_PROFILES=webui docker compose up -d` is safe and may stay.

- [ ] **Step 7: Commit**

```bash
git add compose.yaml README.md docs/site/src/content
git commit -m "docs: deploy via make setup/rebuild; drop the bare compose build command"
```

---

### Task 7: Full-suite verification

**Files:** none (verification only).

- [ ] **Step 1: Run the whole test suite**

Run: `make test`
Expected: all tests pass, including `tests/test_compute_version.py` and `tests/test_dockerfile_version_guard.py`. No regressions.

- [ ] **Step 2: Lint everything touched**

Run: `uv run --extra dev ruff check src/ tests/ tools/`
Expected: no violations.

- [ ] **Step 3: Confirm no uvx on any build path**

Run: `grep -rn 'uvx' Makefile scripts/setup.sh .github/workflows/ci.yml`
Expected: no matches.

- [ ] **Step 4 (optional, if Docker is available on the dev host): end-to-end image build**

Run: `make build-docker && docker run --rm --entrypoint sh led-ticker -c "pip show led-ticker-core | awk '/^Version:/{print \$2}'"`
Expected: a real version (e.g. `2.4.1.dev3`), NOT `0.0.0`. If Docker isn't available locally, this is verified on the Pi at deploy time instead.

---

## Notes / known minor

- `make rebuild` always sets `COMPOSE_PROFILES=webui`, so pointing "subsequent
  deploys" at it starts a webui container even for users without a `[web]` block.
  That container exits cleanly when no `[web]` config is present (per the
  `compose.yaml` comment), so it's harmless — this is pre-existing behavior, not
  introduced here.
- Out-of-scope follow-ups (tracked in the spec, NOT this plan): seeding
  `config/requirements-plugins.txt` in `make setup`; surfacing plugin
  install results in the webui; a README "clone-not-ZIP" note; correcting the
  `constraints-core.txt`-at-runtime model in `CLAUDE.md`/`test_plugin_requirements.py`;
  a true target rename (`build-docker`→`build-image`, `rebuild`→`update`).
