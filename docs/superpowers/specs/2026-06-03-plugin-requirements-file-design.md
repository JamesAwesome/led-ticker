# Plugin-Requirements File — Design

**Date:** 2026-06-03
**Status:** Approved (brainstorm), pending implementation plan

## Goal

Move the external-plugin install out of the hardcoded `Dockerfile` layer into a
declarative, requirements.txt-style file, so that:

1. The `Dockerfile` (the image definition) no longer hardcodes specific plugins
   — plugins are "what this sign runs," declared separately.
2. People who **clone the repo** can customize which plugins they install as part
   of their normal setup process, the same way they customize `config.toml` and
   `.env`.

Installation stays **build-time** (consistent with goal 1 — no runtime/network-at-boot
install). Changing plugins means editing the file and rebuilding the image.

The Dockerfile installs the **live** file only (`config/requirements-plugins.txt`); there
is **no fallback to the example**. The example is a copy-me template — a fresh clone
installs **no plugins** until you `cp` the example to the live file. (Pool is therefore
not baked into a fresh `git clone && docker compose up --build`; that's an accepted
tradeoff for keeping the model explicit and the example purely a template.)

## Background / current state

- `Dockerfile` "Layer 2b" hardcodes the pool plugin:
  ```dockerfile
  ARG POOL_PLUGIN_CACHE_BUST=1
  RUN pip install --no-cache-dir --no-deps \
      "git+https://github.com/JamesAwesome/led-ticker-pool.git@main"
  ```
- `--no-deps` is required because `led-ticker` is **not published to PyPI**, and the
  plugins' runtime deps (e.g. `aiohttp`) are already core app dependencies; a plain
  `pip install` would try (and fail) to resolve `led-ticker` from PyPI.
- Plugins are auto-discovered at runtime via the `led_ticker.plugins` entry point
  (`load_plugins(..., entry_points_enabled=True)` is the default); no config opt-in
  is needed for an installed plugin to register.
- `.dockerignore` excludes `config/config.toml` + a couple example configs, but does
  **not** exclude arbitrary `config/*.txt`, so the new files reach the build context.
- No `config/plugins/` directory exists yet (the `[plugins].dir` default), so the
  chosen filename avoids that latent collision.

## Design

### 1. Files & naming

- **`config/requirements-plugins.example.txt`** — tracked. The working default; ships
  with the pool plugin line plus a header comment documenting the format and the
  `--no-deps` contract:
  ```
  # Plugins to install into the image (pip requirements format, one per line).
  # Copy this file to config/requirements-plugins.txt and edit it for your signs,
  # then rebuild: docker compose up -d --build
  #
  # Installed with --no-deps (led-ticker is not on PyPI). If a plugin needs a
  # runtime library beyond what led-ticker already ships, add it as its own line.
  git+https://github.com/JamesAwesome/led-ticker-pool.git@main
  ```
- **`config/requirements-plugins.txt`** — gitignored. The cloner's live copy; absent
  on a fresh clone.
- `.gitignore` gains `config/requirements-plugins.txt` (alongside `config/config.toml`).

Naming: `requirements-plugins` (not `plugins.txt`) avoids colliding with the
`[plugins].dir` → `config/plugins/` local-plugin directory, and matches the name the
`led-ticker-pool` README already references.

### 2. Dockerfile change (replaces Layer 2b)

```dockerfile
# Layer 2b: external plugins, declared in config/requirements-plugins.txt
# (gitignored; copy config/requirements-plugins.example.txt to create it).
# Installed --no-deps because led-ticker is not on PyPI and plugin runtime deps
# are already app deps; a plugin needing an extra lib must list it as its own
# line. Installs the live file only — if it is absent, no plugins are installed
# (no fallback to the example). The .tx[t] glob is the optional-file trick: it
# copies the live file if present and is silently skipped if not; the .example
# is always present so the COPY itself always succeeds.
COPY config/requirements-plugins.example.txt config/requirements-plugins.tx[t] /code/config/
RUN if [ -f /code/config/requirements-plugins.txt ]; then \
        pip install --no-cache-dir --no-deps -r /code/config/requirements-plugins.txt; \
    else \
        echo "No config/requirements-plugins.txt; skipping plugin install \
(copy config/requirements-plugins.example.txt to add plugins)"; \
    fi
```

