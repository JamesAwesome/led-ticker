"""Run-scoped widget render circuit breaker.

A widget whose draw()/play() raises at render time is disabled (skipped) rather
than crashing or freezing the panel — extending plugin load-time isolation to
render time. State is keyed by a content signature: content-bearing widgets
(including container stories rebuilt each refresh) key on (type, content) so a
recurring bad item is recognized across refreshes; content-less widgets fall
back to id() since they are long-lived top-level widgets with stable ids.
"""

import logging
from typing import Any

from led_ticker import status_board

logger = logging.getLogger(__name__)


def _key(widget: Any) -> object:
    """Stable identity for breaker state. Content-bearing widgets (incl. container
    stories rebuilt each refresh) key on (type, content) so a recurring bad item is
    recognized across refreshes; content-less widgets fall back to id() (they are
    long-lived top-level widgets with stable ids)."""
    content = (
        getattr(widget, "text", None)
        or getattr(widget, "top_text", None)
        or getattr(widget, "path", None)
    )
    if content:
        return (type(widget).__name__, str(content))
    return id(widget)


class RenderBreaker:
    def __init__(self) -> None:
        self.disabled: dict[object, str] = {}  # key -> "ExcType: message"

    def is_disabled(self, widget: Any) -> bool:
        return _key(widget) in self.disabled

    def trip(self, widget: Any, exc: BaseException) -> None:
        """Disable a widget after a render error. First trip only: logs ERROR
        with traceback once and records to the status board; later calls for the
        same widget (or a different object with the same content signature) are
        no-ops (so a widget tripped mid-visit doesn't re-log)."""
        k = _key(widget)
        if k in self.disabled:
            return
        summary = f"{type(exc).__name__}: {exc}"
        self.disabled[k] = summary
        logger.error(
            "widget %s disabled after a render error: %s",
            type(widget).__name__,
            summary,
            exc_info=exc,
        )
        status_board.record_disabled_widget(widget, summary)

    def reset(self) -> None:
        """Clear all disabled state — called on a successful config reload so a
        widget the user just fixed gets another chance (mirrors restart-to-retry)."""
        self.disabled.clear()


class _TransitionDrawGuard:
    """Wraps a widget so its draw() is guarded by the breaker during transition
    compositing. Used ONLY as the outgoing/incoming argument to a transition's
    frame_at / _draw_scroll_frame. Mirrors Ticker._safe_draw: a disabled widget
    renders nothing; a raising draw trips the widget and leaves the canvas
    unchanged (the per-frame reset + the next tick's reset_canvas wipe any partial
    frame). __getattr__ delegates every other attribute to the real widget."""

    __slots__ = ("_widget", "_breaker")

    def __init__(self, widget: Any, breaker: RenderBreaker) -> None:
        object.__setattr__(self, "_widget", widget)
        object.__setattr__(self, "_breaker", breaker)

    def draw(self, canvas: Any, *args: Any, **kwargs: Any) -> Any:
        widget = object.__getattribute__(self, "_widget")
        breaker = object.__getattribute__(self, "_breaker")
        if breaker.is_disabled(widget):
            return canvas, 0
        try:
            return widget.draw(canvas, *args, **kwargs)
        except Exception as exc:  # noqa: BLE001 - a transition draw must not freeze the panel
            breaker.trip(widget, exc)
            return canvas, 0

    def __getattr__(self, name: str) -> Any:
        return getattr(object.__getattribute__(self, "_widget"), name)


def guard_for_transition(widget: Any, breaker: RenderBreaker | None) -> Any:
    """Return a draw-guarded view of `widget` for transition compositing, or the
    widget unchanged when there is no breaker (programmatic/test callers)."""
    if breaker is None:
        return widget
    return _TransitionDrawGuard(widget, breaker)
