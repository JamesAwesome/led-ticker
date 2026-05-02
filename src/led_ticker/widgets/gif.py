"""GIF player widget — displays an animated GIF on the LED panel as
if it were a small monitor.

The widget lazily decodes all frames on first use, paints frames
directly to the underlying real canvas (bypassing ScaledCanvas so
each pixel is a native LED, not a scale×scale block), and exposes
an async `play()` method that drives the per-frame playback loop.

Two run modes:
    - ``mode = "gif"``  legacy panel-takeover orchestrator (no titles)
    - ``mode = "swap"`` unified path; gif rides _show_one's _has_play
                       dispatch and works alongside an optional title

Schema (TOML config keys for `type = "gif"`):

==================  =================  ==========================================
Field               Default            Description
==================  =================  ==========================================
``path``            (required)         Path to GIF file. Relative paths resolve
                                       against the config.toml directory.
``fit``             ``"pillarbox"``    ``pillarbox`` | ``letterbox`` | ``stretch``
                                       | ``crop``
``gif_align``       ``"center"``       ``left`` | ``center`` | ``right`` —
                                       horizontal anchor; only meaningful for
                                       pillarbox.
``text``            ``""``             Optional text rendered alongside the gif.
                                       Supports ``:slug:`` inline emoji.
``text_align``      ``"auto"``         ``auto`` | ``left`` | ``right`` |
                                       ``scroll`` | ``scroll_over``. ``auto``
                                       picks the side opposite ``gif_align`` so
                                       they don't overlap (center gif →
                                       scroll_over).
``text_valign``     ``"center"``       ``top`` | ``center`` | ``bottom`` —
                                       vertical anchor of the text band.
``scroll_direction`` ``"left"``        ``left`` | ``right``. Direction the
                                       marquee TRAVELS (left = enters from
                                       right edge, exits left). Only matters
                                       for scrolling text.
``font_color``      yellow             RGB list ``[r, g, b]`` or "random".
``scroll_speed_ms`` ``50``             Tick cadence when text scrolls (≥ 20).
``text_scale``      ``1``              Block-scale glyphs (1=native; set 2-4 on
                                       bigsign for readable text).
``gif_loops``       ``1``              Per-visit gif loop count when dispatched
                                       via run_swap.
``text_loops``      ``0``              Floor on marquee traversals before
                                       section transitions. Only with scrolling
                                       text; 0 = no floor.
==================  =================  ==========================================

text_align variants:
    - ``"left"``       static text in left pillar (gif under, text over)
    - ``"right"``      static text in right pillar (gif under, text over)
    - ``"scroll"``     marquee UNDER gif (text shows through transparent /
                       pillar areas via skip-black compositing)
    - ``"scroll_over"`` marquee ON TOP of gif (always visible)

Constraints validated at construction:
    - ``text_scale >= 1``
    - ``gif_loops >= 1``
    - ``text_loops >= 0``
    - ``scroll_speed_ms >= 20``
    - ``text_loops > 0`` requires ``text_align`` ∈ ``{scroll, scroll_over}``

See CLAUDE.md "GIF widget" for architectural context (native-resolution
painting, play() dispatch, transparent decode, etc.).
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
from led_ticker.scaled_canvas import ScaledCanvas, unwrap_to_real
from led_ticker.text_render import draw_text
from led_ticker.widgets import register
from led_ticker.widgets._gif_decode import (
    _VALID_GIF_ALIGNS,
    decode_gif,
    validate_choice,
)

_VALID_TEXT_ALIGNS: frozenset[str] = frozenset(
    {"left", "right", "scroll", "scroll_over"}
)
_VALID_TEXT_VALIGNS: frozenset[str] = frozenset({"top", "center", "bottom"})
_VALID_SCROLL_DIRECTIONS: frozenset[str] = frozenset({"left", "right"})
# `text_align="auto"` resolves to the side opposite the gif so they don't
# overlap. Center gif → scroll_over (always paints on top, no overlap zone).
_AUTO_TEXT_ALIGN_FOR_GIF: dict[str, str] = {
    "left": "right",
    "right": "left",
    "center": "scroll_over",
}
_EMOJI_PATTERN = re.compile(r":[a-z_]+:")

# Logical-px gap between the panel edge and the start of static-aligned text.
# Used twice in `_play_with_text` (left edge + right-edge clamp).
_TEXT_EDGE_PADDING_PX: int = 2

# Floor on `scroll_speed_ms`. 50 ms is the project's standard 20 fps tick;
# below ~20 ms the scroll motion outpaces the gif's frame cadence and the
# Python tick loop saturates the CPU.
_MIN_SCROLL_SPEED_MS: int = 20


@register("gif")
@attrs.define
class GifPlayer:
    """Animated-GIF widget. See `mode = "gif"` for orchestration."""

    path: str
    fit: str = "pillarbox"
    # "left" | "center" | "right" — only meaningful for pillarbox
    gif_align: str = "center"
    text: str = ""
    # "auto" | "left" | "right" | "scroll" | "scroll_over". "auto" picks
    # an alignment based on `gif_align` so the text doesn't overlap the
    # gif: left gif → right text, right gif → left text, center gif →
    # scroll_over (which always paints on top, no overlap).
    text_align: str = "auto"
    # "top" | "center" | "bottom" — vertical anchor of the text band.
    # `top` rests text against the panel's top edge; `bottom` against
    # the bottom edge; `center` (default) vertically centers. Useful
    # for split layouts where the gif takes one half and text the other.
    text_valign: str = "center"
    # "left" | "right" — direction the marquee text TRAVELS across the
    # panel. "left" (default): enters from right, exits left.
    # "right": enters from left, exits right. Only meaningful for
    # text_align="scroll" / "scroll_over".
    scroll_direction: str = "left"
    font_color: Color = attrs.Factory(lambda: DEFAULT_COLOR)
    scroll_speed_ms: int = 50  # tick cadence when text is scrolling
    # Pixel-art block scale for text painting only (gif still paints at
    # native res). 1 = native BDF, 2 = 2×2 blocks per glyph pixel, etc.
    # Set to 2-4 on the bigsign so text is visible from across the room.
    text_scale: int = 1
    # Per-visit gif loop count when dispatched via run_swap's _show_one
    # (mode = "swap"). Distinct from section-level `loop_count` ("cycle
    # the widget list N times") and `text_loops` (marquee-traversal
    # floor); naming `gif_loops` keeps all three visibly different.
    gif_loops: int = 1
    # Minimum number of times scrolling text must traverse the panel
    # before the section is allowed to transition. 0 = no floor (gif
    # `gif_loops` drives duration). Only meaningful with
    # text_align="scroll" or "scroll_over"; ignored for static text.
    text_loops: int = 0
    # `font` and `padding` are framework-internal, not user-facing
    # config. `font` defaults to FONT_DEFAULT (6×12 BDF, same as the
    # rest of the project); `padding` is required by the widget
    # protocol but meaningless for full-canvas gif blits.
    font: Font = attrs.field(init=False, default=FONT_DEFAULT)
    padding: int = attrs.field(init=False, default=0)

    _frames: list[tuple[bytes, int]] = attrs.field(init=False, factory=list)
    _current_frame_idx: int = attrs.field(init=False, default=0)
    _panel_w: int = attrs.field(init=False, default=0)
    _panel_h: int = attrs.field(init=False, default=0)
    # Derived per-frame caches built lazily by `_ensure_paint_caches`.
    # `_pil_images[i]` is for `canvas.SetImage`; `_non_black[i]` is the
    # skip-black scroll path.
    _pil_images: list[Any] = attrs.field(init=False, factory=list)
    _non_black: list[list[tuple[int, int, int, int, int]]] = attrs.field(
        init=False, factory=list
    )

    def __attrs_post_init__(self) -> None:
        validate_choice("gif_align", self.gif_align, _VALID_GIF_ALIGNS)
        # Resolve `text_align="auto"` based on gif_align so text doesn't
        # overlap the gif by default. Authors can still pin a specific
        # alignment explicitly. "auto" is silently fine when text="" since
        # nothing renders.
        if self.text_align == "auto":
            self.text_align = _AUTO_TEXT_ALIGN_FOR_GIF[self.gif_align]
        if self.text:
            validate_choice("text_align", self.text_align, _VALID_TEXT_ALIGNS)
        validate_choice("text_valign", self.text_valign, _VALID_TEXT_VALIGNS)
        validate_choice(
            "scroll_direction", self.scroll_direction, _VALID_SCROLL_DIRECTIONS
        )
        # Range checks on numeric fields. Default values (1, 0, 50) all
        # pass; we only catch user-supplied negatives or zeros that would
        # otherwise crash deep or silently behave unexpectedly.
        if self.text_scale < 1:
            raise ValueError(f"text_scale must be >= 1, got {self.text_scale!r}")
        if self.gif_loops < 1:
            raise ValueError(f"gif_loops must be >= 1, got {self.gif_loops!r}")
        if self.text_loops < 0:
            raise ValueError(f"text_loops must be >= 0, got {self.text_loops!r}")
        if self.scroll_speed_ms < _MIN_SCROLL_SPEED_MS:
            raise ValueError(
                f"scroll_speed_ms must be >= {_MIN_SCROLL_SPEED_MS}, "
                f"got {self.scroll_speed_ms!r}"
            )
        # text_loops is a marquee-traversal floor — silently ignored
        # with static text would surprise the user (they set a duration
        # and got the gif's default instead).
        if self.text_loops > 0 and self.text_align in ("left", "right"):
            raise ValueError(
                f"text_loops > 0 only applies when text_align is 'scroll' "
                f"or 'scroll_over'; got text_align={self.text_align!r}"
            )

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
            gif_align=self.gif_align,
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
            # Tests can set `_frames` before `_panel_w/h`; bail and let
            # the next call rebuild after dims are known.
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

    def _paint_full(self, canvas: Canvas, frame_idx: int) -> None:
        """Paint every pixel of frame `frame_idx`, including black pillars.

        Uses the underlying rgbmatrix's `canvas.SetImage(pil, x, y)` —
        a single C call that pushes RGB bytes into the framebuffer in
        one go. ~16,384× faster on the bigsign than the equivalent
        Python triple-nested SetPixel loop.
        """
        self._ensure_paint_caches()
        canvas.SetImage(self._pil_images[frame_idx], 0, 0)

    def _paint_skip_black(self, canvas: Canvas, frame_idx: int) -> None:
        """Paint the non-black pixels of frame `frame_idx` only —
        leaves underlying canvas content (e.g. pre-painted scrolling
        text) showing through pillars and letterbox bands.

        The non-black list is pre-computed at decode time (one pass
        through the bytes) so per-frame painting iterates ~30–60% of
        the total pixel count for typical pillarboxed gifs, with no
        per-pixel branch and no triple-indexed bytes reads.
        """
        self._ensure_paint_caches()
        set_px = canvas.SetPixel
        for x, y, r, g, b in self._non_black[frame_idx]:
            set_px(x, y, r, g, b)

    def _baseline_y(self, h: int) -> int:
        """BDF baseline that anchors a 12-tall font in `h` per `text_valign`.

        FONT_DEFAULT bounding box is 6×12 with 10 ascent + 2 descent. The
        baseline sits on the line between ascender and descender; glyph
        cells extend 10 above and 2 below.
        """
        if self.text_valign == "top":
            # Glyph top at y=0 → baseline at y=10 (ascent rows above).
            return 10
        if self.text_valign == "bottom":
            # Descender row at y=h-1 → baseline at y=h-2.
            return h - 2
        # "center" (default)
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

        Inline emoji are 8 px tall (logical for ScaledCanvas; physical
        otherwise). Anchor `emoji_y = baseline_y - 8` so the sprite's
        bottom row sits on the text baseline regardless of valign or
        canvas type — matches how text glyphs read against their baseline.
        """
        if self._has_emoji():
            from led_ticker.pixel_emoji import draw_with_emoji

            return draw_with_emoji(
                canvas,
                self.font,
                x,
                baseline_y,
                color,
                self.text,
                emoji_y=baseline_y - 8,
            )
        return draw_text(canvas, self.font, x, baseline_y, color, self.text)

    def draw(self, canvas: Canvas, cursor_pos: int = 0, **kwargs: Any) -> DrawResult:
        """Paint the current frame to the real canvas at native res.

        Used for transition compositing (entry/exit dissolves). Text is
        intentionally NOT painted here — the dissolve looks cleaner with
        just the gif, and there's no scroll-position state at draw time.
        """
        del cursor_pos, kwargs

        real = unwrap_to_real(canvas)
        self._load(panel_w=real.width, panel_h=real.height)

        if not self._frames:
            return canvas, canvas.width

        self._paint_full(real, self._current_frame_idx)
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

        for _ in range(loops):
            for idx, (_pixels, duration_ms) in enumerate(self._frames):
                canvas.Clear()
                self._paint_full(canvas, idx)
                canvas = frame.matrix.SwapOnVSync(canvas)
                await asyncio.sleep(duration_ms / 1000)

        self._current_frame_idx = len(self._frames) - 1
        return canvas

    def _render_tick(
        self,
        canvas: Canvas,
        text_canvas: Canvas,
        frame_idx: int,
        scroll_pos: int,
        baseline_y: int,
        text_x_left: int,
        text_x_right: int,
    ) -> None:
        """Compose one frame: clear canvas, paint gif + text in the right
        order for the current `text_align`. Caller advances `scroll_pos`
        and swaps after this returns."""
        canvas.Clear()

        if self.text_align == "scroll":
            # Text under, gif on top with black pillars made transparent
            self._draw_text(text_canvas, scroll_pos, baseline_y, self.font_color)
            self._paint_skip_black(canvas, frame_idx)
        elif self.text_align == "scroll_over":
            # Gif under, text on top — text always visible as a marquee
            self._paint_full(canvas, frame_idx)
            self._draw_text(text_canvas, scroll_pos, baseline_y, self.font_color)
        else:
            # Static text: gif under, text on top
            self._paint_full(canvas, frame_idx)
            text_x = text_x_left if self.text_align == "left" else text_x_right
            self._draw_text(text_canvas, text_x, baseline_y, self.font_color)

    async def _play_with_text(
        self, real_canvas: Canvas, frame: Any, loop_count: int
    ) -> Canvas:
        loops = max(1, loop_count)
        canvas = real_canvas

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
        tick_ms = max(_MIN_SCROLL_SPEED_MS, self.scroll_speed_ms)
        n_ticks = max(1, total_ms // tick_ms)

        text_width = self._measure_text(text_canvas)
        text_x_left = _TEXT_EDGE_PADDING_PX
        text_x_right = max(
            _TEXT_EDGE_PADDING_PX,
            text_w - text_width - _TEXT_EDGE_PADDING_PX,
        )

        # Scroll setup. `scroll_direction = "left"` (default) starts text
        # off the right edge moving leftward → exits left, wraps back to
        # the right. "right" mirrors: starts off the left, moves right,
        # wraps back to the left.
        scrolling = self.text_align in ("scroll", "scroll_over")
        if not scrolling:
            scroll_pos = 0
            scroll_step = 0
        elif self.scroll_direction == "right":
            scroll_pos = -text_width
            scroll_step = 1
        else:  # "left"
            scroll_pos = text_w
            scroll_step = -1

        # If the user wants the text to traverse the panel at least N
        # times before the section transitions, extend the tick budget
        # accordingly. One traversal = `text_w + text_width` ticks (text
        # spans from one off-edge to the other). Gif keeps looping in
        # the background to fill the extended duration.
        if scrolling and self.text_loops > 0:
            ticks_per_text_loop = text_w + text_width
            n_ticks = max(n_ticks, self.text_loops * ticks_per_text_loop)

        for tick in range(n_ticks):
            elapsed_ms = tick * tick_ms
            frame_idx = self._frame_for_elapsed(elapsed_ms, loop_ms)
            self._render_tick(
                canvas,
                text_canvas,
                frame_idx,
                scroll_pos,
                baseline_y,
                text_x_left,
                text_x_right,
            )
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
                scroll_pos += scroll_step
                if scroll_step < 0 and scroll_pos + text_width <= 0:
                    scroll_pos = text_w  # text exited left → respawn right
                elif scroll_step > 0 and scroll_pos >= text_w:
                    scroll_pos = -text_width  # exited right → respawn left

        self._current_frame_idx = len(self._frames) - 1
        return canvas
