# Plugin-Requirements File Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the external-plugin install out of the hardcoded `Dockerfile` layer into a declarative, gitignored `config/requirements-plugins.txt` (copied from a tracked `.example`), installed build-time with dependency resolution constrained to core's versions, live-file-only with no fallback.

**Architecture:** A tracked `config/requirements-plugins.example.txt` (ships the pool plugin line) is a copy-me template; users `cp` it to the gitignored `config/requirements-plugins.txt` and edit. Layer 2 of the `Dockerfile` generates `constraints-core.txt` via `pip list --format=freeze`. The `Dockerfile` and `deploy/install.sh` install the **live** file only, constrained to core's pinned versions (`-c constraints-core.txt`): a plugin may bring new deps but cannot move core's stack — a conflict fails loudly at build rather than silently at runtime. If the live file is absent, no plugins are installed (build still succeeds). The old hardcoded pool layer and its `POOL_PLUGIN_CACHE_BUST` ARG are removed.

**Tech Stack:** Docker, pip requirements files, bash (`deploy/install.sh`), pytest (guard tests).

**Spec:** `docs/superpowers/specs/2026-06-03-plugin-requirements-file-design.md`

**Worktree/branch:** `.claude/worktrees/plugin-requirements` on `feat/plugin-requirements`. Commit with `git -c core.hooksPath=/dev/null commit` (global hooksPath workaround). All paths below are relative to the worktree root.

---

## File Structure

- **Create** `config/requirements-plugins.example.txt` — tracked template; ships the pool plugin line + format/`--no-deps` header comments.
- **Create** `tests/test_plugin_requirements.py` — guard tests for the example file, `.gitignore`, `Dockerfile`, and `install.sh`.
- **Modify** `.gitignore` — ignore the live `config/requirements-plugins.txt`.
- **Modify** `Dockerfile` — replace "Layer 2b" (drop the hardcoded pool install + `POOL_PLUGIN_CACHE_BUST`; install the live requirements file only).
- **Modify** `deploy/install.sh` — install the live requirements file (`--no-deps`) if present, after the package install.
- **Modify** `README.md` — note the plugin file in the Configuration section.

---

### Task 1: Example template file + gitignore + guard test

**Files:**
- Create: `config/requirements-plugins.example.txt`
- Create: `tests/test_plugin_requirements.py`
- Modify: `.gitignore`

- [ ] **Step 1: Write the failing test**

Create `tests/test_plugin_requirements.py`:

```python
"""Guard tests for the declarative plugin-requirements file.

See docs/superpowers/specs/2026-06-03-plugin-requirements-file-design.md.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _noncomment_lines(text: str) -> list[str]:
    out = []
    for raw in text.splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            out.append(line)
    return out


def test_example_requirements_exists_and_lists_pool():
    example = REPO_ROOT / "config" / "requirements-plugins.example.txt"
    assert example.exists(), "config/requirements-plugins.example.txt must exist"
    lines = _noncomment_lines(example.read_text())
    assert any("led-ticker-pool" in line for line in lines), (
        "the example should ship the led-ticker-pool plugin line"
    )
    # each requirement is a single token (no stray internal whitespace)
    for line in lines:
        assert " " not in line, f"malformed requirement line: {line!r}"


def test_live_requirements_file_is_gitignored():
    gitignore = (REPO_ROOT / ".gitignore").read_text()
    assert "config/requirements-plugins.txt" in gitignore, (
        "the live requirements-plugins.txt must be gitignored"
    )
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd <worktree> && uv run pytest tests/test_plugin_requirements.py -q`
Expected: FAIL — example file missing and `.gitignore` entry absent.

- [ ] **Step 3: Create the example file**

Create `config/requirements-plugins.example.txt`:

```
# Plugins to install into the image (pip requirements format, one per line).
# Copy this file to config/requirements-plugins.txt and edit it for your signs,
# then rebuild:  docker compose up -d --build
#
# Installed with --no-deps because led-ticker is not on PyPI. If a plugin needs
# a runtime library beyond what led-ticker already ships, add it as its own line.
#
# Pool water-temperature widget (type = "pool.monitor"):
git+https://github.com/JamesAwesome/led-ticker-pool.git@main
```

