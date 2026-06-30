# Coherent, profile-agnostic docker-lifecycle Make targets

**Date:** 2026-06-30
**Branch:** `refactor/make-lifecycle-targets`
**Type:** Refactor / DX (Make target naming + deploy lifecycle)
**Reviewed by:** PM, hobbyist, and maintainer/DevOps personas (2026-06-30).

## Problem

The Makefile's docker-lifecycle targets are the one cluster whose names don't
match their function, and the cluster is internally inconsistent (every other
family — `render-*`, `derive-*`, `docs-*`, `panel-map-*`, the `-docker`
diagnostic suffix — is already disciplined).

- **`rebuild`** says "build the image" but actually does `git fetch --tags` +
  compute version + `docker compose up -d --build --force-recreate` **with
  `COMPOSE_PROFILES=webui` forced** — i.e. it rebuilds AND restarts/recreates
  all services and force-starts the webui sidecar even for users who never
  opted in. Three hidden side effects behind a one-word "rebuild".
- **`build-docker`** builds the image only (never starts anything), but the
  `-docker` suffix elsewhere in the file means "run this op *inside* the
  production image" (`panel-test` vs `panel-test-docker`). Two meanings for one
  suffix; the name also reads like "build & run". A documented trap: after a
  `git pull`, a user runs `build-docker`, the image builds, nothing starts, and
  the sign keeps running old code — a silent no-op.
- **Lifecycle gaps:** there is no prod `up` / `down` / `restart` / `logs` target
  at all. The only teardown verb is `try-down` (the disposable stack). The
  panel-diagnostic help (`Makefile:55-59`) literally instructs users to
  hand-roll `docker compose stop` / `start`.
- **Dev setup `make dev`** runs `uv sync …` and dies with a raw
  "command not found" if `uv` is absent — no guidance (the original report
  noted "make setup doesn't walk you through installing uv").

## Goals

- Every docker-lifecycle target name matches its function.
- The cluster forms a coherent verb ladder, consistent with the rest of the
  Makefile.
- **No target hardcodes a compose profile** — `COMPOSE_PROFILES` is inherited
  from the environment / `.env` (compose auto-loads `.env`), so the webui is a
  clean opt-in, never forced by a verb.
- `make dev` fails helpfully when `uv` is missing.

Non-goals: renaming `setup` (kept — it's the one unambiguous name and has the
largest blast radius); back-compat aliases (the user chose a hard rename); the
unrelated polish items (see Out of scope).

## Design

### 1. The new docker-lifecycle cluster

Hard rename + additions. Every lifecycle verb is a thin `docker compose`
wrapper that **inherits `COMPOSE_PROFILES` from the environment** (no forced
profile).

| Target | Change | Recipe (essence) | Help text |
|---|---|---|---|
| `setup` | keep | `bash scripts/setup.sh $(MODE)` (preflight + seed + build + up) | One-command first run: check Docker, seed config/.env, bring up. |
| `build` | ← `build-docker` | compute version → `docker build` (no start) | Build the production image only (no start; prerequisite for the `*-docker` diagnostics). |
| `up` | **new** | `docker compose up -d` | Start the sign without rebuilding (set `COMPOSE_PROFILES=webui` in `.env` to include the web UI). |
| `update` | ← `rebuild` | `git fetch --tags` → compute version → `docker compose up -d --build --force-recreate` (NO forced profile) | Update a running deploy after `git pull`: rebuild the image (real version) + recreate services. |
| `restart` | **new** | `docker compose restart` | Restart the sign without rebuilding. |
| `down` | **new** | `docker compose down` | Stop and remove the sign's containers. |
| `logs` | **new** | `docker compose logs -f` | Follow the sign's logs (Ctrl-C to stop). |
| `try` / `try-down` | keep | disposable no-hardware stack | (unchanged) |
| `clean` | keep (help only) | remove build artifacts/caches | clarify: **does NOT touch running containers** — use `make down` for that. |

Resulting ladder: `setup → build → up → update → restart → down → logs`, with
`try` / `try-down` as the disposable pair.

