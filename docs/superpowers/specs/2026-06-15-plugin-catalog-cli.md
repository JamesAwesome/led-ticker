# Plugin catalog + `led-ticker plugin` CLI (registry slice 1)

**Date:** 2026-06-15
**Goal:** Give led-ticker a discoverable, installable plugin registry: a bundled
`plugins.json` catalog (in-repo source of truth) and a `led-ticker plugin`
CLI (`status` / `list` / `search` / `install`) that resolves a friendly name to
a pip-installable source (git **or** PyPI, pip-style), appends it to
`requirements-plugins.txt`, and installs it under the existing core-constraint
mechanism.

This is **slice 1** of the registry effort (steal-list #4). Decomposition:

- **A. Catalog** + **B. install/search CLI** — THIS spec.
- **C. PyPI publishing** — Trusted-Publishing workflows in each plugin repo so
  names also resolve via PyPI. Separate spec, independent. v1 entries are
  git-only; a `pypi` source is added later with no schema change.
- **D. Discovery polish** — docs-site auto-rendered catalog table + broader hint
  polish. Separate spec.

## Decisions (from brainstorming)

1. First slice = catalog (A) + CLI (B), git **and** PyPI sources (pip-style).
2. Catalog is **bundled** in the package (in-repo SoT), read **offline**; remote
   refresh is future.
3. `install` **pins to the catalog-declared `ref` by default**; `--unpinned`
   opts out.
4. CLI unifies under **`plugin`**: `plugin status` (= today's `plugins`),
   `plugin list` / `search` / `install`. Bare `plugins` becomes a deprecated
   alias of `plugin status`.

## Component 1 — the catalog

**File:** `src/led_ticker/plugins_catalog.json` (in-repo SoT, bundled in the wheel
via package-data in `pyproject.toml`).

**Schema (`schema_version: 1`):**

```json
{
  "schema_version": 1,
  "plugins": [
    {
      "name": "pool",
      "namespace": "pool",
      "summary": "Pool water temperature from InfluxDB v2",
      "homepage": "https://github.com/JamesAwesome/led-ticker-pool",
      "provides": ["pool.monitor"],
      "sources": [
        {
          "type": "git",
          "url": "https://github.com/JamesAwesome/led-ticker-pool",
          "ref": "main"
        }
      ]
    }
  ]
}
```

- `name` — the friendly install token (`led-ticker plugin install <name>`); equals
  the registered `namespace` for the first-party plugins.
- `sources` — an **ordered, pip-style list**. Each source is `{type: "git", url,
  ref}` or `{type: "pypi", package, version?}`. The CLI uses the **first** source
  by default; `--source git|pypi` overrides. v1 first-party entries are git-only
  (the repos have no release tags yet, so `ref: "main"` — the pin mechanism is in
  place; real tags land with slice C). A `pypi` source is prepended later and
  becomes the default with no schema change.
- `provides` — registered names contributed (widgets/transitions/emoji), e.g.
  `["pool.monitor"]` — shown by `list`/`search` and matched by `search`.

**Seed entries:** pool (`pool.monitor`), baseball (`baseball.scores`,
`baseball.standings`, `baseball.roll*` transitions, `:baseball.ball:` emoji),
crypto (`crypto.coingecko`). URLs/namespaces per the existing
`config/requirements-plugins.example.txt` + CLAUDE.md plugin ecosystem list.

**Loader:** `src/led_ticker/plugins_catalog.py`

- `load_catalog() -> Catalog` reads + parses the bundled JSON (via
  `importlib.resources`), validating `schema_version`, required fields, and source
  shapes; raises a clear error on a malformed bundled file.
- `Catalog.get(name) -> CatalogEntry | None`, `Catalog.search(query) ->
  list[CatalogEntry]` (case-insensitive substring over name/summary/provides).
- `CatalogEntry.requirement(*, source=None, pinned=True) -> str` builds the pip
  requirement string:
  - git pinned → `git+https://github.com/JamesAwesome/led-ticker-pool.git@<ref>`
  - git unpinned → `git+https://github.com/JamesAwesome/led-ticker-pool.git@main`
  - pypi pinned → `led-ticker-pool==<version>` (when a version is present)
  - pypi unpinned → `led-ticker-pool`
  - normalizes the git url to the `git+https://….git@ref` form
    `requirements-plugins.txt` already uses.

## Component 2 — the `plugin` CLI

**File:** `src/led_ticker/app/cli.py` (extend) + helpers in a new
`src/led_ticker/app/plugin_cmd.py` (keep cli.py thin; the install/catalog logic is
testable in isolation).

`plugin` is an argparse sub-parser with sub-sub-commands:

| Command | Behavior |
|---|---|
| `plugin status [--config P]` | exactly today's `plugins` output (loaded/failed); reuses the existing code path. |
| `plugin list [--config P]` | print every catalog entry (name — summary; provides). Mark `[installed]` when the namespace's distribution is importable (`importlib.metadata`) or the namespace is in the loaded set. |
| `plugin search <query>` | print catalog entries matching the query. |
| `plugin install <name\|pip-spec> [flags]` | the install flow below. |
| `plugins …` | deprecated alias: prints a one-line deprecation note to stderr, then runs `plugin status`. (Preserves back-compat for scripts/docs.) |

**`install` flow (`plugin_cmd.install(...)`):**

1. If `<arg>` exactly matches a catalog `name` → **catalog mode**. Else → **raw
   mode** (treat `<arg>` as a pip spec: `git+…`, a PyPI spec, `name==x`, etc.).
2. Catalog mode: pick the source (`--source` or first in `sources`); build the
   requirement via `CatalogEntry.requirement(source=…, pinned=not --unpinned)`.
   Raw mode: the requirement IS `<arg>` (and the file line is `<arg>` verbatim).
3. **Update `config/requirements-plugins.txt`** (path = `<config_dir>/requirements-plugins.txt`,
   config_dir from `--config`): create from `.example` (or empty) if missing;
   **dedup** — if a line already references the same package/namespace, replace it
   (and say so); otherwise append. Preserve comments/other lines.
4. Unless `--save-only`: freeze the current environment to a temp constraints file
   (`{sys.executable} -m pip list --format=freeze`, exactly like
   `deploy/install.sh`) and run `{sys.executable} -m pip install -c <temp>
   <requirement>` — so a plugin can never move core's pinned deps (fails loud).
5. Print success + the config snippet to add (e.g. `type = "pool.monitor"`), and a
   reminder that the plugin loads on next `led-ticker` start.

**Flags:**

- `--source git|pypi` — pick which catalog source (default: first; error if absent).
- `--unpinned` — write `@main` / bare PyPI name instead of the catalog `ref`/version.
- `--save-only` — only update `requirements-plugins.txt`, skip pip install (the
  Docker/declarative workflow: edit the file, rebuild the image).
- `--dry-run` — print the requirement, the file edit, and the pip command; change
  nothing.
- `--config P` — locate `requirements-plugins.txt` + config dir (same resolution
  as `validate`/`run`).

**pip invocation:** always `sys.executable -m pip` via `subprocess.run`; surface
pip's exit code (nonzero → CLI exits nonzero with pip's stderr). The CLI never
imports pip.

## Component 3 — close the UX loop

Update the plugin-not-installed hint (`src/led_ticker/_plugin_hint.py`, the single
update point identified in review) so the suggested next step is
`led-ticker plugin install <namespace>` instead of "edit
config/requirements-plugins.txt and reinstall". Error → exact command.

## Component 4 — docs

- New docs-site page (or a section on the existing Plugins page) documenting
  `plugin status/list/search/install`, the source/pin/`--save-only` flags, and the
  Docker vs bare-metal note. Fact-pack style consistent with `docs/DOCS-STYLE.md`.
- The auto-rendered catalog table on the docs site is **slice D** — not here.

## Targets / non-goals

- **Targets bare-metal/dev** (a mutable venv). Docker is read-only at runtime, so
  Docker users run `install --save-only` then rebuild; documented.
- **No network, no remote catalog, no PyPI publishing** in this slice.
- **No uninstall/update commands** in v1 (YAGNI; add later if needed).

## Tests (`tests/test_plugins/test_catalog.py`, `test_plugin_cli.py`)

- **Catalog integrity:** the bundled `plugins_catalog.json` parses; `schema_version`
  is 1; every entry has name/namespace/summary/sources; every source is a valid
  git/pypi shape; the three first-party namespaces are present with the expected
  `provides`. (Guards against a malformed hand-edited catalog.)
- **`requirement()`:** git pinned/unpinned, pypi pinned/unpinned, url
  normalization to `git+https://….git@ref`.
- **`search`/`get`:** case-insensitive substring over name/summary/provides.
- **`install` (pip subprocess + filesystem mocked, no network):**
  - catalog name → correct requirement appended to `requirements-plugins.txt` +
    correct `pip install -c <constraints> <req>` invoked.
  - `--unpinned` → `@main`.
  - `--source pypi` on a git-only entry → clear error.
  - raw spec mode (`git+https://…`, `foo==1.0`) → installed verbatim, file line
    verbatim.
  - `--save-only` → file updated, pip NOT invoked.
  - `--dry-run` → nothing changed, plan printed.
  - dedup → re-installing the same plugin replaces (not duplicates) its line.
  - missing `requirements-plugins.txt` → created.
  - pip nonzero exit → CLI exits nonzero, surfaces stderr.
- **`status`/alias:** `plugin status` output equals the old `plugins`; `plugins`
  prints a deprecation note and still works.
- **Hint:** `_plugin_hint` text now contains `led-ticker plugin install`.
- **Hermetic:** reuse the autouse entry-point stub; mock `subprocess.run` for pip;
  use `tmp_path` configs. No real install, no network.
- Full suite + ruff + pyright + docs-lint green.

## Out of scope (separate specs)

- C: PyPI Trusted-Publishing in the plugin repos.
- D: docs-site auto-rendered catalog table; broader hint/UX polish.
- `plugin uninstall` / `plugin update`; remote/live catalog; non-first-party
  third-party submission flow.
