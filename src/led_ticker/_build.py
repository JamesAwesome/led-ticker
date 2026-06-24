"""Build identity — "what commit is actually deployed".

Resolved in priority order:

1. ``LED_TICKER_BUILD_REF`` env — ``branch@shortsha``, computed on the host by
   ``make build-docker`` / ``make rebuild`` and passed into the image as a build
   arg (the Dockerfile sets it as ``ENV``). The literal ``"unknown"`` and empty
   values are treated as not-set.
2. git at runtime, for non-Docker installs that run from a checkout (the
   systemd/venv deploy in ``deploy/led-ticker.service``, or local dev) —
   ``branch@shortsha`` (+``dirty``).
3. ``"unknown"`` — neither applies (e.g. a bare ``docker compose build`` not run
   through ``make rebuild``, or a PyPI install). Deploy with ``make rebuild`` to
   stamp the commit.
"""

import functools
import os
import subprocess
from pathlib import Path


def build_ref() -> str:
    # The literal "unknown" / empty env is "not set" — fall through to git.
    env = os.environ.get("LED_TICKER_BUILD_REF", "").strip()
    if env and env != "unknown":
        return env
    return _git_ref() or "unknown"


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
    except (OSError, subprocess.SubprocessError):
        return None  # git not installed / timed out
    return f"{branch.stdout.strip()}@{sha.stdout.strip()}{'+dirty' if dirty else ''}"
