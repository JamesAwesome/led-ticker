# Flair Transition Pack — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Consolidate the four homage transition packages (`nyancat`/`pokeball`/`pacman`/`sailor_moon`) into one `led-ticker-flair` package with four entry points, so one install brings all four — type strings unchanged.

**Architecture:** One `plugins/flair/` package in the `led-ticker-plugins` monorepo declares four `led_ticker.plugins` entry points (the namespaces stay `nyancat`/`pokeball`/`pacman`/`sailor_moon`). Each family's code moves verbatim into a submodule `led_ticker_flair.<family>`. The engine repo (`led-ticker`) repoints its catalog + example requirements + docs to the single `plugins/flair` source.

**Tech Stack:** Python 3.14, hatchling, uv workspace, pytest (asyncio_mode=auto, `--import-mode=importlib`), the led-ticker plugin entry-point API.

## Two-repo execution

- **Tasks 1–4** run in **`/Users/james/projects/github/jamesawesome/led-ticker-plugins`** (the consolidation). Branch there, e.g. `feat/flair-pack`.
- **Task 5** runs in **`/Users/james/projects/github/jamesawesome/led-ticker`** (catalog/requirements/docs). Branch there, e.g. `feat/flair-catalog-repoint`.
- **Release coupling:** the engine catalog + requirements reference `@flair-v0.1.0`. That tag is created on the **plugins** repo when its PR merges (a release step, by the maintainer). Task 5's *install-resolves* verification can only pass once the tag exists; everything else in Task 5 (string/format/drift correctness) is verifiable immediately. The plan notes this where it matters.

## Global Constraints

- **Bundle the wheel, never the namespace.** Type strings stay byte-for-byte: `nyancat.forward/.reverse/.alternating`, `pokeball.*`, `pacman.*`, `sailor_moon.*`, and `:pokeball.ball:`. NO rename. (Renaming re-creates the deprecated `arcade.*` shape — a hard no.)
- Package name `led-ticker-flair`; distribution dir `plugins/flair/`; import package `led_ticker_flair`; submodules `led_ticker_flair.<family>`.
- Move family code **verbatim** — no internal sprite-trail refactor (YAGNI).
- Plugins import ONLY from `led_ticker.plugin`. No `from __future__ import annotations` (PEP 649 rule). Coverage gate `fail_under = 90`.
- Catalog keeps **four** entries (one per namespace), all pointing at the shared `plugins/flair` source.
- Data plugins (pool/weather/baseball/calendar/rss/crypto) are UNTOUCHED. No border pack.
- Run tests from the relevant repo root: `uv run pytest plugins/flair` (plugins repo) / `PYTHONPATH=tests/stubs uv run pytest <path>` (engine repo). Local git hook is broken in the engine repo — commit with `--no-verify` there.

---

### Task 1: Scaffold `plugins/flair/` and move the nyancat family

**Repo:** `led-ticker-plugins`

**Files:**
- Create: `plugins/flair/pyproject.toml`, `plugins/flair/README.md`, `plugins/flair/CLAUDE.md`, `plugins/flair/src/led_ticker_flair/__init__.py`
- Move: `plugins/nyancat/src/led_ticker_nyancat/` → `plugins/flair/src/led_ticker_flair/nyancat/` (module + `sprites/nyancat.webp`)
- Move: `plugins/nyancat/tests/*` → `plugins/flair/tests/`
- Test: `plugins/flair/tests/test_nyancat.py` (moved), `plugins/flair/tests/test_smoke.py` (new consolidated — Task 3 expands it)

**Interfaces:**
- Produces: a buildable `led-ticker-flair` package whose `nyancat` entry point (`led_ticker_flair.nyancat:register`) registers `nyancat.forward/.reverse/.alternating`. Submodule layout `led_ticker_flair.nyancat.nyancat` (the transition module).

- [ ] **Step 1: Create the package skeleton**

