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


def test_new_palette_colors_exist_and_are_correct():
    from led_ticker.colors import (
        BLUE,
        CYAN,
        GREEN,
        ORANGE,
        PINK,
        PURPLE,
        RED,
        YELLOW,
    )

    assert (RED.red, RED.green, RED.blue) == (255, 40, 40)
    assert (GREEN.red, GREEN.green, GREEN.blue) == (46, 200, 46)
    assert (BLUE.red, BLUE.green, BLUE.blue) == (40, 100, 255)
    assert (YELLOW.red, YELLOW.green, YELLOW.blue) == (255, 220, 0)
    assert (ORANGE.red, ORANGE.green, ORANGE.blue) == (255, 140, 0)
    assert (PURPLE.red, PURPLE.green, PURPLE.blue) == (160, 60, 200)
    assert (CYAN.red, CYAN.green, CYAN.blue) == (0, 220, 220)
    assert (PINK.red, PINK.green, PINK.blue) == (240, 70, 200)


def test_make_color_public_helper():
    from led_ticker.colors import make_color

    c = make_color(10, 20, 30)
    assert c.red == 10
    assert c.green == 20
    assert c.blue == 30


def test_make_color_replaces_private_helper():
    import led_ticker.colors as colors_mod

    assert hasattr(colors_mod, "make_color")
    assert not hasattr(colors_mod, "_color")
