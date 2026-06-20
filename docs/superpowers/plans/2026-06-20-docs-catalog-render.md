# Docs-site Auto-Rendered Catalog Facts (Slice D) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render each plugin's install line and typed provided surfaces in the docs-site Available-plugins page from `plugins_catalog.json` at build time, so those facts can't drift from the catalog.

**Architecture:** A new build-time Astro component (`PluginCatalog.astro`) reads the bundled catalog JSON via `node:fs` (the pattern `scripts/build-demos.mjs` already uses) and renders one plugin's grouped surfaces + pinned install requirement. `available.mdx` keeps its curated prose but swaps each section's hand-typed facts for `<PluginCatalog name="…" />`. A Python tripwire test asserts the set of documented plugins equals the catalog.

**Tech Stack:** Astro 6 + Starlight (docs/site, pnpm), Python 3.14 + pytest (the drift test).

## Global Constraints

- Worktree: `/Users/james/projects/github/jamesawesome/led-ticker-worktrees/docs-catalog-render`, branch `feat/docs-catalog-render` (based on `origin/main` @ d3aa244). **Run `git branch --show-current` before editing; abort if it prints `main`.**
- **Docs-only + one Python test.** Do NOT modify `src/led_ticker/plugins_catalog.py` or `src/led_ticker/plugins_catalog.json` (the JSON is the source of truth, read as-is).
- The install line MUST mirror Python `CatalogEntry.requirement(pinned=True)`: git → `git+{url-without-.git}.git@{ref}` + `#subdirectory={subdirectory}` when present; pypi → `{package}=={version}` (or bare `{package}` when no version). Uses `sources[0]` (the preferred source).
- Provided surfaces MUST use the catalog's canonical kind order and the CLI labels, emoji shown as `:slug:`. Kind order: `widgets, transitions, emoji, fonts, borders, color_providers, animations, easing`.
- docs/site uses **pnpm**. Run `pnpm install` once in `docs/site/` before `pnpm build` / `pnpm run lint`. Run `pnpm run format` (prettier-plugin-astro) before `pnpm run lint` so the new `.astro` file is formatted.
- Python test runs under `PYTHONPATH=tests/stubs uv run pytest`. No `from __future__ import annotations` needed.
- `git add` every new file (check `git status` for `??`). Commit trailer on every commit: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>` and `Claude-Session: https://claude.ai/code/session_01P7r9q2YjKvWBsTSfdPotAh`.
- The 10 plugins: pool, baseball, crypto, calendar, rss, weather, nyancat, pokeball, pacman, sailor_moon (each has a section in `available.mdx` and an entry in the catalog JSON).

---

### Task 1: `PluginCatalog.astro` component, proven on the `pool` section

**Files:**
- Create: `docs/site/src/components/PluginCatalog.astro`
- Modify: `docs/site/src/content/docs/plugins/available.mdx` (add the import; wire ONLY the `pool` section)

**Interfaces:**
- Consumes: `src/led_ticker/plugins_catalog.json` (read at build time).
- Produces: an Astro component usable as `<PluginCatalog name="<plugin>" />`. Renders a "Provides" list (non-empty kinds, canonical order, emoji as `:slug:`) and a fenced install requirement line. Throws at build if `name` is not in the catalog.

- [ ] **Step 1: Create the component**

Create `docs/site/src/components/PluginCatalog.astro` with exactly:

