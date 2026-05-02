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
the text only shows through pillars / letterbox bands. With
`text_align="scroll_over"` the text scrolls right-to-left ON TOP of
the gif — always visible (useful as a marquee over a full-screen
background gif).
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any

import attrs

from led_ticker._types import Canvas, Color, DrawResult, Font
from led_ticker.colors import DEFAULT_COLOR
from led_ticker.drawing import get_text_width
from led_ticker.fonts import FONT_DEFAULT
from led_ticker.scaled_canvas import ScaledCanvas
from led_ticker.text_render import draw_text
from led_ticker.widgets import register
from led_ticker.widgets._gif_decode import decode_gif

_VALID_TEXT_ALIGNS: frozenset[str] = frozenset(
    {"left", "right", "scroll", "scroll_over"}
)
_VALID_GIF_ALIGNS: frozenset[str] = frozenset({"left", "center", "right"})
_EMOJI_PATTERN = re.compile(r":[a-z_]+:")


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
    # Pixel-art block scale for text painting only (gif still paints at
    # native res). 1 = native BDF, 2 = 2×2 blocks per glyph pixel, etc.
    # Set to 2-4 on the bigsign so text is visible from across the room.
    text_scale: int = 1
    loops: int = 1  # gif-internal loops per visit (used by run_swap)
    # Minimum number of times scrolling text must traverse the panel
    # before the section is allowed to transition. 0 = no floor (gif
    # `loops` drives duration). Only meaningful with text_align="scroll"
    # or "scroll_over"; ignored for static text.
    text_loops: int = 0
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

    def _has_emoji(self) -> bool:
        return bool(_EMOJI_PATTERN.search(self.text))

    def _measure_text(self, canvas: Canvas) -> int:
        """Total advance width of `self.text` on `canvas`, accounting for
        inline emoji slugs (which can be wider than a normal glyph)."""
        if self._has_emoji():
            from led_ticker.pixel_emoji import measure_width

            return measure_width(self.font, self.text, canvas=canvas)
        return get_text_width(self.font, self.text, padding=0)

    def _draw_text(self, canvas: Canvas, x: int, baseline_y: int, color: Color) -> int:
        """Draw `self.text` on `canvas`. Routes through the emoji-aware
        path when the text contains `:slug:` tokens; otherwise falls
        back to the plain BDF rasterizer.

        For inline emoji on a real (non-ScaledCanvas) canvas, the 8×8
        sprite is anchored so its bottom row sits on the text baseline
        — matches how text glyphs read against their baseline.
        """
        if self._has_emoji():
            from led_ticker.pixel_emoji import draw_with_emoji

            # On a ScaledCanvas the default emoji_y (logical 4) already
            # aligns with logical text baseline 12; on a real canvas we
            # shift the 8px sprite up so its bottom row meets the baseline.
            emoji_y = None if isinstance(canvas, ScaledCanvas) else baseline_y - 8
            return draw_with_emoji(
                canvas, self.font, x, baseline_y, color, self.text, emoji_y=emoji_y
            )
        return draw_text(canvas, self.font, x, baseline_y, color, self.text)

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
        w_phys = canvas.width
        h_phys = canvas.height

        # Optional ScaledCanvas wrapper for text painting only — gives
        # text the same chunky pixel-art look as other bigsign widgets,
        # while the gif itself keeps painting at native physical res.
        # `text_canvas` is what we hand to the BDF rasterizer / emoji
        # painter; `canvas` (= real) stays the target for gif blits.
        text_canvas: Canvas = (
            ScaledCanvas(canvas, scale=self.text_scale)
            if self.text_scale > 1
            else canvas
        )
        text_w = text_canvas.width  # logical when wrapped, physical otherwise
        text_h = text_canvas.height
        baseline_y = self._baseline_y(text_h)

        loop_ms = sum(d for _, d in self._frames)
        total_ms = loop_ms * loops
        tick_ms = max(20, self.scroll_speed_ms)
        n_ticks = max(1, total_ms // tick_ms)

        text_width = self._measure_text(text_canvas)
        text_x_left = 2
        text_x_right = max(2, text_w - text_width - 2)

        # Scroll starts off the right edge so text enters from the right.
        scrolling = self.text_align in ("scroll", "scroll_over")
        scroll_pos = text_w if scrolling else 0

        # If the user wants the text to traverse the panel at least N
        # times before the section transitions, extend the tick budget
        # accordingly. One traversal = `text_w + text_width` ticks (text
        # enters from the right edge, fully exits left). Gif keeps
        # looping in the background to fill the extended duration.
        if scrolling and self.text_loops > 0:
            ticks_per_text_loop = text_w + text_width
            n_ticks = max(n_ticks, self.text_loops * ticks_per_text_loop)

        for tick in range(n_ticks):
            elapsed_ms = tick * tick_ms
            frame_idx = self._frame_for_elapsed(elapsed_ms, loop_ms)
            pixels, _ = self._frames[frame_idx]

            canvas.Clear()

            if self.text_align == "scroll":
                # Text under, gif on top with black pillars made transparent
                self._draw_text(text_canvas, scroll_pos, baseline_y, self.font_color)
                self._paint_skip_black(canvas, pixels, w_phys, h_phys)
            elif self.text_align == "scroll_over":
                # Gif under, text on top — text always visible as a marquee
                self._paint_full(canvas, pixels, w_phys, h_phys)
                self._draw_text(text_canvas, scroll_pos, baseline_y, self.font_color)
            else:
                # Static text: gif under, text on top
                self._paint_full(canvas, pixels, w_phys, h_phys)
                text_x = text_x_left if self.text_align == "left" else text_x_right
                self._draw_text(text_canvas, text_x, baseline_y, self.font_color)

            canvas = frame.matrix.SwapOnVSync(canvas)
            # Follow the new back-buffer for the next tick's text paint.
            # ScaledCanvas wrappers are mutable (rebind .real); for the
            # text_scale=1 path text_canvas IS the canvas, so we have to
            # rebind it directly — otherwise we'd paint text to the FRONT
            # buffer (now displaying) on every other tick, which reads
            # as a pulsing flicker on the panel.
            if isinstance(text_canvas, ScaledCanvas):
                text_canvas.real = canvas
            else:
                text_canvas = canvas
            await asyncio.sleep(tick_ms / 1000)

            if scrolling:
                scroll_pos -= 1
                if scroll_pos + text_width <= 0:
                    scroll_pos = text_w

        self._current_frame_idx = len(self._frames) - 1
        return canvas