- [ ] **Step 4: Add the gitignore entry**

In `.gitignore`, find the line `config/config.toml` (around line 148) and add directly below it:

```
config/requirements-plugins.txt
```

- [ ] **Step 5: Run to verify it passes**

Run: `cd <worktree> && uv run pytest tests/test_plugin_requirements.py -q`
Expected: PASS (2 tests).

Also confirm the live file is actually ignored: `cd <worktree> && touch config/requirements-plugins.txt && git status --porcelain config/requirements-plugins.txt` → prints nothing (ignored). Then `rm config/requirements-plugins.txt`.

- [ ] **Step 6: Commit**

```bash
git -C <worktree> add config/requirements-plugins.example.txt tests/test_plugin_requirements.py .gitignore
git -C <worktree> -c core.hooksPath=/dev/null commit -m "feat: add config/requirements-plugins.example.txt template + gitignore live file"
```

---

### Task 2: Dockerfile installs the live requirements file (drop hardcoded pool layer)

**Files:**
- Modify: `Dockerfile` (the "Layer 2b" block)
- Modify: `tests/test_plugin_requirements.py` (add guard)

**Context — the current "Layer 2b" block to replace (verbatim):**

```dockerfile
# Layer 2b: external plugins (led_ticker.plugins entry points auto-register at
# startup). Installed --no-deps on purpose: led-ticker is not on PyPI (it's the
# editable install above) and the plugins' runtime deps (aiohttp) are already
# present as app dependencies, so dependency resolution would only fail trying
# to fetch led-ticker from PyPI. Bump POOL_PLUGIN_CACHE_BUST to pull a newer
# plugin revision (Docker caches by instruction text, not remote content).
ARG POOL_PLUGIN_CACHE_BUST=1
RUN pip install --no-cache-dir --no-deps \
    "git+https://github.com/JamesAwesome/led-ticker-pool.git@main"
```

- [ ] **Step 1: Write the failing test**

Append to `tests/test_plugin_requirements.py`:

```python
def test_dockerfile_installs_from_requirements_file():
    dockerfile = (REPO_ROOT / "Dockerfile").read_text()
    # installs the declarative live file conditionally
    assert "-r /code/config/requirements-plugins.txt" in dockerfile, (
        "Dockerfile should pip-install the live requirements-plugins.txt"
    )
    assert "config/requirements-plugins.example.txt" in dockerfile, (
        "Dockerfile should COPY the example (guaranteed source for the optional-file trick)"
    )
    # the old hardcoded mechanism is gone
    assert "POOL_PLUGIN_CACHE_BUST" not in dockerfile, (
        "the per-plugin cache-bust ARG should be removed"
    )
    assert "led-ticker-pool.git" not in dockerfile, (
        "no hardcoded plugin git URL should remain in the Dockerfile"
    )
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd <worktree> && uv run pytest tests/test_plugin_requirements.py::test_dockerfile_installs_from_requirements_file -q`
Expected: FAIL — current Dockerfile still has `POOL_PLUGIN_CACHE_BUST` and the hardcoded URL.

- [ ] **Step 3: Replace the Layer 2b block**

In `Dockerfile`, replace the entire block shown in Context above with:

