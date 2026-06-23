# No-Rebuild Plugin Install — Design (Spec 1: Plugin Store foundation)

**Date:** 2026-06-22
**Status:** Approved (brainstorm + hobbyist-persona review)
**Scope:** The foundation for the future Web Plugin Store — make plugin install/removal a **restart**, not a Docker image **rebuild**, and keep the local (bare-metal) flow equally natural.

## Goal

Today, changing plugins in Docker means editing `config/requirements-plugins.txt` and running `docker compose up -d --build` (a full image rebuild, minutes). After this spec:

> **Edit `requirements-plugins.txt` → `docker compose restart` → plugins installed + active. No `--build`.**

The manifest (`requirements-plugins.txt`) is the **source of truth**; a startup hook **reconciles** the runtime against it. Independently valuable + fully testable with zero web surface. The Web Plugin Store (Spec 2) layers on this later.

## Settled decisions (brainstorm + hobbyist review)

1. **Sequencing:** foundation first; the web Store UI is a separate later spec.
2. **Local target:** local/bare-metal installs into the **active venv** (today's `led-ticker plugin install` behavior). Docker installs into a **plugins volume**. One reconcile, two natural backends, auto-detected.
3. **Docker volume mechanism:** a **`--system-site-packages` venv on a named volume** (inherits core from the image; only plugins + their *new* deps live on the volume — no core duplication, first-install downloads only what's new). The image stays immutable.
4. **Reconcile model:** **true sync** — install declared-but-missing plugins AND uninstall installed-but-undeclared ones. The manifest is fully authoritative. Uninstall is **scoped to `led_ticker.plugins` entry-point packages only** — never core, never non-plugin packages.
5. **Activation:** restart-to-apply (reconcile runs at startup). No live hot-load in this spec (a restart is seconds, not a rebuild). Hot-load deferred.
6. **Visibility (hobbyist):** reconcile results are **surfaced on the web status page** + logged with clear progress — not buried in `docker compose logs`.

## Architecture / Components

### 1. Plugins volume + venv (Docker)
- New named volume **`ticker-plugins`** mounted at **`/data/plugins`** on the **display** service, `rw`. (compose.yaml; with an explanatory comment — see §7.)
- A venv at **`/data/plugins/venv`** created with the image's Python via `python -m venv --system-site-packages` so it inherits core. Created/owned by **root**, **before** `RGBMatrix()` drops privileges (constraint #13 — same slot as `board.prepare_dir()`).
- The venv is **version-stamped** (a small `python-version` marker file). If the image's Python version changed (image upgrade), the reconcile **recreates** the venv and reinstalls from the manifest.

### 2. Startup reconcile hook (`plugin_reconcile.py`)
Runs in the established **pre-frame-build / pre-root-drop slot** in `app/run.py` (right after `board.prepare_dir()`, **before** `_load_plugins_for_config` and before `build_frame_from_config`). Steps:
1. Resolve the **target backend**: container (volume present) → the volume venv; else → the active venv. **Log the chosen target** ("reconcile: installing into /data/plugins/venv" / "<active venv path>").
2. Read the manifest (`config/requirements-plugins.txt`). If absent, **log a hint** ("no requirements-plugins.txt — copy requirements-plugins.example.txt to add plugins") and skip.
3. **Diff** the manifest's declared plugins against currently-installed `led_ticker.plugins` entry-point packages (reuse `_installed_namespaces` / dist-key logic from `app/plugin_cmd.py`).
4. **Install** declared-but-missing, **constraint-pinned** (reuse `_pip_install`'s frozen-core constraints, targeting the resolved venv's pip). **Uninstall** installed-but-undeclared plugin packages (scoped to the entry-point group). Log each action with progress.
5. **Per-plugin failure isolation:** any single install/uninstall failure is caught, recorded, and logged — the reconcile continues and the panel still boots (mirrors load-time plugin isolation). NEVER raise out of the hook.
6. Return a **reconcile result** (per-plugin: installed / uninstalled / unchanged / failed + message) for status surfacing.

### 3. `sys.path` integration
Before `load_plugins_for_config`, insert the volume venv's `site-packages` into `sys.path` so plugins reconciled this boot are importable in the same run (local needs nothing — they're in the active venv). Entry-point discovery (`importlib.metadata.entry_points`) then finds them.

### 4. Mode detection
A single helper decides volume-venv vs active-venv: container iff the plugins volume mount exists (e.g. `/data/plugins` present + writable) — otherwise local. Deterministic + testable; logged.

### 5. Web-status surfacing
Add a **`plugins` (reconcile) block** to the status board (schema bump): last reconcile timestamp + per-plugin state (installed/uninstalled/unchanged/failed + error). The webui renders it so a hobbyist sees "Plugin install failed: led-ticker-rss (see logs)" without `docker compose logs`. (Mirrors how `disabled_widgets` is surfaced.) Recorded pre-drop is fine — the status board is already written in this slot.

### 6. Logging / feedback
- Progress per action: `reconcile: installing led-ticker-rss … done` / `removing led-ticker-foo … done`.
- No-manifest hint (§2.2); chosen-target log (§2.1).
- A constraint/pip failure logs a friendly one-line cause + "see the plugin's docs" (raw pip error demoted to DEBUG).

### 7. compose.yaml + docs
- Add the `ticker-plugins` volume + the `/data/plugins` mount on the display service, **with a comment**: what it holds, and "to reset all installed plugins: `docker volume rm ticker-plugins && docker compose restart`".
- Docs: a prominent **"add a plugin in seconds — edit `requirements-plugins.txt` then `docker compose restart` (no `--build`)"** callout on the Plugins page; document removal (delete the line → restart) and the reset command. Each plugin page already shows its exact install line (from the PyPI-install work, #270).

## Reuse (don't reinvent)
`app/plugin_cmd.py`: `_pip_install` (constraint-pinned), `_installed_namespaces` (entry-point discovery), the manifest parse / `_declared_keys` / dist-key helpers, `_remove_requirement`. The reconcile is a new orchestrator over these, parameterized by the target venv's pip.

## Security
The reconcile installs/uninstalls from the **trusted local manifest** (a file on the host/config volume), supporting any pip spec exactly as `led-ticker plugin install` does today — no new web surface here. The webui already mounts `config/` `:rw` (for the config editor), so Spec 2's web manifest write fits later; **catalog-only enforcement of web-originated writes is a Spec 2 concern.**

## Testing
- **Unit (mock pip + fs):** diff/sync logic (install-missing, uninstall-undeclared, unchanged); per-plugin failure isolation (one fails → others proceed, panel boots); venv version-staleness recreate; mode detection (volume vs active venv); reconcile-result shape; uninstall scoped to entry-point packages only (never core).
- **Tripwire:** the reconcile hook runs **before** frame build / root drop (extend the `test_setup_runs_before_frame_build` family).
- **Status:** the reconcile block serializes into the status schema; webui renders failures.
- **Docker/hardware smoke** (can't be unit-tested): edit manifest → `compose restart` → plugin present, no rebuild; remove line → restart → plugin gone; delete volume → restart → reinstalled.

## Non-goals (this spec)
- The **web Plugin Store UI** + web-driven manifest writes (Spec 2).
- **Live hot-load** without a restart (registries populate at startup; restart-to-activate is the appliance model).
- **Catalog-only / arbitrary-spec security hardening** of web-originated installs (Spec 2 — there are no web writes here).
- Changing where the manifest lives (stays `config/requirements-plugins.txt`).

## Risks / open items
- **Constraint #13:** the reconcile MUST run while still root (to create the venv on the root-owned volume mountpoint) and BEFORE `load_plugins`. Mis-ordering = either a permission failure or plugins not importable. Guarded by the pre-drop-slot tripwire.
- **venv Python-version staleness:** handled by the version-stamp + recreate; the recreate path needs network (first boot after an image Python bump) — logged.
- **True-sync uninstall safety:** must only ever uninstall packages in the `led_ticker.plugins` entry-point group AND absent from the manifest — explicit guard + test so it can never touch core or a non-plugin dependency.
- The Docker build's existing Layer-2b plugin install (`requirements-plugins.txt` baked at build) becomes redundant for the no-rebuild path; decide in the plan whether to keep it (works for a baked image) or drop it (volume reconcile is now the path). Likely keep as a harmless fallback; the plan resolves it.
