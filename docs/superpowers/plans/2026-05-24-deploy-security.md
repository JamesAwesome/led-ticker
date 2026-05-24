# Batch 1 (DR2): Deploy Security & Correctness

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Branch safety:** Before doing ANY work, run `git branch --show-current`. If it prints `main`, stop immediately and ask for a worktree.

**Goal:** Fix the critical `.dockerignore` security gap and the remaining deploy correctness issues. All changes are config files and shell scripts — no production Python code is touched.

**Architecture:** Seven independent one-liner-or-less changes. No dependency order; they can be committed together or as a stacked commit per task. The `.dockerignore` is the most important (C1) and should go first.

**Tech Stack:** Docker, bash, systemd

**Run tests with:** `PYTHONPATH=tests/stubs uv run pytest -x -q` (no production code changes; test suite should be unaffected throughout)

**Verify Docker with:** `docker build -t led-ticker-test .` (after Task 4 and 5 to confirm the image still builds)

---

### Task 1: C1 — Create `.dockerignore`

Without a `.dockerignore`, `COPY . /code/` in `Dockerfile:32` includes `.env` in the build context, embedding API keys (`WEATHERAPI_KEY`, `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`) in a committed image layer. The keys are extractable via `docker image save led-ticker | tar xO | strings` or any filesystem inspection.

**Files:**
- Create: `.dockerignore`

- [ ] **Step 1: Create `.dockerignore`**

Create the file at the repo root with the following content:

```
# API keys and secrets — never bake into image layers
.env

# Version control metadata
.git
.gitignore
.github

# Local config — mounted read-only at runtime via compose.yaml
config/config.toml
config/config.bigsign.example.toml
config/config.moonbunny.example.toml

# Python build artifacts
__pycache__
*.pyc
*.pyo
*.egg-info
.venv
dist/
build/

# Development tools and tests
tests/
tools/
docs/
.claude/

# Editor/OS files
.DS_Store
*.swp
*.swo
```

- [ ] **Step 2: Verify `.env` is excluded**

```bash
docker build --dry-run . 2>/dev/null | grep -c ".env" || echo "no .env in context (good)"
# If docker build --dry-run is not supported on this Docker version:
docker build -t led-ticker-test . --no-cache 2>&1 | tail -5
```

If `.env` is present in the repo root, confirm it does NOT appear in the built image:

```bash
docker run --rm led-ticker-test find /code -name ".env" 2>/dev/null | head
# Expected: no output (file not present in image)
```

- [ ] **Step 3: Commit**

```bash
git add .dockerignore
git commit -m "fix: add .dockerignore to prevent .env API keys baking into image (C1)"
```

---

### Task 2: S6 — Add `--upgrade` to `pip install` in `install.sh`

`deploy/install.sh:50` runs `pip install "${REPO_DIR}"` without `--upgrade`. Re-running the script after `git pull` silently keeps the old version installed if the package version string hasn't changed.

**Files:**
- Modify: `deploy/install.sh:50`

- [ ] **Step 1: Apply the fix**

In `deploy/install.sh`, change line 50:

```bash
# Before:
pip install "${REPO_DIR}"

# After:
pip install --upgrade "${REPO_DIR}"
```

Also update the echo below it to explain the upgrade behavior. Find the block at the bottom of the install section:

```bash
# Change from:
echo "==> Installing led-ticker package..."
pip install "${REPO_DIR}"

# Change to:
echo "==> Installing led-ticker package (upgrading if already installed)..."
pip install --upgrade "${REPO_DIR}"
```

- [ ] **Step 2: Commit**

```bash
git add deploy/install.sh
git commit -m "fix: add --upgrade to pip install in install.sh so re-runs update the package (S6)"
```

---

### Task 3: S7 — Add systemd hardening directives

`deploy/led-ticker.service` runs as root with no capability restrictions, no `NoNewPrivileges`, no restart storm protection. A crashed process can restart-loop indefinitely; a compromised process could escalate via setuid.

**Files:**
- Modify: `deploy/led-ticker.service`

- [ ] **Step 1: Apply the fix**

Replace the `[Service]` section of `deploy/led-ticker.service`:

