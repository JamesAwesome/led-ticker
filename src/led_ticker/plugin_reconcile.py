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

from led_ticker.reload import _CORE_OWNED_TOP_LEVEL_KEYS

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


def _exact_pin(requirement_line: str) -> str | None:
    """Return the exact ``==X.Y.Z`` version pinned by a manifest line, else None.

    Only an EXACT ``==`` pin on a PyPI-style requirement is returned — a restart
    can reliably detect a drift between that pin and the installed version. git /
    url / unpinned / range-spec (``>=``, ``~=``) lines return None: a restart
    can't tell whether the upstream source moved, so reconcile must not churn
    them (the volume reset is the documented way to refresh a non-pinned source).
    """
    line = requirement_line.strip()
    # Reject anything that isn't a plain PyPI requirement.
    if line.startswith(("git+", "-e ", "http://", "https://")) or "://" in line:
        return None
    if "==" not in line:
        return None
    # Take the version token after the FIRST '==', trimming a trailing marker /
    # comment (`pkg==1.2.3 ; python_version>='3.10'`).
    after = line.split("==", 1)[1].strip()
    for delim in (";", " ", "#"):
        idx = after.find(delim)
        if idx != -1:
            after = after[:idx]
    after = after.strip()
    # A trailing comma-spec (`pkg==1.2.0,<2.0`) is a COMPOUND constraint, not an
    # exact pin — the `<2.0` range means a restart can't know the installed
    # version is the only valid one, so don't treat `1.2.0` as exact (it would
    # churn a reinstall every boot). Reject anything carrying a `,`.
    if "," in after:
        return None
    return after or None


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


_TRANSITION_KEYS = ("transition", "entry_transition", "widget_transition")


def referenced_namespaces(config_path: Path) -> set[str]:
    """Return the set of plugin namespace prefixes referenced in config_path.

    Parses widget ``type`` fields AND the transition-selecting string keys
    (``transition`` / ``entry_transition`` / ``widget_transition``), returning the
    part before the first dot for any value that contains a dot. A plugin used
    ONLY via ``transition = "nyancat.forward"`` (never a widget ``type``) must
    still count as referenced so the uninstall guard blocks it — otherwise the
    guard would let the plugin be uninstalled while config still uses it,
    breaking the next boot.

    ALSO treats every top-level TOML table key that isn't core-owned (the same
    ``_CORE_OWNED_TOP_LEVEL_KEYS`` frozenset ``reload.py`` uses to detect
    plugin-owned config blocks) as a referenced namespace. An overlay-only
    plugin — one that paints via a frame overlay hook rather than a widget/
    transition ``type`` string, e.g. the storefront plugin's ``[storefront]``
    block — has no dotted value anywhere in config for the walk above to find,
    so without this the uninstall guard would never see it as referenced and
    would prune it out from under the running overlay on the very next boot.

    Never raises — a bad or missing config returns an empty set.
    """
    try:
        data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except OSError, tomllib.TOMLDecodeError:
        return set()
    except UnicodeDecodeError as e:
        # A non-UTF-8 config is a ValueError, not OSError — it would escape the
        # guard above and abort the whole reconcile. Honor the "empty on bad
        # file" contract and name the offender so the operator can fix it.
        _log.warning(
            "plugin reconcile: config %s is not valid UTF-8 (%s) — "
            "treating it as referencing no plugins",
            config_path,
            e,
        )
        return set()
    out: set[str] = set()

    def walk(o: object) -> None:
        if isinstance(o, dict):
            t = o.get("type")
            if isinstance(t, str) and "." in t:
                out.add(t.split(".")[0])
            for key in _TRANSITION_KEYS:
                v = o.get(key)
                if isinstance(v, str) and "." in v:
                    out.add(v.split(".")[0])
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(data)
    if isinstance(data, dict):
        out.update(set(data) - _CORE_OWNED_TOP_LEVEL_KEYS)
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