Create `plugins/flair/pyproject.toml` (all four entry points declared now; the other three modules arrive in Task 2):
```toml
[project]
name = "led-ticker-flair"
version = "0.1.0"
description = "Homage sprite-trail transitions for led-ticker: nyancat, pokeball, pacman, sailor_moon (+ :pokeball.ball:)."
readme = "README.md"
requires-python = ">=3.14"
authors = [{ name = "James Awesome", email = "james@morelli.nyc" }]
dependencies = [
    "led-ticker",
]

# Each entry-point NAME is a plugin namespace -> e.g. transition = "nyancat.forward".
# One wheel, four namespaces (the loader iterates entry points, not distributions).
[project.entry-points."led_ticker.plugins"]
nyancat     = "led_ticker_flair.nyancat:register"
pokeball    = "led_ticker_flair.pokeball:register"
pacman      = "led_ticker_flair.pacman:register"
sailor_moon = "led_ticker_flair.sailor_moon:register"

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "pytest-cov>=5.0",
    "pre-commit>=4.0",
    "ruff>=0.4",
    "pyright>=1.1",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/led_ticker_flair"]

[tool.ruff]
target-version = "py314"
src = ["src"]

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM"]

[tool.coverage.report]
fail_under = 90
```

Create `plugins/flair/src/led_ticker_flair/__init__.py`:
```python
"""led-ticker-flair: a pack of homage sprite-trail transitions.

One distribution, four plugin namespaces (each a `led_ticker.plugins` entry
point): nyancat, pokeball, pacman, sailor_moon. The type strings are unchanged
from the former per-family packages, e.g. transition = "nyancat.forward".
"""
```

Create `plugins/flair/README.md` (short: what it provides + the one install line `git+https://github.com/JamesAwesome/led-ticker-plugins.git@flair-v0.1.0#subdirectory=plugins/flair`, and the type strings for each family) and `plugins/flair/CLAUDE.md` (contributor invariants: one wheel / four entry points / namespaces stay as the entry-point names / sprites load via `Path(__file__).parent / "sprites"` so they live beside each family module). Keep both concise; follow the tone of the existing `plugins/nyancat/README.md` and `CLAUDE.md` (read them first).

- [ ] **Step 2: Move the nyancat module + sprite (preserving history)**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker-plugins
mkdir -p plugins/flair/src/led_ticker_flair plugins/flair/tests
git mv plugins/nyancat/src/led_ticker_nyancat plugins/flair/src/led_ticker_flair/nyancat
```
This moves `__init__.py`, `nyancat.py`, and `sprites/nyancat.webp` together. The sprite path code (`Path(__file__).resolve().parent / "sprites" / "nyancat.webp"` in `nyancat.py`) is relative to the module file and needs NO change.

- [ ] **Step 3: Update the nyancat submodule's intra-package imports**

In `plugins/flair/src/led_ticker_flair/nyancat/__init__.py`, change the import from the old package name to the new submodule path:
```python
from led_ticker_flair.nyancat.nyancat import NyanCat, NyanCatAlternating, NyanCatReverse
```
Then grep the moved module for any remaining old-package references and rewrite them:
```bash
grep -rn 'led_ticker_nyancat' plugins/flair/src/led_ticker_flair/nyancat/
```
Expected after the `__init__.py` edit: no matches. (The transition module `nyancat.py` imports only from `led_ticker.plugin` + stdlib, so it needs no change — confirm via the grep.)

- [ ] **Step 4: Move the nyancat tests + fix the stale conftest**

```bash
git mv plugins/nyancat/tests/conftest.py plugins/flair/tests/conftest.py
git mv plugins/nyancat/tests/test_nyancat.py plugins/flair/tests/test_nyancat.py
git mv plugins/nyancat/tests/test_smoke.py plugins/flair/tests/test_smoke.py
git mv plugins/nyancat/tests/test_packaging.py plugins/flair/tests/test_packaging.py
git mv plugins/nyancat/tests/test_import_purity.py plugins/flair/tests/test_import_purity.py
```
- In `plugins/flair/tests/conftest.py`, fix the stale docstring `"""Shared pytest fixtures for led-ticker-arcade tests."""` → `"""Shared pytest fixtures for led-ticker-flair tests."""`.
- In `plugins/flair/tests/test_packaging.py`, update the sprite-presence check to the new import package:
```python
from pathlib import Path

