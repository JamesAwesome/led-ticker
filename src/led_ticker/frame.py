"""LED matrix frame wrapper."""

from __future__ import annotations

import attrs

from led_ticker._compat import RGBMatrix, RGBMatrixOptions
from led_ticker._types import Canvas
from led_ticker._types import RGBMatrix as RGBMatrixType

_ENGINE_FPS: int = 20  # must stay in sync with ENGINE_TICK_MS = 50 in ticker.py


@attrs.define
class LedFrame:
    """Hardware abstraction for an LED rgbmatrix panel."""

    led_rows: int = 32
    led_cols: int = 64
    led_chain: int = 1
    led_parallel: int = 1
    led_pwm_bits: int = 11
    led_pwm_dither_bits: int = 0
    led_brightness: int = 100
    led_gpio_mapping: str = "adafruit-hat"
    led_scan_mode: int = 1
    led_pwm_lsb_nanoseconds: int = 130
    led_show_refresh: bool = False
    led_slowdown_gpio: int = 1
    led_no_hardware_pulse: bool = False
    led_rgb_sequence: str = "RGB"
    led_pixel_mapper: str = ""
    led_row_addr_type: int = 0
    led_multiplexing: int = 0
    led_panel_type: str = ""
    # Pi 5 (kingdo9 fork) only: 0 = PIO mode (low CPU), 1 = RP1 RIO mode
    # (higher CPU, higher refresh). Ignored on Pi 4 builds.
    led_rp1_rio: int = 0
    # Cap hardware refresh rate in Hz (0 = unlimited). Useful for making
    # SwapOnVSync timing more predictable relative to the scan cycle on
    # long chains where the uncapped rate causes visible motion artifacts.
    led_limit_refresh_rate_hz: int = 0
    _framerate_fraction: int = attrs.field(init=False)
    matrix: RGBMatrixType = attrs.field(init=False)

    def __attrs_post_init__(self) -> None:
        options = RGBMatrixOptions()

        if self.led_gpio_mapping is not None:
            options.hardware_mapping = self.led_gpio_mapping

        options.rows = self.led_rows
        options.cols = self.led_cols
        options.chain_length = self.led_chain
        options.parallel = self.led_parallel
        options.row_address_type = self.led_row_addr_type
        options.multiplexing = self.led_multiplexing
        options.pwm_bits = self.led_pwm_bits
        options.brightness = self.led_brightness
        options.pwm_lsb_nanoseconds = self.led_pwm_lsb_nanoseconds
        if self.led_pwm_dither_bits and hasattr(options, "pwm_dither_bits"):
            options.pwm_dither_bits = self.led_pwm_dither_bits  # type: ignore[attr-defined]
        options.led_rgb_sequence = self.led_rgb_sequence
        options.pixel_mapper_config = self.led_pixel_mapper
        options.panel_type = self.led_panel_type

        if self.led_show_refresh:
            options.show_refresh_rate = 1

        if self.led_slowdown_gpio is not None:
            options.gpio_slowdown = self.led_slowdown_gpio

        if self.led_no_hardware_pulse:
            options.disable_hardware_pulsing = True

        # rp1_rio is exposed only by the kingdo9 Pi 5 fork; tolerate older
        # builds where the Python binding doesn't have it.
        if self.led_rp1_rio and hasattr(options, "rp1_rio"):
            options.rp1_rio = self.led_rp1_rio

        if self.led_limit_refresh_rate_hz and hasattr(options, "limit_refresh_rate_hz"):
            options.limit_refresh_rate_hz = self.led_limit_refresh_rate_hz

        self.matrix = RGBMatrix(options=options)
        self._framerate_fraction = (
            max(1, round(self.led_limit_refresh_rate_hz / _ENGINE_FPS))
            if self.led_limit_refresh_rate_hz
            else 1
        )

    def get_clean_canvas(self) -> Canvas:
        """Get a clean canvas ready for rendering."""
        canvas = self.matrix.CreateFrameCanvas()
        canvas.Clear()
        return canvas

    def swap(self, canvas: Canvas) -> Canvas:
        """Swap the back-buffer to the display.

        Single centralized swap point. The framerate_fraction argument
        makes SwapOnVSync land at a fixed position in the hardware scan
        cycle, eliminating the scan-seam tearing visible on long chains.
        Future overlay_hooks will iterate here before the swap.
        """
        return self.matrix.SwapOnVSync(canvas, self._framerate_fraction)
