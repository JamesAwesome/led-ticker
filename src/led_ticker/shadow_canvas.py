"""Shadow canvas for offscreen rendering and pixel compositing.

Uses a simple pixel array (no PIL required) so widgets can draw
to it and transition effects can read pixels back for blending.
"""

from __future__ import annotations

import random


class ShadowCanvas:
    """Offscreen canvas that captures widget draw output as pixels.

    Implements the same API surface as rgbmatrix FrameCanvas so
    existing widgets can draw to it unchanged via DrawText/SetPixel.
    Stores pixels in a flat array for fast access.
    """

    def __init__(self, width: int = 160, height: int = 16):
        self.width = width
        self.height = height
        self._pixels = bytearray(width * height * 3)

    def Clear(self):
        for i in range(len(self._pixels)):
            self._pixels[i] = 0

    def Fill(self, r: int, g: int, b: int):
        for i in range(0, len(self._pixels), 3):
            self._pixels[i] = r
            self._pixels[i + 1] = g
            self._pixels[i + 2] = b

    def SetPixel(self, x: int, y: int, r: int, g: int, b: int):
        if 0 <= x < self.width and 0 <= y < self.height:
            idx = (y * self.width + x) * 3
            self._pixels[idx] = r
            self._pixels[idx + 1] = g
            self._pixels[idx + 2] = b

    def get_pixel(self, x: int, y: int) -> tuple[int, int, int]:
        if 0 <= x < self.width and 0 <= y < self.height:
            idx = (y * self.width + x) * 3
            return (
                self._pixels[idx],
                self._pixels[idx + 1],
                self._pixels[idx + 2],
            )
        return (0, 0, 0)


def capture_widget(widget, width: int, height: int) -> ShadowCanvas:
    """Render a widget to a shadow canvas and return it."""
    shadow = ShadowCanvas(width, height)

    # Draw widget to shadow canvas — DrawText works because
    # our stub and the real library both return pixel width.
    # The shadow canvas captures SetPixel calls.
    widget.draw(shadow, cursor_pos=0)
    return shadow


def composite_wipe(
    old: ShadowCanvas,
    new: ShadowCanvas,
    boundary: int,
    canvas,
    direction: str = "left",
):
    """Composite two shadow canvases with a wipe at `boundary`."""
    w, h = old.width, old.height
    for y in range(h):
        for x in range(w):
            if direction == "left" and x < boundary:
                r, g, b = new.get_pixel(x, y)
            elif direction == "left":
                r, g, b = old.get_pixel(x, y)
            elif direction == "right" and x >= w - boundary:
                r, g, b = new.get_pixel(x, y)
            else:
                r, g, b = old.get_pixel(x, y)
            canvas.SetPixel(x, y, r, g, b)


def composite_dissolve(
    old: ShadowCanvas,
    new: ShadowCanvas,
    progress: float,
    canvas,
    seed: int = 42,
):
    """Composite with random pixel dissolve at given progress."""
    w, h = old.width, old.height
    total = w * h
    pixels_to_flip = int(progress * total)

    # Generate a deterministic shuffle order
    rng = random.Random(seed)
    order = list(range(total))
    rng.shuffle(order)

    # Start with old content
    for y in range(h):
        for x in range(w):
            r, g, b = old.get_pixel(x, y)
            canvas.SetPixel(x, y, r, g, b)

    # Flip pixels to new content
    for i in range(pixels_to_flip):
        idx = order[i]
        x = idx % w
        y = idx // w
        r, g, b = new.get_pixel(x, y)
        canvas.SetPixel(x, y, r, g, b)


def composite_split(
    old: ShadowCanvas,
    new: ShadowCanvas,
    progress: float,
    canvas,
):
    """Composite with center-out split reveal."""
    w, h = old.width, old.height
    half = w // 2
    reveal = int(progress * half)
    left_boundary = half - reveal
    right_boundary = half + reveal

    for y in range(h):
        for x in range(w):
            if left_boundary <= x < right_boundary:
                r, g, b = new.get_pixel(x, y)
            else:
                r, g, b = old.get_pixel(x, y)
            canvas.SetPixel(x, y, r, g, b)


def composite_curtain(
    old: ShadowCanvas,
    new: ShadowCanvas,
    progress: float,
    canvas,
):
    """Composite with curtain opening — old slides apart, new revealed."""
    w, h = old.width, old.height
    half = w // 2
    offset = int(progress * half)

    # New content as base
    for y in range(h):
        for x in range(w):
            r, g, b = new.get_pixel(x, y)
            canvas.SetPixel(x, y, r, g, b)

    # Left curtain (old content, columns 0..half-1, shifted left)
    for y in range(h):
        for src_x in range(half):
            dst_x = src_x - offset
            if 0 <= dst_x < w:
                r, g, b = old.get_pixel(src_x, y)
                canvas.SetPixel(dst_x, y, r, g, b)

    # Right curtain (old content, columns half..w-1, shifted right)
    for y in range(h):
        for src_x in range(half, w):
            dst_x = src_x + offset
            if 0 <= dst_x < w:
                r, g, b = old.get_pixel(src_x, y)
                canvas.SetPixel(dst_x, y, r, g, b)
