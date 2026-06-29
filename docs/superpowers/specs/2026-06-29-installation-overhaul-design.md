# Installation overhaul — dead-simple setup, one deploy path — Design

**Date:** 2026-06-29
**Status:** Approved (brainstorm)
**Item:** the long-deferred "installation flow review / uplifts / docs."

## Goal

Make led-ticker **dead simple to set up**, and end the **split installation paths**. Two outcomes:
1. **Docker is the single deploy path.** Drop the systemd/bare-metal deploy machinery — it has drifted from the new features and doubles the maintenance surface.
2. **Two signposted, dead-simple quickstarts:** "try it on your computer" (no hardware) and "deploy to your Pi."

Plus the friction-killers: help users install Docker itself, a one-command bootstrap, and a repo-hygiene fix so a user's own config/assets never show up as untracked.

## Decisions (locked in brainstorm)

- **Drop the systemd path.** Verified gaps with current features: the display unit is `Restart=on-failure`, but the restart-to-apply button does a clean `sys.exit(0)` → systemd would NOT restart it (panel stays dark); the webui unit's `DynamicUser=yes` can't write `config.toml` → the web config editor fails. The plugin reconcile *does* work bare-metal, but two webui features are broken and every new feature needs dual-path testing. Docs already say "prefer Docker"; real signs run Docker.
- **Both experiences are dead-simple:** a laptop **try-it** (no hardware) and a Pi **deploy**.
- **Images are built locally** (no prebuilt-image registry workstream — noted as a possible future; the user chose build-locally for now).
- **The try-it uses a slim headless image** (no rgbmatrix compile → fast build), generalizing the telnet smoke `Dockerfile.smoke` pattern.
- **One phased spec** (this), phased A–E for writing-plans.

## Non-goals

- Publishing a prebuilt multi-arch image (future lever; biggest remaining friction but out of scope here).
- Any engine/render change; the brightness-override seam.
- Changing the production deploy's runtime behavior — only the docs/bootstrap/packaging *around* it.

## Phases

### Phase A — Drop systemd + make Docker the single deploy path
- Remove `deploy/install.sh`, `deploy/led-ticker.service`, `deploy/led-ticker-webui.service`. Keep `deploy/busy-light-camera-watcher.lua` (unrelated).
- Grep for and remove any references (CI, Makefile, READMEs) to those files / `systemctl` / `/opt/led-ticker`. Confirm nothing else depends on `install.sh`.
- (The systemd *docs* sections are removed in Phase D.)

### Phase B — Repo hygiene: `.gitignore` + user-content convention
- Today the `.gitignore` ignores user content by **hardcoded per-sign filenames** (`config/config.pool_bigsign.toml`, `config/config.*.production.toml`) next to ~a dozen committed sample `.toml`s + committed `config/assets/`. A user dropping their own `config.toml` or media shows up as untracked.
- Establish **pattern-based ignores + a clear convention**: a user's running config (`config/config.toml`) + `config/requirements-plugins.txt` stay ignored (already are); replace the hardcoded per-sign lines with a pattern (e.g. ignore `config/*.toml` with `!config/*.example.toml` un-ignored). **Audit the committed non-example `config/*.toml`** (config.baseball.toml, config.busy_*.toml, config.clock_smoketest.toml, …): decide per-file — rename committed dev/sample configs to `*.example.toml` (so they stay tracked under the un-ignore) OR move them to a `config/samples/` dir, so the `config/*.toml`-ignored pattern cleanly separates "committed samples" from "user content." (Exact globs + the per-file dispositions are pinned in the plan.)
- Establish a **gitignored user-assets location** so added media doesn't show as untracked (e.g. document that user media lives under a gitignored path the config points at; keep the committed sample assets tracked). Pin the exact convention in the plan.
- Success: after `clone → cp examples → add your config.toml + your media`, `git status` is clean.

### Phase C — Laptop try-it (no hardware)
- A **slim headless image** (`Dockerfile.try` or similar): `python:3.14`, `pip install led-ticker-core` (+ the webui), **no rgbmatrix compile**; runs the engine with `backend = headless` (or `telnet`) + the webui. Generalize the telnet `Dockerfile.smoke` pattern.
- A compose **`try` profile** (or a `compose.try.yaml`): brings up the headless engine + webui, ports published, so the user opens `localhost:<port>` and sees the sign in the **preview**. No hardware, fast build, one toolchain (Docker).
- Ship a **try-it sample config** (a lively headless config — reuse/adapt the telnet smoke config: bordered + transitions + rainbow).

### Phase D — Pi-deploy bootstrap + Docker-install help
- **Step 0: install Docker (official source).** Docs + a preflight: detect a missing/old Docker and print the **official** install link (`get.docker.com` convenience script for Linux/Pi; Docker Desktop for Mac/Windows) — not stale distro packages. Note `docker compose` v2 ships with modern Docker.
- A **bootstrap** (`make setup` / `scripts/setup.sh`): preflight Docker → copy `config.toml` + `.env` from the examples if absent → bring up the chosen mode. Goal: `clone → one command → running`, with sane defaults so a first-timer hits no "you have to just know this" step.

### Phase E — Docs rewrite
- Rewrite `getting-started.mdx`, `hardware/building-your-own.mdx`, `tutorial/01-setup.mdx`: one Docker deploy path, the **two quickstarts** (try-it + deploy), the **Docker-install Step 0**, the bootstrap, and the repo-hygiene convention. Remove all systemd/bare-metal sections.
- Sweep other surfaces for stale references: `README.md`, `llms.txt`, any page mentioning `install.sh` / systemd / `/opt/led-ticker`.
- DOCS-STYLE compliant (no release-history framing, no "footgun").

## Constraints

- Docker is the single deploy path; do **not** lose the ability to run with **no hardware** (headless/telnet backends — the try-it depends on this).
- The slim try-it image must build **without** the rgbmatrix C library (relies on core's `_compat` stub for any rgbmatrix reference; the headless/telnet backends never construct `RGBMatrix`).
- The production deploy's runtime behavior is unchanged — this is docs/bootstrap/packaging around it.
- Webui stays rgbmatrix-pure; PEP 649.

## Testing / verification

- **Phase A/B/C/D are largely non-unit-testable** (file removal, .gitignore, Dockerfiles, scripts, docs) — verified by: a clean-clone `git status` check (B), a `make docs-build` + `docs-lint` pass (E), and **maintainer deploy-smokes** (flag, don't fake): (1) the try-it (`docker compose --profile try up` → open the preview, no hardware); (2) the Pi deploy still works end-to-end; (3) the bootstrap on a fresh checkout (clone → setup → running); (4) Docker-preflight on a box without Docker prints the official link.
- Any scripted logic (the bootstrap's preflight, a `.gitignore`-coverage check) gets a small test where feasible.

## Risks

- **Destructive removal** (Phase A): ensure nothing (CI, docs deep-links, the firebird/hardware pages) silently depends on `install.sh` / the units before deleting.
- **The committed sample `.toml` configs** (Phase B): the new ignore pattern must not accidentally untrack or mis-handle them — hence the per-file audit (rename-to-example vs move-to-samples).
- **Two images to keep coherent** (Phase C): the slim try-it image + the full deploy image; document that the try-it is headless-only (no panels).

## Process

brainstorm (this) → writing-plans (phased A–E) → subagent-driven execution. Each phase is its own PR(s); the deploy/try-it/bootstrap smokes are maintainer gates.
