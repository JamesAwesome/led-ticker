"""
tests/test_setup_try_mode.py — TDD tests for setup.sh try-mode config selection.

Tests that in try mode:
  (a) When config/config.toml is ABSENT: echo mentions the example and
      hints to create config.toml; must NOT echo 'YOUR config'.
  (b) When config/config.toml EXISTS (with [web]): echo says 'YOUR config'
      or 'Previewing YOUR config'; no [web] warning.
  (c) When config/config.toml EXISTS but LACKS [web]: prominent warning
      mentioning [web] appears in the output.

All tests use a symlink-farm PATH with a fake docker that passes preflight
(docker --version + docker compose version succeed) but exits 0 immediately
on 'compose up' — so the test captures setup.sh's echo decisions without
blocking or requiring real Docker.
"""

import os
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
SETUP_SH = REPO_ROOT / "scripts" / "setup.sh"

# Same tools as test_setup_preflight.py — keep in sync.
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

# Fake docker that passes preflight but exits 0 on everything else.
# This lets the script reach its echo decisions and exit without blocking.
_FAKE_DOCKER_SCRIPT = textwrap.dedent("""\
    #!/bin/sh
    # Fake docker for setup.sh try-mode tests.
    # Passes preflight (--version, compose version); exits 0 on compose up.
    case "$1" in
      --version) echo "Docker version 24.0.0, build fake"; exit 0 ;;
      compose)
        case "$2" in
          version) echo "Docker Compose version v2.0.0"; exit 0 ;;
          *) exit 0 ;;  # "up", "down", etc. — succeed immediately
        esac
        ;;
    esac
    exit 0
""")


@pytest.fixture(scope="session")
def fake_docker_bin(tmp_path_factory: pytest.TempPathFactory) -> str:
    """Temp bin/ dir with POSIX utils AND a fake docker that passes preflight."""
    bin_dir = tmp_path_factory.mktemp("fake_docker_bin")

    for tool in _SYMLINK_TOOLS:
        real = shutil.which(tool)
        if real:
            link = bin_dir / tool
            link.symlink_to(real)

    fake_docker = bin_dir / "docker"
    fake_docker.write_text(_FAKE_DOCKER_SCRIPT)
    fake_docker.chmod(0o755)

    return str(bin_dir)


