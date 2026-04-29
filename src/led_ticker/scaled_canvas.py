"""Scaled-canvas wrapper for the bigsign rendering path.

Wraps a real `RGBMatrix` canvas. Callers always work in a 16-tall logical
canvas; the wrapper paints `scale × scale` blocks and vertically centers
the logical canvas inside the real canvas.

Used only when `scale > 1`. At `scale = 1` the existing sign uses the real
canvas directly without a wrapper.
"""

from __future__ import annotations

from typing import Any

import attrs

CONTENT_HEIGHT = 16


@attrs.define
class ScaledCanvas:
    """Wraps a real canvas; exposes a `content_height`-tall logical canvas."""

    real: Any
    scale: int = 1
    content_height: int = CONTENT_HEIGHT

    @property
    def width(self) -> int:
        return self.real.width // self.scale

    @property
    def height(self) -> int:
        return self.content_height

    @property
    def _y_offset(self) -> int:
        return (self.real.height - self.content_height * self.scale) // 2

    def Clear(self) -> None:
        self.real.Clear()

    def SetPixel(self, x: int, y: int, r: int, g: int, b: int) -> None:
        rx = x * self.scale
        ry = y * self.scale + self._y_offset
        for dy in range(self.scale):
            for dx in range(self.scale):
                self.real.SetPixel(rx + dx, ry + dy, r, g, b)
