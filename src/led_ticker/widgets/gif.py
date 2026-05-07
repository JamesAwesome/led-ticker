"""GIF player widget — displays an animated GIF on the LED panel as
if it were a small monitor.

Despite the name, the decoder (:mod:`_gif_decode`) just calls
``PIL.Image.open()`` and iterates frames via ``n_frames`` /
``seek()``, so any Pillow-supported animated format works:
``.gif``, animated ``.webp``, ``.apng``, multi-frame ``.tiff``.
Per-frame durations come from ``img.info["duration"]`` which Pillow
populates from the format's native chunk metadata. For static
(single-frame) sources prefer :class:`StillImage` (``type = "image"``)
which has a ``hold_seconds`` knob — a 1-frame "gif" works but isn't
the natural fit.

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
``path``            (required)         Path to source file. Relative paths
                                       resolve against the config.toml dir.
                                       Any Pillow-supported animated format
                                       (gif, webp, apng, multi-frame tiff).
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
``font``            ``FONT_DEFAULT``   BDF or HiresFont by name (e.g.
                                       ``"Inter-Regular"``). Defaults to 6×12.
``font_size``       ``None``           Real-pixel size. None = smart default
                                       (BDF only): cell_h × _logical_scale, so
                                       12 on small sign, 48 on bigsign for
                                       FONT_DEFAULT (6×12). HiresFont configs
                                       must specify explicitly. For BDF, snaps
                                       down to the nearest integer multiple of
                                       cell height.
``gif_loops``       ``1``              Per-visit gif loop count when dispatched
                                       via run_swap. (Still widget uses
                                       ``hold_seconds`` instead.)
``text_loops``      ``0``              Floor on marquee traversals before
                                       section transitions. Only with scrolling
                                       text; 0 = no floor.
==================  =================  ==========================================

Constraints validated at construction:
    - ``gif_loops >= 1``
    - ``text_loops >= 0``
    - ``scroll_speed_ms >= 20``
    - ``text_loops > 0`` requires ``text_align`` ∈ ``{scroll, scroll_over}``
    - ``text_x_offset != 0`` requires ``text_align`` ∈ ``{left, right}``
    - ``text_align="scroll"`` requires ``fit != "stretch"``

Validated at first paint (panel dims unknown until then):
    - BDF: ``font_size >= cell_h`` (raises with hint if smaller)
    - Resolved ``font_size``'s logical line-height fits the panel

See CLAUDE.md "GIF widget and Still-image widget" for architectural
context (shared base class, native-resolution painting, play()
dispatch, transparent decode).
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
from led_ticker.widgets._image_fit import reset_canvas


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
    # Sum of frame durations — cached at decode so `_pick_frame_for_elapsed`
    # doesn't re-sum on every tick.
    _loop_ms: int = attrs.field(init=False, default=0)
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
        self._loop_ms = sum(d for _, d in self._frames)

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

        from led_ticker.widgets._image_fit import scan_non_black

        pil_images: list[Any] = []
        non_black: list[list[tuple[int, int, int, int, int]]] = []
        for pixels, _ in self._frames:
            pil_images.append(Image.frombytes("RGB", (panel_w, panel_h), pixels))
            non_black.append(scan_non_black(pixels, panel_w, panel_h))
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
        if self._loop_ms > 0:
            self._current_frame_idx = self._frame_for_elapsed(elapsed_ms, self._loop_ms)

    def _is_static(self) -> bool:
        """A 0- or 1-frame gif is effectively a still image — the
        static-text fast path can apply. Multi-frame gifs must NOT
        fast-path or they freeze on frame 0 with no per-tick frame
        advance. (Tripwire: `test_gif_static_text_does_not_freeze_animation`.)"""
        return len(self._frames) <= 1

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

        Without text: tick at engine 50ms cadence (``ENGINE_TICK_MS``);
        ``_pick_frame_for_elapsed`` picks the gif frame from accumulated
        wall-clock time so animated borders chase uniformly regardless of
        gif frame durations.

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

        if not self._has_text_content():
            return await self._play_no_text(real_canvas, frame, loop_count)

        loops = max(1, loop_count)
        # Cache `_loop_ms` defensively in case `_frames` was injected
        # without going through `_load` (e.g. tests that bypass decode).
        if self._loop_ms == 0:
            self._loop_ms = sum(d for _, d in self._frames)
        total_ms = self._loop_ms * loops
        tick_ms = max(MIN_SCROLL_SPEED_MS, self.scroll_speed_ms)
        n_ticks = max(1, total_ms // tick_ms)
        return await self._play_with_text(real_canvas, frame, n_ticks)

    async def _play_no_text(
        self, real_canvas: Canvas, frame: Any, loop_count: int
    ) -> Canvas:
        """Run the gif at engine 50ms cadence — `_pick_frame_for_elapsed`
        picks the right gif frame from accumulated wall-clock time so
        animated borders (and any future frame-aware overlays) tick
        uniformly regardless of gif frame durations.

        Side effect: gifs with native frame durations < 50ms cap at
        20 Hz on this path — same cap `_play_with_text` already
        imposes. Gifs with frame durations >= 50ms (the common case)
        render identically to before.
        """
        from led_ticker.ticker import ENGINE_TICK_MS

        loops = max(1, loop_count)
        canvas = real_canvas
        if self._loop_ms == 0:
            self._loop_ms = sum(d for _, d in self._frames)
        total_ms = self._loop_ms * loops
        n_ticks = max(1, total_ms // ENGINE_TICK_MS)
        tick_seconds = ENGINE_TICK_MS / 1000

        for tick in range(n_ticks):
            self._pick_frame_for_elapsed(tick * ENGINE_TICK_MS)
            self.advance_frame()
            reset_canvas(canvas, self.bg_color)
            self._paint_image(canvas)
            if self.border is not None:
                self.border.paint(canvas, self._frame_count)
            canvas = frame.matrix.SwapOnVSync(canvas)
            await asyncio.sleep(tick_seconds)

        self._current_frame_idx = len(self._frames) - 1
        return canvas
