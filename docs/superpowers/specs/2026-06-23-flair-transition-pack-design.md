# Design: consolidate the homage transitions into one `led-ticker-flair` pack

**Date:** 2026-06-23
**Status:** Approved for planning
**Repos:** `led-ticker-plugins` (the consolidation) + `led-ticker` (catalog / requirements / docs repoint)

## Motivation

The four "homage" / sprite-trail transition families — `nyancat`, `pokeball`, `pacman`, `sailor_moon` — currently ship as four separate packages in the `led-ticker-plugins` monorepo, each installed on its own (four `git+…#subdirectory=` lines). A maker who wants "the fun transitions" pays four-line install friction and tracks four versions for a set of cosmetic sprites that change together.

This consolidates them into one installable package, **`led-ticker-flair`**, so a single install/requirements line brings all four. `flair` (not `arcade`) leaves room for future non-arcade homages.

A PM + principal-engineer + UX-engineer panel reviewed the idea; the load-bearing conclusion:

> **Bundle the distribution, never the namespace.** A single wheel can declare multiple entry points, so one package registers all four namespaces with the **type strings unchanged** (`nyancat.forward`, `pokeball.alternating`, `:pokeball.ball:`, …). Renaming into a single `flair.*`/`arcade.*` namespace would re-create the exact `arcade.*` shape the project just deprecated (the `_TRANSITION_MIGRATION` map still carries those keys) and owe users a third migration — for zero benefit.

The panel also unanimously rejected a "border pack" (copying `lightbulbs` drifts; moving it breaks configs and violates the dependency-based core/plugin line). **Borders are out of scope here.**

## Decisions (panel + brainstorm)

- **One package, four entry points, namespaces unchanged.** `led-ticker-flair` declares `nyancat` / `pokeball` / `pacman` / `sailor_moon` entry points in the `led_ticker.plugins` group. The loader iterates entry points (not distributions) and `PluginAPI` prefixes by entry-point name, so all four namespaces register from the one wheel with identical type strings.
- **Move family code verbatim** into submodules `led_ticker_flair.<family>` — co-locate only, no internal sprite-trail refactor.
- **Catalog keeps four entries**, all repointed to the shared `plugins/flair` source (per the catalog-shape decision) — preserves per-family search and the namespace-keyed install hint.
- **Delete the four old `plugins/<name>/` dirs on `main`.** Old per-family git tags (`nyancat-v0.1.0`, …) stay immutable, so existing *pinned* requirements keep resolving off history — no immediate breakage. New tag `flair-v0.1.0`.
- **No config migration** (type strings unchanged) and **no engine transition-resolution change** (the existing `arcade.*` / bare-name migration hints stay as-is).
- **Data plugins (pool / weather / baseball / calendar / rss / crypto) are untouched** — they version independently against external surfaces.

## Architecture

### A. The `led-ticker-flair` package (`led-ticker-plugins/plugins/flair/`)

Replaces `plugins/{nyancat,pokeball,pacman,sailor_moon}/`.

```
plugins/flair/
  pyproject.toml            # name = "led-ticker-flair", version = "0.1.0", 4 entry points
  README.md                 # the pack: what it provides + install line
  CLAUDE.md                 # contributor invariants for the pack
  src/led_ticker_flair/
    __init__.py             # package marker (no top-level register)
    nyancat/__init__.py     # register(api) → transitions; nyancat.py + sprites/nyancat.webp
    pokeball/__init__.py     # register(api) → transitions + api.emoji/hires_emoji("ball", …)
    pacman/__init__.py
    sailor_moon/__init__.py
  tests/                    # consolidated smoke / import-purity / packaging / per-family tests
```

`pyproject.toml` entry points (namespaces are the entry-point NAMES — unchanged):

```toml
[project.entry-points."led_ticker.plugins"]
nyancat     = "led_ticker_flair.nyancat:register"
pokeball    = "led_ticker_flair.pokeball:register"
pacman      = "led_ticker_flair.pacman:register"
sailor_moon = "led_ticker_flair.sailor_moon:register"
```

- Each family's existing `register(api)` (e.g. `api.transition("forward")(NyanCat)` …) and transition classes move **verbatim** into the submodule. Imports update from `led_ticker_<family>` → `led_ticker_flair.<family>`. Sprites move to `src/led_ticker_flair/<family>/sprites/`.
- **Pokeball preserves** `api.emoji("ball", POKEBALL)` + `api.hires_emoji("ball", POKEBALL_HIRES)` → `:pokeball.ball:` unchanged.
- `dependencies` = the union of the four packages' deps (all currently depend on `led-ticker`; identical sets — verify and union). `[tool.hatch.build.targets.wheel] packages = ["src/led_ticker_flair"]`. Ruff / coverage config mirrors the existing per-plugin convention.
- **Package data:** ensure the `.webp` sprites are included in the wheel (hatchling includes package data under the wheel package by default; the packaging test asserts the sprites load post-install).

