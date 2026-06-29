# Catalog `backends` kind + telnet entry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `led-ticker-telnet` (the first backend plugin) to the plugin catalog by introducing a first-class `backends` surface kind (schema v3→v4), so telnet appears on the docs Available page and the webui plugin store.

**Architecture:** Mirror the existing surface-kind pattern: add `backends` to the loader's kind tuple + `PluginProvides`, bump `SCHEMA_VERSION`, add the telnet entry to the bundled JSON, teach the Astro component its label, add the docs section, and confirm the webui store (which reads kinds generically) renders it.

**Tech Stack:** Python (attrs, stdlib json), pytest, Astro/MDX (docs site), the webui (aiohttp + JS).

## Global Constraints

- Work in the worktree: `/Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/catalog-backends-telnet` (branch `worktree-catalog-backends-telnet`). Tests: `uv run --extra dev pytest …`. Commit with `git commit --no-verify`.
- **Schema bump 3 → 4**, coordinated: the loader validates `schema_version == SCHEMA_VERSION` exactly, so the JSON's `schema_version` and the `SCHEMA_VERSION` constant must change together in the same task.
- `backends` goes **last** in `_SURFACE_KINDS` / `KIND_ORDER`, and is appended to `_PRIMARY_ORDER`.
- The telnet catalog entry: `name`/`namespace` = `"telnet"`, `provides` = `{"backends": ["telnet"]}`, sources = pypi `led-ticker-telnet` + git `ref: "telnet-v0.1.0"` subdir `plugins/telnet`. Summary from the plugin's pyproject: "Telnet (ANSI terminal) rendering backend for led-ticker — watch your sign in a terminal."
- The docs Available page (`available.mdx`) MUST list every catalog entry (`test_docs_available_covers_catalog.py` enforces it) — telnet's section is mandatory.
- Field name on `PluginProvides` must equal the kind string (`backends`) — the loader splats a `{kind: [...]}` dict into the dataclass.

---

### Task 1: `backends` surface kind + telnet catalog entry (schema v4)

**Files:**
- Modify: `src/led_ticker/plugins_catalog.py` (`_SURFACE_KINDS`, `_PRIMARY_ORDER`, `PluginProvides`, `SCHEMA_VERSION`)
- Modify: `src/led_ticker/plugins_catalog.json` (`schema_version` + new telnet entry)
- Test: `tests/test_plugins/test_catalog.py`

**Interfaces:**
- Produces: `load_catalog().get("telnet").provides.backends == ("telnet",)`; `SCHEMA_VERSION == 4`; `"backends" in plugins_catalog._SURFACE_KINDS`.

- [ ] **Step 1: Write/adjust the failing tests**

In `tests/test_plugins/test_catalog.py`:

Rename `test_bundled_catalog_loads_and_is_v3` and assert the version explicitly:
```python
def test_bundled_catalog_loads_and_is_v4():
    from led_ticker.plugins_catalog import SCHEMA_VERSION
    assert SCHEMA_VERSION == 4
    cat = load_catalog()
    assert isinstance(cat, Catalog)
    assert cat.entries  # non-empty
```

Add `"telnet"` to the first-party name set in `test_bundled_catalog_has_the_first_party_plugins`:
```python
    assert names == {
        "pool",
        "baseball",
        "crypto",
        "calendar",
        "rss",
        "weather",
        "nyancat",
        "pokeball",
        "pacman",
        "sailor_moon",
        "telnet",
    }
```

Add a backends-kind test:
```python
def test_telnet_provides_a_backend():
    from led_ticker.plugins_catalog import _SURFACE_KINDS
    assert "backends" in _SURFACE_KINDS
    cat = load_catalog()
    telnet = cat.get("telnet")
    assert telnet.provides.backends == ("telnet",)
    assert not telnet.provides.is_empty()
    # backend is the plugin's primary (and only) surface
    assert telnet.provides.primary() == ("backends", "telnet")
```

- [ ] **Step 2: Run — expect FAIL**