```ini
# Before:
[Service]
Type=simple
User=root
WorkingDirectory=/opt/led-ticker
EnvironmentFile=/opt/led-ticker/.env
ExecStart=/opt/led-ticker/venv/bin/led-ticker --config /opt/led-ticker/config.toml
Restart=always
RestartSec=10

# After:
[Service]
Type=simple
User=root
WorkingDirectory=/opt/led-ticker
EnvironmentFile=/opt/led-ticker/.env
ExecStart=/opt/led-ticker/venv/bin/led-ticker --config /opt/led-ticker/config.toml
Restart=on-failure
RestartSec=10
StartLimitIntervalSec=60
StartLimitBurst=5

# Harden the service. Root is required for GPIO access; the options
# below constrain what a compromised process can do with root.
NoNewPrivileges=yes
PrivateTmp=yes
```

- [ ] **Step 2: Verify the unit file parses correctly on the Pi**

On the target Pi after copying the file:

```bash
systemd-analyze verify /etc/systemd/system/led-ticker.service
# Expected: no output (clean parse); or warnings about missing binaries (OK in dev)
```

- [ ] **Step 3: Commit**

```bash
git add deploy/led-ticker.service
git commit -m "fix: add NoNewPrivileges, PrivateTmp, StartLimitBurst to systemd unit (S7)"
```

---

### Task 4: S10 — Remove silent failure from Dockerfile dev-dep install

`Dockerfile:29` runs `pip install --no-cache-dir -e ".[dev]" 2>/dev/null || true`, suppressing both stderr and the exit code. A broken dep, yanked package, or network timeout silently produces a successful Docker layer with missing dev tools.

**Files:**
- Modify: `Dockerfile:29`

- [ ] **Step 1: Apply the fix**

In `Dockerfile`, change Layer 2:

```dockerfile
# Before:
# Layer 2: app dependencies (only rebuilds if pyproject.toml changes)
FROM rgbmatrix
WORKDIR /code
COPY pyproject.toml /code/
RUN pip install --no-cache-dir -e ".[dev]" 2>/dev/null || true

# After:
# Layer 2: app dependencies (only rebuilds if pyproject.toml changes)
FROM rgbmatrix
WORKDIR /code
COPY pyproject.toml /code/
RUN pip install --no-cache-dir -e ".[dev]"
```

- [ ] **Step 2: Confirm image builds**

```bash
docker build -t led-ticker-test .
# Expected: successful build; any pip failure now surfaces as a build failure
```

- [ ] **Step 3: Commit**

```bash
git add Dockerfile
git commit -m "fix: remove 2>/dev/null || true from Dockerfile dev-dep install (S10)"
```

---

### Task 5: S11 — Pin Dockerfile `git clone` to a branch

`Dockerfile:19-23` clones `https://github.com/jamesawesome/rpi-rgb-led-matrix.git` with no `--branch`. Two `docker build` runs on different days can produce different rgbmatrix binaries from the same `Dockerfile`.

**Files:**
- Modify: `Dockerfile:19-23`

- [ ] **Step 1: Apply the fix**

In `Dockerfile`, add `--branch main` to the clone command:

```dockerfile
# Before:
# Layer 1: rgbmatrix (only rebuilds if the pinned ref changes)
RUN cd /opt && \
    git clone --depth=1 \
        https://github.com/jamesawesome/rpi-rgb-led-matrix.git rgbmatrix-src && \
    cd rgbmatrix-src && \
    pip install .

# After:
# Layer 1: rgbmatrix (only rebuilds if the pinned ref changes)
# Pin to --branch main so two builds on different days get the same source.
# Once upstream PR hzeller#1886 merges, update to --branch <sha> of hzeller/master.
RUN cd /opt && \
    git clone --depth=1 --branch main \
        https://github.com/jamesawesome/rpi-rgb-led-matrix.git rgbmatrix-src && \
    cd rgbmatrix-src && \
    pip install .
```

- [ ] **Step 2: Confirm image builds**

```bash
docker build -t led-ticker-test .
```

- [ ] **Step 3: Commit**

```bash
git add Dockerfile
git commit -m "fix: pin Dockerfile git clone to --branch main for deterministic builds (S11)"
```

---

### Task 6: S14 — Delete legacy `docker-compose.yml`

