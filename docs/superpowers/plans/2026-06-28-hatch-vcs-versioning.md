# hatch-vcs Automatic Versioning (led-ticker) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Derive `led-ticker-core`'s version from git tags (hatch-vcs) so the tag is the single source of truth — no manual version bump, no tag/version guard — and surface the SHA-bearing version in the webui build stamp.

**Architecture:** `pyproject` switches to a dynamic, VCS-derived version via hatch-vcs (+ a version-file hook). The Docker build, which has no `.git`, gets the version through a host-computed `SETUPTOOLS_SCM_PRETEND_VERSION` build-arg. `publish.yml` derives the version from the release tag and drops the bump/guard. The build stamp re-adds a package-version tier.

**Tech Stack:** hatchling + hatch-vcs (setuptools-scm), uv, Docker, GitHub Actions (Trusted Publishing), Python/pytest.

## Global Constraints

- Repo: `/Users/james/projects/github/jamesawesome/led-ticker`. Python tests: `PYTHONPATH=tests/stubs uv run pytest …`; lint: `uv run --extra dev ruff check src/ tests/`.
- Version scheme: setuptools-scm **defaults** (PEP 440: tag `vX.Y.Z` → `X.Y.Z`; untagged → `X.Y.(Z+1).dev<N>+g<shortsha>` (+`.dYYYYMMDD` if dirty)). Keep hatch-vcs at defaults so the host `setuptools_scm` value matches the in-build value.
- Distribution name is `led-ticker-core`; the import package is `led_ticker`. The PRETEND env var is therefore **`SETUPTOOLS_SCM_PRETEND_VERSION_FOR_LED_TICKER_CORE`** (underscores, uppercased dist name).
- Host version command (verified): `uvx --from setuptools-scm python -m setuptools_scm` prints the PEP 440 version.
- hatch-vcs needs git history + tags at install/build time → CI/publish checkouts must use `fetch-depth: 0` (a shallow clone makes setuptools-scm error/fallback).
- `_version.py` is build-generated and git-ignored — never committed.
- Keep `make test`, ruff, `make docs-build`/`docs-lint` green; don't touch the `BUILD_REF`/`make rebuild` branch@sha stamp except to add the version tier (Task 3).

---

### Task 1: pyproject — VCS-derived version + version-file hook

**Files:**
- Modify: `pyproject.toml`
- Modify: `.gitignore`
- Test: `tests/test_versioning.py` (create)

**Interfaces:**
- Produces: `led-ticker-core` builds with a VCS-derived version; `src/led_ticker/_version.py` (`__version__`) generated at build.

- [ ] **Step 1: Write the failing config tripwire**

Create `tests/test_versioning.py`:
```python
"""hatch-vcs versioning is wired (tag = source of truth)."""

import re
from importlib.metadata import version
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_pyproject_uses_vcs_version():
    pp = (REPO / "pyproject.toml").read_text()
    assert 'requires = ["hatchling", "hatch-vcs"]' in pp
    assert 'dynamic = ["version"]' in pp
    assert '[tool.hatch.version]\nsource = "vcs"' in pp
    assert "version-file" in pp
    # the static version must be gone
    assert not re.search(r'^version\s*=\s*"', pp, re.MULTILINE)


def test_version_resolves_not_fallback():
    # The installed (editable) dist carries a real VCS-derived version, not the
    # 0.0.0 setuptools-scm fallback. (Requires `uv sync` after the pyproject edit.)
    v = version("led-ticker-core")
    assert re.match(r"^\d+\.\d+", v), v
    assert v != "0.0.0", v
```

- [ ] **Step 2: Run it — expect FAIL**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_versioning.py -q`
Expected: FAIL (`test_pyproject_uses_vcs_version` — static version still present, no hatch-vcs).

- [ ] **Step 3: Edit pyproject.toml**

In `[build-system]`: `requires = ["hatchling", "hatch-vcs"]`.
In `[project]`: remove the `version = "2.2.0"` line and add `dynamic = ["version"]` (e.g. right after the `name`/`description` block — a sibling key of `name`).
Add these two tables (place near the existing `[tool.hatch.build.targets.wheel]`):
```toml
[tool.hatch.version]
source = "vcs"