Run: `cd /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/catalog-backends-telnet && uv run --extra dev pytest tests/test_plugins/test_catalog.py -q`
Expected: FAIL — `SCHEMA_VERSION` is 3, `telnet` absent, `_SURFACE_KINDS` has no `backends`.

- [ ] **Step 3: Add the `backends` kind to the loader**

In `src/led_ticker/plugins_catalog.py`:
- Change `SCHEMA_VERSION = 3` to `SCHEMA_VERSION = 4`.
- Append `"backends"` to `_SURFACE_KINDS` (last element).
- Append `"backends"` to `_PRIMARY_ORDER` (last element).
- Add the field to `PluginProvides` (after `easing`):
```python
    easing: tuple[str, ...] = ()
    backends: tuple[str, ...] = ()
```

- [ ] **Step 4: Bump the JSON + add the telnet entry**

In `src/led_ticker/plugins_catalog.json`:
- Change `"schema_version": 3` to `"schema_version": 4`.
- Add this entry to the `"plugins"` array (alongside the others):
```json
{
  "name": "telnet",
  "namespace": "telnet",
  "summary": "Telnet (ANSI terminal) rendering backend for led-ticker — watch your sign in a terminal.",
  "homepage": "https://github.com/JamesAwesome/led-ticker-plugins/tree/main/plugins/telnet",
  "provides": { "backends": ["telnet"] },
  "sources": [
    { "type": "pypi", "package": "led-ticker-telnet" },
    { "type": "git", "url": "https://github.com/JamesAwesome/led-ticker-plugins", "ref": "telnet-v0.1.0", "subdirectory": "plugins/telnet" }
  ]
}
```

- [ ] **Step 5: Run — expect PASS**

Run: `uv run --extra dev pytest tests/test_plugins/test_catalog.py -q`
Expected: PASS (all, including the well-formed-entries test).

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/plugins_catalog.py src/led_ticker/plugins_catalog.json tests/test_plugins/test_catalog.py
git commit --no-verify -m "feat(catalog): add backends surface kind + telnet entry (schema v4)"
```

---

### Task 2: Docs render — Astro label + Available-page section

**Files:**
- Modify: `docs/site/src/components/PluginCatalog.astro` (`KIND_ORDER`, `KIND_LABELS`)
- Modify: `docs/site/src/content/docs/plugins/available.mdx` (new Backends section)
- Test: `tests/test_docs_available_covers_catalog.py` (drift guard — passes once telnet is listed)

**Interfaces:**
- Consumes: the telnet catalog entry (Task 1).

- [ ] **Step 1: Run the drift test — expect FAIL**

Run: `cd /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/catalog-backends-telnet && uv run --extra dev pytest tests/test_docs_available_covers_catalog.py -q`
Expected: FAIL — the catalog now has `telnet` but `available.mdx` doesn't list `<PluginCatalog name="telnet" />`.

- [ ] **Step 2: Teach the Astro component the backends label**

In `docs/site/src/components/PluginCatalog.astro`:
- Add `"backends"` to the `KIND_ORDER` array (last, mirroring `_SURFACE_KINDS`).
- Add `backends: "Backends",` to the `KIND_LABELS` object.

- [ ] **Step 3: Add the Backends section to available.mdx**

In `docs/site/src/content/docs/plugins/available.mdx`, after the `## Transitions` section's plugins and before `## Add your plugin`, add:
```mdx
## Backends

A backend is led-ticker's **rendering target** — where the sign is drawn. Unlike widgets, a backend isn't added to a section; it's selected as the display backend. See the [backends concept](https://docs.ledticker.dev/concepts/backends/) for configuration.

### [telnet](https://github.com/JamesAwesome/led-ticker-plugins/tree/main/plugins/telnet)

Watch your sign in a terminal over Telnet (ANSI rendering).

<PluginCatalog name="telnet" />
```
(If `docs/site/.../concepts/backends/` does not exist, drop the concept link and keep the prose — verify with `ls docs/site/src/content/docs/concepts/ | grep -i backend`.)

- [ ] **Step 4: Run the drift test — expect PASS**

Run: `uv run --extra dev pytest tests/test_docs_available_covers_catalog.py -q`
Expected: PASS.

