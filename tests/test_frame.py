"""Tests for led_ticker.frame."""

from led_ticker.frame import LedFrame


def test_frame_get_clean_canvas():
    frame = LedFrame(led_cols=32, led_chain=5)
    canvas = frame.get_clean_canvas()
    assert canvas.width == 160  # 32 * 5


def test_frame_default_values():
    frame = LedFrame()
    assert frame.led_rows == 32
    assert frame.led_cols == 64
    assert frame.led_brightness == 100
    assert frame.led_gpio_mapping == "adafruit-hat"


def test_stub_canvas_size_honors_u_mapper_fold():
    """U-mapper folds 1×8 chain into 2×4: doubles height, halves width."""
    frame = LedFrame(
        led_rows=32,
        led_cols=64,
        led_chain=8,
        led_parallel=1,
        led_pixel_mapper="U-mapper",
    )
    canvas = frame.matrix.CreateFrameCanvas()
    assert canvas.height == 64
    assert canvas.width == 256


def test_stub_canvas_size_default_no_mapper():
    frame = LedFrame(led_rows=16, led_cols=32, led_chain=5)
    canvas = frame.matrix.CreateFrameCanvas()
    assert canvas.height == 16
    assert canvas.width == 160


def test_stub_canvas_size_parallel_chains():
    frame = LedFrame(led_rows=32, led_cols=64, led_chain=4, led_parallel=2)
    canvas = frame.matrix.CreateFrameCanvas()
    assert canvas.height == 64  # 32 × 2 parallel
    assert canvas.width == 256  # 64 × 4 chain


def test_ledframe_matrix_is_not_none_after_construction():
    frame = LedFrame(led_cols=32, led_chain=5)
    assert frame.matrix is not None