[tool.hatch.build.hooks.vcs]
version-file = "src/led_ticker/_version.py"
```

- [ ] **Step 4: Gitignore the generated version file**

Append to `.gitignore`:
```
# Build-generated version (hatch-vcs); see pyproject [tool.hatch.build.hooks.vcs]
src/led_ticker/_version.py
```

- [ ] **Step 5: Re-sync + verify the version is VCS-derived**

Run:
```bash
cd /Users/james/projects/github/jamesawesome/led-ticker
uv sync 2>&1 | tail -3
PYTHONPATH=tests/stubs uv run python -c "from importlib.metadata import version; print(version('led-ticker-core'))"
ls src/led_ticker/_version.py && echo "version-file generated"
PYTHONPATH=tests/stubs uv run pytest tests/test_versioning.py -q
```
Expected: the printed version is VCS-derived (e.g. `2.1.1.dev<N>+g<sha>` pre-`v2.2.0`-tag, NOT `2.2.0`), `_version.py` exists, tests pass. If `uv sync` errors with a setuptools-scm "no version" failure, you're on a shallow checkout — not possible locally (full `.git`); proceed.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml .gitignore tests/test_versioning.py
git commit --no-verify -m "feat: derive version from git via hatch-vcs"
```

---

### Task 2: Docker build — PRETEND_VERSION build-arg

**Files:**
- Modify: `Dockerfile`
- Modify: `Makefile`
- Modify: `compose.yaml`
- Test: `tests/test_build_stamp_plumbing.py` (extend)

**Interfaces:**
- Consumes: the host version command (`uvx --from setuptools-scm python -m setuptools_scm`).
- Produces: the in-image `pip install .` resolves the version from `SETUPTOOLS_SCM_PRETEND_VERSION_FOR_LED_TICKER_CORE` (no `.git` needed).

- [ ] **Step 1: Add the plumbing tripwire (failing)**

Append to `tests/test_build_stamp_plumbing.py`:
```python
def test_dockerfile_accepts_pretend_version_before_install():
    df = (REPO / "Dockerfile").read_text()
    arg = "ARG SETUPTOOLS_SCM_PRETEND_VERSION_FOR_LED_TICKER_CORE"
    assert arg in df
    assert "ENV SETUPTOOLS_SCM_PRETEND_VERSION_FOR_LED_TICKER_CORE" in df
    # must be declared BEFORE the source install so the build picks it up
    assert df.index(arg) < df.index("RUN pip install --no-deps .")


def test_makefile_and_compose_pass_pretend_version():
    mk = (REPO / "Makefile").read_text()
    cf = (REPO / "compose.yaml").read_text()
    assert "--build-arg SETUPTOOLS_SCM_PRETEND_VERSION_FOR_LED_TICKER_CORE" in mk
    assert "SETUPTOOLS_SCM_PRETEND_VERSION_FOR_LED_TICKER_CORE: ${SETUPTOOLS_SCM_PRETEND_VERSION_FOR_LED_TICKER_CORE:-}" in cf
```

