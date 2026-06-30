# uv-free, fail-loud version resolution

**Date:** 2026-06-30
**Branch:** `fix/uv-free-version`
**Type:** Bugfix (build system / deployment)
**Reviewed by:** deploy-engineer, PM, and hobbyist personas (2026-06-30) — findings folded in below.

## Problem

`led-ticker-core` gets baked into the production Docker image as version `0.0.0`
whenever the host build does not pass a real
`SETUPTOOLS_SCM_PRETEND_VERSION_FOR_LED_TICKER_CORE`. Every first-party plugin
declares a `led-ticker-core>=2.1` (some `>=2.2`) floor, so at runtime
`plugin_reconcile.py` cannot install any of them and pip reports
`ResolutionImpossible` ("The user requested (constraint)
led-ticker-core==0.0.0"). Net effect on a fresh deploy: **the sign boots but no
plugins install** — silently, with the error buried in `docker compose logs`.

### Runtime failure mechanism (corrected)

The blocking constraint is **not** read from `/code/constraints-core.txt` at
runtime. `plugin_reconcile.py` freezes the **live container environment** at
startup via `pip list --format=freeze` (`plugin_cmd.py:387-388`, called from
`plugin_reconcile.py:493`) and passes that as `-c` to the plugin install. If the
installed `led-ticker-core` is `0.0.0`, the freeze captures
`led-ticker-core==0.0.0` and that `-c` line is what blocks the install.
`constraints-core.txt` is a separate artifact used only by the docs' air-gapped
derivative-image bake. **Implication:** the fix must correct the *installed wheel
version* (which the live freeze reads); a Dockerfile guard that checks
`pip show led-ticker-core` targets exactly that value, so it is the right check.

### Two leaks feed the symptom

1. **uv-gated computation.** `make build-docker` computes the version with
   `uvx --from setuptools-scm ...` (`Makefile:136`). With `uv`/`uvx` absent the
   command is "not found", stderr is swallowed by `2>/dev/null`, `VERSION`
   becomes empty, and the build runs with an empty PRETEND arg.

2. **The setup/compose path computes nothing.** `make setup` →
   `scripts/setup.sh` → `docker compose up -d --build`. `compose.yaml:23` reads
   `SETUPTOOLS_SCM_PRETEND_VERSION_FOR_LED_TICKER_CORE: ${...:-}` from the
   environment, which `setup.sh` never sets. So this path bakes `0.0.0`
   **even when uv is installed** — confirmed in a real deploy log.

### Why it lands as 0.0.0

`.dockerignore:5` excludes `.git`, so inside the image `setuptools-scm` has no
git history and no PRETEND_VERSION, hitting `fallback_version = "0.0.0"`
(`pyproject.toml:81`). The host is the only place a real version can come from.

## Goals

- A typical end user does **not** need `uv` installed to build/run.
- A `0.0.0` image can never silently ship again — broken builds fail loudly with
  guidance a non-expert can act on.
- One source of truth for version computation, wired into every host build entry
  point, **without breaking CI or the documented deploy commands**.

Non-goals (this change): changing how releases are versioned (hatch-vcs from
clean tags stays); renaming Make targets; seeding the plugins requirements file;
surfacing plugin install results in the UI. See **Out of scope / follow-ups**.

## Design

### 1. `scripts/compute-version.sh` (new — single source of truth)

POSIX `sh`, no uv, no Python. `cd`s to the repo root (`$(dirname "$0")/..`) so
it works regardless of caller CWD.

Behavior:
- If there is no `.git` at all → print **nothing** to stdout, exit non-zero, and
  print a ZIP-aware message to **stderr** (see Messaging).
- Run `git describe --tags --long --match 'v[0-9]*'`. If it yields nothing
  (no tags) → print nothing to stdout, exit non-zero, print a tags-missing
  message to stderr (shallow-aware: include `--unshallow` only when
  `<git-dir>/shallow` exists).
- On success, parse `v<base>-<distance>-g<sha>` and print a PEP 440 string:
  - `distance == 0` (HEAD exactly on a tag) → `<base>` (e.g. `2.4.0`).
  - otherwise → **bump the last numeric component of `<base>`**, then append
    `.dev<distance>` (e.g. tag `v2.4.0`, 3 commits → `2.4.1.dev3`). This matches
    `setuptools-scm`'s `guess-next-dev` scheme, which is what `uvx
    setuptools-scm` emits today (verified: `git describe` → `v2.4.0-3-g...`,
    `uvx` → `2.4.1.dev3`). The `+g<sha>` local segment is intentionally omitted
    so the baked package version is deterministic-by-commit; the SHA rides in
    `BUILD_REF`.

Why bump (not just `<base>.dev<N>`): under PEP 440, `2.4.0.dev3 < 2.4.0`. A
plugin floor of `>=2.4.0` published right after tag `v2.4.0` would *fail* against
an un-bumped dev string but *pass* against the bumped `2.4.1.dev3`. Matching
setuptools-scm avoids that regression and keeps the baked version identical to
today's behavior.

Properties: offline-friendly (no network in the script itself); deterministic by
commit; a stale-but-reachable tag still clears all `>=2.x` floors.

### 2. Wire it into every host build entry point (no global Make variable)

Compute the version *inside the recipes that need it* so the script never runs
on unrelated `make` invocations and its stderr guidance prints exactly once.

- `Makefile`:
  - Remove the `uvx`-based `VERSION ?=` line.
  - `build-docker`:
    ```make
    @VER="$$(sh scripts/compute-version.sh)" || exit 1; \
    docker build -t led-ticker \
      --build-arg BUILD_REF="$(BUILD_REF)" \
      --build-arg SETUPTOOLS_SCM_PRETEND_VERSION_FOR_LED_TICKER_CORE="$$VER" .
    ```
    On failure the script's stderr guidance shows and `|| exit 1` aborts.
  - `rebuild`: same `VER="$$(...)" || exit 1` capture, then the existing
    `COMPOSE_PROFILES=webui docker compose up -d --build --force-recreate`.
- `scripts/setup.sh` (deploy mode, runs under `set -eu`):
  - Opportunistically refresh tags first (best-effort, never fatal):
    `[ -e .git ] && git fetch --tags --quiet 2>/dev/null || true`.
  - Compute and export: `VERSION="$(sh scripts/compute-version.sh)" || exit 1`
    then `export SETUPTOOLS_SCM_PRETEND_VERSION_FOR_LED_TICKER_CORE="$VERSION"`.
  - Also set `BUILD_REF` (this path sets neither today → the webui header reads
    "unknown" for setup users). Guard each substitution against `set -e`:
    ```sh
    BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
    SHA="$(git rev-parse --short HEAD 2>/dev/null || true)"
    export BUILD_REF="${BRANCH}@${SHA}"
    ```
  - Then the existing `docker compose up -d --build`.

`uvx` leaves the build path entirely. `make dev`/`test`/`lint`/render targets
keep using `uv` — developer-only, unaffected.

### 3. Dockerfile hard-fail guard (defense in depth)

In the **production `Dockerfile` only**, in the source layer, after
`pip install --no-deps .` and **before** writing `constraints-core.txt`:

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

Makes a `0.0.0` image impossible through any path that reaches this Dockerfile.

**`Dockerfile.try` is intentionally exempt** — it deliberately builds core at
`0.0.0` and excludes it from constraints (`Dockerfile.try:37`,
`grep -v '^led-ticker-core=='`) so the try image resolves plugins' `>=2.x` from
PyPI instead of a locally built core. Add a one-line comment there noting the
guard is intentionally absent, so a future maintainer doesn't "unify" the two
Dockerfiles and reintroduce the bug. The text-scan tripwire (below) scopes to
`Dockerfile`, not `Dockerfile.try`.

### 4. Keep CI green (required — the guard breaks it otherwise)

`.github/workflows/ci.yml` `docker-build` job (`:161-171`) runs
`docker build --no-cache -t led-ticker-ci-test .` with a shallow, tagless
checkout and no build-arg → under the guard it resolves `0.0.0` and `exit 1`s,
turning `ci-passed` red on every PR that touches `Dockerfile`/`src/`/
`pyproject.toml`. (`publish.yml` builds PyPI wheels via `uv build`, not the
Docker image, so it is unaffected.) Fix the `docker-build` job:
- give its `actions/checkout` step `fetch-depth: 0` (so tags are present), and
- pass `--build-arg SETUPTOOLS_SCM_PRETEND_VERSION_FOR_LED_TICKER_CORE="$(sh scripts/compute-version.sh)"`.

### 5. Stop teaching the now-failing bare-compose command (required)

The guard makes a bare `docker compose up -d --build` (empty PRETEND →
`0.0.0`) fail. That exact command is currently documented as the happy path.
Replace it with the matching Make target:
- First-time deploy instructions → `make setup`.
- Update / webui-enable instructions → `make rebuild` (already sets
  `COMPOSE_PROFILES=webui`).

Known sites to update: `docs/site/.../hardware/building-your-own.mdx:150`,
`README.md` (~:110), `docs/site/.../getting-started.mdx` (~:112), the
`COMPOSE_PROFILES=webui docker compose up -d --build` line printed by
`scripts/setup.sh:139`, and the `compose.yaml` header comment. Implementation
greps for `docker compose up -d --build` / `docker compose up --build` to catch
any others.

### 6. Cheap target-help sharpening (in-scope ergonomics)

The PM and hobbyist both flagged that `build-docker` vs `rebuild` is muddy and
no target names the "update after `git pull`" op. We are already editing both
recipes, so tighten their `##` help text at zero risk (no renames):
- `build-docker`: `## Build the production image only (no start; used by the *-docker diagnostics)`
- `rebuild`: `## Update a running deploy after 'git pull' — rebuild + recreate all services (incl. webui)`

A true rename (`build-docker`→`build-image`, `rebuild`→`update`) is an
out-of-scope follow-up (muscle memory, docs, breaking). A trivial `update` alias
target pointing at `rebuild` is optional; include only if it stays a one-liner.

### Messaging (plain-English, action-first)

Per the hobbyist review, every failure message says what to DO, in order, and
names the likely cause (clone method), not the command the user already ran.

- No `.git` (ZIP download):
  > Couldn't determine the led-ticker version — this folder isn't a git clone.
  > Plugins need version info that a ZIP download doesn't include.
  > Re-install with:  git clone https://github.com/JamesAwesome/led-ticker.git

- `.git` present, no tags:
  > Couldn't determine the led-ticker version — no release tags found.
  > Run this, then retry:  git fetch --tags
  > (add --unshallow if you cloned with --depth)

Note `git fetch --tags --unshallow` is shown **only** for shallow clones; on a
complete clone `--unshallow` errors ("does not make sense on a complete
repository").

## Testing

- **pytest tripwire** for `compute-version.sh`: in a temp git repo, cover
  on-tag (`v2.4.0` → `2.4.0`), N-commits-past (`v2.4.0` + 3 commits →
  `2.4.1.dev3`, asserting the patch bump), and no-tags (non-zero exit, empty
  stdout) via subprocess.
- **Text-scan tripwire** asserting the production `Dockerfile` (not
  `Dockerfile.try`) retains the `0.0.0` guard (matches the repo's existing
  meta-tripwire style, e.g. `tests/test_engine_redraw_contract.py`).

## Out of scope / follow-ups (do not implement here)

Surfaced by the hobbyist/PM reviews; track separately so this bugfix stays tight:
1. **Seed `config/requirements-plugins.txt`** from its `.example` during
   `make setup` deploy mode (today only `config.toml` + `.env` are seeded), so
   the file that controls which plugins install is visible to new users.
2. **Surface plugin install success/failure** visibly (a post-startup summary
   line and/or the webui Store tab) so a failure isn't logs-only.
3. **README/docs note**: install via `git clone`, not ZIP, so version resolution
   works.
4. **Correct the imprecise "constraints-core.txt at runtime" model** in
   `CLAUDE.md:236` and `tests/test_plugin_requirements.py:53-55` to the live-freeze
   mechanism described above.
5. **Target rename** (`build-docker`→`build-image`, `rebuild`→`update`) as a
   considered, docs-coordinated change.

## Files touched (this change)

- `scripts/compute-version.sh` (new)
- `Makefile` (recipe-local version compute in `build-docker`/`rebuild`; help text)
- `scripts/setup.sh` (compute + export VERSION/BUILD_REF, opportunistic tag fetch)
- `Dockerfile` (0.0.0 guard in source layer)
- `Dockerfile.try` (one-line "intentionally exempt" comment)
- `.github/workflows/ci.yml` (`docker-build`: `fetch-depth: 0` + build-arg)
- `docs/site/.../hardware/building-your-own.mdx`, `getting-started.mdx`,
  `README.md`, `compose.yaml` header (replace bare `docker compose up --build`)
- `tests/` (two tripwires)
