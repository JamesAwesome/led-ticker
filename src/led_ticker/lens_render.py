"""Shared stationary-fisheye-lens text renderer (fisheye spec §2-§3).

Extracted from `widgets/message.py`'s `_draw_lensed`/`_lens_strip`/
`_lens_blit_dst` so image/gif widgets (Task 2) can reuse the exact same
geometry without duplicating it. Behavior is byte-for-byte the same as the
message-widget lens branch this replaces — see `tests/test_widgets/
test_message_lens.py` (the untouched behavioral net for this extraction)
and `tests/test_lens_render.py` (the renderer's own unit contract).
"""

import math
from collections.abc import Callable
from typing import Any

from led_ticker._types import Canvas
from led_ticker.drawing import compute_baseline
from led_ticker.fonts import font_line_height_logical
from led_ticker.rotate import PixelBuffer, build_lens_maps
from led_ticker.rotate import lens_blit as _lens_blit
from led_ticker.scaled_canvas import ScaledCanvas, unwrap_to_real


class LensTextRenderer:
    """Stationary-lens text renderer: owns the construct-once strip buffer,
    draw target, and blit wrapper; a widget owns one instance per lens-capable
    draw surface. Geometry policy is moved VERBATIM from message._draw_lensed
    (render_scale = max(1, scale // 2), derived blit_scale, center-anchored
    src_x0, strip margin, vertical-fit check)."""

    def __init__(self) -> None:
        # Construct-once lens strip: a render-resolution PixelBuffer the text
        # is drawn into fresh every tick (NO snapshot — colors stay live),
        # plus its draw target (a ScaledCanvas wrapper at render_scale, or
        # the bare buffer at render_scale==1). Keyed by
        # (strip_w, strip_h, render_scale); rebuilt on mismatch.
        # `_lens_blit_wrapper` is the construct-once dst wrapper for scaled
        # displays (`.real` rebound per call, RotationSurface discipline).
        self._lens_strip_buffer: Any = None
        self._lens_strip_target: Any = None
        self._lens_strip_key: tuple[int, int, int] | None = None
        self._lens_blit_wrapper: Any = None

    def draw(
        self,
        canvas: Canvas,
        lens: Any,
        *,
        font: Any,
        cursor_pos: int,
        owner_name: str,
        paint_strip: Callable[[Any, int, int, float], None],
        # paint_strip(strip_target, x_logical, strip_baseline, hires_downscale)
        blit: Callable[[Any, Any, Any, float, float], None] | None = None,
    ) -> None:
        """Render text through a stationary fisheye lens (spec §2-§3).

        The text is rasterized FRESH each tick into a render-resolution strip
        buffer (no snapshot — colors stay live), then inverse-mapped onto the
        canvas via ``lens_blit`` and the cached lens maps. Callers paint any
        border themselves BEFORE calling ``draw`` (border-before-text order
        is a widget-level concern, not this renderer's).

        ``blit`` defaults to the real ``lens_blit`` (from ``led_ticker.
        rotate``); callers that need to observe/intercept the blit call
        (e.g. a widget module's own patchable ``lens_blit`` global, as
        ``widgets/message.py`` forwards for its pre-extraction test suite)
        may pass an override — it's read at call time, not bound at import,
        so the widget's own currently-bound name (possibly monkeypatched)
        is honored.

        Resolution policy (spec §3, antagonist F2): the strip renders at
        ``render_scale = max(1, scale // 2)`` and the lens blit expands by
        ``blit_scale = scale // render_scale`` (DERIVED, never hardcoded).
        Bigsign (scale 4) -> render 2 / blit 2; scale 2 -> render 1 / blit 2;
        scale 3 -> render 1 / blit 3; scale 1 (smallsign) -> render 1 / blit 1
        (direct logical blit).
        """
        scale = getattr(canvas, "scale", 1)
        render_scale = max(1, scale // 2)
        blit_scale = scale // render_scale
        logical_h = canvas.height
        panel_w_render = canvas.width * render_scale
        panel_h_render = logical_h * render_scale

        # Vertical-fit check (band-fit policy): a bulge taller than the content
        # band would clip. Raise at first lensed draw, naming the widget.
        line_h_logical = font_line_height_logical(font, scale)
        if lens.magnify * line_h_logical > logical_h:
            raise ValueError(
                f"{owner_name}: fisheye magnify={lens.magnify} × font "
                f"line-height {line_h_logical} = "
                f"{lens.magnify * line_h_logical:.1f} exceeds the content "
                f"height {logical_h} — the bulged text would clip against the "
                f"panel. Lower magnify, use a shorter font, or raise "
                f"content_height."
            )

        maps = build_lens_maps(lens, panel_w_render)
        span = maps.total_src_span

        # src_x0 anchor (spec §2): center-anchored, ONE formula for held and
        # scroll. In RENDER-resolution text columns (cursor_pos × render_scale).
        # The strip is text-column-indexed; its column 0 = the largest
        # render_scale-multiple text column ≤ src_x0, so the text can be drawn
        # at an integer logical origin. The sub-render_scale remainder is
        # folded into the fractional src_x0 passed to lens_blit.
        src_x0_render = (panel_w_render / 2.0 - cursor_pos * render_scale) - span / 2.0
        base_units = math.floor(src_x0_render / render_scale)
        x_logical = -base_units
        src_x0_frac = src_x0_render - base_units * render_scale

        # Strip covers the [0, span] text window plus a render_scale margin for
        # the fractional shift and nearest-neighbor rounding.
        strip_w_render = int(math.ceil(span)) + 2 * render_scale + 2
        strip_buffer, strip_target = self._lens_strip(
            strip_w_render, panel_h_render, render_scale, logical_h
        )
        strip_buffer.clear()

        # Hi-res emoji render at their native physical_size, which is sized for
        # the REAL panel scale. The strip renders at render_scale (<= scale), so
        # a native sprite would be scale/render_scale times too tall and fill
        # the strip, leaving no headroom for the vertical magnification (the
        # top clips and never recovers). Downscale hi-res sprites by
        # render_scale/scale so they keep their real-panel logical size.
        hires_downscale = render_scale / scale if scale > render_scale else 1.0
        strip_baseline = compute_baseline(font, strip_target, valign="center")
        paint_strip(strip_target, x_logical, strip_baseline, hires_downscale)

        dst = self._lens_blit_dst(canvas, blit_scale, panel_h_render)
        blit_fn = blit if blit is not None else _lens_blit
        blit_fn(dst, strip_buffer, maps, src_x0_frac, panel_h_render / 2.0)

    def _lens_strip(
        self, width: int, height: int, render_scale: int, logical_h: int
    ) -> tuple[Any, Any]:
        """Return the (buffer, draw-target) pair, constructing once per dims.

        The draw target is a ``ScaledCanvas`` at ``render_scale`` (so the text
        helpers render into the buffer at reduced resolution) when
        ``render_scale > 1``, else the bare buffer (logical resolution). Mirror
        of ``RotationSurface``'s scale-1-vs-scaled target policy.
        """
        key = (width, height, render_scale)
        if self._lens_strip_key != key:
            buffer = PixelBuffer(width, height)
            if render_scale > 1:
                target: Any = ScaledCanvas(
                    buffer, scale=render_scale, content_height=logical_h
                )
            else:
                target = buffer
            self._lens_strip_buffer = buffer
            self._lens_strip_target = target
            self._lens_strip_key = key
        return self._lens_strip_buffer, self._lens_strip_target

    def _lens_blit_dst(
        self, canvas: Canvas, blit_scale: int, panel_h_render: int
    ) -> Any:
        """Return the lens_blit destination.

        ``blit_scale == 1`` (smallsign): blit directly to the real canvas.
        Otherwise blit through a construct-once ``ScaledCanvas`` at
        ``blit_scale`` whose ``.real`` is rebound to the live back buffer each
        call (one assignment — constraint #9 / RotationSurface discipline).
        """
        if blit_scale == 1:
            return canvas
        real = unwrap_to_real(canvas)
        wrapper = self._lens_blit_wrapper
        if (
            wrapper is None
            or wrapper.scale != blit_scale
            or wrapper.content_height != panel_h_render
        ):
            wrapper = ScaledCanvas(
                real, scale=blit_scale, content_height=panel_h_render
            )
            self._lens_blit_wrapper = wrapper
        else:
            wrapper.real = real
        return wrapper