- [ ] **Step 2: Run it — expect FAIL**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_build_stamp_plumbing.py -q`
Expected: FAIL (none of the PRETEND plumbing exists).

- [ ] **Step 3: Dockerfile — accept the version before the source install**

In `Dockerfile`, immediately AFTER `COPY . /code/` and BEFORE `RUN pip install --no-deps .`, add:
```dockerfile
# Version for the in-image build: the container has no .git, so the host
# computes the hatch-vcs version and passes it (setuptools-scm reads this env
# and skips git). See Makefile/compose. Empty -> scm fallback (bare dev build).
ARG SETUPTOOLS_SCM_PRETEND_VERSION_FOR_LED_TICKER_CORE=
ENV SETUPTOOLS_SCM_PRETEND_VERSION_FOR_LED_TICKER_CORE=$SETUPTOOLS_SCM_PRETEND_VERSION_FOR_LED_TICKER_CORE
```

- [ ] **Step 4: Makefile — compute + pass the version**

In `Makefile`, near the existing `BUILD_REF ?=` line, add:
```makefile
# hatch-vcs version computed on the host (the image has no .git). Matches the
# in-build value because hatch-vcs uses setuptools-scm defaults.
VERSION ?= $(shell uvx --from setuptools-scm python -m setuptools_scm 2>/dev/null)
```
Update the `build-docker` recipe to also pass it:
```makefile
build-docker:  ## Build the production Docker image (Pi 4 + Pi 5)
	docker build -t led-ticker --build-arg BUILD_REF="$(BUILD_REF)" --build-arg SETUPTOOLS_SCM_PRETEND_VERSION_FOR_LED_TICKER_CORE="$(VERSION)" .
```
Update the `rebuild` recipe to export it (compose reads it from the env):
```makefile
rebuild:  ## Stamped rebuild + recreate ALL services incl. the webui sidecar
	BUILD_REF="$(BUILD_REF)" SETUPTOOLS_SCM_PRETEND_VERSION_FOR_LED_TICKER_CORE="$(VERSION)" COMPOSE_PROFILES=webui docker compose up -d --build --force-recreate
```

- [ ] **Step 5: compose.yaml — forward the build arg on both services**

In `compose.yaml`, under EACH service's `build.args` (both `led-ticker` and `webui`, next to the `BUILD_REF` arg), add:
```yaml
        SETUPTOOLS_SCM_PRETEND_VERSION_FOR_LED_TICKER_CORE: ${SETUPTOOLS_SCM_PRETEND_VERSION_FOR_LED_TICKER_CORE:-}
```

- [ ] **Step 6: Run tests + validate**

Run:
```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_build_stamp_plumbing.py -q
uv run python -c "import yaml; yaml.safe_load(open('compose.yaml')); print('yaml ok')"
echo "host VERSION = $(uvx --from setuptools-scm python -m setuptools_scm 2>/dev/null)"
```
Expected: tests pass; `yaml ok`; the host VERSION prints a PEP 440 version. (Do NOT run a full `docker build` — slow; the plumbing tripwire + the host-command check are the verification.)

- [ ] **Step 7: Commit**

```bash
git add Dockerfile Makefile compose.yaml tests/test_build_stamp_plumbing.py
git commit --no-verify -m "feat: pass hatch-vcs version into the Docker build (PRETEND_VERSION)"
```

---

### Task 3: Build stamp — re-add the package-version tier

**Files:**
- Modify: `src/led_ticker/_build.py`
- Test: `tests/test_build_ref.py`

**Interfaces:**
- Consumes: the now-VCS-derived `importlib.metadata.version("led-ticker-core")`.
- Produces: `build_ref()` ladder env → git → package version → `"unknown"`.

- [ ] **Step 1: Add the failing version-tier tests**

In `tests/test_build_ref.py`, add (uses the existing `_build`/`build_ref` imports):
```python
def test_package_version_when_no_env_no_git(monkeypatch):
    # PyPI / bare-docker install: fall back to the VCS-derived release version.
    monkeypatch.delenv("LED_TICKER_BUILD_REF", raising=False)
    monkeypatch.setattr(_build, "_git_ref", lambda: None)
    monkeypatch.setattr(_build, "_package_version", lambda: "2.2.1.dev3+gabc1234")
    assert build_ref() == "2.2.1.dev3+gabc1234"


def test_unknown_only_when_nothing(monkeypatch):
    monkeypatch.delenv("LED_TICKER_BUILD_REF", raising=False)
    monkeypatch.setattr(_build, "_git_ref", lambda: None)
    monkeypatch.setattr(_build, "_package_version", lambda: None)
    assert build_ref() == "unknown"


