"""Build identity — "what commit is actually deployed".

Resolved in priority order:

1. ``LED_TICKER_BUILD_REF`` env — ``branch@shortsha``, computed on the host by
   ``make build`` / ``make update`` and passed into the image as a build
   arg (the Dockerfile sets it as ``ENV``). The literal ``"unknown"`` and empty
   values are treated as not-set.
2. git at runtime, when running from a checkout (local dev or a custom
   supervisor) — ``branch@shortsha`` (+``dirty``).
3. The installed package version (``importlib.metadata``) — for a PyPI or bare
   Docker install.  Because the version is VCS-derived (hatch-vcs), it carries
   the short SHA on untagged builds, e.g. ``2.2.1.dev3+gabc1234``.
4. ``"unknown"`` — none of the above applies.
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
    return _git_ref() or _package_version() or "unknown"


@functools.cache
def _git_ref() -> str | None:
    """``branch@shortsha(+dirty)`` from the git checkout this package lives in,
    or ``None`` when git or a ``.git`` dir is unavailable (the Docker image, a
    PyPI install). Cached — the display calls ``build_ref()`` once per status
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
    except OSError, subprocess.SubprocessError:
        return None  # git not installed / timed out
    return f"{branch.stdout.strip()}@{sha.stdout.strip()}{'+dirty' if dirty else ''}"


@functools.cache
def _package_version() -> str | None:
    """The installed VCS-derived version of ``led-ticker-core`` (carries the
    short SHA on untagged builds, e.g. ``2.2.1.dev3+gabc1234``) — the last-resort
    identity for a PyPI / bare-docker install with no env stamp and no checkout.
    """
    try:
        return version("led-ticker-core")
    except PackageNotFoundError:
        return None
