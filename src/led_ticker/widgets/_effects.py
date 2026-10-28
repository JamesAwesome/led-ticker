"""Shared paint helpers for the per-widget effect slots.

``paint_background`` is the ONE place a widget paints its ``background``
effect, so the z-order contract (background → image → border → text) and the
per-effect counter (``frame_for("background")``) can't drift between the
seven host widgets' render paths. Call it right after the canvas reset and
before anything else is painted.
"""

from typing import Any


def paint_background(widget: Any, canvas: Any) -> None:
    """Paint ``widget.background`` (if any) onto ``canvas`` with the widget's
    per-effect frame counter. No-op for widgets without the field or with
    ``background = None``."""
    bg = getattr(widget, "background", None)
    if bg is None:
        return
    bg.paint(canvas, widget.frame_for("background"))


def background_is_static(widget: Any) -> bool:
    """``True`` when the widget's background (if any) is frame-invariant —
    the fast-path gate term, same shape as the ``border`` one."""
    bg = getattr(widget, "background", None)
    return getattr(bg, "frame_invariant", True) if bg is not None else True
