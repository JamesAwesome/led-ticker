# Plugin manifest management — Docker-first add/remove (registry slice 1b)

**Date:** 2026-06-15
**Goal:** Make `led-ticker plugin` a clean manifest manager so a Docker-only user
never touches pip. Add declarative `add` / `remove` verbs that edit
`config/requirements-plugins.txt` only, give `install` a symmetric `uninstall`,
let `list` show what's **declared** vs **installed**, and deprecate the awkward
`install --save-only` escape hatch.

**Stacks on** PR #217 (plugin catalog + `plugin status/list/search/install`).
Branch `feat/plugin-manifest-mgmt` is cut from `feat/plugin-catalog-cli`; rebases
onto main once #217 merges.

## Mental model

- **`add` / `remove`** manage the **manifest** (`requirements-plugins.txt`) — the
  Docker-native path (the image build installs from the manifest; the runtime
  container is read-only). No pip.
- **`install` / `uninstall`** also touch the **environment** (pip) — bare-metal/dev.

| Command | Manifest | pip | Audience |
|---|---|---|---|
| `plugin add <name\|spec>` | + line | — | Docker (then rebuild) |
| `plugin remove <name\|spec>` | − line | — | Docker (then rebuild) |
| `plugin install <name\|spec>` | + line | install | bare-metal/dev |
| `plugin uninstall <name\|spec>` | − line | uninstall | bare-metal/dev |

## Decisions (from brainstorming)

1. Verb model: `add`/`remove` (file-only) + `install`/`uninstall` (file+pip).
2. Include `uninstall`, the `list` declared/installed markers, and the
   `--save-only` deprecation (all three).
3. `remove` is manifest-only; `uninstall` is the pip one (mirrors `add`/`install`).
4. `uninstall` pip-uninstalls by the **distribution name** derived from the dedup
   key (e.g. `led-ticker-pool`).

## Behavior

All verbs resolve a **catalog name or raw pip spec** (with the typo "did you
mean?" guard from #217) and share #217's path resolution: default
`config/requirements-plugins.txt`, `--config` override, warn when writing outside
a `config/` directory. They dedup by `_requirement_key` and preserve inline
comments.

### `plugin add <name|spec>`

Exactly today's `install --save-only`: resolve → append/replace the manifest line
(dedup, carry inline comment) → print the resolved path + a **"run
`docker compose up -d --build` (or rebuild/redeploy) to apply"** reminder. No pip.
Flags: `--source`, `--unpinned`, `--dry-run`, `--config`.

### `plugin remove <name|spec>`

New `_remove_requirement(path, key) -> removed_line | None`:

- Compute the dedup key: a catalog name → `_requirement_key(entry.requirement())`
  (e.g. `pool` → `led-ticker-pool`); a raw spec → `_requirement_key(spec)`.
- Drop the manifest line(s) whose `_requirement_key` matches; preserve comments
  and unrelated lines; write back.
- Print `Removed '<line>' from <path>` + the rebuild reminder; if no line
  matched, print `'<name>' is not in <path>.` and exit 0 (idempotent). No pip.
- Flags: `--config`, `--dry-run`.

### `plugin install <name|spec>`

Unchanged from #217 (add + constrained pip install). `--save-only` now prints a
deprecation note and routes to `add`.

### `plugin uninstall <name|spec>`

`remove` (manifest) **plus** `pip uninstall -y <dist>` where `<dist>` is the dedup
key. That key equals the installed distribution name under the first-party
"git repo stem == package name" convention; a raw git spec whose repo dir differs
from its pyproject `name` would pip-uninstall the wrong name (pip no-ops with
"not installed") — the manifest line is still removed correctly. Surfaces pip's
exit code; a "not installed" pip result is reported but not treated as a hard
failure. Flags: `--config`, `--dry-run`.

### `plugin list`

Each catalog entry is annotated:

- `[declared]` — its requirement key appears in the manifest (installs on next
  build). Read from the resolved `config/requirements-plugins.txt` (same path
  resolution as install/add; `--config` to override).
- `[installed]` — importable now (entry-point present, via the #217
  `_installed_namespaces()`).

So a Docker user runs `plugin list` and sees what the next build will include.
`list` gains a `--config` flag for the manifest lookup; absent/unreadable manifest
→ nothing marked `[declared]` (no error).

## Implementation

- `src/led_ticker/app/plugin_cmd.py`:
  - Extract a shared `_resolve_requirement(target, catalog, *, source, pinned) ->
    (requirement, entry) | (None signalling a handled error/return code)` used by
    `add` and `install` (catalog vs raw + did-you-mean + `--source` guard).
  - `cmd_add(...)` — the file-only path (factor out of the current `cmd_install`
    write/echo/warn block; `cmd_install` calls `cmd_add` then pip).
  - `_remove_requirement(path, key)`; `_dist_key(target, catalog)` →
    distribution name for removal + pip uninstall.
  - `cmd_remove(...)`, `cmd_uninstall(...)`, `_pip_uninstall(dist)`.
  - `cmd_list` reads the manifest and adds `[declared]`.
- `src/led_ticker/app/cli.py`: `add` / `remove` / `uninstall` sub-sub-parsers
  (with `--config`, `--dry-run`, and `add`'s `--source`/`--unpinned`); `list`
  gains `--config`; `install --save-only` → deprecation note + `cmd_add`.
- Docs: plugins page leads with the Docker flow (`add` → rebuild) then bare-metal
  (`install`); CLI reference documents all four verbs, the `list` markers, and the
  `--save-only` deprecation.

## Tests (hermetic — pip mocked, tmp configs, entry-point stub)

- `add`: writes the manifest line, pip NOT invoked; dedup + comment carry; config/
  default + warn; `--dry-run`.
- `remove`: drops the matching line (catalog name and raw spec), preserves
  comments/other lines, pip NOT invoked; not-found message + exit 0; `--dry-run`.
- `uninstall`: removes the line AND calls `pip uninstall -y <dist>` with the right
  dist; surfaces pip exit code; not-in-manifest still attempts pip uninstall.
- `list`: `[declared]` for a manifest entry, `[installed]` via stubbed entry
  points, both/neither; missing manifest → no `[declared]`, no error.
- `install --save-only`: prints deprecation note, behaves as `add` (no pip).
- argv→`main()` dispatch for `add` / `remove` / `uninstall` (incl. the config/
  default for a `--config`-less `add`).
- Full suite + ruff + pyright + docs-lint green.

## Non-goals

- No auto-running `docker compose` / rebuild from the CLI (just the reminder).
- No remote catalog, no PyPI publishing (slices C/D).
- No `plugin upgrade`/version bump command (YAGNI; re-`add`/`install` replaces the
  pin).
