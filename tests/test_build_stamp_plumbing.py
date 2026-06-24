"""The build paths stamp the commit ref into the image. Without this the
deployed commit is invisible (the motivating bug)."""

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_dockerfile_bakes_build_ref():
    df = (REPO / "Dockerfile").read_text()
    assert "ARG BUILD_REF" in df
    assert "ENV LED_TICKER_BUILD_REF=$BUILD_REF" in df
    # The Dockerfile parses git refs and writes the baked module.
    assert "/code/src/led_ticker/_build_ref.py" in df


def test_dockerfile_treats_unknown_arg_as_unset():
    # compose's BUILD_REF default (and any caller) can pass the literal
    # "unknown"; the bake must normalize it to empty so the git parse still
    # runs — otherwise a bare build skips git and bakes "unknown" (the bug).
    df = (REPO / "Dockerfile").read_text()
    assert '[ "$BR" = "unknown" ] && BR=' in df


def test_makefile_passes_build_arg():
    mk = (REPO / "Makefile").read_text()
    assert "--build-arg BUILD_REF" in mk


def test_compose_does_not_force_unknown():
    # The compose build-arg default must NOT be the literal "unknown" (that
    # suppressed the Dockerfile's git parse). Empty lets the parse run.
    cf = (REPO / "compose.yaml").read_text()
    assert "BUILD_REF: ${BUILD_REF:-}" in cf
    assert "${BUILD_REF:-unknown}" not in cf


def test_dockerignore_keeps_git_refs_drops_objects():
    # The git parse needs HEAD/refs in the build context; only the heavy
    # objects dir is excluded.
    di = (REPO / ".dockerignore").read_text()
    assert ".git/objects" in di
    # the bare `.git` exclusion would remove HEAD/refs and break the parse
    assert not any(line.strip() == ".git" for line in di.splitlines())
