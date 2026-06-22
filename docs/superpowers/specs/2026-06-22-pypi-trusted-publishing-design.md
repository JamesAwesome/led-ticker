# PyPI Trusted Publishing — Design

**Date:** 2026-06-22
**Status:** Approved (brainstorm)
**Scope:** Automated, token-less publishing of led-ticker packages to PyPI via GitHub Actions + Trusted Publishing (OIDC).

## Goal

Make `pip install ledticker` (and the data plugins) work from PyPI, published automatically from CI/CD on a GitHub Release, with **no long-lived API tokens** (OIDC Trusted Publishing) and a **manual approval gate** before every upload. This is the maintainer's first PyPI publish, so the design includes the one-time PyPI-side setup steps.

## Decisions (settled in brainstorm)

1. **Scope:** publish **7 projects** — core + the 6 *original* data plugins. The 4 homage plugins stay GitHub-install-only.
2. **Target:** **real PyPI** (not TestPyPI), gated behind a **manual-approval GitHub environment**.
3. **Trigger:** **GitHub Releases** (`on: release: published`); the release tag identifies the package.
4. **Versioning:** **manual** `version` in each `pyproject.toml`; the workflow **guards that the release tag matches the package version** and fails loudly on mismatch. (Dynamic/`git describe` versioning is rejected — it misbehaves in a monorepo with per-package tags.)
5. **Core PyPI name:** **`ledticker`** (the PyPI name `led-ticker` was registered 2026-06-22 by an unrelated BLE project; PEP 541 does not apply). The Python import package (`led_ticker`) and the `led-ticker` CLI entry point are **unchanged** — only the distribution name changes. Every plugin's `led-ticker` dependency is repointed to `ledticker`.

## Packages

| PyPI name | Repo | Source dir | Current version |
|-----------|------|-----------|-----------------|
| `ledticker` | led-ticker | repo root | 2.0.0 |
| `led-ticker-pool` | led-ticker-plugins | `plugins/pool` | 0.1.0 |
| `led-ticker-baseball` | led-ticker-plugins | `plugins/baseball` | 0.1.0 |
| `led-ticker-crypto` | led-ticker-plugins | `plugins/crypto` | 0.2.0 |
| `led-ticker-calendar` | led-ticker-plugins | `plugins/calendar` | 0.1.0 |
| `led-ticker-rss` | led-ticker-plugins | `plugins/rss` | 0.2.0 |
| `led-ticker-weather` | led-ticker-plugins | `plugins/weather` | 0.2.0 |

All 6 plugin names + `ledticker` are confirmed **available** on PyPI (checked 2026-06-22).

**Homage plugins NOT published** (stay GitHub-only): `nyancat`, `pokeball`, `pacman`, `sailor_moon`.

## 1. Naming + metadata changes (code)

