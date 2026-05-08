"""Minimal stub for rgbmatrix.graphics — used when the real library isn't installed.

Provides Color, Font, and DrawText with the same API surface as the real
rgbmatrix C extension. This lets non-drawing operations (config loading,
validation, font metric queries) work on any machine without a Pi or any
PYTHONPATH tricks.

Drawing calls (SetPixel-based) are no-ops on a None canvas; non-None canvases
get actual pixels written so test assertions still work.
"""

from __future__ import annotations

import os
import re
from typing import Any


class Color:
    def __init__(self, r: int = 0, g: int = 0, b: int = 0) -> None:
        self.red = r
        self.green = g
        self.blue = b

    def __repr__(self) -> str:
        return f"Color({self.red}, {self.green}, {self.blue})"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Color):
            return (self.red, self.green, self.blue) == (
                other.red,
                other.green,
                other.blue,
            )
        return NotImplemented

    def __hash__(self) -> int:
        return hash((self.red, self.green, self.blue))


class Font:
    def __init__(self) -> None:
        self._char_widths: dict[int, int] = {}
        self._default_width = 6
        self._bbx_height = 12

    def LoadFont(self, path: str) -> None:
        if not os.path.exists(path):
            return
        self._char_widths = {}
        current_encoding: int | None = None
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line.startswith("FONTBOUNDINGBOX "):
                    parts = line.split()
                    self._bbx_height = int(parts[2])
                elif line.startswith("ENCODING "):
                    current_encoding = int(line.split()[1])
                elif line.startswith("DWIDTH "):
                    width = int(line.split()[1])
                    if current_encoding is not None:
                        self._char_widths[current_encoding] = width
                    self._default_width = width
                elif line == "ENDCHAR":
                    current_encoding = None
        m = re.match(r"(\d+)x\d+\.bdf", os.path.basename(path))
        if m:
            self._default_width = int(m.group(1))

    def CharacterWidth(self, char_code: int) -> int:
        return self._char_widths.get(char_code, self._default_width)

    @property
    def height(self) -> int:
        return self._bbx_height


def DrawText(
    canvas: Any,
    font: Font,
    x: int,
    y: int,
    color: Color,
    text: str,
) -> int:
    width = sum(font.CharacterWidth(ord(c)) for c in text)
    if canvas is not None and hasattr(canvas, "SetPixel") and hasattr(color, "red"):
        render_y = max(0, y - 1)
        for px in range(int(x), int(x) + width):
            canvas.SetPixel(px, render_y, color.red, color.green, color.blue)
    return width
