# Releasing led-ticker to PyPI

This runbook covers the one-time setup required before any package can be published, the first-publish sequence (core then plugins), and the procedure for subsequent releases.

**Who:** the repository owner (`JamesAwesome`).  
**Packages:** `led-ticker-core` (core, `led-ticker` repo) + six plugin packages (`led-ticker-pool`, `led-ticker-baseball`, `led-ticker-crypto`, `led-ticker-calendar`, `led-ticker-rss`, `led-ticker-weather`) in the `led-ticker-plugins` repo.

---

## A. One-time PyPI setup

These steps are performed once by the maintainer before any GitHub Release is created.

### 1. Create a PyPI account and enable 2FA

1. Go to <https://pypi.org/account/register/> and create an account.
2. Open **Account settings → Two-factor authentication** and enroll a TOTP authenticator (or a hardware key). 2FA is mandatory to publish; PyPI will refuse uploads from accounts without it.

No API tokens are created. Authentication uses Trusted Publishing (OIDC) — the workflow proves identity via GitHub Actions; PyPI never sees a secret.

### 2. Add pending Trusted Publishers

For each package below, go to <https://pypi.org/manage/account/publishing/> → **"Add a new pending publisher"** and fill in the values exactly as shown.

A *pending* Trusted Publisher creates the PyPI project automatically on the first successful workflow run — there is no need to pre-create the project.

| PyPI project | Owner | Repository | Workflow | Environment |
|---|---|---|---|---|
| `led-ticker-core` | `JamesAwesome` | `led-ticker` | `publish.yml` | `release` |
| `led-ticker-pool` | `JamesAwesome` | `led-ticker-plugins` | `publish.yml` | `release` |
| `led-ticker-baseball` | `JamesAwesome` | `led-ticker-plugins` | `publish.yml` | `release` |
| `led-ticker-crypto` | `JamesAwesome` | `led-ticker-plugins` | `publish.yml` | `release` |
| `led-ticker-calendar` | `JamesAwesome` | `led-ticker-plugins` | `publish.yml` | `release` |
| `led-ticker-rss` | `JamesAwesome` | `led-ticker-plugins` | `publish.yml` | `release` |
| `led-ticker-weather` | `JamesAwesome` | `led-ticker-plugins` | `publish.yml` | `release` |

---

## B. Create the `release` environment in each repo

The `publish.yml` workflow targets `environment: release`. GitHub pauses the workflow at that gate and waits for a required-reviewer approval before allowing PyPI upload. You must create this environment in both repos.

### Resolve your numeric user ID (run once)

```bash
gh api /users/JamesAwesome -q .id
# → 1824546
```

### Create the environment via the GitHub CLI

Run the command once for each repo, substituting the repo name:

```bash
# Core repo
gh api --method PUT "/repos/JamesAwesome/led-ticker/environments/release" \
  -f "reviewers[][type]=User" -F "reviewers[][id]=1824546"

# Plugins repo
gh api --method PUT "/repos/JamesAwesome/led-ticker-plugins/environments/release" \
  -f "reviewers[][type]=User" -F "reviewers[][id]=1824546"
```

### Alternative: Settings UI

Go to **Settings → Environments → New environment**, name it `release`, tick **Required reviewers**, and add yourself. Repeat in both repos.

---

## C. First-publish sequence

Plugins declare `led-ticker-core` as a dependency, so **core must be on PyPI before any plugin is published.**

### Step 1: Publish `led-ticker-core` (core)

`led-ticker-core` uses hatch-vcs: the package version is derived from the git tag — no `pyproject.toml` edit is needed or correct. The tag **is** the version.

1. Merge the release branch to `main`.
2. On GitHub: **Releases → Draft a new release**.
   - Tag: `v2.0.0` (create new tag, target `main`)
   - Title: `v2.0.0`
   - Click **Publish release**.
3. The `publish.yml` workflow fires, builds the distribution from the tag-derived version, and **pauses for approval** at the `release` environment gate.
4. Go to **Actions → the running workflow → Review deployments** → approve.
5. Wait for the job to complete, then verify: <https://pypi.org/project/led-ticker-core/>.

Untagged builds (e.g. `main` between releases) report a version like `2.0.1.dev4+gabcdef0` — that's expected and correct.

### Step 2: Publish each plugin

