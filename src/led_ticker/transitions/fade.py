"""`fade`: crossfade between two widgets, or a dip through a colour.

Design: ``docs/superpowers/specs/2026-11-21-fade-design.md``.

Mechanism: on the first ``frame_at`` of a firing, draw the outgoing widget
(at the live geometry, at ``outgoing_scroll_pos``) and the incoming widget
(at the incoming section's geometry) ONCE each into an owned readable raster
(``rotate.PixelBuffer``), convert both to Pillow ``RGB`` images the size of
the real panel, then per frame ``Image.blend`` the two and ``SetImage`` the
result onto the real canvas in one call. With ``transition_color`` set the
first half blends outgoing -> colour and the second half colour -> incoming
(a dip); without it the two snapshots blend directly (a mix). ``end_firing``
(called by the runner in its ``finally``, forwarded by the ``random`` /
``auto`` wrapper) releases the snapshots.

Invariant: the fade's OWN code never raises out of ``frame_at`` (it is
unguarded; only the widget draws sit behind the breaker). The four raise
points and where each is closed:

1. the rgbmatrix ``SetImage`` rejects a non-``RGB`` image: every image here
   is built as ``RGB``;
2. ``Image.blend`` rejects a size mismatch: every image is exactly
   ``(real.width, real.height)``;
3. ``Image.new`` / ``PixelBuffer.Fill`` reject a malformed colour: the
   through colour is refused in the constructor (``rgb_shape_error``), so
   the guarded builder cuts, and a section bg is coerced or dropped by
   ``_norm_bg`` (it reaches the runner un-validated);
4. the raster -> bytes conversion rejects a widget-sourced non-int or
   out-of-range channel (``PixelBuffer`` stores whatever a widget passes):
   the conversion runs inside ``_snapshot``'s try/except and trips the widget
   through the breaker helpers.

No software gamma: the rgbmatrix fork maps every value through the inverse
CIE 1931 L* table at ``SetPixel`` time, so an 8-bit ramp is already
lightness-linear.
"""

import logging
import time
from typing import Any

from PIL import Image

from led_ticker._types import Canvas, ColorTuple
from led_ticker.colors import rgb_shape_error
from led_ticker.render_breaker import transition_draw_tripped, trip_transition_draw
from led_ticker.rotate import PixelBuffer
from led_ticker.scaled_canvas import is_scaled, unwrap_to_real
from led_ticker.ticker import _maybe_wrap
from led_ticker.transitions import register_transition

logger = logging.getLogger(__name__)

_BLACK = b"\0\0\0"


def _geometry(canvas: Any) -> tuple[int, int] | None:
    """``(scale, content_height)`` of a wrapped canvas, ``None`` for a raw one."""
    if is_scaled(canvas):
        return (canvas.scale, canvas.content_height)
    return None


def _wrap(buf: PixelBuffer, geometry: tuple[int, int] | None) -> Any:
    return buf if geometry is None else _maybe_wrap(buf, geometry[0], geometry[1])


def _buffer_to_image(buf: PixelBuffer) -> Image.Image:
    """One ``frombytes`` over the buffer; an unset slot is black. A slot
    holding a non-int or out-of-range channel raises here (``bytes`` refuses
    it), which is raise point 4 above."""
    data = b"".join(_BLACK if p is None else bytes(p) for p in buf._pixels)
    return Image.frombytes("RGB", (buf.width, buf.height), data)


def _norm_bg(bg: Any) -> ColorTuple | None:
    """A section bg reaches the runner un-validated (`_normalize_bg` passes
    lists and floats through); coerce it to three ints 0..255 or fall back to
    black, so neither `Fill` nor `Image.new` can raise on it."""
    if bg is None:
        return None
    try:
        r, g, b = (int(c) for c in bg)
    except TypeError, ValueError:
        logger.warning("fade: ignoring malformed bg colour %r", bg)
        return None
    if not all(0 <= c <= 255 for c in (r, g, b)):
        logger.warning("fade: ignoring out-of-range bg colour %r", bg)
        return None
    return (r, g, b)


def _bg_image(size: tuple[int, int], bg: ColorTuple | None) -> Image.Image:
    return Image.new("RGB", size, bg or (0, 0, 0))


