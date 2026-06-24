"""Compatibility shim for rgbmatrix.

Attempts to import the real rgbmatrix C library (available on Raspberry Pi).
When it isn't installed, only `graphics.*` (Color, Font, DrawText) falls back
to the bundled pure-Python `_rgbmatrix_stub` so `led-ticker validate` and other
non-drawing operations work on any machine.

`RGBMatrix` and `RGBMatrixOptions` are NOT stubbed — off-hardware they are
`None`. Display construction goes through `RgbMatrixBackend.setup()`, which
checks for `None` and raises a clear "use [display] backend = \"headless\""
error if the library is not installed.
"""

from typing import Any

try:
    from rgbmatrix import RGBMatrix, RGBMatrixOptions, graphics
except ImportError:
    from led_ticker import _rgbmatrix_stub as graphics  # type: ignore[assignment]

    RGBMatrix = None  # type: ignore[assignment]
    RGBMatrixOptions = None  # type: ignore[assignment]


def require_graphics() -> Any:
    """Return the graphics module (real rgbmatrix or bundled stub)."""
    return graphics
