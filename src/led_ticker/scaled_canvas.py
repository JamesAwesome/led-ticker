"""Scaled-canvas wrapper for the bigsign rendering path.

Wraps a real `RGBMatrix` canvas. Callers always work in a 16-tall logical
canvas; the wrapper paints `scale × scale` blocks and vertically centers
the logical canvas inside the real canvas.

Used only when `scale > 1`. At `scale = 1` the existing sign uses the real
canvas directly without a wrapper.
"""

from collections.abc import Callable
from typing import Any, TypeGuard

import attrs

CONTENT_HEIGHT = 16


@attrs.define
class ScaledCanvas:
    """Wraps a real canvas; exposes a `content_height`-tall logical canvas.

    `real` is mutable so `_swap()` in ticker.py can rewire the wrapper to
    point at the new back-buffer canvas after each `SwapOnVSync`. Within
    a Ticker session every back buffer comes from the same RGBMatrix so
    its dimensions are constant — we cache `y_offset_real` once at
    construction. `scale` and `content_height` are frozen.
    """

    real: Any
    scale: int = attrs.field(default=1, on_setattr=attrs.setters.frozen)
    content_height: int = attrs.field(
        default=CONTENT_HEIGHT, on_setattr=attrs.setters.frozen
    )
    y_offset_real: int = attrs.field(init=False, default=0)

    def __attrs_post_init__(self) -> None:
        # `content_height * scale` must fit inside the actual panel
        # height — otherwise `y_offset_real` goes negative and content near
        # the top/bottom logical edges silently clips against the panel
        # boundaries. The user-facing pitfall: a TwoRowMessage with
        # `:instagram:` hi-res emoji losing 4-8 real px at the panel
        # bottom (hardware-discovered). Hard-fail here so any future
        # config that misallocates breathing room surfaces immediately
        # instead of producing a half-broken display. We peel through
        # nested wrappers (cross-scale dissolves wrap a wrapper at
        # transition time) so the check sees the genuine panel height,
        # not another wrapper's logical content_height.
        innermost = self.real
        while isinstance(innermost, ScaledCanvas):
            innermost = innermost.real
        panel_h_real = innermost.height
        if self.content_height * self.scale > panel_h_real:
            max_content_height = panel_h_real // self.scale
            raise ValueError(
                f"content_height={self.content_height} × scale={self.scale} "
                f"= {self.content_height * self.scale} exceeds the real "
                f"panel height ({panel_h_real}). The wrapper would "
                f"go into negative y_offset territory and silently clip "
                f"content near the logical canvas edges. Pick "
                f"content_height ≤ {max_content_height}."
            )
        self.y_offset_real = (self.real.height - self.content_height * self.scale) // 2

    @property
    def width(self) -> int:
        return self.real.width // self.scale

    @property
    def height(self) -> int:
        return self.content_height

    def Clear(self) -> None:
        self.real.Clear()

    def Fill(self, r: int, g: int, b: int) -> None:
        """Fill the entire underlying canvas (including any letterbox).

        Used by `color_flash` and other full-canvas transition effects.
        Letterbox bands are filled too so the whole panel flashes.
        """
        self.real.Fill(r, g, b)

    def SetPixel(self, x: int, y: int, r: int, g: int, b: int) -> None:
        s = self.scale
        rx = x * s
        ry = y * s + self.y_offset_real
        self.real.SubFill(rx, ry, s, s, r, g, b)

    def SubFill(
        self, x: int, y: int, width: int, height: int, r: int, g: int, b: int
    ) -> None:
        s = self.scale
        self.real.SubFill(
            x * s, y * s + self.y_offset_real, width * s, height * s, r, g, b
        )

    def rebind_innermost(self, new_real: Any) -> None:
        """Rewire the innermost `.real` to `new_real`, leaving outer wrappers intact.

        Called after `widget.play()` returns a new back-buffer canvas so
        subsequent draws through this wrapper use the fresh canvas. Walks
        nested ScaledCanvas wrappers — cross-scale dissolve transitions wrap
        a wrapper at transition time; we must reach the bottom of the chain.
        """
        innermost = self
        while isinstance(innermost.real, ScaledCanvas):
            innermost = innermost.real
        innermost.real = new_real

    def draw_bdf_text(self, bdf, x: int, y: int, color, text: str) -> int:
        """Draw `text` at logical (x, y) baseline. Returns total advance width.

        Mirrors `graphics.DrawText`: x is the left edge and y is the baseline
        (BDF glyphs draw above the baseline coordinate).
        """
        if isinstance(color, tuple):
            r, g, b = color
        else:
            r, g, b = color.red, color.green, color.blue
        # Hoist for inner loop: SetPixel is invoked once per lit pixel × scale².
        set_pixel = self.SetPixel
        cx = x
        glyphs = bdf.glyphs
        fallback_width = bdf.bbx_width
        for ch in text:
            glyph = glyphs.get(ch)
            if glyph is None:
                cx += fallback_width
                continue
            top_y = y - glyph.bbx_height - glyph.bbx_yoff
            base_x = cx + glyph.bbx_xoff
            # lit_pixels is pre-computed at parse time — iterate ONLY set
            # bits instead of every cell with a per-cell branch. Combined
            # with the SetPixel hoist, halves the Python-side overhead.
            for col, row in glyph.lit_pixels:
                set_pixel(base_x + col, top_y + row, r, g, b)
            cx += glyph.advance_width
        return cx - x


def is_scaled(canvas: Any) -> TypeGuard[ScaledCanvas]:
    """True if ``canvas`` is a scaled wrapper (the bigsign hi-res path).

    The supported way for a plugin to gate its hi-res branch — prefer this
    over ``isinstance(canvas, ScaledCanvas)`` in plugin code. Annotated as a
    ``TypeGuard`` so a positive check narrows ``canvas`` to ``ScaledCanvas``
    for type checkers, exactly as the inline ``isinstance`` did.
    """
    return isinstance(canvas, ScaledCanvas)


def unwrap_to_real(canvas: Any) -> Any:
    """Return the underlying real canvas, peeling any ScaledCanvas wrappers.

    Use this whenever a widget or transition needs to paint at the panel's
    native pixel resolution (gif blits, dissolve scatter). Plain real
    canvases pass through unchanged. Handles nested wrappers — though we
    don't currently create them, the recursion is cheap and protects
    against future regressions.
    """
    while isinstance(canvas, ScaledCanvas):
        canvas = canvas.real
    return canvas


def paint_hires(canvas: Any, callback: Callable[[Any, int, int], None]) -> None:
    """Call `callback(real_canvas, scale, y_offset_real)` with unwrapped coords.

    For a ScaledCanvas, unwraps to the innermost real canvas and forwards
    `canvas.scale` and `canvas.y_offset_real`. For any other canvas, passes
    through with scale=1 and y_offset=0. Use this instead of the three-line
    unwrap idiom whenever a paint site needs to write at physical resolution.
    """
    if isinstance(canvas, ScaledCanvas):
        callback(unwrap_to_real(canvas), canvas.scale, canvas.y_offset_real)
    else:
        callback(canvas, 1, 0)
