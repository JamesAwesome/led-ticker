"""Build identity — "what commit is actually deployed".

Resolved in priority order:

1. ``LED_TICKER_BUILD_REF`` — baked into the Docker image at build time (the
   Dockerfile sets it from the ``BUILD_REF`` arg; see ``make build-docker`` /
   ``compose.yaml``). The container has no git at runtime, so this is the only
   source there.
2. git, for non-Docker installs that run from a checkout (the systemd/venv
   deploy in ``deploy/led-ticker.service``, or local dev) — ``branch@shortsha``
   (+``dirty``).
3. the installed release version (a ``pip install`` from PyPI with no checkout)
   — e.g. ``v2.1.0``.
4. ``"unknown"`` — none of the above (should be rare for a real install).
"""

import functools
import os
import subprocess
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path


def build_ref() -> str:
    # A bare `docker compose build` (no BUILD_REF arg) bakes the literal
    # "unknown" into the env — treat that, and an empty value, as not-set so we
    # still fall through to the git / package-version tiers.
    env = os.environ.get("LED_TICKER_BUILD_REF", "").strip()
    if env and env != "unknown":
        return env
    return _git_ref() or _package_version() or "unknown"


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