```astro
---
/**
 * Renders one plugin's catalog facts (provided surfaces + pinned install
 * requirement) from the bundled `plugins_catalog.json`, read at build time.
 * The JSON (in the Python package) is the single source of truth, so these
 * facts cannot drift from the catalog. Curated prose stays hand-written in
 * available.mdx.
 *
 * Usage: <PluginCatalog name="baseball" />
 */
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
// components -> src -> site -> docs -> repo root
const REPO_ROOT = resolve(__dirname, "..", "..", "..", "..");
const CATALOG_PATH = resolve(REPO_ROOT, "src/led_ticker/plugins_catalog.json");

interface Source {
  type: "git" | "pypi";
  url?: string;
  ref?: string;
  subdirectory?: string;
  package?: string;
  version?: string;
}
interface Entry {
  name: string;
  namespace: string;
  summary: string;
  homepage: string;
  provides: Record<string, string[]>;
  sources: Source[];
}

const catalog = JSON.parse(readFileSync(CATALOG_PATH, "utf8")) as {
  schema_version: number;
  plugins: Entry[];
};

const { name } = Astro.props;
const entry = catalog.plugins.find((p) => p.name === name);
if (!entry) {
  throw new Error(
    `PluginCatalog: no plugin named "${name}" in plugins_catalog.json. ` +
      `Known: ${catalog.plugins.map((p) => p.name).join(", ")}`,
  );
}

// Mirror Python CatalogEntry.requirement(pinned=True): prefer sources[0].
function requirementLine(e: Entry): string {
  const src = e.sources[0];
  if (src.type === "git") {
    const base = (src.url ?? "").replace(/\.git$/, "");
    let req = `git+${base}.git@${src.ref ?? "main"}`;
    if (src.subdirectory) req += `#subdirectory=${src.subdirectory}`;
    return req;
  }
  return src.version ? `${src.package}==${src.version}` : (src.package ?? "");
}

const KIND_ORDER = [
  "widgets",
  "transitions",
  "emoji",
  "fonts",
  "borders",
  "color_providers",
  "animations",
  "easing",
] as const;
const KIND_LABELS: Record<string, string> = {
  widgets: "Widgets",
  transitions: "Transitions",
  emoji: "Emoji",
  fonts: "Fonts",
  borders: "Borders",
  color_providers: "Color providers",
  animations: "Animations",
  easing: "Easing",
};

const groups = KIND_ORDER.filter(
  (k) => (entry.provides[k] ?? []).length > 0,
).map((k) => ({
  label: KIND_LABELS[k],
  names: (entry.provides[k] ?? []).map((n) => (k === "emoji" ? `:${n}:` : n)),
}));

const requirement = requirementLine(entry);
---

<div class="plugin-catalog">
  {
    groups.length > 0 && (
      <ul class="provides">
        {groups.map((g) => (
          <li>
            <strong>{g.label}:</strong> {g.names.join(", ")}
          </li>
        ))}
      </ul>
    )
  }
  <p class="install-caption">
    Add to your <code>config/requirements-plugins.txt</code>:
  </p>
  <pre class="install"><code>{requirement}</code></pre>
</div>

<style>
  .plugin-catalog {
    margin: 0.75rem 0 1.5rem;
  }
  .provides {
    list-style: none;
    padding: 0;
    margin: 0 0 0.75rem;
  }
  .provides li {
    margin: 0.15rem 0;
  }
  .install-caption {
    margin: 0 0 0.35rem;
  }
  .plugin-catalog pre.install {
    margin: 0;
  }
</style>
```

- [ ] **Step 2: Add the import + wire the `pool` section in available.mdx**

In `docs/site/src/content/docs/plugins/available.mdx`, add the import immediately
after the frontmatter (the closing `---`), before the intro paragraph:

```mdx
import PluginCatalog from "../../../components/PluginCatalog.astro";
```

Then in the `pool` section, DELETE these lines (the hand-typed install block):

```mdx
Add to your `config/requirements-plugins.txt`:

