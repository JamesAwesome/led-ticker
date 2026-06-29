"""hatch-vcs versioning is wired (tag = source of truth)."""

import re
from importlib.metadata import version
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_pyproject_uses_vcs_version():
    pp = (REPO / "pyproject.toml").read_text()
    assert 'requires = ["hatchling", "hatch-vcs"]' in pp
    assert 'dynamic = ["version"]' in pp
    assert '[tool.hatch.version]\nsource = "vcs"' in pp
    assert "version-file" in pp
    # the static version must be gone
    assert not re.search(r'^version\s*=\s*"', pp, re.MULTILINE)


def test_version_resolves_not_fallback():
    # The installed (editable) dist carries a real VCS-derived version, not the
    # 0.0.0 setuptools-scm fallback. (Requires `uv sync` after the pyproject edit.)
    v = version("led-ticker-core")
    assert re.match(r"^\d+\.\d+", v), v
    assert v != "0.0.0", v


def test_workflows_use_full_history_and_no_version_guard():
    pub = (REPO / ".github/workflows/publish.yml").read_text()
    assert "check_release_version" not in pub  # tag IS the version now
    assert "fetch-depth: 0" in pub
    ci = (REPO / ".github/workflows/ci.yml").read_text()
    # hatch-vcs needs history at install time; the package-installing jobs fetch it.
    assert "fetch-depth: 0" in ci


def test_version_guard_script_removed():
    assert not (REPO / "scripts/check_release_version.py").exists()