### B. Monorepo workspace + release (`led-ticker-plugins`)

- Update the root uv-workspace member list: remove the four, add `plugins/flair`.
- Root pytest config already uses `--import-mode=importlib` (needed since multiple members share test basenames) — confirm the consolidated `tests/` still collects cleanly.
- **Delete** `plugins/{nyancat,pokeball,pacman,sailor_moon}/`.
- New annotated tag **`flair-v0.1.0`** at the consolidation commit. The per-plugin publish/CI workflow gains a `flair` target (or the existing matrix drops the four and adds `flair`).

### C. Engine repo repoint (`led-ticker`)

- **`src/led_ticker/plugins_catalog.json`** — keep the four entries (`nyancat`/`pokeball`/`pacman`/`sailor_moon`, each with its own `namespace` + `provides`), repoint every `sources[0]` to:
  ```json
  { "type": "git", "url": "https://github.com/JamesAwesome/led-ticker-plugins",
    "ref": "flair-v0.1.0", "subdirectory": "plugins/flair" }
  ```
  Append "Part of the led-ticker-flair pack." to each `summary`. `homepage` → `…/tree/main/plugins/flair`.
- **`config/requirements-plugins.example.txt`** — replace the four homage git lines with one:
  ```
  # Homage sprite-trail transitions (nyancat/pokeball/pacman/sailor_moon) + :pokeball.ball:
  git+https://github.com/JamesAwesome/led-ticker-plugins.git@flair-v0.1.0#subdirectory=plugins/flair
  ```
- **Docs site** — on the transitions catalog page, a grouped **"Homage transitions (flair pack)"** section: one install callout + four individually anchored, searchable entries (per the UX call). Update any example configs / install snippets that referenced the four separate lines. A short note: pinned old-tag requirements keep working; switch to the one flair line at your convenience.
- **No change** to `transitions/__init__.py` migration hints or the resolution path (type strings unchanged).

## Install / data flow

```
New user:  requirements-plugins.txt → 1 git line (@flair-v0.1.0 #subdirectory=plugins/flair)
              → pip installs led-ticker-flair (one wheel)
              → 4 entry points → loader registers nyancat.* / pokeball.* / pacman.* / sailor_moon.* (+ :pokeball.ball:)
              → existing `transition = "nyancat.forward"` configs resolve unchanged
Existing user (pinned old tags): unchanged — old tags + subdirs still exist in git history; resolves as before.
Catalog / store / install-hint: 4 namespace entries → all map to the single led-ticker-flair source.
```

## Testing

- **Multi-entry-point registration (the crux):** a packaging/smoke test that, against the installed/buildable `led-ticker-flair`, asserts **all four entry points are discovered and each `register(api)` runs**, producing all 12 transition types (`<family>.{forward,reverse,alternating}`) and the `pokeball.ball` emoji (+ hires). This proves one wheel → four namespaces.
- **Sprite packaging:** assert each family's `.webp` resolves from the installed package (not just the source tree).
- **Import purity:** the monorepo's AST import-purity convention applied to the consolidated package (plugins import only from `led_ticker.plugin`; no `from __future__ import annotations`).
- **Per-family behavior:** the existing per-family transition tests move into `plugins/flair/tests/` and keep passing (the transitions themselves are unchanged).
- **Engine side:** the catalog drift test (`tests/test_docs_plugin_api_drift.py` / any catalog-vs-docs check) stays green after the repoint; a check that the four catalog entries now share the `plugins/flair` source.

## Scope / non-goals

- **IN:** the `led-ticker-flair` package (4 entry points, verbatim family code, pokeball emoji); delete the 4 old dirs; `flair-v0.1.0` tag + workspace/CI update; engine catalog repoint (4 entries, shared source); one-line requirements example; docs grouping + migration note.
- **OUT:** any namespace/type-string rename (panel hard rule); a border pack or moving/copying core borders (panel unanimous no); internal sprite-trail refactor; touching the data plugins; PyPI publication (these stay git-subdirectory installs, matching today).

## Risks

- **The multi-entry-point-from-one-wheel mechanism must actually work end-to-end** (build → install → all four entry points discovered). This is the load-bearing assumption; the packaging test is written first and proves it before the old dirs are deleted.
- **Sprite package-data inclusion** — a wheel that omits the `.webp`s would fail only at runtime; the packaging test loads them from the installed package to catch it.
- **Pinned-tag back-compat** depends on the old tags + their `plugins/<name>/` trees remaining in git history (they do — tags are immutable). Deleting the dirs on `main` does not rewrite history.
- **CI/publish workflow** in the monorepo must be updated in lockstep with the dir deletion, or the release job references missing members.