### Core repo (`led-ticker`)
- `pyproject.toml`: `name = "led-ticker"` → **`name = "ledticker"`**.
- Add `readme = "README.md"`.
- Add `license = "MIT"` + `license-files = ["LICENSE"]` (SPDX / PEP 639 form). **Do NOT also add the `License :: OSI Approved :: MIT License` classifier** — mixing the SPDX field with the license classifier triggers a deprecation warning/error on modern build backends. (Verify the repo's build backend supports PEP 639; if not, fall back to the license classifier + omit the SPDX field. Confirm the backend in the plan.)
- Add `classifiers` (see below).
- Add `[project.urls]`: `Homepage = "https://docs.ledticker.dev"`, `Repository = "https://github.com/JamesAwesome/led-ticker"`, `Issues = "https://github.com/JamesAwesome/led-ticker/issues"`.
- Confirm the `led-ticker` CLI entry point (`[project.scripts]`) and `led_ticker` import package are **unchanged**.

### Plugins repo (`led-ticker-plugins`), each of the 6 data plugins
- `dependencies`: `"led-ticker"` → **`"ledticker>=2.0"`** (floor at core's 2.0 line).
- Add `license = "MIT"` + `license-files = ["LICENSE"]` (the repo's MIT LICENSE; same PEP 639 guidance + no license classifier as core above).
- Add `classifiers`.
- Add `[project.urls]`: Homepage = docs, Repository = the monorepo, Issues = the monorepo issues.
- `readme` already present.

### Classifiers (all 7)
```
"Development Status :: 4 - Beta",
"Programming Language :: Python :: 3",
"Programming Language :: Python :: 3.14",
"Operating System :: POSIX :: Linux",
"Topic :: Multimedia :: Graphics",
```
(No `License ::` classifier — the license is declared via the SPDX `license` field per PEP 639; see the license note above.)

### Non-PyPI-name fallout to check
- Anything that depended on the *distribution* name `led-ticker` (not the import) must move to `ledticker`: the plugins' `dependencies`, and any `requirements*.txt` / constraints / docs that say `pip install led-ticker` for the PyPI package. The **git+https** install instructions and the import/CLI references stay as-is.

## 2. Publish workflows

A standalone `.github/workflows/publish.yml` in **each** repo. Shared shape:

```yaml
on:
  release:
    types: [published]
permissions:
  contents: read
  id-token: write          # OIDC — the Trusted Publishing token
jobs:
  publish:
    runs-on: ubuntu-latest # GitHub-hosted, NOT self-hosted — isolation for publish
    environment: release   # manual-approval gate (see §3)
    steps:
      - uses: actions/checkout@<pinned-sha>
      - <determine package + dir from the release tag>
      - <guard: tag version == pyproject version, else fail>
      - <build sdist + wheel with `python -m build` (or `uv build`)>
      - uses: pypa/gh-action-pypi-publish@<pinned-sha>   # OIDC, no tokens; packages-dir set to the built dist
```

### Core (`led-ticker/.github/workflows/publish.yml`)
- Tag form: **`vX.Y.Z`**.
- Guard: `vX.Y.Z` minus the leading `v` must equal the `version` in repo-root `pyproject.toml`.
- Build the repo root; publish `ledticker`.

### Plugins (`led-ticker-plugins/.github/workflows/publish.yml`)
- Tag form: **`<plugin>-vX.Y.Z`**.
- Parse `<plugin>` from the tag; map to `plugins/<plugin>`.
- **Allowlist** the 6 data plugins (`pool baseball crypto calendar rss weather`). A homage-plugin tag (`nyancat-*` etc.) **fails fast** with: "This plugin is GitHub-install-only and is not published to PyPI."
- Guard: tag version == `plugins/<plugin>/pyproject.toml` version.
- Build only that plugin dir; publish.

### Notes
- Pin all third-party actions to a commit SHA (repo convention; matches `ci.yml`).
- Use a single `dist/` for the built artifacts; pass it to `gh-action-pypi-publish` via `packages-dir`.
- Publishing runs on `ubuntu-latest` (GitHub-hosted) — never the self-hosted runner — both for OIDC trust and to keep build/publish off the production VM.

## 3. Manual-approval gate (GitHub environment)

A **`release` environment** in each repo with **required reviewer = the maintainer**. The `publish` job references `environment: release`, so after the build step the run **pauses for one-click approval** before `gh-action-pypi-publish` uploads. The maintainer can inspect the built artifacts / logs first. Environments are created via API or Settings → Environments.

## 4. PyPI-side setup (maintainer, one-time)

Provided as exact click-steps at implementation time. Summary:
1. Create a PyPI account; **enable 2FA** (mandatory to publish).
2. Add a **pending Trusted Publisher** for each of the 7 projects (PyPI → *Your projects* / *Publishing* → *Add a pending publisher*). For each, set:
   - PyPI Project Name: the table name above.
   - Owner: `JamesAwesome`.
   - Repository name: `led-ticker` (core) or `led-ticker-plugins` (the 6 plugins).
   - Workflow filename: `publish.yml`.
   - Environment name: `release`.
3. First successful workflow run for each project creates the project on PyPI — **no API token is ever created or stored**.

## 5. First-publish sequence

1. Land the metadata/workflow changes (this spec's implementation) in both repos.
2. Maintainer completes §4 (account, 2FA, 7 pending publishers) + §3 (environments).
3. **Publish core first** (`ledticker`) — plugins depend on it, so it must exist on PyPI for plugin installs to resolve:
   - Confirm/bump core version; create GitHub Release tagged `vX.Y.Z`; approve; verify on PyPI.
4. **Publish the 6 plugins** — for each: confirm version; create Release `<plugin>-vX.Y.Z`; approve; verify.

## 6. Verification

- Per package: in a clean virtualenv, `pip install <name>` resolves **from PyPI** (not git) and imports.
- For a plugin: `pip install led-ticker-pool` pulls **`ledticker`** transitively and the plugin registers via its entry point.
- The PyPI project page shows the README, license, and URLs (metadata sanity).

## 7. Non-goals / YAGNI

- TestPyPI (rejected — awkward for dependency resolution; the approval gate is the safety net).
- Automated version bumping tooling (manual now).
- Publishing the 4 homage plugins.
- Renaming the import package or CLI (only the *distribution* name changes).
- Dynamic/VCS-derived versioning (breaks in the monorepo).

## 8. Risks / open items

- **Existing plugin tags** (`baseball-v0.1.0` etc.) have no GitHub Release yet; the first publish creates Releases (on existing or new tags). Re-publishing an already-uploaded version to PyPI is impossible — version bumps are required for any re-release.
- **`ledticker` brand vs `led-ticker`**: docs/README should note the PyPI name is `ledticker` (distinct from the unrelated BLE `led-ticker`), to avoid user confusion.
- **Self-hosted CI interaction:** the existing `ci.yml` is self-hosted; `publish.yml` is intentionally GitHub-hosted and separate, so no interaction.