- [ ] **Step 5: Build the docs to confirm the component + MDX compile**

Run: `make docs-build 2>&1 | tail -5`
Expected: build succeeds (`docs/site/dist/plugins/available/index.html` exists). If `make docs-build` fails for env reasons (pnpm missing), note it and fall back to verifying the MDX/Astro edits are syntactically consistent with the existing entries.

- [ ] **Step 6: Commit**

```bash
git add docs/site/src/components/PluginCatalog.astro docs/site/src/content/docs/plugins/available.mdx
git commit --no-verify -m "docs(catalog): render the Backends kind + add telnet to the Available page"
```

---

### Task 3: Webui plugin-store renders the backends kind

**Files:**
- Investigate/Modify: `src/led_ticker/webui/store.py` and the webui frontend assets (templates/JS under `src/led_ticker/webui/`)
- Test: `tests/` webui store tests if present (locate via `grep -rl "store" tests/`)

**Interfaces:**
- Consumes: the telnet catalog entry (Task 1).

- [ ] **Step 1: Confirm telnet flows through the store API**

Run:
```bash
cd /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/catalog-backends-telnet
uv run python -c "
from led_ticker.webui import store
items = store.catalog_items() if hasattr(store, 'catalog_items') else None
import inspect
print([n for n,_ in inspect.getmembers(store, inspect.isfunction)])
"
```
Then call whichever function builds the catalog list (the one using `load_catalog()` / `entry.provides.groups()`, ~line 104/166 of `store.py`) and print the telnet item — confirm its `provides` dict contains `{"backends": ["telnet"]}`. Expected: telnet present with the backends group (no code change needed in `store.py` because it splats `groups()`).

- [ ] **Step 2: Find the webui frontend's kind labels (if any)**

Run:
```bash
grep -rniE 'widgets|transitions|color_providers|provides|kind' src/led_ticker/webui/ --include=*.html --include=*.js --include=*.py | grep -iE 'label|widgets|transitions|kind' | head
```
- If the frontend has a kind→label map (mirroring the Astro `KIND_LABELS`), add `backends: "Backends"` (or the file's convention) so the store shows "Backends" not the raw key.
- If the frontend renders the kind key generically (e.g. title-cases it or shows it verbatim), no change is needed — note that in the report.

- [ ] **Step 3: Run the webui store tests**

Run:
```bash
TESTS=$(grep -rl "store" tests/ 2>/dev/null | grep -i webui || true)
uv run --extra dev pytest ${TESTS:-tests/} -q -k "store or webui" 2>&1 | tail -5
```
Expected: green. If a store test enumerates expected catalog kinds/plugins, update it to include telnet/backends.

- [ ] **Step 4: Commit (only if a change was made)**

```bash
git add -A && git commit --no-verify -m "feat(webui): label the backends kind in the plugin store"
```
If Step 2 found no change is needed, skip the commit and record "no webui change needed" in the report.

---

### Task 4: Full verification

- [ ] **Step 1: Run the whole suite + lint**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/catalog-backends-telnet
uv run --extra dev pytest tests/test_plugins/test_catalog.py tests/test_docs_available_covers_catalog.py -q
uv run --extra dev pytest -q 2>&1 | tail -5
uv run --extra dev ruff check src/ tests/ 2>&1 | tail -3
```
Expected: all green; ruff clean. If `make docs-build` was runnable in Task 2, it stays green.

## Self-Review notes (spec coverage)

- Spec A (backends kind + schema v4) → Task 1 (loader) + Task 1 (JSON bump).
- Spec B (telnet entry) → Task 1.
- Spec C (Astro label + available.mdx section) → Task 2.
- Spec D (webui store flow-through + frontend label) → Task 3.
- Spec E (tests: v4, telnet present, backends recognized; drift test) → Task 1 + Task 2 + Task 4.
- Spec risks (schema bump coordinated; missing label; missing mdx section) → covered by the coordinated Task 1, Task 2 label, and the drift test.
- Non-goals (install/config behavior, extra metadata, webui redesign, other backends) → respected by omission.