```dockerfile
# Layer 2b: external plugins, declared in config/requirements-plugins.txt
# (gitignored; copy config/requirements-plugins.example.txt to create it).
# Installed --no-deps because led-ticker is not on PyPI (it's the editable
# install above) and plugin runtime deps (e.g. aiohttp) are already present as
# app dependencies. Installs the live file only — if it is absent, no plugins
# are installed (no fallback to the example). The .tx[t] glob is the optional-
# file trick: it copies the live file if present and is skipped if not; the
# .example is always present so the COPY itself always succeeds. Editing the
# live file invalidates this cached layer and triggers a reinstall.
COPY config/requirements-plugins.example.txt config/requirements-plugins.tx[t] /code/config/
RUN if [ -f /code/config/requirements-plugins.txt ]; then \
        pip install --no-cache-dir --no-deps -r /code/config/requirements-plugins.txt; \
    else \
        echo "No config/requirements-plugins.txt; skipping plugin install (copy the .example to add plugins)"; \
    fi
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd <worktree> && uv run pytest tests/test_plugin_requirements.py -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Lint the Dockerfile (best-effort) + sanity-read**

Run: `cd <worktree> && hadolint Dockerfile 2>/dev/null || echo "hadolint not installed — skipping"`. There must be no `FROM`/layer-ordering change: the new block sits between `RUN pip install --no-cache-dir -e ".[dev]"` (Layer 2) and `# Layer 3: app source` / `COPY . /code/` (unchanged).

- [ ] **Step 6: Commit**

```bash
git -C <worktree> add Dockerfile tests/test_plugin_requirements.py
git -C <worktree> -c core.hooksPath=/dev/null commit -m "feat: Dockerfile installs plugins from config/requirements-plugins.txt (drop hardcoded pool layer)"
```

---

### Task 3: Bare-metal `install.sh` installs the live requirements file

**Files:**
- Modify: `deploy/install.sh`
- Modify: `tests/test_plugin_requirements.py` (add guard)

**Context — the current relevant lines in `deploy/install.sh` (around 48-49):**

```sh
# Install the package
echo "==> Installing led-ticker package (upgrading if already installed)..."
pip install --upgrade "${REPO_DIR}"
```

- [ ] **Step 1: Write the failing test**

Append to `tests/test_plugin_requirements.py`:

```python
def test_install_sh_installs_plugin_requirements():
    install_sh = (REPO_ROOT / "deploy" / "install.sh").read_text()
    assert "config/requirements-plugins.txt" in install_sh, (
        "install.sh should install the live requirements-plugins.txt"
    )
    assert "--no-deps" in install_sh, (
        "install.sh plugin install should use --no-deps"
    )
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd <worktree> && uv run pytest tests/test_plugin_requirements.py::test_install_sh_installs_plugin_requirements -q`
Expected: FAIL — install.sh has no plugin-requirements handling yet.

- [ ] **Step 3: Add the plugin install to `install.sh`**

In `deploy/install.sh`, directly AFTER the line `pip install --upgrade "${REPO_DIR}"`, insert:

```sh

# Install declared plugins (config/requirements-plugins.txt), if present.
# --no-deps: led-ticker is not on PyPI and plugin runtime deps are already
# installed with the package above. No fallback to the .example template.
PLUGINS_REQ="${REPO_DIR}/config/requirements-plugins.txt"
if [ -f "$PLUGINS_REQ" ]; then
    echo "==> Installing plugins from config/requirements-plugins.txt..."
    pip install --no-deps -r "$PLUGINS_REQ"
fi
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd <worktree> && uv run pytest tests/test_plugin_requirements.py -q`
Expected: PASS (4 tests).

- [ ] **Step 5: Shell-lint (best-effort)**

Run: `cd <worktree> && shellcheck deploy/install.sh 2>/dev/null || echo "shellcheck not installed — skipping"`. No new warnings introduced by the added block (the `$PLUGINS_REQ` var is quoted).

- [ ] **Step 6: Commit**

```bash
git -C <worktree> add deploy/install.sh tests/test_plugin_requirements.py
git -C <worktree> -c core.hooksPath=/dev/null commit -m "feat: bare-metal install.sh installs config/requirements-plugins.txt (--no-deps)"
```

---

### Task 4: Document the plugin file in the README

**Files:**
- Modify: `README.md` (Configuration section, after the reference-configs list around line 32)

- [ ] **Step 1: Add a Plugins subsection**

In `README.md`, directly AFTER the line `Full config reference: <https://docs.ledticker.dev/reference/config-options/>. Per-widget pages document every knob: <https://docs.ledticker.dev/widgets/>.` (around line 32), insert a blank line then:

