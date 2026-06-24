"""The build paths stamp LED_TICKER_BUILD_REF into the image. Without this the
deployed commit is invisible (the motivating bug)."""

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_dockerfile_bakes_build_ref():
    df = (REPO / "Dockerfile").read_text()
    assert "ARG BUILD_REF" in df
    assert "ENV LED_TICKER_BUILD_REF=$BUILD_REF" in df


def test_makefile_passes_build_arg():
    mk = (REPO / "Makefile").read_text()
    assert "--build-arg BUILD_REF" in mk


def test_compose_forwards_build_ref():
    cf = (REPO / "compose.yaml").read_text()
    assert "BUILD_REF: ${BUILD_REF:-}" in cf
