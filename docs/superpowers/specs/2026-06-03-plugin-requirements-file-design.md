# Plugin-Requirements File — Design

**Date:** 2026-06-03
**Status:** Implemented

## Goal

Move the external-plugin install out of the hardcoded `Dockerfile` layer into a
declarative, requirements.txt-style file, so that:

1. The `Dockerfile` (the image definition) no longer hardcodes specific plugins
   — plugins are "what this sign runs," declared separately.
2. People who **clone the repo** can customize which plugins they install as part
   of their normal setup process, the same way they customize `config.toml` and
   `.env`.

Installation stays **build-time** (consistent with goal 1 — no runtime/network-at-boot
install), with dependency resolution constrained to core's pinned versions.
Changing plugins means editing the file and rebuilding the image.

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
- `--no-deps` was used originally because `led-ticker` is **not published to PyPI**; a
  plain `pip install` would try (and fail) to resolve `led-ticker` from PyPI. The new
  approach uses `-c constraints-core.txt` with dependency resolution enabled: pip finds
  `led-ticker` already installed (no PyPI hit needed) and pins everything else to core's
  versions.
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
  constraints contract:
  ```
  # Plugins to install into the image (pip requirements format, one per line).
  # Copy this file to config/requirements-plugins.txt and edit it for your signs,
  # then rebuild: docker compose up -d --build
  #
  # Installed with pip dependency resolution, constrained to led-ticker's core
  # dependency versions: a plugin may pull its own new libraries, but may not move
  # a version that core already pins (that fails the build).
  git+https://github.com/JamesAwesome/led-ticker-pool.git@main
  ```
- **`config/requirements-plugins.txt`** — gitignored. The cloner's live copy; absent
  on a fresh clone.
- `.gitignore` gains `config/requirements-plugins.txt` (alongside `config/config.toml`).

Naming: `requirements-plugins` (not `plugins.txt`) avoids colliding with the
`[plugins].dir` → `config/plugins/` local-plugin directory, and matches the name the
`led-ticker-pool` README already references.

### 2. Dockerfile change (Layer 2 + Layer 2b)

Layer 2 now snapshots the core environment after installing:

```dockerfile
# Layer 2: app dependencies (only rebuilds if pyproject.toml changes). After
# installing, snapshot the exact installed versions into a pip constraints file
# (constraints-core.txt) so plugin installs in Layer 2b can pull their own new
# deps but cannot move core's stack. `pip list --format=freeze` renders the
# editable led-ticker as `led-ticker==<v>` (a valid constraint), unlike
# `pip freeze` which emits an unusable `-e ...` line.
FROM rgbmatrix
WORKDIR /code
COPY pyproject.toml /code/
RUN pip install --no-cache-dir -e ".[dev]" \
 && pip list --format=freeze > /code/constraints-core.txt
```

Layer 2b installs plugins with dependency resolution constrained to core's versions:

```dockerfile
# Layer 2b: external plugins, declared in config/requirements-plugins.txt
# (gitignored; copy config/requirements-plugins.example.txt to create it).
# Installed WITH dependency resolution but constrained to the core versions
# captured in Layer 2 (-c constraints-core.txt): led-ticker is already installed
# so it resolves without hitting PyPI, a plugin may pull its own genuinely-new
# transitive deps, but a plugin that tries to move a core dep fails loudly here
# at build rather than silently at runtime. Installs the live file only — if it
# is absent, no plugins are installed (no fallback to the example). The .tx[t]
# glob is the optional-file trick: it copies the live file if present and is
# skipped if not; the .example is always present so the COPY always succeeds.
# Editing the live file invalidates this cached layer and triggers a reinstall.
COPY config/requirements-plugins.example.txt config/requirements-plugins.tx[t] /code/config/
RUN if [ -f /code/config/requirements-plugins.txt ]; then \
        pip install --no-cache-dir -c /code/constraints-core.txt -r /code/config/requirements-plugins.txt; \
    else \
        echo "No config/requirements-plugins.txt; skipping plugin install (copy the .example to add plugins)"; \
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
  the plugins file (live only) constrained to the core versions just installed:
  ```sh
  PLUGINS_REQ="${REPO_DIR}/config/requirements-plugins.txt"
  if [ -f "$PLUGINS_REQ" ]; then
      CONSTRAINTS="$(mktemp)"
      pip list --format=freeze > "$CONSTRAINTS"
      pip install -c "$CONSTRAINTS" -r "$PLUGINS_REQ"
      rm -f "$CONSTRAINTS"
  fi
  ```
  `pip list --format=freeze` generates the constraints from the live venv (led-ticker
  renders as `led-ticker==<v>`, a valid constraint). Live file only — no fallback to
  the example, matching the Dockerfile.
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
- **Plugin needing an extra runtime dep:** pip resolves and installs it (constrained to
  core versions); the plugin simply lists it as a dependency in its own metadata.
- **Plugin pins a conflicting core dep version** (e.g. `pillow<10` when core pins
  `pillow>=10`): build fails loudly with pip `ResolutionImpossible` at Layer 2b —
  the conflict surfaces at build time, not silently at runtime. Intended: core's stack
  is authoritative.

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
- Publishing `led-ticker` to PyPI (would simplify the constraints story; separate,
  larger decision).
