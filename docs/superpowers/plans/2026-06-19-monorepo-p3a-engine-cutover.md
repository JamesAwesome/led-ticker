# Monorepo P3a — Engine Cutover (catalog + requirements + migration hints) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the `led-ticker-plugins` monorepo the authoritative install source in the **engine repo** (`led-ticker`): repoint the plugin catalog at the monorepo subdirectories with namespaced-tag pins, split the `feeds`/`arcade` catalog entries into the 10 final packages, update the example requirements file, and refresh the bare-name migration hints + `CLAUDE.md` to the new names.

**Architecture:** The catalog (`plugins_catalog.py` schema + `plugins_catalog.json` data) is the load-bearing piece — `led-ticker plugin install/add <ns>` builds its pip requirement from it. Add an optional `subdirectory` field to `CatalogSource` (so one repo URL can serve 10 packages) and have `requirement()` append pip's `#subdirectory=` fragment. Then rewrite the bundled catalog to 10 monorepo entries, update the example requirements file, refresh the `arcade.*` transition migration hints to the new `<family>.<variant>` names, and update `CLAUDE.md`. Pure data/text/small-code changes — no change to Docker, `deploy/install.sh`, the constraint install, or the `led_ticker.plugin` API.

**Tech Stack:** Python 3.14, attrs, stdlib json, pytest, ruff.

**Scope:** P3a is the **functional cutover only**. The ~19 docs-site pages (P3b) and the irreversible archival of the 6 old plugin repos with README redirects (P3c) are SEPARATE plans — archival especially must be its own consent-gated step, and it must land only AFTER this catalog cutover so nothing breaks in the interim. See `docs/superpowers/specs/2026-06-19-led-ticker-plugins-monorepo-design.md` (in led-ticker-plugins).

**Working repo:** `/Users/james/projects/github/jamesawesome/led-ticker` (the ENGINE repo — different from P1/P2). Create branch `feat/monorepo-p3a-engine-cutover` off `main`. All work on that branch, never `main`. Run `make dev` first if the venv isn't set up.

**The 10 packages (catalog target), with their cut tags:**
| package | provides (referenceable types) | tag | summary note |
|---|---|---|---|
| pool | `pool.monitor` | `pool-v0.1.0` | pool water-temp (InfluxDB v2) |
| baseball | `baseball.scores/standings/promotions/statcast/attendance` | `baseball-v0.1.0` | + `baseball.roll*` transitions + `:baseball.ball:` (in summary) |
| crypto | `crypto.coingecko` | `crypto-v0.1.0` | CoinGecko price ticker |
| calendar | `calendar.events` | `calendar-v0.1.0` | .ics agenda/next/two_row |
| rss | `rss.feed` | `rss-v0.2.0` | RSS/Atom headlines |
| weather | `weather.current` | `weather-v0.2.0` | current conditions (WeatherAPI.com) |
| nyancat | `nyancat.forward/reverse/alternating` | `nyancat-v0.1.0` | hi-res sprite-trail |
| pokeball | `pokeball.forward/reverse/alternating` | `pokeball-v0.1.0` | + `:pokeball.ball:` emoji (in summary) |
| pacman | `pacman.forward/reverse/alternating` | `pacman-v0.1.0` | sprite-trail (no hi-res) |
| sailor_moon | `sailor_moon.forward/reverse/alternating` | `sailor_moon-v0.1.0` | sprite-trail (no hi-res) |

All 10 share one repo URL `https://github.com/JamesAwesome/led-ticker-plugins` with `subdirectory = "plugins/<name>"`.

---

## File structure

- Modify: `src/led_ticker/plugins_catalog.py` — add `subdirectory` to `CatalogSource`; `requirement()` emits `#subdirectory=`; bump `SCHEMA_VERSION` to 2.
- Modify: `src/led_ticker/plugins_catalog.json` — rewrite to 10 monorepo entries, `schema_version: 2`.
- Modify: `tests/test_plugins/test_catalog.py` — schema 2; new first-party name set; subdirectory in `requirement()`; monorepo url assertions.
- Modify: `config/requirements-plugins.example.txt` — monorepo subdirectory URLs for all 10 packages.
- Modify: `src/led_ticker/transitions/__init__.py` — `_arcade_migration` → per-family `<family>.<variant>` hints pointing at the split packages.
- Modify: `tests/test_transition_migration.py` (+ any other test asserting the old hint text) — expect the new names.
- Modify: `CLAUDE.md` — Plugin ecosystem section + the inline plugin-list paragraph + the sprite-trail/feeds invariant mentions → monorepo + new names.