def _declared_requirements(config_path: Path) -> dict[str, str]:
    """Return ``{namespace: requirement_line}`` declared in the manifest.

    The manifest is ``requirements-plugins.txt`` in the same directory as
    ``config_path``. Each non-comment line is a pip requirement string; we map
    it to a namespace via the bundled catalog (namespace == catalog entry's
    ``namespace`` field), falling back to the ``_requirement_key`` dedup key
    when no catalog match exists.  The VALUE is the operator's verbatim manifest
    line (stripped) — the install path threads it through to pip so an explicit
    pin/source (``led-ticker-pool==0.1.0``, a git+url line) is honored instead
    of being re-derived as the catalog default. If two lines map to the same
    namespace, the last one wins (matches set-dedup semantics).  Never raises —
    a missing/unreadable manifest returns an empty dict.
    """
    manifest = config_path.parent / _MANIFEST_NAME
    if not manifest.exists():
        return {}
    # Lazy import to mirror app/plugin_cmd.py import-purity convention.
    from led_ticker.app.plugin_cmd import _requirement_key  # noqa: PLC0415
    from led_ticker.plugins_catalog import load_catalog  # noqa: PLC0415

    try:
        catalog = load_catalog()
    except Exception:  # noqa: BLE001
        catalog = None

    # Build a lookup: dedup_key -> {namespaces} from the catalog. Register a key
    # for EVERY source of each entry (pypi AND git) and for both the pinned and
    # unpinned requirement forms, because `plugin add --source git` (and the
    # git+subdirectory deploy story) writes a manifest line whose dedup key is the
    # repo#subdir, not the pypi package name. Keying only the default (first)
    # source would leave a git-source line for a pypi-default catalog plugin
    # unresolved → churn (failed reinstall every boot) and a wrong uninstall of
    # the real namespace. Tripwire: test_declared_namespaces_git_source_resolves.
    #
    # The value is a SET, not a single namespace: a SHARED pip package maps one
    # dedup key to MANY namespaces (e.g. led-ticker-flair ships nyancat / pokeball
    # / pacman / sailor_moon, all keyed `led-ticker-flair`). A single-namespace
    # map would last-write-wins-collapse the key to whichever entry the catalog
    # loop happened to visit last, so a `led-ticker-flair` manifest line would
    # declare only that one namespace — the others never install and never load.
    # Tripwire: test_declared_requirements_shared_package_maps_all_namespaces.
    key_to_ns: dict[str, set[str]] = {}
    if catalog is not None:
        for entry in catalog.entries:
            for src in entry.sources:
                for pinned in (True, False):
                    try:
                        k = _requirement_key(
                            entry.requirement(source=src.type, pinned=pinned)
                        )
                        key_to_ns.setdefault(k, set()).add(entry.namespace)
                    except Exception:  # noqa: BLE001
                        pass

    try:
        manifest_text = manifest.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        # A missing/unreadable/non-UTF-8 manifest must honor the "empty dict on
        # bad file" contract — UnicodeDecodeError is a ValueError that would
        # otherwise escape and abort the whole reconcile. Name the offender.
        _log.warning(
            "plugin reconcile: manifest %s is unreadable (%s) — "
            "treating it as declaring no plugins",
            manifest,
            e,
        )
        return {}

    requirements: dict[str, str] = {}
    for line in manifest_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key = _requirement_key(stripped)
        # A shared package's key maps to EVERY namespace it ships; declare each
        # one against the same verbatim manifest line. Fall back to {key} (the
        # line is its own namespace) when the catalog doesn't know it. Distinct
        # keys preserve the existing per-namespace last-line-wins semantics.
        for ns in key_to_ns.get(key, {key}):
            requirements[ns] = stripped
    return requirements


def _declared_namespaces(config_path: Path) -> set[str]:
    """Return the set of plugin namespaces declared in the manifest beside config.

    Thin wrapper over ``_declared_requirements`` kept for the diff computation
    (and for tests that monkeypatch the declared set directly).  Never raises.
    """
    return set(_declared_requirements(config_path))


