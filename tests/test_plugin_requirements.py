"""Guard tests for the declarative plugin-requirements file.

See docs/superpowers/specs/2026-06-03-plugin-requirements-file-design.md.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _noncomment_lines(text: str) -> list[str]:
    out = []
    for raw in text.splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            out.append(line)
    return out


def test_example_requirements_exists_and_lists_pool():
    example = REPO_ROOT / "config" / "requirements-plugins.example.txt"
    assert example.exists(), "config/requirements-plugins.example.txt must exist"
    lines = _noncomment_lines(example.read_text())
    assert any("led-ticker-pool" in line for line in lines), (
        "the example should ship the led-ticker-pool plugin line"
    )
    for line in lines:
        assert " " not in line, f"malformed requirement line: {line!r}"


def test_live_requirements_file_is_gitignored():
    gitignore = (REPO_ROOT / ".gitignore").read_text()
    assert "config/requirements-plugins.txt" in gitignore, (
        "the live requirements-plugins.txt must be gitignored"
    )


def test_dockerfile_installs_from_requirements_file():
    dockerfile = (REPO_ROOT / "Dockerfile").read_text()
    assert "-r /code/config/requirements-plugins.txt" in dockerfile, (
        "Dockerfile should pip-install the live requirements-plugins.txt"
    )
    assert "config/requirements-plugins.example.txt" in dockerfile, (
        "Dockerfile should COPY the example (guaranteed source for the optional-file trick)"
    )
    assert "POOL_PLUGIN_CACHE_BUST" not in dockerfile, (
        "the per-plugin cache-bust ARG should be removed"
    )
    assert "led-ticker-pool.git" not in dockerfile, (
        "no hardcoded plugin git URL should remain in the Dockerfile"
    )


def test_install_sh_installs_plugin_requirements():
    install_sh = (REPO_ROOT / "deploy" / "install.sh").read_text()
    assert "config/requirements-plugins.txt" in install_sh, (
        "install.sh should install the live requirements-plugins.txt"
    )
    assert "--no-deps" in install_sh, (
        "install.sh plugin install should use --no-deps"
    )
