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


def test_dockerfile_accepts_pretend_version_before_install():
    df = (REPO / "Dockerfile").read_text()
    arg = "ARG SETUPTOOLS_SCM_PRETEND_VERSION_FOR_LED_TICKER_CORE"
    assert arg in df
    assert "ENV SETUPTOOLS_SCM_PRETEND_VERSION_FOR_LED_TICKER_CORE" in df
    # must be declared BEFORE the source install so the build picks it up
    assert df.index(arg) < df.index("RUN pip install --no-deps .")


def test_makefile_and_compose_pass_pretend_version():
    mk = (REPO / "Makefile").read_text()
    cf = (REPO / "compose.yaml").read_text()
    pretend_arg = "SETUPTOOLS_SCM_PRETEND_VERSION_FOR_LED_TICKER_CORE"
    assert f"--build-arg {pretend_arg}" in mk
    assert f"{pretend_arg}: ${{{pretend_arg}:-}}" in cf
