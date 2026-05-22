"""Tests that CanvasLike Protocol in _types.py is satisfied
by all canvas implementations."""

from typing import Any

from led_ticker._types import Canvas, CanvasLike


class TestCanvasLike:
    def test_canvaslike_is_exported(self):
        from led_ticker._types import CanvasLike

        assert CanvasLike is not None

    def test_canvas_is_any(self):
        assert Canvas is Any

    def test_stub_canvas_satisfies_protocol(self):
        from rgbmatrix import RGBMatrix, RGBMatrixOptions

        opts = RGBMatrixOptions()
        opts.cols = 32
        opts.rows = 16
        matrix = RGBMatrix(options=opts)
        canvas = matrix.CreateFrameCanvas()
        assert isinstance(canvas, CanvasLike)

    def test_scaled_canvas_satisfies_protocol(self):
        from led_ticker.frame import LedFrame
        from led_ticker.scaled_canvas import ScaledCanvas

        frame = LedFrame(led_cols=32, led_chain=5)
        canvas = frame.get_clean_canvas()
        scaled = ScaledCanvas(real=canvas, scale=2)
        assert isinstance(scaled, CanvasLike)

    def test_plain_object_without_methods_does_not_satisfy(self):
        class NotACanvas:
            pass

        assert not isinstance(NotACanvas(), CanvasLike)