```text
git+https://github.com/JamesAwesome/led-ticker-plugins.git@pool-v0.1.0#subdirectory=plugins/pool
```
```

and replace them with:

```mdx
<PluginCatalog name="pool" />
```

Leave the pool heading and narrative paragraph (including the inline
`type = "pool.monitor"` mention — that's explanatory prose) untouched.

- [ ] **Step 3: Install deps and build to verify the component renders**

Run:
```bash
cd docs/site && pnpm install
pnpm build
```
Expected: build succeeds. Grep the built output to confirm pool's install line and a "Widgets:" line rendered:
```bash
grep -rl "subdirectory=plugins/pool" dist/ | head -1
grep -rl "Widgets:" dist/ | head -1
```
Expected: both print a path under `dist/` (the component rendered). If the build throws `PluginCatalog: no plugin named "pool"`, the read path is wrong — re-check `CATALOG_PATH`.

- [ ] **Step 4: Format + lint**

Run:
```bash
cd docs/site && pnpm run format && pnpm run lint
```
Expected: prettier writes/keeps the `.astro` formatted; `astro check` passes with 0 errors.

- [ ] **Step 5: Commit**

```bash
cd "$(git rev-parse --show-toplevel)"
git add docs/site/src/components/PluginCatalog.astro docs/site/src/content/docs/plugins/available.mdx
git commit -m "feat(docs): PluginCatalog component rendering catalog facts (wired: pool)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01P7r9q2YjKvWBsTSfdPotAh"
```

---

### Task 2: Wire the remaining nine plugin sections

**Files:**
- Modify: `docs/site/src/content/docs/plugins/available.mdx` (sections: baseball, crypto, calendar, rss, weather, nyancat, pokeball, pacman, sailor_moon)

**Interfaces:**
- Consumes: the `<PluginCatalog name="…" />` component from Task 1.
- Produces: an `available.mdx` where all 10 sections render their facts from the catalog.

- [ ] **Step 1: Replace each section's install block with the component**

For EACH of these nine sections, find the trailing block:

```mdx
Add to your `config/requirements-plugins.txt`:

```text
git+https://github.com/JamesAwesome/led-ticker-plugins.git@<ref>#subdirectory=plugins/<name>
```
```

and replace the whole block (the "Add to your…" caption line, the blank line, and
the fenced ```text code block) with a single line:

```mdx
<PluginCatalog name="<name>" />
```

Do this for, using these exact `name` values:
`baseball`, `crypto`, `calendar`, `rss`, `weather`, `nyancat`, `pokeball`, `pacman`, `sailor_moon`.

Keep every heading and narrative paragraph. Do NOT edit the page intro, the
`## Widgets` / `## Transitions` group headers, or the `## Add your plugin` section.
Leaving narrative prose that mentions surface names is fine (the component now owns
the canonical list); trimming such mentions is optional and NOT required.

- [ ] **Step 2: Confirm no hand-typed install blocks remain**

Run:
```bash
cd "$(git rev-parse --show-toplevel)"
grep -n "Add to your \`config/requirements-plugins.txt\`" docs/site/src/content/docs/plugins/available.mdx || echo "NONE-REMAIN"
grep -c "<PluginCatalog name=" docs/site/src/content/docs/plugins/available.mdx
```
Expected: first prints `NONE-REMAIN` (every hand-typed install caption is gone);
second prints `10`.

- [ ] **Step 3: Build + lint**

Run:
```bash
cd docs/site && pnpm build && pnpm run format && pnpm run lint
```
Expected: build succeeds (all 10 `<PluginCatalog />` usages resolve — a typo in any
`name` would throw `no plugin named "…"`); prettier + astro check clean.

- [ ] **Step 4: Spot-check a transition-only and an emoji plugin in the build**

Run:
```bash
cd docs/site
grep -rl "subdirectory=plugins/nyancat" dist/ | head -1   # nyancat install line
grep -rho ":pokeball.ball:" dist/ | head -1                # pokeball emoji as :slug:
```
Expected: the nyancat path prints; `:pokeball.ball:` prints (emoji rendered in
`:slug:` form).

- [ ] **Step 5: Commit**

```bash
cd "$(git rev-parse --show-toplevel)"
git add docs/site/src/content/docs/plugins/available.mdx
git commit -m "feat(docs): render catalog facts for the remaining nine plugins

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01P7r9q2YjKvWBsTSfdPotAh"
```

---

### Task 3: Python drift tripwire — documented set == catalog set

**Files:**
- Create: `tests/test_docs_available_covers_catalog.py`

**Interfaces:**
- Consumes: `src/led_ticker/plugins_catalog.json` and `docs/site/src/content/docs/plugins/available.mdx`.
- Produces: a hermetic test asserting the `<PluginCatalog name="X" />` set equals the catalog plugin-name set.

- [ ] **Step 1: Write the test**

Create `tests/test_docs_available_covers_catalog.py` with exactly:

