"""Startup reconcile: make the installed plugins match the manifest (SoT).

Runs at the top of app/run.py:run() — before plugins load and before the frame
build drops root. NEVER raises: a failure is recorded + logged, the panel boots.
"""

import os
import sys
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