import led_ticker_flair.nyancat


def test_nyancat_sprite_present():
    p = Path(led_ticker_flair.nyancat.__file__).resolve().parent / "sprites" / "nyancat.webp"
    assert p.is_file(), f"missing bundled sprite: {p}"
```
- `test_nyancat.py` tests the transition behavior against the classes; update only its import lines if it imports `led_ticker_nyancat` (grep and rewrite to `led_ticker_flair.nyancat`). `test_smoke.py` and `test_import_purity.py` are reworked in Task 3 — leave them moved-but-unmodified for now (they may fail until Task 3; that's expected and noted there).

- [ ] **Step 5: Verify nyancat builds + registers from flair**

Run:
```bash
cd /Users/james/projects/github/jamesawesome/led-ticker-plugins
uv sync
uv run python -c "
import importlib.metadata as m
eps = [e for e in m.entry_points(group='led_ticker.plugins') if e.name=='nyancat']
print('nyancat ep:', eps)
fn = eps[0].load(); print('register loaded:', fn)
"
uv run pytest plugins/flair/tests/test_nyancat.py plugins/flair/tests/test_packaging.py -q
```
Expected: the `nyancat` entry point resolves to `led_ticker_flair.nyancat:register`; nyancat behavior + sprite-presence tests PASS.

- [ ] **Step 6: Commit**

```bash
git add -A plugins/flair plugins/nyancat
git commit -m "feat(flair): scaffold led-ticker-flair pack + move nyancat family"
```

---

### Task 2: Move pokeball (with emoji), pacman, and sailor_moon

**Repo:** `led-ticker-plugins`

**Files:**
- Move: `plugins/pokeball/src/led_ticker_pokeball/` → `plugins/flair/src/led_ticker_flair/pokeball/` (`__init__.py`, `pokeball.py`, `emoji.py`, `sprites/*.gif`)
- Move: `plugins/pacman/src/led_ticker_pacman/` → `plugins/flair/src/led_ticker_flair/pacman/`
- Move: `plugins/sailor_moon/src/led_ticker_sailor_moon/` → `plugins/flair/src/led_ticker_flair/sailor_moon/`
- Move: each family's `tests/test_<family>.py` (+ pokeball's `test_emoji.py`) into `plugins/flair/tests/`
- Test: the moved per-family tests

**Interfaces:**
- Consumes: the `plugins/flair` skeleton + four declared entry points from Task 1.
- Produces: all four entry points now resolve to real `register` functions; `pokeball.*` transitions + the `pokeball.ball` emoji (lowres + hires) register.

- [ ] **Step 1: Move the three families' source (history-preserving)**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker-plugins
git mv plugins/pokeball/src/led_ticker_pokeball    plugins/flair/src/led_ticker_flair/pokeball
git mv plugins/pacman/src/led_ticker_pacman        plugins/flair/src/led_ticker_flair/pacman
git mv plugins/sailor_moon/src/led_ticker_sailor_moon plugins/flair/src/led_ticker_flair/sailor_moon
```
Sprites move with each module; their `Path(__file__).parent / "sprites"` loading is unchanged.

- [ ] **Step 2: Update each moved family's intra-package imports**

Rewrite the old import-package names to the new submodule paths.

`plugins/flair/src/led_ticker_flair/pokeball/__init__.py`:
```python
from led_ticker_flair.pokeball.emoji import POKEBALL, POKEBALL_HIRES
from led_ticker_flair.pokeball.pokeball import Pokeball, PokeballAlternating, PokeballReverse
```
`plugins/flair/src/led_ticker_flair/pacman/__init__.py`:
```python
from led_ticker_flair.pacman.pacman import Pacman, PacmanAlternating, PacmanReverse
```
`plugins/flair/src/led_ticker_flair/sailor_moon/__init__.py`:
```python
from led_ticker_flair.sailor_moon.sailor_moon import (
    SailorMoon,
    SailorMoonAlternating,
    SailorMoonReverse,
)
```
Then catch any remaining intra-package references inside the moved modules (e.g. `pokeball.py` importing `emoji`):
```bash
grep -rn 'led_ticker_pokeball\|led_ticker_pacman\|led_ticker_sailor_moon' plugins/flair/src/led_ticker_flair/
```
Rewrite every match to the corresponding `led_ticker_flair.<family>...`. Expected after edits: no matches.

- [ ] **Step 3: Move the per-family tests**

```bash
git mv plugins/pokeball/tests/test_pokeball.py plugins/flair/tests/test_pokeball.py
git mv plugins/pokeball/tests/test_emoji.py    plugins/flair/tests/test_emoji.py
git mv plugins/pacman/tests/test_pacman.py     plugins/flair/tests/test_pacman.py
git mv plugins/sailor_moon/tests/test_sailor_moon.py plugins/flair/tests/test_sailor_moon.py
```
In each moved test, grep for the old import package and rewrite to `led_ticker_flair.<family>`:
```bash
grep -rn 'led_ticker_pokeball\|led_ticker_pacman\|led_ticker_sailor_moon' plugins/flair/tests/
```
Rewrite each match. (The other families' `conftest.py` / `test_smoke.py` / `test_import_purity.py` / `test_packaging.py` are duplicates of nyancat's already-moved ones — do NOT move them; they'll be deleted with the old dirs in Task 3. The single consolidated copy under `plugins/flair/tests/` is authoritative.)

- [ ] **Step 4: Verify all four families register + per-family tests pass**

Run:
```bash
cd /Users/james/projects/github/jamesawesome/led-ticker-plugins
uv sync
uv run pytest plugins/flair/tests/test_nyancat.py plugins/flair/tests/test_pokeball.py \
  plugins/flair/tests/test_emoji.py plugins/flair/tests/test_pacman.py \
  plugins/flair/tests/test_sailor_moon.py -q
```
Expected: all per-family behavior + emoji tests PASS.

- [ ] **Step 5: Commit**

```bash
git add -A plugins/flair plugins/pokeball plugins/pacman plugins/sailor_moon
git commit -m "feat(flair): move pokeball (+ emoji), pacman, sailor_moon into the pack"
```

---

### Task 3: Consolidated crux test, delete old dirs, full green

**Repo:** `led-ticker-plugins`

**Files:**
- Modify: `plugins/flair/tests/test_smoke.py` (the all-four-namespaces crux test), `plugins/flair/tests/test_packaging.py` (all four families' sprites), `plugins/flair/tests/test_import_purity.py` (scan the whole `led_ticker_flair` tree)
- Delete: `plugins/nyancat/`, `plugins/pokeball/`, `plugins/pacman/`, `plugins/sailor_moon/` (the now-empty leftovers: each retains only `pyproject.toml`, `README.md`, `CLAUDE.md`, and leftover duplicate test files)

**Interfaces:**
- Consumes: the fully-populated `led_ticker_flair` package from Tasks 1–2.
- Produces: a test proving ONE installed wheel registers all four namespaces + the emoji; the four old distribution dirs removed; `make test` green.

- [ ] **Step 1: Write the consolidated crux smoke test (replace test_smoke.py)**

Replace `plugins/flair/tests/test_smoke.py` with a single test asserting all four namespaces register from the one package (this is the load-bearing "multi-entry-point single wheel" proof):
```python
"""One installed led-ticker-flair wheel registers all four homage namespaces
via four entry points (the crux of the pack consolidation)."""

import pytest
from led_ticker import _plugin_loader as L
from led_ticker.transitions import get_transition_class
from led_ticker.pixel_emoji import EMOJI_REGISTRY, HIRES_REGISTRY

_NAMESPACES = {"nyancat", "pokeball", "pacman", "sailor_moon"}
_TRANSITIONS = [
    f"{fam}.{variant}"
    for fam in _NAMESPACES
    for variant in ("forward", "reverse", "alternating")
]


def test_one_wheel_registers_all_four_namespaces():
    L.reset_plugins()
    try:
        result = L.load_plugins(None, entry_points_enabled=True)
        loaded = {info.namespace for info in result.loaded}
        assert _NAMESPACES <= loaded, f"missing namespaces: {_NAMESPACES - loaded} ({result})"
        for name in _TRANSITIONS:
            assert get_transition_class(name) is not None, f"{name} did not resolve"
    finally:
        L.reset_plugins()


def test_pokeball_emoji_registers():
    L.reset_plugins()
    try:
        L.load_plugins(None, entry_points_enabled=True)
        assert "pokeball.ball" in EMOJI_REGISTRY
        assert "pokeball.ball" in HIRES_REGISTRY
    finally:
        L.reset_plugins()


def test_bogus_name_does_not_resolve():
    L.reset_plugins()
    try:
        L.load_plugins(None, entry_points_enabled=True)
        with pytest.raises(ValueError, match="nyancat.nope"):
            get_transition_class("nyancat.nope")
    finally:
        L.reset_plugins()
```
Verify the emoji-registry import path first: `grep -rn "EMOJI_REGISTRY\|HIRES_REGISTRY" plugins/pokeball/tests/test_emoji.py` (the moved `test_emoji.py`) and mirror whatever symbol/path it already uses to assert the emoji is registered — use that exact mechanism rather than the import above if it differs.

- [ ] **Step 2: Expand the packaging test to all four families' sprites**

Replace `plugins/flair/tests/test_packaging.py` so it asserts every family's bundled sprite ships:
```python
"""Bundled sprite assets must ship with the led-ticker-flair wheel.

Only nyancat and pokeball bundle sprite files; pacman and sailor_moon render
from inline pixel data (no sprites/ dir) and are intentionally not asserted here.
"""

from pathlib import Path

import led_ticker_flair.nyancat
import led_ticker_flair.pokeball


def _sprites(mod) -> Path:
    return Path(mod.__file__).resolve().parent / "sprites"


def test_nyancat_sprite_present():
    assert (_sprites(led_ticker_flair.nyancat) / "nyancat.webp").is_file()


def test_pokeball_sprites_present():
    d = _sprites(led_ticker_flair.pokeball)
    for f in ("pokeball-pikachu.gif", "pokeball.gif", "pikachu-run-transparent.gif"):
        assert (d / f).is_file(), f"missing {f}"
```
(Confirm with `ls plugins/flair/src/led_ticker_flair/*/sprites 2>/dev/null` that only `nyancat` and `pokeball` have a `sprites/` dir before relying on this — the file inventory at plan time showed exactly those two.)

- [ ] **Step 3: Point the import-purity test at the whole flair tree**

In `plugins/flair/tests/test_import_purity.py`, ensure the AST scan walks the entire `plugins/flair/src/led_ticker_flair/` tree (all four submodules), not just one. Read the moved file; if it hardcodes a single package path (e.g. `led_ticker_nyancat`), change it to scan `led_ticker_flair` recursively. The invariant is unchanged: plugin source imports only from `led_ticker.plugin` (or stdlib / its own submodules), never `led_ticker.<internal>`.

- [ ] **Step 4: Delete the four old distribution dirs**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker-plugins
git rm -r plugins/nyancat plugins/pokeball plugins/pacman plugins/sailor_moon
```
(Their `src/`/most `tests/` already moved; this removes the leftover `pyproject.toml`, `README.md`, `CLAUDE.md`, and duplicate `conftest.py`/`test_smoke.py`/`test_import_purity.py`/`test_packaging.py`.) The workspace `members = ["plugins/*"]` glob and the CI `ls -d plugins/*/` matrix both auto-drop them — no list edits.