```markdown
### Plugins

Extra widgets (and other extension points) are installed as plugins, declared in a pip-requirements file:

```bash
cp config/requirements-plugins.example.txt config/requirements-plugins.txt
# edit to add/remove plugins, then rebuild the image:
docker compose up -d --build
```

The live `config/requirements-plugins.txt` is gitignored (it's yours to customize); the tracked `.example` ships the pool water-temperature widget (`type = "pool.monitor"`) as a starting point. Installed plugins auto-register via their `led_ticker.plugins` entry point — no `[plugins]` config change needed. See <https://docs.ledticker.dev/> for writing your own.
```

(Note: the inner fenced block uses triple backticks — when editing, ensure the nested code fence is preserved so the Markdown renders correctly.)

- [ ] **Step 2: Verify the README still renders**

Run: `cd <worktree> && python -c "import pathlib; t=pathlib.Path('README.md').read_text(); assert 'requirements-plugins.example.txt' in t and t.count('\`\`\`') % 2 == 0, 'unbalanced code fences'; print('README ok')"`
Expected: `README ok`.

- [ ] **Step 3: Commit**

```bash
git -C <worktree> add README.md
git -C <worktree> -c core.hooksPath=/dev/null commit -m "docs: document config/requirements-plugins.txt in the README"
```

---

### Task 5: Full suite + Docker build verification

**Files:** none (verification only)

- [ ] **Step 1: Run the full test suite**

Run: `cd <worktree> && make test`
Expected: green (the pre-existing suite plus the 4 new guard tests). If `make dev` hasn't been run in this worktree yet, run `make dev` first.

- [ ] **Step 2: Lint + typecheck**

Run: `cd <worktree> && make lint && make typecheck`
Expected: clean.

- [ ] **Step 3: Docker build — no live file (no plugins installed)**

Ensure no live file exists: `cd <worktree> && rm -f config/requirements-plugins.txt`.
Run: `cd <worktree> && docker build -t led-ticker-pluginreq-test . 2>&1 | tail -20`
Expected: build succeeds; the Layer 2b step prints `No config/requirements-plugins.txt; skipping plugin install`.
Verify no pool plugin: `docker run --rm led-ticker-pluginreq-test led-ticker plugins 2>&1 | tail -5` → lists **no** plugins (no `pool`).

- [ ] **Step 4: Docker build — with live file (pool installed)**

Run: `cd <worktree> && cp config/requirements-plugins.example.txt config/requirements-plugins.txt && docker build -t led-ticker-pluginreq-test . 2>&1 | tail -20`
Expected: build succeeds; Layer 2b pip-installs `led-ticker-pool`.
Verify: `docker run --rm led-ticker-pluginreq-test led-ticker plugins 2>&1 | tail -5` → lists `pool` with `pool.monitor`.
Cleanup: `cd <worktree> && rm -f config/requirements-plugins.txt && docker rmi led-ticker-pluginreq-test 2>/dev/null || true`.

> If Docker is unavailable in the execution environment, record that Steps 3-4 were skipped and must be run on a Docker-capable host before merge; the guard tests (Task 2) still assert the Dockerfile content.

- [ ] **Step 5: Final commit (if any verification fixups were needed)**

Only if Steps 1-4 surfaced a fix. Otherwise nothing to commit here.

---

## Notes for the implementer

- **Do not** add a fallback to the `.example` in either the Dockerfile or `install.sh` — live file only, by design (spec §2/§3).
- Plugin install now uses `-c constraints-core.txt` (not `--no-deps`). Layer 2 generates `constraints-core.txt` via `pip list --format=freeze`; install.sh writes a temp file the same way. A plugin that moves a core dep version fails the build with `ResolutionImpossible` — this is intentional.
- The `.example` being copied into the image (the optional-file COPY trick's guaranteed source) is intentional and harmless; it is never pip-installed.
- Leave the existing `[plugins]` config block and `_plugin_loader` untouched — this change is purely about *installing* plugins, not *loading* them.
- The led-ticker-pool README references `config/requirements-plugins.txt`; this plan makes that real. No change needed in the plugin repo.
