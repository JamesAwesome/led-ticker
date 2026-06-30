"""Tripwire: the production Dockerfile must hard-fail a 0.0.0 core build.

Regression lock for the silent-0.0.0 image that broke plugin installs. The guard
lives ONLY in the production Dockerfile; Dockerfile.try intentionally builds core
at 0.0.0 and excludes it from constraints, so it must NOT carry the guard.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_prod_dockerfile_hard_fails_on_0_0_0():
    text = (REPO_ROOT / "Dockerfile").read_text()
    assert "CORE_VER" in text
    assert '"$CORE_VER" = "0.0.0"' in text
    assert "exit 1" in text


def test_try_dockerfile_is_exempt_from_guard():
    text = (REPO_ROOT / "Dockerfile.try").read_text()
    assert '"$CORE_VER" = "0.0.0"' not in text
