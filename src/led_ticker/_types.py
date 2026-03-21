"""Type aliases for led-ticker.

Since rgbmatrix is a C extension with no type stubs, we use
type aliases to clarify intent at each use site.
"""

from __future__ import annotations

from typing import Any

# C extension objects (no stubs available)
Canvas = Any
Font = Any
Color = Any
RGBMatrix = Any
RGBMatrixOptions = Any

# Common type patterns
ColorTuple = tuple[int, int, int]
PixelData = list[tuple[int, int, int, int, int]]
DrawResult = tuple[Canvas, int]
