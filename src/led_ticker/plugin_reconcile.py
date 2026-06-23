"""Startup reconcile: make the installed plugins match the manifest (SoT).

Runs at the top of app/run.py:run() — before plugins load and before the frame
build drops root. NEVER raises: a failure is recorded + logged, the panel boots.
"""

import importlib.metadata
import logging
import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import attrs

_log = logging.getLogger(__name__)


@attrs.frozen
class PluginAction:
    namespace: str
    action: str  # "installed" | "uninstalled" | "unchanged" | "failed" | "blocked"
    detail: str = ""


@attrs.frozen
class Target:
    kind: str  # "volume" | "venv"
    python_exe: str
    site_packages: str | None


def compute_diff(declared: set[str], installed: set[str]) -> tuple[set[str], set[str]]:
    """Return (to_install, to_uninstall)."""
    return (declared - installed, installed - declared)


def resolve_target(volume_root: Path = Path("/data/plugins")) -> Target:
    if volume_root.is_dir() and os.access(volume_root, os.W_OK):
        venv = volume_root / "venv"
        py_version = f"{sys.version_info.major}.{sys.version_info.minor}"
        sp = venv / "lib" / f"python{py_version}" / "site-packages"
        return Target(
            kind="volume",
            python_exe=str(venv / "bin" / "python"),
            site_packages=str(sp),
        )
    return Target(kind="venv", python_exe=sys.executable, site_packages=None)


def _py_tag() -> str:
    """Return current Python version as X.Y string."""
    return f"{sys.version_info.major}.{sys.version_info.minor}"


def ensure_volume_venv(venv_dir: Path, *, runner=subprocess.run) -> None:
    """Create or recreate volume venv if missing or Python version mismatch.

    If venv_dir exists and has a matching .python-version stamp, do nothing.
    Otherwise, delete the old venv (if any) and create a fresh one with
    --system-site-packages, then write the .python-version stamp.

    Args:
        venv_dir: Path to the venv directory.
        runner: Callable for subprocess.run (injectable for tests).
    """
    stamp = venv_dir / ".python-version"
    if venv_dir.exists() and stamp.exists() and stamp.read_text().strip() == _py_tag():
        return
    if venv_dir.exists():
        shutil.rmtree(venv_dir, ignore_errors=True)
    runner(
        [sys.executable, "-m", "venv", "--system-site-packages", str(venv_dir)],
        check=True,
    )
    stamp.write_text(_py_tag())


# ── Uninstall guards ──────────────────────────────────────────────────────────

_PLUGINS_ENTRY_GROUP = "led_ticker.plugins"


def installed_plugin_dists() -> dict[str, str]:
    """Return {namespace: dist_name} from installed entry points.

    Uses ep.dist.name (the real distribution name), NOT a catalog guess.
    """
    out: dict[str, str] = {}
    for ep in importlib.metadata.entry_points(group=_PLUGINS_ENTRY_GROUP):
        dist = getattr(ep, "dist", None)
        if dist is not None and getattr(dist, "name", None):
            out[ep.name] = dist.name
    return out


def is_depended_on(dist: str) -> bool:
    """Return True if any OTHER installed distribution requires ``dist``."""
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
    """Return the set of plugin namespace prefixes referenced in config_path.

    Parses widget ``type`` fields and returns the part before the first dot
    for any type that contains a dot.  Never raises — a bad or missing config
    returns an empty set.
    """
    try:
        data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except OSError, tomllib.TOMLDecodeError:
        return set()
    out: set[str] = set()

    def walk(o: object) -> None:
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


def uninstall_blocked_reason(
    namespace: str, dist: str, referenced: set[str]
) -> str | None:
    """Return a human-readable reason string if the uninstall must be skipped.

    Blocks when:
    - the config still references widgets in ``namespace``, OR
    - another installed dist depends on ``dist``.

    Returns ``None`` when the uninstall is safe to proceed.
    """
    if namespace in referenced:
        return f"config still references '{namespace}' widgets — remove them first"
    if is_depended_on(dist):
        return "depended on by another installed plugin"
    return None


# ── reconcile orchestrator ────────────────────────────────────────────────────

_MANIFEST_NAME = "requirements-plugins.txt"


