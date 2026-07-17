# Release order guard: monotonic versions on monotonic history — Design

**Date:** 2026-07-16 (late)
**Repos:** led-ticker (core) + led-ticker-plugins (companion change)
**Status:** approved (brainstormed after the v4.16.1/v4.17.0 incident)

## Incident (why)

Two parallel work sessions each cut a core release: one shipped **v4.17.0** (00:06), then a background pipeline from the other session — executing a plan written ~40 minutes earlier with "vNext = 4.16.1" baked in — cut **v4.16.1 on a NEWER commit** (00:45). Result: a lower version number containing strictly more code (all of 4.17.0 + the #405 freeze fix), while resolver-visible "latest" (4.17.0) lacked the fix. Remediated by cutting v4.17.1 and annotating v4.16.1 superseded; PyPI yank of 4.16.1 is a manual owner action (requires PyPI login).

Nothing in the pipeline checks version ORDER: the only existing guard is exact-tag (`tag == hatch-vcs-derived version`, a typo/wrong-commit net). The same gap permits the mirror failure — a HIGHER version tagged on OLDER code — which would be equally wrong.

## The invariant

**Version order must equal commit-ancestry order.** For any two releases of a package: `version(A) > version(B)` ⇔ `commit(B)` is an ancestor of `commit(A)`. The project is trunk-only (decided: no backport/maintenance releases; no escape hatch — a genuine future backport is a conscious one-line workflow edit).

## Design: three complementary layers

### A — CI backstop (publish.yml, both repos) — the layer that cannot be forgotten

A guard step AFTER the existing exact-tag guard, BEFORE build/upload (checkout already has `fetch-depth: 0`):

1. **Monotonic:** the new tag's version is strictly greater (PEP 440; the project uses plain `X.Y.Z` triples) than every existing release tag of the SAME package — core: all `v*` tags; plugins: the `<name>-v*` family only.
2. **Ancestry:** the previous-latest release tag's commit is an ancestor of the new tag's commit (`git merge-base --is-ancestor PREV NEW`).

Fail → `::error::` naming both versions/commits and the remedy ("cut vNEXT on the current main tip") → exit 1 → no upload. First release of a package (no prior tags) passes trivially.

**Logic is a pure, unit-tested function; the workflow is a thin caller.**
- Core: `scripts/release_guard.py` — `check_release_order(new_tag: str, existing_tags: list[str], is_ancestor: Callable[[str, str], bool]) -> str | None` (None = OK, str = failure reason). Workflow runs `python scripts/release_guard.py "$TAG"` which gathers tags via `git tag -l 'v*'` and shells `git merge-base --is-ancestor`. Tests in `tests/test_release_guard.py`: newer-version-newer-commit OK; lower-version-newer-commit FAIL (the incident); higher-version-older-commit FAIL (the mirror); equal version FAIL; first-release OK; non-X.Y.Z tag in history ignored/tolerated.
- Plugins: extend `scripts/check_release.py` (already the tag→dir authority, already invoked by its publish.yml) with the same pure function, family-scoped: for tag `stocks-v0.7.0`, existing = `stocks-v*` only. Same test shapes in the monorepo's script tests.

### B — cut-time tool (both repos) — the layer that prevents

`scripts/cut_release.py` (invoked `uv run python scripts/cut_release.py [name] <patch|minor|major> --notes FILE`):
1. `git fetch origin --tags` — the version base is the LIVE remote at execution time, never a value carried in a plan (the incident's root cause).
2. Compute latest existing version for the package (family-scoped in the monorepo) → bump by the requested level.
3. Assert the guard (same pure function) against `origin/main`'s tip as the target commit.
4. `gh release create <tag> --target <origin/main sha> --title ... --notes-file ...`.
5. Print the created URL. Refuses to run with a dirty index? — not needed (targets origin/main by SHA, local state irrelevant).

Agents, background pipelines, and humans use this instead of raw `gh release create`. Background pipelines get correct-by-construction versions no matter how stale their plan is.

### C — process encoding — the layer that explains

- Memory (`project_release_automation.md` + the incident note): vNext is derived at cut time from the live remote; parallel sessions exist; use `cut_release.py`.
- The monorepo `publishing-a-plugin` skill's release-mode step 2 ("git tag -l | sort -V → new one must be strictly higher") is updated to: use `scripts/cut_release.py`, which does the derivation + guard; manual tagging documented as discouraged.
- RELEASING.md (both repos, wherever the runbook lives): the tool is the documented path.

## Explicitly out of scope

- Full auto-versioning (release-please / merge-triggered) — remains the existing deferred board item; this fix neither blocks nor implements it.
- PyPI-side checks (querying PyPI for published versions) — git tags are the project's source of truth and are atomically created; PyPI lags and adds a network dependency to the guard.
- Yanking v4.16.1 — manual owner action on PyPI (documented in the incident notes).
- Pre-release/dev version schemes — the project uses plain X.Y.Z; the guard rejects anything else for NEW tags (existing malformed tags in history are ignored, not fatal).

## Testing

Pure-function unit tests both repos (shapes listed under A). Workflow-level: not CI-testable without cutting releases; the thin-caller pattern keeps the untested surface to argv/shell plumbing. `cut_release.py`: unit-test version-bump + guard invocation with a fake `gh`/git boundary (or factor compute-next as pure and test that); the `gh release create` call itself stays thin.

## Rollout

Core PR + plugins PR (independent, no ordering constraint). For `release` events GitHub runs the workflow file **as of the tagged commit** — so the guard protects every release whose tagged commit contains it, i.e. every trunk-tip release cut after the PR merges. (A malicious/mistaken tag on an OLD commit would run the old guard-less workflow — but such a tag is exactly a version-order violation on old code, and the exact-tag hatch-vcs guard already rejects most of that shape; residual risk accepted for a solo-maintainer trunk-only repo.)
