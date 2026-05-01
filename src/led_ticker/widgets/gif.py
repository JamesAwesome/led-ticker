"""GIF player widget — displays an animated GIF on the LED panel as
if it were a small monitor.

The widget lazily decodes all frames on first use, paints the current
frame directly to the underlying real canvas (bypassing ScaledCanvas
so each pixel is a native LED, not a scale×scale block), and exposes
an async `play()` method that drives the per-frame playback loop.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import attrs

from led_ticker._types import Canvas, DrawResult
from led_ticker.widgets import register
from led_ticker.widgets._gif_decode import decode_gif


@register("gif")
@attrs.define
class GifPlayer:
    """Animated-GIF widget. See `mode = "gif"` for orchestration."""

    path: str
    fit: str = "pillarbox"
    padding: int = 0  # required by widget protocol; unused here

    _frames: list[tuple[bytes, int]] = attrs.field(init=False, factory=list)
    _current_frame_idx: int = attrs.field(init=False, default=0)
    _panel_w: int = attrs.field(init=False, default=0)
    _panel_h: int = attrs.field(init=False, default=0)

    def _real_canvas(self, canvas: Canvas) -> Canvas:
        """Unwrap ScaledCanvas so we paint native physical pixels."""
        return getattr(canvas, "real", canvas)

    def _load(self, panel_w: int = 0, panel_h: int = 0) -> None:
        """Decode all frames. Idempotent — second call is a no-op."""
        if self._frames:
            return
        # Default to bigsign physical dims; tests/callers can override
        # before the first call by setting _panel_w/_panel_h.
        if panel_w <= 0:
            panel_w = self._panel_w or 256
        if panel_h <= 0:
            panel_h = self._panel_h or 64
        self._panel_w = panel_w
        self._panel_h = panel_h
        self._frames = decode_gif(
            Path(self.path), panel_w=panel_w, panel_h=panel_h, fit=self.fit
        )

    def draw(self, canvas: Canvas, cursor_pos: int = 0, **kwargs: Any) -> DrawResult:
        """Paint the current frame to the real canvas at native res.

        Returns `(canvas, canvas.width)` so the widget claims the full
        row — the framework treats GIFs as full-screen takeovers.
        """
        del cursor_pos, kwargs  # unused

        real = self._real_canvas(canvas)
        # Lazy load using the real canvas's physical dimensions
        self._load(panel_w=real.width, panel_h=real.height)

        if not self._frames:
            return canvas, canvas.width

        pixels, _ = self._frames[self._current_frame_idx]
        w = real.width
        h = real.height
        set_px = real.SetPixel
        for y in range(h):
            row = y * w * 3
            for x in range(w):
                base = row + x * 3
                set_px(x, y, pixels[base], pixels[base + 1], pixels[base + 2])
        return canvas, canvas.width

    async def play(
        self,
        real_canvas: Canvas,
        frame: Any,
        loop_count: int = 1,
    ) -> Canvas:
        """Run the playback loop: paint each frame, swap, sleep,
        repeat for `loop_count` complete loops.

        Returns the back-buffer canvas left after the final swap so
        the caller (Ticker) can keep using it. Per CLAUDE.md #1, the
        SwapOnVSync return value MUST be captured every iteration.
        """
        self._load(panel_w=real_canvas.width, panel_h=real_canvas.height)
        if not self._frames:
            return real_canvas

        loops = max(1, loop_count)
        canvas = real_canvas
        w = canvas.width
        h = canvas.height

        for _ in range(loops):
            for pixels, duration_ms in self._frames:
                canvas.Clear()
                set_px = canvas.SetPixel
                for y in range(h):
                    row = y * w * 3
                    for x in range(w):
                        base = row + x * 3
                        set_px(
                            x,
                            y,
                            pixels[base],
                            pixels[base + 1],
                            pixels[base + 2],
                        )
                canvas = frame.matrix.SwapOnVSync(canvas)
                await asyncio.sleep(duration_ms / 1000)

        # Land on the last frame so subsequent draw() calls (for the
        # exit transition's compositing) paint it.
        self._current_frame_idx = len(self._frames) - 1
        return canvas