---

### Task 1: Catalog schema — add `subdirectory`, emit `#subdirectory=`, bump to v2

**Files:**
- Modify: `src/led_ticker/plugins_catalog.py`
- Modify: `tests/test_plugins/test_catalog.py`

- [ ] **Step 1: Branch + failing test for subdirectory in `requirement()`**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker
git checkout main && git pull --ff-only origin main
git checkout -b feat/monorepo-p3a-engine-cutover
git branch --show-current   # MUST be feat/monorepo-p3a-engine-cutover — if main, STOP
```
Add to `tests/test_plugins/test_catalog.py`:
```python
def test_requirement_git_with_subdirectory():
    from led_ticker.plugins_catalog import CatalogEntry, CatalogSource

    e = CatalogEntry(
        name="rss",
        namespace="rss",
        summary="RSS/Atom headlines.",
        homepage="https://github.com/JamesAwesome/led-ticker-plugins",
        provides=("rss.feed",),
        sources=(
            CatalogSource(
                type="git",
                url="https://github.com/JamesAwesome/led-ticker-plugins",
                ref="rss-v0.2.0",
                subdirectory="plugins/rss",
            ),
        ),
    )
    assert e.requirement() == (
        "git+https://github.com/JamesAwesome/led-ticker-plugins.git"
        "@rss-v0.2.0#subdirectory=plugins/rss"
    )
    # unpinned still carries the subdirectory, falling back to @main
    assert e.requirement(pinned=False) == (
        "git+https://github.com/JamesAwesome/led-ticker-plugins.git"
        "@main#subdirectory=plugins/rss"
    )
```

- [ ] **Step 2: Run it — fails (CatalogSource has no `subdirectory`)**

```bash
uv run pytest tests/test_plugins/test_catalog.py::test_requirement_git_with_subdirectory -x
```
Expected: FAIL (`TypeError: __init__() got an unexpected keyword argument 'subdirectory'`).

- [ ] **Step 3: Add the field + emit the fragment + bump schema**

In `src/led_ticker/plugins_catalog.py`:
1. Bump `SCHEMA_VERSION = 2`.
2. Add to `CatalogSource` (after `ref`):
```python
    subdirectory: str | None = None  # git — package path within a monorepo
```
3. In `requirement()`, the git branch becomes:
```python
        if src.type == "git":
            assert src.url is not None  # guaranteed for git sources (see _parse_source)
            base = src.url.removesuffix(".git")
            ref = src.ref if (pinned and src.ref) else "main"
            req = f"git+{base}.git@{ref}"
            if src.subdirectory:
                req += f"#subdirectory={src.subdirectory}"
            return req
```
4. Find `_parse_source` (the JSON→`CatalogSource` parser) and pass `subdirectory=raw.get("subdirectory")` for git sources, mirroring how `url`/`ref` are read.
5. If `SCHEMA_VERSION` is validated on load (e.g. `assert data["schema_version"] == SCHEMA_VERSION`), the bump to 2 is consistent with the JSON change in Task 2.

- [ ] **Step 4: Run the new test + the existing requirement tests**

```bash
uv run pytest tests/test_plugins/test_catalog.py -k requirement -v
```
Expected: the new subdirectory test PASSES; the existing `test_requirement_git_pinned_uses_ref` / `_unpinned_uses_main` / `_already_dot_git_not_doubled` / pypi tests still PASS (they construct sources without `subdirectory`, which defaults to None → no fragment).

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/plugins_catalog.py tests/test_plugins/test_catalog.py
git commit -m "feat(catalog): add subdirectory source field + emit #subdirectory= (schema v2)"
```

---

### Task 2: Catalog data — rewrite to 10 monorepo entries

**Files:**
- Modify: `src/led_ticker/plugins_catalog.json`
- Modify: `tests/test_plugins/test_catalog.py`

