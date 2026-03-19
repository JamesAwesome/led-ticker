"""Stub rgbmatrix package for testing without hardware."""

from rgbmatrix import graphics  # noqa: F401


class RGBMatrixOptions:
    """Stub for rgbmatrix.RGBMatrixOptions."""

    def __init__(self):
        self.hardware_mapping = ""
        self.rows = 32
        self.cols = 64
        self.chain_length = 1
        self.parallel = 1
        self.row_address_type = 0
        self.multiplexing = 0
        self.pwm_bits = 11
        self.brightness = 100
        self.pwm_lsb_nanoseconds = 130
        self.led_rgb_sequence = "RGB"
        self.pixel_mapper_config = ""
        self.panel_type = ""
        self.show_refresh_rate = 0
        self.gpio_slowdown = 1
        self.disable_hardware_pulsing = False


class _StubCanvas:
    """Stub canvas returned by RGBMatrix."""

    def __init__(self, width=160):
        self.width = width

    def Clear(self):
        pass


class RGBMatrix:
    """Stub for rgbmatrix.RGBMatrix."""

    def __init__(self, options=None):
        self._options = options
        cols = getattr(options, "cols", 64) if options else 64
        chain = getattr(options, "chain_length", 1) if options else 1
        self._width = cols * chain

    def CreateFrameCanvas(self):
        return _StubCanvas(width=self._width)

    def SwapOnVSync(self, canvas):
        return canvas
