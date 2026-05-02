"""GIF player widget — displays an animated GIF on the LED panel as
if it were a small monitor.

Counterpart to :class:`led_ticker.widgets.still.StillImage` — both
inherit from :class:`led_ticker.widgets._image_base._BaseImageWidget`
so the text-overlay surface is identical. The only widget-specific
knobs are ``gif_loops`` (this widget) vs ``hold_seconds`` (still).

The widget lazily decodes all frames on first use, paints frames
directly to the underlying real canvas (bypassing ScaledCanvas so each
pixel is a native LED, not a scale×scale block), and exposes an async
``play()`` method that drives the per-frame playback loop.

Two run modes:
    - ``mode = "gif"``  legacy panel-takeover orchestrator (no titles)
    - ``mode = "swap"`` unified path; gif rides ``_show_one``'s
                       ``_has_play`` dispatch and works alongside an
                       optional title

Schema (TOML config keys for ``type = "gif"``):

==================  =================  ==========================================
Field               Default            Description
==================  =================  ==========================================
``path``            (required)         Path to GIF file. Relative paths resolve
                                       against the config.toml directory.
``fit``             ``"pillarbox"``    ``pillarbox`` | ``letterbox`` | ``stretch``
                                       | ``crop``
``image_align``     ``"center"``       ``left`` | ``center`` | ``right`` —
                                       horizontal anchor; only meaningful for
                                       pillarbox.
``text``            ``""``             Optional text rendered alongside the gif.
                                       Supports ``:slug:`` inline emoji.
``text_align``      ``"auto"``         ``auto`` | ``left`` | ``right`` |
                                       ``scroll`` | ``scroll_over``. ``auto``
                                       picks the side opposite ``image_align``
                                       so they don't overlap.
``text_valign``     ``"center"``       ``top`` | ``center`` | ``bottom``.
``text_y_offset``   ``0``              Logical-pixel shift on baseline picked by
                                       ``text_valign``. Negative=up, positive=down.
``text_x_offset``   ``0``              Logical-pixel shift on static text x.
                                       Positive=right, negative=left. Rejected
                                       when used with scroll modes.
``scroll_direction`` ``"left"``        Direction marquee TRAVELS.
``font_color``      yellow             RGB list ``[r, g, b]`` or "random".
``scroll_speed_ms`` ``50``             Tick cadence when text scrolls (≥ 20).
``text_scale``      ``1``              Block-scale glyphs (1=native; set 2-4 on
                                       bigsign for readable text).
``gif_loops``       ``1``              Per-visit gif loop count when dispatched
                                       via run_swap. (Still widget uses
                                       ``hold_seconds`` instead.)
``text_loops``      ``0``              Floor on marquee traversals before
                                       section transitions. Only with scrolling
                                       text; 0 = no floor.
==================  =================  ==========================================

Constraints validated at construction:
    - ``text_scale >= 1``
    - ``gif_loops >= 1``
    - ``text_loops >= 0``
    - ``scroll_speed_ms >= 20``
    - ``text_loops > 0`` requires ``text_align`` ∈ ``{scroll, scroll_over}``
    - ``text_x_offset != 0`` requires ``text_align`` ∈ ``{left, right}``
    - ``text_align="scroll"`` requires ``fit != "stretch"``

See CLAUDE.md "GIF widget" for architectural context (native-resolution
painting, play() dispatch, transparent decode, etc.).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import attrs

from led_ticker._types import Canvas, DrawResult
from led_ticker.scaled_canvas import unwrap_to_real
from led_ticker.widgets import register
from led_ticker.widgets._gif_decode import decode_gif
from led_ticker.widgets._image_base import MIN_SCROLL_SPEED_MS, _BaseImageWidget


@register("gif")
@attrs.define
class GifPlayer(_BaseImageWidget):
    """Animated-GIF widget. See module docstring for schema."""

    path: str
    fit: str = "pillarbox"
    image_align: str = "center"
    gif_loops: int = 1

    _frames: list[tuple[bytes, int]] = attrs.field(init=False, factory=list)
    _current_frame_idx: int = attrs.field(init=False, default=0)
    # Derived per-frame caches built lazily by `_ensure_paint_caches`.
    # `_pil_images[i]` is for `canvas.SetImage`; `_non_black[i]` is the
    # skip-black scroll path.
    _pil_images: list[Any] = attrs.field(init=False, factory=list)
    _non_black: list[list[tuple[int, int, int, int, int]]] = attrs.field(
        init=False, factory=list
    )

    def __attrs_post_init__(self) -> None:
        self._validate_common(image_align=self.image_align, fit=self.fit)
        if self.gif_loops < 1:
            raise ValueError(f"gif_loops must be >= 1, got {self.gif_loops!r}")

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
            image_align=self.image_align,
        )

    def _ensure_paint_caches(self) -> None:
        """Build per-frame PIL images + non-black pixel lists from the
        decoded RGB bytes. Idempotent — short-circuits when caches are
        already populated for the current `_frames`. Called lazily by
        `_paint_full` / `_paint_skip_black` so tests that synthesize
        `_frames` directly (without going through `_load`) still get
        the derived caches built on first paint.
        """
        if len(self._pil_images) == len(self._frames):
            return
        panel_w, panel_h = self._panel_w, self._panel_h
        if panel_w <= 0 or panel_h <= 0:
            return
        from PIL import Image

        pil_images: list[Any] = []
        non_black: list[list[tuple[int, int, int, int, int]]] = []
        for pixels, _ in self._frames:
            pil_images.append(Image.frombytes("RGB", (panel_w, panel_h), pixels))
            nb: list[tuple[int, int, int, int, int]] = []
            for y in range(panel_h):
                row = y * panel_w * 3
                for x in range(panel_w):
                    base = row + x * 3
                    r = pixels[base]
                    g = pixels[base + 1]
                    b = pixels[base + 2]
                    if r or g or b:
                        nb.append((x, y, r, g, b))
            non_black.append(nb)
        self._pil_images = pil_images
        self._non_black = non_black

    def _frame_for_elapsed(self, elapsed_ms: int, loop_ms: int) -> int:
        """Pick the gif frame index for a given elapsed time (wrapping)."""
        pos = elapsed_ms % loop_ms
        cum = 0
        for i, (_, d) in enumerate(self._frames):
            cum += d
            if pos < cum:
                return i
        return len(self._frames) - 1

    # ------------------------------------------------------------------
    # _BaseImageWidget hook implementations
    # ------------------------------------------------------------------

    def _paint_full(self, canvas: Canvas) -> None:
        """Paint the current frame via SetImage — single C call into
        rgbmatrix that pushes RGB bytes into the framebuffer in one shot."""
        self._ensure_paint_caches()
        if self._pil_images:
            canvas.SetImage(self._pil_images[self._current_frame_idx], 0, 0)

    def _paint_skip_black(self, canvas: Canvas) -> None:
        """Paint the non-black pixels of the current frame only —
        leaves underlying canvas content (pre-painted scrolling text)
        showing through pillars and letterbox bands."""
        self._ensure_paint_caches()
        if not self._non_black:
            return
        set_px = canvas.SetPixel
        for x, y, r, g, b in self._non_black[self._current_frame_idx]:
            set_px(x, y, r, g, b)

    def _pick_frame_for_elapsed(self, elapsed_ms: int) -> None:
        """Advance `_current_frame_idx` based on elapsed playback time
        (per-tick hook from the base text-scroll loop)."""
        if self._frames:
            loop_ms = sum(d for _, d in self._frames)
            self._current_frame_idx = self._frame_for_elapsed(elapsed_ms, loop_ms)

    # ------------------------------------------------------------------
    # Widget protocol + per-section orchestration
    # ------------------------------------------------------------------

    def draw(self, canvas: Canvas, cursor_pos: int = 0, **kwargs: Any) -> DrawResult:
        """Paint the current frame to the real canvas at native res.

        Used for transition compositing (entry/exit dissolves). Text is
        intentionally NOT painted here — the dissolve looks cleaner
        with just the gif, and there's no scroll-position state at
        draw time.
        """
        del cursor_pos, kwargs
        real = unwrap_to_real(canvas)
        self._load(panel_w=real.width, panel_h=real.height)
        if not self._frames:
            return canvas, canvas.width
        self._paint_full(real)
        return canvas, canvas.width

    async def play(
        self,
        real_canvas: Canvas,
        frame: Any,
        loop_count: int = 1,
    ) -> Canvas:
        """Run the playback loop.

        Without text: tick at each gif frame's native duration (existing
        behaviour, fastest path).

        With text: tick at ``scroll_speed_ms``, picking the gif frame
        from elapsed time so playback duration still matches
        ``loop_count × sum(durations)``. Text renders per-tick at its
        current scroll position (or static for left/right alignments).

        Per CLAUDE.md #1, the SwapOnVSync return value MUST be captured
        every iteration.
        """
        self._load(panel_w=real_canvas.width, panel_h=real_canvas.height)
        if not self._frames:
            return real_canvas

        if not self.text:
            return await self._play_no_text(real_canvas, frame, loop_count)

        loops = max(1, loop_count)
        loop_ms = sum(d for _, d in self._frames)
        total_ms = loop_ms * loops
        tick_ms = max(MIN_SCROLL_SPEED_MS, self.scroll_speed_ms)
        n_ticks = max(1, total_ms // tick_ms)
        return await self._play_with_text(real_canvas, frame, n_ticks)

    async def _play_no_text(
        self, real_canvas: Canvas, frame: Any, loop_count: int
    ) -> Canvas:
        loops = max(1, loop_count)
        canvas = real_canvas

        for _ in range(loops):
            for idx, (_pixels, duration_ms) in enumerate(self._frames):
                self._current_frame_idx = idx
                canvas.Clear()
                self._paint_full(canvas)
                canvas = frame.matrix.SwapOnVSync(canvas)
                await asyncio.sleep(duration_ms / 1000)

        self._current_frame_idx = len(self._frames) - 1
        return canvas