def _declared_namespaces(config_path: Path) -> set[str]:
    """Return the set of plugin namespaces declared in the manifest beside config.

    The manifest is ``requirements-plugins.txt`` in the same directory as
    ``config_path``. Each non-comment line is a pip requirement string; we map
    it to a namespace via the bundled catalog (namespace == catalog entry's
    ``namespace`` field), falling back to the ``_requirement_key`` dedup key
    when no catalog match exists.  Never raises — a missing/unreadable manifest
    returns an empty set.
    """
    manifest = config_path.parent / _MANIFEST_NAME
    if not manifest.exists():
        return set()
    # Lazy import to mirror app/plugin_cmd.py import-purity convention.
    from led_ticker.app.plugin_cmd import _requirement_key  # noqa: PLC0415
    from led_ticker.plugins_catalog import load_catalog  # noqa: PLC0415

    try:
        catalog = load_catalog()
    except Exception:  # noqa: BLE001
        catalog = None

    # Build a lookup: dedup_key -> namespace from the catalog. Register a key for
    # EVERY source of each entry (pypi AND git) and for both the pinned and
    # unpinned requirement forms, because `plugin add --source git` (and the
    # git+subdirectory deploy story) writes a manifest line whose dedup key is the
    # repo#subdir, not the pypi package name. Keying only the default (first)
    # source would leave a git-source line for a pypi-default catalog plugin
    # unresolved → churn (failed reinstall every boot) and a wrong uninstall of
    # the real namespace. Tripwire: test_declared_namespaces_git_source_resolves.
    key_to_ns: dict[str, str] = {}
    if catalog is not None:
        for entry in catalog.entries:
            for src in entry.sources:
                for pinned in (True, False):
                    try:
                        k = _requirement_key(
                            entry.requirement(source=src.type, pinned=pinned)
                        )
                        key_to_ns[k] = entry.namespace
                    except Exception:  # noqa: BLE001
                        pass

    namespaces: set[str] = set()
    for line in manifest.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key = _requirement_key(stripped)
        ns = key_to_ns.get(key, key)
        namespaces.add(ns)
    return namespaces


def _install_namespace(
    ns: str, python_exe: str, *, constraints: str | None = None
) -> int:
    """Pip-install the requirement for namespace ``ns``.

    Resolves the manifest line for this namespace via the catalog, then
    delegates to ``_pip_install`` in ``app/plugin_cmd``. Returns the pip exit
    code (0 = success).

    ``constraints`` (a path produced once per reconcile pass by
    ``_freeze_to_constraints``) is forwarded so the per-install env freeze is
    skipped — one freeze per pass instead of one per plugin.
    """
    from led_ticker.app.plugin_cmd import _pip_install  # noqa: PLC0415
    from led_ticker.plugins_catalog import load_catalog  # noqa: PLC0415

    try:
        catalog = load_catalog()
        entry = catalog.get(ns)
        requirement = entry.requirement() if entry is not None else ns
    except Exception:  # noqa: BLE001
        requirement = ns

    return _pip_install(requirement, python_exe=python_exe, constraints=constraints)


def _uninstall_dist(dist: str, python_exe: str) -> int:
    """Pip-uninstall distribution ``dist``. Returns the pip exit code."""
    from led_ticker.app.plugin_cmd import _pip_uninstall  # noqa: PLC0415

    return _pip_uninstall(dist, python_exe=python_exe)


