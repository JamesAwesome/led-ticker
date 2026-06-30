"""Tripwire: the build must use the GLOBAL setuptools-scm pretend-version var.

Root cause of the silent-0.0.0 image (verified 2026-06-30): hatch-vcs does not
pass a dist name to setuptools-scm, so the per-distribution
`SETUPTOOLS_SCM_PRETEND_VERSION_FOR_LED_TICKER_CORE` env var NEVER matches and the
in-image build falls back to `fallback_version = "0.0.0"`. Only the global
`SETUPTOOLS_SCM_PRETEND_VERSION` is honored.

Isolation proof (no .git, build the wheel):
  SETUPTOOLS_SCM_PRETEND_VERSION=9.9.9        -> led_ticker_core-9.9.9  (honored)
  ...PRETEND_VERSION_FOR_LED_TICKER_CORE=9.9.9 -> led_ticker_core-0.0.0  (ignored)

This test fails if any shippable build file reintroduces the inert `_FOR_` form.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Every file on a path that builds/passes the version into the image.
BUILD_FILES = [
    "Dockerfile",
    "Makefile",
    "compose.yaml",
    "scripts/setup.sh",
    "scripts/compute-version.sh",
    ".github/workflows/ci.yml",
]

INERT_VAR = "SETUPTOOLS_SCM_PRETEND_VERSION_FOR_"
GLOBAL_VAR = "SETUPTOOLS_SCM_PRETEND_VERSION"


def _code_lines(text):
    # All build files use '#' comments; a warning comment may legitimately NAME
    # the inert var. Only flag real uses, so skip comment-only lines.
    return [ln for ln in text.splitlines() if not ln.lstrip().startswith("#")]


def test_no_build_file_uses_the_inert_per_dist_var():
    offenders = []
    for rel in BUILD_FILES:
        text = (REPO_ROOT / rel).read_text()
        if any(INERT_VAR in ln for ln in _code_lines(text)):
            offenders.append(rel)
    assert not offenders, (
        f"These build files use the inert per-dist pretend var "
        f"({INERT_VAR}<name>), which hatch-vcs ignores -> image bakes 0.0.0. "
        f"Use the global {GLOBAL_VAR}: {offenders}"
    )


def test_dockerfile_passes_global_var_into_the_core_build():
    text = (REPO_ROOT / "Dockerfile").read_text()
    # The ARG is declared and threaded into the RUN that installs core.
    assert f"ARG {GLOBAL_VAR}=" in text
    assert f'{GLOBAL_VAR}="${GLOBAL_VAR}" pip install --no-deps .' in text
