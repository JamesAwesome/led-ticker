"""Compatibility shim for rgbmatrix.

Attempts to import the real rgbmatrix C library (available on Raspberry Pi).
Falls back to a bundled pure-Python stub of `graphics.*` (Color, Font,
DrawText) when it isn't installed, so `led-ticker validate` and other
non-drawing operations work on any machine without PYTHONPATH tricks.

`RGBMatrix` and `RGBMatrixOptions` are NOT stubbed — running the actual
display requires real hardware. `require_matrix()` raises a clear error
if you try to construct a matrix without rgbmatrix installed.
"""

from __future__ import annotations

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


def require_matrix() -> Any:
    """Return the RGBMatrix class. Raises if rgbmatrix is not installed.

    Use this when actually constructing the display — graphics-only
    operations (Color, Font, DrawText) should use `require_graphics()`
    instead, which always returns something usable.
    """
    if RGBMatrix is None:
        raise RuntimeError(
            "rgbmatrix hardware library not installed. "
            "Run on a Raspberry Pi with the LED matrix library, "
            "or use `PYTHONPATH=tests/stubs` for test fixtures."
        )
    return RGBMatrix
