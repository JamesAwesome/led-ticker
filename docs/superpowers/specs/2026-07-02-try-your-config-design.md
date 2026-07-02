# `make try` previews YOUR config — design

**Date:** 2026-07-02
**Status:** Approved direction (hobbyist-persona verdict "change the tooling", green-lit by James: "start the make try stuff and include updating the initial walkthru to use it").

## Goal

`make try` prefers the user's `config/config.toml` when it exists (falling back to the bundled example on a fresh clone), so the tutorial — and any config work — runs live in Docker with the browser preview and hot-reload, with **no Python 3.14 / uv install on the laptop**. The tutorial's setup chapter leads with this path.

## Why (the persona evidence)

The hobbyist persona's decisive moment in tutorial ch.1 was the "**Python 3.14+**" prerequisite: *"the moment I see 'install a specific version of Python AND a new package manager,' I start calculating whether this is worth it before I've seen the thing run."* Docker they already have. And a live hot-reloading preview beats re-rendering a GIF per edit. Today `compose.try.yaml` hard-codes `--config /code/config/config.try.example.toml`, so try can never show your own file.

## Verified constraints that shape the design

1. **A user's config won't say `backend = "headless"`** (it's destined for the Pi; the field defaults to `rgbmatrix`). In the slim try image (no rgbmatrix lib), `RgbMatrixBackend.setup()` raises "use [display] backend = headless" — a dead try session. The config must NOT need mutation (it stays deploy-ready), so the override lives outside the file.
2. **The webui sidecar needs a `[web]` block** in the config it reads (without one the display process doesn't publish and the sidecar has nothing to serve). A tutorial-built config won't have one unless the tutorial adds it.
3. **Hot-reload already works for this**: `./config` is bind-mounted into both try services; the engine watches its `--config` file. Playlist/widget edits apply within a cycle; `[display]`-level changes need a container restart (same rule as production — document it).
4. Compose files interpolate host env vars (`${VAR:-default}`), so config selection can be host-side with zero image changes.

## Design

### 1. Core: `--backend` CLI override (new, small, generally useful)

- `led-ticker --config X --backend headless` — a new optional top-level arg on the run mode (`cli.py`). Free string (plugins may register backends); resolved through the existing `get_backend_class` registry at frame build, so an unknown name fails with the registry's clear error.
- Plumb: `run(config_path, backend_override: str | None = None)` (keyword, default None — backward compatible; the headless integration test's `run(cfg)` calls are untouched). `run()` passes it to `build_frame_from_config(config.display, backend_override=...)` (`factories.py:1077`), which uses it instead of `getattr(display, "backend", "rgbmatrix")` when set.
- Hot-reload safety: reload never rebuilds the frame/backend (display-level changes already require restart), so the override naturally persists for the process lifetime.
- Tests: CLI parses the flag; `build_frame_from_config` honors the override over the config field; unknown backend → the existing registry error. Document the flag in `reference/cli.mdx`.

### 2. Try config selection: compose interpolation + setup.sh detection

- `compose.try.yaml`: both services' `command` use `${TRY_CONFIG:-/code/config/config.try.example.toml}`; the **engine** command appends `--backend headless`. (The webui command reads the same config for `[web]`; it does no rendering, no backend flag needed — verify whether `led-ticker webui` even accepts one and leave it alone.)
- `scripts/setup.sh` try mode: if `config/config.toml` exists → `TRY_CONFIG=/code/config/config.toml`, echo `Previewing YOUR config/config.toml (hot-reload: edit and watch the browser update)`; else echo `Using the bundled example — create config/config.toml to preview your own sign, then re-run make try`. Export the var for the `docker compose ... up` call.
- **`[web]` warning**: in the config.toml branch, `grep -q '^\[web\]' config/config.toml` — if absent, print a prominent warning: the live preview needs a `[web]` block; add `[web]` (one line) to config.toml. Don't abort (the engine still runs; the preview is just empty).
- Fresh-clone behavior (`make try` with no config.toml) is byte-identical to today. Update the file-header comment in compose.try.yaml.
- Tests: extend the existing setup.sh test suite (symlink-farm PATH pattern, `tests/` — find the existing setup.sh preflight tests) with try-mode selection: config.toml present → TRY_CONFIG set + "YOUR config" echo; absent → example + hint echo; present-without-[web] → warning line. (Test the SCRIPT's decision/echo, not a real compose up.)

### 3. Tutorial rewrite (the "initial walkthru")

**ch.1 (`tutorial/01-setup.mdx`) — lead with try:**
- Prereqs become: Git, Docker, make. Python 3.14 + uv move to an optional "GIF-capture path" note at the end.
- Flow: clone → `make try` → open `http://localhost:8080` → the live preview shows the bundled example (the HN/nyancat try config — motivation first). Then: "from ch.2 you'll create `config/config.toml`; re-run `make try` and it previews YOUR file, hot-reloading as you edit."
- The "Why not just make try?" note (added in #344) inverts to a "Prefer a GIF file?" note: `make render-demo` still exists for capturing a shareable GIF and needs `make dev` (Python 3.14 + uv) — link, don't lead.
- The "Render the destination config" section: keep showing the Firebird destination, but the primary instruction becomes viewing it in the try preview (`TRY_CONFIG` selection means: before the user has a config.toml, they can preview the destination with a one-line `cp` + revert, OR simpler — keep this one section on render-demo/GIF as the optional path and show the bundled destination GIF that's already embedded). Keep it simple: the embedded demo GIF already shows "done"; don't force either toolchain just to see it.
- Update the chapter description/frontmatter if it mentions "install dev deps".

**ch.2 (`tutorial/02-first-config.mdx`) — the loop:**
- When the user creates `config/config.toml`, include `[web]` in the very first config block (one line + a comment: "lets make try show your sign live in the browser; harmless on the Pi").
- The verify step becomes: `make try` (or if already running: edits hot-reload within a playlist cycle; `[display]` changes need Ctrl-C + re-run). Replace the 2 render-demo invocations with the live-preview loop; keep one "or render a GIF" aside.
- Keep the deliberate-error/validate teaching moment (the persona's "one delight") — validate now framed as: the web UI Config tab validates on save, or `make validate` on a dev machine.

**ch.3–5:** grep for loop phrasing ("render", "preview.gif") and align verbs with the live-preview loop where they occur; no structural change.

**getting-started:** Quickstart A gains one sentence: "Have a `config/config.toml` already? `make try` previews it instead of the example." Choose-your-path table Tutorial row: drop any implied Python prerequisite if present.

### 4. Docs/reference

- `reference/cli.mdx`: document `--backend` on the run command row.
- `compose.try.yaml` header comment + `config/config.try.example.toml` header if it claims try always runs it.
- DOCS-STYLE throughout; prettier on touched MDX.

## Constraints

- Core change is additive (keyword arg + CLI flag); zero behavior change without the flag. The headless integration test and all `run(path)` callers unaffected.
- Fresh-clone `make try` byte-identical. No new image; no Dockerfile.try change.
- The user's config file is never mutated by try.
- Gates: full pytest, ruff check + format, pyright, docs-build + docs-lint. Worktree + PR; STOP at the open green PR (explicit merge approval).
- Live smoke: after implementation, actually run `make try` twice in the worktree (no config.toml → example; then with a minimal config.toml containing [web] → the user config) and confirm the preview serves — the try harness has a history of only breaking under a real compose up.

## Out of scope

Changing `led-ticker webui` CLI; auto-injecting `[web]`; a try-specific brightness/size UI; touching Quickstart B or the Pi deploy path.

## Sizing

Core flag ~20 lines + tests; setup.sh ~15 lines + tests; compose 2 lines; tutorial ch.1 rewrite + ch.2 loop swap + small sweeps. One implementer for core+tooling, one for the tutorial docs (or one for both), + review + a hobbyist re-walk of ch.1–2.