`update`'s recipe is today's `rebuild` minus `COMPOSE_PROFILES=webui`:
```make
update:  ## Update a running deploy after 'git pull': rebuild + recreate services
	@git fetch --tags --quiet 2>/dev/null || true; \
	VER="$$(sh scripts/compute-version.sh)" || exit 1; \
	BUILD_REF="$(BUILD_REF)" SETUPTOOLS_SCM_PRETEND_VERSION="$$VER" docker compose up -d --build --force-recreate
```
`build` is today's `build-docker` recipe unchanged except the target name.
The four new verbs take no build-args (they don't build), so they're one
`docker compose` line each.

**Behavior change to call out:** `make update` no longer force-starts the webui.
The webui comes up only when `COMPOSE_PROFILES=webui` is set (in `.env` or the
environment) — same opt-in the docs already describe for `up`. `docker compose
down` tears down all running project containers regardless of profile, so
`make down` stops the webui if it was running (the plan verifies this against a
profile-started webui and adds `--remove-orphans` only if a survivor appears —
without forcing the profile *on*).

### 2. `make dev` uv preflight

Mirror `setup.sh`'s Docker preflight. First recipe line of `dev`:
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
Scope: `make dev` only — the documented contributor-setup entry point. Not
sprinkled across every `uv run` target (noise). `hooks` is left as-is.

### 3. Migration — hard rename, no aliases

Rename `build-docker`→`build` and `rebuild`→`update` outright; sweep all
references in one PR. **CI is untouched** (no workflow invokes these targets;
`ci.yml` only mentions `make test` in a comment).

References to update (verified on `main`):

- **`rebuild` → `update`:**
  `Makefile` (target + `.PHONY` + the version comment ~131-135),
  `README.md:121`, `compose.yaml:7`, `scripts/setup.sh:151`,
  `Dockerfile` (the `0.0.0` guard message — currently "...or 'make rebuild'"),
  `scripts/compute-version.sh:5` (comment), `scripts/panel_map.py` (none),
  `docs/site/.../hardware/building-your-own.mdx:149,154`,
  `docs/site/.../concepts/web-status-ui.mdx:271,273,274`.
- **`build-docker` → `build`:**
  `Makefile` (target + `.PHONY` + comments ~52-53/78-79),
  `scripts/panel_map.py:115`, `scripts/compute-version.sh:5` (comment),
  `docs/site/.../tools/panel-map.mdx:29,47`,
  `docs/site/.../tools/panel-test.mdx:37`,
  `docs/site/.../concepts/web-status-ui.mdx:271`,
  `docs/site/.../reference/cli.mdx:160`.
- **New `up`/`down`/`restart`/`logs`:** additive; add to `make help` naturally
  and update `compose.yaml` header + `README.md` Deployment + `setup.sh`
  "Next steps" so a bare `docker compose up -d` / `down` / `logs -f` instruction
  points at the new make verbs. The panel-diagnostic help (`Makefile:55-59`)
  switches its hand-rolled `docker compose stop`/`start` to `make restart` /
  `make down` + `make up`.

`setup.sh` keeps its current profile-agnostic bring-up (`docker compose up -d
--build` with the version compute already added); only its printed
`make rebuild` guidance (line 151) changes to `make update`.

### 4. Edge: `make up` on a missing image

`docker compose up -d` with no image present will build it — versionless (no
build-arg) → the Dockerfile `0.0.0` guard fails the build loudly with its
"deploy with `make setup`/`make update`" message. Acceptable: first-build is
`setup`/`build`/`update`; the guard is the safety net for misuse. (The guard
message text is updated in §3.)

## Testing

A `tests/test_make_targets.py` tripwire (text-scan, matching the repo's
meta-tripwire style):
- The new lifecycle targets are defined: `setup`, `build`, `up`, `update`,
  `restart`, `down`, `logs`, `try`, `try-down`, `clean` — and listed in
  `.PHONY`.
- The old names are gone: no `^build-docker:` or `^rebuild:` target definition.
- **Profile-agnostic invariant:** no `COMPOSE_PROFILES=` appears in the
  `Makefile` lifecycle recipes (locks in the user's "don't force a profile"
  requirement).
- `make dev`'s recipe contains a `command -v uv` guard.
- No shipped file (`README.md`, `compose.yaml`, `scripts/`, `Dockerfile`,
  `docs/site/src/content/**`) references the retired target names
  `make build-docker` or `make rebuild` (grep-based, excludes
  `docs/superpowers/**` history).

Plus the existing full suite (`make test`) must stay green.

## Out of scope / follow-ups

- `plan-gif` → `render-plan`, `setup-demo-fonts` → `fetch-demo-fonts` (prefix-
  family polish; near-zero blast radius, but unrelated to the lifecycle).
- Making `MODE=try` / `make try` more discoverable in `setup` help text.
- `hooks` target naming ambiguity.
- Back-compat aliases (explicitly declined — hard rename chosen).

## Files touched

- `Makefile` (rename 2 targets, add 4, `.PHONY`, `dev` uv guard, `clean` +
  panel-diagnostic help text, comments)
- `Dockerfile` (guard message `make rebuild` → `make update`)
- `scripts/setup.sh` (printed guidance), `scripts/panel_map.py` (string),
  `scripts/compute-version.sh` (comment)
- `README.md`, `compose.yaml` (header), and the docs-site pages enumerated in §3
- `tests/test_make_targets.py` (new tripwire)
