import subprocess
import sys
import textwrap
from pathlib import Path

from scripts.check_release_version import parse_and_check


def _pyproject(tmp_path: Path, version: str) -> str:
    p = tmp_path / "pyproject.toml"
    p.write_text(
        textwrap.dedent(f"""
        [project]
        name = "led-ticker-core"
        version = "{version}"
    """)
    )
    return str(p)


def test_matching_tag_ok(tmp_path):
    ok, msg = parse_and_check("v2.0.0", _pyproject(tmp_path, "2.0.0"))
    assert ok is True, msg


def test_mismatched_tag_fails(tmp_path):
    ok, msg = parse_and_check("v2.0.1", _pyproject(tmp_path, "2.0.0"))
    assert ok is False
    assert "2.0.1" in msg and "2.0.0" in msg


def test_tag_without_v_prefix_fails(tmp_path):
    ok, msg = parse_and_check("2.0.0", _pyproject(tmp_path, "2.0.0"))
    assert ok is False


def test_cli_exit_codes(tmp_path):
    pp = _pyproject(tmp_path, "2.0.0")
    ok = subprocess.run(
        [sys.executable, "scripts/check_release_version.py", "v2.0.0", pp]
    )
    bad = subprocess.run(
        [sys.executable, "scripts/check_release_version.py", "v9.9.9", pp]
    )
    assert ok.returncode == 0
    assert bad.returncode == 1
