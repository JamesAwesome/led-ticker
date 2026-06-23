# No-Rebuild Plugin Install — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make plugin install/removal a `docker compose restart` (or a local restart), not an image rebuild — a startup reconcile installs/uninstalls plugins to match `config/requirements-plugins.txt` (the source of truth).

**Architecture:** A new `src/led_ticker/plugin_reconcile.py` runs at the TOP of `app/run.py:run()` (before `_load_plugins_for_config`, while still root). It resolves a target (Docker: a `--system-site-packages` venv on the `ticker-plugins` volume; local: the active venv), diffs the manifest against installed `led_ticker.plugins` entry-point packages, installs missing + uninstalls undeclared (guarded), records a result to the status board, and inserts the volume venv's site-packages into `sys.path` so reconciled plugins import this boot. The Docker build's Layer-2b plugin install is dropped — the volume is the single path.

**Tech Stack:** Python 3.14, `importlib.metadata`, `subprocess`+pip, `tomllib`, aiohttp webui, Docker/compose, attrs.

**Spec:** `docs/superpowers/specs/2026-06-22-no-rebuild-plugin-install-design.md`

## Global Constraints

- **Reconcile runs BEFORE `_load_plugins_for_config` and BEFORE `build_frame_from_config`** (root not yet dropped — constraint #13). It is the new first step in `run()`.
- **The reconcile NEVER raises** — any failure is caught, recorded, logged; the panel must boot (constraint #1). Per-plugin isolation.
- **True sync:** install declared-but-missing AND uninstall installed-but-undeclared.
- **Uninstall guards (ALL required, each tested):** (a) scope to `led_ticker.plugins` entry-point dists; (b) resolve the dist via the installed `EntryPoint.dist.name`, NOT the catalog `led-ticker-<name>` guess; (c) skip-if-depended-on (another installed dist `requires` it); (d) skip-if-config-references-it (a widget `type` under the namespace is in `config.toml`) → skip + warn + status "removal blocked"; (e) target the resolved venv's OWN pip; (f) rely on the `--system-site-packages` floor (core un-uninstallable from the volume venv).
- **Docker volume:** named `ticker-plugins` → `/data/plugins` (rw on the display service); venv at `/data/plugins/venv` (`--system-site-packages`); version-stamped, recreated on Python-version change.
- **Manifest stays** `config/requirements-plugins.txt` (read-only read here).
- **Reuse** `app/plugin_cmd.py`: `_installed_namespaces`, `_pip_install`/`_pip_uninstall` (parameterize by target python), `_declared_keys`, manifest parse.
- **Gates:** `PYTHONPATH=tests/stubs uv run --extra dev pytest`; `uv run --extra dev ruff check src/ tests/` + `ruff format`; `pyright src/`; docs via `make docs-build` + `make docs-lint`.
- **NON-GOALS:** web Store UI, web manifest writes, live hot-load, catalog-only web-install hardening, moving the manifest (all Spec 2 / deferred).

## File Structure

- `src/led_ticker/plugin_reconcile.py` — NEW: result types, mode/target detection, volume-venv mgmt, the guards, the `reconcile()` orchestrator, `apply_to_syspath()`. Pure-ish (subprocess/fs injected or monkeypatchable).
- `src/led_ticker/app/plugin_cmd.py` — MODIFY: `_pip_install`/`_pip_uninstall` gain an optional `python_exe: str = sys.executable`.
- `src/led_ticker/app/run.py` — MODIFY: call `reconcile()` + `apply_to_syspath()` at the top of `run()`, before `_load_plugins_for_config`; record the result.
- `src/led_ticker/status_board.py` — MODIFY: `plugin_reconcile` field + `record_plugin_reconcile()` + snapshot + `SCHEMA_VERSION` 6→7.
- `src/led_ticker/webui/static/index.html` (+ any webui render) — MODIFY: render the reconcile block.
- `Dockerfile` — MODIFY: drop Layer-2b.
- `compose.yaml` — MODIFY: add `ticker-plugins` volume + `/data/plugins` mount (commented).
- Docs: `docs/site/src/content/docs/plugins/*` + `docs/content-source/plugins/*` — MODIFY: the no-rebuild callout + removal/reset/offline.
- Tests: `tests/test_plugin_reconcile.py` (NEW), extend `tests/test_status_*`, the `test_setup_runs_before_frame_build` family, `tests/test_plugins/`.

---

## Task 1: Reconcile result types + diff

**Files:** Create `src/led_ticker/plugin_reconcile.py`; Test `tests/test_plugin_reconcile.py`

**Interfaces — Produces:**
- `@attrs.frozen class PluginAction: namespace: str; action: str  # "installed"|"uninstalled"|"unchanged"|"failed"|"blocked"; detail: str = ""`
- `def compute_diff(declared: set[str], installed: set[str]) -> tuple[set[str], set[str]]` → `(to_install, to_uninstall)` where to_install = declared−installed, to_uninstall = installed−declared.

- [ ] **Step 1: failing test** — `tests/test_plugin_reconcile.py`:
```python
from led_ticker.plugin_reconcile import compute_diff, PluginAction


def test_compute_diff_install_and_uninstall():
    to_install, to_uninstall = compute_diff(
        declared={"pool", "rss"}, installed={"pool", "old"}
    )
    assert to_install == {"rss"}
    assert to_uninstall == {"old"}


def test_compute_diff_noop_when_matched():
    assert compute_diff(declared={"pool"}, installed={"pool"}) == (set(), set())


def test_plugin_action_is_frozen():
    a = PluginAction(namespace="pool", action="installed", detail="0.1.0")
    assert a.namespace == "pool" and a.action == "installed"
```

- [ ] **Step 2: run, expect fail** — `PYTHONPATH=tests/stubs uv run --extra dev pytest tests/test_plugin_reconcile.py -v` → FAIL (module/symbol missing).

- [ ] **Step 3: implement** (top of `plugin_reconcile.py`):
```python
"""Startup reconcile: make the installed plugins match the manifest (SoT).

Runs at the top of app/run.py:run() — before plugins load and before the frame
build drops root. NEVER raises: a failure is recorded + logged, the panel boots.
"""

import attrs


@attrs.frozen
class PluginAction:
    namespace: str
    action: str  # "installed" | "uninstalled" | "unchanged" | "failed" | "blocked"
    detail: str = ""


def compute_diff(declared: set[str], installed: set[str]) -> tuple[set[str], set[str]]:
    """Returns (to_install, to_uninstall) = (declared - installed, installed - declared)."""
    return (declared - installed, installed - declared)
```

- [ ] **Step 4: run, expect pass.** **Step 5: commit** (`build: reconcile result types + diff`).

---

## Task 2: Mode / target resolution

**Files:** Modify `src/led_ticker/plugin_reconcile.py`; Test `tests/test_plugin_reconcile.py`

**Interfaces — Produces:** `@attrs.frozen class Target: kind: str  # "volume"|"venv"; python_exe: str; site_packages: str | None` and `def resolve_target(volume_root: Path = Path("/data/plugins")) -> Target`. Docker iff `volume_root` exists and is writable → `kind="volume"`, `python_exe=str(volume_root/"venv/bin/python")`, `site_packages` = that venv's site-packages; else local → `kind="venv"`, `python_exe=sys.executable`, `site_packages=None`.

- [ ] **Step 1: failing test:**
```python
from pathlib import Path
import sys
from led_ticker.plugin_reconcile import resolve_target, Target


def test_resolve_target_local_when_no_volume(tmp_path):
    t = resolve_target(volume_root=tmp_path / "absent")
    assert t.kind == "venv" and t.python_exe == sys.executable and t.site_packages is None


def test_resolve_target_volume_when_present(tmp_path):
    (tmp_path).mkdir(exist_ok=True)
    t = resolve_target(volume_root=tmp_path)
    assert t.kind == "volume"
    assert t.python_exe == str(tmp_path / "venv" / "bin" / "python")
    assert t.site_packages and t.site_packages.endswith("site-packages")
```

- [ ] **Step 2: run, expect fail.**
- [ ] **Step 3: implement** (add imports `import os, sys`, `from pathlib import Path`):
```python
import os
import sys
from pathlib import Path


@attrs.frozen
class Target:
    kind: str  # "volume" | "venv"
    python_exe: str
    site_packages: str | None


def resolve_target(volume_root: Path = Path("/data/plugins")) -> Target:
    if volume_root.is_dir() and os.access(volume_root, os.W_OK):
        venv = volume_root / "venv"
        sp = venv / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "site-packages"
        return Target(kind="volume", python_exe=str(venv / "bin" / "python"), site_packages=str(sp))
    return Target(kind="venv", python_exe=sys.executable, site_packages=None)
```

- [ ] **Step 4: run, expect pass.** **Step 5: commit** (`build: reconcile target/mode detection`).

---

## Task 3: Volume venv management (create / version-stamp / recreate)

**Files:** Modify `plugin_reconcile.py`; Test `tests/test_plugin_reconcile.py`

**Interfaces — Produces:** `def ensure_volume_venv(venv_dir: Path, *, runner=subprocess.run) -> None` — if `venv_dir` missing OR its `.python-version` stamp != current `X.Y` → recreate via `python -m venv --system-site-packages <venv_dir>` and rewrite the stamp. Idempotent when the stamp matches. `runner` is injectable for tests.

- [ ] **Step 1: failing test:**
```python
import subprocess
from led_ticker.plugin_reconcile import ensure_volume_venv


def test_ensure_creates_venv_when_missing(tmp_path):
    calls = []
    def fake_run(cmd, **kw):
        calls.append(cmd)
        (tmp_path / "venv").mkdir(exist_ok=True)
        return subprocess.CompletedProcess(cmd, 0)
    ensure_volume_venv(tmp_path / "venv", runner=fake_run)
    assert any("--system-site-packages" in c for c in calls)
    assert (tmp_path / "venv" / ".python-version").exists()


def test_ensure_noop_when_stamp_matches(tmp_path):
    import sys
    venv = tmp_path / "venv"; venv.mkdir()
    (venv / ".python-version").write_text(f"{sys.version_info.major}.{sys.version_info.minor}")
    calls = []
    ensure_volume_venv(venv, runner=lambda c, **k: calls.append(c) or subprocess.CompletedProcess(c, 0))
    assert calls == []  # no recreate
```

- [ ] **Step 2: run, expect fail.**
- [ ] **Step 3: implement:**
```python
import shutil
import subprocess


def _py_tag() -> str:
    return f"{sys.version_info.major}.{sys.version_info.minor}"


def ensure_volume_venv(venv_dir: Path, *, runner=subprocess.run) -> None:
    stamp = venv_dir / ".python-version"
    if venv_dir.exists() and stamp.exists() and stamp.read_text().strip() == _py_tag():
        return
    if venv_dir.exists():
        shutil.rmtree(venv_dir, ignore_errors=True)
    runner([sys.executable, "-m", "venv", "--system-site-packages", str(venv_dir)], check=True)
    venv_dir.mkdir(exist_ok=True)
    stamp.write_text(_py_tag())
```

- [ ] **Step 4: run, expect pass.** **Step 5: commit** (`build: volume venv create + version-stamp recreate`).

---

## Task 4: Parameterize pip install/uninstall by target python

**Files:** Modify `src/led_ticker/app/plugin_cmd.py`; Test `tests/test_plugins/test_plugin_cli.py` (or the existing pip-primitive test)

**Interfaces — Produces:** `_pip_install(requirement, *, python_exe: str = sys.executable) -> int` and `_pip_uninstall(dist, *, python_exe: str = sys.executable) -> int` — same behavior, but the subprocess uses `[python_exe, "-m", "pip", ...]` (the freeze step in `_pip_install` also uses `python_exe`).

- [ ] **Step 1: failing test** (assert the python_exe is threaded into the subprocess argv):
```python
def test_pip_install_uses_given_python(monkeypatch):
    seen = []
    import subprocess as sp
    from led_ticker.app import plugin_cmd
    def fake_run(cmd, **kw):
        seen.append(cmd)
        return sp.CompletedProcess(cmd, 0, stdout="", stderr="")
    monkeypatch.setattr(plugin_cmd.subprocess, "run", fake_run)
    plugin_cmd._pip_install("led-ticker-pool", python_exe="/venv/bin/python")
    assert all(c[0] == "/venv/bin/python" for c in seen)
```

- [ ] **Step 2: run, expect fail.**
- [ ] **Step 3: implement** — add `python_exe: str = sys.executable` to both signatures and replace the two `sys.executable` literals in `_pip_install` (freeze + install) and the one in `_pip_uninstall` with `python_exe`. (No other behavior change; existing call sites keep the default.)
- [ ] **Step 4: run** the new test + the existing plugin tests (`PYTHONPATH=tests/stubs uv run --extra dev pytest tests/test_plugins/ tests/test_plugin_reconcile.py -q`) → all pass. **Step 5: commit** (`build: parameterize pip primitives by target python`).

---

## Task 5: Uninstall guards

**Files:** Modify `plugin_reconcile.py`; Test `tests/test_plugin_reconcile.py`

**Interfaces — Produces:**
- `def installed_plugin_dists() -> dict[str, str]` → `{namespace: dist_name}` from `importlib.metadata.entry_points(group="led_ticker.plugins")` via `ep.dist.name` (NOT the catalog guess).
- `def is_depended_on(dist: str) -> bool` → True if any OTHER installed dist `requires` `dist`.
- `def referenced_namespaces(config_path: Path) -> set[str]` → raw `tomllib` parse of `config.toml`; collect every `widget["type"]`; return the set of namespace prefixes (`type.split(".")[0]`). NEVER raises (bad/missing config → empty set).
- `def uninstall_blocked_reason(namespace: str, dist: str, referenced: set[str]) -> str | None` → returns a reason string if the uninstall must be SKIPPED (`"config still references '<ns>' widgets"` when `namespace in referenced`; `"depended on by another plugin"` when `is_depended_on(dist)`), else `None`.

- [ ] **Step 1: failing tests** (each guard):
```python
from pathlib import Path
from led_ticker.plugin_reconcile import referenced_namespaces, uninstall_blocked_reason


def test_referenced_namespaces_reads_widget_types(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        '[[playlist.section]]\nmode="swap"\n'
        '[[playlist.section.widget]]\ntype="rss.feed"\n'
    )
    assert "rss" in referenced_namespaces(cfg)


def test_referenced_namespaces_missing_file_is_empty(tmp_path):
    assert referenced_namespaces(tmp_path / "absent.toml") == set()


def test_blocked_when_config_references(monkeypatch):
    import led_ticker.plugin_reconcile as r
    monkeypatch.setattr(r, "is_depended_on", lambda d: False)
    assert uninstall_blocked_reason("rss", "led-ticker-rss", {"rss"}) is not None


def test_blocked_when_depended_on(monkeypatch):
    import led_ticker.plugin_reconcile as r
    monkeypatch.setattr(r, "is_depended_on", lambda d: True)
    reason = uninstall_blocked_reason("rss", "led-ticker-rss", set())
    assert reason and "depended" in reason


def test_not_blocked_when_safe(monkeypatch):
    import led_ticker.plugin_reconcile as r
    monkeypatch.setattr(r, "is_depended_on", lambda d: False)
    assert uninstall_blocked_reason("rss", "led-ticker-rss", set()) is None
```

- [ ] **Step 2: run, expect fail.**
- [ ] **Step 3: implement:**
```python
import importlib.metadata
import tomllib

_PLUGINS_ENTRY_GROUP = "led_ticker.plugins"


def installed_plugin_dists() -> dict[str, str]:
    out: dict[str, str] = {}
    for ep in importlib.metadata.entry_points(group=_PLUGINS_ENTRY_GROUP):
        dist = getattr(ep, "dist", None)
        if dist is not None and getattr(dist, "name", None):
            out[ep.name] = dist.name
    return out


def is_depended_on(dist: str) -> bool:
    target = dist.lower().replace("_", "-")
    for d in importlib.metadata.distributions():
        if (d.metadata["Name"] or "").lower().replace("_", "-") == target:
            continue
        for req in d.requires or []:
            name = req.split(";")[0].split("[")[0].split("(")[0]
            for op in ("==", ">=", "<=", "~=", ">", "<", "!="):
                name = name.split(op)[0]
            if name.strip().lower().replace("_", "-") == target:
                return True
    return False


def referenced_namespaces(config_path: Path) -> set[str]:
    try:
        data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return set()
    out: set[str] = set()
    def walk(o):
        if isinstance(o, dict):
            t = o.get("type")
            if isinstance(t, str) and "." in t:
                out.add(t.split(".")[0])
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(data)
    return out


def uninstall_blocked_reason(namespace: str, dist: str, referenced: set[str]) -> str | None:
    if namespace in referenced:
        return f"config still references '{namespace}' widgets — remove them first"
    if is_depended_on(dist):
        return "depended on by another installed plugin"
    return None
```

- [ ] **Step 4: run, expect pass.** **Step 5: commit** (`build: uninstall guards (dist-via-entrypoint, depended-on, config-ref)`).

---

## Task 6: The reconcile orchestrator + sys.path apply

**Files:** Modify `plugin_reconcile.py`; Test `tests/test_plugin_reconcile.py`

**Interfaces — Produces:**
- `def reconcile(config_path: Path, *, volume_root: Path = Path("/data/plugins")) -> list[PluginAction]` — orchestrates: resolve target; if volume, `ensure_volume_venv`; read declared (`_declared_keys` → namespaces) + installed (`installed_plugin_dists`); compute diff; install missing via `_pip_install(req, python_exe=target.python_exe)`; uninstall undeclared via the guards + `_pip_uninstall(dist, python_exe=...)`; per-item try/except → `PluginAction(...action="failed", detail=str(e))`; LOG the chosen target + each action + a no-manifest hint; NEVER raise. Returns the action list.
- `def apply_to_syspath(target: Target) -> None` — if `target.site_packages` and it exists, `sys.path.insert(0, target.site_packages)` (idempotent).

> **Implementer notes:** the declared set is the manifest's plugin **namespaces**. The manifest stores pip requirement lines; reuse `_declared_keys` for dedup keys, and map a declared line → namespace via the catalog (`load_catalog`) when possible, else the dedup key. For install, pass the raw manifest line as the requirement. For uninstall, use `installed_plugin_dists()[namespace]` as the dist (the EntryPoint.dist.name). Mirror `app/plugin_cmd.py` import-purity (no heavy imports at module top if avoidable). Use the module `logging`.

- [ ] **Step 1: failing test** (drive the 3 outcomes with monkeypatched pip + installed/declared):
```python
import led_ticker.plugin_reconcile as r
from pathlib import Path


def test_reconcile_installs_missing_uninstalls_undeclared(tmp_path, monkeypatch):
    # declared: rss ; installed: old
    manifest = tmp_path / "config" / "requirements-plugins.txt"
    manifest.parent.mkdir(parents=True)
    manifest.write_text("led-ticker-rss\n")
    (tmp_path / "config" / "config.toml").write_text("")  # no widget refs
    monkeypatch.setattr(r, "resolve_target", lambda **k: r.Target("venv", "py", None))
    monkeypatch.setattr(r, "_declared_namespaces", lambda p: {"rss"})
    monkeypatch.setattr(r, "installed_plugin_dists", lambda: {"old": "led-ticker-old"})
    monkeypatch.setattr(r, "is_depended_on", lambda d: False)
    installed, uninstalled = [], []
    monkeypatch.setattr(r, "_install_namespace", lambda ns, py: installed.append(ns) or 0)
    monkeypatch.setattr(r, "_uninstall_dist", lambda dist, py: uninstalled.append(dist) or 0)
    actions = r.reconcile(tmp_path / "config" / "config.toml")
    assert "rss" in installed and "led-ticker-old" in uninstalled
    assert any(a.action == "installed" and a.namespace == "rss" for a in actions)


def test_reconcile_blocks_uninstall_when_config_references(tmp_path, monkeypatch):
    (tmp_path / "config.toml").write_text(
        '[[playlist.section]]\nmode="swap"\n[[playlist.section.widget]]\ntype="old.thing"\n'
    )
    monkeypatch.setattr(r, "resolve_target", lambda **k: r.Target("venv", "py", None))
    monkeypatch.setattr(r, "_declared_namespaces", lambda p: set())
    monkeypatch.setattr(r, "installed_plugin_dists", lambda: {"old": "led-ticker-old"})
    monkeypatch.setattr(r, "is_depended_on", lambda d: False)
    monkeypatch.setattr(r, "_uninstall_dist", lambda *a: (_ for _ in ()).throw(AssertionError("should not uninstall")))
    actions = r.reconcile(tmp_path / "config.toml")
    assert any(a.action == "blocked" and a.namespace == "old" for a in actions)


def test_reconcile_never_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(r, "resolve_target", lambda **k: (_ for _ in ()).throw(RuntimeError("boom")))
    assert r.reconcile(tmp_path / "config.toml") == []  # swallowed
```

- [ ] **Step 2: run, expect fail.**
- [ ] **Step 3: implement** `reconcile`, the small helpers `_declared_namespaces(config_path)` (manifest beside config; map lines→namespaces via catalog/dedup key), `_install_namespace(ns, python_exe)` (resolve the manifest line for ns, call `_pip_install`), `_uninstall_dist(dist, python_exe)` (call `_pip_uninstall`), and `apply_to_syspath`. Wrap the WHOLE body in `try/except Exception: log + return []`; wrap EACH install/uninstall in its own try/except → `PluginAction(action="failed")`. Emit the chosen-target + no-manifest-hint logs.
- [ ] **Step 4: run, expect pass** (+ full `tests/test_plugin_reconcile.py`). **Step 5: commit** (`build: reconcile orchestrator + sys.path apply`).

---

## Task 7: Status-board surfacing (schema 6→7)

**Files:** Modify `src/led_ticker/status_board.py`; Test `tests/test_status_board.py` (+ the schema-drift tripwire)

**Interfaces — Produces:** `StatusBoard.plugin_reconcile: list[dict[str,str]]` (each `{namespace, action, detail}`); `record_plugin_reconcile(actions: list[PluginAction]) -> None` (module fn, mirrors `record_disabled_widget`); included in `snapshot()`; `SCHEMA_VERSION = 7`.

- [ ] **Step 1: failing test:**
```python
from led_ticker import status_board
from led_ticker.plugin_reconcile import PluginAction


def test_reconcile_recorded_in_snapshot():
    board = status_board.StatusBoard(...)  # match existing test construction
    status_board._ACTIVE = board
    status_board.record_plugin_reconcile([PluginAction("rss", "installed", "0.2.0")])
    snap = board.snapshot()
    assert snap["schema"] == 7
    assert snap["plugin_reconcile"][0]["namespace"] == "rss"
```
(Use the same `StatusBoard(...)` construction the existing tests use.)

- [ ] **Step 2: run, expect fail.**
- [ ] **Step 3: implement** — add the `plugin_reconcile` attrs field (factory=list), serialize it in `snapshot()` under `"plugin_reconcile"`, add `record_plugin_reconcile` (mirror `record_disabled_widget` at status_board.py:200-208), bump `SCHEMA_VERSION` to 7. Update the schema-drift tripwire's expected top-level key set to include `plugin_reconcile`.
- [ ] **Step 4: run** `tests/test_status_board.py` + the schema-drift test → pass. **Step 5: commit** (`feat: surface plugin reconcile on the status board (schema 7)`).

---

## Task 8: webui renders the reconcile block

**Files:** Modify `src/led_ticker/webui/static/index.html` (+ the JS that renders status); Test: extend `tests/test_status_*`/webui test if one asserts rendered sections

- [ ] **Step 1:** Read how `disabled_widgets` is rendered in the webui static (find the section). 
- [ ] **Step 2:** Add a "Plugins" panel that lists `plugin_reconcile` entries — `installed`/`uninstalled`/`unchanged` neutral, `failed`/`blocked` highlighted with the `detail` (so a hobbyist sees "blocked: config still references 'rss' widgets" without `docker logs`). Mirror the disabled-widgets markup.
- [ ] **Step 3:** If a webui test asserts on rendered sections, extend it; else add a minimal assertion that the endpoint payload carries `plugin_reconcile`.
- [ ] **Step 4: commit** (`feat(webui): show plugin reconcile results (installed/failed/blocked)`).

---

## Task 9: Wire reconcile into run() + tripwire

**Files:** Modify `src/led_ticker/app/run.py`; Test `tests/test_status_instrumentation.py` (the `test_setup_runs_before_frame_build` family)

- [ ] **Step 1: failing tripwire** — assert (AST or call-order) that in `run()`, `plugin_reconcile.reconcile(...)` + `apply_to_syspath(...)` are called BEFORE `_load_plugins_for_config(...)`, which is before `build_frame_from_config(...)`. Mirror the existing `test_setup_runs_before_frame_build` AST style.
- [ ] **Step 2: run, expect fail.**
- [ ] **Step 3: implement** — at the TOP of `run()` (before `_load_plugins_for_config`):
```python
from led_ticker import plugin_reconcile  # noqa: PLC0415
_recon_target = plugin_reconcile.resolve_target()
_recon_actions = plugin_reconcile.reconcile(config_path)
plugin_reconcile.apply_to_syspath(_recon_target)
```
Then after `_setup_status_board(...)` (status board is active), `status_board.record_plugin_reconcile(_recon_actions)`. (Reconcile result is captured before the board exists; record it once the board is set up — both are pre-drop.)
- [ ] **Step 4: run** the tripwire + full suite (`PYTHONPATH=tests/stubs uv run --extra dev pytest -q`) → pass. **Step 5: commit** (`feat: run plugin reconcile at startup before plugins load`).

---

## Task 10: Drop Dockerfile Layer-2b + add the plugins volume

**Files:** Modify `Dockerfile`, `compose.yaml`

- [ ] **Step 1:** Remove the Layer-2b block in `Dockerfile` (the `COPY config/requirements-plugins.example.txt config/requirements-plugins.tx[t] ...` + the `RUN if [ -f ... ] pip install -r requirements-plugins.txt ...` stanza). Leave Layer 2 (core) + Layer 3 (source) intact. Add a one-line comment where it was: `# Plugins are NOT baked — they install at runtime onto the ticker-plugins volume (see plugin_reconcile.py).`
- [ ] **Step 2:** In `compose.yaml`, under the **display** service `volumes:`, add `- ticker-plugins:/data/plugins   # installed plugins (runtime reconcile); reset = docker volume rm ticker-plugins`; and declare `ticker-plugins:` under the top-level `volumes:`.
- [ ] **Step 3: verify** YAML parses (`uv run --with pyyaml python -c "import yaml; yaml.safe_load(open('compose.yaml'))"`) and `docker build .` still succeeds locally if Docker is available (else note it as a deploy smoke).
- [ ] **Step 4: commit** (`build(docker): drop baked plugin layer; add ticker-plugins volume`).

---

## Task 11: Docs

**Files:** Modify the Plugins docs page (`docs/site/src/content/docs/plugins/index.mdx` or `available.mdx` + `docs/content-source/plugins/*`)

- [ ] **Step 1:** Add a prominent callout: **"Adding/removing a plugin no longer needs a rebuild — edit `config/requirements-plugins.txt`, then `docker compose restart` (NOT `up --build`). The change applies on the next start (seconds)."**
- [ ] **Step 2:** Document removal (delete the line → restart → uninstalled), the volume reset (`docker volume rm ticker-plugins && docker compose restart`), and the offline/air-gapped note (first restart needs network to install; pre-seed the volume or build a custom image if air-gapped). Note local/bare-metal installs into the active venv.
- [ ] **Step 3:** `make docs-build` + `make docs-lint` clean. **Step 4: commit** (`docs: no-rebuild plugin install (edit + restart) + removal/reset/offline`).

---

## Self-Review

**Spec coverage:** §1 reconcile→Tasks 1,5,6; §2 volume venv→Tasks 2,3,9 (sys.path); §"Uninstall guards"→Task 5 (each guard tested) + Task 6 (wired); §4 mode→Task 2; §5 status→Tasks 7,8; §6 logging→Task 6; §7 compose/docs→Tasks 10,11; drop Layer-2b→Task 10; pre-drop placement + tripwire→Task 9; never-raise→Task 6 (`test_reconcile_never_raises`). ✅

**Placeholder scan:** code blocks are concrete; Task 8 (webui) + Task 7 test construction reference "match existing markup/construction" because they must mirror existing code the implementer reads — these are directed reads, not vague TODOs. No "implement later".

**Type consistency:** `PluginAction(namespace, action, detail)`, `Target(kind, python_exe, site_packages)`, `compute_diff -> (set,set)`, `reconcile -> list[PluginAction]`, `_pip_install(..., python_exe=)` are used consistently across tasks. `installed_plugin_dists() -> {namespace: dist}` consumed by Task 6's uninstall path.

**Note for executor:** the Docker `docker build` (Task 10) + the full volume round-trip (edit→restart→present; remove→restart→gone; volume-rm→restart→reinstall) are a **maintainer deploy-smoke** — unit tests can't exercise the Pi/Docker bind-mount + setuid. Flag it; do not fake it.
