"""Startup reconcile: make the installed plugins match the manifest (SoT).

Runs at the top of app/run.py:run() — before plugins load and before the frame
build drops root. NEVER raises: a failure is recorded + logged, the panel boots.
"""

import importlib.metadata
import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import attrs


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
    venv_dir.mkdir(exist_ok=True)
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
