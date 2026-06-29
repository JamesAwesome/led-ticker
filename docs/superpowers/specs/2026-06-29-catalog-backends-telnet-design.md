# Design: add telnet (first backend plugin) to the plugin catalog — schema v4

**Date:** 2026-06-29
**Status:** Approved for planning
**Context:** `led-ticker-telnet` was published to PyPI (per-plugin hatch-vcs flow) but is **absent from the plugin catalog** (`src/led_ticker/plugins_catalog.json`), so it does not appear on the docs Available-plugins page or in the webui plugin store. telnet registers `api.backend("telnet")` — a **backend** — but the catalog's surface kinds (`_SURFACE_KINDS`, schema v3) are `widgets, transitions, emoji, fonts, borders, color_providers, animations, easing` with **no `backends`**. telnet is the first backend plugin; the catalog predates the backend epic (#236). This adds a first-class `backends` surface kind and the telnet entry.

## Decisions (settled at brainstorm)

- **Approach:** add `backends` as a first-class surface kind, mirroring the existing 8 (telnet renders like any plugin, with a "Backends" group). Not a hacky top-level marker.
- **Schema bump:** `SCHEMA_VERSION` 3 → **4** (the loader exact-matches `schema_version`; a new surface kind is a shape change; matches the catalog's prior versioning discipline).
- **`backends` position:** last in `_SURFACE_KINDS` / `KIND_ORDER` (renders after the content kinds) and appended to `_PRIMARY_ORDER`.
- **Single combined change:** schema bump + telnet entry land together (the loader requires the JSON's `schema_version` and the code constant to agree, so they can't be split).
- **telnet version source pin:** the git source `ref` is `telnet-v0.1.0` (its first release tag), matching how the other entries pin a `<plugin>-vX.Y.Z` ref.

## Components

### A. Catalog schema (`src/led_ticker/plugins_catalog.py`)

- `_SURFACE_KINDS`: append `"backends"`.
- `PluginProvides`: add `backends: tuple[str, ...] = ()` (field name matches the kind, per the existing "loader splats a dict" contract).
- `_PRIMARY_ORDER`: append `"backends"` (so a backend-only plugin's `primary()` resolves to its backend rather than `None`).
- `SCHEMA_VERSION = 4`.

### B. Catalog data (`src/led_ticker/plugins_catalog.json`)

- `schema_version: 4`.
- Add the telnet entry (mirrors the shape of existing entries):
  ```json
  {
    "name": "telnet",
    "namespace": "telnet",
    "summary": "Telnet (ANSI terminal) rendering backend — watch your sign in a terminal.",
    "homepage": "https://github.com/JamesAwesome/led-ticker-plugins/tree/main/plugins/telnet",
    "provides": { "backends": ["telnet"] },
    "sources": [
      { "type": "pypi", "package": "led-ticker-telnet" },
      { "type": "git", "url": "https://github.com/JamesAwesome/led-ticker-plugins", "ref": "telnet-v0.1.0", "subdirectory": "plugins/telnet" }
    ]
  }
  ```
  (Final `summary` wording taken from the plugin's own `pyproject.toml` description.)

### C. Docs render

- `docs/site/src/components/PluginCatalog.astro`: add `"backends"` to `KIND_ORDER` and `backends: "Backends"` to `KIND_LABELS`.
- `docs/site/src/content/docs/plugins/available.mdx`: add a telnet section + `<PluginCatalog name="telnet" />`. The `test_docs_available_covers_catalog.py` drift test requires the page to cover every catalog entry, so this is mandatory, not optional. Prose: a backend is the **display target** (configured as led-ticker's rendering backend), not a widget added to a section — so its "usage" framing differs from the data/widget plugins.

### D. Webui store (`src/led_ticker/webui/store.py`)

- No code change required: `store.py` builds `provides` from `entry.provides.groups()`, which generically includes any non-empty kind — so `backends` flows through once added to the schema. **Verify** the webui frontend (the store's JS/template) renders the `backends` kind acceptably; if it has a kind→label map mirroring the Astro component, add `backends: "Backends"` there too. (Investigation task in the plan; no change if the frontend shows the kind key generically.)

### E. Tests

- `tests/test_plugins/test_catalog.py`: rename/update `test_bundled_catalog_loads_and_is_v3` → asserts `schema_version == 4` (and the loader accepts it). Add a test that `telnet` is present and `cat.get("telnet").provides.backends == ("telnet",)`.
- `tests/test_docs_available_covers_catalog.py`: passes unchanged once `available.mdx` includes telnet (it's the drift guard).
- A test that `backends` is a recognized surface kind (e.g. `"backends" in plugins_catalog._SURFACE_KINDS` and a catalog entry providing only a backend is well-formed / not `is_empty()`).

## Data flow

```
plugins_catalog.json (v4, telnet entry)
  ├─► load_catalog() ─► CatalogEntry.provides.backends = ("telnet",)
  │        ├─► PluginCatalog.astro (KIND_LABELS["backends"]="Backends") ─► docs Available page
  │        └─► webui/store.py (provides.groups()) ─► webui plugin store
  └─► drift test: available.mdx must list <PluginCatalog name="telnet"/>
```

## Scope / non-goals

- **IN:** A (backends surface kind + schema v4), B (telnet entry), C (Astro label + available.mdx section), D (verify webui store/frontend renders backends), E (tests).
- **OUT:** changing how backends install or are configured (existing behavior); backend-specific catalog metadata beyond the provided name; any webui redesign; adding other backend plugins (telnet is the only one). The published telnet release itself (already done) is unaffected.

## Risks

- **Schema bump breaks a consumer that pins `schema_version == 3`** → the only consumers are the loader (updated) and `store.py` (uses the loader); the bump is coordinated in one change. The drift + catalog tests catch a mismatch.
- **Astro/webui frontend doesn't know the `backends` label** → renders a raw `backends` key. Mitigated by adding the label in the Astro component (C) and verifying the webui frontend (D).
- **`available.mdx` missing the telnet section** → the drift test fails the build. Mitigated by adding it in C (and the test is the guard).
