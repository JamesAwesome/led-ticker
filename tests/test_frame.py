"""Tests for led_ticker.frame."""

from unittest.mock import MagicMock

from led_ticker.frame import LedFrame


def test_frame_get_clean_canvas():
    frame = LedFrame(led_cols=32, led_chain_length=5)
    canvas = frame.get_clean_canvas()
    assert canvas.width == 160  # 32 * 5


def test_frame_default_values():
    frame = LedFrame()
    assert frame.led_rows == 16
    assert frame.led_cols == 32
    assert frame.led_brightness == 100
    assert frame.led_hardware_mapping == "adafruit-hat"


def test_stub_canvas_size_honors_u_mapper_fold():
    """U-mapper folds 1×8 chain into 2×4: doubles height, halves width."""
    frame = LedFrame(
        led_rows=32,
        led_cols=64,
        led_chain_length=8,
        led_parallel=1,
        led_pixel_mapper_config="U-mapper",
    )
    canvas = frame.matrix.CreateFrameCanvas()
    assert canvas.height == 64
    assert canvas.width == 256


def test_stub_canvas_size_default_no_mapper():
    frame = LedFrame(led_rows=16, led_cols=32, led_chain_length=5)
    canvas = frame.matrix.CreateFrameCanvas()
    assert canvas.height == 16
    assert canvas.width == 160


def test_stub_canvas_size_parallel_chains():
    frame = LedFrame(led_rows=32, led_cols=64, led_chain_length=4, led_parallel=2)
    canvas = frame.matrix.CreateFrameCanvas()
    assert canvas.height == 64  # 32 × 2 parallel
    assert canvas.width == 256  # 64 × 4 chain


def test_ledframe_matrix_is_not_none_after_construction():
    frame = LedFrame(led_cols=32, led_chain_length=5)
    assert frame.matrix is not None


def test_framerate_fraction_default():
    """limit_refresh_rate_hz=0 → fraction stays at 1 (no change to behaviour)."""
    frame = LedFrame(led_limit_refresh_rate_hz=0)
    assert frame._framerate_fraction == 1


def test_framerate_fraction_computed():
    """100 Hz / 20 fps engine = fraction 5."""
    frame = LedFrame(led_limit_refresh_rate_hz=100)
    assert frame._framerate_fraction == 5


def test_framerate_fraction_rounds():
    """15 Hz / 20 fps rounds to 0.75 → floor-at-1 → 1."""
    frame = LedFrame(led_limit_refresh_rate_hz=15)
    assert frame._framerate_fraction == 1


def test_swap_passes_fraction_to_matrix():
    """frame.swap() must forward _framerate_fraction to SwapOnVSync."""
    frame = LedFrame(led_limit_refresh_rate_hz=100)
    mock_matrix = MagicMock()
    frame.matrix = mock_matrix
    canvas = object()
    frame.swap(canvas)
    mock_matrix.SwapOnVSync.assert_called_once_with(canvas, 5)


def test_swap_returns_new_canvas():
    """frame.swap() returns the back-buffer (new canvas, not the same object)."""
    frame = LedFrame()
    canvas = frame.matrix.CreateFrameCanvas()
    result = frame.swap(canvas)
    assert result is not canvas
