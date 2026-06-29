"""
tests/test_setup_preflight.py — TDD test for scripts/setup.sh Docker preflight.

Tests that when Docker is absent the script:
  (a) prints the official install URLs (get.docker.com AND docs.docker.com/get-docker)
  (b) exits non-zero
  (c) does NOT attempt a compose up

All tests run the real shell script with a synthetic PATH built from a
symlink-farm containing the POSIX utilities the script needs (sh, cat, printf,
…) but NOT docker.  This makes 'command -v docker' fail unconditionally,
regardless of where docker happens to be installed on the host — including
/usr/bin/docker on GitHub Actions Ubuntu runners, which was silently causing
the whole suite to skip when PATH was naively stripped to /usr/bin:/bin.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

# Absolute path to the script under test — never rely on cwd.
REPO_ROOT = Path(__file__).parent.parent
SETUP_SH = REPO_ROOT / "scripts" / "setup.sh"

# ---------------------------------------------------------------------------
# Utilities symlinked into the no-docker bin dir.
#
# These are the external commands that setup.sh (and the POSIX sh interpreter
# itself) need to reach for the preflight + heredoc print path.  printf and
# test are shell built-ins in every target shell (sh/dash/bash) so they are
# included opportunistically but their absence won't break anything.
# ---------------------------------------------------------------------------
_SYMLINK_TOOLS = [
    "sh",
    "bash",
    "dash",
    "env",
    "cat",
    "cp",
    "printf",
    "rm",
    "mkdir",
    "test",
    "[",
    "ls",
    "grep",
    "sed",
    "mv",
    "mktemp",
    "chmod",
]


@pytest.fixture(scope="session")
def no_docker_bin(tmp_path_factory: pytest.TempPathFactory) -> str:
    """Return the path to a temp bin/ dir that has POSIX utils but NOT docker.

    Symlinks are created once per test session.  Each tool is resolved via
    shutil.which (using the real host PATH) and symlinked only when found, so
    the fixture degrades gracefully on minimal systems.  docker is explicitly
    NOT included, so 'command -v docker' in the subprocess fails regardless of
    where docker is installed on the host.
    """
    bin_dir = tmp_path_factory.mktemp("no_docker_bin")

    for tool in _SYMLINK_TOOLS:
        real = shutil.which(tool)
        if real:
            link = bin_dir / tool
            link.symlink_to(real)

    return str(bin_dir)


def _run_setup(
    mode: str | None = None,
    *,
    no_docker_bin: str,
) -> subprocess.CompletedProcess[str]:
    """Run scripts/setup.sh in a subprocess using the symlink-farm PATH.

    The subprocess sees only *no_docker_bin* on PATH, so:
    - The shell interpreter (sh) is reachable.
    - The script's coreutils (cat for the heredoc, printf, etc.) are reachable.
    - docker is NOT reachable, so 'command -v docker' always fails.
    """
    env = {**os.environ, "PATH": no_docker_bin}

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


class TestDockerPreflight:
    """The script must detect missing docker and print official install guidance."""

    def test_exits_nonzero_when_docker_absent(self, no_docker_bin: str) -> None:
        result = _run_setup(no_docker_bin=no_docker_bin)
        assert result.returncode != 0, (
            f"Expected non-zero exit when docker is absent, got {result.returncode}\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

    def test_output_contains_get_docker_com(self, no_docker_bin: str) -> None:
        """Linux/Pi install URL must appear."""
        result = _run_setup(no_docker_bin=no_docker_bin)
        combined = result.stdout + result.stderr
        assert "get.docker.com" in combined, (
            "Expected 'get.docker.com' in output when docker is absent.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

    def test_output_contains_docs_docker_com_get_docker(
        self, no_docker_bin: str
    ) -> None:
        """macOS/Windows install URL must appear."""
        result = _run_setup(no_docker_bin=no_docker_bin)
        combined = result.stdout + result.stderr
        assert "docs.docker.com/get-docker" in combined, (
            "Expected 'docs.docker.com/get-docker' in output when docker is absent.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

    def test_does_not_attempt_compose_up(self, no_docker_bin: str) -> None:
        """The script must not reach the docker compose up call."""
        result = _run_setup(no_docker_bin=no_docker_bin)
        combined = result.stdout + result.stderr
        # "compose up" would only appear if the preflight was bypassed.
        assert "compose up" not in combined, (
            "Script attempted 'compose up' despite docker being absent.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

    def test_preflight_applies_to_try_mode(self, no_docker_bin: str) -> None:
        """try mode must also fail the preflight — it's not skipped for try."""
        result = _run_setup(mode="try", no_docker_bin=no_docker_bin)
        assert result.returncode != 0, (
            "Expected non-zero exit in try mode when docker is absent.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        combined = result.stdout + result.stderr
        assert "get.docker.com" in combined

    def test_preflight_applies_to_deploy_mode(self, no_docker_bin: str) -> None:
        """deploy mode must also fail the preflight."""
        result = _run_setup(mode="deploy", no_docker_bin=no_docker_bin)
        assert result.returncode != 0
        combined = result.stdout + result.stderr
        assert "get.docker.com" in combined


class TestUsageErrors:
    """Bad arguments must print usage and exit non-zero."""

    def test_unknown_mode_exits_nonzero(self) -> None:
        # Mode-validation runs BEFORE the docker check in the script, so this
        # test uses the real system PATH — docker presence is irrelevant here.
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