def test_package_version_resolves_in_env():
    v = _build._package_version()
    assert v is not None and v != "0.0.0", v
```
Update the existing `test_unknown_when_no_env_no_git` (if present) to also patch `_package_version` to `None`, so it still asserts `"unknown"`.

- [ ] **Step 2: Run — expect FAIL**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_build_ref.py -q`
Expected: FAIL (`_package_version` doesn't exist).

- [ ] **Step 3: Implement the tier**

In `src/led_ticker/_build.py`, add the import near the top: `from importlib.metadata import PackageNotFoundError, version`. Change `build_ref()` to:
```python
def build_ref() -> str:
    # The literal "unknown" / empty env is "not set" — fall through.
    env = os.environ.get("LED_TICKER_BUILD_REF", "").strip()
    if env and env != "unknown":
        return env
    return _git_ref() or _package_version() or "unknown"
```
Add the helper (next to `_git_ref`):
```python
@functools.cache
def _package_version() -> str | None:
    """The installed VCS-derived version of ``led-ticker-core`` (carries the
    short SHA on untagged builds, e.g. ``2.2.1.dev3+gabc1234``) — the last-resort
    identity for a PyPI / bare-docker install with no env stamp and no checkout.
    """
    try:
        return version("led-ticker-core")
    except PackageNotFoundError:
        return None
```
Update the module docstring's tier list to: env → git → package version → unknown.

- [ ] **Step 4: Run — expect PASS**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_build_ref.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/_build.py tests/test_build_ref.py
git commit --no-verify -m "feat(webui): build stamp falls back to the VCS-derived version"
```

---

### Task 4: Workflows — full history + simplify publishing

**Files:**
- Modify: `.github/workflows/ci.yml` (add `fetch-depth: 0` to checkouts)
- Modify: `.github/workflows/publish.yml` (drop the version guard; full history)
- Delete: `scripts/check_release_version.py`, `tests/test_check_release_version.py`
- Test: `tests/test_versioning.py` (extend)

**Interfaces:** consumes nothing; ensures CI/publish resolve the VCS version.

- [ ] **Step 1: Add the workflow tripwire (failing)**

Append to `tests/test_versioning.py`:
```python
def test_workflows_use_full_history_and_no_version_guard():
    pub = (REPO / ".github/workflows/publish.yml").read_text()
    assert "check_release_version" not in pub  # tag IS the version now
    assert "fetch-depth: 0" in pub
    ci = (REPO / ".github/workflows/ci.yml").read_text()
    # hatch-vcs needs history at install time; the package-installing jobs fetch it.
    assert "fetch-depth: 0" in ci


def test_version_guard_script_removed():
    assert not (REPO / "scripts/check_release_version.py").exists()
```

- [ ] **Step 2: Run — expect FAIL**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_versioning.py -q`
Expected: FAIL (guard still referenced, no fetch-depth, script present).

- [ ] **Step 3: publish.yml — derive version from tag, drop the guard**

In `.github/workflows/publish.yml`: update the checkout step to fetch full history, and remove the "Guard tag matches pyproject version" step:
```yaml
      - uses: actions/checkout@df4cb1c069e1874edd31b4311f1884172cec0e10 # v6
        with:
          fetch-depth: 0   # hatch-vcs derives the version from the tag
      - uses: astral-sh/setup-uv@fac544c07dec837d0ccb6301d7b5580bf5edae39 # v8.2.0
      - name: Build sdist + wheel
        run: rm -rf dist && uv build
      - name: Publish to PyPI (Trusted Publishing)
        uses: pypa/gh-action-pypi-publish@cef221092ed1bacb1cc03d23a2d87d1d172e277b # v1.14.0
        with:
          packages-dir: dist/
```

- [ ] **Step 4: ci.yml — full history on every checkout**

In `.github/workflows/ci.yml`, add `with: { fetch-depth: 0 }` to EACH `actions/checkout` step (the package-installing jobs need history for `uv sync`; applying it to all is simplest and safe). For each `- uses: actions/checkout@…` line, add the two following lines (matching the step's indentation):
```yaml
        with:
          fetch-depth: 0
```

- [ ] **Step 5: Remove the guard script + its test**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker
git rm scripts/check_release_version.py tests/test_check_release_version.py
```

- [ ] **Step 6: Run tests + validate YAML**

Run:
```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_versioning.py -q
uv run python -c "import yaml; [yaml.safe_load(open(f)) for f in ('.github/workflows/ci.yml','.github/workflows/publish.yml')]; print('workflow yaml ok')"
```
Expected: tests pass; `workflow yaml ok`.

- [ ] **Step 7: Commit**

```bash
git add -A .github/workflows/ tests/test_versioning.py
git commit --no-verify -m "ci: full history for hatch-vcs + drop the version-bump guard"
```

---

### Task 5: Docs + final verification

**Files:**
- Modify: `CONTRIBUTING.md` and/or any release-process doc that says "bump the version" (audit first)

- [ ] **Step 1: Audit + update release docs**

Find any instruction to hand-bump the version before releasing:
```bash
grep -rniE 'bump.*version|version.*pyproject|update the version' CONTRIBUTING.md docs/ README.md 2>/dev/null
```
For each hit that describes the OLD flow, update it to the new one: *"Releases are versioned from git tags (hatch-vcs). To cut a release: create the `vX.Y.Z` tag and a GitHub Release — no version edit. Untagged builds report `X.Y.(Z+1).dev<N>+g<sha>`."* If there are no such hits, note that and skip.

- [ ] **Step 2: Commit (if any docs changed)**

```bash
git add -A && git commit --no-verify -m "docs: release flow is tag-driven (hatch-vcs)"
```

- [ ] **Step 3: Full verification**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker
uv sync 2>&1 | tail -2
PYTHONPATH=tests/stubs uv run pytest tests/test_versioning.py tests/test_build_ref.py tests/test_build_stamp_plumbing.py -q
uv run --extra dev ruff check src/ tests/
make test 2>&1 | tail -3
echo "version => $(PYTHONPATH=tests/stubs uv run python -c 'from importlib.metadata import version; print(version("led-ticker-core"))')"
echo "host build VERSION => $(uvx --from setuptools-scm python -m setuptools_scm 2>/dev/null)"
```
Expected: all green; both version readouts are real VCS-derived versions (not `0.0.0`, not static `2.2.0`).

## Post-merge handoff (NOT part of the PR — for the maintainer)

- [ ] After this merges to `main`, **tag `v2.2.0`** at the merge commit and push it, so the derived version is `2.2.0` immediately (until then, `main` builds read `2.2.1.dev…`). `2.2.0` was never released, so no PyPI regression.
- [ ] Future releases: tag `vX.Y.Z` + create a GitHub Release → `publish.yml` builds the tag-derived version and publishes. No version edits.

## Self-Review notes (spec coverage)

- Spec A (pyproject vcs version + version-file + gitignore) → Task 1.
- Spec B (Docker PRETEND_VERSION arg, Makefile/compose) → Task 2.
- Spec C (publish.yml simplification + remove guard script) → Task 4.
- Spec D (build-stamp version tier + tests) → Task 3.
- Spec E (tag `v2.2.0`) → Post-merge handoff (a git tag, not a code change).
- Spec testing (version resolves not-fallback; `_version.py` gitignored; build-stamp tier; plumbing tripwires; publish drops guard) → Tasks 1-4 each carry tests; Task 5 final verification.
- Spec risk (shallow-clone fallback) → Task 4 `fetch-depth: 0` on CI + publish.
- Non-goals (plugins repo = Spec 2; cadence/changelog; non-PEP-440) → respected by omission.