- Installs the **live** file only. If it is absent the step is a no-op (the build
  succeeds with no plugins) — there is **no fallback** to the example.
- The example is always copied (as the guaranteed COPY source for the optional-file
  trick) and lands in the image as a template, but it is **never installed**.
- This is its own cached layer placed before `COPY . /code/`, so editing the live file
  invalidates the cache and triggers reinstall — the **`POOL_PLUGIN_CACHE_BUST` ARG is
  removed** (no longer needed).
- An empty or all-comments live file is valid (`pip install -r` is a no-op), so a cloner
  can run zero plugins by emptying the file.

### 3. Bare-metal install + onboarding

- `deploy/install.sh`: after the existing `pip install --upgrade "${REPO_DIR}"`, install
  the plugins file (live, else example) with `--no-deps` if it exists:
  ```sh
  PLUGINS_REQ="${REPO_DIR}/config/requirements-plugins.txt"
  [ -f "$PLUGINS_REQ" ] && pip install --no-deps -r "$PLUGINS_REQ"
  ```
  Live file only — no fallback to the example, matching the Dockerfile.
- Setup docs (README / onboarding) mention the new file next to `cp config.example.toml
  config.toml` and the `.env` step: "to add or remove plugins, copy
  `config/requirements-plugins.example.txt` to `config/requirements-plugins.txt`, edit,
  and rebuild."

### 4. Relationship to the existing `[plugins]` config block (no overlap)

These are complementary layers, stated explicitly to avoid confusion:

- **`config/requirements-plugins.txt`** controls what is **installed** (pip packages,
  build-time).
- The **`[plugins]` block in `config.toml`** controls what is **loaded** at runtime:
  entry-point discovery is on by default; `[plugins].disable = [...]` skips a namespace;
  `[plugins].dir` points at a local-plugin directory. It does not install anything.

A plugin must be installed (requirements file) **and** not disabled (`[plugins]`) to be
active.

## Error handling / edge cases

- **Missing live file:** no plugins installed; build still succeeds (no fallback to the example).
- **Empty / comments-only file:** `pip install -r` is a no-op; zero plugins installed.
- **Unresolvable git ref / bad line:** the build fails at the pip step with pip's error —
  surfaced at build time, not at runtime. Acceptable (build-time is the right place to
  catch it).
- **Plugin needing an extra runtime dep:** with `--no-deps`, the dep is not auto-pulled;
  the contract (documented in the header) is to add it as its own line. Out of scope to
  solve generally (that was Approach B, deferred as premature).

## Testing

- Unit/repo test: `config/requirements-plugins.example.txt` exists, parses as pip
  requirements (no obviously malformed lines), and contains the pool git URL line.
- Guard test or doc-drift check: the `Dockerfile` references
  `requirements-plugins` and no longer contains `POOL_PLUGIN_CACHE_BUST`.
- Manual verification:
  - `docker compose build` with **no** live file → no plugins installed (`led-ticker
    plugins` lists none); build succeeds.
  - `cp config/requirements-plugins.example.txt config/requirements-plugins.txt` then
    `docker compose build` → `pool.monitor` registered (`led-ticker plugins` lists `pool`).
  - Edit the live file (e.g. remove pool) and rebuild → `led-ticker plugins` reflects the
    new set.

## Out of scope

- Runtime / no-rebuild plugin installation (Approach B/C from brainstorm).
- Dependency-resolution machinery for plugins with novel transitive deps (constraints
  file). Deferred until a real plugin needs it.
- Publishing `led-ticker` to PyPI (would remove the `--no-deps` requirement entirely;
  separate, larger decision).
