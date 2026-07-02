"""Pixel-space rotation engine for rotation-emitting animations.

Resolution-agnostic BY CONTRACT: nothing here knows about logical vs
physical pixels or ScaledCanvas — the physical-resolution follow-up
(propeller spec) reuses this module unchanged at real-pixel dims.

PixelBuffer is an OWNED raster: reading it back is fine (hardware
constraint #3 forbids GetPixel on real canvases, not on our objects).
"""

import math


class PixelBuffer:
    """Minimal readable raster with real-canvas SetPixel semantics
    (out-of-bounds writes are silently ignored)."""

    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self._pixels: list[tuple[int, int, int] | None] = [None] * (width * height)

    def SetPixel(self, x: int, y: int, r: int, g: int, b: int) -> None:  # noqa: N802 - canvas API
        if 0 <= x < self.width and 0 <= y < self.height:
            self._pixels[y * self.width + x] = (r, g, b)

    def SubFill(  # noqa: N802 - canvas API
        self, x: int, y: int, w: int, h: int, r: int, g: int, b: int
    ) -> None:
        """Fill the (clamped) w×h block at (x, y). Out-of-bounds portions
        are silently ignored — same semantics as SetPixel. Required by
        ScaledCanvas, whose SetPixel/SubFill write through real.SubFill."""
        x0 = max(0, x)
        y0 = max(0, y)
        x1 = min(self.width, x + w)
        y1 = min(self.height, y + h)
        pixel = (r, g, b)
        for yy in range(y0, y1):
            row = yy * self.width
            for xx in range(x0, x1):
                self._pixels[row + xx] = pixel

    def clear(self) -> None:
        """Reset every slot to None (transparent). The per-frame reset for
        construct-once rotation surfaces.

        Rebind-not-loop, adjudicated by the antagonist plan review: one
        C-level list construction per frame beats 16K interpreted stores;
        nothing else holds the list (the wrapper holds the BUFFER object;
        rotate_blit reads via get()). The Task-5 benchmark times clear()
        as part of the frame unit and re-adjudicates if it ever matters."""
        self._pixels = [None] * (self.width * self.height)

    def get(self, x: int, y: int) -> tuple[int, int, int] | None:
        """The pixel at (x, y), or None when unset (= transparent)."""
        if 0 <= x < self.width and 0 <= y < self.height:
            return self._pixels[y * self.width + x]
        return None


def rotate_blit(
    dst: object, src: PixelBuffer, angle_deg: float, cx: float, cy: float
) -> None:
    """Paint `src` onto `dst` rotated `angle_deg` clockwise about (cx, cy).

    Inverse-mapped nearest-neighbor: for each dst pixel, sample src at
    R(-angle) — hole-free at every angle (a forward map leaves ~30% gaps
    at 45 deg). Unset src pixels are transparent (never painted), so the
    dst background survives outside the rotated content.

    `dst` is anything with SetPixel (real canvas, ScaledCanvas, another
    buffer). Callers gate the `angle % 360 == 0` no-op; this function
    always blits.

    Sign convention: clockwise-positive in screen coordinates (y grows
    DOWN). Forward map: (dx·cos − dy·sin, dx·sin + dy·cos). Inverse
    (transpose, applied per dst pixel): sx = cx + dx·cos + dy·sin,
    sy = cy − dx·sin + dy·cos.
    """
    theta = math.radians(angle_deg)
    cos_t = math.cos(theta)
    sin_t = math.sin(theta)

    # Conservative dst scan region: axis-aligned bounds of the src rect's
    # four rotated corners, clamped to dst dims.
    corners = [(0.0, 0.0), (src.width, 0.0), (0.0, src.height), (src.width, src.height)]
    xs: list[float] = []
    ys: list[float] = []
    for px, py in corners:
        dx, dy = px - cx, py - cy
        xs.append(cx + dx * cos_t - dy * sin_t)
        ys.append(cy + dx * sin_t + dy * cos_t)
    dst_w: int = getattr(dst, "width", src.width)
    dst_h: int = getattr(dst, "height", src.height)
    x0 = max(0, math.floor(min(xs)))
    x1 = min(dst_w - 1, math.ceil(max(xs)))
    y0 = max(0, math.floor(min(ys)))
    y1 = min(dst_h - 1, math.ceil(max(ys)))

    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            # Inverse map: where in src does this dst pixel come from?
            dx = x - cx
            dy = y - cy
            sx = cx + dx * cos_t + dy * sin_t
            sy = cy - dx * sin_t + dy * cos_t
            pixel = src.get(round(sx), round(sy))
            if pixel is not None:
                dst.SetPixel(x, y, *pixel)  # type: ignore[attr-defined]