`docker-compose.yml` (v1 format) diverges from the canonical `compose.yaml` in two operationally meaningful ways: service name `ticker` (not `led-ticker`) and missing `network_mode: host`. Anyone who runs `docker compose up` after finding the legacy file gets a different deployment. It sorts before `compose.yaml` in `ls`.

**Files:**
- Delete: `docker-compose.yml`
- Modify: `README.md` (name `compose.yaml` explicitly if it's currently ambiguous)

- [ ] **Step 1: Confirm `compose.yaml` is complete**

```bash
cat compose.yaml
# Verify it has: service name = led-ticker, network_mode: host, env_file: ./.env
```

- [ ] **Step 2: Delete the legacy file**

```bash
git rm docker-compose.yml
```

- [ ] **Step 3: Check README for references to the deleted file**

```bash
grep -r "docker-compose.yml" README.md docs/ 2>/dev/null
```

Update any references found to point to `compose.yaml`.

- [ ] **Step 4: Commit**

```bash
git commit -m "fix: delete diverged docker-compose.yml (legacy v1); compose.yaml is canonical (S14)"
```

---

### Task 7: M11 + M12 — Fix stale `install.sh` comment and hoist `RGBMATRIX_REPO`

`deploy/install.sh:9` still says `kingdo9/rpi-rgb-led-matrix_pwm_experiment @ pi5_support` — the actual repo is `jamesawesome/rpi-rgb-led-matrix`. Lines 17–23 have both `if` and `else` branches assigning the same `RGBMATRIX_REPO` URL — only `RGBMATRIX_REF` differs.

**Files:**
- Modify: `deploy/install.sh:9,17-23`

- [ ] **Step 1: Fix the comment (line 9)**

```bash
# Before (line 9):
#   PI5=1 → kingdo9/rpi-rgb-led-matrix_pwm_experiment @ pi5_support

# After:
#   PI5=1 → jamesawesome/rpi-rgb-led-matrix @ pi5_support
```

- [ ] **Step 2: Hoist `RGBMATRIX_REPO` (lines 14-23)**

```bash
# Before:
# Pick the rgbmatrix fork. Both Pi 4 and Pi 5 build off our jamesawesome fork:
# main = Pi 4 (existing sign), pi5_support = kingdo9 PR #1886 + our build patch.
if [ "${PI5:-0}" = "1" ]; then
    : "${RGBMATRIX_REPO:=https://github.com/jamesawesome/rpi-rgb-led-matrix.git}"
    : "${RGBMATRIX_REF:=pi5_support}"
else
    : "${RGBMATRIX_REPO:=https://github.com/jamesawesome/rpi-rgb-led-matrix.git}"
    : "${RGBMATRIX_REF:=main}"
fi

# After:
# Both Pi 4 and Pi 5 build from our jamesawesome fork:
# main = Pi 4 (existing sign), pi5_support = kingdo9 PR #1886 + our build patch.
: "${RGBMATRIX_REPO:=https://github.com/jamesawesome/rpi-rgb-led-matrix.git}"
if [ "${PI5:-0}" = "1" ]; then
    : "${RGBMATRIX_REF:=pi5_support}"
else
    : "${RGBMATRIX_REF:=main}"
fi
```

- [ ] **Step 3: Commit**

```bash
git add deploy/install.sh
git commit -m "fix: update stale kingdo9 comment and hoist RGBMATRIX_REPO in install.sh (M11, M12)"
```

---

## Self-Review

**Spec coverage:**

| Finding | Task | Status |
|---------|------|--------|
| C1 — no `.dockerignore` | Task 1 | ✅ |
| S6 — no `--upgrade` in install.sh | Task 2 | ✅ |
| S7 — no systemd hardening | Task 3 | ✅ |
| S10 — `|| true` in Dockerfile | Task 4 | ✅ |
| S11 — unpinned git clone | Task 5 | ✅ |
| S14 — diverged docker-compose.yml | Task 6 | ✅ |
| M11 — stale install.sh comment | Task 7 | ✅ |
| M12 — duplicate RGBMATRIX_REPO | Task 7 | ✅ |

**Placeholder scan:** No TBD/TODO. All file content is complete.

**Scope:** Zero production Python changes. Test suite count unchanged.
