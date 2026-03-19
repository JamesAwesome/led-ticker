"""Stub rgbmatrix.graphics module for testing without hardware.

Parses real BDF font files to provide accurate CharacterWidth values.
"""

import os
import re


class Color:
    """Stub for graphics.Color."""

    def __init__(self, r=0, g=0, b=0):
        self.red = r
        self.green = g
        self.blue = b

    def __repr__(self):
        return f"Color({self.red}, {self.green}, {self.blue})"

    def __eq__(self, other):
        if isinstance(other, Color):
            return (self.red, self.green, self.blue) == (
                other.red, other.green, other.blue,
            )
        return NotImplemented

    def __hash__(self):
        return hash((self.red, self.green, self.blue))


class Font:
    """Stub for graphics.Font that parses BDF files for accurate widths."""

    def __init__(self):
        self._char_widths = {}
        self._default_width = 6

    def LoadFont(self, path):
        """Parse a BDF font file to extract character widths."""
        if not os.path.exists(path):
            return

        self._char_widths = {}
        current_encoding = None

        with open(path) as f:
            for line in f:
                line = line.strip()
                if line.startswith("ENCODING "):
                    current_encoding = int(line.split()[1])
                elif line.startswith("DWIDTH "):
                    width = int(line.split()[1])
                    if current_encoding is not None:
                        self._char_widths[current_encoding] = width
                    self._default_width = width
                elif line == "ENDCHAR":
                    current_encoding = None

        # Extract default width from font name if available
        basename = os.path.basename(path)
        match = re.match(r"(\d+)x\d+\.bdf", basename)
        if match:
            self._default_width = int(match.group(1))

    def CharacterWidth(self, char_code):
        """Return the width of a character by its code point."""
        return self._char_widths.get(char_code, self._default_width)


def DrawText(canvas, font, x, y, color, text):
    """Stub for graphics.DrawText. Returns the pixel width of the drawn text."""
    width = sum(font.CharacterWidth(ord(c)) for c in text)
    return width
