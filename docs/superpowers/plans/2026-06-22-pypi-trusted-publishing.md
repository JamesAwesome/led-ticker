# PyPI Trusted Publishing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish `ledticker` (core) + 6 data plugins to PyPI automatically from GitHub Releases via OIDC Trusted Publishing, gated by a manual approval environment.

**Architecture:** Two standalone `publish.yml` workflows (one per repo) trigger on `release: published`, parse the tag to identify the package, guard that the tag matches the package's pyproject version, build with `uv build`, and upload via `pypa/gh-action-pypi-publish` (OIDC, no tokens) behind a required-reviewer `release` environment. Metadata (name, license, classifiers, URLs) is brought up to PyPI standard. Core's PyPI distribution name becomes `ledticker` (import `led_ticker` + `led-ticker` CLI unchanged). Maintainer-side PyPI/account setup is a runbook, not code.

**Tech Stack:** Python 3.14, hatchling build backend, uv, GitHub Actions, `pypa/gh-action-pypi-publish`, PyPI Trusted Publishing (OIDC).

**Spec:** `docs/superpowers/specs/2026-06-22-pypi-trusted-publishing-design.md`

## Global Constraints

- **Core PyPI distribution name = `ledticker`** (NOT `led-ticker` — taken). The Python import package `led_ticker` and the `led-ticker` CLI entry point (`[project.scripts] led-ticker = "led_ticker.app:main"`) are UNCHANGED.
- **Plugins publish scope = 6 DATA plugins only:** `pool baseball crypto calendar rss weather`. Homage plugins (`nyancat pokeball pacman sailor_moon`) are NEVER published — the plugins workflow must fail-fast on their tags.
- **Plugin dependency on core:** `"led-ticker"` → `"ledticker>=2.0"`.
- **License:** SPDX `license = "MIT"` + `license-files = ["LICENSE"]` (PEP 639; hatchling supports it). Do NOT add the `License :: OSI Approved :: MIT License` classifier (deprecated mix).
- **Each published plugin must bundle its own `LICENSE`** — copy the monorepo-root `LICENSE` into each `plugins/<name>/`.
- **Publish workflows run on `ubuntu-latest` (GitHub-hosted), NEVER `self-hosted`** — OIDC trust + keep publishing off the production VM.
- **Pin every GitHub Action to a commit SHA** with a trailing `# vX` comment (repo convention, see `ci.yml`).
- **Tag-vs-version guard must fail loudly** (non-zero exit + clear message) on any mismatch.
- **Workflow permissions:** `id-token: write` + `contents: read` only.
- NON-GOALS: TestPyPI; dynamic/VCS versioning; publishing homage plugins; renaming the import package or CLI; automated version bumping.

## Repos & Worktrees