- [ ] **Step 5: Full monorepo verification**

Run:
```bash
cd /Users/james/projects/github/jamesawesome/led-ticker-plugins
uv sync
uv run ruff check plugins/flair && uv run ruff format --check plugins/flair
uv run pyright plugins/flair/src
uv run pytest plugins/flair --cov=plugins/flair/src --cov-report=term-missing
uv run pytest   # whole workspace (import-mode=importlib); confirms no leftover refs to deleted packages
```
Expected: ruff clean; pyright clean; `plugins/flair` coverage ≥ 90%; the crux test (all four namespaces from one wheel) + emoji + all four families' sprites PASS; whole-workspace collection succeeds with the four old packages gone.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat(flair): consolidated crux test + remove the four old homage dirs"
```

---

### Task 4: Plugins-repo finalization (README/CLAUDE polish + PR)

**Repo:** `led-ticker-plugins`

**Files:**
- Modify: `plugins/flair/README.md`, `plugins/flair/CLAUDE.md` (finalize against the now-complete pack), root `README.md` if it enumerates plugins
- Verify: no stray reference to the old package names anywhere in the repo

- [ ] **Step 1: Sweep for stale references to the old package names**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker-plugins
grep -rn 'led-ticker-nyancat\|led-ticker-pokeball\|led-ticker-pacman\|led-ticker-sailor\|led_ticker_nyancat\|led_ticker_pokeball\|led_ticker_pacman\|led_ticker_sailor_moon' . \
  --include='*.py' --include='*.toml' --include='*.md' | grep -v '/\.git/'
```
Rewrite any remaining doc/config references (READMEs, root docs) to `led-ticker-flair` / `led_ticker_flair.<family>`. Type strings in prose (`nyancat.forward`, etc.) stay as-is — those are unchanged and correct.

