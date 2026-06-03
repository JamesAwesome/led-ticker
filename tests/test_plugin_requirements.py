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
