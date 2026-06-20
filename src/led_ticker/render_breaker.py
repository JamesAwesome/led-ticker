"""Run-scoped widget render circuit breaker.

A widget whose draw()/play() raises at render time is disabled (skipped) rather
than crashing or freezing the panel — extending plugin load-time isolation to
render time. State is keyed by id(widget): engine widgets are built once at
startup and persist for the run, so ids are stable and never reused.
"""

import logging
from typing import Any

from led_ticker import status_board

logger = logging.getLogger(__name__)


class RenderBreaker:
    def __init__(self) -> None:
        self.disabled: dict[int, str] = {}  # id(widget) -> "TypeName: message"

    def is_disabled(self, widget: Any) -> bool:
        return id(widget) in self.disabled

    def trip(self, widget: Any, exc: BaseException) -> None:
        """Disable a widget after a render error. First trip only: logs ERROR
        with traceback once and records to the status board; later calls for the
        same widget are no-ops (so a widget tripped mid-visit doesn't re-log)."""
        if id(widget) in self.disabled:
            return
        summary = f"{type(exc).__name__}: {exc}"
        self.disabled[id(widget)] = summary
        logger.error(
            "widget %s disabled after a render error: %s",
            type(widget).__name__,
            summary,
            exc_info=exc,
        )
        status_board.record_disabled_widget(widget, summary)
