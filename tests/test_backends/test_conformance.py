from led_ticker.backends.conformance import run_backend_conformance
from led_ticker.backends.headless import HeadlessBackend


def test_headless_passes_conformance():
    run_backend_conformance(lambda: HeadlessBackend(64, 32))


def test_rgbmatrix_stub_passes_conformance():
    # Off-hardware the stub backs RGBMatrix, so the rgbmatrix backend is
    # constructible and must also pass. (It is exempt from the engine-buildable
    # convention check — the engine special-cases its construction.)
    from led_ticker.backends.rgbmatrix import RgbMatrixBackend

    run_backend_conformance(
        lambda: RgbMatrixBackend(led_rows=32, led_cols=64, led_chain_length=1)
    )


def test_conformance_rejects_non_engine_buildable_backend():
    # A backend can pass every contract check via a caller-written factory yet
    # NOT be buildable by the engine, which constructs non-rgbmatrix backends as
    # `cls(width, height, pixel_mapper_config=…)`. A backend whose __init__ omits
    # pixel_mapper_config must FAIL conformance (the gap the telnet review caught).
    import pytest

    class MissingPixelMapper(HeadlessBackend):
        def __init__(self, width: int = 64, height: int = 32) -> None:
            super().__init__(width, height)  # drops the pixel_mapper_config kwarg

    with pytest.raises(AssertionError, match="engine-buildable"):
        run_backend_conformance(lambda: MissingPixelMapper(64, 32))
