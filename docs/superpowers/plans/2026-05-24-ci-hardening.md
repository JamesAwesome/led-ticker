# Batch 3 (DR2): CI Hardening

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Branch safety:** Before doing ANY work, run `git branch --show-current`. If it prints `main`, stop immediately and ask for a worktree.

**Goal:** Add enforcement and visibility to the CI/CD pipeline: coverage threshold, Docker build verification, pinned action SHAs, fork-PR security documentation, Dependabot Docker ecosystem, and a bookworm migration note. No production code changes.

**Architecture:** Six independent changes to `.github/` files and `pyproject.toml`. The coverage threshold (Task 1) and Docker build job (Task 2) should land together so CI is not broken in the interim.

**Tech Stack:** GitHub Actions, Docker, pyproject.toml, Dependabot

**Run tests with:** `PYTHONPATH=tests/stubs uv run pytest -x -q` (after Task 1 to confirm coverage is >= 90%)

---

### Task 1: S8 — Add coverage threshold enforcement

Both `ci.yml:89` and `Makefile:17` run `pytest --cov` with no `--cov-fail-under`. Coverage currently sits at ~95% but nothing enforces this — a PR that deletes tests can merge without CI objecting.

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Check current coverage**

```bash
PYTHONPATH=tests/stubs uv run pytest --cov=src/led_ticker --cov-report=term-missing -q 2>&1 | tail -5
```

Note the reported coverage percentage. It should be around 95%. If it's below 90%, do NOT add the threshold yet — investigate the gap first.

- [ ] **Step 2: Add `fail_under` to `pyproject.toml`**

In `pyproject.toml`, add a `[tool.coverage.report]` section:

```toml
[tool.coverage.report]
fail_under = 90
```

Place it after `[tool.ruff.lint]`. The `pytest-cov` plugin reads this automatically — no changes needed to `ci.yml` or `Makefile`.

- [ ] **Step 3: Verify the threshold is respected**

```bash
PYTHONPATH=tests/stubs uv run pytest --cov=src/led_ticker --cov-report=term-missing -q 2>&1 | tail -5
```

Expected: exit code 0 (coverage >= 90%). If it exits non-zero, coverage dropped below threshold — investigate before committing.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "fix: add [tool.coverage.report] fail_under = 90 to pyproject.toml (S8)"
```

---

### Task 2: S9 — Add Docker build verification job to CI

`ci.yml` never runs `make build-docker`. A syntax error in the `Dockerfile` or a broken `apt-get` package only surfaces at deploy time.

**Files:**
- Modify: `.github/workflows/ci.yml`

- [ ] **Step 1: Add a `docker` entry to the path filter**

In `.github/workflows/ci.yml`, add a `docker` filter to the `changes` job's `filters` block:

```yaml
# In the changes job, add to the filters:
docker:
  - 'Dockerfile'
  - 'pyproject.toml'
  - 'src/**'
  - '.github/workflows/ci.yml'
```

- [ ] **Step 2: Add the `docker-build` job**

After the `gif-plan-test` job and before `docs-lint`, add:

```yaml
docker-build:
  needs: changes
  if: needs.changes.outputs.docker == 'true'
  runs-on: self-hosted
  steps:
    - uses: actions/checkout@v6
    - name: Build Docker image
      run: docker build --no-cache -t led-ticker-ci-test .
    - name: Clean up test image
      if: always()
      run: docker rmi led-ticker-ci-test || true
```

- [ ] **Step 3: Add `docker-build` to the `ci-passed` rollup job**

In the `ci-passed` job:

```yaml
# Before:
ci-passed:
  needs: [changes, lint, typecheck, test, gif-plan-test, docs-lint]

# After:
ci-passed:
  needs: [changes, lint, typecheck, test, gif-plan-test, docs-lint, docker-build]
```

Also add `docker-build` to the result env vars and the for-loop check in the `ci-passed` step:

```yaml
# Add to env:
DOCKER_BUILD_RESULT: ${{ needs.docker-build.result }}

# Add to the for loop:
docker-build:"$DOCKER_BUILD_RESULT"
```

- [ ] **Step 4: Update `changes` job outputs**

In the `changes` job's `outputs` block, add:

```yaml
outputs:
  python: ${{ steps.f.outputs.python }}
  docs: ${{ steps.f.outputs.docs }}
  gif_plan: ${{ steps.f.outputs.gif_plan }}
  docker: ${{ steps.f.outputs.docker }}   # add this line
```

- [ ] **Step 5: Verify the YAML is valid**

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))" && echo "YAML valid"
```

- [ ] **Step 6: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "fix: add docker-build CI job gated on Dockerfile/src changes (S9)"
```

---

### Task 3: S12 — Pin action versions to commit SHAs

All action references in `ci.yml` and `docs-deploy.yml` use mutable tags (`actions/checkout@v6`, `astral-sh/setup-uv@v8.1.0`, etc.). Tags can be force-pushed to point at malicious commits. The self-hosted runner is a production Pi with GPIO access.

**Files:**
- Modify: `.github/workflows/ci.yml`
- Modify: `.github/workflows/docs-deploy.yml`

- [ ] **Step 1: Find all action references**

```bash
grep -n "uses:" .github/workflows/ci.yml .github/workflows/docs-deploy.yml
```

List all action@tag references that need to be pinned.

- [ ] **Step 2: Resolve current SHAs for each action**

For each action, use `gh api` to resolve the tag to a commit SHA:

```bash
# Example for actions/checkout@v6:
gh api repos/actions/checkout/git/ref/tags/v6 --jq '.object.sha'
# If the tag points to a tag object (not a commit), dereference:
gh api repos/actions/checkout/git/refs/tags/v6 --jq '.object.sha'
```

Alternatively use `gh release view` for actions that use release tags.

Collect SHAs for each action used:
- `actions/checkout`
- `astral-sh/setup-uv`
- `actions/setup-node`
- `dorny/paths-filter`
- Any others found in the grep output

- [ ] **Step 3: Replace tag references with SHA + comment**

Format: `owner/action@<40-char-sha> # v<tag>`

