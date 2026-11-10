"""Per-pixel brightness proxy for animated text (``AnimationFrame.pixel_gain``).

``with_pixel_gain(canvas, gain)`` returns a canvas whose lit pixels are
scaled by ``gain(x, y)`` (real-pixel coords, clamped to ``[0, 1]``).

The proxy sits at the BOTTOM of the wrapper chain so both paint routes hit
it: the block-expanding path (``ScaledCanvas.SetPixel`` -> ``real.SubFill``)
and the hi-res path (``unwrap_to_real(canvas).SetPixel``). ``SubFill`` is
sampled ONCE per block (top-left), so a BDF logical pixel twinkles as a
unit; hi-res glyphs twinkle per real pixel.

Known limit: inline ANIMATED image emoji paint via ``SetImage`` and are not
gained; static sprites are.

Rebuild per draw — the canvas changes every swap, never cache the proxy.
"""

from collections.abc import Callable
from typing import Any

from led_ticker.scaled_canvas import ScaledCanvas


def _clamp(g: float) -> float:
    return 0.0 if g < 0.0 else 1.0 if g > 1.0 else g


class GainCanvas:
    """Wraps a real canvas; scales colour on ``SetPixel`` / ``SubFill``."""

    __slots__ = ("_gain", "real")

    def __init__(self, real: Any, gain: Callable[[int, int], float]) -> None:
        self.real = real
        self._gain = gain

    def SetPixel(self, x: int, y: int, r: int, g: int, b: int) -> None:
        k = _clamp(self._gain(x, y))
        rr, gg, bb = round(r * k), round(g * k), round(b * k)
        if not (rr or gg or bb):
            return  # fully dimmed: transparent, never punch a black hole
        self.real.SetPixel(x, y, rr, gg, bb)

    def SubFill(
        self, x: int, y: int, width: int, height: int, r: int, g: int, b: int
    ) -> None:
        k = _clamp(self._gain(x, y))
        rr, gg, bb = round(r * k), round(g * k), round(b * k)
        if not (rr or gg or bb):
            return
        self.real.SubFill(x, y, width, height, rr, gg, bb)

    def __getattr__(self, name: str) -> Any:
        return getattr(self.real, name)


def with_pixel_gain(canvas: Any, gain: Callable[[int, int], float]) -> Any:
    """Return ``canvas`` rebuilt over a :class:`GainCanvas` (caller's wrappers
    are never mutated)."""
    layers: list[ScaledCanvas] = []
    cur = canvas
    while isinstance(cur, ScaledCanvas):
        layers.append(cur)
        cur = cur.real
    out: Any = GainCanvas(cur, gain)
    for layer in reversed(layers):
        out = ScaledCanvas(out, scale=layer.scale, content_height=layer.content_height)
    return out
