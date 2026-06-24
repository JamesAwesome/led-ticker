"""Stub rgbmatrix package for testing without hardware.

Mirrors the kingdo9 Pi 5 fork's Python bindings closely enough to run
the test suite without a panel. Where the stub diverges from the real
C extension, those gaps are CALLED OUT here so future hardware-only
bugs can be triaged faster:

KNOWN STUB-vs-REAL DIVERGENCES (with rationale):
  - `graphics.Font.height` is exposed as a `@property` here matching
    the real C extension's int attribute. Older versions of this stub
    had it as a method (`font.height()`); production code now reads
    via `font_line_height(font)` which tolerates either shape, but
    new code should treat `Font.height` as an int attribute.
  - `Font.descent` is NOT exposed by the real C extension. Code reading
    descent must go through `get_bdf_for(font).descent` (parsed from
    the BDF file at load time and cached alongside the C font).
  - The stub `RGBMatrix` only honors `pixel_mapper_config="U-mapper"`
    (folds chain in half: doubles height, halves width) — it doesn't
    parse arbitrary `Remap:...` strings the way the real lib does.
    Tests that need the bigsign's vertical-serpentine 2×4 layout pass
    `pixel_mapper_config="U-mapper"` to get a 256×64 canvas.
  - `RGBMatrix.show_refresh_rate` is a config-only flag here; the real
    lib's stderr Hz output is not simulated. The startup explainer log
    (`app.build_frame_from_config` when `show_refresh_rate=true`) makes the
    behaviour visible to users either way.
  - `RGBMatrix.SwapOnVSync` returns the SAME canvas object in this
    stub by default. Test fixtures that need to verify capture-the-
    return semantics use `swapping_frame` (`tests/conftest.py`) which
    rotates between two canvas objects so dropped-capture bugs surface.
"""

from rgbmatrix import graphics  # noqa: F401


def _get_stub_canvas_cls():
    """Lazy import to break the circular-init chain.

    tests/stubs/rgbmatrix is loaded early during pytest collection.
    A top-level ``from led_ticker.backends.headless import …`` triggers
    ``led_ticker.backends.__init__``, which in turn imports
    ``led_ticker.backends.rgbmatrix``, which imports ``led_ticker._compat``,
    which does ``from rgbmatrix import …`` — but *this* module is still
    mid-load, so Python returns the partially-initialized stub and
    ``RGBMatrixOptions`` comes back as ``None``.  Deferring the import to
    first call (after the stub is fully initialised) breaks that cycle.
    """
    from led_ticker.backends.headless import HeadlessCanvas  # noqa: PLC0415

    return HeadlessCanvas


# Public alias kept for any ``from rgbmatrix import _StubCanvas`` callers.
class _StubCanvas:  # noqa: N801
    """Thin proxy: resolves to HeadlessCanvas on first instantiation."""

    def __new__(cls, width=160, height=16):
        return _get_stub_canvas_cls()(width=width, height=height)


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
        # Pi 5 knob (rgbmatrix builds from June 2026 onward) — present
        # here so tests exercise the rp1_pio code path.
        self.rp1_pio = 0
        self.limit_refresh_rate_hz = 0


class RGBMatrix:
    """Stub for rgbmatrix.RGBMatrix."""

    def __init__(self, options=None):
        self._options = options
        cols = getattr(options, "cols", 64) if options else 64
        chain = getattr(options, "chain_length", 1) if options else 1
        rows = getattr(options, "rows", 32) if options else 32
        parallel = getattr(options, "parallel", 1) if options else 1
        mapper = getattr(options, "pixel_mapper_config", "") if options else ""

        width = cols * chain
        height = rows * parallel

        if mapper == "U-mapper":
            # U-mapper folds the chain in half: doubles height, halves width.
            assert chain % 2 == 0, "U-mapper requires an even chain length"
            width = (cols * chain) // 2
            height = rows * 2 * parallel

        self._width = width
        self._height = height
        self._back_buffer = None

    def CreateFrameCanvas(self):
        return _StubCanvas(width=self._width, height=self._height)

    def SwapOnVSync(self, canvas, framerate_fraction=1):
        """Simulate double-buffering: return the previous back buffer."""
        if self._back_buffer is None:
            self._back_buffer = _StubCanvas(
                width=self._width,
                height=self._height,
            )
        old_back = self._back_buffer
        self._back_buffer = canvas
        return old_back
