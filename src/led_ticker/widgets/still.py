"""Still-image widget — displays a single PNG / JPG / etc on the LED panel.

Mirrors the gif widget's TOML feature surface: same fit modes
(pillarbox/letterbox/stretch/crop), same `gif_align`, same text-overlay
options (text, text_align/valign, text_scale, text_loops,
scroll_direction, scroll_speed_ms, font_color), same alpha-aware
transparent decoding. Differences:

  - One frame, no animation timing. `play()` paints the image and
    holds for `hold_seconds` (or longer if `text_loops` floor demands).
  - No `gif_loops` (no per-visit repetition — `hold_seconds` controls
    duration directly).
  - In `mode = "swap"` it dispatches via `_has_play` like gifs do, so
    optional section titles and inter-section transitions all work
    identically.

Schema (TOML config keys for `type = "image"`):

==================  =================  ==========================================
Field               Default            Description
==================  =================  ==========================================
``path``            (required)         Path to the image. Relative paths resolve
                                       against the config.toml directory.
``fit``             ``"pillarbox"``    ``pillarbox`` | ``letterbox`` | ``stretch``
                                       | ``crop``
``gif_align``       ``"center"``       Horizontal anchor for pillarbox.
``text``            ``""``             Optional text alongside the image.
                                       Supports ``:slug:`` inline emoji.
``text_align``      ``"auto"``         ``auto`` | ``left`` | ``right`` |
                                       ``scroll`` | ``scroll_over``.
``text_valign``     ``"center"``       ``top`` | ``center`` | ``bottom``.
``text_y_offset``   ``0``              Logical-pixel shift added to the baseline
                                       picked by `text_valign`. Negative = up,
                                       positive = down. For nudging caps flush
                                       against the panel edge past the BDF
                                       cell's intrinsic top padding.
``scroll_direction`` ``"left"``        Direction marquee TRAVELS.
``font_color``      yellow             RGB list ``[r, g, b]`` or "random".
``scroll_speed_ms`` ``50``             Tick cadence when text scrolls (≥ 20).
``text_scale``      ``1``              Block-scale text glyphs (1=native; 2-4
                                       on bigsign for distance readability).
``hold_seconds``    ``5.0``            How long to display when no scrolling
                                       text. With scrolling text, sets a
                                       MINIMUM duration the section runs.
``text_loops``      ``0``              Floor on marquee passes before
                                       transitioning. Only meaningful for
                                       scrolling text.
==================  =================  ==========================================

See `gif.py` for shared concept docs (text alignments, transparency
compositing, run_swap dispatch).
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
from led_ticker.widgets._image_fit import _VALID_GIF_ALIGNS, validate_choice
from led_ticker.widgets._still_decode import decode_still

_VALID_TEXT_ALIGNS: frozenset[str] = frozenset(
    {"left", "right", "scroll", "scroll_over"}
)
_VALID_TEXT_VALIGNS: frozenset[str] = frozenset({"top", "center", "bottom"})
_VALID_SCROLL_DIRECTIONS: frozenset[str] = frozenset({"left", "right"})

# `text_align="auto"` resolves to the side opposite the image so they
# don't overlap. Centered image → scroll_over (always paints over,
# guaranteed no overlap zone).
_AUTO_TEXT_ALIGN_FOR_GIF: dict[str, str] = {
    "left": "right",
    "right": "left",
    "center": "scroll_over",
}
_EMOJI_PATTERN = re.compile(r":[a-z_]+:")

_TEXT_EDGE_PADDING_PX: int = 2
_MIN_SCROLL_SPEED_MS: int = 20


@register("image")
@attrs.define
class StillImage:
    """Single-image widget. See module docstring for schema."""

    path: str
    fit: str = "pillarbox"
    gif_align: str = "center"
    text: str = ""
    text_align: str = "auto"
    text_valign: str = "center"
    # Logical-pixel adjustment added to the baseline that `text_valign`
    # picks. Negative shifts text UP, positive DOWN. Useful when the
    # font's intrinsic cell-padding leaves caps a few rows below the
    # panel edge at `text_valign="top"` and you want them flush.
    text_y_offset: int = 0
    scroll_direction: str = "left"
    font_color: Color = attrs.Factory(lambda: DEFAULT_COLOR)
    scroll_speed_ms: int = 50
    text_scale: int = 1
    text_loops: int = 0
    hold_seconds: float = 5.0
    # Framework-internal; not user-facing TOML
    font: Font = attrs.field(init=False, default=FONT_DEFAULT)
    padding: int = attrs.field(init=False, default=0)

    # Single decoded frame (panel_w * panel_h * 3 RGB bytes)
    _pixels: bytes = attrs.field(init=False, default=b"")
    _panel_w: int = attrs.field(init=False, default=0)
    _panel_h: int = attrs.field(init=False, default=0)
    # Derived caches built lazily by `_ensure_paint_caches`
    _pil_image: Any = attrs.field(init=False, default=None)
    _non_black: list[tuple[int, int, int, int, int]] = attrs.field(
        init=False, factory=list
    )

    def __attrs_post_init__(self) -> None:
        validate_choice("gif_align", self.gif_align, _VALID_GIF_ALIGNS)
        if self.text_align == "auto":
            self.text_align = _AUTO_TEXT_ALIGN_FOR_GIF[self.gif_align]
        if self.text:
            validate_choice("text_align", self.text_align, _VALID_TEXT_ALIGNS)
        validate_choice("text_valign", self.text_valign, _VALID_TEXT_VALIGNS)
        validate_choice(
            "scroll_direction", self.scroll_direction, _VALID_SCROLL_DIRECTIONS
        )
        if self.text_scale < 1:
            raise ValueError(f"text_scale must be >= 1, got {self.text_scale!r}")
        if self.text_loops < 0:
            raise ValueError(f"text_loops must be >= 0, got {self.text_loops!r}")
        if self.scroll_speed_ms < _MIN_SCROLL_SPEED_MS:
            raise ValueError(
                f"scroll_speed_ms must be >= {_MIN_SCROLL_SPEED_MS}, "
                f"got {self.scroll_speed_ms!r}"
            )
        if self.hold_seconds < 0:
            raise ValueError(f"hold_seconds must be >= 0, got {self.hold_seconds!r}")
        if self.text_loops > 0 and self.text_align in ("left", "right"):
            raise ValueError(
                f"text_loops > 0 only applies when text_align is 'scroll' "
                f"or 'scroll_over'; got text_align={self.text_align!r}"
            )

    def _load(self, panel_w: int = 0, panel_h: int = 0) -> None:
        """Decode the image. Idempotent — second call is a no-op."""
        if self._pixels:
            return
        if panel_w <= 0:
            panel_w = self._panel_w or 256
        if panel_h <= 0:
            panel_h = self._panel_h or 64
        self._panel_w = panel_w
        self._panel_h = panel_h
        self._pixels = decode_still(
            Path(self.path),
            panel_w=panel_w,
            panel_h=panel_h,
            fit=self.fit,
            gif_align=self.gif_align,
        )

    def _ensure_paint_caches(self) -> None:
        """Build PIL image + non-black pixel list from decoded bytes.
        Idempotent. Built lazily so tests that synthesize `_pixels`
        directly still get the derived caches."""
        if self._pil_image is not None:
            return
        if not self._pixels or self._panel_w <= 0 or self._panel_h <= 0:
            return
        from PIL import Image

        self._pil_image = Image.frombytes(
            "RGB", (self._panel_w, self._panel_h), self._pixels
        )
        nb: list[tuple[int, int, int, int, int]] = []
        w, h = self._panel_w, self._panel_h
        pixels = self._pixels
        for y in range(h):
            row = y * w * 3
            for x in range(w):
                base = row + x * 3
                r = pixels[base]
                g = pixels[base + 1]
                b = pixels[base + 2]
                if r or g or b:
                    nb.append((x, y, r, g, b))
        self._non_black = nb

    def _paint_full(self, canvas: Canvas) -> None:
        """Paint the image (including any black pillars) via SetImage —
        a single C call into rgbmatrix that pushes the whole RGB buffer
        in one shot."""
        self._ensure_paint_caches()
        if self._pil_image is not None:
            canvas.SetImage(self._pil_image, 0, 0)

    def _paint_skip_black(self, canvas: Canvas) -> None:
        """Paint non-black pixels only — leaves underlying canvas
        content (e.g. pre-painted scrolling text) showing through
        pillars / letterbox bands / transparent areas."""
        self._ensure_paint_caches()
        set_px = canvas.SetPixel
        for x, y, r, g, b in self._non_black:
            set_px(x, y, r, g, b)

    def _baseline_y(self, h: int) -> int:
        """BDF baseline anchored per `text_valign`, plus `text_y_offset`.

        FONT_DEFAULT is 6×12 with 10 ascent + 2 descent. The valign
        modes give logical-pixel anchors; `text_y_offset` shifts them
        further (negative = up, positive = down)."""
        if self.text_valign == "top":
            base = 10
        elif self.text_valign == "bottom":
            base = h - 2
        else:
            base = (h - 12) // 2 + 10
        return base + self.text_y_offset

    def _has_emoji(self) -> bool:
        return bool(_EMOJI_PATTERN.search(self.text))

    def _measure_text(self, canvas: Canvas) -> int:
        if self._has_emoji():
            from led_ticker.pixel_emoji import measure_width

            return measure_width(self.font, self.text, canvas=canvas)
        return get_text_width(self.font, self.text, padding=0)

    def _draw_text(self, canvas: Canvas, x: int, baseline_y: int, color: Color) -> int:
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
        """Paint the image to the real canvas at native res. Used for
        transition compositing — text is intentionally skipped here
        (see GifPlayer.draw for rationale)."""
        del cursor_pos, kwargs
        real = unwrap_to_real(canvas)
        self._load(panel_w=real.width, panel_h=real.height)
        if self._pixels:
            self._paint_full(real)
        return canvas, canvas.width

    def _render_tick(
        self,
        canvas: Canvas,
        text_canvas: Canvas,
        scroll_pos: int,
        baseline_y: int,
        text_x_left: int,
        text_x_right: int,
    ) -> None:
        """Compose one frame: clear canvas, paint image + text in the
        right order for the current `text_align`."""
        canvas.Clear()

        if self.text_align == "scroll":
            self._draw_text(text_canvas, scroll_pos, baseline_y, self.font_color)
            self._paint_skip_black(canvas)
        elif self.text_align == "scroll_over":
            self._paint_full(canvas)
            self._draw_text(text_canvas, scroll_pos, baseline_y, self.font_color)
        else:
            self._paint_full(canvas)
            text_x = text_x_left if self.text_align == "left" else text_x_right
            self._draw_text(text_canvas, text_x, baseline_y, self.font_color)

    async def play(
        self,
        real_canvas: Canvas,
        frame: Any,
        loop_count: int = 1,
    ) -> Canvas:
        """Run the visit loop. Without text: paint once, hold for
        `hold_seconds`. With text: per-tick scroll loop, with
        `hold_seconds` as a duration floor and `text_loops` as a
        traversal floor.

        `loop_count` is unused (StillImage has no per-visit repetition;
        `hold_seconds` controls duration directly). Accepted for
        compatibility with the `_play_widget` dispatch signature.
        """
        del loop_count  # unused; hold_seconds controls duration
        self._load(panel_w=real_canvas.width, panel_h=real_canvas.height)
        if not self._pixels:
            return real_canvas

        if not self.text:
            return await self._play_no_text(real_canvas, frame)
        return await self._play_with_text(real_canvas, frame)

    async def _play_no_text(self, real_canvas: Canvas, frame: Any) -> Canvas:
        canvas = real_canvas
        canvas.Clear()
        self._paint_full(canvas)
        canvas = frame.matrix.SwapOnVSync(canvas)
        await asyncio.sleep(self.hold_seconds)
        return canvas

    async def _play_with_text(self, real_canvas: Canvas, frame: Any) -> Canvas:
        canvas = real_canvas

        # When wrapping for text_scale > 1, span the FULL panel height in
        # logical units (`content_height = panel_h // scale`) rather than
        # the project default 16. Without this, the wrapper letterboxes
        # text to a centered band — "top" valign would land in the
        # middle of the panel, not at the top edge.
        text_canvas: Canvas = (
            ScaledCanvas(
                canvas,
                scale=self.text_scale,
                content_height=canvas.height // self.text_scale,
            )
            if self.text_scale > 1
            else canvas
        )
        text_w = text_canvas.width
        text_h = text_canvas.height
        baseline_y = self._baseline_y(text_h)

        tick_ms = max(_MIN_SCROLL_SPEED_MS, self.scroll_speed_ms)
        # Duration floor from hold_seconds
        n_ticks = max(1, int(self.hold_seconds * 1000) // tick_ms)

        text_width = self._measure_text(text_canvas)
        text_x_left = _TEXT_EDGE_PADDING_PX
        text_x_right = max(
            _TEXT_EDGE_PADDING_PX,
            text_w - text_width - _TEXT_EDGE_PADDING_PX,
        )

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

        # Marquee floor: at least N traversals across the panel
        if scrolling and self.text_loops > 0:
            ticks_per_text_loop = text_w + text_width
            n_ticks = max(n_ticks, self.text_loops * ticks_per_text_loop)

        for _tick in range(n_ticks):
            self._render_tick(
                canvas,
                text_canvas,
                scroll_pos,
                baseline_y,
                text_x_left,
                text_x_right,
            )
            canvas = frame.matrix.SwapOnVSync(canvas)
            # Keep text_canvas pointing at the new back-buffer (see
            # CLAUDE.md hardware constraint #10 / gif.py for the full
            # explanation of why this matters).
            if isinstance(text_canvas, ScaledCanvas):
                text_canvas.real = canvas
            else:
                text_canvas = canvas
            await asyncio.sleep(tick_ms / 1000)

            if scrolling:
                scroll_pos += scroll_step
                if scroll_step < 0 and scroll_pos + text_width <= 0:
                    scroll_pos = text_w
                elif scroll_step > 0 and scroll_pos >= text_w:
                    scroll_pos = -text_width

        return canvas
