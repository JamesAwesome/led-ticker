"""Headless software backend — runs the full engine with no hardware.

Promoted from the former `tests/stubs/rgbmatrix/` test stub. Shipped and
runtime-selectable via `[display] backend = "headless"`. Provides a software
canvas implementing the full Canvas contract and a double-buffered `swap()`
that returns a DIFFERENT canvas object each call (constraints #1/#8), so
dropped-capture bugs surface here exactly as on hardware.
"""

from typing import Any

from led_ticker.backends import register_backend


class HeadlessCanvas:
    """Software canvas with pixel storage. Satisfies the Canvas contract:
    SetPixel / Clear / Fill / SubFill / SetImage, plus test-only get_pixel /
    count_nonzero helpers."""

    def __init__(self, width: int = 160, height: int = 16) -> None:
        self.width = width
        self.height = height
        self._pixels: dict[tuple[int, int], tuple[int, int, int]] = {}

    def Clear(self) -> None:
        self._pixels.clear()

    def Fill(self, r: int, g: int, b: int) -> None:
        for y in range(self.height):
            for x in range(self.width):
                self._pixels[(x, y)] = (r, g, b)

    def SetPixel(self, x: int, y: int, r: int, g: int, b: int) -> None:
        if 0 <= x < self.width and 0 <= y < self.height:
            self._pixels[(x, y)] = (r, g, b)

    def SubFill(
        self, x: int, y: int, width: int, height: int, red: int, green: int, blue: int
    ) -> None:
        for dy in range(height):
            for dx in range(width):
                self.SetPixel(x + dx, y + dy, red, green, blue)

    def SetImage(self, image: Any, offset_x: int = 0, offset_y: int = 0) -> None:
        """Walk a PIL image and SetPixel each pixel. The real C lib pushes RGB
        bytes in one call; fidelity (not speed) is the job here. Alpha==0
        flattens onto black, matching the production SetImage path."""
        pixels = image.load()
        w, h = image.size
        for y in range(h):
            for x in range(w):
                px = pixels[x, y]
                if len(px) == 4 and px[3] == 0:
                    r, g, b = 0, 0, 0
                else:
                    r, g, b = px[0], px[1], px[2]
                self.SetPixel(offset_x + x, offset_y + y, r, g, b)

    # Read accessors (not part of the Canvas contract). get_pixel is the
    # supported way a backend serializes its OWN canvas's accumulated pixels
    # (constraint #3 bans Canvas GetPixel for the engine, not a backend reading
    # the canvas it created); count_nonzero is test-only.
    def get_pixel(self, x: int, y: int) -> tuple[int, int, int]:
        return self._pixels.get((x, y), (0, 0, 0))

    def count_nonzero(self) -> int:
        return sum(1 for v in self._pixels.values() if v != (0, 0, 0))


@register_backend("headless")
class HeadlessBackend:
    """Software backend. No privilege drop; no hardware output."""

    def __init__(
        self, width: int, height: int, *, pixel_mapper_config: str = ""
    ) -> None:
        if pixel_mapper_config == "U-mapper":
            # U-mapper folds the chain in half: doubles height, halves width.
            assert width % 2 == 0, "U-mapper requires an even effective width"
            width, height = width // 2, height * 2
        self._width = width
        self._height = height
        self.brightness = 100
        self._back_buffer: HeadlessCanvas | None = None

    def setup(self) -> None:
        # No matrix to build, no privileges to drop.
        return None

    def create_canvas(self) -> HeadlessCanvas:
        return HeadlessCanvas(width=self._width, height=self._height)

    def swap(self, canvas: HeadlessCanvas) -> HeadlessCanvas:
        if self._back_buffer is None:
            self._back_buffer = HeadlessCanvas(width=self._width, height=self._height)
        old_back = self._back_buffer
        self._back_buffer = canvas
        return old_back