- **CORE** (`led-ticker`): worktree `/Users/james/projects/github/jamesawesome/led-ticker-worktrees/pypi`, branch `feat/pypi-trusted-publishing` (already holds the spec commit). **Tasks 1–3, 7.**
- **PLUGINS** (`led-ticker-plugins`): create a fresh worktree off `origin/main` (which contains the root `LICENSE` from PR #8 — the existing local checkout is stale). **Tasks 4–6.**
- Two repos → **two branches → two PRs.**

## File Structure

**CORE repo:**
- `pyproject.toml` — MODIFY: name→ledticker, add readme/license/license-files/classifiers/urls (Task 1).
- `scripts/check_release_version.py` — CREATE: tag-vs-version guard (Task 2).
- `tests/test_check_release_version.py` — CREATE: guard unit tests (Task 2).
- `.github/workflows/publish.yml` — CREATE: release→build→guard→publish (Task 3).
- `docs/RELEASING.md` — CREATE: maintainer runbook (Task 7).

**PLUGINS repo:**
- `plugins/<name>/pyproject.toml` ×6 — MODIFY: dep→ledticker>=2.0, add license/license-files/classifiers/urls (Task 4).
- `plugins/<name>/LICENSE` ×6 — CREATE: copy of root LICENSE (Task 4).
- `scripts/check_release.py` — CREATE: tag parse + allowlist + version guard (Task 5).
- `tests/test_check_release.py` — CREATE: unit tests (Task 5).
- `.github/workflows/publish.yml` — CREATE: release→parse→guard→build→publish (Task 6).

---

## Task 1: Core pyproject → `ledticker` + PyPI metadata

**Files:**
- Modify: `pyproject.toml` (core worktree)

**Interfaces:**
- Produces: distribution name `ledticker` v2.0.0; `[project.urls]`; SPDX license. Consumed by Task 3 (build) and by the plugins' `ledticker>=2.0` dependency.

- [ ] **Step 1: Edit `[project]`** — change `name` and add metadata fields. Replace:
```toml
[project]
name = "led-ticker"
version = "2.0.0"
description = "Asyncio LED matrix display for news, weather, crypto, and more"
requires-python = ">=3.14"
authors = [
    { name = "James Awesome", email = "james@morelli.nyc" },
]
```
with:
```toml
[project]
name = "ledticker"
version = "2.0.0"
description = "Asyncio LED matrix display for news, weather, crypto, and more"
readme = "README.md"
license = "MIT"
license-files = ["LICENSE"]
requires-python = ">=3.14"
authors = [
    { name = "James Awesome", email = "james@morelli.nyc" },
]
classifiers = [
    "Development Status :: 4 - Beta",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.14",
    "Operating System :: POSIX :: Linux",
    "Topic :: Multimedia :: Graphics",
]
```

- [ ] **Step 2: Add `[project.urls]`** immediately after the `[project.scripts]` block (after the `led-ticker = "led_ticker.app:main"` line):
```toml
[project.urls]
Homepage = "https://docs.ledticker.dev"
Repository = "https://github.com/JamesAwesome/led-ticker"
Issues = "https://github.com/JamesAwesome/led-ticker/issues"
```
Do NOT touch `[project.scripts]` (the `led-ticker` CLI stays) or `[tool.hatch.build.targets.wheel] packages = ["src/led_ticker"]` (the import stays `led_ticker`).

- [ ] **Step 3: Build and verify metadata**
```bash
cd <core-worktree>
rm -rf dist && uv build
```
Expected: `dist/ledticker-2.0.0.tar.gz` and `dist/ledticker-2.0.0-py3-none-any.whl` (note the **`ledticker-`** prefix, not `led_ticker-`).

- [ ] **Step 4: `twine check` (metadata renders cleanly on PyPI)**
```bash
uvx twine check dist/*
```
Expected: `PASSED` for both files.

- [ ] **Step 5: Confirm name, license, URLs, and unchanged import/CLI in the built metadata**
```bash
python -c "import zipfile,glob;print(zipfile.ZipFile(glob.glob('dist/*.whl')[0]).read('ledticker-2.0.0.dist-info/METADATA').decode())" | grep -iE "^Name:|^License|^Project-URL"
```
Expected: `Name: ledticker`; a `License-Expression: MIT` (or `License: MIT`) line; three `Project-URL:` lines. The wheel still contains `led_ticker/` (import unchanged) and a `led-ticker` console-script entry.

- [ ] **Step 6: Commit**
```bash
git add pyproject.toml
git commit -m "build: rename PyPI distribution to ledticker + add PyPI metadata"
```

---

## Task 2: Core release-version guard script + tests

**Files:**
- Create: `scripts/check_release_version.py` (core worktree)
- Test: `tests/test_check_release_version.py`

**Interfaces:**
- Produces: `parse_and_check(tag: str, pyproject_path: str) -> tuple[bool, str]` returning `(ok, message)`; CLI `python scripts/check_release_version.py <tag>` exits 0 on match, 1 on mismatch/malformed. Consumed by Task 3 (the workflow runs it).

- [ ] **Step 1: Write the failing test** — `tests/test_check_release_version.py`:
```python
import subprocess
import sys
import textwrap
from pathlib import Path

from scripts.check_release_version import parse_and_check


def _pyproject(tmp_path: Path, version: str) -> str:
    p = tmp_path / "pyproject.toml"
    p.write_text(textwrap.dedent(f"""
        [project]
        name = "ledticker"
        version = "{version}"
    """))
    return str(p)


def test_matching_tag_ok(tmp_path):
    ok, msg = parse_and_check("v2.0.0", _pyproject(tmp_path, "2.0.0"))
    assert ok is True, msg


def test_mismatched_tag_fails(tmp_path):
    ok, msg = parse_and_check("v2.0.1", _pyproject(tmp_path, "2.0.0"))
    assert ok is False
    assert "2.0.1" in msg and "2.0.0" in msg


def test_tag_without_v_prefix_fails(tmp_path):
    ok, msg = parse_and_check("2.0.0", _pyproject(tmp_path, "2.0.0"))
    assert ok is False


def test_cli_exit_codes(tmp_path):
    pp = _pyproject(tmp_path, "2.0.0")
    ok = subprocess.run([sys.executable, "scripts/check_release_version.py", "v2.0.0", pp])
    bad = subprocess.run([sys.executable, "scripts/check_release_version.py", "v9.9.9", pp])
    assert ok.returncode == 0
    assert bad.returncode == 1
```

- [ ] **Step 2: Run it to confirm it fails**
```bash
PYTHONPATH=. uv run --extra dev pytest tests/test_check_release_version.py -v
```
Expected: FAIL (`ModuleNotFoundError: scripts.check_release_version`).

- [ ] **Step 3: Implement `scripts/check_release_version.py`**
```python
"""Guard: the release tag (vX.Y.Z) must match pyproject's version. Exit 1 on mismatch."""

import sys
import tomllib


def parse_and_check(tag: str, pyproject_path: str = "pyproject.toml") -> tuple[bool, str]:
    if not tag.startswith("v"):
        return False, f"Tag {tag!r} must start with 'v' (expected vX.Y.Z)."
    tag_version = tag[1:]
    with open(pyproject_path, "rb") as f:
        version = tomllib.load(f)["project"]["version"]
    if tag_version != version:
        return False, (
            f"Release tag {tag!r} (version {tag_version}) does not match "
            f"pyproject version {version!r}. Bump the version or fix the tag."
        )
    return True, f"OK: tag {tag} matches pyproject version {version}."


def main() -> int:
    tag = sys.argv[1]
    pyproject = sys.argv[2] if len(sys.argv) > 2 else "pyproject.toml"
    ok, msg = parse_and_check(tag, pyproject)
    print(msg)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests to confirm pass**
```bash
PYTHONPATH=. uv run --extra dev pytest tests/test_check_release_version.py -v
```
Expected: 4 passed.

- [ ] **Step 5: Lint**
```bash
uv run --extra dev ruff check scripts/ tests/test_check_release_version.py
```
Expected: All checks passed.

- [ ] **Step 6: Commit**
```bash
git add scripts/check_release_version.py tests/test_check_release_version.py
git commit -m "build: add release tag-vs-version guard for publishing"
```

---

## Task 3: Core `publish.yml` workflow

**Files:**
- Create: `.github/workflows/publish.yml` (core worktree)

**Interfaces:**
- Consumes: `scripts/check_release_version.py` (Task 2); the `ledticker` build (Task 1). Requires the `release` GitHub environment + the PyPI pending publisher (Task 7 runbook).

- [ ] **Step 1: Create `.github/workflows/publish.yml`**
```yaml
name: publish

# Publishes `ledticker` to PyPI via OIDC Trusted Publishing when a GitHub
# Release is published. Runs on GitHub-hosted runners (NOT self-hosted) and
# is gated behind the `release` environment (required reviewer).
on:
  release:
    types: [published]

permissions:
  contents: read
  id-token: write   # OIDC token for Trusted Publishing — no API tokens

jobs:
  publish:
    runs-on: ubuntu-latest
    environment: release   # manual approval gate
    steps:
      - uses: actions/checkout@df4cb1c069e1874edd31b4311f1884172cec0e10 # v6
      - uses: astral-sh/setup-uv@fac544c07dec837d0ccb6301d7b5580bf5edae39 # v8.2.0
      - name: Guard tag matches pyproject version
        run: python scripts/check_release_version.py "${{ github.event.release.tag_name }}"
      - name: Build sdist + wheel
        run: rm -rf dist && uv build
      - name: Publish to PyPI (Trusted Publishing)
        uses: pypa/gh-action-pypi-publish@76f52bc884231f62b9a034ebfe128415bbaabdf1 # v1.12.4
        with:
          packages-dir: dist/
```

- [ ] **Step 2: Validate the YAML parses**
```bash
uv run --with pyyaml python -c "import yaml; d=yaml.safe_load(open('.github/workflows/publish.yml')); assert d['jobs']['publish']['runs-on']=='ubuntu-latest'; assert d['jobs']['publish']['environment']=='release'; assert d['permissions']['id-token']=='write'; print('publish.yml valid')"
```
Expected: `publish.yml valid`.

- [ ] **Step 3: Confirm not self-hosted + actions pinned**
```bash
grep -q "runs-on: ubuntu-latest" .github/workflows/publish.yml && ! grep -q "self-hosted" .github/workflows/publish.yml && echo "OK: GitHub-hosted"
grep -E "uses:.*@[0-9a-f]{40}" .github/workflows/publish.yml | wc -l   # expect 3
```

- [ ] **Step 4: Commit**
```bash
git add .github/workflows/publish.yml
git commit -m "ci: add PyPI Trusted Publishing workflow for ledticker"
```

> NOTE for the reviewer/maintainer: verify the `pypa/gh-action-pypi-publish` SHA `76f52bc…` corresponds to a current `v1.12.x` tag before relying on it; update the pin (and `# v…` comment) if a newer release exists. The workflow cannot succeed until the `release` environment and the PyPI pending publisher exist (Task 7).

---

## Task 4: Plugins — metadata + LICENSE + dependency rename (6 data plugins)

**Files (PLUGINS repo worktree, off `origin/main`):**
- Modify: `plugins/{pool,baseball,crypto,calendar,rss,weather}/pyproject.toml`
- Create: `plugins/{pool,baseball,crypto,calendar,rss,weather}/LICENSE`

**Interfaces:**
- Consumes: core's `ledticker` name (Task 1). Produces 6 buildable, PyPI-ready plugin packages depending on `ledticker>=2.0`.

- [ ] **Step 1: Create the plugins worktree off origin/main**
```bash
cd /Users/james/projects/github/jamesawesome/led-ticker-plugins
git fetch origin main
git worktree add -b feat/pypi-trusted-publishing /Users/james/projects/github/jamesawesome/led-ticker-plugins-worktrees/pypi origin/main
cd /Users/james/projects/github/jamesawesome/led-ticker-plugins-worktrees/pypi
test -f LICENSE && echo "root LICENSE present"   # from PR #8
```

- [ ] **Step 2: Copy the root LICENSE into each of the 6 data-plugin dirs**
```bash
for p in pool baseball crypto calendar rss weather; do cp LICENSE "plugins/$p/LICENSE"; done
ls plugins/*/LICENSE | wc -l   # expect 6
```

- [ ] **Step 3: In EACH of the 6 `plugins/<name>/pyproject.toml`, edit `[project]`** — change the `dependencies` entry `"led-ticker"` → `"ledticker>=2.0"`, and add `license`, `license-files`, `classifiers`, and `[project.urls]`. For `plugins/pool/pyproject.toml`, the `[project]` block becomes:
```toml
[project]
name = "led-ticker-pool"
version = "0.1.0"
description = "Pool water-temperature monitor widget for led-ticker (InfluxDB v2 backed)."
readme = "README.md"
license = "MIT"
license-files = ["LICENSE"]
requires-python = ">=3.14"
authors = [{ name = "James Awesome", email = "james@morelli.nyc" }]
classifiers = [
    "Development Status :: 4 - Beta",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.14",
    "Operating System :: POSIX :: Linux",
    "Topic :: Multimedia :: Graphics",
]
dependencies = [
    "ledticker>=2.0",
    "aiohttp",
]
```
Add a `[project.urls]` block to each (after `[project.optional-dependencies]` or before `[build-system]`):
```toml
[project.urls]
Homepage = "https://docs.ledticker.dev"
Repository = "https://github.com/JamesAwesome/led-ticker-plugins"
Issues = "https://github.com/JamesAwesome/led-ticker-plugins/issues"
```
Apply the SAME edits to `baseball`, `crypto`, `calendar`, `rss`, `weather` (keep each plugin's own `name`, `version`, `description`, `dependencies` extras, and `entry-points` — only the dep rename + the license/classifiers/urls additions are uniform). NOTE: some plugins may list the dependency as `"led-ticker"` with extras or a version — replace the distribution name token `led-ticker` with `ledticker>=2.0` wherever it appears as a dependency.

- [ ] **Step 4: Build + twine-check all 6**
```bash
for p in pool baseball crypto calendar rss weather; do
  (cd "plugins/$p" && rm -rf dist && uv build && uvx twine check dist/*) || { echo "FAIL: $p"; exit 1; }
done
echo "all 6 built + twine-checked"
```
Expected: each builds a `led_ticker_<name>-<ver>` sdist+wheel and `twine check` PASSES. (If a build can't resolve `ledticker` because core isn't on PyPI yet, that's fine — `uv build` does not resolve dependencies; only metadata is validated here.)

- [ ] **Step 5: Confirm dependency + license in built metadata (spot-check pool)**
```bash
python -c "import zipfile,glob;m=zipfile.ZipFile(glob.glob('plugins/pool/dist/*.whl')[0]);print([n for n in m.namelist() if n.endswith('METADATA')][0]);print(m.read([n for n in m.namelist() if n.endswith('METADATA')][0]).decode())" | grep -iE "^Requires-Dist:|^License|^Project-URL"
```
Expected: `Requires-Dist: ledticker>=2.0`; a License line; Project-URL lines.

- [ ] **Step 6: Commit**
```bash
git add plugins/*/pyproject.toml plugins/*/LICENSE
git commit -m "build: PyPI metadata + ledticker dep + bundled LICENSE for the 6 data plugins"
```

---

## Task 5: Plugins release script — parse tag + allowlist + version guard + tests

**Files (PLUGINS worktree):**
- Create: `scripts/check_release.py`
- Test: `tests/test_check_release.py`

**Interfaces:**
- Produces: `resolve(tag: str, plugins_root: str) -> tuple[str | None, str]` returning `(plugin_dir_or_None, message)`; CLI `python scripts/check_release.py <tag>` prints the plugin dir to stdout + exits 0 on a valid data-plugin tag whose version matches, else exits 1. Consumed by Task 6.

- [ ] **Step 1: Write the failing test** — `tests/test_check_release.py`:
```python
import subprocess
import sys
import textwrap
from pathlib import Path

from scripts.check_release import resolve

DATA = ["pool", "baseball", "crypto", "calendar", "rss", "weather"]
HOMAGE = ["nyancat", "pokeball", "pacman", "sailor_moon"]


def _mk(tmp_path: Path, plugin: str, version: str) -> str:
    d = tmp_path / "plugins" / plugin
    d.mkdir(parents=True)
    (d / "pyproject.toml").write_text(textwrap.dedent(f"""
        [project]
        name = "led-ticker-{plugin}"
        version = "{version}"
    """))
    return str(tmp_path / "plugins")


def test_data_plugin_matching_ok(tmp_path):
    root = _mk(tmp_path, "pool", "0.1.0")
    plugin_dir, msg = resolve("pool-v0.1.0", root)
    assert plugin_dir == str(Path(root) / "pool"), msg


def test_homage_plugin_rejected(tmp_path):
    root = _mk(tmp_path, "nyancat", "0.1.0")
    plugin_dir, msg = resolve("nyancat-v0.1.0", root)
    assert plugin_dir is None
    assert "not published to PyPI" in msg


def test_version_mismatch_rejected(tmp_path):
    root = _mk(tmp_path, "pool", "0.1.0")
    plugin_dir, msg = resolve("pool-v0.2.0", root)
    assert plugin_dir is None
    assert "0.2.0" in msg and "0.1.0" in msg


def test_unknown_plugin_rejected(tmp_path):
    root = _mk(tmp_path, "pool", "0.1.0")
    plugin_dir, msg = resolve("bogus-v1.0.0", root)
    assert plugin_dir is None


def test_malformed_tag_rejected(tmp_path):
    root = _mk(tmp_path, "pool", "0.1.0")
    plugin_dir, msg = resolve("pool0.1.0", root)
    assert plugin_dir is None


def test_cli_exit_codes(tmp_path):
    root = _mk(tmp_path, "pool", "0.1.0")
    ok = subprocess.run([sys.executable, "scripts/check_release.py", "pool-v0.1.0", root],
                        capture_output=True, text=True)
    bad = subprocess.run([sys.executable, "scripts/check_release.py", "nyancat-v0.1.0", root],
                         capture_output=True, text=True)
    assert ok.returncode == 0 and ok.stdout.strip().endswith("pool")
    assert bad.returncode == 1
```

- [ ] **Step 2: Run it to confirm it fails**
```bash
PYTHONPATH=. uv run --with pytest pytest tests/test_check_release.py -v
```
Expected: FAIL (`ModuleNotFoundError: scripts.check_release`).

- [ ] **Step 3: Implement `scripts/check_release.py`**
```python
"""Resolve a `<plugin>-vX.Y.Z` release tag to a buildable plugin dir.

Allows only the 6 DATA plugins; rejects homage plugins (GitHub-only) and any
tag whose version doesn't match the plugin's pyproject version. On success,
prints the plugin directory to stdout and exits 0; otherwise exits 1.
"""

import sys
import tomllib
from pathlib import Path

DATA_PLUGINS = {"pool", "baseball", "crypto", "calendar", "rss", "weather"}
HOMAGE_PLUGINS = {"nyancat", "pokeball", "pacman", "sailor_moon"}


def resolve(tag: str, plugins_root: str = "plugins") -> tuple[str | None, str]:
    if "-v" not in tag:
        return None, f"Tag {tag!r} is malformed (expected <plugin>-vX.Y.Z)."
    plugin, _, version = tag.rpartition("-v")
    if plugin in HOMAGE_PLUGINS:
        return None, (
            f"Plugin {plugin!r} is GitHub-install-only and is not published to PyPI."
        )
    if plugin not in DATA_PLUGINS:
        return None, f"Unknown plugin {plugin!r} (not in the publishable set)."
    plugin_dir = Path(plugins_root) / plugin
    pyproject = plugin_dir / "pyproject.toml"
    if not pyproject.exists():
        return None, f"No pyproject at {pyproject}."
    with open(pyproject, "rb") as f:
        pp_version = tomllib.load(f)["project"]["version"]
    if version != pp_version:
        return None, (
            f"Tag {tag!r} (version {version}) does not match {plugin} pyproject "
            f"version {pp_version!r}. Bump the version or fix the tag."
        )
    return str(plugin_dir), f"OK: {tag} -> {plugin_dir} (version {version})."


def main() -> int:
    tag = sys.argv[1]
    root = sys.argv[2] if len(sys.argv) > 2 else "plugins"
    plugin_dir, msg = resolve(tag, root)
    print(msg, file=sys.stderr)
    if plugin_dir is None:
        return 1
    print(plugin_dir)   # stdout = the dir, for the workflow to consume
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests to confirm pass**
```bash
PYTHONPATH=. uv run --with pytest pytest tests/test_check_release.py -v
```
Expected: 6 passed.

- [ ] **Step 5: Lint**
```bash
uvx ruff check scripts/check_release.py tests/test_check_release.py
```
Expected: All checks passed.

- [ ] **Step 6: Commit**
```bash
git add scripts/check_release.py tests/test_check_release.py
git commit -m "build: add plugin release tag parser + allowlist + version guard"
```

---

## Task 6: Plugins `publish.yml` workflow

**Files (PLUGINS worktree):**
- Create: `.github/workflows/publish.yml`

**Interfaces:**
- Consumes: `scripts/check_release.py` (Task 5); the 6 plugin builds (Task 4). Requires the `release` environment + 6 PyPI pending publishers (Task 7 runbook).

- [ ] **Step 1: Create `.github/workflows/publish.yml`**
```yaml
name: publish

# Publishes a single data plugin to PyPI via OIDC Trusted Publishing when a
# GitHub Release tagged `<plugin>-vX.Y.Z` is published. Homage plugins are
# rejected by scripts/check_release.py. GitHub-hosted runner, `release`-gated.
on:
  release:
    types: [published]

permissions:
  contents: read
  id-token: write

jobs:
  publish:
    runs-on: ubuntu-latest
    environment: release
    steps:
      - uses: actions/checkout@df4cb1c069e1874edd31b4311f1884172cec0e10 # v6
      - uses: astral-sh/setup-uv@fac544c07dec837d0ccb6301d7b5580bf5edae39 # v8.2.0
      - name: Resolve + guard the release tag
        id: resolve
        run: |
          set -euo pipefail
          DIR="$(python scripts/check_release.py "${{ github.event.release.tag_name }}")"
          echo "plugin_dir=$DIR" >> "$GITHUB_OUTPUT"
      - name: Build the plugin
        run: |
          cd "${{ steps.resolve.outputs.plugin_dir }}"
          rm -rf dist && uv build
      - name: Publish to PyPI (Trusted Publishing)
        uses: pypa/gh-action-pypi-publish@76f52bc884231f62b9a034ebfe128415bbaabdf1 # v1.12.4
        with:
          packages-dir: ${{ steps.resolve.outputs.plugin_dir }}/dist/
```

- [ ] **Step 2: Validate YAML + the homage fail-fast wiring**
```bash
uv run --with pyyaml python -c "import yaml; d=yaml.safe_load(open('.github/workflows/publish.yml')); j=d['jobs']['publish']; assert j['runs-on']=='ubuntu-latest'; assert j['environment']=='release'; assert d['permissions']['id-token']=='write'; print('plugins publish.yml valid')"
grep -q "self-hosted" .github/workflows/publish.yml && echo "ERROR self-hosted" || echo "OK: GitHub-hosted"
```

- [ ] **Step 3: Commit**
```bash
git add .github/workflows/publish.yml
git commit -m "ci: add per-plugin PyPI Trusted Publishing workflow"
```

---

## Task 7: Maintainer runbook (`docs/RELEASING.md`) + `release` environments

**Files (CORE worktree):**
- Create: `docs/RELEASING.md`

This task produces (a) a permanent release runbook in the core repo, and (b) the `release` GitHub environments. The PyPI account/2FA/Trusted-Publisher setup and the actual first publish are MAINTAINER actions performed against the runbook — NOT automated here.

- [ ] **Step 1: Create `docs/RELEASING.md`** with these sections (write them out fully — exact commands, no placeholders):

  **A. One-time PyPI setup (maintainer):**
  1. Create a PyPI account at https://pypi.org and **enable 2FA** (Account settings → Two-factor authentication) — mandatory to publish.
  2. Add a **pending Trusted Publisher** for each project at https://pypi.org/manage/account/publishing/ → "Add a new pending publisher". Values:
     | PyPI project | Owner | Repository | Workflow | Environment |
     |---|---|---|---|---|
     | `ledticker` | `JamesAwesome` | `led-ticker` | `publish.yml` | `release` |
     | `led-ticker-pool` | `JamesAwesome` | `led-ticker-plugins` | `publish.yml` | `release` |
     | `led-ticker-baseball` | `JamesAwesome` | `led-ticker-plugins` | `publish.yml` | `release` |
     | `led-ticker-crypto` | `JamesAwesome` | `led-ticker-plugins` | `publish.yml` | `release` |
     | `led-ticker-calendar` | `JamesAwesome` | `led-ticker-plugins` | `publish.yml` | `release` |
     | `led-ticker-rss` | `JamesAwesome` | `led-ticker-plugins` | `publish.yml` | `release` |
     | `led-ticker-weather` | `JamesAwesome` | `led-ticker-plugins` | `publish.yml` | `release` |
     No API tokens are created. The first successful workflow run creates each project.

  **B. Create the `release` environment (required-reviewer gate) in each repo.** Document these exact commands (replace `<USER_ID>` with the numeric id from `gh api /users/JamesAwesome -q .id`):
  ```bash
  # in led-ticker AND led-ticker-plugins:
  gh api --method PUT "/repos/JamesAwesome/<repo>/environments/release" \
    -f "reviewers[][type]=User" -F "reviewers[][id]=<USER_ID>"
  ```
  (Or Settings → Environments → New environment `release` → Required reviewers → add yourself.)

  **C. First-publish sequence:**
  1. **Core first** (plugins depend on `ledticker`): ensure `pyproject.toml` version is correct → push the merged branch → create a GitHub Release tagged `v2.0.0` → the `publish` workflow builds, then **pauses for approval** → click Approve → verify on https://pypi.org/project/ledticker/.
  2. **Then each plugin:** create a Release tagged `<plugin>-vX.Y.Z` (matching that plugin's pyproject version) → approve → verify.

  **D. Verification (per package):**
  ```bash
  python -m venv /tmp/verify && /tmp/verify/bin/pip install <name>
  # for a plugin, confirm it pulled ledticker transitively:
  /tmp/verify/bin/pip show led-ticker-pool | grep -i requires
  ```

  **E. Re-releases:** PyPI forbids re-uploading an existing version — to re-release, bump the version in pyproject and tag the new version. The tag-vs-version guard enforces the match.

- [ ] **Step 2: Verify the runbook has no placeholders + the publisher table lists 7 rows**
```bash
grep -c "publish.yml" docs/RELEASING.md   # expect >= 7 (the table rows)
! grep -iE "TODO|TBD|FIXME" docs/RELEASING.md && echo "no placeholders"
```

- [ ] **Step 3: Commit**
```bash
git add docs/RELEASING.md
git commit -m "docs: add RELEASING runbook (PyPI Trusted Publishing setup + sequence)"
```

> Execution note: creating the `release` environments via `gh api` (step B) and all of section A/C/D are MAINTAINER/operator actions — the controller hands these to the human at the end and pauses before any real publish. They are documented here, not run by an implementer subagent.

---

## Self-Review

**1. Spec coverage:**
- Scope (7 packages, homage excluded) → Tasks 1, 4, 5 (allowlist), 7 (table). ✅
- Real PyPI + approval gate → Task 3/6 (`environment: release`), Task 7B. ✅
- GitHub Releases trigger → Task 3/6 (`on: release: published`). ✅
- Manual version + tag-match guard → Tasks 2, 5. ✅
- `ledticker` core name, import/CLI unchanged → Task 1 (+ Global Constraints). ✅
- Metadata (license SPDX, classifiers, urls, readme) → Tasks 1, 4. ✅
- Per-plugin LICENSE bundling → Task 4 (steps 2). ✅
- GitHub-hosted not self-hosted → Tasks 3, 6 (+ checks). ✅
- Pinned action SHAs → Tasks 3, 6 (+ reviewer note on the publish-action pin). ✅
- PyPI setup runbook + first-publish sequence + verification → Task 7. ✅

**2. Placeholder scan:** Code steps contain full file content. `<USER_ID>`, `<repo>`, `<name>`, `<plugin>` in Task 7 are deliberate runbook substitution slots (a runbook, not code) with the resolution command given. The `pypa/gh-action-pypi-publish` SHA carries a reviewer-verify note. No `TODO`/`TBD`/"implement later".

**3. Type consistency:** `parse_and_check(tag, pyproject_path) -> (bool, str)` (Task 2) and `resolve(tag, plugins_root) -> (str|None, str)` (Task 5) are used consistently in their tests and workflows. The plugins workflow consumes `check_release.py`'s stdout (the plugin dir) via `$GITHUB_OUTPUT` — matches the script's `print(plugin_dir)` on success.

**Cross-repo note:** Tasks 1–3 + 7 are the CORE PR; Tasks 4–6 are the PLUGINS PR. Build verification in Task 4 does not require core to be on PyPI (uv build skips dependency resolution).
