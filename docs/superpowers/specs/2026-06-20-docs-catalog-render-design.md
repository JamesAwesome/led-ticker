# Docs-site auto-rendered catalog facts (registry slice D)

**Date:** 2026-06-20
**Status:** approved (design), pre-implementation
**Goal:** Stop the docs-site plugin listing from drifting out of sync with the
bundled catalog. Render the **drift-prone facts** — each plugin's install spec
and its typed provided surfaces — from `src/led_ticker/plugins_catalog.json` at
docs build time, while keeping the curated per-plugin prose hand-written.

## Background / why

`docs/site/src/content/docs/plugins/available.mdx` is hand-written prose. Each of
its 10 plugin sections repeats, by hand, two facts that also live in the bundled
catalog: the install line (`git+…@<ref>#subdirectory=…`) and the provided surfaces
(`type =` names, transitions, the emoji). Those hand-typed copies are exactly what
drifted in PR #221 (baseball listed only scores/standings) and again in #246
(typed surface). The rich narrative descriptions (e.g. crypto's coin-spec styles,
weather's `WEATHERAPI_KEY` note) are NOT the drift problem — they carry real value
the catalog's one-line `summary` can't.

Now that the catalog is schema v3 with a typed `provides` object (#246), the docs
can render those facts from the JSON as the single source of truth.

**Approach chosen (from brainstorming): Augment.** Keep the curated prose; replace
only the hand-typed install block + surface enumeration in each section with an
Astro component fed by the catalog JSON.

## Decisions (from brainstorming)

1. **Augment**, not replace or hybrid: prose stays; only the facts are
   auto-rendered inline.
2. **Build-time `node:fs` read** of the catalog JSON (not a Vite JSON import, not a
   copied/generated file): mirrors `docs/site/scripts/build-demos.mjs`, avoids
   Vite's outside-project-root import restriction, and never goes stale.
3. The component renders **only** surfaces + install; summary/homepage stay in the
   hand-written section heading/prose.
4. The set-coverage drift guard is a **Python** test (where the other docs-drift
   tests live), not a JS/Astro test.
5. **Superseded during implementation:** the build-time read uses Astro's
   `import.meta.glob(..., { query: "?raw", eager: true })` (the established
   `OptionsTable.astro` pattern), NOT `node:fs` `readFileSync` as sketched
   below. Reason: at Astro prerender `__dirname`/`import.meta.url` resolves to
   the bundled `dist/` chunk path, not the source tree, so a relative
   `readFileSync` fails. The glob resolves the same source-of-truth JSON at
   compile time. The `readFileSync` sketches in this doc are retained for
   history but are not what shipped.

## Component: `docs/site/src/components/PluginCatalog.astro`

Props: `{ name: string }`.

Build-time data load (mirrors `scripts/build-demos.mjs:25-28`):

```astro
---
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
// components -> src -> site -> docs -> repo root
const REPO_ROOT = resolve(__dirname, "..", "..", "..", "..");
const CATALOG = resolve(REPO_ROOT, "src/led_ticker/plugins_catalog.json");

interface Source {
  type: "git" | "pypi";
  url?: string; ref?: string; subdirectory?: string;
  package?: string; version?: string;
}
interface Entry {
  name: string; namespace: string; summary: string; homepage: string;
  provides: Record<string, string[]>;
  sources: Source[];
}

const catalog = JSON.parse(readFileSync(CATALOG, "utf8")) as {
  schema_version: number; plugins: Entry[];
};

const { name } = Astro.props;
const entry = catalog.plugins.find((p) => p.name === name);
if (!entry) {
  throw new Error(
    `PluginCatalog: no plugin named "${name}" in plugins_catalog.json. ` +
      `Known: ${catalog.plugins.map((p) => p.name).join(", ")}`,
  );
}
---
```

### Install line — mirror the Python `requirement()` shape

The pinned requirement from the entry's **first** source (matches
`CatalogEntry.source_for(None)` / `requirement(pinned=True)` in
`plugins_catalog.py`):

- git: `git+{url-without-.git}.git@{ref}` + (if `subdirectory`) `#subdirectory={subdirectory}`
- pypi: `{package}=={version}` (or bare `{package}` when no version)

All 10 current entries are git; the pypi branch is included for parity (cheap, and
slice C will populate pypi sources).

### Provided surfaces — grouped by kind, canonical order

Render the non-empty kinds of `entry.provides` in the same canonical order and
labels the CLI uses (`_SURFACE_KINDS` / `_KIND_LABELS` in the Python side):
widgets, transitions, emoji, fonts, borders, color providers, animations, easing.
Emoji are shown as `:slug:` (matching `plugin list`). Empty kinds omitted; an
entry with empty `provides` renders no surface lines.

### Output shape

The component renders (HTML/JSX in the `.astro` template):
- a short "Provides" block: one line per non-empty kind, `Label: name, name, …`
  (emoji as `:slug:`);
- a fenced code block with the install requirement line, captioned so it's clear
  it goes in `config/requirements-plugins.txt`.

Exact visual styling follows the surrounding Starlight prose; no new design
system. Keep the markup minimal and accessible (a labeled list + a `<pre><code>`).

## `available.mdx` changes

For each of the 10 plugin sections (pool, baseball, crypto, calendar, rss,
weather, nyancat, pokeball, pacman, sailor_moon):

- **Keep:** the `### [name](homepage)` heading and the narrative paragraph(s).
- **Remove:** the trailing "Add to your `config/requirements-plugins.txt`:" code
  block, and any inline enumeration that merely lists the provided `type=` /
  transition / emoji names (prose that *explains* a surface stays; a bare list of
  slugs that duplicates the catalog goes).
- **Insert:** `<PluginCatalog name="…" />` where the removed facts were.

Add the import at the top of the MDX:
`import PluginCatalog from "../../../components/PluginCatalog.astro";`

The page intro, the `## Widgets` / `## Transitions` groupings, and the
`## Add your plugin` section stay as-is.

## Drift guard (Python test)

`tests/test_docs_available_covers_catalog.py` (hermetic; mirrors the existing
`tests/test_docs_*` drift tests):

- Read `src/led_ticker/plugins_catalog.json` → the set of plugin `name`s.
- Read `docs/site/src/content/docs/plugins/available.mdx` → all
  `<PluginCatalog name="X" />` usages (regex).
- Assert the two sets are **equal**. A new plugin in the JSON without a docs
  section, a removed plugin left in docs, or a typo'd `name` all fail this test.

This closes the one gap Augment leaves open (the component guarantees the *facts*
of each documented plugin; this test guarantees the documented *set* matches the
catalog).

## Testing

- The Python drift test above (no Astro needed; runs in the normal suite).
- `cd docs/site && pnpm build` (or `make docs-build`) must succeed — this compiles
  `PluginCatalog.astro`, resolves the build-time read, and renders every
  `<PluginCatalog />` usage; a bad `name`, a moved JSON, or malformed markup fails
  the build.
- `pnpm run lint` (`prettier --check` + `astro check`) clean.
- Manual: render `available.mdx`, confirm each plugin shows correct grouped
  surfaces + the right pinned install line.

## Error handling

- Unknown `name` prop → build throws (typo guard, like `OptionsTable.astro`).
- Missing / moved catalog JSON → `readFileSync` throws at build.
- Entry with empty `provides` → no surface lines (consistent with the CLI).

## Non-goals

- Top-of-page "at a glance" summary table (the Hybrid option — not chosen).
- Auto-generating the narrative prose descriptions.
- PyPI source publishing (slice C); the pypi install branch is rendered if present
  but no catalog entry uses it yet.
- Changing the catalog schema or the Python `plugins_catalog.py` (slice D is
  docs-only + one test).
