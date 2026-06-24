"""Type aliases for led-ticker.

Since rgbmatrix is a C extension with no type stubs, we define structural
Protocols to clarify intent at each use site and enable isinstance checks.
"""

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class CanvasLike(Protocol):
    """Structural interface every canvas implementation must satisfy.

    Satisfied by: the rgbmatrix real canvas, test stub _StubCanvas,
    and ScaledCanvas (which delegates to a real canvas).

    Use for isinstance checks only. Type annotations should use Canvas (= Any)
    to remain compatible with call sites that access rgbmatrix-specific attrs.
    """

    width: int
    height: int

    def SetPixel(self, x: int, y: int, r: int, g: int, b: int) -> None: ...
    def Clear(self) -> None: ...
    def Fill(self, r: int, g: int, b: int) -> None: ...
    def SubFill(
        self, x: int, y: int, width: int, height: int, r: int, g: int, b: int
    ) -> None: ...
    def SetImage(self, image: object, offset_x: int = 0, offset_y: int = 0) -> None: ...


# Public alias — use Canvas in annotations throughout; CanvasLike for isinstance checks.
Canvas = Any

# C extension objects with no stubs — remain as Any until native stubs exist.
Font = Any
Color = Any
RGBMatrix = Any
RGBMatrixOptions = Any

# Common type patterns
ColorTuple = tuple[int, int, int]
PixelData = list[tuple[int, int, int, int, int]]
DrawResult = tuple[Canvas, int]