- [ ] **Step 2: Final full test + lint**

```bash
uv run pytest plugins/flair --cov=plugins/flair/src
uv run ruff check plugins/flair
```
Expected: green, coverage ≥ 90%.

- [ ] **Step 3: Commit + open the plugins-repo PR**

```bash
git add -A
git commit -m "docs(flair): finalize pack README/CLAUDE; sweep stale package names"
```
Open the PR (branch off the plugins repo's default; do NOT merge without explicit user go-ahead). PR body: one wheel / four entry points / type strings unchanged / four old dirs removed / old tags keep pinned installs working. **Note in the PR that `flair-v0.1.0` must be tagged after merge** so the engine catalog/requirements resolve.

---

### Task 5: Engine repo — catalog, requirements, docs repoint

**Repo:** `led-ticker`

**Files:**
- Modify: `src/led_ticker/plugins_catalog.json` (4 homage entries → shared `plugins/flair` source)
- Modify: `config/requirements-plugins.example.txt` (4 homage git lines → 1 flair line)
- Modify: the docs-site transitions catalog page (grouped "flair pack" section)
- Test: `tests/test_docs_plugin_api_drift.py` and any catalog-consistency test stay green

**Interfaces:**
- Consumes: the `flair-v0.1.0` tag + `plugins/flair` layout produced by Tasks 1–4 (string references; live install-resolution requires the tag to exist).

- [ ] **Step 1: Repoint the four catalog entries to the shared flair source**

In `src/led_ticker/plugins_catalog.json`, for EACH of the four entries (`nyancat`, `pokeball`, `pacman`, `sailor_moon`), keep `name`/`namespace`/`provides` unchanged and replace its `sources[0]` with:
```json
{
  "type": "git",
  "url": "https://github.com/JamesAwesome/led-ticker-plugins",
  "ref": "flair-v0.1.0",
  "subdirectory": "plugins/flair"
}
```
Append `" Part of the led-ticker-flair pack."` to each entry's `summary`, and set each `homepage` to `https://github.com/JamesAwesome/led-ticker-plugins/tree/main/plugins/flair`.

- [ ] **Step 2: Verify the catalog still parses + any catalog test passes**

Run:
```bash
cd /Users/james/projects/github/jamesawesome/led-ticker
PYTHONPATH=tests/stubs uv run python -c "
import json
c = json.load(open('src/led_ticker/plugins_catalog.json'))
fam = [e for e in c['plugins'] if e['namespace'] in {'nyancat','pokeball','pacman','sailor_moon'}]
assert len(fam) == 4
for e in fam:
    s = e['sources'][0]
    assert s['subdirectory'] == 'plugins/flair' and s['ref'] == 'flair-v0.1.0', e['namespace']
print('catalog repoint OK')
"
PYTHONPATH=tests/stubs uv run pytest tests/test_docs_plugin_api_drift.py -q
grep -rn "plugins_catalog\|catalog" tests/ | grep -i 'def test' | head   # discover any catalog test
```
Then run whatever catalog test the grep reveals (e.g. `tests/test_plugins_catalog*.py`) and confirm it passes with the repointed entries. Expected: catalog parses; the four entries share the flair source; existing drift/catalog tests PASS.

- [ ] **Step 3: Collapse the example requirements to one flair line**

In `config/requirements-plugins.example.txt`, replace the four homage blocks (the `nyancat`/`pokeball`/`pacman`/`sailor_moon` git-subdirectory lines + their comment headers) with a single block:
```
# Homage sprite-trail transitions — nyancat / pokeball / pacman / sailor_moon
# (transition = "nyancat.forward" etc.) plus the :pokeball.ball: emoji.
# One install brings all four; the type strings are unchanged.
git+https://github.com/JamesAwesome/led-ticker-plugins.git@flair-v0.1.0#subdirectory=plugins/flair
```
Leave the data-plugin lines (pool/weather/baseball/etc.) untouched.

- [ ] **Step 4: Docs — grouped flair section + migration note**

On the docs-site transitions catalog page (find it: `grep -rln "nyancat\|sprite-trail\|pokeball" docs/site/src/content/docs/`), present the four homage families as a grouped **"Homage transitions (flair pack)"** section: ONE install callout (the single flair requirements line) followed by four individually anchored, searchable sub-entries (nyancat / pokeball / pacman / sailor_moon), each keeping its own type strings + preview. Add a short note: existing configs need no change (type strings unchanged); pinned old-tag requirements keep working; switch to the single flair line at your convenience. Follow `docs/DOCS-STYLE.md` (no padded openers, no "comprehensive/robust/seamlessly", no release-history framing, no gun metaphors). Then:
```bash
make docs-build && make docs-lint
```
Expected: build succeeds; docs-lint 0 errors.

- [ ] **Step 5: Full engine suite + commit + PR**

```bash
PYTHONPATH=tests/stubs uv run pytest -q
uv run --extra dev ruff check src/ tests/
git add -A
git commit --no-verify -m "feat(catalog): repoint homage transitions to the led-ticker-flair pack"
```
Open the engine PR (branch off main; do NOT merge without explicit user go-ahead). PR body: catalog four entries → shared flair source; requirements 4 lines → 1; docs grouped; type strings + migration hints unchanged. **Note the merge ordering:** the plugins-repo PR merges + `flair-v0.1.0` is tagged FIRST; then this PR's `@flair-v0.1.0` install actually resolves.

---

## Final verification (before merging either PR)

- [ ] **End-to-end install (after `flair-v0.1.0` exists):** in a scratch venv, `pip install "git+https://github.com/JamesAwesome/led-ticker-plugins.git@flair-v0.1.0#subdirectory=plugins/flair"`, then confirm `nyancat.forward`, `pokeball.alternating`, `pacman.reverse`, `sailor_moon.forward`, and `:pokeball.ball:` all resolve in a running led-ticker. This proves the one-wheel-four-namespaces install path on real packaging, not just the source tree.

## Self-Review notes (spec coverage)

- Spec §A (one package, four entry points, verbatim move, pokeball emoji, sprite package-data) → Tasks 1–3.
- Spec §B (workspace glob + CI glob auto-adapt, delete old dirs, `flair-v0.1.0` tag) → Task 3 Step 4 (delete) + Task 4 (tag note; the tag itself is a maintainer release step post-merge).
- Spec §C (catalog 4 entries shared source, requirements 4→1, docs grouping, no resolution-path change) → Task 5.
- Spec Testing (multi-entry-point crux, sprite packaging, import purity, per-family, engine catalog drift) → Task 3 (crux/packaging/purity) + Task 2 (per-family) + Task 5 (catalog drift) + Final verification (real-install end-to-end).
- Spec Non-goals (no rename, no border pack, data plugins untouched) → enforced by omission + Global Constraints.
- Spec Risks (multi-entry-point must work end-to-end; sprite inclusion; pinned-tag back-compat; CI lockstep) → Task 3 Step 5 (workspace build/register) + Task 3 Step 2 (sprites) + the immutable-tag note (Task 4) + the glob-based CI (no lockstep edit needed, noted in Task 3 Step 4).
