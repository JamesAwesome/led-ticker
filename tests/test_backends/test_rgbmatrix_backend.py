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
    back = b.swap(front)
    assert back is not front


def test_swap_applies_own_framerate_fraction_to_matrix():
    """swap() reads the backend's OWN framerate_fraction (no protocol arg) and
    passes it to SwapOnVSync — the rgbmatrix tearing/refresh-cap behaviour must
    survive dropping the param from the protocol."""
    b = RgbMatrixBackend(led_limit_refresh_rate_hz=60)  # => fraction 3
    b.setup()
    assert b.framerate_fraction == 3
    captured = []
    real_swap = b._matrix.SwapOnVSync

    def recording_swap(canvas, framerate_fraction=1):
        captured.append(framerate_fraction)
        return real_swap(canvas, framerate_fraction)

    b._matrix.SwapOnVSync = recording_swap
    b.swap(b.create_canvas())
    assert captured == [3]


def test_brightness_setter_forwards_to_matrix_after_setup():
    b = RgbMatrixBackend(led_rows=16, led_cols=32)
    b.setup()
    b.brightness = 42
    assert b._matrix.brightness == 42
    assert b.brightness == 42


def test_setup_raises_actionable_error_when_rgbmatrix_unavailable(monkeypatch):
    import led_ticker.backends.rgbmatrix as mod

    monkeypatch.setattr(mod, "RGBMatrix", None)
    b = RgbMatrixBackend()
    import pytest

    with pytest.raises(RuntimeError, match="headless"):
        b.setup()


def test_build_options_maps_all_fields():
    """Comprehensive field→option parity test: verify ALL mapped fields
    land on the correct options.* attribute. Uses distinct sentinel values
    so a wrong-field typo is caught."""
    b = RgbMatrixBackend(
        led_hardware_mapping="custom-mapping",
        led_rows=24,
        led_cols=48,
        led_chain_length=7,
        led_parallel=3,
        led_row_address_type=13,
        led_multiplexing=17,
        led_pwm_bits=9,
        brightness=85,
        led_pwm_lsb_nanoseconds=200,
        led_pwm_dither_bits=3,
        led_rgb_sequence="BGR",
        led_pixel_mapper_config="Remap:custom",
        led_panel_type="FM6126A",
        led_gpio_slowdown=5,
        led_show_refresh_rate=True,
        led_disable_hardware_pulsing=True,
        led_rp1_pio=2,
        led_limit_refresh_rate_hz=120,
    )
    opts = build_options(b)

    # Verify all mapped fields (led_scan_mode is intentionally NOT mapped).
    assert opts.hardware_mapping == "custom-mapping"
    assert opts.rows == 24
    assert opts.cols == 48
    assert opts.chain_length == 7
    assert opts.parallel == 3
    assert opts.row_address_type == 13
    assert opts.multiplexing == 17
    assert opts.pwm_bits == 9
    assert opts.brightness == 85
    assert opts.pwm_lsb_nanoseconds == 200
    if hasattr(opts, "pwm_dither_bits"):
        assert opts.pwm_dither_bits == 3  # type: ignore[attr-defined]
    assert opts.led_rgb_sequence == "BGR"
    assert opts.pixel_mapper_config == "Remap:custom"
    assert opts.panel_type == "FM6126A"
    assert opts.gpio_slowdown == 5
    assert opts.show_refresh_rate == 1
    assert opts.disable_hardware_pulsing is True
    if hasattr(opts, "rp1_pio"):
        assert opts.rp1_pio == 2  # type: ignore[attr-defined]
    if hasattr(opts, "limit_refresh_rate_hz"):
        assert opts.limit_refresh_rate_hz == 120  # type: ignore[attr-defined]
