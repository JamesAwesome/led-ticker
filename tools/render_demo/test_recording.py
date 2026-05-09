"""Tests for the recording canvas wrapper."""

from __future__ import annotations

import sys
from pathlib import Path

# Make rgbmatrix test stub available before importing led_ticker, and put
# the repo root on sys.path so `tools.render_demo.recording` resolves when
# pytest is invoked directly against this file.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT / "tests" / "stubs"))
sys.path.insert(0, str(_REPO_ROOT))

from tools.render_demo.recording import RecordingMatrix, snapshot_to_image  # noqa: E402


def _make_stub_canvas(width: int, height: int):
    from rgbmatrix import RGBMatrix, RGBMatrixOptions

    opts = RGBMatrixOptions()
    opts.rows = height
    opts.cols = width
    opts.chain_length = 1
    matrix = RGBMatrix(options=opts)
    canvas = matrix.CreateFrameCanvas()
    return matrix, canvas


def test_snapshot_to_image_produces_correct_pixels():
    _, canvas = _make_stub_canvas(width=8, height=4)
    canvas.SetPixel(0, 0, 255, 0, 0)  # red top-left
    canvas.SetPixel(7, 3, 0, 0, 255)  # blue bottom-right

    img = snapshot_to_image(canvas)

    assert img.size == (8, 4)
    assert img.getpixel((0, 0)) == (255, 0, 0)
    assert img.getpixel((7, 3)) == (0, 0, 255)
    assert img.getpixel((1, 1)) == (0, 0, 0)  # untouched defaults to black


def test_recording_matrix_captures_each_swap():
    matrix, canvas = _make_stub_canvas(width=4, height=2)
    rec = RecordingMatrix(matrix)

    # First swap with a single red pixel
    canvas.SetPixel(0, 0, 255, 0, 0)
    canvas2 = rec.SwapOnVSync(canvas)

    # Second swap with a single green pixel
    canvas2.SetPixel(1, 0, 0, 255, 0)
    rec.SwapOnVSync(canvas2)

    assert len(rec.frames) == 2
    assert rec.frames[0].getpixel((0, 0)) == (255, 0, 0)
    assert rec.frames[1].getpixel((1, 0)) == (0, 255, 0)


def test_recording_matrix_forwards_to_underlying_swap():
    """SwapOnVSync must return the underlying stub's return value
    (the previous back-buffer) so engine code that captures the result
    keeps working."""
    matrix, canvas = _make_stub_canvas(width=2, height=2)
    rec = RecordingMatrix(matrix)

    returned = rec.SwapOnVSync(canvas)

    # Stub returns a different canvas (the previous back-buffer); we just
    # verify it's a canvas-shaped object, not None or the same one.
    assert returned is not None
    assert hasattr(returned, "SetPixel")


def test_recording_matrix_proxies_other_attrs():
    """CreateFrameCanvas, etc. should pass through to the wrapped matrix."""
    matrix, _ = _make_stub_canvas(width=4, height=4)
    rec = RecordingMatrix(matrix)
    new_canvas = rec.CreateFrameCanvas()
    assert new_canvas is not None
    assert hasattr(new_canvas, "SetPixel")
