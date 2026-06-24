"""Production rgbmatrix backend.

Owns the RGBMatrixOptions building (moved verbatim from LedFrame, including
the version-tolerant hasattr guards) and constructs RGBMatrix in setup() —
the privilege-drop point (root -> daemon). Behavior is byte-identical to the
pre-refactor LedFrame path.
"""

import attrs

from led_ticker._compat import RGBMatrix, RGBMatrixOptions, require_matrix
from led_ticker._types import Canvas
from led_ticker.backends import register_backend

_ENGINE_FPS: int = 20  # must stay in sync with ENGINE_TICK_MS = 50 in ticker.py


@register_backend("rgbmatrix")
@attrs.define
class RgbMatrixBackend:
    """rgbmatrix hardware backend. Matrix built (and privileges dropped) in
    setup()."""

    led_rows: int = 16
    led_cols: int = 32
    led_chain_length: int = 1
    led_parallel: int = 1
    led_pwm_bits: int = 11
    led_pwm_dither_bits: int = 0
    _brightness: int = attrs.field(alias="brightness", default=100)
    led_hardware_mapping: str = "adafruit-hat"
    led_scan_mode: int = 0
    led_pwm_lsb_nanoseconds: int = 130
    led_show_refresh_rate: bool = False
    led_gpio_slowdown: int = 1
    led_disable_hardware_pulsing: bool = False
    led_rgb_sequence: str = "RGB"
    led_pixel_mapper_config: str = ""
    led_row_address_type: int = 0
    led_multiplexing: int = 0
    led_panel_type: str = ""
    led_rp1_pio: int = 0
    led_limit_refresh_rate_hz: int = 0
    framerate_fraction: int = attrs.field(init=False, default=1)
    _matrix: object = attrs.field(init=False, default=None)

    @property
    def brightness(self) -> int:
        if self._matrix is not None:
            return self._matrix.brightness
        return self._brightness

    @brightness.setter
    def brightness(self, value: int) -> None:
        self._brightness = value
        if self._matrix is not None:
            self._matrix.brightness = value

    def setup(self) -> None:
        options = build_options(self)
        matrix_cls = require_matrix() if RGBMatrix is None else RGBMatrix
        # Constructing RGBMatrix drops root -> daemon (constraint #13).
        self._matrix = matrix_cls(options=options)
        self.framerate_fraction = (
            max(1, round(self.led_limit_refresh_rate_hz / _ENGINE_FPS))
            if self.led_limit_refresh_rate_hz
            else 1
        )

    def create_canvas(self) -> Canvas:
        return self._matrix.CreateFrameCanvas()

    def swap(self, canvas: Canvas, framerate_fraction: int = 1) -> Canvas:
        return self._matrix.SwapOnVSync(canvas, framerate_fraction)


def build_options(backend: RgbMatrixBackend) -> RGBMatrixOptions:
    """Build RGBMatrixOptions from a backend's led_* fields. Verbatim move of
    LedFrame.__attrs_post_init__'s option mapping; keep the hasattr guards —
    they tolerate older installed rgbmatrix builds."""
    options = RGBMatrixOptions()

    if backend.led_hardware_mapping is not None:
        options.hardware_mapping = backend.led_hardware_mapping

    options.rows = backend.led_rows
    options.cols = backend.led_cols
    options.chain_length = backend.led_chain_length
    options.parallel = backend.led_parallel
    options.row_address_type = backend.led_row_address_type
    options.multiplexing = backend.led_multiplexing
    options.pwm_bits = backend.led_pwm_bits
    options.brightness = backend._brightness
    options.pwm_lsb_nanoseconds = backend.led_pwm_lsb_nanoseconds
    if backend.led_pwm_dither_bits and hasattr(options, "pwm_dither_bits"):
        options.pwm_dither_bits = backend.led_pwm_dither_bits  # type: ignore[attr-defined]
    options.led_rgb_sequence = backend.led_rgb_sequence
    options.pixel_mapper_config = backend.led_pixel_mapper_config
    options.panel_type = backend.led_panel_type

    if backend.led_show_refresh_rate:
        options.show_refresh_rate = 1
    if backend.led_gpio_slowdown is not None:
        options.gpio_slowdown = backend.led_gpio_slowdown
    if backend.led_disable_hardware_pulsing:
        options.disable_hardware_pulsing = True
    # rp1_pio exposed by rgbmatrix builds from June 2026 onward.
    if backend.led_rp1_pio and hasattr(options, "rp1_pio"):
        options.rp1_pio = backend.led_rp1_pio
    if backend.led_limit_refresh_rate_hz and hasattr(options, "limit_refresh_rate_hz"):
        options.limit_refresh_rate_hz = backend.led_limit_refresh_rate_hz

    return options
