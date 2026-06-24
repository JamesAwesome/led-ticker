from led_ticker.backends.conformance import run_backend_conformance
from led_ticker.backends.headless import HeadlessBackend


def test_headless_passes_conformance():
    run_backend_conformance(lambda: HeadlessBackend(64, 32))


def test_rgbmatrix_stub_passes_conformance():
    # Off-hardware the stub backs RGBMatrix, so the rgbmatrix backend is
    # constructible and must also pass.
    from led_ticker.backends.rgbmatrix import RgbMatrixBackend

    run_backend_conformance(
        lambda: RgbMatrixBackend(led_rows=32, led_cols=64, led_chain_length=1)
    )
