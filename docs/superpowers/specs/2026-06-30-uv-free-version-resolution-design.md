# uv-free, fail-loud version resolution

**Date:** 2026-06-30
**Branch:** `fix/uv-free-version`
**Type:** Bugfix (build system / deployment)

## Problem

`led-ticker-core` gets baked into the production Docker image as version `0.0.0`
whenever the host build does not pass a real
`SETUPTOOLS_SCM_PRETEND_VERSION_FOR_LED_TICKER_CORE`. A `0.0.0` core is recorded
in `/code/constraints-core.txt`, and every first-party plugin declares a
`led-ticker-core>=2.x` floor — so at runtime `plugin_reconcile.py` installs
plugins with `-c constraints-core.txt` and pip refuses with `ResolutionImpossible`
("The user requested (constraint) led-ticker-core==0.0.0"). Result: **no plugins
install on a fresh deploy.**

### Two leaks, one symptom

1. **uv-gated computation.** `make build-docker` computes the version with
   `uvx --from setuptools-scm ...` (`Makefile:136`). With `uv`/`uvx` absent the
   command is "not found", stderr is swallowed by `2>/dev/null`, `VERSION`
   becomes empty, and the build runs with
   `--build-arg SETUPTOOLS_SCM_PRETEND_VERSION_FOR_LED_TICKER_CORE=""`.

2. **The setup/compose path computes nothing.** `make setup` →
   `scripts/setup.sh` → `docker compose up -d --build`. `compose.yaml` reads
   `SETUPTOOLS_SCM_PRETEND_VERSION_FOR_LED_TICKER_CORE: ${...:-}` from the
   environment, which `setup.sh` never sets. So this path bakes `0.0.0`
   **even when uv is installed** — confirmed in a real deploy log.

### Why it lands as 0.0.0

`.dockerignore` excludes `.git`, so inside the image `setuptools-scm` has no git
history and no PRETEND_VERSION, hitting `fallback_version = "0.0.0"`
(`pyproject.toml:81`). The host is the only place a real version can come from.

## Goals

- A typical end user does **not** need `uv` installed to build/run.
- A `0.0.0` image can never silently ship again — broken builds fail loudly with
  actionable guidance.
- One source of truth for version computation, wired into every build entry
  point.

Non-goals: changing how releases are versioned (hatch-vcs from clean tags stays);
reproducing every nuance of setuptools-scm's local-version/date segments
(the baked package version is intentionally deterministic-by-commit; the SHA
rides in `BUILD_REF`).

## Design

### 1. `scripts/compute-version.sh` (new — single source of truth)

POSIX `sh`. Computes a PEP 440 version from git, no uv, no Python:

- Run `git describe --tags --long --match 'v[0-9]*'`.
- Parse `v<base>-<distance>-g<sha>`:
  - `distance == 0` (HEAD on a tag) → print `<base>` (e.g. `3.0.0`).
  - otherwise → print `<base>.dev<distance>` (e.g. `2.4.1.dev3`). This matches
    what `uvx setuptools-scm` currently emits after the Makefile's
    `sed 's/+.*//'` strips the local `+gSHA` segment.
- On failure (not a git repo, or no matching tags) → print nothing and exit
  non-zero. The caller decides how loud to be.

Properties:
- **Offline-friendly.** No `git fetch`. A stale-but-reachable tag still yields a
  valid version `>= 2.x` that clears all plugin floors; an exactly-current
  version is a nicety, not a requirement.
- **Deterministic by commit.** No date/local segment in the output.

### 2. Wire it into every build entry point

- `Makefile`:
  - `VERSION ?= $(shell sh scripts/compute-version.sh)` (replaces the `uvx`
    line).
  - `build-docker` and `rebuild` gain a guard as the first recipe line:
    `@test -n "$(VERSION)" || { echo "ERROR: couldn't compute version — run: git fetch --tags --unshallow" >&2; exit 1; }`
- `scripts/setup.sh` (deploy mode): compute `VERSION` via the script and
  `BUILD_REF` via `git` (the path currently sets neither — `BUILD_REF` empty is
  why the webui header reads "unknown" for setup users), `export` both, error
  loudly if `VERSION` is empty, then run `docker compose up -d --build`.

`uvx` leaves the build path entirely. `make dev`/`test`/`lint`/render targets
keep using `uv` — developer-only, unaffected.

### 3. Dockerfile hard-fail guard (defense in depth)

In the source layer, after `pip install --no-deps .` and **before** writing
`constraints-core.txt`:

```dockerfile
RUN pip install --no-deps . \
 && CORE_VER="$(pip show led-ticker-core | awk '/^Version:/{print $2}')" \
 && if [ "$CORE_VER" = "0.0.0" ]; then \
        echo "ERROR: led-ticker-core built as 0.0.0 — no version was passed." >&2; \
        echo "Build via 'make setup' or 'make build-docker' (they compute it)." >&2; \
        exit 1; \
    fi \
 && pip list --format=freeze > /code/constraints-core.txt
```

This makes a `0.0.0` image impossible through **any** path, including a bare
`docker compose build` (which becomes intentionally unsupported and fails with a
clear pointer). The editable deps-layer install at `0.0.0` is untouched — the
guard only checks the real source-layer install.

## Testing

- **pytest tripwire** for `compute-version.sh`: in a temp git repo, cover
  on-tag (`3.0.0`), N-commits-past (`3.0.0.dev2`), and no-tags (non-zero exit,
  empty output) cases via subprocess.
- **Text-scan tripwire** asserting the Dockerfile retains the `0.0.0` guard
  (matches the repo's existing meta-tripwire style, e.g.
  `tests/test_engine_redraw_contract.py`).

## Risks to verify during implementation

- Confirm the release/CI workflow already passes a version arg (it builds from a
  clean tag via automation, so the Dockerfile guard should not affect it) —
  check `.github/workflows/` before finalizing.
- Confirm `compute-version.sh` output matches `uvx setuptools-scm` on a real
  checkout (both should give `2.4.1.dev3` on the current HEAD).

## Files touched

- `scripts/compute-version.sh` (new)
- `Makefile` (VERSION var + build-docker/rebuild guards)
- `scripts/setup.sh` (compute + export VERSION/BUILD_REF in deploy mode)
- `Dockerfile` (0.0.0 guard in source layer)
- `tests/` (two tripwires)
