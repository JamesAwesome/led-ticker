"""GIF player widget — displays an animated GIF on the LED panel as
if it were a small monitor.

The widget lazily decodes all frames on first use, paints the current
frame directly to the underlying real canvas (bypassing ScaledCanvas
so each pixel is a native LED, not a scale×scale block), and exposes
an async `play()` method that drives the per-frame playback loop.

Optional `text` renders alongside the GIF. With `text_align="left"` or
`"right"` the text sits statically in the corresponding pillar (gif on
bottom, text on top). With `text_align="scroll"` the text scrolls
right-to-left UNDER the gif — black pixels in the gif are skipped so
the text only shows through pillars / letterbox bands.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import attrs

from led_ticker._types import Canvas, Color, DrawResult, Font
from led_ticker.colors import DEFAULT_COLOR
from led_ticker.drawing import get_text_width
from led_ticker.fonts import FONT_DEFAULT
from led_ticker.text_render import draw_text
from led_ticker.widgets import register
from led_ticker.widgets._gif_decode import decode_gif

_VALID_TEXT_ALIGNS: frozenset[str] = frozenset({"left", "right", "scroll"})
_VALID_GIF_ALIGNS: frozenset[str] = frozenset({"left", "center", "right"})


@register("gif")
@attrs.define
class GifPlayer:
    """Animated-GIF widget. See `mode = "gif"` for orchestration."""

    path: str
    fit: str = "pillarbox"
    # "left" | "center" | "right" — only meaningful for pillarbox
    gif_align: str = "center"
    text: str = ""
    text_align: str = "right"  # "left" | "right" | "scroll"
    font_color: Color = attrs.Factory(lambda: DEFAULT_COLOR)
    font: Font = attrs.Factory(lambda: FONT_DEFAULT)
    scroll_speed_ms: int = 50  # tick cadence when text is scrolling
    loops: int = 1  # gif-internal loops per visit (used by run_swap)
    padding: int = 0  # required by widget protocol; unused here

    _frames: list[tuple[bytes, int]] = attrs.field(init=False, factory=list)
    _current_frame_idx: int = attrs.field(init=False, default=0)
    _panel_w: int = attrs.field(init=False, default=0)
    _panel_h: int = attrs.field(init=False, default=0)

    def __attrs_post_init__(self) -> None:
        if self.text and self.text_align not in _VALID_TEXT_ALIGNS:
            raise ValueError(
                f"unknown text_align={self.text_align!r}; "
                f"expected one of {sorted(_VALID_TEXT_ALIGNS)}"
            )
        if self.gif_align not in _VALID_GIF_ALIGNS:
            raise ValueError(
                f"unknown gif_align={self.gif_align!r}; "
                f"expected one of {sorted(_VALID_GIF_ALIGNS)}"
            )

    def _real_canvas(self, canvas: Canvas) -> Canvas:
        """Unwrap ScaledCanvas so we paint native physical pixels."""
        return getattr(canvas, "real", canvas)

    def _load(self, panel_w: int = 0, panel_h: int = 0) -> None:
        """Decode all frames. Idempotent — second call is a no-op."""
        if self._frames:
            return
        if panel_w <= 0:
            panel_w = self._panel_w or 256
        if panel_h <= 0:
            panel_h = self._panel_h or 64
        self._panel_w = panel_w
        self._panel_h = panel_h
        self._frames = decode_gif(
            Path(self.path),
            panel_w=panel_w,
            panel_h=panel_h,
            fit=self.fit,
            h_align=self.gif_align,
        )

    def _paint_full(self, canvas: Canvas, pixels: bytes, w: int, h: int) -> None:
        """Paint every pixel of the gif frame, including black pillars."""
        set_px = canvas.SetPixel
        for y in range(h):
            row = y * w * 3
            for x in range(w):
                base = row + x * 3
                set_px(x, y, pixels[base], pixels[base + 1], pixels[base + 2])

    def _paint_skip_black(self, canvas: Canvas, pixels: bytes, w: int, h: int) -> None:
        """Paint gif pixels but skip pure-black ones — leaves the
        underlying canvas content (e.g. pre-painted scrolling text) showing
        through pillars and letterbox bands."""
        set_px = canvas.SetPixel
        for y in range(h):
            row = y * w * 3
            for x in range(w):
                base = row + x * 3
                r = pixels[base]
                g = pixels[base + 1]
                b = pixels[base + 2]
                if r or g or b:
                    set_px(x, y, r, g, b)

    def _baseline_y(self, h: int) -> int:
        """BDF baseline that vertically centers a 12-tall font in `h`."""
        # 6x12 font: 12 cell, 10 ascent. Center the cell, baseline = top + 10.
        return (h - 12) // 2 + 10

    def draw(self, canvas: Canvas, cursor_pos: int = 0, **kwargs: Any) -> DrawResult:
        """Paint the current frame to the real canvas at native res.

        Used for transition compositing (entry/exit dissolves). Text is
        intentionally NOT painted here — the dissolve looks cleaner with
        just the gif, and there's no scroll-position state at draw time.
        """
        del cursor_pos, kwargs

        real = self._real_canvas(canvas)
        self._load(panel_w=real.width, panel_h=real.height)

        if not self._frames:
            return canvas, canvas.width

        pixels, _ = self._frames[self._current_frame_idx]
        self._paint_full(real, pixels, real.width, real.height)
        return canvas, canvas.width

    def _frame_for_elapsed(self, elapsed_ms: int, loop_ms: int) -> int:
        """Pick the gif frame index for a given elapsed time (wrapping)."""
        pos = elapsed_ms % loop_ms
        cum = 0
        for i, (_, d) in enumerate(self._frames):
            cum += d
            if pos < cum:
                return i
        return len(self._frames) - 1

    async def play(
        self,
        real_canvas: Canvas,
        frame: Any,
        loop_count: int = 1,
    ) -> Canvas:
        """Run the playback loop.

        Without text: tick at each gif frame's native duration (existing
        behaviour, fastest path).

        With text: tick at `scroll_speed_ms`, picking the gif frame from
        elapsed time so playback duration still matches `loop_count` ×
        sum(durations). Text renders per-tick at its current scroll
        position (or static for left/right alignments).

        Per CLAUDE.md #1, the SwapOnVSync return value MUST be captured
        every iteration.
        """
        self._load(panel_w=real_canvas.width, panel_h=real_canvas.height)
        if not self._frames:
            return real_canvas

        if not self.text:
            return await self._play_no_text(real_canvas, frame, loop_count)
        return await self._play_with_text(real_canvas, frame, loop_count)

    async def _play_no_text(
        self, real_canvas: Canvas, frame: Any, loop_count: int
    ) -> Canvas:
        loops = max(1, loop_count)
        canvas = real_canvas
        w = canvas.width
        h = canvas.height

        for _ in range(loops):
            for pixels, duration_ms in self._frames:
                canvas.Clear()
                self._paint_full(canvas, pixels, w, h)
                canvas = frame.matrix.SwapOnVSync(canvas)
                await asyncio.sleep(duration_ms / 1000)

        self._current_frame_idx = len(self._frames) - 1
        return canvas

    async def _play_with_text(
        self, real_canvas: Canvas, frame: Any, loop_count: int
    ) -> Canvas:
        loops = max(1, loop_count)
        canvas = real_canvas
        w = canvas.width
        h = canvas.height

        loop_ms = sum(d for _, d in self._frames)
        total_ms = loop_ms * loops
        tick_ms = max(20, self.scroll_speed_ms)
        n_ticks = max(1, total_ms // tick_ms)

        text_width = get_text_width(self.font, self.text, padding=0)
        baseline_y = self._baseline_y(h)
        text_x_left = 2
        text_x_right = max(2, w - text_width - 2)

        # Scroll starts off the right edge so text enters from the right.
        scroll_pos = w if self.text_align == "scroll" else 0

        for tick in range(n_ticks):
            elapsed_ms = tick * tick_ms
            frame_idx = self._frame_for_elapsed(elapsed_ms, loop_ms)
            pixels, _ = self._frames[frame_idx]

            canvas.Clear()

            if self.text_align == "scroll":
                # Text under, gif on top with black pillars made transparent
                draw_text(
                    canvas,
                    self.font,
                    scroll_pos,
                    baseline_y,
                    self.font_color,
                    self.text,
                )
                self._paint_skip_black(canvas, pixels, w, h)
            else:
                # Static text: gif under, text on top
                self._paint_full(canvas, pixels, w, h)
                text_x = text_x_left if self.text_align == "left" else text_x_right
                draw_text(
                    canvas,
                    self.font,
                    text_x,
                    baseline_y,
                    self.font_color,
                    self.text,
                )

            canvas = frame.matrix.SwapOnVSync(canvas)
            await asyncio.sleep(tick_ms / 1000)

            if self.text_align == "scroll":
                scroll_pos -= 1
                if scroll_pos + text_width <= 0:
                    scroll_pos = w

        self._current_frame_idx = len(self._frames) - 1
        return canvas