def _run_try(
    *,
    fake_docker_bin: str,
    cwd: Path,
    config_toml_content: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run setup.sh try from a temp CWD.

    If config_toml_content is not None, writes it to <cwd>/config/config.toml
    (simulating a user who has created their config). Otherwise no config.toml
    exists (fresh-clone path).
    """
    config_dir = cwd / "config"
    config_dir.mkdir(exist_ok=True)

    if config_toml_content is not None:
        (config_dir / "config.toml").write_text(config_toml_content)

    env = {**os.environ, "PATH": fake_docker_bin}

    return subprocess.run(
        ["sh", str(SETUP_SH), "try"],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(cwd),
    )


class TestTryModeNoConfigToml:
    """setup.sh try mode with NO config/config.toml (fresh-clone path)."""

    def test_echoes_example_hint(self, fake_docker_bin: str, tmp_path: Path) -> None:
        """Must mention the bundled example and hint to create config.toml."""
        result = _run_try(fake_docker_bin=fake_docker_bin, cwd=tmp_path)
        combined = result.stdout + result.stderr
        # The hint must tell the user to create config.toml or mention the example.
        assert ("config.toml" in combined) or ("example" in combined.lower()), (
            f"Expected hint about example or config.toml creation when absent.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

    def test_does_not_echo_your_config(
        self, fake_docker_bin: str, tmp_path: Path
    ) -> None:
        """Must NOT say 'YOUR config' when config.toml is absent."""
        result = _run_try(fake_docker_bin=fake_docker_bin, cwd=tmp_path)
        combined = result.stdout + result.stderr
        assert "YOUR config" not in combined, (
            f"'YOUR config' must not appear when config.toml is absent.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

    def test_exits_zero_or_docker_fails_cleanly(
        self, fake_docker_bin: str, tmp_path: Path
    ) -> None:
        """Script must not crash before reaching the docker step (only docker
        failure is acceptable as the exit cause in test mode)."""
        result = _run_try(fake_docker_bin=fake_docker_bin, cwd=tmp_path)
        # With our fake docker that exits 0, the script should succeed.
        assert result.returncode == 0, (
            f"Script exited non-zero unexpectedly.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )


class TestTryModeWithConfigTomlAndWeb:
    """setup.sh try mode WITH config/config.toml that has a [web] block."""

    def test_echoes_your_config(self, fake_docker_bin: str, tmp_path: Path) -> None:
        """Must say 'YOUR config' when config.toml is present."""
        content = "[web]\nport = 8080\n[display]\nrows = 16\ncols = 32\n"
        result = _run_try(
            fake_docker_bin=fake_docker_bin, cwd=tmp_path, config_toml_content=content
        )
        combined = result.stdout + result.stderr
        assert "YOUR config" in combined, (
            f"Expected 'YOUR config' when config/config.toml exists.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

    def test_mentions_config_path(self, fake_docker_bin: str, tmp_path: Path) -> None:
        """Must mention config/config.toml path so users know what's being previewed."""
        content = "[web]\nport = 8080\n[display]\nrows = 16\ncols = 32\n"
        result = _run_try(
            fake_docker_bin=fake_docker_bin, cwd=tmp_path, config_toml_content=content
        )
        combined = result.stdout + result.stderr
        assert "config/config.toml" in combined, (
            f"Expected 'config/config.toml' in output.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

    def test_no_web_warning_when_web_block_present(
        self, fake_docker_bin: str, tmp_path: Path
    ) -> None:
        """When [web] block is present, must NOT print the [web] warning."""
        content = "[web]\nport = 8080\n[display]\nrows = 16\ncols = 32\n"
        result = _run_try(
            fake_docker_bin=fake_docker_bin, cwd=tmp_path, config_toml_content=content
        )
        combined = result.stdout + result.stderr
        # "YOUR config" should appear (from the positive branch), but there
        # must be no warning about a missing [web] block.
        # The warning text will contain "live preview" or "needs" + "[web]".
        has_web_warning = (
            "live preview" in combined.lower() and "[web]" in combined
        ) or ("needs" in combined.lower() and "[web]" in combined)
        assert not has_web_warning, (
            f"[web] warning must not appear when [web] block is present.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )


class TestTryModeWithConfigTomlNoWeb:
    """setup.sh try mode WITH config/config.toml that LACKS a [web] block."""

    def test_warns_about_missing_web_block(
        self, fake_docker_bin: str, tmp_path: Path
    ) -> None:
        """Must print a prominent warning about the missing [web] block."""
        content = "[display]\nrows = 16\ncols = 32\n"  # No [web] section.
        result = _run_try(
            fake_docker_bin=fake_docker_bin, cwd=tmp_path, config_toml_content=content
        )
        combined = result.stdout + result.stderr
        assert "[web]" in combined, (
            f"Expected warning mentioning [web] when config.toml has no [web] block.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

    def test_still_echoes_your_config(
        self, fake_docker_bin: str, tmp_path: Path
    ) -> None:
        """Even with a missing [web] block, must still say 'YOUR config'
        (warning + proceed, don't abort)."""
        content = "[display]\nrows = 16\ncols = 32\n"
        result = _run_try(
            fake_docker_bin=fake_docker_bin, cwd=tmp_path, config_toml_content=content
        )
        combined = result.stdout + result.stderr
        assert "YOUR config" in combined, (
            f"Expected 'YOUR config' even when [web] is absent (warn, don't abort).\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

    def test_does_not_abort_on_missing_web(
        self, fake_docker_bin: str, tmp_path: Path
    ) -> None:
        """Script must NOT abort when [web] is absent — warning only, not abort."""
        content = "[display]\nrows = 16\ncols = 32\n"
        result = _run_try(
            fake_docker_bin=fake_docker_bin, cwd=tmp_path, config_toml_content=content
        )
        # With our fake docker (exits 0 everywhere), the script must still succeed.
        assert result.returncode == 0, (
            f"Script aborted on missing [web] block — must warn only, not abort.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )


class TestMakeTryWiring:
    """Tripwire: `make try` must route through scripts/setup.sh try.

    The TRY_CONFIG selection (previewing the user's config/config.toml) lives
    in setup.sh's try mode. A `make try` recipe that calls `docker compose`
    directly silently disables the whole your-config feature on the exact
    path the tutorial teaches — a persona walk caught precisely this gap.
    """

    def test_make_try_recipe_invokes_setup_sh_try(self) -> None:
        makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
        recipe_lines: list[str] = []
        in_try = False
        for line in makefile.splitlines():
            if line.startswith("try:"):
                in_try = True
                continue
            if in_try:
                if line.startswith("\t"):
                    recipe_lines.append(line)
                else:
                    break
        recipe = "\n".join(recipe_lines)
        assert "scripts/setup.sh try" in recipe, (
            "`make try` must invoke `scripts/setup.sh try` (which selects "
            "TRY_CONFIG for a user config/config.toml) — not call docker "
            f"compose directly.\nRecipe was:\n{recipe}"
        )
