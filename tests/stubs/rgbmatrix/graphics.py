"""Test stub for rgbmatrix.graphics — re-exports the canonical bundled stub.

The Color/Font/DrawText classes are general-purpose pure-Python
implementations and live in `led_ticker._rgbmatrix_stub` so they're
also available without `PYTHONPATH=tests/stubs` (e.g., for
`led-ticker validate`). This file just makes them importable as
`rgbmatrix.graphics.*` to satisfy `from rgbmatrix import graphics`.
"""

from led_ticker._rgbmatrix_stub import Color, DrawText, Font

__all__ = ["Color", "DrawText", "Font"]
