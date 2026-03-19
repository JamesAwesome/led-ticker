"""Tests for led_ticker.colors."""

from led_ticker.colors import (
    DEFAULT_COLOR,
    DOWN_TREND_COLOR,
    RANDOM_COLOR,
    RGB_WHITE,
    UP_TREND_COLOR,
)


def test_rgb_white():
    assert RGB_WHITE.red == 255
    assert RGB_WHITE.green == 255
    assert RGB_WHITE.blue == 255


def test_default_color_is_yellow():
    assert DEFAULT_COLOR.red == 255
    assert DEFAULT_COLOR.green == 255
    assert DEFAULT_COLOR.blue == 0


def test_trend_colors():
    assert UP_TREND_COLOR.red == 46
    assert DOWN_TREND_COLOR.red == 194


def test_random_color_cycles():
    colors = [next(RANDOM_COLOR) for _ in range(10)]
    # Should cycle through 5 colors twice
    assert colors[0] == colors[5]
    assert colors[1] == colors[6]