def _snapshot(
    widget: Any,
    real: Any,
    bg: ColorTuple | None,
    geometry: tuple[int, int] | None,
    cursor_pos: int,
) -> Image.Image:
    """Draw ``widget`` once into a fresh raster at ``geometry`` and return it
    as an RGB image. Draw AND conversion share one try/except: a widget that
    raises mid-draw, or whose pixel values only fail at conversion, is tripped
    through its guard and replaced by its bg; with no guard (``breaker=None``,
    programmatic callers) the error propagates."""
    size = (real.width, real.height)
    bg = _norm_bg(bg)
    buf = PixelBuffer(*size)
    if bg is not None:
        buf.Fill(*bg)
    # The wrapper is built OUTSIDE the try: a geometry the panel cannot hold
    # (content_height * scale > rows) is a config error the runner's own
    # re-wrap raises on for every switching transition, never the widget's.
    target = _wrap(buf, geometry)
    try:
        widget.draw(target, cursor_pos=cursor_pos)
        if transition_draw_tripped(widget):
            # The guard swallowed a mid-draw raise and painted nothing more;
            # the per-frame reset that normally hides a partial frame does
            # not apply to a snapshot taken once.
            return _bg_image(size, bg)
        return _buffer_to_image(buf)
    except Exception as exc:
        if trip_transition_draw(widget, exc):
            inner = getattr(widget, "_widget", widget)  # the guard's slot
            logger.debug("fade: snapshot of %s tripped: %r", type(inner).__name__, exc)
            return _bg_image(size, bg)
        raise


@register_transition("fade")
class Fade:
    """Crossfade; ``transition_color`` turns it into a dip through that colour."""

    min_frames = 8  # 0.4 s at the default 50 ms tick

    def __init__(self, color: ColorTuple | None = None, **kwargs: Any) -> None:
        if color:  # falsy ([] -> ()) is the mix
            msg = rgb_shape_error(color)
            if msg is not None:
                raise ValueError(f"fade: transition_color: {msg}")
            self.through: ColorTuple | None = (color[0], color[1], color[2])
        else:
            self.through = None
        self._out_img: Image.Image | None = None
        self._in_img: Image.Image | None = None
        self._key: tuple[Any, Any] | None = None
        self._through_cache: dict[tuple[int, int], Image.Image] = {}
        self._frames = 0
        self._t0 = 0.0

    # -- snapshots -------------------------------------------------------------

    def _ensure_snapshots(
        self, canvas: Any, outgoing: Any, incoming: Any, kwargs: dict[str, Any]
    ) -> None:
        if (
            self._out_img is not None
            and self._key is not None
            and self._key[0] is outgoing
            and self._key[1] is incoming
        ):
            return
        started = time.perf_counter()
        real = unwrap_to_real(canvas)
        live = _geometry(canvas)
        incoming_scale = kwargs.get("incoming_scale")
        incoming_geometry = (
            (incoming_scale, kwargs.get("incoming_content_height", 16))
            if incoming_scale is not None
            else live
        )
        self._out_img = _snapshot(
            outgoing,
            real,
            kwargs.get("outgoing_bg_color"),
            live,
            kwargs.get("outgoing_scroll_pos", 0),
        )
        self._in_img = _snapshot(
            incoming, real, kwargs.get("incoming_bg_color"), incoming_geometry, 0
        )
        self._key = (outgoing, incoming)
        self._frames = 0
        self._t0 = started
        logger.debug(
            "fade: snapshot %dx%d in %.1f ms",
            real.width,
            real.height,
            (time.perf_counter() - started) * 1000,
        )

    def _through_image(self, size: tuple[int, int]) -> Image.Image:
        img = self._through_cache.get(size)
        if img is None:
            assert self.through is not None
            img = Image.new("RGB", size, self.through)
            self._through_cache[size] = img
        return img

    # -- protocol ----------------------------------------------------------------

    def frame_at(
        self, t: float, canvas: Canvas, outgoing: Any, incoming: Any, **kwargs: Any
    ) -> Canvas:
        self._ensure_snapshots(canvas, outgoing, incoming, kwargs)
        assert self._out_img is not None and self._in_img is not None
        k = min(1.0, max(0.0, t))  # plugin easings may overshoot
        if self.through is None:
            img = Image.blend(self._out_img, self._in_img, k)
        else:
            through = self._through_image(self._out_img.size)
            if k < 0.5:
                img = Image.blend(self._out_img, through, 2 * k)
            else:
                img = Image.blend(through, self._in_img, 2 * k - 1)
        unwrap_to_real(canvas).SetImage(img, 0, 0)
        self._frames += 1
        return canvas

    def end_firing(self) -> None:
        """Release the snapshots (the runner calls this in its ``finally``; the
        meta wrapper forwards it). The through image stays cached."""
        if self._out_img is not None:
            logger.debug(
                "fade: firing done, %d frames, %.1f ms",
                self._frames,
                (time.perf_counter() - self._t0) * 1000,
            )
        self._out_img = None
        self._in_img = None
        self._key = None
        self._frames = 0