```python
"""Tripwire: the Available-plugins page documents exactly the catalog's plugins.

`available.mdx` renders each plugin's facts via `<PluginCatalog name="X" />`,
fed by the bundled `plugins_catalog.json`. The component guarantees the *facts*
of each documented plugin can't drift; this test guarantees the documented
*set* matches the catalog — catching a plugin added to the catalog but not given
a docs section, a removed plugin left in the docs, or a typo'd `name`.
"""

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CATALOG = REPO_ROOT / "src" / "led_ticker" / "plugins_catalog.json"
PAGE = (
    REPO_ROOT
    / "docs"
    / "site"
    / "src"
    / "content"
    / "docs"
    / "plugins"
    / "available.mdx"
)

_USAGE_RE = re.compile(r'<PluginCatalog\s+name="([^"]+)"\s*/>')


def _catalog_names() -> set[str]:
    data = json.loads(CATALOG.read_text(encoding="utf-8"))
    return {p["name"] for p in data["plugins"]}


def _documented_names() -> set[str]:
    return set(_USAGE_RE.findall(PAGE.read_text(encoding="utf-8")))


def test_available_page_documents_exactly_the_catalog():
    catalog = _catalog_names()
    documented = _documented_names()
    missing = catalog - documented
    extra = documented - catalog
    assert not missing, f"catalog plugins missing a docs section: {sorted(missing)}"
    assert not extra, f"docs reference unknown plugins: {sorted(extra)}"


def test_every_plugin_is_documented_once():
    # No accidental duplicate <PluginCatalog name="x"/> for the same plugin.
    names = _USAGE_RE.findall(PAGE.read_text(encoding="utf-8"))
    dupes = {n for n in names if names.count(n) > 1}
    assert not dupes, f"plugins rendered more than once: {sorted(dupes)}"
```

- [ ] **Step 2: Run it — confirm it passes against the wired page**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_docs_available_covers_catalog.py -v`
Expected: 2 passed.

- [ ] **Step 3: Prove the tripwire bites (red), then restore**

Temporarily rename one usage in `available.mdx` (e.g. change `name="pacman"` to
`name="pacmann"`), then run the test:

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_docs_available_covers_catalog.py -q`
Expected: FAIL — `missing: ['pacman']` AND `extra: ['pacmann']`.

Then restore the correct `name="pacman"` and re-run:

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_docs_available_covers_catalog.py -q`
Expected: 2 passed.

- [ ] **Step 4: Full suite + lint + types**

Run:
```bash
PYTHONPATH=tests/stubs uv run pytest -q
uv run --extra dev ruff check src/ tests/ && uv run --extra dev ruff format --check src/ tests/
uv run --extra dev pyright src/
```
Expected: full suite green; ruff + format clean; pyright 0 errors.

- [ ] **Step 5: Commit**

```bash
cd "$(git rev-parse --show-toplevel)"
git add tests/test_docs_available_covers_catalog.py
git commit -m "test(docs): tripwire — available.mdx documents exactly the catalog

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01P7r9q2YjKvWBsTSfdPotAh"
```

---

## Final verification (after all tasks)

- [ ] `cd docs/site && pnpm build` succeeds; `pnpm run lint` clean.
- [ ] `PYTHONPATH=tests/stubs uv run pytest -q` green; `uv run --extra dev pyright src/` 0 errors.
- [ ] `grep -c "<PluginCatalog name=" docs/site/src/content/docs/plugins/available.mdx` prints `10`; no `Add to your \`config/requirements-plugins.txt\`` captions remain.
- [ ] `git status` shows no untracked (`??`) files.
- [ ] Push and open a PR against `main`; wait for CI green before requesting merge.

## Notes / gotchas

- `docs/site` is a separate pnpm project; `pnpm install` is needed in the worktree before the first build.
- The docs `build-and-deploy` CI job builds from a full checkout, so the component's relative read of `src/led_ticker/plugins_catalog.json` resolves in CI the same as locally.
- `docs/plugin-system.md` (repo-root docs) is unrelated here; this slice only touches `docs/site/` + one Python test.
- Do not "fix" the catalog JSON or `plugins_catalog.py` — if the rendered facts look wrong, the bug is in the component, not the data (the data was reviewed in #246).
