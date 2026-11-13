"""Shared paint helpers for the per-widget effect slots.

``paint_background`` is the ONE place a widget paints its ``background``
effect, so the z-order contract (background → image → border → text) and the
per-effect counter (``frame_for("background")``) can't drift between the
seven host widgets' render paths. Call it right after the canvas reset and
before anything else is painted.

It is also where a background learns the section's LOGICAL SCALE on every
host. Text hosts already draw on the ``ScaledCanvas`` from ``_maybe_wrap``
(so ``canvas.scale`` is there); image hosts paint on the UNWRAPPED real
canvas (image pixels map 1:1 to LEDs) and only carry the scale as the
``_logical_scale`` field the engine stashes before ``play()``. Rather than
teach every background plugin to guess, ``paint_background`` re-wraps the
real canvas at that scale so a background sees the same kind of canvas on
all hosts and can keep using ``is_scaled`` / ``canvas.scale`` /
``paint_hires`` / ``unwrap_to_real`` (#535). The wrapper spans the FULL
panel (``content_height = real.height // scale``), not the section's
content band — a background is a full-panel effect.
"""

from typing import Any

from led_ticker.scaled_canvas import ScaledCanvas, is_scaled


def _background_canvas(widget: Any, canvas: Any) -> Any:
    """The canvas a background effect should be handed for ``widget``.

    Already-scaled canvases (text hosts) pass through untouched; a raw
    canvas on a host with ``_logical_scale > 1`` (image hosts on a scaled
    sign) is wrapped at that scale over the full panel. Everything else
    (scale 1, or a host without the field) is the raw canvas.
    """
    if is_scaled(canvas):
        return canvas
    scale = getattr(widget, "_logical_scale", 1)
    if scale <= 1:
        return canvas
    return ScaledCanvas(canvas, scale=scale, content_height=canvas.height // scale)


def paint_background(widget: Any, canvas: Any) -> None:
    """Paint ``widget.background`` (if any) onto ``canvas`` with the widget's
    per-effect frame counter. No-op for widgets without the field or with
    ``background = None``. See the module docstring for why a raw canvas is
    re-wrapped at the host's ``_logical_scale`` before the effect sees it."""
    bg = getattr(widget, "background", None)
    if bg is None:
        return
    bg.paint(_background_canvas(widget, canvas), widget.frame_for("background"))


def background_is_static(widget: Any) -> bool:
    """``True`` when the widget's background (if any) is frame-invariant —
    the fast-path gate term, same shape as the ``border`` one."""
    bg = getattr(widget, "background", None)
    return getattr(bg, "frame_invariant", True) if bg is not None else True