def reconcile(
    config_path: Path,
    *,
    volume_root: Path = Path("/data/plugins"),
) -> list[PluginAction]:
    """Make the installed plugins match the manifest beside ``config_path``.

    Steps:
    1. Resolve install target (volume venv or the active venv).
    2. If volume target, ensure the volume venv exists/is current.
    3. Read declared namespaces from the manifest next to ``config_path``.
    4. Read installed namespaces from live entry points.
    5. Compute diff (to_install, to_uninstall).
    6. Install missing plugins; uninstall undeclared (with guards).
    7. Each action is wrapped in try/except → ``PluginAction(action="failed")``.
    8. The WHOLE body is wrapped in try/except — NEVER raises; returns ``[]``.

    Returns a list of ``PluginAction`` describing what was done.
    """
    try:
        target = resolve_target(volume_root=volume_root)
        _log.info(
            "plugin reconcile: target=%s python=%s", target.kind, target.python_exe
        )

        if target.kind == "volume":
            venv_dir = volume_root / "venv"
            ensure_volume_venv(venv_dir)
            # Put the volume venv's site-packages on sys.path BEFORE scanning the
            # installed set. The display process is the BASE interpreter; plugins
            # live in the volume venv's site-packages, which is invisible to
            # importlib.metadata until inserted here. Without this the installed
            # scan reads the base env (effectively empty), so true-sync uninstall
            # never fires and every plugin reinstalls every boot.
            # Tripwire: test_reconcile_observes_target_env_installed.
            apply_to_syspath(target)
            importlib.invalidate_caches()

        manifest = config_path.parent / _MANIFEST_NAME
        if not manifest.exists():
            # No manifest = "I have not opted into declarative plugins". Skip the
            # whole reconcile — crucially BEFORE computing the diff. Without this
            # return, `declared` would be the empty set and the true-sync uninstall
            # path would treat EVERY installed plugin as undeclared and pip-uninstall
            # it (only spared by the config-reference / depended-on guards). On the
            # local-venv path that silently rips catalog plugins out of a dev's
            # active venv. Tripwire: test_reconcile_missing_manifest_uninstalls_nothing.
            _log.info(
                "plugin reconcile: no manifest found at %s — skipping reconcile",
                manifest,
            )
            return []

        declared = _declared_namespaces(config_path)

        installed_map = installed_plugin_dists()  # {namespace: dist_name}
        installed = set(installed_map.keys())

        to_install, to_uninstall = compute_diff(declared, installed)
        _log.info(
            "plugin reconcile: declared=%s installed=%s to_install=%s to_uninstall=%s",
            sorted(declared),
            sorted(installed),
            sorted(to_install),
            sorted(to_uninstall),
        )

        referenced = referenced_namespaces(config_path)
        actions: list[PluginAction] = []

        # Freeze the target env's deps ONCE for the whole install pass: the
        # constraints only pin CORE's deps so a plugin can't move them, and a
        # just-installed plugin doesn't need to appear in the constraints used for
        # the next install. Without this, every install re-ran a full
        # `pip list --format=freeze` subprocess (~1-3s on a cold Pi 4 SD card),
        # N-1 of them redundant, all on the first-boot dark-panel path.
        # Tripwire: test_reconcile_freezes_env_once_per_pass.
        shared_constraints: str | None = None
        if to_install:
            try:
                from led_ticker.app.plugin_cmd import (  # noqa: PLC0415
                    _freeze_to_constraints,
                )

                shared_constraints, _rc = _freeze_to_constraints(target.python_exe)
            except Exception as e:  # noqa: BLE001
                # A failed pass-level freeze is non-fatal: each _install_namespace
                # falls back to its own per-install freeze (constraints=None).
                _log.warning("plugin reconcile: env freeze failed (%s); per-install", e)
                shared_constraints = None

        try:
            for ns in sorted(to_install):
                try:
                    _log.info("plugin reconcile: installing %s", ns)
                    code = _install_namespace(
                        ns, target.python_exe, constraints=shared_constraints
                    )
                    if code != 0:
                        detail = f"pip exited {code} installing {ns}"
                        _log.warning(
                            "plugin reconcile: failed to install %s: %s", ns, detail
                        )
                        actions.append(
                            PluginAction(namespace=ns, action="failed", detail=detail)
                        )
                    else:
                        actions.append(PluginAction(namespace=ns, action="installed"))
                        _log.info("plugin reconcile: installed %s", ns)
                except Exception as e:  # noqa: BLE001
                    _log.warning("plugin reconcile: failed to install %s: %s", ns, e)
                    actions.append(
                        PluginAction(namespace=ns, action="failed", detail=str(e))
                    )
        finally:
            # The pass-level constraints file is ours to clean up (passing it into
            # _pip_install with constraints!=None means that fn does NOT delete it).
            if shared_constraints is not None:
                Path(shared_constraints).unlink(missing_ok=True)

        for ns in sorted(to_uninstall):
            dist = installed_map.get(ns, ns)
            reason = uninstall_blocked_reason(ns, dist, referenced)
            if reason is not None:
                _log.info(
                    "plugin reconcile: blocked uninstall of %s (%s): %s",
                    ns,
                    dist,
                    reason,
                )
                actions.append(
                    PluginAction(namespace=ns, action="blocked", detail=reason)
                )
                continue
            try:
                _log.info("plugin reconcile: uninstalling %s (%s)", ns, dist)
                code = _uninstall_dist(dist, target.python_exe)
                if code != 0:
                    detail = f"pip exited {code} uninstalling {dist}"
                    _log.warning(
                        "plugin reconcile: failed to uninstall %s: %s", ns, detail
                    )
                    actions.append(
                        PluginAction(namespace=ns, action="failed", detail=detail)
                    )
                else:
                    actions.append(PluginAction(namespace=ns, action="uninstalled"))
                    _log.info("plugin reconcile: uninstalled %s", ns)
            except Exception as e:  # noqa: BLE001
                _log.warning("plugin reconcile: failed to uninstall %s: %s", ns, e)
                actions.append(
                    PluginAction(namespace=ns, action="failed", detail=str(e))
                )

        # If anything changed on disk this pass, drop the import-system caches so
        # the immediately-following entry-point discovery in run() sees freshly
        # installed plugins (and stops seeing uninstalled ones) without a second
        # restart. Covers the local-venv path too (apply_to_syspath is a no-op
        # there). Tripwire: test_reconcile_invalidates_caches_after_install.
        if any(a.action in ("installed", "uninstalled") for a in actions):
            importlib.invalidate_caches()

        return actions

    except Exception as e:  # noqa: BLE001
        _log.error("plugin reconcile: unexpected error — %s", e, exc_info=True)
        return []


def apply_to_syspath(target: Target) -> None:
    """Insert the volume venv's site-packages at ``sys.path[0]`` (idempotent).

    Only acts when ``target.site_packages`` is set and the directory exists.
    Inserting at position 0 ensures volume-installed plugins shadow any same-named
    packages in the base environment — safe because the volume venv was built with
    ``--system-site-packages``, so core's deps are still available.
    """
    sp = target.site_packages
    if not sp:
        return
    if not Path(sp).exists():
        return
    if sp not in sys.path:
        sys.path.insert(0, sp)
    # Drop any stale FileFinder/path-importer caches so packages just installed
    # into this directory (this boot) are discoverable by the import system and
    # importlib.metadata's entry-point scan. Cheap; required by the importlib
    # docs after creating modules / mutating sys.path at runtime.
    importlib.invalidate_caches()
