"""Type aliases for led-ticker.

Since rgbmatrix is a C extension with no type stubs, we define structural
Protocols to clarify intent at each use site and enable isinstance checks.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class CanvasLike(Protocol):
    """Structural interface every canvas implementation must satisfy.

    Satisfied by: the rgbmatrix real canvas, test stub _StubCanvas,
    and ScaledCanvas (which delegates to a real canvas).
    """

    width: int
    height: int

    def SetPixel(self, x: int, y: int, r: int, g: int, b: int) -> None: ...
    def Clear(self) -> None: ...
    def Fill(self, r: int, g: int, b: int) -> None: ...


# Public alias — import `Canvas` everywhere; `CanvasLike` is for isinstance checks.
Canvas = CanvasLike

# C extension objects with no stubs — remain as Any until native stubs exist.
Font = Any
Color = Any
RGBMatrix = Any
RGBMatrixOptions = Any

# Common type patterns
ColorTuple = tuple[int, int, int]
PixelData = list[tuple[int, int, int, int, int]]
DrawResult = tuple[Canvas, int]
