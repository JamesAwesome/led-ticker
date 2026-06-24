"""Compatibility shim for rgbmatrix.

Attempts to import the real rgbmatrix C library (available on Raspberry Pi).
Falls back to a bundled pure-Python stub of `graphics.*` (Color, Font,
DrawText) when it isn't installed, so `led-ticker validate` and other
non-drawing operations work on any machine without PYTHONPATH tricks.

`RGBMatrix` and `RGBMatrixOptions` are NOT stubbed — display construction
goes through `RgbMatrixBackend.setup()`, which raises a clear error if the
library is not installed.
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
