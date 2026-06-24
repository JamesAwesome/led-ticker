from led_ticker.backends import Backend, get_backend_class
from led_ticker.backends.rgbmatrix import RgbMatrixBackend, build_options


def test_registered_as_rgbmatrix():
    assert get_backend_class("rgbmatrix") is RgbMatrixBackend


def test_satisfies_backend_protocol():
    assert isinstance(RgbMatrixBackend(), Backend)


def test_build_options_maps_fields():
    b = RgbMatrixBackend(
        led_rows=16,
        led_cols=32,
        led_chain_length=5,
        led_gpio_slowdown=2,
        led_pwm_bits=8,
        led_hardware_mapping="adafruit-hat",
    )
    opts = build_options(b)
    assert opts.rows == 16
    assert opts.cols == 32
    assert opts.chain_length == 5
    assert opts.gpio_slowdown == 2
    assert opts.pwm_bits == 8
    assert opts.hardware_mapping == "adafruit-hat"


def test_framerate_fraction_default_until_setup():
    b = RgbMatrixBackend(led_limit_refresh_rate_hz=0)
    b.setup()
    assert b.framerate_fraction == 1


def test_framerate_fraction_from_refresh_cap():
    # _ENGINE_FPS = 20; 60Hz cap => round(60/20) = 3.
    b = RgbMatrixBackend(led_limit_refresh_rate_hz=60)
    b.setup()
    assert b.framerate_fraction == 3


def test_swap_returns_different_object_through_stub():
    b = RgbMatrixBackend(led_rows=16, led_cols=32, led_chain_length=5)
    b.setup()
    front = b.create_canvas()
    back = b.swap(front, b.framerate_fraction)
    assert back is not front
