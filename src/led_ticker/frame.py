"""LED matrix frame wrapper."""

from collections.abc import Callable

import attrs

from led_ticker import status_board
from led_ticker._compat import RGBMatrix, RGBMatrixOptions
from led_ticker._types import Canvas
from led_ticker._types import RGBMatrix as RGBMatrixType

_ENGINE_FPS: int = 20  # must stay in sync with ENGINE_TICK_MS = 50 in ticker.py


@attrs.define
class LedFrame:
    """Hardware abstraction for an LED rgbmatrix panel."""

    led_rows: int = 16
    led_cols: int = 32
    led_chain_length: int = 1
    led_parallel: int = 1
    led_pwm_bits: int = 11
    led_pwm_dither_bits: int = 0
    led_brightness: int = 100
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
    # Pi 5 (kingdo9 fork) only: 0 = PIO mode (low CPU), 1 = RP1 RIO mode
    # (higher CPU, higher refresh). Ignored on Pi 4 builds.
    led_rp1_rio: int = 0
    # Cap hardware refresh rate in Hz (0 = unlimited). Useful for making
    # SwapOnVSync timing more predictable relative to the scan cycle on
    # long chains where the uncapped rate causes visible motion artifacts.
    led_limit_refresh_rate_hz: int = 0
    overlay_hooks: list[Callable[[Canvas], None]] = attrs.field(factory=list)
    _framerate_fraction: int = attrs.field(init=False)
    matrix: RGBMatrixType = attrs.field(init=False)

    def __attrs_post_init__(self) -> None:
        options = RGBMatrixOptions()

        if self.led_hardware_mapping is not None:
            options.hardware_mapping = self.led_hardware_mapping

        options.rows = self.led_rows
        options.cols = self.led_cols
        options.chain_length = self.led_chain_length
        options.parallel = self.led_parallel
        options.row_address_type = self.led_row_address_type
        options.multiplexing = self.led_multiplexing
        options.pwm_bits = self.led_pwm_bits
        options.brightness = self.led_brightness
        options.pwm_lsb_nanoseconds = self.led_pwm_lsb_nanoseconds
        if self.led_pwm_dither_bits and hasattr(options, "pwm_dither_bits"):
            options.pwm_dither_bits = self.led_pwm_dither_bits  # type: ignore[attr-defined]
        options.led_rgb_sequence = self.led_rgb_sequence
        options.pixel_mapper_config = self.led_pixel_mapper_config
        options.panel_type = self.led_panel_type

        if self.led_show_refresh_rate:
            options.show_refresh_rate = 1

        if self.led_gpio_slowdown is not None:
            options.gpio_slowdown = self.led_gpio_slowdown

        if self.led_disable_hardware_pulsing:
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

        Single centralized swap point. Each registered overlay hook paints
        on the real canvas (physical pixels) immediately before the hardware
        swap, so overlays composite over every render path (engine,
        transitions, play()-style widgets) that routes through here. The
        framerate_fraction argument pins SwapOnVSync to a fixed scan-cycle
        position, eliminating seam tearing on long chains.

        Hooks must be paint-only and not raise: an exception here skips the
        swap and freezes the panel (no per-hook try/except by design — see
        the Overlay-hooks invariant in CLAUDE.md).
        """
        for hook in self.overlay_hooks:
            hook(canvas)
        # Liveness breadcrumb for the web status UI: an int increment
        # (no-op without an active board, no I/O, cannot raise) — the one
        # deliberate exception to LedFrame staying mechanism-only, because
        # this is the single point every render path crosses.
        status_board.record_swap()
        return self.matrix.SwapOnVSync(canvas, self._framerate_fraction)
