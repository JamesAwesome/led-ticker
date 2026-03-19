"""Tests for led_ticker.frame."""

from led_ticker.frame import LedFrame


def test_frame_creates_matrix():
    frame = LedFrame(led_cols=32, led_chain=5)
    assert frame.matrix is not None


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