def _install_namespace(
    ns: str,
    python_exe: str,
    *,
    constraints: str | None = None,
    requirement_line: str | None = None,
) -> int:
    """Pip-install the requirement for namespace ``ns``.

    When ``requirement_line`` is given (the operator's verbatim manifest line) it
    is installed AS WRITTEN — so an explicit pin/source (``led-ticker-pool==0.1.0``,
    a ``git+url`` line) is honored. The manifest is the source of truth for the
    version/source dimension; re-deriving the requirement from the catalog would
    silently install the catalog default (latest, unpinned) and defeat operator
    pins on a fresh/recreated volume venv. Only when no manifest line is known
    (a namespace surfaced without an originating line) do we fall back to the
    catalog requirement, then to the bare namespace. Returns the pip exit code
    (0 = success). Tripwire: test_reconcile_honors_manifest_pin.

    ``constraints`` (a path produced once per reconcile pass by
    ``_freeze_to_constraints``) is forwarded so the per-install env freeze is
    skipped — one freeze per pass instead of one per plugin.
    """
    from led_ticker.app.plugin_cmd import _pip_install  # noqa: PLC0415

    if requirement_line:
        requirement = requirement_line
    else:
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
            # apply_to_syspath already invalidates caches when it inserts the
            # path, so no redundant invalidate is needed here.
            apply_to_syspath(target)

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
        # The verbatim manifest line per namespace, so the install path honors
        # operator pins/sources instead of re-deriving the catalog default.
        # Read separately from `declared` (which may be monkeypatched in tests):
        # a namespace with no known line falls back to the catalog requirement
        # inside `_install_namespace`.
        declared_reqs = _declared_requirements(config_path)

        installed_map = installed_plugin_dists()  # {namespace: dist_name}
        installed = set(installed_map.keys())

        to_install, to_uninstall = compute_diff(declared, installed)

        # Version-pin drift on an ALREADY-installed plugin. compute_diff is a pure
        # namespace set-difference with no version awareness, so editing a manifest
        # line `led-ticker-pool==0.1.0` -> `==0.2.0` and restarting would be a
        # silent no-op (pool is in both `declared` and `installed`). For each
        # declared+installed plugin whose manifest line carries an EXACT `==X.Y.Z`
        # pin that differs from the installed dist version, add it to the install
        # set so pip reinstalls/upgrades in place under the pinned line. For
        # UNPINNED or git/url/non-`==` lines a restart can't reliably detect a
        # source change — do NOT churn them; log one INFO so the operator knows the
        # volume reset is the way to refresh a non-pinned source.
        # Tripwires: test_reconcile_pin_change_on_installed_plugin,
        # test_reconcile_unpinned_installed_plugin_not_reinstalled.
        for ns in sorted(declared & installed):
            line = declared_reqs.get(ns)
            if not line:
                continue
            pin = _exact_pin(line)
            dist = installed_map.get(ns, ns)
            if pin is None:
                _log.info(
                    "plugin reconcile: %s is declared+installed via a non-pinned "
                    "source (%s); cannot verify the source changed on a restart — "
                    "reset the plugin volume to refresh it",
                    ns,
                    line,
                )
                continue
            try:
                current = importlib.metadata.version(dist)
            except importlib.metadata.PackageNotFoundError:
                current = None
            if current is not None and current != pin:
                _log.info(
                    "plugin reconcile: %s pin changed (installed %s -> manifest "
                    "%s); reinstalling in place",
                    ns,
                    current,
                    pin,
                )
                to_install.add(ns)

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

        # Dedup the install work by the actual pip target. A SHARED package maps
        # one requirement line to MANY namespaces (led-ticker-flair → nyancat /
        # pokeball / pacman / sailor_moon), so a naive per-namespace loop would
        # run the SAME `pip install led-ticker-flair` up to 4× — correct but
        # wasteful on a cold Pi. Group the to-install namespaces by their install
        # key (the verbatim manifest line, or the bare namespace when no line is
        # known — those can't be shared), run pip ONCE per group, and emit one
        # PluginAction per covered namespace so the per-namespace reporting (and
        # the cache-invalidation gate below) is unchanged. Mirrors build_store's
        # dedup-by-requirement-key spirit. Tripwire:
        # test_reconcile_shared_package_installs_once.
        install_groups: dict[str, list[str]] = {}
        for ns in to_install:
            line = declared_reqs.get(ns)
            install_groups.setdefault(line or ns, []).append(ns)

        try:
            for key in sorted(install_groups):
                covered = sorted(install_groups[key])
                # Every namespace in a group shares one verbatim manifest line
                # (or, for line-less namespaces, the group is a single namespace
                # == key), so any member's requirement_line drives the install.
                requirement_line = declared_reqs.get(covered[0])
                label = ", ".join(covered)
                try:
                    _log.info("plugin reconcile: installing %s", label)
                    code = _install_namespace(
                        covered[0],
                        target.python_exe,
                        constraints=shared_constraints,
                        requirement_line=requirement_line,
                    )
                    if code != 0:
                        detail = f"pip exited {code} installing {label}"
                        _log.warning(
                            "plugin reconcile: failed to install %s: %s", label, detail
                        )
                        for ns in covered:
                            actions.append(
                                PluginAction(
                                    namespace=ns, action="failed", detail=detail
                                )
                            )
                    else:
                        for ns in covered:
                            actions.append(
                                PluginAction(namespace=ns, action="installed")
                            )
                        _log.info("plugin reconcile: installed %s", label)
                except Exception as e:  # noqa: BLE001
                    _log.warning("plugin reconcile: failed to install %s: %s", label, e)
                    for ns in covered:
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
        # Drop any stale FileFinder/path-importer caches so packages just
        # installed into this directory (this boot) are discoverable by the
        # import system and importlib.metadata's entry-point scan. Required by
        # the importlib docs after mutating sys.path. Guarded to the insert
        # branch: a no-op re-call (already on sys.path) need not invalidate.
        importlib.invalidate_caches()


def apply_volume_visibility(volume_root: Path = Path("/data/plugins")) -> None:
    """Make the volume venv's plugins VISIBLE to this process (read-only).

    Used by the webui sidecar, which mounts the plugin volume ``:ro`` so its
    ``validate_config`` can SEE plugin widget types (and not emit false-positive
    "plugin not loaded" warnings) without ever installing anything. Deliberately
    does NOT use ``resolve_target()``: that gates on ``os.W_OK`` and would fall
    through to the local-venv branch on a read-only mount, leaving the volume
    site-packages invisible. We only need the path on ``sys.path`` for import +
    entry-point discovery — writability is irrelevant.

    Inserts ``<root>/venv/lib/pythonX.Y/site-packages`` at ``sys.path[0]`` iff it
    exists and isn't already present, then invalidates import caches. A no-op when
    the directory is absent (no volume, or venv not yet created). Never raises.
    """
    py_version = f"{sys.version_info.major}.{sys.version_info.minor}"
    sp = volume_root / "venv" / "lib" / f"python{py_version}" / "site-packages"
    if not sp.is_dir():
        return
    sp_str = str(sp)
    if sp_str in sys.path:
        return
    sys.path.insert(0, sp_str)
    importlib.invalidate_caches()
