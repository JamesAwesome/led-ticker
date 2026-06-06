"""Tripwire for the Writing-a-transition how-to's worked example
(examples/plugins/example_transition).

Keeps the shipped example (and the docs bound to it) honest: the wipe registers,
and its frame_at DRAWS onto the canvas (return value ignored), sweeps a colored
line midway, and snaps to the incoming frame at t >= 1.0.
"""

import shutil
from pathlib import Path

import pytest

from led_ticker import _plugin_loader as L
from led_ticker.transitions import get_transition_class

EXAMPLE_DIR = (
    Path(__file__).resolve().parents[2] / "examples" / "plugins" / "example_transition"
)


class _Frame:
    """Stub frame: records draws and paints a recognizable pixel at (0, 0)."""

    def __init__(self, color):
        self.color = color
        self.drawn = False

    def draw(self, canvas, cursor_pos=0):
        self.drawn = True
        canvas.SetPixel(0, 0, *self.color)
        return canvas, 0


def _canvas():
    from rgbmatrix import RGBMatrix, RGBMatrixOptions

    opts = RGBMatrixOptions()
    opts.cols = 64
    opts.rows = 32
    opts.chain_length = 1
    opts.parallel = 1
    return RGBMatrix(options=opts).CreateFrameCanvas()


@pytest.fixture
def wipe_cls(tmp_path):
    L.reset_plugins()
    pdir = tmp_path / "plugins"
    pdir.mkdir()
    shutil.copytree(EXAMPLE_DIR, pdir / "example_transition")
    try:
        result = L.load_plugins(pdir, entry_points_enabled=False)
        assert (
            "example_transition" in {i.namespace for i in result.loaded}
        ), result.failed
        yield get_transition_class("example_transition.wipe")
    finally:
        L.reset_plugins()


def test_wipe_registers(wipe_cls):
    assert wipe_cls.__name__ == "Wipe"
    assert getattr(wipe_cls, "min_frames", 0) == 16


def test_wipe_draws_sweep_line_midway(wipe_cls):
    canvas = _canvas()
    out_frame = _Frame((1, 2, 3))
    in_frame = _Frame((4, 5, 6))
    wipe_cls().frame_at(0.5, canvas, out_frame, in_frame)
    # outgoing drawn, incoming not yet; a cyan sweep line sits at x = 32 (t*64).
    assert out_frame.drawn and not in_frame.drawn
    assert canvas.get_pixel(32, 0) == (0, 255, 255)


def test_wipe_snaps_to_incoming_at_end(wipe_cls):
    canvas = _canvas()
    out_frame = _Frame((1, 2, 3))
    in_frame = _Frame((4, 5, 6))
    wipe_cls().frame_at(1.0, canvas, out_frame, in_frame)
    assert in_frame.drawn
    assert canvas.get_pixel(0, 0) == (4, 5, 6)


def test_wipe_accepts_color_config(wipe_cls):
    canvas = _canvas()
    out_frame = _Frame((1, 2, 3))
    in_frame = _Frame((4, 5, 6))
    wipe_cls(color=[255, 0, 0]).frame_at(0.5, canvas, out_frame, in_frame)
    assert canvas.get_pixel(32, 0) == (255, 0, 0)
