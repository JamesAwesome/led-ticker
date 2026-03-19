"""Compatibility shim for rgbmatrix.

Attempts to import the real rgbmatrix C library (available on Raspberry Pi).
Falls back to a stub that provides the same API surface for development and
testing on non-Pi machines.
"""

try:
    from rgbmatrix import RGBMatrix, RGBMatrixOptions, graphics
except ImportError:
    graphics = None
    RGBMatrix = None
    RGBMatrixOptions = None


def require_graphics():
    """Raise a clear error if rgbmatrix is not available."""
    if graphics is None:
        raise RuntimeError(
            "rgbmatrix is not installed. Install it on a Raspberry Pi or "
            "use the test stubs (PYTHONPATH=tests/stubs)."
        )
    return graphics
