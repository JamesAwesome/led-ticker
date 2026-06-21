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