- [ ] **Step 1: Replace `plugins_catalog.json` with the 10-entry monorepo catalog**

Overwrite `src/led_ticker/plugins_catalog.json`:
```json
{
  "schema_version": 2,
  "plugins": [
    {
      "name": "pool",
      "namespace": "pool",
      "summary": "Pool water temperature from InfluxDB v2 (ticker / two_row layouts).",
      "homepage": "https://github.com/JamesAwesome/led-ticker-plugins/tree/main/plugins/pool",
      "provides": ["pool.monitor"],
      "sources": [
        { "type": "git", "url": "https://github.com/JamesAwesome/led-ticker-plugins", "ref": "pool-v0.1.0", "subdirectory": "plugins/pool" }
      ]
    },
    {
      "name": "baseball",
      "namespace": "baseball",
      "summary": "MLB scores, standings, promotions, statcast & attendance widgets, baseball.roll* transitions, and the :baseball.ball: emoji.",
      "homepage": "https://github.com/JamesAwesome/led-ticker-plugins/tree/main/plugins/baseball",
      "provides": ["baseball.scores", "baseball.standings", "baseball.promotions", "baseball.statcast", "baseball.attendance"],
      "sources": [
        { "type": "git", "url": "https://github.com/JamesAwesome/led-ticker-plugins", "ref": "baseball-v0.1.0", "subdirectory": "plugins/baseball" }
      ]
    },
    {
      "name": "crypto",
      "namespace": "crypto",
      "summary": "CoinGecko cryptocurrency price ticker.",
      "homepage": "https://github.com/JamesAwesome/led-ticker-plugins/tree/main/plugins/crypto",
      "provides": ["crypto.coingecko"],
      "sources": [
        { "type": "git", "url": "https://github.com/JamesAwesome/led-ticker-plugins", "ref": "crypto-v0.1.0", "subdirectory": "plugins/crypto" }
      ]
    },
    {
      "name": "calendar",
      "namespace": "calendar",
      "summary": "Calendar (.ics) agenda/next/two_row widget.",
      "homepage": "https://github.com/JamesAwesome/led-ticker-plugins/tree/main/plugins/calendar",
      "provides": ["calendar.events"],
      "sources": [
        { "type": "git", "url": "https://github.com/JamesAwesome/led-ticker-plugins", "ref": "calendar-v0.1.0", "subdirectory": "plugins/calendar" }
      ]
    },
    {
      "name": "rss",
      "namespace": "rss",
      "summary": "RSS/Atom feed headlines (rss.feed).",
      "homepage": "https://github.com/JamesAwesome/led-ticker-plugins/tree/main/plugins/rss",
      "provides": ["rss.feed"],
      "sources": [
        { "type": "git", "url": "https://github.com/JamesAwesome/led-ticker-plugins", "ref": "rss-v0.2.0", "subdirectory": "plugins/rss" }
      ]
    },
    {
      "name": "weather",
      "namespace": "weather",
      "summary": "Current-conditions weather widget using WeatherAPI.com (weather.current).",
      "homepage": "https://github.com/JamesAwesome/led-ticker-plugins/tree/main/plugins/weather",
      "provides": ["weather.current"],
      "sources": [
        { "type": "git", "url": "https://github.com/JamesAwesome/led-ticker-plugins", "ref": "weather-v0.2.0", "subdirectory": "plugins/weather" }
      ]
    },
    {
      "name": "nyancat",
      "namespace": "nyancat",
      "summary": "Nyan Cat sprite-trail transitions (nyancat.forward/.reverse/.alternating; hi-res).",
      "homepage": "https://github.com/JamesAwesome/led-ticker-plugins/tree/main/plugins/nyancat",
      "provides": ["nyancat.forward", "nyancat.reverse", "nyancat.alternating"],
      "sources": [
        { "type": "git", "url": "https://github.com/JamesAwesome/led-ticker-plugins", "ref": "nyancat-v0.1.0", "subdirectory": "plugins/nyancat" }
      ]
    },
    {
      "name": "pokeball",
      "namespace": "pokeball",
      "summary": "Pokeball/Pikachu sprite-trail transitions (pokeball.forward/.reverse/.alternating; hi-res) and the :pokeball.ball: emoji.",
      "homepage": "https://github.com/JamesAwesome/led-ticker-plugins/tree/main/plugins/pokeball",
      "provides": ["pokeball.forward", "pokeball.reverse", "pokeball.alternating"],
      "sources": [
        { "type": "git", "url": "https://github.com/JamesAwesome/led-ticker-plugins", "ref": "pokeball-v0.1.0", "subdirectory": "plugins/pokeball" }
      ]
    },
    {
      "name": "pacman",
      "namespace": "pacman",
      "summary": "Pac-Man sprite-trail transitions (pacman.forward/.reverse/.alternating).",
      "homepage": "https://github.com/JamesAwesome/led-ticker-plugins/tree/main/plugins/pacman",
      "provides": ["pacman.forward", "pacman.reverse", "pacman.alternating"],
      "sources": [
        { "type": "git", "url": "https://github.com/JamesAwesome/led-ticker-plugins", "ref": "pacman-v0.1.0", "subdirectory": "plugins/pacman" }
      ]
    },
    {
      "name": "sailor_moon",
      "namespace": "sailor_moon",
      "summary": "Sailor Moon sprite-trail transitions (sailor_moon.forward/.reverse/.alternating).",
      "homepage": "https://github.com/JamesAwesome/led-ticker-plugins/tree/main/plugins/sailor_moon",
      "provides": ["sailor_moon.forward", "sailor_moon.reverse", "sailor_moon.alternating"],
      "sources": [
        { "type": "git", "url": "https://github.com/JamesAwesome/led-ticker-plugins", "ref": "sailor_moon-v0.1.0", "subdirectory": "plugins/sailor_moon" }
      ]
    }
  ]
}
```

