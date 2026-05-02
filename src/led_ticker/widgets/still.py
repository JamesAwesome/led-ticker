"""Still-image widget — displays a single PNG / JPG / single-frame GIF
on the LED panel.

Counterpart to :class:`led_ticker.widgets.gif.GifPlayer` — see that file
for shared concept docs (text alignments, transparency compositing,
run_swap dispatch, native-resolution painting). Both widgets inherit
from :class:`led_ticker.widgets._image_base._BaseImageWidget` so the
text-overlay surface is identical; the only widget-specific knobs are
``hold_seconds`` (this widget) vs ``gif_loops`` (gif).

Schema (TOML config keys for ``type = "image"``):

==================  =================  ==========================================
Field               Default            Description
==================  =================  ==========================================
``path``            (required)         Path to the image. Relative paths resolve
                                       against the config.toml directory.
``fit``             ``"pillarbox"``    ``pillarbox`` | ``letterbox`` | ``stretch``
                                       | ``crop``
``image_align``     ``"center"``       ``left`` | ``center`` | ``right`` —
                                       horizontal anchor; only meaningful for
                                       pillarbox.
``text``            ``""``             Optional text alongside the image.
                                       Supports ``:slug:`` inline emoji.
``text_align``      ``"auto"``         ``auto`` | ``left`` | ``right`` |
                                       ``scroll`` | ``scroll_over``. ``auto``
                                       picks the side opposite ``image_align``
                                       so they don't overlap (center → scroll_over).
``text_valign``     ``"center"``       ``top`` | ``center`` | ``bottom``.
``text_y_offset``   ``0``              Logical-pixel shift on baseline picked by
                                       ``text_valign``. Negative=up, positive=down.
``text_x_offset``   ``0``              Logical-pixel shift on static text x.
                                       Positive=right, negative=left. Rejected
                                       when used with scroll modes.
``scroll_direction`` ``"left"``        Direction marquee TRAVELS (left=enters
                                       from right edge, exits left).
``font_color``      yellow             RGB list ``[r, g, b]`` or ``"random"``.
``scroll_speed_ms`` ``50``             Tick cadence when text scrolls (≥ 20).
``text_scale``      ``1``              Block-scale text glyphs (1=native; 2-4
                                       on bigsign for distance readability).
``hold_seconds``    ``5.0``            Per-visit display duration. With
                                       ``text_loops > 0`` becomes a duration
                                       FLOOR: section runs for
                                       ``max(hold_seconds, text_loops × traversal)``.
                                       (Gif widget uses ``gif_loops`` instead.)
``text_loops``      ``0``              Floor on marquee passes before
                                       transitioning. Only meaningful for
                                       scrolling text.
==================  =================  ==========================================

``text_align="auto"`` resolution: ``image_align="left" → text_align="right"``,
``image_align="right" → "left"``, ``image_align="center" → "scroll_over"``
(centered image has no opposite pillar, so we put text over the gif).

Constraints validated at construction:
    - ``text_scale >= 1``
    - ``hold_seconds >= 0.05``
    - ``text_loops >= 0``
    - ``scroll_speed_ms >= 20``
    - ``text_loops > 0`` requires ``text_align`` ∈ ``{scroll, scroll_over}``
    - ``text_x_offset != 0`` requires ``text_align`` ∈ ``{left, right}``
      (scroll modes ignore the static-x offset; raising surfaces silent
      no-ops to the user)
    - ``text_align="scroll"`` requires ``fit != "stretch"`` (scroll relies
      on transparent / pillarbox regions for skip-black to expose text)

Validated at first paint (panel dims unknown until then):
    - ``panel_h // text_scale >= 12`` (BDF cell needs 12 logical rows)
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import attrs
from PIL import Image

from led_ticker._types import Canvas, DrawResult
from led_ticker.scaled_canvas import unwrap_to_real
from led_ticker.widgets import register
from led_ticker.widgets._image_base import HOLD_SECONDS_FLOOR, _BaseImageWidget
from led_ticker.widgets._image_fit import (
    VALID_FITS,
    VALID_IMAGE_ALIGNS,
    apply_fit,
    scan_non_black,
    validate_choice,
)


def _decode_still(
    path: Path,
    panel_w: int,
    panel_h: int,
    fit: str,
    image_align: str,
) -> bytes:
    """Decode a single image to panel-sized RGB bytes.

    Accepts any Pillow-supported format (PNG / JPG / single-frame GIF /
    etc). For animated sources only frame 0 is decoded — use the gif
    widget for animation. Transparent regions composite onto black so
    the existing skip-black scroll path exposes them.
    """
    validate_choice("fit", fit, VALID_FITS)
    validate_choice("image_align", image_align, VALID_IMAGE_ALIGNS)

    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"image not found at {path}")

    with Image.open(path) as img:
        # `seek(0)` is required for animated sources to pin frame 0; for
        # single-frame formats it's a no-op (skipped via the n_frames
        # guard since some PIL backends throw EOFError on seek for
        # genuinely-single-frame files).
        if getattr(img, "n_frames", 1) > 1:
            img.seek(0)
        rgba = img.convert("RGBA")
        return apply_fit(rgba, panel_w, panel_h, fit, image_align).tobytes()


@register("image")
@attrs.define
class StillImage(_BaseImageWidget):
    """Single-image widget. See module docstring for schema."""

    path: str
    fit: str = "pillarbox"
    image_align: str = "center"
    hold_seconds: float = 5.0

    # Single decoded frame (panel_w * panel_h * 3 RGB bytes)
    _pixels: bytes = attrs.field(init=False, default=b"")
    # Derived caches built lazily by `_ensure_paint_caches`
    _pil_image: Any = attrs.field(init=False, default=None)
    _non_black: list[tuple[int, int, int, int, int]] = attrs.field(
        init=False, factory=list
    )

    def __attrs_post_init__(self) -> None:
        self._validate_common(image_align=self.image_align, fit=self.fit)
        if self.hold_seconds < HOLD_SECONDS_FLOOR:
            raise ValueError(
                f"hold_seconds must be >= {HOLD_SECONDS_FLOOR}, "
                f"got {self.hold_seconds!r}"
            )

    def _load(self, panel_w: int = 0, panel_h: int = 0) -> None:
        """Decode the image. Re-decodes when panel dims differ from the
        cached decode (handles a widget reused across small/big sign
        sections — wouldn't happen in practice but defensively correct)."""
        if panel_w <= 0:
            panel_w = self._panel_w or 256
        if panel_h <= 0:
            panel_h = self._panel_h or 64
        if self._pixels and self._panel_w == panel_w and self._panel_h == panel_h:
            return
        self._panel_w = panel_w
        self._panel_h = panel_h
        self._pixels = _decode_still(
            Path(self.path),
            panel_w=panel_w,
            panel_h=panel_h,
            fit=self.fit,
            image_align=self.image_align,
        )
        # Invalidate derived caches when re-decoded
        self._pil_image = None
        self._non_black = []

    def _ensure_paint_caches(self) -> None:
        """Build PIL image + non-black pixel list from decoded bytes."""
        if self._pil_image is not None:
            return
        if not self._pixels or self._panel_w <= 0 or self._panel_h <= 0:
            return
        self._pil_image = Image.frombytes(
            "RGB", (self._panel_w, self._panel_h), self._pixels
        )
        self._non_black = scan_non_black(self._pixels, self._panel_w, self._panel_h)

    # ------------------------------------------------------------------
    # _BaseImageWidget hook implementations
    # ------------------------------------------------------------------

    def _paint_full(self, canvas: Canvas) -> None:
        """Paint the image (including any black pillars) via SetImage."""
        self._ensure_paint_caches()
        if self._pil_image is not None:
            canvas.SetImage(self._pil_image, 0, 0)

    def _paint_skip_black(self, canvas: Canvas) -> None:
        """Paint non-black pixels only — leaves underlying canvas
        content (e.g. pre-painted scrolling text) showing through
        pillars / letterbox / transparent regions."""
        self._ensure_paint_caches()
        set_px = canvas.SetPixel
        for x, y, r, g, b in self._non_black:
            set_px(x, y, r, g, b)

    # ------------------------------------------------------------------
    # Widget protocol + per-section orchestration
    # ------------------------------------------------------------------

    def draw(self, canvas: Canvas, cursor_pos: int = 0, **kwargs: Any) -> DrawResult:
        """Paint the image to the real canvas at native res. Used for
        transition compositing only (text is not painted here — see
        :meth:`GifPlayer.draw` for rationale)."""
        del cursor_pos, kwargs
        real = unwrap_to_real(canvas)
        self._load(panel_w=real.width, panel_h=real.height)
        if self._pixels:
            self._paint_full(real)
        return canvas, canvas.width

    async def play(
        self,
        real_canvas: Canvas,
        frame: Any,
        loop_count: int = 1,
    ) -> Canvas:
        """Run the visit loop. Without text: paint once, hold for
        ``hold_seconds``. With text: per-tick scroll loop (fast-pathed
        to a single paint + sleep when text is static), with
        ``hold_seconds`` as a duration floor and ``text_loops`` as a
        traversal floor.

        ``loop_count`` is unused; ``hold_seconds`` controls duration.
        Accepted for compatibility with the ``_play_widget`` dispatch
        signature in run_swap. The gif widget is the one that uses
        ``loop_count`` (mapped from its ``gif_loops`` field).
        """
        del loop_count
        self._load(panel_w=real_canvas.width, panel_h=real_canvas.height)
        if not self._pixels:
            return real_canvas

        if not self.text:
            return await self._play_no_text(real_canvas, frame)
        # Compute n_ticks from hold_seconds; the base class loop applies
        # the text_loops floor and the static-text fast path internally.
        from led_ticker.widgets._image_base import MIN_SCROLL_SPEED_MS

        tick_ms = max(MIN_SCROLL_SPEED_MS, self.scroll_speed_ms)
        n_ticks = max(1, int(self.hold_seconds * 1000) // tick_ms)
        return await self._play_with_text(real_canvas, frame, n_ticks)

    async def _play_no_text(self, real_canvas: Canvas, frame: Any) -> Canvas:
        canvas = real_canvas
        canvas.Clear()
        self._paint_full(canvas)
        canvas = frame.matrix.SwapOnVSync(canvas)
        await asyncio.sleep(self.hold_seconds)
        return canvas
