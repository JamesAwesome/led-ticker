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
    """Stub canvas with pixel storage for testing."""

    def __init__(self, width=160, height=16):
        self.width = width
        self.height = height
        self._pixels = {}  # (x, y) -> (r, g, b)

    def Clear(self):
        self._pixels.clear()

    def Fill(self, r, g, b):
        for y in range(self.height):
            for x in range(self.width):
                self._pixels[(x, y)] = (r, g, b)

    def SetPixel(self, x, y, r, g, b):
        if 0 <= x < self.width and 0 <= y < self.height:
            self._pixels[(x, y)] = (r, g, b)

    # Test-only helpers
    def get_pixel(self, x, y):
        """Get pixel color at (x, y). Returns (0, 0, 0) if unset."""
        return self._pixels.get((x, y), (0, 0, 0))

    def count_nonzero(self):
        """Count pixels that are not black."""
        return sum(1 for v in self._pixels.values() if v != (0, 0, 0))


class RGBMatrix:
    """Stub for rgbmatrix.RGBMatrix."""

    def __init__(self, options=None):
        self._options = options
        cols = getattr(options, "cols", 64) if options else 64
        chain = getattr(options, "chain_length", 1) if options else 1
        rows = getattr(options, "rows", 32) if options else 32
        self._width = cols * chain
        self._height = rows

    def CreateFrameCanvas(self):
        return _StubCanvas(width=self._width, height=self._height)

    def SwapOnVSync(self, canvas):
        return canvas
