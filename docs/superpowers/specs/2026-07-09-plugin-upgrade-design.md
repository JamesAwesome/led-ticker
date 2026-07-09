# Plugin upgrade through reconcile — design

**Date:** 2026-07-09
**Status:** approved (brainstorm with James)

## Problem

Upgrading an installed plugin currently requires destroying the plugin volume
(`docker compose down -v`). The startup reconcile (`plugin_reconcile.py`) only
detects version drift for exact PyPI `==X.Y.Z` pins (`_exact_pin`); git-source
lines — both deliberate ref edits (`@pool-v0.1.0` → `@pool-v0.2.0`) and
branch-tracking lines whose upstream moved (`@main`) — are silent no-ops. The
first-party plugins install from git, so in practice no upgrade path exists.
Additionally there is no user-facing "upgrade" verb in the CLI or web UI.

## Decisions made during brainstorming

- **Failing cases to solve:** git line with an edited ref, and git line
  tracking `@main`/a branch. (PyPI pins already reinstall on drift; unpinned
  PyPI lines get fixed as a side effect.)
- **`@main` refresh trigger:** an explicit upgrade verb (CLI + web UI), not
  boot-time remote checks and not always-reinstall.
- **Web UI upgrade:** in scope for this work.
- **Upgrade target for pinned lines:** the verb queries the remote for the
  latest version (git tags / PyPI JSON) rather than requiring an explicit
  `--to` target or the bundled catalog's (stale-bound) recommendation.
- **Approach:** pure declarative (Approach A). The upgrade verb always
  rewrites the manifest line to a concrete pin; reconcile detects the line
  change via an installed-state stamp. No side-channel marker file, no
  force-reinstall semantics. A `@main` line becomes a pinned line on its
  first upgrade — with explicit-verb upgrades, branch tracking no longer does
  anything an upgrade-time pin doesn't, and rebuilt volumes become
  reproducible from the manifest alone.

## Architecture

Three layers, independently testable:

### 1. Reconcile stamp (display container, boot path, no network beyond pip)

- New file `/data/plugins/installed.json` (beside the volume venv): a JSON
  object `{namespace: requirement_line}` recording the exact manifest line
  each namespace was last successfully installed from.
- `reconcile()` updates the stamp after each successful install (and removes
  entries on successful uninstall).
- Per declared+installed namespace, reconcile compares the stamped line to the
  current manifest line; any difference adds the namespace to `to_install`
  (pip reinstalls in place under the new line, via the existing grouped-
  install path with core constraints).
- The `_exact_pin` version-drift block is retired; the stamp subsumes it and
  additionally covers git refs, source switches, and comment-preserving
  rewrites. Line comparison is on the requirement portion of the line
  (trailing `#` comments stripped) so provenance comments don't churn.
- **Migration / missing stamp** (first boot after this ships, or after a
  volume reset): treat declared+installed namespaces as in sync and write the
  stamp from the current manifest lines. No churn on existing deployments.
- Honors reconcile's existing contracts: never raises, failures become
  `PluginAction(action="failed")`, the panel always boots.

### 2. Resolver (`plugin_cmd.py`, CLI/webui context, network allowed)

`resolve_latest(requirement_line) -> str` — pure function of the line plus
the network; no manifest knowledge.

- **PyPI lines** (pinned or unpinned): GET `https://pypi.org/pypi/<pkg>/json`,
  pick the highest non-yanked, non-prerelease version using
  `packaging.version`, return `pkg==<version>`.
- **Git lines:** `git ls-remote --tags <url>`, filter tags matching the
  monorepo convention `<name>-vX.Y.Z`, pick the highest version, return the
  line with `@<tag>`. The `<name>` prefix is determined in order: (1) the
  basename of `#subdirectory=` if present, (2) the catalog entry name for the
  namespace, (3) if neither yields matching tags, plain `vX.Y.Z` tags are
  accepted (single-plugin repos). If no tags match at all, fall back to the
  branch-tip commit SHA (`ls-remote <url> <branch>`), preserving
  `#subdirectory=` and any extras.
- The tag convention is stated in user docs so third-party git plugins know
  what the verb expects.

### 3. Verb surfaces

Both surfaces: resolve latest → compare against the current line/stamp → if
unchanged, report "already up to date" and write nothing → else atomically
rewrite the manifest line (existing `_update_manifest_atomic` + lock + backup
convention), appending a provenance comment
(`# upgraded 2026-07-09, was @main`) → report "restart to apply". Neither
surface runs pip; the privileged install happens in boot reconcile.

- **CLI:** `led-ticker plugin upgrade <namespace>` and
  `led-ticker plugin upgrade --all`.
- **Web UI:** `POST /api/store/upgrade` (`{"namespace": ...}`), token-gated
  exactly like install/remove (no token → 403 "editing disabled"). The store
  UI gets an Upgrade button that then lights the existing restart affordance.

## Data flow (round trip)

1. User clicks Upgrade / runs `plugin upgrade pool`.
2. Resolver fetches latest for the current manifest line; up-to-date is a
   no-op response.
3. Manifest rewritten atomically with provenance comment.
4. User restarts (existing restart button / `docker compose restart`).
5. Boot reconcile: manifest line ≠ stamp → pip install new line under core
   constraints → stamp updated.

## Error handling

- **Resolver failure** (network, no matching tags, unparseable versions): the
  verb fails loudly *before* touching the manifest — CLI nonzero exit +
  message; webui JSON error. The manifest never points at something
  unresolved.
- **Pip failure at boot** (bad tag, Pi offline): existing semantics —
  `PluginAction("failed")`, logged, old version stays installed (reinstall in
  place only replaces on success). Stamp updates only on pip success, so
  every boot retries until it works.
- **Stamp corrupt/unwritable:** treat as missing (warn, re-stamp from current
  state); never raises.
- **Shared packages** (one dist, many namespaces — e.g. led-ticker-flair):
  upgrading any member namespace rewrites the single shared line; the
  existing install-group dedup runs pip once; the stamp records the same line
  for every covered namespace.

## Testing

- **Reconcile unit tests** (beside the existing suite): stamp
  write/read/corrupt/missing-migration; line change → reinstall; unchanged
  line → no churn every boot (explicit tripwire — this property is why
  `_exact_pin` rejected non-exact lines); uninstall removes stamp entry;
  shared-package single pip run preserved; comment-only edits don't churn.
- **Resolver tests** (mocked network/subprocess): PyPI JSON parsing with
  yanked/prerelease filtering; `ls-remote` tag parsing under the
  `<name>-vX.Y.Z` convention; SHA fallback; failure → no manifest write.
- **Webui endpoint tests** (mirroring install_handler's suite): token gating,
  atomic rewrite + provenance comment, already-up-to-date no-op, resolver
  error propagation.
- **End-to-end behavioral** (no network): seed manifest + stamp that
  disagree, run `reconcile()` with a stubbed pip runner, assert reinstall +
  stamp update.

## Out of scope

- Live plugin hot-reload (upgrade applies on restart via the existing
  restart-marker flow).
- Downgrades / pinning to an arbitrary older version from the web UI (the
  manifest remains hand-editable for that; the stamp makes any hand edit
  effective, which is itself a fix).
- Automatic/scheduled upgrade checks.
