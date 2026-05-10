"""Canvas-snapshot wrapper around RGBMatrix.SwapOnVSync.

The renderer drives the existing ticker engine and intercepts each
canvas swap to capture pixel data. We avoid modifying engine code by
wrapping the matrix object the engine talks to.
"""

from __future__ import annotations

import time
from typing import Any

from PIL import Image


def snapshot_to_image(canvas: Any) -> Image.Image:
    """Copy a stub canvas's pixel grid into a fresh RGB PIL Image.

    Reads from the test stub's `_pixels` dict directly. The dict is
    keyed by `(x, y)` and stores `(r, g, b)` tuples. Unset pixels
    default to black.
    """
    width = canvas.width
    height = canvas.height
    img = Image.new("RGB", (width, height), (0, 0, 0))
    pixels = canvas._pixels  # stub-only; intentional coupling
    for (x, y), rgb in pixels.items():
        if 0 <= x < width and 0 <= y < height:
            img.putpixel((x, y), rgb)
    return img


class RecordingMatrix:
    """Wraps an RGBMatrix and captures each SwapOnVSync.

    Forwards every other attribute access to the wrapped matrix so the
    engine sees a transparent stand-in.

    Tracks a wall-clock `time.monotonic()` reading for every captured
    swap so the encoder can derive per-frame durations from the
    intervals between swaps. Without this, a static-fast-path widget
    (one swap then `await asyncio.sleep(hold)`) gets credited with a
    single 50 ms tick — the gif's metadata says 50 ms even when the
    engine intended a 4 sec hold.
    """

    def __init__(self, matrix: Any) -> None:
        self._matrix = matrix
        self.frames: list[Image.Image] = []
        self.timestamps: list[float] = []

    def SwapOnVSync(self, canvas: Any) -> Any:
        self.frames.append(snapshot_to_image(canvas))
        self.timestamps.append(time.monotonic())
        return self._matrix.SwapOnVSync(canvas)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._matrix, name)
