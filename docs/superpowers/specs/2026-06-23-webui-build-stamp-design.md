# Design: webui build stamp ("what's actually deployed")

**Date:** 2026-06-23
**Status:** Approved for planning

## Motivation

A sign was silently running a months-old feature branch; every `docker compose build` recompiled the *old* source, and nothing in the running system revealed which commit was deployed. Diagnosing it took a chain of `docker exec` probes. A build stamp visible in the webui makes "what's actually deployed" a five-second glance and would have caught this immediately — the running branch name was the whole problem.

## Constraints (from exploration)

- The container has **no git at runtime** — `.git` is excluded from the Docker build context. The build identity must be **baked in at image-build time** (a build ARG → ENV).
- The **display** and **webui** run as **separate containers from one shared `led-ticker` image**. "What's rendering the sign" is the display process; "what you're looking at" is the webui. They can drift (e.g. one container rebuilt/recreated, the other not).
- `deploy/install.sh` does not build the image; the build paths are `make build-docker` and `docker compose build`.
- `status.json` is versioned by `SCHEMA_VERSION` (currently 7); its top-level key set is guarded by a tripwire in `tests/test_status_board.py`. Adding a key requires a version bump + tripwire update.

## Decisions (settled at brainstorm)

- Stamp content: **`branch@shortsha`** (+ `+dirty` if built from uncommitted changes) — branch included deliberately, since a stale branch was the failure.
- Placement: the **webui header**, next to the `● live` indicator — always visible, true "at a glance".
- **Drift detection IN:** the webui flags when its own build differs from the display's.

## Components

### A. Capture the build ref (image-build time)

- **Dockerfile** (final stage): `ARG BUILD_REF=unknown` → `ENV LED_TICKER_BUILD_REF=$BUILD_REF`.
- **`src/led_ticker/_build.py`** (new): `build_ref() -> str` returning `os.environ.get("LED_TICKER_BUILD_REF", "unknown")`. One source of truth for the env-var name + default; imported by both the display and the webui.
- **`make build-docker`**: compute and pass the ref —
  `BUILD_REF` defaults to `$(git rev-parse --abbrev-ref HEAD)@$(git rev-parse --short HEAD)` plus `+dirty` when `git diff --quiet` fails, and the recipe passes `--build-arg BUILD_REF="$(BUILD_REF)"`.
- **`compose.yaml`**: both services' `build:` gains `args: { BUILD_REF: ${BUILD_REF:-unknown} }`. A bare `docker compose build` (no env) stamps `unknown` — an honest signal that the stamped build path wasn't used.

### B. Display writes the build into status.json

- The display's `status_board.py` snapshot gains a top-level `"build": build_ref()` field.
- **`SCHEMA_VERSION` 7 → 8**, and the top-level-key-set tripwire in `tests/test_status_board.py` is updated to include `build`.

### C. Webui shows the stamp + drift check

- The webui's status response (the payload the frontend already polls) is augmented with **`webui_build`** = the webui container's own `build_ref()`, alongside the display's `build` (which arrives from `status.json`).
- The **header** (`index.html`, next to `#live`) renders a small dimmed monospace stamp: `build <display build>`. When `build` and `webui_build` are both present and differ, append a subtle `⚠ webui <webui_build>` so a container-drift deploy is obvious.
- Degraded cases: if the display status is missing / schema-mismatched (no `build`), the header shows the webui's own build labelled as such (`webui <ref>`) rather than nothing. `unknown` is shown verbatim (it means "not built via the stamped path").

### D. Deploy docs

A short note (deploy walkthrough + the README "Web UI" section) covering: build with the stamp (`make build-docker`, or `BUILD_REF=… docker compose up -d --build`), reading the header stamp to confirm what's live, and the **`COMPOSE_PROFILES=webui` gotcha** — a rebuild that omits the profile leaves the webui container on the old image (the drift the stamp now surfaces).

## Data flow

```
build:  make build-docker / compose  --build-arg BUILD_REF=branch@sha  → ENV LED_TICKER_BUILD_REF
display: build_ref() → status.json {"schema":8, "build":"branch@sha", ...}
webui:   serves status payload + adds {"webui_build": build_ref()}
header:  "build branch@sha"   [+ "⚠ webui <other>" when they differ]
```

## Scope / non-goals

- **IN:** A (capture), B (status field + schema bump), C (header stamp + drift check), D (deploy note), and the tests below.
- **OUT:** exposing the stamp on the LED panel itself; a full `/version` API; auto-updating/self-healing deploys; embedding the SHA into the PyPI package version. Plain `docker compose build` without `BUILD_REF` stamping `unknown` is acceptable (not a gap).

## Testing

- **Schema tripwire:** `tests/test_status_board.py` — the top-level key set now includes `build`; `SCHEMA_VERSION == 8`.
- **`_build.py`:** `build_ref()` returns the env value when set, `"unknown"` when unset.
- **Status content:** the snapshot carries `build` = the env ref.
- **Webui augmentation:** the served status payload includes `webui_build`.
- **Header render (content-presence):** `index.html` reads `build` / `webui_build` and renders the stamp + the drift `⚠` branch (mirrors the existing webui content tests).
- **Build path:** a test that `make build-docker` / the Makefile passes `--build-arg BUILD_REF` (grep-style, like the engine's other Makefile/CI tripwires).
- No hardware needed; `make docs-build` + `docs-lint` stay green for the docs note.

## Risks

- **`unknown` everywhere if people use a bare `docker compose build`.** Mitigated by the deploy-docs note and by `unknown` itself being a legible "you didn't stamp this" signal — strictly better than today (nothing).
- **Schema bump breaks an old reader.** The webui already handles `schema_mismatch` gracefully (degraded state, not a crash); the bump is routine here.
- **Detached HEAD at build** (branch resolves to `HEAD`) — acceptable; the short SHA still identifies the commit.
