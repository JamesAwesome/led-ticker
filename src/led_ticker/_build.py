"""Build identity — "what commit is actually deployed".

Resolved in priority order:

1. ``LED_TICKER_BUILD_REF`` env — an explicit override (``make build-docker`` /
   ``make rebuild`` / ``compose`` pass it as a build arg; can also be set at
   runtime). The literal ``"unknown"`` and empty values are treated as not-set.
2. ``_build_ref.py`` baked into the package — the Dockerfile parses the source's
   git refs at build time and writes ``branch@shortsha`` here, so EVERY docker
   build (bare or ``make``) carries the real commit. Git is what catches a stale
   branch; the package version below can't (it's identical across branches).
3. git at runtime, for non-Docker installs that run from a checkout (the
   systemd/venv deploy in ``deploy/led-ticker.service``, or local dev) —
   ``branch@shortsha`` (+``dirty``).
4. the installed release version (a ``pip install`` from PyPI with no checkout)
   — e.g. ``v2.1.0``.
5. ``"unknown"`` — none of the above (rare for a real install).
"""

import functools
import os
import subprocess
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path


def build_ref() -> str:
    # The literal "unknown" / empty env is "not set" — fall through.
    env = os.environ.get("LED_TICKER_BUILD_REF", "").strip()
    if env and env != "unknown":
        return env
    return _baked_ref() or _git_ref() or _package_version() or "unknown"


def _baked_ref() -> str | None:
    """The ref baked into the package at Docker build time (``_build_ref.py``,
    written by the Dockerfile from the source's git refs). Absent for non-Docker
    installs — the file is git-ignored and only generated inside the image.
    """
    try:
        from led_ticker._build_ref import REF
    except ImportError:
        return None
    ref = (REF or "").strip()
    return ref if ref and ref != "unknown" else None


@functools.cache
def _package_version() -> str | None:
    """The installed release version of ``led-ticker-core`` (a PyPI/pip install
    with no checkout), e.g. ``v2.1.0``. ``None`` when the distribution isn't
    installed under that name.
    """
    try:
        return "v" + version("led-ticker-core")
    except PackageNotFoundError:
        return None


@functools.cache
def _git_ref() -> str | None:
    """``branch@shortsha(+dirty)`` from the git checkout this package lives in,
    or ``None`` when git or a ``.git`` dir is unavailable (Docker image, PyPI
    install). Cached — the display calls ``build_ref()`` once per status
    snapshot, and the answer doesn't change during a run.
    """
    repo = Path(__file__).resolve().parent

    def _git(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            timeout=2,
        )

    try:
        branch = _git("rev-parse", "--abbrev-ref", "HEAD")
        sha = _git("rev-parse", "--short", "HEAD")
        if branch.returncode != 0 or sha.returncode != 0:
            return None  # not a git checkout
        dirty = _git("diff", "--quiet", "HEAD").returncode != 0
    except (OSError, subprocess.SubprocessError):
        return None  # git not installed / timed out
    return f"{branch.stdout.strip()}@{sha.stdout.strip()}{'+dirty' if dirty else ''}"
