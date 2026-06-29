# Design: hatch-vcs automatic versioning for led-ticker (Spec 1)

**Date:** 2026-06-28
**Status:** Approved for planning
**Scope note:** This is Spec 1 of 2. Spec 2 (`led-ticker-plugins` hatch-vcs + the `led-ticker-telnet` PyPI release) is a separate repo and a separate spec, done after this one.

## Motivation

`led-ticker-core`'s version is a static `version = "2.2.0"` in `pyproject.toml`, hand-bumped per release and guarded against the release tag by `scripts/check_release_version.py`. That's error-prone (the static version has already drifted ahead of the tags — `2.2.0` with the latest tag at `v2.1.0`) and is pure manual toil. Deriving the version from git tags makes the **tag the single source of truth**: cutting a release becomes "tag + release," the version can't disagree with the tag, and the version string carries the commit SHA on non-tagged builds — which also lets the webui build stamp surface a meaningful identity for pip/bare-docker installs.

## Decisions (settled at brainstorm)

- **Version source:** `hatch-vcs` (VCS-derived), default setuptools-scm PEP 440 scheme.
- **Build stamp:** re-add the package-version tier (it now carries the SHA, so it's meaningful again).
- **Docker version injection:** `SETUPTOOLS_SCM_PRETEND_VERSION_FOR_LED_TICKER_CORE` build-arg, computed on the host.
- **First tag:** `v2.2.0` (static `2.2.0` is unreleased — no PyPI regression).

## Components

### A. pyproject — VCS-derived version

- `[build-system]` `requires = ["hatchling", "hatch-vcs"]`.
- `[project]`: remove `version = "2.2.0"`; add `dynamic = ["version"]`.
- `[tool.hatch.version] source = "vcs"`.
- `[tool.hatch.build.hooks.vcs] version-file = "src/led_ticker/_version.py"` — writes the resolved version (`__version__ = "…"`) into the package at build, so it's importable and ships in the wheel.
- `.gitignore`: add `src/led_ticker/_version.py` (build-generated, never committed).

Version behavior (setuptools-scm default): on tag `v2.3.0` → `2.3.0`; an untagged commit past `v2.3.0` → `2.3.1.dev<N>+g<shortsha>` (+`.dYYYYMMDD` when the tree is dirty).

### B. Docker build — PRETEND_VERSION build-arg

The container has no `.git`, so the in-image `pip install --no-deps .` cannot run `git describe`. The host (which has `.git`) computes the scm version and passes it in:

- `Dockerfile`: add `ARG SETUPTOOLS_SCM_PRETEND_VERSION_FOR_LED_TICKER_CORE=` and `ENV SETUPTOOLS_SCM_PRETEND_VERSION_FOR_LED_TICKER_CORE=$SETUPTOOLS_SCM_PRETEND_VERSION_FOR_LED_TICKER_CORE`, declared **before** the `RUN pip install --no-deps .` so the build picks it up. (setuptools-scm reads this env and skips git entirely.)
- `Makefile`: a `VERSION` var computed on the host via the project's own scm (e.g. `uv run hatchling version` / `python -m setuptools_scm`), passed by `build-docker` / `rebuild` as `--build-arg SETUPTOOLS_SCM_PRETEND_VERSION_FOR_LED_TICKER_CORE="$(VERSION)"` alongside the existing `BUILD_REF`.
- `compose.yaml`: both services forward `SETUPTOOLS_SCM_PRETEND_VERSION_FOR_LED_TICKER_CORE: ${SETUPTOOLS_SCM_PRETEND_VERSION_FOR_LED_TICKER_CORE:-}` as a build arg.
- Empty/absent → setuptools-scm fallback (an unhelpful `0.0.0`-style version); acceptable for a bare `docker compose build` (a developer path), same posture as the build-stamp's `unknown`.

### C. Release workflow — automatic

The release runner checks out the tag (a real git checkout with full history), so hatch-vcs derives the version from the tag directly — no PRETEND needed there.

- `.github/workflows/publish.yml`: drop the `check_release_version.py` guard step; `uv build` now derives the version from the tag. Keep the `release: [published]` trigger, the `release` environment gate, and Trusted Publishing.
- **Remove `scripts/check_release_version.py`** (and its test, if any) — the tag/version mismatch it guarded against is now impossible.
- Cutting a release: create tag `vX.Y.Z` + a GitHub Release. Nothing else.

### D. Build stamp — re-add the version tier

`build_ref()` (`src/led_ticker/_build.py`) ladder becomes: env (`branch@sha`) → runtime git (`_git_ref`) → **package version** → `"unknown"`.

- Re-add `_package_version()` → `importlib.metadata.version("led-ticker-core")` (now VCS-derived, carries the SHA). Return it verbatim (e.g. `2.2.1.dev4+ge8991a9`); `None`/raise → fall through to `"unknown"`.
- Re-add the tier tests (env-wins, git, **version fallback**, unknown) — restores the tier B removed, now justified because the version is no longer branchless/static.

### E. Version reconciliation + first tag

Static `2.2.0` is unreleased (tags stop at `v2.1.0`; no `v2.2.0` tag → no Release → not on PyPI). At cutover, **tag `v2.2.0`** at the merge commit so the derived version is `2.2.0` immediately. Between tags thereafter, dev builds read `2.2.1.dev…+g…`. No PyPI version regression.

## Data flow

```
git tag vX.Y.Z ──► hatch-vcs (setuptools-scm) ──► version X.Y.Z
  release runner:  uv build (real .git) ─► version from tag ─► PyPI (Trusted Publishing)
  Pi/local Docker: host computes version ─► SETUPTOOLS_SCM_PRETEND_VERSION build-arg ─► in-image pip install
  any install:     importlib.metadata.version("led-ticker-core") ─► build_ref() version tier
```

## Scope / non-goals

- **IN:** A (pyproject vcs version + version-file), B (Docker PRETEND_VERSION arg), C (publish.yml simplification + remove the guard script), D (build-stamp version tier), E (tag `v2.2.0`), tests.
- **OUT:** `led-ticker-plugins` (Spec 2); release cadence / changelog automation; non-PEP-440 schemes (CalVer); any change to the `BUILD_REF`/`make rebuild` branch@sha stamp beyond adding the version tier.

## Testing

- **Version resolves, not fallback:** a test/`make` check that `uv build` (or `hatchling version`) yields a real version (matches `^\d+\.\d+`), not the `0.0.0` scm-fallback.
- **`_version.py`:** git-ignored; importable as `led_ticker.__version__` after a build.
- **Build-stamp version tier:** `build_ref()` returns the package version when env + git are absent; `"unknown"` only when the package metadata is also unavailable.
- **Plumbing:** Makefile/compose pass `SETUPTOOLS_SCM_PRETEND_VERSION_FOR_LED_TICKER_CORE` (content-presence tripwire, like the `BUILD_REF` ones); `publish.yml` no longer references `check_release_version.py`.
- **No regression:** `make test`, ruff, `make docs-build`/`docs-lint` green.

## Risks

- **setuptools-scm fallback to `0.0.0` if git/tags are missing** (shallow clone, no `.git`) — mitigated: the release runner does a full checkout; the Docker path uses PRETEND_VERSION; a bare build degrading is acceptable. CI should fetch tags (`fetch-depth: 0`) where it builds.
- **A consumer importing a hardcoded `__version__`/static version** — none in core today; the version-file hook provides `led_ticker.__version__` going forward.
- **`hatchling version` host command availability** — the plan pins the exact host command (uv-run hatchling or setuptools-scm) and verifies it prints a PEP 440 version before wiring it into the Makefile.