- [ ] **Step 2: Update the bundled-catalog tests for the new shape**

In `tests/test_plugins/test_catalog.py`:
1. `test_bundled_catalog_loads_and_is_v1` → rename to `..._is_v2` and assert `cat` loads (if it checks `SCHEMA_VERSION`, it's now 2).
2. `test_bundled_catalog_has_the_first_party_plugins`: replace the assertion with the full 10:
```python
def test_bundled_catalog_has_the_first_party_plugins():
    cat = load_catalog()
    names = {e.name for e in cat.entries}
    assert names == {
        "pool", "baseball", "crypto", "calendar", "rss", "weather",
        "nyancat", "pokeball", "pacman", "sailor_moon",
    }
    # the split is done — no monolithic feeds/arcade entries remain
    assert "feeds" not in names and "arcade" not in names
```
3. Add an assertion that every bundled git source points at the monorepo with a subdirectory + tag ref:
```python
def test_bundled_entries_install_from_the_monorepo():
    cat = load_catalog()
    for e in cat.entries:
        src = e.sources[0]
        assert src.url == "https://github.com/JamesAwesome/led-ticker-plugins"
        assert src.subdirectory == f"plugins/{e.name}"
        assert src.ref and src.ref.startswith(f"{e.name}-v")
        # the emitted requirement carries the subdirectory fragment
        assert e.requirement().endswith(f"#subdirectory=plugins/{e.name}")
```
4. Add provides assertions for the split families (mirroring `test_pool_provides_monitor`):
```python
def test_split_families_provide_their_types():
    cat = load_catalog()
    assert cat.get("rss").provides == ("rss.feed",)
    assert cat.get("weather").provides == ("weather.current",)
    for fam in ("nyancat", "pokeball", "pacman", "sailor_moon"):
        assert set(cat.get(fam).provides) == {
            f"{fam}.forward", f"{fam}.reverse", f"{fam}.alternating"
        }
```
5. Keep `test_baseball_provides_all_current_widgets` (baseball provides unchanged) and the search tests; if `test_search_*` referenced `arcade`/`feeds` names, update them to the new names. Run the search tests and fix any that assumed the old names.

- [ ] **Step 3: Run the full catalog test file + JSON validity**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker
uv run python -c "import json; json.load(open('src/led_ticker/plugins_catalog.json')); print('json ok')"
uv run pytest tests/test_plugins/test_catalog.py -v
```
Expected: JSON valid; all catalog tests PASS.

- [ ] **Step 4: Smoke the install-line generation end to end**

```bash
uv run python -c "
from led_ticker.plugins_catalog import load_catalog
cat = load_catalog()
for n in ('weather','nyancat','baseball'):
    print(n, '->', cat.get(n).requirement())
"
```
Expected (examples):
`weather -> git+https://github.com/JamesAwesome/led-ticker-plugins.git@weather-v0.2.0#subdirectory=plugins/weather`
`nyancat -> ...@nyancat-v0.1.0#subdirectory=plugins/nyancat`

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/plugins_catalog.json tests/test_plugins/test_catalog.py
git commit -m "feat(catalog): repoint all 10 first-party plugins at the monorepo (feeds/arcade split into final entries)"
```

---

### Task 3: Rewrite the example requirements file

**Files:**
- Modify: `config/requirements-plugins.example.txt`

- [ ] **Step 1: Replace the plugin lines with monorepo subdirectory installs**

Keep the existing header comments (the deploy notes about pinning / gitignored per-sign files are still accurate). Replace the per-plugin install lines (everything from the first `# Pool ...` block down) with:
```
# Each line installs ONE plugin from the led-ticker-plugins monorepo via pip's
# git "#subdirectory=" fragment. Pin to the plugin's namespaced tag for prod
# (shown); use @main for the latest. Delete the lines for plugins you don't use.

# Pool water-temperature widget (type = "pool.monitor"):
git+https://github.com/JamesAwesome/led-ticker-plugins.git@pool-v0.1.0#subdirectory=plugins/pool

# Baseball / MLB widgets (baseball.scores / .standings / .promotions / .statcast
# / .attendance), the baseball.roll* transitions, and the :baseball.ball: emoji:
git+https://github.com/JamesAwesome/led-ticker-plugins.git@baseball-v0.1.0#subdirectory=plugins/baseball

# CoinGecko crypto price ticker (type = "crypto.coingecko"):
git+https://github.com/JamesAwesome/led-ticker-plugins.git@crypto-v0.1.0#subdirectory=plugins/crypto

# Calendar (.ics) agenda/next/two_row widget (type = "calendar.events"):
git+https://github.com/JamesAwesome/led-ticker-plugins.git@calendar-v0.1.0#subdirectory=plugins/calendar

# RSS/Atom feed headlines (type = "rss.feed"):
git+https://github.com/JamesAwesome/led-ticker-plugins.git@rss-v0.2.0#subdirectory=plugins/rss

# Current-conditions weather, WeatherAPI.com (type = "weather.current"):
git+https://github.com/JamesAwesome/led-ticker-plugins.git@weather-v0.2.0#subdirectory=plugins/weather

# Nyan Cat sprite-trail transitions (transition = "nyancat.forward" / ".reverse" / ".alternating"):
git+https://github.com/JamesAwesome/led-ticker-plugins.git@nyancat-v0.1.0#subdirectory=plugins/nyancat

# Pokeball/Pikachu sprite-trail transitions (transition = "pokeball.forward" etc.) + :pokeball.ball: emoji:
git+https://github.com/JamesAwesome/led-ticker-plugins.git@pokeball-v0.1.0#subdirectory=plugins/pokeball

# Pac-Man sprite-trail transitions (transition = "pacman.forward" etc.):
git+https://github.com/JamesAwesome/led-ticker-plugins.git@pacman-v0.1.0#subdirectory=plugins/pacman

# Sailor Moon sprite-trail transitions (transition = "sailor_moon.forward" etc.):
git+https://github.com/JamesAwesome/led-ticker-plugins.git@sailor_moon-v0.1.0#subdirectory=plugins/sailor_moon
```

- [ ] **Step 2: Verify no test asserts the old example content + commit**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker
grep -rln 'requirements-plugins.example' tests/ || echo "no test references the example file"
git add config/requirements-plugins.example.txt
git commit -m "docs(deploy): example requirements install all 10 plugins from the monorepo"
```
(If a test DOES assert the example content, update it to the new lines.)

---

### Task 4: Update bare-name migration hints + CLAUDE.md

**Files:**
- Modify: `src/led_ticker/transitions/__init__.py`
- Modify: `tests/test_transition_migration.py` (+ any other test asserting the hint text)
- Modify: `CLAUDE.md`

- [ ] **Step 1: Refresh the arcade transition migration hints to the new names**

In `src/led_ticker/transitions/__init__.py`, the bare-name → hint map currently maps e.g. `nyancat` / `nyancat_reverse` → suggests `arcade.nyancat*` + "install led-ticker-arcade". Update so each bare name maps to its NEW split type + the right package. Replace `_arcade_migration` + the `_ARCADE_TRANSITIONS` builder:
```python
# bare family name (+ _reverse/_alternating suffix) -> (new namespaced type, plugin)
_SPRITE_VARIANT = {"": "forward", "_reverse": "reverse", "_alternating": "alternating"}
_SPRITE_FAMILIES = ("pacman", "sailor_moon", "nyancat", "pokeball")


def _sprite_migration(family: str, suffix: str) -> tuple[str, str]:
    new = f"{family}.{_SPRITE_VARIANT[suffix]}"
    return (
        f"Transition {family + suffix!r} was extracted from led-ticker core; it "
        f"now ships in the led-ticker-plugins monorepo as {new!r}.",
        f"Install the {family!r} plugin (add "
        f"`git+https://github.com/JamesAwesome/led-ticker-plugins.git"
        f"@{family}-v0.1.0#subdirectory=plugins/{family}` to "
        f"config/requirements-plugins.txt) and use transition = {new!r}.",
    )


_TRANSITION_MIGRATION: dict[str, tuple[str, str]] = {
    f"{family}{suffix}": _sprite_migration(family, suffix)
    for family in _SPRITE_FAMILIES
    for suffix in _SPRITE_VARIANT
}
```
(This keeps the same keys — bare `nyancat`, `nyancat_reverse`, `nyancat_alternating`, … — so a user's stale bare config still gets a hint, now pointing at the new name + monorepo install.)

- [ ] **Step 2: Update the migration tests**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker
uv run pytest tests/test_transition_migration.py -v
```
For each failing assertion, update the expected text to the new hint (new type name like `nyancat.forward`, "led-ticker-plugins monorepo", the `#subdirectory=` install line). Do NOT weaken assertions — match the real new message. Re-run until green. Also run `tests/test_transitions_registry.py` and `tests/test_plugin_hint.py` and fix any that asserted the old arcade hint text.

- [ ] **Step 3: Update `CLAUDE.md`**

Three spots (use the line references as a guide; content may have shifted):
1. The **"### Plugin ecosystem"** list — replace the 6 sibling-repo bullets with the monorepo + its 10 packages, e.g.:
```markdown
First-party plugins live in the **[led-ticker-plugins](https://github.com/JamesAwesome/led-ticker-plugins)** monorepo (one uv workspace, distributed per-plugin). Each package under `plugins/<name>/` carries its own `CLAUDE.md` + `README.md`; the boundary contract above is what core guarantees them.

- `pool` — `pool.monitor`: pool water-temperature (InfluxDB v2).
- `baseball` — `baseball.{scores,standings,promotions,statcast,attendance}` widgets, `baseball.roll*` transitions, `:baseball.ball:` emoji.
- `crypto` — `crypto.coingecko` (CoinGecko price ticker).
- `calendar` — `calendar.events` (.ics agenda/next/two_row).
- `rss` — `rss.feed` (RSS/Atom headlines).
- `weather` — `weather.current` (WeatherAPI.com).
- `nyancat` / `pokeball` / `pacman` / `sailor_moon` — sprite-trail transitions `<family>.forward/.reverse/.alternating` (nyancat + pokeball hi-res; pokeball also ships `:pokeball.ball:`).
```
Keep the trailing "These plugins import a few core symbols … don't delete them." paragraph.
2. The **inline plugin-list paragraph** under "## Plugin invariants" (the long sentence enumerating `led-ticker-pool`/…/`led-ticker-arcade`) — rewrite to name the monorepo and the new types (`rss.feed`, `weather.current`, `<family>.forward/.reverse/.alternating`, `:pokeball.ball:`).
3. The **sprite-trail invariant** (the `_TRANSITION_MIGRATION` mention + "led-ticker-arcade plugin" references at lines ~94, ~188) — update `arcade.<name>` → the new `<family>.<variant>` names and "led-ticker-plugins monorepo (nyancat/pokeball/pacman/sailor_moon packages)". The weather widget mention (`feeds.weather` → `weather.current`, "weather package").

- [ ] **Step 4: Commit**

```bash
git add src/led_ticker/transitions/__init__.py tests/ CLAUDE.md
git commit -m "feat(migration): bare sprite names hint the split monorepo packages; refresh CLAUDE.md ecosystem"
```

---

### Task 5: Full suite green + open PR

**Files:** none.

- [ ] **Step 1: Whole engine test suite + lint**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker
uv run --extra dev ruff check src/ tests/
uv run pytest -q 2>&1 | tail -15
```
Expected: ruff clean; full suite PASSES (catalog, migration, hint, drift tests). If `tests/test_docs_plugin_api_drift.py` or a docs-config drift test fails because it cross-checks the catalog against a docs page, note it — the docs page fix is P3b, but if the test pins the catalog itself, reconcile minimally here and flag.

- [ ] **Step 2: Push + open PR (no merge without consent)**

```bash
git push -u origin feat/monorepo-p3a-engine-cutover
gh pr create --repo JamesAwesome/led-ticker --base main --head feat/monorepo-p3a-engine-cutover \
  --title "P3a: repoint plugin catalog + requirements at the led-ticker-plugins monorepo" \
  --body "Engine cutover for the plugin monorepo (led-ticker#235). Catalog schema v2 adds a subdirectory source field; the bundled catalog + example requirements now install all 10 first-party plugins from led-ticker-plugins via #subdirectory= with namespaced-tag pins. feeds/arcade catalog entries split into their final packages (rss/weather + nyancat/pokeball/pacman/sailor_moon). Bare sprite-name migration hints + CLAUDE.md updated to the new names. No change to Docker/install/deploy/plugin API. Docs-site pages (P3b) and old-repo archival (P3c) are separate follow-ups. Do NOT merge without consent."
```

- [ ] **Step 3: Confirm CI green**

```bash
gh pr checks <PR#> --repo JamesAwesome/led-ticker
```

---

## Self-review

**Spec coverage (P3a slice = the "Engine-side changes (P3)" items that are code/data/config):**
- `plugins_catalog.json` repoint + split + subdirectory schema → Tasks 1–2. ✓
- `requirements-plugins.example.txt` flip → Task 3. ✓
- Bare-name migration hints (`arcade.*` → new names) → Task 4. ✓
- `CLAUDE.md` ecosystem + invariant mentions → Task 4. ✓
- `_plugin_hint.py` — verified generic (derives namespace dynamically); **no change needed**, intentionally omitted. ✓
- `plugin_cmd.py` — already parses `#subdirectory=` fragments; consumes `requirement()` unchanged; **no change needed**. ✓
- Docs-site pages (~19) → **P3b** (separate). ✓
- Archive the 6 old repos + README redirects → **P3c** (separate, consent-gated, must follow this). ✓

**Placeholder scan:** No TBD/TODO; the catalog JSON + code + test code are given in full. `<PR#>` is a runtime value. Task 4 Step 3 references CLAUDE.md line numbers "as a guide" with the exact replacement content supplied. ✓

**Type/name consistency:** `subdirectory` field name, `plugins/<name>` paths, `<name>-v<version>` tags, and the `<family>.forward/.reverse/.alternating` types are used identically across Tasks 1–4 and match the tags actually cut in P2 (pool/baseball/crypto/calendar/nyancat/pokeball/pacman/sailor_moon @ v0.1.0; rss/weather @ v0.2.0). The migration map keeps the original bare-name keys so stale configs still resolve to a hint. ✓

**Pitfalls flagged inline:** `subdirectory` is optional so ad-hoc `CatalogSource` test constructions stay valid; schema bump to 2 must match JSON; don't weaken migration-test assertions (match new text); a docs-drift test may fail if it cross-checks the catalog against a docs page (reconcile minimally, flag for P3b); never commit on main; no merge without consent. **Archival (P3c) must NOT run before this merges** — until the catalog points at the monorepo, the old repos are still the install path.
