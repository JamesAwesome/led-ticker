"""Tripwire for the Service plugins how-to's example plugin.

Keeps examples/plugins/example_service (the page's code) honest: the overlay and
the on_startup hook register, and the overlay paints a status dot.
"""

import shutil
from pathlib import Path

import pytest

from led_ticker import _plugin_loader as L

EXAMPLE_DIR = (
    Path(__file__).resolve().parents[2] / "examples" / "plugins" / "example_service"
)


def _canvas():
    from rgbmatrix import RGBMatrix, RGBMatrixOptions

    opts = RGBMatrixOptions()
    opts.cols = 64
    opts.rows = 32
    opts.chain_length = 1
    opts.parallel = 1
    return RGBMatrix(options=opts).CreateFrameCanvas()


@pytest.fixture
def result(tmp_path):
    L.reset_plugins()
    pdir = tmp_path / "plugins"
    pdir.mkdir()
    shutil.copytree(EXAMPLE_DIR, pdir / "example_service")
    try:
        res = L.load_plugins(pdir, entry_points_enabled=False)
        loaded = {i.namespace for i in res.loaded}
        assert "example_service" in loaded, res.failed
        yield res
    finally:
        L.reset_plugins()


def test_overlay_and_startup_registered(result):
    overlay_ns = [ns for ns, _ in result.overlays]
    startup_ns = [ns for ns, _ in result.startup_hooks]
    assert "example_service" in overlay_ns
    assert "example_service" in startup_ns


def test_overlay_paints_default_status_dot(result):
    paint = next(fn for ns, fn in result.overlays if ns == "example_service")
    canvas = _canvas()
    paint(canvas)
    # Default state is offline -> a red dot at (0, 0).
    assert canvas.get_pixel(0, 0) == (200, 0, 0)