Example:

```yaml
# Before:
- uses: actions/checkout@v6

# After:
- uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v6
```

Apply to every `uses:` line in both workflow files.

- [ ] **Step 4: Verify YAML is valid**

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))" && echo "ci.yml valid"
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/docs-deploy.yml'))" && echo "docs-deploy.yml valid"
```

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/ci.yml .github/workflows/docs-deploy.yml
git commit -m "fix: pin all GitHub Action versions to commit SHAs (S12)"
```

---

### Task 4: S13 — Document fork-PR runner security assumption in `ci.yml`

Both workflows use `on: pull_request:`. For a private repo this only allows collaborators — safe today. If the repo is ever made public, any public PR would execute untrusted code on the Pi runner. There is no `environment:` protection gate.

**Files:**
- Modify: `.github/workflows/ci.yml`

- [ ] **Step 1: Add a comment block to `ci.yml`**

Near the top of `ci.yml`, after the `on:` block, add:

```yaml
# SECURITY NOTE: self-hosted runner model
# Both workflows use `on: pull_request:` which only allows PRs from
# collaborators on a PRIVATE repository. The self-hosted runner is a
# production Raspberry Pi with GPIO hardware access.
#
# If this repo is ever made public, the following changes are REQUIRED
# before any PR is accepted:
#   1. Add `environment: ci` to all jobs that run on self-hosted
#      (requires reviewer approval before workflow runs on fork PRs)
#   OR
#   2. Migrate fork PRs to `workflow_run:` trigger so untrusted code
#      does not run on the self-hosted runner.
#
# Do not make the repo public without implementing one of the above.
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "docs: add fork-PR self-hosted runner security note to ci.yml (S13)"
```

---

### Task 5: M13 — Add Docker ecosystem to Dependabot config

`.github/dependabot.yml` covers `github-actions`, `pip`, and `npm` but not `docker`. `python:3.13-bullseye` reaches Debian 11 EOL in June 2026 — approximately one month from now. After EOL, security patches stop.

**Files:**
- Modify: `.github/dependabot.yml`

- [ ] **Step 1: Add the Docker ecosystem entry**

In `.github/dependabot.yml`, after the `npm` entry, add:

```yaml
  # Docker base image — python:3.13-bullseye (Debian 11) hits EOL June 2026.
  # Dependabot will file a PR when a new python:3.13-* image is released.
  # Before accepting the bookworm bump, verify the GCC 10 RP1 build patch
  # in the Dockerfile (named anonymous PIO params) still compiles under
  # GCC 12. See M14 note in Dockerfile comments.
  - package-ecosystem: docker
    directory: /
    schedule:
      interval: weekly
```

- [ ] **Step 2: Commit**

```bash
git add .github/dependabot.yml
git commit -m "fix: add docker ecosystem to dependabot.yml for base image tracking (M13)"
```

---

### Task 6: M14 — Add bookworm migration note to Dockerfile

`Dockerfile` retains build tools in the final image (no multi-stage build) and uses `python:3.13-bullseye` which hits EOL June 2026. The migration is non-trivial (verify GCC 12 compat with the RP1 build patch) but should be tracked.

**Files:**
- Modify: `Dockerfile`

- [ ] **Step 1: Add a migration note comment**

In `Dockerfile`, at the top of the file or near the `FROM python:3.13-bullseye` line, add:

```dockerfile
# Base image migration note (M14):
# python:3.13-bullseye (Debian 11) reaches EOL June 2026. Migrate to
# python:3.13-bookworm (Debian 12, GCC 12) when ready. Before migrating:
#   1. Verify the RP1 build patch (named anonymous PIO params in pio_rp1.c)
#      still compiles cleanly under GCC 12 — it was written for GCC 10.
#   2. Test a multi-stage build: copy only the compiled rgbmatrix .so from
#      the build stage into a python:3.13-bookworm-slim final stage (~200MB
#      smaller). Verify libstdc++/libgcc links are satisfied by the slim image.
#   3. Run make test + test on both Pi 4 and Pi 5 hardware before merging.
```

- [ ] **Step 2: Commit**

```bash
git add Dockerfile
git commit -m "docs: add bookworm migration plan note to Dockerfile (M14)"
```

---

## Self-Review

**Spec coverage:**

| Finding | Task | Status |
|---------|------|--------|
| S8 — no coverage threshold | Task 1 | ✅ |
| S9 — no Docker build in CI | Task 2 | ✅ |
| S12 — mutable action tags | Task 3 | ✅ |
| S13 — fork PR runner risk undocumented | Task 4 | ✅ |
| M13 — no Docker in Dependabot | Task 5 | ✅ |
| M14 — bullseye EOL migration not tracked | Task 6 | ✅ |

**Placeholder scan:** No TBD/TODO in steps. The SHA values in Task 3 must be resolved at execution time using `gh api` — they cannot be hardcoded here.

**Order note:** Task 1 (coverage) and Task 2 (Docker build) can be PRed together so the new CI checks are verified atomically.