Repeat for each plugin package. Tags are scoped by plugin name so all packages can be managed in the same monorepo without triggering each other's workflows.

For each plugin (example shown for `led-ticker-pool`):

> **Tag format:** `<plugin>-v<version>` using the SHORT plugin name (`pool`, `baseball`, `crypto`, `calendar`, `rss`, `weather`) — NOT the full PyPI package name. This matches the existing tag convention and the allowlist in `scripts/check_release.py`; a full-name tag like `led-ticker-pool-v…` is rejected as an unknown plugin. The `<version>` must equal the plugin's `pyproject.toml` version or the tag-vs-version guard fails the run.

1. Confirm the plugin's `pyproject.toml` version (e.g. `pool` is currently `0.1.0`).
2. On GitHub (`led-ticker-plugins`): **Releases → Draft a new release**.
   - Tag: `pool-v0.1.0`
   - Target: `main`
   - Title: `led-ticker-pool 0.1.0`
   - Click **Publish release**.
3. The `publish.yml` workflow inspects the tag prefix, resolves to the `plugins/pool/` directory, builds, and pauses for approval.
4. Approve via **Actions → Review deployments**.
5. Verify: <https://pypi.org/project/led-ticker-pool/>.

Tag prefixes for each plugin:

| Package | Release tag (short name + current version) |
|---|---|
| `led-ticker-pool` | `pool-v0.1.0` |
| `led-ticker-baseball` | `baseball-v0.1.0` |
| `led-ticker-crypto` | `crypto-v0.2.0` |
| `led-ticker-calendar` | `calendar-v0.1.0` |
| `led-ticker-rss` | `rss-v0.2.0` |
| `led-ticker-weather` | `weather-v0.2.0` |

---

## D. Verification

After each publish, confirm the package installs cleanly from PyPI in a fresh virtual environment.

```bash
# Verify core
python -m venv /tmp/verify-core
/tmp/verify-core/bin/pip install led-ticker-core
/tmp/verify-core/bin/led-ticker --help

# Verify a plugin (confirm led-ticker-core was pulled transitively)
python -m venv /tmp/verify-pool
/tmp/verify-pool/bin/pip install led-ticker-pool
/tmp/verify-pool/bin/pip show led-ticker-pool | grep -i requires
# "Requires: led-ticker-core" must appear in the output
```

Repeat the plugin block for each package, substituting the package name:

```bash
# led-ticker-baseball
python -m venv /tmp/verify-baseball
/tmp/verify-baseball/bin/pip install led-ticker-baseball
/tmp/verify-baseball/bin/pip show led-ticker-baseball | grep -i requires

# led-ticker-crypto
python -m venv /tmp/verify-crypto
/tmp/verify-crypto/bin/pip install led-ticker-crypto
/tmp/verify-crypto/bin/pip show led-ticker-crypto | grep -i requires

# led-ticker-calendar
python -m venv /tmp/verify-calendar
/tmp/verify-calendar/bin/pip install led-ticker-calendar
/tmp/verify-calendar/bin/pip show led-ticker-calendar | grep -i requires

# led-ticker-rss
python -m venv /tmp/verify-rss
/tmp/verify-rss/bin/pip install led-ticker-rss
/tmp/verify-rss/bin/pip show led-ticker-rss | grep -i requires

# led-ticker-weather
python -m venv /tmp/verify-weather
/tmp/verify-weather/bin/pip install led-ticker-weather
/tmp/verify-weather/bin/pip show led-ticker-weather | grep -i requires
```

---

## E. Re-releases

PyPI forbids re-uploading a file for an existing version. If a release has an error:

**For `led-ticker-core`** (hatch-vcs, tag-driven):
1. Create a new GitHub Release with a higher version tag (e.g. `v2.0.1`). The package version is derived from the tag — no `pyproject.toml` edit needed.

**For plugins** (static versions in their `pyproject.toml`):
1. Bump the version in the relevant `plugins/<name>/pyproject.toml` (e.g. `0.1.0` → `0.1.1`).
2. Create a new GitHub Release with a matching tag (e.g. `pool-v0.1.1` — short plugin name). The tag-vs-version guard in the plugins workflow checks that the tag version matches `pyproject.toml` — a mismatch fails the build before any upload is attempted.

There is no way to overwrite or delete an already-published version on PyPI. Plan releases accordingly and use the approval gate (section B) to catch mistakes before the upload runs.
