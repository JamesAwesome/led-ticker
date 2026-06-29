"""
tests/test_setup_preflight.py — TDD test for scripts/setup.sh Docker preflight.

Tests that when Docker is absent the script:
  (a) prints the official install URLs (get.docker.com AND docs.docker.com/get-docker)
  (b) exits non-zero
  (c) does NOT attempt a compose up

All tests run the real shell script with a synthetic PATH that contains no
docker binary, so the check is structural (the script's own detection logic)
not a mock.
"""

import os
import subprocess
from pathlib import Path

# Absolute path to the script under test — never rely on cwd.
REPO_ROOT = Path(__file__).parent.parent
SETUP_SH = REPO_ROOT / "scripts" / "setup.sh"


def _run_setup(
    mode: str | None = None, *, path_dirs: list[str] | None = None
) -> subprocess.CompletedProcess[str]:
    """Run scripts/setup.sh in a subprocess with a controlled PATH.

    *path_dirs* replaces PATH entirely; pass a list of directories that
    contain real POSIX utilities but NOT docker.  Defaults to the bare
    minimum (/usr/bin:/bin) which is present on every POSIX system and
    never ships docker.
    """
    if path_dirs is None:
        path_dirs = ["/usr/bin", "/bin"]

    env = {**os.environ, "PATH": ":".join(path_dirs)}

    cmd = ["sh", str(SETUP_SH)]
    if mode is not None:
        cmd.append(mode)

    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=env,
        # Run from the repo root so relative paths (config/, .env.example) resolve.
        cwd=str(REPO_ROOT),
    )


def _docker_in_stripped_path() -> bool:
    """Return True if docker somehow lives in /usr/bin or /bin (extremely unlikely)."""
    return any((Path(d) / "docker").exists() for d in ("/usr/bin", "/bin"))


# ---------------------------------------------------------------------------
# Guard: skip the whole module if docker actually lives in the stripped PATH.
# In practice this never happens, but the guard prevents a false-green on an
# exotic system where docker is at /usr/bin/docker.
# ---------------------------------------------------------------------------
if _docker_in_stripped_path():
    import pytest

    _SKIP_REASON = (
        "docker found in /usr/bin or /bin"
        " — cannot strip it from PATH for preflight test"
    )
    pytestmark = pytest.mark.skip(reason=_SKIP_REASON)


class TestDockerPreflight:
    """The script must detect missing docker and print official install guidance."""

    def test_exits_nonzero_when_docker_absent(self) -> None:
        result = _run_setup()
        assert result.returncode != 0, (
            f"Expected non-zero exit when docker is absent, got {result.returncode}\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

    def test_output_contains_get_docker_com(self) -> None:
        """Linux/Pi install URL must appear."""
        result = _run_setup()
        combined = result.stdout + result.stderr
        assert "get.docker.com" in combined, (
            "Expected 'get.docker.com' in output when docker is absent.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

    def test_output_contains_docs_docker_com_get_docker(self) -> None:
        """macOS/Windows install URL must appear."""
        result = _run_setup()
        combined = result.stdout + result.stderr
        assert "docs.docker.com/get-docker" in combined, (
            "Expected 'docs.docker.com/get-docker' in output when docker is absent.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

    def test_does_not_attempt_compose_up(self) -> None:
        """The script must not reach the docker compose up call."""
        result = _run_setup()
        combined = result.stdout + result.stderr
        # "compose up" would only appear if the preflight was bypassed.
        assert "compose up" not in combined, (
            "Script attempted 'compose up' despite docker being absent.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

    def test_preflight_applies_to_try_mode(self) -> None:
        """try mode must also fail the preflight — it's not skipped for try."""
        result = _run_setup(mode="try")
        assert result.returncode != 0, (
            "Expected non-zero exit in try mode when docker is absent.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        combined = result.stdout + result.stderr
        assert "get.docker.com" in combined

    def test_preflight_applies_to_deploy_mode(self) -> None:
        """deploy mode must also fail the preflight."""
        result = _run_setup(mode="deploy")
        assert result.returncode != 0
        combined = result.stdout + result.stderr
        assert "get.docker.com" in combined


class TestUsageErrors:
    """Bad arguments must print usage and exit non-zero."""

    def test_unknown_mode_exits_nonzero(self) -> None:
        # Use a path that actually has docker so we get past the preflight
        # and hit the mode-validation branch.  If docker isn't available at
        # all on this machine, the test still validates exit code != 0.
        result = subprocess.run(
            ["sh", str(SETUP_SH), "bogus-mode"],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
        assert result.returncode != 0

    def test_unknown_mode_prints_usage(self) -> None:
        result = subprocess.run(
            ["sh", str(SETUP_SH), "bogus-mode"],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
        combined = result.stdout + result.stderr
        assert "bogus-mode" in combined or "Usage" in combined

    def test_help_flag_exits_zero(self) -> None:
        result = subprocess.run(
            ["sh", str(SETUP_SH), "--help"],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
        assert result.returncode == 0

    def test_help_flag_mentions_modes(self) -> None:
        result = subprocess.run(
            ["sh", str(SETUP_SH), "--help"],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
        combined = result.stdout + result.stderr
        assert "try" in combined and "deploy" in combined
